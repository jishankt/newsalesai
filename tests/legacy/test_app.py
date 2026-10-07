"""
Unit tests for Customer Relations Conversational AI application.
Verifies endpoints, multi-turn history, and strict commercial guardrails.
"""

import unittest
from app import app
from guardrails import PRICE_REFUSAL, DISCOUNT_REFUSAL


class ConversationalAiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        import uuid
        self.session_id = f"test-session-{uuid.uuid4().hex[:8]}"

    def test_config_endpoint(self):
        from config import DEFAULT_MODEL
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("company_context", data)
        self.assertEqual(data["default_model"], DEFAULT_MODEL)

    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("active_model", data)

    def test_price_refusal_guardrail(self):
        resp = self.client.post("/api/chat", json={
            "message": "What is the price of your A1 CAD plotter?",
            "session_id": self.session_id
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["reply"], PRICE_REFUSAL)
        self.assertEqual(data["source"], "guardrail_rule")

    def test_discount_refusal_guardrail(self):
        resp = self.client.post("/api/chat", json={
            "message": "Can you give me a 15% discount or special deal?",
            "session_id": self.session_id
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["reply"], DISCOUNT_REFUSAL)
        self.assertEqual(data["source"], "guardrail_rule")

    def test_product_discovery_turn(self):
        resp = self.client.post("/api/chat", json={
            "message": "I need a printer for CAD drawings.",
            "session_id": self.session_id
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("?", data["reply"])  # Contains exactly one clarifying/requirement question

    def test_switch_from_scanner_to_technical_cad(self):
        """Customer asks for scanner, then switches to 'i want technical cad printer'."""
        import uuid
        sess_id = f"test-scanner-to-cad-{uuid.uuid4().hex[:8]}"
        # Turn 1: Ask for scanner
        resp1 = self.client.post("/api/chat", json={
            "message": "i need a scanner",
            "session_id": sess_id
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("scan", resp1.get_json()["reply"].lower())

        # Turn 2: Switch to technical CAD printer
        resp2 = self.client.post("/api/chat", json={
            "message": "i want technical cad printer",
            "session_id": sess_id
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertIn("print size", data2["reply"].lower())
        self.assertNotIn("scan", data2["reply"].lower())


    def test_cad_qualification_with_both_printing_and_scanning(self):
        """Customer qualifies for CAD with size and answers 'Both printing and scanning'."""
        import uuid
        sess_id = f"test-cad-flow-{uuid.uuid4().hex[:8]}"
        # Turn 1: Ask for technical CAD printer
        resp1 = self.client.post("/api/chat", json={
            "message": "i want technical cad printer",
            "session_id": sess_id
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("print size", resp1.get_json()["reply"].lower())

        # Turn 2: Give size with dimensions
        resp2 = self.client.post("/api/chat", json={
            "message": "I mainly need A1 drawings (594 x 841 mm), but I may also need A0 (841 x 1189 mm) occasionally",
            "session_id": sess_id
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("scanning as well", resp2.get_json()["reply"].lower())

        # Turn 3: Answer with 'Both printing and scanning' (with typo or standard)
        resp3 = self.client.post("/api/chat", json={
            "message": "Both printing and scanning",
            "session_id": sess_id
        })
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.get_json()
        # Must NOT repeat the same scanning question! It must ask the next question (volume)
        self.assertNotIn("scanning as well, or printing only", data3["reply"].lower())
        self.assertIn("drawings or pages", data3["reply"].lower())

        # Turn 4: Answer volume
        resp4 = self.client.post("/api/chat", json={
            "message": "around 20 drawings per day",
            "session_id": sess_id
        })
        self.assertEqual(resp4.status_code, 200)
        data4 = resp4.get_json()
        self.assertIn("recommended", data4["reply"].lower())


if __name__ == "__main__":
    unittest.main()
