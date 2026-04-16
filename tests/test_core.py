"""Integration tests using the service layer via container.

These preserve the original behavior contracts but use the new
service API. Each test uses the global container (rebuilt per test
via conftest fixtures that reset state).
"""

import pytest

from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.models import (
    MemoryCategory, StoreMemoryRequest, UpdateMemoryRequest, SearchRequest,
    MemoryFilter, Pagination,
)


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def project(container, project_slug):
    container.project_service.init_project(project_slug, "Test Project", "A test")
    return project_slug


def _store(container, project, category="decision", title="T", content="C", tags=None, priority=0):
    return container.memory_service.store(StoreMemoryRequest(
        project=project,
        category=MemoryCategory(category),
        title=title,
        content=content,
        tags=tags or [],
        priority=priority,
    ))


class TestProjectInit:
    def test_init_project(self, container, project_slug):
        info = container.project_service.init_project(project_slug, "Test Project", "A test")
        assert info.slug == project_slug

    def test_list_projects(self, container, project):
        projects = container.project_service.list_all()
        assert len(projects) >= 1


class TestStoreAndRecall:
    def test_store_memory(self, container, project):
        mem = _store(container, project, title="Use PostgreSQL",
                     content="We chose PostgreSQL for JSON support.",
                     tags=["database", "backend"])
        assert mem.title == "Use PostgreSQL"
        assert mem.category.value == "decision"
        assert mem.summary is not None
        assert isinstance(mem.entities, list)

    def test_store_auto_summary(self, container, project):
        mem = _store(container, project, category="architecture",
                     title="API Gateway",
                     content="All requests go through Kong API gateway for rate limiting.")
        assert mem.summary

    def test_store_auto_entities(self, container, project):
        mem = _store(container, project,
                     title="Tech Stack",
                     content="Using React with TypeScript frontend, FastAPI backend, PostgreSQL database.")
        assert any("React" in e for e in mem.entities)

    def test_store_rules_never_expire(self, container, project):
        mem = _store(container, project, category="mandatory_rules",
                     title="Always Test", content="Run tests before commits.")
        assert mem.expires_at is None
        assert mem.priority >= 2

    def test_store_with_ttl(self, container, project):
        mem = _store(container, project, category="session",
                     title="Session Note", content="Worked on auth today.")
        assert mem.expires_at is not None

    def test_recall_by_id(self, container, project):
        stored = _store(container, project, category="architecture",
                        title="Microservices",
                        content="Using microservices with Kong gateway.")
        recalled = container.memory_service.recall(project, stored.id, None)
        assert recalled.title == "Microservices"

    def test_recall_by_title(self, container, project):
        _store(container, project, title="JWT Authentication",
               content="Using JWT for stateless auth.")
        recalled = container.memory_service.recall(project, None, "JWT Authentication")
        assert "JWT" in recalled.content


class TestSearch:
    def test_semantic_search(self, container, project):
        _store(container, project, title="Database Choice", content="We chose PostgreSQL for its JSON support.")
        _store(container, project, category="architecture", title="API Design", content="REST API with OpenAPI spec.")
        _store(container, project, category="devops", title="Docker Setup", content="Using Docker Compose.")

        response = container.search_service.search(SearchRequest(
            project=project, query="which database are we using?",
        ))
        assert response.total > 0
        assert "PostgreSQL" in response.results[0].memory.content

    def test_search_with_category_filter(self, container, project):
        _store(container, project, title="DB Decision", content="PostgreSQL chosen.")
        _store(container, project, category="devops", title="DB Deployment", content="PostgreSQL on RDS.")

        response = container.search_service.search(SearchRequest(
            project=project, query="PostgreSQL", category=MemoryCategory.DEVOPS,
        ))
        for hit in response.results:
            assert hit.memory.category == MemoryCategory.DEVOPS

    def test_search_with_token_budget(self, container, project):
        _store(container, project, title="Short", content="Brief content.")
        _store(container, project, title="Long", content="A" * 2000)

        response = container.search_service.search(SearchRequest(
            project=project, query="content", token_budget=100, min_similarity=0.0,
        ))
        assert hasattr(response, "index")
        assert hasattr(response, "details")
        assert hasattr(response, "tokens_used")


