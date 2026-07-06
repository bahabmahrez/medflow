# MedFlow — Project Progress Log

> Running log of everything built, fixed, and decided. Updated after every work session.
> Owner: PM (Houssem). Last updated: 2026-07-06.

---

## Week 1 — Foundation

### What was built
- PostgreSQL 16 database schema with 23 tables covering molecules, drugs, interactions, CYP pathways, contraindications, allergy groups, patients, and lab results
- Docker Compose setup for local development
- Initial set of 30 priority molecules loaded
- 17 ANSM interaction pairs manually encoded in `ansm_interactions_all.csv`
- 8 synthetic trap patients + 22 regular patients designed and loaded
- Basic loader scripts: `load_rxnorm_chembl.py`, `load_drugs_contraindications.py`, `load_ansm_interactions.py`, `load_pct_brands.py`
- Data lake populated: FDA interaction dump (233 MB), ChEMBL drug data, OpenFDA adverse event data, Flockhart P450 HTML, PCT Tunisian medicines catalog

### Known gaps entering Week 2
- Only 17 interaction pairs — clinically worthless for a 50-drug system
- No drug classes, adverse effects, or molecular targets tables populated
- CYP data had no strength column (strong/moderate/weak)
- `treats` table empty
- Contraindications covered only 11 molecule-disease pairs (target ≥15)

---

## Week 2 — Build the Complete Knowledge Graph

### Milestone 1 — Schema locked

All required tables confirmed present:
- `drug_classes`, `class_interactions` — class-level interaction detection
- `adverse_effects` — OpenFDA pharmacovigilance data
- `molecular_targets`, `molecule_molecular_targets` — pharmacodynamic reasoning
- `treats` — drug indications (populated Week 2, session 2)
- `snomed_code` column present in `disease_concepts`

Schema documented in `/docs/graph_schema.md`.

---

### Milestone 2 — Full knowledge base loaded

#### Drug interactions expanded: 17 → 304 pairs

**Problem:** 17 hardcoded ANSM pairs was insufficient for a 50-drug system.

**Solution — two-stage pipeline:**
1. `knowledge_base/loaders/extract_priority_interactions.py` — filters the 233 MB FDA dump to pairs where both drugs are in the 50-drug list → outputs `interactions_priority_50.csv` (108 KB, ~200 pairs)
2. `knowledge_base/DB_loaders/load_priority_interactions.py` — loads those pairs into `drug_interactions` with `source_confidence = 'openfda'`, never overwriting existing ANSM rows

**ANSM manual encoding:** critical pairs upgraded directly from the ANSM Thesaurus. Three pairs were found to have wrong severity from FDA extraction and corrected:
- tacrolimus + fluconazole: `a_prendre_en_compte` → `contre_indique`
- allopurinol + azathioprine: `a_prendre_en_compte` → `contre_indique`
- methotrexate + ibuprofen: `a_prendre_en_compte` → `deconseillee`

---

#### CYP data — replaced with Flockhart table (M4)

**Problem:** `load_cyp_local.py` used hardcoded data with no strength column. `chembl_drug_data.csv` covered only 30 drugs and had inconsistent strength values.

**Solution — Flockhart P450 Drug Interaction Table (Indiana University):**
- Page is a Blazor server-side app with virtual scrolling — standard scraping returns 0 inhibitors/inducers
- **Root cause of virtual scroll problem:** table rows are lazy-rendered; only visible rows exist in the DOM
- **Fix:** parse pre-rendered `data-rvt-dialog` attributes (764 elements, always in DOM) instead of visible table cells
- Two-pass approach: `parse_dialogs()` for drug/enzyme/relationship + `parse_trigger_strengths()` for strength from `<img alt="S|M|W|I">` trigger elements
- 142 duplicate dialog IDs handled by deduplication logic (keeps entry with strength when duplicate exists)
- Drug name cleaning: strips relationship suffixes `(Substrate-3A4/5)`, inline aliases like `(fk506)` for tacrolimus, footnote markers
- **Output:** `flockhart_cyp_table.csv` — 621 unique entries across 8 CYP enzymes, 406 with strength grading
- New canonical loader: `load_cyp_flockhart.py` — replaces `load_cyp_local.py`
- Supplements added for drugs not in Flockhart: valproate CYP2C9/2C19 INHIBITOR weak, isoniazid CYP2E1 INHIBITOR strong, allopurinol CYP2C9 INHIBITOR weak, ethinylestradiol CYP3A4 SUBSTRATE, metronidazole CYP2C9 INHIBITOR moderate
- **Result:** 82 CYP rows (76 Flockhart + 6 supplements)

