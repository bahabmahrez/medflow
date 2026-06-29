"""
GraphRAG pipeline.

  extract_drugs(text)  — detect drug names in free text via graph resolution
  ask(question, ...)   — full Retrieve → Augment → Generate pipeline
"""
import re

from query import (
    resolve_drug_name,
    detect_pairwise_interactions,
    detect_cyp_competition,
    check_contraindications,
    check_allergy_conflict,
    check_therapeutic_duplication,
    check_dose_appropriateness,
)
from llm import generate, load_system_prompt
from .context import (
    fmt_interactions,
    fmt_cyp,
    fmt_contraindications,
    fmt_allergy,
    fmt_duplication,
    fmt_dose,
)

# ── System prompt (loaded once) ────────────────────────────────────────────────

_SYSTEM_PROMPT: str | None = None


def _system() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = load_system_prompt()
    return _SYSTEM_PROMPT


# ── Stop words filtered from drug extraction ──────────────────────────────────
# Short, common, non-drug tokens that would waste graph round-trips.
_STOP = {
    # English
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were",
    "be", "been", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "for", "of", "in", "on", "at", "by", "with", "from", "into",
    "i", "we", "you", "he", "she", "they", "it", "this", "that", "these",
    "those", "my", "your", "his", "her", "our", "their", "its",
    "what", "which", "who", "whom", "when", "where", "why", "how",
    "give", "take", "use", "prescribe", "administer",
    "patient", "drug", "medication", "medicine",
    "safe", "safely", "already", "taking", "given", "prescribed",
    "combination", "together", "combine", "interact", "interaction",
    "contraindicated", "prescription", "please", "tell", "about",
    "if", "not", "no", "yes", "then", "also", "just",
    # French
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou",
    "est", "sont", "peut", "puis", "pour", "dans", "avec", "sans",
    "je", "il", "elle", "nous", "vous", "ils", "elles", "mon", "ma",
    "si", "pas", "ne", "se", "sur", "par",
}


def extract_drugs(text: str) -> list[str]:
    """
    Identify drug names in free text by resolving candidate tokens against
    the knowledge graph.  Returns unique INNs in order of appearance.

    Strategy: tokenise → filter stop words → try bigrams then unigrams.
    Only resolved names (status='found') are kept.  The graph is the filter.
    """
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z]+(?:-[a-zA-Z]+)*", text)]
    filtered = [t for t in tokens if t not in _STOP and len(t) >= 4]

    seen: set[str] = set()
    drugs: list[str] = []

    def _add(inn: str) -> None:
        if inn not in seen:
            seen.add(inn)
            drugs.append(inn)

    # Bigrams first — catch two-word brand names
    for i in range(len(filtered) - 1):
        phrase = f"{filtered[i]} {filtered[i + 1]}"
        r = resolve_drug_name(phrase)
        if r["status"] == "found":
            _add(r["data"]["canonical"])

    # Unigrams
    for token in filtered:
        r = resolve_drug_name(token)
        if r["status"] == "found":
            _add(r["data"]["canonical"])

    return drugs


# ── Severity → risk mapping ────────────────────────────────────────────────────

_SEV_RISK = {
    "contre_indique": "HIGH",
    "major":          "HIGH",
    "deconseillee":   "HIGH",
    "moderate":       "MEDIUM",
    "precaution_emploi":   "MEDIUM",
    "a_prendre_en_compte": "LOW",
}

_RISK_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _worst_risk(interactions: list[dict]) -> str | None:
    """Return the highest risk level across a list of interaction dicts."""
    best = None
    for ix in interactions:
        r = _SEV_RISK.get(ix.get("severity", ""))
        if r and (best is None or _RISK_RANK[r] > _RISK_RANK[best]):
            best = r
    return best


# ── Main pipeline ──────────────────────────────────────────────────────────────

