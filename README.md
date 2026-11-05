# VerifyGrid

<p align="center">
  <strong>Enterprise Multi-Source Reconciliation, Discrepancy Detection & Cryptographic Audit Engine</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.143-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=black" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/PostgreSQL-16%20%2F%20Neon-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Tests-535%20Passed-brightgreen" alt="Automated Tests" />
  <img src="https://img.shields.io/badge/Security-Fail--Closed%20Guards-success" alt="Security Fail-Closed" />
</p>

---

## 1. Overview

**VerifyGrid** is a deterministic, high-throughput verification and financial reconciliation platform designed for mission-critical institutional auditing. Built to eliminate silent data loss and false-positive reconciliations, VerifyGrid cross-references disparate tabular datasets (such as academic registrar rosters vs. campus housing registries, or general ledger invoices vs. banking settlement receipts), categorizes discrepancies with mathematical rigor, and establishes an immutable, cryptographically verifiable audit trail.

### Key Engineering Principles
- **Zero Silent Data Loss:** Duplicate parent keys, ambiguous line items, and multi-receipt allocations are explicitly preserved with distinct row lineage rather than overwritten in memory.
- **Strict Financial Semantics:** Valid zero amounts (`$0.00`) are explicitly decoupled from missing, null, or corrupted financial fields, eliminating phantom reconciliations.
- **Fail-Closed Operational Envelopes:** Database migrations and execution scripts enforce endpoint identity verification and transaction ownership protection, structurally preventing accidental mutations to production environments.
- **Maker-Checker Governance:** Built-in separation of duties guarantees that compliance reconciliations prepared by auditors must be independently certified by supervisory checkers.

---

## 2. Key Capabilities

- **Streaming Multi-Format Ingestion:** High-speed streaming parser supporting chunked CSV and Excel (`.xlsx`, `.xls`) workbooks with multi-worksheet selection and custom header row detection for title-preamble spreadsheets.
- **Multi-Cardinality Reconciliation:**
  - **1 : 1 Matching:** Exact, normalized token, phonetic (Double Metaphone), date window delta ($\pm N$ days), and numeric tolerance bounds ($\Delta \le \epsilon$).
  - **1 : Many Split Payments:** Multi-receipt consolidation attributing multiple partial payments against parent invoices without double-crediting.
  - **Many : 1 Batch Settlements:** Bulk remittance consolidation validating batch disbursements against aggregate invoice schedules.
- **Anti-Fraud Global Receipt Sentry:** Intercepts cross-parent receipt collisions, ensuring a payment voucher or receipt ID cannot be credited toward multiple conflicting obligations.
- **Side-by-Side Discrepancy Comparator:** Interactive discrepancy drawer allowing auditors to inspect granular field-level deltas, quarantine unresolved records, and trigger fuzzy threshold tuning.
- **Cryptographic Audit Trail:** Chained SHA-256 event provenance with parent hash validation (`prev_hash` $\to$ `entry_hash`), creating a tamper-evident audit record suitable for regulatory scrutiny.

---

## 3. Platform Interface & Real Screenshots

The following screenshots illustrate VerifyGrid's end-to-end reconciliation workflow, captured directly from live application execution:

### 01. Institutional Authentication & Governance Scope
*Role-scoped authentication enforcing Maker-Checker separation of duties and JWT Bearer security.*
![01_auth_screen](docs/screenshots/01_auth_screen.png)

---

### 02. Audit Workspaces Dashboard
*Project-level multi-tenant workspaces isolating compliance runs across departments and fiscal terms.*
![02_workspace_dashboard](docs/screenshots/02_workspace_dashboard.png)

---

### 03. 5-Step Reconciliation Wizard & Dataset Profiling
*Streaming ingestion interface displaying automated file profiling, row counts, and cryptographic hash verification.*
![03_reconciliation_wizard](docs/screenshots/03_reconciliation_wizard.png)

---

### 04. Heuristic Column Mapping & Key Recommendation
*Automatic candidate key discovery analyzing column synonyms, cardinality, and data uniqueness.*
![04_column_mapping](docs/screenshots/04_column_mapping.png)

---

