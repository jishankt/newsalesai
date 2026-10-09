"""
Security and Hardening Tests for Customer Authentication, Registration,
Cross-Customer History Protection, and Sensitive API Protection.
"""

import unittest
import json
import uuid
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.conversation_state import ConversationState


class TestCustomerSecurityAndAuthHardening(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.victim_username = f"VictimUser_{uuid.uuid4().hex[:6]}"
        self.victim_phone = "+971 50 111 2233"
        self.victim_email = f"victim_{uuid.uuid4().hex[:4]}@keplertech.ae"

        # Pre-seed victim account
        self.victim = customer_repository.create_or_update_customer(
            name=self.victim_username,
            contact=self.victim_phone,
            phone=self.victim_phone,
            email=self.victim_email
        )
        self.victim_id = self.victim.customer_id
        self.original_hash = self.victim.credential_hash

    def test_failed_login_cannot_create_or_modify_existing_account(self):
        """1. Failed login must not fall through to create or modify an existing account."""
        attacker_phone = "+971 55 999 8877"
        resp = self.client.post("/api/customer/auth/login", json={
            "username": self.victim_username,
            "password": attacker_phone  # Attacker providing wrong credential
        })
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["success"])

        # Verify victim's credential hash was NOT overwritten or modified!
        refreshed_victim = customer_repository.get_by_id(self.victim_id)
        self.assertIsNotNone(refreshed_victim)
        self.assertEqual(refreshed_victim.credential_hash, self.original_hash)
        self.assertEqual(refreshed_victim.phone, self.victim_phone)

    def test_incorrect_phone_or_email_cannot_replace_valid_credential(self):
        """2. An incorrect phone/email cannot replace a valid credential via repository."""
        tampered = customer_repository.create_or_update_customer(
            name=self.victim_username,
            contact="+971 56 000 0000"  # Mismatched contact
        )
        # Repository must retain original credential hash
        self.assertEqual(tampered.credential_hash, self.original_hash)

        # Victim can still authenticate with original password
        auth = customer_repository.authenticate(self.victim_username, self.victim_phone)
        self.assertIsNotNone(auth)
        self.assertEqual(auth.customer_id, self.victim_id)

    def test_registration_and_login_are_distinct_operations(self):
        """3. Registration and login are separate, explicit operations."""
        new_user = f"NewUser_{uuid.uuid4().hex[:6]}"
        new_phone = f"+971 52 {uuid.uuid4().int % 9000000 + 1000000}"

        # Attempting login on non-existent account fails
        login_fail = self.client.post("/api/customer/auth/login", json={
            "username": new_user,
            "password": new_phone
        })
        self.assertEqual(login_fail.status_code, 401)

        # Explicit registration succeeds
        reg_resp = self.client.post("/api/customer/auth/register", json={
            "username": new_user,
            "password": new_phone
        })
        self.assertEqual(reg_resp.status_code, 201)
        reg_data = reg_resp.get_json()
        self.assertTrue(reg_data["success"])
        self.assertEqual(reg_data["customer"]["name"], new_user)

        # Subsequent login succeeds
        login_succ = self.client.post("/api/customer/auth/login", json={
            "username": new_user,
            "password": new_phone
        })
        self.assertEqual(login_succ.status_code, 200)
        self.assertTrue(login_succ.get_json()["success"])

    def test_registration_prevents_duplicate_account_hijack(self):
        """4. Registration fails if username or registered contact already exists."""
        # Attempt to register victim's username with attacker phone
        dup_resp = self.client.post("/api/customer/auth/register", json={
            "username": self.victim_username,
            "password": f"+971 55 {uuid.uuid4().int % 9000000 + 1000000}"
        })
        self.assertEqual(dup_resp.status_code, 409)
        self.assertIn("already exists", dup_resp.get_json()["error"])

    def test_one_customer_cannot_read_another_customers_history(self):
        """5. One customer cannot read another customer's past conversation sessions."""
        # Create victim session
        victim_session = f"victim_sess_{uuid.uuid4().hex[:8]}"
        v_state = ConversationState(session_id=victim_session)
        v_state.customer_id = self.victim_id
        v_state.customer_name = self.victim_username
        state_repository.save_session(victim_session, v_state, [
            {"role": "user", "content": "Secret quote for CAD plotter."}
        ])
        customer_repository.link_session(victim_session, self.victim_id, self.victim_username)

        # Create attacker customer
        attacker_user = f"Attacker_{uuid.uuid4().hex[:6]}"
        attacker_phone = f"+971 58 {uuid.uuid4().int % 9000000 + 1000000}"
        attacker = customer_repository.create_or_update_customer(attacker_user, attacker_phone)


        # Attacker logs in
        login_resp = self.client.post("/api/customer/auth/login", json={
            "username": attacker_user,
            "password": attacker_phone
        })
        self.assertEqual(login_resp.status_code, 200)

        # Attacker attempts to fetch victim's session
        fetch_resp = self.client.get(f"/api/customer/sessions/{victim_session}")
        self.assertIn(fetch_resp.status_code, [401, 404])
        self.assertFalse(fetch_resp.get_json()["success"])

    def test_unauthenticated_leads_endpoint_protection(self):
        """6. Public unauthenticated access to /api/leads must be denied."""
        resp = self.client.get("/api/leads")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.get_json()["success"])

    def test_compare_endpoint_input_validation(self):
        """7. /api/compare must validate inputs to prevent malicious payloads."""
        # Missing or empty
        r1 = self.client.post("/api/compare", json={"product_ids": []})
        self.assertEqual(r1.status_code, 400)

        # Single product (cannot compare fewer than 2)
        r2 = self.client.post("/api/compare", json={"product_ids": ["epson-sc-t3100"]})
        self.assertEqual(r2.status_code, 400)

        # Exceeds max limit (more than 10)
        r3 = self.client.post("/api/compare", json={"product_ids": [f"id-{i}" for i in range(15)]})
        self.assertEqual(r3.status_code, 400)

        # Valid approved products
        r4 = self.client.post("/api/compare", json={"product_ids": ["epson-sc-t3100", "epson-sc-t5100"]})
        self.assertEqual(r4.status_code, 200)
        self.assertTrue(r4.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
