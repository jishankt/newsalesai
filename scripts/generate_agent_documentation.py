#!/usr/bin/env python3
"""
Generate comprehensive AI_AGENT_DOCUMENTATION.md covering all agent files and contents.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "AI_AGENT_DOCUMENTATION.md"

AGENT_DIR = BASE_DIR / "agent"
AGENTS_DIR = BASE_DIR / "agents"

def read_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

doc_content = []

doc_content.append("""# Kepler Tech SalesAI — AI Agent Architecture & Full Code Documentation

This document provides a comprehensive technical architecture guide, workflow specifications, and the complete source code contents for all AI Agent files in the Kepler Tech SalesAI repository.

---

## Table of Contents

1. [Executive Overview & Dual-Layer Architecture](#1-executive-overview--dual-layer-architecture)
2. [Agent System Interaction Diagram](#2-agent-system-interaction-diagram)
3. [Core Decision & Orchestration Engine (`agent/`)](#3-core-decision--orchestration-engine-agent)
   - [3.1 `agent/route_registry.py`](#31-agentroute_registrypy)
   - [3.2 `agent/tool_registry.py`](#32-agenttool_registrypy)
   - [3.3 `agent/tool_executor.py`](#33-agenttool_executorpy)
   - [3.4 `agent/decision_engine.py`](#34-agentdecision_enginepy)
   - [3.5 `agent/evidence_planner.py`](#35-agentevidence_plannerpy)
   - [3.6 `agent/response_composer.py`](#36-agentresponse_composerpy)
   - [3.7 `agent/orchestrator.py`](#37-agentorchestratorpy)
4. [Specialist Sub-Agents Framework (`agents/`)](#4-specialist-sub-agents-framework-agents)
   - [4.1 `agents/__init__.py`](#41-agents__init__py)
   - [4.2 `agents/base_agent.py`](#42-agentsbase_agentpy)
   - [4.3 `agents/receptionist_agent.py`](#43-agentsreceptionist_agentpy)
   - [4.4 `agents/product_catalog_agent.py`](#44-agentsproduct_catalog_agentpy)
   - [4.5 `agents/technical_rag_agent.py`](#45-agentstechnical_rag_agentpy)
   - [4.6 `agents/sales_lead_agent.py`](#46-agentssales_lead_agentpy)
   - [4.7 `agents/pydantic_ai_agent.py`](#47-agentspydantic_ai_agentpy)
5. [Cross-Agent Communication & Conversation Lifecycle](#5-cross-agent-communication--conversation-lifecycle)
6. [Summary File Index](#6-summary-file-index)

---

## 1. Executive Overview & Dual-Layer Architecture

Kepler Tech SalesAI utilizes a **dual-layer agent architecture**:

1. **The Core Decision & Orchestration Layer (`agent/`)**:
   - Designed for high-concurrency, deterministic-first customer conversations.
   - Enforces fail-closed commercial guardrails, 10-tier routing priority, and 3-valued truth logic.
   - Plans verified database evidence before LLM synthesis to eliminate hallucinations.
   - Manages stateful turn tracking, anti-frustration loops, and product qualification.

2. **The Specialist Sub-Agents Layer (`agents/`)**:
   - Modular, persona-based sub-agents for specialized tasks:
     - **Receptionist Concierge**: General inquiries, showroom location, business hours.
     - **Product Catalog Specialist**: Category qualification, model discovery, paper-size matching.
     - **Technical RAG Specialist**: In-depth comparisons, DPI, print speed, ink technology.
     - **Sales Lead Specialist**: CRM lead generation, customer contact capture, quote requests.
     - **PydanticAI Specialist**: Structured schema validation, calculator tools, and enterprise execution.

---

## 2. Agent System Interaction Diagram

```mermaid
flowchart TD
    USER(["👤 Customer / Sales Inquirer"]) --> GATEWAY["API Gateway (app.py)"]
    
    subgraph CoreEngine["Core Orchestration Layer (agent/)"]
        GATEWAY --> ORCH["orchestrator.py (Pipeline Controller)"]
        ORCH --> DEC["decision_engine.py (10-Tier Deterministic Router)"]
        DEC --> ROUTES["route_registry.py (Route Tokens & Types)"]
        DEC --> EXEC["tool_executor.py (Catalog, Consumables & Specs Tools)"]
        EXEC --> REG["tool_registry.py (Function Call Schemas)"]
        EXEC --> PLAN["evidence_planner.py (3-Valued Fact Aggregator)"]
        PLAN --> COMP["response_composer.py (Grounded LLM Composer)"]
    end
    
    subgraph SubAgents["Specialist Sub-Agents Layer (agents/)"]
        ORCH -.->|"Handoff / Multi-Agent Routing"| HUB["agents/__init__.py (Registry)"]
        HUB --> BASE["base_agent.py (Abstract Interface)"]
        HUB --> RECP["receptionist_agent.py (Concierge & Locations)"]
        HUB --> PROD["product_catalog_agent.py (Hardware & Catalog)"]
        HUB --> RAG["technical_rag_agent.py (Deep Technical RAG)"]
        HUB --> LEAD["sales_lead_agent.py (Lead Capture & CRM)"]
        HUB --> PYD["pydantic_ai_agent.py (PydanticAI Engine)"]
    end
    
    COMP --> RESP["Validated Grounded Reply + Interactive Product Cards"]
    RESP --> USER
```

---
""")

# ========================================================
# SECTION 3: agent/ files
# ========================================================
doc_content.append("## 3. Core Decision & Orchestration Engine (`agent/`)\n\n")

core_files = [
    ("3.1 `agent/route_registry.py`", "route_registry.py", "Defines the route names, route decisions, and enumeration mapping conversation intents to routing targets."),
    ("3.2 `agent/tool_registry.py`", "tool_registry.py", "Provides JSON schemas and parameter definitions for all tools callable by the LLM (search_catalog, get_product_specs, get_compatible_consumables, compare_products, get_business_information)."),
    ("3.3 `agent/tool_executor.py`", "tool_executor.py", "The backend execution engine for catalog tools. Connects to `CatalogRepository`, `RAGRetriever`, and `PriceResolver` to execute grounded tool invocations with strict brand filtering."),
    ("3.4 `agent/decision_engine.py`", "decision_engine.py", "The deterministic 10-tier routing decision engine. Overrides LLM suggestions with strict deterministic business rules (Guardrail -> Social -> Business Info -> Process Help -> Explicit Product -> Comparison -> Consumables -> Discovery -> Qualification -> Clarification)."),
    ("3.5 `agent/evidence_planner.py`", "evidence_planner.py", "Plans and aggregates field-aware, verified database evidence. Enforces 3-valued logic (supported, unsupported, unknown) to prevent speculative responses."),
    ("3.6 `agent/response_composer.py`", "response_composer.py", "Question-aware grounded response composer. Combines verified facts and conversation context, prompts the local LLM, and validates output against deterministic rules with fail-closed fallback."),
    ("3.7 `agent/orchestrator.py`", "orchestrator.py", "The central Conversational Orchestrator. Coordinates multi-turn state, normalizer intercepts, requirement extraction, qualification loops, card generation, and response finalization.")
]

for section_title, fname, desc in core_files:
    fpath = AGENT_DIR / fname
    code = read_file(fpath)
    lines_count = len(code.splitlines())
    bytes_count = len(code.encode("utf-8"))
    
    doc_content.append(f"### {section_title}\n\n")
    doc_content.append(f"**Path**: [`/opt/salesai/agent/{fname}`](file:///opt/salesai/agent/{fname})  \n")
    doc_content.append(f"**Lines**: {lines_count} | **Size**: {bytes_count:,} bytes  \n\n")
    doc_content.append(f"**Purpose & Responsibilities**:\n{desc}\n\n")
    doc_content.append(f"#### Complete Source Code for `agent/{fname}`:\n\n")
    doc_content.append(f"```python\n{code}\n```\n\n---\n\n")

# ========================================================
# SECTION 4: agents/ files
# ========================================================
doc_content.append("## 4. Specialist Sub-Agents Framework (`agents/`)\n\n")

specialist_files = [
    ("4.1 `agents/__init__.py`", "__init__.py", "Package registry that exports `SPECIALIST_AGENTS`, `get_agent_by_id`, and `list_agent_metadata`."),
    ("4.2 `agents/base_agent.py`", "base_agent.py", "Abstract base class `BaseSpecialistAgent` defining agent interface methods: `process_turn()`, `can_handle()`, and `get_info()`."),
    ("4.3 `agents/receptionist_agent.py`", "receptionist_agent.py", "Kepler Concierge receptionist handling company introduction, Dubai showroom location, contact phone/email, and business hours."),
    ("4.4 `agents/product_catalog_agent.py`", "product_catalog_agent.py", "Product & Catalog specialist managing product discovery, paper-size requirements, and model recommendations."),
    ("4.5 `agents/technical_rag_agent.py`", "technical_rag_agent.py", "Technical & Comparison specialist performing technical feature lookups, DPI and resolution analysis, and side-by-side model comparisons."),
    ("4.6 `agents/sales_lead_agent.py`", "sales_lead_agent.py", "Sales & Quotation specialist capturing customer contact details (name, email, phone, company), managing quote requests, and persisting leads to SQLite."),
    ("4.7 `agents/pydantic_ai_agent.py`", "pydantic_ai_agent.py", "Enterprise agent built on PydanticAI. Features automatic Ollama model resolution, tool execution (catalog search, calculator, current time), and structured output validation.")
]

for section_title, fname, desc in specialist_files:
    fpath = AGENTS_DIR / fname
    code = read_file(fpath)
    lines_count = len(code.splitlines())
    bytes_count = len(code.encode("utf-8"))
    
    doc_content.append(f"### {section_title}\n\n")
    doc_content.append(f"**Path**: [`/opt/salesai/agents/{fname}`](file:///opt/salesai/agents/{fname})  \n")
    doc_content.append(f"**Lines**: {lines_count} | **Size**: {bytes_count:,} bytes  \n\n")
    doc_content.append(f"**Purpose & Responsibilities**:\n{desc}\n\n")
    doc_content.append(f"#### Complete Source Code for `agents/{fname}`:\n\n")
    doc_content.append(f"```python\n{code}\n```\n\n---\n\n")

# ========================================================
# SECTION 5: Cross-Agent Communication & Lifecycle
# ========================================================
doc_content.append("""## 5. Cross-Agent Communication & Conversation Lifecycle

1. **State Preservation Across Handoffs**:
   - The central `ConversationState` object preserves customer history, active requirements, and displayed product cards regardless of which specialist or route processes the turn.
   
2. **Deterministic Priority Over Machine Guesswork**:
   - The `DecisionEngine` intercepts sensitive intents (e.g., pricing, discounts, unverified competitor comparisons) before any specialist or LLM can formulate a speculative response.

3. **Grounding & Fail-Closed Guarantee**:
   - If the LLM generates a response containing unverified claims, `ResponseComposer` discards the text and falls back to the deterministic `VerifiedEvidenceBundle` prepared by `EvidencePlanner`.

---

## 6. Summary File Index

| Directory | File | Size | Role |
| :--- | :--- | :--- | :--- |
| `agent/` | [`orchestrator.py`](file:///opt/salesai/agent/orchestrator.py) | 333 KB | Master pipeline controller |
| `agent/` | [`decision_engine.py`](file:///opt/salesai/agent/decision_engine.py) | 25 KB | 10-tier deterministic router |
| `agent/` | [`evidence_planner.py`](file:///opt/salesai/agent/evidence_planner.py) | 35 KB | 3-valued evidence aggregator |
| `agent/` | [`response_composer.py`](file:///opt/salesai/agent/response_composer.py) | 21 KB | Grounded LLM response writer |
| `agent/` | [`tool_executor.py`](file:///opt/salesai/agent/tool_executor.py) | 27 KB | Catalog tool execution engine |
| `agent/` | [`tool_registry.py`](file:///opt/salesai/agent/tool_registry.py) | 6 KB | OpenAI/Ollama function calling schemas |
| `agent/` | [`route_registry.py`](file:///opt/salesai/agent/route_registry.py) | 1 KB | Route definitions and tokens |
| `agents/` | [`__init__.py`](file:///opt/salesai/agents/__init__.py) | 2 KB | Sub-agents registry & export |
| `agents/` | [`base_agent.py`](file:///opt/salesai/agents/base_agent.py) | 1.4 KB | Base specialist interface |
| `agents/` | [`receptionist_agent.py`](file:///opt/salesai/agents/receptionist_agent.py) | 2.6 KB | Concierge, locations, hours |
| `agents/` | [`product_catalog_agent.py`](file:///opt/salesai/agents/product_catalog_agent.py) | 1.9 KB | Hardware discovery & qualification |
| `agents/` | [`technical_rag_agent.py`](file:///opt/salesai/agents/technical_rag_agent.py) | 1.4 KB | Deep specs & comparisons |
| `agents/` | [`sales_lead_agent.py`](file:///opt/salesai/agents/sales_lead_agent.py) | 7.9 KB | Lead capture & quote CRM |
| `agents/` | [`pydantic_ai_agent.py`](file:///opt/salesai/agents/pydantic_ai_agent.py) | 12 KB | PydanticAI execution engine |
""")

final_markdown = "".join(doc_content)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(final_markdown)

print(f"Generated {OUTPUT_FILE} successfully! Size: {len(final_markdown):,} bytes")
