from __future__ import annotations

from pathlib import Path
from typing import Protocol

from echo_worker.models import SummaryResult, TranscriptionResult


class Transcriber(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult: ...


class Summarizer(Protocol):
    def summarize(self, transcription: str, prompt: str) -> SummaryResult: ...


def normalize_language(language: str | None) -> str | None:
    """Converts BCP-47 tags like ``pt-BR`` to the ``pt`` form Whisper expects."""
    if not language:
        return None

    primary = language.split("-")[0].split("_")[0].strip().lower()

    return primary or None
