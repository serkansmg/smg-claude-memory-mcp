"""Project registry - connection-per-operation, no locks."""

from contextlib import contextmanager

import duckdb

from memory_mcp.config import settings
from memory_mcp.db.schema import create_registry_schema
from memory_mcp.models import ProjectInfo

_schema_initialized = False


@contextmanager
def _registry():
    """Open a registry connection, use it, close immediately."""
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


def _get_registry():
    """Legacy compat: returns an open connection. Caller must be careful."""
    global _schema_initialized
    settings.ensure_dirs()
    conn = duckdb.connect(str(settings.registry_path))
    if not _schema_initialized:
        create_registry_schema(conn)
        _schema_initialized = True
    return conn


def register_project(slug: str, display_name: str, description: str | None = None) -> ProjectInfo:
    db_path = str(settings.projects_dir / f"{slug}.duckdb")
    with _registry() as conn:
        existing = conn.execute("SELECT slug FROM projects WHERE slug = ?", [slug]).fetchone()
        if existing:
            conn.execute("UPDATE projects SET display_name = ?, description = ?, last_accessed = current_timestamp WHERE slug = ?",
                         [display_name, description, slug])
        else:
            conn.execute("INSERT INTO projects (slug, display_name, description, db_path) VALUES (?, ?, ?, ?)",
                         [slug, display_name, description, db_path])
    return get_project(slug)


def get_project(slug: str) -> ProjectInfo | None:
    with _registry() as conn:
        result = conn.execute(
            "SELECT slug, display_name, description, created_at, last_accessed, db_path FROM projects WHERE slug = ?", [slug]
        ).fetchone()
    if not result:
        return None
    return ProjectInfo(slug=result[0], display_name=result[1], description=result[2],
                       created_at=result[3], last_accessed=result[4], db_path=result[5])


def list_projects() -> list[ProjectInfo]:
    with _registry() as conn:
        rows = conn.execute(
            "SELECT slug, display_name, description, created_at, last_accessed, db_path FROM projects ORDER BY last_accessed DESC"
        ).fetchall()
    return [ProjectInfo(slug=r[0], display_name=r[1], description=r[2],
                        created_at=r[3], last_accessed=r[4], db_path=r[5]) for r in rows]


def touch_project(slug: str) -> None:
    with _registry() as conn:
        conn.execute("UPDATE projects SET last_accessed = current_timestamp WHERE slug = ?", [slug])


def delete_project(slug: str) -> bool:
    with _registry() as conn:
        conn.execute("DELETE FROM projects WHERE slug = ?", [slug])
    return True
