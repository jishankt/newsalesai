"""
LLM Understanding Module for Kepler Tech Conversational AI.
Sends customer messages to the local Ollama model for structured intent
classification. Returns a validated LLMUnderstanding dataclass.

If the LLM is unavailable or returns invalid JSON, falls back to
intent="unclear" with requested_action="ask_clarification".
"""

import logging
from typing import Dict, Any, List, Optional

from domain.conversation_types import LLMUnderstanding, Intent
from prompts.understanding_prompt import (
    build_understanding_messages,
    UNDERSTANDING_SCHEMA,
)
from ollama_client import OllamaClient

logger = logging.getLogger("llm_understanding")


class LLMUnderstandingEngine:
    """Wraps the Ollama classify() call with validation and fallback."""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client

    def understand(
        self,
        customer_message: str,
        recent_turns: List[Dict[str, str]],
        state_summary: Dict[str, Any],
        model: str = None,
    ) -> LLMUnderstanding:
        """
        Classify the customer message using the local LLM.

        Returns a validated LLMUnderstanding. On any failure,
        returns intent=UNCLEAR with requested_action=ask_clarification.
        """
        if not self.client:
            logger.warning("No Ollama client configured — returning fallback understanding.")
            return self._fallback()

        # Check fast path to bypass 12s LLM classify when answer is deterministic
        if self.is_deterministic_fast_path(customer_message, state_summary):
            fast = self._fallback(customer_message)
            if fast.intent != Intent.UNCLEAR:
                logger.info(f"Fast-path classification (<1ms): intent={fast.intent.value} action={fast.requested_action}")
                return fast

        # Build messages for the classifier
        messages = build_understanding_messages(
            customer_message=customer_message,
            recent_turns=recent_turns,
            state_summary=state_summary,
        )

        # Call Ollama structured output
        result = self.client.classify(
            messages=messages,
            schema=UNDERSTANDING_SCHEMA,
            model=model,
        )

        if not result.get("success") or not result.get("result"):
            err_kind = result.get("error_kind", "UNKNOWN")
            reason = result.get("fallback_reason", "No result returned")
            logger.warning(f"LLM classify failed [{err_kind}]: {reason} — utilizing rule-based fallback understanding engine.")
            return self._fallback(customer_message)

        raw = result["result"]
        logger.info(f"LLM understanding raw: intent={raw.get('intent')} "
                     f"confidence={raw.get('confidence')} "
                     f"action={raw.get('requested_action')}")

        # Parse and validate through the dataclass
        understanding = LLMUnderstanding.from_dict(raw)

        # Safety: if confidence is very low, treat as unclear
        if understanding.confidence < 0.3 and understanding.intent != Intent.UNCLEAR:
            logger.info(f"Low confidence ({understanding.confidence}) — overriding to UNCLEAR")
            understanding.intent = Intent.UNCLEAR
            understanding.requested_action = "ask_clarification"

        return understanding

    def is_deterministic_fast_path(self, customer_message: str, state_summary: Dict[str, Any] = None) -> bool:
        """Determines whether message can be resolved deterministically without a slow LLM classify call."""
        msg_l = (customer_message or "").strip().lower()
        words = msg_l.split()
        if not words:
            return True

        # Pure short qualification answers (<= 4 words)
        if len(words) <= 4:
            # Boolean
            if any(w in msg_l for w in ["yes", "no", "yep", "nope", "need scanner", "no scanner", "without scanner", "with scanner", "print only"]):
                return True
            # Size
            if any(s in msg_l for s in ["a0", "a1", "a2", "a3", "4x6", "6x8", "24\"", "36\""]) or "mostly 4x6" in msg_l:
                return True
            # Volume
            if any(ch.isdigit() for ch in msg_l) and (any(w in msg_l for w in ["drawing", "print", "day", "daily", "around", "about", "approx"]) or len(words) == 1):
                return True
            # Corrections
            if "actually" in msg_l:
                return True
            # Recommendations
            if any(k in msg_l for k in ["recommend now", "recommend", "show options", "give me options", "show another", "show another one"]):
                return True

        # Direct product comparisons & superlatives
        if any(w in msg_l for w in [
            "compare", " vs ", " versus ", "which is better", "which is best",
            "fastest", "faster", "highest speed", "quickest", "widest",
            "highest resolution", "largest width", "most compact", "difference between",
            "which citizen", "which epson", "which printer is faster", "which printer is fastest"
        ]):
            return True

        # Direct product attribute questions
        if any(w in msg_l for w in ["how fast", "what is the speed", "what speed", "print speed", "what size can it", "what width", "how wide"]):
            return True

        # Pronoun questions on active product
        if any(p in msg_l for p in ["does it", "can it", "what size can it", "what ink does it", "what ink does the", "why this one", "which is better"]):
            return True

        # Specific model codes
        import re
        if re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3}[a-z]?|cx-?\d{2}|cy-?\d{2}|cz-?\d{2}|am-?c\d{3,4}|wf-?c\d{3,4}[a-z]?)\b", msg_l):
            return True

        # Consumables / Inks / Colors
        if any(w in msg_l for w in ["yellow", "cyan", "magenta", "black", "matte black", "photo black", "gray", "grey", "violet", "orange", "green", "ink", "inks", "cartridge", "cartridges", "maintenance box", "ribbon"]):
            return True

        # Business info questions
        if any(w in msg_l for w in ["delivery", "shipping", "deliver", "ship", "address", "location", "dubai", "where are you", "office hours", "timings", "contact number", "phone number", "whatsapp", "email", "companies", "brands you provide", "what brands"]):
            return True

        return False

    def _fallback(self, customer_message: str = "") -> LLMUnderstanding:
        """Intelligent fallback when LLM is unavailable or times out."""
        msg_l = (customer_message or "").strip().lower()
        entities = {}
        intent = Intent.UNCLEAR
        action = "ask_clarification"

        import re
        # Model codes
        m_code = re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3}[a-z]?|cx-?\d{2}|cy-?\d{2}|cz-?\d{2}|am-?c\d{3,4}|wf-?c\d{3,4}[a-z]?)\b", msg_l)
        if m_code:
            entities["model_code"] = m_code.group(0).upper()
            intent = Intent.PRODUCT_QUESTION
            action = "show_product_specs"

        # Business info
        if any(w in msg_l for w in ["delivery", "shipping", "deliver", "ship", "address", "location", "dubai", "where are you", "office hours", "timings", "open", "contact", "phone", "email", "whatsapp", "companies", "what brands"]):
            intent = Intent.BUSINESS_INFORMATION
            action = "provide_business_info"

        # Direct Comparisons & Superlatives (PRIORITY over discovery)
        comp_keywords = [
            "compare", " vs ", " versus ", "which is better", "which is best",
            "fastest", "faster", "highest speed", "quickest", "widest",
            "highest resolution", "largest width", "most compact", "difference between",
            "which citizen", "which epson", "which printer is faster", "which printer is fastest",
            "epson or citizen", "citizen or epson"
        ]
        if any(w in msg_l for w in comp_keywords):
            intent = Intent.PRODUCT_COMPARISON
            action = "compare_products"
            if "citizen" in msg_l:
                entities["brand"] = "Citizen"
            if "epson" in msg_l:
                entities["brand"] = "Epson"

        # Direct Product Attribute Questions on active product or pronoun
        elif any(w in msg_l for w in [
            "does it", "can it", "what size", "how fast", "what is the speed", "what speed",
            "print speed", "what width", "how wide", "specs", "specifications", "why this one"
        ]):
            intent = Intent.PRODUCT_QUESTION
            action = "show_product_specs"

        # Sizes
        if "a0" in msg_l or "36-inch" in msg_l or "36\"" in msg_l:
            entities["print_size"] = "A0"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "a1" in msg_l or "24-inch" in msg_l or "24\"" in msg_l:
            entities["print_size"] = "A1"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "4x6" in msg_l or "6x8" in msg_l:
            entities["print_size"] = "4x6"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"

        # Volume
        vol = re.search(r"\b(\d{1,4})\b", msg_l)
        if vol and any(vkw in msg_l for vkw in ["print", "drawing", "day", "daily", "around", "about", "approx", "volume"]):
            entities["daily_volume"] = int(vol.group(1))
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "search_products"
        elif vol and len(msg_l.split()) <= 3 and any(ch.isdigit() for ch in msg_l):
            entities["daily_volume"] = int(vol.group(1))
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "search_products"

        # Scanner preference
        if any(w in msg_l for w in ["no scanner", "without scanner", "print only"]):
            entities["scan_required"] = False
        elif any(w in msg_l for w in ["need scanner", "with scanner", "has scanner", "yes scanner"]):
            entities["scan_required"] = True

        # Corrections
        if "actually" in msg_l:
            intent = Intent.CORRECTION
            action = "acknowledge_correction"

        # Confirmations / Rejections
        if intent == Intent.UNCLEAR:
            if any(w in msg_l for w in ["yes", "yep", "yeah", "sure", "need scanner", "with scanner"]):
                intent = Intent.CONFIRMATION
                action = "continue_qualification"
            elif any(w in msg_l for w in ["no", "nope", "no scanner", "without scanner", "print only"]):
                intent = Intent.REJECTION
                action = "continue_qualification"

        # Consumables / Colors
        if any(k in msg_l for k in [
            "consumable", "consumables", "ink", "inks", "cartridge", "cartridges",
            "toner", "ribbon", "what ink", "which ink", "maintenance box",
            "yellow", "cyan", "magenta", "photo black", "matte black", "light cyan", "light magenta", "gray", "grey", "violet", "orange", "green"
        ]):
            intent = Intent.CONSUMABLES_QUERY
            action = "show_consumables"

        # Discovery / Recommendations
        if intent == Intent.UNCLEAR and any(k in msg_l for k in ["recommend now", "recommend", "options", "printer", "plotter", "scanner", "cad"]):
            intent = Intent.PRODUCT_DISCOVERY
            action = "search_products"

        return LLMUnderstanding(
            intent=intent,
            confidence=0.90 if intent != Intent.UNCLEAR else 0.0,
            entities=entities,
            requested_action=action,
            product_related=intent in (Intent.PRODUCT_DISCOVERY, Intent.PRODUCT_QUESTION, Intent.PRODUCT_COMPARISON, Intent.CONSUMABLES_QUERY),
        )


# Module-level singleton (client injected later during app init)
llm_engine = LLMUnderstandingEngine()
