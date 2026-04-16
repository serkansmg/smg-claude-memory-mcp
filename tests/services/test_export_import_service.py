"""Unit tests for ExportImportService."""

import pytest

from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.models import StoreMemoryRequest, MemoryCategory


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def project(container, project_slug):
    container.project_repo.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    container.memory_service.store(StoreMemoryRequest(
        project=project_slug, category=MemoryCategory.DECISION,
        title="PostgreSQL", content="Chose PostgreSQL for JSON support.",
    ))
    container.memory_service.store(StoreMemoryRequest(
        project=project_slug, category=MemoryCategory.MANDATORY_RULES,
        title="Tests", content="Always run pytest.",
    ))
    return project_slug


class TestExportImport:
    def test_export_creates_files(self, container, project, tmp_path):
        target = tmp_path / "exp"
        target.mkdir()
        result = container.export_import_service.export(project, str(target))
        assert result["exported"] == 2
        assert (target / ".memory" / "MEMORY_INDEX.md").exists()
        assert (target / ".memory" / "decision").is_dir()

    def test_import_roundtrip(self, container, project, tmp_path):
        target = tmp_path / "roundtrip"
        target.mkdir()
        container.export_import_service.export(project, str(target))

        container.project_service.init_project("import-test", "Import Test")
        result = container.export_import_service.import_from("import-test", str(target))
        assert result["created"] == 2
