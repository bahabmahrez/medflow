"""
Evaluation runner for the MedFlow GraphRAG pipeline.

Usage:
    python -m evaluation.llm_eval.runner              # all 30 cases
    python -m evaluation.llm_eval.runner --tier T1    # factual only
    python -m evaluation.llm_eval.runner --tier T3    # adversarial only

Requires ANTHROPIC_API_KEY and a running Neo4j instance.
"""
from __future__ import annotations

import argparse
import sys
import time

from graphrag import ask
from .cases import CASES


# ── Scoring ────────────────────────────────────────────────────────────────────

def score(case: dict, result: dict) -> dict:
    """
    Evaluate a pipeline result against a case spec.

    Returns:
        {
            "passed":   bool,
            "failures": list[str],   — human-readable failure reasons
            "result":   dict,        — raw pipeline output
        }
    """
    failures: list[str] = []
    answer_lower = result.get("answer", "").lower()
    detected    = result.get("drugs_detected", [])
    risk        = result.get("risk_level")

    # drugs_detected
    for drug in case["expected_drugs"]:
        if drug not in detected:
            failures.append(f"drug '{drug}' not detected (got {detected})")

    # risk_level (only checked when spec sets it explicitly)
    if case["expected_risk"] is not None:
        if risk != case["expected_risk"]:
            failures.append(
                f"risk_level={risk!r} expected {case['expected_risk']!r}"
            )

    # answer_must_contain  — at least one phrase must appear (OR)
    must = case["answer_must_contain"]
    if must and not any(p.lower() in answer_lower for p in must):
        failures.append(
            f"answer missing required phrase (one of: {must})\n"
            f"  answer: {result.get('answer', '')[:200]}"
        )

    # answer_must_not_contain — none must appear
    for forbidden in case["answer_must_not_contain"]:
        if forbidden.lower() in answer_lower:
            failures.append(
                f"answer contains forbidden phrase {forbidden!r}\n"
                f"  answer: {result.get('answer', '')[:200]}"
            )

    return {
        "passed":   len(failures) == 0,
        "failures": failures,
        "result":   result,
    }


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_cases(cases: list[dict], delay: float = 0.5) -> list[dict]:
    """
    Execute each case through the pipeline and score it.

    Args:
        cases: list of case dicts from cases.py
        delay: seconds to wait between calls (avoid API rate limits)

    Returns:
        list of {case, scored} dicts
    """
    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i:02d}/{len(cases):02d}] {case['id']}  {case['description'][:55]}", end="", flush=True)
        try:
            pipeline_result = ask(case["question"], **case["ask_kwargs"])
            scored = score(case, pipeline_result)
            status = "PASS" if scored["passed"] else "FAIL"
            print(f"  [{status}]")
            if not scored["passed"]:
                for f in scored["failures"]:
                    print(f"         ✗ {f}")
        except Exception as exc:
            scored = {"passed": False, "failures": [str(exc)], "result": {}}
            print(f"  [ERROR] {exc}")
        results.append({"case": case, "scored": scored})
        if i < len(cases):
            time.sleep(delay)
    return results


# ── Reporter ───────────────────────────────────────────────────────────────────

def report(results: list[dict]) -> None:
    tiers = {
        "factual":     ("Tier 1 — Factual    ", []),
        "multihop":    ("Tier 2 — Multi-hop  ", []),
        "adversarial": ("Tier 3 — Adversarial", []),
    }
    for r in results:
        tier = r["case"]["tier"]
        if tier in tiers:
            tiers[tier][1].append(r)

    print()
    print("=" * 65)
    print("  MedFlow GraphRAG — Evaluation Results")
    print("=" * 65)

    total_pass = total = 0
    for tier_key, (label, tier_results) in tiers.items():
        if not tier_results:
            continue
        passed = sum(1 for r in tier_results if r["scored"]["passed"])
        n = len(tier_results)
        pct = int(passed / n * 100)
        print(f"  {label} : {passed:2d}/{n}  ({pct}%)")
        total_pass += passed
        total += n

    print("-" * 65)
    pct = int(total_pass / total * 100) if total else 0
    print(f"  OVERALL                  : {total_pass:2d}/{total}  ({pct}%)")
    print("=" * 65)
    print()

    # Detail failing cases
    failing = [r for r in results if not r["scored"]["passed"]]
    if failing:
        print(f"  {len(failing)} failing case(s):")
        for r in failing:
            print(f"\n  [{r['case']['id']}] {r['case']['description']}")
            for f in r["scored"]["failures"]:
                print(f"     ✗ {f}")
        print()


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run MedFlow GraphRAG evaluation suite")
    parser.add_argument(
        "--tier",
        choices=["T1", "T2", "T3"],
        default=None,
        help="Run only one tier (T1=factual, T2=multihop, T3=adversarial)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between API calls (default 0.5)",
    )
    args = parser.parse_args()

    tier_map = {"T1": "factual", "T2": "multihop", "T3": "adversarial"}
    cases = CASES
    if args.tier:
        target = tier_map[args.tier]
        cases = [c for c in CASES if c["tier"] == target]

    print(f"\nRunning {len(cases)} case(s)…\n")
    results = run_cases(cases, delay=args.delay)
    report(results)

    any_failed = any(not r["scored"]["passed"] for r in results)
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
