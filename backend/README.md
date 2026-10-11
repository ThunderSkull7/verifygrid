# VerifyGrid Backend

VerifyGrid is an intelligent data verification and reconciliation platform designed to ingest, normalize, and reconcile structured datasets (CSV and XLSX).

---

## 1. Tech Stack & Architecture

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **Database & ORM**: PostgreSQL via [SQLAlchemy 2.0](https://www.sqlalchemy.org/) and [psycopg 3](https://www.psycopg.org/)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Validation & Schemas**: [Pydantic v2](https://docs.pydantic.dev/)
- **File Parsing & Processing**: Standard `csv`, `openpyxl`, `python-dateutil`
- **Testing**: [pytest](https://docs.pytest.org/), `TestClient` (FastAPI / Starlette) with SQLite in-memory isolation for unit tests and live PostgreSQL integration tests

---

## 2. Directory Structure

```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── projects.py         # Project management endpoints
│   │       │   ├── uploads.py          # CSV/XLSX file upload endpoints
│   │       │   ├── preprocessing.py    # Preprocessing & normalization endpoints
│   │       │   └── verification.py     # Verification & reconciliation endpoints
│   │       └── router.py               # API v1 router registration & health checks
│   ├── core/
│   │   └── config.py                   # Application settings & environment config
│   ├── db/
│   │   ├── base.py                     # SQLAlchemy DeclarativeBase
│   │   └── session.py                  # Database engine & sessionmaker
│   ├── models/                         # SQLAlchemy models (User, Project, SourceFile)
│   ├── schemas/                        # Pydantic schemas (Project, Upload, Preprocessing, Result)
│   ├── services/
│   │   ├── ingestion.py                # File upload storage & validation
│   │   ├── preprocessing.py            # Preprocessing & normalization pipeline
│   │   ├── project_service.py          # Project business logic
│   │   └── verification_engine.py      # Core verification & reconciliation engine
│   └── utils/
│       └── normalization.py            # Column, number, date, and string cleaners
├── migrations/                         # Alembic database migrations
├── storage/uploads/                    # Local storage root for uploaded files
├── tests/                              # Automated test suite
├── .env.example                        # Example environment variables
├── alembic.ini                         # Alembic configuration
└── requirements.txt                    # Python dependencies
```

---

## 3. Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL (optional for local SQLite unit tests, required for live DB development)

### Setup & Installation

1. **Activate virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     & ".venv\Scripts\Activate.ps1"
     ```
   - **Linux / macOS:**
     ```bash
     source .venv/bin/activate
     ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   Copy `.env.example` to `.env` and set your database connection string:
   ```ini
   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/verifygrid
   STORAGE_ROOT=storage/uploads
   MAX_UPLOAD_BYTES=26214400
   ```

4. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Start the development server:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   Interactive Swagger documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 4. API Endpoints

### System & Health
- `GET /` — API welcome message and version.
- `GET /api/v1/health` — Application liveness probe.
- `GET /api/v1/health/db` — PostgreSQL database connectivity check.

### Projects
- `POST /api/v1/projects` — Create a new reconciliation project.
- `GET /api/v1/projects?skip=0&limit=100` — List projects with pagination.

### File Uploads
- `POST /api/v1/projects/{project_id}/files` — Upload a CSV or XLSX source file (scoped to project, max 25MB).

### Preprocessing & Normalization
- `POST /api/v1/projects/{project_id}/files/{file_id}/preprocess` — Trigger preprocessing and normalization on an uploaded file with optional configuration rules.

### Verification & Reconciliation
- `POST /api/v1/projects/{project_id}/verify` — Execute the in-memory core verification engine comparing two project source files across single or composite keys, detecting matches, missing records, duplicate keys, and field-level discrepancies.
- `POST /api/v1/projects/{project_id}/runs` — Create and execute a persistent verification run, storing run status, summary metrics, and discrepancies.
- `GET /api/v1/projects/{project_id}/runs` — List verification runs for a project with pagination and status filtering.
- `GET /api/v1/projects/{project_id}/runs/{run_id}` — Retrieve details and summary metrics for a specific verification run.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/results` — Paginate and filter discrepancy results for a verification run.

---

## 5. Data Preprocessing & Normalization Pipeline

The preprocessing layer standardizes raw datasets before ingestion into the verification engine:

```
[Uploaded File (CSV / XLSX)]
             │
             ▼
[1. Safe Ingestion & Decoding]
   - File size & empty-file validation
   - Multi-encoding fallback (UTF-8-SIG, UTF-8, CP1252, Latin-1)
   - Delimiter sniffing (comma, tab, semicolon, pipe)
   - Memory-safe streaming for XLSX via openpyxl
             │
             ▼
[2. Header Extraction & Normalization]
   - Missing header detection
   - Column name standardization (lower_snake_case)
   - Duplicate column deduplication with indexed suffixes (_1, _2)
   - Original header mappings preserved
             │
             ▼
[3. Row Cleaning & Type Detection]
   - Whitespace trimming
   - Configurable null value canonicalization
   - Leading zero / identifier preservation (e.g., "00123")
   - Numeric normalization (currency symbols, grouping commas, accounting parentheses)
   - Date parsing to ISO-8601 (YYYY-MM-DD)
   - Boolean normalization ("true"/"false", "yes"/"no")
   - Source row number preservation (1-based index)
             │
             ▼
[4. Validation & Anomaly Reporting]
   - Empty row detection and indexing
   - Duplicate record identification without deletion
   - Column type inconsistency / mismatch detection
   - Maximum row safety limits
             │
             ▼
[Structured Response & Status Update]
   - Updates SourceFile record status to "preprocessed" or "preprocessing_failed"
   - Returns structured metadata, warnings/errors, and normalized preview rows
```

### Supported Formats

| Format | Extension | Library | Parser Behavior |
|---|---|---|---|
| **CSV** | `.csv` | Standard `csv.reader` | Delimiter sniffing (`,`, `\t`, `;`, pipe). Supports `UTF-8`, `UTF-8-SIG` (BOM), `CP1252`, and `Latin-1`. `skipinitialspace=True` for robust quote parsing. |
| **Excel** | `.xlsx` | `openpyxl` | Parsed with `read_only=True` and `data_only=True` for memory efficiency. |

### Normalization Rules

1. **Column Normalization**:
   - Headers converted to clean `snake_case` (e.g., `"Employee ID"` → `"employee_id"`).
   - Duplicate headers renamed with suffix (`"id"`, `"id_1"`).
   - Mapping preserved in `column_mapping`.
2. **Identifiers & Leading Zeros**:
   - Digit sequences with leading zeros (e.g., `"00123"`, `"09876"`) are preserved as strings and tagged with detected type `identifier`.
   - Columns specified in `config.identifier_columns` are always kept as strings.
3. **Numeric & Currency**:
   - Strips currency signs (`$`, `€`, `£`, `₹`) and thousand separators (`1,250.50` → `1250.5`).
   - Parses accounting negatives (`(50.25)` → `-50.25`).
   - Mixed integer/float columns are unified to `float`.
4. **Dates**:
   - Standardizes calendar formats into ISO-8601 (`YYYY-MM-DD`).
5. **Null Values**:
   - Treats configurable tokens as `None` (case-insensitive): `""`, `"null"`, `"none"`, `"nil"`, `"n/a"`, `"na"`, `"nan"`, `"-"`, `"--"`, `"undefined"`, `"#n/a"`.
6. **Duplicate Records**:
   - Detects identical rows across all columns.
   - Preserves all rows and returns groups of 1-based source row numbers for auditability.
7. **Validation Issues**:
   - Returns structured issues with `level` (`error` or `warning`), `issue_type`, `message`, and optional `row_number` and `column_name`.

### Configurable Options (`PreprocessingConfig`)

```json
{
  "strip_whitespace": true,
  "normalize_column_names": true,
  "null_values": ["", "null", "none", "n/a", "na", "nan", "-", "--", "undefined", "#n/a"],
  "normalize_dates": true,
  "normalize_numbers": true,
  "identifier_columns": ["account_number", "roll_no"],
  "max_rows": 100000
}
```

### Preprocessing Response Example

```json
{
  "source_file_id": "8c37d0da-514e-4f76-9057-a5ec0902f232",
  "project_id": "b96874eb-3146-4c28-98e3-bbef08542c3d",
  "original_filename": "employees.csv",
  "file_type": "csv",
  "total_source_rows": 3,
  "data_rows_count": 2,
  "empty_rows_count": 0,
  "duplicate_rows_count": 0,
  "columns": [
    {
      "original_name": "Employee ID",
      "normalized_name": "employee_id",
      "detected_type": "identifier",
      "null_count": 0,
      "non_null_count": 2,
      "sample_values": ["00101", "00102"]
    },
    {
      "original_name": "Salary",
      "normalized_name": "salary",
      "detected_type": "float",
      "null_count": 0,
      "non_null_count": 2,
      "sample_values": [85000.5, 62000]
    }
  ],
  "column_mapping": {
    "Employee ID": "employee_id",
    "Salary": "salary"
  },
  "duplicate_record_row_numbers": [],
  "issues": [],
  "preview_rows": [
    {
      "source_row_number": 2,
      "employee_id": "00101",
      "salary": 85000.5
    }
  ]
}
```

---

## 6. Core Verification Engine

The verification engine performs reconciliation between two preprocessed datasets (e.g. source/baseline vs. target/comparison).

### Key Features

1. **Deterministic Record Matching**:
   - Matches records using single keys or composite multi-column keys (`key_columns: ["dept", "emp_id"]`).
   - Resolves columns case-insensitively and through snake_case normalization.
   - Supports explicit column name remapping (`column_mapping: {"src_col": "tgt_col"}`).

2. **Strict Duplicate Key Detection**:
   - Detects duplicate keys on either or both sides (`DUPLICATE_KEY_SOURCE`, `DUPLICATE_KEY_TARGET`, `DUPLICATE_KEY_BOTH`, `AMBIGUOUS_DUPLICATE`).
   - **Never silently discards duplicate records** or assumes the first match is correct.
   - Preserves and reports all source and target row numbers (`source_row_numbers: [2, 5]`).

3. **Field-Level Comparison**:
   - Compares corresponding fields across matched records.
   - Evaluates null equivalence consistently (e.g., `None` and `""` or `"N/A"` are equal nulls).
   - Preserves identifiers with leading zeros (e.g., `"00123"` is not coerced to `123`).
   - Normalizes numbers, currency symbols, and accounting formats.
   - Supports configurable `numeric_tolerance` for floating-point values.
   - Supports whitespace stripping and case-insensitive comparison (`ignore_whitespace`, `ignore_case`).

4. **Summary Metrics & Discrepancy Accounting**:
   - Calculates mutually exclusive and internally consistent counts across all records on both sides:
     - `matched_records` (`identical_matches` + `field_mismatches`)
     - `unmatched_source_records` (present only in source)
     - `unmatched_target_records` (present only in target)
     - `duplicate_source_records` & `duplicate_target_records`
     - `duplicate_source_keys_count` & `duplicate_target_keys_count`
     - `total_discrepancies`

### Request Example (`POST /api/v1/projects/{project_id}/verify`)

```json
{
  "source_file_id": "8c37d0da-514e-4f76-9057-a5ec0902f232",
  "target_file_id": "e21b7e61-9c17-48f1-8cb5-e51c8a4eb482",
  "key_columns": ["employee_id"],
  "column_mapping": {
    "employee_id": "emp_no",
    "salary": "base_pay"
  },
  "compare_columns": ["salary", "department"],
  "ignore_columns": ["internal_notes"],
  "numeric_tolerance": 0.01,
  "ignore_whitespace": true,
  "ignore_case": false,
  "include_identical": true
}
```

### Response Example

```json
{
  "project_id": "b96874eb-3146-4c28-98e3-bbef08542c3d",
  "source_file_id": "8c37d0da-514e-4f76-9057-a5ec0902f232",
  "target_file_id": "e21b7e61-9c17-48f1-8cb5-e51c8a4eb482",
  "key_columns": ["employee_id"],
  "column_mapping": {
    "employee_id": "emp_no",
    "salary": "base_pay"
  },
  "summary": {
    "total_source_records": 100,
    "total_target_records": 102,
    "matched_records": 95,
    "identical_matches": 90,
    "field_mismatches": 5,
    "records_with_differences": 5,
    "unmatched_source_records": 3,
    "unmatched_target_records": 4,
    "duplicate_source_records": 2,
    "duplicate_target_records": 3,
    "duplicate_source_keys_count": 1,
    "duplicate_target_keys_count": 1,
    "conflicting_duplicate_records": 0,
    "total_discrepancies": 14,
    "status": "completed"
  },
  "results": [],
  "discrepancies": [
    {
      "key_values": {"employee_id": "00102"},
      "match_status": "field_mismatch",
      "discrepancy_category": "field_mismatch",
      "source_row_number": 3,
      "target_row_number": 4,
      "field_differences": [
        {
          "field_name": "salary",
          "source_field": "salary",
          "target_field": "base_pay",
          "source_value": 60000,
          "target_value": 65000,
          "difference_type": "value_mismatch",
          "message": "Difference in 'salary': '60000' vs '65000'"
        }
      ]
    }
  ],
  "warnings": [],
  "errors": []
}
```

### Limitations

- **Fuzzy Matching**: Key matching is exact (with whitespace/case normalization). Approximate/fuzzy string matching is deferred to a future milestone.
- **AI-Based Reconciliation**: Automatic semantic column inference and AI-assisted match resolution are intentionally out of scope for this milestone.
- **Persistent Verification Runs**: Verification is executed on-demand in-memory. Persistent storage of verification runs and historical reconciliation audits will be implemented in the next milestone.

---

## 7. Running Tests

Execute the automated test suite with `pytest`:

```bash
# Run all tests
pytest tests/ -v

# Run verification engine tests
pytest tests/test_verification_engine.py -v

# Run with python module syntax
python -m pytest tests/ -v
```

