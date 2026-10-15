"""
Harness to run all 18 multi-turn evaluation chats through Orchestrator.process_turn
and capture complete outputs and pass/fail diagnostics.
"""

import json
import os
import sys
from typing import Dict, Any, List

# Ensure repository root is on path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState

CHATS = [
    {
        "id": "chat_01",
        "title": "Chat 1: A3 office, wrong volume, then correction",
        "category": "Office printers (A4 / A3)",
        "turns": [
            "hi",
            "need a3 printer for office",
            "its 40",
            "sorry i meant 400 per day",
            "both models have scan?",
        ],
        "pass_criteria": "Turn 3 accepts 40 and doesn't re-ask. Turn 4 replaces the old value with 400. Turn 5 answers for both models shown (WF-C878R and WF-C879R).",
    },
    {
        "id": "chat_02",
        "title": "Chat 2: A4 office, budget and comparison",
        "category": "Office printers (A4 / A3)",
        "turns": [
            "i want a4 colour printer with scanner",
            "50 pages a day",
            "which is cheaper",
            "compare first two",
            "ok give quote for the second",
        ],
        "pass_criteria": "Turn 3 gives no invented prices, only the catalogue price or the sales-desk referral. Turn 5 targets the right second product.",
    },
    {
        "id": "chat_03",
        "title": "Chat 3: 40 ppm vs 40 pages",
        "category": "Office printers (A4 / A3)",
        "turns": [
            "a3 office",
            "40 ppm",
            "how many pages per day is it good for",
            "and the c878r?",
        ],
        "pass_criteria": "'40 ppm' is treated as speed, and turn 4 switches to the C878R.",
    },
    {
        "id": "chat_04",
        "title": "Chat 4: the typo case from your transcript",
        "category": "Epson SureColor F100 (sublimation)",
        "turns": [
            "i need f100 consubales",
            "price?",
            "any other ink for it",
            "what paper size it supports",
        ],
        "pass_criteria": "Turn 1 returns F100 consumables, not the spec card. Turn 2 refers to the sales desk or the published price. Turns 3 and 4 stay on the F100.",
    },
    {
        "id": "chat_05",
        "title": "Chat 5: topic switching",
        "category": "Epson SureColor F100 (sublimation)",
        "turns": [
            "sublimation printer for mugs and t-shirts",
            "a4 only?",
            "and for the a3 office printer?",
            "back to the f100 – ink bottle size",
        ],
        "pass_criteria": "Turn 3 switches to A3 office. Turn 4 comes back to the F100 without losing context.",
    },
    {
        "id": "chat_06",
        "title": "Chat 6: event photographer, step by step",
        "category": "Citizen photo booth (CX-02 / CY-02 / CZ-01)",
        "turns": [
            "photo booth printer for events",
            "4x6 prints",
            "also 6x8 sometimes",
            "cx02 yield?",
            "and cy02?",
        ],
        "pass_criteria": "Turn 3 keeps 4x6 and adds 6x8 (nothing is dropped). Turn 5 answers for the CY-02 and doesn't repeat the CX-02 answer.",
    },
    {
        "id": "chat_07",
        "title": "Chat 7: ambiguous model typo",
        "category": "Citizen photo booth (CX-02 / CY-02 / CZ-01)",
        "turns": [
            "cz02 printer",
            "the first one",
            "media for it",
        ],
        "pass_criteria": "Turn 1 asks which model is meant (CZ-01 or something else) instead of picking silently. Turn 2 resolves against the options shown.",
    },
    {
        "id": "chat_08",
        "title": "Chat 8: pattern change",
        "category": "Citizen photo booth (CX-02 / CY-02 / CZ-01)",
        "turns": [
            "cz01 can i change print pattern",
            "how",
            "what ribbon needed",
        ],
        "pass_criteria": "Answers come from the catalogue, with 'not available' stated where there's no data.",
    },
    {
        "id": "chat_09",
        "title": "Chat 9: CAD / large format",
        "category": "CAD / large format",
        "turns": [
            "cad printer",
            "24",
            "no scanner needed",
            "actually make it 36",
            "roll sizes?",
        ],
        "pass_criteria": "Turn 2 treats '24' as inches because a size question is pending. Turn 4 updates the width and keeps 'no scanner'. Turn 5 gives rolls for the 36-inch.",
    },
    {
        "id": "chat_10",
        "title": "Chat 10: photography large format",
        "category": "CAD / large format",
        "turns": [
            "professional photo printer 44 inch",
            "with scanner",
            "dual roll?",
            "show only 24 inch",
        ],
        "pass_criteria": "Turn 2 adds the scanner requirement. Turn 4 resets the width and keeps photography.",
    },
    {
        "id": "chat_11",
        "title": "Chat 11: wrong spellings",
        "category": "Consumables only",
        "turns": [
            "need ink for epson c878",
            "yellow one price",
            "maintainence box also",
            "total for all 4 colors",
        ],
        "pass_criteria": "The yellow price comes from the catalogue. Turn 4 sums the right items and doesn't invent prices.",
    },
    {
        "id": "chat_12",
        "title": "Chat 12: two inputs at once",
        "category": "Consumables only",
        "turns": [
            "ink for f100 and also maintenance box for c878r",
            "which one is cheaper",
        ],
        "pass_criteria": "Turn 1 answers both parts. Turn 2 compares only the two items from turn 1.",
    },
    {
        "id": "chat_13",
        "title": "Chat 13: Hinglish",
        "category": "Other languages and messy input",
        "turns": [
            "mujhe office ke liye a3 printer chahiye",
            "roz 100 pages",
            "dono ka spec batao",
        ],
        "pass_criteria": "The same flow works as in English, and 'dono' resolves to both products.",
    },
    {
        "id": "chat_14",
        "title": "Chat 14: Arabic",
        "category": "Other languages and messy input",
        "turns": [
            "أريد طابعة مكتبية",
            "A3",
            "كم السعر؟",
        ],
        "pass_criteria": "The category is office printer, A3 is kept, and the price answer follows your price guardrail.",
    },
    {
        "id": "chat_15",
        "title": "Chat 15: Malayalam",
        "category": "Other languages and messy input",
        "turns": [
            "enikku photo printer venam",
            "4x6",
            "ink evide kittum?",
        ],
        "pass_criteria": "The photo category and size are understood, and the consumables answer is correct.",
    },
    {
        "id": "chat_16",
        "title": "Chat 16: policy and refusals",
        "category": "Guardrails and bad input",
        "turns": [
            "what are your prices?",
            "give me 20% discount",
            "do you sell HP LaserJet?",
            "ok then recommend something",
        ],
        "pass_criteria": "No invented prices, discounts or models. The refusals are polite, and the bot steers back to the catalogue.",
    },
    {
        "id": "chat_17",
        "title": "Chat 17: junk and fragments",
        "category": "Guardrails and bad input",
        "turns": [
            "😀",
            "24",
            "?",
            "a3",
            "thanks bye",
        ],
        "pass_criteria": "There are no wrong guesses, only clarification. Turn 5 closes cleanly.",
    },
    {
        "id": "chat_18",
        "title": "Chat 18: customer changes mind mid-way",
        "category": "Guardrails and bad input",
        "turns": [
            "a4 office printer",
            "100 pages",
            "no wait not office, photo booth",
            "4x6",
            "cheapest one?",
        ],
        "pass_criteria": "Customer changes category mid-way from A4 office to photo booth 4x6; bot respects change.",
    },
]


