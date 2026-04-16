"""Provenance repository - audit trail for all memory operations."""

import json

from memory_mcp.db.connection import connect
from memory_mcp.models import ProvenanceEntry


class ProvenanceRepository:
    """Audit log CRUD."""

    def record(
        self,
        project: str,
        memory_id: str,
        operation: str,
        details: dict | None = None,
    ) -> None:
        with connect(project) as conn:
            conn.execute(
                "INSERT INTO provenance (memory_id, operation, details) VALUES (?, ?, ?)",
                [memory_id, operation, json.dumps(details) if details else None],
            )

    def for_memory(self, project: str, memory_id: str) -> list[ProvenanceEntry]:
        with connect(project) as conn:
            rows = conn.execute(
                """
                SELECT id, memory_id, operation, details, created_at
                FROM provenance WHERE memory_id = ?
                ORDER BY created_at ASC
                """,
                [memory_id],
            ).fetchall()

        entries: list[ProvenanceEntry] = []
        for r in rows:
            details = None
            if r[3]:
                try:
                    details = json.loads(r[3]) if isinstance(r[3], str) else r[3]
                except (json.JSONDecodeError, TypeError):
                    details = None
            entries.append(
                ProvenanceEntry(
                    id=r[0], memory_id=r[1], operation=r[2],
                    details=details, created_at=r[4],
                )
            )
        return entries
