# RAG & Website Pricing Implementation Plan

**Target Execution:** Next Working Session  
**Scope:** RAG Technical Retrieval, Website List Prices (AED), Cost-Per-Print Calculations, and Datasheet Specifications  
**Status:** Ready for Execution  

---

## 1. Executive Summary & Objective

Currently, when users ask general technical questions, product dimensions, or pricing inquiries (e.g., *"what is the price of Citizen CZ-01?"*, *"what is the print cost of CZ-01?"*, *"what are the dimensions of SC-T3100?"*), the system often returns a generic sales desk deflection or enters flowchart recommendations rather than providing verified specifications and prices directly.

### Goal:
1. **Provide Direct Published Pricing:** Quote verified website list prices (e.g., `AED 3,200.00` for CZ-01) with official quote/invoice routing.
2. **Calculate Print / Media Costs:** Answer running cost inquiries directly (e.g., CZ-MS46 pack is `AED 295.00` for 300 prints $\approx$ `AED 0.98` per 4×6″ print).
3. **Retrieve Datasheet Technical Specifications:** Directly answer questions about dimensions, weight, DPI, speed, memory, and official brochure PDF URLs from manufacturer datasheets.
4. **Maintain Zero Hallucination:** Only quote verified prices and specifications that exist in official catalogues and caches.

---

## 2. Inventory of Existing Verified Data Assets

All data files already exist within `/opt/salesai/data/`:

| Data Asset | Path | Description |
| :--- | :--- | :--- |
| **Website Verified Prices** | `data/verified_prices.json` | 74 verified hardware models with exact list prices in AED |
| **Website Price Cache** | `data/website_prices_cache.json` | 89 cached models with VAT status (`Excl. VAT`) |
| **Full Consumables Catalog** | `data/products.json` | 804 verified SKUs with exact unit prices in AED |
| **Complete Training Corpus** | `data/sheets/complete_training_corpus.json` | 735 products with dimensions, weights, speeds, DPI, memory, duty cycles |
| **Master Products CSV** | `data/sheets/master_complete_products.csv` | 735 structured rows with datasheet specs & consumable links |
| **Verified Brochures** | `data/verified_brochures.json` | Official manufacturer datasheet PDF URLs |

---

## 3. Work Breakdown Structure (Phases 1 - 4)

