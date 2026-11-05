# VerifyGrid System Architecture

This document provides a comprehensive technical overview of VerifyGrid's system architecture, detailing the end-to-end data flow, frontend client structure, backend service decomposition, database lineage, and fail-closed migration safeguards.

---

## 1. High-Level Architecture Overview

VerifyGrid is an enterprise-grade multi-source reconciliation, discrepancy detection, and cryptographic audit platform designed for financial, academic, and administrative record auditing.

```mermaid
flowchart TB
    subgraph Client ["Client Layer (Browser)"]
        UI["React 19 + TypeScript SPA"]
        State["Context State (Auth, Project, Dataset)"]
        APIClient["Typed API Client (Fetch + Bearer Token)"]
        UI --> State
        State --> APIClient
    end

    subgraph Gateway ["Transport & Security Gateway"]
        CORS["FastAPI CORS Middleware"]
        AuthMid["Bearer JWT Authentication & Scope Validation"]
        APIClient --> CORS --> AuthMid
    end

    subgraph Backend ["FastAPI Application Services"]
        RouterAuth["Auth Router (/auth)"]
        RouterProjects["Projects Router (/projects)"]
        RouterFiles["Files Router (/projects/{id}/files)"]
        RouterPre["Preprocessing Router (/preprocessing)"]
        RouterVerify["Verification Router (/verification)"]
        RouterRules["Rule Engine Router (/rules)"]
        RouterTemplates["Templates & Recipes Router (/templates, /recipes)"]
        RouterAudit["Audit & Sign-Off Router (/audit, /sign-off)"]

        AuthMid --> RouterAuth
        AuthMid --> RouterProjects
        AuthMid --> RouterFiles
        AuthMid --> RouterPre
        AuthMid --> RouterVerify
        AuthMid --> RouterRules
        AuthMid --> RouterTemplates
        AuthMid --> RouterAudit
    end

    subgraph Engine ["Core Processing Engines"]
        PreEngine["Streaming Preprocessing Engine\n(CSV / Excel XLSX chunk parsing, hash generation)"]
        NormEngine["Record Normalization & Inverted Index\n(RapidFuzz tokenization, phonetic, date, currency)"]
        AggEngine["Rule Engine & Aggregator\n(1:1, 1:Many, Split-Payment, Zero-Value Distinction)"]
        AuditEngine["Cryptographic Audit Trail\n(SHA-256 chained hash event provenance)"]

        RouterFiles --> PreEngine
        RouterVerify --> NormEngine --> AggEngine --> AuditEngine
    end

    subgraph Data ["Persistence Layer"]
        DB[(PostgreSQL / Neon Serverless\nSQLite Local Isolation)]
        Storage[(Local Encrypted Dataset Storage)]

        AggEngine --> DB
        AuditEngine --> DB
        RouterProjects --> DB
        PreEngine --> Storage
    end

    subgraph Guard ["Safety & Operational Envelope"]
        TargetGuard["Fail-Closed Migration Guard (migrations/env.py)\nStrict Target & Server Identity Verification"]
        TargetGuard -.-> DB
    end
```

---

## 2. Frontend Client Architecture

The frontend is built with **React 19.2**, **TypeScript 6.0**, and **Vite 8.3**. It is structured as an interactive single-page application (SPA) focused on clarity, responsiveness, and resilient error recovery.

### Component Decomposition

