# MedFlow — Implementation TODO

## Step 1: Rewire Agent Loop over MCP
- [x] Create `agent/permissions.py` — Permission classification + HITL confirmation
- [x] Rewrite `agent/loop.py` — MCP client connection, dynamic tool discovery, permission gate
- [x] Update `agent/__init__.py` — Export permissions module
- [x] Update `agent/tests/test_loop.py` — Adapt mocks for MCP-based execution

## Step 2: Permissions Layer (Priority Gate / HITL)
- [x] Included in `agent/permissions.py` + wired into loop
- [x] Test: `test_read_only_tool_executes_immediately_without_confirmation` ✅
- [x] Test: `test_action_tool_requires_confirmation_and_cancels_if_rejected` ✅

## Step 3: Context Compaction
- [x] Added compaction logic to `agent/loop.py` — summary + recent tail structure
- [x] Test: `test_context_compaction_triggers_at_threshold` ✅

## Step 4: Run Evals Live + Add Observability
- [x] Create `evaluation/observability.py` — Lightweight JSON trace logger
- [ ] Run agent eval suite live against Groq API (requires DB + API key)
- [ ] Run LLM eval suite live against Groq API (requires DB + API key)
- [ ] Fix any failures surfaced

## Cleanup
- [x] Delete `knowledge_base/DB_loaders/load_cyp_local.py`
- [x] Create `evaluation/cleanup_brands.py` — script to fix Kardegic/Depakine

## Verification
- [x] Run agent unit tests: `python -m pytest agent/tests/ -v` — **20/20 passed** ✅
- [x] Run agent + LLM tests: `python -m pytest agent/tests/ llm/tests/ -v` — **35 passed, 3 skipped** ✅
- [ ] Run full test suite: `python -m pytest -m "not live" -q` (requires DB running)

