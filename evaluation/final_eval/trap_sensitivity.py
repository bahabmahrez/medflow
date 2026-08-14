"""
Milestone 4 - interaction detection SENSITIVITY.

Every trap patient carries a known, dangerous prescribing scenario. The system
must never miss one: a false negative here is a patient harmed. This harness
loads each trap patient's real record, scans the prescription that triggers the
trap, and asserts the dangerous finding was raised at the right severity.

Sensitivity is the metric that must be 100%. Specificity (not crying wolf) is
measured separately in specificity.py - the two trade against each other, so
they are reported separately rather than averaged into one flattering number.

Usage:
    python -m evaluation.final_eval.trap_sensitivity
    python -m evaluation.final_eval.trap_sensitivity --verbose

Requires Neo4j + PostgreSQL running (docker compose up -d).
Exits non-zero if any trap is missed.
"""
from __future__ import annotations

import argparse
import sys

from engine import scan_prescription
from interface.patient_data import list_patients, load_patient, to_scan_kwargs

#: What each trap patient is a trap *for*.
#:
#: ``prescription``  - the new script that triggers the danger
#: ``expect_types``  - alert types that must appear
#: ``min_severity``  - the finding must be at least this severe
#: ``expect_drugs``  - INNs that must be named by the triggering alert
TRAPS: dict[str, dict] = {
    "warfarin_aspirin": {
        "prescription": [{"drug": "aspirin", "dose": "100mg"}],
        "expect_types": {"interaction"},
        "min_severity": "major",
        "expect_drugs": {"warfarin", "aspirin"},
        "danger": "Additive bleeding risk on an anticoagulated patient.",
    },
    "metformin_ckd": {
        "prescription": [{"drug": "metformin", "dose": "1000mg"}],
        "expect_types": {"contraindication"},
        "min_severity": "contraindicated",
        "expect_drugs": {"metformin"},
        "danger": "Metformin in severe renal impairment - lactic acidosis.",
    },
    "simvastatin_clarity": {
        "prescription": [{"drug": "clarithromycin", "dose": "500mg"}],
        "expect_types": {"interaction", "cyp_competition"},
        "min_severity": "major",
        "expect_drugs": {"simvastatin", "clarithromycin"},
        "danger": "CYP3A4 inhibition raises simvastatin - rhabdomyolysis.",
    },
    "penicillin_allergy": {
        "prescription": [{"drug": "amoxicillin", "dose": "1g"}],
        "expect_types": {"allergy"},
        "min_severity": "contraindicated",
        "expect_drugs": {"amoxicillin"},
        "danger": "Penicillin given to a penicillin-allergic patient.",
    },
    "serotonin_syndrome": {
        "prescription": [{"drug": "tramadol", "dose": "50mg"}],
        "expect_types": {"interaction", "cyp_competition"},
        "min_severity": "moderate",
        "expect_drugs": {"tramadol"},
        "danger": "Tramadol plus an SSRI - serotonin syndrome.",
    },
    "elderly_dose": {
        "prescription": [{"drug": "ciprofloxacin", "dose": "500mg"}],
        "expect_types": {"dose"},
        "min_severity": "moderate",
        "expect_drugs": {"ciprofloxacin"},
        "danger": "Standard dose in an elderly / renally impaired patient.",
    },
    "cyp2c9_overload": {
        "prescription": [{"drug": "fluconazole", "dose": "200mg"}],
        "expect_types": {"interaction", "cyp_competition"},
        "min_severity": "moderate",
        "expect_drugs": {"fluconazole"},
        "danger": "CYP2C9 inhibition on a warfarin patient - bleeding.",
    },
    "therapeutic_dup": {
        "prescription": [{"drug": "atorvastatin", "dose": "20mg"}],
        "expect_types": {"duplication"},
        "min_severity": "major",
        "expect_drugs": {"atorvastatin"},
        "danger": "Same molecule already dispensed under a brand name.",
    },
}

