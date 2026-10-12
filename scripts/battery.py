"""
Repeatable Dialogue Quality Battery Harness for Kepler Tech SalesAI.
Evaluates the 47-turn conversational battery across 19 scenarios offline
with Ollama mocked, measuring:
- generic_fallback_rate
- identical_consecutive_replies
- turns_with_next_step
- turns_with_cards
- leaked_template_count
- wrong_model_count
"""

import sys
import os
import json
import uuid
from difflib import SequenceMatcher
from unittest.mock import patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domain.conversation_state import ConversationState
from agent.orchestrator import Orchestrator
from ollama_client import ollama_client


# ── The 47-Turn Battery Scenarios (19 Conversations) ──────────────────────────
BATTERY_CONVERSATIONS = [
    {
        "id": "conv_01_spec_and_stand",
        "description": "Case 1 & 6: SC-T5100 raw display_name claim and stand honesty",
        "turns": [
            "tell me about the SC-T5100",
            "does it come with a stand?",
        ],
    },
    {
        "id": "conv_02_silent_fuzzy_substitution",
        "description": "Case 2: WF-C20600 speed query must not silently substitute WF-C21000",
        "turns": [
            "what is the speed of the WF-C20600",
        ],
    },
    {
        "id": "conv_03_delivery_questions",
        "description": "Case 3: Delivery questions (international, same-day, hours, pickup)",
        "turns": [
            "do you ship to india",
            "can you deliver today",
            "what are your showroom opening hours",
            "do you have store pickup in dubai",
        ],
    },
    {
        "id": "conv_04_blueprint_width",
        "description": "Case 4: A1 and A0 blueprints width resolution (largest size wins -> 36 inch)",
        "turns": [
            "We print A1 and A0 blueprints",
        ],
    },
    {
        "id": "conv_05_consumables_compatibility",
        "description": "Case 5: Ink shown, then follow-up 'this is suitable for f500'",
        "turns": [
            "i want ink for f100",
            "this is suitable for f500",
        ],
    },
    {
        "id": "conv_06_unlisted_variant_price",
        "description": "Case 7: Citizen CX-02W price inquiry (unlisted variant)",
        "turns": [
            "how much is the Citizen CX-02W",
        ],
    },
    {
        "id": "conv_07_p7500_ink_count",
        "description": "Case 8: SC-P7500 ink lookup must find all catalogue inks, not 0",
        "turns": [
            "what ink does the P7500 use",
        ],
    },
    {
        "id": "conv_08_direct_model_want",
        "description": "Case 9: Direct want 'I want the Epson SC-P900'",
        "turns": [
            "I want the Epson SC-P900",
        ],
    },
    {
        "id": "conv_09_model_comparisons",
        "description": "Case 10: Structured side-by-side comparisons",
        "turns": [
            "compare T5100 and T5700D",
            "compare SC-F100 and SC-F500",
        ],
    },
    {
        "id": "conv_10_cross_compatibility_referent",
        "description": "Case 11: Roll adapter referent compatibility check for P700",
        "turns": [
            "tell me about the P900 roll adapter",
            "is that compatible with the P700",
        ],
    },
    {
        "id": "conv_11_multi_intent",
        "description": "Case 12: Multi-intent query (price + delivery + speed)",
        "turns": [
            "price of AM-C4000 and do you deliver to Sharjah and how fast is it",
        ],
    },
    {
        "id": "conv_12_objections_short_replies_lead",
        "description": "Case 13 & 14: Objections, short options, lead capture, thanks",
        "turns": [
            "i need a photo printer",
            "it's too expensive",
            "okay I'll think about it",
            "the first one",
            "my name is Ali and number is 0501234567",
            "shukran",
        ],
    },
    {
        "id": "conv_13_mid_greeting_and_repeats",
        "description": "Case 15 & 16: Repeat handling, mid-conversation greeting, frustration",
        "turns": [
            "printer for office",
            "printer for office",
            "printer for office",
            "Hi",
            "this is useless",
        ],
    },
    {
        "id": "conv_14_office_qualification_flow",
        "description": "Case 17: Office qualification flowchart to leaf recommendation with cards",
        "turns": [
            "i need a printer for my office",
            "a3",
            "500 pages a day",
            "we need high speed printing",
        ],
    },
    {
        "id": "conv_15_short_choice_disambiguation",
        "description": "Short choice confirmations and numeric options",
        "turns": [
            "hello",
            "Printer",
            "yes",
            "2",
        ],
    },
    {
        "id": "conv_16_delivery_tracking_returns",
        "description": "Case 18 & Delivery: Tracking, returns, and support contact",
        "turns": [
            "how do I track my delivery",
            "what is your return policy",
            "who can I email for support",
        ],
    },
    {
        "id": "conv_17_cad_qualification_flow",
        "description": "CAD / Technical plotter qualification flowchart",
        "turns": [
            "i need a cad plotter",
            "36 inch",
        ],
    },
    {
        "id": "conv_18_sublimation_flow",
        "description": "Dye-sublimation apparel and gifts qualification flow",
        "turns": [
            "i want sublimation printer",
            "a4",
        ],
    },
    {
        "id": "conv_19_scanner_flow",
        "description": "Document and photo scanner qualification flow",
        "turns": [
            "i need a scanner",
            "photo & film",
            "a3 graphic arts",
        ],
    },
]


