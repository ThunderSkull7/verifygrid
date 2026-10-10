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

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── projects.py         # Project management endpoints
│   │       │   ├── uploads.py          # CSV/XLSX file upload endpoints
│   │       │   └── preprocessing.py    # Preprocessing & normalization endpoints
│   │       └── router.py               # API v1 router registration & health checks
│   ├── core/
│   │   └── config.py                   # Application settings & environment config
│   ├── db/
│   │   ├── base.py                     # SQLAlchemy DeclarativeBase
│   │   └── session.py                  # Database engine & sessionmaker
│   ├── models/                         # SQLAlchemy models (User, Project, SourceFile)
│   ├── schemas/                        # Pydantic schemas (Project, Upload, Preprocessing)
│   ├── services/
│   │   ├── ingestion.py                # File upload storage & validation
│   │   ├── preprocessing.py            # Preprocessing & normalization pipeline
│   │   └── project_service.py          # Project business logic
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

## 6. Running Tests

Execute the automated test suite with `pytest`:

```bash
# Run all tests
pytest tests/ -v

# Run only preprocessing tests
pytest tests/test_preprocessing.py -v

# Run with python module syntax
python -m pytest tests/ -v
```
