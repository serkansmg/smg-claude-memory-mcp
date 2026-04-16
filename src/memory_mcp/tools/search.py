"""Semantic search with composite relevance scoring and token budgeting."""

from memory_mcp.config import settings
from memory_mcp.db.connection import connect
from memory_mcp.db.queries import VECTOR_SEARCH, INCREMENT_ACCESS, row_to_dict
from memory_mcp.embeddings import embed_text
from memory_mcp.utils.scoring import compute_relevance
from memory_mcp.utils.extraction import estimate_tokens


def search_memories(
    project: str,
    query: str,
    category: str | None = None,
    tags: list[str] | None = None,
    status: str = "active",
    limit: int = 10,
    min_similarity: float = 0.3,
    token_budget: int | None = None,
) -> dict:
    """Semantic search with HNSW vector search, composite scoring, and token budgeting."""
    query_embedding = embed_text(query)
    oversample = limit * settings.search_oversample

    with connect(project) as conn:
        rows = conn.execute(
            VECTOR_SEARCH, [query_embedding, status, query_embedding, oversample],
        ).fetchall()

        candidates = []
        for row in rows:
            cosine_distance = row[17]
            similarity = 1.0 - cosine_distance

            if similarity < min_similarity:
                continue
            if category and row[1] != category:
                continue
            if tags:
                row_tags = row[5] or []
                if not any(t in row_tags for t in tags):
                    continue

            relevance = compute_relevance(similarity, row[16], row[13])
            memory_dict = row_to_dict(row[:17])
            candidates.append({
                "memory": memory_dict,
                "similarity": round(similarity, 4),
                "relevance_score": round(relevance, 4),
            })

        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
        candidates = candidates[:limit]

        for r in candidates:
            conn.execute(INCREMENT_ACCESS, [r["memory"]["id"]])

    if token_budget and token_budget > 0:
        index_items = []
        detail_items = []
        tokens_used = 0
        for r in candidates:
            index_items.append({
                "id": r["memory"]["id"], "title": r["memory"]["title"],
                "summary": r["memory"]["summary"], "category": r["memory"]["category"],
                "similarity": r["similarity"],
            })
            content_tokens = estimate_tokens(r["memory"]["content"])
            if tokens_used + content_tokens <= token_budget:
                detail_items.append(r)
                tokens_used += content_tokens
        return {
            "index": index_items, "details": detail_items, "total": len(candidates),
            "tokens_used": tokens_used, "has_more": len(detail_items) < len(candidates),
            "query": query,
        }

    return {"results": candidates, "total": len(candidates), "query": query}
