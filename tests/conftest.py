"""Test fixtures for memory-mcp tests."""

import pytest

from memory_mcp.config import settings
import memory_mcp.db.registry as registry_mod
import memory_mcp.db.connection as conn_mod
from memory_mcp.tools.rules import _rules_cache


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path):
    """Use a temporary directory for all tests."""
    original = settings.data_dir
    settings.data_dir = tmp_path / "memory-mcp"
    settings.ensure_dirs()

    # Reset registry schema flag
    registry_mod._schema_initialized = False

    # Reset connection initialized set
    conn_mod._initialized_dbs.clear()

    # Clear rules cache
    _rules_cache.clear()

    yield tmp_path / "memory-mcp"

    # Reset
    registry_mod._schema_initialized = False
    conn_mod._initialized_dbs.clear()
    settings.data_dir = original


@pytest.fixture
def project_slug():
    return "test-project"


@pytest.fixture
def initialized_project(project_slug):
    from memory_mcp.tools.project import init_project
    return init_project(project_slug, "Test Project", "A test project")
