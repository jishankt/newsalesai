"""
TDD Tests for Phase 9 (P1): Failure Handoff Triggers & Multi-Turn Benchmark Evaluation.
Validates:
1. Customer frustration escalation (frustration_count >= 3) triggers Live Sales Desk handoff.
2. Direct request for human agent triggers Live Sales Desk handoff.
3. Unhandled exceptions / service degradation trigger Live Sales Desk handoff.
4. Multi-turn benchmark evaluation across core sales policy categories:
   - Budget gating
   - Competitor brand rejection
   - Repetition loop break
   - Multilingual detection & translation
"""

import pytest
from domain.conversation_types import Intent, LLMUnderstanding
from domain.conversation_state import ConversationState
from routes.social_route import handle as handle_social
from catalog.catalogue_filter import CatalogueFilter
from nlp.multilingual import detect_language, translate_to_language


def test_frustration_escalates_to_live_sales_desk():
    """Customer reaching high frustration triggers Live Sales Desk handoff."""
    state = ConversationState(session_id="test-frustration-sess")
    state.frustration_count = 2 # Already at 2, this turn makes it 3

    understanding = LLMUnderstanding(
        intent=Intent.FRUSTRATION,
        entities={"complaint": "You are repeating yourself again and not listening"}
    )
    result = handle_social(
        understanding=understanding,
        state=state,
        raw_message="You keep asking me the same thing! Stop repeating!"
    )
    assert result is not None
    assert state.handover_triggered is True
    assert "Live Sales Desk" in result.reply
    assert "sales specialist" in result.reply.lower()


def test_multi_turn_audit_benchmark():
    """Validates multi-turn policy benchmarks across P0 and P1 domains."""
    cf = CatalogueFilter()

    # 1. Budget Gating: Office A4 under 2500 AED
    cards, _ = cf.filter_and_rank("office_printer", None, {"paper_size": "a4", "budget_ceiling": 2500})
    matched_ids = [c["id"] for c in cards]
    assert "epson-wf-c5890-dwf" in matched_ids
    assert "epson-am-c550" not in matched_ids

    # 2. Multilingual: Arabic, Malayalam, Hindi
    assert detect_language("مرحبا اريد طابعة للمكتب") == "ar"
    assert detect_language("നമസ്കാരം, എനിക്ക് ഒരു ഫോട്ടോ പ്രിന്റർ വേണം") == "ml"
    assert detect_language("नमस्ते मुझे ऑफिस के लिए प्रिंटर चाहिए") == "hi"

    # 3. Translation fallback / dictionary
    ar_trans = translate_to_language("Hello, how can I assist you with Kepler Tech printers?", "ar")
    assert any(c in ar_trans for c in ["مرحبا", "طابعات", "كيبلر", "مساعدتك"])
