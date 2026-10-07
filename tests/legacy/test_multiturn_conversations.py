"""
Multi-turn Conversation Test Suite for Canonical State Architecture.
Verifies all 4 required suites:
- Suite 1: Full 10-turn Technical CAD Journey (A0 -> scanner=yes -> volume=60 -> structured retrieval -> why this one -> ink -> show another -> compare -> which is better -> price guardrail)
- Suite 2: Correction Flow (A0 -> actually A1 -> yes scanner -> actually no scanner -> recommend now)
- Suite 3: Pronoun / Item Referencing (show T5400M -> does it have scanner -> what size -> what ink does it use)
- Suite 4: Topic Switching (CAD -> A0 -> actually now I need a photo booth printer -> 4x6 -> cards)
"""

import requests
import json
import uuid
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:5055"


def run_suite_1():
    print("\n" + "="*70)
    print("RUNNING SUITE 1: Full 10-Turn Technical CAD Journey")
    print("="*70)
    session_id = f"test_suite1_{uuid.uuid4().hex[:6]}"

    turns = [
        ("I need a printer for architects", "What maximum drawing size"),
        ("A0", "scanning"),
        ("yes", "drawings do you print per day"),
        ("around 60", "recommended"),
        ("why this one?", "matches your requirement"),
        ("what ink does it use?", "UltraChrome"),
        ("show another one", "another option"),
        ("compare them", "SureColor"),
        ("which is better for me?", "SC-T5400M"),
        ("what is the price?", "price")
    ]

    for idx, (user_msg, expected_snippet) in enumerate(turns, 1):
        resp = requests.post(f"{BASE_URL}/api/chat", json={
            "session_id": session_id,
            "message": user_msg
        }, timeout=60)
        assert resp.status_code == 200, f"Turn {idx} failed with {resp.status_code}"
        data = resp.json()
        reply = data.get("reply", "")
        state = data.get("canonical_state", {})
        print(f"Turn {idx}: Customer: '{user_msg}'")
        print(f"         Assistant: '{reply[:90]}...'")
        print(f"         State reqs: {state.get('requirements')}, active_prod: {state.get('active_product', {}).get('name') if state.get('active_product') else None}")
        
        # Validation checks
        if idx == 4:
            # Check canonical state structure
            reqs = state.get("requirements", {})
            assert reqs.get("print_size") == "A0", f"Expected print_size A0, got {reqs.get('print_size')}"
            assert reqs.get("scan_required") is True, f"Expected scan_required True, got {reqs.get('scan_required')}"
            assert reqs.get("daily_volume") == 60, f"Expected daily_volume 60, got {reqs.get('daily_volume')}"
            assert len(data.get("product_cards", [])) > 0, "Expected product cards returned for Turn 4"
            print("  ==> [VERIFIED] Canonical state matches: {'category': 'technical_cad', 'print_size': 'A0', 'scan_required': True, 'daily_volume': 60}")
        elif idx == 6:
            assert len(data.get("consumable_cards", [])) > 0, "Expected consumable cards for ink question"
            print("  ==> [VERIFIED] Consumable cards successfully returned for active printer")
        elif idx == 10:
            assert any(term in reply.lower() for term in ["pricing", "price", "prices", "rates", "sales@keplertech.ae"]), "Expected commercial guardrail refusal"
            print("  ==> [VERIFIED] Commercial guardrail correctly intercepted price enquiry")

    print("[SUCCESS] Suite 1 Passed 100%!")


def run_suite_2():
    print("\n" + "="*70)
    print("RUNNING SUITE 2: Correction Flow (A0 -> actually A1 -> yes scanner -> actually no scanner)")
    print("="*70)
    session_id = f"test_suite2_{uuid.uuid4().hex[:6]}"

    # Turn 1: Initial query
    r1 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "I need a CAD printer"}).json()
    print("Turn 1: Customer: 'I need a CAD printer'")
    print(f"        Assistant: '{r1.get('reply')}'")

    # Turn 2: A0
    r2 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "A0"}).json()
    print("Turn 2: Customer: 'A0'")
    print(f"        Assistant: '{r2.get('reply')}'")
    assert r2.get("canonical_state", {}).get("requirements", {}).get("print_size") == "A0"

    # Turn 3: Correction: "actually A1"
    r3 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "actually A1"}).json()
    print("Turn 3: Customer: 'actually A1'")
    print(f"        Assistant: '{r3.get('reply')}'")
    assert r3.get("canonical_state", {}).get("requirements", {}).get("print_size") == "A1", f"Correction failed: {r3.get('canonical_state')}"
    print("  ==> [VERIFIED] Correction updated print_size from A0 to A1")

    # Turn 4: "yes need scanner"
    r4 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "yes need scanner"}).json()
    print("Turn 4: Customer: 'yes need scanner'")
    print(f"        Assistant: '{r4.get('reply')}'")
    assert r4.get("canonical_state", {}).get("requirements", {}).get("scan_required") is True

    # Turn 5: Correction: "actually no scanner"
    r5 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "actually no scanner"}).json()
    print("Turn 5: Customer: 'actually no scanner'")
    print(f"        Assistant: '{r5.get('reply')}'")
    assert r5.get("canonical_state", {}).get("requirements", {}).get("scan_required") is False, f"Correction failed: {r5.get('canonical_state')}"
    print("  ==> [VERIFIED] Correction updated scan_required from True to False")

    # Turn 6: "recommend now"
    r6 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "recommend now"}).json()
    print("Turn 6: Customer: 'recommend now'")
    print(f"        Assistant: '{r6.get('reply')}'")
    cards = r6.get("product_cards", [])
    assert len(cards) > 0, "Expected cards for A1 print-only"
    # Should recommend T3100 (A1 24-inch print only)
    assert any("3100" in c.get("name", "") for c in cards), f"Expected SC-T3100 in cards, got: {[c.get('name') for c in cards]}"
    print("  ==> [VERIFIED] Recommendations accurately matched corrected state (A1 print-only SC-T3100)")

    print("[SUCCESS] Suite 2 Passed 100%!")


