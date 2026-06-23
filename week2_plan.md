# MedFlow — Week 2 Execution Plan
> **Theme:** Build a Strong, Complete Drug Knowledge Graph  
> **Stakes:** Everything built in Weeks 3–7 (engine, chatbot, agent) runs on top of what gets built this week. A weak knowledge graph produces a weak agent no matter how good the code is.

---

## Honest State of the Repo Entering Week 2

| Area | Status | Notes |
|---|---|---|
| Database schema | Done | All 19 tables present in `db/migrations/001_schema.sql` |
| Docker / PostgreSQL | Ready | `docker compose up -d` — never confirmed running with data |
| Molecules (50 drugs) | Ready to load | `load_rxnorm_chembl.py` has all 50 INNs listed |
| Drug interactions | **Critical gap** | Only **17 pairs** in `ansm_interactions_all.csv` — need 100+ |
| CYP relationships | Partial | `chembl_drug_data.csv` covers 30 drugs, no strength column |
| Contraindications | Ready to load | `load_drugs_contraindications.py` covers 12 molecule-disease pairs |
| Drug classes (ATC) | **Not built** | No `load_drug_classes.py` exists |
| Adverse effects | **Not built** | No `load_adverse_effects.py` exists |
| Molecular targets | **Not built** | No `load_molecular_targets.py` exists |
| Synthetic patients | Ready to load | `load_patients.py` complete, never run |
| Trap verifications | Blocked | DB is empty — nothing to verify |
| Stress tests | Not written | `/evaluation/stress_tests/` is empty |
| Documentation | Partial | `/docs/graph_schema.md` missing, `/docs/severity_disagreements.md` missing |

**The single most critical gap:** 17 interaction pairs is clinically worthless. An engine querying 50 drugs needs at minimum the full interaction matrix for every high-risk pair. This is the Week 2 priority above all else.

---

## Week 2 Milestones

### Milestone 1 — Get the DB Populated (Day 1, blocking everything)

Nothing can be verified until the database has real data. This must be the first thing done on Day 1.

**Step-by-step commands:**

```bash
# 1. Start the database
cd ~/medflow && docker compose up -d

# 2. Apply schema (only needed on first run or after a reset)
docker exec -i medflow-db-1 psql -U medflow -d medflow < db/migrations/001_schema.sql

# 3. Load all 50 molecules + RxNorm CUIs + ChEMBL IDs
python knowledge_base/DB_loaders/load_rxnorm_chembl.py

# 4. Load CYP relationships
python knowledge_base/DB_loaders/load_cyp.py

# 5. Load drug brand names + contraindications + allergy groups
python knowledge_base/DB_loaders/load_drugs_contraindications.py

# 6. Load Tunisian brand name mappings from PCT catalog
python knowledge_base/DB_loaders/load_pct_brands.py

# 7. Load ANSM interaction pairs (17 pairs currently — expands in Milestone 2)
python knowledge_base/DB_loaders/load_ansm_interactions.py

# 8. Insert 30 synthetic patients (8 trap + 22 regular)
python patients/synthetic/load_patients.py

# 9. Verify baseline
python evaluation/e2e_test.py
```

**Verify it worked:**
```sql
SELECT COUNT(*) FROM molecules;         -- must be 50
SELECT COUNT(*) FROM drugs;             -- must be 30+
SELECT COUNT(*) FROM drug_interactions; -- will be 17 at this point, expands later
SELECT COUNT(*) FROM patients;          -- must be 30
SELECT COUNT(*) FROM patients WHERE is_trap = true; -- must be 8
```

**Owner:** Whoever has Docker running locally. One person, ~2 hours. Unblocks the entire team.

---

### Milestone 2 — Expand Drug Interaction Data (Days 1–2, most critical work)

This is where Week 2 succeeds or fails.

#### The approach

You already have 233MB of FDA interaction data on disk at:
`knowledge_base/sources/dataset/toutes_les_interactions_fda.csv`

And a 96MB enriched version with ATC codes:
`knowledge_base/sources/dataset/interactions_enriched.csv`

**Step 1 — Write `extract_priority_interactions.py`**

This script filters the large FDA dataset to only pairs where both drugs are in the 50-drug list, maps names to canonical INNs, and outputs a clean CSV ready for loading.

