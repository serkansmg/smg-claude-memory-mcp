"""Project repository - manages the registry.duckdb projects table."""

from contextlib import contextmanager

import duckdb

from memory_mcp.config import settings
from memory_mcp.db.schema import create_registry_schema
from memory_mcp.models import ProjectInfo

_schema_initialized = False


@contextmanager
def _registry_conn():
    """Open a registry connection, ensure schema, close on exit."""
    global _schema_initialized
    settings.ensure_dirs()
    conn = duckdb.connect(str(settings.registry_path))
    try:
        if not _schema_initialized:
            create_registry_schema(conn)
            _schema_initialized = True
        yield conn
    finally:
        conn.close()


class ProjectRepository:
    """Registry CRUD - per-operation connection, no locks held."""

    def register(
        self,
        slug: str,
        display_name: str,
        description: str | None = None,
        db_path: str | None = None,
    ) -> ProjectInfo:
        if db_path is None:
            db_path = str(settings.projects_dir / f"{slug}.duckdb")

        with _registry_conn() as conn:
            existing = conn.execute(
                "SELECT slug FROM projects WHERE slug = ?", [slug]
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE projects SET display_name = ?, description = ?, last_accessed = current_timestamp WHERE slug = ?",
                    [display_name, description, slug],
                )
            else:
                conn.execute(
                    "INSERT INTO projects (slug, display_name, description, db_path) VALUES (?, ?, ?, ?)",
                    [slug, display_name, description, db_path],
                )

        result = self.get(slug)
        if result is None:
            raise RuntimeError(f"Failed to register project '{slug}'")
        return result

    def get(self, slug: str) -> ProjectInfo | None:
        with _registry_conn() as conn:
            row = conn.execute(
                "SELECT slug, display_name, description, created_at, last_accessed, db_path FROM projects WHERE slug = ?",
                [slug],
            ).fetchone()
        if not row:
            return None
        return ProjectInfo(
            slug=row[0], display_name=row[1], description=row[2],
            created_at=row[3], last_accessed=row[4], db_path=row[5],
        )

    def list_all(self) -> list[ProjectInfo]:
        with _registry_conn() as conn:
            rows = conn.execute(
                "SELECT slug, display_name, description, created_at, last_accessed, db_path FROM projects ORDER BY last_accessed DESC"
            ).fetchall()
        return [
            ProjectInfo(
                slug=r[0], display_name=r[1], description=r[2],
                created_at=r[3], last_accessed=r[4], db_path=r[5],
            )
            for r in rows
        ]

    def touch(self, slug: str) -> None:
        with _registry_conn() as conn:
            conn.execute(
                "UPDATE projects SET last_accessed = current_timestamp WHERE slug = ?",
                [slug],
            )

    def update_db_path(self, slug: str, db_path: str) -> None:
        with _registry_conn() as conn:
            conn.execute(
                "UPDATE projects SET db_path = ? WHERE slug = ?",
                [db_path, slug],
            )

    def delete(self, slug: str) -> None:
        with _registry_conn() as conn:
            conn.execute("DELETE FROM projects WHERE slug = ?", [slug])
