"""Export memories to .md files and import from .md files.

Export creates a human-readable directory structure.
Import reads markdown files back into the DB with batch embedding for speed.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import MEMORY_COLUMNS, row_to_dict, INSERT_MEMORY, SELECT_MEMORY_BY_ID
from memory_mcp.db.provenance import record_provenance
from memory_mcp.models import MemoryCategory

EXPORT_DIR_NAME = ".memory"


def export_memories(project: str, export_path: str) -> dict:
    """Export all active memories to a structured .md directory."""
    export_dir = Path(export_path).resolve() / EXPORT_DIR_NAME
    export_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection(project)
    rows = conn.execute(
        f"SELECT {MEMORY_COLUMNS} FROM memories WHERE status = 'active' ORDER BY category, title"
    ).fetchall()

    if not rows:
        return {"status": "ok", "exported": 0, "message": "No active memories to export."}

    memories_by_category: dict[str, list[dict]] = {}
    for row in rows:
        memory = row_to_dict(row)
        cat = memory["category"]
        if cat not in memories_by_category:
            memories_by_category[cat] = []
        memories_by_category[cat].append(memory)

    exported = 0
    for category, memories in memories_by_category.items():
        cat_dir = export_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for mem in memories:
            filename = _slugify_filename(mem["title"]) + ".md"
            filepath = cat_dir / filename
            content = _memory_to_markdown(mem)
            filepath.write_text(content, encoding="utf-8")
            exported += 1

    index_content = _create_index(project, memories_by_category)
    (export_dir / "MEMORY_INDEX.md").write_text(index_content, encoding="utf-8")

    readme = _create_export_readme(project)
    (export_dir / "README.md").write_text(readme, encoding="utf-8")

    return {
        "status": "ok",
        "exported": exported,
        "export_path": str(export_dir),
        "categories": {cat: len(mems) for cat, mems in memories_by_category.items()},
    }


def import_memories(project: str, import_path: str) -> dict:
    """Import memories from .md files with batch embedding for speed.

    Uses batch embedding (all texts at once) instead of one-by-one,
    and bulk SQL inserts instead of individual store_memory calls.
    """
    import_dir = Path(import_path).resolve() / EXPORT_DIR_NAME
    if not import_dir.is_dir():
        return {"error": f"No .memory directory found at {import_path}"}

    from memory_mcp.embeddings import embed_texts
    from memory_mcp.utils.text import prepare_embedding_text
    from memory_mcp.utils.extraction import generate_summary, extract_entities, calculate_expiry

    conn = get_connection(project)

    # Phase 1: Parse all files first
    new_memories = []
    update_memories = []
    skipped = 0
    errors = []

    for category_dir in import_dir.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue

        category = category_dir.name
        try:
            MemoryCategory(category)
        except ValueError:
            errors.append(f"Unknown category: {category}")
            continue

        for md_file in category_dir.glob("*.md"):
            try:
                parsed = _parse_markdown(md_file.read_text(encoding="utf-8"))
                if not parsed:
                    errors.append(f"Failed to parse: {md_file.name}")
                    continue

                memory_id = parsed.get("id")
                title = parsed.get("title", md_file.stem)
                content = parsed.get("content", "")
                tags = parsed.get("tags", [])
                priority = parsed.get("priority", 0)
                source = parsed.get("source", "import")
                metadata = parsed.get("metadata")

                if not content:
                    skipped += 1
                    continue

                # Check existing
                if memory_id:
                    existing = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()
                    if existing:
                        existing_dict = row_to_dict(existing)
                        if existing_dict["content"] != content or existing_dict["title"] != title:
                            update_memories.append({
                                "id": memory_id, "title": title, "content": content,
                                "tags": tags, "category": category,
                            })
                        else:
                            skipped += 1
                        continue

                new_memories.append({
                    "category": category, "title": title, "content": content,
                    "tags": tags, "priority": priority, "source": source,
                    "metadata": metadata,
                })

            except Exception as e:
                errors.append(f"{md_file.name}: {str(e)}")

    # Phase 2: Batch embed all new memories at once
    created = 0
    if new_memories:
        texts = [prepare_embedding_text(m["title"], m["content"]) for m in new_memories]
        embeddings = embed_texts(texts)  # Single batch call

        for mem, embedding in zip(new_memories, embeddings):
            try:
                memory_id = str(uuid.uuid4())
                summary = generate_summary(mem["title"], mem["content"])
                entities = extract_entities(f"{mem['title']} {mem['content']}")
                cat = MemoryCategory(mem["category"])
                priority = mem["priority"]
                if cat.value in ("mandatory_rules", "forbidden_rules"):
                    priority = max(priority, 2)
                expires_at = calculate_expiry(mem["category"], priority)

                conn.execute(INSERT_MEMORY, [
                    memory_id, mem["category"], mem["title"], mem["content"],
                    summary, mem["tags"] or [], json.dumps(mem["metadata"]) if mem["metadata"] else None,
                    embedding, "active", priority, mem["source"], [], entities, expires_at,
                ])
                record_provenance(project, memory_id, "create", {"source": "import"})
                created += 1
            except Exception as e:
                errors.append(f"Insert {mem['title']}: {str(e)}")

    # Phase 3: Batch embed updates
    updated = 0
    if update_memories:
        texts = [prepare_embedding_text(m["title"], m["content"]) for m in update_memories]
        embeddings = embed_texts(texts)

        for mem, embedding in zip(update_memories, embeddings):
            try:
                summary = generate_summary(mem["title"], mem["content"])
                entities = extract_entities(f"{mem['title']} {mem['content']}")
                conn.execute(
                    "UPDATE memories SET title=?, content=?, summary=?, entities=?, embedding=?, tags=?, updated_at=current_timestamp WHERE id=?",
                    [mem["title"], mem["content"], summary, entities, embedding, mem["tags"] or [], mem["id"]],
                )
                record_provenance(project, mem["id"], "update", {"source": "import"})
                updated += 1
            except Exception as e:
                errors.append(f"Update {mem['id']}: {str(e)}")

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors if errors else None,
        "message": f"Imported: {created} created, {updated} updated, {skipped} skipped.",
    }


# --- Helpers ---


def _slugify_filename(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:60]


def _memory_to_markdown(mem: dict) -> str:
    tags_str = ", ".join(mem.get("tags", []))
    entities_str = ", ".join(mem.get("entities", []))

    lines = [
        "---",
        f"id: {mem['id']}",
        f"category: {mem['category']}",
        f"title: \"{mem['title']}\"",
        f"status: {mem['status']}",
        f"priority: {mem['priority']}",
    ]
    if tags_str:
        lines.append(f"tags: [{tags_str}]")
    if entities_str:
        lines.append(f"entities: [{entities_str}]")
    if mem.get("source"):
        lines.append(f"source: {mem['source']}")
    if mem.get("expires_at"):
        lines.append(f"expires_at: {mem['expires_at']}")
    if mem.get("created_at"):
        lines.append(f"created_at: {mem['created_at']}")
    if mem.get("updated_at"):
        lines.append(f"updated_at: {mem['updated_at']}")
    if mem.get("metadata"):
        lines.append(f"metadata: {json.dumps(mem['metadata'])}")

    lines.extend(["---", "", f"# {mem['title']}", ""])
    if mem.get("summary"):
        lines.extend([f"> {mem['summary']}", ""])
    lines.extend([mem.get("content", ""), ""])
    if mem.get("related_ids"):
        lines.append("## Related")
        for rid in mem["related_ids"]:
            lines.append(f"- {rid}")
        lines.append("")
    return "\n".join(lines)


def _create_index(project: str, memories_by_category: dict[str, list[dict]]) -> str:
    total = sum(len(mems) for mems in memories_by_category.values())
    lines = [
        f"# Memory Index - {project}", "",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
        f"Total: {total} memories", "",
        "## Categories", "",
        "| Category | Count |", "|----------|-------|",
    ]
    for cat, mems in sorted(memories_by_category.items()):
        lines.append(f"| [{cat}](./{cat}/) | {len(mems)} |")
    lines.append("")

    for cat, mems in sorted(memories_by_category.items()):
        lines.extend([f"## {cat}", ""])
        for mem in mems:
            filename = _slugify_filename(mem["title"]) + ".md"
            summary = mem.get("summary", "")
            lines.append(f"- [{mem['title']}](./{cat}/{filename}) - {summary}")
        lines.append("")
    return "\n".join(lines)


def _create_export_readme(project: str) -> str:
    return f"""# Project Memory - {project}

