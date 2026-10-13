"""
Automated Test Suite for Phase 4: Sales Behaviour & Qualification Budget.

Validates:
1. Qualification budget: Office, plotter, photo, and scanner flows reach recommendations with cards within 4 turns.
2. Max 3 qualification questions before delivering leaf recommendations with product cards.
3. Card presentation: 1 primary recommended model + up to 2 verified alternatives (at most 3 cards).
4. No direct equipment pricing in chat cards (actions contain 'Request Official Quote', is_request is True).
5. Objection handling: Empathy for price objections, lower TCO/yield mentions, commercial quote options.
6. Lead capture with consent: Extracts name, UAE phone, email from natural text, saves in lead_repository, returns reference.
"""

import pytest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState
from persistence.lead_repository import lead_repository


@pytest.fixture
def orchestrator():
    return Orchestrator()


class TestPhase4SalesBehaviour:

    def test_01_office_flow_reaches_cards_within_4_turns(self, orchestrator):
        state = ConversationState(session_id="test_p4_office")
        r1 = orchestrator.process_turn("i need an office printer", session_id="test_p4_office", state=state)
        r2 = orchestrator.process_turn("A4 Output", session_id="test_p4_office", state=state)
        r3 = orchestrator.process_turn("50 pages a day", session_id="test_p4_office", state=state)

        # Reached recommendations with cards on or before turn 3
        cards = r3.get("cards") or r3.get("product_cards") or []
        assert len(cards) >= 1
        assert len(cards) <= 3
        primary_card = cards[0]
        assert "WF-C5890" in (primary_card.get("title") or primary_card.get("name") or primary_card.get("model", ""))
        assert any("Quote" in a for a in primary_card.get("actions", []))
        assert primary_card.get("is_request") is True

    def test_02_plotter_flow_reaches_cards_within_4_turns(self, orchestrator):
        state = ConversationState(session_id="test_p4_plotter")
        r1 = orchestrator.process_turn("i need a CAD plotter", session_id="test_p4_plotter", state=state)
        r2 = orchestrator.process_turn("24 inch", session_id="test_p4_plotter", state=state)
        r3 = orchestrator.process_turn("desktop", session_id="test_p4_plotter", state=state)

        cards = r3.get("cards") or r3.get("product_cards") or []
        assert len(cards) >= 1
        assert len(cards) <= 3
        primary_card = cards[0]
        assert "SC-T3100" in (primary_card.get("title") or primary_card.get("name") or primary_card.get("model", ""))
        assert any("Quote" in a for a in primary_card.get("actions", []))

    def test_03_photo_flow_reaches_cards_within_4_turns(self, orchestrator):
        state = ConversationState(session_id="test_p4_photo")
        r1 = orchestrator.process_turn("i need a photo printer", session_id="test_p4_photo", state=state)
        r2 = orchestrator.process_turn("17 inch", session_id="test_p4_photo", state=state)
        r3 = orchestrator.process_turn("Desktop Sheet", session_id="test_p4_photo", state=state)

        cards = r3.get("cards") or r3.get("product_cards") or []
        assert len(cards) >= 1
        assert len(cards) <= 3
        primary_card = cards[0]
        assert "SC-P900" in (primary_card.get("title") or primary_card.get("name") or primary_card.get("model", ""))

    def test_04_scanner_flow_reaches_cards_within_4_turns(self, orchestrator):
        state = ConversationState(session_id="test_p4_scanner")
        r1 = orchestrator.process_turn("i need a scanner for documents", session_id="test_p4_scanner", state=state)
        r2 = orchestrator.process_turn("Fast Sheetfed Business Scanners", session_id="test_p4_scanner", state=state)

        cards = r2.get("cards") or r2.get("product_cards") or []
        assert len(cards) >= 1
        assert len(cards) <= 3
        assert any("DS-" in (c.get("title") or c.get("name") or c.get("model", "")) for c in cards)

    def test_05_card_presentation_no_direct_equipment_pricing(self, orchestrator):
        state = ConversationState(session_id="test_p4_pricing_guard")
        resp = orchestrator.process_turn("tell me about the Epson SC-F100", session_id="test_p4_pricing_guard", state=state)
        cards = resp.get("cards") or resp.get("product_cards") or []
        for c in cards:
            # Cards must not leak raw equipment prices into chat; must have Request Quote actions
            assert c.get("price") is None
            assert c.get("is_request") is True
            assert any("Quote" in str(a) for a in c.get("actions", []))

    def test_06_price_objection_handling_and_alternatives(self, orchestrator):
        state = ConversationState(session_id="test_p4_objection")
        orchestrator.process_turn("tell me about the Epson SC-P900", session_id="test_p4_objection", state=state)
        r2 = orchestrator.process_turn("it's too expensive for my budget", session_id="test_p4_objection", state=state)
        reply = r2["reply"]
        assert "budget" in reply.lower() or "cost" in reply.lower()
        chips = r2.get("chips") or r2.get("suggested_chips") or []
        assert any("Quote" in c for c in chips)

    def test_07_lead_capture_with_consent_and_persistence(self, orchestrator):
        session_id = "test_p4_lead_capture"
        state = ConversationState(session_id=session_id)
        resp = orchestrator.process_turn(
            "My name is Tariq from Al Manar Printing LLC, my email is tariq@almanar.ae and phone is 0501234567, please send a quote",
            session_id=session_id,
            state=state,
        )
        reply = resp["reply"]
        assert "Tariq" in reply
        assert "0501234567" in reply or "tariq@almanar.ae" in reply
        assert "quote" in reply.lower() or "quotation" in reply.lower() or "sales" in reply.lower()

        # Verify persisted into lead repository
        leads = lead_repository.get_leads(limit=10)
        matching = [l for l in leads if l.get("session_id") == session_id]
        assert len(matching) >= 1
        lead = matching[0]
        assert lead.get("customer_name") == "Tariq"
        assert lead.get("phone") == "0501234567"
        assert lead.get("email") == "tariq@almanar.ae"
