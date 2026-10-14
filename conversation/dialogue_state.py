"""
Dialogue State and Universal Referent Resolution Engine for Kepler Tech SalesAI.
Phase 2: Per-session focus stack, last_shown artifacts, pending questions,
salience-ranked referent resolution, ellipsis inheritance, and short reply binding.
"""

import time
import logging
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from conversation.understanding import (
    TurnUnderstanding,
    DialogueAct,
    Intent,
    EntityMention,
    ReferenceExpression,
    SlotValue,
)

logger = logging.getLogger("conversation.dialogue_state")


# ── State Representation Schemas ──────────────────────────────────────────────

class SalientEntity(BaseModel):
    id: str
    entity_type: str  # "printer", "consumable", "media", "accessory"
    name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    turn_introduced: int = 0
    salience_score: float = 1.0


class PendingQuestion(BaseModel):
    question_id: str
    question_text: str
    topic: str  # e.g., "model_choice", "paper_size", "confirmation"
    expected_type: str  # "choice", "confirmation", "free_text"
    options: List[Dict[str, Any]] = Field(default_factory=list)  # [{"id": "...", "label": "...", "value": "..."}]
    turn_asked: int = 0


class DialogueState(BaseModel):
    session_id: str
    turn_count: int = 0
    category: Optional[str] = None
    focus_stack: List[SalientEntity] = Field(default_factory=list)
    last_shown_products: List[Dict[str, Any]] = Field(default_factory=list)
    last_shown_consumables: List[Dict[str, Any]] = Field(default_factory=list)
    last_shown_cards: List[Dict[str, Any]] = Field(default_factory=list)
    last_shown_chips: List[str] = Field(default_factory=list)
    pending_question: Optional[PendingQuestion] = None
    confirmed_slots: Dict[str, Any] = Field(default_factory=dict)
    corrections_history: List[Dict[str, Any]] = Field(default_factory=list)
    clarifications_asked: Dict[str, int] = Field(default_factory=dict)  # topic -> count
    last_intent: Optional[Intent] = None
    last_dialogue_act: Optional[DialogueAct] = None
    last_direct_answer: Optional[str] = None
    recent_mentions: List[SalientEntity] = Field(default_factory=list)
    recent_assistant_replies: List[str] = Field(default_factory=list)
    recent_openers: List[str] = Field(default_factory=list)
    category_intro_displayed: List[str] = Field(default_factory=list)
    last_user_message: Optional[str] = None
    handover_triggered: bool = False
    handover_reason: Optional[str] = None
    handover_timestamp: Optional[float] = None
    buyer_pace: str = "standard"  # "concise" | "standard" | "technical"
    buyer_pace_turn: int = 0

    def get_current_focus(self, entity_type: Optional[str] = None) -> Optional[SalientEntity]:
        """Returns the top entity from the focus stack matching entity_type if specified."""
        if not self.focus_stack:
            return None
        if not entity_type:
            return self.focus_stack[-1]
        for ent in reversed(self.focus_stack):
            if ent.entity_type == entity_type:
                return ent
        return None

    def push_focus(self, entity: SalientEntity):
        """Pushes an entity to the focus stack, moving duplicates to the top."""
        self.focus_stack = [e for e in self.focus_stack if e.id != entity.id]
        self.focus_stack.append(entity)
        # Keep focus stack at max 10
        if len(self.focus_stack) > 10:
            self.focus_stack = self.focus_stack[-10:]

    def record_shown_artifacts(
        self,
        products: Optional[List[Dict[str, Any]]] = None,
        consumables: Optional[List[Dict[str, Any]]] = None,
        cards: Optional[List[Dict[str, Any]]] = None,
        chips: Optional[List[str]] = None,
    ):
        """Updates last shown artifacts and pushes them to salience."""
        if products is not None:
            self.last_shown_products = products
            for p in reversed(products):
                if isinstance(p, dict):
                    pid = p.get("id") or p.get("model_family") or p.get("sku")
                    pname = p.get("display_name") or p.get("name") or pid
                    meta = p
                else:
                    pid = str(p)
                    pname = str(p)
                    meta = {"id": str(p)}
                if pid:
                    self.push_focus(SalientEntity(
                        id=str(pid),
                        entity_type="printer",
                        name=str(pname),
                        metadata=meta,
                        turn_introduced=self.turn_count,
                        salience_score=1.0,
                    ))

        if consumables is not None:
            self.last_shown_consumables = consumables
            for c in consumables:
                cid = c.get("sku") or c.get("id") or c.get("code")
                cname = c.get("name") or c.get("display_name") or cid
                if cid:
                    self.push_focus(SalientEntity(
                        id=str(cid),
                        entity_type="consumable",
                        name=str(cname),
                        metadata=c,
                        turn_introduced=self.turn_count,
                        salience_score=1.0,
                    ))

        if cards is not None:
            self.last_shown_cards = cards
        if chips is not None:
            self.last_shown_chips = chips


