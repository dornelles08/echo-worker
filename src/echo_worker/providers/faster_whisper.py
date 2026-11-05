from __future__ import annotations

from pathlib import Path
from typing import Any

from echo_worker.logging import get_logger
from echo_worker.models import Segment, TranscriptionResult
from echo_worker.providers.base import normalize_language

logger = get_logger(__name__)


class FasterWhisperTranscriber:
    """Local transcription with faster-whisper (CTranslate2).

    The model is loaded lazily so the worker can boot quickly and so tests can
    run without downloading weights.
    """

    def __init__(self, model_size: str, device: str = "cpu", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info(
                "Loading faster-whisper model %s (device=%s, compute_type=%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )

        return self._model

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        model = self._load_model()

        segments, info = model.transcribe(
            str(audio_path),
            language=normalize_language(language),
            initial_prompt=prompt or None,
            vad_filter=True,
        )

        collected: list[Segment] = []
        texts: list[str] = []

        for segment in segments:
            text = segment.text.strip()
            texts.append(text)
            collected.append(
                Segment(
                    id=str(segment.id),
                    start=float(segment.start),
                    end=float(segment.end),
                    text=text,
                    avg_logprob=float(segment.avg_logprob),
                    compression_ratio=float(segment.compression_ratio),
                    no_speech_prob=float(segment.no_speech_prob),
                )
            )

        return TranscriptionResult(
            text=" ".join(texts).strip(),
            language=getattr(info, "language", None),
            segments=collected,
        )
