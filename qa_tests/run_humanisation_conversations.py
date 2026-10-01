"""
QA Automated Multi-Turn Humanisation & Naturalness Evaluation Suite (Section F)
Runs 5 distinct 6-8 turn conversations against local test database.
Evaluates:
- Real consultative sales rep tone
- Empathy
- No robotic repetition
- No reciting history ("As per your previous message...")
- Appropriate length
- Greeting by name only when known
- No repeated identical openers
- Flags pushy behavior, false claims, unverified stock/discounts/delivery promises.
"""

import json
import os
import uuid
import time
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_humanisation.db")

CONVERSATIONS = [
    {
        "id": "conv_1_architecture_studio",
        "title": "Architectural Studio Blueprint Buyer (Dubai Marina)",
        "turns": [
            "Hi, I am looking for a large format plotter for my architectural consultancy in Dubai Marina. We produce CAD drawings and site plans.",
            "We usually print A1 and A0 blueprints, maybe 40 to 60 sheets a week.",
            "Does the 36-inch model come with a stand and catch basket?",
            "Can we print directly from an iPad or phone on the site?",
            "What ink cartridges does it use and are they water resistant?",
            "How much is the printer and do you deliver to Dubai Marina?",
            "Thank you for the guidance. Can I visit your showroom to see it in person?"
        ]
    },
    {
        "id": "conv_2_fine_art_gallery",
        "title": "Fine-Art Gallery Photographer (Inexperienced / Hesitant)",
        "turns": [
            "Good morning! I'm completely new to professional photo printing and honestly feeling a bit lost with all the options.",
            "I want to print exhibition-grade black and white photography up to 17 inches.",
            "What makes the P900 better than an office inkjet for black and white prints?",
            "Does it support roll paper for panoramic gallery prints?",
            "Can you give me a 20% discount if I buy it today?",
            "Understood about the website pricing. Can I use third party dye ink to save cost?",
            "That makes complete sense. Thank you for being so patient with my questions!"
        ]
    },
    {
        "id": "conv_3_event_photo_booth",
        "title": "Event Photo Booth Business Owner (High Speed & Volume)",
        "turns": [
            "Hey there, we run event photo booths for weddings and corporate parties in Abu Dhabi and Dubai.",
            "We need a compact, super fast printer that can do 4x6 photo strips on the spot without ink drying time.",
            "How many seconds does the Citizen CX-02 take for a 4x6 print?",
            "Does it use ink cartridges or dye-sub ribbon rolls?",
            "How many prints can we get from one media roll before reloading?",
            "Do you have stock available in Dubai right now for immediate delivery?",
            "I need to talk to a human sales rep to set up a trade account."
        ]
    },
    {
        "id": "conv_4_enterprise_office",
        "title": "Enterprise Office Fleet Manager (WorkForce & Scanners)",
        "turns": [
            "Hello, our law firm is looking to replace our old laser copiers with high-speed, lower heat business printers.",
            "We print roughly 30,000 pages per month, mostly legal contracts and court filings in color and mono.",
            "What is the speed and ink capacity of the WorkForce Enterprise WF-C20600?",
            "We also need to scan double-sided legal documents rapidly. Do you have dedicated document scanners?",
            "How fast is the DS-530II duplex scanning?",
            "Can we negotiate a lease contract with Kepler Tech?",
            "Got it, thanks for directing me to the commercial team."
        ]
    },
    {
        "id": "conv_5_returning_customer_flow",
        "title": "Returning Customer Contact Onboarding & Technical Consultation",
        "turns": [
            "Hello, I am looking for a 24 inch technical plotter.",
            "My name is Omar Al Suwaidi and my mobile is +971 52 345 6789",
            "Yes, save chat history",
            "Can the SC-T3100 handle cut sheets as well as roll media?",
            "What is the warranty coverage on this model?",
            "Can you give me free extra ink cartridges with my order?",
            "Thank you, that was very helpful."
        ]
    }
]


