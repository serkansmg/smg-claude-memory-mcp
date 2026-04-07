"""SQL query constants and builders."""

# Column order: id, category, title, content, summary, tags, metadata, embedding, status, priority, source, related_ids, entities, access_count, expires_at, created_at, updated_at
MEMORY_COLUMNS = "id, category, title, content, summary, tags, metadata, embedding, status, priority, source, related_ids, entities, access_count, expires_at, created_at, updated_at"

INSERT_MEMORY = """
    INSERT INTO memories (id, category, title, content, summary, tags, metadata, embedding, status, priority, source, related_ids, entities, expires_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_MEMORY_BY_ID = f"""
    SELECT {MEMORY_COLUMNS} FROM memories WHERE id = ?
"""

SELECT_MEMORY_BY_TITLE = f"""
    SELECT {MEMORY_COLUMNS} FROM memories WHERE title = ? AND status = 'active'
"""

SELECT_RULES = f"""
    SELECT {MEMORY_COLUMNS}
    FROM memories
    WHERE category IN ('mandatory_rules', 'forbidden_rules') AND status = 'active'
    ORDER BY priority DESC, created_at ASC
"""

VECTOR_SEARCH = f"""
    SELECT {MEMORY_COLUMNS},
           array_cosine_distance(embedding, ?::FLOAT[384]) AS distance
    FROM memories
    WHERE status = ? AND (expires_at IS NULL OR expires_at > current_timestamp)
    ORDER BY array_cosine_distance(embedding, ?::FLOAT[384])
    LIMIT ?
"""

INCREMENT_ACCESS = """
    UPDATE memories SET access_count = access_count + 1 WHERE id = ?
"""

SOFT_DELETE = """
    UPDATE memories SET status = 'archived', updated_at = current_timestamp WHERE id = ?
"""

HARD_DELETE = """
    DELETE FROM memories WHERE id = ?
"""

INSERT_SESSION = """
    INSERT INTO sessions (id, started_at) VALUES (?, current_timestamp)
"""

END_SESSION = """
    UPDATE sessions SET ended_at = current_timestamp, summary = ?, memories_created = ?, memories_accessed = ? WHERE id = ?
"""

LAST_SESSION = """
    SELECT id, started_at, ended_at, summary, memories_created, memories_accessed, metadata
    FROM sessions WHERE ended_at IS NOT NULL
    ORDER BY ended_at DESC LIMIT 1
"""

RECENT_BY_CATEGORY = f"""
    SELECT {MEMORY_COLUMNS}
    FROM memories
    WHERE category = ? AND status = 'active' AND created_at >= ?
    ORDER BY created_at DESC
    LIMIT ?
"""

ACTIVE_BY_CATEGORY = f"""
    SELECT {MEMORY_COLUMNS}
    FROM memories
    WHERE category = ? AND status = 'active'
    ORDER BY priority DESC, updated_at DESC
    LIMIT ?
"""

CLEANUP_EXPIRED = """
    UPDATE memories SET status = 'expired' WHERE expires_at IS NOT NULL AND expires_at <= current_timestamp AND status = 'active'
"""


def row_to_dict(row, include_embedding: bool = False) -> dict:
    """Convert a DuckDB row tuple to a memory dict.

    Column order: id(0), category(1), title(2), content(3), summary(4), tags(5),
    metadata(6), embedding(7), status(8), priority(9), source(10), related_ids(11),
    entities(12), access_count(13), expires_at(14), created_at(15), updated_at(16)
    """
    d = {
        "id": row[0],
        "category": row[1],
        "title": row[2],
        "content": row[3],
        "summary": row[4],
        "tags": row[5] or [],
        "metadata": row[6],
        "status": row[8],
        "priority": row[9],
        "source": row[10],
        "related_ids": row[11] or [],
        "entities": row[12] or [],
        "access_count": row[13],
        "expires_at": str(row[14]) if row[14] else None,
        "created_at": str(row[15]) if row[15] else None,
        "updated_at": str(row[16]) if row[16] else None,
    }
    if include_embedding:
        d["embedding"] = row[7]
    return d