```
frontend/src/
├── components/
│   ├── AuthScreen.tsx           # Institutional authentication & self-registration
│   ├── Sidebar.tsx              # Workspace navigation, tenant switching, system status
│   ├── ProjectsView.tsx         # Audit workspace management, creation, dataset inspection
│   ├── ReconciliationWizard.tsx  # Multi-step reconciliation workflow:
│   │                            #   Step 1: File upload & schema profiling
│   │                            #   Step 2: Candidate column mapping & key selection
│   │                            #   Step 3: Verification rule & tolerance definition
│   │                            #   Step 4: Execution trigger & progress monitoring
│   ├── VerificationResults.tsx  # Reconciliation metrics, discrepancy categorisation
│   ├── RecordInspector.tsx      # Side-by-side discrepancy comparator & audit drawer
│   ├── QuarantineView.tsx       # Quarantined & unmapped record resolution table
│   ├── BulkReviewModal.tsx      # Cluster-based bulk sign-off and review workflows
│   ├── AuditHistoryView.tsx     # Cryptographic audit log viewer & hash verification
│   └── AppearanceControl.tsx    # Theme, accessibility, and high-contrast controls
├── context/
│   ├── AuthContext.tsx          # JWT token lifecycle, refresh, and session expiration
│   └── authContextDef.ts        # Context types and interface contracts
├── services/
│   └── api.ts                   # Centralized typed HTTP client with Bearer auth injection
└── types/
    └── index.ts                 # End-to-end domain interfaces matching backend Pydantic schemas
```

### State Management & Lifecycle

- **Authentication State (`AuthContext`):** Tokens are securely stored in browser local storage under `verifygrid_token`. Network requests automatically inject `Authorization: Bearer <token>`. Interceptors catch `401 Unauthorized` responses and cleanly transition the user to the login screen without losing unsaved project identifiers.
- **Dataset Workspace State (`ReconciliationWizard`):** Manages multi-file metadata, selected worksheet tabs for Excel workbooks (`.xlsx`), custom header rows for spreadsheets with preamble banners, and streaming upload states.
- **Side-by-Side Record Comparison:** Discrepancies are categorized into exact matches, partial matches, missing child/parent keys, and tolerance breaches. Clicking any record loads its full field lineage into `RecordInspector.tsx`.

---

## 3. Backend Service Architecture

The backend is built with **FastAPI 0.143**, **SQLAlchemy 2.1 (2.0-style)**, and **Pydantic 2.14**. It follows a decoupled service-layer pattern where routers delegate complex domain calculations to dedicated service engines.

### Router Decomposition

| Router Module | Mount Point | Core Responsibilities |
|---|---|---|
| `app.routers.auth` | `/api/v1/auth` | User registration, login, JWT token generation, `/me` profile inspection. |
| `app.routers.projects` | `/api/v1/projects` | Multi-tenant workspace creation, listing, updating, and project-level RBAC. |
| `app.routers.files` | `/api/v1/projects/{id}/files` | Chunked file upload, format validation, streaming storage, SHA-256 integrity hashing. |
| `app.routers.preprocessing` | `/api/v1/preprocessing` | Schema profiling, automated data type inference, duplicate row detection, column recommendations. |
| `app.routers.verification` | `/api/v1/verification` | Multi-source reconciliation execution, discrepancy list generation, side-by-side inspection. |
| `app.routers.rules` | `/api/v1/rules` | Reconciliation rule authoring, validation, preview against sample data, fuzzy threshold tuning. |
| `app.routers.templates` | `/api/v1/templates` | Higher-education and enterprise reconciliation templates (Tuition vs Bursar, Payroll vs GL). |
| `app.routers.recipes` | `/api/v1/recipes` | Parameterized verification recipe storage, execution, and versioning. |
| `app.routers.audit` | `/api/v1/audit` | Cryptographic audit trail logging, SHA-256 chained hash verification, sign-off state transitions. |
| `app.routers.health` | `/api/v1/health` | Service liveness, readiness probes, and database ping verification (`/health/db`). |

---

