"""
Targeted NLU Probes for jishankt/newsalesai.
Audits core NLU invariants in conversation/understanding.py:
1. Bare numbers never become a model or a budget
2. A correction overwrites earlier slot; negated phrase never fills the slot it negates
3. Two close model candidates produce clarification, not silent pick
4. Budget ranges, 'k' suffix, commas, and Arabic-Indic digits parse correctly
5. Category priority never silently drops a second stated need
6. Non-English messages with clear category/size words are not read as out_of_scope
7. Empty and emoji-only input does not crash and returns low-confidence clarify

Tests that uncover current implementation defects are marked with:
@pytest.mark.xfail(strict=True, reason="...")
so that fixing the bug later flips the test to pass.
"""

import pytest
from conversation.understanding import understand_turn, DialogueAct, Intent


# ==============================================================================
# Invariant 1: Bare numbers never become a model or a budget
# ==============================================================================

def test_bare_numbers_not_models():
    """Bare numbers like '24', '12', '5' must not be recognized as printer models."""
    for num in ["24", "12", "5", "100"]:
        turn = understand_turn(num, allow_llm=False)
        assert turn.slots.get("target_model") is None, f"Bare number {num} set target_model to {turn.slots.get('target_model')}"


@pytest.mark.xfail(strict=True, reason="DEFECT: understand_turn('24') assigns Intent.RECOMMEND with 0.95 confidence instead of low-confidence clarify")
def test_bare_number_intent_not_high_confidence_recommend():
    """A bare number with no context should not produce a confident product recommendation."""
    turn = understand_turn("24", allow_llm=False)
    assert turn.overall_confidence < 0.70 or turn.intent != Intent.RECOMMEND


def test_bare_number_not_parsed_as_budget():
    """A bare number like '24' or '12' must not be parsed as budget ceiling."""
    turn = understand_turn("24", allow_llm=False)
    assert turn.slots.get("budget_ceiling") is None


# ==============================================================================
# Invariant 2: Negation & Correction
# ==============================================================================

@pytest.mark.xfail(strict=True, reason="DEFECT: extract_slots has no negation detection; 'not A3' regex matches 'a3' and sets media_size='a3'")
def test_negated_media_size_not_filled():
    """'not A3' must not fill media_size='a3' in slots."""
    turn = understand_turn("not A3", allow_llm=False)
    media_size = turn.slots.get("media_size")
    val = media_size.value if media_size else None
    assert val != "a3", f"Negated media size was filled as {val}"


@pytest.mark.xfail(strict=True, reason="DEFECT: extract_slots matches 'photo' in 'I don't need photo printing' and assigns target_category='photo_fine_art'")
def test_negated_category_not_filled():
    """'I don't need photo printing' must not set target_category='photo_fine_art'."""
    turn = understand_turn("I don't need photo printing", allow_llm=False)
    cat = turn.slots.get("target_category")
    val = cat.value if cat else None
    assert val != "photo_fine_art", f"Negated category was filled as {val}"


@pytest.mark.xfail(strict=True, reason="DEFECT: 'forget the plotter' matches 'plotter' and fills target_category='technical_cad'")
def test_forget_category_not_filled():
    """'forget the plotter' must not set target_category='technical_cad'."""
    turn = understand_turn("forget the plotter", allow_llm=False)
    cat = turn.slots.get("target_category")
    val = cat.value if cat else None
    assert val != "technical_cad", f"Negated category was filled as {val}"


@pytest.mark.xfail(strict=True, reason="DEFECT: Negated model 'not CX-02' fills target_model with citizen-cx-02")
def test_negated_model_not_filled():
    """'not CX-02' must not set target_model='citizen-cx-02'."""
    turn = understand_turn("not CX-02", allow_llm=False)
    target_model = turn.slots.get("target_model")
    val = target_model.value if target_model else None
    assert val != "citizen-cx-02", f"Negated model was filled as {val}"


# ==============================================================================
# Invariant 3: Model Ambiguity & Comparison
# ==============================================================================

@pytest.mark.xfail(strict=True, reason="DEFECT: 'cz02' typo is hardcoded to citizen-cx-02 in alias_map instead of requesting clarification")
def test_ambiguous_typo_cz02_requests_clarification():
    """'cz02' is ambiguous between CZ-01 and CX-02; it should not silently resolve to citizen-cx-02 with 0.95 confidence."""
    turn = understand_turn("cz02 price", allow_llm=False)
    assert turn.ambiguities or turn.overall_confidence < 0.75, "cz02 silently picked model with high confidence"


@pytest.mark.xfail(strict=True, reason="DEFECT: Spaced model names like 'p 7500' fail alias matching because alias_map only has 'p7500'")
def test_spaced_model_name_recognition():
    """'p 7500' must resolve to epson-sc-p7500 just like 'p7500' does."""
    turn = understand_turn("price of p 7500", allow_llm=False)
    target_model = turn.slots.get("target_model")
    val = target_model.value if target_model else None
    assert val == "epson-sc-p7500", f"Expected epson-sc-p7500, got {val}"


