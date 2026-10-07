"""
Update State Node for Kepler Tech SalesAI.
Deterministically updates conversation requirements, slots, and corrections.
Enforces strict overwrite rules (e.g., 'actually no scanner' -> scanner_required=False).
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from conversation.normalizer import extract_deterministic_requirements


class UpdateStateNode(BaseNode):
    name: str = "UPDATE_STATE"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        state = ctx.state
        if not state:
            step.skip("No conversation state attached")
            return ctx

        applied_updates = {}
        applied_corrections = {}

        try:
            # 1. Deterministic requirements & corrections extraction
            det_reqs, det_corrs = extract_deterministic_requirements(
                ctx.normalized_message,
                state.category,
                state.awaiting_field
            )
            for k, v in det_reqs.items():
                state.requirements[k] = v
                applied_updates[k] = v
            for k, v in det_corrs.items():
                state.requirements[k] = v
                applied_corrections[k] = v

            # 2. Apply resolved slots from contextual resolver
            slot_updates = ctx.resolved_references.get("slot_updates", {})
            for k, v in slot_updates.items():
                state.requirements[k] = v
                applied_updates[k] = v

            slot_corrs = ctx.resolved_references.get("slot_corrections", {})
            for k, v in slot_corrs.items():
                state.requirements[k] = v
                applied_corrections[k] = v

            # 2. Apply structured understanding requirements & corrections
            und = ctx.understanding
            if und:
                # Direct requirements
                for k, v in (und.requirements or {}).items():
                    if k not in state.requirements or state.requirements[k] != v:
                        state.requirements[k] = v
                        applied_updates[k] = v

                # Explicit corrections (strict overwrite)
                for k, v in (und.corrections or {}).items():
                    state.requirements[k] = v
                    applied_corrections[k] = v

                # Handle negations (e.g., scanner_required = False)
                if hasattr(und, "negations") and und.negations:
                    for k, v in und.negations.items():
                        state.requirements[k] = v
                        applied_corrections[k] = v

                # Handle topic switches
                if und.topic_switch:
                    state.reset_category(None)
                    state.requirements.clear()
                    state.stage = "open"
                    applied_updates["topic_reset"] = True

            # 3. Handle active/target product pointer
            target_products = ctx.resolved_references.get("target_products", [])
            if len(target_products) == 1:
                state.active_product_id = target_products[0]
                state.last_explicit_product_id = target_products[0]

            step.complete(
                summary=f"Updated {len(applied_updates)} slots, {len(applied_corrections)} corrections",
                details={
                    "applied_updates": applied_updates,
                    "applied_corrections": applied_corrections,
                    "current_requirements": dict(state.requirements),
                    "active_product_id": state.active_product_id,
                }
            )
        except Exception as e:
            step.fail(str(e))

        return ctx
