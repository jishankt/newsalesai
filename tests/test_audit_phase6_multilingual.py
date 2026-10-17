"""
Phase 6 Test Suite: Multilingual NLU, Entity Extraction & Native Responses.

Validates:
1. Script-based and dialect language detection for Arabic (ar), Hindi (hi), and Malayalam (ml).
2. Inbound normalization translating non-English regional phrases to English for NLU entity extraction.
3. Outbound translation returning native Arabic, Hindi, and Malayalam responses rather than 100% English fallbacks.
"""

import unittest
from nlp.multilingual import detect_language, normalize_multilingual, translate_to_language
from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


class TestAuditPhase6Multilingual(unittest.TestCase):

    def test_multilingual_language_detection(self):
        """Must correctly detect Arabic, Hindi, Malayalam, and English."""
        self.assertEqual(detect_language("أحتاج إلى طابعة مكتبية سريعة"), "ar")
        self.assertEqual(detect_language("मुझे एक अच्छा ऑफिस प्रिंटर चाहिए"), "hi")
        self.assertEqual(detect_language("എനിക്ക് ഒരു ഓഫീസ് പ്രിന്റർ വേണം"), "ml")
        self.assertEqual(detect_language("oru photo printer venam"), "ml")
        self.assertEqual(detect_language("I need an A4 office printer"), "en")

    def test_multilingual_inbound_normalization(self):
        """Inbound normalization must extract English concepts so downstream NLU recognizes category/slots."""
        norm_ar, _, lang_ar = normalize_multilingual("أحتاج إلى طابعة مكتبية سريعة", return_lang=True)
        self.assertEqual(lang_ar, "ar")
        self.assertTrue(
            any(k in norm_ar.lower() for k in ["office", "printer"]),
            f"Expected 'office' or 'printer' in normalized Arabic text, got: {norm_ar}"
        )

        norm_hi, _, lang_hi = normalize_multilingual("मुझे एक अच्छा ऑफिस प्रिंटर चाहिए", return_lang=True)
        self.assertEqual(lang_hi, "hi")
        self.assertTrue(
            any(k in norm_hi.lower() for k in ["office", "printer"]),
            f"Expected 'office' or 'printer' in normalized Hindi text, got: {norm_hi}"
        )

        norm_ml, _, lang_ml = normalize_multilingual("എനിക്ക് ഒരു ഓഫീസ് പ്രിന്റർ വേണം", return_lang=True)
        self.assertEqual(lang_ml, "ml")
        self.assertTrue(
            any(k in norm_ml.lower() for k in ["office", "printer"]),
            f"Expected 'office' or 'printer' in normalized Malayalam text, got: {norm_ml}"
        )

    def test_outbound_translation_returns_native_script(self):
        """Outbound translation must return native script text for Arabic, Hindi, and Malayalam."""
        reply_en = "Welcome to Kepler Tech! Do you require standard A4 output or large-format A3 output for your office documents?"

        reply_ar = translate_to_language(reply_en, "ar")
        self.assertTrue(any('\u0600' <= c <= '\u06FF' for c in reply_ar), f"Expected Arabic script, got: {reply_ar}")

        reply_hi = translate_to_language(reply_en, "hi")
        self.assertTrue(any('\u0900' <= c <= '\u097F' for c in reply_hi), f"Expected Devanagari script, got: {reply_hi}")

        reply_ml = translate_to_language(reply_en, "ml")
        self.assertTrue(any('\u0D00' <= c <= '\u0D7F' for c in reply_ml), f"Expected Malayalam script, got: {reply_ml}")

    def test_end_to_end_arabic_office_printer(self):
        """Arabic input 'أحتاج إلى طابعة مكتبية سريعة' must recognize office printer and reply in Arabic."""
        state = ConversationState(session_id="test-multilingual-ar-1")
        res = orchestrator.process_turn("أحتاج إلى طابعة مكتبية سريعة", state=state)
        reply = res.get("reply", "")

        # Category must be recognized as office_printer or office
        self.assertIn(state.category, ["office_printer", "office_enterprise", "office_workforce", "office"])
        # Reply must contain Arabic script
        self.assertTrue(
            any('\u0600' <= c <= '\u06FF' for c in reply),
            f"Expected native Arabic response, but got 100% English: {reply}"
        )


if __name__ == "__main__":
    unittest.main()
