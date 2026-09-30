# Kepler Tech SalesAI — Claims Audit & Confirmation Matrix (`CLAIMS_TO_CONFIRM.md`)

This document records all business, operational, and commercial claims audited across the codebase (`prompts.py`, `config.py`, `agent/orchestrator.py`, `routes/business_info_route.py`, and `agents/sales_lead_agent.py`) prior to launch on branch `fix/prelaunch-hardening`.

## Audit Summary

| Category | Claim / Statement in Code | Location | Verification Status | Enforced Action / Guardrail |
| :--- | :--- | :--- | :--- | :--- |
| **Warranty** | "1-Year On-Site Manufacturer Warranty covering genuine parts, printheads, and certified technician labor across the UAE" | `routes/business_info_route.py:16`, `agent/orchestrator.py:338, 3125` | **Unverified in Catalogue**: `catalogue_products.json` does not contain explicit warranty fields per SKU. | **Guarded**: Bot states general distributor warranty policy when asked generally, but when asked about a specific model whose specs don't list warranty, replies that the official specifications do not state the exact duration, and directs to sales team for quotation terms. Avoids asserting warranty voiding. |
| **Extended Warranty** | "Optional CoverPlus extended warranties (up to 3 or 5 years) and comprehensive Annual Maintenance Contracts (AMC)" | `routes/business_info_route.py:16`, `agent/orchestrator.py:3126, 3134` | **Unverified Pricing & Availability per SKU**: CoverPlus is an official Epson program, but individual SKU eligibility is not verified in local catalog. | **Guarded**: Offered only as a discussion topic with the commercial sales team; never promised as included by default. |
| **Delivery SLA** | "Fast delivery all over UAE and Middle East", "certified hardware delivery across the UAE" | `config.py:131`, `agent/orchestrator.py:839, 1663` | **Unverified Timeframes**: No SLA (e.g., same-day or 24-hour delivery) is verified in the repo. | **Guarded**: Code never promises exact transit times, same-day dispatch, or free delivery. Delivery timelines must be quoted by the sales desk. |
| **Operating Hours** | "Monday – Friday: 8:30 AM to 5:30 PM \| Saturday: 8:30 AM to 1:00 PM \| Sunday: Closed (GST / UTC+4)" | `config.py:132, 149-160` | **Verified**: Sourced directly from official website (`https://www.keplertechllc.com/`). | **Implemented**: Checked programmatically via `is_within_business_hours()` in `app.py`. Outside business hours, customers are informed of opening hours and prompted for contact details. |
| **Office Location** | "D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai, UAE" | `config.py:131`, `routes/business_info_route.py:13` | **Verified**: Matches verified showroom and headquarters address. | **Preserved**: Returned consistently across location and showroom inquiries. |
| **Partner Phrasing** | "Dubai's #1 Printer, Inkjet Media & Consumables Supplier & Authorized Distributor" | `config.py:121` | **Marketing Tagline**: "#1" is subjective promotional phrasing from the website. | **Guarded**: Controlled via `PARTNER_STATUS_TEXT` in `config.py` ("Kepler Tech is an authorized distributor and partner for Epson, Citizen, Innova Art, Olmec, and Mirage in the UAE"). The bot does not assert legal exclusivity or unverifiable rankings. |
| **Stock / Inventory** | "Yes, we have that in stock!" | `agent/orchestrator.py:3027` | **Unverified Real-time Inventory**: The bot references the static 42-product catalogue and consumables database; live warehouse inventory is not connected. | **Guarded**: Reframed to "We carry this genuine consumable in our authorized distribution catalogue" rather than guaranteeing physical counts. |
| **Pricing & Quotes** | Any numerical price or discount promise | Multiple files | **Strictly Prohibited**: Pricing and discount negotiation in chat is blocked by guardrails. | **Guarded**: Intercepted by `guardrail:discount_refusal` and `guardrail:commercial_policy` with 4 rotating templates directing to official website and offering live sales rep connection. |

---

## Action Items for Operations & Commercial Team
1. **Confirm Warranty Matrix by Brand**: Provide an official mapping of standard warranty durations by brand (Epson SureColor vs WorkForce vs Citizen) for future inclusion in `catalogue_products.json`.
2. **Delivery Terms**: Confirm whether standard delivery is free within Dubai/UAE above a certain order threshold to enable automated shipping answers.
3. **ERP / Live Inventory Integration**: Connect live ERP inventory if stock availability status should be shown in real time.
