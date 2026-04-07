"""LRU connection cache for per-project DuckDB connections."""

import threading
from collections import OrderedDict
from pathlib import Path

import duckdb

from memory_mcp.config import settings
from memory_mcp.db.schema import create_schema, create_hnsw_index, install_vss


class ConnectionManager:
    """Thread-safe LRU cache for DuckDB connections."""

    def __init__(self, max_connections: int | None = None):
        self._connections: OrderedDict[str, duckdb.DuckDBPyConnection] = OrderedDict()
        self._max = max_connections or settings.max_connections
        self._lock = threading.Lock()

    def get_connection(self, slug: str) -> duckdb.DuckDBPyConnection:
        """Get or open a connection for a project. Moves to end of LRU on access."""
        with self._lock:
            if slug in self._connections:
                self._connections.move_to_end(slug)
                conn = self._connections[slug]
                # Ensure VSS is loaded for this connection
                try:
                    conn.execute("LOAD vss;")
                except Exception:
                    pass
                return conn

            # Evict oldest if at capacity
            if len(self._connections) >= self._max:
                _, old_conn = self._connections.popitem(last=False)
                old_conn.close()

            # Check registry for custom db_path (portable DB support)
            db_path = self._resolve_db_path(slug)
            is_new = not db_path.exists()

            conn = duckdb.connect(str(db_path))

            if is_new:
                create_schema(conn)
                create_hnsw_index(conn)
            else:
                try:
                    install_vss(conn)
                except Exception:
                    pass

            self._connections[slug] = conn
            return conn

    def _resolve_db_path(self, slug: str) -> Path:
        """Resolve DB path: check registry for custom path, fallback to central store."""
        try:
            from memory_mcp.db.registry import get_project
            project = get_project(slug)
            if project and project.db_path:
                custom_path = Path(project.db_path)
                # Use custom path if its parent directory exists
                if custom_path.parent.exists():
                    return custom_path
        except Exception:
            pass
        return settings.projects_dir / f"{slug}.duckdb"

    def close_all(self) -> None:
        """Close all cached connections."""
        with self._lock:
            for conn in self._connections.values():
                conn.close()
            self._connections.clear()

    def remove(self, slug: str) -> None:
        """Close and remove a specific connection."""
        with self._lock:
            if slug in self._connections:
                self._connections[slug].close()
                del self._connections[slug]


# Module-level singleton
_manager: ConnectionManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> ConnectionManager:
    """Get the global connection manager singleton."""
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is not None:
            return _manager
        _manager = ConnectionManager()
        return _manager


def get_connection(slug: str) -> duckdb.DuckDBPyConnection:
    """Convenience: get a project connection from the global manager."""
    return get_manager().get_connection(slug)
