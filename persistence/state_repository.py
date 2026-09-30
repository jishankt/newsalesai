"""
SQLite State Repository for Kepler Tech Conversational AI.
Ensures conversation states and message histories survive server restarts.
"""

import sqlite3
import json
import os
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from domain.conversation_state import ConversationState
from persistence.models import CREATE_TABLES_SQL

logger = logging.getLogger("persistence.state_repository")

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


class StateRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cur = conn.execute("PRAGMA table_info(conversation_sessions)")
                cols = [r[1] for r in cur.fetchall()]
                if cols and "customer_id" not in cols:
                    conn.execute("ALTER TABLE conversation_sessions ADD COLUMN customer_id TEXT")
                conn.executescript(CREATE_TABLES_SQL)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_customer ON conversation_sessions (customer_id)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize database at {self.db_path}: {e}")

    def save_session(
        self,
        session_id: str,
        state: ConversationState,
        history: List[Dict[str, str]],
    ) -> bool:
        """Saves or updates conversation state and history in SQLite."""
        try:
            state_data = state.to_dict()
            state_json = json.dumps(state_data, default=str)
            history_json = json.dumps(history, default=str)
            now = time.time()
            cust_name = state.customer_name
            cust_id = getattr(state, "customer_id", None)

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO conversation_sessions (session_id, created_at, updated_at, customer_name, customer_id, state_json, history_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        customer_name = COALESCE(excluded.customer_name, conversation_sessions.customer_name),
                        customer_id = COALESCE(excluded.customer_id, conversation_sessions.customer_id),
                        state_json = excluded.state_json,
                        history_json = excluded.history_json
                    """,
                    (session_id, now, now, cust_name, cust_id, state_json, history_json),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            return False

    def get_session(
        self, session_id: str
    ) -> Optional[Tuple[ConversationState, List[Dict[str, str]]]]:
        """Loads conversation state and history from SQLite."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT state_json, history_json FROM conversation_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()

                if not row:
                    return None

                state_dict = json.loads(row["state_json"])
                state = ConversationState.from_dict(state_dict)
                history = json.loads(row["history_json"])
                return state, history
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session from SQLite."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "DELETE FROM conversation_sessions WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False


state_repository = StateRepository()
