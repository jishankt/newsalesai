"""
Regression tests for pipeline improvements:
1. Discrete catalogue records: epson-p7500 and epson-p9500 separated.
2. Vague terms: "I need a large printer" triggers clarification, not guessed specs.
3. Studio photography: "I need a studio printer" asks technology clarification (dye-sub vs inkjet).
4. Hard constraints & Single eligible match:
   - "I need 8x12" -> CX-02W only with "only verified match".
   - "Do you have another one?" -> Explains hard constraint and asks permission to change size.
5. No unsupported 8x32 claims for CX-02W.
6. Recommendation audit object returned with all 9 required fields.
"""

import unittest
from catalog.repository import catalog_repository
from domain.conversation_state import ConversationState
from agent.orchestrator import Orchestrator
from conversation.requirement_extractor import requirement_extractor
from recommendation.eligibility import EligibilityEngine
from routes.product_route import handle as handle_product_route


class TestPipelineImprovements(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()
        self.eligibility_engine = EligibilityEngine()

    def test_01_discrete_catalogue_records(self):
        """1. Audit catalogue count: epson-p7500 and epson-p9500 must be separate records."""
        p7500 = catalog_repository.get_by_id("epson-p7500")
        p9500 = catalog_repository.get_by_id("epson-p9500")

        self.assertIsNotNone(p7500, "epson-p7500 must exist in catalogue")
        self.assertIsNotNone(p9500, "epson-p9500 must exist in catalogue")
        self.assertNotEqual(p7500.id, p9500.id)

        # Verify specs
        self.assertEqual(p7500.verified.max_width_mm, 610)
        self.assertEqual(p9500.verified.max_width_mm, 1118)
        self.assertIn("24", p7500.verified.max_width_label)
        self.assertIn("44", p9500.verified.max_width_label)

        t5100m = catalog_repository.get_by_id("epson-t5100m")
        t5400m = catalog_repository.get_by_id("epson-t5400m")
        self.assertIsNotNone(t5100m, "epson-t5100m must exist in catalogue")
        self.assertIsNotNone(t5400m, "epson-t5400m must exist in catalogue")
        self.assertNotEqual(t5100m.id, t5400m.id)
        self.assertIn("t5100m", t5100m.source.website_url)
        self.assertIn("t5400m", t5400m.source.website_url)

        # The expanded catalogue includes 104 distinct hardware and accessory records.
        all_prods = catalog_repository.get_all()
        self.assertEqual(len(all_prods), 104)
        self.assertEqual(len({p.id for p in all_prods}), len(all_prods))

    def test_02_vague_terms_require_clarification(self):
        """2. Never normalize 'large' into exact specifications; ask clarification."""
        state = ConversationState(session_id="test-vague-size")
        res = self.orchestrator.process_turn(
            raw_message="I need a large printer",
            session_id="test-vague-size",
            history=[],
            state=state
        )

        reply = res["reply"].lower()
        # Must ask clarification for print dimensions / paper sizes
        self.assertTrue(
            "specify" in reply or "dimensions" in reply or "sizes" in reply or "what size" in reply,
            f"Expected clarification question, got: {res['reply']}"
        )
        # Must NOT set an arbitrary size in requirements
        self.assertNotIn("A0", state.requirements.values())
        self.assertNotIn("44-inch", state.requirements.values())
        self.assertNotIn("8x12 inches", state.requirements.values())
        self.assertEqual(state.awaiting_field, "print_size")

    def test_03_studio_photography_technology_disambiguation(self):
        """3. Do not route studio photography directly to photo_fine_art; ask dye-sub vs inkjet."""
        state = ConversationState(session_id="test-studio-disambiguation")
        res = self.orchestrator.process_turn(
            raw_message="I need a studio printer",
            session_id="test-studio-disambiguation",
            history=[],
            state=state
        )

        reply = res["reply"].lower()
        self.assertIn("dye-sublimation", reply)
        self.assertIn("inkjet", reply)
        self.assertIn("Fast Dye-Sublimation", res["suggested_chips"])
        self.assertIn("Archival Fine-Art Inkjet", res["suggested_chips"])
        self.assertEqual(state.awaiting_field, "studio_technology_preference")

        # Now answer with fast dye-sublimation
        res2 = self.orchestrator.process_turn(
            raw_message="Fast instant dye-sublimation",
            session_id="test-studio-disambiguation",
            history=state.history_turns,
            state=state
        )
        self.assertEqual(state.category, "photo_booth")
        self.assertEqual(state.requirements.get("printing_technology"), "dye_sub")

    def test_04_hard_constraints_and_single_eligible_match(self):
        """4 & 5. 8x12 hard constraint -> CX-02W is only verified match; alternatives require permission."""
        state = ConversationState(session_id="test-8x12-match")
        res = self.orchestrator.process_turn(
            raw_message="I need 8x12",
            session_id="test-8x12-match",
            history=[],
            state=state
        )

        # Must select CX-02W as only verified match
        self.assertTrue("citizen cx-02w" in res["reply"].lower() or "citizen-cx-02w" in res["reply"].lower())
        self.assertIn("only verified match", res["reply"].lower())
        self.assertNotIn("optimal", res["reply"].lower())
        self.assertNotIn("best", res["reply"].lower())

        # Check internal audit object
        audit = res.get("recommendation_audit")
        self.assertIsNotNone(audit, "recommendation_audit object must be present in response")
        required_keys = [
            "collected_requirements", "missing_requirements", "hard_constraints",
            "eligible_products", "rejected_products_with_reason", "ranking_factors",
            "selected_product", "evidence_ids", "unsupported_claims"
        ]
        for key in required_keys:
            self.assertIn(key, audit, f"Audit missing key: {key}")

        self.assertEqual(audit["selected_product"], "citizen-cx-02w")
        self.assertEqual(audit["eligible_products"], ["citizen-cx-02w"])
        # Ensure 6" models were rejected for size
        self.assertIn("citizen-cx-02", audit["rejected_products_with_reason"])
        self.assertIn("citizen-cy-02", audit["rejected_products_with_reason"])
        self.assertIn("citizen-cz-01", audit["rejected_products_with_reason"])

        # Step 2: "Do you have another one?"
        res2 = self.orchestrator.process_turn(
            raw_message="Do you have another one?",
            session_id="test-8x12-match",
            history=state.history_turns,
            state=state
        )

        reply2 = res2["reply"].lower()
        # Must explain constraint and ask permission to adjust, NOT present 6" models as matches
        self.assertIn("only verified match", reply2)
        self.assertTrue(
            "adjust" in reply2 or "willing" in reply2 or "alternatives" in reply2,
            f"Expected constraint explanation and permission prompt, got: {res2['reply']}"
        )

    def test_05_no_8x32_claims_for_cx02w(self):
        """6. CX-02W must not claim 8x32 panoramic output unless approved in catalogue."""
        cx02w = catalog_repository.get_by_id("citizen-cx-02w")
        self.assertIsNotNone(cx02w)

        # Check description and highlights
        desc = (cx02w.description or "") + (cx02w.comparison_highlights or "")
        self.assertNotIn("8x32", desc)
        self.assertNotIn("8×32", desc)

        # Test asking about max width/sizes
        state = ConversationState(session_id="test-cx02w-specs")
        res = self.orchestrator.process_turn(
            raw_message="What are the supported print sizes of the Citizen CX-02W?",
            session_id="test-cx02w-specs",
            history=[],
            state=state
        )
        self.assertNotIn("8x32", res["reply"])
        self.assertNotIn("8×32", res["reply"])


if __name__ == "__main__":
    unittest.main()
