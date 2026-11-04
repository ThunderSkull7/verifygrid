from uuid import uuid4
import pytest

from app.schemas.multisource import SourceDefinition
from app.schemas.result import DiscrepancyCategory, MatchStatus, ReasonCode
from app.services.profiling_service import (
    are_identifier_synonyms,
    discover_multisource_candidate_keys,
)
from app.services.verification_engine import (
    verify_datasets,
    verify_multisource_datasets,
)


def test_zero_comparable_fields_critical_safeguard_multisource():
    """Batch 8 Critical Safeguard: zero comparable fields must NEVER be reported as identical matches."""
    sources = [
        SourceDefinition(
            alias="academic",
            file_id=uuid4(),
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id"},
        ),
        SourceDefinition(
            alias="hostel",
            file_id=uuid4(),
            is_primary=False,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id"},
        ),
    ]

    sources_records = {
        "academic": [
            (1, {"student_id": "S101", "internal_notes": "Note A"}),
            (2, {"student_id": "S102", "internal_notes": "Note B"}),
        ],
        "hostel": [
            (1, {"student_id": "S101", "other_notes": "Note C"}),
            (2, {"student_id": "S102", "other_notes": "Note D"}),
        ],
    }

    # compare_attributes is empty: zero fields mapped for comparison
    summary, results, discrepancies, _, _ = verify_multisource_datasets(
        sources=sources,
        sources_records=sources_records,
        unified_keys=["student_id"],
        compare_attributes=[],
    )

    # Must NOT report identical matches
    assert summary.identical_matches == 0
    assert summary.attribute_comparisons_completed == 0
    # Both records were matched on keys, but flagged for review because 0 fields were checked
    assert summary.needs_review_records == 2
    assert len(discrepancies) == 2
    for item in discrepancies:
        assert item.match_status == MatchStatus.NEEDS_REVIEW
        assert "no comparable fields were evaluated" in (item.message or "").lower()


def test_zero_comparable_fields_critical_safeguard_two_file():
    """Two-file engine safeguard: zero compared fields must not report identical matches."""
    source_records = [
        (1, {"student_id": "S101"}),
        (2, {"student_id": "S102"}),
    ]
    target_records = [
        (1, {"student_id": "S101"}),
        (2, {"student_id": "S102"}),
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source_records,
        target_records=target_records,
        key_columns=["student_id"],
        compare_columns=[],  # empty compare columns
    )

    assert summary.identical_matches == 0
    assert summary.needs_review_records == 2
    assert len(discrepancies) == 2
    for item in discrepancies:
        assert item.match_status == MatchStatus.NEEDS_REVIEW
        assert "no comparable fields were evaluated" in (item.message or "").lower()


def test_different_matching_column_names_multisource():
    """Matching records across 3 sources having different column names (student_id, roll_no, id)."""
    sources = [
        SourceDefinition(
            alias="academic",
            file_id=uuid4(),
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "dept": "department"},
        ),
        SourceDefinition(
            alias="hostel",
            file_id=uuid4(),
            is_primary=False,
            key_columns=["roll_no"],
            field_mapping={"roll_no": "student_id", "department": "department"},
        ),
        SourceDefinition(
            alias="id_card",
            file_id=uuid4(),
            is_primary=False,
            key_columns=["id"],
            field_mapping={"id": "student_id", "branch": "department"},
        ),
    ]

    sources_records = {
        "academic": [
            (1, {"student_id": "S101", "dept": "Computer Science"}),
            (2, {"student_id": "S102", "dept": "Electrical"}),
        ],
        "hostel": [
            (1, {"roll_no": "S101", "department": "Computer Science"}),
            (2, {"roll_no": "S102", "department": "Mechanical"}),  # Mismatch
        ],
        "id_card": [
            (1, {"id": "S101", "branch": "Computer Science"}),
            (2, {"id": "S102", "branch": "Electrical"}),
        ],
    }

    summary, results, discrepancies, _, _ = verify_multisource_datasets(
        sources=sources,
        sources_records=sources_records,
        unified_keys=["student_id"],
        compare_attributes=["department"],
    )

    assert summary.total_source_records == 2
    assert summary.matched_records == 2
    assert summary.identical_matches == 1
    assert summary.field_mismatches == 1
    mismatch = next(d for d in discrepancies if d.match_status != MatchStatus.IDENTICAL)
    assert mismatch.key_values == {"student_id": "S102"}


