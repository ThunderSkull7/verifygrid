# VerifyGrid Backend

VerifyGrid Backend is a high-performance, deterministic data verification and reconciliation service built with FastAPI, SQLAlchemy 2.0, PostgreSQL, and Alembic. It ingests tabular datasets (CSV and XLSX), normalizes schema and row data, matches records across single or composite primary/business keys, computes discrepancy classifications, and exports audit-ready reports.

---

## 1. Architectural Overview

```
                      +-----------------------------------+
                      |         FastAPI REST API          |
                      |   (/api/v1 - Auth, Projects,      |
                      |    Files, Preprocess, Verify)     |
                      +-----------------+-----------------+
                                        |
     +-------------------+--------------+--------------+--------------------+
     |                   |                             |                    |
     v                   v                             v                    v
+---------+     +------------------+          +-----------------+   +---------------+
| Auth &  |     | Ingestion &      |          | Verification    |   | Export        |
| Security|     | Preprocessing    |          | Engine          |   | Service       |
| (JWT,   |     | (CSV/XLSX clean, |          | (Deterministic  |   | (CSV, XLSX,   |
| bcrypt) |     |  typing, nulls)  |          |  key matching,  |   |  JSON reports)|
+----+----+     +--------+---------+          |  discrepancies) |   +-------+-------+
     |                   |                    +--------+--------+           |
     |                   |                             |                    |
     +-------------------+--------------+--------------+--------------------+
                                        |
                                        v
                      +-----------------------------------+
                      |   PostgreSQL / SQLite (SQLAlchemy)|
                      |  Projects, Users, SourceFiles,    |
                      |  VerificationRuns, Discrepancies  |
                      +-----------------------------------+
```

---

## 2. Directory Layout & Key Modules

```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py              # JWT token generation, user registration & /me
│   │       │   ├── projects.py          # Project workspace CRUD operations
│   │       │   ├── uploads.py           # Project-scoped CSV/XLSX file ingestion
│   │       │   ├── preprocessing.py     # Schema profiling & row normalization trigger
│   │       │   ├── verification.py      # In-memory verify & persistent verification run endpoints
│   │       │   └── exports.py           # Multi-format report export (CSV, XLSX, JSON)
│   │       └── router.py                # Main v1 APIRouter mounting all endpoints + /health
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings (DB URLs, JWT secret, CORS, max file size)
│   │   └── security.py                  # Password hashing (bcrypt) and JWT encode/decode logic
│   ├── db/
│   │   ├── base.py                      # SQLAlchemy DeclarativeBase
│   │   └── session.py                   # Engine initialization & get_db dependency sessionmaker
│   ├── models/
│   │   ├── user.py                      # User ORM model (email, hashed_password)
│   │   ├── project.py                   # Project ORM model (scoped workspaces)
│   │   ├── source_file.py               # SourceFile ORM model (path, file_type, status, metadata)
│   │   └── verification_run.py          # VerificationRun & DiscrepancyResult models
│   ├── schemas/
│   │   ├── auth.py                      # UserCreate, UserResponse, TokenResponse
│   │   ├── project.py                   # ProjectCreate, ProjectResponse
│   │   ├── upload.py                    # SourceFileResponse, FileUploadResult
│   │   ├── preprocessing.py             # PreprocessingConfig, ColumnProfile, PreprocessingResult
│   │   ├── verification.py              # VerificationRequest, VerificationResponse, Summary
│   │   └── export.py                    # Export format filters & query schemas
│   ├── services/
│   │   ├── ingestion.py                 # File validation, size limits, disk saving to storage/uploads
│   │   ├── preprocessing.py             # Safe decoding, header normalization, data typing, null canonicalization
│   │   ├── project_service.py           # Project creation and user scoping logic
│   │   ├── verification_engine.py       # Core reconciliation logic, composite key matching, difference scoring
│   │   └── export_service.py            # Stream generation for CSV, XLSX (openpyxl), and JSON exports
│   ├── utils/
│   │   └── normalization.py             # Cleaners for numbers, currencies, dates, booleans, and snake_case
│   └── main.py                          # FastAPI application factory, CORS middleware, global routers
├── migrations/                          # Alembic environment and database version migrations
├── storage/uploads/                     # Local file storage for uploaded datasets (MVP)
├── tests/                               # Comprehensive pytest automated test suite
├── .env.example                         # Environment variable template
├── alembic.ini                          # Alembic database migration config
└── requirements.txt                     # Backend Python dependencies
```

