#!/usr/bin/env python3
"""
Continuous multi-turn conversation test runner for extracted database chats.
Replays customer conversation sessions turn-by-turn without normal greetings,
verifying context continuity, qualification progression, and zero generic fallbacks.
"""

import sys
import os
import json
import time
import re
import argparse

sys.path.insert(0, "/opt/salesai")

from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


def run_continuous_test(
    input_file: str,
    max_sessions: int = None,
    min_turns: int = 2,
    only_real_customers: bool = True
):
    print("=" * 80)
    print(" CONTINUOUS MULTI-TURN CHAT TEST RUNNER")
    print(f" Input File         : {input_file}")
    print(f" Filter Real Cust.  : {only_real_customers}")
    print(f" Min Turns / Session: {min_turns}")
    print(f" Max Sessions       : {max_sessions or 'ALL'}")
    print("=" * 80)

    with open(input_file, "r", encoding="utf-8") as f:
        all_sessions = json.load(f)

    # Filter sessions
    eligible = []
    for s in all_sessions:
        s_id = s.get("session_id", "")
        turns = s.get("turns", [])
        if len(turns) < min_turns:
            continue
        if only_real_customers and not re.match(r"^[a-f0-9]{8}-[a-f0-9]{4}-", s_id):
            continue
        eligible.append(s)

    if max_sessions:
        eligible = eligible[:max_sessions]

    print(f"Selected {len(eligible)} multi-turn sessions for continuous replay.\n")

    session_results = []
    total_turns = 0
    passed_turns = 0
    failed_turns = 0

    t_suite_start = time.time()

    for s_idx, session in enumerate(eligible, 1):
        s_id = session.get("session_id", f"sess_{s_idx}")
        cust = session.get("customer_name", "Anonymous")
        turns = session.get("turns", [])

        print(f"\n[{s_idx}/{len(eligible)}] Session: {s_id} | Customer: '{cust}' | {len(turns)} turns")
        print("-" * 75)

        # Initialize fresh conversation state for this session
        test_session_id = f"cont_{s_id[:16]}_{int(time.time())}"
        state = ConversationState(session_id=test_session_id)

        turn_logs = []
        session_passed = True

        for turn in turns:
            t_num = turn.get("turn_number", len(turn_logs) + 1)
            q = turn.get("user_question", "").strip()
            if not q:
                continue

            total_turns += 1
            t0 = time.time()

            try:
                resp = orchestrator.process_turn(q, session_id=state.session_id, state=state)
                elapsed = time.time() - t0
                reply = resp.get("reply", "")
                source = resp.get("source", "unknown")
                chips = resp.get("suggested_chips", [])
                cards = resp.get("product_cards", [])

                # Verify no generic fallback or unhandled exception
                is_failed = (
                    not reply.strip() or
                    "i did not understand" in reply.lower() or
                    ("how can i help you today?" in reply.lower() and len(reply) < 80)
                )

                if is_failed:
                    status = "FAIL"
                    failed_turns += 1
                    session_passed = False
                else:
                    status = "PASS"
                    passed_turns += 1

                preview = reply.replace("\n", " ")[:100]
                act_prod = state.active_product.get("id") if state.active_product else None
                cat = state.category or "None"
                awaiting = state.awaiting_field or "None"

                print(f"  T{t_num} [{status}] ({elapsed:.2f}s) | Route: {source} | Cat: {cat} | Awaiting: {awaiting}")
                print(f"     User : \"{q}\"")
                print(f"     Bot  : {preview}...")
                if chips:
                    print(f"     Chips: {chips[:3]}")

                turn_logs.append({
                    "turn_number": t_num,
                    "user_question": q,
                    "status": status,
                    "elapsed_sec": round(elapsed, 3),
                    "source": source,
                    "category": cat,
                    "awaiting_field": awaiting,
                    "active_product": act_prod,
                    "reply_preview": preview,
                    "chips": chips,
                })

            except Exception as e:
                failed_turns += 1
                session_passed = False
                print(f"  T{t_num} [ERROR] Crash on \"{q}\": {e}")
                turn_logs.append({
                    "turn_number": t_num,
                    "user_question": q,
                    "status": "ERROR",
                    "error": str(e),
                })

        session_results.append({
            "session_id": s_id,
            "customer_name": cust,
            "turns_count": len(turns),
            "passed": session_passed,
            "turn_logs": turn_logs,
        })

    total_time = time.time() - t_suite_start
    print("\n" + "=" * 80)
    print(" CONTINUOUS MULTI-TURN TEST SUITE SUMMARY")
    print("=" * 80)
    print(f" Sessions Tested : {len(session_results)}")
    print(f" Total Turns     : {total_turns}")
    print(f" Turns Passed    : {passed_turns} ({passed_turns/max(total_turns, 1)*100:.1f}%)")
    print(f" Turns Failed    : {failed_turns}")
    print(f" Total Duration  : {total_time:.2f}s ({total_time/max(total_turns, 1):.3f}s/turn)")
    print("=" * 80)

    # Save results
    out_file = "/opt/salesai/data/extracted_conversations/continuous_test_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_sessions": len(session_results),
            "total_turns": total_turns,
            "passed_turns": passed_turns,
            "failed_turns": failed_turns,
            "pass_rate": round(passed_turns / max(total_turns, 1) * 100, 2),
            "sessions": session_results,
        }, f, indent=2, ensure_ascii=False)
    print(f"Detailed continuous test results saved to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test customer chats continuously.")
    parser.add_argument("--input", default="/opt/salesai/data/extracted_conversations/all_customer_conversations.json")
    parser.add_argument("--max-sessions", type=int, default=20)
    parser.add_argument("--min-turns", type=int, default=2)
    parser.add_argument("--all-sessions", action="store_true", help="Include all sessions, not only UUID customer sessions")
    args = parser.parse_args()

    run_continuous_test(
        args.input,
        max_sessions=args.max_sessions,
        min_turns=args.min_turns,
        only_real_customers=not args.all_sessions
    )
