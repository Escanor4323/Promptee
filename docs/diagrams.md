# Promptee (Daedalus) System Architecture Diagrams

## 1. Class Diagram

Shows all entities, their attributes, and relationships in the Promptee system.

```mermaid
classDiagram
    %% Domain Models
    class User {
        +String email
        +String api_key
        +DateTime created_at
    }
    
    class Query {
        +String text
        +String tradeoff_preference
        +DateTime submitted_at
    }
    
    class PromptTemplate {
        +Int id PK
        +String title
        +String objective
        +String full_text
        +List~String~ variables
        +List~String~ applicable_addons
    }
    
    class Result {
        +Int id
        +String title
        +Float hybrid_score
        +String objective
        +List~String~ variables
    }
    
    %% SQLite Models
    class Template {
        +Int id PK
        +String title
        +String objective
        +String full_text
        +List~String~ variables
        +Int milvus_id FK
        +DateTime created_at
    }
    
    class Execution {
        +Int id PK
        +Int template_id FK
        +Float latency_ms
        +Int input_tokens
        +Int output_tokens
        +Float speed_score
        +Float cost_score
        +String addon_mode
        +DateTime created_at
    }
    
    class Feedback {
        +Int id PK
        +Int execution_id FK
        +Int quality_score (1-5)
        +String notes
        +DateTime created_at
    }
    
    %% Vector DB Model
    class MilvusCollection {
        +Int template_id
        +Vector embedding
        +Int milvus_id
        +String title
        +String objective
    }
    
    %% API Models
    class AddOn {
        +String name
        +String mode
        +String suffix
        +String description
    }
    
    class RecommendItem {
        +Int id
        +Int template_id
        +String title
        +String objective
        +String full_text
        +List~String~ variables
        +Float hybrid_score
        +List~AddOn~ applicable_addons
    }
    
    %% Relationships
    User "1" --> "*" Query : submits
    Query "1" --> "*" Result : returns
    Result "1" <-- "1" RecommendItem : derived from
    RecommendItem "1" <-- "1" Template : based on
    
    Template "1" --> "*" Execution : has
    Execution "1" --> "*" Feedback : receives
    
    Template "1" --> "1" MilvusCollection : synced with
    MilvusCollection "1" --> "1" AddOn : has
    
    Execution "*" --> "1" Feedback : evaluated by
    
```


---

## 2. Data Flow Diagram (DFD) - Level 0

Context diagram showing the entire Promptee system as a single process with external entities.

```mermaid
graph TB
    User["👤 User<br/>(CLI)"]
    Backend["📦 Promptee Backend<br/>(FastAPI)"]
    Milvus["🔍 Milvus<br/>(Vector DB)"]
    SQLite["💾 SQLite<br/>(Relational DB)"]
    FileSystem["📁 File System<br/>(Prompt Files)"]
    
    User -->|1. Query| Backend
    Backend -->|2. Search| Milvus
    Backend -->|3. Read/Write| SQLite
    Backend -->|4. Ingest Files| FileSystem
    Backend -->|5. Results| User
    
```

---

## 3. Data Flow Diagram (DFD) - Level 1

Detailed decomposition showing the main processes and data flows within Promptee.

```mermaid
graph TB
    subgraph External["External Entities"]
        User["👤 User<br/>(CLI)"]
        Files["📁 Files<br/>(Prompts)"]
    end
    
    subgraph API["API Layer (FastAPI Routers)"]
        Health["Health Router<br/>GET /health"]
        Ingest["Ingest Router<br/>POST /ingest"]
        Recommend["Recommend Router<br/>POST /recommend"]
        Telemetry["Telemetry Router<br/>POST /telemetry<br/>POST /feedback"]
    end
    
    subgraph Processing["Processing Services"]
        ChunkEmbed["Chunk & Embed<br/>(ingest.py)"]
        Rerank["Rerank Results<br/>(reranker.py)"]
        Metrics["Compute Metrics<br/>(metrics.py)"]
    end
    
    subgraph Storage["Data Storage"]
        Milvus["🔍 Milvus<br/>(Vector DB)"]
        SQLite["💾 SQLite<br/>(Templates, Executions,<br/>Feedback)"]
    end
    
    %% Input flows
    User -->|POST /ingest| Ingest
    Files -->|Read Chunks| ChunkEmbed
    User -->|POST /recommend| Recommend
    User -->|POST /telemetry| Telemetry
    
    %% Processing flows
    Ingest --> ChunkEmbed
    ChunkEmbed -->|Store embeddings| Milvus
    ChunkEmbed -->|Store metadata| SQLite
    
    Recommend -->|Query embedding| Milvus
    Milvus -->|Top-K results| Recommend
    Recommend -->|Rerank| Rerank
    Rerank -->|Read stats| SQLite
    Rerank -->|Results| Recommend
    
    Telemetry -->|Compute scores| Metrics
    Metrics -->|Read feedback| SQLite
    SQLite -->|Avg quality score| Metrics
    Metrics -->|Write execution| SQLite
    
    %% Output flows
    Ingest -->|Ingested count| User
    Recommend -->|Reranked results| User
    Health -->|Status| User
    Telemetry -->|Confirmed| User
    
```

