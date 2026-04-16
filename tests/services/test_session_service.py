"""Unit tests for SessionService."""

import pytest

from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.models import StoreMemoryRequest, MemoryCategory
from memory_mcp.services.session_service import AUTO_CLOSE_SUMMARY


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def project(container, project_slug):
    container.project_repo.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


class TestSession:
    def test_start_returns_context(self, container, project):
        container.memory_service.store(StoreMemoryRequest(
            project=project, category=MemoryCategory.MANDATORY_RULES,
            title="R", content="always test",
        ))
        container.memory_service.store(StoreMemoryRequest(
            project=project, category=MemoryCategory.SPRINT,
            title="Sprint 1", content="auth module",
        ))
        ctx = container.session_service.start(project)
        assert ctx.session_id
        assert len(ctx.mandatory_rules) == 1
        assert len(ctx.active_sprint) == 1

    def test_end_stores_summary(self, container, project):
        ctx = container.session_service.start(project)
        container.session_service.end(project, ctx.session_id, "all done")

        ctx2 = container.session_service.start(project)
        assert ctx2.last_session_summary == "all done"

    def test_orphaned_sessions_auto_closed(self, container, project):
        # Each start closes any unended sessions first, so:
        # ctx1 starts (0 orphans)
        # ctx2 starts, closes ctx1 (1 orphan)
        # ctx3 starts, closes ctx2 (1 orphan)
        ctx1 = container.session_service.start(project)
        assert ctx1.orphaned_sessions_closed == 0
        ctx2 = container.session_service.start(project)
        assert ctx2.orphaned_sessions_closed == 1
        ctx3 = container.session_service.start(project)
        assert ctx3.orphaned_sessions_closed == 1

    def test_last_summary_skips_auto_close(self, container, project):
        ctx1 = container.session_service.start(project)
        container.session_service.end(project, ctx1.session_id, "real work")

        # Now simulate an orphaned one
        ctx2 = container.session_service.start(project)
        ctx3 = container.session_service.start(project)  # closes ctx2 with auto-close

        assert ctx3.last_session_summary == "real work"
