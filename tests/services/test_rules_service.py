"""Unit tests for RulesService and RulesCache."""

import time

import pytest

from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.models import StoreMemoryRequest, MemoryCategory
from memory_mcp.services import RulesCache


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def project(container, project_slug):
    container.project_repo.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


class TestRulesService:
    def test_empty_rules(self, container, project):
        response = container.rules_service.get_rules(project)
        assert response.total == 0

    def test_separated_by_category(self, container, project):
        for cat in ("mandatory_rules", "mandatory_rules", "forbidden_rules"):
            container.memory_service.store(StoreMemoryRequest(
                project=project, category=MemoryCategory(cat),
                title=f"Rule {cat}", content="rule text",
            ))
        response = container.rules_service.get_rules(project)
        assert len(response.mandatory_rules) == 2
        assert len(response.forbidden_rules) == 1
        assert response.total == 3

    def test_cache_hit(self, container, project):
        container.memory_service.store(StoreMemoryRequest(
            project=project, category=MemoryCategory.MANDATORY_RULES,
            title="R", content="r",
        ))
        first = container.rules_service.get_rules(project)
        # Second call hits cache (same object)
        second = container.rules_service.get_rules(project)
        assert first is second  # same cached instance

    def test_invalidation_after_rule_store(self, container, project):
        container.rules_service.get_rules(project)
        # Storing a new rule should invalidate
        container.memory_service.store(StoreMemoryRequest(
            project=project, category=MemoryCategory.MANDATORY_RULES,
            title="Fresh", content="new rule",
        ))
        response = container.rules_service.get_rules(project)
        assert response.total == 1


class TestRulesCache:
    def test_ttl_expiration(self):
        from memory_mcp.models import RulesResponse
        cache = RulesCache(ttl=1)
        cache.set("proj", RulesResponse(mandatory_rules=[], forbidden_rules=[], total=0))
        assert cache.get("proj") is not None
        time.sleep(1.1)
        assert cache.get("proj") is None

    def test_invalidate(self):
        from memory_mcp.models import RulesResponse
        cache = RulesCache()
        cache.set("a", RulesResponse(mandatory_rules=[], forbidden_rules=[], total=0))
        cache.invalidate("a")
        assert cache.get("a") is None
