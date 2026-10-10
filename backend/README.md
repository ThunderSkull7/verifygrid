# VerifyGrid Backend — Data Preprocessing & Normalization

VerifyGrid is an intelligent data verification and reconciliation platform. This document covers the **Data Preprocessing & Normalization Layer**, which ingests raw CSV and XLSX files and transforms them into clean, standardized datasets ready for verification.

---

## 1. Preprocessing Pipeline Overview

The preprocessing pipeline executes in a modular, memory-conscious sequence:

```
[Uploaded File (CSV / XLSX)]
             │
             ▼
[1. Safe Ingestion & Decoding]
   - File size & empty-file checks
   - Encoding fallback (UTF-8-SIG, UTF-8, CP1252, Latin-1)
   - Delimiter sniffing (comma, tab, semicolon, pipe)
   - Read-only streaming for XLSX
             │
             ▼
[2. Header Extraction & Normalization]
   - Missing header detection
   - Column name standardization (lower_snake_case)
   - Duplicate column deduplication with indexed suffixes
   - Original header mapping preserved
             │
             ▼
[3. Row-by-Row Cleaning & Type Detection]
   - Whitespace stripping
   - Null representation canonicalization
   - Leading zero / identifier preservation (e.g., "00123", "02138")
   - Number normalization (thousands separators, currency, accounting brackets)
   - Date parsing to ISO-8601 (YYYY-MM-DD / YYYY-MM-DDTHH:MM:SS)
   - Boolean normalization ("true"/"false", "yes"/"no")
   - Source row number preservation (1-based index)
             │
             ▼
[4. Validation & Anomaly Reporting]
   - Empty row detection and indexing
   - Duplicate record identification (grouped by 1-based source row numbers)
   - Column type inconsistency / mismatch detection
   - Safety row count limit enforcement
             │
             ▼
[Structured Response & Status Update]
   - Updates SourceFile database status to "preprocessed" or "preprocessing_failed"
   - Returns structured metadata, warnings/errors, and normalized preview rows
```

---

## 2. Supported Formats & Parsing Behavior

| Format | Library | Details |
|---|---|---|
| **CSV** (`.csv`) | Standard `csv.reader` | Uses safe dialect sniffing for `,`, `\t`, `;`, `\|`. Supports `UTF-8`, `UTF-8-SIG` (BOM), `CP1252`, and `Latin-1`. Skips initial space for resilient quote parsing. |
| **XLSX** (`.xlsx`) | `openpyxl` | Parsed with `read_only=True` and `data_only=True` to stream worksheet cell values efficiently without loading rich formatting into memory. |

---

## 3. Normalization Rules & Capabilities

### Column Normalization
- Converts headers into clean `snake_case` (e.g., `"Employee ID"` → `"employee_id"`, `"First Name"` → `"first_name"`).
- Original column headers are preserved in `column_mapping` (`{ "Original Header": "normalized_name" }`).
- Duplicate headers are deduplicated by appending an incremental index (`"id"`, `"id_1"`, `"id_2"`) with a warning logged in `issues`.

### Leading Zero & Identifier Preservation
- Values with leading zeros (e.g., `"00123"`, `"0987654321"`) are **never silently converted to numbers**. They are typed as `identifier` and preserved as strings.
- Columns declared in `config.identifier_columns` are strictly preserved as string identifiers regardless of content.

### Numeric & Currency Normalization
- Standardizes integer and floating-point values.
- Removes currency symbols (`$`, `€`, `£`, `₹`) and thousand grouping commas (`"1,250.50"` → `1250.5`).
- Parses accounting-style negative parentheses (`"(50.25)"` → `-50.25`).
- Mixed integer and float values within a column are unified to `float`.

### Date Normalization
- Parses standard calendar formats into ISO-8601 dates (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`).
- Avoids misinterpreting short integers as dates.

### Null Value Normalization
- Standardizes empty cells and string null representations into `None`.
- Default null tokens (case-insensitive): `""`, `"null"`, `"none"`, `"nil"`, `"n/a"`, `"na"`, `"nan"`, `"-"`, `"--"`, `"undefined"`, `"#n/a"`.

### Duplicate Record Detection
- Duplicate records across all columns are detected and grouped by 1-based source row numbers.
- Records are **not deleted** automatically; their presence and source row numbers are returned for review.

### Validation Warnings & Errors
Issues are categorized with severity levels (`error`, `warning`):
- `empty_file`: 0-byte or blank file.
- `missing_headers`: Header row not found.
- `duplicate_header`: Duplicate column header found in file.
- `empty_rows`: Rows where every cell is null or blank.
- `duplicate_records`: Duplicate records identified.
- `type_mismatch`: Value type diverges from dominant column data type.
- `mixed_column_types`: Column contains inconsistent data types without clear dominant type.
- `malformed_row`: Row has unexpected field count relative to the header.
- `row_limit_reached`: Source row count exceeded `max_rows` threshold.
- `corrupted_file`: File could not be parsed as valid spreadsheet or CSV.

---

## 4. Configurable Options (`PreprocessingConfig`)

Callers can pass a custom JSON payload to `POST /api/v1/projects/{project_id}/files/{file_id}/preprocess`:

```json
{
  "strip_whitespace": true,
  "normalize_column_names": true,
  "null_values": ["", "null", "none", "n/a", "na", "nan", "-", "--", "undefined", "#n/a", "UNKNOWN"],
  "normalize_dates": true,
  "normalize_numbers": true,
  "identifier_columns": ["account_number", "customer_code"],
  "max_rows": 100000
}
```

---

## 5. API Endpoint

### `POST /api/v1/projects/{project_id}/files/{file_id}/preprocess`

**Request:** Optional JSON body matching `PreprocessingConfig`.

**Response (`PreprocessingResultResponse`):**
```json
{
  "source_file_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
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
    }
  ],
  "column_mapping": {
    "Employee ID": "employee_id"
  },
  "duplicate_record_row_numbers": [],
  "issues": [],
  "preview_rows": [
    {
      "source_row_number": 2,
      "employee_id": "00101"
    }
  ]
}
```

---

## 6. Running Tests

Run the full automated test suite using `pytest`:

```powershell
# From the backend directory
& ".venv\Scripts\python.exe" -m pytest tests/ -v
```

Run only the preprocessing test suite:

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_preprocessing.py -v
```
