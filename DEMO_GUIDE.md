# MedFlow — Week 2 Demo Guide
> How to set up, run, and present the project to the teacher.
> Estimated time to run everything from scratch: ~15 minutes.

---

## Before the Demo — One-Time Setup

### 1. Prerequisites (install once)
```
Docker Desktop     — running
Python 3.10+       — installed
psycopg2           — pip install psycopg2-binary
requests           — pip install requests
```

### 2. Get the missing datasets from Google Drive
These files are too large for git. Place them exactly here before running anything:

```
knowledge_base/sources/dataset/ansm_interactions_all.csv        ← CRITICAL
knowledge_base/sources/dataset/flockhart_cyp_table.csv
knowledge_base/sources/dataset/interactions_priority_50.csv
knowledge_base/sources/dataset/chembl_drug_data.csv
knowledge_base/sources/dataset/rxnorm_mapping.csv
knowledge_base/sources/dataset/pct_human_medicines_recent_rich_rows.csv
knowledge_base/sources/dataset/pct_human_medicines_reference_options.csv
```

Large files (only needed if re-generating from raw FDA data — not needed for the demo):
```
knowledge_base/sources/dataset/toutes_les_interactions_fda.csv  (233 MB)
knowledge_base/sources/dataset/interactions_enriched.csv        (96 MB)
```

---

## Step-by-Step Setup

### Step 1 — Start the database
```bash
docker compose up -d
```
Wait ~5 seconds. The schema (`db/migrations/001_schema.sql`) is applied automatically on first start.

Verify it is running:
```bash
docker ps
# should show medflow-postgres-1 (or similar) as Up
```

---

### Step 2 — Load all data (run in this exact order)

```bash
# 1. Load the 50 molecules (RxNorm CUIs, ChEMBL IDs)
python knowledge_base/DB_loaders/load_rxnorm_chembl.py

# 2. Load brand names, contraindications, allergy groups
python knowledge_base/DB_loaders/load_drugs_contraindications.py

# 3. Load Tunisian PCT brand names
python knowledge_base/DB_loaders/load_pct_brands.py

# 4. Load ANSM interaction pairs (hand-curated severity)
python knowledge_base/DB_loaders/load_ansm_interactions.py

# 5. Load FDA-sourced interaction pairs (fills the remaining 280+ pairs)
python knowledge_base/DB_loaders/load_priority_interactions.py

# 6. Load CYP enzyme relationships from Flockhart table (with strength)
python knowledge_base/DB_loaders/load_cyp_flockhart.py

# 7. Load drug classes and class-level interaction rules
python knowledge_base/DB_loaders/load_drug_classes.py

# 8. Load adverse effects (OpenFDA pharmacovigilance data)
python knowledge_base/DB_loaders/load_adverse_effects.py

# 9. Load molecular targets (ChEMBL + hardcoded critical targets)
python knowledge_base/DB_loaders/load_molecular_targets.py

# 10. Load drug indications (what each drug treats)
python knowledge_base/DB_loaders/load_treats.py

# 11. Load synthetic patients (8 traps + 22 regular)
python patients/synthetic/load_patients.py
```

---

### Step 3 — Verify the database is correctly populated

Run this to see all counts at once:
```bash
python -c "
import psycopg2
conn = psycopg2.connect(dbname='medflow', user='medflow', password='medflow', host='localhost')
cur = conn.cursor()
tables = [
    ('molecules',                  50),
    ('drugs',                      30),
    ('drug_interactions',         100),
    ('cyp_relationships',           1),
    ('contraindications',          15),
    ('adverse_effects',           100),
    ('molecular_targets',          20),
    ('treats',                      1),
    ('drug_classes',                1),
    ('class_interactions',          1),
    ('drug_class_members',          1),
    ('molecule_molecular_targets',  1),
    ('patients',                   30),
]
print('Table                          Count   Target   Status')
print('-'*60)
for table, target in tables:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    n = cur.fetchone()[0]
    ok = 'OK' if n >= target else 'UNDER'
    print(f'{table:30s}  {n:5d}   >={target:<5d}   {ok}')
cur.close(); conn.close()
"
```

Expected output — every row should show **OK**.

---

## The Demo — What to Show the Teacher

### Part 1 — Show the schema (2 minutes)
Open `/docs/graph_schema.md` and walk through it.
**Key talking point:** *"Every table has a single responsibility. The power comes from the edges between them — drug_interactions, cyp_relationships, class_interactions — not from storing everything in one big table."*

---

### Part 2 — Show the data quality (3 minutes)

Run these queries live in the terminal:

