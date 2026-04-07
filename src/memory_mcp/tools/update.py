"""Memory update tool - partial updates with re-embedding and provenance."""

import json

from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import SELECT_MEMORY_BY_ID, row_to_dict
from memory_mcp.db.provenance import record_provenance
from memory_mcp.embeddings import embed_text
from memory_mcp.models import MemoryCategory, RULE_CATEGORIES
from memory_mcp.tools.rules import invalidate_rules_cache
from memory_mcp.utils.text import prepare_embedding_text
from memory_mcp.utils.extraction import generate_summary, extract_entities


def update_memory(
    project: str,
    memory_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    status: str | None = None,
    priority: int | None = None,
    related_ids: list[str] | None = None,
) -> dict:
    """Partial update with re-embedding, re-summary, re-entity extraction, and provenance."""
    conn = get_connection(project)

    row = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()
    if not row:
        return {"error": f"Memory '{memory_id}' not found"}

    existing = row_to_dict(row, include_embedding=True)

    updates = {}
    changed_fields = []

    if title is not None:
        updates["title"] = title
        changed_fields.append("title")
    if content is not None:
        updates["content"] = content
        changed_fields.append("content")
    if tags is not None:
        updates["tags"] = tags
        changed_fields.append("tags")
    if metadata is not None:
        updates["metadata"] = json.dumps(metadata)
        changed_fields.append("metadata")
    if status is not None:
        updates["status"] = status
        changed_fields.append("status")
    if priority is not None:
        updates["priority"] = priority
        changed_fields.append("priority")
    if related_ids is not None:
        updates["related_ids"] = related_ids
        changed_fields.append("related_ids")

    if not updates:
        return {"error": "No fields to update"}

    # Re-embed, re-summarize, re-extract entities if title or content changed
    if title is not None or content is not None:
        new_title = title or existing["title"]
        new_content = content or existing["content"]
        embedding_text = prepare_embedding_text(new_title, new_content)
        updates["embedding"] = embed_text(embedding_text)
        updates["summary"] = generate_summary(new_title, new_content)
        updates["entities"] = extract_entities(f"{new_title} {new_content}")

    # Build and execute UPDATE
    set_parts = []
    values = []
    for key, value in updates.items():
        set_parts.append(f"{key} = ?")
        values.append(value)

    set_parts.append("updated_at = current_timestamp")
    values.append(memory_id)

    sql = f"UPDATE memories SET {', '.join(set_parts)} WHERE id = ?"
    conn.execute(sql, values)

    # Record provenance
    record_provenance(project, memory_id, "update", {"changed_fields": changed_fields})

    # Invalidate rules cache if needed
    cat = existing.get("category", "")
    try:
        if MemoryCategory(cat) in RULE_CATEGORIES:
            invalidate_rules_cache(project)
    except ValueError:
        pass

    row = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()
    return {"status": "ok", "memory": row_to_dict(row)}