def test_multi_primary_different_field_owners_correctness():
    """Multi-primary: Academic owns 'cgpa', Hostel owns 'room_no', Target checked against both."""
    sources = [
        SourceDefinition(
            alias="academic",
            file_id=uuid4(),
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "gpa": "cgpa"},
        ),
        SourceDefinition(
            alias="hostel",
            file_id=uuid4(),
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "room": "room_no"},
        ),
        SourceDefinition(
            alias="id_card",
            file_id=uuid4(),
            is_primary=False,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "gpa": "cgpa", "room": "room_no"},
        ),
    ]

    sources_records = {
        "academic": [
            (1, {"student_id": "S101", "gpa": "3.8"}),
        ],
        "hostel": [
            (1, {"student_id": "S101", "room": "A-101"}),
        ],
        "id_card": [
            (1, {"student_id": "S101", "gpa": "3.8", "room": "A-101"}),
        ],
    }

    field_ownership = {
        "cgpa": "academic",
        "room_no": "hostel",
    }

    summary, results, discrepancies, _, _ = verify_multisource_datasets(
        sources=sources,
        sources_records=sources_records,
        unified_keys=["student_id"],
        compare_attributes=["cgpa", "room_no"],
        multi_primary=True,
        field_ownership=field_ownership,
    )

    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert summary.attribute_comparisons_completed == 2


def test_key_recommendations_with_different_column_names_and_value_overlap():
    """Candidate key discovery matches student_id in File 1 to roll_no in File 2 via overlap & synonym."""
    assert are_identifier_synonyms("student_id", "roll_no") is True
    assert are_identifier_synonyms("reg_no", "enrollment_no") is True

    sources_records = {
        "academic": [
            (1, {"student_id": "S101", "name": "Alice"}),
            (2, {"student_id": "S102", "name": "Bob"}),
            (3, {"student_id": "S103", "name": "Charlie"}),
        ],
        "hostel": [
            (1, {"roll_no": "S101", "hostel_room": "101"}),
            (2, {"roll_no": "S102", "hostel_room": "102"}),
            (3, {"roll_no": "S103", "hostel_room": "103"}),
        ],
    }

    recommendations = discover_multisource_candidate_keys(sources_records)
    assert len(recommendations) >= 1
    top = recommendations[0]
    assert top.source_columns["academic"] == ["student_id"]
    assert top.source_columns["hostel"] == ["roll_no"]
    assert top.overall_score >= 0.7


def test_key_recommendations_unsuitability_reason_for_duplicates():
    """Candidate key discovery flags low suitability when a key contains duplicate identifiers."""
    sources_records = {
        "academic": [
            (1, {"status": "enrolled", "department": "CS"}),
            (2, {"status": "enrolled", "department": "EE"}),
            (3, {"status": "enrolled", "department": "ME"}),
        ],
        "hostel": [
            (1, {"status": "enrolled", "room": "101"}),
            (2, {"status": "enrolled", "room": "102"}),
            (3, {"status": "enrolled", "room": "103"}),
        ],
    }

    recommendations = discover_multisource_candidate_keys(sources_records)
    # Status has duplicate values (100% duplicate rate)
    status_rec = next((r for r in recommendations if r.key_name == "status"), None)
    if status_rec:
        assert "duplicate" in status_rec.recommendation_reason.lower() or status_rec.overall_score < 0.6