## 4. Verification & Processing Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Auditor as Compliance Auditor
    participant UI as React Frontend
    participant API as FastAPI Router
    participant Pre as Preprocessing Service
    participant Engine as Aggregation Engine
    participant DB as PostgreSQL Database

    Auditor->>UI: Upload Source Datasets (e.g., SIS Roster + Residence)
    UI->>API: POST /projects/{id}/files (Multipart Form)
    API->>Pre: Hash & Store Dataset Chunk
    Pre-->>API: File ID & SHA-256 Checksum
    API-->>UI: Upload Confirmation

    Auditor->>UI: Configure Matching Keys & Financial Tolerances
    UI->>API: POST /verification/run
    API->>Engine: Reconcile(Parent, Children, Rules)
    
    rect rgb(240, 248, 255)
        Note over Engine: Phase 1: Inverted Index & Key Normalization
        Note over Engine: Phase 2: RapidFuzz Levenshtein & Exact Clustering
        Note over Engine: Phase 3: Split-Payment & 1:Many Aggregation
        Note over Engine: Phase 4: Zero-Value vs Missing Amount Distinction
        Note over Engine: Phase 5: Global Receipt Collision Detection
    end

    Engine->>DB: Persist VerificationRun, Discrepancies, and AuditLog
    Engine-->>API: Summary Metrics & Result ID
    API-->>UI: Verification Complete (Matches, Discrepancies, Unmatched)
    UI-->>Auditor: Render Interactive Dashboard & Record Inspector
```

---

## 5. Database Architecture & Schema Lineage

### Primary Entities & Relationships

```mermaid
erDiagram
    USERS ||--o{ PROJECTS : owns
    PROJECTS ||--o{ SOURCE_FILES : contains
    PROJECTS ||--o{ VERIFICATION_RUNS : executes
    SOURCE_FILES ||--o{ PREPROCESSED_DATASETS : generates
    VERIFICATION_RUNS ||--o{ DISCREPANCIES : detects
    VERIFICATION_RUNS ||--o{ AUDIT_LOGS : records
    VERIFICATION_RUNS ||--o{ SIGN_OFFS : approves

    USERS {
        uuid id PK
        string email UK
        string hashed_password
        string role
        boolean is_active
        timestamp created_at
    }

    PROJECTS {
        uuid id PK
        uuid owner_id FK
        string name
        string description
        timestamp created_at
    }

    SOURCE_FILES {
        uuid id PK
        uuid project_id FK
        string filename
        string file_path
        string sha256_hash
        integer row_count
        timestamp uploaded_at
    }

    VERIFICATION_RUNS {
        uuid id PK
        uuid project_id FK
        string status
        jsonb configuration
        integer total_records
        integer matched_records
        integer discrepancy_count
        timestamp executed_at
    }

    DISCREPANCIES {
        uuid id PK
        uuid run_id FK
        string discrepancy_type
        string severity
        jsonb source_record
        jsonb target_record
        jsonb differences
        string status
    }

    AUDIT_LOGS {
        uuid id PK
        uuid run_id FK
        uuid user_id FK
        string action
        string prev_hash
        string entry_hash
        jsonb metadata
        timestamp created_at
    }
```

### Multi-Engine Persistence Strategy
- **Production Persistence:** PostgreSQL / Neon Serverless (with connection pooling via PgBouncer or direct pool).
- **Local Isolated Development:** SQLite compatibility (`sqlite:///demo.db`) enables frictionless offline development, hermetic testing, and screenshot capture without establishing remote connections.

---

## 6. Migration Safeguards & Operational Security

VerifyGrid implements an explicit, fail-closed database migration guard located in `backend/migrations/env.py`.

### Safeguard Principles
1. **Target Identity Validation:** Verifies that connection URLs, hostname endpoints, and server variables match approved staging or production configurations.
2. **Production Endpoint Isolation:** Staging environments are structurally prohibited from connecting to either hardcoded production endpoints or dynamically configured production endpoints.
3. **Transaction Ownership Safety:** Caller-owned transactions are strictly preserved. The migration guard never calls `rollback()` or `commit()` on connections where a caller transaction was already active, ensuring zero unintended state rollbacks.
4. **Neon Serverless Identity Checks:** When connecting to cloud Postgres instances, the guard inspects server endpoint identities (`SHOW neon.project_id` / server parameters) to prevent misdirected migrations.
