<p align="center">
  <img src="docs/assets/promptee_pet_logo.png" alt="Promptee Logo" width="600" />
</p>

```text
 /$$$$$$$                                               /$$                        
| $$__  $$                                             | $$                        
| $$  \ $$ /$$$$$$   /$$$$$$  /$$$$$$/$$$$   /$$$$$$  /$$$$$$    /$$$$$$   /$$$$$$ 
| $$$$$$$//$$__  $$ /$$__  $$| $$_  $$_  $$ /$$__  $$|_  $$_/   /$$__  $$ /$$__  $$
| $$____/| $$  \__/| $$  \ $$| $$ \ $$ \ $$| $$  \ $$  | $$    | $$$$$$$$| $$$$$$$$
| $$     | $$      | $$  | $$| $$ | $$ | $$| $$  | $$  | $$ /$$| $$_____/| $$_____/
| $$     | $$      |  $$$$$$/| $$ | $$ | $$| $$$$$$$/  |  $$$$/|  $$$$$$$|  $$$$$$$
|__/     |__/       \______/ |__/ |__/ |__/| $$____/    \___/   \_______/ \_______/
                                           | $$                                    
                                           | $$                                    
                                           |__/                                    
```

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
  <img src="https://img.shields.io/badge/Milvus-0D1229?style=for-the-badge&logo=data:image/svg%2Bxml;base64,PHN2ZyBpZD0iTGF5ZXJfMSIgZGF0YS1uYW1lPSJMYXllciAxIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzNjAgMzYwIj48ZGVmcz48c3R5bGU+LmNscy0xe2ZpbGw6I2ZmZjt9PC9zdHlsZT48L2RlZnM+PHRpdGxlPm1pbHZ1cy1pY29uLXdoaXRlPC90aXRsZT48cGF0aCBjbGFzcz0iY2xzLTEiIGQ9Ik0xNjguNTA5ODMsNjMuMzI5M2MzMS45NTY3MS41MDcsNTkuOTM1NTksMTEuMTEyODYsODMuMjc2ODYsMzMuMTg1MzUsMTguNzAwNiwxNy42ODQwNywzMC4yMjY2NywzOS4zMjUxMiwzNC44MTMyOCw2NC42NDQ1MkExMDUuMzIxMTUsMTA1LjMyMTE1LDAsMCwxLDI4OC4zMDk0OCwxODIuMDVjLS41Njk2NywyOC40NzAzOS05Ljk0MTUzLDUzLjY2NjY3LTI4LjY1MzQzLDc1LjE5NzEzLTE4LjEzNjY3LDIwLjg2ODcyLTQwLjkwODg4LDM0LjExNDkzLTY4LjA1NDY5LDM5LjEwMjIyLTM2LjYxMDY2LDYuNzI2My02OS44MjYxNC0xLjQ0NjEzLTk5LjIyNjU2LTI0LjQ0NzMzNy02LjEwNzM1LTQuNzgzNDEtMTEuNDA2NjctMTAuNDQ5MjctMTYuOTI5MTgtMTUuODY1NjhxLTE3LjgzMzU5LTE3LjQ5MDY5LTM1LjYyNS0zNS4wMjQ2UTIzLjY4MTUyLDIwNS4xMjU1Nyw3LjUzNTM1LDE4OS4yNzI4N2MtNC45OTgxMS00LjkyNjQzLTUuMDAxNjYtMTEuNzYxNzctLjAwNjE4LTE2LjY4Nzc1cTE2LjU4MjM5LTE2LjM1MTkzLDMzLjIyMi0zMi42NDU3OWMxMC40MTUtMTAuMjI1MTMsMjAuNzc4Mi0yMC41MDQxNywzMS4yNzM4MS0zMC42NDYwNiw2Ljk2OC02LjczMzA4LDEzLjU2MjEtMTMuODY2NywyMS4yMDUxNS0xOS44ODg3OGExMTkuNjg5NzYsMTE5LjY4OTc2LDAsMCwxLDUxLjM0NTE3LTIzLjY4NjY3LDEyMS4xNjIsMTIxLjE2MiwwLDAsMSwyMy45MzQ1OS0yLjM4ODY5Wm05Mi4zNzEsMTE3LjY5MDg1YTkxLjk5ODIyLDkxLjk5ODIyLDAsMCwwLTEuNDg5MDYtMTUuMDkwNzFjLTQuNjU4OS0yNC40MjEzMi0xNy40ODk0NC00My40OTU0NC0zOC4yMzkzOC01Ni45ODY2NC0yMC4wMTI4My0xMy4wMTE4OC00Mi4wMDc5Mi0xNy4wNTU2OC02NS40NjYyOC0xMi42MTQyOGE4NS42MTk1Miw4NS42MTk1MiwwLDAsMC00NC4wMTg2MiwyMi42NDY4Yy04LjIxNTgyLDcuODQ3MjYtMTYuMjY5LDE1Ljg2NTA1LTI0LjM4MTYzLDIzLjgyMDEzcS0xNi4zMTMzMiwxNS45OTY2Ni0zMi41OTgzNywzMi4wMjE5Yy0zLjc1LDMuNjk3NDktMy43MzM5NCw4LjUyOTA4LS4wMTI2NiwxMi4yMDk4OSw1LjMyNzU4LDUuMjY5NSwxMC42OTI4NSwxMC41MDA4NSwxNi4wMzYzNSwxNS43NTQyOXExOS41NDEzOCwxOS4yMTE4OSwzOS4wODI0NiwzOC40MjQsMjguMzM0MzEsMjcuNzUzMzYsNjcuOTgsMjUuOTQwMzVhODMuMDMyNzksODMuMDMyNzksMCwwLDAsMzkuMTc0MjEtMTEuNTI3MjljMjguMjM3MjktMTYuODE1MTksNDIuNjYwMzktNDEuODc5NTcsNDMuOTMzMDUtNzQuNTk4NDFabTU4LjIzNjEyLS4wNzUyMmExNzEuMzc1NjYsMTcxLjM3NTY2LDAsMCwwLTQuMDkwNzUtMzguMTE0MjUsMTEuNzM3MjMsMTEuNzM3MjMsMCwwLDEtLjIwMTExLTEuMTU2NSwyLjYzNDc4LDIuNjM0NzgsMCwwLDEsMS4yNzQ4MS0yLjc0NzUyLDIuNjcwOTIsMi42NzA5MiwwLDAsMSwzLjE2MTk0LjAyMTQ3LDkuMTM3MTEsOS4xMzcxMSwwLDAsMSwxLjE4ODY0LDEuMDg1NnExNi4xNTUxMiwxNi4xNDgzNCwzMi4zMDUsMzIuMzAyMjZjNS4zMDY1OCw1LjMwNzUsNS4yOTY3LDEyLjA2NTE1LS4wMjI1NSwxNy4zODQ1NXEtMTYuMDk5NTcsMTYuMTAwMTYtMzIuMTk5NywzMi4xOTk4NWMtLjI3Ny4yNzY5NS0uNTQ2ODIuNTYxNzktLjgzNDQ1LjgyNzE3YTIuNzMwODUsMi43MzA4NSwwLDAsMS0zLjUwMTkyLjQ0MDIzLDIuNjgzNCwyLjYgzNCwwLDAsMS0xLjM1MS0zLjExNTc3YzEuMTMxOTItNS4yMDU4NywyLjEwMjMyLTEwLjQzOTY5LDIuNzk4LTE1LjcyNTczYTE2NC4yMjM4OCwxNjQuMjIzODgsMCwwLDAsMS40Njk0NC0xOC44NTU4NmMuMDIzOC0xLjUxNDcuMDAzNTUtMy4wMzAzNC4wMDM1NS00LjU0NTUxWiIvPjxwYXRoIGNsYXNzPSJjbHMtMSIgZD0iTTIzMi4yMDYyNSwxODAuOTY1YTcwLjQ4OTMxLDcwLjQ4OTMxLDAsMSwwLS4wMDAxNSwwWiIvPjwvc3ZnPg==&logoColor=white" alt="Milvus" />
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

