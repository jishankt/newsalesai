"""Customer-facing, multi-turn correctness checks from the September audit."""

from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


def talk(state, question):
    return orchestrator.process_turn(question, session_id=state.session_id, state=state)


def test_cad_correction_keeps_the_stated_volume_and_scanner_preference():
    state = ConversationState(session_id="audit-cad-correction")
    talk(state, "I need an A0 CAD plotter with a scanner.")
    assert state.requirements["scanner_required"] is True
    response = talk(state, "Actually A1, and 3000 drawings per month.")
    assert state.requirements["paper_size"] == "a1"
    assert state.requirements["exact_monthly_volume"] == 3000
    assert state.requirements["daily_volume"] == 100
    assert state.requirements["scanner_required"] is True
    assert not response["product_cards"]  # The catalogue has no A1 integrated-scanner match.
    talk(state, "I do not need a scanner anymore.")
    assert state.requirements["scanner_required"] is False


def test_monthly_correction_removes_stale_exact_daily_count():
    state = ConversationState(session_id="audit-office-volume")
    talk(state, "Need an A3 multifunction office printer for 150 pages per day.")
    talk(state, "Wait, I meant 3000 pages per month, not daily.")
    assert state.requirements["exact_monthly_volume"] == 3000
    assert state.requirements["daily_volume"] == 100
    assert "exact_daily_volume" not in state.requirements


def test_comparison_followups_keep_the_actual_pair():
    state = ConversationState(session_id="audit-compared-photo")
    talk(state, "Compare Epson SC-P700 and SC-P900: which ink cartridges fit each?")
    answer = talk(state, "Which of those two supports 17-inch prints?")["reply"]
    assert "SC-P900" in answer and "SC-P5300" not in answer
    assert "17-inch" in answer
    state = ConversationState(session_id="audit-compared-sublimation")
    answer = talk(state, "Compare Epson SC-F100 and SC-F500: do both print mugs and T-shirts?")["reply"]
    assert "SC-F100" in answer and "SC-F500" in answer
    assert "Mugs:" in answer and "T-shirts:" in answer
    answer = talk(state, "Which one supports A3 sheets?")["reply"]
    assert "SC-F500" in answer and "SC-F100" not in answer


def test_comparison_followup_survives_state_serialization():
    state = ConversationState(session_id="audit-persisted-comparison")
    talk(state, "Compare Epson SC-P700 and SC-P900: which ink cartridges fit each?")
    restored = ConversationState.from_dict(state.to_dict())
    answer = talk(restored, "Which of those two supports 17-inch prints?")["reply"]
    assert "SC-P900" in answer
    assert "SC-P5300" not in answer
    scanner = talk(restored, "Does the second one have a scanner?")["reply"]
    assert "SC-P900" in scanner and "scanner" in scanner.lower()


def test_ink_type_and_model_compatibility_are_checked_before_answering():
    state = ConversationState(session_id="audit-sku-relations")
    response = talk(state, "Which ink cartridges fit Epson SC-P700?")
    assert len(response["consumable_cards"]) == 10
    assert all(c["category"] == "Ink Cartridge" for c in response["consumable_cards"])
    assert "AED" not in response["reply"]
    reply = talk(state, "Is C12C935711 an ink cartridge?")["reply"]
    assert "No" in reply and "maintenance" in reply.lower() and "in stock" not in reply
    reply = talk(state, "Are C13T47A100 cartridges compatible with the SC-P700?")["reply"]
    assert "No" in reply and "SC-P700" in reply and "in stock" not in reply


def test_unverified_fields_are_stated_as_unknown_and_policy_holds():
    state = ConversationState(session_id="audit-unknown-fields")
    assert "not listed" in talk(state, "Does Epson SC-P700 include Wi-Fi?")["reply"].lower()
    assert "does not specify" in talk(state, "How long is the SC-P700 warranty?")["reply"].lower()
    for question in ("How much is the Epson SC-P700?", "Can I get a discount or an official quote?"):
        response = talk(state, question)
        assert "AED" not in response["reply"]
        assert "sales@" not in response["reply"]
        assert "+971" not in response["reply"]
        assert all(card.get("price") is None for card in response["product_cards"] + response["consumable_cards"])


def test_multiattribute_office_spec_uses_its_catalogued_ink_technology():
    state = ConversationState(session_id="audit-office-ink")
    talk(state, "Need an A3 multifunction office printer for 150 pages per day.")
    response = talk(state, "Does it have Wi-Fi, scanner and what ink does it use?")
    answer = response["reply"]
    assert "DURABrite Pro" in answer
    assert "UltraChrome" not in answer
    assert "Wi-Fi" in answer