```bash
# How many interaction pairs and what severity distribution?
python -c "
import psycopg2
conn = psycopg2.connect(dbname='medflow', user='medflow', password='medflow', host='localhost')
cur = conn.cursor()
cur.execute('SELECT severity_active, COUNT(*) FROM drug_interactions GROUP BY severity_active ORDER BY COUNT(*) DESC')
print('Interaction severity breakdown:')
for r in cur.fetchall(): print(f'  {r[0]:25s}  {r[1]}')
cur.close(); conn.close()
"

# Show the CYP strong inhibitors (clinically most dangerous)
python -c "
import psycopg2
conn = psycopg2.connect(dbname='medflow', user='medflow', password='medflow', host='localhost')
cur = conn.cursor()
cur.execute('''
    SELECT m.inn, cr.enzyme, cr.relationship, cr.strength
    FROM cyp_relationships cr JOIN molecules m ON m.id=cr.molecule_id
    WHERE cr.strength = \'strong\' ORDER BY cr.enzyme, m.inn
''')
print('Strong CYP inhibitors/inducers:')
for r in cur.fetchall(): print(f'  {r[0]:20s}  {r[1]:8s}  {r[2]:10s}  {r[3]}')
cur.close(); conn.close()
"

# Show the life-threatening adverse effects
python -c "
import psycopg2
conn = psycopg2.connect(dbname='medflow', user='medflow', password='medflow', host='localhost')
cur = conn.cursor()
cur.execute('''
    SELECT m.inn, ae.adverse_effect_name
    FROM adverse_effects ae JOIN molecules m ON m.id=ae.molecule_id
    WHERE ae.severity = \'life_threatening\' ORDER BY m.inn
''')
print('Life-threatening adverse effects:')
for r in cur.fetchall(): print(f'  {r[0]:20s}  {r[1]}')
cur.close(); conn.close()
"
```

---

### Part 3 — Run the trap verifications (5 minutes)

This is the core demo. Run all 8 traps live:

```bash
for %f in (evaluation\trap_verifications\trap*.py) do python "%f"
```

On Linux/Mac:
```bash
for f in evaluation/trap_verifications/trap*.py; do python "$f"; done
```

**Expected output — all 8 lines say PASS.**

Then run the 5 additional high-risk pairs:
```bash
python evaluation/trap_verifications/additional_high_risk_pairs.py
```

**Talking point for each trap:**
| Trap | What it proves |
|---|---|
| Trap 1 — Warfarin + Aspirin | Direct interaction pair detected, severity + clinical effect returned |
| Trap 2 — Metformin + CKD | Disease-drug contraindication detected, not just drug-drug |
| Trap 3 — Simvastatin + Clarithromycin | Risk detected by traversing CYP3A4 graph, no direct pair needed |
| Trap 4 — Penicillin allergy + Amoxicillin | Allergy cross-reactivity graph works |
| Trap 5 — Fluoxetine + Tramadol | Serotonin syndrome caught, CYP2D6 pathway confirmed |
| Trap 6 — Ciprofloxacin + Renal impairment | Dose adjustment contraindication returned |
| Trap 7 — Warfarin + Fluconazole | CYP2C9 substrate + strong inhibitor detected |
| Trap 8 — Tahor vs Atorvastatin | Brand name and INN resolve to the same molecule — therapeutic duplication caught |

---

### Part 4 — Run the stress tests (3 minutes)

```bash
for %f in (evaluation\stress_tests\stress*.py) do python "%f"
```

On Linux/Mac:
```bash
for f in evaluation/stress_tests/stress*.py; do python "$f"; done
```

**Expected output — all 5 say PASS.**

**Talking point:**
*"The stress tests deliberately try to break the graph. Stress test 1 proves the class-level fallback works — even a drug not individually programmed can still trigger a warning through its drug class. Stress test 5 proves the engine handles unknown drug names gracefully without crashing."*

---

### Part 5 — Show the severity disagreements (1 minute)

Open `/docs/severity_disagreements.md`.

**Talking point:** *"Every case where ANSM and the FDA rated the same interaction differently is documented here. The system always takes the more conservative value. This is what separates a production-grade knowledge graph from a student project — we know where our sources disagree and we made a deliberate, documented decision for each one."*

---

## If Something Goes Wrong During the Demo

| Problem | Fix |
|---|---|
| `psycopg2.OperationalError: connection refused` | Docker isn't running — `docker compose up -d`, wait 10 seconds |
| A trap returns FAIL | Re-run the relevant loader for that trap, then re-run the script |
| `ModuleNotFoundError: psycopg2` | `pip install psycopg2-binary` |
| Wrong count in a table | Re-run the loader for that table — all loaders are idempotent (safe to re-run) |

---

## Final DB Numbers (for reference during Q&A)

| What | Count |
|---|---|
| Drugs in the system | 51 molecules, 31 brand entries |
| Interaction pairs | 304 (17 ANSM hand-curated + 287 FDA-sourced) |
| CYP pathway entries | 82 (from Flockhart Indiana University table) |
| Contraindications | 16 (disease-drug restrictions) |
| Adverse effects | 574 (17 life-threatening, 42 severe) |
| Molecular targets | 58 targets, 74 molecule-target links |
| Drug indications | 84 (what each drug is for) |
| Drug classes | 40 classes, 88 class-level interaction rules |
| Synthetic patients | 30 (8 trap scenarios + 22 regular) |
| Severity disagreements documented | 17 |
