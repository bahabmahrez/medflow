# MedFlow — Project Architecture

> **MedFlow** is a **pharmacy safety intelligence system** that combines a **dual-database medical knowledge graph** (PostgreSQL + Neo4j) with **LLM-powered reasoning** to detect drug-drug interactions, contraindications, allergy conflicts, CYP450 enzyme competition, therapeutic duplications, and dose appropriateness.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [Architecture Layers](#3-architecture-layers)
   - [3.1 Data & Storage Layer](#31-data--storage-layer)
   - [3.2 Knowledge Base & ETL Layer](#32-knowledge-base--etl-layer)
   - [3.3 Query Layer](#33-query-layer)
   - [3.4 GraphRAG Pipeline (Week 3)](#34-graphrag-pipeline-week-3)
   - [3.5 Agent Layer (Week 4)](#35-agent-layer-week-4)
   - [3.6 MCP Server (Week 5)](#36-mcp-server-week-5)
   - [3.7 API Layer](#37-api-layer)
4. [Data Flow](#4-data-flow)
5. [Project Structure Map](#5-project-structure-map)
6. [Key Design Decisions](#6-key-design-decisions)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                  │
│  (FastAPI HTTP)    (MCP Stdio)     (Python SDK)    (Browser)   │
└───────┬─────────────────┬─────────────────┬─────────────────────┘
        │                 │                 │
┌───────▼─────┐   ┌──────▼──────┐   ┌─────▼──────────┐
│  graphrag/   │   │ medflow_mcp/│   │    agent/      │
│  server.py   │   │  server.py  │   │   loop.py      │
│  (FastAPI)   │   │  (MCP stdio)│   │ (tool-calling) │
└───────┬─────┘   └──────┬──────┘   └─────┬──────────┘
        │                 │                 │
        └────────────┬────┘─────────────┬──┘
                     │                  │
              ┌──────▼──────┐   ┌──────▼──────┐
              │  llm/       │   │   query/    │
              │ provider.py │   │  (10 tools) │
              └──────┬──────┘   └──────┬──────┘
                     │                  │
                     │           ┌──────┴──────┐
                     │           │  graphrag/   │
                     │           │ context.py   │
                     │           │ (formatters) │
                     │           └──────┬──────┘
                     │                  │
              ┌──────▼──────────────────▼──────┐
              │         DATA STORE             │
              │  ┌──────────┐  ┌────────────┐  │
              │  │PostgreSQL│  │   Neo4j    │  │
              │  │ (relational│  │ (graph)    │  │
              │  │   +23    │  │  9 labels  │  │
              │  │  tables) │  │ 20+ rels   │  │
              │  └──────────┘  └────────────┘  │
              └──────────────────────────────┘
```

MedFlow is organized across **7 architectural layers**, each with a distinct responsibility:

---

## 2. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Relational DB** | PostgreSQL | 16 | Structured clinical data (molecules, contraindications, patients) |
| **Graph DB** | Neo4j | 5 | Knowledge graph for drug interactions, CYP pathways, class hierarchies |
| **LLM Provider** | Groq (primary) / Anthropic / OpenAI | — | Natural language reasoning & explanation |
| **LLM Model** | Llama 3.3 70B (via Groq) / Claude | — | Core reasoning model |
| **API Framework** | FastAPI | ≥0.138 | REST endpoints for GraphRAG & Agent |
| **MCP Framework** | `mcp` Python SDK | ≥1.25 | Model Context Protocol server |
| **Orchestration** | Docker Compose | — | Local dev environment (Postgres + Neo4j) |
| **Testing** | pytest | ≥9.0 | Unit, integration, evaluation suites |
| **Migration** | SQL (manual) | — | `db/migrations/001_schema.sql` |

---

## 3. Architecture Layers

### 3.1 Data & Storage Layer

MedFlow uses a **dual-database architecture** — each chosen for its strengths:

#### PostgreSQL (`db/migrations/001_schema.sql`)
- **23 tables** covering:
  - `molecules` — 51 canonical drug entities (INN, RxNorm, ChEMBL IDs)
  - `drugs` — 31 brand/market instances (Tunisian, French, international brands)
  - `drug_interactions` — 304 direct pairwise interaction edges
  - `cyp_relationships` — 82 CYP450 enzyme relationships (substrate/inhibitor/inducer)
  - `contraindications` — 16 molecule-disease contra-indication pairs
  - `adverse_effects` — 574 adverse effect entries from OpenFDA
  - `drug_classes` / `class_interactions` — 40 ATC classes with 88 class-level edges
  - `molecular_targets` — 58 protein/receptor targets with 74 drug-target links
  - `treats` — 84 drug-indication mappings
  - `allergy_groups` / `allergy_cross_reactivities` — cross-reactivity network
  - `patients` / `conditions` / `active_medications` / `allergies` / `lab_results` — 30 synthetic patients (8 trap)
  - `prescription_history` / `refill_records`

#### Neo4j (`db/graph/schema.cypher`)
- **9 node labels**: `Molecule`, `Drug`, `CYPEnzyme`, `DrugClass`, `DiseaseConcept`, `AllergyGroup`, `MolecularTarget`, `Patient`, `LabResult`
- **20+ relationship types**: `INTERACTS_WITH`, `SUBSTRATE_OF`, `INHIBITS`, `INDUCES`, `MEMBER_OF`, `CLASS_INTERACTS_WITH`, `CONTRAINDICATED_FOR`, `TARGETS`, `HAS_ADVERSE_EFFECT`, `CROSS_REACTS_WITH`, `BRAND_OF`, `TAKES`, `HAS_CONDITION`, `ALLERGIC_TO`, `HAS_LAB`
- Uniqueness constraints and performance indexes on all major lookup fields

#### Deployment
```yaml
# docker-compose.yml
services:
  postgres:  # port 5432, auto-inits from db/migrations/
  neo4j:     # port 7474 (UI) + 7687 (Bolt), auth disabled
```

---

### 3.2 Knowledge Base & ETL Layer

**Location:** `knowledge_base/`

The knowledge base is built through a **pipeline of data loaders** that ingest and normalize medical data from multiple sources:

#### Data Sources
| Source | Content | Size |
|--------|---------|------|
| **OpenFDA** | Drug interaction dump (`toutes_les_interactions_fda.csv`) | 233 MB |
| **ANSM Thesaurus** | French regulatory interaction & contraindication data | Curated |
| **Flockhart P450 Table** | CYP enzyme interaction table (scraped from Indiana University) | 621 entries |
| **ChEMBL** | Drug mechanism & molecular target data | API |
| **RxNorm** | Drug name normalization & mapping | — |
| **PCT Tunisie** | Tunisian pharmaceutical catalog | — |
| **DrugBank** | Class-level interaction edges (`edges.csv`) | 2,174 edges |

#### Key Loader Scripts
| Script | What it Loads |
|--------|--------------|
| `load_rxnorm_chembl.py` | RxNorm CUIs and ChEMBL IDs for molecules |
| `load_priority_interactions.py` | 200+ FDA interaction pairs filtered to 50-drug list |
| `load_ansm_interactions.py` | ANSM hand-curated severity labels |
| `load_cyp_flockhart.py` | Flockhart CYP table (replaces hardcoded `load_cyp_local.py`) |
| `load_drug_classes.py` | 40 ATC drug classes + 88 class interaction edges |
| `load_molecular_targets.py` | 58 targets (ChEMBL API enriched) |
| `load_adverse_effects.py` | 574 adverse effects (OpenFDA API enriched) |
| `load_drugs_contraindications.py` | 16 molecule-disease contraindication pairs |
| `load_treats.py` | 84 drug-indication mappings |
| `load_pct_brands.py` | Tunisian brand names |
| `load_curated_overrides.py` | Manual corrections to severity/pairs |

#### Data Cleaning Pipeline (`knowledge_base/Data_cleaning/`)
- `data_cleaning.py` — general FDA data cleaning
- `age_pipeline.py` — patient age data processing
- `enrich_openfda.py` — OpenFDA data enrichment
- `graph_prep.py` — data preparation for graph loading
- `Fill pharma class.py` — pharmaceutical class assignment

---

### 3.3 Query Layer

**Location:** `query/`

The query layer is the **core retrieval engine** — 10 deterministic functions that query the databases and return structured results in a consistent envelope:

```python
{"status": "found|not_found|error", "data": {...}, "message": "..."}
```

| Function | Module | Purpose |
|----------|--------|---------|
| `resolve_drug_name(name)` | `resolve.py` | Resolve any drug name (INN, brand, TN brand) to canonical INN |
| `get_drug_profile(drug)` | `drugs.py` | Full drug profile from knowledge graph |
| `get_drugs_by_class(drug_class)` | `drugs.py` | List all drugs in a given ATC class |
| `detect_pairwise_interactions(drug_list)` | `interactions.py` | Direct drug-drug interaction edges |
| `detect_cyp_competition(drug_list)` | `interactions.py` | CYP450 enzyme-mediated interactions |
| `check_contraindications(drug, conditions)` | `safety.py` | Molecule-disease contraindications |
| `check_allergy_conflict(drug, allergies)` | `safety.py` | Allergy + cross-reactivity checks |
| `check_therapeutic_duplication(new_drug, active_meds)` | `safety.py` | Duplicate therapy detection |
| `check_dose_appropriateness(drug, ...)` | `safety.py` | Dose adjustment flags (age, renal, hepatic) |
| `full_prescription_check(...)` | `prescription.py` | Consolidated multi-axis safety check |

These functions are consumed by **three different consumers** (GraphRAG pipeline, Agent loop, MCP server) — this is the **reusable core** of the system.

---

### 3.4 GraphRAG Pipeline (Week 3)

**Location:** `graphrag/`

The **Retrieve → Augment → Generate** pipeline that powers the original `/ask` endpoint:

```
user question
     │
     ▼
┌─────────────────┐
│ extract_drugs() │─── Drug name extraction (multilingual, fuzzy, graph-verified)
└────────┬────────┘
         │ drugs detected
         ▼
┌──────────────────────┐
│  Run graph queries   │─── Pairwise interactions, CYP competition, contraindications,
│ (conditionally based │    allergy conflicts, duplications, dose checks
│  on available kwargs)│
└────────┬─────────────┘
         │ raw results
         ▼
┌──────────────────┐
│ context.py       │─── Format results into structured text blocks
│ (formatters)     │    (fmt_interactions, fmt_cyp, fmt_contraindications, etc.)
└────────┬─────────┘
         │ structured context
         ▼
┌──────────────────┐
│ llm/generate()   │─── LLM generates explanation grounded in context
└────────┬─────────┘
         │
         ▼
    {"answer", "drugs_detected", "context", "risk_level"}
```

**Key design properties:**
- **Deterministic drug extraction** — uses `resolve_drug_name()` as a strict gate to prevent hallucination
- **Multilingual support** — works with English, French, Arabic, and Tunisian Darija drug names
- **Fuzzy matching** — typo-tolerant via `SequenceMatcher` with configurable threshold (default 0.86)
- **Conditional graph queries** — only runs safety checks relevant to the provided kwargs (conditions, allergies, etc.)
- **Risk classification** — aggregates individual severities into HIGH / MEDIUM / LOW

---

### 3.5 Agent Layer (Week 4)

**Location:** `agent/`

The **tool-calling agent** wraps the 10 query functions as callable tools that the LLM decides when and how to invoke — a shift from the fixed pipeline to model-driven exploration.

#### Architecture
```
question + optional patient_context
     │
     ▼
┌─────────────────┐
│  run_agent()    │─── Iterative loop (max 8 iterations)
│  agent/loop.py  │
└────────┬────────┘
         │ messages + tools
         ▼
┌─────────────────────┐
│ generate_with_tools │─── LLM provider (Groq/Anthropic/OpenAI)
│   llm/provider.py   │
└────────┬────────────┘
         │ response (content + tool_calls)
         ▼
    ┌────┴────┐
    │ tool    │  No → final answer
    │ calls?  │
    └────┬────┘
         │ Yes
         ▼
┌─────────────────┐
│  call_tool()    │─── Safely dispatches to query layer
│  agent/tools.py │    (never raises; errors become normal results)
└────────┬────────┘
         │ result
         ▼
    Append result to messages, loop back
```

#### Components
| File | Purpose |
|------|---------|
| `tools.py` | 10 tool schema definitions (JSON Schema format), `TOOL_REGISTRY`, `call_tool()` safe dispatcher |
| `loop.py` | `run_agent()` — iterative message loop with iteration cap handling |
| `prompts.py` | `agent_system_prompt()` — concatenates base safety rules + agentic addendum |
| `system_prompt_addendum.txt` | Agent identity, tool-use rules, reporting rules, refusal boundaries |
| `trace.py` | Full execution trace logging (every step, tool call, argument, result, duration) |

#### Agent Safety Guardrails
1. **Never pass an argument value the pharmacist didn't state**
2. **Verify unfamiliar names first** using `resolve_drug_name`
3. **Never invent a finding for empty/failed tool results**
4. **Severity-first presentation** — lead with most severe finding
5. **Refusal boundaries** — no diagnosis, no unsupported dosing populations, no forced binary answers
6. **Anti-tool-misuse** — never call a tool with a drug that wasn't mentioned

---

### 3.6 MCP Server (Week 5)

**Location:** `medflow_mcp/`

A **Model Context Protocol** server that wraps the same 10 query functions as MCP tools, making them available to **any MCP-compatible client** (Claude Desktop, Cursor, VS Code extensions, etc.).

#### Features
- **10 MCP tools** — same functions as the agent, prefixed with `_tool` suffix
- **3 MCP resources**: `medflow://system-prompt`, `medflow://tools`, `medflow://graph-stats`
- **3 MCP prompts**: `evaluate_prescription()`, `drug_info()`, `check_interactions()`
- Runs via `stdio` transport: `python -m medflow_mcp`

---

### 3.7 API Layer

**Location:** `graphrag/server.py`

A **FastAPI** application exposing two endpoints:

| Endpoint | Method | Backend | Purpose |
|----------|--------|---------|---------|
| `/health` | GET | — | Liveness check |
| `/ask` | POST | `graphrag.pipeline.ask()` | Week 3 GraphRAG pipeline (fixed) |
| `/agent/ask` | POST | `agent.loop.run_agent()` | Week 4 tool-calling agent |

#### `/ask` Request
```json
{
  "question": "Is simvastatin safe with clarithromycin?",
  "conditions": ["hypercholesterolemia"],
  "allergies": [],
  "active_meds": [],
  "age": 65,
  "weight": null,
  "labs": {}
}
```

#### `/agent/ask` Request
```json
{
  "question": "New prescription is clarithromycin for a patient already on simvastatin and warfarin.",
  "patient_context": {
    "conditions": ["atrial fibrillation"],
    "allergies": ["penicillin"],
    "active_meds": ["warfarin", "simvastatin"],
    "age": 72
  },
  "max_iterations": 8
}
```

---

## 4. Data Flow

### End-to-End (Agent path)

```
User Question
     │
     ▼
1. Agent loop: run_agent(question, patient_context)
     │
     ▼
2. LLM generates response with tool calls
     │
     ▼
3. For each tool call:
   call_tool(name, arguments)
     │
     ▼
4. Query layer function executes:
   ┌─ resolve_drug_name() ──► Neo4j (Molecule lookup)
   ├─ get_drug_profile()   ──► Neo4j (multi-hop traversal)
   ├─ detect_pairwise_interactions() ──► Neo4j (INTERACTS_WITH edges)
   ├─ detect_cyp_competition() ──► Postgres (cyp_relationships) + Neo4j
   ├─ check_contraindications() ──► Postgres (contraindications)
   ├─ check_allergy_conflict() ──► Postgres (allergy_groups, cross_reactivities)
   ├─ check_therapeutic_duplication() ──► Neo4j (brand→molecule resolution)
   ├─ check_dose_appropriateness() ──► Postgres (drugs.dose_* columns)
   ├─ get_drugs_by_class() ──► Postgres (drug_classes, drug_class_members)
   └─ full_prescription_check() ──► Multiple tools combined
     │
     ▼
5. Result returned to LLM as tool result
     │
     ▼
6. LLM either:
   ├─ Calls more tools (loop back to step 3)
   └─ Produces final answer (exit loop)
```

---

## 5. Project Structure Map

```
medflow/
├── db/                          # Database schemas & migrations
│   ├── migrations/001_schema.sql  ─── PostgreSQL DDL (23 tables)
│   └── graph/schema.cypher        ─── Neo4j schema (9 labels, 20+ rels)
│
├── knowledge_base/              # ETL & data loading pipeline
│   ├── DB_loaders/              ─── 14 SQL loaders (PostgreSQL)
│   ├── graph_loaders/           ─── 10 Neo4j loaders
│   ├── loaders/                 ─── Raw data extraction & processing
│   ├── Data_cleaning/           ─── Data cleaning & enrichment scripts
│   ├── graph/                   ─── Graph visualization exports
│   ├── pipelines/               ─── Shell/PowerShell automation
│   └── sources/                 ─── Data source artifacts (gitignored)
│
├── query/                       # Core retrieval layer (10 functions)
│   ├── __init__.py              ─── Public API
│   ├── _neo4j.py                ─── Neo4j connection manager
│   ├── resolve.py               ─── Drug name resolution
│   ├── drugs.py                 ─── Drug profile & class queries
│   ├── interactions.py          ─── Pairwise + CYP queries
│   ├── safety.py                ─── Contraindications, allergies, dose
│   ├── prescription.py          ─── Full consolidated check
│   └── tests/                   ─── 5 test files
│
├── graphrag/                    # Week 3 GraphRAG pipeline
│   ├── pipeline.py              ─── ask() + extract_drugs()
│   ├── _drug_extraction.py      ─── Multilingual drug detection
│   ├── context.py               ─── Result formatters
│   ├── server.py                ─── FastAPI server (/ask, /agent/ask)
│   └── tests/                   ─── Pipeline tests
│
├── agent/                       # Week 4 Tool-calling agent
│   ├── loop.py                  ─── run_agent() iterative loop
│   ├── tools.py                 ─── 10 tool schemas + dispatcher
│   ├── prompts.py               ─── System prompt assembly
│   ├── system_prompt_addendum.txt ─── Agentic guardrails
│   ├── trace.py                 ─── Execution trace logging
│   └── tests/                   ─── Agent tests
│
├── llm/                         # LLM provider abstraction
│   ├── provider.py              ─── generate() + generate_with_tools()
│   ├── system_prompt.txt        ─── 8 base safety rules
│   └── tests/                   ─── Provider tests
│
├── medflow_mcp/                 # Week 5 MCP server
│   ├── __main__.py              ─── Entry point
│   ├── server.py                ─── MCP tools, resources, prompts
│   └── tests/                   ─── MCP tests
│
├── evaluation/                  # Comprehensive test suites
│   ├── agent_eval/              ─── 25 agent evaluation scenarios
│   ├── graph_verifications/     ─── 20 graph trap verifications
│   ├── llm_eval/                ─── 10 LLM evaluation cases
│   ├── stress_tests/            ─── 5 stress tests
│   ├── trap_verifications/      ─── 8 trap verification scripts
│   ├── e2e_test.py              ─── End-to-end test
│   └── manual_e2e_test.py       ─── Manual E2E test
│
├── patients/synthetic/          ─── 30 synthetic patient profiles
├── docs/                        ─── Project documentation
├── .gitignore
├── docker-compose.yml           ─── Postgres 16 + Neo4j 5
├── requirements.txt             ─── Python dependencies
├── pytest.ini                   ─── Pytest config
└── PROGRESS.md                  ─── Development progress log
```

---

## 6. Key Design Decisions

### Why Dual Database (PostgreSQL + Neo4j)?
- **PostgreSQL** handles structured, normalized clinical data (patients, lab results, contraindication pairs) where SQL joins and constraints are natural
- **Neo4j** handles graph traversal queries (drug interaction networks, multi-hop CYP pathways, brand→molecule resolution) where graph traversals are 10-100x faster than recursive SQL

### Why Three Distinct Consumers?
The 10 query functions are consumed by:
1. **GraphRAG pipeline** — fixed sequence, conditional logic controlled by caller kwargs
2. **Agent loop** — LLM decides which tools to call and in what order
3. **MCP server** — any MCP-compatible AI client

This avoids duplicating business logic across different interfaces.

### Severity Scale Handling
The system bridges two different severity vocabularies:
- **ANSM scale** (French regulatory): `contre_indique` / `deconseillee` / `precaution_emploi` / `a_prendre_en_compte`
- **DrugBank scale**: `major` / `moderate` / `minor`

Mapped to internal risk levels: HIGH / MEDIUM / LOW.

### LLM Provider Abstraction
The `llm/provider.py` abstracts three providers behind a unified interface:
- **Groq** (default — fastest, free tier available)
- **Anthropic Claude** (requires `ANTHROPIC_API_KEY`)
- **OpenAI / Ollama** (for local models)

Swapping requires only changing environment variables, no code changes.

### Anti-Hallucination Design
Multiple layers prevent the LLM from fabricating drug safety information:
1. **Deterministic extraction** — drugs must pass `resolve_drug_name()` to appear in results
2. **Strict context grounding** — LLM only sees data the query layer actually retrieved
3. **Safety guardrails** — system prompt forbids inventing findings for empty tool results
4. **Error-safe dispatch** — all tool errors become normal structured results, not exceptions

### Agent Loop Safety
The agent loop has multiple safeguards:
- **Max iterations cap** (default 8) — prevents infinite loops
- **Fallback generation** — when cap is hit, one more call with no tools forces synthesis
- **Provider error handling** — malformed tool calls (e.g., Groq server-side schema validation errors) caught and surfaced gracefully
- **Tool misuse detection** — agent prompt explicitly forbids calling tools with drugs not mentioned by the pharmacist

---

## Version History

| Week | Layer | What Was Built |
|------|-------|---------------|
| **Week 1** | Foundation | PostgreSQL schema, Docker Compose, 30 molecules, basic loaders |
| **Week 2** | Knowledge Graph | 304 interactions, CYP Flockhart table, drug classes, molecular targets, adverse effects, 30 patients, trap verifications |
| **Week 3** | GraphRAG | `extract_drugs()`, `ask()` pipeline, LLM integration, `/ask` endpoint |
| **Week 4** | Agent | Tool-calling agent loop, `generate_with_tools()`, 10 tool schemas, 25 eval scenarios, `/agent/ask` endpoint |
| **Week 5** | MCP | MCP server with 10 tools, 3 resources, 3 prompts |

---

*Last updated: 2026-07-06*

