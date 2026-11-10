from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Any

from echo_worker.db import Database
from echo_worker.logging import get_logger
from echo_worker.providers.base import Transcriber
from echo_worker.storage import Storage, build_destination

logger = get_logger(__name__)

# Statuses that mean the transcription step already produced a result.
TRANSCRIBED_STATUSES = {
    "transcribed",
    "pending_summary",
    "processing_summary",
    "summarized",
}


class TranscriptionJob:
    def __init__(
        self,
        database: Database,
        storage: Storage,
        transcriber: Transcriber,
        temp_dir: str = "/tmp/echo-worker",
    ) -> None:
        self._database = database
        self._storage = storage
        self._transcriber = transcriber
        self._temp_dir = temp_dir

    async def __call__(self, job: Any, token: str | None = None) -> dict[str, Any]:
        _ = token

        return await asyncio.to_thread(self.process, job.data)

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        media_id = str(data.get("mediaId") or "")
        trace_id = str(data.get("traceId") or "")

        if not media_id:
            raise ValueError("Transcription job is missing 'mediaId'")

        extra: dict[str, Any] = {"mediaId": media_id}
        if trace_id:
            extra["traceId"] = trace_id

        media = self._database.get_media(media_id)

        if media.transcription and media.status in TRANSCRIBED_STATUSES:
            minutes = self._database.debit_usage(media_id)

            logger.info(
                "Transcription already done for media %s, skipping",
                media_id,
                extra=extra,
            )

            return {
                "mediaId": media_id,
                "status": "skipped",
                "minutesDebited": minutes,
            }

        start_time = time.time()
        self._database.mark_processing_transcription(media_id)

        logger.info(
            "Transcription started for media %s",
            media_id,
            extra=extra,
        )

        try:
            Path(self._temp_dir).mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(dir=self._temp_dir) as temp_directory:
                destination = build_destination(Path(temp_directory), media)
                audio_path = self._storage.download(media, destination)

                download_duration = time.time() - start_time
                logger.info(
                    "Media downloaded for media %s in %.2fs",
                    media_id,
                    download_duration,
                    extra=extra,
                )

                transcribe_start = time.time()
                result = self._transcriber.transcribe(
                    audio_path,
                    language=media.language,
                    prompt=media.prompt,
                )
                transcribe_duration = time.time() - transcribe_start

                logger.info(
                    "Transcription processed for media %s in %.2fs (%s segments)",
                    media_id,
                    transcribe_duration,
                    len(result.segments),
                    extra=extra,
                )
        except Exception:
            total_duration = time.time() - start_time
            logger.exception(
                "Transcription failed for media %s after %.2fs",
                media_id,
                total_duration,
                extra=extra,
            )
            self._database.mark_failed_transcription(media_id)
            raise

        self._database.mark_transcribed(
            media_id,
            result.text,
            result.language,
            result.segments,
        )

        # Debit is idempotent (`usage_debited_at`), so a retry after a debit
        # failure can safely run again.
        minutes = self._database.debit_usage(media_id)

        total_duration = time.time() - start_time

        logger.info(
            "Transcription finished for media %s (%s segments, %s minutes) in %.2fs",
            media_id,
            len(result.segments),
            minutes,
            total_duration,
            extra=extra,
        )

        return {
            "mediaId": media_id,
            "status": "transcribed",
            "language": result.language,
            "segments": len(result.segments),
            "minutesDebited": minutes,
        }
