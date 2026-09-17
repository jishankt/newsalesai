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
            return self._fallback(customer_message)

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
            logger.warning("LLM classify failed or returned empty — using fallback.")
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

        # Direct comparison, superlative queries, specifications, and website lookups can be handled deterministically
        if any(w in msg_l for w in [
            "fastest", "faster", "highest speed", "print speed", "quickest", "print faster",
            "highest capacity", "largest roll", "most prints", "max capacity", "print capacity",
            "most portable", "lightest", "smallest", "most compact", "how heavy", "weight of",
            "widest", "highest resolution", "max resolution", "print 8x12", "8 inch citizen", "8-inch citizen",
            "compare", " vs ", " versus ", "difference between", "differences between", "difference",
            "which is better", "which is best", "which one is better", "which one should i choose",
            "ribbon rewind", "inkjet or dye sub", "dye sub or inkjet",
            "specifications", "description", "datasheet", "brochure", "website",
            "product description", "detailed specs", "technical specs"
        ]):
            return True

        # Standard pill chips and qualification answers fast-path
        known_chip_phrases = {
            "i need a printer", "looking for a printer", "i want a printer", "i want to buy a printer",
            "yes, with scanner", "no, print only", "yes with scanner", "no print only",
            "with scanner", "no scanner", "print only", "printer only", "only print", "just print",
            "technical cad plotters", "cad drawings", "cad", "technical",
            "office enterprise documents", "office & business documents", "office & business documents (a3 / a4)", "business", "a3 or a4",
            "professional photographs", "professional photography & fine art", "fine art", "photo printers (fine art & photo booth)",
            "event photos (photo booth)", "photo booth",
            "compact (desktop / portable)", "large format (24″ to 64″)", "compact", "large format", "large-format",
            "epson desktop (fine art / a3+ / a2+)", "citizen (photo booth / events)", "epson desktop", "citizen photo",
            "dye-sublimation (t-shirts & mugs)", "dye-sublimation", "t-shirt printing", "sublimation",
            "24-inch (a1)", "36-inch (a0)", "44-inch wide", "24-inch", "36-inch", "44-inch",
            "a4 standard", "a3 large format", "a4 desktop (sc-f100)", "24-inch roll (sc-f500)",
            "t-shirts & apparel", "mugs & personalized gifts", "sportswear & soft signage",
            "with roll adapter", "without roll adapter", "without roll adapter (standard)",
            "with roll", "without roll", "i need with", "i need without"
        }
        if msg_l in known_chip_phrases:
            return True

        # If user is speaking in full conversational sentences (more than 3 words) or correcting, always let LLM classify
        if len(words) > 3 or any(w in words for w in ["sorry", "actually", "instead", "think", "thought", "mean", "meant"]):
            return False

        # Isolated Boolean & Scanner answers
        if msg_l in ["yes", "no", "yep", "nope", "both", "print only", "printer only", "only print", "only printer", "just print", "just printer", "no scanner", "with scanner", "need scanner"]:
            return True

        # Isolated Size answers
        if msg_l in ["a0", "a1", "a2", "a3", "a4", "4x6", "6x8", "8x12", "24\"", "36\"", "44\"", "small", "large", "compact", "big", "smaller", "larger", "24", "36", "44"]:
            return True

        # Pure isolated volume numbers (e.g. "60", "150", "10 pages", "20 to 30")
        if len(words) <= 4 and any(ch.isdigit() for ch in msg_l):
            return True

        return False

    def _fallback(self, customer_message: str = "") -> LLMUnderstanding:
        """Intelligent fallback when LLM is unavailable or times out."""
        msg_l = (customer_message or "").strip().lower()
        entities = {}
        intent = Intent.UNCLEAR
        action = "ask_clarification"

        import re

        # 1. Model detection for comparisons
        comp_model_matches = re.findall(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3}[a-z]?|cx-?\d{2}w?|cy-?\d{2}|cz-?\d{2}|am-?c\d{3,4}|wf-?c\d{3,4}[a-z]?)\b", msg_l)
        unique_comp_models = []
        for cm in comp_model_matches:
            clean_cm = re.sub(r"[\s\-_]+", "", cm.lower())
            if clean_cm not in [re.sub(r"[\s\-_]+", "", u.lower()) for u in unique_comp_models]:
                unique_comp_models.append(cm.lower())

        is_comp = (
            len(unique_comp_models) >= 2
            or any(w in msg_l for w in [
                "compare", " vs ", " versus ", "difference", "differences", "difference between",
                "which is better", "which is best", "which one is better", "which one should i choose",
                "how do they compare", "how does", "contrast", "epson or citizen", "citizen or epson"
            ])
        )

        # Direct Consumable / Part Number SKU check (e.g. C13T11C340, C13S210057, CX2.4x6)
        from rag.retriever import rag_retriever
        sku_cand_matches = re.findall(r"\b(c1[123][a-z0-9]{5,9}|c13s\d+|c12c\d+|ifa\s*\d+|olm\s*\d+|cx2[a-z0-9.\-]+|cy[a-z0-9.\-]+|cx2w\s*812)\b", msg_l)
        if not sku_cand_matches:
            for tok in re.findall(r"\b[a-z0-9\.\-]{5,15}\b", msg_l):
                if re.search(r"\d", tok) and tok not in ["epson", "citizen", "printer", "scanner", "plotter", "cartridge", "please"]:
                    p_match = rag_retriever.get_by_sku(tok)
                    if p_match:
                        sku_cand_matches.append(tok)
                        break

        if sku_cand_matches:
            cand_sku = sku_cand_matches[0].upper()
            p_sku = rag_retriever.get_by_sku(cand_sku) or rag_retriever.get_by_name(cand_sku)
            if p_sku:
                cat = str(p_sku.get("category", "")).lower()
                is_consumable_cat = any(ck in cat for ck in ["ink", "cartridge", "box", "tank", "media", "paper", "ribbon", "accessory"]) or p_sku.get("card_type") == "consumable"
                if is_consumable_cat:
                    logger.info(f"Fallback NLU: direct consumable SKU identified: {cand_sku}")
                    entities["sku"] = cand_sku
                    entities["model_code"] = cand_sku
                    return LLMUnderstanding(
                        intent=Intent.CONSUMABLES_QUERY,
                        dialogue_act="questioning",
                        product_related=True,
                        confidence=0.98,
                        sentiment="neutral",
                        language="en",
                        entities=entities,
                        requested_action="show_consumables",
                        tool_request={"name": "get_product_specs", "arguments": {"product_identifier": cand_sku}},
                    )

        # Consumables check before superlative attribute check
        has_ink_kw = any(re.search(rf"\b{re.escape(k)}\b", msg_l) for k in [
            "consumable", "consumables", "ink", "inks", "cartridge", "cartridges",
            "toner", "ribbon", "what ink", "which ink", "maintenance box", "maintenance tank",
            "paper roll", "photo paper", "yellow", "cyan", "magenta", "photo black",
            "matte black", "light cyan", "light magenta", "gray", "grey", "violet", "orange", "green"
        ]) or "compatible with" in msg_l
        is_negating_ink = any(k in msg_l for k in ["not ink", "no ink", "dont want ink", "don't want ink", "printer only", "only printer"])
        is_printer_search = any(p in msg_l for p in ["printer", "printers", "plotter", "plotters", "show all", "show matching", "show every", "need a", "looking for"])
        is_pure_consumable = (has_ink_kw or sku_cand_matches) and not is_negating_ink and not is_printer_search and not any(rw in msg_l for rw in ["ribbon rewind", "rewind", "inkjet or dye sub", "use ink or ribbon"])

        if is_pure_consumable:
            logger.info("Fallback NLU: classified as intent=consumables_query action=show_consumables")
            return LLMUnderstanding(
                intent=Intent.CONSUMABLES_QUERY,
                dialogue_act="questioning",
                product_related=True,
                confidence=0.95,
                sentiment="neutral",
                language="en",
                entities=entities,
                requested_action="show_consumables",
            )

        # Explicit model specification or inquiry check
        from catalog.product_resolver import resolve_canonical_id
        canon_model = entities.get("model_code") or resolve_canonical_id(customer_message)
        cand_model = canon_model
        if not cand_model:
            m_cand = re.search(r"\b(?:sc-?)?([tpf]\d{3,5}[a-z0-9]*|ds-?\d{3,5}[a-z0-9]*|es-?\d{3,5}[a-z0-9]*|cx-?\d{1,2}[a-z0-9]*|cy-?\d{1,2}[a-z0-9]*|cz-?\d{1,2}[a-z0-9]*|am-?c\d{3,4}[a-z0-9]*|wf-?(?:c|m)?\d{3,5}[a-z0-9]*|em-?c\d{3,4}[a-z0-9]*|12000xl|f100|f500|op900(?:ii)?)\b", msg_l)
            if m_cand:
                cand_model = m_cand.group(0).upper()

        if cand_model and any(w in msg_l for w in ["spec", "specification", "detail", "about", "what is", "price", "speed", "size", "show me", "tell me", "description", "overview", "brochure", "datasheet", "website", "find"]):
            entities["model_code"] = cand_model
            return LLMUnderstanding(
                intent=Intent.PRODUCT_QUESTION,
                dialogue_act="questioning",
                product_related=True,
                confidence=0.95,
                sentiment="neutral",
                language="en",
                entities=entities,
                requested_action="answer_product_attribute",
                tool_request={"name": "get_product_specs", "arguments": {"product_identifier": cand_model}}
            )

        is_superlative_attribute = any(w in msg_l for w in [
            "price", "what is the price", "what does it cost", "how much", "rate", "cost", "how much is it",
            "fastest", "highest speed", "how fast", "print speed", "quickest", "print faster",
            "highest capacity", "largest roll", "most prints", "max capacity", "print capacity",
            "most portable", "lightest", "how heavy", "weight of", "most compact", "smallest",
            "ribbon rewind", "print 8x12", "prints 8x12", "8 inch citizen", "8-inch citizen",
            "which citizen", "which epson", "which printer is", "does it have", "can it print", "can it scan",
            "what size", "specs", "specification", "specifications", "description", "overview", "details",
            "why this one", "inkjet or dye sub", "use ink or ribbon"
        ])

        is_general_web_spec_query = any(p in msg_l for p in [
            "description and specifications", "specifications and description",
            "product description", "product specifications", "product specs",
            "find the product description", "find product description",
            "go the website", "go to the website", "go to website",
            "from website", "from the website", "on the website", "check the website",
            "check website", "website specifications"
        ])

        if is_comp:
            logger.info("Fallback NLU: classified as intent=product_comparison action=compare_products reason=direct_comparison_inquiry")
            return LLMUnderstanding(
                intent=Intent.PRODUCT_COMPARISON,
                dialogue_act="questioning",
                product_related=True,
                confidence=0.95,
                sentiment="neutral",
                language="en",
                entities=entities,
                requested_action="compare_products",
            )

        if is_superlative_attribute or is_general_web_spec_query:
            logger.info("Fallback NLU: classified as intent=product_question action=answer_product_attribute reason=superlative_or_spec_inquiry")
            return LLMUnderstanding(
                intent=Intent.PRODUCT_QUESTION,
                dialogue_act="questioning",
                product_related=True,
                confidence=0.95,
                sentiment="neutral",
                language="en",
                entities=entities,
                requested_action="answer_product_attribute",
                tool_request={"name": "answer_product_attribute", "arguments": {"query": customer_message}}
            )


        # Brands & Categories
        if any(c in msg_l for c in ["sublimation", "dye-sub", "dye sub", "f100", "f500", "sc-f100", "sc-f500", "t-shirt", "t shirt", "mug", "merchandise", "textile"]):
            entities["brand"] = "Epson"
            entities["product_category"] = "dye_sublimation"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif any(c in msg_l for c in ["citizen", "cx-02", "cx02", "cz-01", "cz01", "cy-02", "cy02", "photo booth"]):
            entities["brand"] = "Citizen"
            entities["product_category"] = "photo_booth"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "epson" in msg_l:
            entities["brand"] = "Epson"
        if any(c in msg_l for c in ["cad", "technical", "blueprint", "architect", "plotter", "plottaer"]):
            entities["product_category"] = "technical_cad"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif any(c in msg_l for c in ["photo fine art", "photo printer", "photography", "fine art", "gallery"]):
            if "citizen" not in msg_l:
                entities["product_category"] = "photo_fine_art"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif any(c in msg_l for c in ["office", "enterprise", "workforce", "copier", "am-c", "mfp", "business", "a3 or a4", "a4 printer", "a3 printer"]):
            entities["product_category"] = "office_enterprise"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif (
            not any(neg in msg_l for neg in ["no scanner", "without scanner", "not scanner", "don't need scanner", "dont need scanner", "print only", "printer only"])
            and not any(ans in msg_l for ans in ["yes need scanner", "with scanner", "has scanner", "need scanner", "scanner needed", "integrated scanner", "yes scanner", "scanner too"])
            and any(c in msg_l for c in ["scanner", "document scan", "scanning"])
        ):
            entities["product_category"] = "scanner"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"

        # Business info
        if any(w in msg_l for w in ["delivery", "shipping", "deliver", "ship", "address", "location", "dubai", "where are you", "office hours", "timings", "open", "contact", "phone", "email", "whatsapp", "companies", "what brands"]):
            intent = Intent.BUSINESS_INFORMATION
            action = "provide_business_info"

        # Sizes
        if "a0" in msg_l or "36" in msg_l or "36\"" in msg_l:
            entities["print_size"] = "A0"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif not bool(re.search(r"\b24\b.*?\b64\b", msg_l)) and ("a1" in msg_l or "24" in msg_l or "24\"" in msg_l):
            entities["print_size"] = "A1"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "a2" in msg_l or "17" in msg_l or "17\"" in msg_l:
            entities["print_size"] = "A2"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "a3" in msg_l or "13" in msg_l or "13\"" in msg_l:
            entities["print_size"] = "A3"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "a4" in msg_l:
            entities["print_size"] = "A4"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"
        elif "8x12" in msg_l or "8x10" in msg_l:
            entities["print_size"] = "8x12 inches" if "8x12" in msg_l else "8x10 inches"
            entities["product_category"] = "photo_booth"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "search_products"
        elif "4x6" in msg_l or "6x8" in msg_l:
            entities["print_size"] = "4x6"
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "ask_qualification_question"

        # Volume (ignore dimension patterns like 594 x 841 mm, 36-inch, 24", etc.)
        clean_vol_text = re.sub(r"\b\d+\s*[x×*]\s*\d+\s*(?:mm|cm|in|inch|inches)?\b", "", msg_l)
        clean_vol_text = re.sub(r"\b\d+\s*-?\s*(?:mm|cm|in|inch|inches|\"|')\b", "", clean_vol_text)
        clean_vol_text = re.sub(r"\b(?:a0|a1|a2|a3|a4|a5)\b", "", clean_vol_text)
        vol = re.search(r"\b(\d{1,4})\b", clean_vol_text)
        if vol and any(vkw in clean_vol_text for vkw in ["print", "drawing", "day", "daily", "around", "about", "approx", "volume", "page", "pages"]):
            entities["daily_volume"] = int(vol.group(1))
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "search_products"
        elif vol and len(clean_vol_text.split()) <= 3 and any(ch.isdigit() for ch in clean_vol_text) and not any(sz in msg_l for sz in ["36", "24", "44", "17", "13", "inch", "\""]):
            entities["daily_volume"] = int(vol.group(1))
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "search_products"

        # Scanner preference
        if any(w in msg_l for w in ["no scanner", "without scanner", "print only", "printer only", "only print", "only printer", "just print", "just printer", "printing only", "no scan"]):
            entities["scan_required"] = False
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "continue_qualification"
        elif any(w in msg_l for w in [
            "need scanner", "with scanner", "has scanner", "yes scanner", 
            "both", "both printing and scanning", "both print and scan", 
            "printing and scanning", "print and scan", "scannin", "scaning", "scanner too", "scanning too"
        ]):
            entities["scan_required"] = True
            if intent == Intent.UNCLEAR:
                intent = Intent.PRODUCT_DISCOVERY
                action = "continue_qualification"

        # Corrections
        if "actually" in msg_l:
            intent = Intent.CORRECTION
            action = "acknowledge_correction"

        # Confirmations / Rejections
        if intent == Intent.UNCLEAR:
            if any(w in msg_l for w in ["yes", "yep", "yeah", "sure", "need scanner", "with scanner", "both"]):
                intent = Intent.CONFIRMATION
                action = "continue_qualification"
            elif any(w in msg_l for w in ["no", "nope", "no scanner", "without scanner", "print only"]):
                intent = Intent.REJECTION
                action = "continue_qualification"

        # Model detection for multi-model comparisons
        comp_model_matches = re.findall(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3}[a-z]?|cx-?\d{2}w?|cy-?\d{2}|cz-?\d{2}|am-?c\d{3,4}|wf-?c\d{3,4}[a-z]?)\b", msg_l)
        unique_comp_models = []
        for m in comp_model_matches:
            clean_m = re.sub(r"[\s\-_]+", "", m.lower())
            if clean_m not in [re.sub(r"[\s\-_]+", "", u.lower()) for u in unique_comp_models]:
                unique_comp_models.append(m.lower())



        # Consumables / Colors / Media
        has_ink_kw = any(re.search(rf"\b{re.escape(k)}\b", msg_l) for k in [
            "consumable", "consumables", "ink", "inks", "cartridge", "cartridges",
            "toner", "ribbon", "what ink", "which ink", "maintenance box", "maintenance tank",
            "paper roll", "photo paper", "media", "yellow", "cyan", "magenta", "photo black",
            "matte black", "light cyan", "light magenta", "gray", "grey", "violet", "orange", "green"
        ]) or "compatible with" in msg_l
        is_negating_ink = any(k in msg_l for k in ["not ink", "no ink", "dont want ink", "don't want ink", "printer only", "only printer"])
        if (intent in (Intent.UNCLEAR, Intent.PRODUCT_DISCOVERY, Intent.PRODUCT_QUESTION)) and has_ink_kw and not is_negating_ink and intent != Intent.PRODUCT_COMPARISON and action != "answer_product_attribute" and not any(rw in msg_l for rw in ["ribbon rewind", "rewind", "ribbon feature", "technology", "or ribbon"]):
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
            product_related=intent in (Intent.PRODUCT_DISCOVERY, Intent.PRODUCT_QUESTION, Intent.CONSUMABLES_QUERY),
        )


# Module-level singleton (client injected later during app init)
llm_engine = LLMUnderstandingEngine()