```
File to create: knowledge_base/loaders/extract_priority_interactions.py

Input:  knowledge_base/sources/dataset/interactions_enriched.csv
Output: knowledge_base/sources/dataset/interactions_priority_50.csv

Logic:
  - Load all 50 canonical INNs
  - Build a name→INN lookup map (covering synonyms, brand names, alternate spellings)
  - For each row in interactions_enriched.csv:
      - Try to map both drug names to canonical INNs
      - If both resolve → write to output with: inn_a, inn_b, severity_openfda, clinical_effect, mechanism
  - Log: how many rows processed, how many pairs extracted, how many failed to resolve
```

**Step 2 — Update `load_ansm_interactions.py` to also load the new file**

Or write a new loader `load_priority_interactions.py` that:
- Reads `interactions_priority_50.csv`
- For each pair, calls `get_or_create_molecule()` (already implemented in the ANSM loader)
- Inserts into `drug_interactions` with `severity_active = severity_openfda`, `source_confidence = 'openfda'`
- Does NOT overwrite existing rows that already have ANSM data (use `ON CONFLICT DO NOTHING` then update only if ANSM fields are null)

**Step 3 — Manually encode ANSM severity for all critical pairs**

After the FDA extraction, go through every high-risk pair and add the ANSM severity column to `ansm_interactions_all.csv`. The ANSM Thesaurus is the clinical reference — use it.

**Mandatory pairs that MUST be in the database before Week 2 ends:**

| Pair | ANSM Severity | Mechanism | Clinical Effect |
|---|---|---|---|
| warfarin + amiodarone | contre_indique | CYP2C9 inhibition by amiodarone | Dramatic warfarin accumulation → life-threatening bleeding |
| warfarin + aspirin | deconseillee | Additive anticoagulant + gastric damage | Major hemorrhage risk |
| warfarin + fluconazole | deconseillee | CYP2C9 inhibition | Warfarin accumulation |
| warfarin + carbamazepine | precaution_emploi | CYP induction → reduced warfarin effect | Thrombotic risk |
| warfarin + rifampicin | contre_indique | Potent CYP3A4/2C9 induction | Complete loss of anticoagulant effect |
| simvastatin + clarithromycin | contre_indique | CYP3A4 inhibition | Rhabdomyolysis |
| tacrolimus + fluconazole | contre_indique | CYP3A4 inhibition | Tacrolimus toxicity (nephrotoxicity, neurotoxicity) |
| methotrexate + ibuprofen | deconseillee | Reduced renal MTX clearance | Methotrexate toxicity (pancytopenia) |
| allopurinol + azathioprine | contre_indique | Xanthine oxidase inhibition → azathioprine accumulation | Severe myelosuppression |
| fluoxetine + tramadol | deconseillee | Serotonin syndrome + CYP2D6 inhibition | Serotonin syndrome, seizures |
| carbamazepine + clarithromycin | contre_indique | CYP3A4 inhibition | Carbamazepine toxicity |
| digoxin + clarithromycin | precaution_emploi | P-gp inhibition → increased digoxin absorption | Digoxin toxicity |
| enalapril + spironolactone | precaution_emploi | Additive K-sparing | Hyperkalemia |
| clopidogrel + omeprazole | a_prendre_en_compte | CYP2C19 inhibition → reduced clopidogrel activation | Reduced antiplatelet effect |
| lithium + ibuprofen | contre_indique | NSAID reduces renal lithium clearance | Lithium toxicity |
| lithium + diclofenac | contre_indique | Same mechanism | Lithium toxicity |
| cyclosporine + clarithromycin | contre_indique | CYP3A4 inhibition | Cyclosporine toxicity |
| cyclosporine + rifampicin | contre_indique | CYP3A4 induction | Transplant rejection |
| methotrexate + naproxen | deconseillee | Same mechanism as MTX + ibuprofen | Methotrexate toxicity |
| phenobarbital + warfarin | precaution_emploi | CYP induction | Reduced warfarin effect |
| amiodarone + simvastatin | deconseillee | CYP3A4 inhibition | Myopathy risk |
| valproate + carbamazepine | precaution_emploi | Complex pharmacokinetic interaction | Variable effects on both drug levels |
| isoniazid + carbamazepine | precaution_emploi | CYP3A4 inhibition | Carbamazepine toxicity |

