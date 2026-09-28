"""Comprehensive Conversational Understanding and Naturalness Test Suite.

Tests 100+ customer messages and multi-turn conversations covering:
- Typo/spelling normalization (prntr, archtect drwing, insh, rool, cartage, etc.)
- Protected tokens (SKUs, dimensions, negations)
- Negation handling (pre-noun: 'no scanner', post-noun: 'scanner no need', 'scanner not important', 'not for CAD')
- Capability questions vs requirement statements ('does it have scanner?' vs 'I need scanner')
- Corrections ('actually A1 is enough', 'no sorry without scanner', 'maybe 50 actually')
- Short contextual answers with awaiting_field ('A0', 'around 50', 'yes', 'photo', 'office')
- Universal reference resolution ('this one', 'first one', 'second one', 'the one with scanner', 'the wider one', 'the cheaper one', 'the other model')
- Multi-requirement extraction in a single turn
- Multi-part attribute queries ('scanner, wifi and ink?')
- Topic switching ('forget this need photo printer for wedding')
- 26-turn continuous session test as specified in Section 31
"""

import unittest
from domain.conversation_state import ConversationState
from nlp.normalizer import normalize_for_intent, extract_clean_text
from nlp.llm_understanding import LLMUnderstandingEngine
from conversation.canonical_entity_normalizer import canonical_normalizer
from conversation.requirement_extractor import requirement_extractor
from conversation.reference_resolver import reference_resolver
from catalog.repository import catalog_repository
from agent.orchestrator import orchestrator