### 05. Matching Rules & Tolerance Configuration
*Configurable numeric delta thresholds ($\Delta \le \epsilon$), date window margins, and partial payment allowances.*
![05_rules_configuration](docs/screenshots/05_rules_configuration.png)

---

### 06. Reconciliation Summary & Discrepancy Breakdown
*Comprehensive settlement breakdown categorizing exact matches, partial settlements, numeric discrepancies, and orphans.*
![06_verification_results](docs/screenshots/06_verification_results.png)

---

### 07. Granular Discrepancy Record Inspector
*Side-by-side field comparator displaying record-level lineage, candidate matches, and review options.*
![07_record_inspector](docs/screenshots/07_record_inspector.png)

---

### 08. Cryptographic Audit Trail & Event Verification
*Immutable SHA-256 chained audit log tracking reconciliation provenance, reviewer actions, and sign-offs.*
![08_cryptographic_audit](docs/screenshots/08_cryptographic_audit.png)

---

## 4. System Architecture & Workflows

### High-Level System Architecture

```mermaid
flowchart TB
    subgraph Client ["Frontend Client (SPA)"]
        UI["React 19 + TypeScript"]
        Context["Auth & Workspace Context"]
        API["Typed Fetch API Client"]
        UI --> Context --> API
    end

    subgraph Gateway ["Security & API Layer"]
        CORS["CORS Middleware"]
        Auth["JWT Scope & RBAC Enforcer"]
        Routers["FastAPI Routers (14 Modules)"]
        API --> CORS --> Auth --> Routers
    end

    subgraph Engines ["Core Processing Engines"]
        Pre["Streaming Preprocessor\n(CSV / XLSX Chunk Hashing)"]
        Norm["Normalization & Inverted Index\n(RapidFuzz C++ Bindings)"]
        Agg["Financial Aggregator\n(Split-Payment & Sentry)"]
        Audit["Cryptographic Audit Logger\n(SHA-256 Chained Hashes)"]

        Routers --> Pre
        Routers --> Norm --> Agg --> Audit
    end

    subgraph Data ["Data Persistence Layer"]
        PG[(PostgreSQL / Neon Serverless)]
        SQLite[(Local SQLite Offline Mode)]
        Storage[(Local Encrypted Chunk Storage)]

        Agg --> PG
        Audit --> PG
        Pre --> Storage
    end

    subgraph Guard ["Infrastructure Safety"]
        TargetGuard["Fail-Closed Migration Guard (migrations/env.py)\nCaller Transaction Preservation & Identity Verifier"]
        TargetGuard -.-> PG
    end
```

### End-to-End Reconciliation Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Auditor as Compliance Auditor (Maker)
    actor Supervisor as Audit Supervisor (Checker)
    participant UI as React Frontend
    participant API as FastAPI Backend
    participant Engine as Aggregation Engine
    participant DB as PostgreSQL Database

    Auditor->>UI: Upload Source Spreadsheets (e.g. Student Roster vs Bursar)
    UI->>API: POST /projects/{id}/files
    API-->>UI: Chunk SHA-256 & Dataset Profiles

    Auditor->>UI: Configure Match Keys & Tolerances (Delta <= 0.01)
    UI->>API: POST /verification/run
    API->>Engine: Reconcile(Parent, Children, Rules)

    rect rgb(240, 248, 255)
        Note over Engine: 1. Inverted Index Tokenization & RapidFuzz Scoring
        Note over Engine: 2. Split-Payment Consolidation & Receipt Sentry
        Note over Engine: 3. Decouple Valid $0.00 from Corrupt Amounts
        Note over Engine: 4. Chained SHA-256 Event Log Construction
    end

    Engine->>DB: Persist VerificationRun & AuditEvent
    Engine-->>UI: Discrepancy Breakdown & Match Metrics
    Auditor->>UI: Propose Review Decisions & Request Sign-Off
    UI->>API: POST /sign-off/propose
    API-->>Supervisor: Pending Verification Alert
    Supervisor->>UI: Inspect Discrepancy Clusters & Audit Hashes
    Supervisor->>UI: Approve Formal Sign-Off
    UI->>API: POST /sign-off/approve
    API->>DB: Record Cryptographic Sign-Off Block
    API-->>UI: Certification Complete
