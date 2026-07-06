"""
MedFlow GraphRAG API server.

Start with:
    python -m uvicorn graphrag.server:app --reload --port 8000

Endpoints:
    GET  /health    — liveness check
    POST /ask       — full GraphRAG pipeline
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from .pipeline import ask
from agent import run_agent

app = FastAPI(
    title="MedFlow GraphRAG API",
    description=(
        "Drug interaction and safety checks powered by a Neo4j knowledge graph "
        "and an LLM that explains only what the graph retrieved."
    ),
    version="0.3.0",
)


# ── Request / Response models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    question:    str
    conditions:  list[str] = []
    allergies:   list[str] = []
    active_meds: list[str] = []
    age:         int   | None = None
    weight:      float | None = None
    labs:        dict        = {}

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("question must not be empty")
        return v.strip()


class AskResponse(BaseModel):
    answer:         str
    drugs_detected: list[str]
    context:        str
    risk_level:     str | None = None
    error:          str | None = None


class AgentAskRequest(BaseModel):
    question:        str
    patient_context: dict | None = None
    max_iterations:  int = 8

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("question must not be empty")
        return v.strip()


class AgentAskResponse(BaseModel):
    final_answer: str
    trace:        dict


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "MedFlow GraphRAG"}


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest) -> AskResponse:
    result = ask(
        req.question,
        conditions=req.conditions  or None,
        allergies=req.allergies    or None,
        active_meds=req.active_meds or None,
        age=req.age,
        weight=req.weight,
        labs=req.labs or None,
    )
    if result.get("error") and not result.get("answer"):
        raise HTTPException(status_code=503, detail=result["error"])
    return AskResponse(**result)


@app.post("/agent/ask", response_model=AgentAskResponse)
def agent_ask_endpoint(req: AgentAskRequest) -> AgentAskResponse:
    try:
        result = run_agent(
            req.question,
            patient_context=req.patient_context,
            max_iterations=req.max_iterations,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return AgentAskResponse(**result)
