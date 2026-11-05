from __future__ import annotations

from echo_worker.config import Settings
from echo_worker.providers.base import Summarizer, Transcriber
from echo_worker.providers.fake import FakeSummarizer, FakeTranscriber
from echo_worker.providers.faster_whisper import FasterWhisperTranscriber
from echo_worker.providers.openai import OpenAISummarizer, OpenAITranscriber


def build_transcriber(settings: Settings) -> Transcriber:
    if settings.whisper_mode == "fake":
        return FakeTranscriber()

    if settings.whisper_mode == "openai":
        return OpenAITranscriber(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_whisper_model,
        )

    return FasterWhisperTranscriber(
        model_size=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def build_summarizer(settings: Settings) -> Summarizer:
    if settings.summary_mode == "fake":
        return FakeSummarizer()

    return OpenAISummarizer(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
    )
