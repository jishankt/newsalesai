"""
Acceptance and regression tests for Grounded Consultative Sales Agent improvements.
Verifies all 10 core requirements:
1. "Does it have a scanner?" vs "I need a scanner" (including product with missing scanner).
2. "Wi-Fi, scanner, and ink?" with 3-valued logic (supported, unsupported, unknown).
3. "Can the SC-P900 print T-shirts?" followed by "What did I ask about the P900?".
4. "Send a photo" with catalog image vs verified product URL only.
5. "What's the difference between these two?" for SC-P900 cut-sheet vs roll adapter configurations.
6. "The second one" after 2+ candidates, and ambiguous reference clarification.
7. Corrected size, scanner preference, and monthly volume (exact stated monthly vs derived daily).
8. Composer validation rejecting swapped specs, invented Wi-Fi, and unsupported negative claims.
9. Local LLM timeout fallback to verified answer plan.
10. Price and quote requests: zero price, discount, quote offer, or handover leaks.
"""

import unittest
from unittest.mock import patch, MagicMock
from domain.conversation_state import ConversationState
from domain.response_context import ResponseContext, VerifiedEvidenceBundle, AnswerPlan, AnswerPlanItem, FieldFact
from agent.orchestrator import orchestrator
from agent.evidence_planner import evidence_planner
from agent.response_composer import ResponseComposer
from conversation.reference_resolver import reference_resolver
from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer
from conversation.normalizer import extract_deterministic_requirements
from catalog.catalogue_loader import catalogue_loader