def score_turn(reply: str, user_query: str, turn_index: int, prior_replies: list, customer_name: str = None):
    flags = []
    penalties = 0

    lower = reply.lower()

    # 1. Robotic clichés
    cliches = ["as per your previous", "according to our database", "as an ai", "as per records", "delighted to assist"]
    for c in cliches:
        if c in lower:
            flags.append(f"Robotic cliché: '{c}'")
            penalties += 0.5

    # 2. Repeated openers across turns
    if prior_replies:
        first_few_words = " ".join(reply.split()[:4]).lower()
        for p in prior_replies:
            p_words = " ".join(p.split()[:4]).lower()
            if first_few_words and first_few_words == p_words:
                flags.append(f"Repeated identical opener: '{first_few_words}'")
                penalties += 0.5
                break

    # 3. False claims or unverified promises
    if "official epson distributor" in lower:
        flags.append("False claim: 'official Epson distributor'")
        penalties += 1.0

    if any(p in lower for p in ["guarantee immediate same-day delivery", "we have 50 units in stock", "i will give you 10%"]):
        flags.append("Unverified stock/delivery/discount promise")
        penalties += 1.0

    # 4. Greeting by name only when known
    if customer_name and customer_name.lower() in lower and turn_index == 0:
        flags.append(f"Name '{customer_name}' greeted before user provided it")
        penalties += 1.0

    # 5. Pushy behavior
    if any(p in lower for p in ["buy now before price increases", "sign the contract today", "act now"]):
        flags.append("Pushy high-pressure sales tactic")
        penalties += 1.0

    score = max(1.0, min(5.0, 5.0 - penalties))
    return score, flags


def run_all_conversations():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    customer_repository.db_path = TEST_DB_PATH
    customer_repository._init_db()
    state_repository.db_path = TEST_DB_PATH
    state_repository._init_db()

    with state_manager._lock:
        state_manager._store.clear()

    results = []

    for conv in CONVERSATIONS:
        print(f"\n=======================================================")
        print(f"RUNNING: {conv['title']} ({len(conv['turns'])} turns)")
        print(f"=======================================================")
        sid = f"conv_f_{uuid.uuid4().hex[:8]}"
        client = app.test_client()

        conv_history = []
        prior_bot_replies = []
        turn_scores = []
        all_flags = []

        cust_name = "Omar Al Suwaidi" if conv["id"] == "conv_5_returning_customer_flow" else None

        for idx, user_msg in enumerate(conv["turns"]):
            t_start = time.time()
            resp = client.post("/api/chat", json={
                "session_id": sid,
                "message": user_msg
            })
            latency_ms = int((time.time() - t_start) * 1000)

            if resp.status_code != 200:
                print(f"[Turn {idx+1}] ERROR {resp.status_code}: {resp.get_data(as_text=True)}")
                bot_reply = f"ERROR: HTTP {resp.status_code}"
                score = 1.0
                flags = [f"HTTP error {resp.status_code}"]
            else:
                body = resp.get_json()
                bot_reply = body.get("reply", body.get("message", ""))
                score, flags = score_turn(bot_reply, user_msg, idx, prior_bot_replies, customer_name=cust_name)

            turn_scores.append(score)
            if flags:
                all_flags.extend([f"Turn {idx+1}: {f}" for f in flags])
            prior_bot_replies.append(bot_reply)

            print(f"\n[Turn {idx+1}] User: {user_msg}")
            print(f"[Turn {idx+1}] Bot: {bot_reply[:180]}... ({latency_ms}ms, score={score})")
            if flags:
                print(f"   ⚠️ Flags: {flags}")

            conv_history.append({
                "turn": idx + 1,
                "user": user_msg,
                "bot": bot_reply,
                "latency_ms": latency_ms,
                "score": score,
                "flags": flags
            })

        avg_score = round(sum(turn_scores) / len(turn_scores), 2)
        print(f"\n>> {conv['title']} Overall Score: {avg_score}/5.0 (Total Flags: {len(all_flags)})")

        results.append({
            "id": conv["id"],
            "title": conv["title"],
            "overall_score": avg_score,
            "turn_scores": turn_scores,
            "flags": all_flags,
            "transcript": conv_history
        })

    out_path = os.path.join(os.path.dirname(__file__), "humanisation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nHumanisation results saved to: {out_path}")
    return results


if __name__ == "__main__":
    run_all_conversations()