### Phase 1: RAG Retriever & Embedding Index Enhancement
- **Target File:** [`rag/retriever.py`](file:///opt/salesai/rag/retriever.py)
- **Changes Required:**
  1. Add data path constants:
     - `VERIFIED_PRICES_PATH = "data/verified_prices.json"`
     - `WEBSITE_PRICES_PATH = "data/website_prices_cache.json"`
     - `VERIFIED_BROCHURES_PATH = "data/verified_brochures.json"`
     - `COMPLETE_CORPUS_PATH = "data/sheets/complete_training_corpus.json"`
  2. In `RagRetriever._load_and_index()`:
     - Merge `verified_prices.json` and `website_prices_cache.json` into each product dictionary (`price`, `price_str`, `currency`, `vat_note`).
     - Merge `verified_brochures.json` for PDF URLs (`brochure_url`, `pdf_url`).
     - Pull rich datasheet attributes from `complete_training_corpus.json`: `dimensions`, `weight`, `dpi`, `memory`, `consumables_detailed`, `yield_capacity`.
  3. Include price and rich specs in searchable text:
     - Update `self.doc_texts` formatting to include:
       `Price: AED {price}` | `Brochure: {brochure_url}` | `Dimensions: {dimensions}` | `Weight: {weight}` | `Resolution: {dpi}` | `Memory: {memory}`.
  4. In `format_prompt_context()`:
     - Expose `Price`, `Datasheet / Brochure PDF`, `Dimensions`, `Weight`, `Resolution / DPI`, and `Consumables`.

### Phase 2: Understanding & Policy Engine Routing
- **Target Files:**
  - [`conversation/understanding.py`](file:///opt/salesai/conversation/understanding.py)
  - [`conversation/policy.py`](file:///opt/salesai/conversation/policy.py)
- **Changes Required:**
  1. **Intent Extraction ([`conversation/understanding.py`](file:///opt/salesai/conversation/understanding.py)):**
     - In `classify_dialogue_act_and_intent()`:
       When a specific model or SKU is present, prioritize `Intent.PRODUCT_INFO` or `Intent.AVAILABILITY_OR_PRICE_POLICY` over flowchart recommendations (`extract_flowchart_requirements`).
     - Add explicit attribute detection keywords: `"dimensions"`, `"measurements"`, `"weight"`, `"how heavy"`, `"memory"`, `"ram"`, `"price"`, `"cost"`, `"how much"`, `"datasheet"`, `"brochure"`, `"spec sheet"`.
  2. **Policy Decision Engine ([`conversation/policy.py`](file:///opt/salesai/conversation/policy.py)):**
     - Update `Intent.AVAILABILITY_OR_PRICE_POLICY`:
       - Check if inquiry is about **cost per print / print cost**:
         - Calculate media cost per print (e.g., Citizen CZ-01: CZ-MS46 media pack is AED 295.00 for 300 prints $\approx$ AED 0.98 per print).
       - If inquiry is about **printer / hardware price**:
         - If product has verified list price:
           State: `The **{t_name}** is priced at **AED {price:,.2f}** (excl. VAT). Official quotations, tax invoices, and bulk pricing are provided directly through our sales desk at sales@keplertech.ae or +971 4 323 1008.`
         - If product is quote-only (`price: null`):
           State that pricing is provided upon request based on duty cycle and configuration.
     - In `Intent.PRODUCT_INFO`:
       - Expand attribute lookup to handle `dimensions`, `weight`, `memory`, `price`, and `brochure_url` via `EvidenceEngine.get_attribute()`.

### Phase 3: Response Validator Guardrail Adjustment
- **Target File:** [`conversation/response_plan.py`](file:///opt/salesai/conversation/response_plan.py)
- **Changes Required:**
  1. In `ResponsePlanValidator.validate()`:
     - Currently `PRICE_NUMERIC_PATTERN` flags any numbers like `AED 3200` as an unverified commercial policy violation.
     - Allow numeric prices when supported by verified evidence records:
       `if any(rec.field in ("price", "price_str", "cost_per_print", "pricing_policy") and rec.verified for rec in plan.evidence_records): has_price_violation = False`

### Phase 4: Automated Testing & Live Validation
- **Target File:** [`tests/test_rag_and_pricing.py`](file:///opt/salesai/tests/test_rag_and_pricing.py)
- **Test Scenarios to Automate:**
  1. **Hardware Pricing Inquiry:**
     - `"what is the price of citizen cz-01?"` $\rightarrow$ Assert `AED 3,200.00` in response.
     - `"how much is the epson wf-c5890?"` $\rightarrow$ Assert `AED 1,656.00` in response.
     - `"what is the price of epson sc-f100?"` $\rightarrow$ Assert `AED 1,950.00` in response.
  2. **Cost-Per-Print Inquiry:**
     - `"what is the print cost of cz-01?"` $\rightarrow$ Assert `AED 295.00` and `0.98` in response.
  3. **Datasheet Specifications Inquiry:**
     - `"what are the dimensions of sc-t3100?"` $\rightarrow$ Assert `970 × 696 × 913 mm` in response.
     - `"what is the print speed of epson f100?"` $\rightarrow$ Assert `65 sec` in response.
     - `"what is the resolution of citizen cx-02?"` $\rightarrow$ Assert `300` or `600 DPI` in response.
  4. **Datasheet / Brochure Link Inquiry:**
     - `"can i get the datasheet for cx-02?"` $\rightarrow$ Assert contains verified PDF URL.
  5. **Full Regression Suite:**
     - Run `tests/test_all_catalog_flows_twice.py` to ensure all 18 existing catalog flowchart tests continue passing.

---

## 4. Execution Time Estimate

| Phase | Description | Estimated Duration |
| :--- | :--- | :--- |
| **Phase 1** | RAG indexer update (`retriever.py` with pricing & datasheet corpus) | 10 mins |
| **Phase 2** | Policy engine & understanding update (`policy.py`, `understanding.py`) | 12 mins |
| **Phase 3** | Response validator guardrail adjustment (`response_plan.py`) | 5 mins |
| **Phase 4** | Automated test suite execution & live verification on keplarbot | 8 mins |
| **Total** | | **~35 mins** |

---

## 5. Verification Checklist

- [ ] `venv/bin/python tests/test_rag_and_pricing.py` passes all queries.
- [ ] `venv/bin/python tests/test_all_catalog_flows_twice.py` passes all 18 tests.
- [ ] Live endpoint `https://keplarbot.kylesolutions.in` responds accurately to live browser queries.