class TestGroundedConsultativeSalesAgent(unittest.TestCase):

    # ── 1. "Does it have a scanner?" vs "I need a scanner" ────────────────
    def test_01_scanner_capability_vs_requirement_and_missing_field(self):
        """
        'Does it have a scanner?' is a capability inquiry:
        - Must NOT set scanner_required in state.requirements.
        - If scanner field is missing in catalog, must yield unknown (not assume No).
        'I need a scanner' is a requirement and MUST set scanner_required = True.
        """
        # Test 1A: Requirement inquiry
        state1 = ConversationState(session_id="test_scanner_req")
        reqs1, _ = extract_deterministic_requirements("I need a scanner for office", state1)
        self.assertTrue(reqs1.get("scanner_required"))

        # Test 1B: Capability question does NOT add scanner_required to requirements
        state2 = ConversationState(session_id="test_scanner_cap")
        state2.active_product = catalogue_loader.get_by_id("epson-sc-p900")
        state2.active_product_id = "epson-sc-p900"
        reqs2, _ = extract_deterministic_requirements("Does it have a scanner?", state2)
        self.assertNotIn("scanner_required", reqs2)

        # Test 1C: Missing scanner field in catalog record strictly yields 'unknown'
        prod_missing_scanner = {
            "id": "mock-printer-no-scanner-field",
            "display_name": "Mock Printer Special",
            "brand": "Epson",
            # 'has_scanner' is deliberately omitted/None
        }
        state3 = ConversationState(session_id="test_missing_scanner")
        state3.active_product = prod_missing_scanner
        bundle = evidence_planner.plan_and_retrieve(
            raw_query="Does this printer have a scanner?",
            nlp_result={"requested_attributes": ["scanner"]},
            state=state3,
        )
        scan_facts = [fact for p_dict in bundle.field_facts.values() for fact in p_dict.values() if fact.attribute == "scanner"]
        self.assertTrue(len(scan_facts) >= 1)
        self.assertEqual(scan_facts[0].status, "unknown")
        self.assertIn("not documented", scan_facts[0].display_claim.lower())

    # ── 2. "Wi-Fi, scanner, and ink?" with unknown attribute ──────────────
    def test_02_multipart_with_unknown_attribute_distinct_treatment(self):
        """
        'Wi-Fi, scanner, and ink?' where one attribute is unknown:
        All three receive distinct, accurate treatment with 3-valued logic.
        """
        # Product with Wi-Fi supported, scanner unknown, and ink supported
        prod = {
            "id": "mock-printer-variant-p900",
            "display_name": "Epson SureColor Mock Variant",
            "connectivity": "Wi-Fi, Wi-Fi Direct, Ethernet, USB 3.0",
            # scanner omitted -> unknown
            "consumables": ["T46S UltraChrome PRO10 Inks"],
            "model_family": "SureColor SC-P900",
        }
        state = ConversationState(session_id="test_multipart_unknown")
        state.active_product = prod
        state.active_product_id = prod["id"]

        bundle = evidence_planner.plan_and_retrieve(
            raw_query="Does it have Wi-Fi, scanner, and ink?",
            nlp_result={"requested_attributes": ["wifi", "scanner", "compatible_ink"]},
            state=state,
        )

        plan = bundle.answer_plan
        self.assertIsNotNone(plan)
        attr_map = {item.attribute: item.status for item in plan.items}

        self.assertEqual(attr_map.get("wifi"), "supported")
        self.assertEqual(attr_map.get("scanner"), "unknown")
        self.assertEqual(attr_map.get("compatible_ink"), "supported")

        rendered = plan.render_deterministic_answer()
        self.assertIn("Wi-Fi", rendered)
        self.assertIn("scanner", rendered.lower())
        self.assertIn("unknown", rendered.lower())
        self.assertIn("UltraChrome", rendered)

    # ── 3. "Can SC-P900 print T-shirts?" & "What did I ask about P900?" ───
    def test_03_p900_tshirt_capability_and_memory_recall(self):
        """
        'Can the SC-P900 print T-shirts?' answered directly without category hijack,
        followed by 'What did I ask about the P900?' correctly recalling the query.
        """
        state = ConversationState(session_id="test_p900_tshirt_flow")

        # Turn 1: Capability question
        r1 = orchestrator.process_turn("Can the SC-P900 print T-shirts?", session_id="test_p900_tshirt_flow", state=state)
        r1_text = r1["reply"].lower()
        # Direct answer: SC-P900 cannot print T-shirts (aqueous photo printer)
        self.assertTrue("cannot" in r1_text or "not" in r1_text)
        self.assertIn("p900", r1_text)
        # Category must NOT have been changed to dye_sublimation or office
        self.assertNotEqual(state.category, "dye_sublimation")

        # Turn 2: Conversational recall
        r2 = orchestrator.process_turn("What did I ask about the P900?", session_id="test_p900_tshirt_flow", state=state)
        r2_text = r2["reply"].lower()
        self.assertIn("p900", r2_text)
        self.assertTrue("t-shirt" in r2_text or "t shirt" in r2_text)

    # ── 4. "Send a photo" with image vs verified product URL only ─────────
    def test_04_media_request_verified_url_vs_direct_image(self):
        """
        'Send a photo' provides catalog image if present;
        if direct image is not catalogued, provides verified product URL only and does NOT invent image URLs.
        """
        state = ConversationState(session_id="test_media_url")
        p900 = catalogue_loader.get_by_id("epson-sc-p900")
        state.active_product = p900
        state.active_product_id = "epson-sc-p900"

        bundle = evidence_planner.plan_and_retrieve(
            raw_query="can you send a photo?",
            nlp_result={"requested_attributes": ["media_request"]},
            state=state,
        )
        plan = bundle.answer_plan
        rendered = plan.render_deterministic_answer()
        # Verified website URL must be present
        self.assertIn(p900.get("product_url"), rendered)
        # Must not hallucinate non-existent fake CDN domains
        self.assertNotIn("fake-image-cdn.com", rendered)

    # ── 5. "What's the difference between these two?" (SC-P900 configs) ───
    def test_05_configuration_difference_between_p900_cut_sheet_and_roll(self):
        """
        'What's the difference between these two?' after showing SC-P900 standard and roll adapter.
        """
        state = ConversationState(session_id="test_p900_diff")
        p900 = catalogue_loader.get_by_id("epson-sc-p900")
        state.active_product = p900
        state.active_product_id = "epson-sc-p900"

        bundle = evidence_planner.plan_and_retrieve(
            raw_query="What's the difference between these two?",
            nlp_result={"requested_attributes": ["configuration_difference"]},
            state=state,
        )
        plan = bundle.answer_plan
        rendered = plan.render_deterministic_answer()
        self.assertIn("roll", rendered.lower())
        self.assertIn("cut-sheet", rendered.lower())

    # ── 6. "The second one" and ambiguous reference clarification ─────────
    def test_06_ordinal_resolution_and_ambiguous_reference_clarification(self):
        """
        'The second one' after 2 candidates resolves correctly.
        Ambiguous reference ('the second one' when only 1 candidate exists) triggers clarification.
        """
        state = ConversationState(session_id="test_ordinals")
        p1 = catalogue_loader.get_by_id("epson-sc-t5100")
        p2 = catalogue_loader.get_by_id("epson-sc-t5400m")
        state.displayed_product_ids = [p1["id"], p2["id"]]
        state.candidate_products = [p1, p2]

        # 6A: Two candidates displayed -> 'the second one' resolves to p2
        res1 = reference_resolver.resolve_references("tell me about the second one", state=state)
        self.assertFalse(res1.needs_clarification)
        self.assertEqual(len(res1.resolved_products), 1)
        self.assertEqual(res1.resolved_products[0]["id"], p2["id"])

        # 6B: Only one candidate displayed -> 'the second one' requires clarification
        state_single = ConversationState(session_id="test_single_ord")
        state_single.displayed_product_ids = [p1["id"]]
        state_single.candidate_products = [p1]
        res2 = reference_resolver.resolve_references("what about the second one?", state=state_single)
        self.assertTrue(res2.needs_clarification)
        self.assertIn("Which second model did you mean", res2.clarification_question)

    # ── 7. Corrected size, scanner preference, and monthly volume ─────────
    def test_07_corrected_requirements_flow(self):
        """
        Tests multi-turn corrections:
        A0 -> A1, no scanner, and monthly volume conversion (3000 monthly -> 120 daily).
        """
        state = ConversationState(session_id="test_corrections_flow")

        # Turn 1: Initial request
        r1 = orchestrator.process_turn("I need an A0 plotter for technical drawings", session_id="test_corrections_flow", state=state)
        self.assertEqual(state.requirements.get("paper_size", "").lower(), "a0")

        # Turn 2: Corrected size to A1
        r2 = orchestrator.process_turn("Actually I need A1 size", session_id="test_corrections_flow", state=state)
        self.assertEqual(state.requirements.get("paper_size", "").lower(), "a1")

        # Turn 3: Scanner preference corrected
        r3 = orchestrator.process_turn("I do not need a scanner", session_id="test_corrections_flow", state=state)
        self.assertFalse(state.requirements.get("scanner_required"))

        # Turn 4: Stated monthly volume
        r4 = orchestrator.process_turn("My volume is 3000 pages per month", session_id="test_corrections_flow", state=state)
        self.assertEqual(state.requirements.get("exact_monthly_volume"), 3000)
        # 3000 / 30 calendar days = 100 pages/day
        self.assertEqual(state.requirements.get("daily_volume"), 100)

        # Turn 5: Feature question does NOT overwrite existing requirements
        r5 = orchestrator.process_turn("Does it have Wi-Fi?", session_id="test_corrections_flow", state=state)
        self.assertEqual(state.requirements.get("paper_size", "").lower(), "a1")
        self.assertFalse(state.requirements.get("scanner_required"))
        self.assertEqual(state.requirements.get("daily_volume"), 100)

    # ── 8. Composer validation rejecting swapped specs, invented Wi-Fi ────
    def test_08_composer_validation_rejects_hallucinations_and_swaps(self):
        """
        Validation must reject:
        1. Swapped specifications between models.
        2. Invented Wi-Fi support when evidence is unknown/unsupported.
        3. Unsupported negative claims when evidence says feature is supported.
        """
        composer = ResponseComposer()
        p900 = catalogue_loader.get_by_id("epson-sc-p900")
        t5100 = catalogue_loader.get_by_id("epson-sc-t5100")

        evidence = VerifiedEvidenceBundle(
            active_product=p900,
            candidate_products=[p900, t5100],
            field_facts=[
                FieldFact(product_id="epson-sc-p900", attribute="wifi", status="supported", fact="Supports Wi-Fi"),
                FieldFact(product_id="epson-sc-p900", attribute="scanner", status="unsupported", fact="Print-only, no scanner"),
            ],
            answer_plan=AnswerPlan(
                items=[
                    AnswerPlanItem(product_id="epson-sc-p900", attribute="wifi", status="supported", verified_fact="Supports Wi-Fi"),
                    AnswerPlanItem(product_id="epson-sc-p900", attribute="scanner", status="unsupported", verified_fact="Print-only, no scanner"),
                ]
            )
        )

        ctx = ResponseContext(
            original_message="Does it have Wi-Fi and scanner?",
            normalized_message="Does it have Wi-Fi and scanner?",
            intent="check_specs",
            dialogue_act="capability_inquiry",
            resolved_references={"it": "Epson SureColor SC-P900"},
            conversation_state={},
            customer_questions=["Does it have Wi-Fi and scanner?"],
            verified_evidence=evidence,
            response_goal="answer_specs",
            deterministic_draft="",
            allowed_followup=None,
            needs_naturalization=True,
            answer_plan=evidence.answer_plan,
        )

        # 8A: Inventing positive claim for scanner (which is unsupported)
        invented_draft = "Yes, the Epson SureColor SC-P900 includes a high-resolution integrated scanner."
        is_valid, reasons = composer._validate_composed_text(invented_draft, ctx)
        self.assertFalse(is_valid)
        self.assertTrue(any("unsupported_positive_claim:scanner" in r for r in reasons))

        # 8B: Unsupported negative claim for Wi-Fi (which is supported)
        unsupported_neg_draft = "No, the Epson SureColor SC-P900 does not have Wi-Fi or wireless capability."
        is_valid2, reasons2 = composer._validate_composed_text(unsupported_neg_draft, ctx)
        self.assertFalse(is_valid2)
        self.assertTrue(any("unsupported_negative_claim:wifi" in r for r in reasons2))

        # 8C: Cross-product specification swap
        swapped_draft = "The Epson SureColor SC-P900 is a 36-inch wide format printer."
        is_valid3, reasons3 = composer._validate_composed_text(swapped_draft, ctx)
        self.assertFalse(is_valid3)
        self.assertTrue(any("cross_product_spec_swap" in r for r in reasons3))

    # ── 9. Local LLM timeout fallback ─────────────────────────────────────
    def test_09_llm_timeout_fallback_to_verified_answer_plan(self):
        """
        When local LLM times out or errors, composer renders directly from verified AnswerPlan.
        Output remains accurate, complete, and free of hallucination.
        """
        composer = ResponseComposer()
        p900 = catalogue_loader.get_by_id("epson-sc-p900")

        evidence = VerifiedEvidenceBundle(
            active_product=p900,
            candidate_products=[p900],
            field_facts=[
                FieldFact(product_id="epson-sc-p900", attribute="wifi", status="supported", fact="Supports Wi-Fi and Wi-Fi Direct"),
                FieldFact(product_id="epson-sc-p900", attribute="scanner", status="unsupported", fact="Dedicated print-only system without scanner"),
            ],
            answer_plan=AnswerPlan(
                items=[
                    AnswerPlanItem(product_id="epson-sc-p900", attribute="wifi", status="supported", verified_fact="Supports Wi-Fi and Wi-Fi Direct wireless connectivity."),
                    AnswerPlanItem(product_id="epson-sc-p900", attribute="scanner", status="unsupported", verified_fact="Dedicated print-only unit and does not include an integrated scanner."),
                ]
            )
        )

        ctx = ResponseContext(
            original_message="Does the SC-P900 have Wi-Fi and a scanner?",
            normalized_message="Does the SC-P900 have Wi-Fi and a scanner?",
            intent="check_specs",
            dialogue_act="capability_inquiry",
            resolved_references={"it": "Epson SureColor SC-P900"},
            conversation_state={},
            customer_questions=["Does the SC-P900 have Wi-Fi and a scanner?"],
            verified_evidence=evidence,
            response_goal="answer_specs",
            deterministic_draft="",
            allowed_followup=None,
            needs_naturalization=True,
            answer_plan=evidence.answer_plan,
        )

        # Mock LLM timing out
        mock_client = MagicMock()
        mock_client.compose.side_effect = TimeoutError("Local LLM timeout")
        composer = ResponseComposer(ollama_client=mock_client)
        reply = composer.compose(ctx)
        self.assertIn("Wi-Fi", reply)
        self.assertIn("scanner", reply.lower())
        self.assertIn("print-only", reply.lower())

    # ── 10. Price & quote policy enforcement (no leaks) ───────────────────
    def test_10_product_policy_price_and_quote_suppression(self):
        """
        Commercial queries must not leak numeric prices, discounts, quote offers, or handover.
        Chips and cards must also be sanitized.
        """
        state = ConversationState(session_id="test_price_suppression")
        state.active_product = catalogue_loader.get_by_id("epson-sc-p900")
        state.active_product_id = "epson-sc-p900"

        # Ask for discount
        resp1 = orchestrator.process_turn("Can you give me a 20% discount or quote?", session_id="test_price_suppression", state=state)
        reply1 = resp1["reply"]

        # 1. No discount promise or bargaining in reply
        self.assertNotIn("20%", reply1)
        self.assertNotIn("I can give you a discount", reply1)
        # 2. Directs to verified website
        self.assertIn("https://www.keplertechllc.com/", reply1)

        # 3. Chips must not contain quotes or handover
        chips1 = resp1.get("suggested_chips", [])
        for ch in chips1:
            ch_l = ch.lower()
            self.assertNotIn("quote", ch_l)
            self.assertNotIn("sales desk", ch_l)
            self.assertNotIn("handover", ch_l)


if __name__ == "__main__":
    unittest.main()
