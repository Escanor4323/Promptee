# a7f3c2 — Semantic Chunking for PDF Ingestion

**Change type:** Feature  
**Scope:** Backend only (`backend/`)  
**Status:** APPROVED

---

## What
Extend the `/api/v1/ingest` pipeline to accept `.pdf` files alongside `.md`. PDFs are parsed to text, then split by a semantic chunker that respects logical prompt boundaries down to the paragraph level. To optimize storage and keep Milvus clean, the heavy `full_text` will be stored in SQLite and deduplicated via a content hash, with Milvus storing only the embeddings and metadata.

## Why
Currently only markdown files can be ingested. Users who store prompts in PDF documents have no path in. Semantic chunking ensures that each chunk is a complete, coherent prompt. Moving the `full_text` to the relational DB deduplicates heavy text via hashing and reduces vector database overhead.

## How
- **Relational DB Storage & Hashing**: Move `full_text` from Milvus to the SQLite `templates` table alongside a unique `content_hash`.
- **Deduplication**: During ingestion, hash the prompt content. If it already exists, skip embedding/insertion to Milvus.
- **PDF Parsing**: New `pdf_parser.py` using `pypdf`.
- **Semantic Chunking**: New `semantic_chunker.py` that intelligently breaks down content by headings (`#`), numbered sections (`1.`), ALL CAPS headers, or falls back to paragraphs and sentences.
- **Router Updates**: Fetch `full_text` dynamically from SQLite during recommendations.

---

## Phases

### Phase 1: Database Storage Refactor (Milvus -> SQLite)
1. **`backend/app/models/templates.py`**
   - Add `content_hash = Column(String(64), unique=True, index=True, nullable=False)`.
   - Add `full_text = Column(String, nullable=False)`.
2. **Alembic Migration**
   - Generate an Alembic migration using `alembic revision --autogenerate -m "add_full_text_and_hash_to_templates"`.
3. **`backend/app/db/milvus.py`**
   - Remove `full_text_field` from the Milvus `CollectionSchema`.
   - Remove `full_text` from the insert and search functions.

### Phase 2: PDF Parsing & Semantic Chunking Layer
4. **`backend/requirements.txt`** — add `pypdf>=4.0.0`
5. **`backend/app/services/pdf_parser.py`** (NEW)
   - `extract_text(path: str) -> str`
   - `is_pdf(path: str) -> bool`
6. **`backend/app/services/semantic_chunker.py`** (NEW)
   - `chunk_semantic(text: str) -> list[Chunk]`
   - Priority-ordered splits: Headings -> Numbered sections -> ALL CAPS -> Paragraphs -> Sentences.
7. **`backend/app/services/chunker.py`**
   - Add `chunk_file_auto(path: str)` dispatcher for `.md`, `.pdf`, etc.

### Phase 3: API Router Updates
8. **`backend/app/routers/ingest.py`**
   - Accept `.pdf` extension, directory glob `*.md` + `*.pdf`.
   - Hash `chunk.full_text` and deduplicate before inserting into SQLite/Milvus.
9. **`backend/app/routers/recommend.py`**
   - Query SQLite `templates` to fetch `full_text` using `template_id`s returned by Milvus.

### Phase 4: Integration Tests
10. **Test Coverage**
    - `test_pdf_parser.py` (NEW)
    - `test_semantic_chunker.py` (NEW) - verifying paragraph/sentence fallbacks.
    - `test_ingest_pdf.py` (NEW) - verifying SQLite full_text insertion and deduplication.
    - Update `test_e2e_pipeline.py` & `test_recommend.py` for new search flow.

---

## Files Changed
| File | Action |
|------|--------|
| `backend/requirements.txt` | Modified |
| `backend/app/models/templates.py` | Modified |
| `backend/alembic/versions/...` | New |
| `backend/app/db/milvus.py` | Modified |
| `backend/app/services/pdf_parser.py` | New |
| `backend/app/services/semantic_chunker.py` | New |
| `backend/app/services/chunker.py` | Modified |
| `backend/app/routers/ingest.py` | Modified |
| `backend/app/routers/recommend.py` | Modified |
| `backend/tests/test_pdf_parser.py` | New |
| `backend/tests/test_semantic_chunker.py` | New |
| `backend/tests/test_ingest_pdf.py` | New |

---

## Success Criteria
- [ ] Alembic migration successfully adds `full_text` and `content_hash` to SQLite.
- [ ] POST `/api/v1/ingest` with `.pdf` path returns 200, creates SQLite records, and avoids duplicate Milvus insertions.
- [ ] Single large PDFs with no headers are broken down into paragraphs (no giant chunks).
- [ ] Milvus schema no longer contains `full_text`.
- [ ] `recommend` endpoint successfully returns full results by joining Milvus searches with SQLite text.
- [ ] Coverage ≥80% on `pdf_parser.py` and `semantic_chunker.py`.
- [ ] All existing tests pass.
