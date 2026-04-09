"""FastMCP server - tool registration and entrypoint."""

import os

from fastmcp import FastMCP

from memory_mcp.context import set_active_project, resolve_project, load_active_project
from memory_mcp.tools.project import init_project, list_all_projects, get_project_info
from memory_mcp.tools.store import store_memory
from memory_mcp.tools.recall import recall_memory
from memory_mcp.tools.search import search_memories
from memory_mcp.tools.update import update_memory
from memory_mcp.tools.delete import delete_memory
from memory_mcp.tools.list_memories import list_memories
from memory_mcp.tools.rules import get_rules
from memory_mcp.tools.session import session_start, session_end
from memory_mcp.db.provenance import get_provenance
from memory_mcp.tools.portable import attach_project, make_portable, sync_from_portable
from memory_mcp.tools.export_import import export_memories, import_memories
from memory_mcp.tools.model_manager import get_model_info, set_model, reembed_project, load_persisted_model

# Load persisted config before anything else
load_persisted_model()
load_active_project()

mcp = FastMCP("memory-mcp")


def _resolve(project: str | None) -> str:
    """Resolve project slug: explicit > active > cwd-detected. Raises if none found."""
    slug = resolve_project(project, os.getcwd())
    if not slug:
        raise ValueError(
            "No project specified and none detected. "
            "Use memory_use('slug') to set active project, "
            "or pass project= explicitly."
        )
    return slug


# --- Version ---


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


# --- Active Project ---


@mcp.tool()
def memory_use(project: str) -> dict:
    """Set the active project. After this, all other tools use this project by default.

    No need to pass project= to every tool call anymore.
    Also auto-detected from CWD if the project was attached via memory_attach_project.

    Args:
        project: Project slug to set as active
    """
    set_active_project(project)
    return {"status": "ok", "active_project": project, "message": f"Active project set to '{project}'. All tools will use this project by default."}


# --- Project Management ---


@mcp.tool()
def memory_init_project(
    slug: str,
    display_name: str,
    description: str | None = None,
    set_active: bool = True,
) -> dict:
    """Initialize a new project memory namespace.

    Creates a dedicated DuckDB database with vector search support.
    Call this once per project before storing memories.
    Automatically sets the project as active.

    Args:
        slug: URL-safe project identifier (e.g., 'my-web-app')
        display_name: Human-readable project name
        description: Optional project description
        set_active: Set this project as active (default: True)
    """
    result = init_project(slug, display_name, description)
    if set_active and result.get("status") == "ok":
        set_active_project(slug)
        result["active"] = True
    return result


@mcp.tool()
def memory_list_projects() -> dict:
    """List all registered projects with their last access time."""
    return list_all_projects()


@mcp.tool()
def memory_project_info(project: str | None = None) -> dict:
    """Get detailed info for a project.

    Args:
        project: Project slug (optional if active project is set)
    """
    return get_project_info(_resolve(project))


# --- Core Memory Operations ---


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
    """Store a new memory with automatic vector embedding, summary, entity extraction, and TTL.

    Categories: decision, session, sprint, project_plan, architecture, devops,
    mandatory_rules, forbidden_rules, developer_docs, feedback, reference.

    Auto-features:
    - Vector embedding for semantic search
    - 15-20 word summary generation
    - Entity extraction (tech names, @mentions, #tags, acronyms)
    - TTL/expiration based on category and priority
    - Provenance audit trail

    Rules (mandatory_rules, forbidden_rules) automatically get priority=2 and never expire.

    Args:
        category: Memory category
        title: Short descriptive title
        content: Full memory content
        project: Project slug (optional if active project is set)
        tags: Optional tags for filtering
        metadata: Optional JSON metadata
        priority: Priority level (0=normal, auto-set for rules)
        source: Who created this (assistant, user, system)
        related_ids: IDs of related memories
    """
    return store_memory(_resolve(project), category, title, content, tags, metadata, priority, source, related_ids)


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
    """Semantic search across memories using vector similarity.

    Uses HNSW-accelerated cosine similarity with composite relevance scoring
    (similarity + recency + access frequency).

    Supports token budgeting: when token_budget is set, returns a dual-phase response:
    - index: all matches as summary-only (lightweight)
    - details: top matches with full content, within token budget

    Args:
        query: Natural language search query
        project: Project slug (optional if active project is set)
        category: Optional category filter
        tags: Optional tag filter (matches any)
        status: Filter by status (default: active)
        limit: Max results to return
        min_similarity: Minimum cosine similarity threshold
        token_budget: Optional max tokens for response content
    """
    return search_memories(_resolve(project), query, category, tags, status, limit, min_similarity, token_budget)


