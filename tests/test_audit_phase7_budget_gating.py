"""
TDD Tests for Phase 7 (P1): Budget Ceiling Extraction and Hardware Price Gating.
Audit Findings:
- Budget ceiling accuracy was 0% in baseline audit.
- Deterministic extraction failed to populate budget_ceiling and budget_scope='hardware'.
- CatalogueFilter lacked mandatory hard budget ceiling gating.
"""

import pytest
from conversation.numeric_parse import extract_budget
from conversation.normalizer import extract_deterministic_requirements
from catalog.catalogue_filter import CatalogueFilter
from conversation.product_flows import _apply_budget_filter, FlowchartStep
from agent.state_reconciler import StateReconciler
from domain.canonical_turn import CanonicalTurnUnderstanding
from domain.conversation_state import ConversationState


def test_budget_extraction_hardware_scope():
    """Test 7a: 'A4 office printer under 2500 AED' extracts budget_ceiling=2500 and budget_scope='hardware'."""
    text = "A4 office printer under 2500 AED"
    b_res = extract_budget(text)
    assert b_res is not None
    assert b_res.budget_ceiling == 2500.0
    assert b_res.budget_scope == "hardware"

    reqs, _ = extract_deterministic_requirements(text)
    assert reqs.get("budget_ceiling") == 2500.0
    assert reqs.get("budget_scope") == "hardware"
    assert reqs.get("budget_aed") == 2500.0


def test_budget_filtering_in_catalogue_filter():
    """Test 7b: Models exceeding budget ceiling are strictly filtered out of recommendations."""
    cf = CatalogueFilter()
    cards, no_match = cf.filter_and_rank(
        category="office_printer",
        subcategory=None,
        requirements={"paper_size": "a4", "budget_ceiling": 2500.0}
    )

    assert len(cards) > 0
    # WF-C5890 (1656 AED) should be included
    matched_ids = [c["id"] for c in cards]
    assert "epson-wf-c5890-dwf" in matched_ids or any("c5890" in pid for pid in matched_ids)

    # AM-C550 (9000 AED) and AM-C400 (enterprise linehead) MUST be excluded
    assert "epson-am-c550" not in matched_ids
    assert "epson-am-c400" not in matched_ids
    assert "epson-am-c4000" not in matched_ids


def test_apply_budget_filter_step():
    """Flowchart leaf recommendation enforces budget constraint or swaps to budget-fitting model."""
    step = FlowchartStep(
        category="office_printer",
        question="Which printer?",
        chips=["Quote", "Details"],
        target_product_id="epson-am-c550",  # 9000 AED
        supporting_product_ids=["epson-wf-c5890-dwf"],  # 1656 AED
        is_leaf=True,
    )
    reqs = {"budget_ceiling": 2000.0}
    filtered_step = _apply_budget_filter(step, reqs)
    # Target product should be swapped to epson-wf-c5890-dwf which fits 2000 AED
    assert filtered_step.target_product_id == "epson-wf-c5890-dwf"


def test_budget_correction_in_state_reconciler():
    """Customer correcting their budget updates requirements in ConversationState."""
    state = ConversationState(session_id="test_sess")
    state.requirements["budget_ceiling"] = 5000.0
    state.requirements["budget_aed"] = 5000.0

    understanding = CanonicalTurnUnderstanding(
        raw_message="actually my budget is max 1800 AED",
        normalized_message="actually my budget is max 1800 aed",
        corrections={"budget_ceiling": 1800.0, "budget_aed": 1800.0},
        changed_requirements={"budget_ceiling": 1800.0, "budget_aed": 1800.0},
    )

    reconciled = StateReconciler.reconcile(understanding, state)
    assert reconciled.requirements["budget_ceiling"] == 1800.0
    assert reconciled.requirements["budget_aed"] == 1800.0

