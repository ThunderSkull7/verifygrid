"""Alembic migration-parity tests for the canonical 0006 baseline (opt-in).

Batch 26C established the approved canonical single-head graph::

    0001_initial_tables -> 0002_verification_runs -> 0003_user_password
        -> 0004_enterprise_governance -> 0005_verification_templates
        -> 0006_discrepancy_review_decisions

Safety contract:
- Importing this module never opens a database connection.
- Tests skip unless ``VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS`` is enabled.
- ``VERIFYGRID_TEST_DATABASE_URL`` is mandatory and validated by the shared
  fail-closed guard.
- Alembic receives an already-validated connection explicitly; it never falls
  back to application configuration or ``.env``.
- A unique schema is created in the dedicated test database and dropped
  afterwards. No public/development tables are touched.
- ``Base.metadata`` is not used to create or assert the schema under test.
"""

from __future__ import annotations

import ipaddress
import json
import os
import uuid
from pathlib import Path
from typing import Generator, Optional

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from app.db.base import Base
import app.models  # Ensure all models are registered in Base.metadata

from tests.pg_test_target import (
    POSTGRES_INTEGRATION_ENV,
    TEST_DATABASE_URL_ENV,
    TargetCheck,
    integration_tests_enabled,
    safe_schema_name,
    validate_test_database_url,
)


