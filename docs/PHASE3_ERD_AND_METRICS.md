# Phase 3: Entity-Relationship Diagram & Metrics Computation

## Cross-Database Architecture (Milvus ↔ SQLite)

```
┌─────────────────────────────────────────────────────────┐
│                    MILVUS (Vector DB)                  │
│                                                         │
│  ┌──────────────────────────┐                           │
│  │ Collection: "prompts"    │                           │
│  ├──────────────────────────┤                           │
│  │ id                       │  ← [Milvus Vector ID]     │
│  │ text (embedding)         │                           │
│  │ metadata: {              │                           │
│  │   title, objective,      │                           │
│  │   variables, ...         │                           │
│  │ }                        │                           │
│  └──────────────────────────┘                           │
│           ▲                                              │
│           │ milvus_id (unique FK)                        │
│           │                                              │
└───────────┼──────────────────────────────────────────────┘
            │
            │ [CROSSREF: Maps semantic vectors to telemetry]
            │
┌───────────▼──────────────────────────────────────────────┐
│                  SQLITE (Relational DB)                 │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ templates                                       │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ id (PK, INT)                                    │   │
│  │ milvus_id (UNIQUE, NOT NULL)  [crossref ★]    │   │
│  │ title (VARCHAR 256)                             │   │
│  │ objective (VARCHAR 1024)                        │   │
│  │ variables (VARCHAR 1024)  [JSON-serialized]     │   │
│  │ created_at (DATETIME, DEFAULT now())            │   │
│  │ updated_at (DATETIME, ON UPDATE now())          │   │
│  └─────────────────────────────────────────────────┘   │
│           ▲ (1) relationship: ONE-TO-MANY              │
│           │                                             │
│  ┌────────┴──────────────────────────────────────────┐  │
│  │ executions                                  (N)   │  │
│  ├────────────────────────────────────────────────┤  │
│  │ id (PK, INT)                                  │  │
│  │ template_id (FK → templates.id, NOT NULL)     │  │
│  │                                               │  │
│  │ ─── METRICS CAPTURED ───                      │  │
│  │ latency_ms (FLOAT)                            │  │
│  │ input_tokens (INT) ← prompt tokens            │  │
│  │ output_tokens (INT) ← completion tokens       │  │
│  │ context_window_pct (FLOAT, 0-100)             │  │
│  │ verbosity (VARCHAR 32) ∈ {terse|moderate|verbose} │  │
│  │                                               │  │
│  │ ─── COMPUTED TRADEOFF SCORES ───              │  │
│  │ tradeoff_speed (FLOAT, 0-1)                   │  │
│  │ tradeoff_cost (FLOAT, 0-1)                    │  │
│  │ tradeoff_quality (FLOAT, 0-1)                 │  │
│  │ addon_mode (VARCHAR 64) ← Phase 4 integration │  │
│  │ executed_at (DATETIME, DEFAULT now())         │  │
│  └────────────────────────────────────────────────┘  │
│           ▲ (1) relationship: ONE-TO-MANY              │
│           │                                             │
│  ┌────────┴──────────────────────────────────────────┐  │
│  │ feedback                                    (N)  │  │
│  ├────────────────────────────────────────────────┤  │
│  │ id (PK, INT)                                  │  │
│  │ execution_id (FK → executions.id, NOT NULL)   │  │
│  │ quality_score (INT, CHECK(1-5)) ★ ground-truth│  │
│  │ notes (TEXT, nullable) ← user commentary      │  │
│  │ created_at (DATETIME, DEFAULT now())          │  │
│  │                                               │  │
│  │ ★ This score drives quality_score computation│  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Key Integration Points

### 1. Semantic Search → Telemetry Mapping
- **Milvus** returns Top-N vector results with IDs
- **Template.milvus_id** bridges the gap: uniquely maps to vector ID
- **Executions** records track usage of each template
- **Phase 4 Reranking** uses this mapping to boost high-feedback templates

### 2. Execution Metrics Workflow
```
Execution Record
  └─ All [METRICS] captured atomically:
     ├─ latency_ms (from LLM timer)
     ├─ input_tokens (from model)
     ├─ output_tokens (from model)
     ├─ context_window_pct (calculated)
     └─ verbosity (user or system choice)
  └─ Computed [TRADEOFF] scores:
     ├─ speed = 1 / (1 + latency/1000 + tokens/10000)
     ├─ cost = 1 / (1 + tokens/5000)
     └─ quality = avg(feedback.quality_score) / 5.0
