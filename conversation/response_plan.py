"""
Structured Response Plan, Renderer, and Grounded Validator for Kepler Tech SalesAI.
Phase 5: Structured response plan, diverse human openers (3-turn no-repeat),
and strict pre-transmission validators (evidence grounding, intent relevance,
focus consistency, no-pricing-in-chat compliance).
"""

import os
import re
import random
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from conversation.understanding import DialogueAct, Intent
from conversation.dialogue_state import DialogueState, ResolvedTurn, SalientEntity
from conversation.policy import PolicyDecision, PolicyAction
from catalog.evidence import EvidenceEngine, EvidenceRecord, CompatibilityStatus, knowledge_graph

logger = logging.getLogger("conversation.response_plan")


# ── Response Plan Schema ──────────────────────────────────────────────────────

class ResponsePlan(BaseModel):
    direct_answer: str
    assumption: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    product_cards: List[Dict[str, Any]] = Field(default_factory=list)
    consumable_cards: List[Dict[str, Any]] = Field(default_factory=list)
    chips: List[str] = Field(default_factory=list)
    confirm_buttons: List[Dict[str, str]] = Field(default_factory=list)
    next_step: str = ""
    formatted_reply: str = ""
    source: str = "unified_understanding"
    evidence_records: List[EvidenceRecord] = Field(default_factory=list)
    is_valid: bool = True
    validation_errors: List[str] = Field(default_factory=list)


# ── Human Openers Rotation (3-turn no-repeat) ─────────────────────────────────

OPENERS_POOL = [
    "Understood.",
    "Yes, absolutely.",
    "Here are the verified details:",
    "Happy to help with that.",
    "Good question.",
    "Here is the official specification:",
    "Right away.",
    "Here is the breakdown:",
    "Let's look at the specifications:",
    "Here is what the manufacturer specifies:",
]


def _get_varied_opener(state: DialogueState) -> str:
    """Selects an opener avoiding the ones used in the last 3 turns."""
    recent_history = getattr(state, "recent_openers", []) or []
    available = [op for op in OPENERS_POOL if op not in recent_history[-3:]]
    if not available:
        available = OPENERS_POOL
    chosen = random.choice(available)
    if not hasattr(state, "recent_openers"):
        state.recent_openers = []
    state.recent_openers.append(chosen)
    return chosen


# ── Response Plan Builder ─────────────────────────────────────────────────────

