from __future__ import annotations

import asyncio
from typing import Any

from bullmq import Worker

from echo_worker.config import Settings
from echo_worker.db import Database
from echo_worker.jobs.summary import SummaryJob
from echo_worker.jobs.transcription import TranscriptionJob
from echo_worker.logging import get_logger
from echo_worker.providers.factory import build_summarizer, build_transcriber
from echo_worker.storage import Storage

logger = get_logger(__name__)


def _log_event(worker_name: str, event: str, *args: Any) -> None:
    job = args[0] if args else None
    job_id = getattr(job, "id", None)
    details = args[1:]

    if event == "failed":
        error = details[0] if details else None
        logger.error("%s worker: job %s failed: %s", worker_name, job_id, error)
        return

    if event == "error":
        logger.error("%s worker error: %s", worker_name, args[0] if args else "unknown")
        return

    logger.info("%s worker: job %s %s", worker_name, job_id, event)


class WorkerRuntime:
    """Owns the database pool, providers and the two BullMQ consumers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._database = Database(settings.database_url)
        self._storage = Storage(
            endpoint=settings.storage_endpoint,
            access_key=settings.storage_access_key,
            secret_key=settings.storage_secret_key,
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            use_ssl=settings.storage_use_ssl,
        )
        self._workers: list[Worker] = []
        self._stopped = False

    def _worker_options(self, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "connection": self._settings.redis_connection,
            "concurrency": self._settings.concurrency,
            "autorun": False,
        }

    def build_workers(self) -> list[Worker]:
        transcription_job = TranscriptionJob(
            database=self._database,
            storage=self._storage,
            transcriber=build_transcriber(self._settings),
            temp_dir=self._settings.temp_dir,
        )
        summary_job = SummaryJob(
            database=self._database,
            summarizer=build_summarizer(self._settings),
        )

        transcription_worker = Worker(
            self._settings.transcription_queue,
            transcription_job,
            self._worker_options("transcription"),
        )
        summary_worker = Worker(
            self._settings.summary_queue,
            summary_job,
            self._worker_options("summary"),
        )

        for worker in (transcription_worker, summary_worker):
            for event in ("completed", "failed", "error", "stalled"):
                worker.on(
                    event,
                    lambda *args, _event=event, _worker=worker: _log_event(
                        _worker.name, _event, *args
                    ),
                )

        self._workers = [transcription_worker, summary_worker]

        return self._workers

    async def run(self) -> None:
        workers = self.build_workers()

        logger.info(
            "Worker online (transcription=%s, summary=%s, whisper=%s, summary=%s)",
            self._settings.transcription_queue,
            self._settings.summary_queue,
            self._settings.whisper_mode,
            self._settings.summary_mode,
        )

        await asyncio.gather(*(worker.run() for worker in workers))

    async def stop(self) -> None:
        if self._stopped:
            return

        self._stopped = True

        logger.info("Shutting down worker...")

        await asyncio.gather(
            *(worker.close() for worker in self._workers),
            return_exceptions=True,
        )
        self._database.close()

        logger.info("Worker stopped")
