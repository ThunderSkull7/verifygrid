"""Fail-closed target validation for isolated PostgreSQL integration tests.

This module is deliberately dependency-light and must never open a database
connection. It validates an *explicitly supplied* test-database URL before any
engine is created, so a normal ``pytest tests`` run cannot fall back to the
application's configured database (which may be remote).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.engine import URL, make_url

POSTGRES_INTEGRATION_ENV = "VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS"
TEST_DATABASE_URL_ENV = "VERIFYGRID_TEST_DATABASE_URL"

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DISALLOWED_DATABASES = frozenset(
    {"postgres", "template0", "template1", "verifygrid", "neondb"}
)
# Query parameters that can silently redirect a connection or select a
# different service definition. Deliberately rejected even on loopback URLs.
REDIRECT_QUERY_KEYS = frozenset(
    {"host", "hostaddr", "port", "dbname", "database", "user", "service", "servicefile"}
)
TEST_NAME_RE = re.compile(r"test", re.IGNORECASE)
SAFE_SCHEMA_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class TargetCheck:
    """Result of validating a proposed PostgreSQL test target.

    ``url`` is only populated when all checks pass. Error messages never contain
    the URL, password, or query string.
    """

    ok: bool
    errors: tuple[str, ...]
    # Never render credentials/host details in pytest failure output.
    url: Optional[URL] = field(default=None, repr=False)
    database: Optional[str] = None
    username: Optional[str] = None


def integration_tests_enabled() -> bool:
    """True only when the operator explicitly opts in."""
    return os.getenv(POSTGRES_INTEGRATION_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _is_loopback_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _host_resolves_only_to_loopback(host: str, port: Optional[int]) -> bool:
    """Resolve the host and require every returned address to be loopback.

    This prevents ``localhost`` (or a hostile hosts-file entry) from silently
    pointing at a remote database. Resolution itself does not contact PostgreSQL.
    """
    try:
        infos = socket.getaddrinfo(host, port or 5432, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos if info[4]}
    return bool(addresses) and all(_is_loopback_address(addr) for addr in addresses)


def _named_for_test(value: Optional[str]) -> bool:
    return bool(value) and bool(TEST_NAME_RE.search(value))


def validate_test_database_url(
    raw_url: Optional[str],
    application_url: Optional[str] = None,
) -> TargetCheck:
    """Validate an explicitly supplied URL for an isolated PostgreSQL test DB.

    Rejects missing, non-PostgreSQL, non-loopback, ambiguously named, and
    application-database targets. No connection is opened.
    """
    errors: list[str] = []
    if raw_url is None or not raw_url.strip():
        return TargetCheck(
            ok=False,
            errors=(
                f"{TEST_DATABASE_URL_ENV} is required for PostgreSQL integration tests; "
                "the application DATABASE_URL is never used as a fallback.",
            ),
        )

    try:
        url = make_url(raw_url.strip())
    except Exception:
        return TargetCheck(
            ok=False,
            errors=("The test database URL is not a valid SQLAlchemy URL.",),
        )

    if url.drivername != "postgresql+psycopg":
        errors.append("The test database URL must use the postgresql+psycopg driver.")

    host = (url.host or "").strip().strip("[]").lower()
    if not host:
        errors.append("The test database URL must specify an explicit host.")
    elif host not in LOOPBACK_HOSTS:
        errors.append(
            "The test database host must be loopback (localhost, 127.0.0.1, or ::1)."
        )
    elif not _host_resolves_only_to_loopback(host, url.port):
        errors.append(
            "The test database host did not resolve exclusively to loopback addresses."
        )

    database = (url.database or "").strip()
    if not database:
        errors.append("The test database URL must specify a database name.")
    elif database.lower() in DISALLOWED_DATABASES:
        errors.append(
            "The test database name must be dedicated to testing and must not be "
            "the application/development database."
        )
    elif not _named_for_test(database):
        errors.append(
            "The test database name must clearly identify it as a test database "
            "(for example, a name containing 'test')."
        )

    username = (url.username or "").strip()
    if not username:
        errors.append("The test database URL must specify a dedicated login role.")
    elif not _named_for_test(username):
        errors.append(
            "The test database role must clearly identify it as a test role "
            "(for example, a name containing 'test')."
        )

    query_keys = {str(key).lower() for key in (url.query or {})}
    redirected = sorted(query_keys & REDIRECT_QUERY_KEYS)
    if redirected:
        errors.append(
            "The test database URL contains query parameter(s) that could redirect "
            f"the connection: {', '.join(redirected)}."
        )

    if application_url:
        try:
            app_url = make_url(application_url)
        except Exception:
            app_url = None
        if app_url is not None:
            if app_url.host and host and (app_url.host or "").strip().strip("[]").lower() == host:
                same_endpoint = (
                    (app_url.port or 5432) == (url.port or 5432)
                    and (app_url.database or "").strip().lower() == database.lower()
                    and (app_url.username or "").strip().lower() == username.lower()
                )
                if same_endpoint:
                    errors.append(
                        "The test database target is identical to the application "
                        "database target; refusing to reuse it."
                    )
            if (app_url.database or "").strip().lower() == database.lower():
                errors.append(
                    "The test database name matches the application database name; "
                    "refusing an ambiguous target."
                )

    if errors:
        return TargetCheck(ok=False, errors=tuple(errors))
    return TargetCheck(ok=True, errors=(), url=url, database=database, username=username)


def safe_schema_name(raw: str) -> str:
    """Validate a generated per-session schema identifier."""
    if not SAFE_SCHEMA_RE.fullmatch(raw):
        raise ValueError("Unsafe PostgreSQL schema identifier.")
    return raw
