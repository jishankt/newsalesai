#!/usr/bin/env python3
"""
Test runner for the 39 Representative Sample Customer Questions by Domain.
Domains:
  A: Technical CAD & AEC Plotters (6 questions)
  B: Citizen Event & Photo Booth Printers (6 questions)
  C: Commercial Pricing, Quotations & Discounts (6 questions)
  D: Consumables, Inks & Media (6 questions)
  E: Office & Enterprise Multifunction Systems (5 questions)
  F: Dye-Sublimation Gifts & Textiles (4 questions)
  G: Delivery, Showroom & Company Contacts (6 questions)
"""

import sys
import os
import json
import time

sys.path.insert(0, "/opt/salesai")

from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState

QUESTIONS = [
    # Domain A: Technical CAD & AEC Plotters
    {"domain": "A. Technical CAD & AEC Plotters", "qid": "A1", "q": "I need a CAD printer"},
    {"domain": "A. Technical CAD & AEC Plotters", "qid": "A2", "q": "What are the technical specs and print speed of the Epson SC-T3100?"},
    {"domain": "A. Technical CAD & AEC Plotters", "qid": "A3", "q": "Does the SC-T5100 come with a stand or is it desktop only?"},
    {"domain": "A. Technical CAD & AEC Plotters", "qid": "A4", "q": "Looking for a 36 inch plotter with integrated scanner for engineering blueprints"},
    {"domain": "A. Technical CAD & AEC Plotters", "qid": "A5", "q": "SC-T7700D dual roll CAD printer price and availability in UAE"},
    {"domain": "A. Technical CAD & AEC Plotters", "qid": "A6", "q": "Can I print on tracing paper and glossy film with SC-T5400?"},

    # Domain B: Citizen Event & Photo Booth Printers
    {"domain": "B. Citizen Event & Photo Booth Printers", "qid": "B1", "q": "Photo booth printer for events"},
    {"domain": "B. Citizen Event & Photo Booth Printers", "qid": "B2", "q": "What is the print speed and roll yield of the Citizen CX-02?"},
    {"domain": "B. Citizen Event & Photo Booth Printers", "qid": "B3", "q": "Can the CX-02 print both 4x6 and 6x8 without changing paper rolls?"},
    {"domain": "B. Citizen Event & Photo Booth Printers", "qid": "B4", "q": "Citizen CZ-01 compact event printer price"},
    {"domain": "B. Citizen Event & Photo Booth Printers", "qid": "B5", "q": "How heavy is the CZ-01 for portable photo booths?"},
    {"domain": "B. Citizen Event & Photo Booth Printers", "qid": "B6", "q": "Do you have the wide 8x10 Citizen CX-02W in stock?"},

    # Domain C: Commercial Pricing, Quotations & Discounts
    {"domain": "C. Commercial Pricing, Quotations & Discounts", "qid": "C1", "q": "How much does it cost?"},
    {"domain": "C. Commercial Pricing, Quotations & Discounts", "qid": "C2", "q": "Can you send me an official quotation for the SC-F100 with delivery to Dubai?"},
    {"domain": "C. Commercial Pricing, Quotations & Discounts", "qid": "C3", "q": "What is the price of Epson WF-C878R DWF including VAT?"},
    {"domain": "C. Commercial Pricing, Quotations & Discounts", "qid": "C4", "q": "Do you offer corporate or bulk discounts for 5 units?"},
    {"domain": "C. Commercial Pricing, Quotations & Discounts", "qid": "C5", "q": "Is pricing negotiable if we pay by bank transfer?"},
    {"domain": "C. Commercial Pricing, Quotations & Discounts", "qid": "C6", "q": "Cheapest A3 colour multifunction printer for office"},

    # Domain D: Consumables, Inks & Media
    {"domain": "D. Consumables, Inks & Media", "qid": "D1", "q": "I need ink for Epson SC-F100"},
    {"domain": "D. Consumables, Inks & Media", "qid": "D2", "q": "What is the part number for T49N black ink bottle?"},
    {"domain": "D. Consumables, Inks & Media", "qid": "D3", "q": "Need replacement ribbon and paper roll for Citizen CX-02"},
    {"domain": "D. Consumables, Inks & Media", "qid": "D4", "q": "Maintenance box for WorkForce WF-C878R price"},
    {"domain": "D. Consumables, Inks & Media", "qid": "D5", "q": "Can I use third-party compatible inks or does it void the warranty?"},
    {"domain": "D. Consumables, Inks & Media", "qid": "D6", "q": "List all compatible inks and yields for SC-P900"},

    # Domain E: Office & Enterprise Multifunction Systems
    {"domain": "E. Office & Enterprise Multifunction Systems", "qid": "E1", "q": "Printer for my office with 400 pages per day"},
    {"domain": "E. Office & Enterprise Multifunction Systems", "qid": "E2", "q": "A3 colour multifunction printer with scanning and automatic document feeder"},
    {"domain": "E. Office & Enterprise Multifunction Systems", "qid": "E3", "q": "How does the Epson Heat-Free PrecisionCore compare to laser copiers in electricity cost?"},
    {"domain": "E. Office & Enterprise Multifunction Systems", "qid": "E4", "q": "Epson WorkForce Enterprise AM-C4000 monthly duty cycle and print speed"},
    {"domain": "E. Office & Enterprise Multifunction Systems", "qid": "E5", "q": "Difference between WF-C878R and WF-C879R dual-scan speeds"},

    # Domain F: Dye-Sublimation Gifts & Textiles
    {"domain": "F. Dye-Sublimation Gifts & Textiles", "qid": "F1", "q": "Sublimation printer for mugs and t-shirts"},
    {"domain": "F. Dye-Sublimation Gifts & Textiles", "qid": "F2", "q": "Can the SC-F100 print directly onto 100% cotton t-shirts?"},
    {"domain": "F. Dye-Sublimation Gifts & Textiles", "qid": "F3", "q": "What is the difference between SC-F100 A4 desktop and SC-F500 24-inch roll?"},
    {"domain": "F. Dye-Sublimation Gifts & Textiles", "qid": "F4", "q": "Do you sell dye sublimation transfer paper sheets in UAE?"},

    # Domain G: Delivery, Showroom & Company Contacts
    {"domain": "G. Delivery, Showroom & Company Contacts", "qid": "G1", "q": "Where is your showroom in Dubai?"},
    {"domain": "G. Delivery, Showroom & Company Contacts", "qid": "G2", "q": "Can I visit your Khalid Bin Waleed showroom to see a live print demonstration?"},
    {"domain": "G. Delivery, Showroom & Company Contacts", "qid": "G3", "q": "What are your opening hours on Saturday?"},
    {"domain": "G. Delivery, Showroom & Company Contacts", "qid": "G4", "q": "Do you deliver to Abu Dhabi, Sharjah, and Oman?"},
    {"domain": "G. Delivery, Showroom & Company Contacts", "qid": "G5", "q": "وين معرضكم في دبي وكيف طريقة التواصل؟"},
    {"domain": "G. Delivery, Showroom & Company Contacts", "qid": "G6", "q": "Shop location kahan hai?"},
]

