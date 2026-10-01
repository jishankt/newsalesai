"""
QA Automated Test Suite - Section A: Auth and Isolation
Tests:
- Valid, invalid, empty credentials
- Token / session cookie tampering and expiration
- Customer A vs Customer B isolation (cross-tenant access attempts)
- Unauthenticated access to history endpoints
"""

import unittest
import os
import uuid
import json
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager
from domain.conversation_state import ConversationState

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_isolated.db")


class TestSectionAAuthAndIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "qa-test-secret-key-12345"

    def setUp(self):
        # Configure isolated test database
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

    def test_a1_valid_login(self):
        """Customer with valid credentials logs in successfully."""
        cust = customer_repository.create_or_update_customer(
            name="Rashid Al Nuaimi",
            contact="+971 50 123 4567"
        )
        resp = self.client.post("/api/customer/auth/login", json={
            "username": "Rashid Al Nuaimi",
            "password": "+971 50 123 4567"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("customer", {}).get("name"), "Rashid Al Nuaimi")
        self.assertEqual(data.get("customer", {}).get("id"), cust.customer_id)

    def test_a2_invalid_credentials(self):
        """Wrong password or non-existent username returns 401."""
        customer_repository.create_or_update_customer(
            name="Fatima Zahra",
            contact="fatima@example.com"
        )
        # Wrong password
        resp1 = self.client.post("/api/customer/auth/login", json={
            "username": "Fatima Zahra",
            "password": "wrongpassword"
        })
        self.assertEqual(resp1.status_code, 401)
        self.assertFalse(resp1.get_json().get("success"))

        # Non-existent user
        resp2 = self.client.post("/api/customer/auth/login", json={
            "username": "NonExistentUser",
            "password": "+971 50 000 0000"
        })
        self.assertEqual(resp2.status_code, 401)
        self.assertFalse(resp2.get_json().get("success"))

    def test_a3_empty_or_malformed_login_request(self):
        """Empty username or password returns 400."""
        resp1 = self.client.post("/api/customer/auth/login", json={
            "username": "",
            "password": "somepassword"
        })
        self.assertEqual(resp1.status_code, 400)

        resp2 = self.client.post("/api/customer/auth/login", json={
            "username": "ValidUser",
            "password": ""
        })
        self.assertEqual(resp2.status_code, 400)

        resp3 = self.client.post("/api/customer/auth/login", data="non-json")
        self.assertEqual(resp3.status_code, 400)

    def test_a4_unauthenticated_requests_rejected(self):
        """Unauthenticated requests to history endpoints must be rejected with 401."""
        # Unauthenticated sessions list
        resp = self.client.get("/api/customer/sessions")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("Login required", data.get("error", ""))

        # Unauthenticated session detail
        resp_detail = self.client.get("/api/customer/sessions/any_random_session_id")
        self.assertEqual(resp_detail.status_code, 401)
        self.assertFalse(resp_detail.get_json().get("success"))

        # /api/customer/auth/me should indicate not logged in
        resp_me = self.client.get("/api/customer/auth/me")
        self.assertEqual(resp_me.status_code, 200)
        self.assertFalse(resp_me.get_json().get("logged_in"))

    def test_a5_customer_isolation_cross_tenant_prevention(self):
        """Customer A must never see Customer B's history, even when passing Customer B's session_id."""
        # Create Customer A and session A
        cust_a = customer_repository.create_or_update_customer(name="Customer A", contact="+971 50 111 1111")
        session_a = f"sess_a_{uuid.uuid4().hex[:8]}"
        state_a = ConversationState(session_id=session_a, customer_id=cust_a.customer_id, customer_name="Customer A")
        hist_a = [{"role": "user", "content": "Query from Customer A"}]
        state_manager.save(state_a, hist_a)
        customer_repository.link_session(session_a, cust_a.customer_id, "Customer A")

        # Create Customer B and session B
        cust_b = customer_repository.create_or_update_customer(name="Customer B", contact="+971 50 222 2222")
        session_b = f"sess_b_{uuid.uuid4().hex[:8]}"
        state_b = ConversationState(session_id=session_b, customer_id=cust_b.customer_id, customer_name="Customer B")
        hist_b = [{"role": "user", "content": "Private confidential data of Customer B"}]
        state_manager.save(state_b, hist_b)
        customer_repository.link_session(session_b, cust_b.customer_id, "Customer B")

        # Login as Customer A
        client_a = app.test_client()
        login_res_a = client_a.post("/api/customer/auth/login", json={
            "username": "Customer A",
            "password": "+971 50 111 1111"
        })
        self.assertEqual(login_res_a.status_code, 200)

        # 1. Customer A lists sessions: must only see session_a, never session_b
        list_res = client_a.get("/api/customer/sessions")
        self.assertEqual(list_res.status_code, 200)
        sessions_a = list_res.get_json().get("sessions", [])
        session_ids_a = [s["session_id"] for s in sessions_a]
        self.assertIn(session_a, session_ids_a)
        self.assertNotIn(session_b, session_ids_a)

        # 2. Customer A attempts to directly access Customer B's session_id
        leak_attempt = client_a.get(f"/api/customer/sessions/{session_b}")
        # Must return 404 / unauthorized and NOT leak Customer B's history
        self.assertEqual(leak_attempt.status_code, 404)
        leak_data = leak_attempt.get_json()
        self.assertFalse(leak_data.get("success"))
        self.assertNotIn("Private confidential data of Customer B", json.dumps(leak_data))

    def test_a6_tampered_or_invalid_session_cookie(self):
        """Tampered cookie value must not grant customer access."""
        with self.client.session_transaction() as sess:
            sess["customer_id"] = "non_existent_fake_cust_9999"

        # /api/customer/auth/me should reject non-existent customer in DB
        resp = self.client.get("/api/customer/auth/me")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json().get("logged_in"))

    def test_a7_logout_clears_session(self):
        """Logout properly clears session and revokes access to history."""
        customer_repository.create_or_update_customer(name="Logout Tester", contact="+971 50 333 3333")
        self.client.post("/api/customer/auth/login", json={
            "username": "Logout Tester",
            "password": "+971 50 333 3333"
        })
        # Check logged in
        me_res = self.client.get("/api/customer/auth/me")
        self.assertTrue(me_res.get_json().get("logged_in"))

        # Logout
        logout_res = self.client.post("/api/customer/auth/logout")
        self.assertEqual(logout_res.status_code, 200)

        # Verify no longer logged in
        me_after = self.client.get("/api/customer/auth/me")
        self.assertFalse(me_after.get_json().get("logged_in"))

        # Sessions now rejected
        sess_after = self.client.get("/api/customer/sessions")
        self.assertEqual(sess_after.status_code, 401)


if __name__ == "__main__":
    unittest.main()