def ask(
    question: str,
    *,
    conditions:  list[str] | None = None,
    allergies:   list[str] | None = None,
    active_meds: list[str] | None = None,
    age:    int   | None = None,
    weight: float | None = None,
    labs:   dict  | None = None,
) -> dict:
    """
    Full GraphRAG pipeline:
      1. Extract drug names from the question via graph resolution
      2. Run all relevant query-layer functions (interactions, CYP, safety)
      3. Format results as a structured context block
      4. Generate an LLM answer grounded in — and bounded by — that context

    Returns:
        {
            "answer":         str,   — LLM-generated explanation
            "drugs_detected": list,  — INNs found in the question
            "context":        str,   — raw context passed to the LLM
            "risk_level":     str|None  — HIGH / MEDIUM / LOW / None
        }
    """
    if not question or not question.strip():
        return {
            "answer":         "Please provide a question.",
            "drugs_detected": [],
            "context":        "",
            "risk_level":     None,
        }

    # ── 1. Extract drugs ───────────────────────────────────────────────────────
    try:
        drugs = extract_drugs(question)
    except Exception as exc:
        return {
            "answer":         f"Knowledge base unreachable: {exc}",
            "drugs_detected": [],
            "context":        "",
            "risk_level":     None,
            "error":          str(exc),
        }

    if not drugs:
        context = (
            "Drug extraction: No known drug names were detected in the question.\n"
            "The question cannot be answered from the knowledge base."
        )
        answer = generate(_system(), question, context=context)
        return {
            "answer":         answer,
            "drugs_detected": [],
            "context":        context,
            "risk_level":     None,
        }

    # ── 2. Run graph queries ───────────────────────────────────────────────────
    parts = [f"Drugs detected: {', '.join(drugs)}"]
    risk_level: str | None = None

    if len(drugs) >= 2:
        ix_result  = detect_pairwise_interactions(drugs)
        cyp_result = detect_cyp_competition(drugs)
        parts.append(fmt_interactions(ix_result))
        parts.append(fmt_cyp(cyp_result))

        if ix_result["status"] == "found":
            wr = _worst_risk(ix_result["data"].get("interactions", []))
            if wr and (risk_level is None or _RISK_RANK[wr] > _RISK_RANK.get(risk_level, 0)):
                risk_level = wr

        if cyp_result["status"] == "found":
            # CYP competitions with strong inhibition are HIGH risk
            for c in cyp_result["data"].get("competitions", []):
                if c.get("strength") in ("strong", "moderate") and c.get("effect") == "INHIBITS":
                    r = "HIGH" if c["strength"] == "strong" else "MEDIUM"
                    if risk_level is None or _RISK_RANK[r] > _RISK_RANK.get(risk_level, 0):
                        risk_level = r

    if conditions:
        for drug in drugs:
            r = check_contraindications(drug, conditions)
            parts.append(fmt_contraindications(drug, r))
            if r["status"] == "found":
                risk_level = "HIGH"

    if allergies:
        for drug in drugs:
            r = check_allergy_conflict(drug, allergies)
            parts.append(fmt_allergy(drug, r))
            if r["status"] == "found" and r["data"].get("conflicts"):
                risk_level = "HIGH"

    if active_meds:
        for drug in drugs:
            r = check_therapeutic_duplication(drug, active_meds)
            parts.append(fmt_duplication(drug, r))

    if age is not None or weight is not None or labs:
        for drug in drugs:
            r = check_dose_appropriateness(
                drug, dose=None, age=age, weight=weight, labs=labs or {}
            )
            parts.append(fmt_dose(drug, r))

    context = "\n\n".join(parts)

    # ── 3. Generate answer ─────────────────────────────────────────────────────
    try:
        answer = generate(_system(), question, context=context)
    except Exception as exc:
        return {
            "answer":         f"LLM service unavailable: {exc}",
            "drugs_detected": drugs,
            "context":        context,
            "risk_level":     risk_level,
            "error":          str(exc),
        }

    return {
        "answer":         answer,
        "drugs_detected": drugs,
        "context":        context,
        "risk_level":     risk_level,
    }
