# MedFlow — System Architecture

This document presents the system architecture of **MedFlow**, illustrating the flow of clinical data from storage layers to the autonomous agent, GraphRAG pipeline, and Model Context Protocol (MCP) clients.

---

## Architecture Diagram (Mermaid)

You can view this diagram directly on GitHub, VS Code, or any Markdown-compatible viewer that supports Mermaid.js:

```mermaid
graph TD
    %% Clients
    subgraph Client Layer
        CD["Claude Desktop Client"]
        MI["MCP Inspector (Web GUI)"]
        HC["HTTP / REST Client (PowerShell/etc.)"]
    end

    %% Interfaces
    subgraph Interface & Gateway Layer
        MCP["FastMCP Server<br/>(medflow_mcp/server.py)"]
        API["FastAPI / Uvicorn Server<br/>(graphrag/server.py)"]
    end

    %% Orchestrators
    subgraph Agent & Orchestration Layer
        AG["Autonomous Agent Loop<br/>(agent/loop.py)"]
        RAG["GraphRAG Ask Pipeline<br/>(graphrag/ask.py)"]
    end

    %% LLM Engine
    subgraph LLM Inference Engine
        PROV["LLM Provider Shim<br/>(llm/provider.py)"]
        OLL["Local Ollama Server<br/>(qwen2.5:7b-instruct)"]
    end

    %% Storage
    subgraph Hybrid Storage Layer (Docker Compose)
        N4J[("Neo4j Graph Database<br/>(Clinical Knowledge & Rules)")]
        PG[("PostgreSQL Database<br/>(Patients, Doses & Audit Logs)")]
    end

    %% Data Loaders
    subgraph Data Loading Layer
        LDR["Database Loaders<br/>(run_loaders.py)"]
        GLDR["Graph Loaders<br/>(run_loaders_graph.py)"]
        RAW["Clinical Data Sources<br/>(db/data/)"]
    end

    %% Connections
    CD -->|MCP Standard Protocol| MCP
    MI -->|MCP Standard Protocol| MCP
    HC -->|HTTP API Requests| API
    
    API -->|Route: /ask| RAG
    API -->|Route: /agent/ask| AG
    
    AG <-->|Multi-turn Tool Selection| PROV
    RAG -->|Single Context Injection| PROV
    PROV <-->|OpenAI API v1 Compat| OLL
    
    MCP -->|Exposes 10 Safety Tools| N4J
    AG -->|Executes Query Engines| N4J
    AG -->|Queries Biological Data| PG
    RAG -->|Fetches Clinical Context| N4J
    
    RAW --> LDR
    RAW --> GLDR
    LDR --> PG
    GLDR --> N4J
```

---

## Layer Definitions

1. **Client Layer:** The user interfaces. The system supports direct REST requests as well as standard model clients (like Claude Desktop) using the Model Context Protocol (MCP).
2. **Interface & Gateway Layer:** Exposes system endpoints. Uvicorn hosts the FastAPI server, while FastMCP handles the standardized MCP stdio connections.
3. **Agent & Orchestration Layer:** The reasoning core. The Agent loop executes multiple tool queries sequentially to evaluate complex prescriptions, while the GraphRAG pipeline performs direct single-shot context retrieval.
4. **LLM Inference Engine:** Connects the system to the local `qwen2.5:7b-instruct` model running via Ollama at `temperature=0.0`.
5. **Hybrid Storage Layer:** Hosted via Docker. Neo4j manages complex clinical connections (drug classes, CYP paths, allergy groups), and Postgres tracks structured patient information and lab variables.
6. **Data Loading Layer:** Script loaders that parse and ingest raw CSV/HTML/JSON clinical records into PostgreSQL and Neo4j.
