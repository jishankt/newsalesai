"""
Resolve Context Node for Kepler Tech SalesAI.
Resolves anaphora, ordinal pointers ('first one', 'second one'), pronouns ('it', 'that'),
and context references against the conversation history and displayed cards.
"""

import re
from typing import Dict, Any, List
from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from conversation.contextual_slot_resolver import ContextualSlotResolver


class ResolveContextNode(BaseNode):
    name: str = "RESOLVE_CONTEXT"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        resolved: Dict[str, Any] = {}
        msg_l = (ctx.normalized_message or "").lower().strip()
        state = ctx.state

        try:
            # 1. Resolve awaiting field slots via ContextualSlotResolver
            if state and state.awaiting_field:
                req_updates, corrs = ContextualSlotResolver.resolve(
                    text=ctx.normalized_message,
                    awaiting_field=state.awaiting_field,
                    category=state.category,
                    requirements=state.requirements,
                    active_chips=state.active_chips if hasattr(state, "active_chips") else []
                )
                if req_updates or corrs:
                    resolved["slot_updates"] = req_updates
                    resolved["slot_corrections"] = corrs

            # 2. Resolve pronouns and ordinal pointers against displayed products
            displayed = state.displayed_product_ids if state else []
            target_ids: List[str] = []

            # Ordinal pointers: "first one", "1st one", "option 1"
            if re.search(r"\b(?:first|1st|first\s+one|option\s+1|#1|^1$)\b", msg_l):
                if len(displayed) >= 1:
                    target_ids.append(displayed[0])
            elif re.search(r"\b(?:second|2nd|second\s+one|option\s+2|#2|^2$)\b", msg_l):
                if len(displayed) >= 2:
                    target_ids.append(displayed[1])
            elif re.search(r"\b(?:third|3rd|third\s+one|option\s+3|#3|^3$)\b", msg_l):
                if len(displayed) >= 3:
                    target_ids.append(displayed[2])

            # Collective pointers: "both", "these", "all of them"
            if re.search(r"\b(?:both|these|all|both\s+of\s+them|these\s+two)\b", msg_l):
                if displayed:
                    target_ids.extend(displayed)

            # Singular anaphora: "it", "this", "that"
            if not target_ids and re.search(r"\b(?:it|this|that|the\s+printer|the\s+model)\b", msg_l):
                if state:
                    fallback_id = state.active_product_id or state.last_explicit_product_id or (displayed[0] if displayed else None)
                    if fallback_id:
                        target_ids.append(fallback_id)

            if target_ids:
                # Deduplicate while preserving order
                unique_targets = list(dict.fromkeys(target_ids))
                resolved["target_products"] = unique_targets
                if len(unique_targets) == 1 and state:
                    state.active_product_id = unique_targets[0]

            ctx.resolved_references = resolved

            step.complete(
                summary=f"Resolved {len(target_ids)} product reference(s)" if target_ids else "No anaphora reference",
                details=resolved
            )
        except Exception as e:
            step.fail(str(e))

        return ctx
