"""
Function 10 — full_prescription_check(prescription, patient_meds, conditions, allergies, labs)

Integration function: runs all safety checks and returns a single combined
report.  Defined early to enforce the return envelope that all sub-functions
must conform to.
"""
from ._neo4j import ok, err
from .resolve import resolve_drug_name
from .interactions import detect_pairwise_interactions, detect_cyp_competition
from .safety import (
    check_contraindications,
    check_allergy_conflict,
    check_therapeutic_duplication,
    check_dose_appropriateness,
)


def full_prescription_check(
    prescription: list[dict],
    patient_meds: list[str] | None = None,
    conditions:   list[str] | None = None,
    allergies:    list[str] | None = None,
    labs:         dict       | None = None,
) -> dict:
    """
    Run all safety checks for a new prescription against a patient's current state.

    Args:
        prescription:  list of dicts, each with at least {"drug": str} and
                       optionally {"dose": str}.
                       Example: [{"drug": "simvastatin", "dose": "40mg"},
                                  {"drug": "clarithromycin"}]
        patient_meds:  currently active medications (names, any form)
        conditions:    patient conditions as free text or ICD codes
        allergies:     patient allergies (e.g. ["penicillin", "sulfa"])
        labs:          lab values dict (creatinine_umol_L, egfr, alt_iu_L, ast_iu_L)

    Returns a combined report with sections:
        interactions, cyp_competition, contraindications,
        allergy_conflicts, duplications, dose_flags, summary
    """
    patient_meds = patient_meds or []
    conditions   = conditions   or []
    allergies    = allergies    or []
    labs         = labs         or {}

    if not prescription:
        return err("No prescription drugs provided")

    new_drug_names = [p["drug"] for p in prescription if p.get("drug")]
    if not new_drug_names:
        return err("No drug names in prescription entries")

    all_drugs = new_drug_names + patient_meds

    # ── 1. Pairwise interactions across all drugs ─────────────────────────────
    interaction_result = detect_pairwise_interactions(all_drugs) if len(all_drugs) >= 2 else {
        "status": "not_found", "data": {"interactions": []}, "message": "Only one drug"
    }

    # ── 2. CYP competition across all drugs ───────────────────────────────────
    cyp_result = detect_cyp_competition(all_drugs) if len(all_drugs) >= 2 else {
        "status": "not_found", "data": {"competitions": []}, "message": "Only one drug"
    }

    # ── 3-6. Per-new-drug safety checks ──────────────────────────────────────
    per_drug = {}
    for entry in prescription:
        drug = entry.get("drug", "")
        dose = entry.get("dose")
        if not drug:
            continue

        resolved = resolve_drug_name(drug)
        inn = resolved["data"].get("canonical", drug) if resolved["status"] == "found" else drug

        per_drug[inn] = {
            "input_name":        drug,
            "resolved":          resolved["status"] == "found",
            "contraindications": check_contraindications(drug, conditions),
            "allergy_conflict":  check_allergy_conflict(drug, allergies),
            "duplication":       check_therapeutic_duplication(drug, patient_meds),
            "dose_check":        check_dose_appropriateness(
                                     drug, dose=dose, labs=labs,
                                 ) if dose or labs else None,
        }

    # ── Build summary ─────────────────────────────────────────────────────────
    all_interactions  = interaction_result.get("data", {}).get("interactions", [])
    all_competitions  = cyp_result.get("data", {}).get("competitions", [])
    all_ci            = [
        ci
        for d in per_drug.values()
        for ci in d["contraindications"].get("data", {}).get("contraindications", [])
    ]
    all_allergy       = [
        c
        for d in per_drug.values()
        for c in d["allergy_conflict"].get("data", {}).get("conflicts", [])
    ]
    all_dup           = [
        dup
        for d in per_drug.values()
        for dup in d["duplication"].get("data", {}).get("duplicates", [])
    ]
    all_dose_flags    = [
        flag
        for d in per_drug.values()
        if d.get("dose_check")
        for flag in d["dose_check"].get("data", {}).get("flags", [])
    ]

    critical_count = (
        len([i for i in all_interactions if i.get("severity") in ("contre_indique", "deconseillee", "major")])
        + len([c for c in all_competitions if c.get("strength") == "strong"])
        + len([ci for ci in all_ci if ci.get("severity") == "contraindicated"])
        + len(all_allergy)
        + len(all_dup)
    )

    summary = {
        "new_drugs":           new_drug_names,
        "patient_meds":        patient_meds,
        "interactions_found":  len(all_interactions),
        "cyp_competitions":    len(all_competitions),
        "contraindications":   len(all_ci),
        "allergy_conflicts":   len(all_allergy),
        "duplications":        len(all_dup),
        "dose_flags":          len(all_dose_flags),
        "critical_issues":     critical_count,
        "overall_risk":        (
            "HIGH"   if critical_count > 0 else
            "MEDIUM" if (len(all_interactions) + len(all_competitions)) > 0 else
            "LOW"
        ),
    }

    status = "found" if critical_count > 0 or all_interactions or all_competitions else "not_found"

    return {
        "status": status,
        "data": {
            "summary":          summary,
            "interactions":     all_interactions,
            "cyp_competition":  all_competitions,
            "per_drug":         per_drug,
        },
        "message": (
            f"{critical_count} critical issue(s) — overall risk: {summary['overall_risk']}"
        ),
    }
