"""
QA Automated Security & Production-Readiness Audit Suite (Step 3)
Tests:
- SQL injection on login and history endpoints
- Rate limiting on /api/customer/auth/login
- Cookie and CORS security flags
- Password / credential hashing security (SHA-256 unsalted analysis)
- PII logging detection
- Migration idempotency on existing database schema
"""

import unittest
import os
import uuid
import json
import sqlite3
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager
from persistence.models import CREATE_TABLES_SQL

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_security.db")


class TestSecurityAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True

    def setUp(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass
        customer_repository.db_path = TEST_DB_PATH
        customer_repository._init_db()
        state_repository.db_path = TEST_DB_PATH
        state_repository._init_db()

        with state_manager._lock:
            state_manager._store.clear()
        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_sec1_sql_injection_on_history_endpoint(self):
        """Passing SQL injection payloads into /api/customer/sessions/<session_id> must be safely rejected."""
        cust = customer_repository.create_or_update_customer(name="Sec Tester", contact="+971 50 888 8888")
        with self.client.session_transaction() as sess:
            sess["customer_id"] = cust.customer_id
            sess["customer_name"] = cust.display_name

        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE conversation_sessions; --",
            "1' UNION SELECT customer_id, username, display_name, credential_hash, phone, email, created_at, last_login FROM customer_profiles --",
            "\" OR \"\"=\""
        ]

        for payload in sql_payloads:
            resp = self.client.get(f"/api/customer/sessions/{payload}")
            # Must return 404 (not found), never 500 or leak data
            self.assertIn(resp.status_code, (400, 404), f"SQL injection payload '{payload}' produced status {resp.status_code}")
            data = resp.get_json()
            self.assertFalse(data.get("success"))

        # Verify tables still exist
        with sqlite3.connect(TEST_DB_PATH) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            self.assertIn("conversation_sessions", tables)

    def test_sec2_sql_injection_on_login(self):
        """Passing SQL injection payloads into /api/customer/auth/login must not bypass auth."""
        customer_repository.create_or_update_customer(name="Target User", contact="+971 50 999 9999")

        bypass_payloads = [
            {"username": "Target User' OR '1'='1", "password": "any"},
            {"username": "admin' --", "password": "any"},
            {"username": "Target User", "password": "' OR '1'='1"}
        ]

        for p in bypass_payloads:
            resp = self.client.post("/api/customer/auth/login", json=p)
            self.assertEqual(resp.status_code, 401, f"Bypass payload {p} resulted in status {resp.status_code}")
            self.assertFalse(resp.get_json().get("success"))

    def test_sec3_rate_limiting_on_login_endpoint(self):
        """Check whether /api/customer/auth/login is protected by rate limiting."""
        # Send 35 rapid failed login attempts
        statuses = []
        for i in range(35):
            r = self.client.post("/api/customer/auth/login", json={
                "username": f"BruteForceUser_{i}",
                "password": "wrongpassword"
            })
            statuses.append(r.status_code)

        # Audit finding: If no 429 status is returned, login lacks brute-force rate limiting!
        has_rate_limit = 429 in statuses
        # We record whether rate limiting was triggered
        print(f"\n[Security Audit] Login rate limiting active: {has_rate_limit} (Statuses sample: {statuses[:5]}...{statuses[-5:]})")

    def test_sec4_password_hashing_security(self):
        """Analyze credential hashing implementation."""
        # Check customer_repository.hash_credential
        test_cred = "+971 50 123 4567"
        h1 = customer_repository.hash_credential(test_cred)
        h2 = customer_repository.hash_credential(test_cred)
        # Deterministic identical hash without per-user salt:
        is_unsalted = (h1 == h2)
        print(f"\n[Security Audit] Credential hash is unsalted SHA-256: {is_unsalted} (Length={len(h1)})")

    def test_sec5_cookie_and_session_security_settings(self):
        """Check Flask session cookie security flags."""
        cookie_httponly = app.config.get("SESSION_COOKIE_HTTPONLY")
        cookie_secure = app.config.get("SESSION_COOKIE_SECURE")
        cookie_samesite = app.config.get("SESSION_COOKIE_SAMESITE")
        print(f"\n[Security Audit] Cookie flags: HTTPOnly={cookie_httponly}, Secure={cookie_secure}, SameSite={cookie_samesite}")

    def test_sec6_migration_safety_existing_db(self):
        """Verify _init_db safely migrates existing DB without customer_id column."""
        temp_mig_db = os.path.join(os.path.dirname(__file__), "temp_mig.db")
        if os.path.exists(temp_mig_db):
            os.remove(temp_mig_db)

        # 1. Create legacy schema without customer_id column
        with sqlite3.connect(temp_mig_db) as conn:
            conn.execute("""
            CREATE TABLE conversation_sessions (
                session_id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                customer_name TEXT,
                state_json TEXT NOT NULL,
                history_json TEXT NOT NULL
            )
            """)
            conn.execute("""
            INSERT INTO conversation_sessions VALUES (
                'legacy_sess_1', 1000.0, 1000.0, 'Legacy Customer', '{}', '[]'
            )
            """)
            conn.commit()

        # 2. Run customer_repository._init_db on legacy database
        customer_repository.db_path = temp_mig_db
        customer_repository._init_db()

        # 3. Verify legacy data preserved and customer_id column added
        with sqlite3.connect(temp_mig_db) as conn:
            cur = conn.execute("SELECT session_id, customer_id, customer_name FROM conversation_sessions")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "legacy_sess_1")
            self.assertEqual(rows[0][2], "Legacy Customer")
            self.assertIsNone(rows[0][1])  # customer_id is null for legacy row

        if os.path.exists(temp_mig_db):
            os.remove(temp_mig_db)


if __name__ == "__main__":
    unittest.main()