This directory contains exported project memories from the Memory MCP Server.

## For People WITHOUT Memory MCP

You can read and edit these files directly:

- **MEMORY_INDEX.md** - Master index of all memories
- **<category>/<memory>.md** - Individual memory files organized by category

### Categories
- `mandatory_rules/` - Rules that MUST be followed
- `forbidden_rules/` - Things that must NOT be done
- `decision/` - Important decisions and their rationale
- `architecture/` - Architecture decisions and patterns
- `sprint/` - Sprint goals and progress
- `devops/` - DevOps configurations and notes

### Editing
Edit any .md file. Content between `---` markers is metadata. Memory content is below.

## For People WITH Memory MCP

Run `memory_import("{project}", "/path/to/project")` to sync changes back.
"""


def _parse_markdown(text: str) -> dict | None:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return None

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    result = {}
    for line in frontmatter_text.strip().split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            value = [item.strip() for item in inner.split(",")] if inner else []
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        result[key] = value

    content_lines = []
    skip_title = True
    skip_summary = False
    for line in body.split("\n"):
        if skip_title and line.startswith("# "):
            skip_title = False
            skip_summary = True
            continue
        if skip_summary:
            if line.startswith("> "):
                skip_summary = False
                continue
            elif line.strip() == "":
                continue
            else:
                skip_summary = False
        if line.startswith("## Related"):
            break
        content_lines.append(line)

    result["content"] = "\n".join(content_lines).strip()
    return result
