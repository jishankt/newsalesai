"""
Automated Test Suite for Phases 5 & 6: Humanisation & Accuracy Guards.

Validates:
1. Rotating openers (8+ variants, 3-turn no-repeat).
2. Banned phrase filter ('Certainly!', 'delighted to assist', 'Based on your requirements').
3. Category intro paragraph shown once per category per session.
4. Succinct response length (under ~60-65 words unless technical comparison table).
5. Pre-transmission accuracy guard: blocks ungrounded models/specs and falls back to clean evidence.
"""

import pytest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState
from conversation.response_plan import OPENERS_POOL, ResponsePlanValidator, ResponsePlan
from conversation.dialogue_state import DialogueState, ResolvedTurn, TurnUnderstanding
from conversation.understanding import Intent, DialogueAct


@pytest.fixture
def orchestrator():
    return Orchestrator()


class TestPhase5And6HumanisationAndAccuracy:

    def test_01_openers_pool_has_8_plus_variants_no_banned_phrases(self):
        assert len(OPENERS_POOL) >= 8
        banned = ["certainly", "delighted to assist", "based on your requirements", "as an ai"]
        for op in OPENERS_POOL:
            assert not any(b in op.lower() for b in banned)

    def test_02_rotating_openers_do_not_repeat_in_3_turns(self, orchestrator):
        state = ConversationState(session_id="test_p5_openers")
        queries = [
            "tell me about the Epson SC-F100",
            "what is the print speed of the SC-F100?",
            "what ink does the SC-F100 use?",
        ]
        openers_used = []
        for q in queries:
            resp = orchestrator.process_turn(q, session_id="test_p5_openers", state=state)
            reply = resp["reply"]
            first_line = reply.split("\n")[0].strip()
            openers_used.append(first_line)

        # First line of each reply should be diverse
        assert len(set(openers_used)) == len(openers_used)

    def test_03_banned_phrases_completely_eliminated(self, orchestrator):
        state = ConversationState(session_id="test_p5_banned")
        queries = [
            "where is your showroom located?",
            "tell me about your company",
            "can you recommend an office printer?",
        ]
        banned_phrases = ["Certainly!", "delighted to assist", "Based on your requirements", "As an AI"]
        for q in queries:
            resp = orchestrator.process_turn(q, session_id="test_p5_banned", state=state)
            reply = resp["reply"]
            for bp in banned_phrases:
                assert bp.lower() not in reply.lower(), f"Found banned phrase '{bp}' in reply: {reply}"

    def test_04_category_intro_paragraph_capped_to_once(self, orchestrator):
        state = ConversationState(session_id="test_p5_cat_intro")
        r1 = orchestrator.process_turn("i need a CAD plotter", session_id="test_p5_cat_intro", state=state)
        r2 = orchestrator.process_turn("24 inch", session_id="test_p5_cat_intro", state=state)

        # Intro text about Kepler Tech T-series line accuracy should appear at most once
        intro_marker = "engineered for line accuracy"
        count_r1 = r1["reply"].count(intro_marker)
        count_r2 = r2["reply"].count(intro_marker)
        assert count_r1 + count_r2 <= 1

    def test_05_response_length_succinct_under_65_words(self, orchestrator):
        state = ConversationState(session_id="test_p5_length")
        queries = [
            "tell me about the Epson SC-T3100",
            "what inks does it use?",
            "is delivery available to Sharjah?",
        ]
        for q in queries:
            resp = orchestrator.process_turn(q, session_id="test_p5_length", state=state)
            reply = resp["reply"]
            is_table = "|" in reply and "---" in reply
            if not is_table:
                word_count = len(reply.split())
                # Response should be concise
                assert word_count <= 65, f"Response too verbose ({word_count} words): {reply}"

    def test_06_accuracy_guard_blocks_unverified_model(self):
        state = DialogueState(session_id="test_p6_acc")
        und = TurnUnderstanding(raw_text="what about the HP DesignJet T650?", intent=Intent.RECOMMEND, dialogue_act=DialogueAct.QUESTION)
        resolved = ResolvedTurn(understanding=und)

        # Plan mentions an ungrounded third-party/unverified model
        plan = ResponsePlan(
            direct_answer="The HP DesignJet T650 is a 24-inch plotter.",
            formatted_reply="The HP DesignJet T650 is a 24-inch plotter.",
            evidence_ids=[],
            is_valid=True,
        )

        validated = ResponsePlanValidator.validate(plan, resolved, state)
        assert validated.is_valid is False
        assert any("Accuracy violation" in err for err in validated.validation_errors)
        # Fallback executed
        assert "HP DesignJet" not in validated.formatted_reply
