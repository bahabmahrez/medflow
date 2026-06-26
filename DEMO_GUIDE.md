# MedFlow — Graph Database Demo Guide
> How to set up, run, and present the project to the teacher.
> Estimated time to run everything from scratch: ~20 minutes.

---

## What Changed from Week 2

MedFlow now runs a **dual-stack** architecture:

| Layer | Technology | Purpose |
|---|---|---|
| Relational | PostgreSQL 15 | Original schema — molecules, interactions, patients |
| **Graph (new)** | **Neo4j 5** | Property graph — enables CYP traversal, allergy chains, polypharmacy detection |

The graph layer holds the same knowledge base but expresses relationships as **typed edges**, enabling queries impossible in SQL — e.g. *"find all patients whose current medications share a CYP enzyme with a recently added drug"* in a single Cypher statement.

---

## Before the Demo — One-Time Setup

### 1. Prerequisites (install once)
```
Docker Desktop     — running
Python 3.10+       — installed
psycopg2-binary    — pip install psycopg2-binary
neo4j              — pip install neo4j>=5.0
requests           — pip install requests
```

Or install from the requirements files:
```bash
pip install -r requirements.txt
pip install -r requirements-graph.txt
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

---

## Step-by-Step Setup

### Step 1 — Start both databases
```bash
docker compose up -d
```
This starts **PostgreSQL** (port 5432) and **Neo4j 5** (port 7687 / 7474) together.

Verify both are running:
```bash
docker ps
# should show medflow-postgres-1 and medflow-neo4j-1 as Up
```

Neo4j Browser UI (optional, visual exploration):
```
http://localhost:7474
Username: neo4j   Password: medflow
```

---

### Step 2 — Load all data into PostgreSQL (original relational stack)
```bash
python run_loaders.py
```
This runs all 12 SQL loaders in the correct order. Output should end with:
```
All 12 loaders completed successfully.
```

---

### Step 3 — Initialise the Neo4j graph schema
```bash
python db/graph/init_graph.py
```
Creates uniqueness constraints and indexes. Expected output:
```
Schema applied: 8 constraints, 11 property indexes
Neo4j ready.
```

---

### Step 4 — Load all data into Neo4j (graph stack)
```bash
python run_loaders_graph.py
```
This runs the same 12 loaders rewritten in Cypher, in the correct order.
All loaders are idempotent (safe to re-run). Expected output:
```
All 12 loaders completed successfully.
```

---

### Step 5 — Verify graph contents
Open Neo4j Browser at `http://localhost:7474` and run:
```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
```

Expected node counts:

| Label | Expected |
|---|---|
| Molecule | ~51 |
| Drug | ~183 |
| CYPEnzyme | 6 |
| DrugClass | ~40 |
| DiseaseConcept | ~30 |
| AllergyGroup | 5 |
| AdverseEffect | ~80 |
| MolecularTarget | ~53 |
| Patient | **50** |
| LabResult | ~55 |

Or from the terminal:
```bash
python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','medflow'))
r = d.execute_query('MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC')
for rec in r.records: print(f'{rec[\"l\"]:25s}  {rec[\"c\"]}')
d.close()
"
```

---

## The Demo — What to Show the Teacher

### Part 1 — Explain the graph model (2 minutes)
Open `/docs/graph_schema.md` and walk through it.

**Key talking point:**
> *"In the relational version, CYP interactions require three JOINs across four tables. In the graph version, the same query is a single Cypher path expression: `(drug)-[:SUBSTRATE_OF]->(enzyme)<-[:INHIBITS]-(inhibitor)`. The graph makes pharmacological reasoning readable."*

---

### Part 2 — Show graph traversal queries live (3 minutes)

Open Neo4j Browser (`http://localhost:7474`) and run these live:

**Query 1 — CYP3A4 conflict for a patient:**
```cypher
MATCH (p:Patient {name: 'Nabil Chaabane'})
      -[:TAKES]->(:Drug)-[:BRAND_OF]->(sub:Molecule)
      -[:SUBSTRATE_OF]->(cyp:CYPEnzyme {name: 'CYP3A4'})
      <-[:INHIBITS]-(inh:Molecule)
      <-[:BRAND_OF]-(:Drug)<-[:TAKES]-(p)
RETURN p.name, sub.inn AS substrate, cyp.name AS enzyme, inh.inn AS inhibitor
```
*"This finds the simvastatin + clarithromycin CYP3A4 conflict directly from the patient node in one hop."*

