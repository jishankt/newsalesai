"""
Understand Node for Kepler Tech SalesAI.
Executes single-pass structured semantic understanding extraction.
"""

from typing import Optional
from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from nlp.llm_understanding import LLMUnderstandingEngine
from ollama_client import OllamaClient


class UnderstandNode(BaseNode):
    name: str = "UNDERSTAND"

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.understanding_engine = LLMUnderstandingEngine(ollama_client)

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            state_summary = ctx.state.to_dict() if ctx.state else {}
            recent_turns = ctx.history[-6:] if ctx.history else []

            ctx.understanding = self.understanding_engine.understand(
                customer_message=ctx.normalized_message,
                recent_turns=recent_turns,
                state_summary=state_summary,
                model=ctx.model_name,
                raw_message=ctx.raw_message,
            )

            # Update nlp_result for downstream consumption
            ctx.nlp_result["intent"] = ctx.understanding.intent.value if hasattr(ctx.understanding.intent, "value") else str(ctx.understanding.intent)
            ctx.nlp_result["dialogue_act"] = ctx.understanding.dialogue_act.value if hasattr(ctx.understanding.dialogue_act, "value") else str(ctx.understanding.dialogue_act)

            step.complete(
                summary=f"Intent: {ctx.nlp_result['intent']} | Act: {ctx.nlp_result['dialogue_act']}",
                details={
                    "intent": ctx.nlp_result["intent"],
                    "dialogue_act": ctx.nlp_result["dialogue_act"],
                    "confidence": ctx.understanding.confidence,
                    "requirements": ctx.understanding.requirements,
                    "corrections": ctx.understanding.corrections,
                    "questions": ctx.understanding.questions,
                }
            )
        except Exception as e:
            step.fail(str(e))

        return ctx
