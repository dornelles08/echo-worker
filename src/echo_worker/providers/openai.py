from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from echo_worker.logging import get_logger
from echo_worker.models import Segment, SummaryResult, TranscriptionResult
from echo_worker.providers.base import normalize_language

logger = get_logger(__name__)

TRANSCRIPTION_TIMEOUT_SECONDS = 600
SUMMARY_TIMEOUT_SECONDS = 300


class OpenAIError(RuntimeError):
    """An external OpenAI-compatible API call failed."""


def _mime_type(filename: str) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")

    return {
        "mp3": "audio/mpeg",
        "mp4": "audio/mp4",
        "m4a": "audio/mp4",
        "mpeg": "audio/mpeg",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "aac": "audio/aac",
    }.get(extension, "application/octet-stream")


class OpenAITranscriber:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        data: dict[str, str] = {
            "model": self._model,
            "response_format": "verbose_json",
        }

        normalized_language = normalize_language(language)

        if normalized_language:
            data["language"] = normalized_language

        if prompt:
            data["prompt"] = prompt

        with audio_path.open("rb") as audio:
            files = {
                "file": (audio_path.name, audio, _mime_type(audio_path.name)),
            }

            response = self._post("/audio/transcriptions", data=data, files=files)

        payload: dict[str, Any] = response.json()

        segments = [
            Segment(
                id=str(segment.get("id", index)),
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=str(segment["text"]).strip(),
                avg_logprob=float(segment.get("avg_logprob", 0.0)),
                compression_ratio=float(segment.get("compression_ratio", 0.0)),
                no_speech_prob=float(segment.get("no_speech_prob", 0.0)),
            )
            for index, segment in enumerate(payload.get("segments", []))
        ]

        return TranscriptionResult(
            text=str(payload.get("text", "")).strip(),
            language=payload.get("language"),
            segments=segments,
        )

    def _post(
        self,
        path: str,
        *,
        data: dict[str, str],
        files: dict[str, tuple[str, Any, str]],
    ) -> httpx.Response:
        try:
            with httpx.Client(timeout=TRANSCRIPTION_TIMEOUT_SECONDS) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                return response
        except httpx.HTTPError as error:
            raise OpenAIError(f"Transcription request failed: {error}") from error


class OpenAISummarizer:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def summarize(self, transcription: str, prompt: str) -> SummaryResult:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcription},
            ],
            "temperature": 0.7,
        }

        try:
            with httpx.Client(timeout=SUMMARY_TIMEOUT_SECONDS) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise OpenAIError(f"Summary request failed: {error}") from error

        payload: dict[str, Any] = response.json()
        choices = payload.get("choices") or []
        text = ""

        if choices:
            text = str(choices[0].get("message", {}).get("content", "")).strip()

        if not text:
            raise OpenAIError("Summary response was empty")

        return SummaryResult(text=text)