def run_suite():
    print(f"=== TESTING {len(QUESTIONS)} REPRESENTATIVE CUSTOMER QUESTIONS ===")
    results = []
    current_domain = None

    for item in QUESTIONS:
        if item["domain"] != current_domain:
            current_domain = item["domain"]
            print(f"\n{'='*70}\n{current_domain}\n{'='*70}")

        session_id = f"test_{item['qid']}_{int(time.time())}"
        state = ConversationState(session_id=session_id)

        t0 = time.time()
        resp = orchestrator.process_turn(item["q"], session_id=session_id, state=state)
        elapsed = time.time() - t0

        reply = resp.get("reply", "")
        source = resp.get("source", "")
        chips = resp.get("suggested_chips", [])
        cards = resp.get("product_cards", [])
        consumables = resp.get("consumable_cards", [])

        # Check for generic fallback or empty response
        is_generic_fallback = (
            "i did not understand" in reply.lower() or
            "how can i help you today?" in reply.lower() and len(reply) < 80 or
            "i am an ai assistant" in reply.lower() or
            reply.strip() == ""
        )

        status = "FAIL" if is_generic_fallback else "PASS"

        res_record = {
            "qid": item["qid"],
            "domain": item["domain"],
            "question": item["q"],
            "status": status,
            "elapsed_sec": round(elapsed, 3),
            "source": source,
            "reply": reply,
            "chips": chips,
            "product_cards": [c.get("name") or c.get("model") or c.get("id") for c in cards],
            "consumable_cards": [c.get("name") or c.get("sku") for c in consumables],
        }
        results.append(res_record)

        print(f"[{item['qid']}] {status} ({elapsed:.2f}s) | Route: {source}")
        print(f"Q: \"{item['q']}\"")
        preview = reply.replace("\n", " ")[:140]
        print(f"A: {preview}...")
        if chips:
            print(f"   Chips: {chips}")
        if cards:
            print(f"   Cards: {[c.get('name') or c.get('id') for c in cards][:2]}")
        if consumables:
            print(f"   Consumables: {[c.get('name') or c.get('sku') for c in consumables][:2]}")
        print("-" * 50)

    # Save to JSON
    out_path = "/opt/salesai/data/extracted_conversations/representative_test_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAll results saved to {out_path}")

    # Summary
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"\nSummary: {passed}/{total} Passed ({passed/total*100:.1f}%)")

if __name__ == "__main__":
    run_suite()
