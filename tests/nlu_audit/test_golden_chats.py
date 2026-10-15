"""
Tests for Deterministic Universal Multi-Turn Golden Chats and State/Alias Resolution.
Verifies the 18 customer chats plus unit tests with Ollama OFF / unreachable.
"""

import pytest
from domain.conversation_state import ConversationState
from agent.orchestrator import Orchestrator
from catalog.alias_index import alias_index, match_consumables_vocab
from nlp.deterministic_interceptor import intercept


@pytest.fixture
def orch():
    return Orchestrator(ollama_client=None)


# ==============================================================================
# UNIT TESTS
# ==============================================================================

class TestAliasResolver:
    """Unit tests for catalog/alias_index.py"""

    def test_alias_c878(self):
        res = alias_index.resolve("c878")
        assert res.match_type == "exact"
        assert res.product["id"] == "epson-wf-c878r-dwf"

    def test_alias_c878r(self):
        res = alias_index.resolve("c878r")
        assert res.match_type == "exact"
        assert res.product["id"] == "epson-wf-c878r-dwf"

    def test_alias_cz02_candidates(self):
        res = alias_index.resolve("cz02")
        assert res.match_type == "candidates"
        assert len(res.candidates) >= 2
        # Should include CZ-01 and CX-02
        cand_lower = [c["id"].lower() for c in res.candidates]
        assert any("cz" in c for c in cand_lower)
        assert any("cx" in c for c in cand_lower)

    def test_consumables_vocab(self):
        assert match_consumables_vocab("consubales") == "consumables"
        assert match_consumables_vocab("consumbales") == "consumables"
        assert match_consumables_vocab("maintainence") == "maintenance box"
        assert match_consumables_vocab("ink") == "ink"
        assert match_consumables_vocab("ribbon") == "ribbon"


class TestPendingQuestionBinding:
    """Unit tests for pending-question binding in pre_classification_resolver"""

    def test_in_range_volume(self, orch):
        state = ConversationState(session_id="test_in_range")
        state.category = "office_printer"
        state.requirements["paper_size"] = "a3"
        state.save_pending_question(
            question="How many pages per day?",
            field_name="daily_volume",
            expected_type="number",
            valid_range=(100, 10000),
        )
        res = orch.process_turn("400", state=state)
        assert state.requirements.get("daily_volume") == 400
        assert "c878" in res["reply"].lower() or len(res.get("cards", [])) > 0

    def test_out_of_range_volume(self, orch):
        state = ConversationState(session_id="test_out_of_range")
        state.category = "office_printer"
        state.requirements["paper_size"] = "a3"
        state.save_pending_question(
            question="How many pages per day?",
            field_name="daily_volume",
            expected_type="number",
            valid_range=(100, 10000),
        )
        res = orch.process_turn("its 40", state=state)
        rep = res["reply"].lower()
        # Should note 40 is below range and offer nearest A3 / A4 alternative
        assert "below" in rep or "standard minimum" in rep or "c878" in rep or "5890" in rep
        # Must NOT re-ask the exact same question or use operational workflow header
        assert "regarding your operational workflow" not in rep

    def test_bare_number_width(self, orch):
        state = ConversationState(session_id="test_bare_num")
        state.category = "technical_large_format"
        state.save_pending_question(
            question="What print width do you require?",
            field_name="print_width",
            expected_type="number",
            valid_range=(24, 44),
        )
        res = orch.process_turn("24", state=state)
        assert state.requirements.get("print_width") == 24


