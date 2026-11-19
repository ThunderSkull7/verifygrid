from pydantic import ValidationError
import pytest

from app.core.config import DEFAULT_INSECURE_SECRET_KEY, Settings


def test_production_rejects_default_jwt_secret_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            verifygrid_env="production",
            secret_key=DEFAULT_INSECURE_SECRET_KEY,
        )

    message = str(error.value)
    assert "SECRET_KEY must be set" in message
    assert DEFAULT_INSECURE_SECRET_KEY not in message


def test_production_accepts_explicit_jwt_secret() -> None:
    settings = Settings(
        _env_file=None,
        verifygrid_env="production",
        secret_key="a-unique-production-secret-value",
    )

    assert settings.verifygrid_env == "production"
    assert settings.debug is False


def test_debug_defaults_off() -> None:
    settings = Settings(_env_file=None, verifygrid_env="development")

    assert settings.debug is False
