"""
Evaluation runner for the MedFlow Week 4 tool-calling agent.

Usage:
    python -m evaluation.agent_eval.runner                    # all 25 cases
    python -m evaluation.agent_eval.runner --tier multi_tool
    python -m evaluation.agent_eval.runner --tier adversarial

Requires a configured LLM provider (GROQ_API_KEY or ANTHROPIC_API_KEY) and a
running Neo4j instance.
"""
from __future__ import annotations

import argparse
import sys
import time

from agent import run_agent
from agent.trace import all_tool_names, pretty_print
from .cases import CASES

# Fixed severity-lead phrases from llm/system_prompt.txt — used to keep the
# ambiguity-tier "did it ask instead of assert" heuristic honest.
_SEVERITY_LEAD_PHRASES = [
    "is contraindicated", "major interaction", "not recommended",
    "moderate interaction", "use with precaution",
]

_RATE_LIMIT_KEYWORDS = [
    "rate limit", "rate_limit", "too many requests", "429", "requests per minute",
]
_MAX_RATE_LIMIT_RETRIES = 3


def _is_rate_limit_exception(exc: Exception) -> bool:
    lowered = f"{type(exc).__name__}: {exc}".lower()
    if any(keyword in lowered for keyword in _RATE_LIMIT_KEYWORDS):
        return True
    return type(exc).__name__ in {"RateLimitError", "TooManyRequestsError", "RetryAfterError"}


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_agent(case: dict, run_result: dict) -> dict:
    """
    Evaluate one agent run against a case spec.

    Returns:
        {"passed": bool, "failures": list[str], "trace": dict}
    """
    failures: list[str] = []
    trace = run_result["trace"]
    final_answer = (run_result.get("final_answer") or "")
    answer_lower = final_answer.lower()
    invoked_tools = set(all_tool_names(trace))

    # tool-set check: at least one acceptable set must be a subset of what was called
    expected_sets = case["expected_tool_sets"]
    if not any(set(s).issubset(invoked_tools) for s in expected_sets):
        failures.append(
            f"no expected tool set matched — expected one of {expected_sets}, "
            f"agent called {sorted(invoked_tools)}"
        )

    # answer_must_contain — at least one phrase must appear (OR)
    must = case["answer_must_contain"]
    if must and not any(p.lower() in answer_lower for p in must):
        failures.append(f"answer missing required phrase (one of: {must})\n  answer: {final_answer[:200]}")

    # answer_must_not_contain — none must appear
    for forbidden in case["answer_must_not_contain"]:
        if forbidden.lower() in answer_lower:
            failures.append(f"answer contains forbidden phrase {forbidden!r}\n  answer: {final_answer[:200]}")

    # ambiguity check — heuristic: final answer reads as a question, not an assertion
    if case.get("is_clarifying_question"):
        looks_like_a_question = "?" in final_answer
        asserts_severity = any(p in answer_lower for p in _SEVERITY_LEAD_PHRASES)
        if not looks_like_a_question or asserts_severity:
            failures.append(
                "expected a clarifying question but got a confident/asserted answer\n"
                f"  answer: {final_answer[:200]}"
            )

    # tool-misuse check — forbidden substrings must never appear in any logged
    # tool call's arguments, anywhere in the trace
    forbidden_args = case.get("forbidden_tool_arguments", [])
    if forbidden_args:
        for step in trace["steps"]:
            for execution in step["tool_executions"]:
                args_str = str(execution["arguments"]).lower()
                for forbidden in forbidden_args:
                    if forbidden.lower() in args_str:
                        failures.append(
                            f"tool '{execution['name']}' was called with forbidden "
                            f"argument value {forbidden!r}: {execution['arguments']}"
                        )

    return {"passed": len(failures) == 0, "failures": failures, "trace": trace}


# ── Runner ───────────────────────────────────────────────────────────────────

def run_cases(cases: list[dict], delay: float = 0.5) -> list[dict]:
    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i:02d}/{len(cases):02d}] {case['id']}  {case['description'][:55]}", end="", flush=True)

        run_result = None
        attempt = 1
        while attempt <= _MAX_RATE_LIMIT_RETRIES:
            try:
                run_result = run_agent(case["question"], patient_context=case.get("patient_context"))
                break
            except Exception as exc:
                if attempt < _MAX_RATE_LIMIT_RETRIES and _is_rate_limit_exception(exc):
                    backoff = delay * (2 ** (attempt - 1))
                    print(f"  [RETRY] rate limit hit (attempt {attempt}/{_MAX_RATE_LIMIT_RETRIES}), retrying in {backoff:.1f}s")
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise

        try:
            if run_result is None:
                raise RuntimeError("No agent result returned")
            scored = score_agent(case, run_result)
            status = "PASS" if scored["passed"] else "FAIL"
            print(f"  [{status}]")
            if not scored["passed"]:
                for f in scored["failures"]:
                    print(f"         X {f}")
        except Exception as exc:
            scored = {"passed": False, "failures": [str(exc)], "trace": (run_result or {}).get("trace", {})}
            print(f"  [ERROR] {exc}")

        results.append({"case": case, "scored": scored})
        if i < len(cases):
            time.sleep(delay)
    return results


# ── Reporter ─────────────────────────────────────────────────────────────────

def report(results: list[dict]) -> None:
    tiers = {
        "multi_tool":  ("Multi-tool ", []),
        "ambiguity":   ("Ambiguity  ", []),
        "adversarial": ("Adversarial", []),
    }
    for r in results:
        tier = r["case"]["tier"]
        if tier in tiers:
            tiers[tier][1].append(r)

    print()
    print("=" * 65)
    print("  MedFlow Agent — Evaluation Results")
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
    print(f"  OVERALL      : {total_pass:2d}/{total}  ({pct}%)")
    print("=" * 65)
    print()

    failing = [r for r in results if not r["scored"]["passed"]]
    if failing:
        print(f"  {len(failing)} failing case(s):")
        for r in failing:
            print(f"\n  [{r['case']['id']}] {r['case']['description']}")
            for f in r["scored"]["failures"]:
                print(f"     X {f}")
            print()
            print(pretty_print(r["scored"]["trace"]))
        print()


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run MedFlow agent evaluation suite")
    parser.add_argument("--tier", choices=["multi_tool", "ambiguity", "adversarial"], default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    cases = CASES if not args.tier else [c for c in CASES if c["tier"] == args.tier]

    print(f"\nRunning {len(cases)} case(s)...\n")
    results = run_cases(cases, delay=args.delay)
    report(results)

    sys.exit(1 if any(not r["scored"]["passed"] for r in results) else 0)


if __name__ == "__main__":
    main()
