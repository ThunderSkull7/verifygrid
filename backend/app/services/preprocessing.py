"""Data preprocessing and normalization service for CSV and XLSX files."""

from __future__ import annotations

import csv
import io
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

import openpyxl
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source_file import SourceFile
from app.schemas.preprocessing import (
    ColumnMetadata,
    PreprocessingConfig,
    PreprocessingResultResponse,
    ValidationIssue,
)
from app.services.project_service import get_project_by_id
from app.utils.normalization import (
    clean_whitespace,
    deduplicate_column_names,
    is_boolean,
    is_null_value,
    parse_date,
    parse_numeric,
    LEADING_ZERO_REGEX,
)


def _safe_relative_filename(path_str: str) -> str:
    """Return only the basename of a storage path to prevent leaking directory paths."""
    return Path(path_str).name


def read_csv_rows(file_path: Path, max_rows: int) -> Tuple[List[str], List[Tuple[int, List[Any]]], List[ValidationIssue]]:
    """
    Safely parse CSV file with encoding fallback and dialect detection.
    Returns:
        - raw_headers: List of header strings from first row
        - data_rows: List of (1-based source_row_num, [cell_values])
        - issues: List of parsing warnings or errors
    """
    issues: List[ValidationIssue] = []
    
    # Check file size / empty file
    file_size = file_path.stat().st_size
    if file_size == 0:
        issues.append(
            ValidationIssue(
                level="error",
                issue_type="empty_file",
                message="Uploaded file is empty (0 bytes).",
            )
        )
        return [], [], issues

    # Read binary and try encodings
    raw_bytes = file_path.read_bytes()
    content: Optional[str] = None
    for enc in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        issues.append(
            ValidationIssue(
                level="error",
                issue_type="encoding_error",
                message="Unable to decode file. Supported encodings are UTF-8, CP1252, and Latin-1.",
            )
        )
        return [], [], issues

    if not content.strip():
        issues.append(
            ValidationIssue(
                level="error",
                issue_type="empty_file",
                message="Uploaded file contains only blank whitespace.",
            )
        )
        return [], [], issues

    # Sniff delimiter safely
    sample = content[:4096]
    delimiter = ","
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    stream = io.StringIO(content)
    reader = csv.reader(stream, delimiter=delimiter, skipinitialspace=True)

    raw_headers: List[str] = []
    data_rows: List[Tuple[int, List[Any]]] = []
    current_source_row = 0
    header_found = False

    for row in reader:
        current_source_row += 1

        if not header_found:
            # First row with content is treated as the header
            if any(cell.strip() for cell in row):
                raw_headers = row
                header_found = True
            continue

        data_rows.append((current_source_row, row))
        if len(data_rows) >= max_rows:
            issues.append(
                ValidationIssue(
                    level="warning",
                    issue_type="row_limit_reached",
                    message=f"File exceeds maximum row limit of {max_rows}. Processing truncated.",
                    row_number=current_source_row,
                )
            )
            break

    if not header_found or not raw_headers:
        issues.append(
            ValidationIssue(
                level="error",
                issue_type="missing_headers",
                message="File does not contain any header row.",
            )
        )

    return raw_headers, data_rows, issues