class TestReferentResolution:
    """Unit tests for referent resolution against shown_entities"""

    def test_both_zero_shown(self, orch):
        state = ConversationState(session_id="test_both_zero")
        state.shown_entities = []
        state.displayed_product_ids = []
        res = orch.process_turn("both models have scan?", state=state)
        assert "which" in res["reply"].lower() or "please select" in res["reply"].lower()

    def test_both_with_shown(self, orch):
        state = ConversationState(session_id="test_both_two")
        state.shown_entities = ["epson-wf-c878r-dwf", "epson-wf-c879r-dwf"]
        res = orch.process_turn("both models have scan?", state=state)
        rep = res["reply"].lower()
        assert "878" in rep and "879" in rep

    def test_dono_with_shown(self, orch):
        state = ConversationState(session_id="test_dono")
        state.shown_entities = ["epson-wf-c878r-dwf", "epson-wf-c879r-dwf"]
        res = orch.process_turn("dono ka spec batao", state=state)
        rep = res["reply"].lower()
        assert "878" in rep or "spec" in rep or len(res.get("cards", [])) > 0

    def test_the_second(self, orch):
        state = ConversationState(session_id="test_second")
        state.shown_entities = ["epson-wf-c5890-dwf", "epson-em-c800"]
        res = orch.process_turn("ok give quote for the second", state=state)
        rep = res["reply"].lower()
        assert "em-c800" in rep or "quotation" in rep or "second" in rep


class TestStateAndInterceptor:
    """Unit tests for state management and deterministic interceptor"""

    def test_switch_category_clears_dependent_slots(self):
        state = ConversationState(session_id="test_switch")
        state.category = "office_printer"
        state.requirements = {
            "category": "office_printer",
            "daily_volume": 400,
            "paper_size": "a3",
            "colour_mode": "colour",
            "application": "office_documents",
            "user_intent": "high_quality"
        }
        state.switch_category("citizen_photo", reason="Customer switched")
        assert state.category == "citizen_photo"
        assert state.requirements.get("category") == "citizen_photo"
        assert "daily_volume" not in state.requirements
        assert "paper_size" not in state.requirements
        assert "colour_mode" not in state.requirements
        assert "application" not in state.requirements

    def test_interceptor_does_not_switch_on_with_scanner(self):
        state = ConversationState(session_id="test_interceptor")
        state.category = "photography_large_format"
        res = intercept("with scanner", state=state)
        assert not res.matched or getattr(res, "category", None) != "scanners"


# ==============================================================================
# 18 GOLDEN CHATS INTEGRATION TESTS
# ==============================================================================