**Correction applied (session 2):** fluconazole CYP2C9 INHIBITOR reclassified `moderate` → `strong` per FDA drug interaction guidance (Flockhart rated it moderate; clinical pharmacology and ANSM classify it strong).

---

#### 3 missing loaders built (M3)

**`load_drug_classes.py`**
- Hardcoded `MOLECULE_CLASSES` dict: 50 INNs → DrugBank EPC class names
- Hardcoded `CLASS_ATC` dict: EPC class name → WHO ATC code
- Loads 40 drug_classes, 54 drug_class_members, 88 class_interactions
- Class interactions sourced from `knowledge_base/graph/edges.csv` (2,174 DrugBank edges) filtered to relevant class pairs
- NSAID + Vitamin K Antagonist edge added manually (was missing from edges.csv; required for stress test 1)
- **Result:** 40 drug classes, 54 members, 88 class interaction edges

**`load_molecular_targets.py`**
- 40 hardcoded critical targets (INN, target_name, uniprot_id, action_type)
- ChEMBL API used for additional targets: `/mechanism?molecule_chembl_id=<id>` → `/target/<id>` for UniProt
- Key targets confirmed: VKOR (warfarin), COX-1/2 (NSAIDs/aspirin), SERT (SSRIs/tramadol), HMG-CoA reductase (statins), Calcineurin (tacrolimus/cyclosporine), xanthine oxidase (allopurinol)
- **Result:** 58 molecular_targets, 74 molecule_molecular_targets

**`load_adverse_effects.py`**
- 74 hardcoded critical entries for life-threatening adverse effects
- OpenFDA API for top-10 adverse reactions per drug: `count=patient.reaction.reactionmeddrapt.exact`
- **Result:** 574 adverse_effects (17 life_threatening, 42 severe, 514 moderate)

---

#### Contraindications gap fixed

**Problem:** 11 pairs — below the required ≥15.
**Fix:** added 5 rows — ciprofloxacin + N18 (dose_adjustment, critical for Trap 6), aspirin/ibuprofen/diclofenac/naproxen + K27 (Peptic ulcer disease, contraindicated).
**Result:** 16 contraindications.

---

#### `treats` table populated (session 2)

50 drugs × indications loaded from hardcoded clinical data.
Key entries: warfarin → thromboembolic disorders, metformin → type 2 diabetes, simvastatin/atorvastatin → hypercholesterolaemia.

---

### Milestone 3 — Trap verifications

All 8 trap scripts written to `/evaluation/trap_verifications/`. Each connects to the DB, runs the verification query, prints PASS/FAIL, exits 0/1.

| Script | Result | Key check |
|---|---|---|
| trap1_warfarin_aspirin.py | PASS | severity=deconseillee, bleeding mentioned |
| trap2_metformin_ckd.py | PASS | severity=contraindicated, renal/lactic mentioned |
| trap3_cyp3a4_simvastatin.py | PASS | CYP3A4 pathway confirmed |
| trap4_penicillin_allergy.py | PASS | amoxicillin in penicillin group, cephalosporin cross-reactivity |
| trap5_serotonin_syndrome.py | PASS | serotonin mentioned, CYP2D6 pathway confirmed |
| trap6_elderly_dose.py | PASS | dose_adjustment for ciprofloxacin + renal |
| trap7_cyp2c9_overload.py | PASS | warfarin CYP2C9 SUBSTRATE + fluconazole CYP2C9 INHIBITOR strong |
| trap8_therapeutic_duplication.py | PASS | Tahor and atorvastatin → same molecule_id=21 |
| additional_high_risk_pairs.py | ALL PASS | 5/5 contre_indique/deconseillee pairs confirmed |

**Note on severity labels:** The teacher's spec uses DrugBank scale (`major`). The DB stores ANSM scale (`deconseillee`). These are clinically equivalent. Trap verification scripts accept both.

---

### Milestone 4 — Stress tests

All 5 stress test scripts written to `/evaluation/stress_tests/`.

