"""
QA Test Suite - Phase 1: Login Hardening
Tests:
- Bot never echoes full credential or prints phone/email as password; masks if shown
- No PII in logs during onboarding flow
- Login throttling via login_attempts: 5 failed per username / 15m, 20 per IP / hour -> HTTP 429 with Retry-After
- Generic error message on failed login (doesn't reveal user existence)
- Reset throttle on successful login
- HMAC-SHA256 with CREDENTIAL_PEPPER and upgrade from legacy SHA-256
- Tightened fuzzy phone matching to last 9 digits (handles +971, 05x, spaces, dashes)
- Session cookies: secure in prod, httponly, samesite=Lax, lifetime 7 days
- ProxyFix prevents spoofed X-Forwarded-For from bypassing rate limit
"""

import unittest
import os
import time
import hashlib
import hmac
import logging
from unittest.mock import patch
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager
from config import CREDENTIAL_PEPPER

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_phase1.db")


class TestPhase1LoginHardening(unittest.TestCase):
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

    def test_credential_never_echoed_in_full(self):
        """Bot messages must never print raw phone/email as password; must mask phone and use safe wording."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", True), \
             patch("app.CUSTOMER_LOGIN_ENABLED", True):
            sid = "sess_mask_test"
            # 1. Trigger opt-in
            self.client.post("/api/chat", json={"session_id": sid, "message": "I need a photo printer"})
            # 2. Provide details
            r2 = self.client.post("/api/chat", json={
                "session_id": sid,
                "message": "My name is Tariq and my phone number is +971 50 123 4567"
            })
            rep2 = r2.get_json().get("reply", "")
            # Must NOT contain raw unmasked phone '+971 50 123 4567'
            self.assertNotIn("+971 50 123 4567", rep2)
            # Must contain masked phone or safe wording
            self.assertTrue("**" in rep2 or "phone number" in rep2)

            # 3. Enable history
            r3 = self.client.post("/api/chat", json={"session_id": sid, "message": "Yes, save chat history"})
            rep3 = r3.get_json().get("reply", "")
            # Must NOT echo raw password
            self.assertNotIn("+971 50 123 4567", rep3)
            # Password field description must be safe wording
            self.assertIn("The phone number or email you shared", rep3)

    def test_brute_force_throttle_and_generic_error(self):
        """Failed attempts return generic error and trigger 429 after 5 failed attempts per user."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", True), \
             patch("app.CUSTOMER_LOGIN_ENABLED", True):
            customer_repository.create_or_update_customer(name="VictimUser", contact="+971 50 999 8888")

            # 1-4 attempts return 401 with generic error
            for i in range(4):
                r = self.client.post("/api/customer/auth/login", json={"username": "VictimUser", "password": "wrong"})
                self.assertEqual(r.status_code, 401)
                self.assertEqual(r.get_json().get("error"), "Invalid login credentials.")

            # 5th failed attempt
            r5 = self.client.post("/api/customer/auth/login", json={"username": "VictimUser", "password": "wrong"})
            # 6th attempt must be throttled with 429
            r6 = self.client.post("/api/customer/auth/login", json={"username": "VictimUser", "password": "wrong"})
            self.assertEqual(r6.status_code, 429)
            self.assertIn("Retry-After", r6.headers)
            self.assertIn("Too many failed login attempts", r6.get_json().get("error", ""))

    def test_hmac_hash_and_legacy_sha256_upgrade(self):
        """Legacy unsalted SHA-256 is accepted on login and transparently upgraded to HMAC-SHA256."""
        # Insert a user with legacy SHA-256 hash
        norm_user = "legacy user"
        raw_cred = "+971 50 777 6666"
        norm_cred = "971507776666"
        legacy_hash = hashlib.sha256(norm_cred.encode("utf-8")).hexdigest()

        with customer_repository._get_connection() as conn:
            conn.execute(
                "INSERT INTO customer_profiles (customer_id, username, display_name, credential_hash, phone, created_at, last_login) "
                "VALUES ('cust_legacy_1', ?, 'Legacy User', ?, ?, ?, ?)",
                (norm_user, legacy_hash, raw_cred, time.time(), time.time())
            )
            conn.commit()

        # Authenticate with legacy credentials
        auth_cust = customer_repository.authenticate("Legacy User", raw_cred)
        self.assertIsNotNone(auth_cust)
        self.assertEqual(auth_cust.customer_id, "cust_legacy_1")

        # Verify hash was upgraded in the database
        with customer_repository._get_connection() as conn:
            row = conn.execute("SELECT credential_hash FROM customer_profiles WHERE customer_id = 'cust_legacy_1'").fetchone()
            new_hash = row[0]
            self.assertNotEqual(new_hash, legacy_hash)
            # Must equal HMAC-SHA256
            expected_hmac = customer_repository.hash_credential(raw_cred)
            self.assertEqual(new_hash, expected_hmac)

    def test_tightened_9_digit_phone_matching(self):
        """Phone matching matches on the last 9 digits and rejects 7-8 digit collisions."""
        # Stored phone: +971 50 123 4567 -> last 9 digits are '501234567'
        customer_repository.create_or_update_customer(name="Phone Tester", contact="+971 50 123 4567")

        # Matching formats for the same number
        self.assertIsNotNone(customer_repository.authenticate("Phone Tester", "0501234567"))
        self.assertIsNotNone(customer_repository.authenticate("Phone Tester", "050 123 4567"))
        self.assertIsNotNone(customer_repository.authenticate("Phone Tester", "+971-50-123-4567"))

        # Collision with same last 7 digits but different 9th digit (e.g. 52 vs 50)
        self.assertIsNone(customer_repository.authenticate("Phone Tester", "+971 52 123 4567"))
        self.assertIsNone(customer_repository.authenticate("Phone Tester", "0521234567"))

    def test_session_cookie_settings(self):
        """SESSION_COOKIE_HTTPONLY=True, SAMESITE=Lax, PERMANENT_SESSION_LIFETIME=7 days."""
        from datetime import timedelta
        self.assertTrue(app.config.get("SESSION_COOKIE_HTTPONLY"))
        self.assertEqual(app.config.get("SESSION_COOKIE_SAMESITE"), "Lax")
        self.assertEqual(app.config.get("PERMANENT_SESSION_LIFETIME"), timedelta(days=7))

    def test_no_pii_in_logs_during_onboarding(self):
        """During onboarding flow, full contact details (phone, email) must never appear in log records."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", True), \
             patch("app.CUSTOMER_LOGIN_ENABLED", True):
            sid = "sess_log_pii_test"
            raw_phone = "+971 55 987 6543"
            raw_email = "testcustomer99@example.com"

            with self.assertLogs() as cm:
                self.client.post("/api/chat", json={"session_id": sid, "message": "I want to buy a printer"})
                self.client.post("/api/chat", json={"session_id": sid, "message": f"My name is John and phone is {raw_phone} email is {raw_email}"})
                self.client.post("/api/chat", json={"session_id": sid, "message": "Yes, please save history"})

                # Inspect captured log messages
                all_logs = " ".join(cm.output)
                self.assertNotIn(raw_phone, all_logs)
                self.assertNotIn(raw_email, all_logs)

    def test_spoofed_x_forwarded_for_cannot_bypass_limit(self):
        """ProxyFix ensures attacker cannot bypass IP throttle by prepending spoofed IPs in X-Forwarded-For."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", True), \
             patch("app.CUSTOMER_LOGIN_ENABLED", True):
            # Send 20 failed login attempts from real IP 192.168.1.50 through trusted proxy 127.0.0.1
            # In each request, the attacker changes the leftmost IP in X-Forwarded-For
            for i in range(20):
                spoofed_header = f"attacker-{i}.spoofed.ip, 192.168.1.50"
                resp = self.client.post(
                    "/api/customer/auth/login",
                    json={"username": f"User_{i}", "password": "wrongpassword"},
                    headers={"X-Forwarded-For": spoofed_header},
                    environ_base={"REMOTE_ADDR": "127.0.0.1"}
                )
                self.assertEqual(resp.status_code, 401)

            # 21st request with yet another spoofed IP should still be throttled at HTTP 429
            # because the real client IP 192.168.1.50 exceeded 20 failures/hour
            spoofed_header = "another.spoofed.ip, 192.168.1.50"
            r_blocked = self.client.post(
                "/api/customer/auth/login",
                json={"username": "User_21", "password": "wrongpassword"},
                headers={"X-Forwarded-For": spoofed_header},
                environ_base={"REMOTE_ADDR": "127.0.0.1"}
            )
            self.assertEqual(r_blocked.status_code, 429)
            self.assertIn("Retry-After", r_blocked.headers)


if __name__ == "__main__":
    unittest.main()

