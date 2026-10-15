# Comprehensive NLU Audit Report: jishankt/newsalesai
**Audited Component**: `conversation/understanding.py` (Kepler Tech WhatsApp Printer Sales Chatbot)  
**Evaluation Date**: 2026-10-14  
**Evaluation Dataset**: `tests/nlu_audit/dataset.jsonl` (238 hand-labelled & sanitized real test cases across 11 groups)  
**Evaluation Harness**: `tests/nlu_audit/run_eval.py`  
**Targeted Invariant Probes**: `tests/nlu_audit/test_probes.py` (8 passed, 14 xfailed)  

---

## Executive Summary

The NLU module in `conversation/understanding.py` claims to handle **"98% of turns deterministically"** with **"< 5 ms latency"**.

Our audit independently measured both claims and analyzed the accuracy of structured understanding across 238 representative customer messages:
1. **The latency claim is FALSE**: Deterministic latency is **p50 = 30.67 ms**, **p95 = 37.37 ms**, and **p99 = 42.57 ms** (6.1× to 8.5× slower than the claimed "< 5 ms").
2. **The fallback claim is FALSE**: When Ollama is enabled, **13.03%** of queries trigger fallback (not ~2%).
3. **Severe Confident-but-Wrong Failure Mode**: In deterministic mode, **35.29% (84/238)** of queries produce high confidence ($\ge 0.75$) while extracting incorrect structured fields. When LLM fallback is enabled, this rises to **45.38% (108/238)** because LLM outputs are assigned inflated confidence scores.
4. **Confidence Gate is Broken**: Virtually every keyword rule in `classify_dialogue_act_and_intent` hardcodes confidence between **0.90 and 0.99**. Even partial, irrelevant, or negated matches bypass the LLM gate entirely.
5. **Critical Missing Slot Extraction**: The deterministic slot extractor **never extracts `budget_ceiling`** (0.0% accuracy across all budget queries).

---

## 1. Per-Field Accuracy & Worst Group

| Field | Accuracy (Deterministic) | Accuracy (With LLM) | Evaluated Turns | False Positives | Worst Performing Group (min 2 tests) |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`intent`** | 72.73% | 72.73% | 165 | 73 | `compound_intents` (45.0%) |
| **`dialogue_act`** | 75.69% | 72.22% | 144 | 94 | `negation_correction` (31.8%) |
| **`target_category`**| 73.81% | 73.81% | 42 | 32 | `multilingual` (56.2%) |
| **`target_model`** | 89.74% | 89.74% | 39 | 25 | `negation_correction` (50.0%) |
| **`media_size`** | 71.43% | 71.43% | 14 | 1 | `real` (66.7%) |
| **`target_attribute`**| 73.33% | 73.33% | 15 | 40 | `multilingual` (50.0%) |
| **`budget_ceiling`** | **0.00%** | **0.00%** | 19 | 0 | `budget_quantity` (**0.0%**) |
| **`quote_quantity`** | 92.31% | 92.31% | 13 | 1 | `multilingual` (50.0%) |
| **`primary_concern`** | 92.31% | 92.31% | 13 | 28 | `multilingual` (50.0%) |
| **`buyer_pace`** | 100.00% | 100.00% | 9 | **229** | `concern_and_pace` (100.0%) |

> **Note on False Positives**:
> - `buyer_pace` generated **229 false positives** on 238 turns because `extract_buyer_pace` unconditionally inserts `buyer_pace="standard"` into `slots` for every single message.
> - `budget_ceiling` failed **100% of cases** because `extract_slots` in `conversation/understanding.py` lacks budget parsing logic entirely.

---

## 2. Confidence Calibration & Claimed vs Measured Performance

### Confidence Calibration Table

