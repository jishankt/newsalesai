# Kepler Tech Printer Sales Chatbot — Flow Audit Report

*Document ID:* `docs/flow_audit.md`  
*Branch:* `feature/flow-v2-catalogue-grounded`  
*Execution Date:* October 13, 2026  
*Status:* **Phase 0 Complete (Read-Only Audit)**

---

## 1. Executive Summary

This audit assesses the current state of the Kepler Tech conversational AI against the target specification defined for the **6 core product lines** across **43 approved printers** (10 Office MFPs, 13 Technical Large-Format Plotters, 14 Photo/Fine-Art Large-Format, 4 Citizen Dye-Sub Photo, 2 Dye-Sublimation) plus **29 Professional Scanners** (total: 72 products in [`data/catalogue_products.json`](file:///opt/salesai/data/catalogue_products.json)).

### Core Audit Principles Evaluated
1. **Zero Hallucination / Determinism:** Model selection, alternatives, consumables, and specifications must originate strictly from deterministic code over [`data/catalogue_products.json`](file:///opt/salesai/data/catalogue_products.json). The LLM is restricted exclusively to extracting semantic user slots and natural phrasing.
2. **Qualification Budget:** Maximum 3 qualification questions per flow before presenting leaf product cards.
3. **No Pricing in Chat:** Hard rule prohibiting equipment pricing in conversation text and cards (only verified AED 10 flat-rate UAE delivery is quoted).

---

## 2. Answers to the 8 Audit Questions

### Question 1: Where is the category list defined? Does it cover all 6 lines?
- **Finding 1.1:** [conversation/understanding.py:485-515](file:///opt/salesai/conversation/understanding.py#L485-L515)
  - **Current Behaviour:** Defines regex/keyword dictionary with 6 keys: `office_workforce`, `technical_cad`, `photo_fine_art`, `citizen_photo`, `dye_sublimation`, `scanners`.
  - **Target Behaviour:** Standardize category keys to the 6 target product lines: `office_mfp`, `technical_large_format`, `photo_fine_art`, `citizen_photo`, `dye_sublimation`, `scanners`.
  - **Risk:** High. Key divergence between `office_workforce` vs `office_printer` causes downstream qualification engine to drop category context.
- **Finding 1.2:** [conversation/qualification_schema.py:26-110](file:///opt/salesai/conversation/qualification_schema.py#L26-L110)
  - **Current Behaviour:** Defines `CATEGORY_REQUIREMENT_SCHEMAS` using `office_printer`, `technical_large_format`, `photography_large_format`, `citizen_photo`, `dye_sublimation`, `scanners`.
  - **Target Behaviour:** Align category naming uniformly with single source of truth in [`data/flow_rules.json`](file:///opt/salesai/data/flow_rules.json).
  - **Risk:** Medium. Multiple category aliases (`photography_large_format` vs `photo_fine_art`) require redundant normalization logic.
- **Finding 1.3:** [conversation/next_question_engine.py:35-155](file:///opt/salesai/conversation/next_question_engine.py#L35-L155)
  - **Current Behaviour:** Implements branching for `technical_cad` AND `technical_large_format`, as well as `("office_printer", "business_office", "office")`.
  - **Target Behaviour:** Deprecate fragmented branching and drive next questions dynamically from [`data/flow_rules.json`](file:///opt/salesai/data/flow_rules.json).
  - **Risk:** High. Inconsistent category aliases cause repetitive or skipped questions.

---

### Question 2: Where are qualification questions defined? How many are asked max? Are already-answered slots skipped?
- **Finding 2.1:** [conversation/product_flows.py:66-100](file:///opt/salesai/conversation/product_flows.py#L66-L100)
  - **Current Behaviour:** Hardcodes arbitrary daily volume buckets (`under 100`, `100-300`, `300-800`, `800+`) and assigns invented speed classes (`34_ppm`, `25_ppm_rips`, `40_ppm_linehead`, `55_ppm_linehead`).
  - **Target Behaviour:** Replace arbitrary daily thresholds with official catalogue `"recommended_monthly_min"` and `"recommended_monthly_max"` metrics (e.g. WF-C5890: 500–5,000; EM-C800: 1,000–10,000; AM-C400: 1,500–15,000; AM-C550: 2,000–20,000; WF-C878R: 1,500–10,000; WF-C879R: 2,000–15,000; AM-C4000: 5,000–30,000; AM-C5000: 7,000–40,000; AM-C6000: 10,000–60,000; WF-C21000: 15,000–100,000).
  - **Risk:** High. Leads to incorrect model recommendations that violate official workload capacities.
- **Finding 2.2:** [conversation/qualification_schema.py:199-281](file:///opt/salesai/conversation/qualification_schema.py#L199-L281)
  - **Current Behaviour:** `get_missing_mandatory_fields` filters out slots that already exist in `requirements`.
  - **Target Behaviour:** Maintain strict skipping: if user states *"I need an A4 office printer doing 3,000 pages monthly with fax"*, all 3 slots (`paper_size: A4`, `monthly_volume: 3000`, `fax_required: true`) must be marked answered in Turn 1, immediately delivering the leaf recommendation card without asking any questions.
  - **Risk:** Low if properly fed by slot extraction; High if verbal cues overwrite extracted numbers.
- **Finding 2.3:** [conversation/policy.py:40-75](file:///opt/salesai/conversation/policy.py#L40-L75)
  - **Current Behaviour:** Max 3 qualification questions enforced by qualification budget (`QUALIFICATION_MAX_QUESTIONS = 3`).
  - **Target Behaviour:** Keep strict max 3 question budget across all flows; for Dye-Sublimation (1 question max) and Scanners (2 questions max).
  - **Risk:** Low.

---

### Question 3: How are leaf recommendations chosen (hardcoded lists vs catalogue filter)? Check for 43 approved printers.
- **Finding 3.1:** [conversation/product_flows.py:433-441](file:///opt/salesai/conversation/product_flows.py#L433-L441)
  - **Current Behaviour:** Hardcodes static IDs directly in code tuples:
    ```python
    target_product_id="epson-sc-t5405"
    supporting_product_ids=["epson-sc-t5100", "epson-sc-t5700d"]
    ```
  - **Target Behaviour:** Run deterministic query through [`catalog/catalogue_filter.py`](file:///opt/salesai/catalog/catalogue_filter.py) over [`data/catalogue_products.json`](file:///opt/salesai/data/catalogue_products.json).
  - **Risk:** High. Hardcoding leaves bypasses catalogue attributes, breaks when specs update, and risks returning out-of-stock or unlisted variants.
- **Finding 3.2:** [agent/orchestrator.py:505, 1601, 1633, 1665, 1807, 1818](file:///opt/salesai/agent/orchestrator.py#L505)
  - **Current Behaviour:** Hardcodes model assignments directly in Python handlers:
    `cx02 = catalogue_loader.get_by_id("citizen-cx-02")`
    `f500 = catalogue_loader.get_by_id("epson-sc-f500")`
  - **Target Behaviour:** Migrate all decision trees to config in [`data/flow_rules.json`](file:///opt/salesai/data/flow_rules.json).
  - **Risk:** High. Duplication of routing logic across orchestrator, flows, and schema engines.
- **Finding 3.3:** **Catalogue Printer Census (43 Approved Printers Verified in `data/catalogue_products.json`):**
  - **Office (10 models):**
    - A4: `epson-wf-c5890-dwf`, `epson-em-c800-rdwf`, `epson-am-c400`, `epson-am-c550`
    - A3: `epson-wf-c878r-dwf`, `epson-wf-c879r-dwf`, `epson-am-c4000`, `epson-am-c5000`, `epson-am-c6000`, `epson-wf-c21000-d4tw`
  - **Technical Large-Format (13 models):**
    - 24" Print-Only: `epson-sc-t3100`, `epson-sc-t3700e`, `epson-sc-t3700d`, `epson-sc-t3700de` *(No 24" MFP exists)*
    - 36" Print-Only: `epson-sc-t5100`, `epson-sc-t5405`, `epson-sc-t5700d`
    - 36" MFP: `epson-sc-t5100m`, `epson-sc-t5400m`, `epson-sc-t5700dm`
    - 44": `epson-sc-t7700d`, `epson-sc-t7700dl`, `epson-sc-t7700dm`
  - **Photo / Fine Art (14 models):**
    - 13": `epson-sc-p700`
    - 17": `epson-sc-p900`, `epson-sc-p900-roll`, `epson-sc-p5300`
    - 24": `epson-sc-p6500e`, `epson-sc-p6500d`, `epson-sc-p6500de`, `epson-sc-p7500`, `epson-sc-p7500-spectro`
    - 44": `epson-sc-p8500d`, `epson-sc-p8500dm`, `epson-sc-p9500`, `epson-sc-p9500-spectro`
    - 64": `epson-sc-p20500`
  - **Citizen Photo (4 models):**
    - `citizen-cz-01`, `citizen-cx-02`, `citizen-cy-02`, `citizen-cx-02w`
  - **Dye-Sublimation (2 models):**
    - `epson-sc-f100`, `epson-sc-f500`
  - **Total Printers:** Exactly **43 models**. Every model exists and validates in `data/catalogue_products.json`.

---

### Question 4: Is there any invented or wrong model? Any wrong specs?
- **Finding 4.1:** [scripts/benchmark_models.py:52](file:///opt/salesai/scripts/benchmark_models.py#L52), [agent/tool_registry.py:71](file:///opt/salesai/agent/tool_registry.py#L71), [AI_AGENT_DOCUMENTATION.md:216](file:///opt/salesai/AI_AGENT_DOCUMENTATION.md#L216)
  - **Current Behaviour:** References `WF-C5790`.
  - **Target Behaviour:** Remove `WF-C5790` from all prompts, tools, and docs. Replace with approved A4 model `WF-C5890` (`epson-wf-c5890-dwf`).
  - **Risk:** High. `WF-C5790` is an unlisted discontinued model not present in `catalogue_products.json`.
- **Finding 4.2:** [tests/test_phase4_sales_behaviour.py](file:///opt/salesai/tests/test_phase4_sales_behaviour.py)
  - **Current Behaviour:** Some references and responses mention `SC-T3100N` as an alternative to `SC-T3100`.
  - **Target Behaviour:** Remove `SC-T3100N`. Only `epson-sc-t3100` is approved in catalogue.
  - **Risk:** High. Inaccurate model naming triggers accuracy guard failures.
- **Finding 4.3:** [data/sheets/master_complete_products.csv](file:///opt/salesai/data/sheets/master_complete_products.csv) & test fixtures
  - **Current Behaviour:** References `SC-T5400` as a standalone print-only 36" model.
  - **Target Behaviour:** The catalogue only contains `epson-sc-t5400m` (which is an MFP with integrated scanner). The print-only 36" models are `SC-T5100`, `SC-T5405`, and `SC-T5700D`.
  - **Risk:** High. Customer seeking print-only gets recommended an MFP with scanner markup, or vice-versa.
- **Finding 4.4:** [conversation/product_flows.py:73, 88, 264, 300](file:///opt/salesai/conversation/product_flows.py#L264), [static/workflow_flowchart.html:326](file:///opt/salesai/static/workflow_flowchart.html#L326)
  - **Current Behaviour:** Quotes `WF-C5890` at `"Standard 34 ppm"`.
  - **Target Behaviour:** The verified specification in `data/catalogue_products.json` line 44 is `25 ISO ppm black / 25 ISO ppm colour (simplex); 16 ipm duplex`.
  - **Risk:** High. Direct spec contradiction with official catalogue.

---

### Question 5: Are scanners backed by a verified data file? Any invented duty cycles?
- **Finding 5.1:** [data/catalogue_products.json:3500-4880](file:///opt/salesai/data/catalogue_products.json#L3500)
  - **Current Behaviour:** Scanners are present in `catalogue_products.json` (29 models: 27 WorkForce, 2 Expression). However, the printer RAG pipeline in `rag/` historically omitted scanners.
  - **Target Behaviour:** Back scanners with dedicated verified dataset [`data/scanner_catalogue.json`](file:///opt/salesai/data/scanner_catalogue.json) derived strictly from `PROFESSIONAL_SCANNERS_CATALOG.pdf`.
  - **Risk:** Medium. RAG lookups for scanners fall back to ungrounded or empty context.
- **Finding 5.2:** [data/catalogue_products.json:3927, 3987, 4393](file:///opt/salesai/data/catalogue_products.json#L3927)
  - **Current Behaviour:** Stated duty cycles exist for ONLY 3 scanners:
    1. `epson-workforce-ds-900wn`: 11,000 pages/day
    2. `epson-workforce-ds-800wn`: 8,000 pages/day
    3. `epson-workforce-ds-730n`: 6,500 pages/day
    All other 26 scanners have `daily_duty_cycle: null`.
  - **Target Behaviour:** Never guess or state duty cycles for any other scanner. If asked for DS-530II, DS-770II, etc., state clearly that daily duty cycle is not verified in official catalogue and refer to sales team.
  - **Risk:** Critical. Hallucinating duty cycles for commercial document scanners leads to invalid customer contracts.

---

### Question 6: Is "Desktop vs Floor stand" used as a qualifier anywhere?
- **Finding 6.1:** [conversation/product_flows.py:421-425](file:///opt/salesai/conversation/product_flows.py#L421-L425)
  - **Current Behaviour:** For 24" technical plotters, asks:
    `"For 24-inch CAD printing, what configuration fits your workspace?"`
    with chips: `["Entry Desktop (SC-T3100)", "Production Single Roll (SC-T3700E)", "Production Dual Roll (SC-T3700D / DE)"]`.
  - **Target Behaviour:** Remove stand as a qualifier completely. Stand availability is not verified in the catalogue. Qualify technical plotters strictly by:
    1. **Roll width:** 24" / 36" / 44"
    2. **Functions:** Print-only vs Scan+Copy (MFP)
    3. **Roll configuration & volume:** Single roll vs Dual roll / High volume
  - **Risk:** High. Confuses customers because standalone floor stands are accessories with unstated stock/catalogue status.
- **Finding 6.2:** [validation/answer_relevance_validator.py:195](file:///opt/salesai/validation/answer_relevance_validator.py#L195), [routes/comparison_route.py:519, 522](file:///opt/salesai/routes/comparison_route.py#L519)
  - **Current Behaviour:** Generates synthetic text claiming floor stands are included.
  - **Target Behaviour:** Cleanse stand claims; state stand availability as unverified and refer to sales.
  - **Risk:** Medium.

---

### Question 7: How does the bot handle direct lookups, consumables, objections, corrections, compound inputs, and leads?
- **Finding 7.1 (Direct Model Lookup):**
  - **File:Line:** [agent/orchestrator.py:1030-1170](file:///opt/salesai/agent/orchestrator.py#L1030), [conversation/understanding.py:430-480](file:///opt/salesai/conversation/understanding.py#L430)
  - **Current Behaviour:** Matches known SKUs and catalogue IDs, but if user mentions a category along with the model, it occasionally routes into category clarification.
  - **Target Behaviour:** Immediate shortcut: any recognized model name bypasses all qualifiers and renders verified spec card instantly.
  - **Risk:** Medium.
- **Finding 7.2 (Consumables Lookup):**
  - **File:Line:** [conversation/understanding.py:750](file:///opt/salesai/conversation/understanding.py#L750), [agent/orchestrator.py:1750](file:///opt/salesai/agent/orchestrator.py#L1750)
  - **Current Behaviour:** Successfully queries [`data/consumables_and_media.json`](file:///opt/salesai/data/consumables_and_media.json) and formats consumable cards.
  - **Target Behaviour:** "ink/consumables for X" goes straight to that model's verified consumables.
  - **Risk:** Low.
- **Finding 7.3 (Price Objections):**
  - **File:Line:** [conversation/policy.py:420-475](file:///opt/salesai/conversation/policy.py#L420), [conversation/response_plan.py:380](file:///opt/salesai/conversation/response_plan.py#L380)
  - **Current Behaviour:** Empathizes with price objections, highlights productivity/yield specs, and offers specialist quote.
  - **Target Behaviour:** Maintain empathy $\to$ TCO and ink yield $\to$ lower catalogue model or sales quote.
  - **Risk:** Low.
- **Finding 7.4 ("Not Stated in Catalogue" Fields):**
  - **File:Line:** [conversation/policy.py:340-390](file:///opt/salesai/conversation/policy.py#L340), [conversation/response_plan.py:358-372](file:///opt/salesai/conversation/response_plan.py#L358)
  - **Current Behaviour:** Checks evidence IDs. If an attribute (Wi-Fi, warranty, stock, stand) is not in evidence, pre-transmission accuracy guard blocks the message.
  - **Target Behaviour:** Deterministic refusal: state clearly that the field is not verified in the official catalogue and direct to `sales@keplertech.ae`. Never guess.
  - **Risk:** Low.
- **Finding 7.5 (Corrections):**
  - **File:Line:** [conversation/policy.py:520](file:///opt/salesai/conversation/policy.py#L520), [conversation/goal_manager.py:150-180](file:///opt/salesai/conversation/goal_manager.py#L150)
  - **Current Behaviour:** `DialogueAct.CORRECTION` triggers goal manager to purge old requirements, but debounced messages may cross over.
  - **Target Behaviour:** Latest correction overrides earlier intent (e.g. user says *"photo booth"* then *"sorry I want photo printer"* $\to$ Photo/Fine art category, completely excluding Citizen photo booth models).
  - **Risk:** Medium.
- **Finding 7.6 (Compound Inputs):**
  - **File:Line:** [agent/orchestrator.py:270-320](file:///opt/salesai/agent/orchestrator.py#L270)
  - **Current Behaviour:** Queued via per-session mutex lock.
  - **Target Behaviour:** Debounce and bundle multiple inputs arriving together; extract all valid slots simultaneously.
  - **Risk:** Low.
- **Finding 7.7 (Lead Capture Validation):**
  - **File:Line:** [conversation/lead_extractor.py:20-60](file:///opt/salesai/conversation/lead_extractor.py#L20), [persistence/lead_repository.py:39-65](file:///opt/salesai/persistence/lead_repository.py#L39)
  - **Current Behaviour:** Regex extracts UAE phone numbers (`+971 5x...`, `050...`) and emails, requires explicit consent, saves to SQLite `commercial_leads`, triggers sales notification.
  - **Target Behaviour:** Keep existing implementation untouched.
  - **Risk:** Low.

---

### Question 8: Any hardcoded catalogue counts?
- **Finding 8.1:** [catalog/catalogue_loader.py:46](file:///opt/salesai/catalog/catalogue_loader.py#L46)
  - **Current Behaviour:** `EXPECTED_CATALOGUE_COUNT = 72`.
  - **Target Behaviour:** Derive catalogue count dynamically from loaded data: `len(self.products)`.
  - **Risk:** Medium. Hardcoded static integers cause runtime startup crashes if catalogue entries are updated or partitioned.
- **Finding 8.2:** [app.py:181, 216](file:///opt/salesai/app.py#L181), [tests/test_scanners_catalogue.py:37](file:///opt/salesai/tests/test_scanners_catalogue.py#L37)
  - **Current Behaviour:** Checks `len(all_prods) == EXPECTED_CATALOGUE_COUNT`.
  - **Target Behaviour:** Verify `len(all_prods) > 0` and assert catalog integrity against file schema rather than a magic number.
  - **Risk:** Medium.
- **Finding 8.3:** [catalog/catalogue_filter.py:3](file:///opt/salesai/catalog/catalogue_filter.py#L3), [validation/catalogue_validator.py:28](file:///opt/salesai/validation/catalogue_validator.py#L28), [WORKFLOW_FLOWCHART.md:120](file:///opt/salesai/WORKFLOW_FLOWCHART.md#L120)
  - **Current Behaviour:** Text comments and docstrings still state `"41 approved catalogue entries"`.
  - **Target Behaviour:** Update all references to reflect the actual verified inventory (43 printers + 29 scanners = 72 products).
  - **Risk:** Low (documentation consistency).

---

## 3. Audit Summary Table

| Category / Component | File & Line Reference | Current Behaviour | Target Behaviour | Severity |
|---|---|---|---|---|
| **Category Taxonomy** | `conversation/understanding.py:485` | 6 lines with divergent keys (`office_workforce`, `technical_cad`) | Unify to 6 lines: Office MFP, Technical Large-Format, Photo/Fine-Art, Citizen Photo, Dye-Sub, Scanners | **High** |
| **Decision Trees** | `conversation/product_flows.py:66-100` | Arbitrary daily volume thresholds & invented speed classes (`34 ppm`) | Config-driven [`data/flow_rules.json`](file:///opt/salesai/data/flow_rules.json) with official catalogue monthly volume ranges | **High** |
| **Model Gaps** | `scripts/benchmark_models.py:52`, `agent/tool_registry.py:71` | References `WF-C5790`, `SC-T3100N`, `SC-T5400` (without M) | Eliminate unapproved models; map strictly to 43 catalogue printers | **Critical** |
| **Speed Specs** | `conversation/product_flows.py:264`, `WORKFLOW_FLOWCHART.md:18` | Quotes `WF-C5890` at 34 ppm | Strictly quote catalogue spec: 25 ISO ppm | **High** |
| **Scanner Duty Cycles** | `catalog/comparison_engine.py:397` | Unverified scanner duty cycle comparisons | Only state duty cycles for DS-900WN, DS-800WN, DS-730N; refuse others | **Critical** |
| **Stand Qualifier** | `conversation/product_flows.py:421` | "Desktop vs Floor stand" qualifier question | Remove stand qualifier; qualify by Width, Print vs MFP, and Single vs Dual Roll | **Medium** |
| **Catalogue Count** | `catalog/catalogue_loader.py:46`, `app.py:181` | Hardcoded `EXPECTED_CATALOGUE_COUNT = 72` (and "41" in docs) | Derive dynamically from dataset | **Medium** |
