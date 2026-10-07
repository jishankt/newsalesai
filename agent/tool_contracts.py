"""
Unified Tool Contracts for Kepler Tech SalesAI.

Defines standard schemas for all catalog, specification, media, and pricing lookups.
Differentiates SUCCESS, NO_MATCH, AMBIGUOUS, and ERROR to prevent silent failures.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


class ToolStatus(str, Enum):
    SUCCESS = "success"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass
class ToolResult:
    """Standardized response from any system tool."""
    status: ToolStatus = ToolStatus.SUCCESS
    data: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    next_action: Optional[str] = None
    error_message: Optional[str] = None

    def is_success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    def is_no_match(self) -> bool:
        return self.status == ToolStatus.NO_MATCH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "data": self.data,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "next_action": self.next_action,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolResult":
        st_val = d.get("status", "success")
        try:
            st = ToolStatus(st_val)
        except ValueError:
            st = ToolStatus.SUCCESS
        return cls(
            status=st,
            data=dict(d.get("data") or {}),
            evidence=list(d.get("evidence") or []),
            confidence=float(d.get("confidence", 1.0)),
            next_action=d.get("next_action"),
            error_message=d.get("error_message"),
        )
