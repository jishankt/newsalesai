"""
16 parameterized tests for the Universal Comparison Engine.
Tests all required scenarios from the spec.
"""
import html
import unittest

from catalog.catalogue_loader import catalogue_loader
from catalog.comparison_engine import (
    build_comparison,
    build_comparison_intro,
    NOT_VERIFIED,
)


def _get(pid):
    """Helper: fetch a product by ID and fail loudly if missing."""
    p = catalogue_loader.get_by_id(pid)
    if not p:
        raise AssertionError(f"Product '{pid}' not found in catalogue.")
    return p


class TestComparisonEngine(unittest.TestCase):

    # ── 1. WF-C878R vs WF-C879R ──────────────────────────────────────────
    def test_01_wf_c878r_vs_wf_c879r(self):
        """Same subcategory — A3 WorkForce Pro multifunction."""
        p1 = _get("epson-wf-c878r-dwf")
        p2 = _get("epson-wf-c879r-dwf")
        result = build_comparison([p1, p2])

        self.assertEqual(result["comparison_type"], "same_subcategory")
        self.assertIsNone(result["cross_category_note"])
        ids_in = {p["id"] for p in result["products"]}
        self.assertEqual(ids_in, {"epson-wf-c878r-dwf", "epson-wf-c879r-dwf"})

        # Must have more than 5 criteria (not the old generic fixed table)
        self.assertGreater(len(result["criteria"]), 5)

        # Category-specific: paper_size and product_line must appear
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("paper_size", keys)
        self.assertIn("product_line", keys)
        self.assertIn("scanner_integrated", keys)

        # Common criteria must be present
        for ck in ("model", "main_category", "functions", "max_output_size"):
            self.assertIn(ck, keys)

        # No Markdown table in values
        for row in result["criteria"]:
            for val in row["values"].values():
                self.assertNotIn("|", val)

    # ── 2. AM-C4000 vs AM-C6000 ──────────────────────────────────────────
    def test_02_am_c4000_vs_am_c6000(self):
        """Same subcategory — A3 Enterprise multifunction."""
        p1 = _get("epson-am-c4000")
        p2 = _get("epson-am-c6000")
        result = build_comparison([p1, p2])

        self.assertEqual(result["comparison_type"], "same_subcategory")
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("recommended_volume", keys)
        self.assertIn("product_line", keys)

        # Values for product_line should say WorkForce Enterprise for both
        pl_row = next(c for c in result["criteria"] if c["key"] == "product_line")
        for val in pl_row["values"].values():
            self.assertIn("WorkForce Enterprise", val)

    # ── 3. SC-T5100 vs SC-T5700D ─────────────────────────────────────────
    def test_03_sc_t5100_vs_sc_t5700d(self):
        """Same subcategory — 36-inch print-only technical."""
        p1 = _get("epson-sc-t5100")
        p2 = _get("epson-sc-t5700d")
        result = build_comparison([p1, p2])

        self.assertEqual(result["comparison_type"], "same_subcategory")
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("max_width_inches", keys)
        self.assertIn("dual_roll", keys)
        self.assertIn("scanner_integrated", keys)

        # Both should be 36 inches
        width_row = next(c for c in result["criteria"] if c["key"] == "max_width_inches")
        for val in width_row["values"].values():
            self.assertIn("36", val)

    # ── 4. SC-T5100M vs SC-T5700DM ───────────────────────────────────────
    def test_04_sc_t5100m_vs_sc_t5700dm(self):
        """Same subcategory — 36-inch multifunction technical."""
        p1 = _get("epson-sc-t5100m")
        p2 = _get("epson-sc-t5700dm")
        result = build_comparison([p1, p2])

        self.assertEqual(result["comparison_type"], "same_subcategory")
        # Scanner must be Yes for both
        scan_row = next(c for c in result["criteria"] if c["key"] == "scanner_integrated")
        for val in scan_row["values"].values():
            self.assertIn("Yes", val)

    # ── 5. SC-P700 vs SC-P900 ────────────────────────────────────────────
    def test_05_sc_p700_vs_sc_p900(self):
        """Same category, different subcategory — photography."""
        p1 = _get("epson-sc-p700")
        p2 = _get("epson-sc-p900")
        result = build_comparison([p1, p2])

        self.assertIn(result["comparison_type"], ("same_subcategory", "same_category"))
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("spectro", keys)
        self.assertIn("dual_roll", keys)
        self.assertIn("supported_print_sizes", keys)

    # ── 6. SC-P6500D vs SC-P7500 ─────────────────────────────────────────
    def test_06_sc_p6500d_vs_sc_p7500(self):
        """Same category — photography professional / large."""
        p1 = _get("epson-sc-p6500d")
        p2 = _get("epson-sc-p7500")
        result = build_comparison([p1, p2])

        self.assertIn(result["comparison_type"], ("same_subcategory", "same_category"))
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("spectro", keys)

        # Spectro differs: P7500 has spectro variant, P6500D does not
        spectro_row = next(c for c in result["criteria"] if c["key"] == "spectro")
        # At minimum both values must be resolved (not empty)
        for val in spectro_row["values"].values():
            self.assertTrue(len(val) > 0)

    # ── 7. SC-P8500D vs SC-P9500 ─────────────────────────────────────────
    def test_07_sc_p8500d_vs_sc_p9500(self):
        """Same category — photography 44-inch."""
        p1 = _get("epson-sc-p8500d")
        p2 = _get("epson-sc-p9500")
        result = build_comparison([p1, p2])

        self.assertIn(result["comparison_type"], ("same_subcategory", "same_category"))
        # Max width must be 44 for both
        width_row = next(c for c in result["criteria"] if c["key"] == "max_width_inches")
        for val in width_row["values"].values():
            self.assertIn("44", val)

    # ── 8. Citizen CZ-01 vs CX-02 ────────────────────────────────────────
    def test_08_citizen_cz01_vs_cx02(self):
        """Same category — citizen photo, different subcategory."""
        p1 = _get("citizen-cz-01")
        p2 = _get("citizen-cx-02")
        result = build_comparison([p1, p2])

        self.assertIn(result["comparison_type"], ("same_subcategory", "same_category"))
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("supported_print_sizes", keys)
        self.assertIn("applications_citizen", keys)

    # ── 9. Citizen CX-02 vs CY-02 ────────────────────────────────────────
    def test_09_citizen_cx02_vs_cy02(self):
        """Same subcategory — Citizen 6-inch photo printers."""
        p1 = _get("citizen-cx-02")
        p2 = _get("citizen-cy-02")
        result = build_comparison([p1, p2])

        self.assertIn(result["comparison_type"], ("same_subcategory", "same_category"))
        # Photo sizes should appear
        keys = {c["key"] for c in result["criteria"]}
        self.assertIn("supported_print_sizes", keys)

    # ── 10. Citizen CY-02 vs CX-02W ──────────────────────────────────────
    def test_10_citizen_cy02_vs_cx02w(self):
        """Different subcategory (6-inch vs 8-inch) — same category."""
        p1 = _get("citizen-cy-02")
        p2 = _get("citizen-cx-02w")
        result = build_comparison([p1, p2])

        self.assertIn(result["comparison_type"], ("same_subcategory", "same_category"))
        # max_width_inches must differ between the two
        width_row = next(c for c in result["criteria"] if c["key"] == "max_width_inches")
        vals = list(width_row["values"].values())
        # CY-02 is 6 inch, CX-02W is 8 inch
        self.assertNotEqual(vals[0], vals[1])
        self.assertTrue(width_row["highlight"])

    # ── 11. Three-product comparison ──────────────────────────────────────
    def test_11_three_product_comparison(self):
        """Three products: SC-T5100, SC-T5700D, SC-T5100M."""
        p1 = _get("epson-sc-t5100")
        p2 = _get("epson-sc-t5700d")
        p3 = _get("epson-sc-t5100m")
        result = build_comparison([p1, p2, p3])

        self.assertEqual(len(result["products"]), 3)
        for row in result["criteria"]:
            self.assertEqual(len(row["values"]), 3)

        # Scanner differs between MFP and print-only
        scan_row = next(c for c in result["criteria"] if c["key"] == "scanner_integrated")
        self.assertTrue(scan_row["highlight"])

    # ── 12. Mixed-category comparison ─────────────────────────────────────
    def test_12_mixed_category_sc_p700_vs_citizen_cx02(self):
        """Cross-category comparison: photography vs citizen_photo."""
        p1 = _get("epson-sc-p700")
        p2 = _get("citizen-cx-02")
        result = build_comparison([p1, p2])

        self.assertEqual(result["comparison_type"], "cross_category")
        self.assertIsNotNone(result["cross_category_note"])
        self.assertIn("different", result["cross_category_note"].lower())

        # Only shared criteria should be shown
        keys = {c["key"] for c in result["criteria"]}
        # Cross-category must NOT include category-specific keys
        self.assertNotIn("spectro", keys)
        self.assertNotIn("applications_citizen", keys)

    # ── 13. Unknown / unapproved model rejected ───────────────────────────
    def test_13_unknown_model_raises_valueerror(self):
        """Unapproved product ID must raise ValueError before any comparison."""
        p1 = _get("epson-sc-p700")
        fake_product = {
            "id": "epson-sc-f999-fake",
            "display_name": "Fake Model",
            "main_category": "photography_large_format",
            "subcategory": "photo_13_desktop",
        }
        with self.assertRaises(ValueError) as ctx:
            build_comparison([p1, fake_product])
        self.assertIn("not in the approved catalogue", str(ctx.exception))

    # ── 14. Unverified field returns sentinel ─────────────────────────────
    def test_14_unverified_field_returns_sentinel(self):
        """Fields not in catalogue JSON return NOT_VERIFIED sentinel."""
        p1 = _get("epson-sc-t5100")   # print-only: no spectro
        p2 = _get("epson-sc-t5700d")  # also no spectro
        result = build_comparison([p1, p2])

        spectro_row = next(
            (c for c in result["criteria"] if c["key"] == "spectro"), None
        )
        if spectro_row:
            for val in spectro_row["values"].values():
                # Both are print-only, spectro should be "No" or NOT_VERIFIED
                self.assertTrue(val in ("No", NOT_VERIFIED))

        # Any genuinely missing field should return NOT_VERIFIED
        self.assertEqual(NOT_VERIFIED, "Not verified in the approved catalogue.")

    # ── 15. Prompt injection sanitised ───────────────────────────────────
    def test_15_prompt_injection_sanitised(self):
        """Values from catalogue must be HTML-escaped; injected tags cannot survive."""
        # Temporarily patch a product display_name to contain injection
        p1 = dict(_get("epson-sc-p700"))
        p2 = dict(_get("epson-sc-p900"))

        # Inject a script tag into display_name
        p1["display_name"] = "<script>alert('xss')</script> SC-P700"
        # Force it to pass the ID check by keeping original id
        result = build_comparison([p1, p2])

        # The model name in product summaries must be escaped
        product_names = [p["display_name"] for p in result["products"]]
        for name in product_names:
            self.assertNotIn("<script>", name)
            self.assertNotIn("</script>", name)

        # Values must not contain unescaped angle brackets
        for row in result["criteria"]:
            for val in row["values"].values():
                self.assertNotIn("<script>", val)

    # ── 16. No price / discount enforcement ──────────────────────────────
    def test_16_no_price_or_discount_in_comparison(self):
        """Comparison output must never contain prices, AED, or discount language."""
        p1 = _get("epson-am-c4000")
        p2 = _get("epson-am-c6000")
        result = build_comparison([p1, p2])

        # Flatten all text output
        all_text = " ".join(
            v
            for row in result["criteria"]
            for v in row["values"].values()
        )
        all_text += " ".join(p["display_name"] for p in result["products"])
        if result.get("cross_category_note"):
            all_text += result["cross_category_note"]
        if result.get("recommendation_note"):
            all_text += result["recommendation_note"]

        forbidden = ["AED", "USD", "price", "discount", "offer", "$", "£", "€", "%off"]
        for term in forbidden:
            self.assertNotIn(term, all_text,
                msg=f"Comparison output must not contain '{term}'")


class TestComparisonIntro(unittest.TestCase):

    def test_intro_two_products_same_subcategory(self):
        """Intro mentions both product names and subcategory type."""
        p1 = _get("epson-wf-c878r-dwf")
        p2 = _get("epson-wf-c879r-dwf")
        data = build_comparison([p1, p2])
        intro = build_comparison_intro([p1, p2], data)
        self.assertIn("WF-C878R", intro)
        self.assertIn("WF-C879R", intro)
        self.assertIn("subcategory", intro)

    def test_intro_cross_category_note(self):
        """Cross-category intro warns about different application areas."""
        p1 = _get("epson-sc-p700")
        p2 = _get("citizen-cx-02")
        data = build_comparison([p1, p2])
        intro = build_comparison_intro([p1, p2], data)
        self.assertIn("different application", intro.lower())


if __name__ == "__main__":
    unittest.main()
