"""
Response Node for Kepler Tech SalesAI.
Composes conversational grounded responses using local LLM synthesis or verified answer plan.
"""

from typing import Optional
from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from agent.response_composer import ResponseComposer
from ollama_client import OllamaClient


class ResponseNode(BaseNode):
    name: str = "RESPONSE_AI"

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.response_composer = ResponseComposer(ollama_client)

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)

        # If a deterministic intercept already produced a response, keep it
        if ctx.response_text:
            step.complete(summary="Using existing deterministic response")
            return ctx

        try:
            if ctx.response_context:
                reply = self.response_composer.compose(
                    context=ctx.response_context,
                    model_name=ctx.model_name
                )
                if reply:
                    ctx.response_text = reply
                    ctx.source = "route:llm_composed" if self.response_composer.last_composition_succeeded else "route:verified_plan"
                elif ctx.evidence and ctx.evidence.answer_plan:
                    ctx.response_text = ctx.evidence.answer_plan.render_deterministic_answer()
                    ctx.source = "route:answer_plan_fallback"

            if not ctx.response_text:
                is_unclear = bool(
                    ctx.understanding
                    and (
                        getattr(ctx.understanding, "intent", None) in ("unclear", "out_of_scope")
                        or getattr(getattr(ctx.understanding, "intent", None), "value", "") in ("unclear", "out_of_scope")
                    )
                )
                prefix = "Could you tell me that again? " if is_unclear else ""
                ctx.response_text = f"{prefix}I am ready to assist you with our official range of printers, plotters, and document scanners. Which specifications or products would you like to explore?"
                ctx.source = "route:default_greeting"

            step.complete(
                summary=f"Composed {len(ctx.response_text)} chars (Source: {ctx.source})",
                details={"source": ctx.source, "length": len(ctx.response_text)}
            )
        except Exception as e:
            step.fail(str(e))
            if not ctx.response_text:
                ctx.response_text = "Our technical catalog is available to help find the right printing solution. How can I assist you with your requirements?"
                ctx.source = "route:exception_fallback"

        return ctx
