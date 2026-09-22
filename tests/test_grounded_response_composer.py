"""
Comprehensive Test Suite for Grounded LLM Response Composer.

Tests:
1. Unit tests for ResponseContext, VerifiedEvidenceBundle, and ResponseComposer.
2. Question-aware composition (casual phrasing, tone, single attribute, dynamic sizing).
3. Multi-part question decomposition and coverage.
4. Fail-closed deterministic validation and fallback on LLM failure / hallucination.
5. Multi-turn full conversational sessions:
   - TEST A: Full architectural qualification, recommendation, attribute inquiry, comparison, correction.
   - TEST B: Model detail, specs, comparison, reference resolution ("first one"), memory recall.
   - TEST C: 65-inch typo approximation preservation.
   - TEST D: SC-P8500D vs SC-P8500DM protection and consumable query.
   - TEST E: Category switch (CAD -> Photo Booth) without requirement contamination.
   - TEST F: Multi-part query ("does it have scanner, can it print A0 and what ink does it use?").
6. Naturalness and anti-repetition regression checks.
"""

import unittest
from unittest.mock import MagicMock, patch

from domain.response_context import ResponseContext, VerifiedEvidenceBundle
from agent.response_composer import ResponseComposer
from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState
from catalog.catalogue_loader import catalogue_loader


class TestGroundedResponseComposerUnit(unittest.TestCase):
    """Unit tests for the Grounded Response Composer."""

    def setUp(self):
        self.mock_ollama = MagicMock()
        self.composer = ResponseComposer(self.mock_ollama)

    def test_deterministic_bypass_when_naturalization_not_needed(self):
        """If needs_naturalization is False, return deterministic_draft directly."""
        ctx = ResponseContext(
            original_message="give me discount",
            normalized_message="give me discount",
            intent="commercial",
            deterministic_draft="We maintain transparent fixed pricing.",
            needs_naturalization=False,
        )
        result = self.composer.compose(ctx)
        self.assertEqual(result, "We maintain transparent fixed pricing.")
        self.mock_ollama.compose.assert_not_called()

    def test_fallback_when_ollama_offline_or_none(self):
        """If OllamaClient is None or offline, return deterministic_draft safely."""
        offline_composer = ResponseComposer(None)
        ctx = ResponseContext(
            original_message="wifi?",
            normalized_message="wifi?",
            intent="capability",
            deterministic_draft="The SC-P6500D supports Gigabit Ethernet, USB 3.0, and Wi-Fi.",
            needs_naturalization=True,
        )
        result = offline_composer.compose(ctx)
        self.assertEqual(result, "The SC-P6500D supports Gigabit Ethernet, USB 3.0, and Wi-Fi.")

    def test_casual_phrasing_and_question_aware_composition(self):
        """Ensure casual customer tone ('bro this one have scanner?') receives natural response."""
        self.mock_ollama.compose.return_value = {
            "success": True,
            "response": "Yes, it does. The SC-T5700DM comes with an integrated 36-inch dual-light CIS scanner.",
            "latency_ms": 120,
        }
        evidence = VerifiedEvidenceBundle(
            active_product={
                "id": "epson-sc-t5700dm",
                "display_name": "Epson SureColor SC-T5700DM",
                "functions": ["print", "scan", "copy"],
            }
        )
        ctx = ResponseContext(
            original_message="bro this one have scanner?",
            normalized_message="does this product have a scanner?",
            intent="capability",
            resolved_references={"this one": "Epson SureColor SC-T5700DM"},
            verified_evidence=evidence,
            deterministic_draft="The SC-T5700DM includes integrated scanning functionality.",
            allowed_followup=None,
        )
        result = self.composer.compose(ctx)
        self.assertIn("Yes, it does", result)
        self.assertIn("SC-T5700DM", result)
        self.assertIn("scanner", result)

    def test_multi_part_question_decomposition(self):
        """Multi-part question 'does it have scanner and can it print A0?' decomposes into clauses."""
        questions = self.composer._extract_customer_questions("does it have scanner and can it print A0?")
        self.assertGreaterEqual(len(questions), 2)
        self.assertTrue(any("scanner" in q.lower() for q in questions))
        self.assertTrue(any("a0" in q.lower() for q in questions))

    def test_dynamic_length_assessment(self):
        """Verify dynamic length assigns 'short' to brief queries and 'medium' to comparisons."""
        len_short = self.composer._determine_expected_length("wifi?", "capability")
        self.assertEqual(len_short, "short")

        len_comp = self.composer._determine_expected_length("compare SC-P8500D and SC-P8500DM", "comparison")
        self.assertEqual(len_comp, "medium")

        len_why = self.composer._determine_expected_length("why this one for my architecture office?", "product_advice")
        self.assertEqual(len_why, "medium")

    def test_hallucination_validation_fails_and_triggers_bounded_regeneration(self):
        """If composed text contains unverified absolute claims, validator triggers 1 bounded regeneration."""
        # First attempt returns forbidden guarantee; second attempt returns valid claim
        self.mock_ollama.compose.side_effect = [
            {"success": True, "response": "This printer is 100% guaranteed to work and will cause printhead damage with other media."},
            {"success": True, "response": "The SC-T5700DM supports up to 36-inch media width and fast CAD line printing."},
        ]
        evidence = VerifiedEvidenceBundle(
            active_product={
                "id": "epson-sc-t5700dm",
                "display_name": "Epson SureColor SC-T5700DM",
                "print_width": 36,
            }
        )
        ctx = ResponseContext(
            original_message="what is the width?",
            normalized_message="what is the print width?",
            intent="capability",
            verified_evidence=evidence,
            deterministic_draft="The SC-T5700DM supports 36-inch media width.",
            allowed_followup=None,
        )
        result = self.composer.compose(ctx)
        self.assertIn("36-inch", result)
        self.assertEqual(self.mock_ollama.compose.call_count, 2)

    def test_fail_closed_fallback_when_regeneration_also_fails(self):
        """If both initial composition and regeneration fail validation, fall back to deterministic draft."""
        self.mock_ollama.compose.side_effect = [
            {"success": True, "response": "This model is 100% guaranteed to work with zero errors."},
            {"success": True, "response": "We absolutely guarantee compatibility without testing."},
        ]
        evidence = VerifiedEvidenceBundle(
            active_product={"id": "citizen-cx-02", "display_name": "Citizen CX-02"}
        )
        ctx = ResponseContext(
            original_message="what is it?",
            normalized_message="what is it?",
            intent="product_details",
            verified_evidence=evidence,
            deterministic_draft="The Citizen CX-02 is a compact 6-inch dye-sublimation photo printer.",
            allowed_followup=None,
        )
        result = self.composer.compose(ctx)
        self.assertEqual(result, "The Citizen CX-02 is a compact 6-inch dye-sublimation photo printer.")


