"""
Comprehensive Automated Test Suite for SalesAI Architectural Upgrades.

Verifies:
1. Universal Typo Normalizer (maenta -> magenta, canvs -> canvas, citizon -> Citizen)
2. Category Metric Isolation (Office A3 printers do not output 4x6" photo running costs)
3. Multi-Question Handling (Speed + Cost both answered in one turn)
4. WhatsApp Message Buffer Aggregation
5. Clean Formatting & No Unwanted Stars
6. Natural Direct Purchase Intent Handling
"""

import pytest
from nlp.fuzzy_normalizer import fuzzy_normalizer
from nlp.normalizer import normalize_text
from catalog.cost_per_print_calculator import CostPerPrintCalculator
from conversation.message_buffer import MessageSessionBuffer
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator


def test_universal_typo_normalizer_colors_and_media():
    """Verify fuzzy normalizer resolves misspelled colors, media, and brands without hardcoding."""
    # Test colors
    assert fuzzy_normalizer.normalize_color("maenta") == "magenta"
    assert fuzzy_normalizer.normalize_color("megenta") == "magenta"
    assert fuzzy_normalizer.normalize_color("mgenta") == "magenta"
    assert fuzzy_normalizer.normalize_color("cyn") == "cyan"
    assert fuzzy_normalizer.normalize_color("yelow") == "yellow"

    # Test full text token normalization
    res = normalize_text("i need this maenta ink and a canvs roll for my citizon printer")
    assert "magenta" in res["normalized_text"]
    assert "canvas" in res["normalized_text"]
    assert "Citizen" in res["normalized_text"]


def test_category_metric_isolation_for_office_printers():
    """Verify that comparing office printers does NOT display 4x6 photo running costs."""
    from catalog.catalogue_loader import catalogue_loader
    wf1 = catalogue_loader.get_by_id("epson-wf-c878r-dwf")
    wf2 = catalogue_loader.get_by_id("epson-wf-c879r-dwf")

    assert wf1 is not None and wf2 is not None

    table_md = CostPerPrintCalculator.build_investment_and_running_cost_comparison([wf1, wf2])

    # Must NOT mention 4x6" running cost for A3 office machines
    assert "Running Cost (4x6″)" not in table_md
    assert "Running Cost (4x6\")" not in table_md
    # Must use category-appropriate office page metrics
    assert "Running Cost (ISO Page)" in table_md or "High-Yield" in table_md


def test_multi_question_handling_speed_and_cost():
    """Verify asking for speed AND cost in one turn answers BOTH."""
    state = ConversationState(session_id="test_multi_q_speed_cost")
    state.category = "office_printer"
    state.candidate_products = [
        {"id": "epson-wf-c878r-dwf", "display_name": "Epson WorkForce Pro WF-C878R DWF", "print_speed": "25 ppm", "category": "office_printer"},
        {"id": "epson-wf-c879r-dwf", "display_name": "Epson WorkForce Pro WF-C879R DWF", "print_speed": "26 ppm", "category": "office_printer"},
    ]

    res = orchestrator.process_turn(
        "What is the printing speed, and which option would be better for me in terms of initial investment and ongoing printing costs?",
        state=state
    )

    reply = res.get("reply", "")
    # Both speed and cost must be answered
    assert "speed" in reply.lower() or "ppm" in reply.lower()
    assert "investment" in reply.lower() or "cost" in reply.lower()


def test_message_buffer_combines_rapid_whatsapp_messages():
    """Verify message buffer aggregates consecutive rapid messages for the same session."""
    buf = MessageSessionBuffer(window_seconds=10.0)
    session_id = "test_whatsapp_session_123"

    buf.add_message(session_id, "i want the media rolls for this")
    combined = buf.get_combined_prompt(session_id, "i need this magenta ink")

    assert "i want the media rolls for this" in combined
    assert "i need this magenta ink" in combined


def test_direct_purchase_intent_is_clean_and_concise():
    """Verify purchase intent returns a direct natural link rather than corporate handover essay."""
    state = ConversationState(session_id="test_clean_order")
    state.active_consumable = {
        "name": "Epson Dye Sublimation Magenta Ink",
        "title": "Epson Dye Sublimation Magenta Ink",
        "sku": "C13T49N300",
        "price": 110.0,
        "price_str": "AED 110.00",
        "vat_note": "(Excl. VAT)",
        "product_url": "https://www.keplertechllc.com/product/epson-dye-sublimation-magenta-t49n300-ink/"
    }

    res = orchestrator.process_turn("order this", state=state)
    reply = res.get("reply", "")

    assert "order" in reply.lower()
    assert "magenta" in reply.lower()
    # Must NOT have corporate template headings with emoji bullets
    assert "🛒 **1. Official Online Store:**" not in reply
    assert len(res.get("consumable_cards", [])) >= 1 or "website" in reply.lower() or "store" in reply.lower()


def test_media_rolls_discovery_and_fuzzy_typo():
    """Verify 'list aall the medias rolls' normalizes typos and returns media roll collections with cards."""
    res = orchestrator.process_turn("list aall the medias rolls", session_id="test_media_rolls_unit")
    assert res.get("source") == "route:media_discovery:rolls"
    reply = res.get("reply", "")
    assert "Photographic Rolls" in reply or "media rolls" in reply.lower()
    assert "Olmec" in reply or "Innova" in reply
    cards = res.get("consumable_cards", [])
    assert len(cards) >= 4
    for card in cards:
        assert card.get("sku")
        assert "https://www.keplertechllc.com" in (card.get("url") or "")
