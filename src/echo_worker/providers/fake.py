from __future__ import annotations

from pathlib import Path

from echo_worker.models import Segment, SummaryResult, TranscriptionResult
from echo_worker.providers.base import normalize_language

FAKE_TRANSCRIPT = (
    "Esta é uma transcrição simulada usada em desenvolvimento. "
    "Ela existe para permitir testar o fluxo completo sem baixar modelos."
)


class FakeTranscriber:
    """Deterministic transcriber used in development and tests."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        _ = (audio_path, prompt)

        words = FAKE_TRANSCRIPT.split()
        midpoint = len(words) // 2

        segments = [
            Segment(
                id="0",
                start=0.0,
                end=3.0,
                text=" ".join(words[:midpoint]),
                avg_logprob=-0.12,
                compression_ratio=1.2,
                no_speech_prob=0.02,
            ),
            Segment(
                id="1",
                start=3.0,
                end=6.0,
                text=" ".join(words[midpoint:]),
                avg_logprob=-0.15,
                compression_ratio=1.3,
                no_speech_prob=0.03,
            ),
        ]

        return TranscriptionResult(
            text=FAKE_TRANSCRIPT,
            language=normalize_language(language) or "pt",
            segments=segments,
        )


class FakeSummarizer:
    """Deterministic summarizer used in development and tests."""

    def summarize(self, transcription: str, prompt: str) -> SummaryResult:
        return SummaryResult(
            text=(
                "## Resumo simulado\n\n"
                f"- Prompt aplicado: {prompt[:80]}\n"
                f"- Caracteres transcritos: {len(transcription)}\n"
            )
        )
