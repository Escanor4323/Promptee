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

## Notes

- **Cross-Database Reference**: `Template.milvus_id` (SQLite) stores the Milvus vector ID for potential bidirectional lookups
- **Async Throughout**: All database operations use async/await (FastAPI lifespan, async SQLAlchemy sessions, asyncio context managers)
- **Two-Phase Ingest**: SQLite Template row created first (gets PK), then Milvus insert (gets Milvus ID), then SQLite backfill of `milvus_id`
- **Tradeoff Scoring**: User's `tradeoff_preference` (balanced/speed/cost/quality) adjusts alpha/beta/gamma weights in hybrid reranking
- **PromptAddOns**: System-level templates that can be attached to results based on detected patterns or user preferences
