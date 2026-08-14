"""
Alert model for the reactive engine.

Turns raw findings from the ``query`` layer into pharmacist-facing alerts:
a canonical severity, a recommended action, a plain-language explanation, and
a **reasoning chain** - the ordered steps that lead from the patient's data to
the conclusion, so the pharmacist can evaluate the finding rather than obey it.

Design note - why the reasoning chains are built here and not by the LLM:
every sentence below is derived from data already returned by the graph. That
keeps the reactive scan inside its 2-second budget (no inference call in the
hot path) and, just as importantly, makes fabrication structurally impossible:
if the graph does not record a mechanism, no mechanism is stated.
"""
from __future__ import annotations

# ── Canonical severity scale ──────────────────────────────────────────────────
CONTRAINDICATED = "contraindicated"
MAJOR           = "major"
MODERATE        = "moderate"
MINOR           = "minor"

SEVERITY_RANK = {CONTRAINDICATED: 1, MAJOR: 2, MODERATE: 3, MINOR: 4}

# Colour cues for the interface - red / orange / yellow as specified.
SEVERITY_COLOR = {
    CONTRAINDICATED: "red",
    MAJOR:           "orange",
    MODERATE:        "yellow",
    MINOR:           "blue",
}

# ── Recommended actions ───────────────────────────────────────────────────────
DO_NOT_DISPENSE    = "do_not_dispense"
CONTACT_PRESCRIBER = "contact_prescriber"
DISPENSE_WITH_NOTE = "dispense_with_note"
DISPENSE           = "dispense"

ACTION_RANK = {
    DO_NOT_DISPENSE:    1,
    CONTACT_PRESCRIBER: 2,
    DISPENSE_WITH_NOTE: 3,
    DISPENSE:           4,
}

ACTION_LABEL = {
    DO_NOT_DISPENSE:    "Do not dispense",
    CONTACT_PRESCRIBER: "Contact prescriber",
    DISPENSE_WITH_NOTE: "Dispense with counselling note",
    DISPENSE:           "Dispense",
}

_ACTION_PHRASE = {
    DO_NOT_DISPENSE:    "withhold the dispensation and contact the prescriber",
    CONTACT_PRESCRIBER: "contact the prescriber before dispensing",
    DISPENSE_WITH_NOTE: "dispense with a counselling note and monitoring advice",
    DISPENSE:           "dispense normally",
}

SEVERITY_TO_ACTION = {
    CONTRAINDICATED: DO_NOT_DISPENSE,
    MAJOR:           CONTACT_PRESCRIBER,
    MODERATE:        DISPENSE_WITH_NOTE,
    MINOR:           DISPENSE_WITH_NOTE,
}

# ── ANSM grade mapping ────────────────────────────────────────────────────────
# The graph stores French ANSM severity grades; the interface needs a 4-level
# scale. Labels mirror llm/system_prompt.txt so wording stays consistent.
ANSM_TO_SEVERITY = {
    "contre_indique":      CONTRAINDICATED,
    "major":               MAJOR,
    "deconseillee":        MAJOR,
    "moderate":            MODERATE,
    "precaution_emploi":   MODERATE,
    "a_prendre_en_compte": MINOR,
    "minor":               MINOR,
}

ANSM_LABEL = {
    "contre_indique":      "CONTRAINDICATED",
    "major":               "MAJOR",
    "deconseillee":        "NOT RECOMMENDED",
    "moderate":            "MODERATE",
    "precaution_emploi":   "PRECAUTION FOR USE",
    "a_prendre_en_compte": "TAKE INTO ACCOUNT",
    "minor":               "MINOR",
}

# Alert types
TYPE_INTERACTION      = "interaction"
TYPE_CYP              = "cyp_competition"
TYPE_CONTRAINDICATION = "contraindication"
TYPE_ALLERGY          = "allergy"
TYPE_DUPLICATION      = "duplication"
TYPE_DOSE             = "dose"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cap(text: str | None) -> str:
    """Capitalise a drug/INN name for display without touching the rest."""
    if not text:
        return "this medicine"
    return text[0].upper() + text[1:]


