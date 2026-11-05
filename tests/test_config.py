from __future__ import annotations

import pytest

from echo_worker.config import ConfigError, load_settings


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/echo_test")
    monkeypatch.setenv("WHISPER_MODE", "fake")
    monkeypatch.setenv("SUMMARY_MODE", "fake")
    monkeypatch.delenv("WORKER_ENV", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.delenv("REDIS_DB", raising=False)
    monkeypatch.delenv("WORKER_CONCURRENCY", raising=False)


def test_load_settings_defaults() -> None:
    settings = load_settings()

    assert settings.env == "dev"
    assert settings.is_production is False
    assert settings.concurrency == 2
    assert settings.transcription_queue == "media_transcription_queue"
    assert settings.summary_queue == "media_summary_queue"
    assert settings.whisper_mode == "fake"
    assert settings.summary_mode == "fake"
    assert settings.redis_connection == {"host": "localhost", "port": 6379, "db": 0}


def test_redis_connection_includes_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_PASSWORD", "secret")

    settings = load_settings()

    assert settings.redis_connection["password"] == "secret"


def test_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_settings()


def test_rejects_unknown_whisper_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_MODE", "magic")

    with pytest.raises(ConfigError, match="WHISPER_MODE"):
        load_settings()


def test_rejects_fake_providers_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_ENV", "production")

    with pytest.raises(ConfigError, match="not allowed in production"):
        load_settings()


def test_openai_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_MODE", "openai")
    monkeypatch.setenv("SUMMARY_MODE", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_settings()


def test_rejects_non_integer_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_CONCURRENCY", "many")

    with pytest.raises(ConfigError, match="WORKER_CONCURRENCY"):
        load_settings()
