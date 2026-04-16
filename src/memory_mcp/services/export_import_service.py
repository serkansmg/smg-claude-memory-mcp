"""Export/import service - serialize memories to markdown + parse back."""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from memory_mcp.embeddings import embed_texts
from memory_mcp.exceptions import ExportImportError
from memory_mcp.models import Memory, MemoryCategory, MemoryFilter, Pagination, RULE_CATEGORIES
from memory_mcp.repositories import MemoryRepository, ProvenanceRepository
from memory_mcp.utils.extraction import calculate_expiry, extract_entities, generate_summary
from memory_mcp.utils.text import prepare_embedding_text

EXPORT_DIR_NAME = ".memory"


class ExportImportService:
    """Export memories to .md and import from .md files."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        provenance_repo: ProvenanceRepository,
    ):
        self._memory_repo = memory_repo
        self._provenance_repo = provenance_repo

    # ---------- Export ----------

    def export(self, project: str, export_path: str) -> dict:
        export_dir = Path(export_path).resolve() / EXPORT_DIR_NAME
        export_dir.mkdir(parents=True, exist_ok=True)

        memories, total = self._memory_repo.list(
            project, MemoryFilter(), Pagination(limit=500),
        )
        if not memories:
            return {"status": "ok", "exported": 0, "message": "No active memories to export."}

        by_category: dict[str, list[Memory]] = {}
        for mem in memories:
            by_category.setdefault(mem.category.value, []).append(mem)

        exported = 0
        for category, mems in by_category.items():
            cat_dir = export_dir / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            for mem in mems:
                filename = _slugify_filename(mem.title) + ".md"
                (cat_dir / filename).write_text(_memory_to_markdown(mem), encoding="utf-8")
                exported += 1

        (export_dir / "MEMORY_INDEX.md").write_text(
            _create_index(project, by_category), encoding="utf-8",
        )
        (export_dir / "README.md").write_text(
            _create_export_readme(project), encoding="utf-8",
        )

        return {
            "status": "ok",
            "exported": exported,
            "export_path": str(export_dir),
            "categories": {cat: len(m) for cat, m in by_category.items()},
        }

    # ---------- Import ----------

    def import_from(self, project: str, import_path: str) -> dict:
        import_dir = Path(import_path).resolve() / EXPORT_DIR_NAME
        if not import_dir.is_dir():
            return {"error": f"No .memory directory found at {import_path}"}

        new_memories: list[dict] = []
        update_memories: list[dict] = []
        skipped = 0
        errors: list[str] = []

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

                    if memory_id:
                        existing = self._memory_repo.get_by_id(project, memory_id)
                        if existing:
                            if existing.content != content or existing.title != title:
                                update_memories.append({
                                    "id": memory_id, "title": title, "content": content, "tags": tags,
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
                    errors.append(f"{md_file.name}: {e}")

        created = self._bulk_create(project, new_memories, errors)
        updated = self._bulk_update(project, update_memories, errors)

        return {
            "status": "ok",
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors if errors else None,
            "message": f"Imported: {created} created, {updated} updated, {skipped} skipped.",
        }

    def _bulk_create(self, project: str, new_memories: list[dict], errors: list[str]) -> int:
        if not new_memories:
            return 0

        texts = [prepare_embedding_text(m["title"], m["content"]) for m in new_memories]
        embeddings = embed_texts(texts)

        created = 0
        for mem, embedding in zip(new_memories, embeddings):
            try:
                memory_id = str(uuid.uuid4())
                summary = generate_summary(mem["title"], mem["content"])
                entities = extract_entities(f"{mem['title']} {mem['content']}")
                cat = MemoryCategory(mem["category"])
                priority = mem["priority"]
                if cat in RULE_CATEGORIES:
                    priority = max(priority, 2)
                expires_at = calculate_expiry(mem["category"], priority)

                self._memory_repo.insert(
                    project=project, memory_id=memory_id, category=mem["category"],
                    title=mem["title"], content=mem["content"], summary=summary,
                    tags=mem["tags"] or [], metadata=mem["metadata"],
                    embedding=embedding, priority=priority, source=mem["source"],
                    related_ids=[], entities=entities, expires_at=expires_at,
                )
                self._provenance_repo.record(project, memory_id, "create", {"source": "import"})
                created += 1
            except Exception as e:
                errors.append(f"Insert {mem['title']}: {e}")
        return created

    def _bulk_update(self, project: str, update_memories: list[dict], errors: list[str]) -> int:
        if not update_memories:
            return 0

        texts = [prepare_embedding_text(m["title"], m["content"]) for m in update_memories]
        embeddings = embed_texts(texts)

        updated = 0
        for mem, embedding in zip(update_memories, embeddings):
            try:
                summary = generate_summary(mem["title"], mem["content"])
                entities = extract_entities(f"{mem['title']} {mem['content']}")
                self._memory_repo.update(project, mem["id"], {
                    "title": mem["title"], "content": mem["content"],
                    "summary": summary, "entities": entities,
                    "embedding": embedding, "tags": mem["tags"] or [],
                })
                self._provenance_repo.record(project, mem["id"], "update", {"source": "import"})
                updated += 1
            except Exception as e:
                errors.append(f"Update {mem['id']}: {e}")
        return updated


# ---------- Markdown serialization helpers ----------


def _slugify_filename(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:60]


def _memory_to_markdown(mem: Memory) -> str:
    tags_str = ", ".join(mem.tags)
    entities_str = ", ".join(mem.entities)

    lines = [
        "---",
        f"id: {mem.id}",
        f"category: {mem.category.value}",
        f'title: "{mem.title}"',
        f"status: {mem.status}",
        f"priority: {mem.priority}",
    ]
    if tags_str:
        lines.append(f"tags: [{tags_str}]")
    if entities_str:
        lines.append(f"entities: [{entities_str}]")
    if mem.source:
        lines.append(f"source: {mem.source}")
    if mem.expires_at:
        lines.append(f"expires_at: {mem.expires_at}")
    if mem.created_at:
        lines.append(f"created_at: {mem.created_at}")
    if mem.updated_at:
        lines.append(f"updated_at: {mem.updated_at}")
    if mem.metadata:
        lines.append(f"metadata: {json.dumps(mem.metadata)}")

    lines.extend(["---", "", f"# {mem.title}", ""])
    if mem.summary:
        lines.extend([f"> {mem.summary}", ""])
    lines.extend([mem.content, ""])
    if mem.related_ids:
        lines.append("## Related")
        for rid in mem.related_ids:
            lines.append(f"- {rid}")
        lines.append("")
    return "\n".join(lines)


def _create_index(project: str, by_category: dict[str, list[Memory]]) -> str:
    total = sum(len(m) for m in by_category.values())
    lines = [
        f"# Memory Index - {project}", "",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
        f"Total: {total} memories", "",
        "## Categories", "",
        "| Category | Count |", "|----------|-------|",
    ]
    for cat, mems in sorted(by_category.items()):
        lines.append(f"| [{cat}](./{cat}/) | {len(mems)} |")
    lines.append("")

    for cat, mems in sorted(by_category.items()):
        lines.extend([f"## {cat}", ""])
        for mem in mems:
            filename = _slugify_filename(mem.title) + ".md"
            lines.append(f"- [{mem.title}](./{cat}/{filename}) - {mem.summary or ''}")
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

### Editing
Edit any .md file. Metadata lives between `---` markers. Memory content below.

## For People WITH Memory MCP

Run `memory_import("{project}", "/path/to/project")` to sync changes back.
"""


def _parse_markdown(text: str) -> dict | None:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return None

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    result: dict = {}
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

    content_lines: list[str] = []
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
