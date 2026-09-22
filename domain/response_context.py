"""
Canonical Response Context and Verified Evidence Bundle for Kepler Tech SalesAI.

Defines the structured contract passed from the deterministic decision & retrieval
pipeline to the Grounded LLM Response Composer.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class VerifiedEvidenceBundle:
    """
    Strict container for all verified, deterministic facts known to the system.
    The LLM composer is strictly forbidden from stating product claims outside this bundle.
    """
    active_product: Optional[Dict[str, Any]] = None
    candidate_products: List[Dict[str, Any]] = field(default_factory=list)
    specifications: Dict[str, Any] = field(default_factory=dict)
    comparison: Optional[Dict[str, Any]] = None
    consumables: List[Dict[str, Any]] = field(default_factory=list)
    customer_requirements: Dict[str, Any] = field(default_factory=dict)
    qualification: Dict[str, Any] = field(default_factory=dict)
    direct_facts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts bundle to clean dictionary suitable for prompt serialization."""
        data: Dict[str, Any] = {}
        if self.active_product:
            data["active_product"] = {
                "id": self.active_product.get("id"),
                "name": self.active_product.get("display_name") or self.active_product.get("model") or self.active_product.get("name"),
                "brand": self.active_product.get("brand"),
                "category": self.active_product.get("category"),
                "width": self.active_product.get("width") or self.active_product.get("print_width"),
                "speed": self.active_product.get("speed"),
                "technology": self.active_product.get("technology") or self.active_product.get("ink_technology"),
                "functions": self.active_product.get("functions"),
                "key_features": self.active_product.get("key_features", []),
                "summary": self.active_product.get("summary") or self.active_product.get("description", "")[:250],
            }
        if self.candidate_products:
            data["candidate_products"] = [
                {
                    "id": p.get("id"),
                    "name": p.get("display_name") or p.get("model") or p.get("name"),
                    "brand": p.get("brand"),
                    "width": p.get("width") or p.get("print_width"),
                    "speed": p.get("speed"),
                    "technology": p.get("technology") or p.get("ink_technology"),
                    "functions": p.get("functions"),
                    "match_reasons": p.get("match_reasons", []),
                }
                for p in self.candidate_products[:3]
            ]
        if self.specifications:
            data["specifications"] = self.specifications
        if self.comparison:
            data["comparison"] = self.comparison
        if self.consumables:
            data["consumables"] = [
                {
                    "sku": c.get("sku") or c.get("part_number"),
                    "name": c.get("name") or c.get("display_name"),
                    "type": c.get("type") or c.get("category"),
                    "color": c.get("color"),
                    "capacity": c.get("capacity"),
                }
                for c in self.consumables[:8]
            ]
        if self.customer_requirements:
            data["customer_requirements"] = self.customer_requirements
        if self.qualification:
            data["qualification"] = self.qualification
        if self.direct_facts:
            data["direct_facts"] = self.direct_facts
        return data


@dataclass
class ResponseContext:
    """
    Canonical context object holding all conversational, state, evidence, and draft information
    required by the Grounded LLM Response Composer.
    """
    original_message: str
    normalized_message: str
    intent: str
    dialogue_act: str = "general"
    resolved_references: Dict[str, str] = field(default_factory=dict)
    conversation_state: Dict[str, Any] = field(default_factory=dict)
    customer_questions: List[str] = field(default_factory=list)
    verified_evidence: VerifiedEvidenceBundle = field(default_factory=VerifiedEvidenceBundle)
    response_goal: str = ""
    deterministic_draft: str = ""
    allowed_followup: Optional[str] = None
    needs_naturalization: bool = True
    recent_history: List[Dict[str, str]] = field(default_factory=list)
    customer_name: Optional[str] = None
    expected_length: str = "dynamic"  # "short", "medium", "detailed", "dynamic"
