"""Composite relevance scoring for search results."""

from datetime import datetime, timezone

from memory_mcp.config import settings


def compute_relevance(
    cosine_similarity: float,
    updated_at: datetime | str,
    access_count: int,
) -> float:
    """Compute composite relevance score.

    Formula: 0.7 * cosine_sim + 0.15 * recency + 0.15 * access
    """
    w_sim, w_rec, w_acc = settings.relevance_weights

    # Parse string timestamps
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at)
        except (ValueError, TypeError):
            updated_at = datetime.now(timezone.utc)

    # Ensure timezone-aware
    now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    days = max(0, (now - updated_at).total_seconds() / 86400)
    recency_score = 1.0 / (1.0 + days * 0.1)
    access_score = min(1.0, access_count / 10.0)

    return w_sim * cosine_similarity + w_rec * recency_score + w_acc * access_score
