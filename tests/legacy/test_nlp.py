"""
Test suite for Text Normalization, NLP Intent Extraction, and Zero-Hallucination Grounding.
"""

import unittest
from nlp.normalizer import normalize_text
from nlp.intent_extractor import analyze_input, INTENT_PRICE, INTENT_DISCOUNT, INTENT_BUSINESS_INFO, INTENT_TROUBLESHOOTING, INTENT_DISCOVERY
from nlp.grounding_validator import validate_grounding, UNVERIFIED_REFUSAL


class NlpAndGroundingTestCase(unittest.TestCase):
    def test_text_normalization_typos(self):
        # Misspelled input with typos
        raw = "i need a peinter for cadd drawing on 24 in paper from inova"
        norm = normalize_text(raw)
        self.assertIn("printer", norm["normalized_text"])
        self.assertIn("CAD", norm["normalized_text"])
        self.assertIn("Innova", norm["normalized_text"])
        self.assertIn("24-inch (A1)", norm["canonical_sizes"])
        self.assertTrue(len(norm["corrections_applied"]) >= 2)

    def test_intent_classification(self):
        # Price inquiry
        res1 = analyze_input("how much does the epson t3100 cost?")
        self.assertEqual(res1["intent"], INTENT_PRICE)

        # Discount inquiry
        res2 = analyze_input("can you offer any discount on am-c4000?")
        self.assertEqual(res2["intent"], INTENT_DISCOUNT)

        # Business hours
        res3 = analyze_input("what are your office timings and location in dubai?")
        self.assertEqual(res3["intent"], INTENT_BUSINESS_INFO)

        # Troubleshooting
        res4 = analyze_input("my prints have faint white streaks and nozzle lines")
        self.assertEqual(res4["intent"], INTENT_TROUBLESHOOTING)

    def test_entity_extraction_and_chips(self):
        res = analyze_input("we need a plotter for architectural cad plans")
        self.assertIn("cad_plotter", res["categories"])
        self.assertTrue(len(res["suggested_chips"]) > 0)
        # Should suggest standard sizes like A1 or A0
        self.assertTrue(any("A1" in chip or "A0" in chip for chip in res["suggested_chips"]))

    def test_zero_hallucination_unverified_category(self):
        # User asks for 3D printer which Kepler Tech does not supply
        intent_data = analyze_input("do you sell 3d printers or plastic filaments?")
        val = validate_grounding("We have 3d printers available", intent_data["normalized_text"], intent_data)
        self.assertEqual(val["status"], "RULE_F_UNVERIFIED_CATEGORY")
        self.assertIn(UNVERIFIED_REFUSAL, val["sanitized_response"])

    def test_zero_hallucination_price_prevention(self):
        # If an LLM hallucinated a price in AED
        intent_data = analyze_input("epson surecolor")
        val = validate_grounding("The price is AED 4500 with warranty", intent_data["normalized_text"], intent_data)
        self.assertEqual(val["status"], "PRICE_LEAK_PREVENTED")
        self.assertIn("pricing isn’t available through this chat", val["sanitized_response"])


if __name__ == "__main__":
    unittest.main()
