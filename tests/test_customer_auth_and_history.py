"""
Unit and integration tests for Customer Login, Chat History Retrieval,
and Conditional In-Chat Contact Onboarding Flow.
"""

import unittest
from unittest.mock import patch
import json
import uuid
from app import app
from domain.conversation_state import ConversationState
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from conversation.customer_flow_handler import (
    handle_customer_onboarding,
    is_negative_response,
    is_positive_response,
    extract_name_and_contact,
    should_trigger_opt_in_prompt,
)


class TestCustomerAuthAndHistory(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.test_username = f"TestUser_{uuid.uuid4().hex[:6]}"
        self.test_phone = "+971 50 987 6543"
        self.test_email = "testcustomer@keplertech.ae"

    def test_customer_repository_create_and_auth(self):
        """Verify customer registration and authentication with Name + Phone/Email."""
        # 1. Register customer
        cust = customer_repository.create_or_update_customer(
            name=self.test_username,
            contact=self.test_phone
        )
        self.assertIsNotNone(cust.customer_id)
        self.assertEqual(cust.display_name, self.test_username)

        # 2. Authenticate with exact credentials
        auth_cust = customer_repository.authenticate(self.test_username, self.test_phone)
        self.assertIsNotNone(auth_cust)
        self.assertEqual(auth_cust.customer_id, cust.customer_id)

        # 3. Authenticate with lowercase name and normalized phone digits
        auth_cust2 = customer_repository.authenticate(self.test_username.lower(), "0509876543")
        self.assertIsNotNone(auth_cust2)
        self.assertEqual(auth_cust2.customer_id, cust.customer_id)

        # 4. Fail authentication with incorrect password
        fail_auth = customer_repository.authenticate(self.test_username, "wrongpassword123")
        self.assertIsNone(fail_auth)

    def test_customer_session_linking_and_history_retrieval(self):
        """Verify sessions are linked to customer profile and can be retrieved."""
        cust = customer_repository.create_or_update_customer(
            name=self.test_username,
            contact=self.test_email
        )
        session_id = f"test_sess_{uuid.uuid4().hex[:8]}"

        state = ConversationState(session_id=session_id)
        state.customer_name = cust.display_name
        state.customer_id = cust.customer_id
        history = [
            {"role": "user", "content": "I need an Epson SureColor CAD printer."},
            {"role": "assistant", "content": "I recommend the Epson SureColor T3100."}
        ]

        # Save session in database
        state_repository.save_session(session_id, state, history)
        customer_repository.link_session(session_id, cust.customer_id, cust.display_name)

        # Retrieve sessions for customer
        sessions = customer_repository.get_customer_sessions(cust.customer_id)
        self.assertTrue(any(s["session_id"] == session_id for s in sessions))

        # Retrieve full session history
        history_data = customer_repository.get_session_history(session_id, customer_id=cust.customer_id)
        self.assertIsNotNone(history_data)
        self.assertEqual(len(history_data["history"]), 2)
        self.assertEqual(history_data["history"][0]["content"], "I need an Epson SureColor CAD printer.")

    def test_onboarding_opt_in_decline(self):
        """When user declines opt-in, mark declined and never trigger again ('if they say no dont rtriger')."""
        state = ConversationState(session_id=str(uuid.uuid4()))
        state.lead_prompt_status = "offered_opt_in"

        res = handle_customer_onboarding("no, thanks", "no thanks", state, state.session_id)
        self.assertIsNotNone(res)
        self.assertEqual(state.lead_prompt_status, "declined_opt_in")
        self.assertIn("respect your privacy", res["reply"].lower())

        # Verify should_trigger_opt_in_prompt returns False once declined
        self.assertFalse(should_trigger_opt_in_prompt(state))

    def test_onboarding_opt_in_accept_and_provide_details(self):
        """When user accepts opt-in and provides details, prompt for history save."""
        state = ConversationState(session_id=str(uuid.uuid4()))
        state.lead_prompt_status = "offered_opt_in"

        # Step 1: User says yes
        res1 = handle_customer_onboarding("yes, I'm interested", "yes i am interested", state, state.session_id)
        self.assertIsNotNone(res1)
        self.assertEqual(state.lead_prompt_status, "awaiting_details")
        self.assertIn("Name", res1["reply"])

        # Step 2: User provides Name and Phone
        res2 = handle_customer_onboarding(
            "My name is Tariq Al Mansoor, phone +971 55 123 4567",
            "my name is tariq al mansoor phone +971 55 123 4567",
            state,
            state.session_id
        )
        self.assertIsNotNone(res2)
        self.assertIn(state.lead_prompt_status, ["history_enabled", "offered_history_save"])
        self.assertTrue(
            "username" in res2["reply"].lower()
            or "tariq" in res2["reply"].lower()
            or "password" in res2["reply"].lower()
            or "saved" in res2["reply"].lower()
        )

    def test_onboarding_history_decline(self):
        """When user declines history save, do NOT create credentials ('if they say no furthe chat don t do anything')."""
        state = ConversationState(session_id=str(uuid.uuid4()))
        state.customer_name = "Hamdan"
        state.customer_phone_or_email = "+971501112233"
        state.lead_prompt_status = "offered_history_save"

        res = handle_customer_onboarding("No, continue as guest", "no continue as guest", state, state.session_id)
        self.assertIsNotNone(res)
        self.assertEqual(state.lead_prompt_status, "declined_history")
        self.assertIsNone(state.customer_id)
        self.assertIn("guest", res["reply"].lower())

        # Customer account must NOT exist
        auth = customer_repository.authenticate("Hamdan", "+971501112233")
        self.assertIsNone(auth)

    def test_onboarding_history_accept(self):
        """When user accepts history save, activate customer profile with Name & Contact credentials."""
        state = ConversationState(session_id=str(uuid.uuid4()))
        state.customer_name = f"Rashid_{uuid.uuid4().hex[:4]}"
        state.customer_phone_or_email = "+971554443322"
        state.lead_prompt_status = "offered_history_save"

        res = handle_customer_onboarding("Yes, save chat history", "yes save chat history", state, state.session_id)
        self.assertIsNotNone(res)
        self.assertEqual(state.lead_prompt_status, "history_enabled")
        self.assertIsNotNone(state.customer_id)

        # Verify customer can now authenticate with Name & Phone
        auth = customer_repository.authenticate(state.customer_name, "+971554443322")
        self.assertIsNotNone(auth)
        self.assertEqual(auth.customer_id, state.customer_id)

    def test_api_customer_auth_endpoints(self):
        """Verify API endpoints for customer login, me, sessions, and logout."""
        # Setup customer
        cust_name = f"Fatima_{uuid.uuid4().hex[:4]}"
        cust_phone = "+971529998877"
        cust = customer_repository.create_or_update_customer(cust_name, cust_phone)

        # 1. Login API
        resp = self.client.post("/api/customer/auth/login", json={
            "username": cust_name,
            "password": cust_phone
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["customer"]["name"], cust_name)

        # 2. Check /api/customer/auth/me
        resp_me = self.client.get("/api/customer/auth/me")
        self.assertEqual(resp_me.status_code, 200)
        data_me = resp_me.get_json()
        self.assertTrue(data_me["logged_in"])
        self.assertEqual(data_me["customer"]["name"], cust_name)

        # 3. Check /api/customer/sessions
        resp_sess = self.client.get("/api/customer/sessions")
        self.assertEqual(resp_sess.status_code, 200)
        data_sess = resp_sess.get_json()
        self.assertTrue(data_sess["success"])

        # 4. Logout API
        resp_logout = self.client.post("/api/customer/auth/logout")
        self.assertEqual(resp_logout.status_code, 200)

        # Verify logged out
        resp_me_after = self.client.get("/api/customer/auth/me")
        self.assertFalse(resp_me_after.get_json()["logged_in"])

    @patch("config.CUSTOMER_OPT_IN_PROMPT_ENABLED", True)
    def test_orchestrator_multi_turn_customer_flow(self, *args):
        """Verify orchestrator multi-turn interaction with opt-in and decline."""
        from agent.orchestrator import orchestrator

        sess_id = f"test_orch_{uuid.uuid4().hex[:8]}"
        state = ConversationState(session_id=sess_id)
        history = []

        # Turn 1: Normal question
        t1 = orchestrator.process_turn(
            raw_message="What technical CAD plotters do you have?",
            session_id=sess_id,
            history=history,
            state=state
        )
        self.assertIsNotNone(t1.get("reply"))
        # Opt-in question attached
        self.assertIn("Are you interested in sharing your name and contact details", t1["reply"])
        self.assertIn("Yes, I'm interested", t1["suggested_chips"])
        self.assertIn("No, thanks", t1["suggested_chips"])
        self.assertEqual(state.lead_prompt_status, "offered_opt_in")

        # Update history
        history.append({"role": "user", "content": "What technical CAD plotters do you have?"})
        history.append({"role": "assistant", "content": t1["reply"]})

        # Turn 2: User says "No, thanks"
        t2 = orchestrator.process_turn(
            raw_message="No, thanks",
            session_id=sess_id,
            history=history,
            state=state
        )
        self.assertIsNotNone(t2.get("reply"))
        self.assertEqual(state.lead_prompt_status, "declined_opt_in")

        self.assertIn("privacy", t2["reply"].lower())

        # Update history
        history.append({"role": "user", "content": "No, thanks"})
        history.append({"role": "assistant", "content": t2["reply"]})

        # Turn 3: User continues with normal question -> verify opt-in prompt is NOT triggered again!
        t3 = orchestrator.process_turn(
            raw_message="Tell me about SC-T3100 print speed",
            session_id=sess_id,
            history=history,
            state=state
        )
        self.assertIsNotNone(t3.get("reply"))
        self.assertNotIn("Are you interested in sharing your name and contact details", t3["reply"])


if __name__ == "__main__":
    unittest.main()