**Query 2 — Find all patients with supratherapeutic warfarin AND a CYP2C9 inhibitor:**
```cypher
MATCH (p:Patient)
WHERE p.inr > 3.0
MATCH (p)-[:TAKES]->(:Drug)-[:BRAND_OF]->(m:Molecule)
      -[:SUBSTRATE_OF]->(:CYPEnzyme {name: 'CYP2C9'})
      <-[:INHIBITS]-(:Molecule)<-[:BRAND_OF]-(:Drug)<-[:TAKES]-(p)
RETURN p.name, p.inr, collect(m.inn) AS warfarin_substrates
```

**Query 3 — Allergy cross-reactivity chain:**
```cypher
MATCH path = (ag1:AllergyGroup {name: 'penicillin'})-[:CROSS_REACTS_WITH*1..2]->(ag2:AllergyGroup)
RETURN [n IN nodes(path) | n.name] AS allergy_chain
```

---

### Part 3 — Run the SQL trap verifications (3 minutes)

The original 8 SQL-based traps still work on the PostgreSQL stack:

**PowerShell:**
```powershell
Get-ChildItem evaluation\trap_verifications\trap*.py | ForEach-Object { python $_.FullName }
```

**Linux/Mac:**
```bash
for f in evaluation/trap_verifications/trap*.py; do python "$f"; done
```

**Expected: all 8 lines say PASS.**

---

### Part 4 — Run the graph trap verifications (5 minutes — main demo)

This is the core upgrade. 20 graph traps test traversal patterns impossible in SQL:

```bash
python evaluation/graph_verifications/run_all_graph_traps.py
```

**Expected: all 20 lines say PASS.**

**Talking point for each trap category:**

| Category | Traps | What the graph enables |
|---|---|---|
| Direct DDI | 01, 09, 11, 20 | Simple edge lookup — warfarin+aspirin, warfarin+amiodarone, allopurinol+azathioprine, digoxin+amiodarone |
| CYP 2-hop paths | 03, 07, 10, 12, 13, 14 | `substrate→enzyme←inhibitor` — rhabdomyolysis, INR spike, subtherapeutic warfarin, tacrolimus toxicity, antiplatelet failure |
| Allergy chain | 04 | `AllergyGroup -[:CROSS_REACTS_WITH]->` — penicillin allergy → cephalosporin risk |
| Patient-centric | 14, 18 | Start from Patient node, find ALL drug conflicts automatically via traversal |
| Class-level fallback | 15, 17 | `Molecule -[:MEMBER_OF]-> DrugClass -[:CLASS_INTERACTS_WITH]->` — NSAID+VKA, two SSRIs |
| Lab-triggered | 16 | `Patient.creatinine_umol_L > 150` with no CKD ICD code — lab-only contraindication |
| Contraindication | 02, 19 | `Molecule -[:CONTRAINDICATED_FOR]-> DiseaseConcept` — metformin+CKD, NSAID+peptic ulcer |
| Brand resolution | 08 | `Drug -[:BRAND_OF]-> Molecule` — Tahor resolves to atorvastatin |
| Dose context | 06 | `Patient.dob` + `Drug.dose_elderly` — elderly ciprofloxacin flag |

---

### Part 5 — Show a patient's full risk profile (2 minutes)

```bash
python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','medflow'))

# Bechir Hajji — polypharmacy elderly patient with 6 drugs
r = d.execute_query('''
  MATCH (p:Patient {trap_scenario: \"polypharmacy_elderly\"})
        -[:TAKES]->(drug:Drug)-[:BRAND_OF]->(m:Molecule)
  RETURN p.name AS patient, m.inn AS drug, drug.brand_name AS brand
  ORDER BY m.inn
''')
print(f\"Patient: {r.records[0]['patient']} — medications:\")
for rec in r.records:
    print(f\"  {rec['drug']:20s}  ({rec['brand']})\")

# Find all DDIs among their meds
ddi = d.execute_query('''
  MATCH (p:Patient {trap_scenario: \"polypharmacy_elderly\"})
        -[:TAKES]->(:Drug)-[:BRAND_OF]->(m1:Molecule)
        -[r:INTERACTS_WITH]-(m2:Molecule)
        <-[:BRAND_OF]-(:Drug)<-[:TAKES]-(p)
  WHERE id(m1) < id(m2)
  RETURN m1.inn AS a, r.severity_active AS sev, m2.inn AS b
  ORDER BY r.severity_rank DESC
''')
print(f\"\nDDI pairs detected from the graph:\")
for rec in ddi.records:
    print(f\"  {rec['a']:20s} + {rec['b']:20s}  [{rec['sev']}]\")

d.close()
"
```

