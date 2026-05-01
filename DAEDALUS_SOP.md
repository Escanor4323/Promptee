# Daedalus (Promptee) — Phase-Driven Development SOP

> Codename: **Daedalus** | Product: **Promptee** — Local MLOps & RAG CLI
> Architecture: **Dual-Stack Monorepo** (Go CLI + Python FastAPI Backend)
> Local Orchestration: **Bash Daemon** (`start_promptee.sh`)

---

## System Overview

Promptee is a local-first MLOps tool that stores markdown prompt templates in a Milvus vector database, recommends them via semantic + telemetry-weighted search, and presents them through a compiled Go CLI. All services run locally — no cloud dependencies.

```
┌──────────────────────────────────────────────────────┐
│                   start_promptee.sh                  │
│            (Bash Daemon / Orchestrator)               │
│                                                      │
│  ┌─────────────┐     ┌──────────────┐               │
│  │  Milvus     │     │  FastAPI     │               │
│  │  Standalone │◄────│  Uvicorn     │               │
│  │  (Docker)   │     │  (Python)    │               │
│  └─────────────┘     └──────┬───────┘               │
│                             │                        │
│                       /api/v1/*                      │
│                             │                        │
│                      ┌──────▼───────┐               │
│                      │  Go CLI      │               │
│                      │  (Cobra)     │               │
│                      └──────────────┘               │
└──────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
Promptee/
├── cmd/                        # Go CLI entrypoints
│   └── promptee/               # main.go
├── internal/                   # Go internal packages
│   ├── api/                    # HTTP client for FastAPI
│   ├── prompt/                 # Prompt display & variable parsing
│   ├── telemetry/              # Execution timer & feedback collector
│   └── daemon/                 # Daemon health-check & launcher
├── pkg/                        # Go public packages (if needed)
├── backend/                    # Python FastAPI microservice
│   ├── app/
│   │   ├── main.py             # FastAPI app factory
│   │   ├── config.py           # pydantic-settings configuration
│   │   ├── models/             # SQLAlchemy + Pydantic models
│   │   │   ├── templates.py
│   │   │   ├── executions.py
│   │   │   └── feedback.py
│   │   ├── routers/            # API route handlers
│   │   │   ├── health.py
│   │   │   ├── ingest.py
│   │   │   ├── recommend.py
│   │   │   └── telemetry.py
│   │   ├── services/           # Business logic
│   │   │   ├── chunker.py      # Schema-aware structural chunking
│   │   │   ├── embedder.py     # Dual-vector embedding logic
│   │   │   ├── reranker.py     # Hybrid search + telemetry reranking
│   │   │   └── addon.py        # PromptAddOn injection module
│   │   └── db/                 # Database connections
│   │       ├── milvus.py       # Milvus client & collection schema
│   │       └── sqlite.py       # SQLite engine & session factory
│   ├── alembic/                # SQLite migrations
│   ├── tests/                  # pytest suites (80%+ coverage)
│   ├── requirements.txt
│   └── Dockerfile
├── docker/                     # Docker Compose for Milvus
│   └── docker-compose.milvus.yml
├── prompts/                    # Markdown prompt templates (source data)
├── scripts/
│   └── start_promptee.sh       # Bash daemon orchestrator
├── .env.example                # Environment variable schema
├── go.mod
├── go.sum
├── pyproject.toml
├── Makefile
└── README.md
```

---

## Phase 1: Architecture & Repository Scaffolding

**Objective:** Initialize the dual-stack monorepo, set up the Bash orchestrator, and configure the foundational routing for the CLI and backend.

**Task:** Initialize a dual-stack monorepo with strict version control, define the project structure, and scaffold the Bash orchestrator.

**Tools:** `senior-devops`, `spec-driven-workflow`

**Details:** The project is Promptee (Codename: Daedalus), a local MLOps and RAG CLI. The repository will contain a Golang frontend (CLI) and a Python backend (FastAPI). All services must be orchestrated locally via a `start_promptee.sh` Bash daemon.

**Execution Steps (Sequential):**
1. Generate the standard repository directory tree separating the Go CLI and Python microservice.
2. Write the `start_promptee.sh` script to silently initialize a Milvus Standalone instance via Docker Compose and start the FastAPI Uvicorn server in the background.
3. Ensure the script includes a health-check loop that prevents the Go CLI from executing until the `/api/v1/health` endpoint returns a `200 OK` status.

**Optional Deliverable:** Output a `.env` schema for `pydantic-settings` to manage local configurations for internal memory.

**Status:** ✅ Complete

---

## Phase 2: RAG Engine & Data Engineering

**Objective:** Build the FastAPI microservice, implement schema-aware chunking, and configure the Milvus vector database for ingestion.

**Task:** Architect and deploy a local FastAPI microservice for document ingestion, schema-aware chunking, and Milvus vector storage.

**Tools:** `rag-architect`, `senior-ml-engineer`, `senior-backend`

**Details:** The backend must ingest markdown prompt templates into a local Milvus vector database using `sentence-transformers/all-MiniLM-L6-v2` for embeddings.

**Execution Steps (Sequential):**
1. Implement "Schema-Aware Structural Chunking" using Regex Positive Lookaheads to slice markdown documents precisely at template boundaries (e.g., `### 1. Title`), guaranteeing exactly one prompt per chunk.
2. Write the dual-vector embedding logic: embed ONLY the Title and Objective strings into the vector space, while storing the full, unbroken prompt text and dynamically extracted `[VARIABLES]` as metadata payloads.
3. Build the `/api/v1/ingest` and `/api/v1/recommend` FastAPI endpoints.

**Optional Deliverable:** Output the Python Regex extraction logic and the complete Milvus Collection Schema configuration for internal memory.

