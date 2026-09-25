"""
Grounded LLM Conversational Response Composer for Kepler Tech SalesAI.

Transforms verified evidence, deterministic drafts, and contextual state into
natural, professional, customer-attuned responses using local Ollama composition
with strict deterministic validation and fail-closed fallback.
"""

import re
import time
import logging
from typing import Optional, List, Dict, Any

from domain.response_context import ResponseContext
from ollama_client import OllamaClient
from prompts.response_prompt import build_composer_messages
from validation.deterministic_validator import deterministic_validator
from nlp.response_validator import validate_response

logger = logging.getLogger("response_composer")


class ResponseComposer:
    """
    Question-Aware, Grounded Conversational Response Composer.
    Ensures that:
    - Product truth comes solely from verified evidence.
    - Wording is natural, concise, and directly answers what the customer asked.
    - Zero hallucination or unverified claims escape to the user.
    """

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama_client = ollama_client
        self._offline_cooldown_until = 0.0

    def compose(
        self,
        context: ResponseContext,
        model_name: Optional[str] = None,
    ) -> str:
        """
        Composes a natural, grounded response from the provided ResponseContext.
        Falls back safely to context.deterministic_draft on any failure.
        """
        # 1. Deterministic Bypass
        if not context.deterministic_draft:
            return ""

        if not context.needs_naturalization:
            return context.deterministic_draft

        if not self.ollama_client:
            return context.deterministic_draft

        now = time.time()
        if now < getattr(self, "_offline_cooldown_until", 0.0):
            return context.deterministic_draft

        # 2. Decompose Multi-Part Questions if not already explicitly provided
        if not context.customer_questions:
            context.customer_questions = self._extract_customer_questions(
                context.original_message or context.normalized_message
            )

        # 3. Dynamic Length Assessment
        if context.expected_length == "dynamic":
            context.expected_length = self._determine_expected_length(
                context.original_message or context.normalized_message,
                context.intent
            )

        # 4. Build Grounded Messages
        messages = build_composer_messages(context)

        # 5. Execute LLM Composition with Fail-Closed Validation
        try:
            active_pid = None
            if context.verified_evidence.active_product:
                active_pid = context.verified_evidence.active_product.get("id")
            val_context = {
                "product_id": active_pid,
                "evidence": context.verified_evidence.to_dict(),
                "source": "catalog",
            }

            comp_res = self.ollama_client.compose(
                messages=messages,
                model=model_name,
                temperature=0.15,
            )

            if comp_res.get("success") and comp_res.get("response"):
                composed_text = comp_res["response"].strip()

                # Validate composed response against deterministic ground truth
                is_valid, violations = self._validate_composed_text(
                    composed_text=composed_text,
                    context=context,
                    val_context=val_context,
                )

                if is_valid:
                    self._offline_cooldown_until = 0.0
                    logger.info(f"Grounded response composed successfully ({comp_res.get('latency_ms')}ms)")
                    return composed_text

                logger.warning(f"Composed reply failed validation: {violations}. Attempting 1 regeneration.")

                # 6. Bounded Single Regeneration Attempt
                retry_messages = list(messages)
                retry_messages.append({"role": "assistant", "content": composed_text})
                retry_messages.append({
                    "role": "user",
                    "content": (
                        f"Your previous answer had validation violations: {violations}. "
                        f"Strictly adhere to VERIFIED_EVIDENCE. Fix these issues immediately and provide "
                        f"a compliant, natural response."
                    ),
                })

                regen_res = self.ollama_client.compose(
                    messages=retry_messages,
                    model=model_name,
                    temperature=0.1,
                )

                if regen_res.get("success") and regen_res.get("response"):
                    regen_text = regen_res["response"].strip()
                    is_valid_2, violations_2 = self._validate_composed_text(
                        composed_text=regen_text,
                        context=context,
                        val_context=val_context,
                    )
                    if is_valid_2:
                        self._offline_cooldown_until = 0.0
                        logger.info("Regenerated response passed validation successfully.")
                        return regen_text
                    logger.warning(f"Regenerated reply failed validation again: {violations_2}. Falling back to draft.")
            else:
                self._offline_cooldown_until = time.time() + 10.0

        except Exception as e:
            self._offline_cooldown_until = time.time() + 10.0
            logger.warning(f"Error during response composition: {e}. Falling back to deterministic draft.")

        # Safe Fail-Closed Fallback
        return context.deterministic_draft

    def _extract_customer_questions(self, message: str) -> List[str]:
        """
        Extracts individual clauses or questions from a single customer message.
        """
        text = message.strip()
        if not text:
            return []

        # Split by question marks or strong coordinating conjunctions with queries
        raw_parts = re.split(r"\?|\band\s+(?:can|does|is|what|how|which|do|has)\b", text, flags=re.IGNORECASE)
        questions: List[str] = []
        for part in raw_parts:
            cleaned = part.strip().strip(" ,;.-")
            if cleaned and len(cleaned.split()) >= 2:
                # Reconstruct question mark if it was a question
                if not cleaned.endswith("?"):
                    cleaned += "?"
                questions.append(cleaned)

        if not questions:
            questions = [text if text.endswith("?") else text + "?"]
        return questions

    def _determine_expected_length(self, message: str, intent: str) -> str:
        """
        Dynamically selects target response length based on the query depth.
        """
        words = message.strip().split()
        word_count = len(words)
        lower_msg = message.lower()

        # Extremely short queries: "wifi?", "scanner?", "price?", "a0?"
        if word_count <= 3 and not any(w in lower_msg for w in ["why", "compare", "difference", "recommend"]):
            return "short"

        # Comprehensive overview queries
        if any(w in lower_msg for w in ["tell me everything", "full specs", "complete details", "everything about"]):
            return "detailed"

        # Comparison queries
        if "compare" in lower_msg or "difference" in lower_msg:
            return "medium"

        # Suitability questions: "why this one?", "is it good for..."
        if "why" in lower_msg or "suitable" in lower_msg or "good for" in lower_msg:
            return "medium"

        return "dynamic"

    def _validate_composed_text(
        self,
        composed_text: str,
        context: ResponseContext,
        val_context: Dict[str, Any],
    ) -> tuple[bool, List[str]]:
        """
        Validates the composed text using both deterministic catalog fact-checking
        and conversational quality checks.
        """
        if not composed_text or len(composed_text.strip()) < 3:
            return False, ["empty_or_too_short"]

        # 1. Deterministic Catalog Fact Validator
        is_det_valid, det_violations = deterministic_validator.validate(
            composed_text, context=val_context
        )
        if not is_det_valid:
            return False, det_violations

        # 2. Conversational Policy Validator (max 1 question, no unverified discounts)
        conv_val = validate_response(
            response=composed_text,
            previous_response=context.recent_history[-1].get("content") if context.recent_history else None,
            context_intent=context.intent,
        )
        if not conv_val.valid:
            return False, conv_val.violations

        # 3. Follow-up Question Guard: If no allowed follow-up, forbid ending in a question
        if not context.allowed_followup and composed_text.strip().endswith("?"):
            if "?" in composed_text:
                return False, ["unauthorized_followup_question"]

        # 4. Answer Coverage Validation (Section 25)
        # Ensure all requested attributes are answered or explicitly noted as unlisted
        if context.requested_attributes:
            text_lower = composed_text.lower()
            missing = []
            for attr in context.requested_attributes:
                if attr == "scanner":
                    if not re.search(r"\b(?:scanner|scan|scanning|mfp|multifunction|print-only|print\s+only)\b", text_lower):
                        missing.append("coverage:scanner")
                elif attr == "wifi":
                    if not re.search(r"\b(?:wifi|wi-fi|wireless|network|ethernet|connect|connectivity)\b", text_lower) and "not listed" not in text_lower:
                        missing.append("coverage:wifi")
                elif attr in ("compatible_ink", "ink"):
                    if not re.search(r"\b(?:ink|ultrachrome|durabrite|cartridge|c13|t\d{4}|ribbon|toner)\b", text_lower) and "not listed" not in text_lower:
                        missing.append("coverage:ink")
                elif attr == "speed":
                    if not re.search(r"\b(?:speed|ppm|sec|second|fast|faster|minute)\b", text_lower) and "not listed" not in text_lower:
                        missing.append("coverage:speed")
                elif attr == "price":
                    if not re.search(r"\b(?:aed|price|cost|quote|request|quotation)\b", text_lower):
                        missing.append("coverage:price")
                elif attr in ("dimensions", "size"):
                    if not re.search(r"\b(?:dimension|dimensions|cm|mm|width|footprint|weight|kg)\b", text_lower) and "not listed" not in text_lower:
                        missing.append("coverage:dimensions")

            if missing:
                return False, missing

        return True, []