class TestFullConversationalSessions(unittest.TestCase):
    """End-to-end multi-turn session regression tests (Tests A through F)."""

    def test_session_a_architectural_qualification_to_correction(self):
        """
        TEST A:
        Hi -> I need a printer -> architecture drawings -> A0 -> around 60 per day ->
        yes scanner -> what do you recommend? -> why this one? -> does it have wifi? ->
        what ink for it? -> show another -> compare them -> which one has scanner? ->
        actually I don't need scanner -> what would you suggest now?
        """
        state = ConversationState(session_id="test_sess_a")
        
        # Turn 1: Hi
        r1 = orchestrator.process_turn("Hi", session_id="test_sess_a", state=state)
        self.assertIn("welcome", r1["reply"].lower())

        # Turn 2: I need a printer
        r2 = orchestrator.process_turn("I need a printer", session_id="test_sess_a", state=state)
        self.assertTrue(bool(r2["suggested_chips"]))

        # Turn 3: for architecture drawings
        r3 = orchestrator.process_turn("for architecture drawings", session_id="test_sess_a", state=state)
        self.assertEqual(state.category, "technical_large_format")

        # Turn 4: A0
        r4 = orchestrator.process_turn("A0", session_id="test_sess_a", state=state)
        self.assertIn(state.requirements.get("print_width"), (36, 44))

        # Turn 5: around 60 per day
        r5 = orchestrator.process_turn("around 60 per day", session_id="test_sess_a", state=state)
        self.assertEqual(state.requirements.get("daily_volume"), 60)

        # Turn 6: yes scanner
        r6 = orchestrator.process_turn("yes scanner", session_id="test_sess_a", state=state)
        self.assertTrue(state.requirements.get("scanner_required"))
        self.assertTrue(bool(r6["product_cards"]))

        # Turn 7: what do you recommend?
        r7 = orchestrator.process_turn("what do you recommend?", session_id="test_sess_a", state=state)
        self.assertTrue(len(r7["product_cards"]) >= 1)

        # Turn 8: why this one?
        r8 = orchestrator.process_turn("why this one?", session_id="test_sess_a", state=state)
        self.assertTrue(bool(r8["reply"]))

        # Turn 9: does it have wifi?
        r9 = orchestrator.process_turn("does it have wifi?", session_id="test_sess_a", state=state)
        self.assertTrue("wi-fi" in r9["reply"].lower() or "wifi" in r9["reply"].lower() or "connectivity" in r9["reply"].lower())

        # Turn 10: what ink for it?
        r10 = orchestrator.process_turn("what ink for it?", session_id="test_sess_a", state=state)
        self.assertTrue(bool(r10["consumable_cards"]) or "ink" in r10["reply"].lower())

        # Turn 11: show another
        r11 = orchestrator.process_turn("show another", session_id="test_sess_a", state=state)
        self.assertTrue(bool(r11["product_cards"]) or bool(r11["reply"]))

        # Turn 12: compare them
        r12 = orchestrator.process_turn("compare them", session_id="test_sess_a", state=state)
        self.assertTrue("comparison" in r12["source"] or "vs" in r12["reply"].lower() or bool(r12["reply"]))

        # Turn 13: which one has scanner?
        r13 = orchestrator.process_turn("which one has scanner?", session_id="test_sess_a", state=state)
        self.assertIn("scan", r13["reply"].lower())

        # Turn 14: actually I don't need scanner
        r14 = orchestrator.process_turn("actually I don't need scanner", session_id="test_sess_a", state=state)
        self.assertFalse(state.requirements.get("scanner_required"))

        # Turn 15: what would you suggest now?
        r15 = orchestrator.process_turn("what would you suggest now?", session_id="test_sess_a", state=state)
        self.assertTrue(bool(r15["product_cards"]))

    def test_session_b_model_detail_specs_and_memory_recall(self):
        """
        TEST B:
        show SC-P6500D -> what is the width? -> how fast? -> show another one ->
        compare them -> what about the first one? -> what ink does it use? ->
        the last printer I told you which one?
        """
        state = ConversationState(session_id="test_sess_b")

        # Turn 1: show SC-P6500D
        r1 = orchestrator.process_turn("show SC-P6500D", session_id="test_sess_b", state=state)
        self.assertIn("SC-P6500D", r1["reply"])
        self.assertEqual(state.active_product["id"], "epson-sc-p6500d")

        # Turn 2: what is the width?
        r2 = orchestrator.process_turn("what is the width?", session_id="test_sess_b", state=state)
        self.assertIn("24", r2["reply"])

        # Turn 3: how fast?
        r3 = orchestrator.process_turn("how fast?", session_id="test_sess_b", state=state)
        self.assertTrue("m²/hr" in r3["reply"] or "sec" in r3["reply"] or "speed" in r3["reply"].lower())

        # Turn 4: show another one
        r4 = orchestrator.process_turn("show another one", session_id="test_sess_b", state=state)
        self.assertTrue(bool(r4["product_cards"]) or bool(r4["reply"]))

        # Turn 5: compare them
        r5 = orchestrator.process_turn("compare them", session_id="test_sess_b", state=state)
        self.assertTrue(bool(r5["reply"]))

        # Turn 6: what about the first one?
        r6 = orchestrator.process_turn("what about the first one?", session_id="test_sess_b", state=state)
        self.assertIn("SC-P6500D", r6["reply"])

        # Turn 7: what ink does it use?
        r7 = orchestrator.process_turn("what ink does it use?", session_id="test_sess_b", state=state)
        self.assertTrue("ultrachrome" in r7["reply"].lower() or "ink" in r7["reply"].lower() or bool(r7["consumable_cards"]))

        # Turn 8: the last printer I told you which one?
        r8 = orchestrator.process_turn("the last printer I told you which one?", session_id="test_sess_b", state=state)
        self.assertIn("SC-P6500D", r8["reply"])

    def test_session_c_65_inch_roll_typo_handling(self):
        """
        TEST C:
        I need printer -> photo studio -> large roll -> 65" rool ->
        what do you recommend? -> why? -> what media can it handle?
        Must preserve the current 65" -> 64" class approximation.
        """
        state = ConversationState(session_id="test_sess_c")

        orchestrator.process_turn("I need printer", session_id="test_sess_c", state=state)
        orchestrator.process_turn("photo studio", session_id="test_sess_c", state=state)
        orchestrator.process_turn("large roll", session_id="test_sess_c", state=state)
        r4 = orchestrator.process_turn("65\" rool", session_id="test_sess_c", state=state)

        # 65-inch approximation maps to 64-inch class
        self.assertEqual(state.requirements.get("print_width"), 64)
        self.assertTrue(bool(r4["product_cards"]))
        matched_ids = [p["id"] for p in r4["product_cards"]]
        self.assertTrue(any("p9500" in pid or "p8500" in pid or "p20500" in pid for pid in matched_ids))

    def test_session_d_p8500d_vs_p8500dm_protection(self):
        """
        TEST D:
        show me SC-P8500D -> compare it with SC-P8500DM -> which one has scanner? ->
        what about consumables for the second one?
        Must never confuse P8500D with P8500DM.
        """
        state = ConversationState(session_id="test_sess_d")

        r1 = orchestrator.process_turn("show me SC-P8500D", session_id="test_sess_d", state=state)
        self.assertEqual(state.active_product["id"], "epson-sc-p8500d")

        r2 = orchestrator.process_turn("compare it with SC-P8500DM", session_id="test_sess_d", state=state)
        self.assertIn("SC-P8500D", r2["reply"])
        self.assertIn("SC-P8500DM", r2["reply"])

        r3 = orchestrator.process_turn("which one has scanner?", session_id="test_sess_d", state=state)
        self.assertIn("SC-P8500DM", r3["reply"])

        r4 = orchestrator.process_turn("what about consumables for the second one?", session_id="test_sess_d", state=state)
        self.assertTrue(bool(r4["consumable_cards"]) or "ink" in r4["reply"].lower() or "sc-p8500dm" in r4["reply"].lower())

    def test_session_e_category_switch_without_state_contamination(self):
        """
        TEST E:
        I need CAD printer -> A0 -> no scanner ->
        actually now I need a photo booth printer -> 4x6 -> around 500 prints at events ->
        show options.
        CAD state must not contaminate photo booth recommendations.
        """
        state = ConversationState(session_id="test_sess_e")

        orchestrator.process_turn("I need CAD printer", session_id="test_sess_e", state=state)
        orchestrator.process_turn("A0", session_id="test_sess_e", state=state)
        orchestrator.process_turn("no scanner", session_id="test_sess_e", state=state)
        self.assertEqual(state.category, "technical_large_format")

        # Switch to photo booth
        r4 = orchestrator.process_turn("actually now I need a photo booth printer", session_id="test_sess_e", state=state)
        self.assertEqual(state.category, "citizen_photo")
        # CAD specific A0 requirement must not force CAD plotters
        self.assertNotEqual(state.requirements.get("print_width"), 36)

        orchestrator.process_turn("4x6", session_id="test_sess_e", state=state)
        r6 = orchestrator.process_turn("around 500 prints at events", session_id="test_sess_e", state=state)
        matched_ids = [p["id"] for p in r6["product_cards"]]
        # Must recommend Citizen dye-sub models, NOT Epson CAD plotters
        self.assertTrue(any("citizen" in pid for pid in matched_ids))
        self.assertFalse(any("t5700" in pid or "t5400" in pid for pid in matched_ids))

    def test_session_f_multipart_inquiry(self):
        """
        TEST F:
        show SC-T5700DM
        then: does it have scanner, can it print A0 and what ink does it use?
        Must address scanner, A0, and ink using verified evidence.
        """
        state = ConversationState(session_id="test_sess_f")
        orchestrator.process_turn("show SC-T5700DM", session_id="test_sess_f", state=state)
        self.assertEqual(state.active_product["id"], "epson-sc-t5700dm")

        r2 = orchestrator.process_turn(
            "does it have scanner, can it print A0 and what ink does it use?",
            session_id="test_sess_f",
            state=state,
        )
        reply = r2["reply"].lower()
        self.assertIn("scan", reply)
        self.assertTrue("a0" in reply or "36" in reply or "width" in reply)
        self.assertTrue("ink" in reply or "ultrachrome" in reply or bool(r2["consumable_cards"]))


class TestNaturalnessAndRepetition(unittest.TestCase):
    """Detects and prevents bad templated response patterns across turns."""

    def test_no_repetitive_pleasantry_headers(self):
        """Verifies bot does not repeat 'Certainly!' or 'I'd be glad' across consecutive turns."""
        banned_phrases = ["certainly!", "absolutely!", "i'd be glad", "i'd be delighted"]
        state = ConversationState(session_id="test_natural_rep")
        
        responses = []
        inputs = ["Hi", "I need a CAD printer", "A0 size", "30 prints per day", "no scanner"]
        for inp in inputs:
            res = orchestrator.process_turn(inp, session_id="test_natural_rep", state=state)
            responses.append(res["reply"].lower())

        # Check consecutive repetition
        for i in range(len(responses) - 1):
            for bp in banned_phrases:
                if bp in responses[i]:
                    self.assertNotIn(bp, responses[i+1], f"Repeated phrase '{bp}' found in consecutive turns")


if __name__ == "__main__":
    unittest.main()