---

## 3. Technology Stack

- **Python 3.12+**
- **Web Framework**: FastAPI (Starlette under the hood)
- **ASGI Server**: Uvicorn
- **ORM & Database Driver**: SQLAlchemy 2.0 with `psycopg` (version 3) for PostgreSQL
- **Database Migrations**: Alembic
- **Validation**: Pydantic v2 & `pydantic-settings`
- **File Parsing & Exports**: Python standard `csv`, `openpyxl` (streaming XLSX), `python-dateutil`
- **Security**: `passlib[bcrypt]` / `bcrypt` and `pyjwt` (HS256)
- **Testing**: `pytest`, `pytest-asyncio`, `httpx` (FastAPI TestClient), with SQLite in-memory isolation for unit tests

---

## 4. How the Backend Works

### 4.1 Authentication & Authorization
- Endpoints under `/api/v1/auth` handle user registration (`/register`) and login (`/login`).
- Passwords are encrypted using bcrypt.
- Successful authentication returns a JWT bearer token signed with HS256.
- A FastAPI dependency (`get_current_user`) extracts and validates the bearer token from the `Authorization: Bearer <token>` header on protected routes.

### 4.2 Project & File Ingestion Workflow
1. Users create a project workspace via `POST /api/v1/projects`.
2. Users upload source datasets via `POST /api/v1/projects/{project_id}/files`.
3. Ingestion validation verifies:
   - File extension (`.csv`, `.xlsx`, `.xls`).
   - File size does not exceed `MAX_UPLOAD_BYTES` (default: 25 MB).
   - Empty files are rejected.
4. Files are stored in `storage/uploads/{project_id}/` with UUID filenames, preserving original filenames in the `source_files` database record.

### 4.3 Data Preprocessing & Profiling Pipeline
Triggered via `POST /api/v1/projects/{project_id}/files/{file_id}/preprocess`.
1. **Encoding Detection & Decoding**: Attempts `utf-8-sig` (BOM), `utf-8`, `cp1252`, and `latin-1` with automatic delimiter sniffing (`,` `\t`, `;`, `|`).
2. **Header Normalization**: Headers are trimmed, lowercased, converted to `snake_case`, and deduplicated with indexed suffixes (e.g., `id`, `id_1`).
3. **Data Type Profiling & Coercion**:
   - Leading zero strings (e.g., `"00123"`) or configured identifier columns are preserved as strings.
   - Currencies and formatted numbers (`$1,250.50`, `(50.25)`) are parsed into floats.
   - Dates are standardized to ISO-8601 (`YYYY-MM-DD`).
   - Configurable null strings (`"null"`, `"N/A"`, `"-"`, `""`, etc.) are converted to `None`.
4. **Anomaly Tracking**: Identifies empty rows and duplicate records, returning structured column profiles and preview rows.

### 4.4 Verification & Reconciliation Engine
The engine (`app/services/verification_engine.py`) performs deterministic reconciliation:
- **Key Resolution**: Supports single or composite keys (`key_columns: ["dept", "emp_id"]`) with case-insensitive column matching and optional explicit remapping (`column_mapping`).
- **Duplicate Key Guardrails**: Explicitly tags duplicate records as `DUPLICATE_KEY_SOURCE`, `DUPLICATE_KEY_TARGET`, `DUPLICATE_KEY_BOTH`, or `AMBIGUOUS_DUPLICATE`. Duplicate records are never silently dropped or arbitrarily matched.
- **Field-Level Diffing**: Evaluates matched rows across specified compare columns. Applies configurable `numeric_tolerance`, `ignore_whitespace`, and `ignore_case`.
- **Accounting Metrics**:
  - `matched_records` = `identical_matches` + `field_mismatches`
  - `unmatched_source_records` (missing in target)
  - `unmatched_target_records` (missing in source)
  - `duplicate_source_records` & `duplicate_target_records`
  - `total_discrepancies`
