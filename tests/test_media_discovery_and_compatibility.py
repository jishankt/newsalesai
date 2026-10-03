"""
Unit tests for Inkjet Media Discovery, Subcategories, and Compatibility.
Verifies Innova Art, Olmec, Korejet, and Epson Media integration.
"""

import pytest
from catalog.media_registry import media_registry
from agent.orchestrator import Orchestrator


def test_media_registry_loaded():
    """Verify that media_registry is populated with verified products across all categories."""
    assert len(media_registry.products) >= 200
    
    fine_art = media_registry.get_by_category("fine_art")
    assert len(fine_art) >= 20
    
    photo = media_registry.get_by_category("photo")
    assert len(photo) >= 20
    
    canvas = media_registry.get_by_category("canvas")
    assert len(canvas) >= 10
    
    signage = media_registry.get_by_category("signage")
    assert len(signage) >= 5

    # Check key SKUs exist
    ifa11 = media_registry.get_by_sku("IFA-11-610X15")
    assert ifa11 is not None
    assert "Innova" in ifa11.brand
    assert "https://www.keplertechllc.com" in ifa11.url

    olm59 = media_registry.get_by_sku("OLM59R24")
    assert olm59 is not None
    assert olm59.brand == "Olmec"

    korejet = media_registry.get_by_sku("KJP260PL24")
    assert korejet is not None
    assert korejet.brand == "Korejet"


def test_media_discovery_generic():
    """Verify that generic inquiry 'I need inkjet media' returns structured categories and chips."""
    orchestrator = Orchestrator()
    res = orchestrator.process_turn("I need inkjet media", session_id="test_media_gen")
    
    assert res.get("source") == "route:media_discovery"
    reply = res.get("reply") or res.get("reply_text") or ""
    assert "Fine Art & Museum Papers" in reply
    assert "Photographic & Studio Papers" in reply
    assert "Printable Fine Art Canvases" in reply
    assert "Signage & Interior Wallcoverings" in reply
    
    chips = res.get("suggested_chips", [])
    assert "Fine Art Papers (Innova)" in chips
    assert "Photo Papers (Lustre/Gloss)" in chips
    assert "Printable Canvases" in chips
    assert "Signage & Wallpapers" in chips


def test_fine_art_media_discovery():
    """Verify that inquiry for Innova Fine Art returns verified cotton rag models and links."""
    orchestrator = Orchestrator()
    res = orchestrator.process_turn("Fine Art Papers (Innova)", session_id="test_media_fa")
    
    assert res.get("source") == "route:media_discovery:fine_art"
    reply = res.get("reply") or res.get("reply_text") or ""
    assert "IFA-11" in reply
    assert "IFA-04" in reply or "IFA-14" in reply
    assert "IFA-107" in reply or "Fabriano" in reply
    assert "https://www.keplertechllc.com/product/innova-photo-cotton-rag-315gsm-ifa-11/" in reply
    
    cards = res.get("consumable_cards", [])
    assert len(cards) >= 1
    assert any("IFA" in c.get("sku", "") for c in cards)


def test_photo_paper_discovery():
    """Verify that photo paper inquiry returns Olmec and Korejet options."""
    orchestrator = Orchestrator()
    res = orchestrator.process_turn("Photo Papers (Lustre/Gloss)", session_id="test_media_ph")
    
    assert res.get("source") == "route:media_discovery:photo"
    reply = res.get("reply") or res.get("reply_text") or ""
    assert "OLM-59" in reply or "Olmec Photo Lustre" in reply
    assert "OLM-60" in reply or "Olmec Photo Gloss" in reply
    assert "Korejet" in reply


def test_canvas_discovery():
    """Verify that printable canvas inquiry returns Innova and Korejet canvas options."""
    orchestrator = Orchestrator()
    res = orchestrator.process_turn("Printable Canvases", session_id="test_media_cv")
    
    assert res.get("source") == "route:media_discovery:canvas"
    reply = res.get("reply") or res.get("reply_text") or ""
    assert "IFA-54" in reply or "Exhibition Matte Cotton Canvas" in reply
    assert "Korejet" in reply or "Epson Exhibition Canvas" in reply


def test_signage_wallpaper_discovery():
    """Verify that signage inquiry returns wallpaper and eco-solvent options."""
    orchestrator = Orchestrator()
    res = orchestrator.process_turn("Signage & Wallpapers", session_id="test_media_sg")
    
    assert res.get("source") == "route:media_discovery:signage"
    reply = res.get("reply") or res.get("reply_text") or ""
    assert "IFA-98" in reply or "Wallpaper" in reply
    assert "Eco Solvent" in reply


def test_inkjet_disambiguation_and_numeric_choice():
    """Verify that 'i need a inkjet' followed by '1' routes to media discovery, and subsequent '1' routes to Fine Art papers."""
    from domain.conversation_state import ConversationState
    orchestrator = Orchestrator()
    state = ConversationState(session_id="test_disambig_num")

    res1 = orchestrator.process_turn("i need a inkjet", state=state)
    assert res1.get("source") == "route:inkjet_disambiguation"
    assert state.awaiting_field == "inkjet_offering"

    # Turn 2: User selects option 1 (Media)
    res2 = orchestrator.process_turn("1", state=state)
    assert res2.get("source") == "route:media_discovery"
    assert "Fine Art & Museum Papers" in res2.get("reply", "")
    assert state.awaiting_field == "media_category"
    assert "daily_volume" not in state.requirements

    # Turn 3: User selects option 1 (Fine Art Papers)
    res3 = orchestrator.process_turn("1", state=state)
    assert res3.get("source") == "route:media_discovery:fine_art"
    reply3 = res3.get("reply", "")
    assert "IFA-11" in reply3
    assert "Innova" in reply3
    assert "https://www.keplertechllc.com/product/innova-photo-cotton-rag-315gsm-ifa-11/" in reply3
    assert len(res3.get("consumable_cards", [])) >= 1
    assert "daily_volume" not in state.requirements


def test_media_category_numeric_choices():
    """Verify options 1, 2, 3, 4 from general media discovery menu."""
    from domain.conversation_state import ConversationState
    orchestrator = Orchestrator()

    # Test Choice 2: Photo papers
    s2 = ConversationState(session_id="test_opt2")
    orchestrator.process_turn("I need inkjet media", state=s2)
    assert s2.awaiting_field == "media_category"
    r2 = orchestrator.process_turn("2", state=s2)
    assert r2.get("source") == "route:media_discovery:photo"
    assert "OLM-59" in r2.get("reply", "") or "Olmec" in r2.get("reply", "")

    # Test Choice 3: Canvases
    s3 = ConversationState(session_id="test_opt3")
    orchestrator.process_turn("I need inkjet media", state=s3)
    r3 = orchestrator.process_turn("3", state=s3)
    assert r3.get("source") == "route:media_discovery:canvas"
    assert "IFA-54" in r3.get("reply", "") or "Canvas" in r3.get("reply", "")

    # Test Choice 4: Signage & Wallpapers
    s4 = ConversationState(session_id="test_opt4")
    orchestrator.process_turn("I need inkjet media", state=s4)
    r4 = orchestrator.process_turn("4", state=s4)
    assert r4.get("source") == "route:media_discovery:signage"
    assert "IFA-98" in r4.get("reply", "") or "Wallpaper" in r4.get("reply", "")


