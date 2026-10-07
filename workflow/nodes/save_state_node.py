"""
Save State Node for Kepler Tech SalesAI.
Persists conversation state, updates turn counter, and saves history.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext


class SaveStateNode(BaseNode):
    name: str = "SAVE_STATE"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        state = ctx.state

        if not state:
            step.skip("No state object to persist")
            return ctx

        try:
            # 1. Update state attributes
            state.last_assistant_response = ctx.response_text
            state.increment_turn()

            if ctx.product_cards:
                new_ids = [c["id"] for c in ctx.product_cards if isinstance(c, dict) and c.get("id")]
                for nid in new_ids:
                    if nid not in state.displayed_product_ids:
                        state.displayed_product_ids.append(nid)

            # 2. Append history if enabled
            if hasattr(state, "append_turn"):
                state.append_turn(ctx.raw_message, ctx.response_text)

            step.complete(
                summary=f"Saved state for session '{state.session_id}' (Turn {state.turn_count})",
                details={
                    "turn_count": state.turn_count,
                    "displayed_product_ids": state.displayed_product_ids,
                    "requirements": dict(state.requirements),
                }
            )
        except Exception as e:
            step.fail(str(e))

        return ctx
