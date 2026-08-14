"""
Milestone 4 - SEVERITY ACCURACY.

Detecting an interaction is not enough: the grade drives what the pharmacist
does. "Contact the prescriber" and "dispense with a counselling note" are
different actions, and a system that inflates every finding to MAJOR is as
unusable as one that misses them.

Two different questions are being asked here, and they are kept apart on
purpose:

  A. **Does the engine report the knowledge base faithfully?**
     An engineering question with a right answer. The graph stores ANSM grades
     (contre_indique, deconseillee, ...); the engine maps them onto the
     four-level scale the interface shows. A mismatch is a bug.

  B. **Is the knowledge base clinically right?**
     A clinical question this project cannot answer by itself. The reference
     column below is the author's reading of standard practice, not an
     authority. Disagreements are reported for the pharmacist to adjudicate in
     the review session - they are printed as REVIEW, not FAIL.

Usage:
    python -m evaluation.final_eval.severity_accuracy

Exits non-zero only on a mapping bug (question A).
"""
from __future__ import annotations

import sys

from engine import alerts as A
from engine import scan_prescription

#: (new drug, existing meds, expected severity band, clinical rationale)
#: The expected band is a *reference judgement* — see question B above.
REFERENCE: list[tuple] = [
    ("aspirin",        ["warfarin"],       A.MAJOR,
     "Additive bleeding risk; routinely co-prescribed under monitoring."),
    ("clarithromycin", ["simvastatin"],    A.CONTRAINDICATED,
     "Strong CYP3A4 inhibition; rhabdomyolysis risk - withhold the statin."),
    ("amiodarone",     ["warfarin"],       A.CONTRAINDICATED,
     "Marked INR elevation; ANSM grades this contre-indique."),
    ("fluconazole",    ["warfarin"],       A.MAJOR,
     "CYP2C9 inhibition raises INR; manageable with monitoring."),
    ("tramadol",       ["fluoxetine"],     A.MAJOR,
     "Serotonergic load plus CYP2D6 inhibition."),
    ("ibuprofen",      ["warfarin"],       A.MAJOR,
     "NSAID on an anticoagulant - GI bleeding."),
    ("azathioprine",   ["allopurinol"],    A.CONTRAINDICATED,
     "Xanthine oxidase inhibition; profound myelosuppression."),
    ("digoxin",        ["amiodarone"],     A.MAJOR,
     "Amiodarone raises digoxin levels; toxicity risk."),
    ("omeprazole",     ["clopidogrel"],    A.MODERATE,
     "CYP2C19 inhibition reduces clopidogrel activation; clinically debated."),
    ("diclofenac",     ["methotrexate"],   A.MAJOR,
     "Reduced methotrexate clearance."),
    ("verapamil",      ["simvastatin"],    A.MAJOR,
     "CYP3A4 inhibition; statin myopathy risk."),
    ("rifampicin",     ["warfarin"],       A.MAJOR,
     "Strong CYP inducer; loss of anticoagulation."),
]


def _worst(alerts: list[dict], drugs: set[str]) -> dict | None:
    """The most severe alert naming both drugs at issue."""
    involving = [
        a for a in alerts
        if drugs <= {d.lower() for d in a.get("drugs_involved", [])}
    ]
    return min(involving, key=lambda a: a["severity_rank"]) if involving else None


def run() -> int:
    print()
    print("=" * 78)
    print("  MedFlow - Severity Accuracy")
    print("=" * 78)
    print()
    print(f"  {'combination':<34}{'expected':<17}{'reported':<17}verdict")
    print("  " + "-" * 74)

    agree = 0
    review: list[str] = []
    mapping_bugs: list[str] = []
    missed = 0

    for new_drug, meds, expected, rationale in REFERENCE:
        report = scan_prescription([{"drug": new_drug}], patient_meds=meds)
        alert = _worst(report["alerts"], {new_drug.lower(), *(m.lower() for m in meds)})
        combo = f"{new_drug} + {', '.join(meds)}"

        if alert is None:
            print(f"  {combo:<34}{expected:<17}{'-- not raised --':<17}MISS")
            missed += 1
            continue

        reported = alert["severity"]

        # Question A: does the reported severity follow from the stored grade?
        #
        # A merged alert covers two findings for one pair (a documented
        # interaction plus enzyme competition) and deliberately carries the more
        # severe of the two, so its severity is not required to equal the ANSM
        # grade - only to be at least as severe as it. Checking equality there
        # would flag correct behaviour as a bug.
        grade = (alert.get("evidence", {}) or {}).get("ansm_grade")
        if grade:
            from_grade = A.severity_from_ansm(grade)
            merged = bool(alert.get("merged_from"))
            if merged:
                if alert["severity_rank"] > A.SEVERITY_RANK[from_grade]:
                    mapping_bugs.append(
                        f"{combo}: merged alert reported {reported}, which is less "
                        f"severe than the stored grade '{grade}' ({from_grade})"
                    )
            elif from_grade != reported:
                mapping_bugs.append(
                    f"{combo}: stored grade '{grade}' should map to "
                    f"{from_grade}, engine reported {reported}"
                )

        # Question B: does the knowledge base agree with the reference?
        if reported == expected:
            verdict = "agree"
            agree += 1
        else:
            verdict = "REVIEW"
            review.append(f"{combo}: reference {expected}, system {reported} - {rationale}")

        print(f"  {combo:<34}{expected:<17}{reported:<17}{verdict}")

    total = len(REFERENCE)
    print("  " + "-" * 74)
    print(f"  agreement with reference: {agree}/{total} ({agree / total * 100:.0f}%)")
    print(f"  not detected at all:      {missed}")
    print(f"  engine mapping bugs:      {len(mapping_bugs)}")
    print("=" * 78)

    if mapping_bugs:
        print()
        print("  MAPPING BUGS (engine does not report the stored grade faithfully):")
        for bug in mapping_bugs:
            print(f"    !! {bug}")

    if review:
        print()
        print("  FOR PHARMACIST REVIEW (knowledge-base grading, not an engine fault):")
        for item in review:
            print(f"    ? {item}")

    print()
    if mapping_bugs:
        print("  RESULT: FAIL - severity mapping is wrong.")
        return 1
    print("  RESULT: PASS - severity is reported faithfully from the knowledge base.")
    if review:
        print(f"           {len(review)} grading question(s) queued for the pharmacist.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
