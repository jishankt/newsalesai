import pytest
from conversation.canonical_entity_normalizer import canonical_normalizer
from conversation.contextual_slot_resolver import ContextualSlotResolver
from conversation.pre_classification_resolver import PreClassificationResolver
from domain.conversation_state import ConversationState


def test_inverted_negation_do_not_want_print_only():
    text = "I definitely need an integrated wide-format scanner for scanning and copying blueprints. I do not want a print-only model."
    res = canonical_normalizer.normalize_scanner_function(text)
    assert res is not None, "Scanner function should be recognized"
    assert res.get("scanner_required") is True, "Scanner must be required when print-only is rejected"
    assert "scan" in res.get("functions", []), "Scan function must be present"

    # Contextual resolver
    reqs, corrs = ContextualSlotResolver.resolve(text=text, awaiting_field="scanner_required", category="technical_large_format")
    assert reqs.get("scanner_required") is True
    assert "scan" in reqs.get("functions", [])


def test_typo_aphoto_printer():
    state = ConversationState(session_id="test_session")
    res = PreClassificationResolver.resolve("hi i want aphoto printer", "hi i want aphoto printer", state)
    # Typo must be fixed so it does not fail
    assert res is not None


def test_hardware_over_consumables_photo_printer():
    state = ConversationState(session_id="test_session")
    state.category = "photography_large_format"
    state.set_canonical_focus("epson-sc-p900")
    state.shown_entities = ["epson-sc-p900"]

    msg = "Among your professional photo printers, I need the compact 17-inch desktop model for individual photographers and artists. I do not need a heavy-duty production printer with bulk ink cartridges. I need the desktop model with roll-paper printing and a roll adapter."
    res = PreClassificationResolver.resolve(msg, msg, state)
    # Must NOT be hijacked into dumping consumables
    assert res.source != "route:consumables:verified_list", f"Expected not to be hijacked into consumables, but got {res.source}"


def test_domain_deescalation_from_consumables():
    state = ConversationState(session_id="test_session")
    state.active_printer_for_consumables = "Epson SureColor SC-P700"
    state.active_route = "consumable"
    state.category = "consumables"

    msg = "I want to buy a printer"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert state.active_route is None or state.active_route != "consumable"
    assert state.active_printer_for_consumables is None
    assert state.category != "consumables"


def test_auto_2_sided_does_not_corrupt_volume():
    state = ConversationState(session_id="test_session")
    state.category = "office_printer"
    state.requirements["daily_volume"] = 250
    state.requirements["exact_daily_volume"] = 250

    msg = "the printer must be Auto 2-sided printing, duplex scanning, and faxing"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert state.requirements.get("daily_volume") == 250, "daily_volume must not be overwritten to 2"


def test_specific_em_c800_spec_inquiry():
    state = ConversationState(session_id="test_session")
    state.category = "office_printer"

    msg = "I need an A4 colour multifunction printer for a busy office, with a recommended monthly print volume of 2,500–10,000 pages. It must use a replaceable ink pack system with yields of up to 50,000 black pages and 20,000 colour pages, support duplex scanning at up to 60 images per minute, and include a 50-sheet automatic document feeder. Which single product in your catalogue matches all these specifications? Please provide its direct product page link and do not list alternatives."
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert res.handled is True
    assert res.source == "route:model_detail"
    assert any("em-c800" in str(c.get("id", "")).lower() for c in res.product_cards)
    assert "EM-C800" in res.reply
    assert "https://www.keplertechllc.com/product/epson-workforce-pro-em-c800/" in res.reply


def test_hardware_query_with_ink_pack_does_not_dump_consumables():
    state = ConversationState(session_id="test_session")
    state.category = "office_printer"
    state.set_canonical_focus("epson-wf-c5890-dwf")
    state.shown_entities = ["epson-wf-c5890-dwf"]

    msg = "Which business colour multifunction printer supports optional paper trays that expand total paper capacity to 1,830 sheets, while also offering a replaceable ink pack system and automatic duplex scanning?"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert res.source != "route:consumables:verified_list", f"Got consumable dump: {res.source}"

    # Also test explicit negative constraint on ink
    msg_no_ink = "im not searching for ink , i want the colour multifunction"
    res_no_ink = PreClassificationResolver.resolve(msg_no_ink, msg_no_ink, state)
    assert res_no_ink.source != "route:consumables:verified_list", f"Got consumable dump: {res_no_ink.source}"


def test_exact_product_link_request():
    state = ConversationState(session_id="test_session")
    state.category = "photography_large_format"
    state.set_canonical_focus("epson-sc-p900")
    state.shown_entities = ["epson-sc-p900"]

    msg = "please give the exact product link"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert res.handled is True
    assert res.source == "route:product_url"
    assert "https://www.keplertechllc.com/product/epson-surecolor" in res.reply
    assert "p900" in res.reply


def test_active_focus_feature_confirmation():
    state = ConversationState(session_id="test_feat")
    state.category = "office_printer"
    state.set_canonical_focus("epson-em-c800")
    state.shown_entities = ["epson-em-c800"]

    msg = "the printer must be Auto 2-sided printing, duplex scanning, and faxing"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert res.handled is True
    assert res.source == "route:model_detail"
    assert "Epson WorkForce Pro EM-C800" in res.reply
    assert "Auto 2-Sided Printing" in res.reply
    assert "Duplex Scanning" in res.reply
    assert "Faxing" in res.reply
    assert len(res.product_cards) == 1
    assert res.product_cards[0]["id"] == "epson-em-c800"


def test_high_performance_a4_multifunction_printer():
    state = ConversationState(session_id="test_hp")
    state.category = "office_printer"

    msg = "which is the best high-performance A4 multifunction printer among this and it should Auto 2-sided printing, duplex scanning, and faxing"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert res.handled is True
    assert res.source == "route:model_detail"
    assert "AM-C550" in res.reply
    assert "AM-C400" in res.reply
    card_ids = [c["id"] for c in res.product_cards]
    assert "epson-am-c550" in card_ids
    assert "epson-am-c400" in card_ids


def test_em_c800_spec_direct_resolution_hardware_intent():
    from conversation.understanding import understand_turn

    state = ConversationState(session_id="test_em_spec")
    state.set_canonical_focus("epson-em-c800")
    state.category = "office_printer"

    msg = "Which business colour multifunction printer supports optional paper trays that expand total paper capacity to 1,830 sheets, while also offering a replaceable ink pack system and automatic duplex scanning?"
    res = PreClassificationResolver.resolve(msg, msg, state)
    assert res.handled is True
    assert res.source == "route:model_detail"
    assert "Epson WorkForce Pro EM-C800" in res.reply
    assert len(res.consumable_cards) == 0
    assert len(res.product_cards) == 1
    assert res.product_cards[0]["id"] == "epson-em-c800"

    und = understand_turn(msg, state)
    assert und.intent != "consumables_lookup"
