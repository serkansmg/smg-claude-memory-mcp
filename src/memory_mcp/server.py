"""FastMCP server - thin tool layer over the service container.

Each @mcp.tool() is a minimal wrapper:
1. Resolve the project (explicit > active > CWD-detected)
2. Build a request model from inputs
3. Call the service method
4. Return a dict response (or error)
"""

import os

from fastmcp import FastMCP

from memory_mcp.container import container
from memory_mcp.context import (
    load_active_project, resolve_project, set_active_project,
)
from memory_mcp.exceptions import MemoryMCPError
from memory_mcp.models import (
    MemoryCategory, StoreMemoryRequest, UpdateMemoryRequest, SearchRequest,
    MemoryFilter, Pagination,
)

# Load persisted state at startup
container.model_service.load_persisted()
load_active_project()

mcp = FastMCP("memory-mcp")


# ---------- Helpers ----------


def _resolve(project: str | None) -> str:
    """Resolve project slug: explicit > active > CWD-detected. Raises if none."""
    slug = resolve_project(project, os.getcwd())
    if not slug:
        raise ValueError(
            "No project specified and none detected. "
            "Use memory_use('slug') to set active project, or pass project= explicitly."
        )
    return slug


def _safe(fn):
    """Wrap a tool body with uniform error handling."""
    try:
        return fn()
    except MemoryMCPError as e:
        return {"error": str(e), "type": type(e).__name__}
    except ValueError as e:
        return {"error": str(e), "type": "ValueError"}


# ---------- Version ----------


@mcp.tool()
def memory_version() -> dict:
    """Get the current version of the Memory MCP server and configuration."""
    from memory_mcp import __version__
    from memory_mcp.config import settings
    from memory_mcp.context import _active_project

    return {
        "version": __version__,
        "model": settings.embedding_model,
        "model_preset": settings.model_preset,
        "embedding_dim": settings.embedding_dim,
        "data_dir": str(settings.data_dir),
        "active_project": _active_project,
    }


# ---------- Active Project ----------


@mcp.tool()
def memory_use(project: str) -> dict:
    """Set the active project. Subsequent tools use it by default."""
    set_active_project(project)
    return {"status": "ok", "active_project": project}


# ---------- Projects ----------


@mcp.tool()
def memory_init_project(
    slug: str,
    display_name: str,
    description: str | None = None,
    set_active: bool = True,
) -> dict:
    """Initialize a new project namespace (creates DuckDB + registers it)."""
    def _run():
        project = container.project_service.init_project(slug, display_name, description)
        result = {"status": "ok", "project": project.model_dump(mode="json")}
        if set_active:
            set_active_project(project.slug)
            result["active"] = True
        return result
    return _safe(_run)


@mcp.tool()
def memory_list_projects() -> dict:
    """List all registered projects."""
    projects = container.project_service.list_all()
    return {"projects": [p.model_dump(mode="json") for p in projects]}


@mcp.tool()
def memory_project_info(project: str | None = None) -> dict:
    """Get detailed info for a project."""
    def _run():
        p = container.project_service.get(_resolve(project))
        return p.model_dump(mode="json")
    return _safe(_run)


# ---------- Memory CRUD ----------


@mcp.tool()
def memory_store(
    category: str,
    title: str,
    content: str,
    project: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    priority: int = 0,
    source: str = "assistant",
    related_ids: list[str] | None = None,
) -> dict:
    """Store a new memory with auto-embedding, summary, entity extraction, and TTL."""
    def _run():
        req = StoreMemoryRequest(
            project=_resolve(project),
            category=MemoryCategory(category),
            title=title,
            content=content,
            tags=tags or [],
            metadata=metadata,
            priority=priority,
            source=source,
            related_ids=related_ids or [],
        )
        memory = container.memory_service.store(req)
        return {"status": "ok", "memory": memory.model_dump(mode="json")}
    return _safe(_run)


@mcp.tool()
def memory_search(
    query: str,
    project: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    status: str = "active",
    limit: int = 10,
    min_similarity: float = 0.3,
    token_budget: int | None = None,
) -> dict:
    """Semantic search with composite relevance scoring."""
    def _run():
        req = SearchRequest(
            project=_resolve(project),
            query=query,
            category=MemoryCategory(category) if category else None,
            tags=tags,
            status=status,
            limit=limit,
            min_similarity=min_similarity,
            token_budget=token_budget,
        )
        response = container.search_service.search(req)
        return response.model_dump(mode="json")
    return _safe(_run)


@mcp.tool()
def memory_recall(
    project: str | None = None,
    memory_id: str | None = None,
    title: str | None = None,
) -> dict:
    """Recall a specific memory by ID or exact title."""
    def _run():
        memory = container.memory_service.recall(_resolve(project), memory_id, title)
        return {"memory": memory.model_dump(mode="json")}
    return _safe(_run)


@mcp.tool()
def memory_update(
    memory_id: str,
    project: str | None = None,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    status: str | None = None,
    priority: int | None = None,
    related_ids: list[str] | None = None,
) -> dict:
    """Update an existing memory. Re-embeds if title/content changed."""
    def _run():
        req = UpdateMemoryRequest(
            project=_resolve(project), memory_id=memory_id,
            title=title, content=content, tags=tags, metadata=metadata,
            status=status, priority=priority, related_ids=related_ids,
        )
        memory = container.memory_service.update(req)
        return {"status": "ok", "memory": memory.model_dump(mode="json")}
    return _safe(_run)


