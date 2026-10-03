"""
Evaluation Suite for Kepler Tech Conversational Recommendation Engine.
Tests:
  1. Requirement Collection (Single-question flow, CAD, Office, Scanners)
  2. Requirement Corrections ('Actually A0', 'No scanner')
  3. Anti-Hallucination & Unknowns ('What is the resolution when unverified')
  4. Fake / Non-existent product queries
  5. Contradiction & Eligibility Filtering (Scanner required vs print-only)
  6. Conversational interruptions & context persistence
"""
import unittest
from domain.conversation_state import ConversationState
from conversation.next_question_engine import NextQuestionEngine
from conversation.requirement_extractor import requirement_extractor
from recommendation.eligibility import eligibility_engine
from recommendation.ranker import product_ranker
from catalog.repository import catalog_repository
from catalog.product_resolver import resolve_canonical_id
from validation.claim_validator import output_validator


class TestGroundedRecommendationEngine(unittest.TestCase):

    def setUp(self):
        self.state = ConversationState(session_id="eval-test-01")
        self.next_q = NextQuestionEngine()
        self.repo = catalog_repository

    def test_01_cad_single_question_flow(self):
        """Test multi-turn requirement collection asks one question at a time."""
        self.state.category = "technical_cad"
        
        # Turn 1: No size known -> Ask size
        step1 = self.next_q.evaluate_next_step(self.state)
        self.assertIsNotNone(step1)
        self.assertEqual(step1["field"], "print_size")
        self.assertIn("maximum", step1["question"].lower())

        # Customer answers: A0
        extracted = requirement_extractor.extract_and_validate("A0", self.state)
        self.state.requirements.update(extracted)
        self.assertEqual(self.state.requirements.get("print_size"), "A0")

        # Turn 2: Size known -> Ask scanner
        step2 = self.next_q.evaluate_next_step(self.state)
        self.assertIsNotNone(step2)
        self.assertEqual(step2["field"], "scan_required")

        # Customer answers: No scanner
        extracted = requirement_extractor.extract_and_validate("Print only, no scanner needed", self.state)
        self.state.requirements.update(extracted)
        self.assertEqual(self.state.requirements.get("scan_required"), False)

        # Turn 3: Size & Scanner known -> Ask daily volume
        step3 = self.next_q.evaluate_next_step(self.state)
        self.assertIsNotNone(step3)
        self.assertEqual(step3["field"], "daily_volume")

        # Customer answers: 20 drawings per day
        extracted = requirement_extractor.extract_and_validate("About 20 drawings per day", self.state)
        self.state.requirements.update(extracted)
        self.assertEqual(self.state.requirements.get("daily_volume"), "medium")

        # Turn 4: All critical and important satisfied -> None (ready for recommendation)
        step4 = self.next_q.evaluate_next_step(self.state)
        self.assertIsNone(step4)

    def test_02_requirement_corrections(self):
        """Test user correcting an earlier requirement."""
        self.state.category = "technical_cad"
        self.state.requirements = {"print_size": "A1", "scan_required": False}

        # Customer corrects to A0
        extracted = requirement_extractor.extract_and_validate("Actually I need A0", self.state)
        self.state.requirements.update(extracted)
        self.assertEqual(self.state.requirements["print_size"], "A0")

    def test_03_exact_product_resolution(self):
        """Test SKU / model name normalization."""
        self.assertEqual(resolve_canonical_id("SC-T5400M"), "epson-t5400m")
        self.assertEqual(resolve_canonical_id("Epson T5400"), "epson-t5400m")
        self.assertEqual(resolve_canonical_id("T3100"), "epson-t3100")
        self.assertEqual(resolve_canonical_id("Citizen CX-02"), "citizen-cx-02")
        self.assertEqual(resolve_canonical_id("Citizen CX-02W"), "citizen-cx-02w")
        self.assertIsNone(resolve_canonical_id("Citizen CX-02S"))
        self.assertIsNone(resolve_canonical_id("CX-02-S"))
        self.assertIsNone(resolve_canonical_id("SC-T3100X"))
        self.assertIsNone(resolve_canonical_id("Epson ABC-99999"))

    def test_04_hard_eligibility_contradiction_gate(self):
        """Test scanner requirement strictly excludes print-only plotters."""
        t5700d = self.repo.get_by_id("epson-t5700d")  # A0, Print-only (has_scanner = False)
        t5400m = self.repo.get_by_id("epson-t5400m")  # A0, Integrated scanner (has_scanner = True)

        # Customer requires A0 + Scanner
        reqs = {"print_size": "A0", "scan_required": True}
        res_t5700d = eligibility_engine.assess_product(t5700d, reqs)
        res_t5400m = eligibility_engine.assess_product(t5400m, reqs)

        # T5700D must FAIL eligibility
        self.assertFalse(res_t5700d.is_eligible)
        self.assertIn("scan_required", res_t5700d.failed)

        # T5400M must PASS eligibility
        self.assertTrue(res_t5400m.is_eligible)
        self.assertIn("scan_required", res_t5400m.matched)

    def test_05_deterministic_ranking_scores(self):
        """Test python deterministic ranking outputs highest score for best match."""
        candidates = self.repo.get_by_category("technical_cad")
        reqs = {"print_size": "A0", "scan_required": False, "application": "CAD", "daily_volume": "medium"}
        
        eligible = eligibility_engine.filter_candidates(candidates, reqs)
        ranked = product_ranker.rank_candidates(eligible, reqs)

        # Epson T5700D should rank higher than T3100 (which is A1)
        top_product = ranked[0][0]
        self.assertEqual(top_product.id, "epson-t5700d")

    def test_06_claim_and_numeric_validator(self):
        """Test validator intercepts hallucinated numbers and capabilities."""
        evidence = {
            "verified_specs": {
                "resolution": "2400 x 1200 dpi",
                "has_scanner": False,
            }
        }

        # Valid text
        valid_text = "The Epson T5100 prints at 2400 x 1200 dpi."
        ok, msg, _ = output_validator.validate_all(valid_text, evidence)
        self.assertTrue(ok)

        # Hallucinated resolution
        fake_res_text = "The Epson T5100 has an ultra-high 4800 x 2400 dpi resolution."
        ok, msg, _ = output_validator.validate_all(fake_res_text, evidence)
        self.assertFalse(ok)
        self.assertIn("Hallucinated resolution", msg)

        # Hallucinated scanner on print-only
        fake_scanner_text = "This unit includes an integrated scanner for drawings."
        ok, msg, _ = output_validator.validate_all(fake_scanner_text, evidence)
        self.assertFalse(ok)
        self.assertIn("claims scanner exists", msg)

    def test_11_unverified_product_not_falsely_fetched(self):
        """Test that unverified models like CX-02S are rejected and not falsely mapped to CX-02."""
        from agent.orchestrator import orchestrator as new_orchestrator
        from domain.conversation_state import ConversationState

        state = ConversationState(session_id="test_unv_suite")
        res = new_orchestrator.process_turn(
            raw_message="Give me the specifications of the CX-02S",
            session_id="test_unv_suite",
            history=[],
            state=state,
            model_name="qwen2.5:32b"
        )
        self.assertTrue("catalog" in res["source"] or "route:unverified_product" in res["source"])
        self.assertIn("CX-02S", res["reply"])
        self.assertIn("authorized Kepler Tech", res["reply"])
        self.assertEqual(len(res["product_cards"]), 0)

    def test_12_citizen_product_set_and_cy02_resolution(self):
        """Test verified product set and CY-02 resolution dual-mode without contradiction."""
        cx02 = self.repo.get_by_id("citizen-cx-02")
        cx02w = self.repo.get_by_id("citizen-cx-02w")
        cy02 = self.repo.get_by_id("citizen-cy-02")
        cz01 = self.repo.get_by_id("citizen-cz-01")

        self.assertIsNotNone(cx02)
        self.assertIsNotNone(cx02w)
        self.assertIsNotNone(cy02)
        self.assertIsNotNone(cz01)

        # CY-02 resolution dual-mode check: 300 dpi and 600 dpi verified
        cy02_res = cy02.structured_specs.get("resolution", {}).get("options", [])
        self.assertIn("300 dpi", cy02_res)
        self.assertIn("600 dpi", cy02_res)

        # CX-02S must not be in catalog
        self.assertIsNone(self.repo.get_by_id("citizen-cx-02s"))

    def test_13_no_unsupported_consumable_claims(self):
        """Test that unsupported consumable claims (core diameter, IC chips, jamming, printhead mismatch) are caught."""
        unsupported_phrases = [
            "The ribbon core diameter is different",
            "This cartridge includes an IC chip to prevent usage",
            "Using this media will cause mechanical jamming",
            "There is a severe printhead mismatch between models",
        ]
        for phrase in unsupported_phrases:
            self.assertTrue(output_validator.contains_unsupported_consumable_claim(phrase))


if __name__ == "__main__":
    unittest.main()
