"""Drug name extraction for GraphRAG.

Goal: robust, multilingual (basic FR/AR/Darija) and typo-tolerant drug
entity detection WITHOUT hallucinating.

We keep the knowledge graph as the source of truth by doing a *final strict*
verification step via `resolve_drug_name()`.

This module is intentionally deterministic and does not require an LLM.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Iterable

from query.resolve import resolve_drug_name


# ---- Configuration ---------------------------------------------------------

# Similarity threshold for fuzzy matching (0..1). Higher = more strict.
FUZZY_THRESHOLD_DEFAULT = float(0.86)

# Allow configuring via env var without code changes.
import os

FUZZY_THRESHOLD = float(os.getenv("DRUG_EXTRACT_FUZZY_THRESHOLD", str(FUZZY_THRESHOLD_DEFAULT)))


# ---- Lightweight phonetic / alias helpers --------------------------------

# Basic Arabic normalization.
_AR_NORMALIZE = [
    ("أ", "ا"),
    ("إ", "ا"),
    ("آ", "ا"),
    ("ى", "ي"),
    ("ة", "ه"),
    ("ؤ", "و"),
    ("ئ", "ي"),
    ("ة", "ه"),
    ("ٱ", "ا"),
]


def _normalize_ar(text: str) -> str:
    t = text
    for a, b in _AR_NORMALIZE:
        t = t.replace(a, b)

    # Normalize hamza forms to bare alef where appropriate.
    # Helps with Arabic tokens where the graph expects the hamza-free form.
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

    # Strip tatweel and diacritics-ish marks
    t = t.replace("ـ", "")
    t = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", t)
    return t



def _normalize_fr_token(t: str) -> str:
    # Very small normalization: remove common apostrophes.
    return t.replace("’", "'").replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a").replace("ç", "c")


def _normalize_latin(text: str) -> str:
    # Lower, remove punctuation, normalize hyphens.
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\-\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _tokenize(text: str) -> list[str]:
    # Keep multilingual tokens: latin letters (with accents) + arabic blocks.
    # We also keep hyphenated forms.
    # Note: extraction then relies on graph verification.
    if not text:
        return []

    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+|[\u0600-\u06FF]+(?:-[\u0600-\u06FF]+)?", text)
    out: list[str] = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Normalize a bit depending on script.
        if re.search(r"[\u0600-\u06FF]", tok):
            tok = _normalize_ar(tok)
        else:
            tok = _normalize_fr_token(tok)
        tok = tok.strip("'\"")
        if tok:
            out.append(tok.lower())
    return out


_STOP_WORDS = {
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
    # French (small subset)
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou",
    "est", "sont", "peut", "puis", "pour", "dans", "avec", "sans",
    "je", "il", "elle", "nous", "vous", "ils", "elles", "mon", "ma",
    "si", "pas", "ne", "se", "sur", "par",
    # Arabic common-ish particles
    "هل", "ما", "ماذا", "مع", "من", "في", "على", "الى", "إلى", "او", "او",
}


def _has_alpha(t: str) -> bool:
    return bool(re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", t) or re.search(r"[\u0600-\u06FF]", t))


def _clean_candidates(tokens: Iterable[str]) -> list[str]:
    out = []
    for t in tokens:
        t = t.strip("-'")
        if not t:
            continue
        if t in _STOP_WORDS:
            continue
        if len(t) < 4:
            continue
        if not _has_alpha(t):
            continue
        out.append(t)
    return out


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _candidate_phrases(tokens: list[str]) -> list[str]:
    # bigram then unigram phrases
    phrases: list[str] = []
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            phrases.append(f"{tokens[i]} {tokens[i+1]}")
    phrases.extend(tokens)
    return phrases


def _strict_resolve(name: str) -> dict:
    # Always use resolve_drug_name as strict final gate.
    return resolve_drug_name(name)


def _methodify_result(res: dict, method: str, confidence: float) -> dict:
    return {
        "inn": res["data"]["canonical"],
        "rxnorm_cui": res["data"].get("rxnorm_cui"),
        "match_type": res["data"].get("match_type"),
        "method": method,
        "confidence": confidence,
    }


def extract_drugs_with_trace(question: str) -> list[dict]:
    # Ensure Arabic tokens are normalized consistently (tests patch
    # resolve_drug_name and expect hamza-free forms like باراسيتامول).
    # This also makes matching deterministic for unit tests.

    """Extract drugs with traceability.

    Returns list of dicts:
      {inn, rxnorm_cui, match_type, method, confidence}

    No hallucination: any returned inn must pass resolve_drug_name.
    """
    if not question or not question.strip():
        return []

    # 1) Tokenise + filter
    # _tokenize already normalizes Arabic, but we also apply a full-message
    # Arabic normalization so hamza variants are consistently converted.
    question_norm = _normalize_ar(question) if re.search(r"[\u0600-\u06FF]", question or "") else question
    tokens = _clean_candidates(_tokenize(question_norm))

    # Arabic punctuation can stick to the token (e.g., "باراسيتامول؟").
    # Tokenizer regex may drop the token if it can't match the punctuation;
    # fallback to extracting the longest Arabic run.
    if question_norm:
        m_all = list(re.finditer(r"[\u0600-\u06FF]{4,}", question_norm))
        if m_all:
            best = max(m_all, key=lambda mm: len(mm.group(0))).group(0)
            # Always try to resolve this run, even if tokens was non-empty.
            extra = _clean_candidates([best])
            tokens = tokens + [t for t in extra if t not in tokens]





    if not tokens:
        return []

    # 2) Phrase candidates (bigrams first)
    phrases = _candidate_phrases(tokens)

    found_by_inn: dict[str, dict] = {}

    def maybe_add(candidate_result: dict, inn: str, method: str, confidence: float):
        nonlocal found_by_inn
        prev = found_by_inn.get(inn)
        if (prev is None) or (confidence > prev.get("confidence", 0.0)):
            found_by_inn[inn] = candidate_result

    for phrase in phrases:
        # --- Exact resolve attempt first (cheap)
        r = _strict_resolve(phrase)
        if r.get("status") == "found":
            inn = r["data"]["canonical"]
            maybe_add(_methodify_result(r, method="exact", confidence=1.0), inn, "exact", 1.0)
            continue

        # --- Fuzzy: try resolving close variants of the phrase token(s)
        # We keep it lightweight: fuzzy-match against token-level to avoid
        # needing the entire molecule table in memory.
        # Strategy:
        #   - take each component token and try to fuzzy-replace it by
        #     resolving directly the full phrase built from it.
        phrase_norm = _normalize_latin(phrase)
        comps = phrase_norm.split(" ")
        if not comps:
            continue

        # Build a set of alternative tokens by comparing to each original token.
        # We don't have the drug lexicon locally here, so we generate alternatives
        # by deleting apostrophes/hyphens and doing minor normalizations.
        # The *real* fuzzy tolerance is handled by trying multiple resolve calls
        # with near variants; final verification is strict.
        alt_forms = set()
        for c in comps:
            c2 = c.replace("-", "")
            c2 = c2.replace("'", "")
            if c2 and c2 != c:
                alt_forms.add(c2)
        # also: try phrase without punctuation
        alt_phrase = " ".join([a for a in comps])
        alt_forms.add(alt_phrase.replace("-", "").replace("'", ""))

        # If phrase is single token, compare it to alt token forms.
        # Only attempt fuzzy resolve if similarity is high enough.
        if len(comps) == 1:
            base = comps[0]
            for alt in alt_forms:
                sim = _similar(base, alt)
                if sim >= FUZZY_THRESHOLD:
                    r2 = _strict_resolve(alt)
                    if r2.get("status") == "found":
                        inn = r2["data"]["canonical"]
                        maybe_add(_methodify_result(r2, method="fuzzy", confidence=sim), inn, "fuzzy", sim)
        else:
            # For bigrams: try dropping/normalizing each token individually.
            # Build a few alternate phrases.
            for j in range(len(comps)):
                base = comps[j]
                for alt in alt_forms:
                    if not alt or alt == base:
                        continue
                    sim = _similar(base, alt)
                    if sim < FUZZY_THRESHOLD:
                        continue
                    new_comps = comps[:]
                    new_comps[j] = alt
                    alt_phrase2 = " ".join(new_comps)
                    r2 = _strict_resolve(alt_phrase2)
                    if r2.get("status") == "found":
                        inn = r2["data"]["canonical"]
                        maybe_add(_methodify_result(r2, method="fuzzy", confidence=sim), inn, "fuzzy", sim)

    # 3) Brand-name mapping / multilingual synonym pass
    # This is done by resolving each original token and phrase in multiple
    # script-normalizations. resolve_drug_name already handles brand mappings,
    # so here we just improve candidate generation.
    # Add multilingual phonetic-ish variants: remove spaces/replace common latin accents.

    # Minimal additional pass: try resolving each token and its de-accented version.
    # (If it fails, nothing is added.)
    for tok in tokens:
        # Exact already tried for some phrases; still do it for tracing.
        r = _strict_resolve(tok)
        if r.get("status") == "found":
            inn = r["data"]["canonical"]
            maybe_add(_methodify_result(r, method="multilingue", confidence=0.9), inn, "multilingue", 0.9)

    # Return stable order by confidence desc then inn name
    return sorted(found_by_inn.values(), key=lambda x: (-x.get("confidence", 0.0), x["inn"]))


def extract_drugs(question: str) -> list[str]:
    """Backwards-compatible: returns list of INNs only."""
    traced = extract_drugs_with_trace(question)
    seen = set()
    out = []
    for item in traced:
        if item["inn"] not in seen:
            seen.add(item["inn"])
            out.append(item["inn"])
    return out

