"""Rules retrieval with in-memory caching."""

import time
import threading

from memory_mcp.config import settings
from memory_mcp.db.connection import connect
from memory_mcp.db.queries import SELECT_RULES, row_to_dict

_rules_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def invalidate_rules_cache(project: str) -> None:
    with _cache_lock:
        _rules_cache.pop(project, None)


def get_rules(project: str) -> dict:
    now = time.time()
    with _cache_lock:
        if project in _rules_cache:
            cached_time, cached_result = _rules_cache[project]
            if now - cached_time < settings.rules_cache_ttl:
                return cached_result

    with connect(project) as conn:
        rows = conn.execute(SELECT_RULES).fetchall()

    mandatory = []
    forbidden = []
    for row in rows:
        memory = row_to_dict(row)
        if memory["category"] == "mandatory_rules":
            mandatory.append(memory)
        elif memory["category"] == "forbidden_rules":
            forbidden.append(memory)

    result = {"mandatory_rules": mandatory, "forbidden_rules": forbidden, "total": len(mandatory) + len(forbidden)}

    with _cache_lock:
        _rules_cache[project] = (now, result)

    return result
