"""
Decision Node for Kepler Tech SalesAI.

Uses the canonical SalesConsultantAgent as the sole authoritative decision maker,
retiring independent legacy routing conflicts.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from agent.sales_consultant_agent import SalesConsultantAgent, AgentAction, AgentDecision
from domain.conversation_types import RouteDecision, RouteName
from domain.canonical_turn import extract_canonical_turn


class DecisionNode(BaseNode):
    name: str = "DECISION"

    def __init__(self):
        super().__init__()
        self.agent = SalesConsultantAgent()

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            state = ctx.state
            raw_msg = ctx.raw_message or ctx.normalized_message

            # 1. Canonical Turn Understanding
            canonical_turn = extract_canonical_turn(raw_msg, ctx.normalized_message, state)
            ctx.canonical_turn = canonical_turn

            # 2. Reconcile state
            from agent.state_reconciler import StateReconciler
            state = StateReconciler.reconcile(canonical_turn, state)
            ctx.state = state

            # 3. Canonical SalesConsultantAgent Decision
            agent_decision: AgentDecision = self.agent.plan(
                understanding=canonical_turn,
                state=state,
            )
            ctx.agent_decision = agent_decision

            # 4. Map AgentAction to RouteDecision for backward-compatible downstream nodes
            route_map = {
                AgentAction.ANSWER: RouteName.PRODUCT,
                AgentAction.RETRIEVE: RouteName.PRODUCT,
                AgentAction.COMPARE: RouteName.COMPARISON,
                AgentAction.RECOMMEND: RouteName.PRODUCT,
                AgentAction.ASK_CLARIFICATION: RouteName.QUALIFICATION,
                AgentAction.HANDLE_OBJECTION: RouteName.PRODUCT,
                AgentAction.CONFIRM: RouteName.PRODUCT,
                AgentAction.HANDOFF: RouteName.SUPPORT,
                AgentAction.CLOSE: RouteName.SOCIAL,
            }
            target_route_name = route_map.get(agent_decision.action, RouteName.PRODUCT)
            target_tool = agent_decision.required_tools[0] if agent_decision.required_tools else None

            ctx.decision = RouteDecision(
                route=target_route_name,
                tool=target_tool,
                tool_arguments={"product_id": agent_decision.target_product} if agent_decision.target_product else {},
                reason=agent_decision.reason,
            )
            ctx.target_route = target_route_name.value

            step.complete(
                summary=f"SalesConsultantAgent Action: {agent_decision.action.value} ({agent_decision.reason})",
                details=agent_decision.to_dict()
            )
        except Exception as e:
            step.fail(str(e))
            ctx.target_route = "qualification"

        return ctx
