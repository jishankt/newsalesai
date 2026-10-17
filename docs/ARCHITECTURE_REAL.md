# Real Architectural Map & Module Status

**System**: Kepler Tech B2B Sales Chatbot (`newsalesai`)  
**Channel Target**: Dedicated Web Chat (`keplarbot.kylesolutions.in`), Customer Onboarding, Live Sales Desk Takeover  
**Document Purpose**: Definitive inventory of active, legacy, and dead components with a non-destructive migration roadmap.

---

## 1. Module Inventory & Status

| Module / Directory | Classification | Runtime Reality & Execution Path | Reason for Classification |
| :--- | :--- | :--- | :--- |
| `app.py` | **LIVE (Primary)** | Central HTTP Flask entrypoint handling `/api/chat`, auth routes, polling, and admin dashboard mounting. | Production entrypoint. |
| `agent/orchestrator.py` | **LIVE (Primary Core)** | Monolithic procedural turn coordinator (~7,700 lines). Executes NLP normalization, pre-classification, turn understanding, state reconciliation, catalog retrieval, and response composition. | Live chat requests invoke `orchestrator.process_turn()` directly. |
| `conversation/policy.py` | **LIVE (Primary Core)** | Policy rules, requirement gating, category disambiguation, and sales progression logic. | Core decision brancher invoked during `process_turn()`. |
| `conversation/understanding.py` | **LIVE** | Slot extraction, entity normalization, and canonical turn intent detection. | Invoked on every inbound turn. |
| `conversation/dialogue_state.py` | **LIVE (Legacy-Bound)** | In-memory slot tracker (`DialogueState`). Synced bi-directionally with `ConversationState`. | Actively mutated during orchestrator turns. |
| `domain/conversation_state.py` | **LIVE (Canonical)** | Data schema for session serialization, customer ID tracking, and database commits. | Stored in SQLite (`conversations.db`). |
| `domain/state_store.py` | **LIVE** | Thread-safe in-memory session manager with TTL, HMAC signing, and session concurrency locks. | Primary state layer for web chat. |
| `catalog/repository.py` | **LIVE** | Authoritative catalog index for Epson and Citizen commercial equipment and consumables. | Authoritative data store. |
| `catalog/price_resolver.py` | **LIVE** | Deterministic quoting calculator, VAT (5%) math, and quote suppression. | Truth layer for pricing. |
| `catalog/cost_per_print_calculator.py` | **LIVE** | Cartridge yield and running cost arithmetic calculator. | Truth layer for TCO inquiries. |
| `persistence/trace_repository.py` | **LIVE** | SQLite trace and node event logger feeding the real-time admin observability canvas. | Stores real node timing and statuses. |
| `workflow/engine.py` | **DEAD CODE** | 11-node n8n-style graph engine (`WorkflowEngine`). | **Never executed in production chat.** Only invoked via unit test `test_workflow_engine.py` and diagnostic route `/api/workflow/run`. |
| `agents/receptionist_agent.py` | **DEAD CODE** | Standalone receptionist agent class. | Never invoked by live chat; `orchestrator.py` executes procedural rules directly. |
| `agents/product_catalog_agent.py` | **DEAD CODE** | Standalone catalog specialist agent class. | Never invoked by live chat; orchestrator queries `catalog/` directly. |
| `agents/technical_rag_agent.py` | **DEAD CODE** | Technical RAG specialist agent class. | Never invoked by live chat; orchestrator routes via `routes/product_route.py`. |
| `agents/pydantic_ai_agent.py` | **DEAD CODE** | PydanticAI-style experimental agent wrapper. | Completely disconnected from live chat loop. |
| `routes/qualification_route.py` | **LEGACY (Unused)** | Experimental router for qualification. | Bypassed by `conversation/policy.py`. |
| `routes/support_route.py` | **LEGACY (Unused)** | Experimental support router. | Bypassed by `conversation/policy.py`. |
| `routes/help_and_guardrail_route.py`| **LEGACY (Unused)** | Early guardrail router. | Superseded by `agent/naturalness_validator.py`. |
| `conversation/message_buffer.py` | **LIVE (Re-Wired Phase 1)**| Consecutive message aggregator and debouncer. | Now actively wired to `app.py` `/api/chat` with 1.5s window. |

---

## 2. Real vs Simulated Execution Flow

### Historical Simulation (Pre-Audit)
Historically, `agent/orchestrator.py` emitted hardcoded dummy timings (`1.2ms`, `0.8ms`, `2.1ms`, `0.7ms`) for `node_tool`, `node_evidence`, `node_compose`, `node_validate`, and `node_stop` to fabricate an 11-node n8n graph execution for the admin dashboard, even when those nodes never ran.

### Truthful Observability (Post-Phase 2 Fix)
- Real start and end timestamps are recorded for every active stage.
- If a turn resolves deterministically via direct policy or greeting:
  - `node_tool` is explicitly marked `status="skipped"`, `duration_ms=0.0`.
  - `node_evidence` is explicitly marked `status="skipped"`, `duration_ms=0.0`.
  - ASCII trace renders skipped nodes with `⊘` instead of a falsified `✓`.
- Real execution durations reflect genuine wall-clock time spent in NLU, catalog retrieval, and validator passes.

---

## 3. Proposed (Non-Breaking) Migration & Deletion Plan

To eliminate technical debt without risking production regressions:

### Phase A: Deprecate Dead Agent Stubs (Safe)
- Keep classes in `agents/` (`receptionist_agent.py`, `product_catalog_agent.py`, `technical_rag_agent.py`, `pydantic_ai_agent.py`) as inert wrappers for now.
- Add `@typing.deprecated` or docstring notices marking them internal/legacy.
- No production imports depend on them.

### Phase B: Unify Workflow Engine or Retire `/api/workflow/run`
- Currently, `/api/workflow/run` is an ungrounded alternative pipeline.
- Plan: Either deprecate `/api/workflow/run` and standardise tests onto `/api/chat`, or extract the procedural stages in `orchestrator.py` into genuinely decoupled callable nodes that both `/api/chat` and `WorkflowEngine` execute.

### Phase C: Dual State Consolidation (Phase 3 of Audit Fix)
- Merge `conversation.dialogue_state.DialogueState` into `domain.conversation_state.ConversationState`.
- Eliminate the ~70-line bidirectional translation layer in `orchestrator.py:387-455`.
- Unify conflicting `Intent` enums into `domain.conversation_types.Intent`.