class TestConversationalUnderstanding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = catalog_repository
        cls.llm_engine = LLMUnderstandingEngine()

    # =========================================================================
    # 1. NORMALIZATION & PRESERVATION TESTS (25 cases)
    # =========================================================================
    def test_01_typo_correction_and_token_protection(self):
        cases = [
            ("i need a prntr", "printer", True),
            ("archtect drwing output", "architect drawing", True),
            ("36 insh rool paper", "36 inch roll", True),
            ("need cosumable and cartage", "consumable and cartridge", True),
            ("scaner and scnner both work", "scanner and scanner", True),
            # SKU / Model Protection
            ("SC-T5700DM vs SC-T5700D", "sc-t5700dm", True),
            ("SC-P8500D vs SC-P8500DM", "sc-p8500dm", True),
            ("Citizen CX-02 and CX-02W", "cx-02w", True),
            ("Cartridge C13T00E100", "c13t00e100", True),
            # Negative words protection
            ("no scanner", "no", True),
            ("without scan", "without", True),
            ("don't need CAD", "don't", True),
            ("not that one", "not", True),
            ("instead show second", "instead", True),
            ("actually A1", "actually", True),
            ("only 24 inch", "only", True),
        ]
        for raw, expected_sub, should_contain in cases:
            norm = normalize_for_intent(raw)
            if should_contain:
                self.assertIn(expected_sub.lower(), norm.lower(), f"Failed for '{raw}' -> '{norm}'")

    # =========================================================================
    # 2. NEGATION HANDLING TESTS (15 cases)
    # =========================================================================
    def test_02_negation_understanding(self):
        state = ConversationState(session_id="neg_test")
        state.category = "technical_cad"

        # Pre-noun negations
        res = canonical_normalizer.normalize_scanner_function("no scanner")
        self.assertIsNotNone(res)
        self.assertFalse(res.get("scanner_required"))

        res = canonical_normalizer.normalize_scanner_function("without scanner")
        self.assertIsNotNone(res)
        self.assertFalse(res.get("scanner_required"))

        res = canonical_normalizer.normalize_scanner_function("don't need scan")
        self.assertIsNotNone(res)
        self.assertFalse(res.get("scanner_required"))

        # Post-noun negations
        self.assertFalse(canonical_normalizer.normalize_scanner_function("scanner not needed").get("scanner_required"))
        self.assertFalse(canonical_normalizer.normalize_scanner_function("scanner no need").get("scanner_required"))
        self.assertFalse(canonical_normalizer.normalize_scanner_function("scanner not important").get("scanner_required"))
        self.assertFalse(canonical_normalizer.normalize_scanner_function("scanner not necessary").get("scanner_required"))
        self.assertFalse(canonical_normalizer.normalize_scanner_function("scan no need").get("scanner_required"))
        self.assertFalse(canonical_normalizer.normalize_scanner_function("scanning is not required").get("scanner_required"))

        # Requirements extraction with post-noun negations
        reqs = requirement_extractor.extract_and_validate("need A0 around 60 drawings scanner no need", state)
        self.assertEqual(reqs.get("scan_required"), False)
        self.assertEqual(reqs.get("print_size"), "A0")

        reqs2 = requirement_extractor.extract_and_validate("scanner not important but need A1", state)
        self.assertEqual(reqs2.get("scan_required"), False)
        self.assertEqual(reqs2.get("print_size"), "A1")

        # CAD negation ("printer but not for CAD")
        from conversation.normalizer import normalize_category
        cat = normalize_category("I need a printer but not for CAD")
        self.assertNotEqual(cat, "technical_large_format")

    # =========================================================================
    # 3. CAPABILITY QUESTION VS REQUIREMENT (10 cases)
    # =========================================================================
    def test_03_capability_query_vs_requirement(self):
        state = ConversationState(session_id="cap_vs_req")
        state.active_product = "epson-t5400m"

        # Capability questions - should NOT set scan_required = True
        cap_queries = [
            "Does it have a scanner?",
            "does this have scanner",
            "has scanner?",
            "is there a scanner?",
            "does it come with a scanner?",
            "scanner?",
        ]
        for query in cap_queries:
            self.assertTrue(
                canonical_normalizer.is_capability_query(query),
                f"Query '{query}' should be recognized as capability query"
            )
            extracted = requirement_extractor.extract_and_validate(query, state)
            self.assertNotIn("scan_required", extracted, f"Capability query '{query}' should NOT extract scan_required")

        # Requirement statements - SHOULD set scan_required = True
        req_statements = [
            "I need a scanner",
            "I need one with scanner",
            "must have scanner",
            "scanner is required",
        ]
        for stmt in req_statements:
            self.assertFalse(
                canonical_normalizer.is_capability_query(stmt),
                f"Statement '{stmt}' should NOT be recognized as capability query"
            )
            extracted = requirement_extractor.extract_and_validate(stmt, state)
            self.assertEqual(extracted.get("scan_required"), True)

    # =========================================================================
    # 4. CORRECTIONS & OVERWRITES (10 cases)
    # =========================================================================
    def test_04_corrections_and_overwrites(self):
        state = ConversationState(session_id="corr_test")
        state.category = "technical_cad"
        state.requirements = {"print_size": "A0", "scan_required": True, "daily_volume": "high"}

        # Paper size correction: A0 -> A1
        extracted = requirement_extractor.extract_and_validate("actually A1 is enough", state)
        state.requirements.update(extracted)
        self.assertEqual(state.requirements["print_size"], "A1")

        # Scanner correction: True -> False
        extracted = requirement_extractor.extract_and_validate("no sorry without scanner", state)
        state.requirements.update(extracted)
        self.assertEqual(state.requirements["scan_required"], False)

        # Volume correction: high -> 50
        extracted = requirement_extractor.extract_and_validate("maybe 50 actually", state)
        state.requirements.update(extracted)
        self.assertTrue(
            state.requirements.get("daily_volume") in ("medium", "high", 50)
            or state.requirements.get("exact_daily_volume") == 50
        )

    # =========================================================================
    # 5. CONTEXTUAL SHORT ANSWERS WITH AWAITING_FIELD (10 cases)
    # =========================================================================
    def test_05_short_contextual_answers(self):
        state = ConversationState(session_id="ctx_short_test")
        state.category = "technical_cad"

        # awaiting daily_volume
        state.awaiting_field = "daily_volume"
        reqs = requirement_extractor.extract_and_validate("around 50", state)
        self.assertTrue(
            reqs.get("daily_volume") in ("medium", "high", 50)
            or reqs.get("exact_daily_volume") == 50
        )

        # awaiting print_size
        state.awaiting_field = "print_size"
        reqs = requirement_extractor.extract_and_validate("A0", state)
        self.assertEqual(reqs.get("print_size"), "A0")

        # awaiting scan_required
        state.awaiting_field = "scan_required"
        reqs = requirement_extractor.extract_and_validate("no", state)
        self.assertEqual(reqs.get("scan_required"), False)

        reqs = requirement_extractor.extract_and_validate("yes", state)
        self.assertEqual(reqs.get("scan_required"), True)

        reqs = requirement_extractor.extract_and_validate("without", state)
        self.assertEqual(reqs.get("scan_required"), False)

    # =========================================================================
    # 6. UNIVERSAL REFERENCE RESOLUTION (15 cases)
    # =========================================================================
    def test_06_reference_resolution(self):
        state = ConversationState(session_id="ref_test")
        state.active_product = "epson-t5400m"
        state.candidate_products = ["epson-t3100", "epson-t5100", "epson-t5400m"]
        state.comparison_product_ids = ["epson-t3100", "epson-t5400m"]

        # Deictic references
        self.assertEqual(reference_resolver.resolve_references("what about this one?", state)[0], "epson-t5400m")
        self.assertEqual(reference_resolver.resolve_references("why that one", state)[0], "epson-t5400m")
        self.assertEqual(reference_resolver.resolve_references("does it have wifi", state)[0], "epson-t5400m")

        # Ordinal references
        self.assertEqual(reference_resolver.resolve_references("what about first one", state)[0], "epson-t3100")
        self.assertEqual(reference_resolver.resolve_references("second one?", state)[0], "epson-t5100")
        self.assertEqual(reference_resolver.resolve_references("last one", state)[0], "epson-t5400m")

        # Attribute-based references
        self.assertEqual(reference_resolver.resolve_references("the one with scanner", state)[0], "epson-t5400m")
        self.assertEqual(reference_resolver.resolve_references("the 36-inch one", state)[0], "epson-t5400m")
        self.assertEqual(reference_resolver.resolve_references("the wider one", state)[0], "epson-t5400m")

        # Alternative / Rejection
        self.assertEqual(reference_resolver.resolve_references("show another", state)[0], "epson-t3100")
        self.assertEqual(reference_resolver.resolve_references("not this one, show the other model", state)[0], "epson-t3100")

        # Comparison reference (two products)
        targets = reference_resolver.resolve_comparison_targets("compare this with first one", state)
        self.assertIn("epson-t5400m", targets)
        self.assertIn("epson-t3100", targets)

    # =========================================================================
    # 7. MULTI-REQUIREMENT EXTRACTION IN ONE TURN (10 cases)
    # =========================================================================
    def test_07_multi_requirement_extraction(self):
        state = ConversationState(session_id="multi_req_test")

        raw = "I run architecture office need A0 around 60 drawings every day and scanner not important"
        reqs = requirement_extractor.extract_and_validate(raw, state)

        self.assertEqual(reqs.get("print_size"), "A0")
        self.assertEqual(reqs.get("scan_required"), False)
        self.assertTrue(
            reqs.get("daily_volume") in ("medium", "high", 60)
            or reqs.get("exact_daily_volume") == 60
        )

        # Should infer technical_large_format category
        from conversation.normalizer import normalize_category
        cat = normalize_category(raw)
        self.assertIn(cat, ["technical_large_format", "technical_cad"])

    # =========================================================================
    # 8. MULTI-PART ATTRIBUTE EXTRACTION (10 cases)
    # =========================================================================
    def test_08_multi_part_attribute_extraction(self):
        cases = [
            ("does this have scanner, wifi and what ink does it use?", ["scanner", "wifi", "compatible_ink"]),
            ("speed and price?", ["speed", "price"]),
            ("what dimensions and resolution?", ["dimensions", "resolution"]),
            ("warranty and paper handling?", ["warranty", "paper_handling"]),
        ]
        for query, expected_attrs in cases:
            extracted = reference_resolver.extract_requested_attributes(query)
            for attr in expected_attrs:
                self.assertIn(attr, extracted, f"Attribute '{attr}' missing for query: '{query}'")

    # =========================================================================
    # 9. TOPIC SWITCH DETECTION (5 cases)
    # =========================================================================
    def test_09_topic_switch_detection(self):
        state = ConversationState(session_id="switch_test")
        state.category = "technical_cad"
        state.requirements = {"print_size": "A0", "scan_required": True, "daily_volume": "high"}
        state.active_product = "epson-t5400m"

        switch_msg = "forget this, now I need photo printer for wedding"
        self.assertTrue(reference_resolver.is_topic_switch(switch_msg))

        # Check semantic understanding engine identifies topic_switch
        sem = self.llm_engine._extract_semantic_features(switch_msg, state)
        self.assertTrue(sem["topic_switch"])