def severity_from_ansm(grade: str | None) -> str:
    """Map an ANSM severity grade to the canonical scale (unknown -> moderate)."""
    return ANSM_TO_SEVERITY.get((grade or "").strip().lower(), MODERATE)


def _make_alert(
    *,
    alert_id: str,
    alert_type: str,
    severity: str,
    title: str,
    explanation: str,
    reasoning_chain: list[str],
    drugs_involved: list[str],
    evidence: dict,
    action: str | None = None,
) -> dict:
    resolved_action = action or SEVERITY_TO_ACTION.get(severity, DISPENSE_WITH_NOTE)
    return {
        "id":                 alert_id,
        "type":               alert_type,
        "severity":           severity,
        "severity_rank":      SEVERITY_RANK.get(severity, 99),
        "color":              SEVERITY_COLOR.get(severity, "blue"),
        "title":              title,
        "explanation":        explanation,
        "reasoning_chain":    reasoning_chain,
        "drugs_involved":     drugs_involved,
        "recommended_action": resolved_action,
        "action_label":       ACTION_LABEL.get(resolved_action, resolved_action),
        "evidence":           {k: v for k, v in evidence.items() if v not in (None, "", [])},
    }


def _origin_phrase(drug: str, new_drugs: set[str], active_meds: set[str]) -> str:
    lowered = (drug or "").lower()
    if lowered in new_drugs and lowered in active_meds:
        return "on both the new prescription and the active list"
    if lowered in new_drugs:
        return "newly prescribed"
    if lowered in active_meds:
        return "an active medication"
    return "in this patient's medication set"


# ── Builders, one per finding type ────────────────────────────────────────────

def build_interaction_alert(
    item: dict, index: int, new_drugs: set[str], active_meds: set[str]
) -> dict:
    a, b = item.get("drug_a", ""), item.get("drug_b", "")
    grade = (item.get("severity") or "").lower()
    severity = severity_from_ansm(grade)
    label = ANSM_LABEL.get(grade, grade.upper() or "DOCUMENTED")
    effect    = item.get("effect")
    mechanism = item.get("mechanism")
    source    = item.get("source")
    action = SEVERITY_TO_ACTION.get(severity, DISPENSE_WITH_NOTE)

    chain = [
        f"{_cap(a)} is {_origin_phrase(a, new_drugs, active_meds)}; "
        f"{b} is {_origin_phrase(b, new_drugs, active_meds)} - so the two will be taken together.",
        f"The knowledge base records a documented interaction between {a} and {b}, "
        f"graded {label}" + (f" (source: {source})" if source else "") + ".",
    ]
    if mechanism:
        chain.append(f"Mechanism - {mechanism}")
    if effect:
        chain.append(f"Expected clinical effect - {effect}")
    chain.append(
        f"At {label} severity, the recommended handling is to {_ACTION_PHRASE[action]}."
    )

    explanation = (
        f"{_cap(a)} and {b} interact ({label.lower()})."
        + (f" {effect}" if effect else "")
    )

    return _make_alert(
        alert_id=f"INT-{index:02d}",
        alert_type=TYPE_INTERACTION,
        severity=severity,
        title=f"{_cap(a)} + {_cap(b)} - {label.lower()} interaction",
        explanation=explanation,
        reasoning_chain=chain,
        drugs_involved=[a, b],
        evidence={
            "ansm_grade": grade, "mechanism": mechanism,
            "clinical_effect": effect, "source": source,
        },
        action=action,
    )