### Headless Agent Mode
Promptee can be run headlessly for seamless integration into scripts, LLM agents, or automated pipelines without launching the TUI:

```bash
# Get recommendations for a query directly in standard output
./promptee "write a robust python API" --agent

# Output the results in raw JSON (perfect for Claude Code/Cursor integration)
./promptee "write a robust python API" --agent --json

# Control tradeoff and number of results
./promptee "write a robust python API" --agent --json --top-k 3 --tradeoff speed
```

*Note: In agent mode, Promptee automatically injects the `[PROMPTEE_TRACE:...]` telemetry tokens into the output texts, ensuring your automated workflows remain trackable in the background!*

## 📊 Telemetry Architecture

Promptee monitors your local LLM usage (like Claude Code) via asynchronous log tailing. It intercepts special `[PROMPTEE_TRACE:...]` tokens that are appended to the clipboard. The LLM ignores these trace tokens, but Promptee uses them to cross-reference actual execution latency, token counts, and session outcomes—feeding this data back into the Hybrid Reranker.

## 🐾 The Promptee Pet

Promptee features a reactive "digital pet" mascot in the TUI that changes its facial expression based on the current system state, telemetry scores, and active Add-Ons. 

| Emoticon | State | Trigger |
| :---: | :--- | :--- |
| **`o _ o`** | Attentive / Ready | The CLI is open and waiting for the user to type their natural language intent. |
| **`- _ -`** | Dormant / Asleep | The system is booting up, or the backend daemon is in zero-drain standby mode. |
| **`> _ <`** | Straining / Processing | The FastAPI backend is querying the Milvus vector database and calculating hybrid weights. |
| **`O _ O`** | Bingo / Found | The RAG pipeline just returned an exact, high-confidence template match for the user's intent. |
| **`^ _ ^`** | Delighted / Success | The user executes a prompt and gives it a 5-star quality rating during the telemetry phase. |
| **`X _ X`** | Fatal / Error | A system failure occurs (e.g., Milvus container is down, or required `[VARIABLES]` are missing). |
| **`¬ _ ¬`** | Skeptical / Warning | The user is about to execute a prompt that historically has a very low 1-star quality score, or token limits are dangerously high. |
| **`* _ *`** | Overclocked / Speed Mode | The user attaches the "Speed AddOn" to strip all markdown and explanations for maximum velocity. |
| **`• _ •`** | Focused / Quality Mode | The user attaches the "Quality AddOn" (Chain-of-Thought), shifting the AI into strict, step-by-step reasoning. |
| **`T _ T`** | Sad / Low Rating | The user gives an executed prompt a 1-star rating, mathematically demoting it in the SQLite database. |

## 🤝 Contributing

Contributions are welcome! Please check out the [Issues](https://github.com/user/promptee/issues) page. Make sure your code passes `make test` before submitting a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
