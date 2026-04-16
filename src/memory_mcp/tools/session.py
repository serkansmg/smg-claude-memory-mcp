"""Session lifecycle tools."""

import uuid
from datetime import datetime, timedelta, timezone

from memory_mcp.db.connection import connect
from memory_mcp.db.queries import INSERT_SESSION, END_SESSION, LAST_SESSION, RECENT_BY_CATEGORY, ACTIVE_BY_CATEGORY, row_to_dict
from memory_mcp.db.registry import touch_project
from memory_mcp.tools.rules import get_rules

AUTO_CLOSE_SUMMARY = "[Auto-closed: session was not properly ended (context overflow or crash)]"


def session_start(project: str) -> dict:
    """Start a new session. Auto-closes orphaned sessions first."""
    session_id = str(uuid.uuid4())

    with connect(project) as conn:
        # Auto-close orphaned sessions
        orphans = conn.execute("SELECT id FROM sessions WHERE ended_at IS NULL").fetchall()
        orphans_closed = 0
        for orphan in orphans:
            conn.execute(END_SESSION, [AUTO_CLOSE_SUMMARY, 0, 0, orphan[0]])
            orphans_closed += 1

        conn.execute(INSERT_SESSION, [session_id])

        last_session = conn.execute(LAST_SESSION).fetchone()
        last_summary = last_session[3] if last_session else None
        if last_summary == AUTO_CLOSE_SUMMARY:
            real_last = conn.execute(
                "SELECT summary FROM sessions WHERE ended_at IS NOT NULL AND summary != ? ORDER BY ended_at DESC LIMIT 1",
                [AUTO_CLOSE_SUMMARY],
            ).fetchone()
            last_summary = real_last[0] if real_last else None

        sprint_rows = conn.execute(ACTIVE_BY_CATEGORY, ["sprint", 10]).fetchall()
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        decision_rows = conn.execute(RECENT_BY_CATEGORY, ["decision", seven_days_ago, 20]).fetchall()

    touch_project(project)
    rules = get_rules(project)

    result = {
        "session_id": session_id,
        "project": project,
        "mandatory_rules": rules["mandatory_rules"],
        "forbidden_rules": rules["forbidden_rules"],
        "last_session_summary": last_summary,
        "active_sprint": [row_to_dict(r) for r in sprint_rows],
        "recent_decisions": [row_to_dict(r) for r in decision_rows],
    }
    if orphans_closed > 0:
        result["orphaned_sessions_closed"] = orphans_closed
    return result


def session_end(project: str, session_id: str, summary: str, memories_created: int = 0, memories_accessed: int = 0) -> dict:
    with connect(project) as conn:
        conn.execute(END_SESSION, [summary, memories_created, memories_accessed, session_id])
    return {"status": "ok", "session_id": session_id, "summary": summary}