```

---

## 5. Technical Stack

| Layer | Technologies | Key Capabilities |
|---|---|---|
| **Backend** | Python 3.12+, FastAPI 0.143, Pydantic v2, SQLAlchemy 2.1 | Asynchronous REST API, strict schema validation, type-safe database ORM. |
| **Matching Engine** | RapidFuzz 3.14 (C++), Levenshtein, Double Metaphone | High-speed string distance, fuzzy token sorting, phonetics, date delta calculation. |
| **Frontend** | React 19.2, TypeScript 6.0, Vite 8.3, Lucide Icons | Responsive SPA, multi-step reconciliation wizard, side-by-side record comparison. |
| **Database** | PostgreSQL 16, Neon Serverless, SQLite (Offline) | Multi-tenant relational schema, JSONB discrepancy storage, connection pooling. |
| **Safety & Tooling**| Alembic 1.20, Fail-Closed Target Guard, Pytest, Vitest | Target-bound migration safety, transaction ownership preservation, hermetic testing. |

---

## 6. Repository Structure

```
verifygrid/
├── .github/
│   ├── ISSUE_TEMPLATE/        # Standardized bug report and feature request templates
│   ├── workflows/             # GitHub Actions CI for backend and frontend test suites
│   ├── PULL_REQUEST_TEMPLATE  # Comprehensive review and verification checklist
│   └── SECURITY.md            # Coordinated vulnerability disclosure policy
├── backend/
│   ├── app/
│   │   ├── api/               # REST API endpoints (auth, projects, files, verification, etc.)
│   │   ├── core/              # Security (JWT, bcrypt), configuration settings
│   │   ├── db/                # SQLAlchemy session lifecycle, base declarative metadata
│   │   ├── models/            # Relational models (User, Project, Run, AuditEvent, etc.)
│   │   ├── schemas/           # Pydantic validation and serialization schemas
│   │   ├── services/          # Business logic: aggregation_engine, matching_engine, profiling
│   │   └── utils/             # Normalization, tokenization, and string cleaning utilities
│   ├── migrations/            # Alembic migrations with fail-closed target guard (env.py)
│   └── tests/                 # Automated pytest test suites (449 offline tests, 76 guard tests)
├── frontend/
│   ├── src/
│   │   ├── components/        # React 19 UI components (Wizard, Inspector, Dashboard, Sidebar)
│   │   ├── context/           # Authentication state and JWT token lifecycle
│   │   ├── services/          # Typed API client and column mapping heuristics
│   │   └── types/             # Domain TypeScript interfaces mirroring backend schemas
│   └── tests/                 # Node.js native logic tests and Vitest component tests (86 tests)
└── docs/
    ├── ARCHITECTURE.md        # Comprehensive system architecture & data flow specification
    ├── VERIFICATION_ENGINE.md # Reconciliation algorithms, financial aggregation, & benchmarks
    ├── SECURITY.md            # Maker-Checker governance, target guard, & cryptographic audit
    ├── TESTING.md             # Automated test matrix, isolation safeguards, & execution guide
    └── screenshots/           # Authentic screenshots captured from live application runs
```

---

## 7. Installation & Local Setup

### Prerequisites
- **Python 3.12+**
- **Node.js 20+** and **npm**
- **Git**

### 1. Backend Setup (Local Offline Mode)

VerifyGrid supports zero-setup local execution using an isolated SQLite database, requiring no external PostgreSQL server:

```bash
# Clone the repository
git clone https://github.com/ThunderSkull7/verifygrid.git
cd verifygrid/backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\Activate.ps1

# Install backend dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure local development environment (SQLite fallback)
export DATABASE_URL="sqlite:///./dev.db"  # On Windows: $env:DATABASE_URL="sqlite:///./dev.db"

# Initialize local database tables
python -c "import app.models; from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(bind=engine)"

# Start the FastAPI backend server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

*Interactive Swagger API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).*

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd ../frontend

# Install frontend dependencies
npm install

# Start Vite development server
npm run dev
```

*The application interface will be live at [http://127.0.0.1:5173](http://127.0.0.1:5173).*

### 3. Target-Guarded Database Migrations (PostgreSQL)

When running migrations against PostgreSQL, VerifyGrid enforces fail-closed target verification:

```bash
cd backend

