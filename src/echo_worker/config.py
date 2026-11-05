from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

VALID_WHISPER_MODES = {"local", "openai", "fake"}
VALID_SUMMARY_MODES = {"openai", "fake"}


class ConfigError(RuntimeError):
    """Raised when the environment configuration is invalid."""


def _get(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)

    if value is None:
        raise ConfigError(f"Missing required environment variable: {name}")

    return value


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or raw == "":
        return default

    try:
        return int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer") from error


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None or raw == "":
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str
    concurrency: int

    database_url: str

    redis_host: str
    redis_port: int
    redis_password: str | None
    redis_db: int
    transcription_queue: str
    summary_queue: str

    whisper_mode: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str

    summary_mode: str
    openai_api_key: str
    openai_base_url: str
    openai_whisper_model: str
    openai_model: str

    storage_endpoint: str
    storage_access_key: str
    storage_secret_key: str
    storage_bucket: str
    storage_region: str
    storage_use_ssl: bool

    temp_dir: str

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def redis_connection(self) -> dict[str, object]:
        connection: dict[str, object] = {
            "host": self.redis_host,
            "port": self.redis_port,
            "db": self.redis_db,
        }

        if self.redis_password:
            connection["password"] = self.redis_password

        return connection


def load_settings() -> Settings:
    env = _get("WORKER_ENV", "dev")

    whisper_mode = _get("WHISPER_MODE", "local")
    summary_mode = _get("SUMMARY_MODE", "openai")

    if whisper_mode not in VALID_WHISPER_MODES:
        raise ConfigError(f"WHISPER_MODE must be one of {sorted(VALID_WHISPER_MODES)}")

    if summary_mode not in VALID_SUMMARY_MODES:
        raise ConfigError(f"SUMMARY_MODE must be one of {sorted(VALID_SUMMARY_MODES)}")

    if env == "production" and whisper_mode == "fake":
        raise ConfigError("WHISPER_MODE=fake is not allowed in production")

    if env == "production" and summary_mode == "fake":
        raise ConfigError("SUMMARY_MODE=fake is not allowed in production")

    settings = Settings(
        env=env,
        concurrency=_get_int("WORKER_CONCURRENCY", 2),
        database_url=_get("DATABASE_URL"),
        redis_host=_get("REDIS_HOST", "localhost"),
        redis_port=_get_int("REDIS_PORT", 6379),
        redis_password=os.getenv("REDIS_PASSWORD") or None,
        redis_db=_get_int("REDIS_DB", 0),
        transcription_queue=_get("TRANSCRIPTION_QUEUE", "media_transcription_queue"),
        summary_queue=_get("SUMMARY_QUEUE", "media_summary_queue"),
        whisper_mode=whisper_mode,
        whisper_model=_get("WHISPER_MODEL", "small"),
        whisper_device=_get("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=_get("WHISPER_COMPUTE_TYPE", "int8"),
        summary_mode=summary_mode,
        openai_api_key=_get("OPENAI_API_KEY", ""),
        openai_base_url=_get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_whisper_model=_get("OPENAI_WHISPER_MODEL", "whisper-1"),
        openai_model=_get("OPENAI_MODEL", "gpt-4o-mini"),
        storage_endpoint=_get("STORAGE_ENDPOINT", "http://localhost:9000"),
        storage_access_key=_get("STORAGE_ACCESS_KEY", "minioadmin"),
        storage_secret_key=_get("STORAGE_SECRET_KEY", "minioadmin"),
        storage_bucket=_get("STORAGE_BUCKET", "echo_dev"),
        storage_region=_get("STORAGE_REGION", "us-east-1"),
        storage_use_ssl=_get_bool("STORAGE_USE_SSL", False),
        temp_dir=_get("TEMP_DIR", "/tmp/echo-worker"),
    )

    if settings.whisper_mode == "openai" and not settings.openai_api_key:
        raise ConfigError("OPENAI_API_KEY is required when WHISPER_MODE=openai")

    if settings.summary_mode == "openai" and not settings.openai_api_key:
        raise ConfigError("OPENAI_API_KEY is required when SUMMARY_MODE=openai")

    return settings
