"""
Regression test suite for session d6170f27-df40-44b4-8412-1964343b9f5c.
Verifies fixes for:
1. Quoted and metric photo dimension extraction (6"x4", 10cm X 15cm -> 4x6).
2. Portability brand and subcategory inference for Citizen photo printers.
3. Comparison grammar ("all" for 3+ models) and markdown table inclusion in text.
4. Cost-per-print (CPP) inquiry routing vs machine acquisition price.
5. Consumable page yield query answering ISO yields rather than repeating SKU lists.
6. Product and general warranty inquiry routing to warranty terms rather than office location.
7. Genuine consumable pricing resolution for Citizen CZ-01 media (AED 450.00).
"""

import pytest
from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer
from conversation.normalizer import extract_deterministic_requirements
from conversation.next_question_engine import NextQuestionEngine
from catalog.comparison_engine import build_comparison, build_comparison_intro, format_comparison_markdown_table
from catalog.catalogue_resolver import build_approved_comparison_response
from catalog.price_resolver import price_resolver
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator


def test_quoted_and_metric_photo_dimension_extraction():
    """Verify quoted inches and metric dimensions are normalized to canonical photo sizes."""
    # 6"x4"
    sizes_quoted = CanonicalEntityNormalizer.extract_photo_sizes('portable one, to print maximum of 6"x4"')
    assert "4x6" in sizes_quoted

    # 10cm X 15cm
    sizes_metric = CanonicalEntityNormalizer.extract_photo_sizes('portable one, to print maximum of 10cm X 15cm')
    assert "4x6" in sizes_metric

    # 10 x 15 cm
    sizes_space = CanonicalEntityNormalizer.extract_photo_sizes('photos 10 x 15 cm')
    assert "4x6" in sizes_space

    # 13x18cm -> 5x7
    assert "5x7" in CanonicalEntityNormalizer.extract_photo_sizes('13x18cm prints')

    # 15x20cm -> 6x8
    assert "6x8" in CanonicalEntityNormalizer.extract_photo_sizes('15x20cm prints')


def test_portable_photo_qualification_infers_citizen():
    """Verify that specifying portable photo printer does not get trapped asking Epson vs Citizen."""
    reqs, _ = extract_deterministic_requirements(
        text='portable one, to print maximum of 6"x4"',
        category="photo_printer"
    )
    assert reqs.get("print_sizes") == ["4x6"]
    assert reqs.get("photo_brand") == "citizen"

    # Next question engine should complete compact photo qualification without looping
    next_q = NextQuestionEngine.get_next_question(
        category="photo_printer",
        requirements=reqs,
        unresolved_fields=[]
    )
    # Qualification should be complete (ready to recommend CZ-01)
    assert next_q is None


def test_comparison_grammar_and_markdown_table():
    """Verify comparison grammar uses 'all' for 3 models and output contains markdown table."""
    p1 = {"id": "epson-sc-t5100", "display_name": "Epson SureColor SC-T5100", "main_category": "technical_large_format", "subcategory": "cad_technical"}
    p2 = {"id": "epson-sc-t5405", "display_name": "Epson SureColor SC-T5405", "main_category": "technical_large_format", "subcategory": "cad_technical"}
    p3 = {"id": "epson-sc-t5700d", "display_name": "Epson SureColor SC-T5700D", "main_category": "technical_large_format", "subcategory": "cad_technical"}

    data = build_comparison([p1, p2, p3])
    intro = build_comparison_intro([p1, p2, p3], data)

    # Must NOT use 'both' for 3 items
    assert "both" not in intro.lower()
    assert "all from the same product subcategory" in intro

    # Verify markdown table formatter
    table_md = format_comparison_markdown_table([p1, p2, p3], data)
    assert "| Specification |" in table_md
    assert "Epson SureColor SC-T5100" in table_md
    assert "Epson SureColor SC-T5405" in table_md
    assert "Epson SureColor SC-T5700D" in table_md

    # Verify build_approved_comparison_response returns the table in reply_text
    reply_text, cards, _ = build_approved_comparison_response([p1, p2, p3])
    assert "| Specification |" in reply_text
    assert len(cards) == 3


