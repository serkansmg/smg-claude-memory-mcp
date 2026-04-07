"""Test fixtures for memory-mcp tests."""

import pytest

from memory_mcp.config import settings
from memory_mcp.db.connection import get_manager
import memory_mcp.db.registry as registry_mod
from memory_mcp.tools.rules import _rules_cache


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path):
    """Use a temporary directory for all tests."""
    original = settings.data_dir
    settings.data_dir = tmp_path / "memory-mcp"
    settings.ensure_dirs()

    # Reset registry singleton so it uses the new data dir
    registry_mod._registry_conn = None

    # Clear rules cache
    _rules_cache.clear()

    yield tmp_path / "memory-mcp"

    # Cleanup
    get_manager().close_all()
    if registry_mod._registry_conn is not None:
        registry_mod._registry_conn.close()
        registry_mod._registry_conn = None
    settings.data_dir = original


@pytest.fixture
def project_slug():
    return "test-project"


@pytest.fixture
def initialized_project(project_slug):
    """Create and return an initialized test project."""
    from memory_mcp.tools.project import init_project

    result = init_project(project_slug, "Test Project", "A test project")
    return result
