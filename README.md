<p align="center">
  <img src="docs/assets/promptee_logo.png" alt="Promptee Logo" width="600" />
</p>

# Promptee (Codename: Daedalus)

> A production-ready Local MLOps & RAG CLI built for terminal-based AI workflows.

**Promptee** is an open-source toolchain that bridges the gap between ad-hoc prompt engineering and production AI infrastructure. It provides a blistering fast Go-based Terminal User Interface (TUI) alongside a robust Python FastAPI backend, utilizing PostgreSQL and Milvus for intelligent hybrid vector reranking and telemetry tracking.

Designed for developers who spend their lives in the terminal, Promptee acts as an AI "co-pilot memory," analyzing the telemetry of your prompts, predicting the best workflow add-ons (speed vs. quality tradeoffs), and seamlessly dropping polished contexts directly into your clipboard.

## ✨ Features

- **Blazing Fast TUI (Go + Cobra + Tooey)**: Instantly search, review, and fill variables for complex prompt templates without ever leaving your terminal.
- **Hybrid Vector Reranking (Milvus + PostgreSQL)**: Combines dense vector semantic search (Sentence-Transformers) with historical telemetry (execution frequency, quality scores, and speed tradeoffs) to surface the best prompt for the job.
- **Invisible Telemetry Pipelines**: Automatically captures token usage, latency, and AI judgments from Claude Code and Free Claude Code via regex log scraping, silently learning which prompts perform best in the real world.
- **Dynamic Tradeoff Add-Ons**: Instruct the recommender system to prioritize "speed," "cost," or "quality," and Promptee will automatically append the optimal instructional add-ons.
- **Zero-Day Containerized Deployments**: Run `./promptee build` to instantly spin up the entire backend stack (FastAPI, Postgres, Milvus, MinIO, etcd) via Docker Compose.

## 🛠️ Tech Stack

<div align="center">
  <img src="https://img.shields.io/badge/Go-00ADD8?style=for-the-badge&logo=go&logoColor=white" alt="Go" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Milvus-0D1229?style=for-the-badge&logo=vectorworks&logoColor=white" alt="Milvus" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</div>

### CLI / Frontend
- **Go 1.21+**: Core CLI binary for blazing performance.
- **Cobra**: Command orchestration and routing.
- **Tooey**: Rich, responsive Terminal User Interface.

### Backend API
- **Python 3.11+ / FastAPI**: Async, high-performance API.
- **Sentence-Transformers**: Local embeddings (`all-MiniLM-L6-v2`) for semantic mapping.
- **SQLAlchemy (Asyncpg) / aiosqlite**: Relational telemetry and execution storage.

### Infrastructure (Dockerized)
- **PostgreSQL 15**: Primary database for metrics, feedback, and telemetry data.
- **Milvus v2.3.3**: Enterprise-grade vector database for semantic chunk retrieval.
- **Docker & Docker Compose**: Automated orchestrator for isolated environments.

## 🚀 Getting Started

### Prerequisites
- Docker & Docker Compose
- Go 1.21+
- `make`

### Installation (Zero-Day Build)

Promptee comes with a built-in orchestrator that handles building the Go binary and launching the Docker infrastructure.

```bash
# Clone the repository
git clone https://github.com/user/promptee.git
cd promptee

# 1. Compile the initial Go CLI
make build

# 2. Launch the full Promptee infrastructure
./promptee build
```

This single command will:
1. Recompile the CLI if necessary.
2. Pull and start `postgres`, `milvus`, `etcd`, and `minio` containers.
3. Build the FastAPI `backend` image and start the server.
4. Block and wait until the health check endpoint returns `200 OK`.

### Granular Rebuilding
If you are developing Promptee and want to isolate component rebuilds:
- `./promptee build cli` - Recompiles only the Go binary.
- `./promptee build backend` - Rebuilds only the FastAPI Docker container.
- `./promptee build all` - Rebuilds everything.

## 💻 Usage

Start the TUI by simply running:

```bash
./promptee
```

### Core Commands
Inside the TUI, you can use the following commands:
- `/add <prompt>` - Ingest a new chunk/template into the vector database.
- `/add-addon <description>` - Create a new dynamic add-on rule.
- `/copy` - (or `Cmd+C` / `Ctrl+Shift+C`) Send the filled template to your system clipboard.
- `/clean` - Clear the current workspace and terminal screen.

## 📊 Telemetry Architecture

Promptee monitors your local LLM usage (like Claude Code) via asynchronous log tailing. It intercepts special `[PROMPTEE_TRACE:...]` tokens that are appended to the clipboard. The LLM ignores these trace tokens, but Promptee uses them to cross-reference actual execution latency, token counts, and session outcomes—feeding this data back into the Hybrid Reranker.

## 🤝 Contributing

Contributions are welcome! Please check out the [Issues](https://github.com/user/promptee/issues) page. Make sure your code passes `make test` before submitting a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
