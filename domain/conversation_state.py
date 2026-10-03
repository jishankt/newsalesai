




"""
Enhanced Conversation State for Kepler Tech Conversational AI.
Tracks category, subcategory, requirements, missing fields, qualification status,
displayed product IDs, and ensures strict state preservation and correction handling.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class ConversationState:
    """Complete conversation state that preserves customer memory and qualification requirements."""
    session_id: str

    # ── Customer Memory ──────────────────────────────────────────────────
    customer_name: Optional[str] = None
    customer_id: Optional[str] = None
    lead_prompt_status: Optional[str] = None
    customer_phone_or_email: Optional[str] = None
    preferred_language: str = "en"

    # ── Conversation Control ─────────────────────────────────────────────
    stage: str = "open"  # open | qualifying | recommending | comparing | consumables | supporting | closing
    active_route: Optional[str] = None
    last_intent: Optional[str] = None
    last_dialogue_act: Optional[str] = None
    last_assistant_response: Optional[str] = None
    pending_question: Optional[str] = None
    pending_field: Optional[str] = None
    interrupted_field: Optional[str] = None
    frustration_count: int = 0

    # ── Qualification & Product Memory ───────────────────────────────────
    category: Optional[str] = None  # office_printer | technical_large_format | photography_large_format | citizen_photo
    subcategory: Optional[str] = None
    requirements: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    qualification_complete: bool = False
    results_loaded: bool = False
    matched_product_ids: List[str] = field(default_factory=list)
    displayed_product_ids: List[str] = field(default_factory=list)
    selected_product_id: Optional[str] = None
    comparison_product_ids: List[str] = field(default_factory=list)
    catalogue_version: str = "41_approved_v1"

    # ── Active Product Context ───────────────────────────────────────────
    candidate_products: List[Dict[str, Any]] = field(default_factory=list)
    active_product: Optional[Dict[str, Any]] = None
    active_product_id: Optional[str] = None
    last_explicit_product_id: Optional[str] = None
    compared_product_ids: List[str] = field(default_factory=list)
    active_printer_for_consumables: Optional[str] = None
    requested_ink_color: Optional[str] = None
    active_consumable: Optional[Dict[str, Any]] = None
    active_consumables: List[Dict[str, Any]] = field(default_factory=list)

    # ── Operational ──────────────────────────────────────────────────────
    awaiting_field: Optional[str] = None
    pending_disambiguation_model: Optional[str] = None
    unresolved_field_turns: int = 0
    last_suggested_chips: List[str] = field(default_factory=list)
    history_turns: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    state_version: int = 3
    # ── Template Variety Control ─────────────────────────────────────────
    last_opener_index: Optional[int] = None
    last_pricing_index: Optional[int] = None

    # ── Live Sales Agent & Handover Control ──────────────────────────────
    human_agent_active: bool = False
    human_agent_id: Optional[str] = None
    human_agent_name: Optional[str] = None
    handover_triggered: bool = False
    handover_reason: Optional[str] = None
    handover_timestamp: Optional[float] = None
    pending_agent_messages: List[Dict[str, Any]] = field(default_factory=list)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict. Backward-compatible with original CanonicalState."""
        return {
            "session_id": self.session_id,
            "customer_name": self.customer_name,
            "customer_id": self.customer_id,
            "lead_prompt_status": self.lead_prompt_status,
            "customer_phone_or_email": self.customer_phone_or_email,
            "preferred_language": self.preferred_language,
            "stage": self.stage,
            "active_route": self.active_route,
            "last_intent": self.last_intent,
            "last_dialogue_act": self.last_dialogue_act,
            "last_assistant_response": self.last_assistant_response,
            "pending_question": self.pending_question,
            "pending_field": self.pending_field,
            "interrupted_field": self.interrupted_field,
            "frustrated": self.frustration_count,
            "frustration_count": self.frustration_count,
            "category": self.category,
            "subcategory": self.subcategory,
            "requirements": self.requirements,
            "missing_fields": self.missing_fields,
            "qualification_complete": self.qualification_complete,
            "results_loaded": self.results_loaded,
            "matched_product_ids": self.matched_product_ids,
            "displayed_product_ids": self.displayed_product_ids,
            "selected_product_id": self.selected_product_id,
            "comparison_product_ids": self.comparison_product_ids,
            "catalogue_version": self.catalogue_version,
            "active_product": self.active_product,
            "active_product_id": self.active_product_id,
            "last_explicit_product_id": self.last_explicit_product_id,
            "candidate_products": self.candidate_products,
            "compared_product_ids": self.compared_product_ids,
            "active_printer_for_consumables": self.active_printer_for_consumables,
            "requested_ink_color": self.requested_ink_color,
            "active_consumable": self.active_consumable,
            "active_consumables": self.active_consumables,
            "awaiting_field": self.awaiting_field,
            "pending_disambiguation_model": self.pending_disambiguation_model,
            "unresolved_field_turns": self.unresolved_field_turns,
            "last_suggested_chips": self.last_suggested_chips,
            "history_turns": self.history_turns,
            "turn_count": self.turn_count or len(self.history_turns),
            "state_version": self.state_version,
            "human_agent_active": self.human_agent_active,
            "human_agent_id": self.human_agent_id,
            "human_agent_name": self.human_agent_name,
            "handover_triggered": self.handover_triggered,
            "handover_reason": self.handover_reason,
            "handover_timestamp": self.handover_timestamp,
            "last_opener_index": self.last_opener_index,
            "last_pricing_index": self.last_pricing_index,
            "pending_agent_messages": self.pending_agent_messages,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        """Deserialize from dict."""
        return cls(
            session_id=data.get("session_id", ""),
            customer_name=data.get("customer_name"),
            customer_id=data.get("customer_id"),
            lead_prompt_status=data.get("lead_prompt_status"),
            customer_phone_or_email=data.get("customer_phone_or_email"),
            preferred_language=data.get("preferred_language", "en"),
            stage=data.get("stage", "open"),
            active_route=data.get("active_route"),
            last_intent=data.get("last_intent"),
            last_dialogue_act=data.get("last_dialogue_act"),
            last_assistant_response=data.get("last_assistant_response"),
            pending_question=data.get("pending_question"),
            pending_field=data.get("pending_field"),
            interrupted_field=data.get("interrupted_field"),
            frustration_count=data.get("frustrated", data.get("frustration_count", 0)),
            category=data.get("category"),
            subcategory=data.get("subcategory"),
            requirements=data.get("requirements", {}),
            missing_fields=data.get("missing_fields", []),
            qualification_complete=data.get("qualification_complete", False),
            results_loaded=data.get("results_loaded", False),
            matched_product_ids=data.get("matched_product_ids", []),
            displayed_product_ids=data.get("displayed_product_ids", []),
            selected_product_id=data.get("selected_product_id"),
            comparison_product_ids=data.get("comparison_product_ids", []),
            catalogue_version=data.get("catalogue_version", "41_approved_v1"),
            active_product=data.get("active_product"),
            active_product_id=data.get("active_product_id"),
            last_explicit_product_id=data.get("last_explicit_product_id"),
            candidate_products=data.get("candidate_products", []),
            compared_product_ids=data.get("compared_product_ids", []),
            active_printer_for_consumables=data.get("active_printer_for_consumables"),
            requested_ink_color=data.get("requested_ink_color"),
            active_consumable=data.get("active_consumable"),
            active_consumables=data.get("active_consumables", []),
            awaiting_field=data.get("awaiting_field"),
            pending_disambiguation_model=data.get("pending_disambiguation_model"),
            unresolved_field_turns=data.get("unresolved_field_turns", 0),
            last_suggested_chips=data.get("last_suggested_chips", []),
            history_turns=data.get("history_turns", []),
            turn_count=data.get("turn_count", 0),
            state_version=data.get("state_version", 3),
            human_agent_active=bool(data.get("human_agent_active", False)),
            human_agent_id=data.get("human_agent_id"),
            human_agent_name=data.get("human_agent_name"),
            handover_triggered=bool(data.get("handover_triggered", False)),
            handover_reason=data.get("handover_reason"),
            handover_timestamp=data.get("handover_timestamp"),
            last_opener_index=data.get("last_opener_index"),
            last_pricing_index=data.get("last_pricing_index"),
            pending_agent_messages=data.get("pending_agent_messages", []),
        )

    # ── State Mutations ──────────────────────────────────────────────────

    def update_requirements(self, new_reqs: Dict[str, Any], corrections: Optional[Dict[str, Any]] = None):
        """
        Updates requirements, replacing old values when explicitly corrected.
        Clears results_loaded if a filtering requirement changed so fresh cards are fetched.
        """
        changed = False
        incoming = {**(corrections or {}), **(new_reqs or {})}
        # Exact counts refer to what the customer stated. A changed monthly
        # count supersedes an older exact daily statement and vice versa.
        if "exact_monthly_volume" in incoming and "exact_daily_volume" not in incoming:
            if self.requirements.pop("exact_daily_volume", None) is not None:
                changed = True
        elif "exact_daily_volume" in incoming and "exact_monthly_volume" not in incoming:
            if self.requirements.pop("exact_monthly_volume", None) is not None:
                changed = True
        if corrections:
            for k, v in corrections.items():
                if self.requirements.get(k) != v:
                    self.requirements[k] = v
                    changed = True
        
        if new_reqs:
            for k, v in new_reqs.items():
                if v is not None and v != "":
                    if self.requirements.get(k) != v:
                        self.requirements[k] = v
                        changed = True
                        
        if changed:
            # Force refetch of cards on requirement change
            self.results_loaded = False
            self.candidate_products = []
            self.active_product = None

    def reset_category(self, new_category: Optional[str]):
        """
        Resets only incompatible requirements when the customer changes categories.
        Preserves common fields like daily_volume if applicable.
        """
        if self.category == new_category and new_category is not None:
            return
        
        # Incompatible requirements are cleared
        preserved_volume = self.requirements.get("daily_volume")
        self.category = new_category
        self.subcategory = None
        self.requirements = {}
        if preserved_volume is not None:
            self.requirements["daily_volume"] = preserved_volume

        self.qualification_complete = False
        self.results_loaded = False
        self.stage = "qualifying"
        self.matched_product_ids = []
        self.displayed_product_ids = []
        self.candidate_products = []
        self.compared_products = []
        self.compared_product_ids = []
        self.active_product = None
        self.active_product_id = None
        self.active_printer_for_consumables = None
        self.awaiting_field = None
        self.pending_question = None
        self.pending_field = None
        self.unresolved_field_turns = 0

    def reset_subcategory(self, new_subcategory: Optional[str] = None):
        """
        Clears subcategory-specific requirements and active products when subcategory changes.
        """
        if self.subcategory == new_subcategory and new_subcategory is not None:
            return
        self.subcategory = new_subcategory
        self.qualification_complete = False
        self.results_loaded = False
        self.displayed_product_ids = []
        self.candidate_products = []
        self.compared_products = []
        self.compared_product_ids = []
        self.active_product = None
        self.active_product_id = None
        self.active_printer_for_consumables = None
        self.awaiting_field = None
        self.unresolved_field_turns = 0

    def save_pending_question(self, question: str, field_name: str):
        self.pending_question = question
        self.pending_field = field_name

    def consume_pending_question(self) -> Optional[str]:
        q = self.pending_question
        self.pending_question = None
        self.pending_field = None
        return q

    def record_frustration(self):
        self.frustration_count += 1

    def increment_turn(self):
        self.turn_count += 1

    def format_requirements_summary(self) -> str:
        """Returns a natural, concise summary of all currently gathered requirements."""
        if not self.requirements:
            return ""
        reqs = self.requirements
        parts = []

        # 1. Size / Width
        sz = reqs.get("paper_size") or reqs.get("print_size") or reqs.get("print_width") or reqs.get("size")
        if sz:
            if isinstance(sz, int) or (isinstance(sz, str) and str(sz).isdigit()):
                parts.append(f"{sz}″ width")
            elif str(sz).lower().startswith("a"):
                parts.append(str(sz).upper())
            else:
                parts.append(str(sz))
        elif reqs.get("print_sizes"):
            p_sizes = reqs["print_sizes"]
            if isinstance(p_sizes, list):
                parts.append("/".join(p_sizes))

        # 2. Volume
        d_vol = reqs.get("exact_daily_volume") or reqs.get("daily_volume")
        m_vol = reqs.get("exact_monthly_volume") or reqs.get("monthly_volume")
        if d_vol:
            cat_l = str(self.category or "").lower()
            vol_unit = "pages/day" if ("cad" in cat_l or "office" in cat_l) else "prints/day"
            parts.append(f"{d_vol} {vol_unit}")
        elif m_vol:
            parts.append(f"~{m_vol:,} pages/month")

        # 3. Functions
        if reqs.get("scanner_required") is False or reqs.get("scan_required") is False or reqs.get("functions") == ["print"]:
            parts.append("print-only")
        elif reqs.get("scanner_required") is True or reqs.get("scan_required") is True:
            parts.append("integrated scanner")
        elif "functions" in reqs and isinstance(reqs["functions"], list):
            parts.append("/".join(reqs["functions"]))

        # 4. Duplex / Ethernet / Hardware Features
        if reqs.get("duplex"):
            parts.append("auto-duplex")
        if reqs.get("ethernet"):
            parts.append("Ethernet")
        if reqs.get("dual_roll_required"):
            parts.append("dual rolls")
        if reqs.get("ribbon_rewind"):
            parts.append("2×6″ photo strips")
        if reqs.get("matte"):
            parts.append("matte finish")
        if reqs.get("portable") or reqs.get("under_10kg"):
            parts.append("< 10 kg")

        # 5. Technology / Inks
        if reqs.get("printing_technology") == "pigment" or reqs.get("pigment_ink"):
            parts.append("pigment inks")
        elif reqs.get("printing_technology") == "dye_sub":
            parts.append("dye-sublimation")

        return ", ".join(parts)
