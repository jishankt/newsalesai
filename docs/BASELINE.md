# Baseline Conversational Battery Evaluation (Phase 0)

**Commit**: `653c83f` (feature/universal-understanding-production-ready)  
**Date**: October 12, 2026  
**Environment**: Local Offline Mode (Ollama Mocked)  
**Harness**: `scripts/battery.py` (47 turns across 19 conversational scenarios)

---

## Executive Summary

| Metric | Baseline Value | Target |
| :--- | :--- | :--- |
| **Total Turns Evaluated** | 47 | 47 |
| **Generic Fallback Count / Rate** | 0 (0.0% on strict phrasing) / 5 turns hitting category select fallback | <= 3.0% |
| **Identical Consecutive Replies** | 9 | 0 |
| **Turns With Next Step / Chips** | 46 (97.87%) | 100% |
| **Turns With Product/Consumable Cards** | 10 (21.28%) | Re-enabled post qualification |
| **Leaked Template Markers (` = `, `display_name`, etc.)** | 4 | 0 |
| **Wrong Model Substitutions (Silent fuzzy mismatch)** | 2 | 0 |

---

## Key Failure Patterns Identified

1. **Raw Claims Leaking Internal Structure (Cases 1, 2, 10)**:
   - Queries like `"tell me about the SC-T5100"` or `"what is the speed of the WF-C20600"` produce responses such as:
     `"Epson SureColor SC-T5100 has display_name = Epson SureColor SC-T5100"`
     `"Epson WorkForce Enterprise WF-C21000 D4TW has display_name = ..."`
   - `catalog/evidence.py:256` generates raw claim strings that leak `{field} = {val}` into user-facing copy.

2. **Silent Fuzzy Substitution (Cases 2, 7)**:
   - Query `"what is the speed of the WF-C20600"` silently matches and answers for `"WF-C21000 D4TW"`.
   - Query `"how much is the Citizen CX-02W"` lists CX-02 / CY-02 rather than detecting that CX-02W is not in the approved catalogue.

3. **Repetition & Stale Cache on Unverified Queries (Case 6)**:
   - Asking `"does it come with a stand?"` repeats the exact previous reply rather than stating honestly that the specification is unverified in data.

4. **Hardcoded Delivery & Ignored Country/Urgency Constraints (Case 3)**:
   - Questions like `"can you deliver today"` or `"do you ship to india"` receive the hardcoded UAE insured delivery blurb from `conversation/policy.py:270`.

5. **Empty Model Comparison (Case 10)**:
   - `"compare SC-F100 and SC-F500"` outputs `"Compared 2 models across fields: category, width, resolution, speed, connectivity."` with zero tabular or side-by-side comparison data.

6. **Short Replies, Objections & Lead Capture Dropped to Fallback (Cases 13, 14)**:
   - `"okay I'll think about it"`, `"the first one"`, and `"my name is Ali and number is 0501234567"` all trigger the generic category selection fallback.

7. **Repeated Inputs Triggering Verbatim Duplicates (Case 16)**:
   - Inputting `"printer for office"` three times in a row yields the exact same long category overview paragraph three times.

---

## Artifacts Generated
- Run dataset: `data/battery_latest_run.json`
- Test Harness: `scripts/battery.py`
