"""
Qualification Route for Kepler Tech Conversational AI.
Wraps the unified NextQuestionEngine and RequirementExtractor to ask
exactly one question at a time, never repeat already-answered fields,
and support corrections and topic switches mid-qualification.
"""

import logging
import re
from domain.conversation_types import Intent, LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState
from conversation.next_question_engine import NextQuestionEngine
from conversation.requirement_extractor import requirement_extractor

logger = logging.getLogger("route:qualification")
_next_q = NextQuestionEngine()


def handle(understanding: LLMUnderstanding, state: ConversationState, raw_message: str = "") -> RouteResult:
    """
    Handle qualification flow:
    1. Apply category detection & topic switching
    2. Extract and update requirements from raw message and entities
    3. Ask the next unanswered question or transition to recommendation
    """
    entities = understanding.entities
    intent = understanding.intent
    msg_lower = (raw_message or "").strip().lower()

    # ── 1. Dynamic Category Detection & Switching ────────────────────────
    detected_cat = None
    ent_cat = (entities.get("product_category") or "").strip().lower()
    if ent_cat in ["technical_cad", "photo_fine_art", "photo_booth", "office_enterprise", "scanner", "consumable"]:
        detected_cat = ent_cat

    if not detected_cat:
        if any(k in msg_lower for k in ["cad", "plotter", "blueprint", "architect", "engineering", "technical drawing", "technical & cad", "technical_cad"]):
            detected_cat = "technical_cad"
        elif any(k in msg_lower for k in ["photo booth", "dye-sub", "citizen cx", "citizen cy", "events", "photo_booth"]):
            detected_cat = "photo_booth"
        elif any(k in msg_lower for k in ["photo fine art", "fine art", "photo & fine art", "gallery", "exhibition", "p900", "p700", "p5300", "p7500", "p9500", "photo_fine_art", "photography"]):
            detected_cat = "photo_fine_art"
        elif any(k in msg_lower for k in ["office", "enterprise", "workforce", "copier", "am-c4000", "am-c550", "mfp", "office_enterprise", "business printer"]):
            detected_cat = "office_enterprise"
        elif not any(neg in msg_lower for neg in ["no scanner", "without scanner", "not scanner", "don't need scanner", "dont need scanner", "print only"]) and any(k in msg_lower for k in ["scanner", "document scan", "scanning", "document scanners"]):
            detected_cat = "scanner"
        elif any(k in msg_lower for k in ["ink", "cartridge", "toner", "ribbon", "consumable", "maintenance box"]):
            detected_cat = "consumable"
        elif any(k in msg_lower for k in ["want a printer", "buy a printer", "looking for a printer", "need a printer"]):
            # Customer was in scanner and switched to general printer
            if state.category == "scanner":
                detected_cat = "technical_cad"

    # Distinguish general photo inquiry if category is not yet specified
    if not detected_cat and (not state.category or state.awaiting_field in ("category", "photo_category")):
        if any(k in msg_lower for k in ["photo printer", "photo printers", "photo printing", "photos", "photo", "pictures", "picture printer"]):
            state.awaiting_field = "photo_category"
            clarify_q = (
                "We offer two distinct photo printer solutions: **Photo & Fine Art** (Epson SureColor wide-format printers for galleries and professional photography) "
                "and **Photo Booth / Dye-Sub** (Citizen compact instant printers for events and kiosks). Which of these fits your requirements?"
            )
            state.save_pending_question(clarify_q, "photo_category")
            return RouteResult(
                reply=clarify_q,
                suggested_chips=["Photo Booth / Dye-Sub", "Photo & Fine Art"],
                source="route:qualification",
            )

    if detected_cat:
        # Switch category if not set or if customer explicitly changes category
        if not state.category or state.category != detected_cat:
            if state.category is None or any(kw in msg_lower for kw in ["actually", "instead", "switch", "want a printer", "buy a printer", "need a printer", "want a scanner", "looking for", "photo"]):
                state.reset_category(detected_cat)
                logger.info(f"Category switched to: {detected_cat}")
            elif not state.category:
                state.reset_category(detected_cat)
        if state.awaiting_field in ("category", "photo_category"):
            state.awaiting_field = None

    # ── 2. Extract Verified Requirements ─────────────────────────────────
    extracted = requirement_extractor.extract_and_validate(raw_message, state)
    if extracted:
        state.requirements.update(extracted)
        state.active_product = None
        state.candidate_products = []

    # Handle volume numbers (e.g. "10000 per month", "50 per day", "20")
    vol_match = re.search(r"\b(\d{1,6})\b", msg_lower)
    if vol_match:
        try:
            val = int(vol_match.group(1))
            if "month" in msg_lower:
                val = max(1, val // 30)  # Convert monthly to approximate daily
            state.requirements["daily_volume"] = "high" if val >= 50 else ("medium" if val >= 10 else "low")
            if state.awaiting_field == "daily_volume":
                state.awaiting_field = None
        except ValueError:
            pass

    # Handle scanner-specific keywords
    if state.category == "scanner":
        if any(kw in msg_lower for kw in ["document", "invoice", "paper", "sheet", "sheetfed", "high-speed", "high speed", "duplex"]):
            state.requirements["document_type"] = "standard_documents"
            state.awaiting_field = None
        elif any(kw in msg_lower for kw in ["photo", "book", "bound", "id", "card", "passport", "flatbed"]):
            state.requirements["document_type"] = "flatbed_ids"
            state.awaiting_field = None
        elif any(kw in msg_lower for kw in ["nothing", "general", "normal", "any", "standard", "all"]):
            state.requirements["document_type"] = "standard_documents"
            state.awaiting_field = None

    # Handle "nothing", "skip", "any", "none", "don't know"
    if any(s in msg_lower for s in ["nothing", "skip", "any", "no preference", "default", "dont know", "don't know"]):
        if state.awaiting_field:
            state.requirements[state.awaiting_field] = "standard"
            state.awaiting_field = None

    # Handle corrections
    if intent == Intent.CORRECTION:
        field = entities.get("correction_field")
        value = entities.get("correction_value")
        if field and value is not None:
            state.requirements[field] = value
            state.active_product = None
            state.candidate_products = []

    # ── 3. Check for recommendation triggers or skip ─────────────────────
    rec_keywords = ["recommend now", "recommend", "show options", "show recommendations",
                    "what do you recommend", "suggest options", "show me options",
                    "give me options", "just show"]
    if any(k in msg_lower for k in rec_keywords):
        state.stage = "recommending"
        state.awaiting_field = None
        return RouteResult(
            reply="__READY_FOR_SEARCH__",
            source="route:qualification",
        )

    # ── 4. Deterministic Next Question ───────────────────────────────────
    state.stage = "qualifying"
    next_step = _next_q.evaluate_next_step(state)

    if next_step:
        question = next_step["question"]
        pills = next_step.get("pills", [])
        field = next_step.get("field", "")

        state.save_pending_question(question, field)

        return RouteResult(
            reply=question,
            suggested_chips=pills,
            source="route:qualification",
        )

    # All requirements collected -> Ready for product recommendation
    state.stage = "recommending"
    return RouteResult(
        reply="__READY_FOR_SEARCH__",
        source="route:qualification",
    )

