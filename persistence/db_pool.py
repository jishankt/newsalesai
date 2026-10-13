"""
Thread-safe SQLite Connection Manager with Connection Pooling, WAL Mode, and Busy Timeout.

Ensures high concurrency without database locked errors under multi-threaded Gunicorn workers.
"""

import sqlite3
import os
import threading
from typing import Dict

logger = logging = __import__("logging").getLogger("persistence.db_pool")


class SQLiteConnectionPool:
    """Thread-safe SQLite connection pool with automatic WAL configuration."""
    _local = threading.local()

    @classmethod
    def get_connection(cls, db_path: str, timeout: float = 10.0) -> sqlite3.Connection:
        """Retrieves or creates a thread-local cached SQLite connection."""
        if not hasattr(cls._local, "connections"):
            cls._local.connections = {}

        conn = cls._local.connections.get(db_path)
        if conn is None:
            conn = cls._create_connection(db_path, timeout)
            cls._local.connections[db_path] = conn
        else:
            try:
                conn.execute("SELECT 1;")
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = cls._create_connection(db_path, timeout)
                cls._local.connections[db_path] = conn

        return conn

    @classmethod
    def _create_connection(cls, db_path: str, timeout: float) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=timeout)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception as e:
            logger.warning(f"Could not apply PRAGMA settings on {db_path}: {e}")
        return conn

    @classmethod
    def close_all(cls):
        """Closes all thread-local connections for the current thread."""
        if hasattr(cls._local, "connections"):
            for path, conn in list(cls._local.connections.items()):
                try:
                    conn.close()
                except Exception:
                    pass
            cls._local.connections.clear()
