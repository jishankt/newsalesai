# Kepler Tech SalesAI: Decisions Needed

This document records conflicts, policy ambiguities, and business decisions required from Kepler Tech LLC stakeholders. Under the fail-closed integrity rule, the chatbot does not fabricate assumptions where verified sources diverge.

---

## 1. Contact Email Conflict (info@keplertech.ae vs sales@keplertech.ae)

- **Source A (Website FAQ / General Inquiries)**:
  - Cites `info@keplertech.ae` as the primary customer-facing contact email.
- **Source B (Terms & Conditions, Commercial Sales Practice, Prior Codebase)**:
  - Cites `sales@keplertech.ae` for formal quotes, commercial pricing, equipment proposals, and volume procurement.
- **Current Technical Implementation**:
  - Centralized in `config.py` as:
    - `OFFICIAL_SUPPORT_EMAIL` (`sales@keplertech.ae` by default, configurable via environment variable).
    - `OFFICIAL_INFO_EMAIL` (`info@keplertech.ae`).
    - `OFFICIAL_SUPPORT_PHONE` (`+971 4 323 1008`).
- **Decision Needed from Stakeholders**:
  - Should customer-facing inquiries route exclusively to `info@keplertech.ae`, `sales@keplertech.ae`, or should sales equipment proposals route to `sales@` while general policy/support routes to `info@`?

---

## 2. No-Product-Pricing-in-Chat Policy (Including Cards)

- **Strict Commercial Policy**:
  - Chatbot replies strictly avoid outputting arbitrary digits, ad-hoc price quotes, or negotiable discounts for equipment in conversational text.
  - Formal pricing, official tax invoices, and volume tier contracts must be quoted by human enterprise sales representatives.
- **Product & Consumable Cards**:
  - Hardware and consumable cards displayed in the UI currently omit numeric price tags in sales flows to maintain uniform consistency with this policy.
- **Decision Needed from Stakeholders**:
  - Should UI product cards display MSRP / starting catalogue prices from `data/catalogue_products.json`, or must all card price fields remain hidden/unpopulated ("Request Quote") in chat flows?

---

## 3. Delivery Coverage and Geographical Scope

- **Source A (Terms & Conditions s3)**:
  - Specifies delivery services apply strictly to the UAE and GCC region.
- **Source B (Website FAQ Shipping Section)**:
  - References Middle East and global international shipping via FedEx / Aramex (6–8 business days).
- **Decision Needed from Stakeholders**:
  - What is the definitive shipping boundary for online inquiries (UAE only, GCC, or worldwide)?
  - How should customs duty and local VAT liability be presented to international buyers?

---

## 4. Processing Time vs Transit Time

- **Source A (Terms & Conditions s4)**:
  - States standard dispatch occurs within 1–2 business days.
- **Source B (FAQ Shipping)**:
  - Domestic delivery cited as 1–2 business days; international as 6–8 business days.
- **Decision Needed from Stakeholders**:
  - Are processing time (1–2 business days) and transit time (1–2 domestic / 6–8 international) additive, or is the total lead time 1–2 business days domestically?

---

## 5. Sales Notification Channel & Lead Handoff

- **Requirement**:
  - When leads are captured (customer name, UAE phone number, email), the system must dispatch notifications.
- **Decision Needed from Stakeholders**:
  - Preferred delivery mechanism: Webhook URL (e.g., CRM / Slack / ERP) or SMTP Email to sales desk?
  - Required SMTP host / port / credentials or Webhook endpoint URL.