def run_battery():
    orchestrator = Orchestrator()

    total_turns = 0
    generic_fallbacks = 0
    identical_consecutive = 0
    turns_with_next_step = 0
    turns_with_cards = 0
    leaked_templates = 0
    wrong_model_count = 0

    results = []

    # Mock Ollama offline so all tests execute deterministically
    with patch.object(ollama_client, "classify", return_value={"success": False, "result": {}, "fallback_used": True}), \
         patch.object(ollama_client, "chat_completions", return_value={"choices": [{"message": {"content": ""}}]}), \
         patch.object(ollama_client, "generate", return_value={"response": ""}):

        for conv in BATTERY_CONVERSATIONS:
            sess_id = f"battery_{conv['id']}_{uuid.uuid4().hex[:6]}"
            state = ConversationState(session_id=sess_id)
            history = []
            prev_reply = ""

            conv_result = {
                "id": conv["id"],
                "description": conv["description"],
                "turns": [],
            }

            for user_input in conv["turns"]:
                total_turns += 1
                res = orchestrator.process_turn(user_input, session_id=sess_id, history=history, state=state)

                reply = res.get("reply", "") or ""
                chips = res.get("suggested_chips", []) or []
                prod_cards = res.get("product_cards", []) or []
                cons_cards = res.get("consumable_cards", []) or []
                source = res.get("source", "")

                # 1. Generic fallback check
                is_fallback = False
                if "How can I best assist you with Kepler Tech printing equipment? Please select a category" in reply:
                    is_fallback = True
                elif "Select a category to begin guided equipment qualification" in reply:
                    is_fallback = True
                if is_fallback:
                    generic_fallbacks += 1

                # 2. Identical consecutive reply check
                is_identical = False
                if prev_reply:
                    ratio = SequenceMatcher(None, reply.strip().lower(), prev_reply.strip().lower()).ratio()
                    if ratio >= 0.85:
                        identical_consecutive += 1
                        is_identical = True

                # 3. Turns with next step check
                has_next_step = False
                if chips or "?" in reply or "please " in reply.lower() or "would you like" in reply.lower():
                    turns_with_next_step += 1
                    has_next_step = True

                # 4. Turns with cards check
                has_cards = bool(prod_cards or cons_cards)
                if has_cards:
                    turns_with_cards += 1

                # 5. Leaked template check
                leaked_markers = [" = ", "display_name", "{step.", "None", "null", "{", "}"]
                has_leaked = any(m in reply for m in leaked_markers)
                if has_leaked:
                    leaked_templates += 1

                # 6. Wrong model substitution check
                is_wrong_model = False
                u_lower = user_input.lower()
                r_lower = reply.lower()
                if "wf-c20600" in u_lower and ("wf-c21000" in r_lower and "wf-c20600" not in r_lower):
                    is_wrong_model = True
                elif "cx-02w" in u_lower and ("cx-02" in r_lower and "cx-02w" not in r_lower and "not in our catalogue" not in r_lower):
                    is_wrong_model = True
                if is_wrong_model:
                    wrong_model_count += 1

                turn_record = {
                    "user": user_input,
                    "reply": reply,
                    "source": source,
                    "chips": chips,
                    "cards_count": len(prod_cards) + len(cons_cards),
                    "is_fallback": is_fallback,
                    "is_identical": is_identical,
                    "has_next_step": has_next_step,
                    "has_cards": has_cards,
                    "has_leaked": has_leaked,
                    "is_wrong_model": is_wrong_model,
                }
                conv_result["turns"].append(turn_record)

                # Update history and state
                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": reply})
                prev_reply = reply

            results.append(conv_result)

    generic_fallback_rate = (generic_fallbacks / total_turns * 100) if total_turns else 0.0
    next_step_rate = (turns_with_next_step / total_turns * 100) if total_turns else 0.0
    cards_rate = (turns_with_cards / total_turns * 100) if total_turns else 0.0

    summary = {
        "total_turns": total_turns,
        "generic_fallback_count": generic_fallbacks,
        "generic_fallback_rate": round(generic_fallback_rate, 2),
        "identical_consecutive_replies": identical_consecutive,
        "turns_with_next_step": turns_with_next_step,
        "next_step_rate": round(next_step_rate, 2),
        "turns_with_cards": turns_with_cards,
        "cards_rate": round(cards_rate, 2),
        "leaked_template_count": leaked_templates,
        "wrong_model_count": wrong_model_count,
    }

    print("=" * 60)
    print("BATTERY HARNESS EXECUTION SUMMARY (OFFLINE / OLLAMA MOCKED)")
    print("=" * 60)
    print(f"Total Turns Evaluated:            {total_turns}")
    print(f"Generic Fallback Count:          {generic_fallbacks} ({summary['generic_fallback_rate']}%)")
    print(f"Identical Consecutive Replies:   {identical_consecutive}")
    print(f"Turns With Next Step / Chips:    {turns_with_next_step} ({summary['next_step_rate']}%)")
    print(f"Turns With Product/Consumable Cards: {turns_with_cards} ({summary['cards_rate']}%)")
    print(f"Leaked Template Markers:         {leaked_templates}")
    print(f"Wrong Model Substitutions:       {wrong_model_count}")
    print("=" * 60)

    return summary, results


if __name__ == "__main__":
    summary, results = run_battery()
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "battery_latest_run.json")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "conversations": results}, f, indent=2)
        print(f"Detailed run saved to {output_path}")
    except Exception as e:
        print(f"Warning: could not save json output: {e}")