_SEVERITY_RANK = {"contraindicated": 1, "major": 2, "moderate": 3, "minor": 4}


def _rank(severity: str | None) -> int:
    return _SEVERITY_RANK.get((severity or "").lower(), 99)


def evaluate_trap(scenario: str, spec: dict, patient: dict) -> dict:
    """Scan one trap patient and decide whether the danger was caught."""
    kwargs = to_scan_kwargs(patient)
    report = scan_prescription(spec["prescription"], **kwargs)
    alerts = report.get("alerts", [])

    failures: list[str] = []

    # 1. The right kind of finding must be present...
    matching = [a for a in alerts if a["type"] in spec["expect_types"]]
    if not matching:
        raised = sorted({a["type"] for a in alerts}) or ["nothing"]
        failures.append(
            f"expected one of {sorted(spec['expect_types'])}, raised {raised}"
        )

    # 2. ...at or above the required severity...
    severe_enough = [a for a in matching if _rank(a["severity"]) <= _rank(spec["min_severity"])]
    if matching and not severe_enough:
        worst = min(matching, key=lambda a: _rank(a["severity"]))["severity"]
        failures.append(
            f"severity too low: worst matching finding was {worst}, "
            f"needed {spec['min_severity']} or above"
        )

    # 3. ...and it must actually name the drugs at issue.
    if severe_enough:
        named = {d.lower() for a in severe_enough for d in a.get("drugs_involved", [])}
        missing = {d.lower() for d in spec["expect_drugs"]} - named
        if missing:
            failures.append(f"finding did not name {sorted(missing)} (named {sorted(named)})")

    return {
        "scenario": scenario,
        "patient": patient.get("name"),
        "passed": not failures,
        "failures": failures,
        "report": report,
        "triggering": severe_enough[0] if severe_enough else None,
    }


def run(verbose: bool = False) -> int:
    by_scenario = {
        p["trap_scenario"]: p for p in list_patients()
        if p.get("is_trap") and p.get("trap_scenario")
    }

    print()
    print("=" * 78)
    print("  MedFlow - Trap Patient Sensitivity  (a miss here is a patient harmed)")
    print("=" * 78)
    print()

    results: list[dict] = []
    for scenario, spec in TRAPS.items():
        row = by_scenario.get(scenario)
        if row is None:
            print(f"  [SKIP] {scenario:<24} no trap patient with this scenario")
            continue

        patient = load_patient(row["id"])
        if patient is None:
            print(f"  [SKIP] {scenario:<24} patient {row['id']} could not be loaded")
            continue

        outcome = evaluate_trap(scenario, spec, patient)
        results.append(outcome)

        status = "PASS" if outcome["passed"] else "MISS"
        trigger = outcome["triggering"]
        detail = (
            f"{trigger['severity']:<15} {trigger['title'][:44]}"
            if trigger else "-- nothing raised --"
        )
        print(f"  [{status}] {scenario:<24} {detail}")
        for failure in outcome["failures"]:
            print(f"         !! {failure}")

        if verbose and trigger:
            for i, step in enumerate(trigger["reasoning_chain"], 1):
                print(f"           {i}. {step}")
            print()

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    latencies = [r["report"]["latency_ms"] for r in results]

    print()
    print("-" * 78)
    pct = (passed / total * 100) if total else 0.0
    print(f"  SENSITIVITY: {passed}/{total} traps detected  ({pct:.0f}%)")
    if latencies:
        print(f"  latency: max {max(latencies):.0f} ms, mean {sum(latencies)/len(latencies):.0f} ms")
    print("=" * 78)
    print()

    if passed < total:
        print("  RESULT: FAIL - a dangerous scenario was missed.")
        return 1
    print("  RESULT: PASS - every trap patient was detected.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Trap patient sensitivity evaluation")
    parser.add_argument("--verbose", action="store_true",
                        help="print the reasoning chain of each triggering alert")
    args = parser.parse_args()
    sys.exit(run(verbose=args.verbose))


if __name__ == "__main__":
    main()
