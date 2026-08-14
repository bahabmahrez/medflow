"""
Functions 5, 6, 7, 8 — safety checks

  5. check_contraindications(drug, conditions)
  6. check_allergy_conflict(drug, allergies)
  7. check_therapeutic_duplication(new_drug, active_meds)
  8. check_dose_appropriateness(drug, dose, age, weight, labs)
"""
from ._neo4j import connect, ok, not_found, err
from .resolve import resolve_drug_name


def check_contraindications(drug: str, conditions: list[str]) -> dict:
    """
    Check whether a drug is contraindicated for any of the patient's conditions.

    Matches conditions against DiseaseConcept.condition_name (substring) or
    DiseaseConcept.icd11_code (exact) to handle both free-text and coded input.

    Example:
        check_contraindications("metformin", ["CKD stage 4"])
        -> contraindicated: lactic acidosis risk (icd=N18)

        check_contraindications("warfarin", ["pregnancy"])
        -> contraindicated: teratogenic (icd=Z34)
    """
    resolved = resolve_drug_name(drug)
    if resolved["status"] != "found":
        return resolved

    inn = resolved["data"]["canonical"]
    if not conditions:
        return ok(
            {"drug": inn, "conditions_checked": [], "contraindications": []},
            "No conditions provided",
        )

    driver = connect()
    try:
        found = []
        for condition in conditions:
            # Match the patient's condition to a concept, then walk the IS_A
            # hierarchy up to whatever the drug is actually contraindicated for.
            # Contraindications are recorded against general concepts ("Renal
            # impairment") while patients carry specific ones ("Chronic kidney
            # disease stage 4"); without this traversal the two never meet.
            result = driver.execute_query(
                """
                MATCH (pc:DiseaseConcept)
                WHERE toLower(pc.condition_name) CONTAINS toLower($condition)
                   OR pc.icd11_code = $condition
                MATCH path = (pc)-[:IS_A*0..3]->(target:DiseaseConcept)
                MATCH (m:Molecule {inn: $inn})-[r:CONTRAINDICATED_FOR]->(target)
                // The same concept can be reachable by several routes (a
                // duplicate code, or a code plus its parent). Keep the shortest
                // route per contraindication so one risk is reported once.
                WITH target, r, pc, length(path) AS hops
                ORDER BY hops
                WITH target, r,
                     head(collect({via: pc.condition_name, hops: hops})) AS best
                RETURN target.condition_name AS condition_name,
                       target.icd11_code     AS icd_code,
                       best.via              AS matched_via,
                       best.hops > 0         AS generalised,
                       r.severity            AS severity,
                       r.reason              AS reason,
                       r.source              AS source
                """,
                inn=inn, condition=condition,
            )
            for rec in result.records:
                found.append({
                    "input_condition":  condition,
                    "matched_concept":  rec["condition_name"],
                    "icd_code":         rec["icd_code"],
                    "matched_via":      rec["matched_via"],
                    "generalised":      bool(rec["generalised"]),
                    "severity":         rec["severity"],
                    "reason":           rec["reason"],
                    "source":           rec["source"],
                })

        status = "found" if found else "not_found"
        msg = (
            f"{len(found)} contraindication(s) for '{inn}' given conditions: {conditions}"
            if found
            else f"No contraindications found for '{inn}' with given conditions"
        )
        return {
            "status": status,
            "data": {
                "drug":                inn,
                "conditions_checked":  conditions,
                "contraindications":   found,
            },
            "message": msg,
        }

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()


