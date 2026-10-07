"""
Evidence Node for Kepler Tech SalesAI.
Aggregates ground-truth facts into a VerifiedEvidenceBundle with strict 3-valued truth logic.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from agent.evidence_planner import EvidencePlanner
from domain.response_context import ResponseContext


class EvidenceNode(BaseNode):
    name: str = "VERIFIED_EVIDENCE"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            # Plan and compile verified evidence
            bundle = EvidencePlanner.plan_and_retrieve(
                user_message=ctx.normalized_message,
                state=ctx.state,
                understanding=ctx.understanding,
                product_cards=ctx.product_cards,
                consumable_cards=ctx.consumable_cards,
                nlp_result=ctx.nlp_result,
            )
            ctx.evidence = bundle

            # Build ResponseContext for composition
            ctx.response_context = ResponseContext(
                original_message=ctx.raw_message,
                normalized_message=ctx.normalized_message,
                intent=ctx.nlp_result.get("intent", "product_question"),
                dialogue_act=ctx.nlp_result.get("dialogue_act", "informing"),
                verified_evidence=bundle,
                answer_plan=bundle.answer_plan,
                conversation_state=ctx.state.to_dict() if ctx.state else {},
                customer_questions=ctx.understanding.questions if ctx.understanding else [],
            )

            fact_count = len(bundle.facts) if hasattr(bundle, "facts") else 0
            step.complete(
                summary=f"Compiled verified evidence ({fact_count} field facts bound)",
                details={"facts_count": fact_count, "target_route": ctx.target_route}
            )
        except Exception as e:
            step.fail(str(e))

        return ctx