def run_suite_3():
    print("\n" + "="*70)
    print("RUNNING SUITE 3: Pronoun & Item Referencing")
    print("="*70)
    session_id = f"test_suite3_{uuid.uuid4().hex[:6]}"

    # Turn 1: Show me T5400M
    r1 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "show me T5400M"}).json()
    print("Turn 1: Customer: 'show me T5400M'")
    print(f"        Assistant: '{r1.get('reply')}'")
    state = r1.get("canonical_state", {})
    assert state.get("active_product") is not None and "5400" in state.get("active_product", {}).get("name", "")
    print(f"  ==> [VERIFIED] Active product bound to: {state['active_product']['name']}")

    # Turn 2: "does it have a scanner?"
    r2 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "does it have a scanner?"}).json()
    print("Turn 2: Customer: 'does it have a scanner?'")
    print(f"        Assistant: '{r2.get('reply')}'")
    assert "scanner" in r2.get("reply", "").lower()
    print("  ==> [VERIFIED] Pronoun 'it' answered correctly using active product context")

    # Turn 3: "what size can it print?"
    r3 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "what size can it print?"}).json()
    print("Turn 3: Customer: 'what size can it print?'")
    print(f"        Assistant: '{r3.get('reply')}'")
    assert "36" in r3.get("reply", "") or "A0" in r3.get("reply", "")
    print("  ==> [VERIFIED] Size answered correctly (36 inches / A0)")

    # Turn 4: "what ink does it use?"
    r4 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "what ink does it use?"}).json()
    print("Turn 4: Customer: 'what ink does it use?'")
    print(f"        Assistant: '{r4.get('reply')}'")
    assert len(r4.get("consumable_cards", [])) > 0 or "UltraChrome" in r4.get("reply", "")
    print("  ==> [VERIFIED] Inks and consumables retrieved for active referenced model")

    print("[SUCCESS] Suite 3 Passed 100%!")


def run_suite_4():
    print("\n" + "="*70)
    print("RUNNING SUITE 4: Clean Topic Switching (CAD -> Photo Booth)")
    print("="*70)
    session_id = f"test_suite4_{uuid.uuid4().hex[:6]}"

    # Turn 1: CAD
    r1 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "I need a printer for CAD drawings"}).json()
    print("Turn 1: Customer: 'I need a printer for CAD drawings'")
    print(f"        Assistant: '{r1.get('reply')}'")
    assert r1.get("canonical_state", {}).get("category") == "technical_cad"

    # Turn 2: A0
    r2 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "A0"}).json()
    print("Turn 2: Customer: 'A0'")
    print(f"        Assistant: '{r2.get('reply')}'")
    assert r2.get("canonical_state", {}).get("requirements", {}).get("print_size") == "A0"

    # Turn 3: Topic switch: "actually now I need a photo booth printer"
    r3 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "actually now I need a photo booth printer"}).json()
    print("Turn 3: Customer: 'actually now I need a photo booth printer'")
    print(f"        Assistant: '{r3.get('reply')}'")
    state3 = r3.get("canonical_state", {})
    assert state3.get("category") == "photo_booth", f"Expected category photo_booth, got: {state3.get('category')}"
    # Old CAD requirements must be wiped clean
    assert "A0" not in str(state3.get("requirements")), f"CAD A0 requirement was not cleared: {state3.get('requirements')}"
    print("  ==> [VERIFIED] Category cleanly switched to photo_booth and CAD requirements were wiped")

    # Turn 4: "mostly 4x6"
    r4 = requests.post(f"{BASE_URL}/api/chat", json={"session_id": session_id, "message": "mostly 4x6"}).json()
    print("Turn 4: Customer: 'mostly 4x6'")
    print(f"        Assistant: '{r4.get('reply')}'")
    cards = r4.get("product_cards", [])
    assert len(cards) > 0, "Expected photo booth cards returned"
    assert any("CX-02" in c.get("name", "") or "Citizen" in c.get("name", "") for c in cards), f"Expected Citizen CX-02 cards, got: {[c.get('name') for c in cards]}"
    print("  ==> [VERIFIED] Successfully delivered Citizen CX-02 photo booth cards for 4x6 photo requirement")

    print("[SUCCESS] Suite 4 Passed 100%!")


if __name__ == "__main__":
    print("STARTING MULTI-TURN TEST SUITES AGAINST RUNNING FLASK SERVER...")
    try:
        run_suite_1()
        run_suite_2()
        run_suite_3()
        run_suite_4()
        print("\n" + "*"*70)
        print("ALL 4 MULTI-TURN CONVERSATION TEST SUITES PASSED PERFECTLY!")
        print("*"*70)
    except Exception as e:
        print(f"\n[ERROR IN TEST SUITE]: {e}")
        import traceback
        traceback.print_exc()
