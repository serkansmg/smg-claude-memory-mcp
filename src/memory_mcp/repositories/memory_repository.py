"""Memory repository - all SQL for memory CRUD, search, and filtering."""

import json
from datetime import datetime

from memory_mcp.db.connection import connect
from memory_mcp.models import Memory, MemoryFilter, Pagination

MEMORY_COLUMNS = "id, category, title, content, summary, tags, metadata, embedding, status, priority, source, related_ids, entities, access_count, expires_at, created_at, updated_at"


def _row_to_memory(row, include_embedding: bool = False) -> Memory:
    """Convert a DB row tuple into a Memory domain model."""
    metadata = None
    if row[6]:
        try:
            metadata = json.loads(row[6]) if isinstance(row[6], str) else row[6]
        except (json.JSONDecodeError, TypeError):
            metadata = None

    data = {
        "id": row[0],
        "category": row[1],
        "title": row[2],
        "content": row[3],
        "summary": row[4],
        "tags": row[5] or [],
        "metadata": metadata,
        "status": row[8],
        "priority": row[9],
        "source": row[10],
        "related_ids": row[11] or [],
        "entities": row[12] or [],
        "access_count": row[13],
        "expires_at": row[14],
        "created_at": row[15],
        "updated_at": row[16],
    }
    if include_embedding:
        data["embedding"] = row[7]
    return Memory(**data)


