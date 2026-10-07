"""
Social Route for Kepler Tech Conversational AI.
Handles greetings, name introductions, feedback, frustration, thanks,
and small talk WITHOUT triggering product search or RAG.

Critical rule: social messages must NOT remove product state.
When handling "my name is Jishan" mid-qualification, save the name
and then resume the pending question.
"""

import logging
from domain.conversation_types import Intent, LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState

logger = logging.getLogger("route:social")


def handle(understanding: LLMUnderstanding, state: ConversationState) -> RouteResult:
    """Handle social intents. Never touches product state."""
    intent = understanding.intent
    entities = understanding.entities

    # ── Customer introduction ────────────────────────────────────────────
    if intent == Intent.CUSTOMER_INTRODUCTION:
        name = entities.get("customer_name", "").strip()
        if name:
            state.customer_name = name
            logger.info(f"Customer introduced as: {name}")

        # Check if there's a pending question to resume
        pending = state.pending_question
        if pending and name:
            reply = f"Pleasure to meet you, {name}! {pending}"
            state.consume_pending_question()
        elif name:
            reply = f"Pleasure to meet you, {name}! How can I assist you with your printing equipment or consumables today?"
        else:
            reply = "Pleasure to meet you! How can I assist you with your printing equipment or consumables today?"

        return RouteResult(
            reply=reply,
            suggested_chips=[],
            source="route:social",
        )

    # ── Greeting ─────────────────────────────────────────────────────────
    if intent == Intent.GREETING:
        if not state.history_turns or len(state.history_turns) <= 1:
            state.candidate_products = []
            state.active_product = None
            state.requirements = {}
            state.category = None
        if state.customer_name:
            reply = f"Hello, {state.customer_name}! Great to connect with you. How can I help you find the right printing setup or consumables today?"
        else:
            reply = "Hello and welcome to Kepler Tech! How can I assist you with your printing solutions today?"

        return RouteResult(
            reply=reply,
            suggested_chips=["Office & Business Printers", "Technical CAD Plotters", "Photo & Fine Art", "Dye-Sublimation (T-Shirts & Mugs)"],
            product_cards=[],
            consumable_cards=[],
            source="route:social",
        )

    # ── Positive feedback ────────────────────────────────────────────────
    if intent == Intent.POSITIVE_FEEDBACK:
        reply = "Delighted to help! Whenever you're ready to dive deeper into technical specifications, media choices, or genuine supplies, I'm right here."
        return RouteResult(reply=reply, source="route:social")

    # ── Negative feedback ────────────────────────────────────────────────
    if intent == Intent.NEGATIVE_FEEDBACK:
        state.record_frustration()
        pending = state.pending_question

        if state.frustration_count >= 2:
            reply = "I completely understand your frustration, and I apologize for missing the mark. Let me step back and give you exactly what you need."
            if pending:
                reply += f" {pending}"
                state.consume_pending_question()
        else:
            reply = "I hear you, and appreciate the feedback. Let's get straight to the solution—how can I best assist you right now?"

        return RouteResult(reply=reply, source="route:social")

    # ── Frustration ──────────────────────────────────────────────────────
    if intent == Intent.FRUSTRATION:
        state.record_frustration()

        if state.frustration_count >= 3:
            reply = "I sincerely apologize for the inconvenience. Let me skip the formalities and focus directly on solving this for you."
        elif "repeat" in (understanding.entities.get("complaint", "") or "").lower() or \
             state.frustration_count >= 2:
            reply = "You're completely right, and I apologize for repeating myself. Moving forward with what you've shared so far:"
        else:
            reply = "I understand your point completely. Let me adjust my approach and focus directly on what you need."

        # Don't ask a new question when frustrated — just acknowledge
        return RouteResult(reply=reply, source="route:social")

    # ── Small talk ───────────────────────────────────────────────────────
    if intent == Intent.SMALL_TALK:
        pending = state.pending_question
        if pending:
            reply = f"Thank you! To continue with your printing setup: {pending}"
            state.consume_pending_question()
        else:
            reply = "I'm always glad to help! What printing equipment, photo printer, or genuine consumables can I assist you with today?"
        return RouteResult(
            reply=reply,
            suggested_chips=[],
            source="route:social",
        )

    # ── Conversation ending ──────────────────────────────────────────────
    if intent == Intent.CONVERSATION_ENDING:
        name_suffix = f", {state.customer_name}" if state.customer_name else ""
        reply = f"Thank you for contacting Kepler Tech LLC{name_suffix}! If you need official quotations, technical data, or delivery arrangements, we're always here to assist. Have a wonderful day!"
        state.stage = "closing"
        return RouteResult(reply=reply, source="route:social")

    # ── Fallback for any other social intent ─────────────────────────────
    return RouteResult(
        reply="How can I help you today?",
        suggested_chips=[],
        source="route:social",
    )
