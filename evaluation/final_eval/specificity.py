"""
Milestone 4 - SPECIFICITY, i.e. does the system cry wolf?

Sensitivity and specificity pull against each other: a system that alerts on
everything scores 100% sensitivity and is useless, because a pharmacist who is
interrupted on every second prescription stops reading the interruptions. That
is alert fatigue, and it is a patient-safety problem in its own right.

This harness scans combinations that are routine and safe in Tunisian community
practice and counts what fires. Findings are graded, because not all noise is
equal:

  * a CONTRAINDICATED or MAJOR alert on a safe combination is a **false alarm** -
    it stops a dispensation that should have proceeded
  * a MODERATE or MINOR alert is **noise** - tolerable in small amounts, harmful
    in bulk

Reported separately from sensitivity on purpose: averaging the two into one
number would hide whichever is worse.

Usage:
    python -m evaluation.final_eval.specificity
    python -m evaluation.final_eval.specificity --verbose

Exits non-zero if any safe combination raises a false alarm.
"""
from __future__ import annotations

import argparse
import sys

from engine import scan_prescription

#: Combinations a pharmacist dispenses without a second thought.
#: Each is a new prescription against an existing regimen, with patient context
#: where that context is itself unremarkable.
SAFE_CASES: list[dict] = [
    {
        "name": "amoxicillin for a hypertensive patient",
        "prescription": [{"drug": "amoxicillin", "dose": "1g"}],
        "patient_meds": ["amlodipine"],
        "conditions": ["Hypertension"],
    },
    {
        "name": "metformin + ramipril (routine diabetic + hypertensive)",
        "prescription": [{"drug": "ramipril", "dose": "5mg"}],
        "patient_meds": ["metformin"],
        "conditions": ["Type 2 diabetes mellitus", "Hypertension"],
    },
    {
        "name": "atorvastatin added to amlodipine",
        "prescription": [{"drug": "atorvastatin", "dose": "20mg"}],
        "patient_meds": ["amlodipine"],
        "conditions": ["Hyperlipidaemia"],
    },
    {
        "name": "omeprazole for reflux on levothyroxine",
        "prescription": [{"drug": "omeprazole", "dose": "20mg"}],
        "patient_meds": ["levothyroxine"],
        "conditions": ["Gastro-oesophageal reflux disease"],
    },
    {
        "name": "amoxicillin for a chest infection, no regular meds",
        "prescription": [{"drug": "amoxicillin", "dose": "500mg"}],
        "patient_meds": [],
        "conditions": ["Community-acquired pneumonia"],
    },
    {
        "name": "levothyroxine for hypothyroidism on amlodipine",
        "prescription": [{"drug": "levothyroxine", "dose": "75mcg"}],
        "patient_meds": ["amlodipine"],
        "conditions": ["Hypothyroidism"],
    },
    {
        "name": "insulin added to metformin",
        "prescription": [{"drug": "insulin glargine"}],
        "patient_meds": ["metformin"],
        "conditions": ["Type 2 diabetes mellitus"],
    },
    {
        "name": "paracetamol-class analgesia: tramadol alone, no interacting meds",
        "prescription": [{"drug": "tramadol", "dose": "50mg"}],
        "patient_meds": ["amlodipine"],
        "conditions": ["Pain"],
    },
    {
        "name": "metronidazole for a young healthy patient",
        "prescription": [{"drug": "metronidazole", "dose": "500mg"}],
        "patient_meds": [],
        "conditions": ["Bacterial infection"],
        "age": 32,
    },
    {
        "name": "prednisolone short course on levothyroxine",
        "prescription": [{"drug": "prednisolone", "dose": "20mg"}],
        "patient_meds": ["levothyroxine"],
        "conditions": ["Asthma"],
    },
]

_FALSE_ALARM = {"contraindicated", "major"}


def evaluate_case(case: dict) -> dict:
    kwargs = {k: v for k, v in case.items() if k not in ("name",)}
    prescription = kwargs.pop("prescription")
    report = scan_prescription(prescription, **kwargs)
    alerts = report.get("alerts", [])

    false_alarms = [a for a in alerts if a["severity"] in _FALSE_ALARM]
    noise = [a for a in alerts if a["severity"] not in _FALSE_ALARM]

    return {
        "name": case["name"],
        "clean": not alerts,
        "false_alarms": false_alarms,
        "noise": noise,
        "report": report,
    }


def run(verbose: bool = False) -> int:
    print()
    print("=" * 78)
    print("  MedFlow - Specificity  (does it cry wolf on safe prescriptions?)")
    print("=" * 78)
    print()

    results = [evaluate_case(case) for case in SAFE_CASES]

    for outcome in results:
        if outcome["false_alarms"]:
            status = "ALARM"
        elif outcome["noise"]:
            status = "noise"
        else:
            status = "CLEAN"
        print(f"  [{status:>5}] {outcome['name'][:58]:<60}"
              f"{len(outcome['false_alarms'])} alarm / {len(outcome['noise'])} noise")

        for alert in outcome["false_alarms"]:
            print(f"          !! {alert['severity'].upper()}: {alert['title']}")
        if verbose:
            for alert in outcome["noise"]:
                print(f"           - {alert['severity']}: {alert['title']}")

    total = len(results)
    clean = sum(1 for r in results if r["clean"])
    alarms = sum(len(r["false_alarms"]) for r in results)
    noise = sum(len(r["noise"]) for r in results)
    cases_with_alarm = sum(1 for r in results if r["false_alarms"])

    print()
    print("-" * 78)
    print(f"  SPECIFICITY: {total - cases_with_alarm}/{total} safe cases free of false alarms "
          f"({(total - cases_with_alarm) / total * 100:.0f}%)")
    print(f"  fully clean screens: {clean}/{total}")
    print(f"  false alarms (contraindicated/major): {alarms}")
    print(f"  low-grade noise (moderate/minor):     {noise}"
          f"   ({noise / total:.1f} per safe prescription)")
    print("=" * 78)
    print()

    if alarms:
        print("  RESULT: FAIL - a safe prescription was blocked by a false alarm.")
        return 1
    print("  RESULT: PASS - no safe prescription raised a false alarm.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Specificity / alert-fatigue evaluation")
    parser.add_argument("--verbose", action="store_true", help="list low-grade noise too")
    args = parser.parse_args()
    sys.exit(run(verbose=args.verbose))


if __name__ == "__main__":
    main()
