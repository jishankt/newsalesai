"""
Normalize Node for Kepler Tech SalesAI.
Normalizes customer input, corrects typos, and extracts standard size tokens.
"""

from workflow.nodes.base_node import BaseNode
from workflow.context import WorkflowContext
from nlp.normalizer import normalize_text


class NormalizeNode(BaseNode):
    name: str = "NORMALIZE"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        step = ctx.trace.start_step(self.name)
        try:
            norm_result = normalize_text(ctx.raw_message)
            ctx.normalized_message = norm_result["normalized_text"]

            ctx.nlp_result = {
                "raw_text": norm_result["raw_text"],
                "clean_text": norm_result["clean_text"],
                "normalized_text": ctx.normalized_message,
                "corrections": norm_result["corrections_applied"],
                "intent": "",
                "brands": [],
                "categories": [],
                "models": [],
                "sizes": norm_result["canonical_sizes"],
            }

            step.complete(
                summary=f"Cleaned message ({len(norm_result['corrections_applied'])} corrections)",
                details={
                    "normalized": ctx.normalized_message,
                    "sizes": norm_result["canonical_sizes"],
                }
            )
        except Exception as e:
            step.fail(str(e))
            ctx.normalized_message = ctx.raw_message.strip()

        return ctx
