"""Provenance tracking - audit trail for all memory operations."""

import json

from memory_mcp.db.connection import get_connection


def record_provenance(
    project: str,
    memory_id: str,
    operation: str,
    details: dict | None = None,
) -> None:
    """Record a provenance entry for a memory operation."""
    conn = get_connection(project)
    conn.execute(
        "INSERT INTO provenance (memory_id, operation, details) VALUES (?, ?, ?)",
        [memory_id, operation, json.dumps(details) if details else None],
    )


def get_provenance(project: str, memory_id: str) -> list[dict]:
    """Get full provenance chain for a memory."""
    conn = get_connection(project)
    rows = conn.execute(
        """
        SELECT id, memory_id, operation, details, created_at
        FROM provenance WHERE memory_id = ?
        ORDER BY created_at ASC
        """,
        [memory_id],
    ).fetchall()
    return [
        {
            "id": r[0],
            "memory_id": r[1],
            "operation": r[2],
            "details": json.loads(r[3]) if r[3] else None,
            "created_at": str(r[4]) if r[4] else None,
        }
        for r in rows
    ]
