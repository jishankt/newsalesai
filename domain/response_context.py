"""
Canonical Response Context and Verified Evidence Bundle for Kepler Tech SalesAI.

Defines the structured contract passed from the deterministic decision & retrieval
pipeline to the Grounded LLM Response Composer.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class FieldFact:
    """
    Field-aware verified fact for a specific product and attribute.
    Status must be strictly one of: 'supported', 'unsupported', or 'unknown'.
    """
    product_id: str
    attribute: str
    status: str  # "supported" | "unsupported" | "unknown"
    product_name: str = ""
    value: Any = None
    source: str = "catalog"
    display_claim: str = ""
    fact: str = ""

    def __post_init__(self):
        if not self.product_name:
            self.product_name = self.product_id
        if self.fact and not self.display_claim:
            self.display_claim = self.fact
        elif self.display_claim and not self.fact:
            self.fact = self.display_claim

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "attribute": self.attribute,
            "status": self.status,
            "value": self.value,
            "source": self.source,
            "display_claim": self.display_claim,
        }


@dataclass
class AnswerPlanItem:
    """
    Single unit of a customer's inquiry to be answered.
    """
    attribute: str
    item_id: str = ""
    question_text: str = ""
    target_product_id: Optional[str] = None
    target_product_name: Optional[str] = None
    configuration: Optional[str] = None
    status: str = "supported"  # "supported" | "unsupported" | "unknown" | "needs_clarification"
    evidence_value: Any = None
    evidence_source: Optional[str] = None
    factual_claim: Optional[str] = None
    clarification_prompt: Optional[str] = None
    product_id: Optional[str] = None
    verified_fact: Optional[str] = None

    def __post_init__(self):
        if not self.item_id:
            self.item_id = self.attribute
        if self.product_id and not self.target_product_id:
            self.target_product_id = self.product_id
        if self.verified_fact and not self.factual_claim:
            self.factual_claim = self.verified_fact
        elif self.factual_claim and not self.verified_fact:
            self.verified_fact = self.factual_claim

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "question_text": self.question_text,
            "attribute": self.attribute,
            "target_product_id": self.target_product_id,
            "target_product_name": self.target_product_name,
            "configuration": self.configuration,
            "status": self.status,
            "evidence_value": self.evidence_value,
            "evidence_source": self.evidence_source,
            "factual_claim": self.factual_claim,
            "clarification_prompt": self.clarification_prompt,
        }


@dataclass
class AnswerPlan:
    """
    Deterministic plan for a conversational turn.
    """
    items: List[AnswerPlanItem] = field(default_factory=list)
    resolved_products: List[Dict[str, Any]] = field(default_factory=list)
    displayed_product_order: List[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    overall_goal: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [it.to_dict() for it in self.items],
            "resolved_product_ids": [p.get("id") for p in self.resolved_products if isinstance(p, dict)],
            "displayed_product_order": list(self.displayed_product_order),
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "overall_goal": self.overall_goal,
        }

    def render_deterministic_answer(self) -> str:
        """
        Produces a concise, verified, conversational answer directly from plan items.
        Used as fail-closed fallback when LLM is unavailable or fails validation.
        """
        if self.needs_clarification and self.clarification_question:
            return self.clarification_question

        if not self.items:
            return ""

        claims = [it.factual_claim for it in self.items if it.factual_claim]
        if not claims:
            return ""

        if len(claims) == 1:
            return claims[0]

        prod_name = self.items[0].target_product_name or "this model"
        lines = [f"Here is the verified information for the **{prod_name}**:"]
        for it in self.items:
            if it.factual_claim:
                lines.append(f"• {it.factual_claim}")
        return "\n".join(lines)


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
    field_facts: Dict[str, Dict[str, FieldFact]] = field(default_factory=dict)
    answer_plan: Optional[AnswerPlan] = None
    displayed_product_order: List[str] = field(default_factory=list)

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
        if self.field_facts:
            if isinstance(self.field_facts, list):
                ff_dict = {}
                for f in self.field_facts:
                    pid = f.product_id
                    attr = f.attribute
                    if pid not in ff_dict:
                        ff_dict[pid] = {}
                    ff_dict[pid][attr] = f.to_dict() if hasattr(f, "to_dict") else dict(f)
                data["field_facts"] = ff_dict
            else:
                data["field_facts"] = {
                    pid: {attr: fact.to_dict() if hasattr(fact, "to_dict") else dict(fact) for attr, fact in facts.items()}
                    for pid, facts in self.field_facts.items()
                }
        if self.answer_plan:
            data["answer_plan"] = self.answer_plan.to_dict()
        if self.displayed_product_order:
            data["displayed_product_order"] = list(self.displayed_product_order)
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
    answer_plan: Optional[AnswerPlan] = None
    response_goal: str = ""
    deterministic_draft: str = ""
    allowed_followup: Optional[str] = None
    needs_naturalization: bool = True
    recent_history: List[Dict[str, str]] = field(default_factory=list)
    customer_name: Optional[str] = None
    expected_length: str = "dynamic"  # "short", "medium", "detailed", "dynamic"
    customer_goal: str = ""
    requested_attributes: List[str] = field(default_factory=list)
    requirement_updates: Dict[str, Any] = field(default_factory=dict)
    rejected_products: List[str] = field(default_factory=list)
    answer_coverage: Dict[str, bool] = field(default_factory=dict)
    conversation_stage: str = "open"
    displayed_product_order: List[str] = field(default_factory=list)