**Status:** ✅ Complete

---

## Phase 3: Telemetry & Relational DB Integration

**Objective:** Design the local MLOps tracking layer using SQLite to capture execution metrics and human-in-the-loop feedback.

**Task:** Design and integrate a local relational database to capture execution telemetry and human-in-the-loop quality feedback.

**Tools:** `database-designer`, `sql-database-assistant`

**Details:** The FastAPI backend must log historical execution data mapped to Milvus vector IDs using SQLite. The core **[METRICS]** to track are Latency, Token Usage, Context Window Utilization (%), Verbosity, and Quality Score (1-5 stars).

**Execution Steps (Sequential):**
1. Design the SQLite schema with tables for Templates, Executions, and Feedback.
2. Write the SQLAlchemy (or raw SQL) models to intercept and log these specific **[METRICS]** post-execution.
3. Map these metrics to core developer tradeoffs: **SPEED** (low latency/tokens), **COST** (low input/output tokens), and **QUALITY** (high user feedback scores).
4. Create a new API route specifically to accept post-execution telemetry from the Go CLI.

**Optional Deliverable:** Output the Entity-Relationship Diagram (ERD) mapping the Milvus vector entities to the SQLite telemetry tables for internal memory.

**Status:** ✅ Complete

---

## Phase 4: Hybrid Reranking & PromptAddOn Module

**Objective:** Upgrade the retrieval pipeline to mathematically rerank prompts based on historical data and inject modular PromptAddOns.

**Task:** Implement a mathematical hybrid reranking algorithm and scaffold the dynamic PromptAddOn injection module.

**Tools:** `senior-data-scientist`, `rag-architect`

**Details:** The retrieval pipeline must evaluate semantic matches from Milvus against historical telemetry data in SQLite to boost scores based on developer **[TRADEOFFS]**. It must also support **[ADDONS]**—modular, metric-aligned suffixes dynamically injected into the base payload.

**Execution Steps (Sequential):**
1. Write the Python hybrid search algorithm that intercepts the Top 10 semantic results from Milvus, queries SQLite for their historical Quality Scores, and mathematically boosts 5-star templates into the Top 5.
2. Define the PromptAddOn schema supporting predefined modes (e.g., "Speed AddOn: Output only raw code," "Quality AddOn: Think step-by-step").
3. Update the `/api/v1/recommend` endpoint to accept a `tradeoff_preference` parameter and return both the enriched prompt and the applicable AddOns.

**Optional Deliverable:** Output the specific mathematical weighting function used for the hybrid reranking algorithm for internal memory.

**Status:** ✅ Complete

---

## Phase 5: CLI Frontend & Execution Workflow

**Objective:** Build the fast, zero-dependency Golang terminal interface that interacts with the user, triggers the daemon, and collects feedback.

**Task:** Build an interactive, cross-platform Golang CLI to capture user intent, parse variables, and collect post-execution telemetry.

**Tools:** `senior-frontend` (Golang CLI context), `observability-designer`

**Details:** The frontend is a compiled Go binary (using Cobra/Viper/Promptui) that provides an interactive terminal UI. It acts as the primary user interface for the Daedalus system.

**Execution Steps (Sequential):**
1. Implement the startup sequence: the Go binary must check for the FastAPI heartbeat; if offline, it programmatically triggers `start_promptee.sh`.
2. Build the interactive terminal prompt that displays the Top 5 results from the backend and allows the user to select one.
3. Write the parsing logic to detect required `[VARIABLES]` (e.g., `[DATABASE]`) in the chosen template and interactively ask the user to fill them in.
4. Append the selected AddOn mode (Speed vs. Quality) to the compiled payload.
5. Implement the execution timer in Go and, post-execution, prompt the user for a 1-5 Quality rating, transmitting all final telemetry back to the SQLite store.

**Optional Deliverable:** Write comprehensive pytest and pytest-asyncio suites covering the API boundaries to guarantee 80%+ test coverage before outputting the Go CLI routing structure for internal memory.

**Status:** 🔄 In Progress

---

## Dependency Graph

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
  │              │           │           │           │
  │              │           │           └─── depends on Phase 2 + 3
  │              │           └─── depends on Phase 2
  │              └─── depends on Phase 1
  └─── foundation
```

- Phase 1 must complete first (repo structure, daemon, health-check)
- Phase 2 depends on Phase 1 (needs the scaffolded backend directory)
- Phase 3 depends on Phase 2 (needs the running FastAPI + Milvus)
- Phase 4 depends on Phase 2 + 3 (needs both Milvus results and SQLite data)
- Phase 5 depends on Phase 4 (needs the finalized API contract)

---

## Agent Delegation Strategy

Each phase will be delegated to an isolated agent with full context of the SOP. Since phases have sequential dependencies, agents will be launched to produce their phase's artifacts independently. Integration will be verified after all phases complete.

| Phase | Agent Type | Isolation | Key Artifacts |
|-------|-----------|-----------|---------------|
| 1 | `senior-devops` + `spec-driven-workflow` | worktree | Directory tree, `start_promptee.sh`, `.env.example`, `docker-compose.milvus.yml` |
| 2 | `rag-architect` + `senior-backend` | worktree | `chunker.py`, `embedder.py`, `milvus.py`, ingest/recommend routers |
| 3 | `database-designer` + `senior-backend` | worktree | SQLAlchemy models, `sqlite.py`, telemetry router |
| 4 | `senior-data-scientist` + `rag-architect` | worktree | `reranker.py`, `addon.py`, updated recommend router |
| 5 | `senior-frontend` | worktree | Go CLI (`cmd/`, `internal/`), pytest suites |
