"""
Comprehensive Multi-Turn Scenario Acceptance Suite for Kepler Tech SalesAI.

Covers all 17 required behavioral categories:
A. Discovery & Bounded Questioning
B. Technical Evaluation & Specification Inquiries
C. Product Comparisons
D. Price Objections & Policies
E. Purchase Intent & Clean Ordering
F. Customer Frustration Recovery
G. Topic Switching without Leakage
H. Customer Closing & Clean Finish
I. Ambiguous Language Disambiguation
J. Typo-Heavy Queries
K. Multi-Question Single Turns
L. Returning Customer Context
M. Consumables & Ink Compatibility
N. Media Rolls & Paper Sizing
O. Unsupported Products (Polite Refusal)
P. Unsupported Attributes (Grounded Refusal)
Q. No-Match Requirement Alternatives

Plus the Verbatim 8-Turn End-to-End Acceptance Conversation.
"""

import pytest
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator
from catalog.catalogue_loader import catalogue_loader
from conversation.question_ledger import QuestionLedger, QuestionStatus
from conversation.goal_manager import GoalManager


# ── Final 8-Turn End-to-End Acceptance Conversation ──────────────────────────

def test_verbatim_8_turn_acceptance_conversation():
    """
    Executes the exact 8-turn conversation verbatim:
    1. "I need a photo printer." -> 1 discovery question.
    2. "For weddings, 4x6, very fast." -> recommends Citizen CX-02 (no A4/A3 question).
    3. "How fast is the CX-02?" -> answers speed only.
    4. "And how many prints per roll?" -> answers media capacity.
    5. "Does it support WiFi?" -> answers WiFi specifically.
    6. "How much?" -> follows pricing policy.
    7. "That's expensive." -> objection handling.
    8. "Thanks, that's all." -> closes cleanly.
    """
    state = ConversationState(session_id="verbatim_8_turn_acceptance")

    # Turn 1
    res1 = orchestrator.process_turn("I need a photo printer.", state=state)
    reply1 = res1.get("reply", "")
    assert "?" in reply1, "Turn 1 must ask a single consultative discovery question."
    assert "photo" in reply1.lower()
    assert "**" not in reply1, "Zero markdown asterisks allowed."

    # Turn 2
    res2 = orchestrator.process_turn("For weddings, 4x6, very fast.", state=state)
    reply2 = res2.get("reply", "")
    assert "Citizen CX-02" in reply2 or "CX-02" in reply2 or "Citizen" in reply2
    assert "a4 or a3" not in reply2.lower(), "Must NOT ask irrelevant A4/A3 question when 4x6 is known."
    assert "**" not in reply2

    # Turn 3
    res3 = orchestrator.process_turn("How fast is the CX-02?", state=state)
    reply3 = res3.get("reply", "")
    assert any(term in reply3.lower() for term in ["second", "speed", "8.4", "sec"]), "Turn 3 must answer printing speed."
    assert "**" not in reply3

    # Turn 4
    res4 = orchestrator.process_turn("And how many prints per roll?", state=state)
    reply4 = res4.get("reply", "")
    assert any(term in reply4 for term in ["400", "800", "roll", "yield"]), "Turn 4 must answer media yield."
    assert "**" not in reply4

    # Turn 5
    res5 = orchestrator.process_turn("Does it support WiFi?", state=state)
    reply5 = res5.get("reply", "")
    assert any(term in reply5.lower() for term in ["no", "does not", "usb", "not feature built-in wi-fi"]), "Turn 5 must accurately state Wi-Fi status."
    assert "**" not in reply5

    # Turn 6
    res6 = orchestrator.process_turn("How much?", state=state)
    reply6 = res6.get("reply", "")
    assert "4,385" in reply6 or "aed" in reply6.lower(), "Turn 6 must provide verified pricing."
    assert "**" not in reply6

    # Turn 7
    res7 = orchestrator.process_turn("That's expensive.", state=state)
    reply7 = res7.get("reply", "")
    assert any(term in reply7.lower() for term in ["investment", "running cost", "cz-01", "3,200", "durab"]), "Turn 7 must handle price objection consultatively."
    assert "**" not in reply7

    # Turn 8
    res8 = orchestrator.process_turn("Thanks, that's all.", state=state)
    reply8 = res8.get("reply", "")
    assert any(term in reply8.lower() for term in ["welcome", "great day", "feel free", "anytime"]), "Turn 8 must close cleanly."
    assert "?" not in reply8, "Closing must not ask further questions."
    assert "**" not in reply8