---

## 4. Data Flow Diagram (DFD) - Level 1 Detailed Process Flows

### Process 1: Ingest Pipeline
```mermaid
graph LR
    Input["📄 Input Files"]
    Parse["Parse Files"]
    Chunk["Chunk Text"]
    Embed["Embed Chunks"]
    WriteMilvus["Write to Milvus"]
    WriteSQL["Write to SQLite"]
    Output["✅ Ingested"]
    
    Input --> Parse
    Parse --> Chunk
    Chunk --> Embed
    Embed --> WriteMilvus
    Embed --> WriteSQL
    WriteMilvus --> Output
    WriteSQL --> Output
    
```

### Process 2: Recommendation Pipeline
```mermaid
graph LR
    Query["🔍 Query Text"]
    EmbedQuery["Embed Query"]
    SearchMilvus["Search Milvus"]
    TopK["Top-K Results"]
    ReadStats["Read SQLite Stats"]
    Rerank["Hybrid Rerank<br/>Score"]
    AddOns["Attach AddOns"]
    Return["📊 Results"]
    
    Query --> EmbedQuery
    EmbedQuery --> SearchMilvus
    SearchMilvus --> TopK
    TopK --> ReadStats
    ReadStats --> Rerank
    Rerank --> AddOns
    AddOns --> Return
    
```

### Process 3: Telemetry & Feedback Pipeline
```mermaid
graph LR
    SubmitTelem["📈 Submit Telemetry"]
    ComputeScores["Compute Speed/Cost"]
    ComputeQuality["Compute Quality<br/>Score"]
    ReadFeedback["Read Feedback<br/>from SQLite"]
    WriteExecution["Write Execution<br/>to SQLite"]
    Response["✅ Recorded"]
    
    SubmitTelem --> ComputeScores
    SubmitTelem --> ComputeQuality
    ComputeQuality --> ReadFeedback
    ReadFeedback --> WriteExecution
    ComputeScores --> WriteExecution
    WriteExecution --> Response
    
```

---

## 5. Use Case Diagram - Level 1

High-level use cases showing interactions between user and system.

```mermaid
flowchart TD
    User["👤 User"]
    
    UC1["📥 UC1: Ingest Prompts<br/>Upload and index prompt files"]
    UC2["🔍 UC2: Search Prompts<br/>Find relevant prompts"]
    UC3["⭐ UC3: Get Recommendations<br/>Get reranked results"]
    UC4["📊 UC4: Record Telemetry<br/>Log execution metrics"]
    UC5["💬 UC5: Submit Feedback<br/>Rate execution quality"]
    UC6["💚 UC6: Check Health<br/>Verify system status"]
    
    Milvus["Milvus<br/>Vector DB"]
    SQLite["SQLite<br/>Relational DB"]
    
    User -->|1| UC1
    User -->|2| UC2
    User -->|3| UC3
    User -->|4| UC4
    User -->|5| UC5
    User -->|6| UC6
    
    UC1 --> Milvus
    UC1 --> SQLite
    UC2 --> Milvus
    UC3 --> Milvus
    UC3 --> SQLite
    UC4 --> SQLite
    UC5 --> SQLite
    UC6 --> Milvus
    UC6 --> SQLite
```

---

## 6. Use Case Diagram - Level 2a: Ingest & Recommendation Flows

Detailed workflows for ingest and recommendation operations.

