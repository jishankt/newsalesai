# NLU Module Accuracy: Implementation Plan

**Branch:** `fix/nlu-accuracy`  
**Current Status:** All Fixes (Step 0, Fix 1 through Fix 8) and Final Verifications are **COMPLETED & VERIFIED**. All 22/22 probes pass cleanly.

---

## 1. Summary of Work Completed

| Milestone / Fix | Status | Probes Flipped to Passing | Key Outcome |
| :--- | :---: | :--- | :--- |
| **Step 0: Baseline & Split** | Done | — | Stratified 70/30 Dev (195 turns) & Holdout (83 turns), compound scoring enabled, exempted default pace FP, saved `baseline_before.json`. |
| **Fix 1: Shared Budget Parser** | Done | `test_budget_k_suffix`<br>`test_budget_comma_separated`<br>`test_budget_arabic_indic_digits` | Created `conversation/numeric_parse.py`; budget accuracy reached **100%** on both dev and holdout. |
| **Fix 2: Negation & Polarity** | Done | `test_negated_media_size_not_filled`<br>`test_negated_category_not_filled`<br>`test_forget_category_not_filled`<br>`test_negated_model_not_filled` | 4-token polarity detector window; `slots["excluded"]` populated; `policy.py` & `dialogue_state.py` clear confirmed negated slots; confident-but-wrong dropped from 33.3% to **23.59%** on dev and 25.3% to **19.28%** on holdout. |
| **Fix 3 & Fallback Upgrade** | Done | — | Upgraded default fallback model to `qwen2.5:14b` (fitting comfortably in Quadro RTX 6000 24 GB VRAM); added token penalty deduction in `parse()`. |
| **Fix 4: Compound Intents & Priority** | Done | — | Anchored flow patterns; prioritized specific application queries over blanket chips; preserved compound secondary intents in `PolicyEngine`. |
| **Fix 5: Entity & Model Matching** | Done | `test_spaced_model_name_recognition`<br>`test_ambiguous_typo_cz02_requests_clarification` | Collapsed alphanumeric boundary spaces; removed hardcoded `cz02` alias; added near-match runner-up ambiguity check (`abs(score1 - score2) <= 0.15`). |
| **Fix 6: Category Overlap & Preservation** | Done | `test_category_priority_does_not_silently_drop_second_need`<br>`test_photo_booth_and_office_overlap` | Stopped stripping explicit office mentions; recorded multiple category candidates in slots and ambiguities. |
| **Fix 7: Multilingual Lexicons** | Done | `test_arabic_category_request`<br>`test_hinglish_size_and_category_keywords` | Added Arabic, Hindi/Hinglish, and Malayalam lexicons for categories and closed intent keywords. |
| **Fix 8: Empty/Emoji & Bare Numbers** | Done | `test_empty_string_dialogue_act_not_question`<br>`test_bare_number_intent_not_high_confidence_recommend` | Handled empty/emoji with `DialogueAct.CHITCHAT` (conf: 0.20); handled bare numbers with `0.40` low confidence and `bare_number_no_context` ambiguity. |

---

## 2. Implementation Steps (Fix 3 to Fix 8)

### Fix 3: Confidence Calibration & Evidence-Based Scoring + Model Benchmark
- **Objective:** Replace hard-coded constants (`0.90`, `0.95`, `0.99`) with evidence-based scoring derived from token and context features, and benchmark fallback LLMs.
- **Implementation:**
  1. Base confidence assigned by rule match type (exact alias match: 0.95, regex pattern: 0.88, near match: 0.70).
  2. Deduct penalties:
     - `-0.15` for competing intent keywords in the same turn.
     - `-0.10` for negation token presence.
     - `-0.15` for non-ASCII / unlexiconed tokens.
     - `-0.10` for unresolved reference expressions.
     - `-0.15` for 2+ question marks or `"and"`-joined compound requests.
  3. Fit penalty weights against DEV split so accuracy in each bucket matches stated confidence within $\pm 10\%$.
  4. **Fallback LLM Model Benchmark & Selection:**
     - Target Hardware: Quadro RTX 6000 (24 GB VRAM).
     - Benchmark local candidates: `qwen2.5:latest` (7B baseline) vs **`qwen2.5:14b` (Primary Upgrade Target)** vs `qwen3:8b`.
     - Evaluate: JSON schema compliance rate, p50/p95 latency, VRAM utilization, and classification accuracy on dev split.
     - Cap fallback confidence at `0.80`, require strict JSON schema validation, and discard fallback if it contradicts explicit SKU/model/negation rules.
  5. Calibrate fallback threshold to achieve confident-but-wrong $< 10\%$ on holdout with fallback rate $\le 20\%$.
- **Validation:** Run `run_eval.py --split dev` and `--split holdout`; generate calibration table. Commit separately.

---

