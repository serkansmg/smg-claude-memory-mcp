"""Core integration tests for memory-mcp."""

import pytest


class TestProjectInit:
    def test_init_project(self, project_slug):
        from memory_mcp.tools.project import init_project

        result = init_project(project_slug, "Test Project", "A test")
        assert result["status"] == "ok"
        assert result["project"]["slug"] == project_slug

    def test_list_projects(self, initialized_project):
        from memory_mcp.tools.project import list_all_projects

        result = list_all_projects()
        assert len(result["projects"]) >= 1


class TestStoreAndRecall:
    def test_store_memory(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory

        result = store_memory(
            project=project_slug,
            category="decision",
            title="Use PostgreSQL",
            content="We chose PostgreSQL for JSON support and reliability.",
            tags=["database", "backend"],
        )
        assert result["status"] == "ok"
        assert result["memory"]["title"] == "Use PostgreSQL"
        assert result["memory"]["category"] == "decision"
        # New features
        assert result["memory"]["summary"] is not None
        assert isinstance(result["memory"]["entities"], list)

    def test_store_auto_summary(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory

        result = store_memory(
            project=project_slug,
            category="architecture",
            title="API Gateway",
            content="All requests go through Kong API gateway for rate limiting and auth.",
        )
        assert result["memory"]["summary"]
        assert len(result["memory"]["summary"]) > 0

    def test_store_auto_entities(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory

        result = store_memory(
            project=project_slug,
            category="decision",
            title="Tech Stack",
            content="Using React with TypeScript frontend, FastAPI backend, PostgreSQL database, and Docker for deployment.",
        )
        entities = result["memory"]["entities"]
        assert len(entities) > 0
        # Should detect tech names
        assert any("React" in e for e in entities)

    def test_store_rules_never_expire(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory

        result = store_memory(
            project=project_slug,
            category="mandatory_rules",
            title="Always Test",
            content="Run tests before every commit.",
        )
        assert result["memory"]["expires_at"] is None
        assert result["memory"]["priority"] >= 2

    def test_store_with_ttl(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory

        result = store_memory(
            project=project_slug,
            category="session",
            title="Session Note",
            content="Worked on auth module today.",
        )
        # Session category has 30-day TTL
        assert result["memory"]["expires_at"] is not None

    def test_recall_by_id(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.recall import recall_memory

        stored = store_memory(
            project=project_slug,
            category="architecture",
            title="Microservices",
            content="Using microservices architecture with Kong API gateway.",
        )
        memory_id = stored["memory"]["id"]

        recalled = recall_memory(project=project_slug, memory_id=memory_id)
        assert recalled["memory"]["title"] == "Microservices"

    def test_recall_by_title(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.recall import recall_memory

        store_memory(
            project=project_slug,
            category="decision",
            title="JWT Authentication",
            content="Using JWT for stateless auth.",
        )

        recalled = recall_memory(project=project_slug, title="JWT Authentication")
        assert recalled["memory"]["content"] == "Using JWT for stateless auth."


class TestSearch:
    def test_semantic_search(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.search import search_memories

        store_memory(project_slug, "decision", "Database Choice", "We chose PostgreSQL for its JSON support.")
        store_memory(project_slug, "architecture", "API Design", "REST API with OpenAPI spec.")
        store_memory(project_slug, "devops", "Docker Setup", "Using Docker Compose for local dev.")

        results = search_memories(project_slug, "which database are we using?")
        assert len(results["results"]) > 0
        assert "PostgreSQL" in results["results"][0]["memory"]["content"]

    def test_search_with_category_filter(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.search import search_memories

        store_memory(project_slug, "decision", "DB Decision", "PostgreSQL chosen.")
        store_memory(project_slug, "devops", "DB Deployment", "PostgreSQL on RDS.")

        results = search_memories(project_slug, "PostgreSQL", category="devops")
        for r in results["results"]:
            assert r["memory"]["category"] == "devops"

    def test_search_with_token_budget(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.search import search_memories

        store_memory(project_slug, "decision", "Short", "Brief content.")
        store_memory(project_slug, "decision", "Long", "A" * 2000)

        results = search_memories(project_slug, "content", token_budget=100)
        assert "index" in results
        assert "details" in results
        assert "tokens_used" in results


class TestRules:
    def test_store_and_get_rules(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.rules import get_rules

        store_memory(project_slug, "mandatory_rules", "Run Tests", "Always run pytest before committing.")
        store_memory(project_slug, "forbidden_rules", "No Force Push", "Never force push to main.")

        rules = get_rules(project_slug)
        assert len(rules["mandatory_rules"]) == 1
        assert len(rules["forbidden_rules"]) == 1
        assert rules["mandatory_rules"][0]["priority"] >= 2

    def test_rules_are_cached(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.rules import get_rules, _rules_cache

        store_memory(project_slug, "mandatory_rules", "Test Rule", "Test content.")

        get_rules(project_slug)
        assert project_slug in _rules_cache

        result = get_rules(project_slug)
        assert result["total"] == 1


class TestUpdateAndDelete:
    def test_update_content(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.update import update_memory

        stored = store_memory(project_slug, "decision", "Original", "Original content.")
        memory_id = stored["memory"]["id"]

        updated = update_memory(project_slug, memory_id, content="Updated content.")
        assert updated["memory"]["content"] == "Updated content."
        # Summary should be regenerated
        assert updated["memory"]["summary"] is not None

    def test_soft_delete(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.delete import delete_memory

        stored = store_memory(project_slug, "decision", "To Delete", "Will be archived.")
        memory_id = stored["memory"]["id"]

        result = delete_memory(project_slug, memory_id, reason="No longer relevant")
        assert result["action"] == "archived"


class TestProvenance:
    def test_provenance_tracking(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.update import update_memory
        from memory_mcp.tools.recall import recall_memory
        from memory_mcp.db.provenance import get_provenance

        stored = store_memory(project_slug, "decision", "Tracked", "Original.")
        memory_id = stored["memory"]["id"]

        update_memory(project_slug, memory_id, content="Updated.")
        recall_memory(project_slug, memory_id=memory_id)

        trail = get_provenance(project_slug, memory_id)
        operations = [t["operation"] for t in trail]
        assert "create" in operations
        assert "update" in operations
        assert "access" in operations


class TestSession:
    def test_session_lifecycle(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.session import session_start, session_end

        store_memory(project_slug, "mandatory_rules", "Always Test", "Run tests first.")
        store_memory(project_slug, "sprint", "Sprint 1", "Implement auth module.")

        ctx = session_start(project_slug)
        assert ctx["session_id"]
        assert len(ctx["mandatory_rules"]) == 1
        assert ctx["project"] == project_slug

        result = session_end(project_slug, ctx["session_id"], "Completed auth module.")
        assert result["status"] == "ok"

        ctx2 = session_start(project_slug)
        assert ctx2["last_session_summary"] == "Completed auth module."


class TestListMemories:
    def test_list_with_pagination(self, initialized_project, project_slug):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.list_memories import list_memories

        for i in range(5):
            store_memory(project_slug, "decision", f"Decision {i}", f"Content {i}")

        result = list_memories(project_slug, limit=2, offset=0)
        assert len(result["memories"]) == 2
        assert result["total"] == 5

        result2 = list_memories(project_slug, limit=2, offset=2)
        assert len(result2["memories"]) == 2


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