| Confidence Bucket | Count | All-Correct Turns | Real Accuracy | Evaluation |
| :--- | :---: | :---: | :---: | :--- |
| **0.00 - 0.50** | 0 | 0 | 0.0% | Never assigned by deterministic rules |
| **0.50 - 0.75** | 0 | 0 | 0.0% | Completely bypassed (rules jump from default 0.60 to $\ge 0.80$) |
| **0.75 - 0.90** | 47 | 11 | **23.4%** | Highly miscalibrated (claims ~85% accuracy, delivers 23.4%) |
| **0.90 - 1.00** | 191 | 119 | **62.3%** | Poorly calibrated (claims $\ge 90\%$ accuracy, delivers 62.3%) |

### Claims vs Measured Metrics

| Metric | Design Claim | Measured (Deterministic) | Measured (With Ollama Fallback) | Discrepancy |
| :--- | :---: | :---: | :---: | :--- |
| **Latency p50** | < 5 ms | **30.67 ms** | 31.55 ms | **6.1× slower** |
| **Latency p95** | < 10 ms | **37.37 ms** | 41.92 ms | **3.7× slower** |
| **Latency p99** | < 20 ms | **42.57 ms** | 45.83 ms | **2.1× slower** |
| **LLM Fallback Rate**| ~2% ("98% deterministic") | 0.0% (disabled) | **13.03%** (31/238 turns) | **6.5× higher** |
| **Confident-but-Wrong**| Rare (< 2%) | **35.29%** (84/238) | **45.38%** (108/238) | **Critical Risk** |

---

## 3. Top 20 Confident-But-Wrong Cases

The following cases scored $\ge 0.75$ confidence (skipping or surviving LLM fallback) yet produced incorrect structured output:

| # | Conf | Turn ID | Group | Customer Input | Expected Output | Actual Predicted Output | Impact |
| :- | :--: | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **0.96** | `real_018` | real | "Do you have stock available in Dubai right now for immediate delivery?" | `intent=availability_or_price_policy` | `intent=shipping_or_delivery` | Ignores stock/availability check |
| 2 | **0.96** | `multilingual_023` | multilingual | "scanner bhi chahiye A3 size ka" | `intent=recommend`, `media_size=a3` | `intent=product_info` | Drops purchase recommendation |
| 3 | **0.96** | `compound_003` | compound_intents | "is SC-T3100 available in stock and how fast can you deliver?" | `intent=availability_or_price_policy` | `intent=shipping_or_delivery` | Silently overrides stock check |
| 4 | **0.96** | `compound_005` | compound_intents | "give me specifications, dimensions and quotation for 2 units" | `intent=product_info` | `intent=quote_request` | Drops spec discovery |
| 5 | **0.96** | `compound_006` | compound_intents | "can you deliver to Abu Dhabi and give 10% discount?" | `intent=shipping_or_delivery` | `intent=discount_request` | Drops shipping request |
| 6 | **0.96** | `compound_008` | compound_intents | "is P900 compatible with roll paper and what is the cost?" | `intent=product_info` | `intent=compatibility_check` | Drops pricing inquiry |
| 7 | **0.96** | `compound_016` | compound_intents | "tell me about warranty and delivery charges" | `intent=product_info` | `intent=shipping_or_delivery` | Overrides warranty query |
| 8 | **0.96** | `compound_019` | compound_intents | "is this in stock in Dubai and can you deliver today?" | `intent=availability_or_price_policy` | `intent=shipping_or_delivery` | Drops stock inquiry |
| 9 | **0.96** | `ref_009` | reference_resolution | "is it suitable for CAD?" | `dialogue_act=question` | `dialogue_act=reference_follow_up` | Misclassifies dialogue act |
| 10 | **0.96** | `ref_012` | reference_resolution | "which printers work with this ink?" | `intent=product_info` | `intent=compatibility_check` | Inverts printer-ink relationship |
| 11 | **0.95** | `real_003` | real | "Does the 36-inch model come with a stand and catch basket?" | `intent=product_info`, `media_size=36inch` | `intent=recommend`, `media_size=None` | Misses 36-inch size specification |
| 12 | **0.95** | `real_005` | real | "What ink cartridges does it use and are they water resistant?" | `dialogue_act=question` | `dialogue_act=reference_follow_up` | Misidentifies dialogue act |
| 13 | **0.95** | `real_010` | real | "What makes the P900 better than an office inkjet for black and white prints?" | `intent=product_info` | `intent=recommend` | Recommends instead of providing technical spec comparison |
| 14 | **0.95** | `real_011` | real | "Does it support roll paper for panoramic gallery prints?" | `intent=product_info` | `intent=consumables_lookup` | Looks up consumables instead of feature capability |
| 15 | **0.95** | `real_014` | real | "We need a compact, super fast printer that can do 4x6 photo strips on the spot without ink drying time." | `intent=recommend`, `target_category=citizen_photo` | `intent=consumables_lookup`, `target_category=None` | Critical misroute to consumables |
| 16 | **0.95** | `real_015` | real | "How many seconds does the Citizen CX-02 take for a 4x6 print?" | `intent=product_info`, `target_attribute=print_speed` | `intent=recommend`, `target_attribute=None` | Drops print_speed attribute |
| 17 | **0.95** | `real_016` | real | "Does it use ink cartridges or dye-sub ribbon rolls?" | `intent=product_info` | `intent=consumables_lookup` | Classifies media inquiry as consumable reorder |
| 18 | **0.95** | `cat_overlap_006` | category_overlap | "fine art printing and dye sub apparel" | `intent=recommend` | `intent=other` | Drops multi-category inquiry |
| 19 | **0.95** | `cat_overlap_010` | category_overlap | "photo booth printer with sublimation ink" | `intent=recommend` | `intent=consumables_lookup` | False positive consumable match |
| 20 | **0.95** | `model_conf_004` | model_confusion | "p 7500" | `target_model=epson-sc-p7500` | `target_model=None` | Fails on spaced model name |