class ResponsePlanBuilder:
    """Constructs a grounded, interactive response plan from policy decisions."""

    @classmethod
    def build(
        cls,
        decision: PolicyDecision,
        resolved: ResolvedTurn,
        state: DialogueState,
    ) -> ResponsePlan:
        und = resolved.understanding
        cards: List[Dict[str, Any]] = []
        c_cards: List[Dict[str, Any]] = []
        confirm_buttons: List[Dict[str, str]] = []
        chips = list(decision.options_or_chips)
        direct_answer = ""
        assumption = decision.assumption_text
        evidence_ids: List[str] = []

        # Gather evidence IDs
        for rec in decision.evidence_records:
            evidence_ids.extend(rec.entity_ids)

        # 1. Compatibility Answer Flow
        if decision.action in (PolicyAction.ANSWER, PolicyAction.ANSWER_WITH_STATED_ASSUMPTION) and und.intent == Intent.COMPATIBILITY_CHECK:
            rec = decision.evidence_records[0] if decision.evidence_records else None
            direct_answer = rec.claim if rec else "Compatibility could not be verified."

            # Attach Hardware Card for target printer
            if decision.target_entity_id:
                t_node = knowledge_graph.nodes.get(decision.target_entity_id.lower())
                if t_node:
                    cards.append({
                        "card_type": "hardware",
                        "id": t_node.id,
                        "model_family": t_node.attributes.get("model_family") or t_node.name,
                        "display_name": t_node.name,
                        "primary_category": t_node.attributes.get("category"),
                        "product_url": t_node.attributes.get("url") or f"https://www.keplertechllc.com/product/{t_node.id}",
                        "image_url": t_node.attributes.get("image_url") or "/static/img/products/default.png",
                        "badges": ["Verified Official Model"],
                    })

            # Attach Consumable Card for active item
            if decision.active_item_id:
                c_node = knowledge_graph.nodes.get(decision.active_item_id.upper())
                if c_node:
                    c_cards.append({
                        "card_type": "consumable",
                        "sku": c_node.id,
                        "name": c_node.name,
                        "category": c_node.attributes.get("type", "consumable"),
                        "color": c_node.attributes.get("color"),
                        "product_url": c_node.attributes.get("url") or f"https://www.keplertechllc.com/product/{c_node.id.lower()}",
                        "badges": ["Genuine Kepler Tech Consumable"],
                    })

            confirm_buttons = [
                {"label": "Yes, show full specs", "payload": f"specs_{decision.target_entity_id}"},
                {"label": "Show compatible inks", "payload": f"inks_{decision.target_entity_id}"},
            ]

        # 2. Clarification Flow
        elif decision.action == PolicyAction.CLARIFY:
            direct_answer = decision.clarification_question or "Could you clarify your requirements?"
            opt_chips = [
                c for c in (decision.options_or_chips or [])
                if c not in ("Contact Sales Desk", "Official Quotation", "View Technical Specifications", "Ask a Question", "Continue Consultation", "Start Over")
            ]
            if opt_chips and not any(c.lower() in direct_answer.lower() for c in opt_chips[:2]):
                options_block = "\n".join([f"• {c}" for c in opt_chips])
                direct_answer = f"{direct_answer}\n\n{options_block}"

        # 3. Handoff Flow
        elif decision.action == PolicyAction.NOT_VERIFIED_HANDOFF:
            direct_answer = decision.next_step

        # 4. Out of Scope Flow
        elif decision.action == PolicyAction.OUT_OF_SCOPE_REDIRECT:
            direct_answer = (
                "Kepler Tech is an authorized distributor specializing in official Epson large-format "
                "and Citizen photo/dye-sublimation systems. We do not carry 3D printers, laser copiers, or third-party brands in our catalogue."
            )

        # 5. Default Answer Flow
        else:
            rec = decision.evidence_records[0] if decision.evidence_records else None
            direct_answer = rec.claim if rec else (decision.next_step or "Here is the information from our verified catalogue.")

        # Ensure hardware cards are attached whenever target_entity_id is present
        # Ensure hardware cards are attached whenever target_entity_id or supporting_product_ids are present
        all_target_ids: List[str] = []
        if decision.target_entity_id:
            all_target_ids.append(decision.target_entity_id)
        if getattr(decision, "supporting_product_ids", None):
            for spid in decision.supporting_product_ids:
                if spid not in all_target_ids:
                    all_target_ids.append(spid)

        for pid in all_target_ids[:3]:
            if not any(c.get("id") == pid for c in cards):
                t_node = knowledge_graph.nodes.get(pid.lower())
                name_str = t_node.name if t_node else pid
                cat_str = (t_node.attributes.get("category") if t_node else None) or "Hardware"
                url_str = (t_node.attributes.get("url") if t_node else None) or f"https://www.keplertechllc.com/product/{pid}"
                img_str = (t_node.attributes.get("image_url") if t_node else None) or "/static/img/products/default.png"
                mod_str = (t_node.attributes.get("model_family") if t_node else None) or name_str

                if not t_node:
                    try:
                        from catalog.catalogue_loader import catalogue_loader
                        p_info = catalogue_loader.get_by_id(pid.lower()) or {}
                        if p_info:
                            name_str = p_info.get("display_name") or p_info.get("name") or name_str
                            cat_str = p_info.get("category") or cat_str
                            url_str = p_info.get("product_url") or url_str
                            img_str = p_info.get("image_url") or img_str
                            mod_str = p_info.get("model") or p_info.get("model_family") or mod_str
                    except Exception:
                        pass

                is_primary = (len(cards) == 0)
                badge = "Primary Recommendation" if is_primary else "Verified Alternative"
                rationale = "Primary recommendation matching your specifications." if is_primary else "Verified alternative option with matching capabilities."

                cards.append({
                    "card_type": "hardware",
                    "id": pid,
                    "title": name_str,
                    "name": name_str,
                    "model": mod_str,
                    "model_family": mod_str,
                    "display_name": name_str,
                    "primary_category": cat_str,
                    "category": cat_str,
                    "product_url": url_str,
                    "image_url": img_str,
                    "badges": [badge],
                    "rationale": rationale,
                    "match_reasons": [rationale],
                    "actions": ["Request Official Quote", "View Specs", "Compare"],
                    "buttons": [
                        {"label": "Request Official Quote", "payload": f"quote_{pid}"},
                        {"label": "Compare", "payload": f"compare_{pid}"},
                    ],
                    "price": None,
                    "price_formatted": "Commercial Quote on Request",
                    "price_str": "Commercial Quote on Request",
                    "currency": "AED",
                    "is_request": True,
                })

        # Cap hardware cards to 1 primary + up to 2 verified alternatives (max 3 cards)
        cards = cards[:3]

        # Ensure consumable cards are attached whenever active_item_id is present
        if decision.active_item_id and not c_cards:
            c_node = knowledge_graph.nodes.get(decision.active_item_id.upper())
            if c_node and c_node.node_type == "consumable":
                c_url = c_node.attributes.get("product_url") or c_node.attributes.get("url") or c_node.attributes.get("website_url") or f"https://www.keplertechllc.com/product/{c_node.id.lower()}"
                c_img = c_node.attributes.get("image_url") or c_node.attributes.get("image") or "https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png"
                c_cards.append({
                    "card_type": "consumable",
                    "sku": c_node.id,
                    "name": c_node.name,
                    "title": c_node.name,
                    "category": c_node.attributes.get("category") or c_node.attributes.get("type", "consumable"),
                    "color": c_node.attributes.get("color"),
                    "product_url": c_url,
                    "url": c_url,
                    "source_url": c_url,
                    "website_url": c_url,
                    "image_url": c_img,
                    "image": c_img,
                    "price": c_node.attributes.get("price"),
                    "price_str": c_node.attributes.get("price_str") or c_node.attributes.get("price_formatted"),
                    "badges": ["Genuine Kepler Tech Consumable"],
                })

        # Also attach consumable cards from evidence records supporting data (e.g. list_consumables)
        for rec_item in decision.evidence_records:
            if rec_item.supporting_data and "consumables" in rec_item.supporting_data:
                for c_item in rec_item.supporting_data["consumables"][:6]:
                    if isinstance(c_item, dict):
                        c_sku = c_item.get("sku") or c_item.get("id")
                        c_name = c_item.get("name") or f"Genuine Consumable {c_sku}"
                        c_cat = c_item.get("category") or "consumable"
                        c_col = c_item.get("color")
                        c_url = c_item.get("product_url") or c_item.get("url") or c_item.get("website_url") or c_item.get("source_url")
                        c_img = c_item.get("image_url") or c_item.get("image")
                        c_price = c_item.get("price")
                        c_price_str = c_item.get("price_str") or c_item.get("price_formatted")
                    else:
                        c_sku = str(c_item)
                        c_name = f"Genuine Consumable {c_sku}"
                        c_cat = "consumable"
                        c_col = None
                        c_url = None
                        c_img = None
                        c_price = None
                        c_price_str = None

                    # If image or url is missing, lookup from knowledge_graph node
                    if c_sku:
                        knode = knowledge_graph.nodes.get(c_sku.upper()) or knowledge_graph.nodes.get(c_sku)
                        if knode:
                            if not c_img or c_img == "/static/img/products/default.png":
                                c_img = knode.attributes.get("image_url") or knode.attributes.get("image")
                            if not c_url or c_url.endswith("#") or c_url.endswith("/product/"):
                                c_url = knode.attributes.get("product_url") or knode.attributes.get("url") or knode.attributes.get("website_url") or knode.attributes.get("source_url")
                            if c_price is None:
                                c_price = knode.attributes.get("price")
                                c_price_str = knode.attributes.get("price_str") or knode.attributes.get("price_formatted")
                            if not c_name or c_name == f"Genuine Consumable {c_sku}":
                                c_name = knode.name or c_name

                    if not c_url:
                        c_url = f"https://www.keplertechllc.com/product/{c_sku.lower()}"

                    if not c_img:
                        c_img = "https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png"

                    if c_sku and not any(cc.get("sku") == c_sku for cc in c_cards):
                        c_cards.append({
                            "card_type": "consumable",
                            "sku": c_sku,
                            "name": c_name,
                            "title": c_name,
                            "category": c_cat,
                            "color": c_col,
                            "product_url": c_url,
                            "url": c_url,
                            "source_url": c_url,
                            "website_url": c_url,
                            "image_url": c_img,
                            "image": c_img,
                            "price": c_price,
                            "price_str": c_price_str,
                            "badges": ["Genuine Kepler Tech Consumable"],
                        })

        # Assemble full formatted text
        parts = []
        if assumption:
            parts.append(f"*{assumption}*\n")

        # If direct_answer starts directly with a brand or model, prepend a natural varied opener
        clean_direct = direct_answer.strip()
        if clean_direct.startswith(("Epson", "Citizen", "**Epson", "**Citizen")) and not assumption:
            opener = _get_varied_opener(state)
            parts.append(f"{opener}\n\n{clean_direct}")
        else:
            parts.append(direct_answer)

        if decision.next_step and decision.next_step not in direct_answer:
            parts.append(f"\n\n{decision.next_step}")

        formatted_text = "".join(parts).strip()

        plan = ResponsePlan(
            direct_answer=direct_answer,
            assumption=assumption,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            product_cards=cards,
            consumable_cards=c_cards,
            chips=chips,
            confirm_buttons=confirm_buttons,
            next_step=decision.next_step,
            formatted_reply=formatted_text,
            evidence_records=decision.evidence_records,
            source=f"unified:{decision.action.value.lower()}",
        )

        # Run strict grounding and policy validators
        validated_plan = ResponsePlanValidator.validate(plan, resolved, state)
        return validated_plan


