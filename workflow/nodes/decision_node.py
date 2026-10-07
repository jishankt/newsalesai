"""
Decision Node for Kepler Tech SalesAI.
Evaluates deterministic 10-tier routing priority order to choose the execution path.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from agent.decision_engine import decide


class DecisionNode(BaseNode):
    name: str = "DECISION"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            und = ctx.understanding
            state = ctx.state

            # Execute deterministic 10-tier decision
            ctx.decision = decide(
                understanding=und,
                state=state,
                raw_message=ctx.normalized_message
            )

            route_name = ctx.decision.route.value if hasattr(ctx.decision.route, "value") else str(ctx.decision.route)
            ctx.target_route = route_name

            step.complete(
                summary=f"Selected Route: {route_name.upper()} ({ctx.decision.reason or 'deterministic rule'})",
                details={
                    "route": route_name,
                    "target_tool": ctx.decision.tool,
                    "tool_arguments": ctx.decision.tool_arguments,
                    "reason": ctx.decision.reason,
                }
            )
        except Exception as e:
            step.fail(str(e))
            ctx.target_route = "qualification"

        return ctx