def read_xlsx_rows(file_path: Path, max_rows: int) -> Tuple[List[str], List[Tuple[int, List[Any]]], List[ValidationIssue]]:
    """
    Safely parse first sheet of XLSX file using openpyxl in read_only mode.
    Returns:
        - raw_headers: List of header strings from first row
        - data_rows: List of (1-based source_row_num, [cell_values])
        - issues: List of parsing warnings or errors
    """
    issues: List[ValidationIssue] = []

    try:
        workbook = openpyxl.load_workbook(filename=str(file_path), read_only=True, data_only=True)
    except Exception:
        issues.append(
            ValidationIssue(
                level="error",
                issue_type="corrupted_file",
                message="Unable to read XLSX spreadsheet. The file may be corrupt or encrypted.",
            )
        )
        return [], [], issues

    try:
        sheet = workbook.active
        if sheet is None:
            issues.append(
                ValidationIssue(
                    level="error",
                    issue_type="empty_file",
                    message="Spreadsheet contains no active worksheet.",
                )
            )
            return [], [], issues

        raw_headers: List[str] = []
        data_rows: List[Tuple[int, List[Any]]] = []
        header_found = False
        current_source_row = 0

        for row in sheet.iter_rows(values_only=True):
            current_source_row += 1
            row_list = list(row)

            # Skip trailing empty cells
            if not header_found:
                if any(c is not None and str(c).strip() for c in row_list):
                    # Trim right-side empty header cells
                    while row_list and (row_list[-1] is None or not str(row_list[-1]).strip()):
                        row_list.pop()
                    raw_headers = ["" if c is None else str(c) for c in row_list]
                    header_found = True
                continue

            data_rows.append((current_source_row, row_list))
            if len(data_rows) >= max_rows:
                issues.append(
                    ValidationIssue(
                        level="warning",
                        issue_type="row_limit_reached",
                        message=f"Spreadsheet exceeds maximum row limit of {max_rows}. Processing truncated.",
                        row_number=current_source_row,
                    )
                )
                break

        if not header_found or not raw_headers:
            issues.append(
                ValidationIssue(
                    level="error",
                    issue_type="missing_headers",
                    message="Spreadsheet does not contain a header row.",
                )
            )

        return raw_headers, data_rows, issues

    finally:
        workbook.close()


