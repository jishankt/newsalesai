# Conversational Routing & Interceptor Audit

**Date**: 2026-10-12  
**Repository**: `jishankt/newsalesai`  
**Scope**: Systematic audit of all conversational routes, regex interceptors, guardrails, and decision branches across `agent/orchestrator.py`, `conversation/*`, `catalog/*`, and `rag/*` that can return a response before or without proper conversation context consultation.

---

## 1. Executive Summary & Root Cause Analysis

A major architectural liability in the existing pipeline is **order-dependent, phrase-by-phrase regex routing** executed before or during orchestrator processing. Over 130 distinct interceptors and routes match on surface keywords rather than resolving the customer's true dialogue act, intent, and conversational referents.

### The Specific Target Failure
> **Scenario**: The bot displays ink `C13T49N400` (Epson T49N yellow sublimation ink). The customer asks:  
> *"this is suitable for f500"*  
> **Actual Behavior (Hijacked)**: The system triggers `agent:dye_sublimation_recommendation` (lines 1710–1770) because `"f500"` matched the category discovery trigger. It discarded `state.active_consumable`, ignored `"this"`, and returned a generic SC-F100 vs SC-F500 overview rather than a yes/no compatibility confirmation.  
> **Required General Behavior**:
> 1. Turn understanding identifies: `intent: compatibility_check`, `reference: "this"`, `target: "f500"`.
> 2. Dialogue state resolves: `"this"` $\rightarrow$ `C13T49N400` (from `last_shown_consumables` / `focus_entity`), `"f500"` $\rightarrow$ `epson-sc-f500`.
> 3. Evidence layer evaluates `check_compatibility(item="C13T49N400", target="epson-sc-f500")` $\rightarrow$ `VERIFIED_YES`.
> 4. Policy emits a grounded `ANSWER` confirming compatibility, displaying the product card, without hijacking to a generic overview.

---

## 2. Comprehensive Interceptor & Route Inventory

Below is the complete map of routes and interceptors evaluated in execution order within `agent/orchestrator.py` and supporting modules.

| Line Range | Route / Interceptor Name | Trigger Condition | Reads Session Context? | Can Hijack Follow-up? | Impact / Failure Modes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **308–340** | `guardrail:untrusted_instruction` | Prompt injection regexes (`ignore instructions`, `system override`, `developer debug mode`, etc.) | No | Low | Correct security guardrail. Preserved. |
| **343–408** | `route:consumables:direct_sku` (Early) | SKU pattern match in text (`c1[123]...`, `ms...`, `ifa...`, `olm...`) | Partial (`state.last_explicit_product_id` if no model named) | **HIGH** | If a customer provides a SKU in a complex follow-up, it intercepts before intent analysis. Does NOT trigger if customer uses reference pronoun ("this") referring to a shown SKU. |
| **410–445** | `recommendation:catalogue_list` | "single paper roll", "ribbon rewind", "without media loss", "6x8" + "single roll" | No | **HIGH** | Hijacks any follow-up mentioning paper rolls or rewind to Citizen CX-02 even if discussing another printer. |
| **447–494** | `guardrail:commercial_policy` (CX-02W media) | "media" + ("cx-02w" or "this printer") | Partial (`state.active_product_id == "citizen-cx-02w"`) | Medium | Diverts price/media inquiry to sales rep. |
| **495–515** | `guardrail:discount_refusal` | Discount keywords (`discount`, `best price`, `cheapest price`) | Yes (`state.active_product_id`) | Medium | Preserved commercial guardrail. |
| **517–545** | `guardrail:commercial_policy` | Pricing inquiry keywords for hardware | Yes (`state.active_product`) | Medium | Preserved commercial guardrail. |
| **547–571** | `route:unsupported_category` | Labels, stickers, vinyl cutter, resin 3d, uv flatbed | No | **HIGH** | If mentioned in comparative questions, abruptly exits to out-of-scope refusal. |
| **573–594** | `route:compatibility_warning` | Cotton / 100% cotton + dye sublimation | Yes (`state.category == "dye_sublimation"`) | Low | Domain warning for cotton on sublimation. |
| **596–618** | `qualification:category_prompt` (Greeting) | `canonical_turn.primary_intent == "greeting"` | No | Medium | Can intercept short greetings in mid-dialogue. |
| **620–695** | `qualification:category_prompt` (Category Select) | `is_scanner_select`, `is_printer_select`, `is_consumable_select` | No | **CRITICAL** | If user says "inks" or "printers" while a printer is in focus, it asks "Which printer do you have?" rather than listing consumables for active printer. |
| **696–764** | `1b-5. Consumables Selection Follow-up` | `state.waiting_for_consumable_model` or `state.last_shown_options` | Yes | Medium | Linear state machine branch. |
| **765–960** | `1c. Direct Answer for Explicit Questions` | `canonical_turn.explicit_questions` | Partial | **HIGH** | Contains duplicate regex routing and hardcoded `direct_sku` fallback. |
| **1000–1170**| `route:product_spec_attribute` & `agent:direct_comparison` | Attribute or comparison keywords | Yes | Medium | Compares models but lacks general ellipsis resolution. |
| **1175–1215**| `agent:closing` | "thank you", "bye", "goodbye" | No | Low | Closes session. |
| **1220–1250**| `agent:delivery_policy` | Shipping / delivery questions | No | Low | Direct policy reply. |
| **1251–1270**| `agent:acknowledgment` | "ok", "got it", "sure", "thanks" | No | **HIGH** | Steals short confirmation responses ("ok", "yes") instead of binding to `pending_question` options. |
| **1272–1290**| `capability:language` | Language queries ("speak arabic?") | No | Low | Informational response. |
| **1370–1410**| `agent:price_objection` | "too expensive", "high price" | Yes | Medium | Justifies value / proposes tier alternatives. |
| **1490–1650**| `recommendation:citizen_*` | Citizen model keywords (`citizen`, `cz-01`, `cx-02`, etc.) | No | **HIGH** | Mentioning a Citizen model triggers discovery cards instead of answering specific follow-up questions. |
| **1690–1707**| `agent:investment_cost_comparison` | Investment cost keywords | No | Medium | Heuristic comparison. |
| **1710–1770**| `agent:dye_sublimation_recommendation` | Keywords `["dy sublimation", "dye sublimation", "sublimation", "f100", "f500", "t-shirt", "mug"]` | **Ignored** | **CRITICAL (Primary Bug)** | **Directly causes the target failure.** Any message containing `"f500"` or `"f100"` triggers the category overview, completely ignoring active consumables and compatibility queries. |
| **1772–1810**| Product Page Purchase Link | "how do i buy", "purchase link", "where to buy" | Yes | Medium | Generates direct links. |
| **1830–1870**| `route:category_switch` | Category switch keywords | Yes | Medium | Switches focus category. |
| **1950–1980**| `route:customer_login_help` | Login/account keywords | No | Low | Account guidance. |
| **2000–2450**| Heuristic Interceptors (`frustration_recovery`, `redisplay_card`, `datasheet_brochure`, `warranty_info`, `accessory_classification`, etc.) | Individual regex phrases | Partial | **HIGH** | Scattered regex interceptors that pre-empt structured understanding. |
| **5433–5590**| `6b. Exact Model Detail Inquiry` | Specific model mentions with specs intent | Partial | Medium | Formats specs card for model. |

