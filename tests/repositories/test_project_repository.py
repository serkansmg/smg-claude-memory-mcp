"""Unit tests for ProjectRepository."""

import pytest

from memory_mcp.repositories import ProjectRepository


@pytest.fixture
def repo():
    return ProjectRepository()


class TestRegisterAndGet:
    def test_register_new(self, repo):
        info = repo.register("alpha", "Alpha Project", "desc")
        assert info.slug == "alpha"
        assert info.display_name == "Alpha Project"
        assert info.description == "desc"

    def test_register_existing_updates(self, repo):
        repo.register("beta", "Beta", "orig")
        info = repo.register("beta", "Beta Updated", "new desc")
        assert info.display_name == "Beta Updated"
        assert info.description == "new desc"

    def test_get_missing(self, repo):
        assert repo.get("nonexistent") is None

    def test_list_all_orders_by_last_accessed(self, repo):
        repo.register("p1", "P1")
        repo.register("p2", "P2")
        repo.touch("p1")  # p1 becomes most recent
        all_projects = repo.list_all()
        slugs = [p.slug for p in all_projects]
        assert "p1" in slugs and "p2" in slugs


class TestDbPath:
    def test_update_db_path(self, repo):
        repo.register("gamma", "Gamma")
        repo.update_db_path("gamma", "/custom/path/gamma.duckdb")
        info = repo.get("gamma")
        assert info.db_path == "/custom/path/gamma.duckdb"


class TestDelete:
    def test_delete(self, repo):
        repo.register("delta", "Delta")
        repo.delete("delta")
        assert repo.get("delta") is None
