"""
Load State Node for Kepler Tech SalesAI.
Retrieves or initializes the ConversationState for the current session.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from domain.conversation_state import ConversationState


class LoadStateNode(BaseNode):
    name: str = "LOAD_STATE"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            if ctx.state is None:
                ctx.state = ConversationState(session_id=ctx.session_id)

            if not ctx.history and hasattr(ctx.state, "history_turns"):
                ctx.history = ctx.state.history_turns

            step.complete(
                summary=f"Loaded session '{ctx.session_id}' (Turn {ctx.state.turn_count})",
                details={
                    "stage": ctx.state.stage,
                    "category": ctx.state.category,
                    "active_requirements": ctx.state.requirements,
                    "displayed_products": ctx.state.displayed_product_ids,
                }
            )
        except Exception as e:
            step.fail(str(e))
            if ctx.state is None:
                ctx.state = ConversationState(session_id=ctx.session_id)

        return ctx