---

### Part 6 — Show severity source hierarchy (1 minute)

Open `/docs/severity_disagreements.md`.

**Talking point:**
> *"Every case where ANSM and the FDA rated the same interaction differently is documented here. The graph always stores the more conservative value — ANSM overrides FDA, curated overrides upgrade never downgrade. This is what separates a production-grade knowledge graph from a student project."*

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ServiceUnavailable: Unable to connect to bolt://localhost:7687` | Neo4j container not running — `docker compose up -d neo4j`, wait 15 seconds |
| `AuthError: The client is unauthorized` | Wrong credentials — check `NEO4J_AUTH=neo4j/medflow` in docker-compose.yml |
| `psycopg2.OperationalError: connection refused` | PostgreSQL not running — `docker compose up -d postgres` |
| A graph trap returns FAIL | Re-run the relevant graph loader, then re-run the trap script |
| `ModuleNotFoundError: neo4j` | `pip install neo4j>=5.0` |
| `ModuleNotFoundError: psycopg2` | `pip install psycopg2-binary` |
| Wrong node count in Neo4j | All graph loaders use MERGE — re-running `python run_loaders_graph.py` is safe |

---

## Summary Counts (for Q&A)

### PostgreSQL (relational layer)
| What | Count |
|---|---|
| Molecules | 51 |
| Drug entries (brands + dosage forms) | 183 |
| Interaction pairs | 281 (17 ANSM + 261 FDA + 3 curated) |
| CYP pathway entries | 109 |
| Contraindications | 11 |
| Adverse effects | ~1,600 |
| Molecular targets | 53 targets, 67 links |
| Drug indications | 84 |
| Drug classes | 40 classes, 88 class rules |
| Synthetic patients | 30 (legacy count) |

### Neo4j (graph layer — new)
| What | Count |
|---|---|
| Molecule nodes | 51 |
| Drug nodes | ~183 |
| INTERACTS_WITH edges | 281+ |
| CYPEnzyme nodes | 6 |
| SUBSTRATE_OF / INHIBITS / INDUCES edges | 109+ |
| CONTRAINDICATED_FOR edges | 11+ |
| DrugClass nodes | ~40 |
| CLASS_INTERACTS_WITH edges | 88+ |
| AllergyGroup nodes | 5 |
| Patient nodes | **50** (20 trap + 30 regular) |
| Trap scenarios covered | **20** |
| Graph trap verifications | **20** (all in `evaluation/graph_verifications/`) |

### Trap scenarios breakdown
| # | Scenario | Traversal type |
|---|---|---|
| 1 | Warfarin + Aspirin | Direct INTERACTS_WITH |
| 2 | Metformin + CKD | CONTRAINDICATED_FOR |
| 3 | Simvastatin + Clarithromycin | CYP3A4 2-hop |
| 4 | Penicillin allergy → cephalosporin | CROSS_REACTS_WITH chain |
| 5 | Fluoxetine + Tramadol | Direct DDI + shared SERT target |
| 6 | Elderly dose — ciprofloxacin | Patient.dob + Drug.dose_elderly |
| 7 | Warfarin + Fluconazole | CYP2C9 strong inhibitor 2-hop |
| 8 | Tahor → atorvastatin | BRAND_OF resolution |
| 9 | Warfarin + Amiodarone | Direct contre_indique |
| 10 | Rifampicin + Warfarin | CYP2C9 INDUCES 2-hop |
| 11 | Allopurinol + Azathioprine | Direct contre_indique (xanthine oxidase) |
| 12 | Tacrolimus + Fluconazole | Narrow TI + CYP3A4 strong inhibitor |
| 13 | Clopidogrel + Omeprazole | CYP2C19 loss-of-effect 2-hop |
| 14 | CYP2D6 patient traversal | Patient→Drug→CYP←Drug←Patient |
| 15 | NSAID + VKA + steroid | DrugClass CLASS_INTERACTS_WITH fallback |
| 16 | Metformin eGFR lab-only | Patient.creatinine_umol_L property (no ICD code) |
| 17 | Two SSRIs | Therapeutic duplication via DrugClass |
| 18 | Polypharmacy elderly ≥6 drugs | Multi-hop DDI scan from Patient node |
| 19 | NSAID + Peptic ulcer | Patient→HAS_CONDITION→DC←CONTRAINDICATED_FOR |
| 20 | Digoxin + Amiodarone | Direct INTERACTS_WITH |