class MemoryRepository:
    """All memory-related SQL operations, centralized."""

    # ---------- Insert ----------

    def insert(
        self,
        project: str,
        memory_id: str,
        category: str,
        title: str,
        content: str,
        summary: str | None,
        tags: list[str],
        metadata: dict | None,
        embedding: list[float],
        priority: int,
        source: str,
        related_ids: list[str],
        entities: list[str],
        expires_at: datetime | None,
        status: str = "active",
    ) -> Memory:
        with connect(project) as conn:
            conn.execute(
                """
                INSERT INTO memories (id, category, title, content, summary, tags, metadata, embedding, status, priority, source, related_ids, entities, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    memory_id, category, title, content, summary, tags,
                    json.dumps(metadata) if metadata else None,
                    embedding, status, priority, source, related_ids, entities, expires_at,
                ],
            )
            row = conn.execute(
                f"SELECT {MEMORY_COLUMNS} FROM memories WHERE id = ?", [memory_id]
            ).fetchone()
        return _row_to_memory(row)

    # ---------- Read ----------

    def get_by_id(self, project: str, memory_id: str) -> Memory | None:
        with connect(project) as conn:
            row = conn.execute(
                f"SELECT {MEMORY_COLUMNS} FROM memories WHERE id = ?", [memory_id]
            ).fetchone()
        return _row_to_memory(row) if row else None

    def get_by_title(self, project: str, title: str, status: str = "active") -> Memory | None:
        with connect(project) as conn:
            row = conn.execute(
                f"SELECT {MEMORY_COLUMNS} FROM memories WHERE title = ? AND status = ?",
                [title, status],
            ).fetchone()
        return _row_to_memory(row) if row else None

    def get_rules(self, project: str) -> tuple[list[Memory], list[Memory]]:
        """Return (mandatory_rules, forbidden_rules) as typed Memory lists."""
        with connect(project) as conn:
            rows = conn.execute(
                f"""
                SELECT {MEMORY_COLUMNS} FROM memories
                WHERE category IN ('mandatory_rules', 'forbidden_rules') AND status = 'active'
                ORDER BY priority DESC, created_at ASC
                """
            ).fetchall()

        mandatory: list[Memory] = []
        forbidden: list[Memory] = []
        for row in rows:
            mem = _row_to_memory(row)
            if mem.category.value == "mandatory_rules":
                mandatory.append(mem)
            else:
                forbidden.append(mem)
        return mandatory, forbidden

    def get_recent_by_category(
        self, project: str, category: str, since: datetime, limit: int = 20
    ) -> list[Memory]:
        with connect(project) as conn:
            rows = conn.execute(
                f"""
                SELECT {MEMORY_COLUMNS} FROM memories
                WHERE category = ? AND status = 'active' AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [category, since, limit],
            ).fetchall()
        return [_row_to_memory(r) for r in rows]

    def get_active_by_category(
        self, project: str, category: str, limit: int = 10
    ) -> list[Memory]:
        with connect(project) as conn:
            rows = conn.execute(
                f"""
                SELECT {MEMORY_COLUMNS} FROM memories
                WHERE category = ? AND status = 'active'
                ORDER BY priority DESC, updated_at DESC
                LIMIT ?
                """,
                [category, limit],
            ).fetchall()
        return [_row_to_memory(r) for r in rows]

    def list(
        self, project: str, filters: MemoryFilter, pagination: Pagination
    ) -> tuple[list[Memory], int]:
        """Return (memories, total_count) applying filters and pagination."""
        conditions = ["status = ?"]
        params: list = [filters.status]

        if filters.category:
            conditions.append("category = ?")
            params.append(filters.category)

        if filters.tags:
            tag_conditions = ["list_contains(tags, ?)"] * len(filters.tags)
            conditions.append(f"({' OR '.join(tag_conditions)})")
            params.extend(filters.tags)

        if filters.status == "active":
            conditions.append("(expires_at IS NULL OR expires_at > current_timestamp)")

        where = " AND ".join(conditions)

        with connect(project) as conn:
            # Cleanup expired as a side-effect (only when listing active)
            if filters.status == "active":
                conn.execute(
                    "UPDATE memories SET status = 'expired' "
                    "WHERE expires_at IS NOT NULL AND expires_at <= current_timestamp AND status = 'active'"
                )

            total = conn.execute(
                f"SELECT COUNT(*) FROM memories WHERE {where}", params
            ).fetchone()[0]

            query_sql = (
                f"SELECT {MEMORY_COLUMNS} FROM memories WHERE {where} "
                f"ORDER BY {pagination.sort_by} {pagination.sort_order} "
                f"LIMIT ? OFFSET ?"
            )
            page_params = params + [pagination.limit, pagination.offset]
            rows = conn.execute(query_sql, page_params).fetchall()

        return [_row_to_memory(r) for r in rows], total

    def vector_search(
        self, project: str, query_embedding: list[float], status: str, limit: int
    ) -> list[tuple[Memory, float]]:
        """Return list of (memory, cosine_distance) pairs, ordered by distance asc."""
        with connect(project) as conn:
            rows = conn.execute(
                f"""
                SELECT {MEMORY_COLUMNS},
                       array_cosine_distance(embedding, ?::FLOAT[384]) AS distance
                FROM memories
                WHERE status = ? AND (expires_at IS NULL OR expires_at > current_timestamp)
                ORDER BY array_cosine_distance(embedding, ?::FLOAT[384])
                LIMIT ?
                """,
                [query_embedding, status, query_embedding, limit],
            ).fetchall()

        results: list[tuple[Memory, float]] = []
        for row in rows:
            memory = _row_to_memory(row[:17])
            distance = row[17]
            results.append((memory, distance))
        return results

    # ---------- Update ----------

    def update(self, project: str, memory_id: str, fields: dict) -> Memory:
        """Apply a set of field updates. fields keys map to column names.

        Caller is responsible for serializing metadata (e.g. json.dumps).
        """
        if not fields:
            return self.get_by_id(project, memory_id)

        set_parts = [f"{k} = ?" for k in fields]
        set_parts.append("updated_at = current_timestamp")
        values = list(fields.values()) + [memory_id]

        with connect(project) as conn:
            conn.execute(
                f"UPDATE memories SET {', '.join(set_parts)} WHERE id = ?",
                values,
            )
            row = conn.execute(
                f"SELECT {MEMORY_COLUMNS} FROM memories WHERE id = ?", [memory_id]
            ).fetchone()
        return _row_to_memory(row)

    def increment_access(self, project: str, memory_id: str) -> None:
        with connect(project) as conn:
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1 WHERE id = ?",
                [memory_id],
            )

    # ---------- Delete ----------

    def soft_delete(self, project: str, memory_id: str) -> None:
        with connect(project) as conn:
            conn.execute(
                "UPDATE memories SET status = 'archived', updated_at = current_timestamp WHERE id = ?",
                [memory_id],
            )

    def hard_delete(self, project: str, memory_id: str) -> None:
        with connect(project) as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", [memory_id])

    # ---------- Counts ----------

    def count_active(self, project: str) -> int:
        with connect(project) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM memories WHERE status = 'active'"
            ).fetchone()[0]

    # ---------- Iteration for batch ops (e.g. re-embed) ----------

    def iter_active(self, project: str):
        """Yield all active memories. Used by reembed."""
        with connect(project) as conn:
            rows = conn.execute(
                f"SELECT {MEMORY_COLUMNS} FROM memories WHERE status = 'active'"
            ).fetchall()
        for row in rows:
            yield _row_to_memory(row)

    def update_embedding(self, project: str, memory_id: str, embedding: list[float]) -> None:
        with connect(project) as conn:
            conn.execute(
                "UPDATE memories SET embedding = ?, updated_at = current_timestamp WHERE id = ?",
                [embedding, memory_id],
            )