---

## 4. Root Cause Analysis by Failure Pattern

### Pattern A: Budget Extraction Missing from NLU
- **File & Lines**: [`conversation/understanding.py:711-867`](file:///opt/salesai/conversation/understanding.py#L711-L867)
- **Root Cause**: `TurnUnderstandingExtractor.extract_slots` extracts `target_category`, `target_model`, `media_size`, `target_attribute`, `quote_quantity`, and `primary_concern`, but **completely omits `budget_ceiling`**. Budget parsing logic is sequestered in [`conversation/product_flows.py:346`](file:///opt/salesai/conversation/product_flows.py#L346) and is never invoked during turn understanding. Furthermore, the regex in `product_flows.py` only matches `\d+`, failing on `10k`, `10,000`, and Arabic-Indic numerals `١٨٠٠`.
- **Evidence**:
  - Input: `"my budget is 10k AED"` -> `slots['budget_ceiling'] = None` (0% accuracy).

### Pattern B: Negation Blindness
- **File & Lines**: [`conversation/understanding.py:762-769`](file:///opt/salesai/conversation/understanding.py#L762-L769), [`conversation/understanding.py:205-236`](file:///opt/salesai/conversation/understanding.py#L205-L236)
- **Root Cause**: Keyword extractors use direct pattern searches (`re.search(r"\b(a4|a3)\b", text_l)` or `if "photo" in text:`) without checking polarity or negative lookbehind (`not`, `don't need`, `no`, `forget`). Negated slots are extracted as if positively asserted.
- **Evidence**:
  - Input: `"not A3"` -> `slots['media_size'] = 'a3'` (Confidence: 0.90).
  - Input: `"I don't need photo printing"` -> `slots['target_category'] = 'photo_fine_art'` (Confidence: 0.95).
  - Input: `"forget the plotter"` -> `slots['target_category'] = 'technical_cad'` (Confidence: 0.95).

### Pattern C: Category Priority Silently Drops Stated Needs
- **File & Lines**: [`conversation/understanding.py:716-733`](file:///opt/salesai/conversation/understanding.py#L716-L733)
- **Root Cause**: The slot extractor hardcodes `CATEGORY_PRIORITY` (`photo_fine_art: 1`, `citizen_photo: 2`, `technical_cad: 3`, `dye_sublimation: 4`, `scanners: 5`, `office_workforce: 6`). When a customer expresses multiple needs, the dictionary sorting retains only the first element and silently discards all others without logging an ambiguity or compound intent.
- **Evidence**:
  - Input: `"office printer for CAD drawings"` -> sets `technical_cad`, completely drops `office_workforce`.
  - Input: `"photo booth for events and also office use"` -> sets `citizen_photo`, completely drops `office_workforce`.

### Pattern D: Model Name Spacing and Typo Blindness
- **File & Lines**: [`conversation/understanding.py:84-245`](file:///opt/salesai/conversation/understanding.py#L84-L245)
- **Root Cause**: The `alias_map` caches unspaced and standard hyphenated variants (`"p7500"`, `"sc-p7500"`, `"cx02"`, `"cx-02"`), but lacks regex whitespace collapse. Inputs like `"p 7500"` or `"p 9500"` fail to match any entity. Moreover, typo `"cz02"` is hardcoded to `"citizen-cx-02"` (line 160) instead of flagging ambiguity between `CZ-01` and `CX-02`.
- **Evidence**:
  - Input: `"p 7500"` -> `target_model = None`.
  - Input: `"cz02 price"` -> silently picks `citizen-cx-02` with 0.95 confidence.

### Pattern E: Inflation of Rule Confidence Overriding Fallback Gate
- **File & Lines**: [`conversation/understanding.py:870-1175`](file:///opt/salesai/conversation/understanding.py#L870-L1175), [`conversation/understanding.py:1218`](file:///opt/salesai/conversation/understanding.py#L1218)
- **Root Cause**: Line 1218 checks `if det_understanding.overall_confidence >= 0.75: return det_understanding`. In `classify_dialogue_act_and_intent`, almost every regex rule hardcodes confidence to `0.90`, `0.95`, or `0.99`. Even incidental token overlaps (e.g., matching `"ink"` inside `"What makes P900 better than an office inkjet"`) return `0.95` confidence and route to `consumables_lookup`, completely preventing LLM fallback.
- **Evidence**:
  - Out of 238 turns, 191 received confidence $\ge 0.90$, yet 37.7% of them contained wrong slot or intent extractions.

### Pattern F: Dialogue Act Defaulting to `QUESTION`
- **File & Lines**: [`conversation/understanding.py:313`](file:///opt/salesai/conversation/understanding.py#L313), [`conversation/understanding.py:873`](file:///opt/salesai/conversation/understanding.py#L873)
- **Root Cause**: The parser initializes `dialogue_act = DialogueAct.QUESTION` and only overrides it if specific statement keywords are present. Empty strings, whitespace, and emoji sequences default to `DialogueAct.QUESTION`.
- **Evidence**:
  - Input: `""` -> `dialogue_act=DialogueAct.QUESTION`, `intent=Intent.OTHER`, `confidence=0.60`.
  - Input: `"🖨️📸🔥"` -> `dialogue_act=DialogueAct.QUESTION`, `intent=Intent.OTHER`, `confidence=0.60`.

---

## 5. Category Confusion Matrix

Analysis of expected vs predicted categories across evaluated turns:

```
Expected \ Predicted      | citizen_ph | dye_sublim | none       | office_wor | photo_fine | scanners   | technical_
--------------------------------------------------------------------------------------------------------------------
citizen_photo             | 4          | 0          | 2          | 0          | 1          | 0          | 0          |
dye_sublimation           | 0          | 4          | 1          | 0          | 1          | 0          | 0          |
office_workforce          | 0          | 0          | 1          | 4          | 0          | 0          | 0          |
photo_fine_art            | 0          | 0          | 3          | 0          | 7          | 1          | 0          |
scanners                  | 0          | 0          | 0          | 0          | 0          | 2          | 0          |
technical_cad             | 0          | 0          | 1          | 0          | 0          | 0          | 10         |
```

**Key Takeaways**:
- `photo_fine_art` falsely captures queries intended for `citizen_photo` and `dye_sublimation` due to the word "photo" having higher priority in `CATEGORY_PRIORITY`.
- 8 category queries were predicted as `none` because non-English or colloquial expressions were missed by deterministic regexes.

---

## 6. Ranked Fix List (Impact × Frequency)

| Rank | Issue | Impact | Frequency | Action Type | Recommended Action |
| :-: | :--- | :---: | :---: | :--- | :--- |
| **1** | **Budget Ceiling slot missing** | Critical | High (100% of budgets) | **Add Rule + Add Test** | Move and enhance budget extraction into `extract_slots`: support `k`/`K` (10k -> 10,000), commas (`10,000`), ranges, and convert Arabic-Indic digits (`٠-٩`). |
| **2** | **Negation blindness** | High | High (68.2% of negations) | **Add Rule + Add Test** | Add negative lookbehind and prefix polarity check (`not`, `no`, `don't want`, `except`, `forget`) before setting `media_size`, `target_category`, or `target_model`. |
| **3** | **Uncalibrated confidence gate** | High | High (45.4% of turns) | **Route to LLM Fallback** | Lower base regex confidence from hardcoded `0.95` to `0.70` when query contains competing keywords, negations, or non-ASCII tokens. Lower gate threshold or invoke LLM on ambiguous multi-intent signals. |
| **4** | **Spaced model names ("p 7500")** | High | Medium (35% of model typos) | **Add Rule** | Normalize user text by collapsing single-letter prefixes followed by spaces and digits (e.g. `re.sub(r"\b([a-z]{1,2})\s+(\d{3,4})\b", r"\1\2", text)`). |
| **5** | **Category priority suppression** | Medium | Medium (30% of overlaps) | **Ask Clarification** | When multiple categories match (e.g. `office` + `cad`), set `ambiguities=["multiple_categories"]` and generate a clarification prompt rather than silently discarding the lower-priority category. |
| **6** | **Multilingual queries drop to `other`** | High | Medium (25% of multilingual) | **Route to LLM Fallback** | Detect non-Latin scripts (Arabic, Devanagari, Malayalam) and immediately route to Ollama LLM fallback instead of evaluating against English regexes. |
| **7** | **Ambiguous model typos ("cz02")** | Medium | Low (10% of typos) | **Ask Clarification** | Remove hardcoded `"cz02": "citizen-cx-02"` alias. Flag as ambiguous between `CZ-01` and `CX-02` and prompt user to clarify. |
| **8** | **Empty / Emoji input default to QUESTION**| Low | Low (edge cases) | **Add Rule + Add Test** | Check `if not text.strip() or not re.search(r"\w", text): return DialogueAct.CLARIFICATION, Intent.OTHER, 0.20`. |

---

## 7. What Was NOT Verified and Why

1. **Production Redis / Customer Conversation Dumps**: Real production message history was not available in this workspace (no Redis instance or raw production chat DB). Real customer messages were mined from local test fixtures (`qa_tests/test_qa_humanisation.db`) with PII removed.
2. **Network Webhook Jitter & Real-Time WhatsApp Latency**: Benchmarks reflect pure Python process execution time in Linux (`venv/bin/python3.12`), excluding network round-trip time between Meta WhatsApp Cloud API and the webhook handler.
3. **Large Parameter LLM Models**: Evaluation was performed using local Ollama `qwen2.5:latest` (7B parameter model) as configured in the repository. Larger 70B+ parameter models or commercial cloud APIs (OpenAI / Claude) were not benchmarked.
