"""Memory recall tool - retrieve specific memories by ID or title."""

from memory_mcp.db.connection import connect
from memory_mcp.db.queries import SELECT_MEMORY_BY_ID, SELECT_MEMORY_BY_TITLE, INCREMENT_ACCESS, row_to_dict
from memory_mcp.db.provenance import record_provenance


def recall_memory(
    project: str,
    memory_id: str | None = None,
    title: str | None = None,
) -> dict:
    """Retrieve a specific memory by ID or exact title match."""
    if not memory_id and not title:
        return {"error": "Provide either memory_id or title"}

    with connect(project) as conn:
        if memory_id:
            row = conn.execute(SELECT_MEMORY_BY_ID, [memory_id]).fetchone()
        else:
            row = conn.execute(SELECT_MEMORY_BY_TITLE, [title]).fetchone()

        if not row:
            return {"error": "Memory not found"}

        conn.execute(INCREMENT_ACCESS, [row[0]])

    record_provenance(project, row[0], "access", {"method": "recall"})
    return {"memory": row_to_dict(row)}