# ── Response Plan Pre-Transmission Validators ─────────────────────────────────

class ResponsePlanValidator:
    """
    Enforces 4 strict pre-flight invariant gates before emitting any reply:
    1. Grounding check: Every SKU/model in text exists in evidence
    2. Answers the question check: Reply addresses customer's intent
    3. Focus consistency: Focus model is not silently swapped
    4. Commercial policy check: No chat pricing or volume discount promises
    """

    PRICE_NUMERIC_PATTERN = re.compile(r"\b(?:aed\s*\d+|price\s*is\s*\d+|\$\s*\d+)\b", re.I)

    @classmethod
    def validate(
        cls,
        plan: ResponsePlan,
        resolved: ResolvedTurn,
        state: DialogueState,
    ) -> ResponsePlan:
        errors: List[str] = []
        text = plan.formatted_reply

        # 1. Commercial Policy Guardrail: No chat pricing or volume discount promises
        # Official quotations must strictly route to sales desk (except verified flat AED 10 delivery fee
        # and explicitly verified list prices / print-cost calculations backed by evidence records).
        has_price_violation = False
        for m in cls.PRICE_NUMERIC_PATTERN.finditer(text):
            matched = m.group(0).lower()
            # Verified flat AED 10 delivery fee is explicitly permitted
            if "10" in matched and any(k in text.lower() for k in ["delivery", "shipping", "fee", "courier", "postage"]):
                continue
            has_price_violation = True
            break

        # Allow numeric prices when supported by a verified evidence record (price, cost_per_print, pricing_policy)
        if has_price_violation:
            PRICE_EVIDENCE_FIELDS = {"price", "price_str", "cost_per_print", "pricing_policy"}
            has_verified_price_evidence = any(
                rec.field in PRICE_EVIDENCE_FIELDS and rec.verified
                for rec in plan.evidence_records
            )
            if has_verified_price_evidence:
                has_price_violation = False

        if has_price_violation and "official request" not in text.lower():
            errors.append("Commercial policy violation: unverified price numeric claim in text.")

        # 2. Grounding Check: If text mentions a SKU, verify it exists in evidence records or associated products
        sku_mentions = re.findall(r"\b(c1[123][a-z0-9]{5,9}|cy-ms\w+|cz-ms\w+|cx2\w+)\b", text.lower())
        for sm in sku_mentions:
            sm_clean = sm.upper().replace(" ", "").replace("-", "")
            in_ev_ids = any(sm_clean in eid.upper().replace("-", "") for eid in plan.evidence_ids)
            in_active_item = bool(resolved.resolved_active_item and sm_clean in resolved.resolved_active_item.id.upper().replace("-", ""))
            in_associated = False
            if not (in_ev_ids or in_active_item):
                for rec in plan.evidence_records:
                    for eid in rec.entity_ids:
                        node = knowledge_graph.nodes.get(eid.lower()) or knowledge_graph.nodes.get(eid.upper())
                        if node:
                            node_cons = [str(c).upper().replace(" ", "").replace("-", "") for c in node.attributes.get("consumables", [])]
                            if any(sm_clean in nc or nc in sm_clean for nc in node_cons):
                                in_associated = True
                                break
                    if in_associated:
                        break

            if not (in_ev_ids or in_active_item or in_associated):
                errors.append(f"Grounding violation: SKU '{sm}' in text without supporting evidence.")

        # 3. Intent Relevance Check
        if resolved.understanding.intent == Intent.COMPATIBILITY_CHECK:
            if not any(w in text.lower() for w in ["yes", "no", "compatible", "not compatible", "suitable"]):
                errors.append("Relevance violation: compatibility check did not contain a yes/no verification.")

        # 4. Silent Focus Switch Check
        if resolved.resolved_target_product and state.get_current_focus("printer"):
            current_f = state.get_current_focus("printer")
            new_f = resolved.resolved_target_product
            # If changed without explicit mention in user text or entities
            is_explicitly_mentioned = (
                new_f.id in resolved.understanding.raw_text.lower()
                or any(e.normalised_id == new_f.id for e in resolved.understanding.entities)
                or any(r.resolved_entity and r.resolved_entity.id == new_f.id for r in resolved.resolved_referents)
            )
            if current_f.id != new_f.id and not is_explicitly_mentioned:
                errors.append(f"Focus violation: switched focus from {current_f.id} to {new_f.id} without user mention.")

        # 5. Template & Leaked Internal Structure Guard
        LEAK_MARKERS = [" = ", "display_name", "None", "null", "{", "}"]
        found_leaks = [m for m in LEAK_MARKERS if m in text]
        if found_leaks:
            errors.append(f"Template leak violation: markers found in response text: {found_leaks}")

        # 5b. Pre-Transmission Accuracy Guard: All recommended models must belong to approved catalogue
        is_unlisted_explanation = any(phrase in text.lower() for phrase in [
            "not in our verified catalogue", "not part of our approved", "we do not supply", "unlisted", "does not list",
            "not in our", "not part of our", "catalogue does not include", "do not carry", "is not in our"
        ])
        if not is_unlisted_explanation:
            from catalog.catalogue_loader import catalogue_loader
            all_prods = catalogue_loader.get_all()
            model_mentions = re.findall(r"\b(?:sc-?)?(?:[tpf]\d{3,5}[a-z0-9]*|ds-?\d{3,5}[a-z0-9]*|cx-?[0-9o]{1,2}[a-z0-9]*|am-?c\d{3,4}[a-z0-9]*|wf-?(?:c|m)?\d{3,5}[a-z0-9]*)\b", text.lower())
            for mm in model_mentions:
                if len(mm) >= 4:
                    in_cat = any(mm in str(p.get("id", "")).lower() or mm in str(p.get("model", "")).lower() or mm in str(p.get("display_name", "")).lower() for p in all_prods)
                    in_cards = any(mm in (str(c.get("id", "")) + str(c.get("name", "")) + str(c.get("model", ""))).lower() for c in (plan.product_cards + plan.consumable_cards))
                    in_ev = any(mm in eid.lower() or eid.lower() in mm for eid in plan.evidence_ids)
                    if not (in_cat or in_cards or in_ev):
                        errors.append(f"Accuracy violation: Model '{mm}' mentioned without verified evidence.")

        # 5c. Banned Corporate Cliches Filter
        BANNED_PHRASE_REPLACEMENTS = [
            (r"\bCertainly!\s*", ""),
            (r"\bWe would be delighted to assist you(?: in person)?!\s*", ""),
            (r"\bdelighted to assist\b", "pleased to help"),
            (r"\bBased on your requirements,?\s*", ""),
            (r"\bAs an AI(?: language model)?,?\s*", ""),
            (r"\bAccording to our database,?\s*", ""),
            (r"\bAs per records,?\s*", ""),
            (r"\bAs per your previous (?:question|message)?,?\s*", ""),
        ]
        for pat, repl in BANNED_PHRASE_REPLACEMENTS:
            text = re.sub(pat, repl, text, flags=re.IGNORECASE).strip()
        plan.formatted_reply = text

        # 5d. Enforce Succinct Length (under ~60 words unless technical comparison table or structured list)
        is_structured = (
            ("|" in text and "---" in text)
            or text.count("•") >= 2
            or len(text.split("\n\n")) >= 3
            or bool(getattr(resolved.understanding, "secondary_intents", []))
            or "@" in text
            or any(k in text.lower() for k in ["sales desk", "official quote", "official delivery", "flat aed 10", "business days"])
        )
        words = text.split()
        if not is_structured and len(words) > 65:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
            trimmed = []
            curr_words = 0
            for s in sentences:
                s_len = len(s.split())
                if curr_words + s_len <= 60 or not trimmed:
                    trimmed.append(s)
                    curr_words += s_len
                else:
                    break
            if trimmed:
                text = " ".join(trimmed)
                plan.formatted_reply = text

        if errors:
            logger.warning(f"Response plan validation errors: {errors}. Falling back to deterministic template.")
            plan.is_valid = False
            plan.validation_errors = errors
            # Fallback to deterministic template: use clean claim from evidence record
            clean_claim = None
            if plan.evidence_records:
                for rec in plan.evidence_records:
                    if rec.claim and not any(m in rec.claim for m in LEAK_MARKERS):
                        clean_claim = rec.claim
                        break
                if not clean_claim and plan.evidence_records:
                    raw_c = plan.evidence_records[0].claim
                    # Sanitize any residual raw claim
                    raw_c = raw_c.replace("display_name = ", "").replace(" = ", ": ").replace("{", "").replace("}", "")
                    clean_claim = raw_c

            if clean_claim:
                plan.formatted_reply = clean_claim
                if plan.next_step and not any(m in plan.next_step for m in LEAK_MARKERS):
                    plan.formatted_reply += f"\n\n{plan.next_step}"
            else:
                plan.formatted_reply = "I can only confirm specifications verified in our official catalogue. How can I assist you with your equipment requirements?"

            # Final safety check: scrub any remaining leak markers
            for lm in LEAK_MARKERS:
                if lm in plan.formatted_reply:
                    if lm == " = ":
                        plan.formatted_reply = plan.formatted_reply.replace(" = ", ": ")
                    elif lm == "display_name":
                        plan.formatted_reply = plan.formatted_reply.replace("display_name", "model")
                    else:
                        plan.formatted_reply = plan.formatted_reply.replace(lm, "")

        # 6. Anti-Repeat Consecutive Reply Guard
        prev_replies = getattr(state, "recent_assistant_replies", []) or []
        if prev_replies and plan.formatted_reply:
            from difflib import SequenceMatcher
            for prev_r in prev_replies[-2:]:
                ratio = SequenceMatcher(None, plan.formatted_reply.strip().lower(), prev_r.strip().lower()).ratio()
                if ratio >= 0.85:
                    logger.warning(f"Anti-repeat guard: Candidate reply similarity {ratio:.2f} >= 0.85. Rephrasing.")
                    transitions = [
                        "To continue with your equipment selection:",
                        "Moving forward with your request:",
                        "Regarding your operational workflow:",
                        "To help guide you to the right system:",
                    ]
                    chosen_t = transitions[state.turn_count % len(transitions)]
                    plan.formatted_reply = f"{chosen_t}\n\n{plan.formatted_reply}"
                    break

        if not hasattr(state, "recent_assistant_replies") or state.recent_assistant_replies is None:
            state.recent_assistant_replies = []
        state.recent_assistant_replies.append(plan.formatted_reply)
        if len(state.recent_assistant_replies) > 5:
            state.recent_assistant_replies.pop(0)

        return plan
