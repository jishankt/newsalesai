"""
TDD Tests for Phase 8 (P1): Competitor Consumable Rejection in routes/consumables_route.py.
Audit Finding:
- routes/consumables_route.py lacks the competitor brand filter present in routes/product_route.py:22.
- Inquiries for HP, Canon, Xerox, Brother consumables must be politely rejected with an authorized partner disclaimer.
"""

import pytest
from domain.conversation_types import LLMUnderstanding
from domain.conversation_state import ConversationState
from routes.consumables_route import handle as handle_consumables


def test_reject_hp_toner_in_consumables_route():
    """Inquiry for HP toner should return explicit rejection without fallback/hallucination."""
    state = ConversationState(session_id="test-sess-hp")
    understanding = LLMUnderstanding(
        intent="consumables_inquiry",
        entities={"brand": "HP"}
    )
    result = handle_consumables(
        understanding=understanding,
        state=state,
        raw_message="Do you sell HP LaserJet toner cartridges?"
    )
    assert result is not None
    assert "HP" in result.reply
    assert "Kepler Tech" in result.reply
    assert any(b in result.reply for b in ["Epson", "Citizen"])
    assert not result.consumable_cards
    assert result.source in ("route:consumables:unsupported_brand", "route:unsupported_brand")


def test_reject_canon_ink_in_consumables_route():
    """Inquiry for Canon imagePROGRAF ink should be rejected with authorized partner notice."""
    state = ConversationState(session_id="test-sess-canon")
    understanding = LLMUnderstanding(
        intent="consumables_inquiry",
        entities={"brand": "Canon"}
    )
    result = handle_consumables(
        understanding=understanding,
        state=state,
        raw_message="I need replacement ink for Canon imageprograf"
    )
    assert result is not None
    assert "Canon" in result.reply
    assert "Kepler Tech" in result.reply
    assert not result.consumable_cards
    assert result.source in ("route:consumables:unsupported_brand", "route:unsupported_brand")


def test_reject_xerox_brother_in_consumables_route():
    """Inquiry for Xerox or Brother consumables should be rejected politely."""
    state = ConversationState(session_id="test-sess-xerox")
    understanding = LLMUnderstanding(intent="consumables_inquiry")
    result = handle_consumables(
        understanding=understanding,
        state=state,
        raw_message="Looking for Brother toner bottles"
    )
    assert result is not None
    assert "Brother" in result.reply
    assert not result.consumable_cards
    assert result.source in ("route:consumables:unsupported_brand", "route:unsupported_brand")
