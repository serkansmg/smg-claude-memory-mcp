"""Tests for portable DB, export, and import features."""

import pytest
from pathlib import Path


class TestAttachProject:
    def test_attach_new_project(self, temp_data_dir, tmp_path):
        from memory_mcp.tools.portable import attach_project

        project_dir = tmp_path / "my-cool-project"
        project_dir.mkdir()

        result = attach_project(str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "created_new"
        assert result["project"]["slug"] == "my-cool-project"

    def test_attach_project_with_existing_db(self, temp_data_dir, tmp_path):
        from memory_mcp.tools.portable import attach_project, PORTABLE_DB_NAME
        import duckdb
        from memory_mcp.db.schema import create_schema, create_hnsw_index

        project_dir = tmp_path / "existing-project"
        project_dir.mkdir()

        # Create a portable DB in the project
        db_path = project_dir / PORTABLE_DB_NAME
        conn = duckdb.connect(str(db_path))
        create_schema(conn)
        create_hnsw_index(conn)
        conn.close()

        result = attach_project(str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "attached_existing_db"


class TestMakePortable:
    def test_make_portable(self, initialized_project, project_slug, tmp_path):
        from memory_mcp.tools.portable import make_portable, PORTABLE_DB_NAME
        from memory_mcp.tools.store import store_memory

        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        # Store some data first
        store_memory(project_slug, "decision", "Test", "Test content")

        result = make_portable(project_slug, str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "moved_to_project"
        assert (project_dir / PORTABLE_DB_NAME).exists()


class TestSyncFromPortable:
    def test_sync(self, temp_data_dir, tmp_path):
        from memory_mcp.tools.portable import PORTABLE_DB_NAME, sync_from_portable
        import duckdb
        from memory_mcp.db.schema import create_schema, create_hnsw_index

        project_dir = tmp_path / "synced-project"
        project_dir.mkdir()

        # Simulate git pull with a DB
        db_path = project_dir / PORTABLE_DB_NAME
        conn = duckdb.connect(str(db_path))
        create_schema(conn)
        create_hnsw_index(conn)
        # Add a test memory
        import uuid
        from memory_mcp.embeddings import embed_text
        mid = str(uuid.uuid4())
        emb = embed_text("Test memory")
        conn.execute(
            "INSERT INTO memories (id, category, title, content, embedding, status, priority) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [mid, "decision", "Git Decision", "We use git for version control", emb, "active", 0],
        )
        conn.close()

        result = sync_from_portable(str(project_dir))
        assert result["status"] == "ok"
        assert result["action"] == "synced"
        assert result["memories_count"] == 1


class TestExportImport:
    def test_export(self, initialized_project, project_slug, tmp_path):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.export_import import export_memories

        store_memory(project_slug, "decision", "Use PostgreSQL", "Chose PostgreSQL for JSON support.")
        store_memory(project_slug, "mandatory_rules", "Run Tests", "Always run pytest.")
        store_memory(project_slug, "architecture", "REST API", "Using RESTful architecture.")

        project_dir = tmp_path / "export-test"
        project_dir.mkdir()

        result = export_memories(project_slug, str(project_dir))
        assert result["status"] == "ok"
        assert result["exported"] == 3

        # Check directory structure
        memory_dir = project_dir / ".memory"
        assert memory_dir.exists()
        assert (memory_dir / "MEMORY_INDEX.md").exists()
        assert (memory_dir / "README.md").exists()
        assert (memory_dir / "decision").is_dir()
        assert (memory_dir / "mandatory_rules").is_dir()
        assert (memory_dir / "architecture").is_dir()

    def test_export_then_import(self, initialized_project, project_slug, temp_data_dir, tmp_path):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.export_import import export_memories, import_memories
        from memory_mcp.tools.project import init_project

        # Store memories in original project
        store_memory(project_slug, "decision", "Database Choice", "We chose PostgreSQL.")
        store_memory(project_slug, "mandatory_rules", "Test First", "Always test before commit.")

        # Export
        project_dir = tmp_path / "roundtrip-test"
        project_dir.mkdir()
        export_memories(project_slug, str(project_dir))

        # Create a new project and import
        init_project("import-test", "Import Test")
        result = import_memories("import-test", str(project_dir))

        assert result["status"] == "ok"
        assert result["created"] == 2
        assert result["skipped"] == 0

    def test_exported_files_are_readable(self, initialized_project, project_slug, tmp_path):
        from memory_mcp.tools.store import store_memory
        from memory_mcp.tools.export_import import export_memories

        store_memory(project_slug, "decision", "Use Redis", "Redis for caching and session storage.")

        project_dir = tmp_path / "readable-test"
        project_dir.mkdir()
        export_memories(project_slug, str(project_dir))

        # Read the exported file
        decision_dir = project_dir / ".memory" / "decision"
        files = list(decision_dir.glob("*.md"))
        assert len(files) == 1

        content = files[0].read_text()
        assert "---" in content  # Has frontmatter
        assert "Use Redis" in content  # Has title
        assert "Redis for caching" in content  # Has content
        assert "category: decision" in content  # Has metadata
