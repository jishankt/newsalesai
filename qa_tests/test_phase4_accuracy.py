"""
Unit and integration tests for Phase 4: Accuracy & Guardrails Hardening.
Tests:
1. Closing / thanks intent (no product cards, deterministic short closing)
2. Handover off-hours handling (Dubai GST business hours & contact details prompts)
3. Generalized unknown model handling (Citizen & Epson, no hallucination, no echo)
4. Model alias matching at match time (SC-P700, P700, sc p700, surecolor p700)
5. Rotating template variety (openers & pricing redirects, no consecutive repetition, sales rep offer)
6. Consumables formatting (strict requirement of name, markdown link, and SKU)
"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app import app
from config import is_within_business_hours
from domain.conversation_state import ConversationState
from domain.state_store import state_manager
from catalog.catalogue_resolver import find_mentioned_catalogue_products
from agent.orchestrator import (
    orchestrator,
    format_rotating_opener,
    format_rotating_pricing_redirect,
    OPENER_TEMPLATES,
    PRICING_REDIRECT_TEMPLATES,
)
from nlp.deterministic_interceptor import intercept


class TestPhase4AccuracyAndGuardrails(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.session_id = f"test-phase4-{datetime.now().timestamp()}"

    # ── 1. Closing / Thanks Intent ───────────────────────────────────────

    def test_closing_thanks_intent_deterministic(self):
        """User closing/thanks statements with zero product terms return clean closing with no product cards."""
        closing_phrases = [
            "Got it, thanks for directing me to the commercial team.",
            "thank you for directing me",
            "got it, thanks",
            "thanks for the information",
            "Understood, thank you!",
        ]
        for phrase in closing_phrases:
            res = intercept(phrase)
            self.assertTrue(res.matched, f"Expected matched=True for phrase: '{phrase}'")
            self.assertEqual(res.intent, "conversation_ending")
            self.assertFalse(res.should_continue)
            self.assertIn("Kepler Tech", res.response)

        # End-to-end through /api/chat
        resp = self.client.post("/api/chat", json={
            "session_id": self.session_id,
            "message": "Got it, thanks for directing me to the commercial team.",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("product_cards", []), [])
        self.assertEqual(data.get("consumable_cards", []), [])
        self.assertIn("Kepler Tech", data.get("reply", ""))

    def test_closing_with_product_terms_not_swallowed(self):
        """A message saying thanks but asking about a product or price must NOT be swallowed as conversation_ending."""
        res = intercept("Thanks, but what is the price of the P700?")
        self.assertNotEqual(res.intent, "conversation_ending")

    # ── 2. Handover Off-Hours Handling ────────────────────────────────────

    def test_business_hours_schedule(self):
        """Test Dubai GST business hours (Mon-Fri 8:30-17:30, Sat 8:30-13:00, Sun closed)."""
        gst = timezone(timedelta(hours=4))

        # Tuesday at 10:00 GST -> Open
        tue_open = datetime(2026, 9, 29, 10, 0, tzinfo=gst)
        self.assertTrue(is_within_business_hours(tue_open))

        # Tuesday at 18:00 GST -> Closed
        tue_closed = datetime(2026, 9, 29, 18, 0, tzinfo=gst)
        self.assertFalse(is_within_business_hours(tue_closed))

        # Saturday at 10:00 GST -> Open
        sat_open = datetime(2026, 10, 3, 10, 0, tzinfo=gst)
        self.assertTrue(is_within_business_hours(sat_open))

        # Saturday at 14:00 GST -> Closed
        sat_closed = datetime(2026, 10, 3, 14, 0, tzinfo=gst)
        self.assertFalse(is_within_business_hours(sat_closed))

        # Sunday at 11:00 GST -> Closed
        sun_closed = datetime(2026, 10, 4, 11, 0, tzinfo=gst)
        self.assertFalse(is_within_business_hours(sun_closed))

    @patch("app.is_within_business_hours", return_value=False)
    def test_handover_off_hours_without_contact(self, mock_hours):
        """Handover requested outside business hours when contact details are missing prompts for phone/email."""
        resp = self.client.post("/api/chat", json={
            "session_id": f"{self.session_id}-off1",
            "message": "I want to speak to a human agent please",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("handover_triggered"))
        reply = data.get("reply", "")
        self.assertIn("closed", reply.lower())
        self.assertIn("next working day", reply.lower())
        self.assertIn("contact number or email", reply.lower())

    @patch("app.is_within_business_hours", return_value=False)
    def test_handover_off_hours_with_contact(self, mock_hours):
        """Handover requested outside business hours when contact details exist confirms follow-up on next day."""
        sess_id = f"{self.session_id}-off2"
        state = ConversationState(session_id=sess_id, customer_phone_or_email="+971501234567")
        state_manager.save(state)

        resp = self.client.post("/api/chat", json={
            "session_id": sess_id,
            "message": "Can I speak to a person?",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("handover_triggered"))
        reply = data.get("reply", "")
        self.assertIn("closed", reply.lower())
        self.assertIn("contact details on file", reply.lower())

    # ── 3. Generalized Unknown Model Handling ─────────────────────────────

    def test_unknown_citizen_model(self):
        """Inputs like 'Do you sell the Citizen SuperPhotomaster 10000?' state model is not in catalogue and recommend Citizen options."""
        state = ConversationState(session_id=f"{self.session_id}-unk1")
        res = orchestrator.process_turn("Do you sell the Citizen SuperPhotomaster 10000?", state=state)
        reply = res.get("reply", "")
        self.assertIn("Superphotomaster 10000", reply)
        self.assertIn("not in our authorized catalogue", reply)
        self.assertIn("Citizen CX-02", reply)
        self.assertIn("Citizen CY-02", reply)
        # Does not echo the raw query sentence
        self.assertNotIn("Do you sell the Citizen SuperPhotomaster 10000?", reply)

    def test_unknown_epson_model(self):
        """Inputs like 'Do you carry the Epson SuperPrint 5000?' state model is not in catalogue and recommend Epson options."""
        state = ConversationState(session_id=f"{self.session_id}-unk2")
        res = orchestrator.process_turn("Do you carry the Epson SuperPrint 5000?", state=state)
        reply = res.get("reply", "")
        self.assertIn("Superprint 5000", reply)
        self.assertIn("not in our authorized catalogue", reply)
        self.assertIn("SC-T3100", reply)
        self.assertIn("SC-P700", reply)

    # ── 4. Model Alias Matching at Match Time ─────────────────────────────

    def test_model_alias_matching_variants(self):
        """SC-P700, P700, sc p700, surecolor p700 all resolve to epson-sc-p700."""
        queries = [
            "Tell me about the SC-P700",
            "What are the specs of P700?",
            "Can I buy the sc p700?",
            "Tell me about SureColor P700",
            "Do you have the SC P700 in stock?",
        ]
        for q in queries:
            matched = find_mentioned_catalogue_products(q)
            self.assertTrue(len(matched) >= 1, f"Expected match for query: '{q}'")
            matched_ids = [m["id"] for m in matched]
            self.assertIn("epson-sc-p700", matched_ids, f"epson-sc-p700 not found for: '{q}'")

    # ── 5. Template Variety ───────────────────────────────────────────────

    def test_opener_template_rotation(self):
        """Category openers rotate through 4 variants and never repeat consecutively in a session."""
        state = ConversationState(session_id=f"{self.session_id}-opener")
        openers = []
        for _ in range(len(OPENER_TEMPLATES) * 2):
            op = format_rotating_opener("A4 colour printers", state)
            openers.append(op)

        # Check consecutive pairs are never equal
        for i in range(len(openers) - 1):
            self.assertNotEqual(openers[i], openers[i + 1])

        # Check all templates are used
        unique_openers = set(openers)
        self.assertEqual(len(unique_openers), len(OPENER_TEMPLATES))

    def test_pricing_redirect_rotation_and_sales_rep_offer(self):
        """Pricing redirects rotate, never repeat consecutively, and offer connection to a sales representative."""
        state = ConversationState(session_id=f"{self.session_id}-pricing")
        redirects = []
        for _ in range(len(PRICING_REDIRECT_TEMPLATES) * 2):
            red = format_rotating_pricing_redirect(state)
            redirects.append(red)
            # Must offer sales representative connection
            self.assertTrue(
                "sales" in red.lower() and ("representative" in red.lower() or "specialist" in red.lower() or "team" in red.lower()),
                f"Sales representative offer missing from: {red}"
            )
            # Must reference official website
            self.assertIn("https://www.keplertechllc.com/", red)

        # Check consecutive pairs are never equal
        for i in range(len(redirects) - 1):
            self.assertNotEqual(redirects[i], redirects[i + 1])

    # ── 6. Consumables Formatting ─────────────────────────────────────────

    def test_consumables_strict_sku_and_url_format(self):
        """Every rendered consumable bullet must contain markdown link and SKU, and missing ones omitted."""
        state = ConversationState(session_id=f"{self.session_id}-cons")
        # Inquire about consumables for SC-T3100
        res = orchestrator.process_turn("What ink cartridges are compatible with the SC-T3100?", state=state)
        reply = res.get("reply", "")
        lines = [line.strip() for line in reply.split("\n") if line.strip().startswith("•")]
        self.assertTrue(len(lines) > 0, "Expected consumable bullet lines in response")
        for line in lines:
            # Must contain markdown link: [title](url)
            self.assertRegex(line, r"\[.+?\]\(https?://.+?\)", f"Missing markdown link in consumable line: {line}")
            # Must contain SKU: (SKU: ...)
            self.assertIn("SKU:", line, f"Missing SKU in consumable line: {line}")


if __name__ == "__main__":
    unittest.main()
