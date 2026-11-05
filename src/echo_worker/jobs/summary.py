from __future__ import annotations

import asyncio
from typing import Any

from echo_worker.db import Database
from echo_worker.logging import get_logger
from echo_worker.providers.base import Summarizer

logger = get_logger(__name__)


class SummaryJob:
    """Generates a summary for an already transcribed media.

    The API composes the final prompt (template + user instructions) and sends
    it in the job payload, so the worker never parses prompt templates.
    """

    def __init__(self, database: Database, summarizer: Summarizer) -> None:
        self._database = database
        self._summarizer = summarizer

    async def __call__(self, job: Any, token: str | None = None) -> dict[str, Any]:
        _ = token

        return await asyncio.to_thread(self.process, job.data)

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        media_id = str(data.get("mediaId") or "")

        if not media_id:
            raise ValueError("Summary job is missing 'mediaId'")

        media = self._database.get_media(media_id)
        prompt = str(data.get("prompt") or media.summary_prompt or "")

        if not prompt:
            raise ValueError(f"Summary job for media {media_id} is missing 'prompt'")

        if not media.transcription:
            logger.warning(
                "Media %s has no transcription, resetting to pending_transcription",
                media_id,
            )
            self._database.reset_to_pending_transcription(media_id)

            return {
                "mediaId": media_id,
                "status": "missing_transcription",
            }

        self._database.mark_processing_summary(media_id)

        try:
            result = self._summarizer.summarize(media.transcription, prompt)
        except Exception:
            logger.exception("Summary failed for media %s", media_id)
            self._database.mark_failed_summary(media_id)
            raise

        self._database.append_summary(media_id, result.text, prompt)

        logger.info("Summary finished for media %s (%s chars)", media_id, len(result.text))

        return {
            "mediaId": media_id,
            "status": "summarized",
            "characters": len(result.text),
        }
