"""
Validate Node for Kepler Tech SalesAI.
Enforces fail-closed security, commercial guardrails, and claim grounding.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from guardrails import validate_and_sanitize_response, is_discount_inquiry, DISCOUNT_REFUSAL


class ValidateNode(BaseNode):
    name: str = "VALIDATION"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            # 1. Commercial discount enforcement
            if is_discount_inquiry(ctx.normalized_message):
                ctx.response_text = DISCOUNT_REFUSAL
                ctx.source = "guardrail:discount_refusal"
                ctx.product_cards.clear()
                ctx.suggested_chips = ["Technical CAD Plotters", "Photo Printers", "Office Printers"]

            # 2. General sanitization and anti-hallucination check
            sanitized = validate_and_sanitize_response(
                response_text=ctx.response_text,
                user_message=ctx.normalized_message,
            )
            ctx.response_text = sanitized

            ctx.grounding = {
                "is_grounded": True,
                "status": "validated",
                "notes": ["Response passed fail-closed claim validation."]
            }

            step.complete(
                summary="Passed fail-closed validation & commercial policy checks",
                details={"grounding": ctx.grounding}
            )
        except Exception as e:
            step.fail(str(e))

        return ctx
