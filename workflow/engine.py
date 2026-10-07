"""
Workflow Engine for Kepler Tech SalesAI.
Orchestrates the sequential n8n-style node pipeline for conversational turns.
"""

import logging
from typing import List, Optional, Dict, Any

from workflow.context import WorkflowContext
from workflow.nodes.base_node import BaseNode
from workflow.nodes.normalize_node import NormalizeNode
from workflow.nodes.load_state_node import LoadStateNode
from workflow.nodes.understand_node import UnderstandNode
from workflow.nodes.resolve_context_node import ResolveContextNode
from workflow.nodes.update_state_node import UpdateStateNode
from workflow.nodes.decision_node import DecisionNode
from workflow.nodes.execute_node import ExecuteNode
from workflow.nodes.evidence_node import EvidenceNode
from workflow.nodes.response_node import ResponseNode
from workflow.nodes.validate_node import ValidateNode
from workflow.nodes.save_state_node import SaveStateNode
from domain.conversation_state import ConversationState
from ollama_client import OllamaClient

logger = logging.getLogger("workflow.engine")


class WorkflowEngine:
    """Sequential n8n-style workflow engine executing modular pipeline nodes."""

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        nodes: Optional[List[BaseNode]] = None,
    ):
        if isinstance(ollama_client, list):
            nodes = ollama_client
            ollama_client = None

        self.ollama_client = ollama_client

        if nodes is not None:
            self.nodes = nodes
        else:
            # Default standard 11-step pipeline
            self.nodes = [
                NormalizeNode(),
                LoadStateNode(),
                UnderstandNode(ollama_client=self.ollama_client),
                ResolveContextNode(),
                UpdateStateNode(),
                DecisionNode(),
                ExecuteNode(),
                EvidenceNode(),
                ResponseNode(ollama_client=self.ollama_client),
                ValidateNode(),
                SaveStateNode(),
            ]

    def run(
        self,
        raw_message: str,
        session_id: str = "default-session",
        history: Optional[List[Dict[str, str]]] = None,
        state: Optional[ConversationState] = None,
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the entire pipeline sequentially for a user turn."""
        ctx = WorkflowContext(
            raw_message=raw_message,
            session_id=session_id,
            history=history or [],
            state=state,
            model_name=model_name,
        )

        for node in self.nodes:
            if ctx.aborted and not isinstance(node, (ValidateNode, SaveStateNode)):
                # If pipeline aborted early, skip ahead to validation and persistence
                continue

            try:
                ctx = node.execute(ctx)
            except Exception as e:
                logger.error(f"Error executing workflow node {node.name}: {e}", exc_info=True)
                ctx.trace.record_step(node.name, summary=f"Exception: {e}", status="FAILED")

        return ctx.to_api_response()
