"""Portable DB management - attach existing projects, move DB to project dir, sync via git."""

import shutil
from pathlib import Path

from memory_mcp.config import settings
from memory_mcp.db.connection import get_connection, get_manager
from memory_mcp.db.registry import register_project, get_project, touch_project
from memory_mcp.db.schema import create_schema, create_hnsw_index, install_vss
from memory_mcp.utils.text import slugify, validate_slug

import duckdb

# Well-known filename when DB lives inside a project directory
PORTABLE_DB_NAME = ".memory-mcp.duckdb"


def attach_project(
    project_path: str,
    slug: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
) -> dict:
    """Attach an existing project directory to the memory MCP.

    If the project dir already contains a .memory-mcp.duckdb, use that.
    Otherwise create a new DB in the central store.

    Args:
        project_path: Absolute path to the project directory
        slug: Optional slug (auto-derived from directory name)
        display_name: Optional display name (auto-derived from directory name)
        description: Optional description
    """
    project_dir = Path(project_path).resolve()
    if not project_dir.is_dir():
        return {"error": f"Directory not found: {project_path}"}

    # Auto-derive slug and display name from directory
    dir_name = project_dir.name
    if not slug:
        slug = slugify(dir_name)
    if not validate_slug(slug):
        slug = slugify(slug)
    if not display_name:
        display_name = dir_name

    settings.ensure_dirs()

    # Check if project dir already has a portable DB
    portable_db = project_dir / PORTABLE_DB_NAME
    if portable_db.exists():
        # Register with the path pointing to the project's own DB
        project = register_project(slug, display_name, description)

        # Update registry to point to the portable DB path
        from memory_mcp.db.registry import _get_registry
        conn = _get_registry()
        conn.execute(
            "UPDATE projects SET db_path = ? WHERE slug = ?",
            [str(portable_db), slug],
        )

        return {
            "status": "ok",
            "action": "attached_existing_db",
            "project": {
                "slug": slug,
                "display_name": display_name,
                "db_path": str(portable_db),
                "project_path": str(project_dir),
            },
            "message": f"Found existing .memory-mcp.duckdb in project. Attached as '{slug}'.",
        }

    # No existing DB - create one in central store
    project = register_project(slug, display_name, description)

    # Create project DB via connection manager
    get_connection(slug)

    return {
        "status": "ok",
        "action": "created_new",
        "project": {
            "slug": slug,
            "display_name": display_name,
            "db_path": str(settings.projects_dir / f"{slug}.duckdb"),
            "project_path": str(project_dir),
        },
        "message": f"Created new memory DB for '{slug}'. Use memory_make_portable to move DB into the project directory for git sharing.",
    }


def make_portable(project: str, project_path: str) -> dict:
    """Move a project's DB from central store into the project directory.

    After this, the DB lives at <project_path>/.memory-mcp.duckdb and can be
    committed to git for team sharing.

    Args:
        project: Project slug
        project_path: Absolute path to the project directory
    """
    project_dir = Path(project_path).resolve()
    if not project_dir.is_dir():
        return {"error": f"Directory not found: {project_path}"}

    project_info = get_project(project)
    if not project_info:
        return {"error": f"Project '{project}' not found"}

    current_db = Path(project_info.db_path)
    target_db = project_dir / PORTABLE_DB_NAME

    # If already portable at this location
    if current_db == target_db:
        return {
            "status": "ok",
            "action": "already_portable",
            "db_path": str(target_db),
            "message": "DB is already in the project directory.",
        }

    # Close existing connection
    get_manager().remove(project)

    # Copy or move the DB file
    if current_db.exists():
        shutil.copy2(str(current_db), str(target_db))
        # Keep the central copy as backup
        backup_path = settings.backups_dir / f"{project}_pre-portable.duckdb"
        shutil.move(str(current_db), str(backup_path))
    else:
        # DB doesn't exist yet in central store, create at target
        conn = duckdb.connect(str(target_db))
        create_schema(conn)
        create_hnsw_index(conn)
        conn.close()

    # Update registry to point to the new location
    from memory_mcp.db.registry import _get_registry
    reg_conn = _get_registry()
    reg_conn.execute(
        "UPDATE projects SET db_path = ? WHERE slug = ?",
        [str(target_db), project],
    )

    # Suggest .gitignore entry for WAL files
    gitignore_path = project_dir / ".gitignore"
    wal_entry = "*.duckdb.wal"
    needs_gitignore_update = True
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if wal_entry in content:
            needs_gitignore_update = False

    return {
        "status": "ok",
        "action": "moved_to_project",
        "db_path": str(target_db),
        "backup": str(settings.backups_dir / f"{project}_pre-portable.duckdb") if current_db.exists() else None,
        "gitignore_hint": f"Add '{wal_entry}' to .gitignore" if needs_gitignore_update else None,
        "message": f"DB moved to {target_db}. Commit .memory-mcp.duckdb to git for team sharing.",
    }


def sync_from_portable(project_path: str, slug: str | None = None) -> dict:
    """Sync/register a portable DB found in a project directory.

    Use this after `git pull` on a new machine to pick up the shared DB.

    Args:
        project_path: Absolute path to the project directory
        slug: Optional slug (auto-derived from directory name)
    """
    project_dir = Path(project_path).resolve()
    portable_db = project_dir / PORTABLE_DB_NAME

    if not portable_db.exists():
        return {"error": f"No .memory-mcp.duckdb found in {project_path}"}

    if not slug:
        slug = slugify(project_dir.name)

    settings.ensure_dirs()

    # Register project pointing to the portable DB
    register_project(slug, project_dir.name)

    from memory_mcp.db.registry import _get_registry
    conn = _get_registry()
    conn.execute(
        "UPDATE projects SET db_path = ? WHERE slug = ?",
        [str(portable_db), slug],
    )

    # Verify the DB is valid by opening it
    try:
        test_conn = duckdb.connect(str(portable_db))
        install_vss(test_conn)
        count = test_conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        test_conn.close()
    except Exception as e:
        return {"error": f"DB exists but failed to open: {e}"}

    return {
        "status": "ok",
        "action": "synced",
        "project": {
            "slug": slug,
            "display_name": project_dir.name,
            "db_path": str(portable_db),
        },
        "memories_count": count,
        "message": f"Synced '{slug}' from portable DB ({count} memories). Ready to use.",
    }
