from __future__ import annotations

import asyncio
import tempfile
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

        if not media_id:
            raise ValueError("Transcription job is missing 'mediaId'")

        media = self._database.get_media(media_id)

        if media.transcription and media.status in TRANSCRIBED_STATUSES:
            minutes = self._database.debit_usage(media_id)

            logger.info("Transcription already done for media %s, skipping", media_id)

            return {
                "mediaId": media_id,
                "status": "skipped",
                "minutesDebited": minutes,
            }

        self._database.mark_processing_transcription(media_id)

        try:
            Path(self._temp_dir).mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(dir=self._temp_dir) as temp_directory:
                destination = build_destination(Path(temp_directory), media)
                audio_path = self._storage.download(media, destination)

                result = self._transcriber.transcribe(
                    audio_path,
                    language=media.language,
                    prompt=media.prompt,
                )
        except Exception:
            logger.exception("Transcription failed for media %s", media_id)
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

        logger.info(
            "Transcription finished for media %s (%s segments, %s minutes)",
            media_id,
            len(result.segments),
            minutes,
        )

        return {
            "mediaId": media_id,
            "status": "transcribed",
            "language": result.language,
            "segments": len(result.segments),
            "minutesDebited": minutes,
        }
