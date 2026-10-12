# Kepler Tech SalesAI: Tomorrow's Implementation Plan

**Branch:** `feature/production-ready-v1`  
**Base Commit:** `653c83f`  
**Latest Commits:**
- `fa4edc6`: *feat(baseline): add repeatable battery harness and baseline documentation* (Phase 0)
- `49f43fc`: *fix(phase-1): resolve customer-visible bugs cases 1-12 and 18* (Phase 1)
**Execution Environment:** Local Xeon 4-core, NVIDIA RTX 6000 (24 GB VRAM), Local Ollama (`http://127.0.0.1:11434`)

---

## 1. Executive Summary & Starting Point

All foundational baseline and Phase 1 customer-visible bugs are resolved, committed, and tested:
- **Baseline Battery:** 47 turns across 19 conversations in [`scripts/battery.py`](file:///opt/salesai/scripts/battery.py)
- **Phase 1 Automated Test Suite:** 11/11 tests passing in [`tests/test_phase1_customer_visible_bugs.py`](file:///opt/salesai/tests/test_phase1_customer_visible_bugs.py)
- **Leaked Template Markers:** **0** (was 4)
- **Wrong Model Substitutions:** **0** (was 2)
- **Generic Fallback Rate:** **0.0%** (was 34.0%)
- **Turns with Next Step / Chips:** **100.0%** (47/47 turns)
- **Offline Multi-Agent Core Runner:** Completed in [`jobs/runner.py`](file:///opt/salesai/jobs/runner.py) with typed Pydantic steps, retry, and proposal isolation.

---

## 2. Priority 1: Complete Offline Multi-Agent Jobs (`jobs/`)
*Estimated time: ~25 minutes. Must NEVER run inside the `/api/chat` request path.*

### Files to Create:
1. `jobs/job_product_enrichment.py`:
   - Iterate through catalogue models in [`data/catalogue_products.json`](file:///opt/salesai/data/catalogue_products.json).
   - Fetch product pages and brochures (respect `robots.txt`, 1.5s rate limit, cache raw HTML in `data/html_cache/`).
   - Extract structured fields: specs, connectivity, accessories, consumables, media, warranty, use cases with `source_url` per field.
   - Diff against catalogue, flag conflicts, draft `best_for` / `not_ideal_for` only from source text.
   - Write proposals to `data/proposals/` and output `docs/ENRICHMENT_REPORT.md`.
2. `jobs/job_nightly_qa.py`:
   - Ingest conversations from database and `data/review_queue.jsonl`.
   - Score each turn: `answers_the_question`, `model_consistency`, `fact_grounding` (deterministic), and `naturalness` (LLM judge using `QA_NATURALNESS_RUBRIC`).
   - Cluster failure patterns; auto-draft proposed pytest regression tests in `tests/proposed/`.
   - Output daily markdown report with top 10 failure patterns.
3. `jobs/job_lead_brief.py` & `jobs/notifier.py`:
   - Extract lead attributes (name, phone, product interest, volume, urgency, next step) from conversation state.
   - LLM step generates a concise executive brief paragraph.
   - Dispatch brief via `jobs/notifier.py` interface (Webhook / SMTP with retry & backoff, idempotent by `lead_id`).
4. `jobs/job_policy_drift.py`:
   - Weekly fetch of Kepler Terms & Conditions and FAQ pages.
   - Extract delivery, returns, and payment sections; diff against `data/delivery_policy.json` to flag drift.
5. `scripts/apply_proposal.py`:
   - CLI tool for humans to review and apply proposals (`--list`, `--apply <proposal_id>`, `--dry-run`).
   - Ensures no job writes directly to production data without human review.
6. `tests/test_offline_jobs.py`:
   - Test all 4 jobs against fixtures with Ollama mocked offline.
   - Verify missing values stay `"missing"` (no hallucinated defaults).
   - Verify malformed LLM JSON is retried once and logged.
   - Verify proposals cannot mutate production files without `apply_proposal.py`.
   - **Import-graph test:** Verify that `jobs` is NOT imported by any chat module (`app.py`, `agent/orchestrator.py`, `routes/`, `conversation/`).

**Commit:** `feat(jobs): implement offline multi-agent jobs package and proposal review tool`

---

## 3. Priority 2: Phase 2 – Delivery & Policy Knowledge Base
*Estimated time: ~15 minutes.*

1. **Create `data/delivery_policy.json`:**
   - Extract from Kepler Terms & Conditions (s3, s4, s7, s8, s10) and FAQ.
   - Grounded facts: UAE flat AED 10; outside UAE checkout calculation; dispatch 1–2 business days; free store pickup; payment in full before dispatch; report defects within 2 days; 24-hr order cancellation; no trade with OFAC countries; Dubai hours (Mon–Fri 8:30–17:30, Sat 8:30–13:00).
   - Document conflicts as `status: "conflict"` in data and update [`docs/DECISIONS_NEEDED.md`](file:///opt/salesai/docs/DECISIONS_NEEDED.md).
2. **Wire 12 Delivery Intents in `conversation/policy.py`:**
   - Replace hardcoded delivery strings with dynamic zone lookups (`UAE`, `OMAN`, `GCC_OTHER`, `OUTSIDE_GCC`, `SANCTIONED`, `UNKNOWN`).
   - Implement targeted responses for: `coverage`, `fee`, `time`, `pickup`, `tracking`, `courier`, `returns`, `cancellation`, `customs`, `payment`, `same_day`, `hours`.
   - Ask destination once with chips; remember it.
3. **Phase 2 Gate:**
   - All 12 delivery scenarios in test suite receive targeted verified answers.

**Commit:** `feat(phase-2): add verified delivery knowledge base and zone-aware policy engine`

---

## 4. Priority 3: Phase 3 – Understanding & Fallback Ladder
*Estimated time: ~15 minutes.*

1. **Structured `decide()` Ladder:**
   - Priority sequence: Dialogue state -> Verified evidence -> Stated assumption -> Confirm chips -> Targeted single question (2–4 chips) -> Honest partial answer -> Human handoff.
   - Eliminate all generic fallbacks mid-conversation.
2. **Anti-Repeat & Frustration Guard:**
   - Calculate similarity to last 2 assistant replies; block if $>85\%$ similar.
   - Acknowledge repeated customer slot ("Understood, A4 office printer") and advance forward.
   - Frustrated phrases ("I already said", "useless") trigger apology and handoff offer.
3. **Mid-Conversation Continuity:**
   - Greetings mid-chat ("Hi") continue the active discussion topic instead of restarting the welcome flow.
   - Bind short replies ("yes", "ok", "2", "the first one") to pending options.
4. **Phase 3 Gate:**
   - `generic_fallback_rate <= 3%`, `identical_consecutive_replies == 0` on battery.

**Commit:** `feat(phase-3): implement unified fallback ladder, anti-repeat, and continuity`

---

## 5. Priority 4: Phase 4 – Sales Behaviour & Qualification Budget
*Estimated time: ~20 minutes.*

1. **Qualification Budget:**
   - Maximum 3 qualification questions per flow before delivering leaf recommendations with product cards.
2. **Card Presentation:**
   - Show 1 primary recommended model + up to 2 verified alternatives with evidence-based rationale.
   - Strict adherence to no-pricing in chat (cards display "Request Quote" buttons).
3. **Objection Handling:**
   - Empathize with price objections, highlight productivity/yield specs, offer lower-spec verified alternatives, offer specialist quote.
4. **Lead Capture with Consent:**
   - Extract name, email, and UAE phone format (`+971 5x...`, `050...`) from natural text.
   - Confirm details, save in lead repository, and trigger Job 3 lead brief notifier.
5. **Phase 4 Gate:**
   - Office, plotter, photo, and scanner flows reach recommendations with cards within 4 turns.

**Commit:** `feat(phase-4): add qualification budget, card recommendations, and lead capture`

---

## 6. Priority 5: Phases 5 & 6 – Humanisation & Accuracy Guards
*Estimated time: ~15 minutes.*

1. **Humanisation:**
   - Wire rotating openers (8+ variants, 3-turn no-repeat) from `conversation/response_plan.py`.
   - Banned phrase filter ("Certainly!", "delighted to assist", "Based on your requirements").
   - Category intro paragraph shown only once per session; subsequent turns use short acknowledgments.
   - Enforce response length under ~60 words (unless technical comparison table).
2. **Pre-Transmission Accuracy Guard:**
   - Enforce gate on every outgoing message: every SKU, spec, and model must exist in collected evidence.
   - If validation fails, fallback to deterministic template from evidence; never hallucinate.
   - Update QA scorer in `qa_tests/run_humanisation_conversations.py`.

**Commit:** `feat(phase-5-6): wire naturalness openers, session caps, and accuracy guard`

---

## 7. Priority 6: Phases 7 & 8 – Production Resilience & Full DoD
*Estimated time: ~25 minutes.*

1. **Reliability & Production:**
   - LLM timeout + circuit breaker (opens after $N$ failures, half-open health probe).
   - `/health/ready` endpoint reporting `ready` vs `degraded`.
   - SQLite WAL mode + busy timeout + connection pooling.
   - Production deployment files: Gunicorn (`--workers 1 --threads 4`), systemd service unit, Nginx reverse proxy template.
   - Security: escape bot text before rendering in UI, add CSP and HSTS headers.
2. **Model Benchmark Script (`scripts/benchmark_models.py`):**
   - Benchmark 50 test queries across installed local models (`qwen2.5:14b`, `qwen3:30b`, `qwen2.5:32b`, `gpt-oss:20b`, `qwen3:8b`).
   - Report tokens/s, p50/p95 latency, JSON parse rate, VRAM usage; save to `docs/MODEL_BENCHMARK.md`.
3. **Phase 8 Tests & Final Verification:**
   - Run full test suite: `python -m pytest tests -q --ignore=tests/legacy`.
   - Metamorphic tests (typos, shorthand, case, Arabic/English mix).
   - Persona simulator (terse, rambling, frustrated, indecisive).
   - Generate final Definition of Done report.

**Commit:** `feat(phase-7-8): production hardening, circuit breaker, benchmarks, and full DoD verification`

---

## 8. Exact Commands to Resume Tomorrow

To resume execution directly from Step 1, run:
```bash
cd /opt/salesai
source venv/bin/activate
git status
python -m pytest tests/test_phase1_customer_visible_bugs.py -v
```

Then proceed with implementing the offline jobs:
```bash
# Verify offline jobs execution
python -m pytest tests/test_offline_jobs.py -v

# Run the repeatable dialogue battery
python scripts/battery.py
```
