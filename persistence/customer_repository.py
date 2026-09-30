"""
Customer Profile and Authentication Repository for Kepler Tech Conversational AI.
Manages customer accounts (Username = Name, Password = Phone or Email)
and links conversation sessions to customer accounts for chat history retrieval.
"""

import sqlite3
import json
import os
import re
import time
import uuid
import hashlib
import logging
from typing import Dict, Any, List, Optional
from persistence.models import CustomerRecord, CREATE_TABLES_SQL

logger = logging.getLogger("persistence.customer_repository")

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


class CustomerRepository:
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
            logger.error(f"Failed to initialize customer tables at {self.db_path}: {e}")

    @staticmethod
    def normalize_username(name: str) -> str:
        """Normalizes name: stripped, lowercased, single-spaced."""
        if not name:
            return ""
        return " ".join(name.strip().lower().split())

    @staticmethod
    def normalize_credential(credential: str) -> str:
        """Normalizes email or phone credential."""
        if not credential:
            return ""
        cred = credential.strip()
        if "@" in cred:
            return cred.lower()
        # Phone: strip spaces, dashes, parentheses
        digits = re.sub(r"[^\d+]", "", cred)
        return digits

    @classmethod
    def hash_credential(cls, credential: str) -> str:
        norm = cls.normalize_credential(credential)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def create_or_update_customer(
        self,
        name: str,
        contact: str,
        phone: Optional[str] = None,
        email: Optional[str] = None
    ) -> CustomerRecord:
        """Creates or updates a customer profile."""
        norm_user = self.normalize_username(name)
        display_name = name.strip()
        cred_hash = self.hash_credential(contact)
        phone_val = phone or (contact if "@" not in contact else None)
        email_val = email or (contact if "@" in contact else None)
        now = time.time()

        with self._get_connection() as conn:
            # Check existing customer with same normalized username
            row = conn.execute(
                "SELECT customer_id, username, display_name, credential_hash, phone, email, created_at, last_login "
                "FROM customer_profiles WHERE username = ?",
                (norm_user,)
            ).fetchone()

            if row:
                cid = row["customer_id"]
                conn.execute(
                    """
                    UPDATE customer_profiles
                    SET display_name = ?, credential_hash = ?, phone = COALESCE(?, phone), email = COALESCE(?, email), last_login = ?
                    WHERE customer_id = ?
                    """,
                    (display_name, cred_hash, phone_val, email_val, now, cid)
                )
                conn.commit()
                return CustomerRecord(
                    customer_id=cid,
                    username=norm_user,
                    display_name=display_name,
                    credential_hash=cred_hash,
                    phone=phone_val or row["phone"],
                    email=email_val or row["email"],
                    created_at=row["created_at"],
                    last_login=now
                )

            # Insert new customer
            cid = f"cust_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO customer_profiles (customer_id, username, display_name, credential_hash, phone, email, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, norm_user, display_name, cred_hash, phone_val, email_val, now, now)
            )
            conn.commit()
            return CustomerRecord(
                customer_id=cid,
                username=norm_user,
                display_name=display_name,
                credential_hash=cred_hash,
                phone=phone_val,
                email=email_val,
                created_at=now,
                last_login=now
            )

    def get_by_id(self, customer_id: str) -> Optional[CustomerRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT customer_id, username, display_name, credential_hash, phone, email, created_at, last_login "
                "FROM customer_profiles WHERE customer_id = ?",
                (customer_id,)
            ).fetchone()
            if not row:
                return None
            return CustomerRecord(
                customer_id=row["customer_id"],
                username=row["username"],
                display_name=row["display_name"],
                credential_hash=row["credential_hash"],
                phone=row["phone"],
                email=row["email"],
                created_at=row["created_at"],
                last_login=row["last_login"]
            )

    def authenticate(self, username: str, password_credential: str) -> Optional[CustomerRecord]:
        """
        Authenticates customer by Name (username) and Phone/Email (password).
        Handles flexible phone matching (e.g. matching last 7+ digits).
        """
        if not username or not password_credential:
            return None

        norm_user = self.normalize_username(username)
        target_hash = self.hash_credential(password_credential)
        norm_cred = self.normalize_credential(password_credential)

        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT customer_id, username, display_name, credential_hash, phone, email, created_at, last_login "
                "FROM customer_profiles WHERE username = ?",
                (norm_user,)
            ).fetchall()

            for row in rows:
                # 1. Exact hash match
                if row["credential_hash"] == target_hash:
                    return self._finish_login(conn, row)

                # 2. Email case-insensitive comparison
                if "@" in norm_cred and row["email"]:
                    if row["email"].strip().lower() == norm_cred:
                        return self._finish_login(conn, row)

                # 3. Flexible phone comparison (match last 7+ digits)
                cred_digits = re.sub(r"\D", "", norm_cred)
                stored_phone = row["phone"] or ""
                stored_digits = re.sub(r"\D", "", stored_phone)
                if len(cred_digits) >= 7 and len(stored_digits) >= 7:
                    if cred_digits.endswith(stored_digits[-7:]) or stored_digits.endswith(cred_digits[-7:]):
                        return self._finish_login(conn, row)

            return None

    def _finish_login(self, conn: sqlite3.Connection, row: sqlite3.Row) -> CustomerRecord:
        now = time.time()
        conn.execute("UPDATE customer_profiles SET last_login = ? WHERE customer_id = ?", (now, row["customer_id"]))
        conn.commit()
        return CustomerRecord(
            customer_id=row["customer_id"],
            username=row["username"],
            display_name=row["display_name"],
            credential_hash=row["credential_hash"],
            phone=row["phone"],
            email=row["email"],
            created_at=row["created_at"],
            last_login=now
        )

    def link_session(self, session_id: str, customer_id: str, customer_name: Optional[str] = None) -> bool:
        """Links an existing session to a customer account."""
        try:
            with self._get_connection() as conn:
                if customer_name:
                    conn.execute(
                        "UPDATE conversation_sessions SET customer_id = ?, customer_name = ? WHERE session_id = ?",
                        (customer_id, customer_name, session_id)
                    )
                else:
                    conn.execute(
                        "UPDATE conversation_sessions SET customer_id = ? WHERE session_id = ?",
                        (customer_id, session_id)
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to link session {session_id} to customer {customer_id}: {e}")
            return False

    def get_customer_sessions(self, customer_id: str) -> List[Dict[str, Any]]:
        """Returns all past chat sessions belonging to a customer."""
        sessions = []
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT session_id, created_at, updated_at, customer_name, state_json, history_json
                    FROM conversation_sessions
                    WHERE customer_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 50
                    """,
                    (customer_id,)
                ).fetchall()

                for r in rows:
                    preview = ""
                    turn_count = 0
                    category = ""
                    product = ""
                    try:
                        hist = json.loads(r["history_json"])
                        turn_count = len(hist) // 2 if hist else 0
                        # Find first user query for preview
                        for msg in hist:
                            if msg.get("role") == "user":
                                preview = msg.get("content", "")[:120]
                                break
                    except Exception:
                        pass

                    try:
                        st = json.loads(r["state_json"])
                        category = st.get("category") or ""
                        product = (st.get("active_product") or {}).get("name") or ""
                    except Exception:
                        pass

                    sessions.append({
                        "session_id": r["session_id"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "customer_name": r["customer_name"],
                        "turn_count": turn_count,
                        "preview": preview or "Chat session",
                        "category": category,
                        "product": product
                    })
        except Exception as e:
            logger.error(f"Failed to get sessions for customer {customer_id}: {e}")
        return sessions

    def get_session_history(self, session_id: str, customer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves full conversation history and state for a session."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT session_id, created_at, updated_at, customer_name, customer_id, state_json, history_json "
                    "FROM conversation_sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if not row:
                    return None

                if customer_id and row["customer_id"] != customer_id:
                    logger.warning(f"Unauthorized session access: session {session_id} not owned by {customer_id}")
                    return None

                return {
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "customer_name": row["customer_name"],
                    "customer_id": row["customer_id"],
                    "state": json.loads(row["state_json"]),
                    "history": json.loads(row["history_json"])
                }
        except Exception as e:
            logger.error(f"Failed to get session history for {session_id}: {e}")
            return None


customer_repository = CustomerRepository()
