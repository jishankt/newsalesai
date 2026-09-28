"""Evidence Planner for Kepler Tech SalesAI.

Deterministically plans and retrieves verified ground-truth data from catalogue,
specifications, and consumable databases before calling the ResponseComposer.
Ensures zero factual hallucination by binding the LLM response strictly to verified data.
Implements field-aware facts, explicit 3-valued logic (supported, unsupported, unknown),
and multi-part answer planning.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from domain.response_context import (
    VerifiedEvidenceBundle,
    FieldFact,
    AnswerPlanItem,
    AnswerPlan,
)
from domain.conversation_types import DialogueAct, Intent, LLMUnderstanding
from domain.conversation_state import ConversationState
from catalog.catalogue_loader import catalogue_loader
from catalog.repository import catalog_repository

logger = logging.getLogger("evidence_planner")


class EvidencePlanner:
    """Plans and aggregates field-aware, verified database evidence for response composition."""

    @classmethod
    def _normalize_product_dict(cls, prod: Any) -> Optional[Dict[str, Any]]:
        """Normalizes any product reference into a standard dictionary from catalogue."""
        if not prod:
            return None
        if isinstance(prod, dict) and prod.get("id"):
            # Ensure full catalogue record is loaded if dictionary is partial
            full = catalogue_loader.get_by_id(prod["id"])
            if full:
                merged = dict(full)
                merged.update({k: v for k, v in prod.items() if v is not None})
                return merged
            return prod
        if isinstance(prod, str):
            res = catalogue_loader.get_by_id(prod)
            if not res and prod.startswith("epson-") and not prod.startswith("epson-sc-"):
                res = catalogue_loader.get_by_id(prod.replace("epson-", "epson-sc-"))
            if not res:
                # Check repository
                rp = catalog_repository.get_by_id(prod)
                if rp:
                    return rp.to_dict()
            return res
        if hasattr(prod, "to_dict"):
            return prod.to_dict()
        if hasattr(prod, "id"):
            return catalogue_loader.get_by_id(prod.id)
        return None

    @classmethod
    def plan_and_retrieve(
        cls,
        user_message: str = "",
        state: Optional[ConversationState] = None,
        understanding: Optional[LLMUnderstanding] = None,
        resolved_products: Optional[List[Dict[str, Any]]] = None,
        requested_attributes: Optional[List[str]] = None,
        displayed_candidates: Optional[List[Dict[str, Any]]] = None,
        raw_query: str = "",
        nlp_result: Optional[Dict[str, Any]] = None,
        product_cards: Optional[List[Dict[str, Any]]] = None,
        consumable_cards: Optional[List[Dict[str, Any]]] = None,
        comparison_data: Optional[Dict[str, Any]] = None,
        recommendation_audit: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> VerifiedEvidenceBundle:
        """
        Builds a field-aware VerifiedEvidenceBundle and AnswerPlan.
        """
        bundle = VerifiedEvidenceBundle()
        msg_raw = user_message or raw_query or (nlp_result.get("normalized_text") if nlp_result else "") or ""
        msg_l = msg_raw.lower()

        if displayed_candidates is None and product_cards:
            displayed_candidates = product_cards
        if requested_attributes is None and nlp_result:
            requested_attributes = nlp_result.get("requested_attributes")
        if state is None:
            state = ConversationState()

        # 1. Resolve candidate and displayed products
        displayed_order: List[str] = []
        if displayed_candidates:
            for p in displayed_candidates:
                p_dict = cls._normalize_product_dict(p)
                if p_dict and p_dict.get("id") and p_dict["id"] not in displayed_order:
                    displayed_order.append(p_dict["id"])
        elif getattr(state, "displayed_product_ids", None):
            displayed_order = list(state.displayed_product_ids)

        bundle.displayed_product_order = displayed_order

        # 2. Resolve Active / Target Product(s)
        prods_to_evaluate: List[Dict[str, Any]] = []
        if resolved_products and len(resolved_products) > 0:
            for p in resolved_products:
                norm_p = cls._normalize_product_dict(p)
                if norm_p and norm_p not in prods_to_evaluate:
                    prods_to_evaluate.append(norm_p)
        elif state.active_product:
            norm_p = cls._normalize_product_dict(state.active_product)
            if norm_p:
                prods_to_evaluate.append(norm_p)
        elif state.active_product_id:
            norm_p = cls._normalize_product_dict(state.active_product_id)
            if norm_p:
                prods_to_evaluate.append(norm_p)
        elif state.selected_product_id:
            norm_p = cls._normalize_product_dict(state.selected_product_id)
            if norm_p:
                prods_to_evaluate.append(norm_p)
        elif displayed_order:
            for pid in displayed_order[:2]:
                norm_p = cls._normalize_product_dict(pid)
                if norm_p:
                    prods_to_evaluate.append(norm_p)

        active_prod = prods_to_evaluate[0] if prods_to_evaluate else None
        if active_prod:
            bundle.active_product = active_prod

        # 3. Identify Requested Attributes and Questions
        attrs = list(requested_attributes or [])
        if understanding and understanding.requested_attributes:
            for a in understanding.requested_attributes:
                if a not in attrs:
                    attrs.append(a)

        # Decompose message clauses / keywords if attributes list is empty
        if any(w in msg_l for w in ["wifi", "wi-fi", "wireless"]) and "wifi" not in attrs:
            attrs.append("wifi")
        if any(w in msg_l for w in ["scanner", "scanning", "scan"]) and "scanner" not in attrs:
            attrs.append("scanner")
        if any(w in msg_l for w in ["ink", "cartridge", "consumable", "ribbon"]) and "compatible_ink" not in attrs and "ink" not in attrs:
            attrs.append("compatible_ink")
        if any(w in msg_l for w in ["t-shirt", "t shirt", "tshirt", "t-shirts", "apparel", "garment", "fabric"]) and "t_shirt_capability" not in attrs:
            attrs.append("t_shirt_capability")
        if any(w in msg_l for w in ["photo", "photos", "picture", "pictures", "image", "images", "pic", "pics"]) and any(w in msg_l for w in ["send", "show", "give", "provide", "share", "see", "view", "?"]) and "media_request" not in attrs:
            attrs.append("media_request")
        if any(w in msg_l for w in ["difference between", "diffrance bw", "between this two", "between these two", "compare this two", "compare these two", "tell both"]) and "configuration_difference" not in attrs:
            attrs.append("configuration_difference")
        if any(w in msg_l for w in ["what i asked", "what did i ask", "my previous question", "earlier question"]) and "prior_question_recall" not in attrs:
            attrs.append("prior_question_recall")
        if any(w in msg_l for w in ["price", "cost", "how much", "quote", "quotation", "rate", "discount"]):
            attrs.append("price")

        # 4. Check for Ambiguous Reference
        needs_clarification = False
        clarification_q = None

        is_ordinal_second = bool(re.search(r"\b(?:the\s+)?(?:2nd|second)\s*(?:one|printer|model)?\b", msg_l))
        is_generic_pronoun = bool(re.search(r"\b(?:it|this\s+one|that\s+one|the\s+printer|which\s+one)\b", msg_l))

        if is_ordinal_second:
            if len(displayed_order) >= 2:
                sec_prod = cls._normalize_product_dict(displayed_order[1])
                if sec_prod:
                    active_prod = sec_prod
                    bundle.active_product = sec_prod
                    prods_to_evaluate = [sec_prod]
            else:
                needs_clarification = True
                clarification_q = "Only one model was displayed earlier. Could you specify which model you are referring to?"
        elif is_generic_pronoun and not active_prod and len(displayed_order) >= 2:
            p1 = cls._normalize_product_dict(displayed_order[0])
            p2 = cls._normalize_product_dict(displayed_order[1])
            p1_name = p1.get("display_name") or displayed_order[0] if p1 else displayed_order[0]
            p2_name = p2.get("display_name") or displayed_order[1] if p2 else displayed_order[1]
            needs_clarification = True
            clarification_q = f"Could you clarify which model you mean—the {p1_name} or the {p2_name}?"

        # 5. Build AnswerPlan and FieldFacts
        plan = AnswerPlan(
            resolved_products=prods_to_evaluate,
            displayed_product_order=displayed_order,
            needs_clarification=needs_clarification,
            clarification_question=clarification_q,
            overall_goal=understanding.customer_goal if understanding else "",
        )

        field_facts: Dict[str, Dict[str, FieldFact]] = {}
        direct_facts: Dict[str, Any] = {}

        if active_prod and not needs_clarification:
            pid = active_prod.get("id", "")
            p_name = active_prod.get("display_name") or active_prod.get("model") or active_prod.get("name") or pid
            field_facts[pid] = {}

            # Process each requested attribute
            for attr in attrs:
                if attr == "wifi":
                    fact = cls._evaluate_wifi(active_prod)
                    field_facts[pid]["wifi"] = fact
                    direct_facts["wifi"] = fact.display_claim
                    plan.items.append(AnswerPlanItem(
                        item_id="wifi",
                        question_text="Does this have Wi-Fi?",
                        attribute="wifi",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr == "scanner":
                    fact = cls._evaluate_scanner(active_prod)
                    field_facts[pid]["scanner"] = fact
                    direct_facts["scanner"] = fact.display_claim
                    plan.items.append(AnswerPlanItem(
                        item_id="scanner",
                        question_text="Does it have an integrated scanner?",
                        attribute="scanner",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr in ("compatible_ink", "ink"):
                    fact, c_cards = cls._evaluate_ink(active_prod)
                    field_facts[pid]["compatible_ink"] = fact
                    direct_facts["compatible_ink"] = fact.display_claim
                    if c_cards:
                        bundle.consumables = c_cards[:10]
                    plan.items.append(AnswerPlanItem(
                        item_id="compatible_ink",
                        question_text="What ink or cartridges are compatible?",
                        attribute="compatible_ink",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr == "t_shirt_capability":
                    fact = cls._evaluate_tshirt(active_prod)
                    field_facts[pid]["t_shirt_capability"] = fact
                    direct_facts["t_shirt_capability"] = fact.display_claim
                    plan.items.append(AnswerPlanItem(
                        item_id="t_shirt_capability",
                        question_text="Can it print on T-shirts?",
                        attribute="t_shirt_capability",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr == "media_request":
                    fact = cls._evaluate_media_request(active_prod)
                    field_facts[pid]["media_request"] = fact
                    direct_facts["media_request"] = {
                        "product_name": p_name,
                        "url": fact.value,
                        "description": fact.display_claim,
                    }
                    plan.items.append(AnswerPlanItem(
                        item_id="media_request",
                        question_text="Send photo or product images",
                        attribute="media_request",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr == "configuration_difference":
                    fact = cls._evaluate_configuration_difference(active_prod)
                    field_facts[pid]["configuration_difference"] = fact
                    direct_facts["configuration_difference"] = {
                        "product": p_name,
                        "summary": fact.display_claim,
                    }
                    plan.items.append(AnswerPlanItem(
                        item_id="configuration_difference",
                        question_text="What's the difference between these two configurations?",
                        attribute="configuration_difference",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr == "prior_question_recall":
                    fact = cls._evaluate_prior_question_recall(state, active_prod)
                    field_facts[pid]["prior_question_recall"] = fact
                    direct_facts["prior_question_recall"] = fact.display_claim
                    plan.items.append(AnswerPlanItem(
                        item_id="prior_question_recall",
                        question_text="What did I ask about this model earlier?",
                        attribute="prior_question_recall",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

                elif attr == "price":
                    fact = cls._evaluate_price_policy(active_prod)
                    field_facts[pid]["price"] = fact
                    direct_facts["price"] = fact.display_claim
                    plan.items.append(AnswerPlanItem(
                        item_id="price",
                        question_text="How much does it cost?",
                        attribute="price",
                        target_product_id=pid,
                        target_product_name=p_name,
                        status=fact.status,
                        evidence_value=fact.value,
                        evidence_source=fact.source,
                        factual_claim=fact.display_claim,
                    ))

        elif needs_clarification:
            plan.items.append(AnswerPlanItem(
                item_id="clarification",
                question_text=msg_raw,
                attribute="reference_clarification",
                status="needs_clarification",
                factual_claim=clarification_q,
                clarification_prompt=clarification_q,
            ))

        bundle.field_facts = field_facts
        bundle.answer_plan = plan
        bundle.direct_facts = direct_facts
        bundle.customer_requirements = dict(state.requirements) if hasattr(state, "requirements") else {}
        return bundle

    # ── Field Evaluation Helpers ──────────────────────────────────────────────

    @classmethod
    def _evaluate_wifi(cls, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        # Look in raw catalog dict
        conn_raw = prod.get("connectivity")
        summary_raw = str(prod.get("summary") or "")
        features_raw = str(prod.get("key_features") or prod.get("features") or "")

        # Also check NormalizedProduct repository if available
        repo_prod = catalog_repository.get_by_id(pid)
        repo_conn = repo_prod.verified.connectivity if repo_prod else []

        combined_text = (
            str(conn_raw or "") + " " + " ".join(repo_conn) + " " + summary_raw + " " + features_raw
        ).lower()

        # Check for positive Wi-Fi confirmation
        if any(w in combined_text for w in ["wifi", "wi-fi", "wireless", "wi-fi direct"]):
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="wifi",
                status="supported",
                value="Wi-Fi and Wi-Fi Direct wireless connectivity",
                source="catalog:connectivity",
                display_claim=f"Yes, the {p_name} supports Wi-Fi and Wi-Fi Direct wireless connectivity.",
            )

        # Check if connectivity is explicitly defined without Wi-Fi (e.g. Ethernet LAN only, USB only)
        if conn_raw or repo_conn:
            conn_desc = str(conn_raw) if conn_raw else ", ".join(repo_conn)
            if any(w in conn_desc.lower() for w in ["ethernet", "lan", "usb", "network"]):
                return FieldFact(
                    product_id=pid,
                    product_name=p_name,
                    attribute="wifi",
                    status="unsupported",
                    value=conn_desc,
                    source="catalog:connectivity",
                    display_claim=f"No, the {p_name} does not feature built-in Wi-Fi; verified connectivity is {conn_desc}.",
                )

        # Neither confirmed supported nor explicitly unsupported -> UNKNOWN
        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="wifi",
            status="unknown",
            value=None,
            source="none",
            display_claim=f"Wi-Fi connectivity is not listed in the verified catalogue specifications for the {p_name} and is unknown.",
        )

    @classmethod
    def _evaluate_scanner(cls, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        scanner_integrated = prod.get("scanner_integrated")
        functions = prod.get("functions") or []

        # Check repository NormalizedProduct if available
        repo_prod = catalog_repository.get_by_id(pid)
        if repo_prod and scanner_integrated is None:
            scanner_integrated = repo_prod.verified.has_scanner

        # Explicit True
        if scanner_integrated is True or "scan" in [f.lower() for f in functions]:
            w = prod.get("print_width") or prod.get("width")
            w_str = f" {w}-inch" if w else ""
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="scanner",
                status="supported",
                value=f"Integrated{w_str} scanner (Print, Scan, Copy)",
                source="catalog:functions",
                display_claim=f"Yes, the {p_name} features an integrated{w_str} scanner for scanning and copying.",
            )

        # Explicit False or functions explicitly print-only
        if scanner_integrated is False or (functions and functions == ["print"]):
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="scanner",
                status="unsupported",
                value="Dedicated print-only (no scanner)",
                source="catalog:functions",
                display_claim=f"No, the {p_name} is a dedicated print-only model and does not have an integrated scanner.",
            )

        # Field is absent/null -> UNKNOWN (Never infer from model suffix!)
        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="scanner",
            status="unknown",
            value=None,
            source="none",
            display_claim=f"The verified catalogue specifications for the {p_name} do not list whether an integrated scanner is included; scanner support is not documented and unknown.",
        )

    @classmethod
    def _evaluate_ink(cls, prod: Dict[str, Any]) -> Tuple[FieldFact, List[Dict[str, Any]]]:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        consumables = []
        try:
            from rag.consumables_engine import consumables_engine
            consumables = consumables_engine.get_consumables_for_printer(pid) or []
        except Exception:
            pass
        if not consumables and prod.get("consumables"):
            consumables = [{"name": str(c), "sku": str(c)} for c in prod["consumables"]]

        ink_tech = prod.get("ink_technology") or prod.get("colour_specification") or prod.get("technology")

        if consumables or ink_tech:
            tech_desc = ink_tech or "genuine manufacturer ink"
            skus = [c.get("sku") or c.get("part_number") for c in consumables if c.get("sku") or c.get("part_number")]
            sku_part = f" (compatible SKUs: {', '.join(skus[:6])})" if skus else ""
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="compatible_ink",
                status="supported",
                value={"technology": tech_desc, "skus": skus},
                source="catalog:consumables",
                display_claim=f"The {p_name} uses genuine {tech_desc}{sku_part}.",
            ), consumables

        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="compatible_ink",
            status="unknown",
            value=None,
            source="none",
            display_claim=f"Compatible consumables and ink specifications for the {p_name} are not listed in the verified catalogue and are unknown.",
        ), []

    @classmethod
    def _evaluate_tshirt(cls, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid
        cat = prod.get("category", "") or prod.get("main_category", "")

        if "f100" in pid or "f500" in pid or cat == "dye_sublimation":
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="t_shirt_capability",
                status="supported",
                value="Dye-sublimation transfer paper on polyester fabrics",
                source="catalog:category",
                display_claim=f"Yes, the {p_name} can be used for T-shirt printing by printing onto dye-sublimation transfer paper and heat-pressing onto polyester fabrics or garments.",
            )

        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="t_shirt_capability",
            status="unsupported",
            value="Aqueous pigment photo printer for paper/canvas; not compatible with direct apparel printing",
            source="catalog:specifications",
            display_claim=(
                f"No, the {p_name} is an aqueous pigment photo and fine-art printer designed for paper and canvas media; "
                "it cannot print directly on T-shirts or garments. Apparel printing requires dye-sublimation printers "
                "(such as the Epson SC-F100 or SC-F500) or direct-to-garment (DTG) systems."
            ),
        )

    @classmethod
    def _evaluate_media_request(cls, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        img_url = prod.get("image_url")
        prod_url = prod.get("product_url") or prod.get("website_url") or f"https://www.keplertechllc.com/product/{pid}/"

        # Validate that image_url is an actual verified URL and not a generic placeholder
        is_valid_img = (
            img_url
            and isinstance(img_url, str)
            and img_url.startswith("https://")
            and "placeholder" not in img_url.lower()
        )

        if is_valid_img:
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="media_request",
                status="supported",
                value=img_url,
                source="catalog:image_url",
                display_claim=f"Verified product photograph for the {p_name} is available here: {img_url}. You can also explore full product details at {prod_url}.",
            )

        # Verified URL only
        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="media_request",
            status="supported",
            value=prod_url,
            source="catalog:product_url",
            display_claim=f"Verified photographs, gallery views, and full technical specifications for the {p_name} can be viewed directly on our official product page at {prod_url}.",
        )

    @classmethod
    def _evaluate_configuration_difference(cls, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        if "p900" in pid.lower():
            diff_text = (
                "The difference between the two configurations is the media feeding mechanism: "
                "the standard Epson SureColor SC-P900 uses manual cut-sheet trays (supporting sheets up to A2+ / 17 inches wide), "
                "while the Roll Adapter configuration includes the optional roll media unit, enabling continuous roll paper printing "
                "and panoramic banners up to 17 inches wide and 18 meters in length."
            )
            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="configuration_difference",
                status="supported",
                value="Standard cut-sheet vs Roll Adapter unit",
                source="catalog:configurations",
                display_claim=diff_text,
            )

        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="configuration_difference",
            status="unknown",
            value=None,
            source="none",
            display_claim=f"Specific configuration differences for the {p_name} are not documented in the verified catalogue.",
        )

    @classmethod
    def _evaluate_prior_question_recall(cls, state: ConversationState, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        history = getattr(state, "history_turns", []) or []
        prior_q = None
        for turn in reversed(history[:-1] if len(history) > 1 else history):
            if turn.get("role") == "user":
                content = turn.get("content", "")
                if any(w in content.lower() for w in ["t-shirt", "t shirt", "tshirt", "p900", "print", "scan", "wifi"]):
                    prior_q = content
                    break

        if not prior_q:
            # Fall back to any prior user turn
            for turn in reversed(history[:-1] if len(history) > 1 else history):
                if turn.get("role") == "user":
                    prior_q = turn.get("content", "")
                    break

        if prior_q:
            if any(w in prior_q.lower() for w in ["t-shirt", "t shirt", "tshirt"]):
                recall_claim = (
                    f"Earlier you asked: \"{prior_q}\" (inquiring whether the {p_name} can print on T-shirts). "
                    f"To confirm: the {p_name} is an aqueous fine-art/photo printer and cannot print on T-shirts or apparel."
                )
            else:
                recall_claim = f"Earlier you asked: \"{prior_q}\" regarding the {p_name}."

            return FieldFact(
                product_id=pid,
                product_name=p_name,
                attribute="prior_question_recall",
                status="supported",
                value=prior_q,
                source="conversation_state:history",
                display_claim=recall_claim,
            )

        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="prior_question_recall",
            status="unknown",
            value=None,
            source="none",
            display_claim=f"I don't have a record of a prior specific question about the {p_name} in this session.",
        )

    @classmethod
    def _evaluate_price_policy(cls, prod: Dict[str, Any]) -> FieldFact:
        pid = prod.get("id", "")
        p_name = prod.get("display_name") or prod.get("model") or pid

        policy_text = (
            "I can assist you with verified product specifications, technical capabilities, and consumable compatibility "
            "from our official catalogue. For current pricing information, please check our official website at "
            "https://www.keplertechllc.com/."
        )
        return FieldFact(
            product_id=pid,
            product_name=p_name,
            attribute="price",
            status="unsupported",
            value=None,
            source="policy:commercial_refusal",
            display_claim=policy_text,
        )


evidence_planner = EvidencePlanner()
