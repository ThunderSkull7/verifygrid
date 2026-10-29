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
ALLOW_REMOTE_ENV = "VERIFYGRID_ALLOW_PRODUCTION_MIGRATION"
ACK_ENV = "VERIFYGRID_PRODUCTION_MIGRATION_ACK"

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
) -> tuple[URL, bool]:
    """Validate an explicit CLI/offline URL.

    Returns ``(url, is_loopback)``. A non-loopback URL is rejected unless both
    production guard variables are present.
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
    else:
        allowed = _enabled(ALLOW_REMOTE_ENV, env)
        acknowledgement = ((_environment(env).get(ACK_ENV)) or "").strip()
        if not (allowed and acknowledgement):
            raise MigrationTargetError(
                "Refusing a non-loopback migration target. Set both "
                f"{ALLOW_REMOTE_ENV}=1 and {ACK_ENV}=<change-ticket-id> only for "
                "an authorized production migration."
            )

    return url, loopback


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
    return validate_target_url(raw_url, env)


def _assert_server_identity(
    connection: Connection,
    url: URL,
    *,
    require_loopback: bool,
) -> None:
    """Check the live database, role, and server address before DDL."""
    already_in_transaction = connection.in_transaction()
    row = connection.execute(
        text("SELECT current_database(), current_user, inet_server_addr()")
    ).one()
    database, username, server_address = row[0], row[1], row[2]

    if not already_in_transaction and connection.in_transaction():
        # End the read-only identity transaction so Alembic can own the DDL
        # transaction. A caller-supplied transaction is left untouched.
        connection.rollback()

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
