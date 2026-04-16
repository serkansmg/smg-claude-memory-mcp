"""Portable service - attach, make portable, sync."""

import shutil
from pathlib import Path

import duckdb

from memory_mcp.config import settings
from memory_mcp.db.connection import get_connection
from memory_mcp.db.schema import create_hnsw_index, create_schema, install_vss
from memory_mcp.exceptions import ProjectNotFoundError
from memory_mcp.repositories import ProjectRepository
from memory_mcp.utils.text import slugify, validate_slug

PORTABLE_DB_NAME = ".memory-mcp.duckdb"


class PortableService:
    """Attach existing projects, move DBs for git sharing, and sync on new machines."""

    def __init__(self, project_repo: ProjectRepository):
        self._repo = project_repo

    def attach(
        self,
        project_path: str,
        slug: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
    ) -> dict:
        project_dir = Path(project_path).resolve()
        if not project_dir.is_dir():
            return {"error": f"Directory not found: {project_path}"}

        dir_name = project_dir.name
        if not slug:
            slug = slugify(dir_name)
        elif not validate_slug(slug):
            slug = slugify(slug)
        if not display_name:
            display_name = dir_name

        settings.ensure_dirs()

        portable_db = project_dir / PORTABLE_DB_NAME
        if portable_db.exists():
            self._repo.register(slug, display_name, description, db_path=str(portable_db))
            self._repo.update_db_path(slug, str(portable_db))
            return {
                "status": "ok",
                "action": "attached_existing_db",
                "project": {
                    "slug": slug, "display_name": display_name,
                    "db_path": str(portable_db), "project_path": str(project_dir),
                },
                "message": f"Found existing .memory-mcp.duckdb. Attached as '{slug}'.",
            }

        project = self._repo.register(slug, display_name, description)
        conn = get_connection(slug)
        conn.close()

        return {
            "status": "ok",
            "action": "created_new",
            "project": {
                "slug": slug, "display_name": display_name,
                "db_path": project.db_path, "project_path": str(project_dir),
            },
            "message": f"Created new memory DB for '{slug}'.",
        }

    def make_portable(self, project: str, project_path: str) -> dict:
        project_dir = Path(project_path).resolve()
        if not project_dir.is_dir():
            return {"error": f"Directory not found: {project_path}"}

        project_info = self._repo.get(project)
        if not project_info:
            raise ProjectNotFoundError(f"Project '{project}' not found")

        current_db = Path(project_info.db_path)
        target_db = project_dir / PORTABLE_DB_NAME

        if current_db == target_db:
            return {
                "status": "ok",
                "action": "already_portable",
                "db_path": str(target_db),
                "message": "DB is already in the project directory.",
            }

        if current_db.exists():
            shutil.copy2(str(current_db), str(target_db))
            backup_path = settings.backups_dir / f"{project}_pre-portable.duckdb"
            shutil.move(str(current_db), str(backup_path))
            backup_str = str(backup_path)
        else:
            conn = duckdb.connect(str(target_db))
            try:
                create_schema(conn)
                create_hnsw_index(conn)
            finally:
                conn.close()
            backup_str = None

        self._repo.update_db_path(project, str(target_db))

        gitignore_path = project_dir / ".gitignore"
        wal_entry = "*.duckdb.wal"
        gitignore_hint = None
        if not gitignore_path.exists() or wal_entry not in gitignore_path.read_text():
            gitignore_hint = f"Add '{wal_entry}' to .gitignore"

        return {
            "status": "ok",
            "action": "moved_to_project",
            "db_path": str(target_db),
            "backup": backup_str,
            "gitignore_hint": gitignore_hint,
            "message": f"DB moved to {target_db}. Commit .memory-mcp.duckdb to git.",
        }

    def sync(self, project_path: str, slug: str | None = None) -> dict:
        project_dir = Path(project_path).resolve()
        portable_db = project_dir / PORTABLE_DB_NAME

        if not portable_db.exists():
            return {"error": f"No .memory-mcp.duckdb found in {project_path}"}

        if not slug:
            slug = slugify(project_dir.name)

        settings.ensure_dirs()
        self._repo.register(slug, project_dir.name)
        self._repo.update_db_path(slug, str(portable_db))

        try:
            test_conn = duckdb.connect(str(portable_db))
            try:
                install_vss(test_conn)
                count = test_conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            finally:
                test_conn.close()
        except Exception as e:
            return {"error": f"DB exists but failed to open: {e}"}

        return {
            "status": "ok",
            "action": "synced",
            "project": {
                "slug": slug, "display_name": project_dir.name,
                "db_path": str(portable_db),
            },
            "memories_count": count,
            "message": f"Synced '{slug}' from portable DB ({count} memories).",
        }
