# Plan: Qualitative telemetry + dual feedback (human-weighted)

This document adapts the “evaluation layer” idea (quality score, impact scope, resolution status, parser directives, reporting) to **this repository’s actual layout** (Promptee: FastAPI + SQLite + Go TUI client), and adds an explicit requirement: **two feedback channels—agent vs human—with human signal dominating** when both exist.

---

## Goals

1. Capture **qualitative** execution metadata beyond raw counters: discrete quality (1–5), **blast radius** (`impact_scope`), and **outcome** (`resolution_status`).
2. Support **agent-submitted** self-evaluation (e.g. from Agent mode / hooks) and **human-submitted** ratings, stored distinctly.
3. Apply **higher weight to human feedback** wherever aggregates drive product behavior (tradeoff quality, reranking, summaries).
4. Optional **GitOps / CI** reporting (Markdown tables, blocker flags).
5. Keep **legacy rows** valid: new columns nullable; existing API clients keep working.

**Non-goals (for this phase):** Rewriting the entire memory stack; implementing a full claude-mem TypeScript plugin inside this repo unless you later vendor it here.

---

## Current architecture (ground truth)

| Layer | Role today |
|--------|------------|
| `backend/app/models/executions.py` | `Execution`: latency, tokens, verbosity, computed `tradeoff_*`, `source`, `model_id`. |
| `backend/app/models/feedback.py` | `Feedback`: `execution_id`, `quality_score` (1–5), `notes`, `judged_by` (`"user"` \| `"model"` per comments), timestamps. |
| `backend/app/routers/telemetry.py` | `POST /api/v1/telemetry`, `POST /api/v1/feedback`, `GET /api/v1/telemetry/summary`. |
| `backend/app/services/metrics.py` | `compute_quality_score(template_id)`: **simple average** of all `Feedback.quality_score` for executions of that template → normalized 0–1. **No weighting by `judged_by`.** |
| `backend/app/services/reranker.py` | `_get_template_stats`: same **unweighted** `avg(Feedback.quality_score)` for `quality_boost`. |
| `internal/api/client.go` | `FeedbackRequest` has **no** `judged_by` field; TUI `doSubmitFeedback` does not set it (server uses model default). |
| `internal/tui/commands.go` | Human path: `/feedback <1-5>` after telemetry. |

**Gap vs desired behavior:** Agent and human feedback are not first-class in the Go client; `judged_by` is not validated in Pydantic; aggregates **treat agent and human equally**; no `impact_scope` / `resolution_status`.

---

## Design: dual feedback + weighting

### 1. Canonical roles

Standardize `judged_by`:

| Value | Meaning | Weight |
|-------|---------|--------|
| `user` | Human (TUI, API, reviewer) | **High** (e.g. `W_user = 3.0`—tune via config) |
| `agent` | Model self-evaluation in agent mode / automation | **Low** (e.g. `W_agent = 1.0`) |

**Migration note:** Today the schema comment says `"model"`. Treat `"model"` as alias for `"agent"` in queries or migrate rows once.

### 2. Weighted aggregate formula (template-level quality)

For each template, compute a **weighted mean** of star ratings (1–5), then normalize to 0–1 for `tradeoff_quality` / reranker:

\[
\text{weighted\_avg} = \frac{\sum_i w_{source(i)} \cdot score_i}{\sum_i w_{source(i)}}
\]

**Policy when only agent feedback exists:** Use weighted average; optional **cap** (e.g. normalized max 0.6) until first human rating so self-scores do not dominate cold-start.

**Policy when human feedback exists:** Full formula; human rows pull the aggregate toward ground truth.

**Edge case:** Multiple ratings per execution—allow multiple rows initially; optional later unique partial index on `(execution_id)` where `judged_by='user'`.

### 3. Where to store qualitative fields

**Recommended:** Extend `feedback` table so each rating row (human or agent) can carry:

- `impact_scope` — `NULL` \| `'local'` \| `'component'` \| `'architectural'`
- `resolution_status` — `NULL` \| `'resolved'` \| `'partial'` \| `'blocked'`

Rationale: Feedback already models “how good was this execution”; scope/status are judgment metadata. Nullable preserves legacy.

---

## Implementation phases

### Phase 1 — Schema & models

**Files:** new Alembic revision under `backend/alembic/versions/`, `backend/app/models/feedback.py`, exports in `backend/app/models/__init__.py`.

**SQL (conceptual):**

- `ALTER TABLE feedback ADD COLUMN impact_scope VARCHAR(32) NULL;`
- `ALTER TABLE feedback ADD COLUMN resolution_status VARCHAR(32) NULL;`
- Optional: `CHECK` constraints for allowed literals when non-null.

**Enums:** Centralize allowed sets in one place (constants + Pydantic validators in `telemetry.py` or a small shared module).

