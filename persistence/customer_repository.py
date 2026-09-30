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
import hmac
import logging
from typing import Dict, Any, List, Optional, Tuple
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
        """Computes HMAC-SHA256 credential hash using CREDENTIAL_PEPPER."""
        from config import CREDENTIAL_PEPPER
        norm = cls.normalize_credential(credential)
        pepper = CREDENTIAL_PEPPER or "kepler-default-dev-credential-pepper-12345"
        return hmac.new(pepper.encode("utf-8"), norm.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def hash_credential_legacy(cls, credential: str) -> str:
        """Legacy unsalted SHA-256 hash for backward compatibility."""
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
        Authenticates customer:
        1. Finds customer by credential (exact HMAC hash, legacy SHA-256, email, or 9-digit phone suffix).
        2. Requires that the first name token of the input username matches the first name token of the customer record.
        3. Upgrades legacy hash to HMAC-SHA256 upon successful login.
        """
        if not username or not password_credential:
            return None

        norm_user = self.normalize_username(username)
        if not norm_user:
            return None
        input_first_name = norm_user.split()[0]

        target_hmac = self.hash_credential(password_credential)
        target_legacy = self.hash_credential_legacy(password_credential)
        norm_cred = self.normalize_credential(password_credential)
        cred_digits = re.sub(r"\D", "", norm_cred)

        with self._get_connection() as conn:
            candidates = conn.execute(
                "SELECT customer_id, username, display_name, credential_hash, phone, email, created_at, last_login "
                "FROM customer_profiles"
            ).fetchall()

            for row in candidates:
                stored_hash = row["credential_hash"]
                stored_phone = row["phone"] or ""
                stored_digits = re.sub(r"\D", "", stored_phone)
                stored_email = (row["email"] or "").strip().lower()

                matched_cred = False
                needs_upgrade = False

                # 1. Exact HMAC hash match
                if hmac.compare_digest(stored_hash, target_hmac):
                    matched_cred = True
                # 2. Legacy SHA-256 match
                elif hmac.compare_digest(stored_hash, target_legacy):
                    matched_cred = True
                    needs_upgrade = True
                # 3. Email match
                elif "@" in norm_cred and stored_email and hmac.compare_digest(stored_email, norm_cred):
                    matched_cred = True
                    needs_upgrade = True
                # 4. Tightened 9-digit phone match
                elif len(cred_digits) >= 9 and len(stored_digits) >= 9:
                    if cred_digits[-9:] == stored_digits[-9:]:
                        matched_cred = True
                        needs_upgrade = True

                if matched_cred:
                    stored_user = self.normalize_username(row["username"])
                    stored_display = self.normalize_username(row["display_name"])
                    stored_first_name = stored_user.split()[0] if stored_user else ""
                    stored_disp_first = stored_display.split()[0] if stored_display else ""

                    target_first = stored_first_name or stored_disp_first
                    name_matches = bool(
                        input_first_name
                        and target_first
                        and input_first_name == target_first
                    )

                    if name_matches:
                        if needs_upgrade:
                            try:
                                conn.execute(
                                    "UPDATE customer_profiles SET credential_hash = ? WHERE customer_id = ?",
                                    (target_hmac, row["customer_id"])
                                )
                                conn.commit()
                                logger.info(f"Upgraded customer {row['customer_id']} credential hash to HMAC-SHA256.")
                            except Exception as e:
                                logger.warning(f"Failed to upgrade hash for {row['customer_id']}: {e}")

                        return self._finish_login(conn, row)

            return None

    def record_login_attempt(self, username: str, ip_address: str, success: bool):
        now = time.time()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO login_attempts (username, ip_address, success, attempt_time) VALUES (?, ?, ?, ?)",
                    (username.strip().lower() if username else "", ip_address.strip() if ip_address else "", 1 if success else 0, now)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record login attempt: {e}")

    def check_login_throttle(self, username: str, ip_address: str) -> Tuple[bool, Optional[int]]:
        """
        Limits failed attempts:
        - 5 per username per 15 minutes (900s)
        - 20 per IP per hour (3600s)
        Returns (allowed: bool, retry_after: Optional[int]).
        """
        now = time.time()
        norm_user = username.strip().lower() if username else ""
        norm_ip = ip_address.strip() if ip_address else ""

        try:
            with self._get_connection() as conn:
                # 1. Check username limit (5 failures in last 15 min)
                if norm_user:
                    window_user = now - 900
                    row_u = conn.execute(
                        "SELECT COUNT(*), MIN(attempt_time) FROM login_attempts "
                        "WHERE username = ? AND success = 0 AND attempt_time > ?",
                        (norm_user, window_user)
                    ).fetchone()
                    count_u = row_u[0] if row_u else 0
                    if count_u >= 5:
                        min_time = row_u[1] or window_user
                        retry_after = max(1, int(900 - (now - min_time)))
                        return False, retry_after

                # 2. Check IP limit (20 failures in last 60 min)
                if norm_ip:
                    window_ip = now - 3600
                    row_ip = conn.execute(
                        "SELECT COUNT(*), MIN(attempt_time) FROM login_attempts "
                        "WHERE ip_address = ? AND success = 0 AND attempt_time > ?",
                        (norm_ip, window_ip)
                    ).fetchone()
                    count_ip = row_ip[0] if row_ip else 0
                    if count_ip >= 20:
                        min_time_ip = row_ip[1] or window_ip
                        retry_after = max(1, int(3600 - (now - min_time_ip)))
                        return False, retry_after

        except Exception as e:
            logger.error(f"Error checking login throttle: {e}")

        return True, None

    def reset_login_throttle(self, username: str, ip_address: str):
        """Clears failed attempts upon successful login."""
        norm_user = username.strip().lower() if username else ""
        norm_ip = ip_address.strip() if ip_address else ""
        try:
            with self._get_connection() as conn:
                if norm_user:
                    conn.execute("DELETE FROM login_attempts WHERE username = ?", (norm_user,))
                if norm_ip:
                    conn.execute("DELETE FROM login_attempts WHERE ip_address = ?", (norm_ip,))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to reset login throttle: {e}")

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
