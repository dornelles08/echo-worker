from __future__ import annotations

import math
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from echo_worker.logging import get_logger
from echo_worker.models import MediaRecord, Segment

logger = get_logger(__name__)


class MediaNotFoundError(RuntimeError):
    """The media referenced by a job does not exist anymore."""


class UsageCounterMissingError(RuntimeError):
    """The user has no usage counter row, so minutes cannot be debited."""


def _to_media(row: dict[str, Any]) -> MediaRecord:
    return MediaRecord(
        id=str(row["id"]),
        filename=row["filename"],
        url=row["url"],
        storage_key=row["storage_key"],
        media_type=row["type"],
        status=row["status"],
        language=row["language"],
        prompt=row["prompt"],
        duration=float(row["duration"]),
        transcription=row["transcription"],
        summary_prompt=row["summary_prompt"],
        user_id=str(row["user_id"]),
        usage_debited_at=row["usage_debited_at"],
    )


class Database:
    """PostgreSQL access owned by the API schema.

    The worker never runs migrations; it only reads and writes rows that the
    API created.
    """

    def __init__(self, database_url: str, pool_size: int = 5) -> None:
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=pool_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    def close(self) -> None:
        self._pool.close()

    def get_media(self, media_id: str) -> MediaRecord:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT id, filename, url, storage_key, type, status, language,
                       prompt, duration, transcription, summary_prompt, user_id,
                       usage_debited_at
                FROM medias
                WHERE id = %s
                """,
                (media_id,),
            ).fetchone()

        if row is None:
            raise MediaNotFoundError(f"Media {media_id} not found")

        return _to_media(row)

    def mark_processing_transcription(self, media_id: str) -> None:
        self._execute(
            """
            UPDATE medias
            SET status = 'processing_transcription', updated_at = now()
            WHERE id = %s
            """,
            (media_id,),
        )

    def mark_transcribed(
        self,
        media_id: str,
        transcription: str,
        language: str | None,
        segments: list[Segment],
    ) -> None:
        payload = Jsonb([segment.to_json() for segment in segments])

        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE medias
                SET status = 'transcribed',
                    transcription = %s,
                    language = COALESCE(%s, language),
                    segments = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (transcription, language, payload, media_id),
            )

    def mark_failed_transcription(self, media_id: str) -> None:
        self._execute(
            "UPDATE medias SET status = 'failed_transcription', updated_at = now() WHERE id = %s",
            (media_id,),
        )

    def mark_processing_summary(self, media_id: str) -> None:
        self._execute(
            "UPDATE medias SET status = 'processing_summary', updated_at = now() WHERE id = %s",
            (media_id,),
        )

    def mark_failed_summary(self, media_id: str) -> None:
        self._execute(
            "UPDATE medias SET status = 'failed_summary', updated_at = now() WHERE id = %s",
            (media_id,),
        )

    def reset_to_pending_transcription(self, media_id: str) -> None:
        self._execute(
            "UPDATE medias SET status = 'pending_transcription', updated_at = now() WHERE id = %s",
            (media_id,),
        )

    def append_summary(self, media_id: str, summary: str, prompt: str | None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE medias
                SET status = 'summarized',
                    summary = array_append(summary, %s),
                    summary_prompt = COALESCE(%s, summary_prompt),
                    updated_at = now()
                WHERE id = %s
                """,
                (summary, prompt, media_id),
            )

    def debit_usage(self, media_id: str) -> int | None:
        """Debits the media duration from the user's cycle, at most once.

        Returns the number of minutes debited, or ``None`` when the media was
        already debited by a previous attempt.
        """
        with self._pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "SELECT user_id, duration, usage_debited_at FROM medias WHERE id = %s FOR UPDATE",
                (media_id,),
            ).fetchone()

            if row is None:
                raise MediaNotFoundError(f"Media {media_id} not found")

            if row["usage_debited_at"] is not None:
                logger.info("Usage already debited for media %s", media_id)
                return None

            minutes = math.ceil(float(row["duration"]) / 60)
            user_id = row["user_id"]

            updated = conn.execute(
                """
                UPDATE usage_counters
                SET minutes_used = minutes_used + %s, updated_at = now()
                WHERE user_id = %s
                """,
                (minutes, user_id),
            )

            if updated.rowcount == 0:
                raise UsageCounterMissingError(f"Usage counter not found for user {user_id}")

            conn.execute(
                "UPDATE medias SET usage_debited_at = now(), updated_at = now() WHERE id = %s",
                (media_id,),
            )

        logger.info("Debited %s minutes for user %s (media %s)", minutes, user_id, media_id)
        return minutes

    def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        with self._pool.connection() as conn:
            conn.execute(query, params)
