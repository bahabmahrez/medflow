# Week 5 — Pharmacy AI Agent: Learning & Build Plan

> **Theme:** Turn the existing tools into a *real* agent loop that drives them over the **MCP server**, give the agent an **identity + permissions gate**, add **context compaction**, and make **evaluation + observability** an always-on layer.
>
> **How we work this week:** *Guide & review.* You write the core implementation so the concepts stick. I explain each concept, scaffold structure + stubs with `TODO`s, and review/critique your code. **Loop approach:** manual MCP client (reuse the existing loop). **Scope:** a working first version of **all four** milestones.
>
> **📌 Status update — 2026-07-31:** The team has **implemented Milestones 1–3 and the observability piece of M4** (committed in `b4ec9b1`). The loop now drives tools over a real MCP client, with a permission gate and context compaction; evaluation runs are logged via a **custom JSON logger** (chosen over Opik). **What's left:** run the eval suites *live* against Groq and fix failures (§8), plus the **code-review findings in §9** (dated today). Study guide: [docs/MCP_STUDY_GUIDE.md](docs/MCP_STUDY_GUIDE.md); sources: [docs/LEARNING_LOG.md](docs/LEARNING_LOG.md).

---

## 0. Context — where the project actually stands

The Week 5 brief assumed less existed than it did — and as of **2026-07-31** most of the build is done. Status table below reflects reality after commit `b4ec9b1`:

| Capability | Status (2026-07-31) | File |
|---|---|---|
| Agent loop (native tool-calling, 8-iteration cap, forced final synthesis, trace) | ✅ Exists — now **async**, drives tools over MCP | [agent/loop.py](agent/loop.py) |
| 10 clinical tools (pairwise, CYP, contraindication, allergy, dose…) | ✅ Exists, all **read-only** | [query/](query/) |
| MCP **server** (FastMCP, 10 tools + 3 resources + 3 prompts, stdio) | ✅ Exists | [medflow_mcp/server.py](medflow_mcp/server.py) |
| Provider layer with native function-calling (Groq / Anthropic / Ollama) | ✅ Exists — `generate_with_tools` | [llm/provider.py](llm/provider.py) |
| Eval suites (30 GraphRAG cases + 25 agentic cases, tiered) | ✅ Exists, keyword-substring scoring | [evaluation/](evaluation/) |
| **MCP *client*** (loop connects to the server, discovers tools) | ✅ **Done (M1)** — `_create_mcp_session` → `list_tools` → `call_tool` | [agent/loop.py](agent/loop.py) |
| **Permissions / HITL gate**, read-vs-write tool classification | ✅ **Done (M2)** — `classify_tool` + `require_confirmation` gate | [agent/permissions.py](agent/permissions.py) |
| **Context management / compaction** | ✅ **Done (M3)** — `summary + recent tail`, threshold 12 | [agent/loop.py](agent/loop.py) |
| **Observability**, trace persistence | ✅ **Done (custom)** — JSON run logger (chose over Opik) | [evaluation/observability.py](evaluation/observability.py) |
| Live eval runs (Groq) + LLM-as-judge scoring | 🚧 **Remaining (M4)** — see §8 | [evaluation/](evaluation/) |

**So the mental model now is "understand, harden, and verify," not "build from zero."** The single most important idea to *understand deeply* is **tool discovery over MCP**: the loop no longer knows its tools from a hardcoded registry — it *asks the MCP server* what tools exist and calls them across a protocol boundary ([docs/MCP_STUDY_GUIDE.md](docs/MCP_STUDY_GUIDE.md) walks this through your actual code). That is what makes the Pharmacy Agent a reusable service the future Doctor Agent can also call.

---

## 1. The reference architecture (memorize this)

