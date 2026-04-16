"""Unit tests for SearchService."""

import pytest

from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.models import (
    SearchRequest, StoreMemoryRequest, MemoryCategory,
    SearchResponse, SearchResponseTokenBudgeted,
)


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def seeded_project(container, project_slug):
    container.project_repo.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()

    memories = [
        ("decision", "Database", "We chose PostgreSQL for JSON support."),
        ("devops", "Deployment", "Using Docker Compose."),
        ("architecture", "API", "REST API with OpenAPI spec."),
    ]
    for cat, title, content in memories:
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory(cat),
            title=title, content=content,
        ))
    return project_slug


class TestSearch:
    def test_returns_response_object(self, container, seeded_project):
        req = SearchRequest(project=seeded_project, query="database choice")
        result = container.search_service.search(req)
        assert isinstance(result, SearchResponse)
        assert result.query == "database choice"
        assert result.total >= 1

    def test_category_filter(self, container, seeded_project):
        req = SearchRequest(
            project=seeded_project, query="deployment",
            category=MemoryCategory.DEVOPS,
        )
        result = container.search_service.search(req)
        for hit in result.results:
            assert hit.memory.category == MemoryCategory.DEVOPS

    def test_token_budget_returns_dual_phase(self, container, seeded_project):
        req = SearchRequest(
            project=seeded_project, query="database postgresql",
            token_budget=200, min_similarity=0.0,
        )
        result = container.search_service.search(req)
        assert isinstance(result, SearchResponseTokenBudgeted)
        assert len(result.index) > 0
        assert "tokens_used" in result.model_dump()

    def test_min_similarity_filters(self, container, seeded_project):
        # Extreme threshold should return nothing
        req = SearchRequest(
            project=seeded_project, query="something completely unrelated blah blah",
            min_similarity=0.99,
        )
        result = container.search_service.search(req)
        assert result.total == 0