---

## 3. Supporting Module Deficiencies

### A. `conversation/reference_resolver.py`
- **Printer-Only Limitation**: Exclusively resolves hardware printers via `_to_prod_dict()`. Completely blind to consumables (`active_consumable`, `last_shown_consumables`).
- **Single-Entity Assumption**: Cannot resolve a turn containing BOTH a reference expression and an explicit entity (e.g., `"this [reference: consumable] is suitable for f500 [explicit: printer]"`).

### B. `conversation/contextual_slot_resolver.py`
- Lacks a typed dialogue act taxonomy (confirmation, rejection, ellipsis, clarification).
- Does not maintain a salience-ranked focus stack (`last_shown > pending_options > focus_stack > recent_mentions`).

### C. `catalog/catalogue_resolver.py` & `rag/retriever.py`
- Operates on unstructured keyword queries rather than a typed Knowledge Graph with verified relationship edges (`uses_consumable`, `compatible_with`, `alternative_of`).

---

## 4. The Strangler Architecture: Insertion Point

To prevent regressions across the 7,480 lines of `agent/orchestrator.py` while universally resolving conversational follow-ups:

```
Customer Message
       │
       ▼
[node_understand] / [node_reconcile] (Lines 274-288)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  UNIFIED UNDERSTANDING & FALLBACK ENGINE (Strangler Layer)  │
│  Behind feature flag: USE_UNIFIED_UNDERSTANDING=true        │
│                                                             │
│  1. Structured Understanding (DialogueAct, Intent, Entities)│
│  2. Dialogue State & Multi-Referent Resolution              │
│  3. Typed Evidence Layer (Knowledge Graph)                  │
│  4. Fallback Policy Engine (Actions & Guardrails)           │
│  5. Response Plan & Validation                              │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
   [Plan Executable?]                     [No Plan / Flag=False]
            │                                     │
      YES   ▼                                     ▼
Return Verified Response Plan           Fall Through to Legacy
with Cards, Chips & Confirmations       Orchestrator Routes
```

### Strangler Gate Rules:
1. **Hook Location**: Right after `StateReconciler.reconcile` (line 288) and before adversarial/SKU/category interceptors.
2. **Feature Flag**: `USE_UNIFIED_UNDERSTANDING = os.getenv("USE_UNIFIED_UNDERSTANDING", "false").lower() == "true"` (defaults to `false` until approved).
3. **Execution Guarantee**: If the Unified Engine produces a validated response plan, the turn terminates immediately with verified facts and UI artifacts.
4. **Safety Net**: If the unified layer cannot confidently handle the dialogue act or returns `None`, it seamlessly falls through to the existing orchestrator pipeline without disrupting existing tests.
