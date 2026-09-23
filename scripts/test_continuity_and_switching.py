#!/usr/bin/env python3
"""
Test script evaluating Continuity, Switching, and Out-of-Catalogue questions
from real previous database chat sessions against the live SalesAI service.
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5050/api/chat"

SESSIONS = [
    {
        "name": "TEST 1: Continuity & Anaphoric Reference Resolution ('it', 'this machine', memory recall)",
        "session_id": f"test-cont-{int(time.time())}",
        "turns": [
            "I need Epson SureColor SC-P6500D",
            "does it support wifi?",
            "what ink does this machine use?",
            "the last time I told one printer which one?"
        ]
    },
    {
        "name": "TEST 2: Category Switching (Scanner -> Printer discovery)",
        "session_id": f"test-switch-cat-{int(time.time())}",
        "turns": [
            "i need scanner",
            "both",
            "i want to buy a printer"
        ]
    },
    {
        "name": "TEST 3: Product & Consumable Switching ('what about P900')",
        "session_id": f"test-switch-prod-{int(time.time())}",
        "turns": [
            "i need consumable for f100",
            "what about p900"
        ]
    },
    {
        "name": "TEST 4: Out-of-Catalogue Inquiry (Canon TM-300 vs TX-3100)",
        "session_id": f"test-out-of-cat-{int(time.time())}",
        "turns": [
            "Can someone help me choose between TM-300 and TX-3100?"
        ]
    }
]

def run_evaluation():
    print("=" * 85)
    print(" EVALUATION: CONTINUITY, SWITCHING & OUT-OF-CATALOGUE QUESTIONS")
    print(f" Target Endpoint: {BASE_URL}")
    print("=" * 85)

    all_results = []

    for test_idx, sess in enumerate(SESSIONS, 1):
        print(f"\n{'#' * 85}")
        print(f" {sess['name']}")
        print(f" Session ID: {sess['session_id']}")
        print(f"{'#' * 85}")

        session_turns_result = []

        for turn_idx, user_msg in enumerate(sess["turns"], 1):
            print(f"\n  [Turn {turn_idx}/{len(sess['turns'])}] User: \"{user_msg}\"")
            start = time.time()
            try:
                resp = requests.post(
                    BASE_URL,
                    json={"message": user_msg, "session_id": sess["session_id"]},
                    timeout=90
                )
                elapsed = time.time() - start

                if resp.status_code == 200:
                    data = resp.json()
                    reply = data.get("reply", "")
                    agent = data.get("active_agent", {}).get("name", "Unknown Agent")
                    source = data.get("source", "unknown")
                    cards = [c.get("name") or c.get("model") or c.get("id") for c in data.get("product_cards", [])]
                    chips = data.get("suggested_chips", [])

                    print(f"  -> Agent: {agent} | Route: {source} | Elapsed: {elapsed:.2f}s")
                    print(f"  -> Reply:\n     {reply}")
                    if cards:
                        print(f"  -> Product Cards: {cards}")
                    if chips:
                        print(f"  -> Suggested Chips: {chips}")

                    session_turns_result.append({
                        "turn": turn_idx,
                        "user": user_msg,
                        "agent": agent,
                        "route": source,
                        "elapsed": elapsed,
                        "reply": reply,
                        "cards": cards,
                        "chips": chips
                    })
                else:
                    print(f"  -> ERROR HTTP {resp.status_code}: {resp.text[:200]}")
                    session_turns_result.append({
                        "turn": turn_idx,
                        "user": user_msg,
                        "error": f"HTTP {resp.status_code}"
                    })
            except Exception as e:
                print(f"  -> EXCEPTION: {e}")
                session_turns_result.append({
                    "turn": turn_idx,
                    "user": user_msg,
                    "error": str(e)
                })

        all_results.append({
            "test_name": sess["name"],
            "session_id": sess["session_id"],
            "turns": session_turns_result
        })

    with open("scripts/continuity_switching_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n" + "=" * 85)
    print(" ALL CONTINUITY & SWITCHING TESTS COMPLETED")
    print(" Detailed report saved to scripts/continuity_switching_results.json")
    print("=" * 85)

if __name__ == "__main__":
    run_evaluation()