| Script | Result | Key check |
|---|---|---|
| stress1_class_fallback.py | PASS | naproxen+warfarin surfaced via NSAID↔VKA class edge |
| stress2_polypharmacy_6drugs.py | PASS | 5/15 pairs found, 0 query errors across 6-drug patient |
| stress3_cyp_competition.py | PASS | omeprazole/clopidogrel CYP2C19 indirect pathway detected |
| stress4_name_resolution.py | PASS | Tahor/Glucophage/Seroquel resolve to correct molecule_id |
| stress5_unknown_drug.py | PASS | 4 invalid inputs return 0 rows, no crash |

**Data fixes discovered during stress tests:**
- quetiapine was missing from molecules — added with Seroquel brand
- NSAID ↔ Vitamin K Antagonist class_interactions edge was missing — added

---

### Documentation

- `/docs/graph_schema.md` — one-line justification per table, severity scale reference
- `/docs/severity_disagreements.md` — 17 real disagreements between ANSM and DrugBank/FDA, resolution policy documented

---

## Week 2 Final DB Counts

| Table | Count | Target |
|---|---|---|
| molecules | 51 | ≥50 |
| drugs | 31 | ≥30 |
| drug_interactions | 304 | ≥100 |
| cyp_relationships | 82 | — |
| cyp_relationships with strength | 60 | critical entries present |
| contraindications | 16 | ≥15 |
| adverse_effects | 574 | ≥100 |
| molecular_targets | 58 | ≥20 |
| drug_classes | 40 | >0 |
| class_interactions | 88 | >0 |
| drug_class_members | 54 | >0 |
| molecule_molecular_targets | 74 | >0 |
| patients | 30 | 30 |
| patients (trap) | 8 | 8 |
| treats | 84 | >0 |

---

## Datasets Not in Git (must share manually)

`.gitignore` excludes `knowledge_base/sources/dataset/*.csv`.

### Share with all contributors (< 2 MB total)
| File | Why critical |
|---|---|
| `ansm_interactions_all.csv` | Hand-curated ANSM severity — cannot be regenerated |
| `flockhart_cyp_table.csv` | Scraped CYP data — input to `load_cyp_flockhart.py` |
| `interactions_priority_50.csv` | Filtered FDA pairs for 50 drugs |
| `chembl_drug_data.csv` | ChEMBL IDs and CYP data |
| `rxnorm_mapping.csv` | RxNorm CUI lookups |

### Share via Google Drive only (large files, ~500 MB)
| File | Size | Who needs it |
|---|---|---|
| `toutes_les_interactions_fda.csv` | 233 MB | Whoever re-runs `extract_priority_interactions.py` |
| `interactions_enriched.csv` | 96 MB | Same |
| `interactions_fda_clean.csv` | 95 MB | Same |
| `interactions_grouped_by_class.csv` | 93 MB | Class loader work |

---

## Gap Analysis — Teacher Spec vs. Actual (resolved 2026-06-24)

After comparing against the teacher's original milestone document, 3 gaps were found and fixed:

### Gap 1 — `treats` table was empty ✅ fixed
New loader `knowledge_base/DB_loaders/load_treats.py` created.
84 indication rows inserted for all 50 priority drugs (DrugBank/WHO ATC source, evidence_level A/B/C).
Also created 36 new `disease_concepts` rows (ICD-11 codes BA00, 5A11, 6A60, etc.) as a side effect.

### Gap 2 — fluconazole CYP2C9 strength was `moderate`, should be `strong` ✅ fixed
Flockhart table rated it moderate; FDA drug interaction guidance and ANSM Thesaurus classify fluconazole
as a STRONG CYP2C9 inhibitor. Updated directly. Trap 7 now returns `strong` as required.

### Gap 3 — SNOMED codes missing from disease_concepts ✅ fixed
All 46 disease_concepts rows now have `snomed_code` except DA41 (Peptic ulcer disease ICD-11),
which is a known duplicate of K27 — both map to SNOMED 13200003 and the unique constraint
prevents assigning it twice. DA41 has proper condition_name but null snomed_code.

### Note on severity label mismatch (Trap 1 & 5)
Teacher's spec says `severity_active = major`. DB stores `deconseillee` (ANSM scale).
These are clinically equivalent — DrugBank uses `major`, ANSM uses `deconseillee` for the same weight.
Trap verification scripts accept both values. Documented in `/docs/severity_disagreements.md`.

