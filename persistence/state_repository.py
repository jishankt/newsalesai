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
                if cols and "version" not in cols:
                    conn.execute("ALTER TABLE conversation_sessions ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
                conn.executescript(CREATE_TABLES_SQL)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_customer ON conversation_sessions (customer_id)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize database at {self.db_path}: {e}")

    @staticmethod
    def merge_histories(base_history: List[Dict[str, Any]], incoming_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges history by appending any new turns from incoming_history that are not
        already present in base_history, preserving chronological order and preventing overwriting.
        """
        merged = list(base_history)

        def turn_sig(turn):
            role = turn.get("role", "")
            content = turn.get("content", "")
            if isinstance(content, str):
                return (role, content.strip())
            return (role, str(content))

        existing_sigs = {turn_sig(t) for t in base_history}
        for t in incoming_history:
            sig = turn_sig(t)
            if sig not in existing_sigs:
                merged.append(t)
                existing_sigs.add(sig)
        return merged

    def save_session(
        self,
        session_id: str,
        state: ConversationState,
        history: List[Dict[str, Any]],
        max_retries: int = 3,
    ) -> bool:
        """
        Saves conversation state and history in SQLite using optimistic concurrency control.
        Uses version integer column: UPDATE ... WHERE session_id=? AND version=?
        On conflict, re-reads latest database state, merges history by appending new turns, and retries (max 3).
        """
        try:
            cust_name = state.customer_name
            cust_id = getattr(state, "customer_id", None)
            now = time.time()

            with self._get_connection() as conn:
                for attempt in range(max_retries + 1):
                    row = conn.execute(
                        "SELECT version, state_json, history_json FROM conversation_sessions WHERE session_id = ?",
                        (session_id,)
                    ).fetchone()

                    if not row:
                        # Insert brand-new session
                        state_data = state.to_dict()
                        state_json = json.dumps(state_data, default=str)
                        history_json = json.dumps(history, default=str)
                        try:
                            conn.execute(
                                """
                                INSERT INTO conversation_sessions
                                (session_id, created_at, updated_at, customer_name, customer_id, state_json, history_json, version)
                                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                                """,
                                (session_id, now, now, cust_name, cust_id, state_json, history_json),
                            )
                            conn.commit()
                            state._version = 1
                            return True
                        except sqlite3.IntegrityError:
                            # Concurrent insert collision; retry as update
                            continue

                    # Session already exists: optimistic update with version check
                    db_version = row["version"]
                    expected_version = getattr(state, "_version", None)
                    if expected_version is None:
                        expected_version = db_version

                    if expected_version != db_version:
                        # In-memory version is already stale compared to DB; merge before writing
                        db_history = json.loads(row["history_json"])
                        history = self.merge_histories(db_history, history)
                        state.history_turns = history
                        expected_version = db_version

                    state_data = state.to_dict()
                    state_json = json.dumps(state_data, default=str)
                    history_json = json.dumps(history, default=str)

                    cur = conn.execute(
                        """
                        UPDATE conversation_sessions
                        SET updated_at = ?,
                            customer_name = COALESCE(?, customer_name),
                            customer_id = COALESCE(?, customer_id),
                            state_json = ?,
                            history_json = ?,
                            version = version + 1
                        WHERE session_id = ? AND version = ?
                        """,
                        (now, cust_name, cust_id, state_json, history_json, session_id, expected_version),
                    )
                    conn.commit()

                    if cur.rowcount > 0:
                        state._version = expected_version + 1
                        return True

                    # Optimistic concurrency conflict: another process updated the record
                    logger.warning(
                        f"Concurrency conflict saving session {session_id} "
                        f"(expected version={expected_version}). Retrying ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(0.02 * (attempt + 1))

            logger.error(f"Failed to save session {session_id} after {max_retries} optimistic retry attempts.")
            return False
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            return False

    def get_session(
        self, session_id: str
    ) -> Optional[Tuple[ConversationState, List[Dict[str, Any]]]]:
        """Loads conversation state and history from SQLite, tracking optimistic version."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT state_json, history_json, version FROM conversation_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()

                if not row:
                    return None

                state_dict = json.loads(row["state_json"])
                state = ConversationState.from_dict(state_dict)
                state._version = row["version"] if "version" in row.keys() else 1
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
