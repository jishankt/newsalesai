import sys
import os
import json
import time
import argparse
from typing import Dict, Any, List
from collections import defaultdict

# Ensure repo root is on sys.path
sys.path.insert(0, '/opt/salesai')

from conversation.understanding import understand_turn
from conversation.dialogue_state import DialogueState, ReferentResolver

DATASET_PATH = "/opt/salesai/tests/nlu_audit/dataset.jsonl"
FIELD_KEYS = [
    "intent",
    "dialogue_act",
    "target_category",
    "target_model",
    "media_size",
    "target_attribute",
    "budget_ceiling",
    "quote_quantity",
    "primary_concern",
    "buyer_pace",
]


def load_dataset(path: str = DATASET_PATH, split: str = "all") -> List[Dict[str, Any]]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if split == "all" or item.get("split") == split:
                    cases.append(item)
    return cases


def evaluate_dataset(
    cases: List[Dict[str, Any]],
    allow_llm: bool = False,
    model: str = None
) -> Dict[str, Any]:
    results = []
    latencies = []
    crashes = []
    category_confusion = defaultdict(lambda: defaultdict(int))

    for case in cases:
        case_id = case["id"]
        text = case["text"]
        group = case["group"]
        expected = case["expected"]
        notes = case.get("notes", "")
        prior_context = case.get("prior_context", [])

        # Build simulated dialogue state from prior context
        state = DialogueState(session_id=f"audit_{case_id}")
        if prior_context:
            for p_msg in prior_context:
                try:
                    p_text = p_msg if isinstance(p_msg, str) else p_msg.get("content", "")
                    p_und = understand_turn(p_text, allow_llm=False)
                    p_res = ReferentResolver.resolve_turn(p_und, state)
                    from conversation.policy import PolicyEngine
                    p_dec = PolicyEngine.decide(p_res, state)
                except Exception as e:
                    pass

        # Execute turn
        t0 = time.time()
        exc_str = None
        und = None
        resolved = None

        try:
            und = understand_turn(text, allow_llm=allow_llm, model=model)
            resolved = ReferentResolver.resolve_turn(und, state)
        except Exception as e:
            exc_str = f"{type(e).__name__}: {str(e)}"
            crashes.append({"id": case_id, "text": text, "error": exc_str})

        elapsed_ms = (time.time() - t0) * 1000.0
        latencies.append(elapsed_ms)

        pred = {}
        confidence = 0.0
        used_llm = False

        if und:
            confidence = getattr(und, "overall_confidence", 0.0)
            used_llm = getattr(und, "used_llm", False)
            pred["intent"] = und.intent.value if und.intent else None
            pred["dialogue_act"] = und.dialogue_act.value if und.dialogue_act else None
            
            # Category resolution
            res_cat = getattr(state, "category", None) or (und.slots.get("target_category").value if und.slots.get("target_category") else None)
            pred["target_category"] = res_cat

            # Model resolution
            res_model = resolved.resolved_target_product.id if (resolved and resolved.resolved_target_product) else None
            slot_model = und.slots.get("target_model").value if und.slots.get("target_model") else None
            pred["target_model"] = res_model or slot_model

            pred["media_size"] = und.slots.get("media_size").value if und.slots.get("media_size") else None
            pred["target_attribute"] = und.slots.get("target_attribute").value if und.slots.get("target_attribute") else None
            pred["budget_ceiling"] = und.slots.get("budget_ceiling").value if und.slots.get("budget_ceiling") else None
            pred["quote_quantity"] = und.slots.get("quote_quantity").value if und.slots.get("quote_quantity") else None
            pred["primary_concern"] = und.slots.get("primary_concern").value if und.slots.get("primary_concern") else None
            pred["buyer_pace"] = und.buyer_pace if hasattr(und, "buyer_pace") else None
            pred["secondary_intents"] = [si.value for si in und.secondary_intents] if und.secondary_intents else []
        else:
            for k in FIELD_KEYS:
                pred[k] = None
            pred["secondary_intents"] = []

        # Evaluate matches
        field_eval = {}
        all_labelled_correct = True
        has_any_labelled_field = False

        for k in FIELD_KEYS:
            exp_val = expected.get(k)
            pred_val = pred.get(k)
            if exp_val is not None:
                has_any_labelled_field = True
                is_match = False
                if k == "intent":
                    # Step 0a: Score correct if primary matches OR secondary list covers expected compound set
                    exp_primary = exp_val
                    exp_secondary = set(expected.get("secondary_intents") or [])
                    pred_primary = pred_val
                    pred_secondary = set(pred.get("secondary_intents") or [])

                    if exp_primary == pred_primary:
                        is_match = True
                    elif exp_secondary and pred_primary in exp_secondary:
                        if exp_primary in pred_secondary or exp_secondary.issubset(pred_secondary | {pred_primary}):
                            is_match = True
                    elif exp_secondary and exp_secondary.issubset(pred_secondary):
                        is_match = True
                    elif exp_primary in pred_secondary and exp_secondary.issubset(pred_secondary | {pred_primary}):
                        is_match = True
                elif isinstance(exp_val, (int, float)) and isinstance(pred_val, (int, float)):
                    is_match = abs(float(exp_val) - float(pred_val)) < 1e-4
                elif isinstance(exp_val, str) and isinstance(pred_val, str):
                    is_match = (exp_val.strip().lower() == pred_val.strip().lower())
                else:
                    is_match = (exp_val == pred_val)

                field_eval[k] = is_match
                if not is_match:
                    all_labelled_correct = False
            else:
                field_eval[k] = None

        # Category confusion matrix
        if expected.get("target_category") is not None:
            exp_cat = expected.get("target_category")
            actual_cat = pred.get("target_category") or "none"
            category_confusion[exp_cat][actual_cat] += 1

        is_confident = (confidence >= 0.75)
        is_confident_but_wrong = (is_confident and not all_labelled_correct and has_any_labelled_field)

        results.append({
            "id": case_id,
            "text": text,
            "group": group,
            "split": case.get("split", "dev"),
            "notes": notes,
            "expected": expected,
            "predicted": pred,
            "field_eval": field_eval,
            "confidence": confidence,
            "used_llm": used_llm,
            "latency_ms": elapsed_ms,
            "all_labelled_correct": all_labelled_correct,
            "is_confident": is_confident,
            "is_confident_but_wrong": is_confident_but_wrong,
            "error": exc_str,
        })

    # Summary statistics
    total_turns = len(results)
    field_stats = {}
    for k in FIELD_KEYS:
        evals = [r["field_eval"][k] for r in results if r["field_eval"][k] is not None]
        # Step 0b: Stop counting buyer_pace="standard" default as false positive
        if k == "buyer_pace":
            fps = [
                1 for r in results
                if r["expected"].get(k) is None and r["predicted"].get(k) not in (None, "standard")
            ]
        else:
            fps = [
                1 for r in results
                if r["expected"].get(k) is None and r["predicted"].get(k) is not None
            ]
        total_tested = len(evals)
        correct = sum(1 for e in evals if e is True)
        acc = (correct / total_tested * 100.0) if total_tested > 0 else 100.0
        field_stats[k] = {
            "tested": total_tested,
            "correct": correct,
            "accuracy": round(acc, 2),
            "false_positives": len(fps),
        }

    # Per-group statistics
    groups = sorted(list(set(r["group"] for r in results)))
    group_stats = {}
    for g in groups:
        g_results = [r for r in results if r["group"] == g]
        group_stats[g] = {}
        for k in FIELD_KEYS:
            evals = [r["field_eval"][k] for r in g_results if r["field_eval"][k] is not None]
            tested = len(evals)
            corr = sum(1 for e in evals if e is True)
            acc = (corr / tested * 100.0) if tested > 0 else 100.0
            group_stats[g][k] = {
                "tested": tested,
                "correct": corr,
                "accuracy": round(acc, 2),
            }

    # Confident-but-wrong list
    cbw_cases = [r for r in results if r["is_confident_but_wrong"]]
    cbw_cases.sort(key=lambda x: x["confidence"], reverse=True)

    # Calibration table
    buckets = [
        ("0.0 - 0.50", 0.0, 0.50),
        ("0.50 - 0.75", 0.50, 0.75),
        ("0.75 - 0.90", 0.75, 0.90),
        ("0.90 - 1.00", 0.90, 1.01),
    ]
    calibration = []
    for label, b_min, b_max in buckets:
        b_res = [r for r in results if b_min <= r["confidence"] < b_max]
        b_count = len(b_res)
        b_correct = sum(1 for r in b_res if r["all_labelled_correct"])
        b_acc = (b_correct / b_count * 100.0) if b_count > 0 else 0.0
        calibration.append({
            "bucket": label,
            "count": b_count,
            "correct": b_correct,
            "real_accuracy": round(b_acc, 2),
        })

    # Latencies
    latencies.sort()
    p50 = round(latencies[int(len(latencies) * 0.50)], 2) if latencies else 0.0
    p95 = round(latencies[int(len(latencies) * 0.95)], 2) if latencies else 0.0
    p99 = round(latencies[int(len(latencies) * 0.99)], 2) if latencies else 0.0

    llm_fallbacks = sum(1 for r in results if r["used_llm"])
    fallback_rate = round(llm_fallbacks / total_turns * 100.0, 2) if total_turns > 0 else 0.0

    return {
        "allow_llm": allow_llm,
        "model": model,
        "total_turns": total_turns,
        "crashes": crashes,
        "field_stats": field_stats,
        "group_stats": group_stats,
        "confident_but_wrong_count": len(cbw_cases),
        "confident_but_wrong_rate": round(len(cbw_cases) / total_turns * 100.0, 2) if total_turns > 0 else 0.0,
        "confident_but_wrong_cases": cbw_cases,
        "category_confusion": {k: dict(v) for k, v in category_confusion.items()},
        "latency_percentiles_ms": {"p50": p50, "p95": p95, "p99": p99},
        "llm_fallback_count": llm_fallbacks,
        "llm_fallback_rate": fallback_rate,
        "calibration": calibration,
    }


