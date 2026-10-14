"""
Test Suite for 12 Sales Behaviours Audit Fixes.
Validates:
Fix 1: Real quote / discount handoff, no duplicate sentences, no fake promises.
Fix 2: Budget as a deterministic slot.
Fix 3: Price objection clarify first, no unverified promises.
Fix 4: Grounded competitor handling.
Fix 5: Primary concern slot (problem discovery).
Fix 6: Buyer pace (concise mode), content never changes.
Fix 7: Prompt conflict (consumables rule static test).
"""

import unittest
import re
from app import app
from conversation.understanding import understand_turn, Intent, DialogueAct
from conversation.dialogue_state import DialogueState, ReferentResolver
from conversation.policy import PolicyEngine, PolicyAction
from conversation.response_plan import ResponsePlanBuilder
from agent.orchestrator import orchestrator


def _has_repeated_sentences(text: str) -> bool:
    """Checks whether any complete sentence (> 15 chars) appears more than once."""
    seen = set()
    paras = text.split("\n\n")
    for para in paras:
        for line in para.split("\n"):
            line = line.strip()
            if not line or line.startswith(("•", "-", "*", "#")):
                continue
            sents = re.split(r"(?<=[.!?])\s+", line)
            for s in sents:
                clean = re.sub(r"[^a-zA-Z0-9]", "", s).lower()
                if len(clean) > 20:
                    if clean in seen:
                        return True
                    seen.add(clean)
    return False


class TestAuditSalesBehavioursFix1(unittest.TestCase):
    """FIX 1: Real quote / discount handoff."""

    def setUp(self):
        self.client = app.test_client()

    def test_discount_request_sets_handover_and_no_fake_confirmation(self):
        """Discount request sets handover flag and contains no 'applied/confirmed'."""
        state = DialogueState(session_id="test-discount-1")
        turn = understand_turn("Can you give me 20% discount?")
        self.assertEqual(turn.intent, Intent.DISCOUNT_REQUEST)

        resolved = ReferentResolver.resolve_turn(turn, state)
        decision = PolicyEngine.decide(resolved, state)
        plan = ResponsePlanBuilder.build(decision, resolved, state)

        self.assertTrue(state.handover_triggered)
        self.assertEqual(state.handover_reason, "discount_request")
        reply = plan.formatted_reply.lower()

        # Must NOT claim applied or confirmed
        for forbidden in ["discount applied", "discount confirmed", "we applied", "quote confirmed", "callback scheduled"]:
            self.assertNotIn(forbidden, reply)

        # Must state plainly that discounts are handled by sales team
        self.assertTrue(
            "sales" in reply and ("cannot approve" in reply or "cannot confirm" in reply or "sales team" in reply),
            f"Expected bot limitation in reply, got: {plan.formatted_reply}"
        )
        self.assertFalse(_has_repeated_sentences(plan.formatted_reply), f"Duplicate sentence found in: {plan.formatted_reply}")

    def test_quote_for_5_units_custom_setup(self):
        """'Send me a quotation for 5 units with custom setup' mentions 5 units and sets handover."""
        state = DialogueState(session_id="test-quote-5u")
        turn = understand_turn("Send me a quotation for 5 units with custom setup")
        self.assertIn(turn.intent, (Intent.QUOTE_REQUEST, Intent.CUSTOM_CONFIG_REQUEST))
        self.assertIn("quote_quantity", turn.slots)
        self.assertEqual(turn.slots["quote_quantity"].value, 5)

        resolved = ReferentResolver.resolve_turn(turn, state)
        decision = PolicyEngine.decide(resolved, state)
        plan = ResponsePlanBuilder.build(decision, resolved, state)

        self.assertTrue(state.handover_triggered)
        self.assertIn(state.handover_reason, ("quote_request", "custom_configuration"))
        self.assertIn("5 units", plan.formatted_reply)
        self.assertFalse(_has_repeated_sentences(plan.formatted_reply), f"Duplicate sentence found in: {plan.formatted_reply}")

    def test_price_with_no_context_returns_clarify_zero_prices(self):
        """'price?' with no context returns a clarify action with zero prices."""
        state = DialogueState(session_id="test-price-no-ctx")
        turn = understand_turn("price?")
        resolved = ReferentResolver.resolve_turn(turn, state)
        decision = PolicyEngine.decide(resolved, state)
        plan = ResponsePlanBuilder.build(decision, resolved, state)

        self.assertEqual(decision.action, PolicyAction.CLARIFY)
        self.assertIn("Which model or application", plan.formatted_reply)
        self.assertEqual(len(plan.product_cards), 0)
        self.assertFalse(re.search(r"\bAED\s*[\d,]+", plan.formatted_reply), f"Found prices in clarify reply: {plan.formatted_reply}")
        self.assertFalse(_has_repeated_sentences(plan.formatted_reply), f"Duplicate sentence found in: {plan.formatted_reply}")

    def test_live_api_chat_discount_handover(self):
        """End-to-end /api/chat discount request returns handover_triggered."""
        res = self.client.post("/api/chat", json={
            "session_id": "test-live-disc-api",
            "message": "Can you give me 20% discount on 3 printers?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("handover_triggered"))
        self.assertEqual(data.get("handover_reason"), "discount_request")
        self.assertFalse(_has_repeated_sentences(data.get("reply", "")))
