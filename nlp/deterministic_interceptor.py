"""
Deterministic Interceptor for Kepler Tech Conversational AI.

Runs BEFORE any LLM call to fast-path messages that must always behave
deterministically: price/discount refusals, greetings, thanks, empty input,
reset requests, and prompt injection attempts.

Complex customer meaning is NOT handled here — only cases that must
always produce the same output regardless of conversation context.
"""

import re
from typing import Optional
from domain.conversation_types import InterceptResult
from guardrails import (
    check_user_intent_for_pricing_or_discount,
    is_discount_inquiry,
    is_price_inquiry,
    PRICE_REFUSAL,
    DISCOUNT_REFUSAL,
)


# ── Patterns for deterministic interception ──────────────────────────────

_GREETING_PATTERN = re.compile(
    r"^(?:hi+|hello+|helo+|hey+|hlo|hola|good\s+(?:morning|afternoon|evening)|howdy|assalamu\s*alaikum|marhaba)[\s!.]*$",
    re.IGNORECASE,
)

_ENDING_PATTERN = re.compile(
    r"^(?:thanks?|thank\s+you|bye|goodbye|good\s*bye|that'?s?\s+all|have\s+a\s+(?:good|nice)\s+day|see\s+ya?)[\s!.]*$",
    re.IGNORECASE,
)

_RESET_PATTERN = re.compile(
    r"^(?:start\s+over|reset|clear|new\s+conversation|begin\s+again)[\s!.]*$",
    re.IGNORECASE,
)

_INJECTION_PATTERNS = [
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"alert\s*\(", re.IGNORECASE),
    re.compile(r"(?:ignore|disregard|forget)\s+(?:previous|earlier|all|prior|everything)\s*(?:instructions?|context|prompts?)?", re.IGNORECASE),
    re.compile(r"(?:tell|show|output|reveal|print|repeat)\s+(?:me\s+)?(?:your\s+)?(?:system\s+prompt|developer\s+prompt|base\s+instructions?|initial\s+prompt|rules?|internal\s+prompt)", re.IGNORECASE),
    re.compile(r"what\s+(?:is|are)\s+your\s+(?:instructions?|rules?|system\s+prompt|developer\s+prompt|prompt)", re.IGNORECASE),
    re.compile(r"(?:act|pretend|behave)\s+as\s+(?:if|a|an|dan|developer|terminal)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the|dan|unrestricted|in\s+developer\s+mode)", re.IGNORECASE),
    re.compile(r"\b(?:jailbreak|dan\s+mode|developer\s+mode|prompt\s+injection|system\s+override|override\s+(?:rules|system))\b", re.IGNORECASE),
    re.compile(r"repeat\s+(?:the\s+)?(?:text\s+)?above", re.IGNORECASE),
]

_UNRELATED_PATTERNS = [
    re.compile(r"\b(?:recipe|cook|bake|cooking|weather|forecast|who won|football|cricket|basketball|movie|song|poem|joke|horoscope|capital of|president of|prime minister of)\b", re.IGNORECASE),
    re.compile(r"\b(?:write code in|python script to hack|generate password|bitcoin|crypto trading|flight booking|hotel booking)\b", re.IGNORECASE),
]

_EMPTY_THRESHOLD = 2  # Messages with <= this many non-whitespace chars are "empty"


def intercept(message: str, raw_message: Optional[str] = None) -> InterceptResult:
    """
    Fast-path deterministic interception. Returns InterceptResult.

    If matched=True and should_continue=False, the caller should return
    the response directly without calling LLM or product tools.

    If matched=True and should_continue=True, the caller should note the
    intent/entities but proceed to the LLM for richer handling.

    If matched=False, proceed normally.
    """
    text = (message or "").strip()

    # ── 1. Simple greetings (check before empty threshold since "hi" = 2 chars) ──
    if _GREETING_PATTERN.match(text) and len(text.split()) <= 5:
        return InterceptResult(
            matched=True,
            intent="greeting",
            response="Hello! Welcome to Kepler Tech LLC. How can I assist you with your printing solutions today?",
            should_continue=False,
            suggested_chips=[],
        )

    # ── 2. Thanks / goodbye ─────────────────────────────────────────────
    if _ENDING_PATTERN.match(text):
        return InterceptResult(
            matched=True,
            intent="conversation_ending",
            response="Thank you for contacting Kepler Tech LLC! Feel free to reach out anytime you need help with printing equipment or consumables.",
            should_continue=False,
            suggested_chips=[],
        )

    # ── 3. Empty / non-alphanumeric messages ────────────────────────────
    stripped = text.replace(" ", "")
    if len(stripped) == 0 or (len(stripped) == 1 and not stripped.isalnum()):
        return InterceptResult(
            matched=True,
            intent="empty",
            response="How can I help you today? Feel free to ask about our printers, scanners, or consumables.",
            should_continue=False,
            suggested_chips=[],
        )

    # ── 4. Prompt injection / adversarial attempts (Security First) ──────
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text) or pattern.search(raw_message or ""):
            return InterceptResult(
                matched=True,
                intent="out_of_scope",
                response="I'm a product assistant for Kepler Tech LLC. I can help you find printers, scanners, and consumables. What would you like to explore?",
                should_continue=False,
                suggested_chips=[],
            )

    # ── 5. Explicitly unrelated out-of-scope questions ──────────────────
    for pattern in _UNRELATED_PATTERNS:
        if pattern.search(text):
            return InterceptResult(
                matched=True,
                intent="out_of_scope",
                response="I am a specialized product assistant for Kepler Tech LLC. I can assist you with large format technical plotters, photo printers, office enterprise MFPs, document scanners, and genuine consumables. How can I assist you with your printing requirements today?",
                should_continue=False,
                suggested_chips=["Large Format Plotters", "Photo Printers", "Office MFPs", "Document Scanners"],
            )

    # ── 6. Price / discount handling ────────────────────────────────────
    msg_to_check = raw_message or text
    if is_discount_inquiry(msg_to_check):
        return InterceptResult(
            matched=True,
            intent="discount_inquiry",
            response=DISCOUNT_REFUSAL,
            should_continue=False,
            suggested_chips=["Large Format Plotters", "Photo Printers", "Office MFPs", "View Consumables"],
        )

    if is_price_inquiry(msg_to_check):
        return InterceptResult(
            matched=True,
            intent="price_inquiry",
            response="",
            should_continue=True,
            suggested_chips=[],
        )

    # ── 6. Reset requests ────────────────────────────────────────────────
    if _RESET_PATTERN.match(text):
        return InterceptResult(
            matched=True,
            intent="reset",
            response="No problem! Let's start fresh. What can I help you with?",
            should_continue=False,
            suggested_chips=[],
        )

    # ── No match — pass through to LLM ──────────────────────────────────
    return InterceptResult(matched=False)
