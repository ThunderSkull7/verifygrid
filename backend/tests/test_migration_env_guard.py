"""Unit and static tests for the Batch 25 migration target guard.

These tests never open a database connection. They prove that:

- ``migrations/env.py`` has no application-settings/.env fallback;
- missing, malformed, remote, and ambiguous targets fail closed;
- the isolated test policy requires a loopback host, a test-named database,
  and a test-named role;
- the live database/role/address identity check rejects mismatches;
- Alembic graph inspection works without a target; and
- the restored revision template generates a syntactically valid migration in
  a temporary copy of the migrations directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
VERSIONS_DIR = MIGRATIONS_DIR / "versions"
ENV_PATH = MIGRATIONS_DIR / "env.py"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
RECOVERED_GOVERNANCE = VERSIONS_DIR / "0004_enterprise_governance_and_materiality.py"

EXPECTED_HEAD = "0006_discrepancy_review_decisions"
RECOVERED_GOVERNANCE_SHA256 = (
    "44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB"
)
LOOPBACK_TEST_URL = (
    "postgresql+psycopg://verifygrid_test_app@127.0.0.1:55432/verifygrid_test"
)
REMOTE_URL = "postgresql+psycopg://verifygrid_app:placeholder@db.example.com:5432/verifygrid"


def _load_env_module():
    spec = importlib.util.spec_from_file_location("verifygrid_batch25_env", ENV_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


env_mod = _load_env_module()


class _FakeConnection:
    """Minimal Connection double for the identity check (no DB)."""

    def __init__(
        self,
        database: str,
        username: str,
        address,
        already_in_transaction: bool = False,
        raise_on_rollback: bool = False,
    ):
        self._row = (database, username, address)
        self._in_transaction = already_in_transaction
        self.rollbacks = 0
        self.caller_transaction_untouched = already_in_transaction
        self.caller_work_intact = already_in_transaction
        self.raise_on_rollback = raise_on_rollback
        self.is_invalidated = False

    def in_transaction(self) -> bool:
        return self._in_transaction

    def execute(self, _statement):
        class _Result:
            def __init__(self, row):
                self._row = row

            def one(self):
                return self._row

        self._in_transaction = True
        return _Result(self._row)

    def rollback(self) -> None:
        if self.raise_on_rollback:
            raise RuntimeError("Underlying connection broken during rollback")
        self.rollbacks += 1
        self._in_transaction = False
        self.caller_transaction_untouched = False
        self.caller_work_intact = False


def _run_alembic(*args: str, overrides: dict[str, str] | None = None):
    clean = os.environ.copy()
    for key in (
        env_mod.MIGRATION_URL_ENV,
        env_mod.INTEGRATION_ENV,
        env_mod.ALLOW_REMOTE_ENV,
        env_mod.ACK_ENV,
        "DATABASE_URL",
    ):
        clean.pop(key, None)
    if overrides:
        clean.update(overrides)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_DIR,
        env=clean,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _combined(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + (result.stderr or "")


def test_env_has_no_application_settings_or_ini_fallback():
    text = ENV_PATH.read_text(encoding="utf-8")
    assert "settings.database_url" not in text
    assert "from app.core.config import settings" not in text
    assert "engine_from_config" not in text
    assert "sqlalchemy.url" not in text
    assert env_mod.MIGRATION_URL_ENV in text


def test_alembic_ini_has_no_usable_target_url():
    text = ALEMBIC_INI.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("sqlalchemy.url"):
            pytest.fail("alembic.ini still contains a sqlalchemy.url setting")
    assert "postgresql+psycopg://" not in text


def test_missing_target_fails_closed():
    with pytest.raises(env_mod.MigrationTargetError, match="explicit migration target"):
        env_mod.select_explicit_url({}, {})


def test_database_url_environment_is_not_a_target():
    with pytest.raises(env_mod.MigrationTargetError, match="explicit migration target"):
        env_mod.select_explicit_url({}, {"DATABASE_URL": REMOTE_URL})


def test_migration_url_environment_is_accepted_for_loopback():
    url, loopback = env_mod.select_explicit_url(
        {}, {env_mod.MIGRATION_URL_ENV: LOOPBACK_TEST_URL}
    )
    assert loopback is True
    assert url.database == "verifygrid_test"
    assert url.username == "verifygrid_test_app"


def test_x_argument_takes_precedence_over_environment():
    url, _ = env_mod.select_explicit_url(
        {"db_url": LOOPBACK_TEST_URL},
        {env_mod.MIGRATION_URL_ENV: REMOTE_URL},
    )
    assert url.database == "verifygrid_test"


def test_non_postgres_target_is_rejected():
    with pytest.raises(env_mod.MigrationTargetError, match="postgresql\\+psycopg"):
        env_mod.validate_target_url("sqlite:///verifygrid.db", {})


def test_system_database_is_rejected():
    with pytest.raises(env_mod.MigrationTargetError, match="system database"):
        env_mod.validate_target_url(
            "postgresql+psycopg://verifygrid_test_app@127.0.0.1:55432/postgres",
            {},
        )


def test_remote_target_is_rejected_without_guard_variables():
    with pytest.raises(env_mod.MigrationTargetError, match="non-loopback"):
        env_mod.validate_target_url(REMOTE_URL, {})


def test_old_generic_remote_target_is_rejected():
    """Prove the old permissive un-targeted remote target (Batch 25) fails closed."""
    with pytest.raises(env_mod.MigrationTargetError):
        env_mod.validate_target_url(REMOTE_URL, {env_mod.ALLOW_REMOTE_ENV: "1"})
    with pytest.raises(env_mod.MigrationTargetError):
        env_mod.validate_target_url(REMOTE_URL, {env_mod.ACK_ENV: "CHG-123"})
    with pytest.raises(env_mod.MigrationTargetError, match="permitted Neon direct hostname pattern"):
        env_mod.validate_target_url(
            REMOTE_URL,
            {env_mod.ALLOW_REMOTE_ENV: "1", env_mod.ACK_ENV: "CHG-123"},
        )


# =============================================================================
# Batch 15: Target-Bound Staging & Production Authorization Test Suite
# =============================================================================

VALID_STAGING_ENDPOINT = "ep-staging-rehearsal-123456"
VALID_STAGING_URL = (
    f"postgresql+psycopg://neondb_owner:secret@{VALID_STAGING_ENDPOINT}.ap-southeast-1.aws.neon.tech/neondb"
)

VALID_PROD_ENDPOINT = "ep-round-sea-b3b78mtc"
VALID_PROD_URL = (
    f"postgresql+psycopg://neondb_owner:secret@{VALID_PROD_ENDPOINT}.c-4.ap-southeast-1.aws.neon.tech/neondb"
)

POOLED_STAGING_URL = (
    f"postgresql+psycopg://neondb_owner:secret@{VALID_STAGING_ENDPOINT}-pooler.ap-southeast-1.aws.neon.tech/neondb"
)


def test_staging_authorization_success_via_environment():
    """Staging authorization succeeds when target-bound ack matches endpoint ID."""
    url, loopback = env_mod.validate_target_url(
        VALID_STAGING_URL,
        {
            env_mod.ALLOW_STAGING_ENV: "1",
            env_mod.STAGING_ACK_ENV: VALID_STAGING_ENDPOINT,
        },
    )
    assert loopback is False
    assert url.database == "neondb"
    assert url.username == "neondb_owner"


def test_staging_authorization_success_via_cli_x_args():
    """Staging authorization succeeds with per-invocation -x arguments."""
    url, loopback = env_mod.validate_target_url(
        VALID_STAGING_URL,
        {},
        x_args={"target": "staging", "ack": VALID_STAGING_ENDPOINT},
    )
    assert loopback is False
    assert url.database == "neondb"


def test_production_authorization_success_via_environment():
    """Production authorization succeeds with exact production endpoint and ack."""
    url, loopback = env_mod.validate_target_url(
        VALID_PROD_URL,
        {
            env_mod.ALLOW_PRODUCTION_ENV: "1",
            env_mod.PRODUCTION_ACK_ENV: f"CONFIRM-PRODUCTION-{VALID_PROD_ENDPOINT}",
        },
    )
    assert loopback is False
    assert url.database == "neondb"


def test_production_authorization_success_via_cli_x_args():
    """Production authorization succeeds with per-invocation -x arguments."""
    url, loopback = env_mod.validate_target_url(
        VALID_PROD_URL,
        {},
        x_args={"target": "production", "ack": VALID_PROD_ENDPOINT},
    )
    assert loopback is False


def test_staging_ack_against_production_endpoint_fails_closed():
    """Staging credentials MUST NOT authorize production endpoint."""
    with pytest.raises(env_mod.MigrationTargetError, match="known production endpoint"):
        env_mod.validate_target_url(
            VALID_PROD_URL,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_PROD_ENDPOINT,
            },
        )


def test_production_ack_against_staging_endpoint_fails_closed():
    """Production credentials MUST NOT authorize staging endpoint."""
    with pytest.raises(env_mod.MigrationTargetError, match="does not match expected production endpoint"):
        env_mod.validate_target_url(
            VALID_STAGING_URL,
            {
                env_mod.ALLOW_PRODUCTION_ENV: "1",
                env_mod.PRODUCTION_ACK_ENV: f"CONFIRM-PRODUCTION-{VALID_PROD_ENDPOINT}",
            },
        )


def test_wrong_staging_endpoint_id_fails_closed():
    """Mismatched acknowledgement fails closed."""
    with pytest.raises(env_mod.MigrationTargetError, match="does not match target endpoint ID"):
        env_mod.validate_target_url(
            VALID_STAGING_URL,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: "ep-different-endpoint-999999",
            },
        )


def test_wrong_database_name_fails_closed():
    """Non-neondb database name fails closed."""
    bad_db_url = f"postgresql+psycopg://neondb_owner:secret@{VALID_STAGING_ENDPOINT}.neon.tech/wrong_db"
    with pytest.raises(env_mod.MigrationTargetError, match="Invalid staging database name"):
        env_mod.validate_target_url(
            bad_db_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_STAGING_ENDPOINT,
            },
        )


def test_wrong_database_role_fails_closed():
    """Non-neondb_owner role fails closed."""
    bad_role_url = f"postgresql+psycopg://wrong_user:secret@{VALID_STAGING_ENDPOINT}.neon.tech/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="Invalid staging database role"):
        env_mod.validate_target_url(
            bad_role_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_STAGING_ENDPOINT,
            },
        )


def test_missing_acknowledgement_fails_closed():
    """Missing acknowledgement flag fails closed."""
    with pytest.raises(env_mod.MigrationTargetError, match="target-bound acknowledgement"):
        env_mod.validate_target_url(
            VALID_STAGING_URL,
            {env_mod.ALLOW_STAGING_ENV: "1"},
        )


def test_empty_acknowledgement_fails_closed():
    """Whitespace-only acknowledgement fails closed."""
    with pytest.raises(env_mod.MigrationTargetError, match="target-bound acknowledgement"):
        env_mod.validate_target_url(
            VALID_STAGING_URL,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: "   ",
            },
        )


def test_malformed_hostname_pattern_fails_closed():
    """Non-Neon hostname fails closed."""
    malformed_url = "postgresql+psycopg://neondb_owner:secret@non-neon-host.example.com/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="permitted Neon direct hostname pattern"):
        env_mod.validate_target_url(
            malformed_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: "non-neon-host",
            },
        )


def test_pooled_endpoint_rejected_for_schema_migrations():
    """Pooled endpoints containing -pooler are explicitly rejected."""
    with pytest.raises(env_mod.MigrationTargetError, match="pooled endpoint"):
        env_mod.validate_target_url(
            POOLED_STAGING_URL,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_STAGING_ENDPOINT,
            },
        )


def test_conflicting_authorization_flags_fail_closed():
    """Enabling both staging and production simultaneously fails closed."""
    with pytest.raises(env_mod.MigrationTargetError, match="Conflicting authorization"):
        env_mod.validate_target_url(
            VALID_STAGING_URL,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.ALLOW_PRODUCTION_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_STAGING_ENDPOINT,
            },
        )


def test_cli_argument_precedence_over_environment():
    """CLI -x arguments override ambient environment variables."""
    url, loopback = env_mod.validate_target_url(
        VALID_STAGING_URL,
        {
            env_mod.ALLOW_STAGING_ENV: "0",
            env_mod.STAGING_ACK_ENV: "wrong_env_ack",
        },
        x_args={"target": "staging", "ack": VALID_STAGING_ENDPOINT},
    )
    assert loopback is False
    assert url.database == "neondb"


class _FakeNeonConnection(_FakeConnection):
    def __init__(
        self,
        database,
        username,
        address,
        endpoint,
        raise_on_endpoint=False,
        already_in_transaction: bool = False,
        raise_on_rollback: bool = False,
    ):
        super().__init__(
            database,
            username,
            address,
            already_in_transaction=already_in_transaction,
            raise_on_rollback=raise_on_rollback,
        )
        self._endpoint = endpoint
        self._raise_on_endpoint = raise_on_endpoint

    def execute(self, statement):
        self._in_transaction = True
        stmt_str = str(statement)
        if "neon.endpoint_id" in stmt_str:
            if self._raise_on_endpoint:
                self.is_invalidated = True
                raise RuntimeError("Neon GUC query failed: connection reset")
            class _NeonResult:
                def __init__(self, ep):
                    self._ep = ep
                def scalar_one_or_none(self):
                    return self._ep
                def one(self):
                    return (self._ep,)
            return _NeonResult(self._endpoint)
        return super().execute(statement)


def test_post_connection_neon_endpoint_match_succeeds():
    """Matching endpoint ID succeeds and finishes cleanly."""
    conn_match = _FakeNeonConnection("neondb", "neondb_owner", "203.0.113.5", VALID_STAGING_ENDPOINT)
    env_mod._assert_server_identity(conn_match, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_match.rollbacks == 1


def test_post_connection_neon_endpoint_mismatch_fails_closed():
    """Mismatched endpoint ID fails closed before any DDL."""
    conn_mismatch = _FakeNeonConnection("neondb", "neondb_owner", "203.0.113.5", "ep-unexpected-rogue-endpoint")
    with pytest.raises(env_mod.MigrationTargetError, match="does not match expected target endpoint"):
        env_mod._assert_server_identity(conn_mismatch, make_url(VALID_STAGING_URL), require_loopback=False)


def test_post_connection_neon_endpoint_missing_fails_closed():
    """Missing (NULL) endpoint ID fails closed for remote Neon target."""
    conn_missing = _FakeNeonConnection("neondb", "neondb_owner", "203.0.113.5", None)
    with pytest.raises(env_mod.MigrationTargetError, match="did not report a 'neon.endpoint_id' setting"):
        env_mod._assert_server_identity(conn_missing, make_url(VALID_STAGING_URL), require_loopback=False)


def test_post_connection_neon_endpoint_empty_fails_closed():
    """Empty or whitespace-only endpoint ID fails closed for remote Neon target."""
    conn_empty = _FakeNeonConnection("neondb", "neondb_owner", "203.0.113.5", "   ")
    with pytest.raises(env_mod.MigrationTargetError, match="did not report a 'neon.endpoint_id' setting"):
        env_mod._assert_server_identity(conn_empty, make_url(VALID_STAGING_URL), require_loopback=False)


def test_post_connection_neon_endpoint_malformed_fails_closed():
    """Malformed endpoint ID without 'ep-' prefix fails closed."""
    conn_malformed = _FakeNeonConnection("neondb", "neondb_owner", "203.0.113.5", "rogue-endpoint-without-prefix")
    with pytest.raises(env_mod.MigrationTargetError, match="malformed Neon endpoint ID"):
        env_mod._assert_server_identity(conn_malformed, make_url(VALID_STAGING_URL), require_loopback=False)


def test_post_connection_neon_endpoint_query_exception_fails_closed():
    """Query failure when querying neon.endpoint_id is not swallowed and fails closed."""
    conn_err = _FakeNeonConnection("neondb", "neondb_owner", "203.0.113.5", None, raise_on_endpoint=True)
    with pytest.raises(env_mod.MigrationTargetError, match="Failed to query server setting 'neon.endpoint_id'"):
        env_mod._assert_server_identity(conn_err, make_url(VALID_STAGING_URL), require_loopback=False)


def test_post_connection_loopback_skips_neon_endpoint_check():
    """Existing loopback targets do not query neon.endpoint_id and continue to pass."""
    conn_loopback = _FakeNeonConnection("verifygrid_test", "verifygrid_test_app", "127.0.0.1", None)
    env_mod._assert_server_identity(conn_loopback, make_url(LOOPBACK_TEST_URL), require_loopback=True)
    assert conn_loopback.rollbacks == 1


def test_caller_transaction_survives_successful_validation():
    """Existing caller-owned transactions survive successful validation with zero rollbacks."""
    conn_caller = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", VALID_STAGING_ENDPOINT, already_in_transaction=True
    )
    env_mod._assert_server_identity(conn_caller, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_caller.rollbacks == 0
    assert conn_caller.in_transaction() is True
    assert conn_caller.caller_work_intact is True


def test_caller_transaction_survives_failed_endpoint_validation():
    """Existing caller-owned transactions survive failed endpoint validation without being rolled back."""
    conn_caller = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", "ep-unexpected-rogue-endpoint", already_in_transaction=True
    )
    with pytest.raises(env_mod.MigrationTargetError, match="does not match expected target endpoint"):
        env_mod._assert_server_identity(conn_caller, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_caller.rollbacks == 0
    assert conn_caller.in_transaction() is True
    assert conn_caller.caller_work_intact is True


def test_caller_transaction_survives_endpoint_query_exception():
    """Endpoint query exception fails closed while preserving caller-owned transaction and work."""
    conn_caller = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", None, raise_on_endpoint=True, already_in_transaction=True
    )
    with pytest.raises(env_mod.MigrationTargetError, match="Failed to query server setting 'neon.endpoint_id'"):
        env_mod._assert_server_identity(conn_caller, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_caller.rollbacks == 0
    assert conn_caller.in_transaction() is True
    assert conn_caller.caller_transaction_untouched is True
    assert conn_caller.is_invalidated is True


def test_caller_transaction_query_failure_semantics():
    """When an endpoint query fails under a caller-owned transaction, the guard
    never rolls back the caller transaction (rollbacks == 0), but the failure
    invalidates the underlying connection and fails closed."""
    conn_caller = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", None, raise_on_endpoint=True, already_in_transaction=True
    )
    with pytest.raises(env_mod.MigrationTargetError, match="Failed to query server setting 'neon.endpoint_id'"):
        env_mod._assert_server_identity(conn_caller, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_caller.rollbacks == 0
    assert conn_caller.caller_transaction_untouched is True
    assert conn_caller.is_invalidated is True


def test_guard_cleanup_rollback_error_does_not_conceal_identity_failure():
    """When a guard-owned connection encounters a rollback failure during cleanup,
    the original identity validation error is preserved and not concealed."""
    conn_guard = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", "ep-unexpected-rogue-endpoint",
        already_in_transaction=False,
        raise_on_rollback=True,
    )
    with pytest.raises(env_mod.MigrationTargetError, match="does not match expected target endpoint"):
        env_mod._assert_server_identity(conn_guard, make_url(VALID_STAGING_URL), require_loopback=False)


def test_guard_cleanup_rollback_error_raised_if_no_prior_exception():
    """When no identity error occurs but cleanup rollback fails, the rollback error is raised."""
    conn_guard = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", VALID_STAGING_ENDPOINT,
        already_in_transaction=False,
        raise_on_rollback=True,
    )
    with pytest.raises(RuntimeError, match="Underlying connection broken during rollback"):
        env_mod._assert_server_identity(conn_guard, make_url(VALID_STAGING_URL), require_loopback=False)


def test_staging_rejects_configured_production_endpoint_via_env():
    """Staging authorization rejects a custom production endpoint configured via environment."""
    custom_prod_ep = "ep-custom-prod-999999"
    custom_prod_url = f"postgresql+psycopg://neondb_owner:secret@{custom_prod_ep}.neon.tech/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="configured production endpoint"):
        env_mod.validate_target_url(
            custom_prod_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: custom_prod_ep,
                env_mod.PRODUCTION_ENDPOINT_ENV: custom_prod_ep,
            },
        )


def test_staging_rejects_configured_production_endpoint_via_x_args():
    """Staging authorization rejects a custom production endpoint configured via CLI x_args."""
    custom_prod_ep = "ep-custom-prod-888888"
    custom_prod_url = f"postgresql+psycopg://neondb_owner:secret@{custom_prod_ep}.neon.tech/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="configured production endpoint"):
        env_mod.validate_target_url(
            custom_prod_url,
            env={env_mod.ALLOW_STAGING_ENV: "1", env_mod.STAGING_ACK_ENV: custom_prod_ep},
            x_args={"target": "staging", "production_endpoint_id": custom_prod_ep, "ack": custom_prod_ep},
        )


def test_staging_rejects_both_hardcoded_and_configured_production_endpoints():
    """Staging authorization rejects both KNOWN_PRODUCTION_ENDPOINT and configured production endpoint."""
    custom_prod_ep = "ep-custom-prod-777777"
    # 1. Configured custom prod endpoint rejected
    custom_prod_url = f"postgresql+psycopg://neondb_owner:secret@{custom_prod_ep}.neon.tech/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="configured production endpoint"):
        env_mod.validate_target_url(
            custom_prod_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: custom_prod_ep,
                env_mod.PRODUCTION_ENDPOINT_ENV: custom_prod_ep,
            },
        )
    # 2. Hardcoded KNOWN_PRODUCTION_ENDPOINT is also still rejected
    with pytest.raises(env_mod.MigrationTargetError, match="known production endpoint"):
        env_mod.validate_target_url(
            VALID_PROD_URL,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_PROD_ENDPOINT,
                env_mod.PRODUCTION_ENDPOINT_ENV: custom_prod_ep,
            },
        )


def test_staging_conflicting_expected_staging_endpoint_matching_production_fails():
    """Configuring expected staging endpoint to match a production endpoint fails closed."""
    custom_prod_ep = "ep-custom-prod-666666"
    valid_staging_url = f"postgresql+psycopg://neondb_owner:secret@{VALID_STAGING_ENDPOINT}.neon.tech/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="matches a production endpoint"):
        env_mod.validate_target_url(
            valid_staging_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_STAGING_ENDPOINT,
                env_mod.STAGING_ENDPOINT_ENV: custom_prod_ep,
                env_mod.PRODUCTION_ENDPOINT_ENV: custom_prod_ep,
            },
        )


def test_staging_with_production_ack_fails_closed():
    """Attempting staging migration with a production acknowledgement fails closed."""
    valid_staging_url = f"postgresql+psycopg://neondb_owner:secret@{VALID_STAGING_ENDPOINT}.neon.tech/neondb"
    with pytest.raises(env_mod.MigrationTargetError, match="does not match target endpoint ID"):
        env_mod.validate_target_url(
            valid_staging_url,
            {
                env_mod.ALLOW_STAGING_ENV: "1",
                env_mod.STAGING_ACK_ENV: VALID_PROD_ENDPOINT,
            },
        )


def test_guard_owned_transaction_cleaned_up_on_success():
    """Guard-owned transaction (not in transaction initially) is cleanly rolled back on success."""
    conn_guard = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", VALID_STAGING_ENDPOINT, already_in_transaction=False
    )
    env_mod._assert_server_identity(conn_guard, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_guard.rollbacks == 1
    assert conn_guard.in_transaction() is False


def test_guard_owned_transaction_cleaned_up_on_failure():
    """Guard-owned transaction is cleanly rolled back on validation failure."""
    conn_guard = _FakeNeonConnection(
        "neondb", "neondb_owner", "203.0.113.5", "ep-unexpected-rogue-endpoint", already_in_transaction=False
    )
    with pytest.raises(env_mod.MigrationTargetError):
        env_mod._assert_server_identity(conn_guard, make_url(VALID_STAGING_URL), require_loopback=False)
    assert conn_guard.rollbacks == 1
    assert conn_guard.in_transaction() is False


def test_caller_transaction_survives_loopback_validation():
    """Caller-owned transaction on local loopback target survives validation without rollback."""
    conn_loopback = _FakeConnection("verifygrid_test", "verifygrid_test_app", "127.0.0.1", already_in_transaction=True)
    env_mod._assert_server_identity(conn_loopback, make_url(LOOPBACK_TEST_URL), require_loopback=True)
    assert conn_loopback.rollbacks == 0
    assert conn_loopback.in_transaction() is True
    assert conn_loopback.caller_work_intact is True



def test_redirect_query_parameters_are_rejected():
    with pytest.raises(env_mod.MigrationTargetError, match="redirect"):
        env_mod.validate_target_url(LOOPBACK_TEST_URL + "?host=db.example.com", {})


def test_test_connection_rejects_non_loopback_host():
    with pytest.raises(env_mod.MigrationTargetError, match="loopback"):
        env_mod.validate_test_connection_url(
            make_url("postgresql+psycopg://verifygrid_test_app@db.example.com/verifygrid_test")
        )


def test_test_connection_rejects_application_database_name():
    with pytest.raises(env_mod.MigrationTargetError, match="test database name"):
        env_mod.validate_test_connection_url(
            make_url("postgresql+psycopg://verifygrid_test_app@127.0.0.1:55432/verifygrid")
        )


def test_test_connection_rejects_non_test_role():
    with pytest.raises(env_mod.MigrationTargetError, match="test login role"):
        env_mod.validate_test_connection_url(
            make_url("postgresql+psycopg://verifygrid_app@127.0.0.1:55432/verifygrid_test")
        )


def test_loopback_test_connection_is_accepted():
    env_mod.validate_test_connection_url(make_url(LOOPBACK_TEST_URL))


def test_identity_database_mismatch_is_rejected():
    connection = _FakeConnection("other_database", "verifygrid_test_app", "127.0.0.1")
    with pytest.raises(env_mod.MigrationTargetError, match="database"):
        env_mod._assert_server_identity(
            connection,
            make_url(LOOPBACK_TEST_URL),
            require_loopback=True,
        )


def test_identity_role_mismatch_is_rejected():
    connection = _FakeConnection("verifygrid_test", "other_role", "127.0.0.1")
    with pytest.raises(env_mod.MigrationTargetError, match="role"):
        env_mod._assert_server_identity(
            connection,
            make_url(LOOPBACK_TEST_URL),
            require_loopback=True,
        )


def test_identity_missing_server_address_is_rejected():
    connection = _FakeConnection("verifygrid_test", "verifygrid_test_app", None)
    with pytest.raises(env_mod.MigrationTargetError, match="TCP address"):
        env_mod._assert_server_identity(
            connection,
            make_url(LOOPBACK_TEST_URL),
            require_loopback=True,
        )


def test_identity_remote_address_is_rejected_in_test_mode():
    connection = _FakeConnection("verifygrid_test", "verifygrid_test_app", "203.0.113.10")
    with pytest.raises(env_mod.MigrationTargetError, match="not loopback"):
        env_mod._assert_server_identity(
            connection,
            make_url(LOOPBACK_TEST_URL),
            require_loopback=True,
        )


def test_identity_loopback_match_is_accepted_and_transaction_ended():
    connection = _FakeConnection("verifygrid_test", "verifygrid_test_app", "127.0.0.1")
    env_mod._assert_server_identity(
        connection,
        make_url(LOOPBACK_TEST_URL),
        require_loopback=True,
    )
    assert connection.rollbacks == 1


def test_non_loopback_target_reaching_loopback_server_is_ambiguous():
    connection = _FakeConnection("verifygrid", "verifygrid_app", "127.0.0.1")
    with pytest.raises(env_mod.MigrationTargetError, match="ambiguous"):
        env_mod._assert_server_identity(
            connection,
            make_url(REMOTE_URL),
            require_loopback=False,
        )


def test_cli_missing_target_fails_before_connecting():
    result = _run_alembic("current", overrides={"DATABASE_URL": REMOTE_URL})
    output = _combined(result)
    assert result.returncode != 0
    assert "explicit migration target is required" in output
    assert "could not connect" not in output.lower()


def test_cli_integration_mode_without_connection_fails():
    result = _run_alembic(
        "current",
        overrides={env_mod.INTEGRATION_ENV: "1"},
    )
    output = _combined(result)
    assert result.returncode != 0
    assert "integration mode requires an explicitly validated connection" in output


def test_cli_remote_target_is_rejected_without_acknowledgement():
    result = _run_alembic("-x", f"db_url={REMOTE_URL}", "current")
    output = _combined(result)
    assert result.returncode != 0
    assert "non-loopback migration target" in output


def test_heads_and_history_do_not_require_a_target():
    heads = _run_alembic("heads")
    assert heads.returncode == 0, _combined(heads)
    assert EXPECTED_HEAD in heads.stdout

    history = _run_alembic("history")
    assert history.returncode == 0, _combined(history)
    assert EXPECTED_HEAD in history.stdout
    assert "0005_verification_lineage" not in history.stdout


def test_canonical_graph_is_linear_with_one_head():
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [EXPECTED_HEAD]

    expected_parents = {
        "0001_initial_tables": None,
        "0002_verification_runs": "0001_initial_tables",
        "0003_user_password": "0002_verification_runs",
        "0004_enterprise_governance": "0003_user_password",
        "0005_verification_templates": "0004_enterprise_governance",
        "0006_discrepancy_review_decisions": "0005_verification_templates",
    }
    for revision, parent in expected_parents.items():
        assert script.get_revision(revision).down_revision == parent

    active_ids = {revision.revision for revision in script.walk_revisions()}
    assert active_ids == set(expected_parents)
    assert len(list(VERSIONS_DIR.glob("*.py"))) == 6


def test_retired_revisions_are_not_in_the_active_graph():
    active_text = "\n".join(
        path.read_text(encoding="utf-8") for path in VERSIONS_DIR.glob("*.py")
    )
    assert "0005_verification_lineage" not in active_text
    assert "0004_verification_templates" not in active_text

    retired = {path.name for path in (MIGRATIONS_DIR / "retired").glob("*.py")}
    assert retired == {"0004_verification_templates.py", "0005_verification_lineage.py"}


def test_recovered_governance_revision_hash_matches_provenance():
    assert hashlib.sha256(RECOVERED_GOVERNANCE.read_bytes()).hexdigest().upper() == (
        RECOVERED_GOVERNANCE_SHA256
    )


def test_template_generates_valid_revision_in_temp_copy(tmp_path: Path):
    import shutil

    target = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, target)

    before = {path.name for path in VERSIONS_DIR.glob("*.py")}

    config = Config()
    config.set_main_option("script_location", str(target))
    command.revision(
        config,
        message="batch25 template probe",
        rev_id="batch25_template_probe",
    )

    generated = [
        path
        for path in (target / "versions").glob("*.py")
        if path.name not in before
    ]
    assert len(generated) == 1, generated
    text = generated[0].read_text(encoding="utf-8")
    assert "revision: str = 'batch25_template_probe'" in text
    assert "down_revision: Union[str, Sequence[str], None] = '0006_discrepancy_review_decisions'" in text
    assert "def upgrade() -> None:" in text
    assert "def downgrade() -> None:" in text
    compile(text, str(generated[0]), "exec")

    after = {path.name for path in VERSIONS_DIR.glob("*.py")}
    assert after == before, "revision generation must not touch the repository graph"