### Fix 4: Compound Intents & Intent Priority Bugs
- **Objective:** Replace first-regex-wins with multi-intent scoring, primary intent selection, and `secondary_intents` list.
- **Implementation:**
  1. Score all matched intent patterns rather than returning on first regex match.
  2. Specific intent fixes:
     - Stock / availability must NOT lose to delivery when both occur together.
     - Price alongside compatibility must retain price intent as secondary.
     - `"warranty"` belongs to `Intent.PRODUCT_INFO`, not general inquiry.
     - `"ink"` / `"paper"` within capability/spec inquiries (`"does it support roll paper"`, `"ink cartridges or ribbon"`) is `Intent.PRODUCT_INFO`, not `Intent.CONSUMABLES_LOOKUP`.
     - `Intent.CONSUMABLES_LOOKUP` strictly requires supply-ordering signal (buy/need/order/replacement cartridges).
     - Map `"how many seconds"`, `"speed"`, `"ppm"` to `target_attribute="print_speed"`.
     - Hyphenated sizes (`36-inch`, `36in`, `36"`) normalize to `media_size="36inch"`.
  3. Update `PolicyEngine` to preserve and answer/clarify `secondary_intents`.
- **Validation:** Run full test suite, evaluate dev & holdout. Commit separately.

---

### Fix 5: Entity & Model Matching Improvements
- **Objective:** Whitespace/hyphen normalization for model codes, fuzzy near-match ambiguity clarification.
- **Implementation:**
  1. Collapse spaces and hyphens in alphanumeric patterns when matching known model families (`"p 7500"`, `"p-7500"`, `"cx 02"` $\rightarrow$ `p7500`, `cx02`). Leave bare numbers unaffected.
  2. Remove hardcoded `"cz02" -> citizen-cx-02` alias.
  3. Implement near-match runner-up margin: if top candidate and runner-up are within similarity margin of 0.15, return `ambiguities=["model:citizen-cz-01|citizen-cx-02"]`.
- **Probes to Flip:**
  - `test_spaced_model_name_recognition`
  - `test_ambiguous_typo_cz02_requests_clarification`
- **Validation:** Run `pytest tests/nlu_audit/test_probes.py`. Commit separately.

---

### Fix 6: Category Overlap & Explicit Disambiguation
- **Objective:** Never silently discard secondary category mentions; return candidate list and ask clarifying question.
- **Implementation:**
  1. Return `slots["target_category"] = primary`, `slots["category_candidates"] = [all_matched]`, and set `ambiguities=["multiple_categories"]`.
  2. Disambiguation precedence:
     - `"photo booth"` / `"events"` takes precedence over generic `"photo"`.
     - `"sublimation"` takes precedence over `"photo"` when apparel/t-shirt/mug/transfer keywords are present.
  3. Policy: present quick-reply chips for each category candidate when `ambiguities` contains `multiple_categories`.
- **Probes to Flip:**
  - `test_category_priority_does_not_silently_drop_second_need`
  - `test_photo_booth_and_office_overlap`
- **Validation:** Run probe suite and eval. Commit separately.

---

### Fix 7: Multilingual Lexicons & Fallback
- **Objective:** High-speed deterministic extraction for non-English queries without blanket LLM routing, with `qwen2.5:14b` fallback for unlexiconed dialect phrases.
- **Implementation:**
  1. Create `conversation/lexicons/`:
     - `arabic.json`: printer, scanner, plotter, size, price, stock, delivery, numbers.
     - `hinglish.json` & `hindi.json`: printer, chote, dam, chahiye, nahi, daam.
     - `malayalam.json` & `manglish.json`: printer, vela, ethra, venda, alla.
  2. Text normalization (NFKC Unicode normalization, strip Arabic tatweel and diacritics).
  3. If non-English script detected and no lexicon matches, lower confidence to trigger fallback via `qwen2.5:14b`. If lexicon matches, extract deterministically with high confidence.
  4. Ensure dataset contains 40+ multilingual cases evaluated across dev/holdout.
- **Probes to Flip:**
  - `test_arabic_category_request`
  - Maintain `test_hinglish_size_and_category_keywords` passing.
- **Validation:** Run probe suite and eval. Commit separately.

---

### Fix 8: Empty/Emoji Handling & Bare Number Guard
- **Objective:** Graceful handling of degenerate, emoji, and ungrounded numeric inputs.
- **Implementation:**
  1. Empty, whitespace-only, or emoji-only inputs: set `dialogue_act=DialogueAct.CLARIFICATION`, `intent=Intent.OTHER`, `confidence=0.20`.
  2. Capability questions with reference pronouns ("does it print duplex?") keep `dialogue_act=DialogueAct.QUESTION` and set `has_reference=True` (not `REFERENCE_FOLLOW_UP`).
  3. Bare numbers without context ("24", "12") receive low confidence ($< 0.50$) unless the previous turn explicitly prompted for size/quantity.
  4. Correct documentation and comments to reflect measured latency ($\sim 30\text{--}40\text{ ms}$) instead of unsubstantiated claims.
- **Probes to Flip:**
  - `test_empty_string_dialogue_act_not_question`
  - `test_bare_number_intent_not_high_confidence_recommend`
- **Validation:** Run probe suite and eval. Commit separately.

---

### Final Milestone: Final Verification & Audit Report
1. Run complete evaluation on DEV and HOLDOUT with and without LLM fallback.
2. Compile complete Metric Delta Table across all 8 fixes.
3. Generate final Confidence Calibration Table and latency percentiles (p50/p95/p99).
4. Run all 17 sales scenarios in `tests/test_audit_sales_behaviours.py` and raw conversations to ensure zero regression in the dialogue layer.
5. Finalize `docs/nlu_label_changes.md` and report.
