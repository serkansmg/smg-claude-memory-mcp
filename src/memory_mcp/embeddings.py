"""Lazy-loaded singleton embedding model for vector generation."""

import threading

import numpy as np

from memory_mcp.config import settings

_model = None
_lock = threading.Lock()


def get_model():
    """Get or lazily load the sentence-transformers model (thread-safe singleton)."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.embedding_model)
        return _model


def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text. Returns normalized 384-dim vector."""
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts. Returns list of normalized vectors."""
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [e.tolist() for e in embeddings]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    arr_a = np.array(a)
    arr_b = np.array(b)
    return float(np.dot(arr_a, arr_b))
