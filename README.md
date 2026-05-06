<p align="center">
  <img src="docs/assets/logo.png" alt="Promptee Logo" width="300" />
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/user/promptee?style=flat-square&color=blue" alt="License" />
  <img src="https://img.shields.io/badge/Go-1.25+-00ADD8?style=flat-square&logo=go&logoColor=white" alt="Go Version" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker Ready" />
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome" />
</p>

---

# Promptee — Local MLOps & RAG CLI

**Promptee** (Codename: *Daedalus*) is a production-ready prompt management toolchain built for developers who live in the terminal. It bridges the gap between ad-hoc prompt engineering and production-grade AI infrastructure: a fast Go TUI on the front, a Python FastAPI backend with hybrid vector search on the back.

Its core job is simple: **stop guessing which prompt works and start knowing.**

---

## How It Works

Promptee stores your prompts in a hybrid vector database (dense semantic embeddings + BM25 sparse vectors). When you query it, a multi-signal reranker blends semantic similarity, keyword relevance, historical quality scores, and usage popularity into a single `hybrid_score`. The best result is returned — already filled with variable placeholders — and dropped straight into your clipboard.

The more you use it, the smarter it gets. Telemetry scraped from tools like Claude Code feeds outcome data (token cost, latency, AI judgments) back into the reranker through a feedback flywheel.

---

## Key Features

**Hybrid Reranking**  
Combines four signals: semantic similarity (dense vectors), keyword match (BM25 sparse vectors), historical quality ratings, and retrieval popularity. This beats pure semantic search for prompt-engineering workloads where exact terminology matters as much as intent.

**Schema-Aware Chunking**  
Regex-based prompt boundary detection preserves prompt structure (objective, variables, instructions) across chunks, preventing the over-splitting common in generic RAG pipelines.

**Reactive Mascot TUI**  
A terminal pet (`o _ o`) reflects system state in real time — searching, match found, backend offline, speed mode active. It's a live status indicator that doesn't require reading logs.

**Add-On Templates**  
A separate collection for reusable workflow add-ons (e.g., Chain-of-Thought suffixes, speed-mode strippers). Add-ons can be toggled dynamically and composed with retrieved prompts at query time.

**Async Ingest Jobs**  
File ingestion runs in background tasks with progress tracking. Supports plain text, markdown, and PDF sources. The backend validates, chunks, embeds, and inserts into both Milvus and SQLite without blocking the API.

**Transcript Telemetry**  
Parses Claude Code `.jsonl` conversation logs to extract token usage, latency, and outcome signals. This data auto-populates quality scores without any manual rating.

**Headless Agent Mode**  
A `--agent --json` flag pair bypasses the TUI and returns structured JSON — purpose-built as a retrieval oracle for LLM agents. Agents pay a short query (10–20 tokens) and get back a battle-tested, variable-filled template instead of reasoning one from scratch. The `PROMPTEE_TRACE` token embedded in every response closes the feedback loop: execution outcomes flow back into the reranker automatically.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| CLI & TUI | Go, Cobra, Tooey |
| Backend API | Python, FastAPI, asyncio |
| Vector DB | Milvus (dense + sparse collections) |
| Metadata DB | SQLite (via SQLAlchemy async) |
| Embeddings | Sentence Transformers |
| Sparse Search | BM25 (rank-bm25, FNV-1a hashing) |
| Infrastructure | Docker Compose (Milvus, MinIO, etcd) |

---

## Getting Started

### 1. Build & Launch

```bash
git clone https://github.com/user/promptee.git
cd promptee
make build

# Spin up Milvus, MinIO, etcd, and the FastAPI backend
./promptee build all
```

### 2. Ingest Prompts

```bash
# Ingest a file of prompts
./promptee ingest --file ./my-prompts.md

# Ingest a directory
./promptee ingest --directory ./prompt-library/
```

### 3. Interactive TUI

```bash
./promptee
```

- **Type your intent** — e.g., `write a python api`
- **Pick a result** — press `1–5` to select from ranked recommendations
- **Fill variables** — the TUI prompts for any `[VARIABLE]` placeholders
- **Copy** — run `/copy` to push the final prompt to your clipboard

### 4. Headless Agent Mode

```bash
# Top result with quality add-ons, structured JSON output
./promptee "write a robust python API" --agent --json --top-k 1 --tradeoff quality

# Speed-optimized: strips markdown and explanations to reduce token cost
./promptee "write a robust python API" --agent --json --top-k 1 --tradeoff speed
```

#### Integrating with Claude Code

Add this to your `CLAUDE.md` to wire Promptee as a retrieval oracle before any complex task:

```markdown
Before executing any multi-step implementation task, call:
./promptee "[task description]" --agent --json --top-k 1 --tradeoff quality
Use the returned `full_text` as your base prompt if `hybrid_score > 0.7`.
```

> Other tools help humans manage prompts. **Promptee helps agents retrieve better prompts than they'd generate themselves.**

---

## Mascot State Reference

| State | Emoticon | Meaning |
| :--- | :---: | :--- |
| Attentive | `o _ o` | Ready for input |
| Searching | `> _ <` | Querying Milvus and reranking |
| Match found | `O _ O` | High-confidence result returned |
| Delighted | `^ _ ^` | You rated a prompt 5 stars |
| Speed mode | `* _ *` | Speed add-on is active |
| Offline | `X _ X` | Backend or Milvus unreachable |

---

## Project Structure

```
promptee/
├── internal/
│   ├── tui/          # Go TUI: app, commands, views, transcript parser
│   └── api/          # Go HTTP client for backend communication
├── backend/
│   ├── app/
│   │   ├── db/       # Milvus and SQLite async clients
│   │   ├── models/   # SQLAlchemy models (prompts, add-on templates)
│   │   ├── routers/  # FastAPI routers: ingest, recommend, addons
│   │   └── services/ # Chunker, embedder, BM25, ingest job, PDF parser
│   └── tests/        # pytest suite
└── docker/           # Docker Compose files for Milvus infrastructure
```

---

## Contributing

1. Run `make test` (Python) and `make go-test` (Go) before submitting.
2. Follow the architectural patterns documented in `DAEDALUS_SOP.md`.
3. New retrieval signals belong in `backend/app/routers/recommend.py`; new ingestion sources go in `backend/app/services/`.

---

<p align="center">Built with ❤️ for terminal dwellers.</p>
