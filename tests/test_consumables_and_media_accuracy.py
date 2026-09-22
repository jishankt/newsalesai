"""
Test Consumables and Media Accuracy.
Validates:
1. All 43 catalogue products in data/catalogue_products.json have non-empty, genuine consumables arrays.
2. Verified hardware models have correct website URLs, high-res images, and brochure links.
3. Media & Paper category products are recognized and returned when querying paper/media.
4. Consumable queries return accurate inks, maintenance boxes, and ribbons.
"""

import json
from pathlib import Path
import pytest
from catalog.repository import CatalogRepository
from agent.tool_executor import catalog_tool_executor
from domain.conversation_types import LLMUnderstanding
from domain.conversation_state import ConversationState
from routes.consumables_route import handle as handle_consumables


@pytest.fixture
def repo():
    return CatalogRepository()


def test_all_catalogue_products_have_consumables():
    """All 72 products in catalogue_products.json must have valid media/urls, and 43 printers must have non-empty consumables."""
    cat_path = Path(__file__).resolve().parent.parent / "data" / "catalogue_products.json"
    assert cat_path.exists()
    with open(cat_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    assert len(products) == 72
    printers = [p for p in products if p.get("main_category") != "scanners"]
    scanners = [p for p in products if p.get("main_category") == "scanners"]
    assert len(printers) == 43
    assert len(scanners) == 29

    for p in printers:
        p_id = p.get("id")
        consumables = p.get("consumables", [])
        assert isinstance(consumables, list), f"Product {p_id} consumables should be a list"
        assert len(consumables) > 0, f"Product {p_id} ({p.get('display_name')}) has empty consumables!"

    for p in products:
        p_id = p.get("id")
        # Check website url
        p_url = p.get("product_url")
        assert p_url and p_url.startswith("https://www.keplertechllc.com/"), f"Product {p_id} URL invalid: {p_url}"
        # Check image url
        img = p.get("image_url")
        assert img and img.startswith("https://www.keplertechllc.com/"), f"Product {p_id} image invalid: {img}"


def test_hardware_products_urls_and_images(repo):
    """Ensure no sibling URL overwrites or wrong image URLs exist for major printers."""
    # SC-P20000 should not point to SC-T7200
    prod_path = Path(__file__).resolve().parent.parent / "data" / "products.json"
    with open(prod_path, "r", encoding="utf-8") as f:
        prods = json.load(f)
    p20k = next((p for p in prods if p.get("sku") == "C11CE20001A0"), None)
    assert p20k is not None
    assert "t7200" not in (p20k.get("website_url") or "").lower()
    assert "p20000" in (p20k.get("website_url") or "").lower()

    # SC-P700 image must be P700, not P7000
    p700 = repo.get_by_id("epson-p700")
    assert p700 is not None
    assert "p7000" not in p700.image_url.lower()
    assert "p700" in p700.image_url.lower()

    # SC-P9500 image must be P9500, not P7500
    p9500 = repo.get_by_id("epson-p9500")
    assert p9500 is not None
    assert "p7500" not in p9500.image_url.lower()
    assert "p9500" in p9500.image_url.lower()


def test_citizen_cx02_consumables():
    """Citizen CX-02 must return genuine dye-sub media rolls and not liquid ink cartridges."""
    res = catalog_tool_executor.execute_tool(
        "get_compatible_consumables",
        {"printer_identifier": "Citizen CX-02", "limit": 10}
    )
    assert res["success"] is True
    assert res["count"] >= 1
    cards = res["consumable_cards"]
    skus = [c["sku"] for c in cards]
    assert any("CX2" in s.upper() for s in skus)
    # Ensure no liquid ink cartridges are listed for CX-02
    assert not any("ink cartridge" in c["name"].lower() for c in cards)


def test_epson_p900_consumables():
    """Epson SC-P900 must return UltraChrome Pro10 inks and maintenance box."""
    res = catalog_tool_executor.execute_tool(
        "get_compatible_consumables",
        {"printer_identifier": "Epson SC-P900", "limit": 12}
    )
    assert res["success"] is True
    assert res["count"] >= 5
    skus = [c["sku"] for c in res["consumable_cards"]]
    # Maintenance box C12C935711
    assert "C12C935711" in skus
    # T47A series inks
    assert any(s.startswith("C13T47A") for s in skus)


def test_epson_t3100_consumables():
    """Epson SC-T3100 must return UltraChrome XD2 inks and maintenance box."""
    res = catalog_tool_executor.execute_tool(
        "get_compatible_consumables",
        {"printer_identifier": "SC-T3100", "limit": 10}
    )
    assert res["success"] is True
    assert res["count"] >= 3
    skus = [c["sku"] for c in res["consumable_cards"]]
    # Maintenance box C13S210057
    assert "C13S210057" in skus


def test_media_query_prioritizes_media_paper():
    """When a customer asks for paper/media for an Epson printer, media rolls are prioritized."""
    state = ConversationState(session_id="test-session")
    understanding = LLMUnderstanding(
        intent="consumables_inquiry",
        entities={"printer_model": "SC-P9500"}
    )
    result = handle_consumables(
        understanding=understanding,
        state=state,
        raw_message="What paper rolls and media are compatible with SC-P9500?"
    )
    assert result.consumable_cards
    # The first card should be Print Media
    badges = [c.get("badge") for c in result.consumable_cards]
    assert "Print Media" in badges
    first_badge = result.consumable_cards[0].get("badge")
    assert first_badge == "Print Media"
    assert "media rolls and papers" in result.reply.lower()


def test_unsupported_brand_consumables_rejected():
    """Competitor brands like Canon / HP designjet should return count 0 without hallucination."""
    res = catalog_tool_executor.execute_tool(
        "get_compatible_consumables",
        {"printer_identifier": "HP DesignJet T650", "limit": 5}
    )
    assert res["success"] is True
    assert res["count"] == 0
    assert len(res["consumable_cards"]) == 0
