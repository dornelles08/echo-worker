"""Inicialização do Sentry para o worker (Python)."""

from __future__ import annotations

import os

import sentry_sdk


def init_sentry() -> None:
    """Inicializa o Sentry apenas quando SENTRY_DSN_WORKER está definido."""
    dsn = os.getenv("SENTRY_DSN_WORKER", "")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("WORKER_ENV", "dev"),
        release=os.getenv("VITE_APP_VERSION"),
        traces_sample_rate=0.1 if os.getenv("WORKER_ENV") == "production" else 1.0,
        send_default_pii=False,
    )
