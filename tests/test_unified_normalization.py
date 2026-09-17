"""
Comprehensive Test Suite for Unified Normalization Architecture.
Validates:
1. Canonical entity dimension normalization & orientation invariance
2. Metric-to-roll width normalization
3. Volume conversion formulas (25-day business standard)
4. Scanner requirement negation vs affirmation
5. Dialogue act classification (capability inquiry vs search filter)
6. Model code & SKU protection during NLP typo passes
7. Multilingual Manglish translation
"""

import unittest
from nlp.normalizer import normalize_text
from nlp.multilingual import normalize_multilingual
from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer
from conversation.normalizer import extract_deterministic_requirements, normalize_category
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator


class TestUnifiedNormalization(unittest.TestCase):

    # ── 1. Dimension & Photo Size Invariance ───────────────────────────────────

    def test_photo_pair_orientation_invariance(self):
        """Pairs like 6x4 and 4x6, 6x2 and 2x6, 12x8 and 8x12 must resolve to identical canonical forms."""
        # 4x6 vs 6x4
        d1 = CanonicalEntityNormalizer.normalize_dimensions("I want 4x6 prints")
        d2 = CanonicalEntityNormalizer.normalize_dimensions("I want 6x4 prints")
        self.assertEqual(d1.get("print_sizes"), ["4x6"])
        self.assertEqual(d2.get("print_sizes"), ["4x6"])

        # 2x6 vs 6x2
        d3 = CanonicalEntityNormalizer.normalize_dimensions("photo strips 2x6")
        d4 = CanonicalEntityNormalizer.normalize_dimensions("photo strips 6x2")
        self.assertEqual(d3.get("print_sizes"), ["2x6"])
        self.assertEqual(d4.get("print_sizes"), ["2x6"])

        # 8x12 vs 12x8
        d5 = CanonicalEntityNormalizer.normalize_dimensions("large 8x12 photos")
        d6 = CanonicalEntityNormalizer.normalize_dimensions("large 12x8 photos")
        self.assertEqual(d5.get("print_sizes"), ["8x12"])
        self.assertEqual(d6.get("print_sizes"), ["8x12"])

    def test_metric_width_normalization(self):
        """Metric dimensions (mm/cm) must map accurately to imperial roll widths."""
        # 914 mm -> 36-inch (A0)
        m1 = CanonicalEntityNormalizer.normalize_dimensions("roll width 914mm for architectural plans")
        self.assertEqual(m1.get("print_width"), 36)
        self.assertEqual(m1.get("paper_size"), "a0")

        # 610 mm -> 24-inch (A1)
        m2 = CanonicalEntityNormalizer.normalize_dimensions("need 610 mm plotter")
        self.assertEqual(m2.get("print_width"), 24)
        self.assertEqual(m2.get("paper_size"), "a1")

        # 1118 mm -> 44-inch
        m3 = CanonicalEntityNormalizer.normalize_dimensions("1118mm wide format production")
        self.assertEqual(m3.get("print_width"), 44)
        self.assertEqual(m3.get("paper_size"), "44-inch")

    # ── 2. Volume Normalization ───────────────────────────────────────────────

    def test_monthly_to_daily_canonical_conversion(self):
        """Monthly volume must convert to daily using standard 30-day month."""
        v1 = CanonicalEntityNormalizer.normalize_volume("expecting 6000 prints per month")
        self.assertEqual(v1.get("monthly_volume"), 6000)
        self.assertEqual(v1.get("daily_volume"), 200)

        v2 = CanonicalEntityNormalizer.normalize_volume("1,500 pages a month")
        self.assertEqual(v2.get("monthly_volume"), 1500)
        self.assertEqual(v2.get("daily_volume"), 50)

    def test_daily_volume_detection(self):
        """Daily volume must be correctly extracted and calculate monthly counterpart."""
        v1 = CanonicalEntityNormalizer.normalize_volume("around 40 drawings daily")
        self.assertEqual(v1.get("daily_volume"), 40)
        self.assertEqual(v1.get("monthly_volume"), 1200)

        v2 = CanonicalEntityNormalizer.normalize_volume("20 to 30 prints a day")
        self.assertEqual(v2.get("daily_volume"), 25)
        self.assertEqual(v2.get("monthly_volume"), 750)

    # ── 3. Scanner Function Normalization ─────────────────────────────────────

    def test_scanner_negation_precedence(self):
        """Negations ('without scanner', 'print only') must strictly yield False/print."""
        s1 = CanonicalEntityNormalizer.normalize_scanner_function("we need a plotter without scanner")
        self.assertIsNotNone(s1)
        self.assertFalse(s1["scanner_required"])
        self.assertEqual(s1["functions"], ["print"])

        s2 = CanonicalEntityNormalizer.normalize_scanner_function("print only, don't need scanner")
        self.assertIsNotNone(s2)
        self.assertFalse(s2["scanner_required"])
        self.assertEqual(s2["functions"], ["print"])

    def test_scanner_affirmation(self):
        """Positive scanner assertions must yield True/print,scan,copy."""
        s = CanonicalEntityNormalizer.normalize_scanner_function("we require an integrated scanner for blueprints")
        self.assertIsNotNone(s)
        self.assertTrue(s["scanner_required"])
        self.assertEqual(s["functions"], ["print", "scan", "copy"])

    # ── 4. Dialogue Act Separation ────────────────────────────────────────────

    def test_capability_query_detection(self):
        """Queries inquiring about features/specs must be recognized as capability queries."""
        self.assertTrue(CanonicalEntityNormalizer.is_capability_query("CAN I PRINT 2X6 STRIP IN THIS PRINTER?"))
        self.assertTrue(CanonicalEntityNormalizer.is_capability_query("does it support 4x6 borderless?"))
        self.assertTrue(CanonicalEntityNormalizer.is_capability_query("is this printer able to cut paper?"))
        self.assertFalse(CanonicalEntityNormalizer.is_capability_query("I want a 24-inch printer with scanner"))

    def test_capability_query_preserves_active_product(self):
        """Asking a capability query on an active product must not mutate requirements or clear active product."""
        state = ConversationState(session_id="test-cap-preserve")
        # Turn 1: recommend CX-02W
        res1 = orchestrator.process_turn("I need an 8x12 event photo printer", state=state)
        self.assertIsNotNone(state.active_product)
        active_id = state.active_product_id
        self.assertEqual(active_id, "citizen-cx-02w")

        # Turn 2: capability question mentioning 2x6 strip
        res2 = orchestrator.process_turn("Can I print 2x6 strip in this printer?", state=state)
        # Should answer the capability question and recommend CX-02 for 2x6
        self.assertIn("CX-02", res2.get("reply", ""))
        self.assertIn("CX-02W", res2.get("reply", ""))
        self.assertIn("multi-cut", res2.get("reply", ""))

    # ── 5. Model Code & SKU Protection ────────────────────────────────────────

    def test_model_codes_protected_from_typos(self):
        """Approved model numbers must never be mangled by typo regexes."""
        raw = "we have SC-T3100, CX-02W, and AM-C5000 in our office"
        norm = normalize_text(raw)
        text = norm["normalized_text"]
        self.assertIn("SC-T3100", text)
        self.assertIn("CX-02W", text)
        self.assertIn("AM-C5000", text)

    # ── 6. Multilingual Manglish Normalization ─────────────────────────────────

    def test_manglish_translations(self):
        """Colloquial Manglish phrases must be translated into clean English equivalents."""
        t1, _ = normalize_multilingual("oru photo printer venam")
        self.assertEqual(t1, "I need a photo printer")

        t2, _ = normalize_multilingual("ithu nallathano")
        self.assertEqual(t2, "is this good")

        t3, _ = normalize_multilingual("kurakko")
        self.assertEqual(t3, "reduce price")


if __name__ == "__main__":
    unittest.main()
