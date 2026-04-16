"""Test fixtures for memory-mcp tests."""

import pytest

from memory_mcp.config import settings
import memory_mcp.db.connection as conn_mod
import memory_mcp.repositories.project_repository as project_repo_mod


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path):
    """Use a temporary directory for all tests. Reset all process-level caches."""
    original = settings.data_dir
    settings.data_dir = tmp_path / "memory-mcp"
    settings.ensure_dirs()

    # Reset initialization flags so each test gets a fresh schema
    project_repo_mod._schema_initialized = False
    conn_mod._initialized_dbs.clear()

    yield tmp_path / "memory-mcp"

    project_repo_mod._schema_initialized = False
    conn_mod._initialized_dbs.clear()
    settings.data_dir = original


@pytest.fixture
def project_slug():
    return "test-project"