```mermaid
flowchart TD
    User["👤 User"]
    
    subgraph Ingest["📥 UC1: Ingest Workflow"]
        I1["Parse Files"]
        I2["Validate Format"]
        I3["Generate Embeddings"]
        I4["Persist to Milvus"]
        I5["Persist to SQLite"]
    end
    
    subgraph Recommend["⭐ UC3: Recommendation Workflow"]
        R1["Embed Query"]
        R2["Vector Search<br/>Milvus"]
        R3["Fetch Statistics<br/>SQLite"]
        R4["Compute Hybrid Score<br/>alpha*semantic +<br/>beta*quality +<br/>gamma*popularity"]
        R5["Rerank Results"]
        R6["Attach PromptAddOns"]
        R7["Return to User"]
    end
    
    User -->|Upload files| Ingest
    User -->|Submit query| Recommend
    
    I1 --> I2
    I2 --> I3
    I3 --> I4
    I3 --> I5
    I4 & I5 -->|Complete| User
    
    R1 --> R2
    R2 -->|Top-K hits| R3
    R3 -->|Quality scores| R4
    R4 --> R5
    R5 --> R6
    R6 --> R7
    R7 --> User
```

---

## 6. Use Case Diagram - Level 2b: Telemetry, Feedback & Health

Detailed workflows for telemetry, feedback, and health check operations.

```mermaid
flowchart TD
    User["👤 User"]
    
    subgraph Telemetry["📊 UC4: Telemetry Workflow"]
        T1["Submit Execution Data<br/>latency, tokens, tradeoff"]
        T2["Compute Metrics<br/>speed_score, cost_score"]
        T3["Fetch Feedback History<br/>from SQLite"]
        T4["Compute Quality Score<br/>AVG feedback rating"]
        T5["Persist to SQLite<br/>Execution record"]
    end
    
    subgraph Feedback["💬 UC5: Feedback Workflow"]
        F1["Submit Quality Rating<br/>1-5 scale"]
        F2["Validate Rating"]
        F3["Persist to SQLite<br/>Feedback record"]
    end
    
    subgraph Health["💚 UC6: Health Check"]
        H1["Query Milvus Status"]
        H2["Query SQLite Status"]
        H3["Report Health Status"]
    end
    
    User -->|Submit metrics| Telemetry
    User -->|Rate execution| Feedback
    User -->|Check system| Health
    
    T1 --> T2
    T2 --> T3
    T3 --> T4
    T4 --> T5
    T5 -->|Confirmed| User
    
    F1 --> F2
    F2 -->|Valid| F3
    F3 -->|Saved| User
    
    H1 --> H3
    H2 --> H3
    H3 -->|Status| User
```

---

## 7. System Integration Points

### Data Model Relationships
```mermaid
graph TB
    Query["User Query<br/>(text)"]
    EmbedQuery["Query Embedding<br/>(vector)"]
    MilvusHits["Milvus Hits<br/>(template_id, score)"]
    
    Template["Template<br/>(id, title, milvus_id)"]
    Execution["Execution<br/>(template_id, latency,<br/>speed_score, cost_score)"]
    Feedback["Feedback<br/>(execution_id,<br/>quality_score)"]
    
    HybridScore["Hybrid Score<br/>(alpha*semantic +<br/>beta*quality +<br/>gamma*popularity)"]
    
    Final["Final Result<br/>(template_id, hybrid_score,<br/>PromptAddOn)"]
    
    Query --> EmbedQuery
    EmbedQuery --> MilvusHits
    MilvusHits --> Template
    Template --> Execution
    Execution --> Feedback
    Execution --> HybridScore
    Feedback --> HybridScore
    MilvusHits --> HybridScore
    HybridScore --> Final
    
```

---

## 8. Architecture Summary

| Component | Technology | Purpose | Key Tables/Collections |
|-----------|-----------|---------|----------------------|
| **API Gateway** | FastAPI + uvicorn | Request routing, validation | N/A |
| **Vector Database** | Milvus 2.3.3 | Semantic search on embeddings | Collections with `template_id` metadata |
| **Relational Database** | SQLite (aiosqlite) | Execution telemetry, feedback, templates | `templates`, `executions`, `feedback` |
| **Embedding Model** | Configurable (default: all-minilm) | Convert text to vectors | N/A |
| **Reranking** | Hybrid algorithm (alpha/beta/gamma) | Combine semantic + quality scores | Reads from SQLite, uses Milvus scores |
| **CLI** | Go + tooey + tsuey | User interface, terminal rendering | N/A (reads from FastAPI) |

---

## 9. Phase Progression Map

```mermaid
graph LR
    P1["Phase 1<br/>Core API<br/>Ingest+Recommend"]
    P2["Phase 2<br/>Vector RAG<br/>Milvus Integration"]
    P3["Phase 3<br/>Telemetry<br/>SQLite + Metrics"]
    P4["Phase 4<br/>Hybrid Reranking<br/>+ PromptAddOns"]
    P5["Phase 5<br/>CLI TUI<br/>Go + tooey"]
    
    P1 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> P5
    
```