@mcp.tool()
def memory_recall(
    project: str | None = None,
    memory_id: str | None = None,
    title: str | None = None,
) -> dict:
    """Recall a specific memory by ID or exact title.

    Increments the access counter and records provenance.

    Args:
        project: Project slug (optional if active project is set)
        memory_id: Exact memory UUID
        title: Exact title match
    """
    return recall_memory(_resolve(project), memory_id, title)


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
    """Update an existing memory. Only provided fields are changed.

    Automatically re-generates embedding, summary, and entities if title or content changes.
    Records all changes in the provenance audit trail.

    Args:
        memory_id: ID of memory to update
        project: Project slug (optional if active project is set)
        title: New title (triggers re-embedding)
        content: New content (triggers re-embedding)
        tags: Replace tags
        metadata: Replace metadata
        status: New status (active, archived)
        priority: New priority
        related_ids: Replace related IDs
    """
    return update_memory(_resolve(project), memory_id, title, content, tags, metadata, status, priority, related_ids)


@mcp.tool()
def memory_delete(
    memory_id: str,
    project: str | None = None,
    hard: bool = False,
    reason: str | None = None,
) -> dict:
    """Delete a memory. Soft-delete (archive) by default.

    Records deletion in provenance audit trail with optional reason.

    Args:
        memory_id: ID of memory to delete
        project: Project slug (optional if active project is set)
        hard: If True, permanently removes the memory
        reason: Optional reason for deletion
    """
    return delete_memory(_resolve(project), memory_id, hard, reason)


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
    """List memories with filtering, sorting, and pagination.

    Uses direct SQL queries, not vector search.
    Automatically cleans up expired memories.

    Args:
        project: Project slug (optional if active project is set)
        category: Filter by category
        status: Filter by status (default: active)
        tags: Filter by tags (matches any)
        sort_by: Sort field (updated_at, created_at, title, priority, access_count)
        sort_order: asc or desc
        limit: Page size
        offset: Page offset
    """
    return list_memories(_resolve(project), category, status, tags, sort_by, sort_order, limit, offset)


# --- Provenance / Audit ---


@mcp.tool()
def memory_provenance(
    memory_id: str,
    project: str | None = None,
) -> dict:
    """Get the full audit trail for a memory.

    Returns all operations (create, update, delete, access) with timestamps.

    Args:
        memory_id: ID of memory to audit
        project: Project slug (optional if active project is set)
    """
    slug = _resolve(project)
    trail = get_provenance(slug, memory_id)
    return {"memory_id": memory_id, "provenance": trail, "total": len(trail)}


# --- Rules ---


@mcp.tool()
def memory_get_rules(project: str | None = None) -> dict:
    """Get all mandatory and forbidden rules for a project.

    Uses direct SQL (not vector search) with in-memory caching.
    Rules are ALWAYS returned completely - never approximated.

    IMPORTANT: Call this before performing any operation to ensure
    mandatory rules are followed and forbidden patterns are avoided.

    Args:
        project: Project slug (optional if active project is set)
    """
    return get_rules(_resolve(project))


# --- Session Management ---


@mcp.tool()
def memory_session_start(project: str | None = None) -> dict:
    """Start a new session and load full project context.

    Returns in a single call:
    - All mandatory and forbidden rules
    - Last session summary
    - Active sprint goals
    - Recent decisions (last 7 days)

    Call this at the beginning of every conversation.

    Args:
        project: Project slug (optional if active project is set)
    """
    slug = _resolve(project)
    set_active_project(slug)  # Auto-activate on session start
    return session_start(slug)


@mcp.tool()
def memory_session_end(
    session_id: str,
    summary: str,
    project: str | None = None,
    memories_created: int = 0,
    memories_accessed: int = 0,
) -> dict:
    """End a session and store its summary.

    The summary will be shown to the next session via memory_session_start.

    Args:
        session_id: Session ID from memory_session_start
        summary: Session summary text
        project: Project slug (optional if active project is set)
        memories_created: Count of memories created this session
        memories_accessed: Count of memories accessed this session
    """
    return session_end(_resolve(project), session_id, summary, memories_created, memories_accessed)


