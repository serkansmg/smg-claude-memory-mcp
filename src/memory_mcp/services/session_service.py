"""Session service - start/end sessions, load context, handle orphans."""

import uuid
from datetime import datetime, timedelta, timezone

from memory_mcp.models import SessionContext
from memory_mcp.repositories import (
    MemoryRepository, ProjectRepository, SessionRepository,
)
from memory_mcp.services.rules_service import RulesService

AUTO_CLOSE_SUMMARY = "[Auto-closed: session was not properly ended (context overflow or crash)]"


class SessionService:
    """Session lifecycle with orphaned-session auto-close and context loading."""

    def __init__(
        self,
        session_repo: SessionRepository,
        memory_repo: MemoryRepository,
        project_repo: ProjectRepository,
        rules_service: RulesService,
    ):
        self._session_repo = session_repo
        self._memory_repo = memory_repo
        self._project_repo = project_repo
        self._rules_service = rules_service

    def start(self, project: str) -> SessionContext:
        session_id = str(uuid.uuid4())

        # Auto-close orphans
        orphans = self._session_repo.orphaned(project)
        for orphan_id in orphans:
            self._session_repo.end(project, orphan_id, AUTO_CLOSE_SUMMARY, 0, 0)

        self._session_repo.insert(project, session_id)
        self._project_repo.touch(project)

        rules = self._rules_service.get_rules(project)

        # Find the last non-auto-closed summary
        last = self._session_repo.last_with_summary(project)
        last_summary = last.summary if last else None
        if last_summary == AUTO_CLOSE_SUMMARY:
            real_last = self._session_repo.last_with_summary(
                project, exclude_summary=AUTO_CLOSE_SUMMARY
            )
            last_summary = real_last.summary if real_last else None

        active_sprint = self._memory_repo.get_active_by_category(project, "sprint", limit=10)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_decisions = self._memory_repo.get_recent_by_category(
            project, "decision", seven_days_ago, limit=20,
        )

        return SessionContext(
            session_id=session_id,
            project=project,
            mandatory_rules=rules.mandatory_rules,
            forbidden_rules=rules.forbidden_rules,
            last_session_summary=last_summary,
            active_sprint=active_sprint,
            recent_decisions=recent_decisions,
            orphaned_sessions_closed=len(orphans),
        )

    def end(
        self,
        project: str,
        session_id: str,
        summary: str,
        memories_created: int = 0,
        memories_accessed: int = 0,
    ) -> dict:
        self._session_repo.end(project, session_id, summary, memories_created, memories_accessed)
        return {"status": "ok", "session_id": session_id, "summary": summary}
