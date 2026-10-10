"""Utility functions for string, column, date, and numeric normalization."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, List, Optional, Set, Tuple
from dateutil import parser as date_parser

# Regex pattern for non-alphanumeric characters used in slugifying / snake_casing
NON_ALPHANUM_REGEX = re.compile(r"[^a-zA-Z0-9]+")
# Matches purely digit strings with a leading zero and length > 1 (e.g., "00123", "04")
LEADING_ZERO_REGEX = re.compile(r"^0\d+$")
# Matches standard integer strings (e.g., "-123", "456")
INTEGER_REGEX = re.compile(r"^-?\d+$")
# Matches float strings (e.g., "-123.45", "0.99")
FLOAT_REGEX = re.compile(r"^-?\d+\.\d+$")
# Clean currency symbols and commas: "$1,234.50", "€100", "(50.00)"
CURRENCY_REGEX = re.compile(r"^[\$€£₹]?\s*-?\d{1,3}(,\d{3})*(\.\d+)?\s*[\$€£₹]?$")
PAREN_NEGATIVE_REGEX = re.compile(r"^\((.+)\)$")


def normalize_column_name(header: Any, index: int = 0) -> str:
    """
    Normalize a column header string into a consistent lower_snake_case name.
    If the header is empty or None, generates an 'unnamed_column_{index+1}' name.
    """
    if header is None:
        return f"unnamed_column_{index + 1}"

    text = str(header).strip()
    if not text:
        return f"unnamed_column_{index + 1}"

    # Replace CamelCase / PascalCase transitions with underscore
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)

    # Replace non-alphanumeric with underscore and convert to lower
    slug = NON_ALPHANUM_REGEX.sub("_", s2).strip("_").lower()
    if not slug:
        return f"unnamed_column_{index + 1}"
    return slug


def deduplicate_column_names(
    raw_headers: List[Any],
    normalize: bool = True,
) -> Tuple[List[str], List[Tuple[str, str]], List[str]]:
    """
    Produce unique column names while preserving original headers.

    Returns:
        - normalized_names: List of normalized, unique column names
        - column_pairs: List of (original_name, normalized_name)
        - duplicate_warnings: List of messages for any duplicate column names found
    """
    seen_normalized: Set[str] = set()
    normalized_names: List[str] = []
    column_pairs: List[Tuple[str, str]] = []
    duplicate_warnings: List[str] = []

    for idx, header in enumerate(raw_headers):
        orig_name = str(header) if header is not None else f"Column_{idx + 1}"
        base_name = normalize_column_name(header, idx) if normalize else orig_name.strip()
        if not base_name:
            base_name = f"column_{idx + 1}"

        norm_name = base_name
        counter = 1
        if norm_name in seen_normalized:
            duplicate_warnings.append(
                f"Duplicate column header '{orig_name}' detected. Renamed to '{norm_name}_{counter}'."
            )
            while f"{base_name}_{counter}" in seen_normalized:
                counter += 1
            norm_name = f"{base_name}_{counter}"

        seen_normalized.add(norm_name)
        normalized_names.append(norm_name)
        column_pairs.append((orig_name, norm_name))

    return normalized_names, column_pairs, duplicate_warnings


def is_null_value(value: Any, null_values: Set[str]) -> bool:
    """Check if a value represents null/empty according to configured null representations."""
    if value is None:
        return True
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return True
    val_str = str(value).strip().lower()
    return val_str in null_values


def clean_whitespace(val: Any) -> Any:
    """Strip leading and trailing whitespace from strings."""
    if isinstance(val, str):
        return val.strip()
    return val


def parse_numeric(val: Any) -> Tuple[Optional[Any], Optional[str]]:
    """
    Attempt to parse a string/value as int or float.
    Returns (parsed_value, type_name) where type_name is 'integer' or 'float',
    or (None, None) if not numeric.
    """
    if isinstance(val, (int, float)):
        if isinstance(val, bool):
            return None, None
        if isinstance(val, int):
            return val, "integer"
        if isinstance(val, float):
            return (int(val), "integer") if val.is_integer() else (val, "float")

    if not isinstance(val, str):
        return None, None

    s = val.strip()
    if not s:
        return None, None

    # Preserve leading zeros (e.g., '0123') as non-pure-number unless it is literally '0'
    if LEADING_ZERO_REGEX.match(s):
        return None, None

    # Handle accounting format: "(100.50)" -> "-100.50"
    paren_match = PAREN_NEGATIVE_REGEX.match(s)
    if paren_match:
        inner = paren_match.group(1).strip()
        parsed, p_type = parse_numeric(inner)
        if parsed is not None:
            return -parsed, p_type

    # Remove commas and common currency symbols
    cleaned = re.sub(r"[\$€£₹,]", "", s).strip()
    if not cleaned:
        return None, None

    if INTEGER_REGEX.match(cleaned):
        try:
            return int(cleaned), "integer"
        except ValueError:
            pass

    if FLOAT_REGEX.match(cleaned):
        try:
            f = float(cleaned)
            return (int(f), "integer") if f.is_integer() else (f, "float")
        except ValueError:
            pass

    return None, None


def parse_date(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempt to parse a date or datetime.
    Returns (iso_string, 'date' | 'datetime') or (None, None).
    Avoids interpreting pure numbers as dates.
    """
    if isinstance(val, datetime):
        return val.isoformat(), "datetime"
    if isinstance(val, date):
        return val.isoformat(), "date"

    if not isinstance(val, str):
        return None, None

    s = val.strip()
    # Reject pure numbers or short strings (like "123", "2024", "99") to prevent false date parsing
    if INTEGER_REGEX.match(s) or FLOAT_REGEX.match(s) or len(s) < 6:
        return None, None

    # Check for date-like delimiters: contains '/' or '-' or '.'
    if not any(char in s for char in ["/", "-", ".", " "]):
        return None, None

    try:
        parsed = date_parser.parse(s, fuzzy=False)
        # Verify year is sensible (e.g., 1800 to 2200)
        if 1800 <= parsed.year <= 2200:
            if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0:
                return parsed.date().isoformat(), "date"
            return parsed.isoformat(), "datetime"
    except (ValueError, OverflowError, TypeError):
        pass

    return None, None


def is_boolean(val: Any) -> Tuple[Optional[bool], bool]:
    """Check if value is a boolean string like 'true', 'false', 'yes', 'no'."""
    if isinstance(val, bool):
        return val, True
    if isinstance(val, str):
        lower = val.strip().lower()
        if lower in {"true", "yes"}:
            return True, True
        if lower in {"false", "no"}:
            return False, True
    return None, False
