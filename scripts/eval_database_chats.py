"""
Comprehensive Evaluation of Real Database Chats.
Replays actual user conversation trajectories from /opt/salesai/data/conversations.db.
Audits:
  1. Question resolution accuracy
  2. Multi-turn context continuity
  3. Consultative humanisation & tone
  4. Naturalisation vs robotic scriptiness
"""
import sys
import os
import json
import sqlite3

sys.path.insert(0, "/opt/salesai")

from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


def replay_chat(session_title, turns):
    print("=" * 80)
    print(f"REPLAYING SESSION: {session_title} ({len(turns)} turns)")
    print("=" * 80)
    
    state = ConversationState(session_id=f"eval_{session_title[:16]}")
    results = []
    
    for i, user_query in enumerate(turns, 1):
        resp = orchestrator.process_turn(user_query, session_id=state.session_id, state=state)
        reply = resp.get("reply", "")
        source = resp.get("source", "")
        agent = resp.get("active_agent", {}).get("name", "")
        act_p = state.active_product.get("id") if state.active_product else None
        
        results.append({
            "turn": i,
            "query": user_query,
            "reply": reply,
            "source": source,
            "agent": agent,
            "active_product": act_p,
            "awaiting_field": state.awaiting_field,
            "category": state.category,
            "requirements": dict(state.requirements),
        })
        
        print(f"\n--- [Turn {i}] USER: '{user_query}' ---")
        print(f"Routing Source : {source}")
        print(f"Active Agent   : {agent}")
        print(f"Category       : {state.category} | Awaiting: {state.awaiting_field}")
        print(f"Requirements   : {state.requirements}")
        print(f"Active Product : {act_p}")
        print(f"BOT RESPONSE ({len(reply)} chars):")
        print("-" * 50)
        print(reply)
        print("-" * 50)

    return results


if __name__ == "__main__":
    # Session 1: Most recent live user chat (a196e22c)
    turns_last_chat = [
        "hey",
        "i need a printer",
        "office",
        "a4",
        "1000",
        "soorry i think its100",
        "its fine also need a scanner",
        "i want a photo printer",
        "compact",
        "citizen",
        "compare this fout",
        "what is the price?",
        "warantee?",
        "Compare Citizen CX-02 and Citizen CZ-01",
        "i need CZ-01 and CX-02"
    ]
    
    replay_chat("last_chat_a196e22c", turns_last_chat)