- **Execution Modes**:
  - *On-Demand*: `POST /api/v1/projects/{project_id}/verify` returns immediate in-memory results.
  - *Persistent Runs*: `POST /api/v1/projects/{project_id}/runs` executes the reconciliation and persists the run metrics and individual discrepancy items to PostgreSQL.

### 4.5 Export Service
Users can download reconciliation reports via `GET /api/v1/projects/{project_id}/runs/{run_id}/export`:
- `format=csv`: Exports a CSV report containing summary header metadata followed by discrepancy detail rows.
- `format=xlsx`: Generates a multi-sheet Excel workbook (`Summary` overview sheet and `Discrepancies` detail sheet).
- `format=json`: Streams full JSON containing all execution parameters, metrics, and discrepancy items.
- Supports query filtering by `discrepancy_category` and `match_status`.

---

## 5. REST API Endpoints Reference

| Method | Path | Description | Protected |
|---|---|---|---|
| `GET` | `/` | Service root and version info | No |
| `GET` | `/api/v1/health` | Service liveness health check | No |
| `GET` | `/api/v1/health/db` | PostgreSQL connectivity health check | No |
| `POST` | `/api/v1/auth/register` | Register a new user | No |
| `POST` | `/api/v1/auth/login` | Login and obtain JWT access token | No |
| `GET` | `/api/v1/auth/me` | Current authenticated user profile | Yes |
| `GET` | `/api/v1/projects` | List projects (with pagination) | Yes |
| `POST` | `/api/v1/projects` | Create a new project | Yes |
| `POST` | `/api/v1/projects/{id}/files` | Upload CSV or XLSX dataset | Yes |
| `POST` | `/api/v1/projects/{id}/files/{file_id}/preprocess` | Run preprocessing & profiling | Yes |
| `POST` | `/api/v1/projects/{id}/verify` | On-demand verification execution | Yes |
| `POST` | `/api/v1/projects/{id}/runs` | Create and execute persistent verification run | Yes |
| `GET` | `/api/v1/projects/{id}/runs` | List verification runs with status filter | Yes |
| `GET` | `/api/v1/projects/{id}/runs/{run_id}` | Get run details and status | Yes |
| `GET` | `/api/v1/projects/{id}/runs/{run_id}/summary` | Get summary metrics for a run | Yes |
| `GET` | `/api/v1/projects/{id}/runs/{run_id}/results` | Paginate and filter discrepancies for a run | Yes |
| `GET` | `/api/v1/projects/{id}/runs/{run_id}/export` | Export report (`csv`, `xlsx`, `json`) | Yes |

---

## 6. Local Setup & Execution Guide

### 6.1 Prerequisites
- Python 3.12+
- PostgreSQL (or local SQLite for unit testing)

### 6.2 Environment Setup
1. **Navigate to the backend directory**:
   ```powershell
   cd backend
   ```
2. **Activate the virtual environment**:
   - Windows:
     ```powershell
     & ".venv\Scripts\Activate.ps1"
     ```
   - Linux/macOS:
     ```bash
     source .venv/bin/activate
     ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment variables**:
   Create `.env` based on `.env.example`:
   ```ini
   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/verifygrid
   STORAGE_ROOT=storage/uploads
   MAX_UPLOAD_BYTES=26214400
   SECRET_KEY=your-secure-secret-key-for-jwt
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   ```
5. **Run Alembic database migrations**:
   ```bash
   alembic upgrade head
   ```
6. **Start the development server**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   Interactive Swagger docs are accessible at: `http://localhost:8000/docs`.

---

## 7. Running Automated Tests

Run the test suite using `pytest`:
```bash
# Run all tests
pytest tests/ -v

# Run verification engine tests specifically
pytest tests/test_verification_engine.py -v

# Run export tests
pytest tests/test_exports.py -v

# Run authentication and persistence tests
pytest tests/test_auth.py tests/test_verification_persistence.py -v
```
The test suite isolates unit tests using in-memory SQLite fixtures (`sqlite:///:memory:`) configured in `tests/conftest.py`.
