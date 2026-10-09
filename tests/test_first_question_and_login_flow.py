"""
Regression Tests for Initial Scanner/Printer/Consumables Qualification Flow
and Customer Login Flow.
"""

import unittest
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator
from app import app


class TestFirstQuestionAndLoginFlow(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_first_question_greeting_offers_scanner_printer_consumables(self):
        """Initial turn or greeting asks 'Do you want a scanner, printer, or consumables?' with chips."""
        state = ConversationState(session_id="test-greeting-flow")
        res = orchestrator.process_turn("Hello!", session_id="test-greeting-flow", state=state)
        
        reply = res.get("reply", "")
        self.assertIn("Do you want a scanner, printer, or consumables?", reply)
        chips = res.get("suggested_chips", [])
        self.assertIn("Printer", chips)
        self.assertIn("Scanner", chips)
        self.assertIn("Consumables", chips)

    def test_primary_choice_scanner_routes_to_scanner_flow(self):
        """Choosing 'Scanner' routes to scanner types qualification."""
        state = ConversationState(session_id="test-choose-scanner")
        orchestrator.process_turn("hi", session_id="test-choose-scanner", state=state)
        res = orchestrator.process_turn("Scanner", session_id="test-choose-scanner", state=state)
        
        reply = res.get("reply", "").lower()
        self.assertIn("scanner", reply)
        chips = res.get("suggested_chips", [])
        self.assertTrue(any("business" in c.lower() for c in chips))
        self.assertTrue(any("photo" in c.lower() for c in chips))
        self.assertEqual(state.category, "scanners")

    def test_primary_choice_printer_routes_to_printer_flow(self):
        """Choosing 'Printer' routes to printer printing application qualification."""
        state = ConversationState(session_id="test-choose-printer")
        orchestrator.process_turn("hello", session_id="test-choose-printer", state=state)
        res = orchestrator.process_turn("Printer", session_id="test-choose-printer", state=state)
        
        reply = res.get("reply", "").lower()
        self.assertIn("printing", reply)
        chips = res.get("suggested_chips", [])
        self.assertIn("Technical CAD Plotters", chips)
        self.assertIn("Professional Photo & Fine Art", chips)

    def test_primary_choice_consumables_routes_to_consumables_flow(self):
        """Choosing 'Consumables' asks for printer model and provides quick chips."""
        state = ConversationState(session_id="test-choose-consumables")
        orchestrator.process_turn("hey", session_id="test-choose-consumables", state=state)
        res = orchestrator.process_turn("Consumables", session_id="test-choose-consumables", state=state)
        
        reply = res.get("reply", "").lower()
        self.assertTrue("consumables" in reply or "ink" in reply)
        chips = res.get("suggested_chips", [])
        self.assertGreater(len(chips), 0)
        self.assertEqual(state.category, "consumables")

    def test_customer_login_api_flow(self):
        """Customer can authenticate or sign in with Name and Phone/Email."""
        resp = self.client.post("/api/customer/auth/login", json={
            "username": "Tariq",
            "password": "+971 50 123 4567"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["customer"]["name"], "Tariq")
        self.assertIn("sessions", data)