@mcp.tool()
def memory_delete(
    memory_id: str,
    project: str | None = None,
    hard: bool = False,
    reason: str | None = None,
) -> dict:
    """Soft-delete (archive) or hard-delete a memory."""
    def _run():
        return container.memory_service.delete(
            _resolve(project), memory_id, hard=hard, reason=reason,
        )
    return _safe(_run)


@mcp.tool()
def memory_list(
    project: str | None = None,
    category: str | None = None,
    status: str = "active",
    tags: list[str] | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List memories with filtering, sorting, and pagination."""
    def _run():
        slug = _resolve(project)
        filters = MemoryFilter(status=status, category=category, tags=tags)
        pagination = Pagination(
            limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order,
        )
        memories, total = container.memory_repo.list(slug, filters, pagination)
        return {
            "memories": [m.model_dump(mode="json") for m in memories],
            "total": total, "limit": limit, "offset": offset,
        }
    return _safe(_run)


# ---------- Provenance ----------


@mcp.tool()
def memory_provenance(memory_id: str, project: str | None = None) -> dict:
    """Get the full audit trail for a memory."""
    def _run():
        slug = _resolve(project)
        entries = container.provenance_repo.for_memory(slug, memory_id)
        return {
            "memory_id": memory_id,
            "provenance": [e.model_dump(mode="json") for e in entries],
            "total": len(entries),
        }
    return _safe(_run)


# ---------- Rules ----------


@mcp.tool()
def memory_get_rules(project: str | None = None) -> dict:
    """Get all mandatory and forbidden rules (direct SQL, cached)."""
    def _run():
        response = container.rules_service.get_rules(_resolve(project))
        return response.model_dump(mode="json")
    return _safe(_run)


# ---------- Sessions ----------


@mcp.tool()
def memory_session_start(project: str | None = None) -> dict:
    """Start a session. Loads rules, last summary, sprint goals, recent decisions."""
    def _run():
        slug = _resolve(project)
        set_active_project(slug)
        ctx = container.session_service.start(slug)
        return ctx.model_dump(mode="json")
    return _safe(_run)


@mcp.tool()
def memory_session_end(
    session_id: str,
    summary: str,
    project: str | None = None,
    memories_created: int = 0,
    memories_accessed: int = 0,
) -> dict:
    """End a session and store its summary."""
    def _run():
        return container.session_service.end(
            _resolve(project), session_id, summary,
            memories_created, memories_accessed,
        )
    return _safe(_run)


# ---------- Portability ----------


@mcp.tool()
def memory_attach_project(
    project_path: str,
    slug: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
) -> dict:
    """Attach an existing project directory. Auto-activates on success."""
    def _run():
        result = container.portable_service.attach(
            project_path, slug, display_name, description,
        )
        if result.get("status") == "ok":
            project_slug = result.get("project", {}).get("slug")
            if project_slug:
                set_active_project(project_slug)
                result["active"] = True
        return result
    return _safe(_run)


@mcp.tool()
def memory_make_portable(
    project_path: str,
    project: str | None = None,
) -> dict:
    """Move the project's DB into the project directory for git sharing."""
    def _run():
        return container.portable_service.make_portable(_resolve(project), project_path)
    return _safe(_run)


@mcp.tool()
def memory_sync(project_path: str, slug: str | None = None) -> dict:
    """Sync a portable DB after git pull. Auto-activates on success."""
    def _run():
        result = container.portable_service.sync(project_path, slug)
        if result.get("status") == "ok":
            project_slug = result.get("project", {}).get("slug")
            if project_slug:
                set_active_project(project_slug)
        return result
    return _safe(_run)


# ---------- Export / Import ----------


@mcp.tool()
def memory_export(export_path: str, project: str | None = None) -> dict:
    """Export all active memories to human-readable .md files."""
    def _run():
        return container.export_import_service.export(_resolve(project), export_path)
    return _safe(_run)


@mcp.tool()
def memory_import(import_path: str, project: str | None = None) -> dict:
    """Import memories from exported .md files."""
    def _run():
        return container.export_import_service.import_from(_resolve(project), import_path)
    return _safe(_run)


# ---------- Model Management ----------


@mcp.tool()
def memory_model_info() -> dict:
    """Current embedding model + available presets."""
    return container.model_service.info()


@mcp.tool()
def memory_set_model(
    preset: str,
    project: str | None = None,
    confirm: bool = False,
) -> dict:
    """Switch embedding model between 'english' and 'multilingual' presets."""
    def _run():
        slug = _resolve(project) if project else None
        return container.model_service.set_model(preset, slug, confirm)
    return _safe(_run)


@mcp.tool()
def memory_reembed(project: str | None = None) -> dict:
    """Re-embed all active memories with the current model."""
    def _run():
        return container.model_service.reembed(_resolve(project))
    return _safe(_run)


# ---------- Entrypoint ----------


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
