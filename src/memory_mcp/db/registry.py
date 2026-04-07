"""Project registry CRUD operations on registry.duckdb."""

import threading
from datetime import datetime

import duckdb

from memory_mcp.config import settings
from memory_mcp.db.schema import create_registry_schema
from memory_mcp.models import ProjectInfo

_registry_conn: duckdb.DuckDBPyConnection | None = None
_registry_lock = threading.Lock()


def _get_registry() -> duckdb.DuckDBPyConnection:
    """Get or create the registry database connection."""
    global _registry_conn
    if _registry_conn is not None:
        return _registry_conn
    with _registry_lock:
        if _registry_conn is not None:
            return _registry_conn
        settings.ensure_dirs()
        _registry_conn = duckdb.connect(str(settings.registry_path))
        create_registry_schema(_registry_conn)
        return _registry_conn


def register_project(slug: str, display_name: str, description: str | None = None) -> ProjectInfo:
    """Register a new project in the registry."""
    conn = _get_registry()
    db_path = str(settings.projects_dir / f"{slug}.duckdb")

    # DuckDB ON CONFLICT doesn't support current_timestamp in SET clause
    existing = conn.execute("SELECT slug FROM projects WHERE slug = ?", [slug]).fetchone()
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

    return get_project(slug)


def get_project(slug: str) -> ProjectInfo | None:
    """Get a project by slug."""
    conn = _get_registry()
    result = conn.execute(
        "SELECT slug, display_name, description, created_at, last_accessed, db_path FROM projects WHERE slug = ?",
        [slug],
    ).fetchone()

    if not result:
        return None

    return ProjectInfo(
        slug=result[0],
        display_name=result[1],
        description=result[2],
        created_at=result[3],
        last_accessed=result[4],
        db_path=result[5],
    )


def list_projects() -> list[ProjectInfo]:
    """List all registered projects."""
    conn = _get_registry()
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


def touch_project(slug: str) -> None:
    """Update last_accessed timestamp."""
    conn = _get_registry()
    conn.execute(
        "UPDATE projects SET last_accessed = current_timestamp WHERE slug = ?",
        [slug],
    )


def delete_project(slug: str) -> bool:
    """Remove project from registry."""
    conn = _get_registry()
    conn.execute("DELETE FROM projects WHERE slug = ?", [slug])
    return True