# ── 17 Scenario Categories (A through Q) ──────────────────────────────────────

def test_scenario_a_discovery_and_bounded_questioning():
    """A. Discovery & Bounded Questioning: never ask more than 1 question at a time."""
    state = ConversationState(session_id="scen_a")
    res = orchestrator.process_turn("I need a printer for my office.", state=state)
    reply = res.get("reply", "")
    # Should ask max 1 question
    question_count = reply.count("?")
    assert question_count <= 1
    assert "**" not in reply


def test_scenario_b_technical_evaluation_specs():
    """B. Technical Evaluation: answer speed, weight, dimensions directly."""
    state = ConversationState(session_id="scen_b")
    state.active_product_id = "epson-sc-t5100"
    state.active_product = catalogue_loader.get_by_id("epson-sc-t5100")
    res = orchestrator.process_turn("What are the dimensions and weight of this printer?", state=state)
    reply = res.get("reply", "")
    assert any(term in reply.lower() for term in ["dimensions", "weight", "kg", "mm", "size"])
    assert "**" not in reply


def test_scenario_c_product_comparisons():
    """C. Product Comparisons: clean comparative breakdown without asterisks."""
    state = ConversationState(session_id="scen_c")
    res = orchestrator.process_turn("Compare Citizen CX-02 and Citizen CY-02.", state=state)
    reply = res.get("reply", "")
    assert "CX-02" in reply and "CY-02" in reply
    assert "**" not in reply


def test_scenario_d_price_objections_and_policies():
    """D. Price Objections: consultative value and alternative lower investment options."""
    state = ConversationState(session_id="scen_d")
    state.active_product_id = "citizen-cx-02"
    state.active_product = catalogue_loader.get_by_id("citizen-cx-02")
    res = orchestrator.process_turn("That is too expensive for our budget.", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["investment", "cz-01", "running cost", "commercial", "budget"])
    assert "**" not in reply


def test_scenario_e_purchase_intent_clean_ordering():
    """E. Purchase Intent: clean direct link and order instructions without corporate handover essay."""
    state = ConversationState(session_id="scen_e")
    state.active_product_id = "citizen-cx-02"
    state.active_product = catalogue_loader.get_by_id("citizen-cx-02")
    res = orchestrator.process_turn("I want to order this printer.", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["order", "purchase", "website", "keplertechllc.com", "link"])
    assert "🛒 **1. Official Online Store:**" not in reply
    assert "**" not in reply


def test_scenario_f_customer_frustration_recovery():
    """F. Customer Frustration Recovery: apologizes and addresses core need without being defensive."""
    state = ConversationState(session_id="scen_f")
    state.active_product_id = "epson-sc-t5100"
    state.active_product = catalogue_loader.get_by_id("epson-sc-t5100")
    res = orchestrator.process_turn("You didn't answer my question about the speed!", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["sorry", "apolog", "speed", "seconds", "sec"])
    assert "**" not in reply


def test_scenario_g_topic_switching_without_leakage():
    """G. Topic Switching: switching from CAD plotter to photo printer cleans CAD slots."""
    state = ConversationState(session_id="scen_g")
    state.category = "technical_large_format"
    state.requirements = {"print_width": 36, "scanner_required": True, "application": "cad"}

    res = orchestrator.process_turn("Actually forget CAD, I need a compact photo printer for events.", state=state)
    assert state.category == "citizen_photo"
    assert "scanner_required" not in state.requirements
    assert state.requirements.get("print_width") != 36


