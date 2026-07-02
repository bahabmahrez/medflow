"""
Pipeline unit tests.  Graph queries and LLM generate() are mocked so these
tests run without Neo4j or an API key.  They verify:
  - drug extraction logic (stop-word filtering, bigram/unigram)
  - context assembly (right sections included, right drugs checked)
  - risk_level inference (severity -> HIGH/MEDIUM/LOW)
  - error handling (empty question, graph down, LLM down)
  - FastAPI contract (status codes, response shape)

Live end-to-end tests (real graph + real LLM) are marked @pytest.mark.live.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ── Shared mock builders ───────────────────────────────────────────────────────

def _ok_resolve(inn: str):
    return {"status": "found", "data": {"canonical": inn, "inn": inn}, "message": ""}

def _not_found_resolve():
    return {"status": "not_found", "data": {}, "message": "not found"}

def _ix_result(pairs, interactions=None):
    interactions = interactions or []
    return {
        "status": "found" if interactions else "not_found",
        "data": {
            "drugs_resolved":     [p for p in pairs],
            "drugs_unresolved":   [],
            "pairs_checked":      1,
            "interactions_found": len(interactions),
            "interactions":       interactions,
        },
        "message": "",
    }

def _cyp_result(competitions=None):
    competitions = competitions or []
    return {
        "status": "found" if competitions else "not_found",
        "data": {
            "drugs_resolved":    [],
            "drugs_unresolved":  [],
            "competitions_found": len(competitions),
            "competitions":      competitions,
        },
        "message": "",
    }


# ── extract_drugs ──────────────────────────────────────────────────────────────

def test_extract_drugs_finds_two_drugs():
    """Tokens that resolve should be returned as INNs."""
    side_effects = {
        "warfarin": _ok_resolve("warfarin"),
        "amiodarone": _ok_resolve("amiodarone"),
    }
    def fake_resolve(name):
        return side_effects.get(name, _not_found_resolve())

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve):
        from graphrag.pipeline import extract_drugs
        drugs = extract_drugs("Can I give warfarin with amiodarone?")
    assert set(drugs) == {"warfarin", "amiodarone"}


def test_extract_drugs_deduplicates():
    """Brand and INN resolving to same INN should appear once."""
    def fake_resolve(name):
        if name in ("warfarin", "coumadin"):
            return _ok_resolve("warfarin")
        return _not_found_resolve()

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve):
        from graphrag.pipeline import extract_drugs
        drugs = extract_drugs("Is warfarin the same as Coumadin?")
    assert drugs == ["warfarin"]


def test_extract_drugs_ignores_stop_words():
    """Common words ('give', 'patient', 'safe') must not hit the graph."""
    calls = []
    def tracking_resolve(name):
        calls.append(name)
        return _not_found_resolve()

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=tracking_resolve):
        from graphrag.pipeline import extract_drugs
        extract_drugs("give safe patient")
    assert calls == [], f"stop words triggered resolve calls: {calls}"


def test_extract_drugs_empty_text():
    with patch("graphrag.pipeline.resolve_drug_name", return_value=_not_found_resolve()):
        from graphrag.pipeline import extract_drugs
        assert extract_drugs("") == []



# ── ask() structure ────────────────────────────────────────────────────────────

def test_ask_empty_question_no_graph_call():
    """Empty question must return immediately without hitting graph or LLM."""
    with patch("graphrag.pipeline.resolve_drug_name") as mock_resolve, \
         patch("graphrag.pipeline.generate") as mock_gen:
        from graphrag.pipeline import ask
        r = ask("   ")
    mock_resolve.assert_not_called()
    mock_gen.assert_not_called()
    assert r["answer"] == "Please provide a question."
    assert r["drugs_detected"] == []


def test_ask_no_drugs_found():
    """When no drugs are detected the LLM is still called with a no-drug context."""
    with patch("graphrag.pipeline.resolve_drug_name", return_value=_not_found_resolve()), \
         patch("graphrag.pipeline.generate", return_value="Not in knowledge base.") as mock_gen:
        from graphrag.pipeline import ask
        r = ask("What is the meaning of life?")
    assert r["drugs_detected"] == []
    assert mock_gen.called
    assert "No known drug names" in r["context"]


def test_ask_returns_correct_structure():
    """ask() return dict must always have the four required keys."""
    def fake_resolve(name):
        return _ok_resolve(name) if name == "warfarin" else _not_found_resolve()

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value=_ix_result(["warfarin"])), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value=_cyp_result()), \
         patch("graphrag.pipeline.generate", return_value="Use with precaution."):
        from graphrag import ask
        r = ask("Tell me about warfarin and aspirin")
    assert "answer"         in r
    assert "drugs_detected" in r
    assert "context"        in r
    assert "risk_level"     in r


def test_ask_risk_level_high_for_contre_indique():
    """contre_indique severity must produce risk_level='HIGH'."""
    def fake_resolve(name):
        if name in ("warfarin", "amiodarone"):
            return _ok_resolve(name)
        return _not_found_resolve()

    interaction = {
        "drug_a": "warfarin", "drug_b": "amiodarone",
        "severity": "contre_indique", "effect": "INR elevation",
        "mechanism": "CYP2C9 inhibition", "source": "ANSM",
    }

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value=_ix_result(["warfarin", "amiodarone"], [interaction])), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value=_cyp_result()), \
         patch("graphrag.pipeline.generate", return_value="CONTRAINDICATED."):
        from graphrag import ask
        r = ask("Can I prescribe amiodarone with warfarin?")
    assert r["risk_level"] == "HIGH"


def test_ask_risk_level_medium_for_moderate():
    def fake_resolve(name):
        return _ok_resolve(name) if name in ("metoprolol", "diltiazem") else _not_found_resolve()

    interaction = {
        "drug_a": "metoprolol", "drug_b": "diltiazem",
        "severity": "moderate", "effect": "bradycardia",
        "mechanism": "additive", "source": "ANSM",
    }

    with patch("graphrag.pipeline.extract_drugs", return_value=["metoprolol", "diltiazem"]), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value=_ix_result(["metoprolol", "diltiazem"], [interaction])), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value=_cyp_result()), \
         patch("graphrag.pipeline.generate", return_value="Monitor."):
        from graphrag import ask
        r = ask("metoprolol with diltiazem")
    assert r["risk_level"] == "MEDIUM"


def test_ask_risk_level_high_for_strong_cyp_inhibition():
    """Strong CYP inhibition in detect_cyp_competition must set risk=HIGH."""
    def fake_resolve(name):
        return _ok_resolve(name) if name in ("simvastatin", "clarithromycin") else _not_found_resolve()

    competition = {
        "substrate": "simvastatin", "modulator": "clarithromycin",
        "enzyme": "CYP3A4", "effect": "INHIBITS", "strength": "strong",
        "risk": "simvastatin accumulation risk",
    }

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value=_ix_result(["simvastatin", "clarithromycin"])), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value=_cyp_result([competition])), \
         patch("graphrag.pipeline.generate", return_value="HIGH risk via CYP3A4."):
        from graphrag import ask
        r = ask("Is simvastatin safe with clarithromycin?")
    assert r["risk_level"] == "HIGH"


def test_ask_context_contains_interaction_section():
    """The assembled context must include the PAIRWISE INTERACTIONS header."""
    def fake_resolve(name):
        return _ok_resolve(name) if name in ("warfarin", "aspirin") else _not_found_resolve()

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value=_ix_result(["warfarin", "aspirin"])), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value=_cyp_result()), \
         patch("graphrag.pipeline.generate", return_value="answer"):
        from graphrag import ask
        r = ask("warfarin and aspirin")
    assert "PAIRWISE INTERACTIONS" in r["context"]
    assert "CYP ENZYME COMPETITION" in r["context"]


def test_ask_graph_down_returns_error():
    """If the graph raises during extraction, ask() returns an error response."""
    with patch("graphrag.pipeline.extract_drugs",
               side_effect=Exception("Connection refused")):
        from graphrag import ask
        r = ask("warfarin with amiodarone")
    assert "error" in r
    assert r["drugs_detected"] == []


def test_ask_llm_down_returns_error():
    """If generate() raises, ask() returns a partial result with error key."""
    def fake_resolve(name):
        return _ok_resolve(name) if name in ("warfarin", "aspirin") else _not_found_resolve()

    with patch("graphrag.pipeline.resolve_drug_name", side_effect=fake_resolve), \
         patch("graphrag.pipeline.detect_pairwise_interactions",
               return_value=_ix_result(["warfarin", "aspirin"])), \
         patch("graphrag.pipeline.detect_cyp_competition",
               return_value=_cyp_result()), \
         patch("graphrag.pipeline.generate",
               side_effect=Exception("API rate limit")):
        from graphrag import ask
        r = ask("warfarin with aspirin")
    assert "error" in r
    assert r["context"] != ""   # context was built; LLM failed after


# ── FastAPI server ─────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from graphrag.server import app
    return TestClient(app)


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ask_endpoint_returns_200(client):
    """POST /ask with a mocked pipeline must return 200 and the expected shape."""
    mock_result = {
        "answer":         "This is CONTRAINDICATED.",
        "drugs_detected": ["warfarin", "amiodarone"],
        "context":        "...",
        "risk_level":     "HIGH",
    }
    with patch("graphrag.server.ask", return_value=mock_result):
        r = client.post("/ask", json={"question": "warfarin + amiodarone?"})
    assert r.status_code == 200
    body = r.json()
    assert body["risk_level"] == "HIGH"
    assert "warfarin" in body["drugs_detected"]


def test_ask_endpoint_rejects_empty_question(client):
    r = client.post("/ask", json={"question": "   "})
    assert r.status_code == 422   # FastAPI validation error


def test_ask_endpoint_accepts_patient_context(client):
    mock_result = {
        "answer":         "Dose adjustment required.",
        "drugs_detected": ["metformin"],
        "context":        "...",
        "risk_level":     "HIGH",
    }
    with patch("graphrag.server.ask", return_value=mock_result) as mock_ask:
        r = client.post("/ask", json={
            "question":   "Is metformin safe?",
            "conditions": ["CKD stage 4"],
            "age":        72,
        })
    assert r.status_code == 200
    call_kwargs = mock_ask.call_args
    assert call_kwargs.kwargs["conditions"] == ["CKD stage 4"]
    assert call_kwargs.kwargs["age"] == 72


# ── Live end-to-end (requires Neo4j + ANTHROPIC_API_KEY) ──────────────────────

@pytest.mark.live
def test_live_warfarin_amiodarone_high_risk():
    """Real graph + real LLM: the answer must mention the contraindication."""
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from graphrag import ask
    r = ask("Can I prescribe amiodarone to a patient already taking warfarin?")
    assert r["risk_level"] == "HIGH"
    assert "warfarin" in r["drugs_detected"]
    assert "amiodarone" in r["drugs_detected"]
    lower = r["answer"].lower()
    assert any(w in lower for w in ("contraindicated", "contre-indiqué", "not recommended"))


@pytest.mark.live
def test_live_simvastatin_clarithromycin_cyp():
    """No direct DDI edge — must be caught via CYP3A4 competition."""
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from graphrag import ask
    r = ask("Is simvastatin safe with clarithromycin?")
    assert r["risk_level"] == "HIGH"
    assert "simvastatin" in r["drugs_detected"]
    assert "CYP" in r["context"]