**Owner:** 2 people in parallel.
- Person A: writes `extract_priority_interactions.py` and runs it
- Person B: manually adds ANSM severity to `ansm_interactions_all.csv` for all critical pairs using the ANSM Thesaurus PDF

**Target:** `SELECT COUNT(*) FROM drug_interactions` returns ≥ 100 by end of Day 2.

---

### Milestone 3 — Build the 3 Missing Loaders (Days 2–3)

These loaders exist in the Week 2 spec but have no corresponding files in the repo. Each follows the exact same pattern as existing loaders.

#### `load_drug_classes.py`

**What it does:** Populates `drug_classes`, `drug_class_members`, and `class_interactions`.

**Why this matters:** Class-level rules catch NSAIDs vs anticoagulants even for drugs not individually encoded in `drug_interactions`. If a pharmacist dispenses an NSAID that's not in your 50-drug list, the engine can still warn about it via the class edge.

**Data source:** `knowledge_base/graph/edges.csv` already has 2,174 class-to-class edges. `knowledge_base/graph/nodes.csv` has 353 class nodes.

```
File to create: knowledge_base/DB_loaders/load_drug_classes.py

Logic:
  1. Read nodes.csv → insert into drug_classes (atc_code, class_name)
  2. For each of the 50 molecules, map their ATC code to a drug_class → insert into drug_class_members
     (ATC codes are already stored in drugs.atc_code by load_drugs_contraindications.py)
  3. Read edges.csv → insert into class_interactions (class_a_id, class_b_id, severity, clinical_effect)
  4. Log: N drug_classes, N drug_class_members, N class_interactions inserted

Key ATC class mappings to hardcode if edges.csv does not cover them:
  - All M01A (NSAIDs) → interact with B01 (anticoagulants): severity deconseillee
  - All J01 (antibiotics) → class-level interaction note for Vitamin K and warfarin
  - All C10A (statins) → interact with CYP3A4 inhibitors at class level
```

#### `load_adverse_effects.py`

**What it does:** Populates `adverse_effects` with real-world pharmacovigilance data.

**Data source:** OpenFDA adverse event API + `openfda_drug_data.csv` (already on disk for 30 drugs).

```
File to create: knowledge_base/DB_loaders/load_adverse_effects.py

Logic:
  1. For each of the 50 molecules, call OpenFDA:
     GET https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:"<inn>"&count=patient.reaction.reactionmeddrapt.exact&limit=10
  2. This returns the top 10 reported adverse reactions with counts
  3. Map to: molecule_id, adverse_effect_name, frequency (derive from count rank), source='openfda'
  4. MedDRA code: look up from the reaction term if available; otherwise leave null
  5. ON CONFLICT DO NOTHING
  6. Log: N adverse effects loaded per drug

Critical adverse effects to ensure are present (add manually if API misses them):
  - warfarin: hemorrhage (life-threatening)
  - metformin: lactic acidosis (rare, life-threatening)
  - statins: rhabdomyolysis (rare, life-threatening), myopathy (uncommon)
  - methotrexate: pancytopenia (severe), hepatotoxicity (severe)
  - tacrolimus: nephrotoxicity (severe), neurotoxicity (severe)
  - lithium: lithium toxicity / tremor / polyuria (common)
  - amiodarone: pulmonary toxicity (severe), thyroid dysfunction (common)
```

#### `load_molecular_targets.py`

**What it does:** Populates `molecular_targets` and `molecule_molecular_targets`.

**Data source:** ChEMBL API — the mechanism endpoint.