---

---

## 10. Comprehensive Backend Architecture (APIs, Databases & Relations)

Detailed view of all backend routers, services, databases, and their interactions.

```mermaid
graph TB
    subgraph FastAPI["FastAPI Backend (Port 8000)"]
        Health["🏥 Health Router<br/>GET /health<br/>System Status"]
        Ingest["📥 Ingest Router<br/>POST /ingest<br/>Upload PDFs"]
        Recommend["🎯 Recommend Router<br/>POST /recommend<br/>Query Templates"]
        Templates["📋 Templates Router<br/>GET/POST /templates<br/>Manage Templates"]
        Jobs["⚙️ Jobs Router<br/>GET /jobs/:id<br/>Track Async Jobs"]
        AddOns["🔌 AddOns Router<br/>GET /addons<br/>Prompt Modifications"]
        Models["🤖 Models Router<br/>GET/POST /models<br/>Model Config"]
        Preferences["⚙️ Preferences Router<br/>GET/POST /preferences<br/>User Prefs"]
        Telemetry["📊 Telemetry Router<br/>POST /feedback<br/>Metrics & Feedback"]
    end

    subgraph Services["Core Services"]
        PDFParser["PDF Parser<br/>docling converter<br/>Extract text & metadata"]
        Chunker["Document Chunker<br/>Split by prompts<br/>Semantic boundaries"]
        ChildSplitter["Child Splitter<br/>Hierarchical chunks<br/>Parent-child links"]
        IngestValidator["Ingest Validator<br/>Validate inputs<br/>Check duplicates"]
        JobRunner["Job Runner<br/>Async execution<br/>Status tracking"]
        PromptDetector["Prompt Detector<br/>Boundary detection<br/>Segment extraction"]
        BM25Scorer["BM25 Scorer<br/>Lexical ranking<br/>Keyword search"]
        Tokenizer["Tokenizer<br/>Token counting<br/>Cost estimation"]
        RerankingEngine["Hybrid Reranker<br/>BM25 + semantic<br/>AddOn injection"]
        MetricsService["Metrics Service<br/>Compute tradeoffs<br/>Speed/Cost/Quality"]
    end

    subgraph Databases["Data Layer"]
        SQLite["<b>SQLite</b><br/><br/>📋 Templates<br/>├─ id, title, objective<br/>├─ full_text, hash<br/>├─ variables, addons<br/>└─ milvus_id (FK)<br/><br/>📊 Executions<br/>├─ id, template_id (FK)<br/>├─ query, latency<br/>└─ token_count<br/><br/>⭐ Feedback<br/>├─ id, execution_id (FK)<br/>├─ score, quality<br/>└─ timestamp<br/><br/>⚙️ Jobs<br/>├─ id, type, status<br/>├─ metadata, error<br/>└─ created_at<br/><br/>🤖 Models<br/>├─ id, name, type<br/>└─ config<br/><br/>💾 Preferences<br/>├─ user_id, model_id<br/>└─ tradeoff"]
        
        Milvus["<b>Milvus Vector DB</b><br/><br/>📚 Collections<br/>├─ Embeddings (1M+ vectors)<br/>├─ Metadata (template id)<br/>└─ Similarity Index"]
    end

    subgraph External["External Services"]
        OpenAI["OpenAI API<br/>text-embedding-3-small<br/>LLM inference"]
    end

    %% Service to Service flows
    Ingest -->|Parse PDF| PDFParser
    PDFParser -->|Split text| Chunker
    Chunker -->|Extract boundaries| PromptDetector
    PromptDetector -->|Create chunks| ChildSplitter
    ChildSplitter -->|Validate| IngestValidator
    IngestValidator -->|Async job| JobRunner
    
    JobRunner -->|Extract embeddings| OpenAI
    JobRunner -->|Store embeddings| Milvus
    JobRunner -->|Store template| SQLite
    
    Recommend -->|Query job| Jobs
    Recommend -->|Lookup templates| SQLite
    Recommend -->|Vector search| Milvus
    Recommend -->|Rank results| BM25Scorer
    Recommend -->|Rerank| RerankingEngine
    RerankingEngine -->|Apply addons| AddOns
    RerankingEngine -->|Compute metrics| MetricsService
    MetricsService -->|Log execution| Telemetry
    
    Telemetry -->|Store metrics| SQLite
    
    Health -->|Check status| SQLite
    Health -->|Check status| Milvus
    
    Models -->|Manage| SQLite
    Preferences -->|Store| SQLite
    Templates -->|Query| SQLite
    
    Tokenizer -->|Count tokens| Chunker
    Tokenizer -->|Estimate cost| MetricsService

    style FastAPI fill:#4A90E2,color:#fff,stroke:#2E5C8A,stroke-width:3px
    style Services fill:#50C878,color:#fff,stroke:#2D7A4A,stroke-width:2px
    style Databases fill:#FF6B6B,color:#fff,stroke:#B83C3C,stroke-width:2px
    style External fill:#FFA500,color:#fff,stroke:#B37A00,stroke-width:2px
```

