"""
Grounded LLM Conversational Response Composer for Kepler Tech SalesAI.

Transforms verified evidence, deterministic drafts, and contextual state into
natural, professional, customer-attuned responses using local Ollama composition
with strict deterministic validation and fail-closed fallback to the verified answer plan.
"""

import re
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

from domain.response_context import ResponseContext, AnswerPlan
from ollama_client import OllamaClient
from prompts.response_prompt import build_composer_messages
from validation.deterministic_validator import deterministic_validator
from nlp.response_validator import validate_response

logger = logging.getLogger("response_composer")


class ResponseComposer:
    """
    Question-Aware, Grounded Conversational Response Composer.
    Ensures that:
    - Product truth comes solely from verified evidence and explicit answer plan.
    - Wording is natural, concise, and directly answers what the customer asked.
    - Zero hallucination or unverified claims escape to the user.
    - Fallback is strictly grounded in the verified plan rather than an inaccurate draft.
    """

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama_client = ollama_client
        self._offline_cooldown_until = 0.0
        self.last_composition_succeeded = False

    def compose(
        self,
        context: ResponseContext,
        model_name: Optional[str] = None,
    ) -> str:
        """
        Composes a natural, grounded response from the provided ResponseContext.
        Falls back safely to the verified AnswerPlan or deterministic_draft on failure.
        """
        self.last_composition_succeeded = False
        # Determine fallback text directly from verified answer plan or rich deterministic draft
        fallback_text = ""
        if context.deterministic_draft and ("### " in context.deterministic_draft or "\n• " in context.deterministic_draft):
            fallback_text = context.deterministic_draft
        elif context.answer_plan:
            fallback_text = context.answer_plan.render_deterministic_answer()
        elif context.verified_evidence and context.verified_evidence.answer_plan:
            fallback_text = context.verified_evidence.answer_plan.render_deterministic_answer()
        if not fallback_text:
            fallback_text = context.deterministic_draft or ""

        # 1. Deterministic Bypass
        if not fallback_text and not context.deterministic_draft:
            return ""

        if not context.needs_naturalization:
            return fallback_text

        if not self.ollama_client:
            return fallback_text

        now = time.time()
        if now < getattr(self, "_offline_cooldown_until", 0.0):
            return fallback_text

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
            is_multi = (
                len(getattr(context.verified_evidence, "displayed_product_order", []) or []) > 1
                or "comparison" in (context.dialogue_act or "").lower()
                or "recommendation" in (context.dialogue_act or "").lower()
            )
            if not is_multi and context.verified_evidence and context.verified_evidence.active_product:
                active_pid = context.verified_evidence.active_product.get("id")
            val_context = {
                "product_id": active_pid,
                "evidence": context.verified_evidence.to_dict() if context.verified_evidence else {},
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
                    self.last_composition_succeeded = True
                    logger.info(f"Grounded response composed successfully ({comp_res.get('latency_ms')}ms)")
                    return self._clean_unwanted_stars(composed_text)

                logger.warning(f"Composed reply failed validation: {violations}. Attempting 1 bounded regeneration.")

                # 6. Bounded Single Regeneration Attempt
                retry_messages = list(messages)
                retry_messages.append({"role": "assistant", "content": composed_text})
                retry_messages.append({
                    "role": "user",
                    "content": (
                        f"Your previous answer had validation violations: {violations}. "
                        f"Strictly adhere to VERIFIED_ANSWER_PLAN and VERIFIED_EVIDENCE. "
                        f"Do NOT invent unlisted attributes, do not present prices/discounts/quotes, "
                        f"and fix these issues immediately."
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
                        self.last_composition_succeeded = True
                        logger.info("Regenerated response passed validation successfully.")
                        return self._clean_unwanted_stars(regen_text)
                    logger.warning(f"Regenerated reply failed validation again: {violations_2}. Falling back to verified plan.")
            else:
                self._offline_cooldown_until = time.time() + 10.0

        except Exception as e:
            self._offline_cooldown_until = time.time() + 10.0
            logger.warning(f"Error during response composition: {e}. Falling back to verified plan.")

        # Safe Fail-Closed Fallback directly from verified plan
        self.last_composition_succeeded = False
        return fallback_text

    @staticmethod
    def _clean_unwanted_stars(text: str) -> str:
        """
        Removes unwanted markdown asterisks/stars from chat responses:
        - **phrase** -> phrase
        - *phrase* -> phrase
        - Leading bullet stars '* item' -> '• item'
        """
        if not text:
            return text
        # Remove bold asterisks **phrase** -> phrase
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        # Remove italic asterisks *phrase* -> phrase
        cleaned = re.sub(r"(?<!\*|\n)\*([^*\n]+)\*(?!\*)", r"\1", cleaned)
        # Replace bullet stars * item -> • item
        cleaned = re.sub(r"^\s*\*\s+", r"• ", cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def _extract_customer_questions(self, message: str) -> List[str]:
        """
        Extracts individual clauses or questions from a single customer message.
        Handles comma-separated queries e.g. "Wi-Fi, scanner, and ink?".
        """
        text = (message or "").strip()
        if not text:
            return []

        # Check for compact comma-separated attribute query: "Wi-Fi, scanner, and ink?"
        if re.search(r"^(?:does\s+it\s+have\s+)?(?:wi-?fi|scanner|scan|ink|speed|size|dimensions)(?:\s*,\s*(?:wi-?fi|scanner|scan|ink|speed|size|dimensions|\w+))+\s*\??$", text, re.I):
            items = [re.sub(r"^(?:and|or)\s+", "", part.strip(), flags=re.I).strip(" ?.,") for part in text.split(",")]
            return [f"Does it support {item}?" for item in items if item]

        # Split by question marks or strong coordinating conjunctions
        raw_parts = re.split(r"\?|\band\s+(?:can|does|is|what|how|which|do|has)\b", text, flags=re.IGNORECASE)
        questions: List[str] = []
        for part in raw_parts:
            cleaned = part.strip().strip(" ,;.-")
            if cleaned and len(cleaned.split()) >= 2:
                if not cleaned.endswith("?"):
                    cleaned += "?"
                questions.append(cleaned)

        if not questions:
            questions = [text if text.endswith("?") else text + "?"]
        return questions

    def _determine_expected_length(self, message: str, intent: str) -> str:
        """
        Dynamically selects target response length based on query depth.
        """
        words = (message or "").strip().split()
        word_count = len(words)
        lower_msg = (message or "").lower()

        # Extremely short queries: "wifi?", "scanner?", "t shirts?"
        if word_count <= 4 and not any(w in lower_msg for w in ["why", "compare", "difference", "recommend"]):
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
        val_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Validates the composed text using deterministic catalog fact-checking,
        product policy enforcement, and AnswerPlan item coverage.
        """
        if val_context is None:
            val_context = {}
        if not composed_text or len(composed_text.strip()) < 3:
            return False, ["empty_or_too_short"]

        text_lower = composed_text.lower()
        violations: List[str] = []

        # 1. Product Policy Guard (Rule 7: No unprompted prices, discounts, quote offers, or handover suggestions)
        # Allow price mentions when price/cost/investment was requested or is in the verified evidence
        is_price_requested = bool(re.search(
            r"\b(?:price|cost|how\s+much|rate|investment|running\s*cost|cpp|aed|pricing|budget)\b",
            (getattr(context, "original_message", "") or getattr(context, "normalized_message", "") or "").lower()
        ))
        is_price_allowed = (
            is_price_requested
            or getattr(context, "intent", "") in ("PRICE_INQUIRY", "COMMERCIAL_PRICING", "COST_PER_PRINT")
            or "cost" in str(getattr(context, "target_route", "")).lower()
            or "price" in str(getattr(context, "target_route", "")).lower()
            or ("aed" in str(getattr(context, "deterministic_draft", "") or "").lower())
        )
        if not is_price_allowed:
            if re.search(r"\b(?:aed|\$|usd|eur|gbp)\s*\d+", text_lower) or re.search(r"\b\d+\s*(?:aed|usd|dollars|dirhams)\b", text_lower):
                violations.append("prohibited_policy:price_leaked")

        # Check for quotation offers
        if re.search(r"\b(?:prepare\s+(?:an?\s+)?(?:official\s+)?quotation|prepare\s+(?:an?\s+)?quote|quote\s+for\s+you|official\s+quote\s+offer)\b", text_lower):
            violations.append("prohibited_policy:quote_offered")

        # Check for discount / negotiation promises
        if re.search(r"\b(?:give\s+you\s+a\s+discount|offer\s+a\s+discount|negotiate\s+the\s+price|special\s+discount\s+for\s+you)\b", text_lower):
            violations.append("prohibited_policy:discount_offered")

        # Check for handover suggestions (unless user explicitly requested it)
        if context.intent != "HUMAN_HANDOVER_REQUEST":
            if re.search(r"\b(?:our\s+sales\s+desk\s+will\s+reach\s+out|sales\s+agent\s+will\s+contact|leave\s+your\s+contact\s+details)\b", text_lower):
                violations.append("prohibited_policy:handover_suggested")

        if violations:
            return False, violations

        # 2. Deterministic Catalog Fact Validator
        is_det_valid, det_violations = deterministic_validator.validate(
            composed_text, context=val_context
        )
        if not is_det_valid:
            return False, det_violations

        # 3. Follow-up Question Guard: If no allowed follow-up, forbid ending in a question
        if not context.allowed_followup and composed_text.strip().endswith("?"):
            if "?" in composed_text:
                return False, ["unauthorized_followup_question"]

        # 4. Answer Plan Item Validation (Field-Aware 3-Valued Logic Coverage)
        plan = context.answer_plan or context.verified_evidence.answer_plan
        if plan and plan.items:
            for item in plan.items:
                attr = item.attribute
                status = item.status

                if status == "supported":
                    if attr == "wifi":
                        if not re.search(r"\b(?:wifi|wi-fi|wireless|wi-fi\s+direct)\b", text_lower):
                            violations.append(f"plan_coverage_missing:wifi_supported")
                        if re.search(r"\b(?:no\s+wi-?fi|not\s+support\s+wi-?fi|does\s+not\s+(?:have|support)\s+wi-?fi|ethernet\s+only)\b", text_lower):
                            violations.append(f"unsupported_negative_claim:{attr}")

                    elif attr == "scanner":
                        if not re.search(r"\b(?:scanner|scan|scanning|mfp|multifunction)\b", text_lower):
                            violations.append(f"plan_coverage_missing:scanner_supported")
                        if re.search(r"\b(?:no\s+scanner|print-only|print\s+only|does\s+not\s+(?:have|support)\s+scanner)\b", text_lower):
                            violations.append(f"unsupported_negative_claim:{attr}")

                    elif attr == "t_shirt_capability":
                        if not re.search(r"\b(?:dye-sublimation|dye\s+sublimation|transfer\s+paper|polyester|fabric|garment|t-shirt)\b", text_lower):
                            violations.append("plan_coverage_missing:t_shirt_supported")

                elif status == "unsupported":
                    if attr == "t_shirt_capability":
                        # Must make negative assertion
                        if not re.search(r"\b(?:cannot|can't|does\s+not|not\s+designed|not\s+support|not\s+compatible|not\s+for\s+t-shirts|requires?\s+dye-sublimation|fine\s*art|paper)\b", text_lower):
                            violations.append("missing_negative_claim_t_shirt")
                        # Must NOT falsely claim it prints directly on t-shirts
                        if re.search(r"\b(?:can\s+print\s+(?:directly\s+)?on\s+t-shirts|prints\s+t-shirts\s+directly)\b", text_lower):
                            violations.append(f"unsupported_positive_claim:{attr}")

                    elif attr == "scanner":
                        # Must assert negative or print only
                        if not re.search(r"\b(?:print-only|print\s+only|no\s+scanner|no\s+integrated\s+scanner|does\s+not\s+have\s+(?:a\s+)?scanner)\b", text_lower):
                            violations.append("missing_negative_claim_scanner")
                        if re.search(r"\b(?:includes?|features?|has|comes\s+with|equipped\s+with)\s+.*?\bscanner\b", text_lower) or re.search(r"\byes\b.*?\bscanner\b", text_lower):
                            violations.append(f"unsupported_positive_claim:{attr}")

                    elif attr == "wifi":
                        # Must NOT claim built-in Wi-Fi
                        if re.search(r"\b(?:supports?\s+wi-?fi|built-in\s+wi-?fi|features?\s+wi-?fi)\b", text_lower):
                            violations.append(f"unsupported_positive_claim:{attr}")

                elif status == "unknown":
                    # Must acknowledge as unlisted / unknown / not confirmed
                    if not re.search(r"\b(?:not\s+listed|unknown|not\s+specified|not\s+confirmed|unconfirmed|not\s+documented)\b", text_lower):
                        violations.append(f"missing_unknown_acknowledgement:{attr}")
                    # Must NOT falsely assert support or assume arbitrary default
                    if attr == "wifi" and re.search(r"\b(?:supports?\s+wi-?fi|built-in\s+wi-?fi|ethernet\s+only)\b", text_lower):
                        violations.append("invented_fact:unknown_wifi_asserted")
                    if attr == "scanner" and re.search(r"\b(?:integrated\s+scanner|features?\s+a\s+scanner)\b", text_lower):
                        violations.append("invented_fact:unknown_scanner_asserted")

        # 5. Cross-Product Contamination Checks
        active_prod = context.verified_evidence.active_product
        if active_prod:
            pid = str(active_prod.get("id", "")).lower()
            true_width = active_prod.get("width") or active_prod.get("print_width") or active_prod.get("max_width_inches")
            if true_width:
                try:
                    true_w_int = int(float(true_width))
                    w_matches = re.findall(r"\b(13|17|24|36|44|64)[\s-]*(?:inch|in|\"|'')\b", text_lower)
                    for wm in w_matches:
                        if int(wm) != true_w_int and not any(k in text_lower for k in ["compare", "vs", "difference", "alternative", "other"]):
                            violations.append("cross_product_spec_swap:width_mismatch")
                            break
                except (ValueError, TypeError):
                    pass

            if "cx-02" in pid and "cx-02w" not in pid:
                # CX-02 must not claim 8x12 or 8x10 support or 700 prints (those belong to CY-02 or CX-02W)
                if any(k in text_lower for k in ["8x10", "8x12", "8×10", "8×12", "700 prints"]) and not any(k in text_lower for k in ["compare", "vs", "difference", "cy-02", "cx-02w"]):
                    violations.append("cross_product_contamination:cx02_assigned_cy02_specs")
            elif "t5100m" in pid:
                # SC-T5100M must not claim 5400m speed or dual roll
                if "dual roll" in text_lower or "2 rolls" in text_lower:
                    violations.append("cross_product_contamination:t5100m_assigned_dual_roll")
        # 6. Unapproved Model Code & Brand-Card Inconsistency Validator
        # Ensure that no invented or unapproved printer model numbers escape to the user
        from catalog.catalogue_loader import catalogue_loader
        approved_tokens = set()
        for p in catalogue_loader.products:
            raw_id = p.get("id", "").lower().replace("epson-", "").replace("citizen-", "")
            approved_tokens.add(raw_id)
            approved_tokens.add(raw_id.replace("-", ""))
            p_name = (p.get("name") or p.get("display_name") or "").lower()
            for part in re.split(r"[\s,]+", p_name):
                if re.search(r"\d", part) and len(part) >= 3:
                    clean_p = part.strip("().,")
                    approved_tokens.add(clean_p)
                    approved_tokens.add(clean_p.replace("-", ""))

        for c in (getattr(context.verified_evidence, "consumable_cards", []) or []):
            c_name = (c.get("name") or c.get("title") or "").lower()
            for part in re.split(r"[\s,]+", c_name):
                if re.search(r"\d", part) and len(part) >= 3:
                    clean_c = part.strip("().,")
                    approved_tokens.add(clean_c)
                    approved_tokens.add(clean_c.replace("-", ""))

        # Check for model-like tokens (e.g. p7060, t5280, wf-c5710, sc-t9999)
        found_models = re.findall(r"\b(?:epson\s+|citizen\s+|surecolor\s+|workforce\s+)?((?:sc|wf|am|em|cx|cy|cz|op|ds|es|xp|et|l|p|t)[-\s]?[a-z]?\d{2,5}[a-z0-9]*)\b", text_lower)
        for m_token in found_models:
            m_clean = m_token.replace(" ", "").replace("-", "")
            # Skip unit measurements and common specs
            if re.search(r"^(?:\d+dpi|\d+ppm|\d+ipm|\d+inch|\d+cm|\d+mm|\d+gsm|\d+ml|\d+bit|\d+mb|\d+gb|\d+kg)$", m_clean):
                continue
            if not any(m_clean == app or m_clean in app or app in m_clean for app in approved_tokens):
                violations.append(f"unapproved_model_invented:{m_token}")

        # Brand consistency check between text and cards/evidence
        has_epson_in_text = bool(re.search(r"\bepson\b", text_lower))
        has_citizen_in_text = bool(re.search(r"\bcitiz[eo]n\b", text_lower))
        displayed_ids = [str(x).lower() for x in (getattr(context.verified_evidence, "displayed_product_order", []) or [])]
        if displayed_ids:
            all_citizen_cards = all("citizen" in pid for pid in displayed_ids)
            all_epson_cards = all("epson" in pid for pid in displayed_ids)
            if all_citizen_cards and has_epson_in_text and not has_citizen_in_text:
                violations.append("brand_card_mismatch:epson_text_with_citizen_cards")
            elif all_epson_cards and has_citizen_in_text and not has_epson_in_text:
                violations.append("brand_card_mismatch:citizen_text_with_epson_cards")

        if violations:
            return False, violations

        return True, []