def build_cyp_alert(
    item: dict,
    index: int,
    new_drugs: set[str],
    active_meds: set[str],
    *,
    has_direct_edge: bool = False,
) -> dict:
    substrate = item.get("substrate", "")
    modulator = item.get("modulator", "")
    enzyme    = item.get("enzyme", "the shared enzyme")
    effect    = (item.get("effect") or "").upper()
    strength  = (item.get("strength") or "unknown").lower()
    risk      = item.get("risk")

    inhibits = effect == "INHIBITS"
    severity = {"strong": MAJOR, "moderate": MODERATE}.get(strength, MINOR)
    action = SEVERITY_TO_ACTION.get(severity, DISPENSE_WITH_NOTE)
    role = "inhibitor" if inhibits else "inducer"

    chain = [
        f"{_cap(modulator)} ({_origin_phrase(modulator, new_drugs, active_meds)}) "
        f"is recorded as a {strength} {role} of {enzyme}.",
        f"{_cap(substrate)} ({_origin_phrase(substrate, new_drugs, active_meds)}) "
        f"is metabolised by {enzyme}.",
    ]
    # Only claim the pathway is the *sole* signal when that is actually true —
    # this pair may also carry a documented direct interaction.
    if has_direct_edge:
        chain.append(
            "This pair also carries a documented direct interaction; the shared "
            "enzyme pathway explains part of that risk."
        )
    else:
        chain.append(
            "There is no direct interaction edge between these two drugs - this risk "
            "is visible only through the metabolic pathway they share."
        )
    if inhibits:
        chain.append(
            f"With {enzyme} inhibited, {substrate} is cleared more slowly and its plasma "
            f"concentration rises above the expected range."
        )
    else:
        chain.append(
            f"With {enzyme} induced, {substrate} is cleared faster and may fall below "
            f"its therapeutic range."
        )
    if risk:
        chain.append(f"Clinical consequence - {risk}.")
    chain.append(
        f"Because the {role} is graded {strength}, the recommended handling is to "
        f"{_ACTION_PHRASE[action]}."
    )

    direction = "accumulation" if inhibits else "loss of effect"
    explanation = (
        f"{_cap(modulator)} {'inhibits' if inhibits else 'induces'} {enzyme}, which "
        f"metabolises {substrate} - risk of {substrate} {direction}. "
        + ("Documented alongside a direct interaction for this pair."
           if has_direct_edge else
           "No direct interaction is recorded; this is enzyme-mediated.")
    )

    return _make_alert(
        alert_id=f"CYP-{index:02d}",
        alert_type=TYPE_CYP,
        severity=severity,
        title=f"{_cap(substrate)} + {_cap(modulator)} - {enzyme} competition ({strength})",
        explanation=explanation,
        reasoning_chain=chain,
        drugs_involved=[substrate, modulator],
        evidence={
            "enzyme": enzyme, "effect": effect,
            "strength": strength, "risk": risk,
        },
        action=action,
    )


def build_contraindication_alert(item: dict, drug: str, index: int) -> dict:
    condition  = item.get("input_condition", "")
    matched    = item.get("matched_concept", condition)
    icd        = item.get("icd_code")
    raw_sev    = (item.get("severity") or "").lower()
    reason     = item.get("reason")
    source     = item.get("source")

    severity = CONTRAINDICATED if "contraindicat" in raw_sev or raw_sev in {
        "contre_indique", "absolute"
    } else MAJOR
    action = SEVERITY_TO_ACTION[severity]

    generalised = bool(item.get("generalised"))
    matched_via = item.get("matched_via") or condition

    chain = [f"The patient's record lists the condition '{condition}'."]
    if generalised:
        # Say plainly that this came from the concept hierarchy rather than a
        # direct match - the pharmacist is entitled to see the inference.
        chain.append(
            f"The knowledge base classifies '{matched_via}' as a form of "
            f"'{matched}'" + (f" (ICD-11 {icd})" if icd else "") + "."
        )
    else:
        chain.append(
            f"This matches the knowledge-base concept '{matched}'"
            + (f" (ICD-11 {icd})" if icd else "") + "."
        )
    chain.append(
        f"{_cap(drug)} is recorded as contraindicated for this condition"
        + (f" (source: {source})" if source else "") + "."
    )
    if reason:
        chain.append(f"Reason - {reason}")
    chain.append(
        f"Given a documented contraindication, the recommended handling is to "
        f"{_ACTION_PHRASE[action]}."
    )

    explanation = (
        f"{_cap(drug)} is contraindicated in {matched}."
        + (f" {reason}" if reason else "")
    )

    return _make_alert(
        alert_id=f"CI-{index:02d}",
        alert_type=TYPE_CONTRAINDICATION,
        severity=severity,
        title=f"{_cap(drug)} - contraindicated in {matched}",
        explanation=explanation,
        reasoning_chain=chain,
        drugs_involved=[drug],
        evidence={
            "condition": condition, "matched_concept": matched,
            "icd_code": icd, "reason": reason, "source": source,
        },
        action=action,
    )