```
Interactive mode ──┐                                    ┌── Headless mode (Week 6)
                   ▼                                    ▼
            ┌──────────────────── AGENT LOOP ──────────────────────┐
   user →   │  LLM  ⇄  Tools   (Action → Observation → Action …)   │
            │         ▲                                            │
            │   Permissions Gate (read-only pass · action = HITL)  │  ← Milestone 2
            └──────────────────────────────────────────────────────┘
                   ▲                        ▲
   Context Window: [ summary + recent tail ]   ← compaction   ← Milestone 3
                   ▲
   Tools come from:  MCP SERVER  (discovered via list_tools)    ← Milestone 1
                   ▲
   Always on:  EVALS & OBSERVABILITY (benchmarks · regressions · prod) ← Milestone 4
```

Everything you build this week snaps into one of these boxes. When you're unsure why a task matters, locate it on this diagram.

---

## 2. Core concepts to master (the learning track)

Your instructor's rule: **whenever you use AI, also read the official docs and understand the concept.** For each concept below: read the doc, then be able to explain it in two sentences without notes. Log every doc you read in the **Learning Log** (§6).

### 2.1 Model Context Protocol (MCP) — the week's centerpiece
- **What to understand:** why MCP exists (tools as a *server* any client can connect to, vs. hardwired into one app); the client↔server handshake (`initialize`); **tool discovery** (`list_tools`); **tool invocation** (`call_tool`); **transports** (you use **stdio** — the client launches the server as a subprocess and talks over stdin/stdout).
- **Be able to answer:** "What is the difference between our MCP *server* (already built) and the MCP *client* I'm building?" and "How does the agent learn what tools exist without me hardcoding them?"
- **Docs:** `modelcontextprotocol.io` (Introduction, **Core concepts → Tools**, **Clients**), the official **Python SDK** (`github.com/modelcontextprotocol/python-sdk` — read the *client* example: `ClientSession`, `stdio_client`, `StdioServerParameters`), and Anthropic's MCP quickstart.

### 2.2 Agent loops & native tool-calling
- **What to understand:** the Action→Observation loop; how the model returns a *structured tool call* (not text you parse); how you execute it and feed the result back as a `tool` message; why you need an **iteration cap**. Then read our existing loop and map every paragraph of the doc onto real lines.
- **Be able to answer:** "Walk me through one full turn of `run_agent` — what goes to the model, what comes back, what happens next?"
- **Docs:** Anthropic **Tool use / function calling** guide; Anthropic engineering post **"Building effective agents"** (read the *agent loop* and *tools* sections). Then: [agent/loop.py](agent/loop.py) lines ~55–137.

### 2.3 Permissions / Human-in-the-Loop (HITL)
- **What to understand:** classify tools as **read-only** (run freely) vs **action** (must pause for explicit human confirmation *before* executing). Why build it now when all tools are read-only? Because the *gate* must exist before Week 6 adds write-tools — you're testing the mechanism against safe tools.
- **Be able to answer:** "Where in the loop does the gate sit, and what exactly does it interrupt?"
- **Docs:** search "LLM agent human-in-the-loop tool approval" pattern; LangGraph's *human-in-the-loop / interrupt* docs are a good conceptual reference **even though we're building it manually**.

### 2.4 Context management & compaction
- **What to understand:** context windows are finite; you can't append forever. The `[summary + recent tail]` pattern: keep the last *N* turns verbatim, compress older turns into a running summary that preserves essentials (which patient, which drugs, what was already flagged). Token budgeting: know roughly how big your history is.
- **Be able to answer:** "What must the summary *never* drop for a pharmacy consult?" (patient identity, drugs discussed, severity findings already surfaced).
- **Docs:** Anthropic **"Effective context engineering" / context management** guidance; the general summarize-older-turns pattern. Ours will be a manual summarization call to the LLM itself.

### 2.5 Evaluation & observability
- **What to understand:** three eval categories — **Benchmarks** (must always pass: the 8 trap patients, multi-hop cases), **Regressions** (nothing that passed may break), **Production-style** (messy, multi-part questions). Observability = every tool call logged as a **trace** (spans) you can inspect and measure. The leap this week: from an in-memory dict to a real **traces + datasets + experiments** platform, and from keyword-substring scoring toward **LLM-as-judge**.
- **Be able to answer:** "What's the difference between a benchmark and a regression run?" and "What does a *trace* capture that a pass/fail score doesn't?"
- **Docs:** **Opik** docs (`comet.com` → Opik → *Tracing*, *Datasets & Experiments*, *LLM-as-a-judge metrics*); `github.com/comet-ml/opik`. Our existing trace ([agent/trace.py](agent/trace.py)) is the natural adapter point.