```
File to create: knowledge_base/DB_loaders/load_molecular_targets.py

Logic:
  For each molecule with a chembl_id in the DB:
    GET https://www.ebi.ac.uk/chembl/api/data/mechanism?molecule_chembl_id=<id>&format=json
    → returns: mechanism_of_action, target_chembl_id, action_type
    
    GET https://www.ebi.ac.uk/chembl/api/data/target/<target_chembl_id>?format=json
    → returns: target_name, target_components (includes UniProt ID)
    
    Insert into molecular_targets (target_name, uniprot_id) ON CONFLICT DO NOTHING
    Insert into molecule_molecular_targets (molecule_id, molecular_target_id, action_type)

  Rate limit: sleep(0.3) between calls (same pattern as load_rxnorm_chembl.py)
  Log: N targets discovered, N molecule-target links inserted

Key targets to ensure are present:
  - Vitamin K epoxide reductase (VKOR) — warfarin target
  - COX-1, COX-2 — NSAIDs, aspirin
  - Serotonin transporter (SERT) — SSRIs, tramadol
  - CYP2C9 — as metabolic target for warfarin, fluconazole
  - HMG-CoA reductase — all statins
  - Calcineurin — tacrolimus, cyclosporine
```

**Owners:** One person per loader, working in parallel. Each loader is ~80–120 lines following existing patterns. Estimated time: 3–4 hours per loader including testing.

---

### Milestone 4 — Expand CYP Data with Strength (Day 2–3)

The current `load_cyp.py` reads from `chembl_drug_data.csv` but the strength column (strong/moderate/weak) is not consistently populated. This is clinically critical — Trap 3 and Trap 7 depend on `strength = 'strong'` being correct.

**Action:**

1. Update `chembl_drug_data.csv` to add the strength column for every CYP entry
2. Update `load_cyp.py` to read the strength column and write it to `cyp_relationships.strength`

**Required CYP entries that must have correct strength:**

| Molecule | Enzyme | Relationship | Strength | Clinical relevance |
|---|---|---|---|---|
| clarithromycin | CYP3A4 | INHIBITOR | strong | Trap 3: simvastatin accumulation |
| fluconazole | CYP2C9 | INHIBITOR | strong | Trap 7: warfarin accumulation |
| fluconazole | CYP3A4 | INHIBITOR | moderate | Tacrolimus interaction |
| amiodarone | CYP2C9 | INHIBITOR | strong | Warfarin contraindication |
| rifampicin | CYP3A4 | INDUCER | strong | Warfarin, tacrolimus, cyclosporine |
| rifampicin | CYP2C9 | INDUCER | strong | Warfarin |
| carbamazepine | CYP3A4 | INDUCER | strong | Multiple drug interactions |
| phenobarbital | CYP3A4 | INDUCER | strong | Multiple drug interactions |
| simvastatin | CYP3A4 | SUBSTRATE | — | Trap 3 |
| warfarin | CYP2C9 | SUBSTRATE | — | Trap 7 |
| tacrolimus | CYP3A4 | SUBSTRATE | — | Tacrolimus interactions |
| cyclosporine | CYP3A4 | SUBSTRATE | — | Cyclosporine interactions |
| fluoxetine | CYP2D6 | INHIBITOR | moderate | Tramadol activation reduction |
| omeprazole | CYP2C19 | INHIBITOR | moderate | Clopidogrel activation |
| clopidogrel | CYP2C19 | SUBSTRATE | — | Omeprazole interaction |
| methotrexate | — | — | — | Not CYP-mediated; renal clearance interaction |

Also run `load_rxnorm_chembl.py` for the 20 new drugs — this will fetch their CYP metabolism data from ChEMBL automatically.

---

### Milestone 5 — Run All Trap Verifications (Days 3–4)

Write and commit one verification script per trap to `/evaluation/trap_verifications/`. Each script:
- Connects to the DB
- Runs the required query
- Prints PASS or FAIL with the result
- Exits 0 on pass, 1 on fail

If a verification fails: **fix the loader and rerun**. Never patch the DB manually.

#### Trap 1 — Warfarin + Aspirin

```python
# File: evaluation/trap_verifications/trap1_warfarin_aspirin.py
# Expected: severity_active in (major, deconseillee, contre_indique)
# clinical_effect mentions hemorrhage or bleeding
# management mentions INR or physician contact

SELECT di.severity_active, di.clinical_effect, di.management
FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'warfarin'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'aspirin';
```

#### Trap 2 — Metformin + CKD Contraindication

