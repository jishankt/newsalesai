"""
Understanding Prompt Builder for Kepler Tech Conversational AI.
Constructs the system prompt and message history for the LLM classifier
that produces structured JSON understanding of customer messages.
"""

from typing import Dict, Any, List, Optional
from domain.conversation_types import Intent


# JSON Schema for Ollama structured output (format parameter)
UNDERSTANDING_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [i.value for i in Intent],
            "description": "The primary customer intent."
        },
        "dialogue_act": {
            "type": "string",
            "enum": ["informing", "requesting", "questioning", "correcting",
                     "confirming", "rejecting", "greeting", "thanking",
                     "complaining", "clarifying"],
            "description": "What the customer is doing conversationally."
        },
        "product_related": {
            "type": "boolean",
            "description": "Whether this message relates to products, printing, or equipment."
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence in the classification (0.0 to 1.0)."
        },
        "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative", "frustrated"],
            "description": "Customer emotional tone."
        },
        "language": {
            "type": "string",
            "description": "ISO 639-1 language code detected in the message."
        },
        "entities": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "product_category": {
                    "type": "string",
                    "enum": ["technical_cad", "photo_fine_art", "photo_booth",
                             "office_enterprise", "scanner", "consumable", ""]
                },
                "model_code": {"type": "string"},
                "print_size": {"type": "string"},
                "scan_required": {"type": "boolean"},
                "daily_volume": {"type": "integer"},
                "scanner_type": {"type": "string"},
                "correction_field": {"type": "string"},
                "correction_value": {"type": "string"},
                "item_reference": {"type": "integer"},
            },
            "description": "Extracted named entities from the message."
        },
        "requirement_updates": {
            "type": "object",
            "description": "Fields to update in the conversation state requirements."
        },
        "requested_action": {
            "type": "string",
            "enum": [
                "respond_socially", "ask_qualification_question",
                "search_products", "show_product_specs",
                "show_consumables", "compare_products",
                "provide_business_info", "provide_support",
                "ask_clarification", "close_conversation",
                "acknowledge_correction", "continue_qualification",
            ],
            "description": "What action the system should take."
        },
        "tool_request": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "arguments": {"type": "object"}
            },
            "description": "Optional tool call suggestion (Python will validate before executing)."
        }
    },
    "required": ["intent", "dialogue_act", "product_related", "confidence",
                  "sentiment", "entities", "requested_action"]
}


def build_understanding_system_prompt(
    state_summary: Dict[str, Any],
    allowed_intents: Optional[List[str]] = None,
) -> str:
    """
    Builds the system prompt for the LLM understanding classifier.
    """
    intents_list = allowed_intents or [i.value for i in Intent]
    intents_str = ", ".join(intents_list)

    # Build state context
    state_ctx = []
    if state_summary.get("customer_name"):
        state_ctx.append(f"Customer name: {state_summary['customer_name']}")
    if state_summary.get("category"):
        state_ctx.append(f"Active category: {state_summary['category']}")
    if state_summary.get("requirements"):
        reqs = ", ".join(f"{k}={v}" for k, v in state_summary["requirements"].items())
        state_ctx.append(f"Known requirements: {reqs}")
    if state_summary.get("pending_question"):
        state_ctx.append(f"Pending question: {state_summary['pending_question']}")
    if state_summary.get("active_product"):
        p_name = state_summary["active_product"].get("name", "unknown")
        state_ctx.append(f"Active product: {p_name}")
    if state_summary.get("awaiting_field"):
        state_ctx.append(f"Awaiting answer for: {state_summary['awaiting_field']}")

    state_block = "\n".join(f"  - {s}" for s in state_ctx) if state_ctx else "  - No context yet (new conversation)"

    return f"""You are a customer intent classifier for Kepler Tech LLC, a printing equipment company in Dubai.

Your job is to analyze the customer's latest message and return a structured JSON classification.

## Allowed Intents
{intents_str}

## Current Conversation State
{state_block}

## Classification Rules
1. If the customer introduces themselves (e.g., "my name is X"), intent = "customer_introduction", extract customer_name.
2. If the customer gives positive or negative feedback about the bot, intent = "positive_feedback" or "negative_feedback".
3. If the customer expresses frustration (e.g., "you already asked me that", "stop repeating"), intent = "frustration".
4. If the customer corrects a previous answer (e.g., "actually A0", "no scanner"), intent = "correction".
5. If the customer asks for a recommendation or consultative advice (e.g., "recommend now", "show options", "what do you recommend", "suggest options", "need a printer for CAD"), intent = "product_discovery" and requested_action = "search_products".
6. If the customer asks about inks/cartridges/consumables for a specific printer, intent = "consumables_query".
7. If the customer asks to compare products or asks superlative/comparative questions (e.g. "Which Citizen printer is the fastest?", "compare X and Y", "which is better", "fastest printer"), intent = "product_comparison" and requested_action = "compare_products".
8. If the customer asks a direct attribute or specification question about a product (e.g. "what is the print speed of CX-02", "what size does T3100 print", "specs of SC-P900"), intent = "product_question" and requested_action = "show_product_specs".
9. If the customer asks about business hours/location/contact, intent = "business_information".
10. If the customer reports a printer problem, intent = "troubleshooting".
10. If the message is a simple greeting, intent = "greeting".
11. If the message is thanks or goodbye, intent = "conversation_ending".
12. If the message is answering a pending question (like "A0", "yes", "around 60"), check the awaiting_field and classify appropriately.
13. If the intent is genuinely unclear, use "unclear". NEVER default to "product_discovery" for unclear messages.
14. Social messages (greetings, introductions, feedback) should set product_related = false.

## Entity Extraction
- Extract model codes (e.g., T3100, P900, SC-F100, CX-02, DS-790WN)
- Extract print sizes (A0, A1, A3, 4x6)
- Extract scanner preferences (yes/no)
- Extract daily volumes (numbers)
- Extract customer names from introductions
- Extract correction field and value when intent is "correction"

Return valid JSON matching the required schema. Do not add explanation text."""


def build_understanding_messages(
    customer_message: str,
    recent_turns: List[Dict[str, str]],
    state_summary: Dict[str, Any],
    max_turns: int = 6,
) -> list:
    """
    Builds the messages array for the Ollama classify() call.
    """
    system_prompt = build_understanding_system_prompt(state_summary)

    messages = [{"role": "system", "content": system_prompt}]

    # Add recent conversation turns for context (last N turns)
    for turn in recent_turns[-max_turns:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Add the current customer message
    messages.append({"role": "user", "content": f"Classify this customer message: \"{customer_message}\""})

    return messages