def preprocess_file_data(
    file_path: Path,
    file_type: str,
    config: Optional[PreprocessingConfig] = None,
) -> Tuple[List[ColumnMetadata], Dict[str, str], List[Dict[str, Any]], List[List[int]], List[int], List[ValidationIssue], int, int]:
    """
    Core parsing, cleaning, and normalization logic.
    Returns:
        - columns_metadata: List[ColumnMetadata]
        - column_mapping: Dict[orig_name, normalized_name]
        - normalized_preview: List[dict] (first 10 normalized rows with source_row_number)
        - duplicate_record_row_numbers: List[List[int]] (groups of row numbers with identical records)
        - empty_row_numbers: List[int]
        - issues: List[ValidationIssue]
        - total_source_rows: int
        - data_rows_count: int
    """
    if config is None:
        config = PreprocessingConfig()

    null_set = {v.strip().lower() for v in config.null_values if v is not None}
    identifier_names = {name.strip().lower() for name in config.identifier_columns}

    # 1. Read rows according to file type
    if file_type == "csv":
        raw_headers, data_rows, issues = read_csv_rows(file_path, config.max_rows)
    elif file_type == "xlsx":
        raw_headers, data_rows, issues = read_xlsx_rows(file_path, config.max_rows)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported file type '{file_type}'. Supported types are csv and xlsx.",
        )

    # If fatal error reading headers or file
    has_fatal_error = any(issue.level == "error" for issue in issues)
    if has_fatal_error or not raw_headers:
        return [], {}, [], [], [], issues, 0, 0

    if config.strip_whitespace:
        raw_headers = [str(clean_whitespace(h)) for h in raw_headers]

    # 2. Normalize and deduplicate column names
    normalized_cols, col_pairs, dup_warnings = deduplicate_column_names(
        raw_headers, normalize=config.normalize_column_names
    )
    for warn_msg in dup_warnings:
        issues.append(
            ValidationIssue(
                level="warning",
                issue_type="duplicate_header",
                message=warn_msg,
            )
        )

    column_mapping = {orig: norm for orig, norm in col_pairs}
    total_cols = len(normalized_cols)

    # 3. Process data rows: whitespace, nulls, empty rows detection
    processed_records: List[Tuple[int, Dict[str, Any]]] = []
    empty_row_numbers: List[int] = []
    seen_row_hashes: Dict[str, List[int]] = defaultdict(list)

    # Collect per-column value information for type inference & inconsistency detection
    # col_idx -> list of (row_num, val, detected_type)
    col_type_observations: Dict[int, List[Tuple[int, Any, str]]] = defaultdict(list)

    for src_row_num, row_cells in data_rows:
        original_cell_count = len(row_cells)
        if original_cell_count != total_cols:
            issues.append(
                ValidationIssue(
                    level="warning",
                    issue_type="malformed_row",
                    row_number=src_row_num,
                    message=f"Row {src_row_num} has {original_cell_count} field(s); expected {total_cols} columns.",
                )
            )

        # Pad or trim cells to match column count
        cells = list(row_cells)
        if len(cells) < total_cols:
            cells.extend([None] * (total_cols - len(cells)))
        elif len(cells) > total_cols:
            cells = cells[:total_cols]

        record: Dict[str, Any] = {}
        all_null = True

        for c_idx, cell_value in enumerate(cells):
            norm_col_name = normalized_cols[c_idx]
            orig_col_name = col_pairs[c_idx][0]

            # Whitespace handling
            val = clean_whitespace(cell_value) if config.strip_whitespace else cell_value

            # Null check
            if is_null_value(val, null_set):
                record[norm_col_name] = None
                continue

            all_null = False

            # Check if this column is explicitly declared as an identifier
            is_identifier_col = (
                norm_col_name.lower() in identifier_names
                or orig_col_name.lower() in identifier_names
            )

            # Preserve leading zeros as identifiers
            val_str = str(val)
            if is_identifier_col or LEADING_ZERO_REGEX.match(val_str):
                record[norm_col_name] = val_str
                col_type_observations[c_idx].append((src_row_num, val_str, "identifier"))
                continue

            # Check boolean
            bool_val, is_bool = is_boolean(val)
            if is_bool:
                record[norm_col_name] = bool_val
                col_type_observations[c_idx].append((src_row_num, bool_val, "boolean"))
                continue

            # Number normalization
            if config.normalize_numbers:
                num_val, num_type = parse_numeric(val)
                if num_val is not None:
                    record[norm_col_name] = num_val
                    col_type_observations[c_idx].append((src_row_num, num_val, num_type))
                    continue

            # Date normalization
            if config.normalize_dates:
                date_val, date_type = parse_date(val)
                if date_val is not None:
                    record[norm_col_name] = date_val
                    col_type_observations[c_idx].append((src_row_num, date_val, "date"))
                    continue

            # Default to string/raw
            record[norm_col_name] = val
            col_type_observations[c_idx].append((src_row_num, val, "string"))

        if all_null:
            empty_row_numbers.append(src_row_num)
        else:
            processed_records.append((src_row_num, record))
            # Track duplicates using record serialization key
            row_key = "|".join(f"{k}:{v}" for k, v in sorted(record.items()))
            seen_row_hashes[row_key].append(src_row_num)

    if empty_row_numbers:
        issues.append(
            ValidationIssue(
                level="warning",
                issue_type="empty_rows",
                message=f"Detected {len(empty_row_numbers)} completely empty row(s) in source file.",
            )
        )

    # 4. Check for duplicate records without deleting them
    duplicate_record_row_numbers: List[List[int]] = [
        rows for rows in seen_row_hashes.values() if len(rows) > 1
    ]
    duplicate_rows_count = sum(len(group) for group in duplicate_record_row_numbers)
    if duplicate_record_row_numbers:
        issues.append(
            ValidationIssue(
                level="warning",
                issue_type="duplicate_records",
                message=(
                    f"Found {duplicate_rows_count} duplicate row(s) grouped across "
                    f"{len(duplicate_record_row_numbers)} unique record(s)."
                ),
            )
        )

    # 5. Column metadata and type inference + inconsistency checking
    columns_metadata: List[ColumnMetadata] = []
    total_data_records = len(processed_records)

    for c_idx, norm_col in enumerate(normalized_cols):
        orig_col = col_pairs[c_idx][0]
        obs = col_type_observations.get(c_idx, [])
        non_null_count = len(obs)
        null_count = total_data_records - non_null_count

        sample_vals = [item[1] for item in obs[:5]]

        if not obs:
            detected_type = "empty"
        else:
            # Count type frequencies
            type_counts: Dict[str, int] = defaultdict(int)
            for _, _, t in obs:
                type_counts[t] += 1

            types_set = set(type_counts.keys())
            # If column consists solely of numeric values (integers and/or floats), treat as numeric
            if types_set.issubset({"integer", "float"}):
                detected_type = "float" if "float" in types_set else "integer"
            else:
                # Identify dominant type
                dominant_type, dominant_count = max(type_counts.items(), key=lambda x: x[1])
                dominance_ratio = dominant_count / non_null_count

                # If dominant type is >= 80% but there are minority types, flag inconsistent values
                if dominance_ratio >= 0.8 and len(type_counts) > 1:
                    detected_type = dominant_type
                    # Report specific rows with mismatching types
                    for src_row, val, val_type in obs:
                        if val_type != dominant_type:
                            # Allow integer inside float column without warning
                            if dominant_type == "float" and val_type == "integer":
                                continue
                            issues.append(
                                ValidationIssue(
                                    level="warning",
                                    issue_type="type_mismatch",
                                    row_number=src_row,
                                    column_name=norm_col,
                                    message=(
                                        f"Value '{val}' in column '{orig_col}' has detected type '{val_type}', "
                                        f"which is inconsistent with column type '{dominant_type}'."
                                    ),
                                )
                            )
                elif dominance_ratio < 0.8 and len(type_counts) > 1:
                    detected_type = "mixed"
                    issues.append(
                        ValidationIssue(
                            level="warning",
                            issue_type="mixed_column_types",
                            column_name=norm_col,
                            message=f"Column '{orig_col}' has inconsistent/mixed data types: {dict(type_counts)}.",
                        )
                    )
                else:
                    detected_type = dominant_type

        columns_metadata.append(
            ColumnMetadata(
                original_name=orig_col,
                normalized_name=norm_col,
                detected_type=detected_type,
                null_count=null_count,
                non_null_count=non_null_count,
                sample_values=sample_vals,
            )
        )

    # 6. Preview rows (first 10 records with source_row_number)
    normalized_preview = [
        {"source_row_number": row_num, **rec} for row_num, rec in processed_records[:10]
    ]

    total_source_rows = len(data_rows) + 1  # data rows + header
    return (
        columns_metadata,
        column_mapping,
        normalized_preview,
        duplicate_record_row_numbers,
        empty_row_numbers,
        issues,
        total_source_rows,
        len(processed_records),
    )


