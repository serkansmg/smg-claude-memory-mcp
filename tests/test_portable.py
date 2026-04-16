"""Integration tests for portable DB, export, and import - via service layer."""

import duckdb
import pytest

from memory_mcp.container import Container
from memory_mcp.db.schema import create_hnsw_index, create_schema
from memory_mcp.models import StoreMemoryRequest, MemoryCategory
from memory_mcp.services.portable_service import PORTABLE_DB_NAME


@pytest.fixture
def container():
    return Container()


class TestAttachProject:
    def test_attach_new_project(self, container, tmp_path):
        project_dir = tmp_path / "my-cool-project"
        project_dir.mkdir()

        result = container.portable_service.attach(str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "created_new"
        assert result["project"]["slug"] == "my-cool-project"

    def test_attach_project_with_existing_db(self, container, tmp_path):
        project_dir = tmp_path / "existing-project"
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
    def test_make_portable(self, container, tmp_path, project_slug):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        container.project_service.init_project(project_slug, "Test")
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.DECISION,
            title="Test", content="Test content",
        ))

        result = container.portable_service.make_portable(project_slug, str(project_dir))
        assert result["status"] == "ok"
        assert (project_dir / PORTABLE_DB_NAME).exists()


class TestSyncFromPortable:
    def test_sync(self, container, tmp_path):
        project_dir = tmp_path / "synced-project"
        project_dir.mkdir()
        db_path = project_dir / PORTABLE_DB_NAME

        conn = duckdb.connect(str(db_path))
        try:
            create_schema(conn)
            create_hnsw_index(conn)
            # Seed a memory
            import uuid
            from memory_mcp.embeddings import embed_text
            mid = str(uuid.uuid4())
            emb = embed_text("Test memory")
            conn.execute(
                "INSERT INTO memories (id, category, title, content, embedding, status, priority) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [mid, "decision", "Git Decision", "We use git", emb, "active", 0],
            )
        finally:
            conn.close()

        result = container.portable_service.sync(str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "synced"
        assert result["memories_count"] == 1


class TestExportImport:
    def test_export(self, container, tmp_path, project_slug):
        container.project_service.init_project(project_slug, "Test")
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.DECISION,
            title="Use PostgreSQL", content="Chose PostgreSQL for JSON.",
        ))
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.MANDATORY_RULES,
            title="Run Tests", content="Always run pytest.",
        ))
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.ARCHITECTURE,
            title="REST API", content="Using RESTful architecture.",
        ))

        project_dir = tmp_path / "export-test"
        project_dir.mkdir()

        result = container.export_import_service.export(project_slug, str(project_dir))
        assert result["status"] == "ok"
        assert result["exported"] == 3

        memory_dir = project_dir / ".memory"
        assert memory_dir.exists()
        assert (memory_dir / "MEMORY_INDEX.md").exists()
        assert (memory_dir / "README.md").exists()
        assert (memory_dir / "decision").is_dir()
        assert (memory_dir / "mandatory_rules").is_dir()
        assert (memory_dir / "architecture").is_dir()

    def test_export_then_import(self, container, tmp_path, project_slug):
        container.project_service.init_project(project_slug, "Test")
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.DECISION,
            title="Database", content="We chose PostgreSQL.",
        ))
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.MANDATORY_RULES,
            title="Test First", content="Always test.",
        ))

        project_dir = tmp_path / "roundtrip-test"
        project_dir.mkdir()
        container.export_import_service.export(project_slug, str(project_dir))

        container.project_service.init_project("import-test", "Import Test")
        result = container.export_import_service.import_from("import-test", str(project_dir))

        assert result["status"] == "ok"
        assert result["created"] == 2

    def test_exported_files_are_readable(self, container, tmp_path, project_slug):
        container.project_service.init_project(project_slug, "Test")
        container.memory_service.store(StoreMemoryRequest(
            project=project_slug, category=MemoryCategory.DECISION,
            title="Use Redis", content="Redis for caching.",
        ))

        project_dir = tmp_path / "readable-test"
        project_dir.mkdir()
        container.export_import_service.export(project_slug, str(project_dir))

        decision_dir = project_dir / ".memory" / "decision"
        files = list(decision_dir.glob("*.md"))
        assert len(files) == 1

        content = files[0].read_text()
        assert "---" in content
        assert "Use Redis" in content
        assert "Redis for caching" in content
        assert "category: decision" in content