# Applying migrations to local loopback PostgreSQL
export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/verifygrid"
alembic upgrade head

# Applying migrations to production requires explicit target acknowledgement
export DATABASE_URL="<production-url>"
export VERIFYGRID_TARGET="production"
export VERIFYGRID_ACKNOWLEDGE_PRODUCTION_MIGRATION="true"
alembic upgrade head
```

---

## 8. Verification & Test Execution

VerifyGrid maintains an automated test matrix of **535+ tests** across backend and frontend codebases:

```
========================= Test Matrix Summary =========================
Backend Non-Postgres Suite:   449 passed, 21 skipped (~25 s)
Target Guard Safety Suite:    76 passed (100% pass rate) (~1.8 s)
Financial Aggregation Suite:  39 passed (100% pass rate) (~1.2 s)
Frontend Full Suite:          86 passed (29 logic + 57 components) (~5.5 s)
=======================================================================
```

### Run Backend Tests

```bash
cd backend
source .venv/bin/activate

# Execute complete offline backend test suite
pytest tests -m "not postgres"

# Execute migration target guard tests specifically
pytest tests/test_migration_env_guard.py -v

# Execute financial aggregation correctness regression tests specifically
pytest tests/test_financial_aggregation_batches_a_d.py -v
```

### Run Frontend Tests

```bash
cd frontend

# Execute complete frontend test suite (logic + components)
npm test

# Run individual test suites
npm run test:logic        # 29 fast Node.js logic tests
npm run test:components   # 57 Vitest React component tests
```

---

## 9. Engineering Highlights & Design Decisions

### 1. Fail-Closed Target Guard with Caller Transaction Safety
- **Context:** Database migrations often execute in shared test harnesses or transactional contexts where an existing caller already manages a transaction.
- **Decision:** In `backend/migrations/env.py`, the target guard inspects `connection.in_transaction()`. If the caller already owns a transaction, the guard **never** invokes `connection.rollback()` or `connection.commit()` on identity failures. This preserves unrelated caller state and fails closed cleanly.

### 2. Elimination of Phantom Zero Reconciliations
- **Context:** Financial reconciliation logic commonly coerced `clean_numeric(val) or 0.0`. Under this behavior, missing amounts or non-numeric corrupted strings collapsed into `0.0`, triggering false-positive matches against zero-balance line items.
- **Decision:** Built strict numeric distinguishing in `aggregation_engine.py`: valid zero amounts (`$0.00`) are treated as numerical zeros, while missing or unparseable fields trigger a `DATA_INTEGRITY_DISCREPANCY` with `CRITICAL` severity, preventing false reconciliations.

### 3. Anti-Fraud Global Receipt Sentry
- **Context:** In 1:Many split payments, a single receipt or credit voucher could be claimed by multiple parent invoices, silently double-crediting balances across accounts.
- **Decision:** Implemented an in-memory `global_receipt_registry` that validates receipt ownership across all parent groups, halting double-counting and raising `DUPLICATE_RECEIPT_COLLISION` alerts.

---

## 10. Operational Status & Roadmap

### Completed Milestones
- [x] **Core Verification Engine:** Multi-pass string normalization, RapidFuzz fuzzy scoring, and date delta windows.
- [x] **Financial Aggregation Corrections (Batches A–D):** Duplicate parent grouping, valid zero distinction, orphan collision safety, explicit partial payment semantics.
- [x] **Security Hardening (F-06A & F-06B):** Staging vs. production endpoint isolation, transaction ownership safety.
- [x] **Full-Stack UI & Wizard:** React 19 5-step reconciliation wizard, side-by-side discrepancy comparator, and cryptographic audit log.

### Production Readiness Notice
> [!NOTE]
> While VerifyGrid is fully functional with passing automated test suites, **live production database migrations remain gated** behind final staging rehearsals and dry-run backup verification.

---

## 11. Author

**Shahab** — Software Engineer<br />
GitHub: [@ThunderSkull7](https://github.com/ThunderSkull7)<br />
Project Repository: [https://github.com/ThunderSkull7/verifygrid](https://github.com/ThunderSkull7/verifygrid)
