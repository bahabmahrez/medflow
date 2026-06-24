# MedFlow — Knowledge Graph Schema

> One-line justification per table. The full column definitions live in `db/migrations/001_schema.sql`.

---

## Core Drug Entities

### `molecules`
Canonical drug entity keyed on INN (International Nonproprietary Name). All interaction logic lives at the molecule level so every brand-name variant inherits it automatically. Stores RxNorm CUI, DrugBank ID, ChEMBL ID, and molecular class.

### `drugs`
Market instances of a molecule — brand names (Tunisian, French, international), ATC code, dosage form, and dosing guidance for adult, elderly, renal-impaired, and hepatically-impaired patients. Many drugs can point to the same molecule.

---

## Interaction Layer

### `drug_interactions`
Pairwise pharmacokinetic and pharmacodynamic interaction edges between molecules (not drugs). Stores severity separately from ANSM Thesaurus (`severity_ansm`) and DrugBank/OpenFDA (`severity_drugbank`); `severity_active` always holds the more conservative value. Carries `clinical_effect`, `management`, and `mechanism_type` for LLM-readable output.

### `cyp_relationships`
CYP450 enzyme edges per molecule: each row records whether a molecule is a SUBSTRATE, INHIBITOR, or INDUCER of a specific CYP enzyme, plus strength (strong/moderate/weak). Enables indirect interaction detection when two drugs share a CYP enzyme without a direct `drug_interactions` entry (e.g. omeprazole + clopidogrel via CYP2C19).

### `class_interactions`
Interaction edges between drug classes rather than individual molecules. Catches risks for drugs not individually encoded — e.g. any NSAID vs. any anticoagulant — and provides a severity and mechanism readable by the engine.

---

## Drug Classification

### `drug_classes`
ATC classification nodes, one row per pharmacological class (e.g. "Nonsteroidal Anti-Inflammatory Drug", "Vitamin K Antagonist"). Used as the basis for class-level interaction rules.

### `drug_class_members`
Many-to-many junction: which molecules belong to which drug class. A molecule can belong to multiple classes (e.g. aspirin is both an NSAID and a Platelet Aggregation Inhibitor).

---

## Contraindications

### `contraindications`
Links a molecule to a disease concept where its use is restricted. Severity distinguishes absolute contraindication from dose adjustment or monitoring requirements. Critical for Trap 2 (metformin + CKD) and Trap 6 (ciprofloxacin + renal impairment).

### `disease_concepts`
Canonical disease entities with ICD-11 and SNOMED-CT codes. Shared reference table for `contraindications`, `conditions`, and `treats` — all disease links point here so concept identity is consistent across tables.

---

## Allergy System

### `allergy_groups`
Allergy categories for cross-reactivity detection (e.g. Penicillins, Cephalosporins, NSAIDs). Separates the structural class concept from individual drug instances.

### `allergy_cross_reactivities`
Cross-reactivity edges between allergy groups with a documented rate. Powers Trap 4: patient allergic to penicillin → warn on cephalosporins because the cross-reactivity edge exists here.

### `drug_allergy_groups`
Links a drug (brand instance) to its allergy group. Queried on every prescription scan against the patient's `allergies` table.

---

## Pharmacology Detail

### `adverse_effects`
Real-world side effects per molecule sourced from OpenFDA pharmacovigilance data. Carries MedDRA term, frequency category (common/uncommon/rare), and severity (moderate/severe/life_threatening). Used for risk-benefit context in LLM explanations.

### `molecular_targets`
Protein or receptor targets (UniProt ID, target name). Two drugs sharing the same molecular target may have additive or antagonistic effects even without a `drug_interactions` row — the engine can surface this as a pharmacodynamic flag.

### `molecule_molecular_targets`
Many-to-many: which molecules act on which targets, with action type (agonist, antagonist, inhibitor, substrate). The bridge between molecule identity and pharmacodynamic reasoning.

### `treats`
Indication edges: what each molecule is indicated for, linked to `disease_concepts`. The reasoning layer needs to know what a drug treats to detect therapeutic duplication or indication mismatch, not just what it interacts with.

---

## Patient Records

### `patients`
Clinical patient records with demographics (age, sex, weight), renal/hepatic status flags, and `is_trap` tagging for the 8 synthetic trap scenarios. The central node for every prescription scan.

### `conditions`
Patient-specific condition instances linking a patient to a canonical `disease_concepts` entry, with onset date and status (active/resolved). Queried to evaluate contraindications against current diagnoses.

### `active_medications`
What a patient is currently prescribed — molecule, brand, dose, and start date. Queried on every incoming prescription to detect drug–drug interactions and therapeutic duplication.

### `allergies`
Patient allergy records linked to `allergy_groups`. Every new prescription is checked against this table via `drug_allergy_groups` to surface cross-reactivity warnings.

### `lab_results`
Biomarker values (creatinine, INR, ALT, AST, HbA1c, eGFR) with reference ranges and collection date. Used for contraindication checks that depend on patient physiology rather than just diagnosis codes — e.g. eGFR < 30 triggers metformin contraindication independent of whether CKD is explicitly recorded.

### `prescription_history`
Archived prescription records for compliance monitoring and duplication detection across time. Distinguishes a new prescription from a continuing one.

### `refill_records`
Expected vs. actual refill dates per prescription. Used for proactive adherence monitoring — a refill significantly later than expected may indicate the patient stopped the medication.

---

## Severity Scale Reference

| ANSM label | Meaning | Typical action |
|---|---|---|
| `contre_indique` | Absolute contraindication | Refuse dispensing, alert prescriber |
| `deconseillee` | Strongly discouraged | Alert prescriber, suggest alternative |
| `precaution_emploi` | Use with caution | Monitoring required, dose may need adjustment |
| `a_prendre_en_compte` | Be aware | Inform patient, no dose change needed |
| `contraindicated` | Used for disease contraindications | Same as contre_indique |
| `dose_adjustment` | Renal/hepatic dose modification required | Apply dose table from `drugs` |
| `monitoring` | Lab monitoring required | Schedule follow-up |

---

*Schema version: Week 2. Next structural change expected in Week 4 (engine integration).*
*Full column definitions: `db/migrations/001_schema.sql`*