---

## Open Issues / Technical Debt

- `load_cyp_local.py` still exists alongside `load_cyp_flockhart.py` — old file should be removed before Week 3
- Kardegic (aspirin) and Depakine (valproate) brand names not in `drugs` table — flagged in stress4 as WARN
- DA41 disease_concept has null `snomed_code` (acceptable — duplicate of K27)
- `load_drugbank.py` named in teacher's spec — equivalent data loaded via multiple scripts; worth creating a wrapper script for clarity

---

## Week 4 — From Chatbot to Agent (Tool-Calling)

### What changed

Week 3's `graphrag.ask()` was a **fixed pipeline**: Python `if`-branches decided
which of the 10 query functions ran, based on which kwargs the *caller* passed
in (`conditions=`, `allergies=`, etc.). The LLM only ever explained data that
was already assembled for it — it never chose what to look up.

Week 4 flips that control to the model. A new `agent/` package gives the LLM
the full list of 10 query functions as callable tools; the model decides which
to call, with what arguments, reads the results, and can call more tools
before answering — up to a hard iteration cap. This is purely additive: **no
Week 3 file was modified** (`llm/provider.py::generate()`, `llm/system_prompt.txt`,
`graphrag/pipeline.py::ask()`, and the existing `/ask` endpoint are all
untouched, and all 82 Week 3 unit tests still pass unmodified).

### Milestone 1 — Tools

- `llm/provider.py` gained a new sibling function, `generate_with_tools()`,
  alongside the existing `generate()`. It takes/returns provider-agnostic,
  OpenAI-wire-format structures (`messages` list, `tools` list of
  `{name, description, parameters}` dicts) and normalizes the response to
  `{content, stop_reason, tool_calls}` regardless of provider.
  - **Groq / OpenAI-compatible branch** (`_call_openai_compat_with_tools`) —
    the live path in this environment (`.env` has `LLM_PROVIDER=groq`, no
    Anthropic key). Near-zero translation since the tool schema is already
    OpenAI's native shape.
  - **Anthropic branch** (`_call_anthropic_with_tools`) — full translation
    shim (`_to_anthropic_tools`, `_to_anthropic_messages`) converting the
    canonical OpenAI-wire history into Anthropic's content-block format
    (tool results become a `role:"user"` message with a `tool_result` block —
    the one non-obvious part). **Only verified with a mocked Anthropic
    client** — there's no `ANTHROPIC_API_KEY` configured here, so this path
    has never run live.
- `agent/tools.py` — the 10 query functions wrapped as tool schemas with
  precise, LLM-facing "when to use this" descriptions (not just restated
  docstrings), a `TOOL_REGISTRY` name→function map, and a `call_tool()` safe
  dispatcher that never raises: unknown tool name, missing required
  argument, malformed JSON arguments, or an exception inside the underlying
  query function all become a normal `{"status":"error",...}` result instead
  of crashing the loop.

### Milestone 2 — Agent loop

- `agent/loop.py::run_agent(question, *, patient_context=None, max_iterations=8)`
  — sends the question (plus an optional plain-text patient-context block —
  informational only, the model still has to decide to act on it) and the
  full tool list to the model; executes whatever tools it requests; feeds
  results back; repeats until a final answer or the iteration cap. If the cap
  is hit, one forced call with no tools makes the model synthesize an answer
  from whatever was already gathered, instead of truncating silently.
- `agent/trace.py` — every step logged: the model's text for that turn, every
  tool call requested (name + arguments), and every tool execution (result,
  status, duration). `pretty_print()` renders a human-readable trace for
  demos/debugging.

### Milestone 3 — Identity and guardrails