pytestmark = pytest.mark.skipif(
    not integration_tests_enabled(),
    reason=(
        "Alembic migration-parity tests are opt-in. Set "
        f"{POSTGRES_INTEGRATION_ENV}=1 and {TEST_DATABASE_URL_ENV} to an "
        "explicitly isolated loopback test database. No application database "
        "is ever used as a fallback."
    ),
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
BASELINE_0004 = "0004_enterprise_governance"
EXPECTED_HEAD = "0006_discrepancy_review_decisions"

RUN_GOVERNANCE_COLUMNS = {
    "sources": ("json", "YES", None),
    "sign_off_status": ("character varying", "NO", "DRAFT"),
    "sign_off_proposed_by": ("uuid", "YES", None),
    "sign_off_proposed_by_name": ("character varying", "YES", None),
    "sign_off_proposal_note": ("text", "YES", None),
    "sign_off_proposed_at": ("timestamp with time zone", "YES", None),
    "sign_off_approved_by": ("uuid", "YES", None),
    "sign_off_approved_by_name": ("character varying", "YES", None),
    "sign_off_decision_note": ("text", "YES", None),
    "sign_off_decided_at": ("timestamp with time zone", "YES", None),
}

DISCREPANCY_GOVERNANCE_COLUMNS = {
    "source_row_indices": ("json", "YES", None),
    "source_records": ("json", "YES", None),
    "child_records": ("json", "YES", None),
    "aggregated_amount": ("double precision", "YES", None),
    "expected_amount": ("double precision", "YES", None),
    "source_amount": ("double precision", "YES", None),
    "target_amount": ("double precision", "YES", None),
    "variance_amount": ("double precision", "YES", None),
    "exposure_amount": ("double precision", "YES", None),
    "currency": ("character varying", "YES", "USD"),
    "severity": ("character varying", "YES", "medium"),
    "resolution_status": ("character varying", "YES", "unresolved"),
    "resolution_note": ("text", "YES", None),
    "resolved_by": ("character varying", "YES", None),
    "resolved_at": ("timestamp with time zone", "YES", None),
    "cluster_id": ("character varying", "YES", None),
    "cluster_name": ("character varying", "YES", None),
    "assigned_to": ("character varying", "YES", None),
    "assigned_at": ("timestamp with time zone", "YES", None),
    "side_by_side": ("json", "YES", None),
    "reason_code": ("character varying", "YES", None),
    "confidence_score": ("double precision", "YES", None),
}

AUDIT_EVENT_COLUMNS = {
    "id": ("uuid", "NO", None),
    "event_id": ("character varying", "NO", None),
    "sequence_number": ("integer", "NO", "1"),
    "run_id": ("uuid", "YES", None),
    "project_id": ("uuid", "NO", None),
    "user_id": ("uuid", "YES", None),
    "user_email": ("character varying", "YES", None),
    "user_role": ("character varying", "NO", "MAKER"),
    "event_type": ("character varying", "NO", None),
    "timestamp_utc": ("timestamp with time zone", "NO", "now()"),
    "timestamp_str": ("character varying", "NO", None),
    "event_payload": ("json", "NO", None),
    "previous_event_hash": ("character varying", "NO", None),
    "current_event_hash": ("character varying", "NO", None),
}

TEMPLATE_COLUMNS = {
    "id": ("uuid", "NO", None),
    "owner_id": ("uuid", "YES", None),
    "name": ("character varying", "NO", None),
    "description": ("text", "YES", None),
    "mode": ("character varying", "NO", None),
    "visibility": ("character varying", "NO", "personal"),
    "config_version": ("integer", "NO", "1"),
    "configuration": ("json", "NO", None),
    "created_at": ("timestamp with time zone", "NO", "now()"),
    "updated_at": ("timestamp with time zone", "NO", "now()"),
}

REVIEW_DECISION_COLUMNS = {
    "id": ("uuid", "NO", None),
    "discrepancy_id": ("uuid", "NO", None),
    "run_id": ("uuid", "NO", None),
    "decision": ("character varying", "NO", None),
    "justification": ("text", "NO", None),
    "reviewer_id": ("character varying", "YES", None),
    "reviewer_email": ("character varying", "YES", None),
    "previous_status": ("character varying", "YES", None),
    "new_status": ("character varying", "NO", None),
    "is_bulk_action": ("boolean", "NO", "false"),
    "cluster_id": ("character varying", "YES", None),
    "created_at": ("timestamp with time zone", "NO", "now()"),
}

EXPECTED_TABLES = {
    "users",
    "projects",
    "source_files",
    "verification_runs",
    "verification_discrepancies",
    "audit_events",
    "verification_templates",
    "discrepancy_review_decisions",
    "alembic_version",
}


def _require_safe_target() -> TargetCheck:
    check = validate_test_database_url(
        os.getenv(TEST_DATABASE_URL_ENV),
        application_url=os.getenv("DATABASE_URL"),
    )
    if not check.ok:
        pytest.fail(
            "Refusing to run Alembic migration-parity tests: "
            + " ".join(check.errors),
            pytrace=False,
        )
    assert check.url is not None
    return check


def _verify_connected_target(conn: Connection, check: TargetCheck) -> None:
    """Verify the actual server is the validated loopback test target."""
    database, username, address = conn.execute(
        text("SELECT current_database(), current_user, host(inet_server_addr())")
    ).one()
    assert database == check.database
    assert username == check.username
    if address is not None:
        assert ipaddress.ip_address(address).is_loopback, (
            "Connected PostgreSQL server address is not loopback."
        )


@pytest.fixture(scope="session")
def pg_target() -> TargetCheck:
    return _require_safe_target()


@pytest.fixture()
def migration_target(
    pg_target: TargetCheck,
) -> Generator[tuple[TargetCheck, str, Engine], None, None]:
    """Create a unique schema and an engine pinned to that schema."""
    assert pg_target.url is not None
    schema = safe_schema_name(f"verifygrid_mig_{uuid.uuid4().hex[:12]}")
    admin_engine = create_engine(
        pg_target.url,
        connect_args={"connect_timeout": 5},
    )
    migration_engine: Optional[Engine] = None
    try:
        with admin_engine.begin() as conn:
            _verify_connected_target(conn, pg_target)
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        migration_engine = create_engine(
            pg_target.url,
            connect_args={
                "connect_timeout": 5,
                "options": f"-csearch_path={schema}",
            },
            pool_pre_ping=True,
        )
        with migration_engine.connect() as conn:
            _verify_connected_target(conn, pg_target)
        yield pg_target, schema, migration_engine
    finally:
        if migration_engine is not None:
            migration_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def _run_alembic(
    engine: Engine,
    check: TargetCheck,
    action: str,
    revision: str,
) -> None:
    """Run Alembic through an explicitly validated connection."""
    with engine.connect() as connection:
        _verify_connected_target(connection, check)
        connection.rollback()
        config = _alembic_config(connection)
        if action == "upgrade":
            command.upgrade(config, revision)
        elif action == "downgrade":
            command.downgrade(config, revision)
        else:
            raise ValueError(f"Unsupported Alembic action: {action}")
        connection.rollback()


def _expected_head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def _current_revision(conn: Connection) -> str:
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _column_info(conn: Connection, schema: str) -> dict[tuple[str, str], dict]:
    rows = conn.execute(
        text(
            """
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = :schema
            """
        ),
        {"schema": schema},
    ).mappings()
    return {(row["table_name"], row["column_name"]): dict(row) for row in rows}


def _assert_column(
    columns: dict[tuple[str, str], dict],
    table: str,
    name: str,
    data_type: str,
    nullable: str,
    default_contains: Optional[str],
) -> None:
    key = (table, name)
    assert key in columns, f"Missing migrated column {table}.{name}"
    actual = columns[key]
    assert actual["data_type"] == data_type, (
        f"{table}.{name} type is {actual['data_type']!r}, expected {data_type!r}"
    )
    assert actual["is_nullable"] == nullable, (
        f"{table}.{name} nullability is {actual['is_nullable']!r}, "
        f"expected {nullable!r}"
    )
    if default_contains is None:
        assert actual["column_default"] is None, (
            f"{table}.{name} unexpectedly has a default: "
            f"{actual['column_default']!r}"
        )
    else:
        assert default_contains in (actual["column_default"] or ""), (
            f"{table}.{name} default {actual['column_default']!r} does not "
            f"contain {default_contains!r}"
        )


def _assert_canonical_schema(conn: Connection, schema: str) -> None:
    inspector = inspect(conn)
    actual_tables = set(inspector.get_table_names(schema=schema))
    assert actual_tables == EXPECTED_TABLES, (
        f"Unexpected table set: {sorted(actual_tables)}"
    )

    columns = _column_info(conn, schema)
    _assert_column(columns, "users", "role", "character varying", "NO", "MAKER")
    for name, expected in RUN_GOVERNANCE_COLUMNS.items():
        _assert_column(columns, "verification_runs", name, *expected)
    for name, expected in DISCREPANCY_GOVERNANCE_COLUMNS.items():
        _assert_column(columns, "verification_discrepancies", name, *expected)
    for name, expected in AUDIT_EVENT_COLUMNS.items():
        _assert_column(columns, "audit_events", name, *expected)
    for name, expected in TEMPLATE_COLUMNS.items():
        _assert_column(columns, "verification_templates", name, *expected)
    for name, expected in REVIEW_DECISION_COLUMNS.items():
        _assert_column(columns, "discrepancy_review_decisions", name, *expected)

    # Verification run indexes
    run_indexes = {
        index["name"]
        for index in inspector.get_indexes("verification_runs", schema=schema)
    }
    assert "ix_verification_runs_sign_off_status" in run_indexes

    # Discrepancy indexes
    discrepancy_indexes = {
        index["name"]
        for index in inspector.get_indexes("verification_discrepancies", schema=schema)
    }
    assert {
        "ix_verification_discrepancies_exposure_amount",
        "ix_verification_discrepancies_severity",
        "ix_verification_discrepancies_resolution_status",
        "ix_verification_discrepancies_cluster_id",
        "ix_verification_discrepancies_assigned_to",
        "ix_verification_discrepancies_reason_code",
    } <= discrepancy_indexes

    # Audit event indexes
    audit_indexes = {
        index["name"] for index in inspector.get_indexes("audit_events", schema=schema)
    }
    assert {
        "ix_audit_events_event_id",
        "ix_audit_events_sequence_number",
        "ix_audit_events_run_id",
        "ix_audit_events_project_id",
        "ix_audit_events_event_type",
        "ix_audit_events_current_event_hash",
    } <= audit_indexes

    # Template indexes and unique constraints
    template_indexes = {
        index["name"]
        for index in inspector.get_indexes("verification_templates", schema=schema)
    }
    assert "ix_verification_templates_owner_id" in template_indexes

    template_unique = [
        set(u["column_names"])
        for u in inspector.get_unique_constraints("verification_templates", schema=schema)
    ]
    assert {"owner_id", "name"} in template_unique

    # Review decision indexes
    review_indexes = {
        index["name"]
        for index in inspector.get_indexes("discrepancy_review_decisions", schema=schema)
    }
    assert {
        "ix_discrepancy_review_decisions_cluster_id",
        "ix_discrepancy_review_decisions_discrepancy_id",
        "ix_discrepancy_review_decisions_reviewer_id",
        "ix_discrepancy_review_decisions_run_id",
    } <= review_indexes

    # Foreign key checks (including RESTRICT for review decisions and SET NULL for templates)
    template_fks = {
        (
            fk["constrained_columns"][0],
            fk["referred_table"],
            (fk.get("options") or {}).get("ondelete"),
        )
        for fk in inspector.get_foreign_keys("verification_templates", schema=schema)
    }
    assert ("owner_id", "users", "SET NULL") in template_fks

    review_fks = {
        (
            fk["constrained_columns"][0],
            fk["referred_table"],
            (fk.get("options") or {}).get("ondelete"),
        )
        for fk in inspector.get_foreign_keys("discrepancy_review_decisions", schema=schema)
    }
    assert ("discrepancy_id", "verification_discrepancies", "RESTRICT") in review_fks
    assert ("run_id", "verification_runs", "RESTRICT") in review_fks


def _insert_production_0004_data(conn: Connection) -> dict[str, uuid.UUID]:
    """Insert production-equivalent data that exists at revision 0004."""
    ids = {
        "user": uuid.uuid4(),
        "project": uuid.uuid4(),
        "source_file": uuid.uuid4(),
        "run": uuid.uuid4(),
        "discrepancy": uuid.uuid4(),
        "audit_event": uuid.uuid4(),
    }
    conn.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role) "
            "VALUES (:id, :email, :hashed_password, :full_name, :role)"
        ),
        {
            "id": ids["user"],
            "email": "prod-lead@example.com",
            "hashed_password": "hashed_prod_password",
            "full_name": "Production Lead",
            "role": "ADMIN",
        },
    )
    conn.execute(
        text("INSERT INTO projects (id, name, owner_id) VALUES (:id, :name, :owner_id)"),
        {"id": ids["project"], "name": "Production Project", "owner_id": ids["user"]},
    )
    conn.execute(
        text(
            """
            INSERT INTO source_files
                (id, project_id, original_filename, storage_path, file_type, file_size, status)
            VALUES
                (:id, :project_id, :filename, :storage_path, :file_type, :file_size, :status)
            """
        ),
        {
            "id": ids["source_file"],
            "project_id": ids["project"],
            "filename": "prod_data.csv",
            "storage_path": "/storage/prod_data.csv",
            "file_type": "csv",
            "file_size": 1024,
            "status": "uploaded",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO verification_runs
                (id, project_id, source_file_id, status, key_columns,
                 column_mapping, configuration, summary, sources, sign_off_status,
                 sign_off_proposed_by, sign_off_proposed_by_name)
            VALUES
                (:id, :project_id, :source_file_id, :status,
                 CAST(:key_columns AS json), CAST(:column_mapping AS json),
                 CAST(:configuration AS json), CAST(:summary AS json),
                 CAST(:sources AS json), :sign_off_status,
                 :sign_off_proposed_by, :sign_off_proposed_by_name)
            """
        ),
        {
            "id": ids["run"],
            "project_id": ids["project"],
            "source_file_id": ids["source_file"],
            "status": "completed",
            "key_columns": json.dumps(["account_id"]),
            "column_mapping": json.dumps({"primary": {"account_id": "account_id"}}),
            "configuration": json.dumps({"mode": "organization"}),
            "summary": json.dumps({"total_discrepancies": 1}),
            "sources": json.dumps([{"alias": "ledger", "file_id": str(ids["source_file"])}]),
            "sign_off_status": "AWAITING_SIGN_OFF",
            "sign_off_proposed_by": ids["user"],
            "sign_off_proposed_by_name": "Production Lead",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO verification_discrepancies
                (id, run_id, match_status, discrepancy_category, key_values,
                 source_row_number, target_row_number, source_row_numbers, target_row_numbers,
                 source_records, target_record, field_differences, message,
                 source_amount, target_amount, variance_amount, exposure_amount,
                 currency, severity, resolution_status, cluster_id, cluster_name,
                 reason_code, confidence_score)
            VALUES
                (:id, :run_id, :match_status, :discrepancy_category, CAST(:key_values AS json),
                 :source_row_number, :target_row_number, CAST(:source_row_numbers AS json), CAST(:target_row_numbers AS json),
                 CAST(:source_records AS json), CAST(:target_record AS json), CAST(:field_differences AS json), :message,
                 :source_amount, :target_amount, :variance_amount, :exposure_amount,
                 :currency, :severity, :resolution_status, :cluster_id, :cluster_name,
                 :reason_code, :confidence_score)
            """
        ),
        {
            "id": ids["discrepancy"],
            "run_id": ids["run"],
            "match_status": "field_mismatch",
            "discrepancy_category": "amount_variance",
            "key_values": json.dumps({"account_id": "ACC-100"}),
            "source_row_number": 1,
            "target_row_number": 1,
            "source_row_numbers": json.dumps([1]),
            "target_row_numbers": json.dumps([1]),
            "source_records": json.dumps({"ledger": {"account_id": "ACC-100", "amount": 5000.0}}),
            "target_record": json.dumps({"account_id": "ACC-100", "amount": 4500.0}),
            "field_differences": json.dumps([{"field": "amount", "diff": 500.0}]),
            "message": "Amount variance detected",
            "source_amount": 5000.0,
            "target_amount": 4500.0,
            "variance_amount": 500.0,
            "exposure_amount": 500.0,
            "currency": "USD",
            "severity": "high",
            "resolution_status": "unresolved",
            "cluster_id": "CLUST-VARIANCE-01",
            "cluster_name": "High Exposure Ledger Variance",
            "reason_code": "FIELD_MISMATCH",
            "confidence_score": 0.98,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO audit_events
                (id, event_id, sequence_number, run_id, project_id, user_id, user_email,
                 user_role, event_type, timestamp_str, event_payload,
                 previous_event_hash, current_event_hash)
            VALUES
                (:id, :event_id, :sequence_number, :run_id, :project_id, :user_id, :user_email,
                 :user_role, :event_type, :timestamp_str, CAST(:event_payload AS json),
                 :previous_event_hash, :current_event_hash)
            """
        ),
        {
            "id": ids["audit_event"],
            "event_id": "EVT-0001",
            "sequence_number": 1,
            "run_id": ids["run"],
            "project_id": ids["project"],
            "user_id": ids["user"],
            "user_email": "prod-lead@example.com",
            "user_role": "ADMIN",
            "event_type": "RUN_SIGN_OFF_PROPOSED",
            "timestamp_str": "2026-10-29T10:00:00Z",
            "event_payload": json.dumps({"action": "PROPOSE_SIGN_OFF"}),
            "previous_event_hash": "GENESIS_HASH",
            "current_event_hash": "a1b2c3d4e5f6",
        },
    )
    return ids


# =============================================================================
# Parity Tests
# =============================================================================


def test_alembic_head_matches_canonical_baseline(migration_target) -> None:
    """Fresh upgrade from empty schema through 0006 creates full canonical schema."""
    check, schema, engine = migration_target
    assert _expected_head() == EXPECTED_HEAD

    _run_alembic(engine, check, "upgrade", "head")

    with engine.connect() as conn:
        _verify_connected_target(conn, check)
        assert _current_revision(conn) == EXPECTED_HEAD
        _assert_canonical_schema(conn, schema)


def test_upgrade_from_0004_production_baseline_preserves_records(migration_target) -> None:
    """Upgrading a production-equivalent schema at 0004 to 0006 preserves existing data."""
    check, schema, engine = migration_target

    # 1. Upgrade to production baseline (0004)
    _run_alembic(engine, check, "upgrade", BASELINE_0004)
    with engine.connect() as conn:
        _verify_connected_target(conn, check)
        assert _current_revision(conn) == BASELINE_0004
        inspector = inspect(conn)
        tables = set(inspector.get_table_names(schema=schema))
        assert "verification_templates" not in tables
        assert "discrepancy_review_decisions" not in tables

    # 2. Populate production data at 0004
    with engine.begin() as conn:
        ids = _insert_production_0004_data(conn)

    # 3. Upgrade to canonical head (0006)
    _run_alembic(engine, check, "upgrade", "head")
    with engine.connect() as conn:
        _verify_connected_target(conn, check)
        assert _current_revision(conn) == EXPECTED_HEAD
        _assert_canonical_schema(conn, schema)

        # Verify existing 0004 user preserved
        user_row = dict(conn.execute(
            text("SELECT email, role, full_name FROM users WHERE id = :id"),
            {"id": ids["user"]},
        ).mappings().one())
        assert user_row["email"] == "prod-lead@example.com"
        assert user_row["role"] == "ADMIN"

        # Verify existing 0004 run preserved
        run_row = dict(conn.execute(
            text("SELECT status, sign_off_status, sign_off_proposed_by_name FROM verification_runs WHERE id = :id"),
            {"id": ids["run"]},
        ).mappings().one())
        assert run_row["status"] == "completed"
        assert run_row["sign_off_status"] == "AWAITING_SIGN_OFF"
        assert run_row["sign_off_proposed_by_name"] == "Production Lead"

        # Verify existing 0004 discrepancy and materiality preserved
        disc_row = dict(conn.execute(
            text(
                "SELECT source_amount, target_amount, exposure_amount, currency, "
                "severity, cluster_id, reason_code, confidence_score "
                "FROM verification_discrepancies WHERE id = :id"
            ),
            {"id": ids["discrepancy"]},
        ).mappings().one())
        assert disc_row["source_amount"] == 5000.0
        assert disc_row["exposure_amount"] == 500.0
        assert disc_row["severity"] == "high"
        assert disc_row["cluster_id"] == "CLUST-VARIANCE-01"
        assert disc_row["reason_code"] == "FIELD_MISMATCH"
        assert disc_row["confidence_score"] == 0.98

        # Verify existing audit event preserved
        audit_count = conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
        assert audit_count == 1

    # 4. Insert into new 0005/0006 tables using existing references
    with engine.begin() as conn:
        tmpl_id = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO verification_templates
                    (id, owner_id, name, mode, visibility, config_version, configuration)
                VALUES
                    (:id, :owner_id, :name, :mode, :visibility, :config_version, CAST(:config AS json))
                """
            ),
            {
                "id": tmpl_id,
                "owner_id": ids["user"],
                "name": "Standard Invoicing Template",
                "mode": "organization",
                "visibility": "personal",
                "config_version": 1,
                "config": json.dumps({"rules": []}),
            },
        )

        dec_id = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO discrepancy_review_decisions
                    (id, discrepancy_id, run_id, decision, justification,
                     reviewer_id, reviewer_email, new_status, is_bulk_action)
                VALUES
                    (:id, :disc_id, :run_id, :decision, :justification,
                     :rev_id, :rev_email, :new_status, :is_bulk)
                """
            ),
            {
                "id": dec_id,
                "disc_id": ids["discrepancy"],
                "run_id": ids["run"],
                "decision": "APPROVE",
                "justification": "Approved variance under threshold",
                "rev_id": str(ids["user"]),
                "rev_email": "prod-lead@example.com",
                "new_status": "APPROVED",
                "is_bulk": False,
            },
        )

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM verification_templates")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM discrepancy_review_decisions")).scalar_one() == 1


def test_empty_downgrade_and_reupgrade_round_trip(migration_target) -> None:
    """Downgrading from 0006 to 0004 drops new tables; re-upgrade restores them cleanly."""
    check, schema, engine = migration_target

    _run_alembic(engine, check, "upgrade", "head")
    with engine.connect() as conn:
        _verify_connected_target(conn, check)
        assert _current_revision(conn) == EXPECTED_HEAD
        _assert_canonical_schema(conn, schema)

    # Downgrade to 0004
    _run_alembic(engine, check, "downgrade", BASELINE_0004)
    with engine.connect() as conn:
        _verify_connected_target(conn, check)
        assert _current_revision(conn) == BASELINE_0004
        inspector = inspect(conn)
        tables = set(inspector.get_table_names(schema=schema))
        assert "verification_templates" not in tables
        assert "discrepancy_review_decisions" not in tables
        assert "audit_events" in tables
        assert "verification_runs" in tables

    # Re-upgrade to 0006
    _run_alembic(engine, check, "upgrade", "head")
    with engine.connect() as conn:
        _verify_connected_target(conn, check)
        assert _current_revision(conn) == EXPECTED_HEAD
        _assert_canonical_schema(conn, schema)
