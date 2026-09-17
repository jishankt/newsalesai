"""
Comprehensive unit test suite for ContextualSlotResolver and Conversation Loop Guard.
Tests ordinal references, affirmative/negative parsing, bare number slots,
descriptive tiers, relaxation transitions, and multi-turn anti-loop guards.
"""

import unittest
from conversation.contextual_slot_resolver import ContextualSlotResolver
from domain.conversation_state import ConversationState
from agent.orchestrator import Orchestrator


class TestContextualSlotResolver(unittest.TestCase):

    def test_ordinal_references_against_chips(self):
        """Tests 'first', 'second', '1', '2' mapping to chip text."""
        chips = ["Compact (Desktop / Portable)", "Large Format (24″ to 64″)"]
        
        # Test "1st" or "first"
        reqs1, _ = ContextualSlotResolver.resolve(
            text="the first one",
            awaiting_field="photo_form_factor",
            active_chips=chips
        )
        self.assertEqual(reqs1.get("photo_form_factor"), "compact")

        # Test "2" or "option 2"
        reqs2, _ = ContextualSlotResolver.resolve(
            text="option 2",
            awaiting_field="photo_form_factor",
            active_chips=chips
        )
        self.assertEqual(reqs2.get("photo_form_factor"), "large")

        # Test bare number "1"
        reqs3, _ = ContextualSlotResolver.resolve(
            text="1",
            awaiting_field="photo_form_factor",
            active_chips=chips
        )
        self.assertEqual(reqs3.get("photo_form_factor"), "compact")

    def test_binary_scanner_resolution(self):
        """Tests affirmative and negative conversational replies for scanner_required."""
        # Affirmative replies
        for aff in ["yes", "yeah", "yep", "sure", "definitely", "with scanner", "scanner", "scan", "mfp", "copier"]:
            reqs, _ = ContextualSlotResolver.resolve(text=aff, awaiting_field="scanner_required")
            self.assertIs(reqs.get("scanner_required"), True, f"Failed for '{aff}'")
            self.assertEqual(reqs.get("functions"), ["print", "scan", "copy"])

        # Negative replies
        for neg in ["no", "nope", "nah", "print only", "printer only", "without scanner", "just print", "no scanner"]:
            reqs, _ = ContextualSlotResolver.resolve(text=neg, awaiting_field="scanner_required")
            self.assertIs(reqs.get("scanner_required"), False, f"Failed for '{neg}'")
            self.assertEqual(reqs.get("functions"), ["print"])

    def test_print_width_resolution(self):
        """Tests bare numbers and format codes for print width."""
        widths = {
            "24": 24,
            "36": 36,
            "44": 44,
            "13": 13,
            "17": 17,
            "a1": 24,
            "a0": 36,
            "24-inch": 24,
            "36\"": 36,
        }
        for token, expected_w in widths.items():
            reqs, _ = ContextualSlotResolver.resolve(text=token, awaiting_field="print_width")
            self.assertEqual(reqs.get("print_width"), expected_w, f"Failed for '{token}'")

    def test_daily_volume_descriptors_and_ranges(self):
        """Tests descriptive volume tiers ('low', 'medium', 'high') and range strings."""
        reqs_low, _ = ContextualSlotResolver.resolve(text="low volume", awaiting_field="daily_volume")
        self.assertEqual(reqs_low.get("daily_volume"), 30)

        reqs_med, _ = ContextualSlotResolver.resolve(text="medium", awaiting_field="daily_volume")
        self.assertEqual(reqs_med.get("daily_volume"), 120)

        reqs_high, _ = ContextualSlotResolver.resolve(text="high volume", awaiting_field="daily_volume")
        self.assertEqual(reqs_high.get("daily_volume"), 350)

        reqs_range, _ = ContextualSlotResolver.resolve(text="100 to 200 pages", awaiting_field="daily_volume")
        self.assertEqual(reqs_range.get("daily_volume"), 150)

    def test_sublimation_paper_size_resolution(self):
        """Tests format and application resolving in dye sublimation flow."""
        # A4 Desktop / SC-F100
        for token in ["a4", "desktop", "mugs", "sc-f100", "small gifts"]:
            reqs, _ = ContextualSlotResolver.resolve(text=token, awaiting_field="paper_size", category="dye_sublimation")
            self.assertEqual(reqs.get("paper_size"), "a4")
            self.assertEqual(reqs.get("model"), "epson-sc-f100")

        # 24-inch Roll / SC-F500
        for token in ["24", "roll", "t-shirts", "apparel", "sportswear", "sc-f500"]:
            reqs, _ = ContextualSlotResolver.resolve(text=token, awaiting_field="paper_size", category="dye_sublimation")
            self.assertEqual(reqs.get("print_width"), 24)
            self.assertEqual(reqs.get("model"), "epson-sc-f500")

    def test_relaxation_transition_resolution(self):
        """Tests relaxation question transition logic."""
        reqs_current = {"print_width": 24, "scanner_required": True}
        
        # User agrees to 36-inch multifunction
        reqs_agree, corrs_agree = ContextualSlotResolver.resolve(
            text="yes that works",
            awaiting_field="relaxation",
            requirements=reqs_current
        )
        self.assertEqual(reqs_agree.get("print_width"), 36)
        self.assertIs(reqs_agree.get("scanner_required"), True)

        # User chooses 24-inch print-only
        reqs_decl, _ = ContextualSlotResolver.resolve(
            text="no I want 24 print only",
            awaiting_field="relaxation",
            requirements=reqs_current
        )
        self.assertIs(reqs_decl.get("scanner_required"), False)


class TestConversationLoopPrevention(unittest.TestCase):

    def setUp(self):
        self.orchestrator = Orchestrator()

    def test_loop_prevention_on_unresolved_answers(self):
        """Tests that 1 unresolved turn clarifies, and 2 unresolved turns breaks loop with products."""
        state = ConversationState(session_id="loop-test-1")

        # Turn 1: Start CAD flow -> prompts for width
        r1 = self.orchestrator.process_turn("I need a CAD printer", state=state)
        self.assertEqual(state.awaiting_field, "print_width")

        # Turn 2: Send ambiguous response once
        r2 = self.orchestrator.process_turn("something good", state=state)
        # Verify Turn 1 clarification instead of verbatim question
        self.assertEqual(state.awaiting_field, "print_width")
        self.assertEqual(state.unresolved_field_turns, 1)
        self.assertIn("confirm", r2.get("reply", "").lower())
        self.assertTrue(len(r2.get("suggested_chips", [])) > 0)

        # Turn 3: Send ambiguous response a second time -> BREAK LOOP!
        r3 = self.orchestrator.process_turn("just whatever", state=state)
        self.assertIsNone(state.awaiting_field)
        self.assertTrue(state.qualification_complete)
        self.assertTrue(len(r3.get("product_cards", [])) > 0)
        card_ids = [c["id"] for c in r3.get("product_cards", [])]
        self.assertIn("epson-sc-t3100", card_ids)


if __name__ == "__main__":
    unittest.main()
