"""Export memories to .md files and import from .md files.

Export creates a human-readable directory structure that can be used
by people who don't have the MCP installed. They can read and edit
the markdown files directly.

Import reads the markdown files back into the DB.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import MEMORY_COLUMNS, row_to_dict
from memory_mcp.db.provenance import record_provenance
from memory_mcp.models import MemoryCategory

# Export directory name inside the project
EXPORT_DIR_NAME = ".memory"


def export_memories(project: str, export_path: str) -> dict:
    """Export all active memories to a structured .md directory.

    Creates:
      <export_path>/.memory/
        MEMORY_INDEX.md          # Master index with all memories
        decisions/
          use-postgresql.md      # One file per memory
          jwt-authentication.md
        mandatory_rules/
          always-run-tests.md
        architecture/
          api-gateway-pattern.md
        ...

    Each .md file has YAML frontmatter with metadata, making it
    readable by humans and parseable for import.

    Args:
        project: Project slug
        export_path: Path to the project directory
    """
    export_dir = Path(export_path).resolve() / EXPORT_DIR_NAME
    export_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection(project)

    # Fetch all active memories
    rows = conn.execute(
        f"SELECT {MEMORY_COLUMNS} FROM memories WHERE status = 'active' ORDER BY category, title"
    ).fetchall()

    if not rows:
        return {"status": "ok", "exported": 0, "message": "No active memories to export."}

    memories_by_category: dict[str, list[dict]] = {}
    all_memories = []

    for row in rows:
        memory = row_to_dict(row)
        cat = memory["category"]
        if cat not in memories_by_category:
            memories_by_category[cat] = []
        memories_by_category[cat].append(memory)
        all_memories.append(memory)

    # Create category directories and write individual files
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

    # Create master index
    index_content = _create_index(project, memories_by_category)
    (export_dir / "MEMORY_INDEX.md").write_text(index_content, encoding="utf-8")

    # Create a README explaining the format
    readme = _create_export_readme(project)
    (export_dir / "README.md").write_text(readme, encoding="utf-8")

    return {
        "status": "ok",
        "exported": exported,
        "export_path": str(export_dir),
        "categories": {cat: len(mems) for cat, mems in memories_by_category.items()},
        "message": f"Exported {exported} memories to {export_dir}",
    }


def import_memories(project: str, import_path: str) -> dict:
    """Import memories from exported .md files back into the DB.

    Reads .md files with YAML frontmatter from the .memory directory.
    Skips memories that already exist (by ID).
    Updates memories whose content has changed.

    Args:
        project: Project slug
        import_path: Path to the project directory (looks for .memory/ subdir)
    """
    import_dir = Path(import_path).resolve() / EXPORT_DIR_NAME
    if not import_dir.is_dir():
        return {"error": f"No .memory directory found at {import_path}"}

    from memory_mcp.tools.store import store_memory
    from memory_mcp.tools.update import update_memory
    from memory_mcp.db.queries import SELECT_MEMORY_BY_ID

    conn = get_connection(project)

    created = 0
    updated = 0
    skipped = 0
    errors = []

    # Scan all .md files in category directories
    for category_dir in import_dir.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue

        category = category_dir.name

        # Validate category
        try:
            MemoryCategory(category)
        except ValueError:
            errors.append(f"Unknown category directory: {category}")
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

                # Check if memory already exists
                if memory_id:
                    existing = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()
                    if existing:
                        existing_dict = row_to_dict(existing)
                        # Update if content changed
                        if existing_dict["content"] != content or existing_dict["title"] != title:
                            update_memory(project, memory_id, title=title, content=content, tags=tags)
                            updated += 1
                        else:
                            skipped += 1
                        continue

                # Create new memory
                result = store_memory(
                    project=project,
                    category=category,
                    title=title,
                    content=content,
                    tags=tags,
                    metadata=metadata,
                    priority=priority,
                    source=source,
                )

                if "error" in result:
                    errors.append(f"{md_file.name}: {result['error']}")
                else:
                    created += 1

            except Exception as e:
                errors.append(f"{md_file.name}: {str(e)}")

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors if errors else None,
        "message": f"Imported: {created} created, {updated} updated, {skipped} skipped.",
    }


# --- Helper Functions ---


def _slugify_filename(title: str) -> str:
    """Convert a title to a safe filename."""
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:60]


def _memory_to_markdown(mem: dict) -> str:
    """Convert a memory dict to a markdown file with YAML frontmatter."""
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

    lines.append("---")
    lines.append("")
    lines.append(f"# {mem['title']}")
    lines.append("")

    if mem.get("summary"):
        lines.append(f"> {mem['summary']}")
        lines.append("")

    lines.append(mem.get("content", ""))
    lines.append("")

    if mem.get("related_ids"):
        lines.append("## Related")
        for rid in mem["related_ids"]:
            lines.append(f"- {rid}")
        lines.append("")

    return "\n".join(lines)


def _create_index(project: str, memories_by_category: dict[str, list[dict]]) -> str:
    """Create the master MEMORY_INDEX.md file."""
    lines = [
        f"# Memory Index - {project}",
        "",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    total = sum(len(mems) for mems in memories_by_category.values())
    lines.append(f"Total: {total} memories")
    lines.append("")

    # Table of contents
    lines.append("## Categories")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, mems in sorted(memories_by_category.items()):
        lines.append(f"| [{cat}](./{cat}/) | {len(mems)} |")
    lines.append("")

    # Per-category listings
    for cat, mems in sorted(memories_by_category.items()):
        lines.append(f"## {cat}")
        lines.append("")
        for mem in mems:
            filename = _slugify_filename(mem["title"]) + ".md"
            summary = mem.get("summary", "")
            lines.append(f"- [{mem['title']}](./{cat}/{filename}) - {summary}")
        lines.append("")

    return "\n".join(lines)


def _create_export_readme(project: str) -> str:
    """Create a README explaining the export format."""
    return f"""# Project Memory - {project}

This directory contains exported project memories from the Memory MCP Server.

## For People WITHOUT Memory MCP

You can read and edit these files directly:

- **MEMORY_INDEX.md** - Master index of all memories
- **<category>/<memory>.md** - Individual memory files organized by category
- Each file has YAML frontmatter (metadata) and markdown content

### Categories
- `mandatory_rules/` - Rules that MUST be followed
- `forbidden_rules/` - Things that must NOT be done
- `decision/` - Important decisions and their rationale
- `architecture/` - Architecture decisions and patterns
- `sprint/` - Sprint goals and progress
- `devops/` - DevOps configurations and notes
- `developer_docs/` - Developer documentation
- `reference/` - External resource pointers

### Editing
You can edit any .md file. The content between the `---` frontmatter markers
contains metadata. The actual memory content is below the frontmatter.

## For People WITH Memory MCP

Run `memory_import("{project}", "/path/to/project")` to sync changes
from these files back into the MCP database.

Or use: `/smg-memory import {project} /path/to/project`
"""


def _parse_markdown(text: str) -> dict | None:
    """Parse a markdown file with YAML frontmatter into a dict."""
    # Extract frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return None

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    # Parse simple YAML frontmatter
    result = {}
    for line in frontmatter_text.strip().split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Remove quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        # Parse lists [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if inner:
                value = [item.strip() for item in inner.split(",")]
            else:
                value = []

        # Parse integers
        if isinstance(value, str) and value.isdigit():
            value = int(value)

        result[key] = value

    # Extract content from body (skip title heading and summary blockquote)
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

        # Stop at ## Related section
        if line.startswith("## Related"):
            break

        content_lines.append(line)

    result["content"] = "\n".join(content_lines).strip()
    return result
