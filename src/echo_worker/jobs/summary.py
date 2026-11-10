from __future__ import annotations

import asyncio
import time
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
        trace_id = str(data.get("traceId") or "")

        if not media_id:
            raise ValueError("Summary job is missing 'mediaId'")

        extra: dict[str, Any] = {"mediaId": media_id}
        if trace_id:
            extra["traceId"] = trace_id

        media = self._database.get_media(media_id)
        prompt = str(data.get("prompt") or media.summary_prompt or "")

        if not prompt:
            raise ValueError(f"Summary job for media {media_id} is missing 'prompt'")

        if not media.transcription:
            logger.warning(
                "Media %s has no transcription, resetting to pending_transcription",
                media_id,
                extra=extra,
            )
            self._database.reset_to_pending_transcription(media_id)

            return {
                "mediaId": media_id,
                "status": "missing_transcription",
            }

        start_time = time.time()
        self._database.mark_processing_summary(media_id)

        logger.info(
            "Summary started for media %s",
            media_id,
            extra=extra,
        )

        try:
            result = self._summarizer.summarize(media.transcription, prompt)
        except Exception:
            total_duration = time.time() - start_time
            logger.exception(
                "Summary failed for media %s after %.2fs",
                media_id,
                total_duration,
                extra=extra,
            )
            self._database.mark_failed_summary(media_id)
            raise

        self._database.append_summary(media_id, result.text, prompt)

        total_duration = time.time() - start_time

        logger.info(
            "Summary finished for media %s (%s chars) in %.2fs",
            media_id,
            len(result.text),
            total_duration,
            extra=extra,
        )

        return {
            "mediaId": media_id,
            "status": "summarized",
            "characters": len(result.text),
        }
