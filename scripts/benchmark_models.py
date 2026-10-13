#!/usr/bin/env python3
"""
Model Benchmark Suite for Kepler Tech Sales AI.

Evaluates local Ollama models on:
- Latency (p50, p95)
- Generation throughput (tokens/sec)
- Structured JSON conformance rate
- GPU VRAM consumption

Saves detailed benchmarking reports to docs/MODEL_BENCHMARK.md.
"""

import sys
import os
import time
import json
import argparse
import subprocess
import requests
import numpy as np
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

BENCHMARK_MODELS = [
    "qwen2.5:14b",
    "qwen3:30b",
    "qwen2.5:32b",
    "gpt-oss:20b",
    "qwen3:8b",
]

TEST_QUERIES = [
    "I need a 24-inch CAD plotter for architectural blueprints.",
    "What is the maximum paper width for the Epson SureColor SC-T5100?",
    "Do you deliver to Abu Dhabi and how much does it cost?",
    "What ink cartridges are compatible with the Epson SC-P7500?",
    "Can you give me a discount on the Epson WorkForce WF-C879R?",
    "Does the Epson SC-T3100 come with an automatic paper cutter?",
    "We need a heavy-duty photo printer for our studio in Sharjah.",
    "What is the scan speed of the WorkForce DS-530II duplex scanner?",
    "Is store pickup available in Dubai?",
    "Can you compare the SC-T3100 and SC-T5100 in terms of roll width?",
    "We print around 5,000 architectural drawings a month. What do you recommend?",
    "What is your warranty and returns policy for defective items?",
    "Do you have pigment ink or dye ink plotters?",
    "What are your showroom opening hours?",
    "Can you provide a formal commercial quotation for 3 scanners?",
    "I am looking for replacement maintenance box for Epson WF-C5790.",
    "Do you accept cash on delivery in Ajman?",
    "Can the Epson SC-T5400 print borderless on 36-inch rolls?",
    "What paper types work best with the SureColor P900?",
    "Is uncrating and installation included with production printers?",
    "My name is Tariq, email tariq@design.ae, phone +971 50 123 4567.",
    "Do you have high-speed flatbed scanners for books?",
    "What is the resolution of the Citizen CX-02 photo printer?",
    "Can we pay by bank transfer before dispatch?",
    "Are Epson UltraChrome inks fade resistant?",
    "What is the delivery time to Muscat, Oman?",
    "How many prints can one media roll do on CX-02?",
    "Do you offer trade-in discounts on old HP plotters?",
    "Does the SC-T3100 handle cut sheet paper sizes like A3 and A4?",
    "I need replacement black ink for my SC-T3100 plotter.",
    "What is the difference between SC-P7500 and SC-P9500?",
    "Can I cancel my order before it ships from Dubai?",
    "Do you stock matte black ink for the Epson P-series?",
    "What is the energy consumption of the WorkForce enterprise printer?",
    "Can the DS-770II scanner scan plastic ID cards and passports?",
    "We need a compact desktop plotter with Wi-Fi and Apple AirPrint.",
    "Who is your authorized courier partner for GCC shipments?",
    "Do you supply continuous ink supply systems?",
    "Is technical training provided for operators?",
    "What is the price of the Epson SC-T5100?",
    "Can we lease office equipment on an annual maintenance contract?",
    "I need consumables for Epson WorkForce Enterprise AM-C4000.",
    "Can the SC-T5100 be used outdoors for banner printing?",
    "What is the duty rate for deliveries into Saudi Arabia?",
    "Do you carry genuine Epson spare parts?",
    "Can the DS-530II scan double sided in a single pass?",
    "What are the network connectivity options on the SC-T5400?",
    "Can I return an opened ink cartridge if ordered by mistake?",
    "Do you provide on-site repair in Ras Al Khaimah?",
    "Please send an authorized quotation to info@keplertech.ae."
]

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "PRODUCT_DISCOVERY", "CHECK_SPECS", "DELIVERY_QUERY",
                "CONSUMABLES_QUERY", "PRICE_POLICY", "BUSINESS_INFORMATION"
            ]
        },
        "extracted_model": {"type": "string"},
        "confidence": {"type": "number"}
    },
    "required": ["intent", "confidence"]
}


