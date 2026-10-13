"""
Automated Test Suite for Phase 2: Delivery & Policy Knowledge Base.
Validates all 12 delivery scenarios against grounded facts in data/delivery_policy.json:
1. Coverage (UAE, Oman, GCC, non-OFAC)
2. Fee (UAE flat AED 10, dynamic checkout outside UAE, free store pickup)
3. Timing (1-2 business days dispatch after confirmation)
4. Store Pickup (Free Dubai showroom pickup in 1-2 days)
5. Tracking (Courier tracking emailed upon dispatch)
6. Courier (Insured 3rd-party courier / technical team for heavy plotters)
7. Returns (2 days report defective in unopened packaging, 45-day refund)
8. Cancellation (24 hours order cancellation window)
9. Customs (Customer responsible for destination customs/taxes outside UAE)
10. Payment (Full payment before dispatch via Visa/MasterCard/PayPal)
11. Same Day (Standard 1-2 days, emergency Dubai coordination available)
12. Business Hours (Mon-Fri 8:30-17:30, Sat 8:30-13:00, Sun closed)
13. Destination Memory (Remembers destination across turns)
14. Sanctions Enforcement (Refusal for OFAC jurisdictions)
"""

import pytest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState


@pytest.fixture
def orchestrator():
    return Orchestrator()


class TestPhase2DeliveryPolicy:
    def test_01_coverage_scenario(self, orchestrator):
        state = ConversationState(session_id="test_p2_cov")
        resp = orchestrator.process_turn(
            "Where do you deliver?",
            session_id="test_p2_cov",
            state=state,
        )
        reply = resp["reply"]
        assert "UAE" in reply
        assert "Oman" in reply
        assert "AED 10" in reply
        assert "1 to 2 business days" in reply

    def test_02_fee_scenario_uae_flat_rate(self, orchestrator):
        state = ConversationState(session_id="test_p2_fee_uae")
        resp = orchestrator.process_turn(
            "How much is delivery in Dubai?",
            session_id="test_p2_fee_uae",
            state=state,
        )
        reply = resp["reply"]
        assert "AED 10" in reply
        assert "Dubai" in reply

    def test_02b_fee_scenario_oman_checkout(self, orchestrator):
        state = ConversationState(session_id="test_p2_fee_oman")
        resp = orchestrator.process_turn(
            "What is the delivery fee to Oman?",
            session_id="test_p2_fee_oman",
            state=state,
        )
        reply = resp["reply"]
        assert "Oman" in reply
        assert "checkout" in reply.lower()

    def test_03_time_dispatch_timing(self, orchestrator):
        state = ConversationState(session_id="test_p2_time")
        resp = orchestrator.process_turn(
            "How long does delivery take?",
            session_id="test_p2_time",
            state=state,
        )
        reply = resp["reply"]
        assert "1 to 2 business days" in reply

    def test_04_pickup_store_collection(self, orchestrator):
        state = ConversationState(session_id="test_p2_pickup")
        resp = orchestrator.process_turn(
            "Can I pick up my order from your showroom in person?",
            session_id="test_p2_pickup",
            state=state,
        )
        reply = resp["reply"]
        assert "pickup" in reply.lower() or "store pickup" in reply.lower()
        assert "free" in reply.lower()
        assert "Khalid Bin Waleed" in reply or "Dubai" in reply

    def test_05_tracking_notification(self, orchestrator):
        state = ConversationState(session_id="test_p2_track")
        resp = orchestrator.process_turn(
            "How do I track my order once shipped?",
            session_id="test_p2_track",
            state=state,
        )
        reply = resp["reply"]
        assert "track" in reply.lower()
        assert "courier" in reply.lower() or "notification" in reply.lower()

    def test_06_courier_details(self, orchestrator):
        state = ConversationState(session_id="test_p2_courier")
        resp = orchestrator.process_turn(
            "Which courier company do you use to deliver?",
            session_id="test_p2_courier",
            state=state,
        )
        reply = resp["reply"]
        assert "courier" in reply.lower()
        assert "third-party" in reply.lower() or "installation" in reply.lower()

    def test_07_returns_and_defects_policy(self, orchestrator):
        state = ConversationState(session_id="test_p2_returns")
        resp = orchestrator.process_turn(
            "What is your return policy for defective items?",
            session_id="test_p2_returns",
            state=state,
        )
        reply = resp["reply"]
        assert "2 days" in reply
        assert "45 days" in reply
        assert "packaging" in reply.lower()

    def test_08_cancellation_policy(self, orchestrator):
        state = ConversationState(session_id="test_p2_cancel")
        resp = orchestrator.process_turn(
            "Can I cancel my order after placing it?",
            session_id="test_p2_cancel",
            state=state,
        )
        reply = resp["reply"]
        assert "24 hours" in reply
        assert "sales@keplertech.ae" in reply or "+971 4 323 1008" in reply

    def test_09_customs_and_import_duty(self, orchestrator):
        state = ConversationState(session_id="test_p2_customs")
        resp = orchestrator.process_turn(
            "Do I have to pay customs duty for delivery outside the UAE?",
            session_id="test_p2_customs",
            state=state,
        )
        reply = resp["reply"]
        assert "customs" in reply.lower()
        assert "responsible" in reply.lower() or "taxes" in reply.lower()

    def test_10_payment_terms_before_dispatch(self, orchestrator):
        state = ConversationState(session_id="test_p2_payment")
        resp = orchestrator.process_turn(
            "Can I pay cash on delivery or do I pay before shipping?",
            session_id="test_p2_payment",
            state=state,
        )
        reply = resp["reply"]
        assert "in full" in reply.lower() or "before dispatch" in reply.lower()
        assert "Visa" in reply or "PayPal" in reply or "card" in reply.lower()

    def test_11_same_day_delivery_inquiry(self, orchestrator):
        state = ConversationState(session_id="test_p2_sameday")
        resp = orchestrator.process_turn(
            "Do you offer same day delivery in Dubai today?",
            session_id="test_p2_sameday",
            state=state,
        )
        reply = resp["reply"]
        assert "1 to 2 business days" in reply
        assert "sales desk" in reply.lower() or "Dubai" in reply

    def test_12_business_and_showroom_hours(self, orchestrator):
        state = ConversationState(session_id="test_p2_hours")
        resp = orchestrator.process_turn(
            "What are your showroom opening hours?",
            session_id="test_p2_hours",
            state=state,
        )
        reply = resp["reply"]
        assert "8:30" in reply
        assert "5:30" in reply
        assert "Saturday" in reply

    def test_13_destination_memory_across_turns(self, orchestrator):
        state = ConversationState(session_id="test_p2_mem")
        # Turn 1: User mentions Abu Dhabi
        r1 = orchestrator.process_turn(
            "I need delivery to Abu Dhabi",
            session_id="test_p2_mem",
            state=state,
        )
        assert "Abu Dhabi" in r1["reply"] or "AED 10" in r1["reply"]

        # Turn 2: User asks cost without repeating location
        r2 = orchestrator.process_turn(
            "How much will the delivery fee be?",
            session_id="test_p2_mem",
            state=state,
        )
        assert "AED 10" in r2["reply"]

    def test_14_sanctioned_country_fail_closed(self, orchestrator):
        state = ConversationState(session_id="test_p2_sanc")
        resp = orchestrator.process_turn(
            "Do you ship printers to Iran or Syria?",
            session_id="test_p2_sanc",
            state=state,
        )
        reply = resp["reply"]
        assert "OFAC" in reply or "sanctioned" in reply.lower() or "does not trade" in reply.lower()
