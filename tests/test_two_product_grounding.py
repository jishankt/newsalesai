"""Regression for a single turn asking about two printer models and their ink."""

from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


def test_two_named_models_keep_their_own_ink_and_width():
    result = orchestrator.process_turn(
        "Compare Epson SC-P700 and SC-P900: what is the print width and which ink cartridges does each use?",
        state=ConversationState(session_id="two-product-ink-width"),
    )
    reply = result["reply"]
    p700, p900 = reply.split("**Epson SureColor SC-P900**")
    assert "13.0 inches" in p700 and "17.0 inches" in p900
    assert "C13T46S100" in p700 and "C13T47A100" not in p700
    assert "C13T47A100" in p900 and "C13T46S100" not in p900
    assert [p["id"] for p in result["product_cards"]] == ["epson-sc-p700", "epson-sc-p900"]
    assert len(result["consumable_cards"]) == 20
    assert all(c["category"] == "Ink Cartridge" for c in result["consumable_cards"])
    assert all(c.get("price") is None for c in result["product_cards"] + result["consumable_cards"])


def test_missing_spec_is_reported_as_unknown_for_each_model():
    result = orchestrator.process_turn(
        "What ink and Wi-Fi connectivity do Epson SC-P700 and SC-P900 have?",
        state=ConversationState(session_id="two-product-unknown-wifi"),
    )
    assert result["reply"].count("not") >= 2
    assert "**Epson SureColor SC-P700**" in result["reply"]
    assert "**Epson SureColor SC-P900**" in result["reply"]
