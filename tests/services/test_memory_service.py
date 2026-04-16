"""Unit tests for MemoryService."""

import pytest

from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.exceptions import MemoryNotFoundError
from memory_mcp.models import StoreMemoryRequest, UpdateMemoryRequest, MemoryCategory


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def project(container, project_slug):
    container.project_repo.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


class TestStore:
    def test_store_basic(self, container, project):
        req = StoreMemoryRequest(
            project=project,
            category=MemoryCategory.DECISION,
            title="Use PostgreSQL",
            content="Chose PostgreSQL for JSON support.",
        )
        memory = container.memory_service.store(req)
        assert memory.id
        assert memory.title == "Use PostgreSQL"
        assert memory.summary
        assert memory.created_at

    def test_store_rules_forces_priority(self, container, project):
        req = StoreMemoryRequest(
            project=project,
            category=MemoryCategory.MANDATORY_RULES,
            title="Always Test",
            content="Run pytest before commits.",
            priority=0,
        )
        memory = container.memory_service.store(req)
        assert memory.priority >= 2

    def test_store_extracts_entities(self, container, project):
        req = StoreMemoryRequest(
            project=project,
            category=MemoryCategory.DECISION,
            title="Stack",
            content="Using React, PostgreSQL, Docker, and AWS.",
        )
        memory = container.memory_service.store(req)
        assert any("React" in e for e in memory.entities)


class TestRecall:
    def test_recall_by_id(self, container, project):
        req = StoreMemoryRequest(
            project=project, category=MemoryCategory.DECISION,
            title="T", content="C",
        )
        stored = container.memory_service.store(req)
        recalled = container.memory_service.recall(project, stored.id, None)
        assert recalled.id == stored.id

    def test_recall_increments_access(self, container, project):
        req = StoreMemoryRequest(
            project=project, category=MemoryCategory.DECISION,
            title="T", content="C",
        )
        stored = container.memory_service.store(req)
        container.memory_service.recall(project, stored.id, None)
        got = container.memory_repo.get_by_id(project, stored.id)
        assert got.access_count >= 1

    def test_recall_missing_raises(self, container, project):
        with pytest.raises(MemoryNotFoundError):
            container.memory_service.recall(project, "missing-id", None)


class TestUpdate:
    def test_update_changes_fields(self, container, project):
        req = StoreMemoryRequest(
            project=project, category=MemoryCategory.DECISION,
            title="Old", content="Old content.",
        )
        stored = container.memory_service.store(req)

        upd = UpdateMemoryRequest(
            project=project, memory_id=stored.id,
            content="New content for update.",
        )
        updated = container.memory_service.update(upd)
        assert updated.content == "New content for update."

    def test_update_missing_raises(self, container, project):
        upd = UpdateMemoryRequest(
            project=project, memory_id="nope", title="x",
        )
        with pytest.raises(MemoryNotFoundError):
            container.memory_service.update(upd)


class TestDelete:
    def test_soft_delete(self, container, project):
        req = StoreMemoryRequest(
            project=project, category=MemoryCategory.DECISION,
            title="T", content="C",
        )
        stored = container.memory_service.store(req)
        result = container.memory_service.delete(project, stored.id)
        assert result["action"] == "archived"
        got = container.memory_repo.get_by_id(project, stored.id)
        assert got.status == "archived"

    def test_hard_delete(self, container, project):
        req = StoreMemoryRequest(
            project=project, category=MemoryCategory.DECISION,
            title="T", content="C",
        )
        stored = container.memory_service.store(req)
        container.memory_service.delete(project, stored.id, hard=True)
        assert container.memory_repo.get_by_id(project, stored.id) is None

    def test_delete_missing_raises(self, container, project):
        with pytest.raises(MemoryNotFoundError):
            container.memory_service.delete(project, "missing")
