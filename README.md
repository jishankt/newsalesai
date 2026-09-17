# Kepler Tech — SalesAI Conversational Assistant

> **AI-Powered Sales & CRM Bot for Kepler Tech LLC** — Dubai's #1 Printer, Inkjet Media & Consumables Supplier.

---

## Documentation Links
- 📖 **[Developer Guide & Architecture Overview (DEVELOPER.md)](DEVELOPER.md)**: In-depth technical architecture, module breakdown, conversational state machine, SKU resolver, and developer workflows.

---

## Key Features & Capabilities

- **Deterministic-First Conversational Orchestrator**: Single canonical pipeline ([`agent/orchestrator.py`](agent/orchestrator.py)) strictly governing qualification schemas, catalog matching, anti-frustration guards, and model detail queries.
- **Direct Part Number & SKU Resolver**: Instant recognition of genuine Epson consumables (`C13T...`, `C13S...`, `C12C...`) and Citizen photo media (`CX2.4x6`, `CX2.6X8`, `CX2W 812`, `CY-MS46`, etc.) returning verified product cards without unnecessary qualification loops.
- **Dynamic Consumables & Accessories Engine**: Graph-based resolver connecting hardware printers to authorized inks, maintenance boxes, and paper rolls.
- **Approved 43-Hardware Product Catalogue Scope**: Strict filtering across Technical CAD (T-Series), Photo & Fine Art (P-Series), WorkForce Enterprise/Pro Office (AM/WF-Series), Dye-Sublimation (SC-F100/F500), and Citizen Photo (CX/CY/CZ-Series).
- **Zero-Hallucination & Fail-Closed Guardrails**: Attribute-specific validation preventing speculative claims, unapproved models, or invented product links.
- **HMAC-Protected Multi-Turn State**: Thread-safe session state store with 2-hour TTL, LRU eviction, and optional Redis persistence.

---

## Quick Start

### 1. Environment Setup
```bash
# Clone repository and enter directory
cd /opt/salesai

# Activate Python virtual environment
source venv/bin/activate

# Configure environment variables
cp .env.example .env
# Edit .env to configure SECRET_KEY, PORT (default 5050), and OLLAMA_BASE_URL
```

### 2. Running Locally
```bash
python run.py
```
Server starts at **http://localhost:5050** (or configured `PORT`).

### 3. Service Management (Systemd)
The production service runs as a systemd user service:
```bash
# Check service status
systemctl --user status salesai.service

# Restart service after code updates
systemctl --user restart salesai.service

# Stream live service logs
journalctl --user -u salesai.service -f
```

### 4. API — Conversational Endpoint
```bash
# Standard printer inquiry
curl -X POST http://localhost:5050/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I need a 36-inch CAD plotter with scanner.", "session_id": "demo-001"}'

# Direct SKU inquiry
curl -X POST http://localhost:5050/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "i need C13T11C340", "session_id": "demo-002"}'
```

### 5. Health & Readiness Probes
```bash
curl http://localhost:5050/health/live   # {"status": "alive"}
curl http://localhost:5050/health/ready  # {"status": "ready", "catalog_count": 43, "catalogue_ok": true, "persistence_ok": true}
```

---

## Architecture Overview

```
app.py  ──▶  agent/orchestrator.py  ──▶  agent/decision_engine.py
                     │                          │
             nlp/llm_understanding.py    rag/consumables_engine.py
                     │                          ↕
             catalog/catalogue_resolver.py  rag/retriever.py
             conversation/qualification_schema.py
             validation/deterministic_validator.py
                     │
             domain/state_store.py  (Session State & HMAC Security)
```

For complete technical specifications, see [**DEVELOPER.md**](DEVELOPER.md).

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5050` | Flask server listening port |
| `SECRET_KEY` | *(configured in .env)* | HMAC session signing secret |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama LLM server address |
| `DEFAULT_MODEL` | `qwen2.5:32b` | Primary LLM model for natural language understanding |
| `ALLOWED_MODELS` | *(see .env.example)* | Comma-separated model allowlist |
| `CORS_ORIGINS` | `localhost:5050` | Allowed CORS origins |
| `MAX_REQUEST_BYTES` | `65536` | Maximum allowed request body size (64 KB) |
| `REDIS_URL` | *(optional)* | Redis connection string for persistent session state |

---

## Running Test Suites

```bash
# Run complete test suite via pytest
pytest

# Run direct SKU & consumable resolution tests
pytest tests/test_direct_sku_resolution.py -v

# Run comparison engine tests
pytest tests/test_comparison_engine.py -v

# Run adversarial and resilience test suite
pytest tests/test_adversarial_and_resilience.py -v

# Run architectural integrity test suite
pytest tests/test_architecture_single_orchestrator.py -v
```

---

## Contact & Support

**Kepler Tech LLC** — Dubai, UAE
- 📧 sales@keplertech.ae | info@keplertech.ae
- 📞 +971 4 323 1008 | +971 55 835 8586
- 🌐 [www.keplertechllc.com](https://www.keplertechllc.com)