# ── Generic Referent Resolution Engine ────────────────────────────────────────

class ResolvedReferent(BaseModel):
    reference_text: str
    resolved_entity: Optional[SalientEntity] = None
    confidence: float = 0.0
    alternatives: List[SalientEntity] = Field(default_factory=list)
    resolution_source: str = "none"  # "last_shown", "pending_options", "focus_stack", "recent_mentions"


class ResolvedTurn(BaseModel):
    understanding: TurnUnderstanding
    resolved_referents: List[ResolvedReferent] = Field(default_factory=list)
    resolved_target_product: Optional[SalientEntity] = None
    resolved_active_item: Optional[SalientEntity] = None
    is_ellipsis: bool = False
    bound_pending_option: Optional[Dict[str, Any]] = None


class ReferentResolver:
    """
    Generic resolver: every reference expression and every elided slot is resolved
    against a salience-ranked candidate list:
    last_shown > pending options > focus stack > recent mentions.
    """

    @classmethod
    def resolve_reference(
        cls,
        ref: ReferenceExpression,
        state: DialogueState,
    ) -> ResolvedReferent:
        """Resolves a single reference expression to a salient candidate."""
        hint = ref.target_type_hint or "unknown"
        text_l = ref.text.lower()

        # Build salience-ranked candidate list
        # Priority 1: Last shown items matching hint
        candidates: List[Tuple[SalientEntity, str]] = []

        if hint in ("consumable", "unknown") and state.last_shown_consumables:
            for c in state.last_shown_consumables:
                cid = c.get("sku") or c.get("id")
                cname = c.get("name") or cid
                if cid:
                    candidates.append((SalientEntity(
                        id=str(cid),
                        entity_type="consumable",
                        name=str(cname),
                        metadata=c,
                        turn_introduced=state.turn_count,
                    ), "last_shown"))

        if hint in ("printer", "unknown") and state.last_shown_products:
            for p in state.last_shown_products:
                pid = p.get("id") or p.get("model_family")
                pname = p.get("display_name") or p.get("name") or pid
                if pid:
                    candidates.append((SalientEntity(
                        id=str(pid),
                        entity_type="printer",
                        name=str(pname),
                        metadata=p,
                        turn_introduced=state.turn_count,
                    ), "last_shown"))

        # Priority 2: Pending options
        if state.pending_question and state.pending_question.options:
            for opt in state.pending_question.options:
                opt_id = opt.get("id") or opt.get("value")
                opt_label = opt.get("label") or opt_id
                if opt_id:
                    candidates.append((SalientEntity(
                        id=str(opt_id),
                        entity_type="printer",
                        name=str(opt_label),
                        metadata=opt,
                        turn_introduced=state.turn_count,
                    ), "pending_options"))

        # Priority 3: Focus stack (most recent first)
        for ent in reversed(state.focus_stack):
            if hint == "unknown" or ent.entity_type == hint:
                if not any(c[0].id == ent.id for c in candidates):
                    candidates.append((ent, "focus_stack"))

        # Priority 4: Recent mentions
        for ent in reversed(state.recent_mentions):
            if hint == "unknown" or ent.entity_type == hint:
                if not any(c[0].id == ent.id for c in candidates):
                    candidates.append((ent, "recent_mentions"))

        if not candidates and hint != "unknown":
            # Fallback across types if specific hint yielded no candidates
            for p in state.last_shown_products:
                pid = p.get("id") or p.get("model_family")
                pname = p.get("display_name") or p.get("name") or pid
                if pid and not any(c[0].id == str(pid) for c in candidates):
                    candidates.append((SalientEntity(
                        id=str(pid),
                        entity_type="printer",
                        name=str(pname),
                        metadata=p,
                        turn_introduced=state.turn_count,
                    ), "last_shown"))
            for ent in reversed(state.focus_stack):
                if not any(c[0].id == ent.id for c in candidates):
                    candidates.append((ent, "focus_stack"))

        if not candidates:
            return ResolvedReferent(
                reference_text=ref.text,
                resolved_entity=None,
                confidence=0.0,
                alternatives=[],
                resolution_source="none",
            )

        # Handle specific reference types
        # 1. Color reference (e.g. "the yellow one", "the black one")
        if ref.reference_type == "color_ref":
            for color in ["yellow", "cyan", "magenta", "black", "grey", "gray"]:
                if color in text_l:
                    for cand, src in candidates:
                        cand_color = str(cand.metadata.get("color") or "").lower()
                        cand_name = cand.name.lower()
                        if color in cand_color or color in cand_name:
                            return ResolvedReferent(
                                reference_text=ref.text,
                                resolved_entity=cand,
                                confidence=0.98,
                                alternatives=[c[0] for c in candidates if c[0].id != cand.id],
                                resolution_source=src,
                            )

        # 2. Ordinal reference (e.g. "the first one", "the second one")
        if ref.reference_type == "ordinal":
            idx = 0
            if any(w in text_l for w in ["second", "2nd"]):
                idx = 1
            elif any(w in text_l for w in ["third", "3rd"]):
                idx = 2
            elif "last" in text_l:
                idx = len(candidates) - 1

            if 0 <= idx < len(candidates):
                cand, src = candidates[idx]
                return ResolvedReferent(
                    reference_text=ref.text,
                    resolved_entity=cand,
                    confidence=0.95,
                    alternatives=[c[0] for c in candidates if c[0].id != cand.id],
                    resolution_source=src,
                )

        # 3. Comparative reference (e.g. "the cheaper one", "the faster one")
        if ref.reference_type == "comparative" and "cheaper" in text_l:
            priced = [c for c in candidates if c[0].metadata.get("price")]
            if priced:
                cheapest, src = min(priced, key=lambda c: float(c[0].metadata.get("price", 9999999)))
                return ResolvedReferent(
                    reference_text=ref.text,
                    resolved_entity=cheapest,
                    confidence=0.90,
                    alternatives=[c[0] for c in candidates if c[0].id != cheapest.id],
                    resolution_source=src,
                )

        # Default salience pick (top candidate)
        top_cand, top_src = candidates[0]
        return ResolvedReferent(
            reference_text=ref.text,
            resolved_entity=top_cand,
            confidence=0.92,
            alternatives=[c[0] for c in candidates[1:]],
            resolution_source=top_src,
        )

    @classmethod
    def bind_short_reply(
        cls,
        text: str,
        state: DialogueState,
    ) -> Optional[Dict[str, Any]]:
        """Binds short replies ('yes', 'ok', '1', '2', 'the first one', 'the second') to pending options or chips."""
        options: List[Dict[str, Any]] = []
        if state.pending_question and state.pending_question.options:
            options = list(state.pending_question.options)
        elif state.last_shown_products:
            options = [
                {
                    "id": p.get("id") or p.get("model_family"),
                    "label": p.get("display_name") or p.get("name") or p.get("id"),
                    "value": p.get("id"),
                    "product": p,
                }
                for p in state.last_shown_products
            ]
        elif state.last_shown_chips:
            options = [{"id": c, "label": c, "value": c} for c in state.last_shown_chips]

        text_l = text.lower().strip()

        # Direct chip label match if user typed or clicked a chip
        if state.last_shown_chips:
            for c in state.last_shown_chips:
                c_l = c.lower().strip()
                if text_l == c_l or (len(text_l) > 3 and text_l in c_l):
                    return {"id": c, "label": c, "value": c}

        if not options:
            return None

        # Ordinal or numeric binding ("1", "first", "the first one", "2", "second", "the second one")
        if text_l in ("1", "first", "the first", "the first one", "first one", "option 1", "choice 1"):
            return options[0] if len(options) > 0 else None
        if text_l in ("2", "second", "the second", "the second one", "second one", "option 2", "choice 2"):
            return options[1] if len(options) > 1 else None
        if text_l in ("3", "third", "the third", "the third one", "third one", "option 3", "choice 3"):
            return options[2] if len(options) > 2 else None

        # Yes / Affirmative binding
        if text_l in ("yes", "yep", "sure", "ok", "correct", "affirmative", "that's right", "thats right"):
            for opt in options:
                if str(opt.get("id", "")).lower() in ("yes", "confirm", "proceed") or "yes" in str(opt.get("label", "")).lower():
                    return opt
            return options[0]

        # No / Rejection binding
        if text_l in ("no", "nope", "neither", "cancel", "disagree"):
            for opt in options:
                if str(opt.get("id", "")).lower() in ("no", "reject", "cancel") or "no" in str(opt.get("label", "")).lower():
                    return opt

        # Exact or partial label match
        for opt in options:
            label = str(opt.get("label", "")).lower()
            if text_l == label or text_l in label or label in text_l:
                return opt

        return None

    @classmethod
    def resolve_turn(
        cls,
        understanding: TurnUnderstanding,
        state: DialogueState,
    ) -> ResolvedTurn:
        """
        Resolves an entire turn:
        1. Binds short replies to pending questions.
        2. Resolves all reference expressions ("this", "it", etc.).
        3. Handles ellipsis inheritance ("and for the f100?").
        4. Resolves active item and target model together.
        """
        resolved_refs: List[ResolvedReferent] = []
        bound_option = None

        # Track buyer pace with decay
        current_pace = getattr(understanding, "buyer_pace", "standard") or "standard"
        if current_pace != "standard":
            state.buyer_pace = current_pace
            state.buyer_pace_turn = state.turn_count
        else:
            if state.buyer_pace != "standard" and (state.turn_count - getattr(state, "buyer_pace_turn", 0) > 3):
                state.buyer_pace = "standard"
        state.confirmed_slots["buyer_pace"] = state.buyer_pace

        # 1. Short reply binding
        is_short_or_ordinal = (
            understanding.dialogue_act in (DialogueAct.CONFIRMATION, DialogueAct.REJECTION, DialogueAct.ANSWER_TO_MY_QUESTION)
            or len(understanding.raw_text.split()) <= 4
            or any(w in understanding.raw_text.lower() for w in ["first", "second", "third", "1st", "2nd", "3rd", "option", "yes", "ok", "confirm"])
        )
        if is_short_or_ordinal:
            bound_option = cls.bind_short_reply(understanding.raw_text, state)

        # 2. Reference expressions resolution
        for ref in understanding.reference_expressions:
            res_ref = cls.resolve_reference(ref, state)
            resolved_refs.append(res_ref)

        # 3. Target product resolution:
        # Check explicit entities first
        target_prod = None
        explicit_models = [e for e in understanding.entities if e.entity_type == "model" and not (e.metadata and e.metadata.get("is_negated"))]
        if explicit_models:
            from catalog.catalogue_loader import catalogue_loader
            p_data = catalogue_loader.get_by_id(explicit_models[0].normalised_id) or {}
            target_prod = SalientEntity(
                id=explicit_models[0].normalised_id,
                entity_type="printer",
                name=p_data.get("display_name") or explicit_models[0].surface_text,
                metadata=p_data,
                turn_introduced=state.turn_count,
            )
        elif resolved_refs:
            for r in resolved_refs:
                if r.resolved_entity and r.resolved_entity.entity_type == "printer":
                    target_prod = r.resolved_entity
                    break

        if not target_prod and bound_option:
            p_data = bound_option.get("product")
            p_id = bound_option.get("id") or bound_option.get("value")
            if not p_data and p_id:
                from catalog.catalogue_loader import catalogue_loader
                p_data = catalogue_loader.get_by_id(str(p_id))
            if p_data:
                target_prod = SalientEntity(
                    id=str(p_data.get("id", p_id)),
                    entity_type="printer",
                    name=p_data.get("display_name") or str(p_id),
                    metadata=p_data,
                    turn_introduced=state.turn_count,
                )

        if not target_prod and state.get_current_focus("printer"):
            text_l = understanding.raw_text.lower()
            cat_slot = understanding.slots.get("target_category")
            new_cat = cat_slot.value if cat_slot else None
            is_category_query = bool(new_cat) or any(e.entity_type == "category" for e in understanding.entities)
            is_general_discovery = any(w in text_l for w in ["do you have", "recommend", "looking for", "show me", "what printers", "what options", "options for"])
            is_company_capability = "company_capability" in understanding.ambiguities or any(p in text_l for p in ["do you supply", "do you supplay", "do you sell", "product list"])
            is_out_of_scope_or_frustrated = understanding.dialogue_act in (DialogueAct.OUT_OF_SCOPE, DialogueAct.COMPLAINT)
            
            prev_focus = state.get_current_focus("printer")
            prev_is_scanner = "scanner" in prev_focus.name.lower() or "ds-" in prev_focus.id.lower() or "12000xl" in prev_focus.id.lower()
            query_wants_printer = any(w in text_l for w in ["printer", "plotter", "print", "printing"])
            query_wants_scanner = any(w in text_l for w in ["scanner", "scanning", "scan"])
            
            hardware_mismatch = (prev_is_scanner and query_wants_printer and not query_wants_scanner) or (not prev_is_scanner and query_wants_scanner and not query_wants_printer)
            
            if is_out_of_scope_or_frustrated or is_company_capability or hardware_mismatch:
                target_prod = None
            elif understanding.intent in (Intent.PRODUCT_INFO, Intent.AVAILABILITY_OR_PRICE_POLICY, Intent.CONSUMABLES_LOOKUP):
                target_prod = prev_focus
            elif not is_category_query and not is_general_discovery and understanding.intent != Intent.RECOMMEND:
                target_prod = prev_focus

        # 4. Active consumable / item resolution:
        active_item = None
        explicit_skus = [e for e in understanding.entities if e.entity_type == "sku"]
        if explicit_skus:
            active_item = SalientEntity(
                id=explicit_skus[0].normalised_id,
                entity_type="consumable",
                name=explicit_skus[0].surface_text,
                metadata=explicit_skus[0].metadata,
                turn_introduced=state.turn_count,
            )
        elif resolved_refs:
            for r in resolved_refs:
                if r.resolved_entity:
                    if r.resolved_entity.entity_type == "consumable":
                        active_item = r.resolved_entity
                        break
                    elif understanding.intent == Intent.COMPATIBILITY_CHECK and target_prod and r.resolved_entity.id != target_prod.id:
                        active_item = r.resolved_entity
                        break

        if not active_item and state.get_current_focus("consumable"):
            active_item = state.get_current_focus("consumable")
        elif not active_item and understanding.intent == Intent.COMPATIBILITY_CHECK and target_prod:
            for ent in reversed(state.focus_stack):
                if ent.id != target_prod.id:
                    active_item = ent
                    break

        # 5. Ellipsis detection and inheritance
        is_ellipsis = any(r.reference_type == "ellipsis" for r in understanding.reference_expressions)
        if is_ellipsis and state.last_intent and understanding.intent in (Intent.OTHER, Intent.PRODUCT_INFO):
            understanding.intent = state.last_intent

        return ResolvedTurn(
            understanding=understanding,
            resolved_referents=resolved_refs,
            resolved_target_product=target_prod,
            resolved_active_item=active_item,
            is_ellipsis=is_ellipsis,
            bound_pending_option=bound_option,
        )