```python
# File: evaluation/trap_verifications/trap2_metformin_ckd.py
# Expected: contraindication entry for metformin + renal impairment
# severity = 'contraindicated'
# reason mentions lactic acidosis

SELECT c.severity, c.reason
FROM contraindications c
JOIN molecules m ON m.id = c.molecule_id AND m.inn = 'metformin'
JOIN disease_concepts dc ON dc.id = c.disease_concept_id
WHERE dc.condition_name ILIKE '%renal%' OR dc.icd11_code = 'N18';
```

#### Trap 3 — Simvastatin + Clarithromycin (CYP3A4)

```python
# File: evaluation/trap_verifications/trap3_cyp3a4_simvastatin.py
# Expected: TWO rows — simvastatin SUBSTRATE CYP3A4 + clarithromycin INHIBITOR CYP3A4 strong

SELECT m.inn, cr.enzyme, cr.relationship, cr.strength
FROM cyp_relationships cr
JOIN molecules m ON m.id = cr.molecule_id
WHERE m.inn IN ('simvastatin', 'clarithromycin')
  AND cr.enzyme = 'CYP3A4';
# Must return 2 rows: simvastatin/SUBSTRATE and clarithromycin/INHIBITOR/strong
```

#### Trap 4 — Penicillin Allergy + Amoxicillin

```python
# File: evaluation/trap_verifications/trap4_penicillin_allergy.py
# Expected: amoxicillin linked to Penicillins group
# AND Penicillins cross-reacts with Cephalosporins

-- Check 1: amoxicillin in penicillin allergy group
SELECT d.id, m.inn, ag.name
FROM drug_allergy_groups dag
JOIN drugs d ON d.id = dag.drug_id
JOIN molecules m ON m.id = d.molecule_id AND m.inn = 'amoxicillin'
JOIN allergy_groups ag ON ag.id = dag.allergy_group_id;

-- Check 2: penicillin <-> cephalosporin cross-reactivity exists
SELECT ag1.name, ag2.name
FROM allergy_cross_reactivities acr
JOIN allergy_groups ag1 ON ag1.id = acr.group_a_id
JOIN allergy_groups ag2 ON ag2.id = acr.group_b_id
WHERE ag1.name ILIKE '%penicillin%' OR ag2.name ILIKE '%penicillin%';
```

#### Trap 5 — Fluoxetine + Tramadol (Serotonin Syndrome)

```python
# File: evaluation/trap_verifications/trap5_serotonin_syndrome.py
# Expected: severity_active = major or deconseillee
# mechanism mentions serotonin

SELECT di.severity_active, di.clinical_effect, di.mechanism_type
FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'fluoxetine'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'tramadol';
```

#### Trap 6 — Elderly Dose (Ciprofloxacin + Renal Impairment)

```python
# File: evaluation/trap_verifications/trap6_elderly_dose.py
# Expected: contraindication or dose_adjustment for ciprofloxacin + renal impairment

SELECT c.severity, c.reason
FROM contraindications c
JOIN molecules m ON m.id = c.molecule_id AND m.inn = 'ciprofloxacin'
JOIN disease_concepts dc ON dc.id = c.disease_concept_id
WHERE dc.condition_name ILIKE '%renal%' OR dc.icd11_code = 'N18';
```

#### Trap 7 — CYP2C9 Overload (Warfarin + Fluconazole)

```python
# File: evaluation/trap_verifications/trap7_cyp2c9_overload.py
# Expected: warfarin SUBSTRATE CYP2C9 + fluconazole INHIBITOR CYP2C9 strong

SELECT m.inn, cr.enzyme, cr.relationship, cr.strength
FROM cyp_relationships cr
JOIN molecules m ON m.id = cr.molecule_id
WHERE m.inn IN ('warfarin', 'fluconazole')
  AND cr.enzyme = 'CYP2C9';
# Must return 2 rows: warfarin/SUBSTRATE and fluconazole/INHIBITOR/strong
```

#### Trap 8 — Therapeutic Duplication (Tahor = Atorvastatin)

```python
# File: evaluation/trap_verifications/trap8_therapeutic_duplication.py
# Expected: Tahor and atorvastatin resolve to the SAME molecule_id and same rxnorm_cui

SELECT d.brand_name_tn, m.inn, m.rxnorm_cui, m.id AS molecule_id
FROM drugs d
JOIN molecules m ON m.id = d.molecule_id
WHERE d.brand_name_tn = 'Tahor' OR m.inn = 'atorvastatin';
# Both rows must have the same molecule_id
```

