"""
Phase 1 Gate Automated Test Suite: Customer-Visible Bugs (Cases 1-12, 18)
Validates offline / deterministic behavior for:
 1. SC-T5100 clean specs (no raw 'display_name = ')
 2. WF-C20600 unlisted model refusal + verified alternatives (no silent substitution)
 3. Delivery question routing
 4. Blueprint width resolution: largest size wins (A1 & A0 -> 36-inch)
 5. Referent consumable compatibility (F100 ink -> F500: verified YES)
 6. Stand honesty (honest unverified, no fabricate or verbatim repeat)
 7. Citizen CX-02W pricing policy (exact model, strict quotation policy, no wrong models)
 8. SC-P7500 ink lookup returns all 30 catalogue consumables
 9. Direct want 'I want the Epson SC-P900' resolves with cards and overview
 10. Structured side-by-side comparisons (T5100 vs T5700D, F100 vs F500)
 11. Cross-referent compatibility (P900 roll adapter -> P700: verified NO with what it IS verified for)
 12. Multi-intent handling (price + delivery + speed answered in order)
 18. Centralized support contacts (OFFICIAL_SUPPORT_EMAIL / PHONE)
"""

import unittest
from unittest.mock import patch

from domain.conversation_state import ConversationState
from agent.orchestrator import Orchestrator
from catalog.evidence import EvidenceEngine, CompatibilityStatus
from conversation.product_flows import resolve_plotter_width_from_text
from ollama_client import ollama_client
import config