---

## 11. Frontend & API Integration Diagram

Shows how the Go TUI communicates with the FastAPI backend through HTTP.

```mermaid
graph TB
    subgraph TUI["Promptee TUI (Go)<br/>internal/tui/"]
        Input["Input Handler<br/>Keyboard & Mouse<br/>Query typing"]
        Prompt["Prompt Selector<br/>Browse templates<br/>Select with Enter"]
        VarFill["Variable Filler<br/>Fill template vars<br/>Dynamic values"]
        Executor["Executor<br/>Run prompt<br/>Stream output"]
        Transcript["Transcript Viewer<br/>Display results<br/>Formatting"]
        History["Chat History<br/>Store sessions<br/>Replay commands"]
    end

    subgraph APIClient["HTTP Client<br/>internal/api/"]
        Health["CheckHealth()<br/>GET /api/v1/health"]
        Recommend["Recommend()<br/>POST /api/v1/recommend"]
        Ingest["Ingest()<br/>POST /api/v1/ingest"]
        GetJob["GetJobStatus()<br/>GET /api/v1/jobs/:id"]
        GetTemplates["GetTemplates()<br/>GET /api/v1/templates"]
        GetAddOns["GetAddOns()<br/>GET /api/v1/addons"]
    end

    subgraph Backend["Backend APIs<br/>port 8000"]
        HealthAPI["Health Router"]
        RecommendAPI["Recommend Router"]
        IngestAPI["Ingest Router"]
        JobAPI["Jobs Router"]
        TemplatesAPI["Templates Router"]
        AddOnsAPI["AddOns Router"]
    end

    subgraph State["Application State"]
        AppState["AppState<br/>├─ CurrentMode<br/>├─ SelectedTemplate<br/>├─ QueryHistory<br/>├─ JobID<br/>└─ LastResults"]
    end

    %% User Interactions
    Input -->|Type query| Prompt
    Prompt -->|Browse & select| VarFill
    VarFill -->|Fill variables| Executor
    Executor -->|Get recommendations| Recommend
    Executor -->|Upload PDF| Ingest
    Executor -->|Track async job| GetJob
    
    %% API Client HTTP calls
    Recommend -->|Query backend<br/>HTTP POST| RecommendAPI
    Ingest -->|Upload file<br/>HTTP POST| IngestAPI
    GetJob -->|Poll status<br/>HTTP GET| JobAPI
    GetTemplates -->|Fetch list<br/>HTTP GET| TemplatesAPI
    GetAddOns -->|Get addons<br/>HTTP GET| AddOnsAPI
    Health -->|Check alive<br/>HTTP GET| HealthAPI
    
    %% Results display
    RecommendAPI -->|Results + scoring<br/>JSON response| Transcript
    Transcript -->|Display formatted| Executor
    Executor -->|Save to history| History
    
    %% State management
    Input -->|Update state| AppState
    Prompt -->|Update selection| AppState
    Executor -->|Track job| AppState
    History -->|Persist| AppState

    style TUI fill:#667EEA,color:#fff,stroke:#4C47D1,stroke-width:3px
    style APIClient fill:#8B5CF6,color:#fff,stroke:#6D28D9,stroke-width:2px
    style Backend fill:#4A90E2,color:#fff,stroke:#2E5C8A,stroke-width:2px
    style State fill:#F59E0B,color:#fff,stroke:#B45309,stroke-width:2px
```

---

## 12. Complete End-to-End Workflow Sequence Diagram

Shows the full interaction sequence from user starting app through getting recommendations.

