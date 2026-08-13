"""
Stable identity for a clinical finding, across scans.

Alert ids (``INT-01``, ``CYP-02``) are positional — they change from run to run
and cannot be used to recognise "the pharmacist already reviewed this". A
fingerprint is derived from the *clinical content* instead, so the same finding
produces the same key every time:

    ddi:clarithromycin|simvastatin
    ci:metformin|chronic kidney disease
    alg:amoxicillin|penicillin
    dup:atorvastatin
    dose:ciprofloxacin|renal_impairment

Two properties matter:

* **Order-free** — ``warfarin + aspirin`` and ``aspirin + warfarin`` are one
  finding, and which drug is "new" this time is irrelevant.
* **Merge-stable** — a direct interaction and CYP competition about the same
  pair share the ``ddi:`` prefix. The reactive engine merges those into one
  alert, and which of the two leads depends on their relative severity, so
  keying on the alert's type would make the identity flip between scans.
"""
from __future__ import annotations

PREFIX_DDI     = "ddi"
PREFIX_CI      = "ci"
PREFIX_ALLERGY = "alg"
PREFIX_DUP     = "dup"
PREFIX_DOSE    = "dose"
PREFIX_UNKNOWN = "unk"


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _pair(drugs: list[str] | None) -> str:
    return "|".join(sorted(_norm(d) for d in (drugs or []) if _norm(d)))


def fingerprint(alert: dict) -> str:
    """
    Return the stable identity for *alert*.

    Unrecognised alert types fall back to ``<type>:<sorted drugs>``, which is
    still order-free and still stable — an unknown finding type is remembered
    rather than silently un-rememberable.
    """
    alert_type = _norm(alert.get("type"))
    drugs = alert.get("drugs_involved") or []
    evidence = alert.get("evidence") or {}

    if alert_type in ("interaction", "cyp_competition"):
        return f"{PREFIX_DDI}:{_pair(drugs)}"

    if alert_type == "contraindication":
        # Prefer the matched concept: the pharmacist may type "CKD stage 4" one
        # day and "chronic kidney disease" the next, but the graph resolves both
        # to the same concept.
        condition = (
            _norm(evidence.get("matched_concept"))
            or _norm(evidence.get("icd_code"))
            or _norm(evidence.get("condition"))
        )
        return f"{PREFIX_CI}:{_pair(drugs)}|{condition}"

    if alert_type == "allergy":
        allergy = _norm(evidence.get("patient_allergy")) or _norm(evidence.get("drug_group"))
        return f"{PREFIX_ALLERGY}:{_pair(drugs)}|{allergy}"

    if alert_type == "duplication":
        # The duplicated molecule is the finding; the brand name it arrived
        # under is incidental.
        inn = _norm(evidence.get("resolved_inn")) or _pair(drugs)
        return f"{PREFIX_DUP}:{inn}"

    if alert_type == "dose":
        return f"{PREFIX_DOSE}:{_pair(drugs)}|{_norm(evidence.get('flag'))}"

    if alert_type == "unknown_drug":
        return f"{PREFIX_UNKNOWN}:{_norm(evidence.get('input_name')) or _pair(drugs)}"

    return f"{alert_type}:{_pair(drugs)}"
