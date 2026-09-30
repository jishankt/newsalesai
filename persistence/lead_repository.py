"""
SQLite Lead Repository for Kepler Tech Conversational AI.
Persists qualified commercial leads and customer contact information.
"""

import sqlite3
import os
import time
import logging
from typing import Dict, Any, List, Optional

from persistence.models import CREATE_TABLES_SQL, LeadRecord

logger = logging.getLogger("persistence.lead_repository")

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


class LeadRepository:
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
                conn.executescript(CREATE_TABLES_SQL)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize lead database at {self.db_path}: {e}")

    def save_lead(
        self,
        session_id: str,
        customer_name: Optional[str] = None,
        company: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        product_interest: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[int]:
        """Saves a commercial lead record to SQLite."""
        try:
            now = time.time()
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO commercial_leads (session_id, created_at, customer_name, company, email, phone, product_interest, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, now, customer_name, company, email, phone, product_interest, notes),
                )
                conn.commit()
                lead_id = cursor.lastrowid
                logger.info(f"Saved lead #{lead_id} for session {session_id}")
                return lead_id
        except Exception as e:
            logger.error(f"Error saving lead for session {session_id}: {e}")
            return None

    def get_leads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves latest commercial leads ordered by created_at desc."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT lead_id, session_id, created_at, customer_name, company, email, phone, product_interest, notes
                    FROM commercial_leads
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching leads: {e}")
            return []

    def get_leads_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves leads captured for a specific session."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT lead_id, session_id, created_at, customer_name, company, email, phone, product_interest, notes
                    FROM commercial_leads
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching leads for session {session_id}: {e}")
            return []


lead_repository = LeadRepository()
