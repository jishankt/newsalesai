"""
QA Test Suite - Phase 2: Full-Name Bug & First-Name Matching
Tests:
- Full-name extraction keeps up to 4 alphabetic tokens (allows Arabic, hyphens, apostrophes)
- Stops at stop-words (and, my, mobile, phone, number, email, is, am, the, whatsapp, etc.), digits, '@'
- Stores and displays the full name during onboarding and history save
- Login matching: finds customer by credential first, requires first name token match (case-insensitive, normalized spaces)
- Full name, first name only, and extra spaces must all work; wrong first name must fail
"""

import unittest
import os
from unittest.mock import patch
from app import app
from conversation.customer_flow_handler import extract_name_and_contact, extract_full_name
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_phase2.db")


class TestPhase2FullName(unittest.TestCase):
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

    def test_extract_omar_al_suwaidi(self):
        """Omar Al Suwaidi must not be truncated to 'Omar Al'."""
        text = "My name is Omar Al Suwaidi and my mobile is +971 52 345 6789"
        name, contact, phone, email = extract_name_and_contact(text)
        self.assertEqual(name, "Omar Al Suwaidi")
        self.assertEqual(contact, "+971 52 345 6789")

    def test_extract_sara(self):
        """'I'm Sara, sara@x.com' must extract 'Sara'."""
        text = "I'm Sara, sara@x.com"
        name, contact, phone, email = extract_name_and_contact(text)
        self.assertEqual(name, "Sara")
        self.assertEqual(contact, "sara@x.com")

    def test_extract_arabic_name(self):
        """Arabic script names must be supported."""
        text = "اسمي عمر السويدي ورقمي 0501234567"
        name, contact, phone, email = extract_name_and_contact(text)
        self.assertEqual(name, "عمر السويدي")
        self.assertEqual(contact, "0501234567")

    def test_extract_hyphenated_name(self):
        """Hyphenated names must be preserved."""
        text = "Jean-Luc Picard, jean@x.com"
        name, contact, phone, email = extract_name_and_contact(text)
        self.assertEqual(name, "Jean-Luc Picard")
        self.assertEqual(contact, "jean@x.com")

    def test_extract_single_name(self):
        """Single names must work properly."""
        text = "Tariq, 0501234567"
        name, contact, phone, email = extract_name_and_contact(text)
        self.assertEqual(name, "Tariq")
        self.assertEqual(contact, "0501234567")

    def test_display_and_store_full_name_in_onboarding(self):
        """Full name is stored and displayed in bot replies."""
        with patch("config.CUSTOMER_LOGIN_ENABLED", True), \
             patch("app.CUSTOMER_LOGIN_ENABLED", True):
            sid = "sess_p2_full_name"
            # 1. Trigger opt-in
            self.client.post("/api/chat", json={"session_id": sid, "message": "I need a photo printer"})
            # 2. Provide details with 3-word name
            r2 = self.client.post("/api/chat", json={
                "session_id": sid,
                "message": "My name is Omar Al Suwaidi and my mobile is +971 52 345 6789"
            })
            rep2 = r2.get_json().get("reply", "")
            self.assertIn("Thank you, **Omar Al Suwaidi**!", rep2)

            # 3. Agree to save history
            r3 = self.client.post("/api/chat", json={"session_id": sid, "message": "Yes, save chat history"})
            rep3 = r3.get_json().get("reply", "")
            self.assertIn("• **Username:** **Omar Al Suwaidi**", rep3)

            # 4. Check DB customer record
            with customer_repository._get_connection() as conn:
                row = conn.execute("SELECT display_name, username FROM customer_profiles").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["display_name"], "Omar Al Suwaidi")
                self.assertEqual(row["username"], "omar al suwaidi")

    def test_login_first_name_token_matching(self):
        """First name token must match: full name, first name only, and extra spaces work; wrong first name fails."""
        customer_repository.create_or_update_customer(
            name="Omar Al Suwaidi",
            contact="+971 52 345 6789"
        )

        # 1. Full name matching
        cust = customer_repository.authenticate("Omar Al Suwaidi", "+971 52 345 6789")
        self.assertIsNotNone(cust)
        self.assertEqual(cust.display_name, "Omar Al Suwaidi")

        # 2. First name only matching
        cust2 = customer_repository.authenticate("Omar", "+971 52 345 6789")
        self.assertIsNotNone(cust2)
        self.assertEqual(cust2.display_name, "Omar Al Suwaidi")

        # 3. Case-insensitivity & extra spaces
        cust3 = customer_repository.authenticate("   omar    ", "+971 52 345 6789")
        self.assertIsNotNone(cust3)

        cust4 = customer_repository.authenticate("   oMaR   al   suwaidi  ", "+971 52 345 6789")
        self.assertIsNotNone(cust4)

        # 4. Wrong first name with same credential must FAIL
        self.assertIsNone(customer_repository.authenticate("Ali", "+971 52 345 6789"))
        self.assertIsNone(customer_repository.authenticate("Ali Al Suwaidi", "+971 52 345 6789"))
        self.assertIsNone(customer_repository.authenticate("Khalid", "+971 52 345 6789"))

    def test_arabic_and_hyphenated_login(self):
        """Arabic names and hyphenated names support first-token matching."""
        customer_repository.create_or_update_customer(name="عمر السويدي", contact="0501112233")
        self.assertIsNotNone(customer_repository.authenticate("عمر", "0501112233"))
        self.assertIsNotNone(customer_repository.authenticate("عمر السويدي", "0501112233"))
        self.assertIsNone(customer_repository.authenticate("علي", "0501112233"))

        customer_repository.create_or_update_customer(name="Jean-Luc Picard", contact="jean@picard.com")
        self.assertIsNotNone(customer_repository.authenticate("Jean-Luc", "jean@picard.com"))
        self.assertIsNotNone(customer_repository.authenticate("Jean-Luc Picard", "jean@picard.com"))
        self.assertIsNone(customer_repository.authenticate("Picard", "jean@picard.com"))


if __name__ == "__main__":
    unittest.main()
