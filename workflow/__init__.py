"""
Workflow Layer Package for Kepler Tech SalesAI.
Provides n8n-style modular orchestration, shared context, and step-by-step execution tracing.
"""

from workflow.context import WorkflowContext
from workflow.trace import ExecutionTrace, TraceStep
from workflow.engine import WorkflowEngine
from workflow.nodes import (
    BaseNode,
    NormalizeNode,
    LoadStateNode,
    UnderstandNode,
    ResolveContextNode,
    UpdateStateNode,
    DecisionNode,
    ExecuteNode,
    EvidenceNode,
    ResponseNode,
    ValidateNode,
    SaveStateNode,
)

__all__ = [
    "WorkflowContext",
    "ExecutionTrace",
    "TraceStep",
    "WorkflowEngine",
    "BaseNode",
    "NormalizeNode",
    "LoadStateNode",
    "UnderstandNode",
    "ResolveContextNode",
    "UpdateStateNode",
    "DecisionNode",
    "ExecuteNode",
    "EvidenceNode",
    "ResponseNode",
    "ValidateNode",
    "SaveStateNode",
]
