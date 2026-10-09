"""
State Reconciler for Kepler Tech SalesAI.

Responsibilities:
1. Applies customer corrections with strict priority.
2. Actively invalidates stale context, recommendations, and dependent evidence.
3. Flushes irrelevant category assumptions on topic switches.
4. Resolves anaphoric references ("that one", "the other model").
5. Updates question ledger and maintains single active source of truth.
"""

from typing import Dict, Any, Optional, List
import logging

from domain.canonical_turn import CanonicalTurnUnderstanding, CanonicalQuestion
from domain.conversation_state import ConversationState, CanonicalProductFocus
from conversation.question_ledger import QuestionLedger, QuestionStatus

logger = logging.getLogger("state_reconciler")


class StateReconciler:
    """Authoritative reconciler that updates ConversationState each turn."""

    @classmethod
    def reconcile(
        cls,
        understanding: CanonicalTurnUnderstanding,
        state: ConversationState,
    ) -> ConversationState:
        """
        Reconciles the customer's current turn understanding into conversation state.
        Ensures state represents the customer's CURRENT situation, not historical inertia.
        """
        # Ensure ledgers exist
        if getattr(state, "question_ledger", None) is None:
            state.question_ledger = QuestionLedger()
        if getattr(state, "goal_manager", None) is None:
            from conversation.goal_manager import GoalManager
            state.goal_manager = GoalManager()

        # ── 1. Priority Customer Corrections & Stale Invalidation ───────────
        if understanding.corrections:
            cls._apply_corrections(understanding.corrections, state)

        # ── 2. Topic Switch Invalidation ─────────────────────────────────────
        if understanding.topic_switch:
            cls._apply_topic_switch(understanding, state)

        # ── 3. Merge Changed Requirements ────────────────────────────────────
        for k, v in understanding.changed_requirements.items():
            state.requirements[k] = v
        for k, v in understanding.corrections.items():
            if k in ("application", "category", "format", "paper_size"):
                state.requirements[k] = v
        if "category" in understanding.changed_requirements and understanding.changed_requirements["category"]:
            state.category = understanding.changed_requirements["category"]
        if "category" in understanding.corrections and understanding.corrections["category"]:
            state.category = understanding.corrections["category"]

        # ── 4. Update Product Focus ──────────────────────────────────────────
        # If the customer explicitly mentioned products in the latest turn (and not a correction already handled)
        if understanding.mentioned_products and "product" not in understanding.corrections:
            new_primary = understanding.mentioned_products[0]
            # If customer mentioned a new product, update focus and invalidate conflicting single-product assumptions
            current_focus = state.get_canonical_focus_id() if hasattr(state, "get_canonical_focus_id") else None
            if current_focus != new_primary and len(understanding.mentioned_products) == 1:
                state.set_canonical_focus(new_primary, source="customer_selected")
                state.last_explicit_product_id = new_primary
                # Invalidate old product-specific candidates
                if hasattr(state, "candidate_products"):
                    state.candidate_products = [new_primary]

        # ── 5. Anaphoric Reference Resolution ────────────────────────────────
        if understanding.references and not understanding.mentioned_products:
            cls._resolve_references(understanding.references, state)

        # ── 6. Update Question Ledger with Turn's Explicit Questions ─────────
        resolved_focus = state.get_canonical_focus_id() if hasattr(state, "get_canonical_focus_id") else None
        for q in understanding.explicit_questions:
            if not understanding.mentioned_products and resolved_focus:
                q.target_product = resolved_focus
            target_prod = q.target_product or resolved_focus
            state.question_ledger.register_customer_question(
                text=q.text,
                turn_index=state.turn_count,
                target_product=target_prod,
                target_attribute=q.target_attribute,
                explicit_semantic_key=q.semantic_key,
            )

        # ── 7. Update Customer Profile & Behavior ────────────────────────────
        state.customer_behavior = understanding.customer_behavior
        state.customer_goal = understanding.primary_goal
        if understanding.customer_behavior == "FRUSTRATED":
            state.frustration_count = getattr(state, "frustration_count", 0) + 1

        return state

    @classmethod
    def _apply_corrections(cls, corrections: Dict[str, Any], state: ConversationState) -> None:
        """Applies explicit customer corrections and invalidates dependent stale evidence."""
        # Product Correction (e.g. "Actually I meant CX-02W")
        if "product" in corrections:
            prod_info = corrections["product"]
            old_prod = prod_info.get("old")
            new_prod = prod_info.get("new")
            logger.info("Applying product correction: %s -> %s", old_prod, new_prod)

            if new_prod:
                # 1. Update canonical focus
                state.set_canonical_focus(new_prod, source="customer_selected")
                state.last_explicit_product_id = new_prod
                state.active_product_id = new_prod

                # 2. Invalidate old candidates and stale recommendations
                state.candidate_products = [new_prod]
                state.displayed_product_ids = [new_prod]

                # 3. Invalidate dependent questions for old product
                if old_prod and state.question_ledger:
                    for item in state.question_ledger.items:
                        if item.target_product == old_prod and item.status == QuestionStatus.UNANSWERED:
                            item.status = QuestionStatus.SUPERSEDED

        # 1. Reset or Category Switch first (invalidate stale prior requirements)
        if corrections.get("reset_requirements") or ("category" in corrections and state.category != corrections["category"]):
            state.requirements.clear()
            state.missing_fields.clear()
            state.candidate_products.clear()
            state.active_product = None
            state.active_product_id = None
            state.canonical_focus = None
            if state.question_ledger:
                state.question_ledger.invalidate_for_topic_switch()

        if "category" in corrections:
            state.category = corrections["category"]

        # 2. Application correction
        if "application" in corrections:
            state.requirements["application"] = corrections["application"]

        # 3. Format / Size Correction
        if "format" in corrections:
            state.requirements["format"] = corrections["format"]
            state.requirements["print_width"] = corrections["format"]

    @classmethod
    def _apply_topic_switch(cls, understanding: CanonicalTurnUnderstanding, state: ConversationState) -> None:
        """Handles category or goal topic switch, ensuring zero context contamination."""
        logger.info("Handling topic switch for customer turn.")
        new_cat = understanding.changed_requirements.get("category")
        if new_cat and new_cat != state.category:
            state.category = new_cat
            cls._flush_category_requirements(state)

        state.active_product = None
        state.active_product_id = None
        state.canonical_focus = None
        state.candidate_products = []
        if state.question_ledger:
            state.question_ledger.invalidate_for_topic_switch()

    @classmethod
    def _flush_category_requirements(cls, state: ConversationState) -> None:
        """Flushes category-specific requirements that do not apply across hardware domains."""
        domain_keys = [
            "print_size", "size", "print_width", "format", "media_type",
            "roll_capacity", "cad_precision", "adf", "scanner", "speed_priority",
            "scanner_required", "scanner_integrated", "cad", "photo_form_factor",
            "daily_volume", "paper_size"
        ]
        for k in domain_keys:
            state.requirements.pop(k, None)
        # If application was category-specific (e.g. cad vs wedding), pop unless newly set
        if state.requirements.get("application") in ("cad", "cad_drawings", "office_documents"):
            state.requirements.pop("application", None)
        state.active_product = None
        state.active_product_id = None
        state.canonical_focus = None
        if hasattr(state, "candidate_products") and isinstance(state.candidate_products, list):
            state.candidate_products.clear()
        state.missing_fields.clear()
        state.qualification_complete = False

    @classmethod
    def _resolve_references(cls, references: List[str], state: ConversationState) -> None:
        """Resolves references like 'the second one', 'the other one', 'that model'."""
        comp_prods = getattr(state, "compared_product_ids", []) or getattr(state, "comparison_product_ids", []) or getattr(state, "displayed_product_ids", [])
        active_focus = state.get_canonical_focus_id() if hasattr(state, "get_canonical_focus_id") else None

        for ref in references:
            ref_l = ref.lower()
            if ref_l in ["the second one", "second one", "second printer", "second model"]:
                if len(comp_prods) >= 2:
                    state.set_canonical_focus(comp_prods[1], source="customer_selected")
                    return
            elif ref_l in ["the first one", "first one", "first printer", "first model"]:
                if len(comp_prods) >= 1:
                    state.set_canonical_focus(comp_prods[0], source="customer_selected")
                    return
            elif ref_l in ["the other one", "other printer", "other model"]:
                if len(comp_prods) >= 2:
                    # Choose the one that is not current focus
                    other = comp_prods[1] if active_focus == comp_prods[0] else comp_prods[0]
                    state.set_canonical_focus(other, source="customer_selected")
                    return
