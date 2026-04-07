"""Memory list tool - filtered listing with pagination."""

from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import row_to_dict, MEMORY_COLUMNS, CLEANUP_EXPIRED

VALID_SORT_FIELDS = {"created_at", "updated_at", "title", "priority", "access_count", "category"}
VALID_SORT_ORDERS = {"asc", "desc"}


def list_memories(
    project: str,
    category: str | None = None,
    status: str = "active",
    tags: list[str] | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List memories with filtering, sorting, and pagination. Cleans up expired entries."""
    if sort_by not in VALID_SORT_FIELDS:
        sort_by = "updated_at"
    if sort_order not in VALID_SORT_ORDERS:
        sort_order = "desc"

    conn = get_connection(project)

    # Cleanup expired memories
    conn.execute(CLEANUP_EXPIRED)

    conditions = ["status = ?"]
    params: list = [status]

    if category:
        conditions.append("category = ?")
        params.append(category)

    if tags:
        tag_conditions = ["list_contains(tags, ?)"] * len(tags)
        conditions.append(f"({' OR '.join(tag_conditions)})")
        params.extend(tags)

    # Exclude expired for active queries
    if status == "active":
        conditions.append("(expires_at IS NULL OR expires_at > current_timestamp)")

    where = " AND ".join(conditions)

    count_sql = f"SELECT COUNT(*) FROM memories WHERE {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    query_sql = f"""
        SELECT {MEMORY_COLUMNS}
        FROM memories
        WHERE {where}
        ORDER BY {sort_by} {sort_order}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = conn.execute(query_sql, params).fetchall()

    return {
        "memories": [row_to_dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
