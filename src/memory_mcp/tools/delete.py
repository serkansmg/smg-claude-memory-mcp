"""Memory delete tool - soft or hard delete with provenance."""

from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import SELECT_MEMORY_BY_ID, SOFT_DELETE, HARD_DELETE
from memory_mcp.db.provenance import record_provenance
from memory_mcp.models import MemoryCategory, RULE_CATEGORIES
from memory_mcp.tools.rules import invalidate_rules_cache


def delete_memory(
    project: str,
    memory_id: str,
    hard: bool = False,
    reason: str | None = None,
) -> dict:
    """Soft-delete (archive) or hard-delete a memory with provenance tracking."""
    conn = get_connection(project)

    row = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()
    if not row:
        return {"error": f"Memory '{memory_id}' not found"}

    category = row[1]

    # Record provenance before deletion
    action = "hard_delete" if hard else "soft_delete"
    record_provenance(project, memory_id, action, {"reason": reason})

    if hard:
        conn.execute(HARD_DELETE, [memory_id])
        result = {"status": "ok", "action": "hard_deleted", "memory_id": memory_id}
    else:
        conn.execute(SOFT_DELETE, [memory_id])
        result = {"status": "ok", "action": "archived", "memory_id": memory_id}

    try:
        if MemoryCategory(category) in RULE_CATEGORIES:
            invalidate_rules_cache(project)
    except ValueError:
        pass

    return result