def check_allergy_conflict(drug: str, allergies: list[str]) -> dict:
    """
    Check whether a drug conflicts with the patient's stated allergies.

    Checks:
      1. Direct match: the drug's allergy group is in the patient's allergy list
      2. Cross-reactivity: the drug's group CROSS_REACTS_WITH a group the
         patient is allergic to

    Example:
        check_allergy_conflict("amoxicillin", ["penicillin"])
        -> direct conflict: amoxicillin belongs to penicillin group

        check_allergy_conflict("cephalexin", ["penicillin"])
        -> cross-reactivity: cephalosporin cross-reacts with penicillin
    """
    resolved = resolve_drug_name(drug)
    if resolved["status"] != "found":
        return resolved

    inn = resolved["data"]["canonical"]
    if not allergies:
        return ok(
            {"drug": inn, "allergies_checked": [], "conflicts": []},
            "No allergies provided",
        )

    allergies_lower = [a.strip().lower() for a in allergies]
    driver = connect()
    try:
        result = driver.execute_query(
            """
            MATCH (d:Drug)-[:BRAND_OF]->(m:Molecule {inn: $inn})
            MATCH (d)-[:BELONGS_TO_ALLERGY_GROUP]->(ag:AllergyGroup)
            OPTIONAL MATCH (ag)-[:CROSS_REACTS_WITH]->(cross:AllergyGroup)
            RETURN ag.name AS allergy_group,
                   collect(DISTINCT cross.name) AS cross_reactive
            LIMIT 1
            """,
            inn=inn,
        )

        if not result.records or not result.records[0]["allergy_group"]:
            return not_found(
                f"'{inn}' has no allergy group in knowledge base — no conflict detected",
                data={
                    "drug":              inn,
                    "allergies_checked": allergies,
                    "conflicts":         [],
                    "allergy_group":     None,
                },
            )

        rec = result.records[0]
        group = rec["allergy_group"]
        cross = [c.lower() for c in (rec["cross_reactive"] or [])]

        conflicts = []
        for allergy in allergies_lower:
            if allergy == group.lower():
                conflicts.append({
                    "type":           "direct",
                    "patient_allergy": allergy,
                    "drug_group":      group,
                    "message":         f"Direct allergy conflict: '{inn}' belongs to '{group}'",
                })
            elif allergy in cross:
                conflicts.append({
                    "type":           "cross_reactive",
                    "patient_allergy": allergy,
                    "drug_group":      group,
                    "cross_reacts_with": allergy,
                    "message":         (
                        f"Cross-reactivity risk: '{inn}' is in '{group}', "
                        f"which cross-reacts with '{allergy}'"
                    ),
                })

        status = "found" if conflicts else "not_found"
        msg = (
            f"{len(conflicts)} allergy conflict(s) for '{inn}'"
            if conflicts
            else f"No allergy conflicts for '{inn}' with given allergies"
        )
        return {
            "status": status,
            "data": {
                "drug":              inn,
                "allergy_group":     group,
                "cross_reactive_to": rec["cross_reactive"],
                "allergies_checked": allergies,
                "conflicts":         conflicts,
            },
            "message": msg,
        }

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()


def check_therapeutic_duplication(new_drug: str, active_meds: list[str]) -> dict:
    """
    Detect if the new drug is already being taken under a different name.

    Resolves all active medications to their canonical INN and checks if any
    match the new drug.  Catches Tahor + atorvastatin, Coumadin + warfarin, etc.

    Example:
        check_therapeutic_duplication("atorvastatin", ["Tahor", "metformin"])
        -> duplication: atorvastatin already prescribed as 'Tahor'
    """
    resolved_new = resolve_drug_name(new_drug)
    if resolved_new["status"] != "found":
        return resolved_new

    new_inn = resolved_new["data"]["canonical"]

    if not active_meds:
        return not_found(
            "No active medications provided",
            data={"new_drug": new_inn, "active_meds_resolved": [], "duplicates": []},
        )

    resolved_meds = {}
    unresolved = []
    for med in active_meds:
        r = resolve_drug_name(med)
        if r["status"] == "found":
            resolved_meds[med] = r["data"]["canonical"]
        else:
            unresolved.append(med)

    duplicates = [
        {"input_name": name, "resolved_inn": inn, "same_as": new_inn}
        for name, inn in resolved_meds.items()
        if inn == new_inn
    ]

    status = "found" if duplicates else "not_found"
    msg = (
        f"Therapeutic duplication detected: '{new_inn}' already in active medications"
        if duplicates
        else f"No duplication: '{new_inn}' not present in active medications"
    )
    return {
        "status": status,
        "data": {
            "new_drug":            new_inn,
            "active_meds_resolved": resolved_meds,
            "unresolved":          unresolved,
            "duplicates":          duplicates,
        },
        "message": msg,
    }


