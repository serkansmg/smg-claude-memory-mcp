"""Unit tests for PortableService."""

import duckdb
import pytest

from memory_mcp.container import Container
from memory_mcp.db.schema import create_hnsw_index, create_schema
from memory_mcp.services.portable_service import PORTABLE_DB_NAME


@pytest.fixture
def container():
    return Container()


class TestAttach:
    def test_attach_creates_new_when_empty(self, container, tmp_path):
        project_dir = tmp_path / "new-project"
        project_dir.mkdir()
        result = container.portable_service.attach(str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "created_new"

    def test_attach_recognizes_existing_db(self, container, tmp_path):
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        db_path = project_dir / PORTABLE_DB_NAME

        conn = duckdb.connect(str(db_path))
        try:
            create_schema(conn)
            create_hnsw_index(conn)
        finally:
            conn.close()

        result = container.portable_service.attach(str(project_dir))
        assert result["action"] == "attached_existing_db"


class TestMakePortable:
    def test_make_portable_moves_db(self, container, tmp_path, project_slug):
        container.project_service.init_project(project_slug, "Test")
        project_dir = tmp_path / "portable-dest"
        project_dir.mkdir()
        result = container.portable_service.make_portable(project_slug, str(project_dir))
        assert result["status"] == "ok"
        assert (project_dir / PORTABLE_DB_NAME).exists()


class TestSync:
    def test_sync_registers_portable_db(self, container, tmp_path):
        project_dir = tmp_path / "synced"
        project_dir.mkdir()
        db_path = project_dir / PORTABLE_DB_NAME
        conn = duckdb.connect(str(db_path))
        try:
            create_schema(conn)
            create_hnsw_index(conn)
        finally:
            conn.close()

        result = container.portable_service.sync(str(project_dir))
        assert result["status"] == "ok"
        assert result["memories_count"] == 0
