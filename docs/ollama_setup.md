# MedFlow — Local LLM Setup with Ollama

> How to run the MedFlow LLM locally using Ollama, replacing the free-tier API keys that were insufficient for the team's needs.

---

## Why Ollama?

The project originally used Groq and Anthropic free-tier API keys. These hit rate limits and quota caps almost immediately — impossible for running 55 evaluation cases or developing iteratively. Ollama runs a local LLM on your machine with no API keys, no rate limits, and no internet dependency.

---

## Prerequisites

- **RAM:** 8 GB minimum (16 GB recommended)
- **Disk:** ~5 GB free for the model
- **Docker Desktop:** running (for PostgreSQL and Neo4j)
- **Python venv:** activated with `pip install -r requirements.txt` done

---

## 1. Install Ollama

Download and install from: **https://ollama.com**

Run the installer. After installation, verify it's running:

```powershell
ollama --version
```

You should see a version number (e.g. `ollama version 0.6.x`).

---

## 2. Pull the model

MedFlow uses **qwen2.5:7b-instruct** — a 7B-parameter instruction-tuned model that runs well on consumer hardware.

```powershell
ollama pull qwen2.5:7b-instruct
```

This downloads ~4.7 GB. Wait for it to finish.

Verify the model is available:

```powershell
ollama list
```

You should see `qwen2.5:7b-instruct` in the list.

---

## 3. Verify Ollama is serving

Ollama runs an OpenAI-compatible API on `http://localhost:11434`. Test it:

```powershell
curl http://localhost:11434/v1/models
```

You should get a JSON response listing the available models.

---

## 4. Configure `.env`

The `.env` file at the project root should contain these lines:

```
LLM_PROVIDER=openai
LLM_MODEL=qwen2.5:7b-instruct
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
```

**What each line means:**

| Variable | Value | Why |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Tells the code to use the OpenAI-compatible SDK path. Ollama speaks the same API format as OpenAI. |
| `LLM_MODEL` | `qwen2.5:7b-instruct` | The model Ollama will serve. Must match what you pulled in step 2. |
| `OPENAI_BASE_URL` | `http://localhost:11434/v1` | Points the OpenAI SDK at Ollama instead of OpenAI's servers. |
| `OPENAI_API_KEY` | `ollama` | Dummy value. Ollama doesn't need a real key, but the SDK requires one to be set. |

**Do NOT commit your `.env` file to Git.** It's in `.gitignore`.

---

## 5. Start everything

```powershell
# 1. Start databases
docker compose up -d

# 2. Load data into PostgreSQL
python run_loaders.py

# 3. Initialize Neo4j schema
python db\graph\init_graph.py

# 4. Load data into Neo4j
python run_loaders_graph.py

# 5. Quick smoke test — ask a clinical question
python -c "
from graphrag import ask
r = ask('Is it safe to give warfarin and aspirin together?')
print(r['answer'][:300])
"
```

If you get a coherent clinical answer about the warfarin-aspirin interaction, everything is working.

---

## 6. Alternative models

If `qwen2.5:7b-instruct` doesn't perform well on evaluations, you can swap the model:

```powershell
# Pull an alternative
ollama pull llama3.1:8b-instruct
```

Then update `.env`:
```
LLM_MODEL=llama3.1:8b-instruct
```

**Model comparison (rough guide):**

| Model | Size | RAM needed | Tool-calling | Clinical reasoning |
|---|---|---|---|---|
| `qwen2.5:7b-instruct` | 4.7 GB | 8 GB | Good | Decent |
| `llama3.1:8b-instruct` | 4.7 GB | 8 GB | Good | Good |
| `mistral:7b-instruct` | 4.1 GB | 8 GB | Moderate | Moderate |
| `qwen2.5:14b-instruct` | 9 GB | 16 GB | Very good | Very good |

For the evaluation suite, **stick with qwen2.5:7b-instruct** first so we have a consistent baseline. Switch only if results clearly show the model is too weak.

---

## Troubleshooting

**"Connection refused" when running the smoke test:**
Ollama isn't running. Start it manually — on Windows it usually runs as a system tray app. Open the Ollama app and try again.

**Model not found:**
Run `ollama list` to see what's installed. If the model isn't there, run `ollama pull qwen2.5:7b-instruct` again.

**Slow responses (30+ seconds per question):**
Normal for a 7B model on CPU-only. If you have an NVIDIA GPU, install the CUDA toolkit — Ollama will automatically use it and responses will be 5-10x faster.

**Port 11434 already in use:**
Another process is using the port. Run `netstat -ano | findstr :11434` to find it, or restart Ollama.

**"Rate limit" errors during evaluation:**
These are false positives — the evaluation runner treats certain error messages as rate limits. Ollama doesn't rate-limit, but if the model crashes under load, the error text might match. Check the actual error message.

---

## How provider switching works

The code in `llm/provider.py` supports three providers through a single interface:

```
LLM_PROVIDER=anthropic  →  Uses Anthropic SDK (requires ANTHROPIC_API_KEY)
LLM_PROVIDER=openai     →  Uses OpenAI SDK (reads OPENAI_BASE_URL + OPENAI_API_KEY)
LLM_PROVIDER=groq       →  Uses OpenAI SDK pointed at Groq's API
```

Ollama works because it speaks the OpenAI API format. Setting `LLM_PROVIDER=openai` with `OPENAI_BASE_URL=http://localhost:11434/v1` makes the OpenAI SDK talk to Ollama transparently. No code changes needed — just environment variables.
