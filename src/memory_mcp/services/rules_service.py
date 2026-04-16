"""Rules service - cached retrieval of mandatory/forbidden rules."""

import threading
import time

from memory_mcp.config import settings
from memory_mcp.models import RulesResponse
from memory_mcp.repositories import MemoryRepository


class RulesCache:
    """Thread-safe in-memory cache for rules per project."""

    def __init__(self, ttl: int | None = None):
        self._cache: dict[str, tuple[float, RulesResponse]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl if ttl is not None else settings.rules_cache_ttl

    def get(self, project: str) -> RulesResponse | None:
        now = time.time()
        with self._lock:
            entry = self._cache.get(project)
            if not entry:
                return None
            ts, value = entry
            if now - ts > self._ttl:
                return None
            return value

    def set(self, project: str, value: RulesResponse) -> None:
        with self._lock:
            self._cache[project] = (time.time(), value)

    def invalidate(self, project: str) -> None:
        with self._lock:
            self._cache.pop(project, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class RulesService:
    """Retrieves rules with caching. Never uses vector search - rules must be complete."""

    def __init__(self, memory_repo: MemoryRepository, cache: RulesCache):
        self._repo = memory_repo
        self._cache = cache

    def get_rules(self, project: str) -> RulesResponse:
        cached = self._cache.get(project)
        if cached is not None:
            return cached

        mandatory, forbidden = self._repo.get_rules(project)
        response = RulesResponse(
            mandatory_rules=mandatory,
            forbidden_rules=forbidden,
            total=len(mandatory) + len(forbidden),
        )
        self._cache.set(project, response)
        return response

    def invalidate(self, project: str) -> None:
        self._cache.invalidate(project)