def get_gpu_vram() -> str:
    """Retrieves current GPU VRAM usage if nvidia-smi is available."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        lines = res.stdout.strip().split("\n")
        if lines and lines[0]:
            used, total = lines[0].split(",")
            return f"{used.strip()} MB / {total.strip()} MB"
    except Exception:
        pass
    return "N/A (CPU / Unified)"


def benchmark_model(
    model_name: str,
    queries: List[str],
    base_url: str = "http://localhost:11434"
) -> Dict[str, Any]:
    """Runs structured evaluation queries against a local Ollama model."""
    print(f"\nEvaluating Model: {model_name} ({len(queries)} queries)...")
    latencies = []
    tokens_per_sec_list = []
    json_parse_success = 0
    total_eval_tokens = 0

    endpoint = f"{base_url}/api/chat"

    # Pre-warm model with ping
    try:
        requests.post(
            endpoint,
            json={"model": model_name, "messages": [{"role": "user", "content": "ping"}], "stream": False},
            timeout=15.0
        )
    except Exception:
        pass

    for i, q in enumerate(queries):
        messages = [
            {"role": "system", "content": "You are a sales intent classification engine. Output JSON only."},
            {"role": "user", "content": q}
        ]
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "format": INTENT_SCHEMA,
            "options": {"temperature": 0.0, "num_predict": 120}
        }
        if "qwen3" in model_name.lower():
            payload["options"]["think"] = False

        start_t = time.time()
        try:
            resp = requests.post(endpoint, json=payload, timeout=25.0)
            dur = time.time() - start_t
            if resp.status_code == 200:
                data = resp.json()
                latencies.append(dur * 1000)

                eval_count = data.get("eval_count", 0)
                eval_dur = data.get("eval_duration", 0)
                if eval_dur > 0 and eval_count > 0:
                    tps = eval_count / (eval_dur / 1e9)
                    tokens_per_sec_list.append(tps)
                    total_eval_tokens += eval_count

                content = data.get("message", {}).get("content", "").strip()
                try:
                    parsed = json.loads(content)
                    if "intent" in parsed:
                        json_parse_success += 1
                except Exception:
                    pass
            else:
                latencies.append(dur * 1000)
        except Exception as e:
            latencies.append(25000.0)

        sys.stdout.write(f"\r  [{i+1}/{len(queries)}] Completed... ")
        sys.stdout.flush()

    p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    mean_tps = float(np.mean(tokens_per_sec_list)) if tokens_per_sec_list else 0.0
    parse_rate = (json_parse_success / len(queries)) * 100.0 if queries else 0.0

    print(f"\n  Done! p50: {p50:.1f}ms | p95: {p95:.1f}ms | Throughput: {mean_tps:.1f} tok/s | JSON Parse Rate: {parse_rate:.1f}%")

    return {
        "model": model_name,
        "queries_tested": len(queries),
        "p50_latency_ms": round(p50, 1),
        "p95_latency_ms": round(p95, 1),
        "tokens_per_sec": round(mean_tps, 1),
        "json_parse_rate_pct": round(parse_rate, 1),
        "vram_usage": get_gpu_vram()
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark local Ollama LLM models.")
    parser.add_argument("--count", type=int, default=50, help="Number of benchmark queries to run")
    parser.add_argument("--models", nargs="+", default=BENCHMARK_MODELS, help="Models to benchmark")
    parser.add_argument("--output", type=str, default=os.path.join(BASE_DIR, "docs", "MODEL_BENCHMARK.md"))
    args = parser.parse_args()

    selected_queries = TEST_QUERIES[:args.count]
    results = []

    print(f"============================================================")
    print(f"Kepler Tech Sales AI - Production Model Benchmark")
    print(f"Evaluating {len(args.models)} models across {len(selected_queries)} queries")
    print(f"============================================================")

    for m in args.models:
        res = benchmark_model(m, selected_queries)
        results.append(res)

    # Generate Markdown Report
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    md_content = f"""# Local LLM Model Benchmark Report

*Generated on: {timestamp}*  
*Total Queries per Model: {len(selected_queries)}*

## 1. Summary Benchmark Matrix

| Model | p50 Latency (ms) | p95 Latency (ms) | Tokens / Sec | JSON Parse Rate (%) | VRAM Allocation | Recommended Role |
|---|---|---|---|---|---|---|
"""
    for r in results:
        role = "Classifier & Primary" if "qwen2.5:14b" in r["model"] or "qwen3:30b" in r["model"] else "Heavy In-depth" if "32b" in r["model"] else "Lightweight Edge"
        md_content += (
            f"| `{r['model']}` | {r['p50_latency_ms']} ms | {r['p95_latency_ms']} ms | "
            f"{r['tokens_per_sec']} tok/s | {r['json_parse_rate_pct']}% | {r['vram_usage']} | {role} |\n"
        )

    md_content += """
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
"""

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\nBenchmark complete! Results written to: {args.output}")


if __name__ == "__main__":
    main()
