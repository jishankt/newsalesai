#!/usr/bin/env python3
"""
Test script running authentic previous customer questions from conversations.db
against the live SalesAI service to evaluate the Grounded LLM Response Composer.
"""

import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:5050/api/chat"

TEST_QUERIES = [
    {
        "category": "High Volume Production Recommendation",
        "question": "sorry i i have 3000 print per day, what you suggest?",
    },
    {
        "category": "Office Printing Discovery",
        "question": "i am looking for an office printer",
    },
    {
        "category": "Scanner Ingestion & Category Routing",
        "question": "i need scanner",
    },
    {
        "category": "Direct Model Comparison",
        "question": "Compare SC-T5100M and SC-T5700DM",
    },
    {
        "category": "Specific Model Ingestion & Specs",
        "question": "I need Epson SureColor SC-P6500D",
    },
    {
        "category": "Consumables & Cartridges",
        "question": "can ii have the replacement cartridges details of AM-C5000",
    },
    {
        "category": "Dimension & Form Factor Query",
        "question": "looking for 36\" one",
    },
    {
        "category": "Multi-Part Technical Query",
        "question": "does SC-T5700DM have scanner, can it print A0 and what ink does it use?",
    },
]

def run_tests():
    print("=" * 80)
    print(" TESTING LIVE SALESAI ENGINE WITH REAL HISTORICAL DATABASE QUESTIONS")
    print(f" Target Endpoint: {BASE_URL}")
    print("=" * 80)

    results = []

    for idx, item in enumerate(TEST_QUERIES, 1):
        q = item["question"]
        cat = item["category"]
        session_id = f"test-db-q-{idx}-{int(time.time())}"

        print(f"\n[{idx}/{len(TEST_QUERIES)}] Category: {cat}")
        print(f" Customer Question: \"{q}\"")

        start = time.time()
        try:
            resp = requests.post(
                BASE_URL,
                json={"message": q, "session_id": session_id},
                timeout=90
            )
            elapsed = time.time() - start

            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("reply", "")
                agent = data.get("active_agent", {}).get("name", "Unknown Agent")
                source = data.get("source", "unknown")
                cards = [c.get("name") or c.get("model") or c.get("id") for c in data.get("product_cards", [])]
                consumables = [c.get("name") or c.get("sku") for c in data.get("consumable_cards", [])]
                chips = data.get("suggested_chips", [])

                print(f" Elapsed: {elapsed:.2f}s | Agent: {agent} | Route: {source}")
                print(f" Generated Response:\n {reply}")
                if cards:
                    print(f" Product Cards ({len(cards)}): {', '.join(cards[:3])}")
                if consumables:
                    print(f" Consumables ({len(consumables)}): {', '.join(consumables[:4])}")
                if chips:
                    print(f" Suggested Chips: {chips}")

                results.append({
                    "category": cat,
                    "question": q,
                    "success": True,
                    "elapsed": elapsed,
                    "agent": agent,
                    "route": source,
                    "reply": reply,
                    "cards": cards,
                    "consumables": consumables,
                    "chips": chips,
                })
            else:
                print(f" FAILED (HTTP {resp.status_code}): {resp.text[:200]}")
                results.append({
                    "category": cat,
                    "question": q,
                    "success": False,
                    "error": f"HTTP {resp.status_code}",
                })

        except Exception as e:
            print(f" ERROR: {e}")
            results.append({
                "category": cat,
                "question": q,
                "success": False,
                "error": str(e),
            })

    print("\n" + "=" * 80)
    print(" SUMMARY OF EVALUATION RUN")
    print("=" * 80)
    passed = sum(1 for r in results if r.get("success"))
    print(f" Total Tested: {len(results)} | Passed: {passed} | Failed: {len(results) - passed}")

    with open("scripts/db_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(" Saved detailed results to scripts/db_test_results.json")

if __name__ == "__main__":
    run_tests()
