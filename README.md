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
A `--agent` flag bypasses the TUI entirely and returns structured JSON. Designed for LLM agents (Claude Code, Cursor) that need a retrieval oracle without human interaction.

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

For scripted use or LLM agent integration:

```bash
# JSON output, top result, quality add-ons applied
./promptee "write a robust python API" --agent --json --top-k 1 --tradeoff quality

# Speed-optimized: strips markdown and explanations to reduce token cost
./promptee "write a robust python API" --agent --json --top-k 1 --tradeoff speed
```

#### Integrating with Claude Code

Add this to your `CLAUDE.md` to have agents automatically retrieve battle-tested prompts before starting complex tasks:

```markdown
Before executing any multi-step implementation task, call:
./promptee "[task description]" --agent --json --top-k 1 --tradeoff quality
Use the returned `full_text` as your base prompt if `hybrid_score > 0.7`.
```

> **Why this matters for agents:** A short query (10–20 tokens) retrieves a battle-tested, variable-filled template, eliminating the reasoning tokens required to construct a complex prompt from scratch. The `PROMPTEE_TRACE` token embedded in each result closes the feedback loop by capturing real execution outcomes.

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

---

# 🚀 Promptee: Local MLOps & RAG CLI

**Promptee** (Codename: *Daedalus*) is a production-ready toolchain designed for developers who live in the terminal. It bridges the gap between ad-hoc prompt engineering and production-grade AI infrastructure by providing a blistering fast Go-based TUI and a robust Python FastAPI backend.

## 🎯 What is it for?

Promptee acts as your **AI "co-pilot memory."** It analyzes your prompt telemetry, predicts the best workflow add-ons (speed vs. quality), and drops polished, variables-filled contexts directly into your clipboard. It's built to turn "guessing what prompt worked" into "knowing what prompt wins."

---

## 😎 The "Cool Things"

- **👾 Reactive Digital Pet**: The TUI features a mascot that reacts to your system state—getting excited (`^ _ ^`) when you find a high-quality match and falling asleep (`- _ -`) when the backend is idle.
- **🧠 Hybrid Reranking**: It doesn't just do semantic search. It uses a mathematical formula to weight **Similarity + Historical Quality + Popularity**, ensuring you get the most effective prompts, not just the most "related" ones.
- **🛰️ Invisible Telemetry**: It silently scrapes logs from tools like Claude Code to track token usage, latency, and AI judgments, feeding that data back into its recommendation engine.
- **⚙️ Dynamic Add-Ons**: Instantly toggle between "Speed Mode" (stripping markdown/explanations) and "Quality Mode" (Chain-of-Thought) with one click.
- **📄 Schema-Aware Chunking**: Specialized regex-based chunking that understands prompt boundaries, preventing the "over-splitting" issues common in generic RAG systems.

---

## 🤖 The "Sleeper" Feature: Agent Mode as a Retrieval Oracle

While Promptee is great for humans, its most powerful use case is as a **retrieval oracle for other AI agents** (like Claude Code). 

### 🔄 The Agent Loop
Instead of an agent reinventing the wheel every session, it calls Promptee to retrieve a proven, variable-filled template that has already been optimized by historical telemetry.

> **Core Insight:** Other tools help humans manage prompts. **Promptee helps agents retrieve better prompts than they'd generate themselves.**

### 💎 Why This Matters
*   **📉 Massive Token Savings**: Agents pay only for a short query (10-20 tokens) and get back a battle-tested template, bypassing the reasoning tokens required to "hallucinate" a complex prompt from scratch.
*   **🏎️ Speed vs. Quality Tradeoffs**: By passing `--tradeoff speed`, the agent receives a leaner prompt (stripped of markdown/explanations), further reducing context window pressure and downstream costs.
*   **📈 The Feedback Flywheel**: Every prompt retrieved in agent mode includes a `PROMPTEE_TRACE` token. The telemetry pipeline captures the agent's real-world execution data (latency, outcome) and automatically refines the hybrid reranker—making the system smarter the more it's used.

---

## 🛠️ Tech Stack

### CLI & Interface
[![Go](https://img.shields.io/badge/Go-00ADD8?style=for-the-badge&logo=go&logoColor=white)](https://go.dev/)
[![Cobra](https://img.shields.io/badge/Cobra-CLI-blue?style=for-the-badge)](https://github.com/spf13/cobra)
[![Tooey](https://img.shields.io/badge/Tooey-TUI-orange?style=for-the-badge)](https://github.com/stukennedy/tooey)

### Backend & AI
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Milvus](https://img.shields.io/badge/Milvus-Vector_DB-0D1229?style=for-the-badge)](https://milvus.io/)
[![Sentence Transformers](https://img.shields.io/badge/Sentence--Transformers-AI-yellow?style=for-the-badge)](https://sbert.net/)

---

## 🚀 How to Use

### 1. Installation (Zero-Day Build)
Compile the CLI and spin up the full containerized stack (Postgres, Milvus, MinIO, etcd) with a single command:

```bash
# Clone and build
git clone https://github.com/user/promptee.git
cd promptee
make build

# Launch the full infrastructure
./promptee build all
```

### 2. Basic TUI Usage
Launch the interface:
```bash
./promptee
```
- **Type your intent**: "Write a python api"
- **Pick a result**: Press `1-5` to select a recommended prompt.
- **Fill variables**: The TUI will prompt you for any `[VARIABLES]` defined in the template.
- **Copy & Go**: The final prompt is added to the clipboard by the command `/copy` which drops into your clipboard.

### 3. Headless Agent Mode
Promptee can be run headlessly for seamless integration into scripts or LLM agents. This allows agents to retrieve your best prompts, ranked by what actually worked.

```bash
# Get recommendations for a query directly in standard output
./promptee "write a robust python API" --agent

# Output raw JSON (perfect for Claude Code/Cursor integration)
./promptee "write a robust python API" --agent --json --top-k 1 --tradeoff quality
```

#### 🛠️ Strategic Integration: `CLAUDE.md`
You can instruct your agents to always check Promptee before starting a complex task. Add this to your `CLAUDE.md`:

```markdown
Before executing any multi-step implementation task, call:
./promptee "[task description]" --agent --json --top-k 1 --tradeoff quality
and use the returned full_text as your base prompt if hybrid_score > 0.7.
```

---

## 🐾 The Mascot Cheat Sheet

| Emoticon | State | Trigger |
| :---: | :--- | :--- |
| **`o _ o`** | Attentive | Ready for your input. |
| **`> _ <`** | Straining | Querying vector database & reranking. |
| **`O _ O`** | Bingo! | Found an exact, high-confidence match. |
| **`^ _ ^`** | Delighted | You gave a prompt a 5-star rating. |
| **`X _ X`** | Fatal | Backend or Milvus is offline. |
| **`* _ *`** | Overclocked | Speed Add-On is active. |

---

## 🤝 Contributing

We love PRs! Before submitting:
1. Ensure `make test` (Python) and `make go-test` (Go) pass.
2. Follow the architectural patterns in `DAEDALUS_SOP.md`.

---
<p align="center">Built with ❤️ for terminal dwellers.</p>