def check_dose_appropriateness(
    drug: str,
    dose: str | None = None,
    age: int | None = None,
    weight: float | None = None,
    labs: dict | None = None,
) -> dict:
    """
    Compare a prescribed dose against the graph's dose ranges, adjusted for
    the patient's age and renal/hepatic function.

    labs dict keys accepted:
        creatinine_umol_L  — serum creatinine in µmol/L  (flag if > 150)
        egfr               — eGFR in mL/min/1.73m2       (flag if < 30)
        alt_iu_L           — ALT in IU/L                  (flag if > 120)
        ast_iu_L           — AST in IU/L                  (flag if > 120)

    Note: dose fields in the graph are free text (e.g. "500-2000mg/day").
    This function returns them as guidance strings; the LLM in Milestone 3
    interprets them in context.

    Example:
        check_dose_appropriateness("ciprofloxacin", dose="500mg", age=78,
                                    labs={"creatinine_umol_L": 210})
        -> flags elderly + renal adjustment needed
    """
    resolved = resolve_drug_name(drug)
    if resolved["status"] != "found":
        return resolved

    inn = resolved["data"]["canonical"]
    labs = labs or {}

    driver = connect()
    try:
        result = driver.execute_query(
            """
            MATCH (d:Drug)-[:BRAND_OF]->(m:Molecule {inn: $inn})
            RETURN d.dose_adult              AS dose_adult,
                   d.dose_elderly            AS dose_elderly,
                   d.dose_renal_impairment   AS dose_renal,
                   d.dose_hepatic_impairment AS dose_hepatic,
                   d.therapeutic_category    AS category
            LIMIT 1
            """,
            inn=inn,
        )

        if not result.records:
            return not_found(f"No dose data found for '{inn}'")

        rec = result.records[0]

        flags = []
        recommendations = []

        elderly = age is not None and age >= 75

        def _get_val(d, key, default):
            v = d.get(key)
            return default if v is None else v

        renal   = (
            _get_val(labs, "creatinine_umol_L", 0) > 150
            or _get_val(labs, "egfr", 100) < 30
        )
        hepatic = (
            _get_val(labs, "alt_iu_L", 0) > 120
            or _get_val(labs, "ast_iu_L", 0) > 120
        )

        if elderly and rec["dose_elderly"]:
            flags.append("elderly")
            recommendations.append({
                "flag":   "elderly",
                "reason": f"Patient age {age} >= 75",
                "guidance": rec["dose_elderly"],
            })

        if renal and rec["dose_renal"]:
            flags.append("renal_impairment")
            recommendations.append({
                "flag":   "renal_impairment",
                "reason": (
                    f"creatinine={labs.get('creatinine_umol_L', '?')} umol/L"
                    if labs.get("creatinine_umol_L")
                    else f"eGFR={labs.get('egfr', '?')} mL/min"
                ),
                "guidance": rec["dose_renal"],
            })

        if hepatic and rec["dose_hepatic"]:
            flags.append("hepatic_impairment")
            recommendations.append({
                "flag":   "hepatic_impairment",
                "reason": f"ALT/AST elevated",
                "guidance": rec["dose_hepatic"],
            })

        status = "found" if recommendations else "not_found"
        msg = (
            f"{len(flags)} dose flag(s) for '{inn}': {', '.join(flags)}"
            if flags
            else f"No dose adjustment flags for '{inn}' with given parameters"
        )

        return {
            "status": status,
            "data": {
                "drug":              inn,
                "prescribed_dose":   dose,
                "age":               age,
                "weight":            weight,
                "labs":              labs,
                "standard_dose":     rec["dose_adult"],
                "flags":             flags,
                "recommendations":   recommendations,
            },
            "message": msg,
        }

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()