#### 5 Additional High-Risk Pairs

```sql
-- Must all return rows with the indicated severity before Week 2 ends

-- Warfarin + Amiodarone → contre_indique
SELECT severity_active FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'warfarin'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'amiodarone';

-- Tacrolimus + Fluconazole → contre_indique
SELECT severity_active FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'tacrolimus'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'fluconazole';

-- Rifampicin + Warfarin → contre_indique
SELECT severity_active FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'rifampicin'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'warfarin';

-- Methotrexate + Ibuprofen → deconseillee or major
SELECT severity_active FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'methotrexate'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'ibuprofen';

-- Allopurinol + Azathioprine → contre_indique
SELECT severity_active FROM drug_interactions di
JOIN molecules a ON a.id = di.molecule_a_id AND a.inn = 'allopurinol'
JOIN molecules b ON b.id = di.molecule_b_id AND b.inn = 'azathioprine';
```

**File:** `evaluation/trap_verifications/additional_high_risk_pairs.py`

---

### Milestone 6 — Stress Tests (Day 4–5)

Write and commit all 5 stress tests to `/evaluation/stress_tests/`. Each documents: what it tests, what the expected result is, and whether it passed.

#### Stress Test 1 — Class-Level Fallback

Test that a drug not individually in `drug_interactions` still returns a risk via `class_interactions`.

```python
# File: evaluation/stress_tests/stress1_class_fallback.py
# Scenario: ibuprofen might not have a direct drug_interactions row with a specific anticoagulant,
#           but the NSAID class has a class_interactions edge with anticoagulants.
# Query: find class interactions for a molecule via its ATC membership

SELECT ci.severity, ci.clinical_effect
FROM class_interactions ci
JOIN drug_class_members dcm_a ON dcm_a.drug_class_id = ci.class_a_id
JOIN drug_class_members dcm_b ON dcm_b.drug_class_id = ci.class_b_id
JOIN molecules ma ON ma.id = dcm_a.molecule_id AND ma.inn = 'naproxen'
JOIN molecules mb ON mb.id = dcm_b.molecule_id AND mb.inn = 'warfarin';

# Expected: returns at least 1 row with severity deconseillee or higher
# Even if naproxen+warfarin has no direct drug_interactions row
```

#### Stress Test 2 — 6-Drug Polypharmacy

Test that all 15 pairwise combinations are returned for a 6-drug patient.

```python
# File: evaluation/stress_tests/stress2_polypharmacy_6drugs.py
# Drugs: warfarin, aspirin, enalapril, spironolactone, simvastatin, omeprazole
# Expected: 15 pairs attempted, each returns either an interaction row or NULL (not a crash)
# Log how many pairs have documented interactions vs no data

six_drugs = ['warfarin', 'aspirin', 'enalapril', 'spironolactone', 'simvastatin', 'omeprazole']
# Generate all 15 pairs from itertools.combinations
# For each pair: query drug_interactions with both orderings
# Print: pair, severity_active or "no direct interaction found"
```

#### Stress Test 3 — CYP Competition Without Direct Pair

Test that indirect CYP-mediated risk is detectable even without a `drug_interactions` row.

```python
# File: evaluation/stress_tests/stress3_cyp_indirect.py
# Scenario: two statins both on CYP3A4, one strong inhibitor added
# Pick: atorvastatin (CYP3A4 substrate) + simvastatin (CYP3A4 substrate) + clarithromycin (CYP3A4 inhibitor strong)
# Query: which molecules share a CYP enzyme where one is an inhibitor?

SELECT
  m_sub.inn AS substrate_drug,
  m_inh.inn AS inhibitor_drug,
  cr_sub.enzyme,
  cr_inh.strength AS inhibitor_strength
FROM cyp_relationships cr_sub
JOIN cyp_relationships cr_inh
  ON cr_inh.enzyme = cr_sub.enzyme
  AND cr_inh.relationship = 'INHIBITOR'
  AND cr_inh.molecule_id != cr_sub.molecule_id
JOIN molecules m_sub ON m_sub.id = cr_sub.molecule_id
JOIN molecules m_inh ON m_inh.id = cr_inh.molecule_id
WHERE cr_sub.relationship = 'SUBSTRATE'
  AND m_sub.inn IN ('atorvastatin', 'simvastatin')
  AND cr_inh.strength = 'strong';

# Expected: returns clarithromycin as a threat to both statins via CYP3A4
# No direct drug_interactions row needed between the two statins themselves
```