def preprocess_source_file(
    db: Session,
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    config: Optional[PreprocessingConfig] = None,
) -> PreprocessingResultResponse:
    """
    Execute preprocessing for an uploaded file belonging to a project.
    Validates project and file existence, runs preprocessing pipeline,
    and updates SourceFile record status.
    """
    # 1. Project verification
    project = get_project_by_id(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    # 2. File verification and project-scoped isolation check
    source_file = db.query(SourceFile).filter(
        SourceFile.id == file_id,
        SourceFile.project_id == project_id,
    ).first()

    if source_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found for this project.",
        )

    storage_path = Path(source_file.storage_path)

    # Path traversal and existence check
    try:
        resolved_path = storage_path.resolve()
        storage_root_resolved = settings.storage_root.resolve()
        if not str(resolved_path).startswith(str(storage_root_resolved)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to the specified file path is restricted.",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file storage path could not be resolved.",
        )

    if not resolved_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file content not found on disk.",
        )

    # 3. Run preprocessing
    (
        columns_metadata,
        column_mapping,
        preview_rows,
        duplicate_record_row_numbers,
        empty_row_numbers,
        issues,
        total_source_rows,
        data_rows_count,
    ) = preprocess_file_data(
        file_path=resolved_path,
        file_type=source_file.file_type,
        config=config,
    )

    has_error = any(issue.level == "error" for issue in issues)
    new_status = "preprocessing_failed" if has_error else "preprocessed"

    try:
        source_file.status = new_status
        db.commit()
        db.refresh(source_file)
    except Exception:
        db.rollback()
        raise

    return PreprocessingResultResponse(
        source_file_id=source_file.id,
        project_id=project.id,
        original_filename=source_file.original_filename,
        file_type=source_file.file_type,
        total_source_rows=total_source_rows,
        data_rows_count=data_rows_count,
        empty_rows_count=len(empty_row_numbers),
        duplicate_rows_count=sum(len(group) for group in duplicate_record_row_numbers),
        columns=columns_metadata,
        column_mapping=column_mapping,
        duplicate_record_row_numbers=duplicate_record_row_numbers,
        issues=issues,
        preview_rows=preview_rows,
    )