class TestRules:
    def test_store_and_get_rules(self, container, project):
        _store(container, project, category="mandatory_rules",
               title="Run Tests", content="Always run pytest.")
        _store(container, project, category="forbidden_rules",
               title="No Force Push", content="Never force push to main.")

        rules = container.rules_service.get_rules(project)
        assert len(rules.mandatory_rules) == 1
        assert len(rules.forbidden_rules) == 1
        assert rules.mandatory_rules[0].priority >= 2

    def test_rules_are_cached(self, container, project):
        _store(container, project, category="mandatory_rules",
               title="Test", content="Test rule")
        first = container.rules_service.get_rules(project)
        second = container.rules_service.get_rules(project)
        assert first is second  # same cached instance


class TestUpdateAndDelete:
    def test_update_content(self, container, project):
        stored = _store(container, project, title="Original", content="Original content.")
        updated = container.memory_service.update(UpdateMemoryRequest(
            project=project, memory_id=stored.id, content="Updated content.",
        ))
        assert updated.content == "Updated content."
        assert updated.summary is not None

    def test_soft_delete(self, container, project):
        stored = _store(container, project, title="To Delete", content="Will be archived.")
        result = container.memory_service.delete(project, stored.id, reason="no longer needed")
        assert result["action"] == "archived"


class TestProvenance:
    def test_provenance_tracking(self, container, project):
        stored = _store(container, project, title="Tracked", content="Original.")
        container.memory_service.update(UpdateMemoryRequest(
            project=project, memory_id=stored.id, content="Updated.",
        ))
        container.memory_service.recall(project, stored.id, None)

        trail = container.provenance_repo.for_memory(project, stored.id)
        ops = [e.operation for e in trail]
        assert "create" in ops
        assert "update" in ops
        assert "access" in ops


class TestSession:
    def test_session_lifecycle(self, container, project):
        _store(container, project, category="mandatory_rules",
               title="Always Test", content="Run tests first.")
        _store(container, project, category="sprint",
               title="Sprint 1", content="Auth module.")

        ctx = container.session_service.start(project)
        assert ctx.session_id
        assert len(ctx.mandatory_rules) == 1
        assert ctx.project == project

        result = container.session_service.end(project, ctx.session_id, "Completed auth.")
        assert result["status"] == "ok"

        ctx2 = container.session_service.start(project)
        assert ctx2.last_session_summary == "Completed auth."


class TestListMemories:
    def test_list_with_pagination(self, container, project):
        for i in range(5):
            _store(container, project, title=f"Decision {i}", content=f"Content {i}")

        memories, total = container.memory_repo.list(
            project, MemoryFilter(), Pagination(limit=2, offset=0),
        )
        assert len(memories) == 2
        assert total == 5

        memories2, _ = container.memory_repo.list(
            project, MemoryFilter(), Pagination(limit=2, offset=2),
        )
        assert len(memories2) == 2


class TestEntityExtraction:
    def test_extract_tech_names(self):
        from memory_mcp.utils.extraction import extract_entities
        entities = extract_entities("We use React, PostgreSQL, and Docker with AWS deployment")
        assert "React" in entities
        assert "PostgreSQL" in entities
        assert "Docker" in entities
        assert "AWS" in entities

    def test_extract_mentions_and_tags(self):
        from memory_mcp.utils.extraction import extract_entities
        entities = extract_entities("@serkan assigned #backend task for API refactoring")
        assert "@serkan" in entities
        assert "#backend" in entities
        assert "API" in entities

    def test_extract_camelcase(self):
        from memory_mcp.utils.extraction import extract_entities
        entities = extract_entities("FastMCP and DuckDB integration with SentenceTransformer")
        assert "FastMCP" in entities
        assert "DuckDB" in entities
        assert "SentenceTransformer" in entities
