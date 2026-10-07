"""
Workflow Context for Kepler Tech SalesAI.
Carries all state, understanding, decisions, evidence, and response payloads across the pipeline.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time

from domain.conversation_state import ConversationState
from domain.conversation_types import (
    LLMUnderstanding,
    RouteDecision,
    RouteResult,
    RouteName,
    Intent,
    DialogueAct,
)
from domain.response_context import VerifiedEvidenceBundle, ResponseContext
from workflow.trace import ExecutionTrace


@dataclass
class WorkflowContext:
    # 1. Inputs
    raw_message: str
    session_id: str = "default-session"
    history: List[Dict[str, str]] = field(default_factory=list)
    model_name: Optional[str] = None
    start_time: float = field(default_factory=time.time)

    # 2. Text Processing & State
    normalized_message: str = ""
    state: Optional[ConversationState] = None
    nlp_result: Dict[str, Any] = field(default_factory=dict)

    # 3. Intelligence & Extraction
    understanding: Optional[LLMUnderstanding] = None
    resolved_references: Dict[str, Any] = field(default_factory=dict)

    # 4. Routing & Decision
    decision: Optional[RouteDecision] = None
    target_route: Optional[str] = None

    # 5. Tool Execution & Evidence
    tool_outputs: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Optional[VerifiedEvidenceBundle] = None
    response_context: Optional[ResponseContext] = None

    # 6. Response Construction & Cards
    response_text: str = ""
    source: str = "workflow:default"
    product_cards: List[Dict[str, Any]] = field(default_factory=list)
    consumable_cards: List[Dict[str, Any]] = field(default_factory=list)
    suggested_chips: List[str] = field(default_factory=list)
    grounding: Dict[str, Any] = field(default_factory=lambda: {"is_grounded": True, "notes": []})
    active_agent: str = "Sales Assistant"

    # 7. Pipeline Control & Observability
    trace: ExecutionTrace = field(default_factory=ExecutionTrace)
    aborted: bool = False
    abort_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def abort(self, reason: str = ""):
        self.aborted = True
        self.abort_reason = reason

    def to_api_response(self) -> Dict[str, Any]:
        """Formats the context into the exact dictionary required by app.py and tests."""
        latency_ms = int((time.time() - self.start_time) * 1000)
        self.trace.finalize()

        return {
            "reply": self.response_text,
            "message": self.response_text,
            "llm_generated_message": self.response_text,
            "is_llm_generated": bool(self.source and "llm" in self.source.lower()),
            "source": self.source,
            "product_cards": self.product_cards,
            "cards": self.product_cards,  # Alias
            "consumable_cards": self.consumable_cards,
            "suggested_chips": self.suggested_chips,
            "grounding": self.grounding,
            "nlp": self.nlp_result,
            "state": self.state,
            "retrieved_items": [c.get("id") or c.get("sku") for c in self.product_cards if isinstance(c, dict)],
            "active_agent": self.active_agent,
            "latency_ms": latency_ms,
            "execution_trace": self.trace.to_list(),
            "trace_summary": self.trace.render_ascii(),
            "ascii_trace": self.trace.render_ascii(),
        }
