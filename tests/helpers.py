from __future__ import annotations

from pathlib import Path
from typing import Any

from echo_worker.db import MediaNotFoundError
from echo_worker.models import MediaRecord, Segment, SummaryResult, TranscriptionResult


def make_media(**overrides: Any) -> MediaRecord:
    values: dict[str, Any] = {
        "id": "media-1",
        "filename": "audio.mp3",
        "url": "http://localhost:9000/echo/audio.mp3",
        "storage_key": "medias/audio.mp3",
        "media_type": "audio",
        "status": "pending_transcription",
        "language": "pt-BR",
        "prompt": None,
        "duration": 120.0,
        "transcription": None,
        "summary_prompt": None,
        "user_id": "user-1",
        "usage_debited_at": None,
    }
    values.update(overrides)

    return MediaRecord(**values)


class FakeJob:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


class FakeDatabase:
    def __init__(self, media: MediaRecord | None) -> None:
        self.media = media
        self.statuses: list[str] = []
        self.debited: list[str] = []
        self.appended: list[tuple[str, str, str | None]] = []

    def get_media(self, media_id: str) -> MediaRecord:
        if self.media is None or self.media.id != media_id:
            raise MediaNotFoundError(media_id)

        return self.media

    def mark_processing_transcription(self, media_id: str) -> None:
        self.statuses.append("processing_transcription")

    def mark_transcribed(
        self,
        media_id: str,
        transcription: str,
        language: str | None,
        segments: list[Segment],
    ) -> None:
        self.statuses.append("transcribed")
        self.media = MediaRecord(
            **{
                **self.media.__dict__,
                "status": "transcribed",
                "transcription": transcription,
                "language": language or self.media.language,
            }
        )

    def mark_failed_transcription(self, media_id: str) -> None:
        self.statuses.append("failed_transcription")

    def mark_processing_summary(self, media_id: str) -> None:
        self.statuses.append("processing_summary")

    def mark_failed_summary(self, media_id: str) -> None:
        self.statuses.append("failed_summary")

    def reset_to_pending_transcription(self, media_id: str) -> None:
        self.statuses.append("pending_transcription")

    def append_summary(self, media_id: str, summary: str, prompt: str | None) -> None:
        self.statuses.append("summarized")
        self.appended.append((media_id, summary, prompt))

    def debit_usage(self, media_id: str) -> int | None:
        self.debited.append(media_id)

        return 2


class FakeStorage:
    def __init__(self) -> None:
        self.downloaded: list[MediaRecord] = []

    def download(self, media: MediaRecord, destination: Path) -> Path:
        self.downloaded.append(media)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-audio")

        return destination


class FakeTranscriber:
    def __init__(
        self,
        result: TranscriptionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or TranscriptionResult(
            text="transcrição de teste",
            language="pt",
            segments=[
                Segment(
                    id="0",
                    start=0.0,
                    end=1.0,
                    text="transcrição de teste",
                    avg_logprob=-0.1,
                    compression_ratio=1.0,
                    no_speech_prob=0.0,
                )
            ],
        )
        self.error = error
        self.calls: list[tuple[Path, str | None, str | None]] = []

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        self.calls.append((audio_path, language, prompt))

        if self.error:
            raise self.error

        return self.result


class FakeSummarizer:
    def __init__(self, result: SummaryResult | None = None, error: Exception | None = None) -> None:
        self.result = result or SummaryResult(text="resumo de teste")
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def summarize(self, transcription: str, prompt: str) -> SummaryResult:
        self.calls.append((transcription, prompt))

        if self.error:
            raise self.error

        return self.result
