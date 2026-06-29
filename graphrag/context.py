"""
Context formatters: turn query-layer result dicts into structured plain-text
blocks the LLM can read without ambiguity.

Each formatter:
  - states explicitly what was checked (prevents the LLM from assuming)
  - labels missing data as "none found" (prevents hallucination)
  - keeps keys as recognisable to the system prompt (severity names verbatim)
"""


def fmt_interactions(result: dict) -> str:
    if result["status"] == "error":
        return f"=== PAIRWISE INTERACTIONS ===\nERROR: {result['message']}\n"

    data = result.get("data", {})
    interactions = data.get("interactions", [])
    pairs_checked = data.get("pairs_checked", 0)

    lines = ["=== PAIRWISE INTERACTIONS ==="]

    if not interactions:
        lines.append(
            f"Pairs checked: {pairs_checked}  |  "
            "Interactions found: 0\n"
            "No direct INTERACTS_WITH edge exists between any of these drugs."
        )
    else:
        for ix in interactions:
            lines.append(
                f"Pair: {ix['drug_a']} + {ix['drug_b']}\n"
                f"  severity: {ix['severity']}\n"
                f"  effect:   {ix.get('effect') or 'not specified'}\n"
                f"  mechanism:{ix.get('mechanism') or 'not specified'}\n"
                f"  source:   {ix.get('source') or 'not specified'}"
            )
        lines.append(
            f"\nPairs checked: {pairs_checked}  |  "
            f"Interactions found: {len(interactions)}"
        )

    if data.get("drugs_unresolved"):
        lines.append(
            f"Unresolved (not in knowledge base): "
            f"{', '.join(data['drugs_unresolved'])}"
        )

    return "\n".join(lines)


def fmt_cyp(result: dict) -> str:
    if result["status"] == "error":
        return f"=== CYP ENZYME COMPETITION ===\nERROR: {result['message']}\n"

    data = result.get("data", {})
    competitions = data.get("competitions", [])

    lines = ["=== CYP ENZYME COMPETITION ==="]

    if not competitions:
        lines.append(
            "Competitions found: 0\n"
            "No shared CYP substrate/inhibitor or substrate/inducer paths detected."
        )
    else:
        for c in competitions:
            lines.append(
                f"{c['substrate']} (substrate) + {c['modulator']} "
                f"({c['effect'].lower()}) via {c['enzyme']}\n"
                f"  strength: {c['strength']}\n"
                f"  risk:     {c['risk']}"
            )
        lines.append(f"\nCompetitions found: {len(competitions)}")

    return "\n".join(lines)


def fmt_contraindications(drug: str, result: dict) -> str:
    if result["status"] == "error":
        return (
            f"=== CONTRAINDICATIONS ({drug.upper()}) ===\n"
            f"ERROR: {result['message']}\n"
        )

    data = result.get("data", {})
    cis = data.get("contraindications", [])

    lines = [f"=== CONTRAINDICATIONS ({drug.upper()}) ==="]

    if not cis:
        lines.append("No contraindications found for the given conditions.")
    else:
        for ci in cis:
            lines.append(
                f"CONTRAINDICATED with: {ci['matched_concept']}"
                + (f" (ICD: {ci['icd_code']})" if ci.get("icd_code") else "")
                + f"\n  severity: {ci.get('severity', 'not specified')}"
                + f"\n  reason:   {ci.get('reason', 'not specified')}"
                + f"\n  source:   {ci.get('source', 'not specified')}"
            )
        lines.append(f"\nContraindications found: {len(cis)}")

    return "\n".join(lines)


def fmt_allergy(drug: str, result: dict) -> str:
    if result["status"] == "error":
        return f"=== ALLERGY CONFLICT ({drug.upper()}) ===\nERROR: {result['message']}\n"

    data = result.get("data", {})
    conflicts = data.get("conflicts", [])

    lines = [f"=== ALLERGY CONFLICT ({drug.upper()}) ==="]

    allergy_group = data.get("allergy_group")
    if allergy_group:
        lines.append(f"Drug allergy group: {allergy_group}")
    else:
        lines.append("Drug has no allergy group in knowledge base.")

    if not conflicts:
        lines.append("No allergy conflict detected.")
    else:
        for c in conflicts:
            conflict_type = "DIRECT CONFLICT" if c["type"] == "direct" else "CROSS-REACTIVITY"
            lines.append(
                f"{conflict_type}: patient allergic to '{c['patient_allergy']}'"
                f" | drug group: '{c['drug_group']}'"
            )
        lines.append(f"\nConflicts found: {len(conflicts)}")

    return "\n".join(lines)


def fmt_duplication(drug: str, result: dict) -> str:
    if result["status"] == "error":
        return f"=== THERAPEUTIC DUPLICATION ({drug.upper()}) ===\nERROR: {result['message']}\n"

    data = result.get("data", {})
    duplicates = data.get("duplicates", [])

    lines = [f"=== THERAPEUTIC DUPLICATION ({drug.upper()}) ==="]

    if not duplicates:
        lines.append("No therapeutic duplication detected.")
    else:
        for d in duplicates:
            lines.append(
                f"DUPLICATE: '{drug}' is the same drug as '{d['input_name']}' "
                f"already in active medications (both resolve to INN: {d['resolved_inn']})"
            )

    return "\n".join(lines)


def fmt_dose(drug: str, result: dict) -> str:
    if result["status"] == "error":
        return f"=== DOSE APPROPRIATENESS ({drug.upper()}) ===\nERROR: {result['message']}\n"

    data = result.get("data", {})
    recs = data.get("recommendations", [])

    lines = [f"=== DOSE APPROPRIATENESS ({drug.upper()}) ==="]

    if data.get("standard_dose"):
        lines.append(f"Standard adult dose: {data['standard_dose']}")
    if data.get("prescribed_dose"):
        lines.append(f"Prescribed dose:     {data['prescribed_dose']}")

    if not recs:
        lines.append("No dose adjustment flags.")
    else:
        for r in recs:
            lines.append(
                f"FLAG [{r['flag'].upper()}]: {r['reason']}\n"
                f"  Guidance: {r['guidance']}"
            )

    return "\n".join(lines)
