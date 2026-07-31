# Learning Log — Tools, Frameworks & Documentation

> **Instructor deliverable.** A running record of every tool, framework, library, platform, and doc I used or read this week. As your instructor asked: I use AI to move faster, *and* I read the official docs to understand the concepts behind the code. Fill the **"What I learned"** column in your own words as you go — that column is the point.
>
> Keep adding rows as you open new things. Send this at the end of the week.

---

## 1. Videos watched

| # | Title | Link | Topic | What I learned (fill in) |
|---|---|---|---|---|
| V1 | MCP Explained — Model Context Protocol — MCP Server vs MCP Host vs MCP Client | https://youtu.be/1q1J3Fu8ZgA | The three MCP roles (server / host / client) and how they relate | _…_ |
| V2 | Model Context Protocol (MCP) Explained for Beginners: AI Flight Booking Demo | https://youtu.be/E2DEHOEbzks | Beginner intro to MCP via a practical flight-booking demo | _…_ |
| V3 | Model Context Protocol (MCP) Explained in 20 Minutes | https://www.youtube.com/watch?v=N3vHJcHBS-w | Concise end-to-end overview of MCP | _…_ |

---

## 2. Official documentation read

| # | Resource | Link | Why it mattered / where used | What I learned (fill in) |
|---|---|---|---|---|
| D1 | **MCP** — Introduction & Core Concepts (Tools, Clients) | https://modelcontextprotocol.io | The protocol the whole agent loop is built on (Milestone 1) | _…_ |
| D2 | **MCP** — For Client Developers (Python quickstart) | https://modelcontextprotocol.io/quickstart/client | The exact `ClientSession` + `stdio_client` pattern in `agent/loop.py` | _…_ |
| D3 | **MCP Python SDK** (source + examples) | https://github.com/modelcontextprotocol/python-sdk | `ClientSession`, `stdio_client`, `StdioServerParameters`, `FastMCP` | _…_ |
| D4 | **MCP Specification** — lifecycle & tools | https://modelcontextprotocol.io/specification | The JSON-RPC messages behind initialize / list_tools / call_tool | _…_ |
| D5 | **Anthropic** — Tool use (function calling) | https://docs.anthropic.com/en/docs/build-with-claude/tool-use | How the model returns structured tool calls (`generate_with_tools`) | _…_ |
| D6 | **Groq** — Tool use / function calling | https://console.groq.com/docs/tool-use | Our live provider is Groq (`llama-3.3-70b-versatile`) | _…_ |
| D7 | **Python** — `asyncio` | https://docs.python.org/3/library/asyncio.html | Why the loop is async and how `asyncio.run()` bridges sync→async | _…_ |

---

## 3. Suggested further reading (curated — open the ones relevant to your milestone)

Prioritized. The ⭐ ones are highest-value for this week.

### MCP & agents (Milestone 1)
| Resource | Link | Why it's worth your time |
|---|---|---|
| ⭐ Anthropic — **Introducing the Model Context Protocol** | https://www.anthropic.com/news/model-context-protocol | The origin/"why" of MCP in 5 min — great for your understanding + demo narrative |
| ⭐ Anthropic — **Building Effective Agents** | https://www.anthropic.com/engineering/building-effective-agents | The canonical agent-loop patterns (tools, the loop, when *not* to use a framework) |
| DeepLearning.AI — **MCP: Build Rich-Context AI Apps with Anthropic** (free short course) | https://www.deeplearning.ai/short-courses/ | Hands-on MCP client+server course; reinforces exactly what you built |
| `anyio` docs | https://anyio.readthedocs.io | MCP's stdio client runs on anyio task scopes — explains the async-lifecycle subtleties in `_create_mcp_session` |

### Permissions / Human-in-the-Loop (Milestone 2)
| Resource | Link | Why |
|---|---|---|
| LangGraph — **Human-in-the-loop** concepts | https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/ | Reference for the *pattern* even though your gate is hand-built (`agent/permissions.py`) |

### Context management (Milestone 3)
| Resource | Link | Why |
|---|---|---|
| ⭐ Anthropic — **Effective context engineering for AI agents** | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | The `summary + recent tail` idea your `_compact_conversation` implements |

### Evaluation & observability (Milestone 4)
| Resource | Link | Why |
|---|---|---|
| ⭐ **Opik** (Comet) — tracing, datasets, LLM-as-judge | https://www.comet.com/docs/opik/ | The platform the Week-5 brief named. Your team chose a **custom JSON logger** (`evaluation/observability.py`) instead — read Opik to understand *what you traded away* (a UI, LLM-judge metrics, run comparison) and be able to justify the choice |
| LangSmith — evaluation & tracing | https://docs.smith.langchain.com | Alternative observability platform, for comparison |
| Anthropic — **building evals / LLM-as-judge** guidance | https://docs.anthropic.com/en/docs/test-and-evaluate | Moving beyond keyword-substring scoring (your current scorer) |

### Optional / comparison (buffer)
| Resource | Link | Why |
|---|---|---|
| LangGraph | https://langchain-ai.github.io/langgraph/ | The framework alternative to your hand-built loop — good to spike & compare |
| `langchain-mcp-adapters` | https://github.com/langchain-ai/langchain-mcp-adapters | Shows how a framework auto-wires MCP tools into a LangGraph agent |

---

## 4. Tools & platforms used (not docs — actual tooling)

| Tool | What it's for | Where in the project |
|---|---|---|
| **`mcp` Python SDK** (`>=1.25`) | MCP server (`FastMCP`) **and** client (`ClientSession`) | `medflow_mcp/server.py`, `agent/loop.py` |
| **MCP Inspector** (`mcp dev`) | Web GUI to inspect/call a server's tools by hand | Verification / debugging |
| **Groq API** (`openai` SDK) | The live LLM provider (function-calling) | `llm/provider.py` |
| **Neo4j** + **Docker Compose** | Graph DB the tools query; started via `docker compose up -d` | `query/`, `docker-compose.yml` |
| **pytest** | Test + eval harness (`-m "not live"` vs `-m live`) | `*/tests/`, `evaluation/` |
| **draw.io** | Architecture diagram | `docs/medflow_architecture.drawio` |

---

## 5. How I used AI this week (for the instructor)

- Used an AI assistant to **analyze the codebase**, **explain the MCP concepts**, and **scaffold/review** — not to blindly generate the final code.
- For every concept, I also read the **official doc** listed above and can explain it in my own words (see `docs/MCP_STUDY_GUIDE.md` self-check questions).
- _(Add your own honest notes here: where AI helped, where you had to read docs to actually understand, what you'd do differently.)_
