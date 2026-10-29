"""Unit tests for the PostgreSQL test-target safety guard (no connections)."""

from __future__ import annotations

import pytest

from tests.pg_test_target import (
    safe_schema_name,
    validate_test_database_url,
)

VALID = "postgresql+psycopg://verifygrid_test_app@127.0.0.1:55432/verifygrid_test"
REMOTE = "postgresql+psycopg://verifygrid_test_app@db.example.com:5432/verifygrid_test"


def _messages(check) -> str:
    return " ".join(check.errors)


def test_missing_test_url_fails_closed():
    check = validate_test_database_url(None)
    assert check.ok is False
    assert "required" in _messages(check)
    assert "never used as a fallback" in _messages(check)


def test_non_postgres_url_is_rejected():
    check = validate_test_database_url("sqlite:///verifygrid_test.db")
    assert check.ok is False
    assert "postgresql+psycopg" in _messages(check)


def test_remote_host_is_rejected_without_dns_or_connection():
    check = validate_test_database_url(REMOTE)
    assert check.ok is False
    assert "loopback" in _messages(check)
    assert check.url is None


def test_development_database_name_is_rejected():
    check = validate_test_database_url(
        "postgresql+psycopg://verifygrid_test_app@127.0.0.1:5432/verifygrid"
    )
    assert check.ok is False
    assert "dedicated" in _messages(check)


def test_database_name_must_look_like_a_test_database():
    check = validate_test_database_url(
        "postgresql+psycopg://verifygrid_test_app@127.0.0.1:5432/verifygrid_scratch"
    )
    assert check.ok is False
    assert "test database" in _messages(check)


def test_role_must_look_like_a_test_role():
    check = validate_test_database_url(
        "postgresql+psycopg://verifygrid_user@127.0.0.1:5432/verifygrid_test"
    )
    assert check.ok is False
    assert "test role" in _messages(check)


def test_redirect_query_parameters_are_rejected():
    check = validate_test_database_url(VALID + "?host=db.example.com")
    assert check.ok is False
    assert "redirect" in _messages(check)


def test_application_database_target_is_rejected():
    check = validate_test_database_url(VALID, application_url=VALID)
    assert check.ok is False
    assert "identical to the application" in _messages(check)


def test_application_database_name_is_rejected_even_on_another_host():
    check = validate_test_database_url(
        VALID,
        application_url="postgresql+psycopg://someone@localhost:5432/verifygrid_test",
    )
    assert check.ok is False
    assert "matches the application database name" in _messages(check)


def test_valid_loopback_test_target_is_accepted():
    check = validate_test_database_url(VALID)
    assert check.ok is True
    assert check.errors == ()
    assert check.database == "verifygrid_test"
    assert check.username == "verifygrid_test_app"
    assert check.url is not None


def test_schema_identifier_validation():
    assert safe_schema_name("verifygrid_it_abc123") == "verifygrid_it_abc123"
    with pytest.raises(ValueError):
        safe_schema_name('public"; DROP SCHEMA public CASCADE; --')
