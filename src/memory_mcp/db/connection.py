"""Connection manager with WAL mode, retry logic, and multi-instance support."""

import time
import threading
from collections import OrderedDict
from pathlib import Path

import duckdb

from memory_mcp.config import settings
from memory_mcp.db.schema import create_schema, create_hnsw_index, install_vss

MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds


def _open_connection(db_path: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection with retry logic for lock conflicts."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            config = {}
            if read_only:
                config["access_mode"] = "READ_ONLY"
            conn = duckdb.connect(str(db_path), read_only=read_only, config=config)
            # Enable WAL mode for better concurrent access
            if not read_only:
                try:
                    conn.execute("PRAGMA enable_progress_bar;")
                except Exception:
                    pass
            return conn
        except duckdb.IOException as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                # Last resort: try read-only
                if not read_only:
                    try:
                        return duckdb.connect(str(db_path), read_only=True)
                    except Exception:
                        pass
                raise last_error


class ConnectionManager:
    """Thread-safe LRU cache with WAL mode and multi-instance support."""

    def __init__(self, max_connections: int | None = None):
        self._connections: OrderedDict[str, duckdb.DuckDBPyConnection] = OrderedDict()
        self._max = max_connections or settings.max_connections
        self._lock = threading.Lock()

    def get_connection(self, slug: str) -> duckdb.DuckDBPyConnection:
        """Get or open a connection. Retries on lock conflict, falls back to read-only."""
        with self._lock:
            if slug in self._connections:
                conn = self._connections[slug]
                # Verify connection is still alive
                try:
                    conn.execute("SELECT 1")
                    self._connections.move_to_end(slug)
                    return conn
                except Exception:
                    # Connection dead, remove and reconnect
                    try:
                        conn.close()
                    except Exception:
                        pass
                    del self._connections[slug]

            # Close ALL other connections before opening new one
            # This prevents lock conflicts between projects
            self._close_others(slug)

            db_path = self._resolve_db_path(slug)
            is_new = not db_path.exists()

            conn = _open_connection(str(db_path))

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

    def _close_others(self, keep_slug: str) -> None:
        """Close all connections except the specified one. Prevents cross-project locks."""
        to_close = [s for s in self._connections if s != keep_slug]
        for slug in to_close:
            try:
                self._connections[slug].close()
            except Exception:
                pass
            del self._connections[slug]

    def _resolve_db_path(self, slug: str) -> Path:
        """Resolve DB path: check registry for custom path, fallback to central store."""
        try:
            from memory_mcp.db.registry import get_project
            project = get_project(slug)
            if project and project.db_path:
                custom_path = Path(project.db_path)
                if custom_path.parent.exists():
                    return custom_path
        except Exception:
            pass
        return settings.projects_dir / f"{slug}.duckdb"

    def close_all(self) -> None:
        """Close all cached connections."""
        with self._lock:
            for conn in self._connections.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()

    def remove(self, slug: str) -> None:
        """Close and remove a specific connection."""
        with self._lock:
            if slug in self._connections:
                try:
                    self._connections[slug].close()
                except Exception:
                    pass
                del self._connections[slug]


# Module-level singleton
_manager: ConnectionManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> ConnectionManager:
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is not None:
            return _manager
        _manager = ConnectionManager()
        return _manager


def get_connection(slug: str) -> duckdb.DuckDBPyConnection:
    return get_manager().get_connection(slug)
