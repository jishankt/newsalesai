"""
Base Workflow Node Interface for Kepler Tech SalesAI.
"""

from abc import ABC, abstractmethod
from typing import Optional
from workflow.context import WorkflowContext


class BaseNode(ABC):
    """Abstract interface for all deterministic and AI workflow nodes."""

    name: str = "BaseNode"

    @abstractmethod
    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        """Processes the context and returns the updated context."""
        pass
