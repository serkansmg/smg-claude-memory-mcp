"""Project initialization and management tools."""

from memory_mcp.config import settings
from memory_mcp.db.connection import get_connection
from memory_mcp.db.registry import register_project, list_projects, get_project
from memory_mcp.utils.text import slugify, validate_slug


def init_project(slug: str, display_name: str, description: str | None = None) -> dict:
    """Initialize a new project with DuckDB database and registry entry."""
    slug = slugify(slug) if not validate_slug(slug) else slug

    settings.ensure_dirs()

    # Register in registry
    project = register_project(slug, display_name, description)

    # Create project DB (triggers schema creation via connection manager)
    get_connection(slug)

    return {
        "status": "ok",
        "project": {
            "slug": project.slug,
            "display_name": project.display_name,
            "description": project.description,
            "db_path": project.db_path,
            "created_at": str(project.created_at) if project.created_at else None,
        },
    }


def list_all_projects() -> dict:
    """List all registered projects."""
    projects = list_projects()
    return {
        "projects": [
            {
                "slug": p.slug,
                "display_name": p.display_name,
                "description": p.description,
                "last_accessed": str(p.last_accessed) if p.last_accessed else None,
            }
            for p in projects
        ]
    }


def get_project_info(slug: str) -> dict:
    """Get info for a specific project."""
    project = get_project(slug)
    if not project:
        return {"error": f"Project '{slug}' not found"}
    return {
        "slug": project.slug,
        "display_name": project.display_name,
        "description": project.description,
        "created_at": str(project.created_at) if project.created_at else None,
        "last_accessed": str(project.last_accessed) if project.last_accessed else None,
    }