def run_all_chats() -> Dict[str, Any]:
    orch = Orchestrator()
    results = {}

    for chat_cfg in CHATS:
        chat_id = chat_cfg["id"]
        title = chat_cfg["title"]
        category = chat_cfg["category"]
        turns = chat_cfg["turns"]
        pass_crit = chat_cfg["pass_criteria"]

        print(f"\n========================================================")
        print(f"RUNNING {title} ({category})")
        print(f"========================================================")

        state = ConversationState(session_id=chat_id)
        chat_record = {
            "title": title,
            "category": category,
            "pass_criteria": pass_crit,
            "turns": [],
        }

        for idx, user_msg in enumerate(turns, 1):
            res = orch.process_turn(user_msg, state=state)
            reply = res.get("reply", "")
            chips = res.get("suggested_chips", [])
            product_cards = [c.get("id") or c.get("model") for c in res.get("product_cards", [])]
            consumable_cards = [c.get("id") or c.get("name") for c in res.get("consumable_cards", [])]
            source = res.get("source", "")
            latency = res.get("latency_ms", 0)

            turn_info = {
                "turn": idx,
                "user_message": user_msg,
                "reply": reply,
                "chips": chips,
                "product_cards": product_cards,
                "consumable_cards": consumable_cards,
                "source": source,
                "latency_ms": latency,
                "state_category": state.category,
                "state_active_product": state.active_product_id,
                "state_requirements": dict(state.requirements or {}),
            }
            chat_record["turns"].append(turn_info)

            print(f"\n--- Turn {idx}: '{user_msg}' ---")
            print(f"Reply: {reply[:150]}...")
            print(f"Cards: {product_cards} | Consumables: {consumable_cards}")
            print(f"Category: {state.category} | Reqs: {state.requirements}")

        results[chat_id] = chat_record

    return results


if __name__ == "__main__":
    out_dir = os.path.join(repo_root, "data")
    os.makedirs(out_dir, exist_ok=True)
    all_res = run_all_chats()
    out_file = os.path.join(out_dir, "eval_18_chats_raw_output.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False)
    print(f"\nSaved raw outputs for all 18 chats to {out_file}")