- `agent/system_prompt_addendum.txt` + `agent/prompts.py` — the agent's
  system prompt is Week 3's existing 8 safety rules (`llm/system_prompt.txt`,
  loaded via `llm.load_system_prompt()`, unchanged) plus a new addendum
  layered on top at runtime (not a duplicated copy on disk, so the two can
  never drift apart). The addendum covers: agent identity (pharmacy-safety
  assistant, not a diagnostician), tool-use rules (never pass an argument
  value the pharmacist didn't state, verify unfamiliar names first),
  reporting rules (never invent a finding for an empty/failed tool result),
  severity-first-and-present-don't-command, refusal boundaries (diagnosis,
  unsupported dosing populations, forced binary answers, ambiguous
  references), and anti-tool-misuse (never call a tool with a drug that
  wasn't mentioned).

### Milestone 4 — Evaluation (25 scenarios)

New `evaluation/agent_eval/` package, parallel to Week 3's `evaluation/llm_eval/`:

- **10 multi-tool** cases, grounded in real trap patients from
  `patients/synthetic/load_patients_graph.py` (`warfarin_aspirin`,
  `metformin_ckd`, `simvastatin_cyp3a4`, `penicillin_allergy`,
  `polypharmacy_elderly`, `digoxin_amiodarone`, etc.), run as natural
  pharmacist questions, plus 2 non-trap cases targeting `get_drug_profile`
  and `get_drugs_by_class` specifically (no trap scenario naturally exercises
  those two).
- **7 ambiguity** cases — a dose with no unit, a vague drug-class reference,
  a patient reference with no data, an allergy mentioned with no candidate
  drug named, etc. Scored on whether the final answer reads as a clarifying
  question rather than a confident assertion.
- **8 adversarial** cases — 6 of Week 3's Tier-3 adversarial cases (leading
  question, authority claim, unknown drug, out-of-scope, hallucination trap,
  dose fishing) replayed against the agent, plus 2 new tool-misuse cases:
  an unresolvable drug in a multi-drug list must be surfaced (not silently
  dropped or fabricated), and a training-data-plausible but never-mentioned
  drug (e.g. "aspirin" alongside warfarin) must never appear in any tool
  call's arguments.
- `runner.py::score_agent()` scores each case on: whether at least one
  *acceptable* set of tools was called (an OR of tool-name sets, since
  `full_prescription_check` legitimately substitutes for several granular
  tools — scoring doesn't overfit to one arbitrary strategy), required/
  forbidden answer phrases, the clarifying-question heuristic, and a scan of
  every logged tool argument for forbidden values.
- `test_coverage.py` — a meta-test asserting the 25-case suite is capable of
  exercising all 10 registered tools (static check) plus a `@pytest.mark.live`
  version asserting all 10 are *actually* invoked across real runs.

### Also touched (additive only)

- `graphrag/server.py` — new `POST /agent/ask` endpoint (separate
  request/response models, takes `patient_context` instead of `/ask`'s flat
  kwargs, returns the full trace). Existing `/ask` and `/health` untouched.
- `requirements.txt` — added `openai>=1.0` explicitly (was already installed
  and used by the Groq path, but never declared; Week 4 makes that path
  load-bearing for every live test here).
- `DEMO_GUIDE.md` — new sections 10-12 (testing `/agent/ask`, running the
  25-case agent eval suite, running the full Weeks 1-4 unit test suite).

### Test results

```
python -m pytest -m "not live" -q
125 passed, 61 deselected
```
= 82 pre-existing Week 1-3 tests (unmodified) + 43 new Week 4 tests
(`agent/tests/`: 15, `llm/tests/test_provider_tools.py`: 8,
`evaluation/agent_eval/` unit tests: ~20), verified with Neo4j + Postgres
both running via `docker compose up -d`.

### Known limitations / open issues

- The Anthropic tool-calling path (`_call_anthropic_with_tools` and its
  translation shim) is unit-tested with mocks only — never exercised live,
  since this environment has no `ANTHROPIC_API_KEY`. Worth a live check if
  the project ever switches `LLM_PROVIDER` to `anthropic`.
- The 25-case `evaluation/agent_eval` suite has not yet been run live against
  the real Groq API (`python -m evaluation.agent_eval.runner`) — the mocked
  unit tests confirm the scoring logic is correct, but real pass/fail rates
  against the actual model are still unmeasured.
- A pre-existing (Week 3, not introduced here) gap was found while
  investigating a test hang: `graphrag/tests/test_pipeline.py`'s
  `test_extract_drugs_*` tests patch `graphrag.pipeline.resolve_drug_name`,
  but `extract_drugs()` also calls a second, independently-imported
  `resolve_drug_name` reference inside `graphrag/_drug_extraction.py` that
  the patch doesn't intercept — those tests silently depend on a live Neo4j
  connection rather than being fully mocked. Not fixed here (out of Week 4's
  additive-only scope) but worth a follow-up.
