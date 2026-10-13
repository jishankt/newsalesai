"""
Automated Test Suite for Phase 3: Understanding & Fallback Ladder.
Validates:
1. Frustration / complaint triggers apology and human specialist handoff.
2. Natural language lead capture (name + UAE phone number) without unlisted model false positives.
3. Anti-repeat guard detects repeated slots and advances forward with stated assumptions.
4. Mid-conversation greeting continuity maintains discussion topic without resetting.
5. Short reply and ordinal binding ('the first one', '2', 'yes').
6. Price objection handling with TCO empathy and commercial quotation routing.
7. Zero identical consecutive replies and zero generic fallbacks.
"""

import pytest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState


@pytest.fixture
def orchestrator():
    return Orchestrator()


class TestPhase3FallbackLadder:
    def test_01_frustration_apology_and_specialist_handoff(self, orchestrator):
        state = ConversationState(session_id="test_p3_frust")
        resp = orchestrator.process_turn(
            "this is useless",
            session_id="test_p3_frust",
            state=state,
        )
        reply = resp["reply"]
        assert "apologize" in reply.lower()
        assert "specialist" in reply.lower() or "sales@keplertech.ae" in reply
        assert any(c in resp["chips"] for c in ["Speak to Specialist", "Request Call Back"])

    def test_02_lead_capture_without_model_false_positive(self, orchestrator):
        state = ConversationState(session_id="test_p3_lead")
        # Pre-seed a product or category in conversation
        orchestrator.process_turn(
            "i need a photo printer",
            session_id="test_p3_lead",
            state=state,
        )

        resp = orchestrator.process_turn(
            "my name is Ali and number is 0501234567",
            session_id="test_p3_lead",
            state=state,
        )
        reply = resp["reply"]
        # Must NOT claim '0501234567' is an unlisted model
        assert "not in our approved equipment catalogue" not in reply
        assert "Ali" in reply
        assert "0501234567" in reply or "contact" in reply.lower()

    def test_03_anti_repeat_advances_forward(self, orchestrator):
        state = ConversationState(session_id="test_p3_repeat")
        # Turn 1
        r1 = orchestrator.process_turn(
            "printer for office",
            session_id="test_p3_repeat",
            state=state,
        )
        # Turn 2: exact repeat
        r2 = orchestrator.process_turn(
            "printer for office",
            session_id="test_p3_repeat",
            state=state,
        )
        # Turn 3: second repeat
        r3 = orchestrator.process_turn(
            "printer for office",
            session_id="test_p3_repeat",
            state=state,
        )

        # Responses must NOT be identical
        from difflib import SequenceMatcher
        ratio_1_2 = SequenceMatcher(None, r1["reply"].lower(), r2["reply"].lower()).ratio()
        ratio_2_3 = SequenceMatcher(None, r2["reply"].lower(), r3["reply"].lower()).ratio()
        assert ratio_1_2 < 0.85
        assert ratio_2_3 < 0.85
        # Turn 3 advances forward with top recommendations
        assert "WF-C5890" in r3["reply"] or "AM-C4000" in r3["reply"]

    def test_04_mid_conversation_greeting_continuity(self, orchestrator):
        state = ConversationState(session_id="test_p3_cont")
        # Turn 1: Establish office category
        r1 = orchestrator.process_turn(
            "i need a printer for my office",
            session_id="test_p3_cont",
            state=state,
        )
        # Turn 2: User says 'Hi'
        r2 = orchestrator.process_turn(
            "Hi",
            session_id="test_p3_cont",
            state=state,
        )
        reply = r2["reply"]
        # Must retain office context, not reset to generic initial welcome
        assert "office" in reply.lower() or "discussing" in reply.lower()
        assert any("office" in c.lower() for c in r2.get("chips", []))

    def test_05_short_reply_ordinal_selection(self, orchestrator):
        state = ConversationState(session_id="test_p3_ordinal")
        # Turn 1: Compare or show options
        r1 = orchestrator.process_turn(
            "compare SC-F100 and SC-F500",
            session_id="test_p3_ordinal",
            state=state,
        )
        # Turn 2: User selects 'the first one'
        r2 = orchestrator.process_turn(
            "the first one",
            session_id="test_p3_ordinal",
            state=state,
        )
        reply = r2["reply"]
        assert "SC-F100" in reply
        assert "How can I best assist you with Kepler Tech printing equipment? Please select a category" not in reply

    def test_06_price_objection_empathy(self, orchestrator):
        state = ConversationState(session_id="test_p3_obj")
        orchestrator.process_turn(
            "tell me about the Epson SC-P900",
            session_id="test_p3_obj",
            state=state,
        )
        resp = orchestrator.process_turn(
            "it's too expensive",
            session_id="test_p3_obj",
            state=state,
        )
        reply = resp["reply"]
        assert "budget" in reply.lower() or "cost" in reply.lower()
        assert any(c in resp["chips"] for c in ["Cost-Effective Models", "Running Cost Comparison", "Request Official Quote"])

    def test_07_hesitation_polite_acknowledgment(self, orchestrator):
        state = ConversationState(session_id="test_p3_hes")
        resp = orchestrator.process_turn(
            "okay I'll think about it",
            session_id="test_p3_hes",
            state=state,
        )
        reply = resp["reply"]
        assert "time" in reply.lower() or "ready" in reply.lower()
        assert "How can I best assist you with Kepler Tech printing equipment? Please select a category" not in reply
