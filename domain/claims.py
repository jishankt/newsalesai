"""
Claim-Level Mapping and Grounding Contract for Kepler Tech SalesAI.

Binds every factual statement to verified evidence in VerifiedEvidenceBundle.
Enforces the Zero-Hallucination rule: if an attribute is unverified,
the system explicitly refuses to guess from parametric memory.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal


@dataclass
class Claim:
    """Individual factual statement tied to verified evidence."""
    attribute: str
    product_id: str
    value: Any
    evidence_id: str
    verified: bool
    status: Literal["supported", "unsupported", "unknown"]
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribute": self.attribute,
            "product_id": self.product_id,
            "value": self.value,
            "evidence_id": self.evidence_id,
            "verified": self.verified,
            "status": self.status,
            "text": self.text,
        }


@dataclass
class AnswerPlan:
    """Structured plan for answering a customer turn based on verified claims."""
    target_product_id: Optional[str]
    claims: List[Claim] = field(default_factory=list)
    unverified_attributes: List[str] = field(default_factory=list)
    response_mode: str = "direct_answer"
    response_budget: Literal["SHORT", "MODERATE", "DETAILED", "CONCISE_OBJECTION", "CLOSING"] = "SHORT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_product_id": self.target_product_id,
            "claims": [c.to_dict() for c in self.claims],
            "unverified_attributes": list(self.unverified_attributes),
            "response_mode": self.response_mode,
            "response_budget": self.response_budget,
        }
