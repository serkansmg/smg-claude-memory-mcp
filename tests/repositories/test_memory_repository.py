"""Unit tests for MemoryRepository."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from memory_mcp.repositories import MemoryRepository, ProjectRepository
from memory_mcp.models import MemoryFilter, Pagination
from memory_mcp.db.connection import get_connection


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def project(project_slug) -> str:
    # Register project + init DB via direct registry use
    pr = ProjectRepository()
    pr.register(project_slug, "Test Project")
    # Trigger DB schema creation
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


def _make_embedding() -> list[float]:
    # Return a unit vector of dim 384
    from memory_mcp.embeddings import embed_text
    return embed_text("dummy text for embedding")


def _insert(repo, project, title="Test", content="Content", category="decision", priority=0, tags=None):
    return repo.insert(
        project=project,
        memory_id=str(uuid.uuid4()),
        category=category,
        title=title,
        content=content,
        summary=f"summary of {title}",
        tags=tags or [],
        metadata=None,
        embedding=_make_embedding(),
        priority=priority,
        source="test",
        related_ids=[],
        entities=[],
        expires_at=None,
    )


class TestInsertAndGet:
    def test_insert_returns_typed_memory(self, repo, project):
        mem = _insert(repo, project, title="Hello")
        assert mem.id
        assert mem.title == "Hello"
        assert mem.category.value == "decision"
        assert mem.status == "active"

    def test_get_by_id(self, repo, project):
        mem = _insert(repo, project, title="FindMe")
        found = repo.get_by_id(project, mem.id)
        assert found is not None
        assert found.title == "FindMe"

    def test_get_by_id_missing(self, repo, project):
        assert repo.get_by_id(project, "nonexistent") is None

    def test_get_by_title(self, repo, project):
        _insert(repo, project, title="Unique Title")
        found = repo.get_by_title(project, "Unique Title")
        assert found is not None

    def test_get_by_title_missing(self, repo, project):
        assert repo.get_by_title(project, "Nope") is None


class TestRules:
    def test_get_rules_partitions_correctly(self, repo, project):
        _insert(repo, project, title="Mand1", category="mandatory_rules", priority=2)
        _insert(repo, project, title="Mand2", category="mandatory_rules", priority=2)
        _insert(repo, project, title="Forb1", category="forbidden_rules", priority=2)
        _insert(repo, project, title="Dec1", category="decision")

        mandatory, forbidden = repo.get_rules(project)
        assert len(mandatory) == 2
        assert len(forbidden) == 1
        for m in mandatory:
            assert m.category.value == "mandatory_rules"


class TestList:
    def test_list_basic(self, repo, project):
        for i in range(5):
            _insert(repo, project, title=f"Item {i}")

        memories, total = repo.list(project, MemoryFilter(), Pagination(limit=10))
        assert total == 5
        assert len(memories) == 5

    def test_list_pagination(self, repo, project):
        for i in range(5):
            _insert(repo, project, title=f"Item {i}")

        page1, total = repo.list(project, MemoryFilter(), Pagination(limit=2, offset=0))
        page2, _ = repo.list(project, MemoryFilter(), Pagination(limit=2, offset=2))

        assert total == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    def test_list_category_filter(self, repo, project):
        _insert(repo, project, category="decision")
        _insert(repo, project, category="devops")
        _insert(repo, project, category="devops")

        memories, total = repo.list(
            project, MemoryFilter(category="devops"), Pagination()
        )
        assert total == 2
        assert all(m.category.value == "devops" for m in memories)

    def test_list_tag_filter(self, repo, project):
        _insert(repo, project, title="A", tags=["python"])
        _insert(repo, project, title="B", tags=["rust"])

        memories, _ = repo.list(
            project, MemoryFilter(tags=["python"]), Pagination()
        )
        assert len(memories) == 1
        assert memories[0].title == "A"


class TestVectorSearch:
    def test_vector_search_returns_distances(self, repo, project):
        _insert(repo, project, title="Database", content="PostgreSQL chosen for JSON")
        _insert(repo, project, title="Cache", content="Redis for session storage")

        from memory_mcp.embeddings import embed_text
        query_emb = embed_text("database choice")
        results = repo.vector_search(project, query_emb, "active", limit=5)

        assert len(results) == 2
        for mem, dist in results:
            assert 0 <= dist <= 2  # cosine distance range


class TestUpdateAndDelete:
    def test_update_fields(self, repo, project):
        mem = _insert(repo, project, title="Original")
        updated = repo.update(project, mem.id, {"title": "Updated"})
        assert updated.title == "Updated"

    def test_soft_delete(self, repo, project):
        mem = _insert(repo, project)
        repo.soft_delete(project, mem.id)
        got = repo.get_by_id(project, mem.id)
        assert got.status == "archived"

    def test_hard_delete(self, repo, project):
        mem = _insert(repo, project)
        repo.hard_delete(project, mem.id)
        assert repo.get_by_id(project, mem.id) is None

    def test_increment_access(self, repo, project):
        mem = _insert(repo, project)
        assert mem.access_count == 0
        repo.increment_access(project, mem.id)
        repo.increment_access(project, mem.id)
        got = repo.get_by_id(project, mem.id)
        assert got.access_count == 2


class TestRecentAndActive:
    def test_get_recent_by_category(self, repo, project):
        _insert(repo, project, category="decision", title="D1")
        _insert(repo, project, category="decision", title="D2")
        _insert(repo, project, category="devops", title="Dev1")

        since = datetime.now(timezone.utc) - timedelta(days=1)
        rows = repo.get_recent_by_category(project, "decision", since, limit=10)
        assert len(rows) == 2

    def test_get_active_by_category(self, repo, project):
        _insert(repo, project, category="sprint", title="S1")
        rows = repo.get_active_by_category(project, "sprint", limit=10)
        assert len(rows) == 1


class TestCountAndIterate:
    def test_count_active(self, repo, project):
        assert repo.count_active(project) == 0
        _insert(repo, project)
        _insert(repo, project)
        assert repo.count_active(project) == 2

    def test_iter_active_yields_all(self, repo, project):
        _insert(repo, project, title="A")
        _insert(repo, project, title="B")
        mems = list(repo.iter_active(project))
        assert len(mems) == 2

    def test_update_embedding(self, repo, project):
        mem = _insert(repo, project)
        from memory_mcp.embeddings import embed_text
        new_emb = embed_text("completely different text")
        repo.update_embedding(project, mem.id, new_emb)
        # No exception = success (embedding not returned in get_by_id by default)
