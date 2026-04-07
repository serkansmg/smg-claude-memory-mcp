"""Session lifecycle tools - start and end sessions with context loading."""

import uuid
from datetime import datetime, timedelta, timezone

from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import (
    INSERT_SESSION,
    END_SESSION,
    LAST_SESSION,
    RECENT_BY_CATEGORY,
    ACTIVE_BY_CATEGORY,
    row_to_dict,
)
from memory_mcp.db.registry import touch_project
from memory_mcp.tools.rules import get_rules


def session_start(project: str) -> dict:
    """Start a new session. Returns full context: rules, last session, sprint, recent decisions."""
    session_id = str(uuid.uuid4())

    conn = get_connection(project)
    conn.execute(INSERT_SESSION, [session_id])
    touch_project(project)

    # Load rules
    rules = get_rules(project)

    # Last session summary
    last_session = conn.execute(LAST_SESSION).fetchone()
    last_summary = last_session[3] if last_session else None

    # Active sprint goals
    sprint_rows = conn.execute(ACTIVE_BY_CATEGORY, ["sprint", 10]).fetchall()
    active_sprint = [row_to_dict(r) for r in sprint_rows]

    # Recent decisions (last 7 days)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    decision_rows = conn.execute(
        RECENT_BY_CATEGORY, ["decision", seven_days_ago, 20]
    ).fetchall()
    recent_decisions = [row_to_dict(r) for r in decision_rows]

    return {
        "session_id": session_id,
        "project": project,
        "mandatory_rules": rules["mandatory_rules"],
        "forbidden_rules": rules["forbidden_rules"],
        "last_session_summary": last_summary,
        "active_sprint": active_sprint,
        "recent_decisions": recent_decisions,
    }


def session_end(
    project: str,
    session_id: str,
    summary: str,
    memories_created: int = 0,
    memories_accessed: int = 0,
) -> dict:
    """End a session and store its summary."""
    conn = get_connection(project)

    conn.execute(END_SESSION, [summary, memories_created, memories_accessed, session_id])

    return {
        "status": "ok",
        "session_id": session_id,
        "summary": summary,
    }