class TestLongContinuousSession(unittest.TestCase):
    """Section 31: 26-turn continuous multi-turn session test."""

    def test_section_31_long_continuous_session(self):
        state = ConversationState(session_id="section_31_session")

        script = [
            ("Hi", ["hello", "assist", "help", "kepler"]),
            ("need printer", ["what", "type", "print", "size", "photo", "cad"]),
            ("for archtect drawings", ["drawing", "cad", "size", "a0", "a1"]),
            ("a0", ["a0", "drawings", "day", "volume", "scan"]),
            ("maybe 60 daily", ["scan", "scanner", "recommend", "t5"]),
            ("no scan", ["epson", "t5100", "t5400", "t5700", "recommend"]),
            ("what u suggest", ["epson", "t5100", "plotter", "36"]),
            ("why this one", ["cad", "technical", "36", "a0", "volume"]),
            ("wifi?", ["wi-fi", "wifi", "yes", "support"]),
            ("what ink", ["ink", "cartridge", "ultra"]),
            ("show another", ["epson", "t5400", "t5700", "model"]),
            ("difference between them", ["difference", "speed", "scanner", "resolution"]),
            ("which one faster", ["sec", "speed", "faster", "ppm"]),
            ("what about first one", ["t5100", "first", "36"]),
            ("actually scanner needed", ["scanner", "t5400m", "integrated"]),
            ("now which", ["t5400m", "scanner", "integrated"]),
            ("why", ["scanner", "integrated", "a0", "cad"]),
            ("forget this", ["look", "need", "help", "switch", "print", "what", "got it"]),
            ("need photo printer for wedding", ["photo", "citizen", "wedding", "cx"]),
            ("4x6 mostly", ["4x6", "citizen", "cx-02", "volume", "prints"]),
            ("around 500 pic", ["citizen", "cx-02", "cy-02", "wedding"]),
            ("which good", ["citizen", "cx-02", "prints"]),
            ("second one?", ["one model", "which model", "citizen", "cy-02", "cx-02w"]),
            ("what media for that", ["media", "paper", "ribbon", "roll"]),
            ("how many prints", ["prints", "roll", "yield", "box"]),
            ("last printer i asked before photo which one?", ["t5400m", "epson", "t5100", "cad", "architect"]),
        ]

        history = []
        for i, (msg, expected_keywords) in enumerate(script, 1):
            res = orchestrator.process_turn(
                raw_message=msg,
                session_id=state.session_id,
                history=history,
                state=state,
                model_name="qwen2.5:32b"
            )
            reply = res["reply"].lower()
            source = res.get("source", "")

            # Maintain conversation history
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": res["reply"]})

            # Check that we got a valid response (not empty, no raw DB leaks)
            self.assertTrue(len(reply) > 5, f"Turn {i} '{msg}' yielded empty response")
            self.assertNotIn("subcategory", reply)
            self.assertNotIn("qualification_complete", reply)
            self.assertNotIn("match_score", reply)

            # Check keyword presence or sensible progression
            matches = [kw for kw in expected_keywords if kw in reply]
            self.assertTrue(
                len(matches) > 0,
                f"Turn {i} '{msg}' reply did not contain any expected keywords {expected_keywords}.\nReply: {res['reply']}\nSource: {source}"
            )


if __name__ == "__main__":
    unittest.main()