---

## 3. Milestone-by-milestone build plan (the execution track)

Each milestone lists: the concept → what already exists → **what you build** → **what I scaffold/review** → **done when**. Work them in order; each is a working first version (breadth-first).

### Milestone 1 — Agent loop over the MCP server
**Concept:** the loop discovers tools from the MCP server and calls them across the protocol, instead of an in-process registry.

- **Exists:** the whole loop mechanism ([agent/loop.py](agent/loop.py)), native tool-calling in the provider (`generate_with_tools`), and the MCP server with 10 tools.
- **What you build:**
  1. An **MCP client session** (stdio) that launches `python -m medflow_mcp` and calls `initialize()` → `list_tools()`.
  2. A small **adapter** that converts MCP tool definitions → the tool schema shape `generate_with_tools` expects (mind the naming: MCP tools are `*_tool`-suffixed and SDK-generated; the current hardcoded ones in [agent/tools.py](agent/tools.py) are not — reconcile this).
  3. Replace the in-process `call_tool(...)` dispatch in the loop with an **MCP `session.call_tool(name, arguments)`** round-trip; parse the result back into a `tool` message.
  4. Keep the **iteration cap** and **trace logging** working through the new path.
- **I scaffold/review:** a stubbed `agent/mcp_client.py` with function signatures + `TODO`s and doc pointers; a checklist for the schema/naming reconciliation; review of your session lifecycle (do you close it cleanly? one session per run or reused?).
- **Done when:** the worked example runs end-to-end over MCP —
  *"clarithromycin + simvastatin + warfarin, safe?"* → agent discovers tools via MCP → calls `detect_pairwise_interactions_tool` → reasons → calls `detect_cyp_competition_tool` → answers **severe-finding-first**, every step in the trace.

### Milestone 2 — Agent identity + permissions gate
**Concept:** a clear system identity, and a gate that lets read-only tools through but **pauses action-tools for human confirmation**.

