"""Alembic environment with explicit, fail-closed target selection.

A migration target is never read from application configuration,
``backend/.env``, or ``alembic.ini``. The only accepted targets are:

* a SQLAlchemy connection supplied by the caller through
  ``config.attributes["connection"]`` (the isolated test/programmatic path); or
* an explicit URL supplied with ``-x db_url=...`` or
  ``VERIFYGRID_MIGRATION_DATABASE_URL``.

The database, role, and server address are checked before any DDL. Loopback
targets are allowed by default. A non-loopback target additionally requires
both ``VERIFYGRID_ALLOW_PRODUCTION_MIGRATION=1`` and a non-empty
``VERIFYGRID_PRODUCTION_MIGRATION_ACK``. Those variables are guardrails, not
authorization; the human two-person production gate is still required.

Graph inspection and revision generation (``heads``, ``history``, and
``revision`` without ``--autogenerate``) do not execute this module, so they
work without a database target.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Mapping, Optional

from alembic import context
from sqlalchemy import create_engine, pool, text
from sqlalchemy.engine import Connection, URL, make_url

# Ensure backend root is on sys.path so the application metadata is importable.
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401  # registers every model on Base.metadata

# Model metadata for migration detection.
target_metadata = Base.metadata

INTEGRATION_ENV = "VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS"
MIGRATION_URL_ENV = "VERIFYGRID_MIGRATION_DATABASE_URL"

# Separate Staging Authorization Path
ALLOW_STAGING_ENV = "VERIFYGRID_ALLOW_STAGING_MIGRATION"
STAGING_ACK_ENV = "VERIFYGRID_STAGING_MIGRATION_ACK"
STAGING_ENDPOINT_ENV = "VERIFYGRID_STAGING_ENDPOINT_ID"

# Separate Production Authorization Path
ALLOW_PRODUCTION_ENV = "VERIFYGRID_ALLOW_PRODUCTION_MIGRATION"
PRODUCTION_ACK_ENV = "VERIFYGRID_PRODUCTION_MIGRATION_ACK"
PRODUCTION_ENDPOINT_ENV = "VERIFYGRID_PRODUCTION_ENDPOINT_ID"

# Backward-compatibility aliases
ALLOW_REMOTE_ENV = ALLOW_PRODUCTION_ENV
ACK_ENV = PRODUCTION_ACK_ENV

KNOWN_PRODUCTION_ENDPOINT = "ep-round-sea-b3b78mtc"
NEON_DATABASE_NAME = "neondb"
NEON_ROLE_NAME = "neondb_owner"

NEON_HOST_RE = re.compile(
    r"^ep-[a-z0-9-]+(?:\.c-[0-9]+)?(?:\.[a-z0-9-]+)?\.aws\.neon\.tech$|^ep-[a-z0-9-]+\.neon\.tech$",
    re.IGNORECASE,
)

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SYSTEM_DATABASES = frozenset({"postgres", "template0", "template1"})
TEST_DISALLOWED_DATABASES = frozenset(
    {"postgres", "template0", "template1", "verifygrid", "neondb"}
)
# Query parameters that can silently redirect a connection or select a
# different service definition. They are rejected even on loopback URLs.
REDIRECT_QUERY_KEYS = frozenset(
    {"host", "hostaddr", "port", "dbname", "database", "user", "service", "servicefile"}
)


def extract_endpoint_id(host: Optional[str]) -> Optional[str]:
    """Extract Neon endpoint identifier from hostname if starting with ep-."""
    if not host:
        return None
    cleaned = host.strip().strip("[]").lower()
    if "-pooler" in cleaned:
        return None
    first_part = cleaned.split(".")[0]
    return first_part if first_part.startswith("ep-") else None


class MigrationTargetError(RuntimeError):
    """Raised when no safe, explicit migration target can be established."""


def _environment(
    env: Optional[Mapping[str, str]] = None,
) -> Mapping[str, str]:
    return os.environ if env is None else env


def _enabled(name: str, env: Optional[Mapping[str, str]] = None) -> bool:
    value = (_environment(env).get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _host_is_loopback(host: str) -> bool:
    host = (host or "").strip().strip("[]").lower()
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolves_only_to_loopback(host: str, port: Optional[int]) -> bool:
    """Resolve a host and require every returned address to be loopback.

    This prevents a hosts-file entry from silently pointing a loopback name at
    a remote database. Resolution itself does not contact PostgreSQL.
    """
    try:
        infos = socket.getaddrinfo(host, port or 5432, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos if info[4]}
    return bool(addresses) and all(_host_is_loopback(address) for address in addresses)


def _parse_url(raw_url: Optional[str]) -> URL:
    if raw_url is None or not raw_url.strip():
        raise MigrationTargetError("An explicit migration target is required.")
    try:
        url = make_url(raw_url.strip())
    except Exception:
        raise MigrationTargetError(
            "The migration target is not a valid SQLAlchemy URL."
        ) from None

    if url.drivername != "postgresql+psycopg":
        raise MigrationTargetError(
            "The migration target must use the postgresql+psycopg driver."
        )

    host = (url.host or "").strip().strip("[]").lower()
    if not host:
        raise MigrationTargetError(
            "The migration target must specify an explicit host."
        )

    database = (url.database or "").strip()
    if not database:
        raise MigrationTargetError(
            "The migration target must specify a database name."
        )
    if database.lower() in SYSTEM_DATABASES:
        raise MigrationTargetError(
            "Refusing to migrate a PostgreSQL system database."
        )

    if not (url.username or "").strip():
        raise MigrationTargetError(
            "The migration target must specify an explicit login role."
        )

    query_keys = {str(key).lower() for key in (url.query or {})}
    redirected = sorted(query_keys & REDIRECT_QUERY_KEYS)
    if redirected:
        raise MigrationTargetError(
            "The migration target contains query parameter(s) that could redirect "
            "the connection: " + ", ".join(redirected) + "."
        )

    return url


def validate_target_url(
    raw_url: Optional[str],
    env: Optional[Mapping[str, str]] = None,
    x_args: Optional[Mapping[str, str]] = None,
) -> tuple[URL, bool]:
    """Validate an explicit CLI/offline URL with target-bound authorization.

    Returns ``(url, is_loopback)``.
    - Loopback hosts are permitted for local development and integration tests.
    - Staging targets require VERIFYGRID_ALLOW_STAGING_MIGRATION=1, valid Neon direct
      hostname, endpoint matching, and VERIFYGRID_STAGING_MIGRATION_ACK.
    - Production targets require VERIFYGRID_ALLOW_PRODUCTION_MIGRATION=1, exact
      production endpoint matching, and VERIFYGRID_PRODUCTION_MIGRATION_ACK.
    - Conflicting, ambiguous, pooled, or unacknowledged targets fail closed.
    """
    url = _parse_url(raw_url)
    host = (url.host or "").strip().strip("[]").lower()
    loopback = _host_is_loopback(host)

    if loopback:
        if not _resolves_only_to_loopback(host, url.port):
            raise MigrationTargetError(
                "The migration target host did not resolve exclusively to "
                "loopback addresses."
            )
        return url, True

    # Remote target authorization
    env_dict = _environment(env)
    x_dict = x_args or {}

    is_staging = (
        _enabled(ALLOW_STAGING_ENV, env_dict)
        or (x_dict.get("allow_staging") or "").strip().lower() in {"1", "true", "yes", "on"}
        or (x_dict.get("target") or "").strip().lower() == "staging"
    )

    is_production = (
        _enabled(ALLOW_PRODUCTION_ENV, env_dict)
        or (x_dict.get("allow_production") or "").strip().lower() in {"1", "true", "yes", "on"}
        or (x_dict.get("target") or "").strip().lower() == "production"
    )

    if is_staging and is_production:
        raise MigrationTargetError(
            "Conflicting authorization: both staging and production migrations are enabled. "
            "Specify exactly one target."
        )

    if not (is_staging or is_production):
        raise MigrationTargetError(
            "Refusing a non-loopback migration target. Remote migrations require explicit authorization: "
            f"set {ALLOW_STAGING_ENV}=1 for staging, or {ALLOW_PRODUCTION_ENV}=1 for production."
        )

    if "-pooler" in host:
        raise MigrationTargetError(
            f"Target host '{host}' is a pooled endpoint. "
            "Pooled endpoints cannot be used for schema migrations; use the direct compute endpoint instead."
        )

    if not NEON_HOST_RE.match(host):
        raise MigrationTargetError(
            f"Target host '{host}' does not match the permitted Neon direct hostname pattern "
            "(must start with 'ep-' and end with '.neon.tech')."
        )

    endpoint_id = host.split(".")[0].strip().lower()

    # Determine effective production endpoint (configured or default)
    configured_prod_endpoint = (
        (x_dict.get("production_endpoint_id") or x_dict.get("endpoint_id") or env_dict.get(PRODUCTION_ENDPOINT_ENV) or "")
    ).strip().lower()
    effective_prod_endpoint = configured_prod_endpoint or KNOWN_PRODUCTION_ENDPOINT

    if is_staging:
        disallowed_prod_endpoints = {KNOWN_PRODUCTION_ENDPOINT.lower(), effective_prod_endpoint}
        if endpoint_id in disallowed_prod_endpoints:
            prod_desc = (
                f"known production endpoint '{KNOWN_PRODUCTION_ENDPOINT}'"
                if endpoint_id == KNOWN_PRODUCTION_ENDPOINT.lower()
                else f"configured production endpoint '{endpoint_id}'"
            )
            raise MigrationTargetError(
                f"Refusing staging migration against {prod_desc}. "
                "Staging authorization cannot be used for production targets."
            )

        staging_ack = (
            (x_dict.get("staging_ack") or x_dict.get("ack") or env_dict.get(STAGING_ACK_ENV) or "")
        ).strip()
        if not staging_ack:
            raise MigrationTargetError(
                "Staging migration requires a target-bound acknowledgement. "
                f"Set {STAGING_ACK_ENV}=<staging-endpoint-id> or supply -x ack=<staging-endpoint-id>."
            )

        expected_staging_endpoint = (
            (x_dict.get("staging_endpoint_id") or x_dict.get("endpoint_id") or env_dict.get(STAGING_ENDPOINT_ENV) or "")
        ).strip().lower()
        if expected_staging_endpoint and expected_staging_endpoint in disallowed_prod_endpoints:
            raise MigrationTargetError(
                f"Conflicting configuration: expected staging endpoint '{expected_staging_endpoint}' "
                "matches a production endpoint."
            )
        if expected_staging_endpoint and expected_staging_endpoint != endpoint_id:
            raise MigrationTargetError(
                f"Target endpoint '{endpoint_id}' does not match expected staging endpoint '{expected_staging_endpoint}'."
            )

        if staging_ack.lower() != endpoint_id:
            raise MigrationTargetError(
                f"Staging acknowledgement '{staging_ack}' does not match target endpoint ID '{endpoint_id}'."
            )

        if staging_ack.lower() in disallowed_prod_endpoints:
            raise MigrationTargetError(
                f"Refusing staging migration with production acknowledgement '{staging_ack}'."
            )

        db_name = (url.database or "").strip().lower()
        user_name = (url.username or "").strip().lower()
        if db_name != NEON_DATABASE_NAME:
            raise MigrationTargetError(
                f"Invalid staging database name '{url.database}'; expected '{NEON_DATABASE_NAME}'."
            )
        if user_name != NEON_ROLE_NAME:
            raise MigrationTargetError(
                f"Invalid staging database role '{url.username}'; expected '{NEON_ROLE_NAME}'."
            )

    if is_production:
        expected_prod_endpoint = effective_prod_endpoint

        if endpoint_id != expected_prod_endpoint:
            raise MigrationTargetError(
                f"Production migration target endpoint '{endpoint_id}' does not match "
                f"expected production endpoint '{expected_prod_endpoint}'."
            )

        prod_ack = (
            (x_dict.get("production_ack") or x_dict.get("ack") or env_dict.get(PRODUCTION_ACK_ENV) or "")
        ).strip()
        if not prod_ack:
            raise MigrationTargetError(
                "Production migration requires an explicit target-bound acknowledgement. "
                f"Set {PRODUCTION_ACK_ENV}=<production-endpoint-id> or supply -x ack=<production-endpoint-id>."
            )

        valid_acks = {expected_prod_endpoint, f"confirm-production-{expected_prod_endpoint}"}
        if prod_ack.lower() not in valid_acks:
            raise MigrationTargetError(
                f"Production acknowledgement '{prod_ack}' does not match required endpoint confirmation "
                f"('{expected_prod_endpoint}' or 'CONFIRM-PRODUCTION-{expected_prod_endpoint}')."
            )

        db_name = (url.database or "").strip().lower()
        user_name = (url.username or "").strip().lower()
        if db_name != NEON_DATABASE_NAME:
            raise MigrationTargetError(
                f"Invalid production database name '{url.database}'; expected '{NEON_DATABASE_NAME}'."
            )
        if user_name != NEON_ROLE_NAME:
            raise MigrationTargetError(
                f"Invalid production database role '{url.username}'; expected '{NEON_ROLE_NAME}'."
            )

    return url, False


def validate_test_connection_url(url: URL) -> None:
    """Validate the URL behind an explicitly supplied isolated test connection.

    This is stricter than the CLI policy: the database and role must be named
    for testing, and the server must be loopback.
    """
    if url.drivername != "postgresql+psycopg":
        raise MigrationTargetError(
            "The isolated test connection must use the postgresql+psycopg driver."
        )

    host = (url.host or "").strip().strip("[]").lower()
    if not _host_is_loopback(host):
        raise MigrationTargetError(
            "The isolated test connection must use a loopback host."
        )
    if not _resolves_only_to_loopback(host, url.port):
        raise MigrationTargetError(
            "The isolated test host did not resolve exclusively to loopback addresses."
        )

    database = (url.database or "").strip()
    username = (url.username or "").strip()
    if database.lower() in TEST_DISALLOWED_DATABASES or "test" not in database.lower():
        raise MigrationTargetError(
            "The isolated test target must use a dedicated test database name "
            "(for example, a name containing 'test')."
        )
    if "test" not in username.lower():
        raise MigrationTargetError(
            "The isolated test target must use a dedicated test login role "
            "(for example, a role containing 'test')."
        )

    query_keys = {str(key).lower() for key in (url.query or {})}
    redirected = sorted(query_keys & REDIRECT_QUERY_KEYS)
    if redirected:
        raise MigrationTargetError(
            "The isolated test URL contains query parameter(s) that could redirect "
            "the connection: " + ", ".join(redirected) + "."
        )


def select_explicit_url(
    x_args: Optional[Mapping[str, str]],
    env: Optional[Mapping[str, str]] = None,
) -> tuple[URL, bool]:
    """Resolve the explicit CLI/offline target, or fail closed."""
    raw_url = (
        ((x_args or {}).get("db_url") or "")
        or ((_environment(env).get(MIGRATION_URL_ENV)) or "")
    ).strip()
    if not raw_url:
        raise MigrationTargetError(
            "An explicit migration target is required. Supply "
            "-x db_url=<url> or "
            f"{MIGRATION_URL_ENV}. Application configuration and .env are never "
            "used as a migration target."
        )
    return validate_target_url(raw_url, env, x_args=x_args)


def _assert_server_identity(
    connection: Connection,
    url: URL,
    *,
    require_loopback: bool,
) -> None:
    """Check the live database, role, and server address before DDL."""
    already_in_transaction = connection.in_transaction()
    identity_check_failed = False
    try:
        row = connection.execute(
            text("SELECT current_database(), current_user, inet_server_addr()")
        ).one()
        database, username, server_address = row[0], row[1], row[2]

        if database != (url.database or "").strip():
            raise MigrationTargetError(
                "The connected database does not match the validated migration target."
            )
        if username != (url.username or "").strip():
            raise MigrationTargetError(
                "The connected role does not match the validated migration target."
            )

        if server_address is None:
            raise MigrationTargetError(
                "The server did not report a TCP address; refusing to migrate an "
                "unverifiable target."
            )

        address = str(server_address).strip()
        try:
            address_is_loopback = ipaddress.ip_address(address).is_loopback
        except ValueError:
            raise MigrationTargetError(
                "The server reported an unrecognized address; refusing to migrate."
            ) from None

        if require_loopback and not address_is_loopback:
            raise MigrationTargetError(
                "The connected server address is not loopback; refusing an isolated "
                "test migration."
            )
        if not require_loopback and address_is_loopback:
            raise MigrationTargetError(
                "The migration target is non-loopback but the server reported a "
                "loopback address; refusing an ambiguous target."
            )

        # Post-connection Neon endpoint identity verification
        if not require_loopback:
            endpoint_id = extract_endpoint_id(url.host)
            if not endpoint_id:
                raise MigrationTargetError(
                    f"Cannot determine expected Neon endpoint ID from target host '{url.host}'."
                )

            try:
                res = connection.execute(text("SELECT current_setting('neon.endpoint_id', true)"))
                neon_endpoint = None
                if hasattr(res, "scalar_one_or_none"):
                    neon_endpoint = res.scalar_one_or_none()
                elif hasattr(res, "one"):
                    r = res.one()
                    neon_endpoint = r[0] if isinstance(r, (tuple, list)) else r
            except MigrationTargetError:
                raise
            except Exception as err:
                raise MigrationTargetError(
                    f"Failed to query server setting 'neon.endpoint_id': {err}"
                ) from err

            if neon_endpoint is None or not str(neon_endpoint).strip():
                raise MigrationTargetError(
                    "The server did not report a 'neon.endpoint_id' setting; "
                    "refusing to migrate an unverifiable Neon target."
                )

            ep_str = str(neon_endpoint).strip().lower()
            if not ep_str.startswith("ep-"):
                raise MigrationTargetError(
                    f"Server reported malformed Neon endpoint ID '{neon_endpoint}'; expected ID starting with 'ep-'."
                )

            if ep_str != endpoint_id.lower():
                raise MigrationTargetError(
                    f"Connected Neon endpoint '{neon_endpoint}' does not match "
                    f"expected target endpoint '{endpoint_id}'."
                )
    except Exception:
        identity_check_failed = True
        raise
    finally:
        if not already_in_transaction and connection.in_transaction():
            # End the read-only identity transaction so Alembic can own the DDL
            # transaction. A caller-supplied transaction is left untouched.
            try:
                connection.rollback()
            except Exception:
                # If an exception is already in flight from the identity check,
                # do not let a cleanup/rollback error suppress or conceal it.
                if not identity_check_failed:
                    raise


def _validate_programmatic_url(url: URL) -> bool:
    """Apply the explicit target policy to a caller-supplied connection URL."""
    validated, loopback = validate_target_url(
        url.render_as_string(hide_password=False)
    )
    return loopback


def _run(config) -> None:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    offline = context.is_offline_mode()
    if offline:
        x_args = context.get_x_argument(as_dictionary=True)
        url, _ = select_explicit_url(x_args)
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    provided_connection = config.attributes.get("connection")
    integration_mode = _enabled(INTEGRATION_ENV)

    if provided_connection is not None:
        engine = getattr(provided_connection, "engine", None)
        url = getattr(engine, "url", None)
        if url is None:
            raise MigrationTargetError(
                "The supplied connection has no engine URL; cannot validate the "
                "migration target."
            )

        if integration_mode:
            validate_test_connection_url(url)
            require_loopback = True
        else:
            require_loopback = _validate_programmatic_url(url)

        _assert_server_identity(
            provided_connection,
            url,
            require_loopback=require_loopback,
        )
        context.configure(
            connection=provided_connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    if integration_mode:
        raise MigrationTargetError(
            "PostgreSQL integration mode requires an explicitly validated "
            "connection in config.attributes['connection']; no URL fallback is "
            "permitted."
        )

    x_args = context.get_x_argument(as_dictionary=True)
    url, loopback = select_explicit_url(x_args)

    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            _assert_server_identity(
                connection,
                url,
                require_loopback=loopback,
            )
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


def _active_config():
    """Return the Alembic config when executing under Alembic, else ``None``.

    Importing this module outside an Alembic run (for unit tests or static
    inspection) must not execute migrations or require a target.
    """
    try:
        return context.config
    except Exception:
        return None


_runtime_config = _active_config()
if _runtime_config is not None:
    _run(_runtime_config)
