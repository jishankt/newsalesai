"""
Unit and Integration Tests for Session 99e948f8 Fixes:
1. Dimension & typo handling (65" rool -> 64-inch photo roll, SC-P20500).
2. Comparison disambiguation: SC-P6500D vs SC-P8500DM has exactly 2 models (no phantom SC-P8500D).
3. Table formatting cleanliness (no ugly 'Not verified' rows for spectro or applications).
4. Human handover escalation with typo tolerance ('I need talk in real humen') and immediate alert acknowledgment.
5. Conversational memory recall ('the last time I told one printer which one?').
"""
import unittest
from app import app
from domain.state_store import state_manager
from domain.conversation_state import ConversationState
from catalog.catalogue_resolver import find_mentioned_catalogue_products
from catalog.catalogue_loader import catalogue_loader
from catalog.comparison_engine import build_comparison, format_comparison_markdown_table
from conversation.normalizer import extract_deterministic_requirements, normalize_category
from catalog.subcategory_resolver import resolve_subcategory
from agent.orchestrator import orchestrator


class TestLiveChatSessionFixes(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_01_dimension_and_typo_resolution(self):
        """Verify '65\" rool' resolves to 64-inch photo roll and maps to SC-P20500."""
        msg = '65" rool'
        cat = normalize_category(msg, current_category="photography_large_format")
        self.assertEqual(cat, "photography_large_format")

        reqs, _ = extract_deterministic_requirements(
            msg, category="photography_large_format", awaiting_field="photo_form_factor"
        )
        self.assertEqual(reqs.get("print_width"), 64)
        self.assertEqual(reqs.get("photo_form_factor"), "large")

        subcat = resolve_subcategory("photography_large_format", reqs)
        self.assertEqual(subcat, "photo_64_production")

        # Full orchestrator turn
        state = ConversationState(session_id="test-dim-65")
        state.category = "photography_large_format"
        state.awaiting_field = "photo_form_factor"
        res = orchestrator.process_turn(
            raw_message=msg,
            session_id="test-dim-65",
            history=[],
            state=state,
        )
        self.assertIn("Epson SureColor SC-P20500", res["reply"])
        self.assertTrue(any(c.get("id") == "epson-sc-p20500" for c in res["product_cards"]))

    def test_02_comparison_no_phantom_product(self):
        """Verify comparing SC-P6500D and SC-P8500DM yields exactly 2 products."""
        msg = "Compare Epson SureColor SC-P6500D and Epson SureColor SC-P8500DM"
        mentioned = find_mentioned_catalogue_products(msg)
        self.assertEqual(len(mentioned), 2)
        matched_ids = {p["id"] for p in mentioned}
        self.assertEqual(matched_ids, {"epson-sc-p6500d", "epson-sc-p8500dm"})
        self.assertNotIn("epson-sc-p8500d", matched_ids)

        # Comparison table formatting
        p1 = catalogue_loader.get_by_id("epson-sc-p6500d")
        p2 = catalogue_loader.get_by_id("epson-sc-p8500dm")
        data = build_comparison([p1, p2])
        table = format_comparison_markdown_table([p1, p2], data)

        self.assertIn("No — not equipped", table)
        self.assertNotIn("Not verified in the approved catalogue.", table)
        self.assertIn("Commercial Photo", table)

    def test_03_human_handover_with_typo(self):
        """Verify 'I need talk in real humen' triggers handover and returns alert message."""
        session_id = "test-humen-handover"
        res = self.client.post("/api/chat", json={
            "session_id": session_id,
            "message": "I need talk in real humen"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data.get("handover_triggered"))
        self.assertIn("notified our Live Sales Desk", data.get("reply"))

        # Check state
        state = state_manager.get(session_id)
        self.assertIsNotNone(state)
        self.assertTrue(state.handover_triggered)
        self.assertEqual(state.handover_reason, "customer_requested_human")

    def test_04_conversational_memory_recall(self):
        """Verify bot remembers previously mentioned printer when asked 'the last time I told one printer which one?'"""
        state = ConversationState(session_id="test-memory-recall")

        # Turn 1: User asks for SC-P6500D
        t1 = orchestrator.process_turn(
            raw_message="I need Epson SureColor SC-P6500D",
            session_id="test-memory-recall",
            history=[],
            state=state,
        )
        self.assertEqual(state.active_product_id, "epson-sc-p6500d")

        # Turn 2: User asks for discount
        t2 = orchestrator.process_turn(
            raw_message="I need discount",
            session_id="test-memory-recall",
            history=list(state.history_turns),
            state=state,
        )

        # Turn 3: User asks which printer was mentioned earlier
        t3 = orchestrator.process_turn(
            raw_message="the last time I told one printer which one?",
            session_id="test-memory-recall",
            history=list(state.history_turns),
            state=state,
        )
        self.assertIn("Epson SureColor SC-P6500D", t3["reply"])
        self.assertEqual(t3["source"], "route:conversational_memory_recall")
        self.assertTrue(len(t3["product_cards"]) > 0)
        self.assertEqual(t3["product_cards"][0]["id"], "epson-sc-p6500d")

    def test_06_scanner_comparison_no_print_resolution_or_multifunction(self):
        """Verify comparing standalone scanners omits Print Resolution and Multifunction claims."""
        msg = "Compare Epson WorkForce WF DS-60000 Color Document Scanner and Epson WorkForce WF DS-60000N Color Document Scanner"
        state = ConversationState(session_id="test-scanner-comp")
        state.category = "scanners"
        state.subcategory = "hybrid_scanners"
        res = orchestrator.process_turn(raw_message=msg, session_id="test-scanner-comp", state=state)
        reply = res.get("reply", "")
        self.assertNotIn("Print Resolution (DPI)", reply)
        self.assertNotIn("Multifunction: print, scan, copy", reply)
        self.assertIn("Scanning Speed", reply)
        self.assertIn("Optical Resolution", reply)

    def test_07_scanner_recommendation_intro_dynamic_scanners(self):
        """Verify recommendation intro for scanners says 'scanners' and not 'printers'."""
        state = ConversationState(session_id="test-scanner-intro")
        r1 = orchestrator.process_turn("i need scanner", session_id="test-scanner-intro", state=state)
        self.assertEqual(state.category, "scanners")
        r2 = orchestrator.process_turn("both", session_id="test-scanner-intro", state=state)
        reply = r2.get("reply", "")
        self.assertIn("scanners", reply.lower())
        self.assertNotIn("catalogue printers", reply.lower())

    def test_08_buy_printer_from_scanner_state_clears_active_scanner(self):
        """Verify user saying 'i want to buy a printer' when active product is a scanner transitions cleanly to printer qualification."""
        state = ConversationState(session_id="test-cat-switch-buy")
        state.category = "scanners"
        state.active_product = catalogue_loader.get_by_id("epson-workforce-ds-60000n")
        state.active_product_id = "epson-workforce-ds-60000n"

        res = orchestrator.process_turn("i want to buy a printer", session_id="test-cat-switch-buy", state=state)
        reply = res.get("reply", "")
        # Must not quote or display the DS-60000N scanner
        self.assertNotIn("DS-60000N", reply)
        self.assertIsNone(state.active_product)
        # Must prompt for what they want to print
        self.assertIn("print", reply.lower())
        self.assertIsNone(state.category)

    def test_09_model_number_typo_fuzzy_resolution(self):
        """Verify repeated-character and typo queries like 'wf c55890' resolve to WF-C5890 and override previous active product."""
        # 1. Direct resolver check
        prods = find_mentioned_catalogue_products("what is the price wf c55890")
        self.assertEqual(len(prods), 1)
        self.assertEqual(prods[0]["id"], "epson-wf-c5890-dwf")

        # 2. End-to-end turn check where AM-C550 was previous active product
        state = ConversationState(session_id="test-typo-c55890")
        am_c550 = catalogue_loader.get_by_id("epson-am-c550")
        state.active_product = am_c550
        state.active_product_id = "epson-am-c550"

        res = orchestrator.process_turn("what is the price wf c55890", session_id="test-typo-c55890", state=state)
        reply = res.get("reply", "")
        # Must resolve the typo while withholding commercial details.
        self.assertIn("WF-C5890", reply)
        self.assertNotIn("AM-C550", reply)
        self.assertNotIn("1,656", reply)
        self.assertEqual(state.active_product_id, "epson-wf-c5890-dwf")


if __name__ == "__main__":
    unittest.main()