def test_citizen_cz01_media_pricing():
    """Verify Citizen CZ-01 media (CZ-MS46) returns live verified AED 295.00 price and correct URL."""
    price_info = price_resolver.get_price_info("CZ-MS46")
    assert price_info["price"] == 295.0
    assert "295.00" in price_info["price_str"]
    assert price_info["is_request"] is False
    assert "citizen-cz-ms46-4x-6" in price_info["url"]

    # Verify CZ-MS458 (4.5x8) media
    cz458_info = price_resolver.get_price_info("CZ-MS458")
    assert cz458_info["price"] == 340.0
    assert "340.00" in cz458_info["price_str"]

    # Verify CX2.4X6 media
    cx_info = price_resolver.get_price_info("CX2.4X6")
    assert cx_info["price"] == 490.0

    # Verify Maintenance box URL does not get overwritten by printer brochure
    from agent.tool_executor import catalog_tool_executor
    mb_card = catalog_tool_executor.format_card({
        "_id": "C12C937181",
        "sku": "C12C937181",
        "name": "Epson Maintenance Box (AM-C4000/C5000/C6000) - C12C937181",
        "website_url": "https://www.keplertechllc.com/product/c12c937181-epson-maintenance-box-am-c4000-5000-6000/"
    }, card_type="consumable")
    assert "c12c937181-epson-maintenance-box" in mb_card["url"]
    assert "am-c4000-printer" not in mb_card["url"]
    assert mb_card["price"] == 180.0


def test_other_model_media_price_inquiry():
    """Verify asking 'what about other model media price?' returns CY-02, CX-02, and CX-02W media prices and links."""
    state = ConversationState(session_id="test_other_media_session")
    state.category = "citizen_photo"
    response = orchestrator.process_turn("what about other model media price?", state=state)
    assert response.get("source") == "route:consumable_price_inquiry"
    msg = response.get("message", "")
    assert "625.00" in msg
    assert "490.00" in msg
    assert "975.00" in msg
    assert "CY-MS46" in msg
    assert "https://www.keplertechllc.com/product/citizen-cy-ms46-4x6/" in msg


def test_cost_per_print_orchestrator_route():
    """Verify 'what is the per print cost of each one' routes to cost_per_print, not price disclaimer."""
    state = ConversationState(session_id="test_cpp_session")
    state.category = "office_printer"
    state.active_product_id = "epson-am-c5000"
    state.active_product = {
        "id": "epson-am-c5000",
        "display_name": "Epson WorkForce Enterprise AM-C5000",
        "category": "office_printer"
    }

    response = orchestrator.process_turn(
        "what is the per print cost of each one",
        state=state
    )

    assert response.get("source") == "route:cost_per_print"
    # Must contain CPP information, NOT enterprise quote disclaimer
    msg = response.get("message", "").lower()
    assert "cost-per-page" in msg or "cost per page" in msg or "cost per print" in msg
    assert "is not listed for direct online checkout" not in msg
    assert "0.02" in msg


def test_print_yield_orchestrator_route():
    """Verify asking for print yield returns ISO page yields rather than repeating SKU list."""
    state = ConversationState(session_id="test_yield_session")
    state.category = "office_printer"
    state.active_product_id = "epson-am-c4000"
    state.active_product = {
        "id": "epson-am-c4000",
        "display_name": "Epson WorkForce Enterprise AM-C4000",
        "category": "office_printer"
    }

    response = orchestrator.process_turn(
        "what will be the print yeild of each color?",
        state=state
    )

    assert response.get("source") == "route:consumables"
    # Must contain page yield numbers
    msg = response.get("message", "")
    assert "31,500" in msg or "28,000" in msg or "iso pages" in msg.lower()
    assert "Maintenance Box" in msg


def test_warranty_orchestrator_route():
    """Verify asking for warranty returns warranty terms rather than Dubai headquarters location."""
    state = ConversationState(session_id="test_warranty_session")
    state.category = "office_printer"
    state.active_product_id = "epson-am-c4000"
    state.active_product = {
        "id": "epson-am-c4000",
        "display_name": "Epson WorkForce Enterprise AM-C4000",
        "category": "office_printer"
    }

    response = orchestrator.process_turn(
        "what will be the warranty for the printer?",
        state=state
    )

    assert response.get("source") == "route:warranty_info"
    msg = response.get("message", "")
    assert "1-Year On-Site Warranty" in msg or "Manufacturer Warranty" in msg
    # Must NOT return headquarters address or opening hours
    assert "Khalid Bin Waleed Road" not in msg
    assert "Abdulla Al Awar Building" not in msg
    assert "Monday – Friday: 8:30 AM" not in msg

