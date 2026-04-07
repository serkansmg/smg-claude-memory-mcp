"""Active project context - auto-detect from CWD or explicit set."""

import json
import threading
from pathlib import Path

from memory_mcp.config import settings
from memory_mcp.tools.portable import PORTABLE_DB_NAME

_active_project: str | None = None
_lock = threading.Lock()

# State file for persisting active project between sessions
STATE_FILE = ".memory-mcp-active"


def set_active_project(slug: str) -> None:
    """Set the active project slug."""
    global _active_project
    with _lock:
        _active_project = slug


def get_active_project(cwd: str | None = None) -> str | None:
    """Get the active project, with CWD auto-detection fallback.

    Resolution order:
    1. Explicitly set active project (via memory_use)
    2. CWD-based detection: walk up from cwd looking for .memory-mcp.duckdb
    3. CWD-based detection: match cwd directory name to registered project slug
    4. None
    """
    global _active_project

    # 1. Explicit
    if _active_project:
        return _active_project

    if not cwd:
        return None

    cwd_path = Path(cwd).resolve()

    # 2. Walk up looking for .memory-mcp.duckdb
    check = cwd_path
    for _ in range(10):  # Max 10 levels up
        portable_db = check / PORTABLE_DB_NAME
        if portable_db.exists():
            slug = _slug_from_path(check)
            if slug:
                return slug
        if check.parent == check:
            break
        check = check.parent

    # 3. Match directory name to registered projects
    slug = _slug_from_path(cwd_path)
    if slug:
        return slug

    return None


def _slug_from_path(path: Path) -> str | None:
    """Try to find a registered project matching this path."""
    from memory_mcp.db.registry import list_projects
    from memory_mcp.utils.text import slugify

    dir_name = path.name
    dir_slug = slugify(dir_name)

    try:
        projects = list_projects()
        for p in projects:
            if p.slug == dir_slug:
                return p.slug
            # Also check if db_path is inside this directory
            if p.db_path and path.as_posix() in p.db_path:
                return p.slug
    except Exception:
        pass

    return None


def resolve_project(project: str | None = None, cwd: str | None = None) -> str | None:
    """Resolve project slug: explicit > active > cwd-detected.

    This is the main function tools should call to resolve the project.
    """
    if project:
        return project
    return get_active_project(cwd)
