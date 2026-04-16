"""Search service - semantic search with composite relevance scoring."""

from memory_mcp.config import settings
from memory_mcp.embeddings import embed_text
from memory_mcp.models import (
    SearchRequest, SearchResponse, SearchResponseTokenBudgeted, SearchHit,
)
from memory_mcp.repositories import MemoryRepository
from memory_mcp.utils.extraction import estimate_tokens
from memory_mcp.utils.scoring import compute_relevance


class SearchService:
    """Semantic search with optional token budgeting."""

    def __init__(self, memory_repo: MemoryRepository):
        self._memory_repo = memory_repo

    def search(self, request: SearchRequest) -> SearchResponse | SearchResponseTokenBudgeted:
        query_embedding = embed_text(request.query)
        oversample = request.limit * settings.search_oversample

        raw = self._memory_repo.vector_search(
            request.project, query_embedding, request.status, oversample,
        )

        # Post-filter and score
        candidates: list[SearchHit] = []
        for memory, distance in raw:
            similarity = 1.0 - distance
            if similarity < request.min_similarity:
                continue
            if request.category and memory.category != request.category:
                continue
            if request.tags:
                if not any(t in memory.tags for t in request.tags):
                    continue

            relevance = compute_relevance(
                similarity, memory.updated_at, memory.access_count
            )
            candidates.append(
                SearchHit(
                    memory=memory,
                    similarity=round(similarity, 4),
                    relevance_score=round(relevance, 4),
                )
            )

        candidates.sort(key=lambda x: x.relevance_score, reverse=True)
        candidates = candidates[: request.limit]

        # Increment access counts (side effect of a successful search)
        for hit in candidates:
            self._memory_repo.increment_access(request.project, hit.memory.id)

        if request.token_budget and request.token_budget > 0:
            return self._build_budgeted(candidates, request)

        return SearchResponse(
            results=candidates, total=len(candidates), query=request.query,
        )

    def _build_budgeted(
        self, candidates: list[SearchHit], request: SearchRequest
    ) -> SearchResponseTokenBudgeted:
        index_items: list[dict] = []
        detail_items: list[SearchHit] = []
        tokens_used = 0

        for hit in candidates:
            index_items.append({
                "id": hit.memory.id,
                "title": hit.memory.title,
                "summary": hit.memory.summary,
                "category": hit.memory.category.value,
                "similarity": hit.similarity,
            })
            content_tokens = estimate_tokens(hit.memory.content)
            if tokens_used + content_tokens <= request.token_budget:
                detail_items.append(hit)
                tokens_used += content_tokens

        return SearchResponseTokenBudgeted(
            index=index_items,
            details=detail_items,
            total=len(candidates),
            tokens_used=tokens_used,
            has_more=len(detail_items) < len(candidates),
            query=request.query,
        )