#### Stress Test 4 — Name Resolution Across 3 Identifiers

Test that querying by brand name, INN, or Tunisian brand all return the same molecule.

```python
# File: evaluation/stress_tests/stress4_name_resolution.py
# Drug: atorvastatin / Tahor (Tunisian brand) / Tahor (French brand)

-- By INN:
SELECT m.id, m.inn, m.rxnorm_cui FROM molecules m WHERE m.inn = 'atorvastatin';

-- By Tunisian brand name:
SELECT m.id, m.inn, m.rxnorm_cui FROM drugs d
JOIN molecules m ON m.id = d.molecule_id
WHERE d.brand_name_tn = 'Tahor';

-- By RxNorm CUI:
SELECT m.id, m.inn FROM molecules m WHERE m.rxnorm_cui = '83367'; -- atorvastatin CUI

# All three must return the same molecule.id
```

#### Stress Test 5 — Unknown Drug Graceful Handling

Test that querying an unknown drug returns empty, not an error.

```python
# File: evaluation/stress_tests/stress5_unknown_drug.py
# Drug: 'thisisnotalldrug123'

SELECT * FROM molecules WHERE inn = 'thisisnotalldrug123';
SELECT * FROM drug_interactions di
JOIN molecules m ON m.id = di.molecule_a_id
WHERE m.inn = 'thisisnotalldrug123';

# Expected: 0 rows, no exception, no crash
# This confirms the engine can safely handle unknown drug names at scan time
```

---

### Milestone 7 — Documentation (Day 5)

Two documents are explicitly required by the Week 2 spec. Both must be committed before the Week 2 checkpoint.

#### `/docs/graph_schema.md`

One line per table explaining why it exists. Template:

```markdown
# MedFlow — Knowledge Graph Schema

## molecules
Canonical drug entity keyed on INN. All interaction logic lives at the molecule level so brand name variants inherit it automatically.

## drugs
Brand/market instances of a molecule. Carries Tunisian and French brand names, ATC code, dosage form, and dose guidance for adult, elderly, renal-impaired, and hepatically-impaired patients.

## drug_interactions
Pairwise interaction edges between molecules (not drugs). Stores severity from both ANSM and OpenFDA separately; severity_active always uses the more conservative.

## cyp_relationships
CYP enzyme metabolic pathway edges per molecule. Enables indirect interaction detection when two drugs share an enzyme without a direct drug_interactions entry.

## contraindications
Links molecules to disease concepts where use is restricted. Severity: contraindicated | dose_adjustment | monitoring.

## disease_concepts
Canonical disease entities with ICD-11 and SNOMED-CT codes. Shared reference for contraindications, conditions, and treats.

## drug_classes
ATC classification nodes. Enables class-level interaction rules that apply to an entire drug category.

## drug_class_members
Many-to-many: which molecules belong to which ATC class.

## class_interactions
Interaction edges between drug classes. Catches risks for drugs not individually encoded (e.g. any NSAID vs anticoagulants).

## adverse_effects
Real-world side effects per molecule from OpenFDA pharmacovigilance with MedDRA codes and frequency.

## molecular_targets
Protein or receptor targets. Two drugs targeting the same receptor may have additive or antagonistic effects even without a drug_interactions entry.

## molecule_molecular_targets
Many-to-many: which molecules act on which targets, with action type (agonist, antagonist, inhibitor).

## treats
What each molecule is indicated for. The LLM reasoning layer needs to know what a drug treats, not just what it interacts with.

## allergy_groups
Allergy categories for cross-reactivity detection (e.g. Penicillins, Cephalosporins, NSAIDs).

## allergy_cross_reactivities
Cross-reactivity edges between allergy groups. Enables penicillin allergy → cephalosporin warning.

## drug_allergy_groups
Links drug brand instances to their allergy group.

## patients
Clinical patient records with demographic data and trap scenario tagging.

## conditions
Patient-specific condition instances linked to canonical disease_concepts.

## active_medications
What a patient is currently prescribed. Queried on every incoming prescription scan.

## allergies
Patient allergy records linked to allergy groups. Queried for allergy conflict detection.

## lab_results
Biomarker values (creatinine, INR, ALT, AST, HbA1c). Used for contraindication checks that depend on patient physiology.

## prescription_history
Historical prescription records for compliance and duplication detection.

## refill_records
Expected vs actual refill dates for proactive adherence monitoring.
```

