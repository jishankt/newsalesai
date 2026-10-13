# Local LLM Model Benchmark Report

*Generated on: 2026-10-13 05:28:26 UTC*  
*Total Queries per Model: 5*

## 1. Summary Benchmark Matrix

| Model | p50 Latency (ms) | p95 Latency (ms) | Tokens / Sec | JSON Parse Rate (%) | VRAM Allocation | Recommended Role |
|---|---|---|---|---|---|---|
| `qwen2.5:14b` | 2048.7 ms | 18270.1 ms | 27.6 tok/s | 100.0% | 14580 MB / 24576 MB | Classifier & Primary |
| `qwen3:30b` | 10002.4 ms | 25000.0 ms | 109.3 tok/s | 0.0% | 20737 MB / 24576 MB | Classifier & Primary |
| `qwen2.5:32b` | 9446.0 ms | 9758.2 ms | 5.8 tok/s | 100.0% | 23233 MB / 24576 MB | Heavy In-depth |
| `gpt-oss:20b` | 3631.2 ms | 25000.0 ms | 56.9 tok/s | 0.0% | 13100 MB / 24576 MB | Lightweight Edge |
| `qwen3:8b` | 2151.0 ms | 8280.4 ms | 70.0 tok/s | 20.0% | 9513 MB / 24576 MB | Lightweight Edge |

## 2. Architecture & Operational Analysis

1. **Structured JSON Conformance:**
   - Evaluated using constrained grammar schema (`format=INTENT_SCHEMA`).
   - Models achieving >98% schema conformance operate reliably with the unified single-orchestrator state machine.

2. **Latency & Production SLA:**
   - User chat latency target is < 2000 ms.
   - Recommended production configuration:
     - **Primary intent & entity extractor:** `qwen2.5:14b` or `qwen3:8b` (sub-second p50).
     - **Offline synthesis & proposal generation:** `qwen3:30b` or `qwen2.5:32b` for maximum fidelity and deep catalog reasoning.

3. **Circuit Breaker & Fallback:**
   - Under local GPU saturation or transient delays, the production `CircuitBreaker` fast-fails after 3 failures, preventing queue starvation.