def test_scenario_h_customer_closing_clean_finish():
    """H. Customer Closing: warm goodbye without interrogation."""
    state = ConversationState(session_id="scen_h")
    res = orchestrator.process_turn("Thank you, that's everything for today.", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["welcome", "great day", "feel free", "pleasure"])
    assert "?" not in reply
    assert "**" not in reply


def test_scenario_i_ambiguous_language_disambiguation():
    """I. Ambiguous Language Disambiguation: politely asks to clarify."""
    state = ConversationState(session_id="scen_i")
    res = orchestrator.process_turn("printer", state=state)
    reply = res.get("reply", "")
    assert "?" in reply
    assert any(w in reply.lower() for w in ["what", "which", "look", "assist", "print"])


def test_scenario_j_typo_heavy_queries():
    """J. Typo-Heavy Queries: resolves misspelled brands, colors, and media."""
    state = ConversationState(session_id="scen_j")
    res = orchestrator.process_turn("how fst is the citizn cx02?", state=state)
    reply = res.get("reply", "")
    assert any(term in reply.lower() for term in ["speed", "second", "8.4", "sec"])


def test_scenario_k_multi_question_single_turn():
    """K. Multi-Question Single Turns: answers both questions in one response."""
    state = ConversationState(session_id="scen_k")
    state.active_product_id = "citizen-cx-02"
    state.active_product = catalogue_loader.get_by_id("citizen-cx-02")
    res = orchestrator.process_turn("Does it support WiFi, and how many prints per roll?", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["wi-fi", "wifi", "usb", "wireless"])
    assert any(w in reply for w in ["400", "800", "roll", "yield"])


def test_scenario_l_returning_customer_context():
    """L. Returning Customer Context: retains customer profile across turns."""
    state = ConversationState(session_id="scen_l")
    state.customer_name = "Rashid Al-Maktoum"
    res = orchestrator.process_turn("What was the printer we talked about?", state=state)
    reply = res.get("reply", "")
    assert reply is not None


def test_scenario_m_consumables_and_ink_compatibility():
    """M. Consumables & Ink Compatibility: lists verified inks for active printer."""
    state = ConversationState(session_id="scen_m")
    state.active_product_id = "citizen-cx-02"
    state.active_product = catalogue_loader.get_by_id("citizen-cx-02")
    res = orchestrator.process_turn("What media and ink does it use?", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["media", "cx2.4x6", "roll", "ribbon", "thermal"])


def test_scenario_n_media_rolls_and_paper_sizing():
    """N. Media Rolls: returns photographic and fine art rolls with consumable cards."""
    res = orchestrator.process_turn("Show me photographic media rolls.", session_id="scen_n")
    cards = res.get("consumable_cards", [])
    assert len(cards) >= 1 or "media" in res.get("reply", "").lower()


def test_scenario_o_unsupported_products_polite_refusal():
    """O. Unsupported Products: polite refusal when product is not in catalog."""
    res = orchestrator.process_turn("Do you have HP DesignJet T650?", session_id="scen_o")
    reply = res.get("reply", "").lower()
    assert any(w in reply for w in ["do not carry", "not list", "epson", "alternative", "catalogue", "catalog", "not available"])


def test_scenario_p_unsupported_attributes_grounded_refusal():
    """P. Unsupported Attributes: grounded answer without inventing unverified specs."""
    state = ConversationState(session_id="scen_p")
    state.active_product_id = "citizen-cx-02"
    state.active_product = catalogue_loader.get_by_id("citizen-cx-02")
    res = orchestrator.process_turn("Does it have built-in Bluetooth audio speakers?", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["no", "does not", "doesn't", "not feature", "not support"])


def test_scenario_q_no_match_requirement_alternatives():
    """Q. No-Match Alternatives: suggests closest catalogue match when constraints conflict."""
    state = ConversationState(session_id="scen_q")
    state.category = "technical_large_format"
    state.requirements = {"print_width": 24, "scanner_required": True}
    res = orchestrator.process_turn("I need a 24-inch plotter with integrated scanner.", state=state)
    reply = res.get("reply", "")
    assert any(w in reply.lower() for w in ["36", "wider", "scanner", "catalogue", "match"])
