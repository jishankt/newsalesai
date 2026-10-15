import json

def analyze():
    with open("data/eval_18_chats_raw_output.json", "r") as f:
        data = json.load(f)

    for cid, cinfo in data.items():
        title = cinfo["title"]
        category = cinfo["category"]
        crit = cinfo["pass_criteria"]
        print("=" * 64)
        print(f"{title} ({category})")
        print(f"Goal / Pass Criteria: {crit}")
        print("-" * 64)
        for t in cinfo["turns"]:
            turn_no = t["turn"]
            user_msg = t["user_message"]
            reply_snip = t["reply"].replace("\n", " ").strip()
            cards = t.get("product_cards", [])
            cons = t.get("consumable_cards", [])
            state_cat = t.get("state_category")
            chips = t.get("chips", [])
            reqs = t.get("state_requirements", {})

            print(f"Turn {turn_no}: User: '{user_msg}'")
            print(f"   Reply: {reply_snip[:140]}...")
            if cards:
                print(f"   Cards ({len(cards)}): {cards}")
            if cons:
                print(f"   Consumables ({len(cons)}): {cons}")
            print(f"   State Category: {state_cat} | Reqs: {reqs}")
            print()

if __name__ == "__main__":
    analyze()