---

### Phase 2 — API contracts

**File:** `backend/app/routers/telemetry.py`

- Extend `FeedbackRequest` / `FeedbackResponse` with optional `impact_scope`, `resolution_status`.
- **Validate `judged_by`:** allow `user` \| `agent`; normalize `model` → `agent` on write.
- Default `judged_by="user"` for backward compatibility (human `/feedback`).

**File:** `backend/app/services/metrics.py`

- Replace plain `avg(Feedback.quality_score)` with **weighted** aggregation using `judged_by`.
- Config: `QUALITY_WEIGHT_USER`, `QUALITY_WEIGHT_AGENT` (later env via `app.config`).

**File:** `backend/app/services/reranker.py`

- Update `_get_template_stats` to use the **same** weighted quality helper as metrics (extract shared function to avoid drift).

**File:** `backend/app/routers/telemetry.py` — `GET /api/v1/telemetry/summary`

- Add: `avg_quality_weighted`, breakdown by source, counts, optional **blocker** counts (`resolution_status = 'blocked'` or `quality_score <= 2`).

---

### Phase 3 — Go client & TUI

**Files:** `internal/api/client.go`, `internal/tui/commands.go`, `internal/api/client_test.go`.

- Add `JudgedBy string` `json:"judged_by,omitempty"` to `FeedbackRequest`.
- **Agent path:** set `judged_by: "agent"` when automation submits self-evaluation.
- **Human path:** omit or set `user` for `/feedback`.

---

### Phase 4 — Agent instructions (this repo)

There is **no** `src/sdk/parser.ts` in Promptee—that pattern applies to external **claude-mem**-style plugins. Here, directives live in **agent/addon prompts or Cursor rules**.

**Behavioral contract for agents:**

1. `POST /api/v1/telemetry` as today.
2. `POST /api/v1/feedback` with `judged_by: "agent"`, `quality_score` 1–5, optional `notes`, `impact_scope`, `resolution_status`.

**Optional XML bridge:** If observations are still emitted as `<observation>...</observation>` elsewhere, parse `<quality_score>`, `<impact_scope>`, `<resolution_status>` with strict validators and map to the same JSON body + `judged_by=agent`.

---

### Phase 5 — Reporting & CI

**New script:** e.g. `backend/scripts/summarize_quality.py`.

**Report:** weighted vs raw averages by template/model; blocker table; recent rows with `judged_by` and qualitative fields.

**CI:** Optional non-zero exit if blocker count exceeds threshold.

---

### Phase 6 — Tests

**Files:** `backend/tests/test_telemetry.py`, `backend/tests/test_reranker.py`, `backend/tests/test_e2e_pipeline.py`.

- Mixed human+agent feedback → weighted aggregate favors human.
- Enum validation and NULL legacy columns.
- Go client sends `judged_by` when specified.

---

## Weighting constants (starting point)

| Constant | Suggested initial | Notes |
|----------|-------------------|--------|
| `W_user` | `3.0` | Human > agent |
| `W_agent` | `1.0` | Self-evaluation prior |
| Agent-only cap (normalized) | `0.6` max until first human | Optional |

---

## Triggering model

| Source | Trigger |
|--------|---------|
| Human | TUI `/feedback`, direct API |
| Agent | Agent mode / hooks after execution, `judged_by=agent` |

Both reference the same `execution_id` from `POST /api/v1/telemetry`.

---

## File checklist (Promptee)

| Area | Files |
|------|--------|
| DB | New Alembic migration; `feedback` columns |
| Models | `backend/app/models/feedback.py` |
| API | `backend/app/routers/telemetry.py` |
| Metrics | `backend/app/services/metrics.py` |
| Rerank | `backend/app/services/reranker.py` |
| Client | `internal/api/client.go`, `internal/tui/commands.go` |
| Tests | `backend/tests/test_telemetry.py`, `test_reranker.py`, `test_e2e_pipeline.py`, `internal/api/client_test.go` |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Agent inflates scores | Weighting + optional agent-only cap |
| Drift metrics vs reranker | Single shared aggregate function |
| Breaking clients | Omitempty new fields; defaults on server |

---

## Success criteria

1. Human and agent feedback distinguished by `judged_by`.
2. `compute_quality_score` and reranker use **identical weighted** logic; human moves aggregates more than agent.
3. Optional `impact_scope` / `resolution_status` on API + DB.
4. Summary exposes split stats.
5. Tests cover weighting and backward compatibility.

---

## Open decisions

1. Standardize on `user`/`agent` only vs keep `model` as deprecated alias.
2. One vs many human feedback rows per `execution_id`.
3. Whether each `Execution`’s `tradeoff_quality` is snapshot-at-insert vs always recomputed from live feedback (today: computed at telemetry insert from DB state).
