"""Session repository - CRUD for session records in per-project DB."""

from memory_mcp.db.connection import connect
from memory_mcp.models import SessionRecord


class SessionRepository:
    """Session CRUD."""

    def insert(self, project: str, session_id: str) -> None:
        with connect(project) as conn:
            conn.execute(
                "INSERT INTO sessions (id, started_at) VALUES (?, current_timestamp)",
                [session_id],
            )

    def end(
        self,
        project: str,
        session_id: str,
        summary: str,
        memories_created: int = 0,
        memories_accessed: int = 0,
    ) -> None:
        with connect(project) as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = current_timestamp, summary = ?, memories_created = ?, memories_accessed = ? WHERE id = ?",
                [summary, memories_created, memories_accessed, session_id],
            )

    def orphaned(self, project: str) -> list[str]:
        """Return IDs of sessions that never received an ended_at timestamp."""
        with connect(project) as conn:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE ended_at IS NULL"
            ).fetchall()
        return [r[0] for r in rows]

    def last_with_summary(self, project: str, exclude_summary: str | None = None) -> SessionRecord | None:
        """Return the most recent ended session, optionally skipping a given summary."""
        sql = (
            "SELECT id, started_at, ended_at, summary, memories_created, memories_accessed "
            "FROM sessions WHERE ended_at IS NOT NULL"
        )
        params: list = []
        if exclude_summary is not None:
            sql += " AND summary != ?"
            params.append(exclude_summary)
        sql += " ORDER BY ended_at DESC LIMIT 1"

        with connect(project) as conn:
            row = conn.execute(sql, params).fetchone()

        if not row:
            return None
        return SessionRecord(
            id=row[0], started_at=row[1], ended_at=row[2], summary=row[3],
            memories_created=row[4], memories_accessed=row[5],
        )