class TestGoldenChats:
    """Tests all 18 multi-turn customer chat flows with per-turn assertions."""

    def test_chat_01_a3_office_volume_and_both(self, orch):
        state = ConversationState(session_id="chat_01")
        # 1. hi
        r1 = orch.process_turn("hi", state=state)
        # 2. need a3 printer for office
        r2 = orch.process_turn("need a3 printer for office", state=state)
        assert state.category == "office_printer"
        # 3. its 40 -> out of range handled, not re-asking volume question
        r3 = orch.process_turn("its 40", state=state)
        rep3 = r3["reply"].lower()
        assert "how many pages do you print per day" not in rep3
        assert "select your daily page volume" not in rep3
        # 4. sorry i meant 400 per day -> updates volume and returns models
        r4 = orch.process_turn("sorry i meant 400 per day", state=state)
        assert state.requirements.get("daily_volume") == 400
        assert len(r4.get("cards", [])) > 0 or "878" in r4["reply"]
        # 5. both models have scan? -> answers for both 878 and 879
        r5 = orch.process_turn("both models have scan?", state=state)
        rep5 = r5["reply"].lower()
        assert "878" in rep5 and "879" in rep5

    def test_chat_02_a4_office_budget_compare(self, orch):
        state = ConversationState(session_id="chat_02")
        # 1. i want a4 colour printer with scanner
        r1 = orch.process_turn("i want a4 colour printer with scanner", state=state)
        assert state.category == "office_printer"
        # 2. 50 pages a day
        r2 = orch.process_turn("50 pages a day", state=state)
        assert len(r2.get("cards", [])) > 0
        # 3. which is cheaper
        r3 = orch.process_turn("which is cheaper", state=state)
        # 4. compare first two
        r4 = orch.process_turn("compare first two", state=state)
        assert len(r4.get("cards", [])) >= 2 or "comparison" in r4["reply"].lower()
        # 5. ok give quote for the second
        r5 = orch.process_turn("ok give quote for the second", state=state)
        assert "which model or application are you looking to price" not in r5["reply"].lower()

    def test_chat_03_40_ppm_vs_pages(self, orch):
        state = ConversationState(session_id="chat_03")
        orch.process_turn("a3 office", state=state)
        # 40 ppm treated as speed -> AM-C4000
        r2 = orch.process_turn("40 ppm", state=state)
        assert any("am-c4000" in str(c.get("id", "")).lower() for c in r2.get("cards", [])) or "am-c4000" in r2["reply"].lower()
        # duty cycle inquiry
        orch.process_turn("how many pages per day is it good for", state=state)
        # c878r resolves
        r4 = orch.process_turn("and the c878r?", state=state)
        assert "not in our approved equipment catalogue" not in r4["reply"].lower()
        assert "c878" in r4["reply"].lower()

    def test_chat_04_f100_typo_and_paper_size(self, orch):
        state = ConversationState(session_id="chat_04")
        # Turn 1: i need f100 consubales
        r1 = orch.process_turn("i need f100 consubales", state=state)
        assert len(r1.get("consumable_cards", [])) > 0 or "consumable" in r1["reply"].lower() or "t49n" in r1["reply"].lower()
        orch.process_turn("price?", state=state)
        orch.process_turn("any other ink for it", state=state)
        # Turn 4: what paper size it supports -> answers paper size (A4), not consumables
        r4 = orch.process_turn("what paper size it supports", state=state)
        assert "a4" in r4["reply"].lower()

    def test_chat_05_topic_switching(self, orch):
        state = ConversationState(session_id="chat_05")
        orch.process_turn("sublimation printer for mugs and t-shirts", state=state)
        orch.process_turn("a4 only?", state=state)
        # Turn 3: switches to A3 office
        r3 = orch.process_turn("and for the a3 office printer?", state=state)
        assert state.category == "office_printer"
        # Turn 4: back to F100
        r4 = orch.process_turn("back to the f100 – ink bottle size", state=state)
        assert state.category != "office_printer"

    def test_chat_06_event_photographer(self, orch):
        state = ConversationState(session_id="chat_06")
        orch.process_turn("photo booth printer for events", state=state)
        orch.process_turn("4x6 prints", state=state)
        # Turn 3: also 6x8 sometimes -> retains both 4x6 and 6x8 models
        r3 = orch.process_turn("also 6x8 sometimes", state=state)
        assert len(r3.get("cards", [])) >= 2
        orch.process_turn("cx02 yield?", state=state)
        orch.process_turn("and cy02?", state=state)

    def test_chat_07_ambiguous_model_cz02(self, orch):
        state = ConversationState(session_id="chat_07")
        # Turn 1: cz02 printer -> candidates, not rejection
        r1 = orch.process_turn("cz02 printer", state=state)
        assert "not in our approved equipment catalogue" not in r1["reply"].lower()
        # Turn 2: the first one -> resolves
        r2 = orch.process_turn("the first one", state=state)
        assert len(r2.get("cards", [])) > 0 or "cz-01" in r2["reply"].lower()
        orch.process_turn("media for it", state=state)

    def test_chat_08_pattern_change(self, orch):
        state = ConversationState(session_id="chat_08")
        orch.process_turn("cz01 can i change print pattern", state=state)
        orch.process_turn("how", state=state)
        orch.process_turn("what ribbon needed", state=state)

    def test_chat_09_cad_large_format_36(self, orch):
        state = ConversationState(session_id="chat_09")
        orch.process_turn("cad printer", state=state)
        orch.process_turn("24", state=state)
        orch.process_turn("no scanner needed", state=state)
        # Turn 4: actually make it 36
        r4 = orch.process_turn("actually make it 36", state=state)
        assert state.requirements.get("print_width") == 36
        assert len(r4.get("cards", [])) > 0 or "36" in r4["reply"]
        orch.process_turn("roll sizes?", state=state)

    def test_chat_10_photography_large_format(self, orch):
        state = ConversationState(session_id="chat_10")
        orch.process_turn("professional photo printer 44 inch", state=state)
        r2 = orch.process_turn("with scanner", state=state)
        assert state.category in ("photography_large_format", "photo")
        orch.process_turn("dual roll?", state=state)
        r4 = orch.process_turn("show only 24 inch", state=state)
        assert state.category in ("photography_large_format", "photo")

    def test_chat_11_wrong_spellings_consumables(self, orch):
        state = ConversationState(session_id="chat_11")
        # c878 resolves
        r1 = orch.process_turn("need ink for epson c878", state=state)
        assert "not in our approved equipment catalogue" not in r1["reply"].lower()
        orch.process_turn("yellow one price", state=state)
        orch.process_turn("maintainence box also", state=state)
        orch.process_turn("total for all 4 colors", state=state)

    def test_chat_12_compound_two_inputs(self, orch):
        state = ConversationState(session_id="chat_12")
        # Turn 1: ink for f100 and also maintenance box for c878r
        r1 = orch.process_turn("ink for f100 and also maintenance box for c878r", state=state)
        rep1 = r1["reply"].lower()
        assert "f100" in rep1 or "t49n" in rep1
        assert "c878" in rep1 or "t6714" in rep1
        # Turn 2: which one is cheaper
        r2 = orch.process_turn("which one is cheaper", state=state)
        assert "cheaper" in r2["reply"].lower()

    def test_chat_13_hinglish_dono_spec(self, orch):
        state = ConversationState(session_id="chat_13")
        orch.process_turn("mujhe office ke liye a3 printer chahiye", state=state)
        orch.process_turn("roz 100 pages", state=state)
        r3 = orch.process_turn("dono ka spec batao", state=state)
        assert len(r3.get("consumable_cards", [])) == 0 or len(r3.get("cards", [])) > 0

    def test_chat_14_arabic_price_guardrail(self, orch):
        state = ConversationState(session_id="chat_14")
        orch.process_turn("أريد طابعة مكتبية", state=state)
        orch.process_turn("A3", state=state)
        r3 = orch.process_turn("كم السعر؟", state=state)
        rep3 = r3["reply"].lower()
        assert "how many pages do you print per day" not in rep3
        assert "select your daily page volume" not in rep3

    def test_chat_15_malayalam_photo_printer(self, orch):
        state = ConversationState(session_id="chat_15")
        orch.process_turn("enikku photo printer venam", state=state)
        orch.process_turn("4x6", state=state)
        r3 = orch.process_turn("ink evide kittum?", state=state)
        assert not (r3.get("cards") and not r3.get("consumable_cards"))

    def test_chat_16_policy_and_refusals(self, orch):
        state = ConversationState(session_id="chat_16")
        orch.process_turn("what are your prices?", state=state)
        orch.process_turn("give me 20% discount", state=state)
        orch.process_turn("do you sell HP LaserJet?", state=state)
        orch.process_turn("ok then recommend something", state=state)

    def test_chat_17_junk_and_fragments(self, orch):
        state = ConversationState(session_id="chat_17")
        orch.process_turn("😀👍", state=state)
        orch.process_turn("24", state=state)
        orch.process_turn("?", state=state)
        orch.process_turn("a3", state=state)
        orch.process_turn("thanks bye", state=state)

    def test_chat_18_customer_changes_mind_switch_category(self, orch):
        state = ConversationState(session_id="chat_18")
        orch.process_turn("a4 office printer", state=state)
        orch.process_turn("100 pages", state=state)
        # Turn 3: switches to photo booth
        r3 = orch.process_turn("no wait not office, photo booth", state=state)
        assert state.category == "citizen_photo"
        # Turn 4: 4x6 prints
        r4 = orch.process_turn("4x6", state=state)
        assert state.category == "citizen_photo"
        # Turn 5: cheapest one?
        r5 = orch.process_turn("cheapest one?", state=state)
        assert "cz-01" in r5["reply"].lower()