- **Exists:** the identity prompt ([llm/system_prompt.txt](llm/system_prompt.txt) 8 rules + [agent/system_prompt_addendum.txt](agent/system_prompt_addendum.txt)); all 10 tools are read-only.
- **What you build:**
  1. A **tool classification** map: each tool → `read_only` | `action`. (All 10 are `read_only` today — the map is the point.)
  2. A **permission gate** in the loop: before executing a tool, if it's `action`, pause and require explicit confirmation; if `read_only`, proceed. Test it by temporarily marking one tool `action` and watching it pause.
  3. Confirm/refine the **identity**: reasons only from tools, never invents interactions/doses, severe-finding-first, *presents* findings for the pharmacist to evaluate (doesn't command).
- **I scaffold/review:** a `permissions.py` stub (classification map + `requires_confirmation(tool)` + a pluggable `confirm()` callback so it works in both interactive and headless contexts); review that the gate sits *before* execution and that read-only flow is unchanged.
- **Done when:** read-only tools run freely; a tool flagged `action` reliably halts for confirmation before executing; identity behavior verified against a couple of adversarial eval cases.

### Milestone 3 — Context compaction (first version)
**Concept:** keep `[summary + recent tail]`; compress older turns when history grows past a threshold.

- **Exists:** nothing — history grows unbounded, capped only by iterations. This is genuine from-scratch.
- **What you build:**
  1. A **size trigger** (turn count or a rough token estimate) that fires when history exceeds a threshold.
  2. A **summarize step**: send older turns to the LLM with a prompt that preserves essentials (patient, drugs discussed, findings already flagged) and returns a compact block; keep the last *N* turns verbatim; rebuild `messages` as `[system, summary_block, …recent tail]`.
  3. Wire it into the loop so long consults stay coherent.
- **I scaffold/review:** a `context.py` stub (`estimate_size()`, `should_compact()`, `compact(messages)`), plus a summary prompt template to critique; review that compaction never drops a surfaced severity finding.
- **Done when:** a deliberately long multi-drug conversation stays coherent and under budget; before/after `messages` show older turns collapsed into a summary with the tail intact.

### Milestone 4 — Evaluation & observability as a continuous layer
**Concept:** benchmarks + regressions + production-style evals, all logged as traces via **Opik**.

- **Exists:** two structured suites (30 + 25 cases, tiered) with a pytest-integrated **keyword** scorer ([evaluation/agent_eval/runner.py](evaluation/agent_eval/runner.py)); in-memory trace with per-tool timing.
- **What you build:**
  1. **Install + wire Opik** (`pip install opik`, local mode is fine); instrument `run_agent` so every run + every tool call is a logged **trace/span**. Feed the existing `agent/trace.py` data into Opik rather than replacing it.
  2. Organize evals into the **three categories**: Benchmarks (the 8 traps + multi-hop), Regressions (run the full suite after every change — nothing green may go red), Production-style (a few messy, multi-part pharmacist questions you author).
  3. Reach **≥25 agentic scenarios passing**, traces logged, regressions green. *(Stretch, if time: one LLM-as-judge metric to complement keyword scoring.)*
- **I scaffold/review:** an Opik integration stub (init + a `@track`/span wrapper around the loop and tool calls) with doc pointers; a runner flag to emit traces; review of your benchmark/regression split.
- **Done when:** running the agent produces traces visible in Opik; the full suite runs as a regression gate and is green; ≥25 scenarios pass with traces attached.

---

## 4. Suggested weekly shape

Breadth-first — get a thin working version of all four, then deepen. Adjust to your own pace.

- **Day 1 — Learn + M1 start.** Read MCP (§2.1) + agent-loop (§2.2) docs. Read our loop end-to-end. Stub the MCP client; get `initialize()` + `list_tools()` printing the 10 tools.
- **Day 2 — M1 finish.** Swap dispatch to `session.call_tool`; run the worked example over MCP with trace intact.
- **Day 3 — M2.** Read HITL (§2.3). Build the classification map + gate; prove pause-on-action.
- **Day 4 — M3.** Read context (§2.4). Build `should_compact` + `compact`; prove a long consult stays coherent.
- **Day 5 — M4.** Read Opik (§2.5). Wire tracing; organize benchmarks/regressions; get ≥25 passing green with traces.
- **Buffer / stretch:** LLM-as-judge metric; a LangGraph spike for your learning log; reconcile the model-of-record drift (see §7).

---

## 5. Verification — how you prove each piece works

Run from the repo root. Non-live tests **still need Neo4j up** (many DB tests aren't mocked), so start the stack first.

```bash
# 0. Bring up databases (needed by query/ and MCP tools)
docker compose up -d            # Neo4j + PostgreSQL

# 1. Regression baseline BEFORE you change anything (record the number)
python -m pytest -m "not live" -q

# 2. MCP server sanity (Milestone 1 target lives here)
python -m medflow_mcp           # server should start on stdio
#    …and inspect tools visually:
mcp dev medflow_mcp/server.py   # opens the MCP Inspector

# 3. Agent loop over MCP — the worked example (Milestone 1 done-when)
#    drive run_agent with: clarithromycin + simvastatin + warfarin
#    confirm the trace shows detect_pairwise → detect_cyp, severe-first answer

# 4. Live agentic eval suite (Milestone 4) — needs the configured LLM key
python -m evaluation.agent_eval.runner
python -m pytest -m live evaluation/agent_eval -q   # ≥25 scenarios green

# 5. Regression AFTER each change — must match/beat step 1
python -m pytest -m "not live" -q
```

For M2/M3, verification is behavioral: temporarily flag a tool `action` and confirm the loop pauses; run a long multi-drug conversation and diff `messages` before/after compaction.

---

## 6. Learning Log (instructor deliverable — fill the "What I learned" column all week)

Keep this current; it's what you share Friday. Pre-seeded with what this plan will touch.

| Tool / Library / Doc | What it is | Where used this week | Official doc | What I learned |
|---|---|---|---|---|
| **MCP (Model Context Protocol)** | Open standard: tools as a server clients discover | Milestone 1 | modelcontextprotocol.io | _…_ |
| **`mcp` Python SDK — client** | `ClientSession`, `stdio_client`, `list_tools`, `call_tool` | Milestone 1 | github.com/modelcontextprotocol/python-sdk | _…_ |
| **MCP Inspector** (`mcp dev`) | Web GUI to inspect a server's tools | Verification | modelcontextprotocol.io | _…_ |
| **Anthropic tool-use / function-calling** | Structured tool calls from the model | M1 (concept) | docs.anthropic.com | _…_ |
| **"Building effective agents"** | Agent-loop & tool design patterns | M1–M2 (concept) | anthropic.com/engineering | _…_ |
| **HITL / tool-approval pattern** | Pause action-tools for human confirmation | Milestone 2 | (LangGraph interrupt docs, as reference) | _…_ |
| **Context compaction** (`summary + tail`) | Summarize old turns, keep recent verbatim | Milestone 3 | Anthropic context-engineering | _…_ |
| **Opik** (Comet) | LLM tracing + datasets + LLM-as-judge evals | Milestone 4 | comet.com / github.com/comet-ml/opik | _…_ |
| **LangGraph** *(optional spike)* | Framework for agentic loops | Buffer (compare) | langchain-ai.github.io/langgraph | _…_ |
| _(add every other doc/tool you actually open)_ | | | | |

---

## 7. Gotchas & risks the analysis surfaced (read before you start)

1. **Tool-name / schema mismatch.** MCP tools are `*_tool`-suffixed with SDK-generated schemas; the current hardcoded `TOOLS`/`TOOL_REGISTRY` in [agent/tools.py](agent/tools.py) are not. Milestone 1's adapter must reconcile names/args, or tool calls will 404 against the server.
2. **"Not live" ≠ "no infrastructure."** `query/tests`, `medflow_mcp/tests`, and the trap scripts hit **live Neo4j/Postgres unmocked** — they *hang* rather than fail cleanly if the DBs are down. Always `docker compose up -d` first. (There's no `conftest.py`/shared fixtures anywhere — worth noting.)
3. **Model-of-record drift.** `.env` runs **Groq `llama-3.3-70b-versatile`**, but `DEMO_GUIDE.md` / `evaluation/RESULTS.md` describe **Ollama `qwen2.5:7b`**, and [medflow_architecture.md](medflow_architecture.md) still cites qwen. Pick one model for your Week-5 eval baseline and note it, so numbers are comparable.
4. **Temperature inconsistency.** `temperature=0.0` is set only on the Groq/OpenAI *tool* path ([llm/provider.py](llm/provider.py)); the plain `generate()` OpenAI path and both Anthropic paths use provider defaults. If eval numbers wobble, this is a suspect.
5. **Anthropic tool path is mock-tested only** — never run live (no `ANTHROPIC_API_KEY` configured). Groq is the working live path.
6. **Per-call DB connections.** Every query function opens+closes its own Neo4j driver; an agent making many tool calls reconnects each time. Fine for now — just don't be surprised by latency in traces.

---

## 8. Definition of done (the Week 5 checkpoint) — updated 2026-07-31

- [x] **M1** — Agent loop runs **over the MCP server**: tools discovered via `list_tools`, selected/chained autonomously, iteration cap + trace intact. *(Unit-tested with a mocked session — not yet verified against the live server.)*
- [x] **M2** — Clear identity; **permissions gate** forces confirmation on any `action`-class tool (tested via a temporarily-flagged tool; read-only unchanged).
- [x] **M3** — A working **context-compaction** first version (`summary + tail`, threshold 12). *(§9 C2 fixed — compaction now preserves assistant/tool pairing, safe for long live conversations.)*
- [~] **M4** — Observability logging done (custom JSON logger). **Remaining:** run benchmarks/regressions/production-style **live against Groq**, reach **≥25 agentic scenarios green**, and (stretch) add one **LLM-as-judge** metric.
- [ ] **Learning Log** ([docs/LEARNING_LOG.md](docs/LEARNING_LOG.md)) complete and ready to share.

### Remaining, concretely
1. `docker compose up -d`, then run `python -m evaluation.agent_eval.runner` and `python -m evaluation.llm_eval.runner` **live**; record results in `evaluation/RESULTS.md`.
2. Fix any failures surfaced; keep the non-live suite green (`pytest -m "not live" -q`).
3. Address the §9 code-review findings (at least C1–C4).
4. Reconcile the model-of-record drift (§7.3) so the eval baseline is comparable.

---

## 9. Code-review findings — 2026-07-31

Review of the Week 5 changeset (`agent/loop.py`, `agent/permissions.py`, `evaluation/observability.py`, the runners). Ranked; **C = correctness, Q = quality/robustness.** None block the unit tests (which mock the MCP session) — most bite only on the **live path**, which is exactly the remaining M4 work.

> **✅ Resolved 2026-07-31.** All seven findings below were fixed; `agent/tests` + `llm/tests` stay green (**35 passed, 3 skipped**). Fixes: **C1** → `AsyncExitStack` owns the session, closed in the same task; **C2** → compaction walks the tail boundary so it never starts on a `tool` message; **C3** → ASCII confirmation prompt; **C4** → short→MCP name map built dynamically at discovery (static dict removed); **Q5** → cancelled-branch duration set to `0.0`; **Q6** → `getattr` guard on error content; **Q7** → `datetime.now(timezone.utc)`. *(Not yet committed — the team commits manually.)*

| # | Sev | Finding | Where |
|---|---|---|---|
| **C1** | High | **MCP session entered via `__aenter__()` but never `__aexit__()`-ed** — cleanup only closes the raw streams. Skips anyio/subprocess teardown → leaked `server.py` subprocesses (25+ across an eval run) and possible "cancel scope" errors. Fix: use `contextlib.AsyncExitStack` (enter+close in the same task). | [agent/loop.py](agent/loop.py) `_create_mcp_session` L224–242, cleanup L309–315 |
| **C2** | High | **Compaction can split an `assistant(tool_calls)` message from its `tool` results.** If the retained 5-message tail starts on a `role:"tool"` message, the next Groq/OpenAI call 400s ("tool message must follow tool_calls"). Triggers on long live consults (>12 msgs) — the very scenario the feature exists for. Fix: compact on turn boundaries; never start the tail on a `tool` message. | [agent/loop.py](agent/loop.py) `_compact_conversation` L159–219 |
| **C3** | Med | **Emoji in confirmation prompt crashes on Windows cp1252 console** (`⚠️` → `UnicodeEncodeError`). The project already had cp1252 issues. Bites in Week 6 when action tools go live. Fix: ASCII (`[!]`). | [agent/permissions.py](agent/permissions.py) L61 |
| **C4** | Med | **Hardcoded `_SHORT_TO_MCP_NAME` map defeats dynamic discovery.** Add an 11th server tool and the LLM sees it but `call_tool` sends the wrong (unsuffixed) name → tool-not-found. Fix: build the short→MCP map during discovery from the real tool names. | [agent/loop.py](agent/loop.py) L35–46, L417 |
| Q5 | Low | Cancelled-branch `start`/`duration_ms` measures nothing (always ~0). Set `duration_ms = 0.0`. | [agent/loop.py](agent/loop.py) L401–402 |
| Q6 | Low | `_convert_mcp_result` error path assumes `content[0].text` exists (uncaught `AttributeError` if not `TextContent`). | [agent/loop.py](agent/loop.py) L134–138 |
| Q7 | Low | `datetime.utcnow()` deprecated (Py 3.12+). Use `datetime.now(timezone.utc)`. | [evaluation/observability.py](evaluation/observability.py) L58, L71 |

**Not bugs, worth noting:** a fresh MCP subprocess *and* fresh Neo4j driver are created **per question** — fine for a demo, slow for a 25-case suite (and compounds C1). Reusing one session across a batch is a natural Week-6 optimization.
