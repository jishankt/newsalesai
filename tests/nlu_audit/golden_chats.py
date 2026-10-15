"""
Golden Chats Replay Engine and Test Definitions.
Provides replay_chat() and GOLDEN_CHATS definitions for the 18 multi-turn evaluation chats.
"""

from typing import List, Dict, Any, Optional
from domain.conversation_state import ConversationState
from agent.orchestrator import Orchestrator

GOLDEN_CHATS = [
    {
        "id": "chat_01",
        "title": "Chat 1: A3 office, wrong volume, then correction",
        "turns": [
            "hi",
            "need a3 printer for office",
            "its 40",
            "sorry i meant 400 per day",
            "both models have scan?",
        ],
        "pass_criteria": "40 accepted and not re-asked; 400 replaces the volume and returns models; 'both' answers for WF-C878R and WF-C879R.",
    },
    {
        "id": "chat_02",
        "title": "Chat 2: A4 office, budget and comparison",
        "turns": [
            "i want a4 colour printer with scanner",
            "50 pages a day",
            "which is cheaper",
            "compare first two",
            "ok give quote for the second",
        ],
        "pass_criteria": "stays in printers; no invented prices; 'second' targets the right product.",
    },
    {
        "id": "chat_03",
        "title": "Chat 3: 40 ppm vs 40 pages",
        "turns": [
            "a3 office",
            "40 ppm",
            "how many pages per day is it good for",
            "and the c878r?",
        ],
        "pass_criteria": "40 ppm treated as speed; c878r resolves to WF-C878R.",
    },
    {
        "id": "chat_04",
        "title": "Chat 4: the typo case from transcript",
        "turns": [
            "i need f100 consubales",
            "price?",
            "any other ink for it",
            "what paper size it supports",
        ],
        "pass_criteria": "consumables for F100 on turn 1; paper size answered on turn 4 (not consumables again).",
    },
    {
        "id": "chat_05",
        "title": "Chat 5: topic switching",
        "turns": [
            "sublimation printer for mugs and t-shirts",
            "a4 only?",
            "and for the a3 office printer?",
            "back to the f100 – ink bottle size",
        ],
        "pass_criteria": "turn 3 switches to A3 office; turn 4 returns to F100 and state.category is not office_printer.",
    },
    {
        "id": "chat_06",
        "title": "Chat 6: event photographer, step by step",
        "turns": [
            "photo booth printer for events",
            "4x6 prints",
            "also 6x8 sometimes",
            "cx02 yield?",
            "and cy02?",
        ],
        "pass_criteria": "already passes; must not regress.",
    },
    {
        "id": "chat_07",
        "title": "Chat 7: ambiguous model typo",
        "turns": [
            "cz02 printer",
            "the first one",
            "media for it",
        ],
        "pass_criteria": "asks which model (CZ-01 or CX-02); 'the first one' resolves to the first option.",
    },
    {
        "id": "chat_08",
        "title": "Chat 8: pattern change",
        "turns": [
            "cz01 can i change print pattern",
            "how",
            "what ribbon needed",
        ],
        "pass_criteria": "already passes; must not regress.",
    },
    {
        "id": "chat_09",
        "title": "Chat 9: CAD / large format",
        "turns": [
            "cad printer",
            "24",
            "no scanner needed",
            "actually make it 36",
            "roll sizes?",
        ],
        "pass_criteria": "36-inch models returned; no-scanner kept; rolls for the 36-inch model.",
    },
    {
        "id": "chat_10",
        "title": "Chat 10: photography large format",
        "turns": [
            "professional photo printer 44 inch",
            "with scanner",
            "dual roll?",
            "show only 24 inch",
        ],
        "pass_criteria": "stays photography; scanner is an attribute; turn 4 resets width and keeps photography.",
    },
    {
        "id": "chat_11",
        "title": "Chat 11: wrong spellings",
        "turns": [
            "need ink for epson c878",
            "yellow one price",
            "maintainence box also",
            "total for all 4 colors",
        ],
        "pass_criteria": "c878 resolves; catalogue prices only; total sums the right items.",
    },
    {
        "id": "chat_12",
        "title": "Chat 12: two inputs at once",
        "turns": [
            "ink for f100 and also maintenance box for c878r",
            "which one is cheaper",
        ],
        "pass_criteria": "both parts answered; comparison uses exactly those two items.",
    },
    {
        "id": "chat_13",
        "title": "Chat 13: Hinglish",
        "turns": [
            "mujhe office ke liye a3 printer chahiye",
            "roz 100 pages",
            "dono ka spec batao",
        ],
        "pass_criteria": "'dono' gives specs for both models, not consumables.",
    },
    {
        "id": "chat_14",
        "title": "Chat 14: Arabic",
        "turns": [
            "أريد طابعة مكتبية",
            "A3",
            "كم السعر؟",
        ],
        "pass_criteria": "price guardrail reply, A3 kept, volume question not repeated in place of the answer.",
    },
    {
        "id": "chat_15",
        "title": "Chat 15: Malayalam",
        "turns": [
            "enikku photo printer venam",
            "4x6",
            "ink evide kittum?",
        ],
        "pass_criteria": "4x6 recognised; last turn gives consumables, not a hardware card.",
    },
    {
        "id": "chat_16",
        "title": "Chat 16: policy and refusals",
        "turns": [
            "what are your prices?",
            "give me 20% discount",
            "do you sell HP LaserJet?",
            "ok then recommend something",
        ],
        "pass_criteria": "already passes; must not regress.",
    },
    {
        "id": "chat_17",
        "title": "Chat 17: junk and fragments",
        "turns": [
            "😀",
            "24",
            "?",
            "a3",
            "thanks bye",
        ],
        "pass_criteria": "already passes; must not regress.",
    },
    {
        "id": "chat_18",
        "title": "Chat 18: customer changes mind mid-way",
        "turns": [
            "a4 office printer",
            "100 pages",
            "no wait not office, photo booth",
            "4x6",
            "cheapest one?",
        ],
        "pass_criteria": "category becomes citizen_photo; office slots cleared; turn 5 uses photo booth results only.",
    },
]


def replay_chat(turns: List[str], session_id: str = "golden_replay", orchestrator: Optional[Orchestrator] = None) -> List[Dict[str, Any]]:
    """
    Replays a list of user turns through Orchestrator.process_turn with a fresh ConversationState.
    Returns a list of turn records containing:
      user_message, reply, cards, consumable_cards, chips, state_category, state_reqs, state_active_product, state_shown_entities.
    """
    orch = orchestrator or Orchestrator()
    state = ConversationState(session_id=session_id)
    history_records = []

    for idx, user_msg in enumerate(turns, 1):
        res = orch.process_turn(user_msg, state=state)
        product_cards = [c.get("id") or c.get("model") for c in res.get("product_cards", [])]
        consumable_cards = [c.get("id") or c.get("name") for c in res.get("consumable_cards", [])]
        chips = res.get("suggested_chips", [])
        reply = res.get("reply", "")

        turn_rec = {
            "turn": idx,
            "user_message": user_msg,
            "reply": reply,
            "cards": product_cards,
            "consumable_cards": consumable_cards,
            "chips": chips,
            "state_category": state.category,
            "state_active_product": state.active_product_id,
            "state_requirements": dict(state.requirements or {}),
            "state_shown_entities": list(getattr(state, "shown_entities", []) or getattr(state, "displayed_product_ids", []) or []),
            "pending_question": getattr(state, "pending_question", None),
        }
        history_records.append(turn_rec)

    return history_records