#### `/docs/severity_disagreements.md`

Log every case where ANSM and OpenFDA disagreed during loading. Template:

```markdown
# Severity Disagreements — ANSM vs OpenFDA

Every case where the two sources classify the same interaction differently.
severity_active always uses the more conservative value.

| Pair | ANSM | OpenFDA | Active | Clinical note |
|---|---|---|---|---|
| warfarin + aspirin | deconseillee | major | deconseillee | ANSM deconseillee ≈ OpenFDA major in clinical weight |
| warfarin + heparin | precaution_emploi | major | major | OpenFDA more conservative here |
| ... | | | | |
```

This file is auto-populated as loaders run — make sure both `load_ansm_interactions.py` and `load_priority_interactions.py` print disagreements to stdout and log them here.

---

## Team Assignments

| Person | Day 1 | Day 2 | Days 3–4 | Day 5 |
|---|---|---|---|---|
| **PM (you)** | Confirm DB is up, review loader outputs | Review interaction data quality | Drive verifications, enforce pass criteria | severity_disagreements.md, final commit review |
| **Intern 1** | Run all existing loaders, confirm baseline | Write `extract_priority_interactions.py` | `load_drug_classes.py` | Stress tests 1 + 2 |
| **Intern 2 (Malak)** | Expand `ansm_interactions_all.csv` with ANSM severity for critical pairs | Finish ANSM encoding, run `load_ansm_interactions.py` | `load_adverse_effects.py` | Stress tests 3 + 4 + 5 |
| **Intern 3** | Run `load_patients.py`, confirm patients in DB | Update `chembl_drug_data.csv` with CYP strength, rerun `load_cyp.py` | `load_molecular_targets.py` + all trap verification scripts | `graph_schema.md` |

---

## Week 2 Checkpoint — 4 Things That Must Be True

Before calling Week 2 done, verify all of these:

**1. Schema locked and documented**
```
[ ] /docs/graph_schema.md committed with one-line justification per table
```

**2. All 50 drugs fully loaded**
```sql
SELECT COUNT(*) FROM molecules;         -- must be 50
SELECT COUNT(*) FROM drug_interactions; -- must be ≥ 100
SELECT COUNT(*) FROM cyp_relationships
WHERE strength IS NOT NULL;             -- critical entries must have strength
SELECT COUNT(*) FROM contraindications; -- must be ≥ 15
SELECT COUNT(*) FROM adverse_effects;   -- must be ≥ 100 (10 per drug average)
SELECT COUNT(*) FROM molecular_targets; -- must be ≥ 20
```

**3. All verifications pass**
```bash
# Run all trap verifications — all must exit 0
for f in evaluation/trap_verifications/*.py; do python "$f" && echo "PASS: $f" || echo "FAIL: $f"; done

# Run 5 additional pair checks
python evaluation/trap_verifications/additional_high_risk_pairs.py
```

**4. All stress tests pass and committed**
```bash
for f in evaluation/stress_tests/*.py; do python "$f" && echo "PASS" || echo "FAIL"; done
```

**5. Severity disagreements documented**
```
[ ] /docs/severity_disagreements.md committed with real entries from loader logs
```

---

## What Not to Do

- Do not patch the database manually when a verification fails. Fix the loader and rerun it.
- Do not skip the strength column in CYP relationships. The engine cannot detect strong vs weak inhibitors without it.
- Do not expand to 50 drugs in `drug_interactions` by making up severities. Use ANSM Thesaurus and OpenFDA as sources. Document your source for every row.
- Do not leave `engine/` or `interface/` empty and call it Week 2 scope — those are Week 3+. Stay focused on data quality.
- Do not commit with a passing e2e_test.py but a failing trap verification — every trap must pass independently.
