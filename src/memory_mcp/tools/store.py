"""Memory store tool - save new memories with auto-embedding, summary, entities, TTL."""

import json
import uuid

from memory_mcp.db.connection import connect
from memory_mcp.db.queries import INSERT_MEMORY, row_to_dict, SELECT_MEMORY_BY_ID
from memory_mcp.db.registry import touch_project
from memory_mcp.db.provenance import record_provenance
from memory_mcp.embeddings import embed_text
from memory_mcp.models import MemoryCategory, RULE_CATEGORIES
from memory_mcp.tools.rules import invalidate_rules_cache
from memory_mcp.utils.text import prepare_embedding_text
from memory_mcp.utils.extraction import generate_summary, extract_entities, calculate_expiry


def store_memory(
    project: str,
    category: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    priority: int = 0,
    source: str = "assistant",
    related_ids: list[str] | None = None,
) -> dict:
    """Store a new memory with auto-embedding, summary, entity extraction, and TTL."""
    try:
        cat = MemoryCategory(category)
    except ValueError:
        valid = [c.value for c in MemoryCategory]
        return {"error": f"Invalid category '{category}'. Valid: {valid}"}

    if cat in RULE_CATEGORIES:
        priority = max(priority, 2)

    summary = generate_summary(title, content)
    full_text = f"{title} {content}"
    entities = extract_entities(full_text)
    expires_at = calculate_expiry(category, priority)
    embedding_text = prepare_embedding_text(title, content)
    embedding = embed_text(embedding_text)
    memory_id = str(uuid.uuid4())

    with connect(project) as conn:
        conn.execute(INSERT_MEMORY, [
            memory_id, category, title, content, summary, tags or [],
            json.dumps(metadata) if metadata else None, embedding, "active",
            priority, source, related_ids or [], entities, expires_at,
        ])
        row = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()

    touch_project(project)
    record_provenance(project, memory_id, "create", {
        "category": category, "title": title, "source": source,
        "entities_extracted": len(entities),
    })

    if cat in RULE_CATEGORIES:
        invalidate_rules_cache(project)

    return {"status": "ok", "memory": row_to_dict(row)}
