from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

from echo_worker.config import ConfigError, load_settings
from echo_worker.logging import get_logger, setup_logging
from echo_worker.sentry import init_sentry
from echo_worker.worker import WorkerRuntime

logger = get_logger(__name__)


async def _serve(runtime: WorkerRuntime) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    runner = asyncio.create_task(runtime.run())
    stopper = asyncio.create_task(stop_event.wait())

    try:
        done, _ = await asyncio.wait(
            {runner, stopper},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if runner in done:
            # The worker loop exited on its own (for example, a fatal error).
            await runner
            return
    finally:
        stopper.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await stopper

    await runtime.stop()

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(runner, timeout=30)


async def run() -> None:
    settings = load_settings()

    # Inicializa Sentry (apenas se SENTRY_DSN_WORKER estiver definido)
    init_sentry()

    # Logs em JSON quando LOKI_URL está definido (produção com Loki)
    use_json = bool(os.getenv("LOKI_URL"))
    setup_logging(
        "DEBUG" if not settings.is_production else "INFO",
        json_output=use_json,
    )

    runtime = WorkerRuntime(settings)

    try:
        await _serve(runtime)
    finally:
        await runtime.stop()


def main() -> None:
    try:
        asyncio.run(run())
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
