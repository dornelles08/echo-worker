from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Segment:
    id: str
    start: float
    end: float
    text: str
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "avg_logprob": self.avg_logprob,
            "compression_ratio": self.compression_ratio,
            "no_speech_prob": self.no_speech_prob,
        }


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None
    segments: list[Segment] = field(default_factory=list)


@dataclass(frozen=True)
class MediaRecord:
    id: str
    filename: str
    url: str
    storage_key: str | None
    media_type: str
    status: str
    language: str
    prompt: str | None
    duration: float
    transcription: str | None
    summary_prompt: str | None
    user_id: str
    usage_debited_at: datetime | None


@dataclass(frozen=True)
class SummaryResult:
    text: str
