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

    def __init__(self, database: str, username: str, address):
        self._row = (database, username, address)
        self._in_transaction = False
        self.rollbacks = 0

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
        self.rollbacks += 1
        self._in_transaction = False


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


def test_remote_target_requires_both_guard_variables():
    with pytest.raises(env_mod.MigrationTargetError, match="non-loopback"):
        env_mod.validate_target_url(REMOTE_URL, {env_mod.ALLOW_REMOTE_ENV: "1"})
    with pytest.raises(env_mod.MigrationTargetError, match="non-loopback"):
        env_mod.validate_target_url(REMOTE_URL, {env_mod.ACK_ENV: "CHG-123"})

    url, loopback = env_mod.validate_target_url(
        REMOTE_URL,
        {env_mod.ALLOW_REMOTE_ENV: "1", env_mod.ACK_ENV: "CHG-123"},
    )
    assert loopback is False
    assert url.database == "verifygrid"


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