def build_allergy_alert(item: dict, drug: str, index: int) -> dict:
    kind    = item.get("type", "direct")
    allergy = item.get("patient_allergy", "")
    group   = item.get("drug_group", "")
    direct  = kind == "direct"

    severity = CONTRAINDICATED if direct else MAJOR
    action = SEVERITY_TO_ACTION[severity]

    if direct:
        chain = [
            f"The patient has a recorded allergy to '{allergy}'.",
            f"{_cap(drug)} belongs to the '{group}' allergy group.",
            f"The patient's allergy matches this drug's own group directly.",
            "Administering it risks a hypersensitivity reaction, up to anaphylaxis.",
        ]
        explanation = (
            f"{_cap(drug)} belongs to '{group}', which the patient is directly "
            f"allergic to."
        )
        title = f"{_cap(drug)} - direct allergy conflict ({allergy})"
    else:
        chain = [
            f"The patient has a recorded allergy to '{allergy}'.",
            f"{_cap(drug)} belongs to the '{group}' allergy group.",
            f"'{group}' is recorded as cross-reacting with '{allergy}'.",
            "Cross-reactivity means a hypersensitivity reaction remains possible even "
            "though the patient has not reacted to this exact drug before.",
        ]
        explanation = (
            f"{_cap(drug)} is in '{group}', which cross-reacts with the patient's "
            f"'{allergy}' allergy."
        )
        title = f"{_cap(drug)} - cross-reactive allergy risk ({allergy})"

    chain.append(f"Recommended handling is to {_ACTION_PHRASE[action]}.")

    return _make_alert(
        alert_id=f"ALG-{index:02d}",
        alert_type=TYPE_ALLERGY,
        severity=severity,
        title=title,
        explanation=explanation,
        reasoning_chain=chain,
        drugs_involved=[drug],
        evidence={"conflict_type": kind, "patient_allergy": allergy, "drug_group": group},
        action=action,
    )


def build_duplication_alert(item: dict, index: int) -> dict:
    existing = item.get("input_name", "")
    inn      = item.get("resolved_inn", "")
    same_as  = item.get("same_as", inn)
    action = CONTACT_PRESCRIBER

    # The active list may hold the molecule under a brand name or under the INN
    # itself. Saying "atorvastatin is already taken as 'atorvastatin'" is
    # tautological, so only describe a rename when there genuinely is one.
    renamed = (existing or "").strip().lower() != (inn or "").strip().lower()

    chain = [f"{_cap(same_as)} is on the new prescription."]
    if renamed:
        chain.append(
            f"The patient's active medication '{existing}' resolves to the same "
            f"molecule ({inn})."
        )
        chain.append("The two are therefore the same active substance under different names.")
    else:
        chain.append(f"{_cap(inn)} is already on the patient's active medication list.")
    chain.append(
        "Dispensing both would double the daily dose without the patient realising it."
    )
    chain.append(f"Recommended handling is to {_ACTION_PHRASE[action]}.")

    return _make_alert(
        alert_id=f"DUP-{index:02d}",
        alert_type=TYPE_DUPLICATION,
        severity=MAJOR,
        title=(
            f"{_cap(same_as)} - already taken as '{existing}'" if renamed
            else f"{_cap(same_as)} - already on the active medication list"
        ),
        explanation=(
            f"Therapeutic duplication: '{existing}' is {inn}, the same molecule as the "
            f"newly prescribed {same_as}." if renamed else
            f"Therapeutic duplication: {inn} is already on the patient's active "
            f"medication list."
        ),
        reasoning_chain=chain,
        drugs_involved=[same_as, existing],
        evidence={"existing_name": existing, "resolved_inn": inn},
        action=action,
    )