```

### 3. Feedback Loop for Quality
```
User executes prompt
  ↓
Metrics captured in executions table
  ↓
CLI prompts user for 1-5 quality rating
  ↓
Feedback record created
  ↓
Quality score recomputed for template
  ↓
Future executions benefit from higher quality boosting (Phase 4)
```

---

## Tradeoff Scoring Formulas

### Speed Score
Lower latency + fewer tokens = higher score
```
speed = 1.0 / (1.0 + (latency_ms / 1000.0) + ((input_tokens + output_tokens) / 10000.0))
```
- Result: 0.0 to 1.0
- 0.9+ = fast execution, minimal tokens
- 0.5 = moderate execution
- 0.1- = slow execution, many tokens

### Cost Score
Fewer tokens = higher score (reflects lower API cost)
```
cost = 1.0 / (1.0 + ((input_tokens + output_tokens) / 5000.0))
```
- Result: 0.0 to 1.0
- 0.9+ = very few tokens (<1000 total)
- 0.5 = medium token usage (~5000 total)
- 0.1- = high token usage (>10000 total)

### Quality Score
Historical user ratings = higher score
```
quality = avg(feedback.quality_score) / 5.0  [with 0.5 default if no feedback]
```
- Result: 0.0 to 1.0
- 0.9+ = consistently 4.5-5 star ratings
- 0.5 = mixed feedback or no data (neutral)
- 0.1- = consistently 1-2 star ratings

---

## Schema Constraints & Integrity

| Constraint | Purpose | Implementation |
|-----------|---------|-----------------|
| `milvus_id UNIQUE` | Ensure 1-to-1 mapping | UNIQUE constraint on templates.milvus_id |
| `quality_score CHECK(1-5)` | Enforce rating bounds | CHECK(quality_score >= 1 AND quality_score <= 5) |
| `FK template_id` | Data integrity | executions.template_id → templates.id |
| `FK execution_id` | Data integrity | feedback.execution_id → executions.id |
| Async session | ACID compliance | SQLAlchemy async transactions with rollback |

---

## Phase 3 → Phase 4 Dependencies

Phase 4 (Hybrid Reranking) depends on Phase 3 providing:

1. **SQLite Data Layer** ✅
   - Historical execution metrics
   - User quality feedback
   - Quality score computation

2. **Metrics Computation** ✅
   - Speed, Cost, Quality formulas
   - Normalization to 0-1 range
   - Default fallback (0.5 for no feedback)

3. **API Contracts** ✅
   - POST /api/v1/telemetry (record execution)
   - POST /api/v1/feedback (record user rating)
   - Proper request/response Pydantic models

4. **Database Relationships** ✅
   - Templates ← (1-to-N) → Executions
   - Executions ← (1-to-N) → Feedback
   - Milvus ID ↔ Template ID mapping

---

## Files Modified in Phase 3

| File | Purpose |
|------|---------|
| `backend/app/models/templates.py` | SQLAlchemy Template model with Milvus crossref |
| `backend/app/models/executions.py` | SQLAlchemy Execution model with metrics fields |
| `backend/app/models/feedback.py` | SQLAlchemy Feedback model with quality_score |
| `backend/app/db/sqlite.py` | Async SQLAlchemy engine, session factory, init_db() |
| `backend/app/services/metrics.py` | Tradeoff score computation functions |
| `backend/app/routers/telemetry.py` | POST /api/v1/telemetry and /api/v1/feedback endpoints |
| `backend/app/main.py` | Database init in lifespan, telemetry router registration |
| `backend/tests/test_telemetry.py` | Telemetry endpoint tests (4 tests, all passing) |

---

## Deployment Readiness

✅ All Phase 3 components operational:
- [x] SQLite schema designed and validated
- [x] SQLAlchemy models with relationships
- [x] Metrics computation service
- [x] Telemetry API endpoints
- [x] Feedback API endpoints
- [x] Database initialization
- [x] Test coverage (65% overall, 74% for telemetry)
- [x] Input validation and error handling
- [x] Async/await throughout
- [x] ERD documentation completed

**Status: READY FOR PHASE 4** 🎯
