"""
Extract structured drug-drug interaction pairs from the FDA label text data.

Input:  knowledge_base/sources/dataset/interactions_enriched.csv
        (one row per drug, Texte_Interaction = free-text FDA label section)

Output: knowledge_base/sources/dataset/interactions_priority_50.csv
        (one row per extracted pair: inn_a, inn_b, severity_inferred, extracted_text)

Strategy:
  For each row whose inn_name_clean matches one of the 50 priority drugs (drug A),
  scan Texte_Interaction for mentions of other priority drugs (drug B).
  Extract the sentence(s) containing the mention and infer severity from keywords.
"""

import csv
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV  = os.path.join(BASE_DIR, "../sources/dataset/interactions_enriched.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "../sources/dataset/interactions_priority_50.csv")

# ── 50 priority INNs ──────────────────────────────────────────────────────────

PRIORITY_DRUGS = [
    "warfarin", "heparin", "aspirin", "clopidogrel",
    "metformin", "glibenclamide", "insulin glargine",
    "enalapril", "ramipril", "amlodipine", "furosemide",
    "spironolactone", "digoxin", "atorvastatin", "simvastatin",
    "ibuprofen", "diclofenac", "naproxen", "prednisolone",
    "amoxicillin", "ciprofloxacin", "metronidazole",
    "clarithromycin", "fluconazole",
    "carbamazepine", "valproate", "fluoxetine", "sertraline",
    "omeprazole", "tramadol",
    "lithium", "haloperidol", "risperidone",
    "methotrexate", "azathioprine", "tacrolimus", "cyclosporine",
    "rifampicin", "isoniazid", "phenobarbital",
    "levodopa", "amiodarone", "verapamil", "diltiazem",
    "losartan", "allopurinol", "colchicine",
    "levothyroxine", "ethinylestradiol", "sildenafil",
]

# Alternate spellings / brand fragments that appear in FDA label text
# Maps search term → canonical INN
ALIASES = {
    "warfarin": "warfarin",
    "coumarin": "warfarin",
    "heparin": "heparin",
    "aspirin": "aspirin",
    "acetylsalicylic": "aspirin",
    "clopidogrel": "clopidogrel",
    "plavix": "clopidogrel",
    "metformin": "metformin",
    "glibenclamide": "glibenclamide",
    "glyburide": "glibenclamide",
    "insulin glargine": "insulin glargine",
    "enalapril": "enalapril",
    "ramipril": "ramipril",
    "amlodipine": "amlodipine",
    "furosemide": "furosemide",
    "frusemide": "furosemide",
    "spironolactone": "spironolactone",
    "digoxin": "digoxin",
    "atorvastatin": "atorvastatin",
    "simvastatin": "simvastatin",
    "ibuprofen": "ibuprofen",
    "diclofenac": "diclofenac",
    "naproxen": "naproxen",
    "prednisolone": "prednisolone",
    "prednisone": "prednisolone",
    "amoxicillin": "amoxicillin",
    "amoxycillin": "amoxicillin",
    "ciprofloxacin": "ciprofloxacin",
    "metronidazole": "metronidazole",
    "clarithromycin": "clarithromycin",
    "fluconazole": "fluconazole",
    "carbamazepine": "carbamazepine",
    "valproate": "valproate",
    "valproic": "valproate",
    "divalproex": "valproate",
    "fluoxetine": "fluoxetine",
    "sertraline": "sertraline",
    "omeprazole": "omeprazole",
    "tramadol": "tramadol",
    "lithium": "lithium",
    "haloperidol": "haloperidol",
    "risperidone": "risperidone",
    "methotrexate": "methotrexate",
    "azathioprine": "azathioprine",
    "tacrolimus": "tacrolimus",
    "cyclosporine": "cyclosporine",
    "ciclosporin": "cyclosporine",
    "cyclosporin": "cyclosporine",
    "rifampicin": "rifampicin",
    "rifampin": "rifampicin",
    "isoniazid": "isoniazid",
    "phenobarbital": "phenobarbital",
    "phenobarbitone": "phenobarbital",
    "levodopa": "levodopa",
    "amiodarone": "amiodarone",
    "verapamil": "verapamil",
    "diltiazem": "diltiazem",
    "losartan": "losartan",
    "allopurinol": "allopurinol",
    "colchicine": "colchicine",
    "levothyroxine": "levothyroxine",
    "thyroxine": "levothyroxine",
    "ethinylestradiol": "ethinylestradiol",
    "ethinyl estradiol": "ethinylestradiol",
    "sildenafil": "sildenafil",
}

# Severity inference: keyword → severity label (checked in order, first match wins)
SEVERITY_RULES = [
    # Strongest signals first
    (r"\bcontraindicated\b",                                   "contre_indique"),
    (r"\bdo not (use|administer|give|co-?administer)\b",       "contre_indique"),
    (r"\bfatal\b|\bdeath\b|\blife.?threatening\b",             "contre_indique"),
    (r"\bavoid (concomitant|concurrent|combination|use)\b",    "deconseillee"),
    (r"\bshould (not|never) be (used|given|combined)\b",       "deconseillee"),
    (r"\bserious\b|\bsevere\b|\bmajor\b",                      "deconseillee"),
    (r"\bsignificant(ly)?\b|\bsubstantial(ly)?\b",             "precaution_emploi"),
    (r"\bmonitor\b|\bclose(ly)?\b|\bcaution\b|\badjust\b",     "precaution_emploi"),
    (r"\bmay (increase|decrease|affect|alter|change)\b",       "a_prendre_en_compte"),
    (r"\bcan (increase|decrease|affect|alter|change)\b",       "a_prendre_en_compte"),
    (r"\binteraction\b",                                       "a_prendre_en_compte"),
]


def infer_severity(text: str) -> str:
    text_lower = text.lower()
    for pattern, severity in SEVERITY_RULES:
        if re.search(pattern, text_lower):
            return severity
    return "a_prendre_en_compte"


def extract_sentences_containing(text: str, term: str) -> str:
    """Return up to 2 sentences from text that contain term."""
    # Split on sentence boundaries (., !, ?)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    hits = [s.strip() for s in sentences if term.lower() in s.lower()]
    return " ".join(hits[:2])


def normalize_inn(raw: str) -> str | None:
    """Map a raw drug name from the CSV to a canonical INN, or None if not a priority drug."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    # Direct match first
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    # Prefix match
    for alias, inn in ALIASES.items():
        if cleaned.startswith(alias) or alias.startswith(cleaned):
            return inn
    return None


def find_drug_mentions(text: str) -> list[tuple[str, str]]:
    """Return (canonical_inn, extracted_context) for every priority drug mentioned in text."""
    results = []
    text_lower = text.lower()
    seen_inns = set()

    for alias, inn in ALIASES.items():
        if inn in seen_inns:
            continue
        # Word-boundary search for the alias
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, text_lower):
            context = extract_sentences_containing(text, alias)
            results.append((inn, context))
            seen_inns.add(inn)

    return results


# ── Main extraction loop ──────────────────────────────────────────────────────

print(f"Reading: {INPUT_CSV}")

rows_read = 0
rows_matched_drug_a = 0
pairs_extracted = 0
pairs_written = 0

# Track unique pairs to avoid duplicates (both orderings map to the same canonical pair)
seen_pairs: set[tuple[str, str]] = set()

with open(INPUT_CSV, newline="", encoding="utf-8", errors="replace") as fin, \
     open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fout:

    reader = csv.DictReader(fin)
    writer = csv.DictWriter(fout, fieldnames=[
        "inn_a", "inn_b", "severity_inferred", "extracted_text", "source"
    ])
    writer.writeheader()

    for row in reader:
        rows_read += 1
        if rows_read % 50000 == 0:
            print(f"  {rows_read:,} rows read, {pairs_written} pairs written so far...")

        # Identify drug A from this row
        raw_inn = row.get("inn_name_clean", "") or row.get("Nom_Generique", "")
        inn_a = normalize_inn(raw_inn)
        if not inn_a:
            continue

        rows_matched_drug_a += 1
        text = row.get("Texte_Interaction", "")
        if not text or len(text) < 20:
            continue

        # Find all priority drug mentions in the interaction text
        mentions = find_drug_mentions(text)
        for inn_b, context in mentions:
            if inn_b == inn_a:
                continue  # skip self-mentions

            pairs_extracted += 1

            # Deduplicate: store pair in sorted order
            pair_key = tuple(sorted([inn_a, inn_b]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            severity = infer_severity(context)
            writer.writerow({
                "inn_a":             inn_a,
                "inn_b":             inn_b,
                "severity_inferred": severity,
                "extracted_text":    context[:500],  # cap at 500 chars
                "source":            "openfda_label",
            })
            pairs_written += 1

print(f"\nDone.")
print(f"  Rows read:            {rows_read:,}")
print(f"  Rows matching drug A: {rows_matched_drug_a:,}")
print(f"  Raw pair mentions:    {pairs_extracted:,}")
print(f"  Unique pairs written: {pairs_written}")
print(f"  Output:               {OUTPUT_CSV}")