# --- Project Portability ---


@mcp.tool()
def memory_attach_project(
    project_path: str,
    slug: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
) -> dict:
    """Attach an existing project directory to the memory system.

    If the directory already has a .memory-mcp.duckdb file, uses that.
    Otherwise creates a new memory DB for the project.
    Automatically sets the project as active.

    Args:
        project_path: Absolute path to the project directory
        slug: Optional slug (auto-derived from directory name)
        display_name: Optional display name
        description: Optional description
    """
    result = attach_project(project_path, slug, display_name, description)
    if result.get("status") == "ok" and result.get("project", {}).get("slug"):
        set_active_project(result["project"]["slug"])
        result["active"] = True
    return result


@mcp.tool()
def memory_make_portable(
    project_path: str,
    project: str | None = None,
) -> dict:
    """Move a project's memory DB into the project directory for git sharing.

    After this, the DB lives at <project_path>/.memory-mcp.duckdb.
    Commit this file to git so teammates can use it on other machines.

    Remember to add *.duckdb.wal to .gitignore.

    Args:
        project_path: Absolute path to the project directory
        project: Project slug (optional if active project is set)
    """
    return make_portable(_resolve(project), project_path)


@mcp.tool()
def memory_sync(
    project_path: str,
    slug: str | None = None,
) -> dict:
    """Sync a portable memory DB after git pull on a new machine.

    Registers the .memory-mcp.duckdb found in the project directory
    so the MCP can pick up right where the last user left off.
    Automatically sets the project as active.

    Args:
        project_path: Absolute path to the project directory
        slug: Optional slug (auto-derived from directory name)
    """
    result = sync_from_portable(project_path, slug)
    if result.get("status") == "ok" and result.get("project", {}).get("slug"):
        set_active_project(result["project"]["slug"])
    return result


# --- Export / Import ---


@mcp.tool()
def memory_export(
    export_path: str,
    project: str | None = None,
) -> dict:
    """Export all memories to human-readable .md files.

    Creates a .memory/ directory in the project with:
    - MEMORY_INDEX.md (master index)
    - <category>/<title>.md (individual memory files)
    - README.md (format documentation)

    These files can be read and edited by anyone, even without the MCP.
    Use memory_import to sync changes back.

    Args:
        export_path: Path to the project directory
        project: Project slug (optional if active project is set)
    """
    return export_memories(_resolve(project), export_path)


@mcp.tool()
def memory_import(
    import_path: str,
    project: str | None = None,
) -> dict:
    """Import memories from exported .md files into the DB.

    Reads the .memory/ directory in the project.
    Creates new memories, updates changed ones, skips unchanged ones.

    Args:
        import_path: Path to the project directory
        project: Project slug (optional if active project is set)
    """
    return import_memories(_resolve(project), import_path)


# --- Model Management ---


@mcp.tool()
def memory_model_info() -> dict:
    """Get current embedding model info and available presets.

    Shows: current model, available presets (english/multilingual),
    disk usage, RAM usage, supported languages, and speed.
    """
    return get_model_info()


@mcp.tool()
def memory_set_model(
    preset: str,
    project: str | None = None,
    confirm: bool = False,
) -> dict:
    """Switch embedding model between english-only and multilingual.

    Presets:
    - 'english': all-MiniLM-L6-v2 (~80MB disk, ~90MB RAM, English only, very fast)
    - 'multilingual': paraphrase-multilingual-MiniLM-L12-v2 (~470MB disk, ~500MB RAM, 50+ languages incl. Turkish)

    First call without confirm=True shows the impact (disk, RAM, re-embed count).
    Second call with confirm=True applies the change and re-embeds existing memories.

    Args:
        preset: 'english' or 'multilingual'
        project: If provided, re-embed this project's memories after switching
        confirm: Must be True to proceed after reviewing the impact
    """
    return set_model(preset, _resolve(project) if project else None, confirm)


@mcp.tool()
def memory_reembed(
    project: str | None = None,
) -> dict:
    """Re-embed all active memories in a project with the current model.

    Use after switching embedding models to update all vectors.

    Args:
        project: Project slug (optional if active project is set)
    """
    return reembed_project(_resolve(project))


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