def print_report(metrics: Dict[str, Any], title: str = "NLU EVALUATION REPORT"):
    print("\n" + "=" * 80)
    print(f" {title} (Total turns: {metrics['total_turns']})")
    print("=" * 80)
    print(f"Crashes / Exceptions: {len(metrics['crashes'])}")
    print(f"Actual LLM Fallback Rate: {metrics['llm_fallback_rate']}% ({metrics['llm_fallback_count']}/{metrics['total_turns']} turns)")
    lat = metrics['latency_percentiles_ms']
    print(f"Deterministic Latency: p50={lat['p50']}ms, p95={lat['p95']}ms, p99={lat['p99']}ms")
    print(f"Confident-but-wrong cases (conf >= 0.75): {metrics['confident_but_wrong_count']} ({metrics['confident_but_wrong_rate']}%)")
    print("-" * 80)

    print("\n[PER-FIELD ACCURACY & FALSE POSITIVES]")
    print(f"{'Field':20} | {'Tested':8} | {'Correct':8} | {'Accuracy':10} | {'False Positives':15}")
    print("-" * 72)
    for field, stats in metrics["field_stats"].items():
        print(f"{field:20} | {stats['tested']:<8} | {stats['correct']:<8} | {stats['accuracy']:<8} % | {stats['false_positives']:<15}")

    print("\n[CONFIDENCE CALIBRATION TABLE]")
    print(f"{'Confidence Bucket':20} | {'Count':8} | {'All-Correct':12} | {'Real Accuracy':15}")
    print("-" * 60)
    for row in metrics["calibration"]:
        print(f"{row['bucket']:20} | {row['count']:<8} | {row['correct']:<12} | {row['real_accuracy']:<12} %")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["all", "dev", "holdout"], default="all")
    parser.add_argument("--allow-llm", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--save-baseline", type=str, default=None)
    args = parser.parse_args()

    cases = load_dataset(split=args.split)
    print(f"Loaded {len(cases)} cases (split={args.split}).")

    if args.save_baseline:
        # Run baseline on dev and holdout separately
        print("Running baseline on DEV...")
        dev_cases = load_dataset(split="dev")
        dev_det = evaluate_dataset(dev_cases, allow_llm=False)
        print_report(dev_det, "BASELINE: DEV (Deterministic)")

        print("Running baseline on HOLDOUT...")
        ho_cases = load_dataset(split="holdout")
        ho_det = evaluate_dataset(ho_cases, allow_llm=False)
        print_report(ho_det, "BASELINE: HOLDOUT (Deterministic)")

        baseline_data = {
            "dev": dev_det,
            "holdout": ho_det,
            "all_det": evaluate_dataset(cases, allow_llm=False),
        }

        # Try Ollama pass with qwen2.5:32b
        prod_model = "qwen2.5:32b"
        try:
            print(f"Running baseline on DEV with Ollama {prod_model}...")
            dev_llm = evaluate_dataset(dev_cases, allow_llm=True, model=prod_model)
            baseline_data["dev_llm_32b"] = dev_llm
            print_report(dev_llm, f"BASELINE: DEV (Ollama {prod_model})")
        except Exception as e:
            print(f"Ollama {prod_model} failed: {e}")
            baseline_data["dev_llm_32b"] = "NOT VERIFIED"

        with open(args.save_baseline, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, indent=2)
        print(f"Saved baseline to {args.save_baseline}")
        return

    # Normal single run
    metrics = evaluate_dataset(cases, allow_llm=args.allow_llm, model=args.model)
    title = f"NLU EVALUATION (split={args.split}, allow_llm={args.allow_llm})"
    print_report(metrics, title)


if __name__ == "__main__":
    main()