def build_dose_alert(rec: dict, drug: str, dose_data: dict, index: int) -> dict:
    flag     = rec.get("flag", "")
    reason   = rec.get("reason", "")
    guidance = rec.get("guidance", "")
    prescribed = dose_data.get("prescribed_dose")
    standard   = dose_data.get("standard_dose")

    readable = {
        "elderly":            "the patient's age",
        "renal_impairment":   "reduced renal function",
        "hepatic_impairment": "reduced hepatic function",
    }.get(flag, flag.replace("_", " "))

    action = DISPENSE_WITH_NOTE

    chain = [
        f"{_cap(drug)} was prescribed"
        + (f" at {prescribed}." if prescribed else " without a stated dose."),
        f"This patient requires dose review because of {readable} ({reason}).",
    ]
    if standard:
        chain.append(f"Standard adult dose on record - {standard}.")
    if guidance:
        chain.append(f"Knowledge-base guidance for this population - {guidance}.")
    chain.append(
        "The knowledge base stores dose ranges as guidance text, so this is a prompt "
        "for pharmacist review, not a calculated dose."
    )
    chain.append(f"Recommended handling is to {_ACTION_PHRASE[action]}.")

    return _make_alert(
        alert_id=f"DOSE-{index:02d}",
        alert_type=TYPE_DOSE,
        severity=MODERATE,
        title=f"{_cap(drug)} - dose review needed ({readable})",
        explanation=(
            f"{_cap(drug)} may need dose adjustment for {readable}."
            + (f" Guidance: {guidance}" if guidance else "")
        ),
        reasoning_chain=chain,
        drugs_involved=[drug],
        evidence={
            "flag": flag, "reason": reason, "guidance": guidance,
            "prescribed_dose": prescribed, "standard_dose": standard,
        },
        action=action,
    )


def merge_pair_alerts(direct: dict, cyp: dict) -> dict:
    """
    Collapse two findings about the *same drug pair* into one alert.

    A pair can be flagged twice: once as a documented direct interaction and
    once as enzyme competition. Showing both is redundant noise at the counter
    and inflates alert counts, which is exactly what drives alert fatigue.

    The more severe finding leads; the other is folded in as a supporting line
    so no information is lost.
    """
    primary, secondary = (
        (direct, cyp) if direct["severity_rank"] <= cyp["severity_rank"] else (cyp, direct)
    )
    merged = dict(primary)
    chain = list(primary["reasoning_chain"])
    # Insert just before the closing recommendation sentence.
    chain.insert(max(len(chain) - 1, 0), f"Supporting finding - {secondary['explanation']}")
    merged["reasoning_chain"] = chain
    merged["evidence"] = {**secondary.get("evidence", {}), **primary.get("evidence", {})}
    merged["merged_from"] = sorted({direct["id"], cyp["id"]})
    return merged


# ── Report-level roll-up ──────────────────────────────────────────────────────

def sort_alerts(alerts: list[dict]) -> list[dict]:
    """Most dangerous finding first; stable within a severity band."""
    return sorted(alerts, key=lambda a: (a["severity_rank"], a["type"], a["id"]))


def overall_action(alerts: list[dict]) -> str:
    """The most cautious action any single finding demands."""
    if not alerts:
        return DISPENSE
    return min(
        (a["recommended_action"] for a in alerts),
        key=lambda action: ACTION_RANK.get(action, 99),
    )


def overall_risk(alerts: list[dict]) -> str:
    """HIGH / MEDIUM / LOW / NONE, driven by the most severe finding."""
    if not alerts:
        return "NONE"
    top = min(a["severity_rank"] for a in alerts)
    if top <= SEVERITY_RANK[MAJOR]:
        return "HIGH"
    if top == SEVERITY_RANK[MODERATE]:
        return "MEDIUM"
    return "LOW"


def severity_counts(alerts: list[dict]) -> dict:
    counts = {CONTRAINDICATED: 0, MAJOR: 0, MODERATE: 0, MINOR: 0}
    for alert in alerts:
        if alert["severity"] in counts:
            counts[alert["severity"]] += 1
    return counts