def test_comparison_preserves_both_models():
    """'compare CX-02 and CY-02' must capture comparison_models in slots."""
    turn = understand_turn("compare CX-02 and CY-02", allow_llm=False)
    comp = turn.slots.get("comparison_models")
    assert comp is not None, "comparison_models slot was not extracted"
    assert "citizen-cx-02" in comp.value and "citizen-cy-02" in comp.value


# ==============================================================================
# Invariant 4: Budget Parsing ('k', commas, ranges, Arabic-Indic digits)
# ==============================================================================

def test_budget_k_suffix():
    """'10k' or 'budget 10k AED' must extract budget_ceiling=10000."""
    turn = understand_turn("my budget is 10k AED", allow_llm=False)
    budget = turn.slots.get("budget_ceiling")
    assert budget is not None and budget.value == 10000, f"Expected 10000, got {budget}"


def test_budget_comma_separated():
    """'10,000-15,000 AED' must extract budget_ceiling."""
    turn = understand_turn("budget is between 10,000 and 15,000 AED", allow_llm=False)
    budget = turn.slots.get("budget_ceiling")
    assert budget is not None, "budget_ceiling was not extracted for comma-formatted number"


def test_budget_arabic_indic_digits():
    """'ميزانيتي ١٨٠٠ درهم' must extract budget_ceiling=1800."""
    turn = understand_turn("ميزانيتي ١٨٠٠ درهم", allow_llm=False)
    budget = turn.slots.get("budget_ceiling")
    assert budget is not None and budget.value == 1800, f"Expected 1800, got {budget}"


def test_non_budget_daily_volume_not_parsed_as_budget():
    """'200 pages daily' must not be parsed as a budget."""
    turn = understand_turn("200 pages daily", allow_llm=False)
    budget = turn.slots.get("budget_ceiling")
    assert budget is None, f"Daily volume was wrongly parsed as budget: {budget}"


# ==============================================================================
# Invariant 5: Category Priority Never Silently Drops Second Need
# ==============================================================================

@pytest.mark.xfail(strict=True, reason="DEFECT: CATEGORY_PRIORITY silently drops 'office_workforce' when 'technical_cad' matches in 'office printer for CAD drawings'")
def test_category_priority_does_not_silently_drop_second_need():
    """'office printer for CAD drawings' contains both office_workforce and technical_cad."""
    turn = understand_turn("office printer for CAD drawings", allow_llm=False)
    # The system should either record both categories, flag ambiguity, or set secondary intent
    assert turn.ambiguities or len(turn.entities) >= 2, "Secondary category was silently discarded without ambiguity flag"


@pytest.mark.xfail(strict=True, reason="DEFECT: 'photo booth for events and also office use' silently drops office use")
def test_photo_booth_and_office_overlap():
    """'photo booth for events and also office use' contains citizen_photo and office_workforce."""
    turn = understand_turn("photo booth for events and also office use", allow_llm=False)
    assert turn.ambiguities or len(turn.entities) >= 2, "Multi-category intent silently resolved to single category"


# ==============================================================================
# Invariant 6: Non-English Messages Handled
# ==============================================================================

@pytest.mark.xfail(strict=True, reason="DEFECT: Arabic printer request 'أريد طابعة فوتوغرافية احترافية' matches zero keywords, returning Intent.OTHER with no category")
def test_arabic_category_request():
    """Arabic inquiry for professional photo printer should identify photo_fine_art category."""
    turn = understand_turn("أريد طابعة فوتوغرافية احترافية", allow_llm=False)
    cat = turn.slots.get("target_category")
    val = cat.value if cat else None
    assert val == "photo_fine_art", f"Expected photo_fine_art, got {val}"


def test_hinglish_size_and_category_keywords():
    """Hinglish 'A3 photo printer chahiye' contains English keywords 'A3' and 'photo'."""
    turn = understand_turn("A3 photo printer chahiye", allow_llm=False)
    assert turn.slots.get("media_size") is not None
    assert turn.slots["media_size"].value == "a3"


# ==============================================================================
# Invariant 7: Empty and Emoji-Only Input Safety & Clarification
# ==============================================================================

def test_empty_string_does_not_crash():
    """Empty string must not crash understanding."""
    turn = understand_turn("", allow_llm=False)
    assert turn is not None


def test_whitespace_string_does_not_crash():
    """Whitespace string must not crash understanding."""
    turn = understand_turn("   ", allow_llm=False)
    assert turn is not None


def test_emoji_only_does_not_crash():
    """Emoji-only string must not crash understanding."""
    turn = understand_turn("🖨️📸🔥", allow_llm=False)
    assert turn is not None


@pytest.mark.xfail(strict=True, reason="DEFECT: Empty string defaults to DialogueAct.QUESTION instead of DialogueAct.CLARIFICATION/STATEMENT with low confidence")
def test_empty_string_dialogue_act_not_question():
    """Empty input should not be classified as DialogueAct.QUESTION."""
    turn = understand_turn("", allow_llm=False)
    assert turn.dialogue_act != DialogueAct.QUESTION, f"Empty string classified as {turn.dialogue_act}"
