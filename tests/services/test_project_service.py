"""Unit tests for ProjectService."""

import pytest

from memory_mcp.container import Container
from memory_mcp.exceptions import ProjectNotFoundError


@pytest.fixture
def container():
    return Container()


class TestProjectService:
    def test_init_project(self, container):
        info = container.project_service.init_project("alpha", "Alpha")
        assert info.slug == "alpha"

    def test_get_missing_raises(self, container):
        with pytest.raises(ProjectNotFoundError):
            container.project_service.get("does-not-exist")

    def test_list_all(self, container):
        container.project_service.init_project("x", "X")
        container.project_service.init_project("y", "Y")
        projects = container.project_service.list_all()
        slugs = [p.slug for p in projects]
        assert "x" in slugs
        assert "y" in slugs