```mermaid
sequenceDiagram
    actor User
    participant TUI as Promptee TUI
    participant APIClient as HTTP Client
    participant Backend as FastAPI Backend
    participant Jobs as Job Runner
    participant Parser as PDF Parser
    participant Chunker as Document Chunker
    participant Milvus as Milvus Vector DB
    participant SQLite as SQLite
    participant OpenAI as OpenAI API

    User->>TUI: 1. Start app
    TUI->>APIClient: CheckHealth()
    APIClient->>Backend: GET /api/v1/health
    Backend->>Backend: Verify DBs
    Backend-->>APIClient: 200 OK
    APIClient-->>TUI: Connected

    User->>TUI: 2. Upload PDF
    TUI->>APIClient: Ingest(file)
    APIClient->>Backend: POST /api/v1/ingest
    Backend->>Jobs: Create async job_id
    Backend-->>APIClient: {job_id}
    APIClient-->>TUI: Job started

    Jobs->>Parser: Parse PDF
    Parser->>Parser: Extract text + metadata
    Parser->>Chunker: Split by boundaries
    Chunker->>Chunker: Extract prompts
    Chunker->>SQLite: Store templates
    SQLite-->>Chunker: template_ids

    Chunker->>OpenAI: Generate embeddings
    OpenAI-->>Chunker: Vector embeddings
    Chunker->>Milvus: Store vectors
    Milvus-->>Chunker: Confirmed
    
    Jobs->>SQLite: Mark job COMPLETED
    
    TUI->>APIClient: Poll GetJobStatus(job_id)
    APIClient->>Backend: GET /api/v1/jobs/{job_id}
    Backend->>SQLite: Fetch job status
    SQLite-->>Backend: COMPLETED
    Backend-->>APIClient: Status OK
    APIClient-->>TUI: Job done!

    User->>TUI: 3. Type query
    TUI->>TUI: Display templates
    User->>TUI: Select template
    TUI->>TUI: Show variables
    User->>TUI: Fill variables
    
    User->>TUI: 4. Execute prompt
    TUI->>APIClient: Recommend(query, vars)
    APIClient->>Backend: POST /api/v1/recommend
    
    Backend->>Milvus: Semantic search
    Milvus-->>Backend: Top-k similar vectors
    Backend->>SQLite: Fetch template data
    SQLite-->>Backend: Templates + metadata
    
    Backend->>Backend: BM25 lexical ranking
    Backend->>Backend: Rerank (hybrid)
    Backend->>Backend: Inject addons
    Backend->>Backend: Compute metrics
    
    Backend-->>APIClient: Results + scores
    APIClient-->>TUI: Recommendations

    TUI->>TUI: Format results
    TUI->>Transcript: Display with syntax highlighting
    Transcript-->>TUI: Rendered view
    TUI-->>User: Show results

    User->>TUI: 5. Provide feedback
    TUI->>APIClient: SendFeedback(score)
    APIClient->>Backend: POST /api/v1/feedback
    Backend->>SQLite: Store feedback
    SQLite-->>Backend: Confirmed
    Backend-->>APIClient: 200 OK
    APIClient-->>TUI: Saved

    TUI->>History: Store session
    History-->>TUI: Persisted

    style User fill:#FFD700
    style TUI fill:#667EEA,color:#fff
    style APIClient fill:#8B5CF6,color:#fff
    style Backend fill:#4A90E2,color:#fff
    style Jobs fill:#50C878,color:#fff
    style Parser fill:#50C878,color:#fff
    style Chunker fill:#50C878,color:#fff
    style Milvus fill:#FF6B6B,color:#fff
    style SQLite fill:#FF6B6B,color:#fff
    style OpenAI fill:#FFA500,color:#fff
```

---

## Notes

- **Cross-Database Reference**: `Template.milvus_id` (SQLite) stores the Milvus vector ID for potential bidirectional lookups
- **Async Throughout**: All database operations use async/await (FastAPI lifespan, async SQLAlchemy sessions, asyncio context managers)
- **Two-Phase Ingest**: SQLite Template row created first (gets PK), then Milvus insert (gets Milvus ID), then SQLite backfill of `milvus_id`
- **Tradeoff Scoring**: User's `tradeoff_preference` (balanced/speed/cost/quality) adjusts alpha/beta/gamma weights in hybrid reranking
- **PromptAddOns**: System-level templates that can be attached to results based on detected patterns or user preferences
- **Job Queue**: Async PDF ingest uses job runner for long-running operations with status polling from TUI
- **Hybrid Search**: Combines semantic similarity (Milvus) + BM25 lexical ranking + quality feedback scores
- **Stateful TUI**: Application state tracks current mode, selected template, query history, and active job IDs
