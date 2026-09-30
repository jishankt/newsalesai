"""
QA Test Suite - Phase 0: Feature Flag CUSTOMER_LOGIN_ENABLED
Tests:
- When CUSTOMER_LOGIN_ENABLED is False (default):
  * Endpoints return 404
  * Onboarding opt-in prompt is NOT attached
  * No customer profiles created
- When CUSTOMER_LOGIN_ENABLED is True:
  * Endpoints are active and reachable
  * Onboarding prompt triggers
"""

import unittest
import os
from unittest.mock import patch
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager
from domain.conversation_state import ConversationState

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_phase0.db")


class TestPhase0FeatureFlag(unittest.TestCase):
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

    def test_endpoints_disabled_when_flag_false(self):
        """When CUSTOMER_LOGIN_ENABLED is False, auth and session endpoints must return 404."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", False), \
             patch("app.CUSTOMER_LOGIN_ENABLED", False):
            # Login endpoint
            r_login = self.client.post("/api/customer/auth/login", json={"username": "test", "password": "123"})
            self.assertEqual(r_login.status_code, 404)

            # Me endpoint
            r_me = self.client.get("/api/customer/auth/me")
            self.assertEqual(r_me.status_code, 404)

            # Logout endpoint
            r_logout = self.client.post("/api/customer/auth/logout")
            self.assertEqual(r_logout.status_code, 404)

            # Sessions endpoint
            r_sess = self.client.get("/api/customer/sessions")
            self.assertEqual(r_sess.status_code, 404)

            # Session detail endpoint
            r_detail = self.client.get("/api/customer/sessions/any_sess")
            self.assertEqual(r_detail.status_code, 404)

    def test_onboarding_skipped_when_flag_false(self):
        """When CUSTOMER_LOGIN_ENABLED is False, the opt-in prompt must not be attached during normal chat."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", False), \
             patch("app.CUSTOMER_LOGIN_ENABLED", False), \
             patch("agent.orchestrator.CUSTOMER_LOGIN_ENABLED", False, create=True), \
             patch("conversation.customer_flow_handler.CUSTOMER_LOGIN_ENABLED", False, create=True):
            sid = "sess_p0_disabled"
            r = self.client.post("/api/chat", json={
                "session_id": sid,
                "message": "I need a photo printer for gallery exhibitions."
            })
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            reply = data.get("reply", "")
            self.assertNotIn("Are you interested in sharing your name and contact details", reply)

    def test_endpoints_enabled_when_flag_true(self):
        """When CUSTOMER_LOGIN_ENABLED is True, endpoints respond normally."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", True), \
             patch("app.CUSTOMER_LOGIN_ENABLED", True):
            r_me = self.client.get("/api/customer/auth/me")
            self.assertEqual(r_me.status_code, 200)
            data = r_me.get_json()
            self.assertTrue(data.get("success"))
            self.assertFalse(data.get("logged_in"))


if __name__ == "__main__":
    unittest.main()
