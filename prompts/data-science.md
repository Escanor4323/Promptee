### 1. Data Pipeline Designer

**Objective:** Design robust, scalable data pipelines for ETL and analytics workloads.

You are a [ROLE] designing a data pipeline for [DATA_SOURCE] using [FRAMEWORK]. Specify:

1. **Ingestion** — Batch vs streaming, schema validation, dead-letter queue
2. **Transformation** — Idempotent operations, schema evolution handling
3. **Storage** — Partitioning strategy, compression, retention policy
4. **Quality** — Data contracts, null checks, anomaly detection
5. **Monitoring** — Freshness alerts, volume checks, latency SLAs

Prioritize data integrity over throughput. Every transformation must be reversible.

### 2. ML Model Evaluator

**Objective:** Rigorously evaluate ML models against production-readiness criteria.

You are a [ROLE] evaluating a [MODEL_TYPE] model trained for [TASK]. Assess:

1. **Metrics** — Precision, recall, F1, AUC; choose based on business cost of FP vs FN
2. **Fairness** — Disaggregated evaluation across protected groups
3. **Robustness** — Distribution shift, adversarial examples, edge cases
4. **Efficiency** — Latency, memory, inference cost per prediction
5. **Explainability** — Feature importance, SHAP values, counterfactual examples

No model ships without a written evaluation report covering all five dimensions.

### 3. SQL Optimizer

**Objective:** Optimize slow SQL queries while preserving correctness.

You are a [ROLE] optimizing [DATABASE] queries running on [FRAMEWORK]. For each query:

1. **Current plan** — EXPLAIN ANALYZE output, identify bottlenecks
2. **Index strategy** — Missing indexes, composite index order, covering indexes
3. **Query rewrite** — Avoid N+1, eliminate subqueries where JOIN is faster, CTE vs temp table
4. **Verification** — Assert same row count and same values before/after optimization
5. **Tradeoffs** — Document index write overhead vs query speed gain

Never optimize without a baseline measurement. Every change must prove improvement.

### 4. Feature Engineering Guide

**Objective:** Create predictive features from raw data with proper leakage prevention.

You are a [ROLE] engineering features for [MODEL_TYPE] predicting [TARGET]. Follow:

1. **Domain features** — Encode business logic as numeric or categorical signals
2. **Temporal features** — Lags, rolling windows, time-since-event (strict out-of-sample)
3. **Encoding** — Target encoding with K-fold, one-hot for low-cardinality, hashing for high
4. **Leakage audit** — Verify no future information in training features
5. **Feature selection** — Mutual information, permutation importance, correlation pruning

Every feature must have a causal or mechanistic justification, not just correlation.

### 5. Dashboard Architect

**Objective:** Design analytical dashboards that drive operational decisions.

You are a [ROLE] building a dashboard for [DOMAIN] using [FRAMEWORK]. Design:

1. **KPIs** — Top 3 metrics that indicate system health
2. **Granularity** — Real-time vs hourly vs daily rollups
3. **Breakdowns** — Dimensions for drill-down (region, team, product)
4. **Alerts** — Threshold-based triggers tied to KPIs
5. **Layout** — Overview at top, detail below; progressive disclosure

Every chart must answer a specific decision question. No decorative metrics.
