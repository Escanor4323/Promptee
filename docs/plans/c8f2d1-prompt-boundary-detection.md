# Enriched Implementation Plan: Prompt-Boundary Detection & Hierarchical Chunking (ADR-006)

This plan overhauls the chunking architecture to introduce a **Parent-Child (Hierarchical) Retrieval** pattern and fixes the boundary detection bug. By isolating prompts deterministically and then fragmenting them into granular "child" chunks for embedding, we solve the paradox of semantic dilution without sacrificing prompt cohesion. It also integrates layout-aware parsing and hybrid BM25 search to maximize retrieval accuracy.

## Proposed Architecture Changes

### 1. Layout-Aware Ingestion & Structuring
- **Target**: `backend/requirements.txt` & `backend/app/services/pdf_parser.py`
- **Change**: Introduce `docling` and `llama-parse` as standard dependencies for parsing. Transition from generic extraction to a layout-aware parser strategy that strips recurring headers/footers and outputs clean Markdown, accurately converting visual titles into explicit `#` headings.

### 2. Deterministic Marker Splitting (Fixing the Bug)
- **Target**: `backend/app/services/prompt_detector.py` (NEW)
- **Change**: Implement a Strategy pattern (`CascadingDetector`) that strictly isolates distinct prompts:
  1. `ObjectiveAnchoredDetector`: Looks for `Objective:` and walks backward/forward. Explicitly rejects numbered lists (e.g., `2.`, `3.`) to fix the over-splitting bug.
  2. `TitlePatternDetector`: Strict regex for Markdown headings or ALL CAPS.
  3. `WholeDocumentDetector`: Fallback if no boundaries exist.
- **Output**: 1 to 25 unfragmented `PromptSpan` objects representing the Parent prompts.

### 3. Validation & Truncation Safeguards
- **Target**: `backend/app/routers/ingest.py`
- **Change**: 
  - **Prompt Limit**: Introduce a strict limit of 25 prompts per ingestion to prevent massive payload processing overhead. If a document yields >25 prompts, return an HTTP 422 error.
  - **Token Limit**: Before passing chunks to the embedding model, introduce a validation step that checks the token count. If any chunk exceeds the embedding model's context window, flag it or return an HTTP 422 rather than allowing the embedding model to silently hard-truncate the data.

### 4. Hierarchical (Parent-Child) Chunking & Storage
- **Target**: `backend/app/services/chunker.py` & `backend/app/routers/ingest.py`
- **Change**: Instead of embedding massive Parent prompts (which leads to semantic dilution):
  - **Parents**: Insert the cohesive `Chunk` objects strictly into the SQLite `Template` table.
  - **Children**: Implement a secondary recursive character splitter configured for small, dense windows (e.g., 250 tokens, 50-token overlap). Split each Parent into multiple Child chunks.
  - **Vectorization**: Embed ONLY the Child chunks. Insert them into Milvus, attaching a `template_id` metadata pointer linking back to the Parent in SQLite.
  - **Dimensionality**: Ensure native API parameters are used for any Matryoshka Representation Learning (MRL) dimensionality truncation.

### 5. BM25 + Dense Hybrid Search Retrieval Execution
- **Target**: `backend/app/db/milvus.py` & `backend/app/routers/recommend.py`
- **Change**: 
  - Update Milvus schema to incorporate a sparse vector field for BM25 keyword matching alongside the dense vector.
  - Execute a hybrid semantic search (BM25 + Dense Cosine Similarity) against the densely packed Child vectors in Milvus.
  - Upon identifying the top Child vectors, extract their `template_id` metadata pointers.
  - Fetch the corresponding full, unfragmented Parent prompts from SQLite and return those to the LLM/user.

## Verification Plan

### Automated Tests
- **`test_prompt_detector.py`**: Unit tests confirming exactly 20 spans are generated from the `prompts.pdf` test fixture, verifying nested bullets are ignored. Add a test asserting an exception/422 is raised if >25 prompts are detected.
- **`test_semantic_chunker.py`**: Verify that 1 Parent prompt correctly generates multiple 250-token Child chunks.
- **`test_ingest_pdf.py`**: Verify SQLite receives exactly 20 rows for the test PDF fixture, while Milvus receives a larger multiple of vectors (the Child chunks). Verify a payload with 26 prompts is rejected with HTTP 422.
- **`test_recommend.py`**: Verify querying a granular concept returns the full Parent prompt, not just a 250-token fragment, and BM25 keywords successfully trigger hits.