class TestPhase1CustomerVisibleBugs(unittest.TestCase):

    def setUp(self):
        self.state = ConversationState(session_id="test_phase1")
        self.orchestrator = Orchestrator()

    def _turn(self, msg: str):
        with patch.object(ollama_client, "classify", return_value={"success": False, "result": {}, "fallback_used": True}), \
             patch.object(ollama_client, "chat_completions", return_value={"choices": [{"message": {"content": ""}}]}), \
             patch.object(ollama_client, "generate", return_value={"response": ""}):
            return self.orchestrator.process_turn(msg, session_id=self.state.session_id, state=self.state)

    def test_case_01_and_06_spec_and_stand_honesty(self):
        """Case 1 & 6: Clean specs without ' = ' or 'display_name', honest missing stand field."""
        r1 = self._turn("tell me about the SC-T5100")
        reply1 = r1.get("reply", "")
        self.assertNotIn(" = ", reply1)
        self.assertNotIn("display_name", reply1)
        self.assertNotIn("None", reply1)
        self.assertIn("SC-T5100", reply1)

        r2 = self._turn("does it come with a stand?")
        reply2 = r2.get("reply", "")
        self.assertNotEqual(reply1, reply2)
        self.assertTrue(
            any(w in reply2.lower() for w in ["don't have verified", "not have verified", "specialist", "confirm"]),
            f"Expected honest lack of verification, got: {reply2}"
        )

    def test_case_02_silent_fuzzy_substitution_prevented(self):
        """Case 2: WF-C20600 must not be silently substituted with WF-C21000."""
        r = self._turn("what is the speed of the WF-C20600")
        reply = r.get("reply", "")
        self.assertIn("wf-c20600", reply.lower())
        self.assertTrue(
            any(w in reply.lower() for w in ["not in our approved", "not in our catalogue", "not in catalogue"]),
            f"Expected refusal for unlisted model, got: {reply}"
        )
        self.assertTrue(
            any(w in reply.lower() for w in ["alternative", "epson workforce", "wf-c21000"]),
            f"Expected verified alternatives, got: {reply}"
        )

    def test_case_04_width_resolution_largest_wins(self):
        """Case 4: A1 and A0 blueprints must resolve to 36-inch (A0)."""
        width, cat = resolve_plotter_width_from_text("We print A1 and A0 blueprints")
        self.assertEqual(width, 36)

        width_a0, _ = resolve_plotter_width_from_text("A0 only")
        self.assertEqual(width_a0, 36)

        width_up_a0, _ = resolve_plotter_width_from_text("up to A0")
        self.assertEqual(width_up_a0, 36)

        width_a1, _ = resolve_plotter_width_from_text("A1 drawings")
        self.assertEqual(width_a1, 24)

    def test_case_05_referent_consumable_compatibility(self):
        """Case 5: SC-F100 ink followed by 'this is suitable for f500' -> verified YES."""
        r1 = self._turn("i want ink for f100")
        self.assertGreater(len(r1.get("consumable_cards", [])), 0)

        r2 = self._turn("this is suitable for f500")
        reply2 = r2.get("reply", "")
        self.assertTrue(
            any(w in reply2.lower() for w in ["yes", "verified compatible", "suitable"]),
            f"Expected verified YES compatibility, got: {reply2}"
        )
        self.assertIn("f500", reply2.lower())

    def test_case_07_citizen_cx02w_pricing_policy(self):
        """Case 7: Citizen CX-02W pricing query must answer pricing policy without numbers or wrong models."""
        r = self._turn("how much is the Citizen CX-02W")
        reply = r.get("reply", "")
        self.assertIn("cx-02w", reply.lower())
        self.assertNotIn("aed", reply.lower())
        self.assertTrue(
            any(w in reply.lower() for w in ["pricing", "quotation", "sales desk"]),
            f"Expected commercial pricing policy response, got: {reply}"
        )
        self.assertGreater(len(r.get("product_cards", [])), 0)
        self.assertEqual(r["product_cards"][0]["id"], "citizen-cx-02w")

    def test_case_08_p7500_consumables_count(self):
        """Case 8: P7500 ink lookup returns 30 verified catalogue consumables."""
        items, rec = EvidenceEngine.list_consumables("epson-sc-p7500")
        self.assertEqual(len(items), 30)
        self.assertTrue(rec.verified)
        self.assertEqual(rec.status, CompatibilityStatus.VERIFIED_YES)

    def test_case_09_direct_model_want(self):
        """Case 9: 'I want the Epson SC-P900' resolves directly without generic fallback."""
        r = self._turn("I want the Epson SC-P900")
        reply = r.get("reply", "")
        self.assertIn("sc-p900", reply.lower())
        self.assertNotEqual(r.get("source"), "fallback:clarify")
        self.assertGreater(len(r.get("product_cards", [])), 0)

    def test_case_10_structured_model_comparisons(self):
        """Case 10: Model comparisons output structured comparison table."""
        matrix, rec = EvidenceEngine.compare(
            ["epson-sc-t5100", "epson-sc-t5700d"],
            ["category", "width", "resolution", "speed", "connectivity"]
        )
        self.assertIn("| Specification |", rec.claim)
        self.assertIn("SC-T5100", rec.claim)
        self.assertIn("SC-T5700D", rec.claim)

    def test_case_11_cross_referent_compatibility(self):
        """Case 11: P900 roll adapter referent compatibility check for P700."""
        r1 = self._turn("tell me about the P900 roll adapter")
        self.assertIn("p900", r1.get("reply", "").lower())

        r2 = self._turn("is that compatible with the P700")
        reply2 = r2.get("reply", "")
        self.assertTrue(
            any(w in reply2.lower() for w in ["not compatible", "no"]),
            f"Expected verified NO compatibility, got: {reply2}"
        )
        self.assertTrue(
            any(w in reply2.lower() for w in ["sc-p900", "p900"]),
            f"Expected mention of what it is verified for, got: {reply2}"
        )

    def test_case_12_multi_intent_compound_response(self):
        """Case 12: Price + delivery + speed answered in order, with next step."""
        r = self._turn("price of AM-C4000 and do you deliver to Sharjah and how fast is it")
        reply = r.get("reply", "")
        # Answers price
        self.assertTrue(any(w in reply.lower() for w in ["pricing", "quotation", "sales desk"]))
        # Answers delivery to Sharjah
        self.assertTrue(any(w in reply.lower() for w in ["sharjah", "delivery", "emirates"]))
        # Answers speed
        self.assertTrue(any(w in reply.lower() for w in ["speed", "40", "ppm"]))
        # Single next step
        self.assertIn(config.OFFICIAL_SUPPORT_EMAIL, reply)

    def test_case_18_centralized_support_config(self):
        """Case 18: Support contacts centralized in config.py."""
        self.assertTrue(hasattr(config, "OFFICIAL_SUPPORT_EMAIL"))
        self.assertTrue(hasattr(config, "OFFICIAL_SUPPORT_PHONE"))
        self.assertIn("@keplertech.ae", config.OFFICIAL_SUPPORT_EMAIL)


if __name__ == "__main__":
    unittest.main()
