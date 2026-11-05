from __future__ import annotations

import pytest
from helpers import FakeDatabase, FakeJob, FakeSummarizer, make_media

from echo_worker.jobs.summary import SummaryJob


def build_job(
    database: FakeDatabase,
    summarizer: FakeSummarizer | None = None,
) -> tuple[SummaryJob, FakeSummarizer]:
    summarizer = summarizer or FakeSummarizer()
    job = SummaryJob(
        database=database,  # type: ignore[arg-type]
        summarizer=summarizer,
    )

    return job, summarizer


def test_appends_summary_and_stores_prompt() -> None:
    database = FakeDatabase(make_media(status="transcribed", transcription="conteúdo transcrito"))
    job, summarizer = build_job(database)

    result = job.process({"mediaId": "media-1", "prompt": "resuma em tópicos"})

    assert result["status"] == "summarized"
    assert result["characters"] == len("resumo de teste")
    assert database.statuses == ["processing_summary", "summarized"]
    assert database.appended == [("media-1", "resumo de teste", "resuma em tópicos")]
    assert summarizer.calls == [("conteúdo transcrito", "resuma em tópicos")]


def test_falls_back_to_media_summary_prompt() -> None:
    database = FakeDatabase(
        make_media(
            status="transcribed",
            transcription="conteúdo",
            summary_prompt="prompt salvo",
        )
    )
    job, summarizer = build_job(database)

    job.process({"mediaId": "media-1"})

    assert summarizer.calls == [("conteúdo", "prompt salvo")]


def test_resets_to_pending_transcription_when_missing() -> None:
    database = FakeDatabase(make_media(transcription=None))
    job, summarizer = build_job(database)

    result = job.process({"mediaId": "media-1", "prompt": "resuma"})

    assert result == {"mediaId": "media-1", "status": "missing_transcription"}
    assert database.statuses == ["pending_transcription"]
    assert database.appended == []
    assert summarizer.calls == []


def test_marks_failure_and_reraises() -> None:
    database = FakeDatabase(make_media(status="transcribed", transcription="conteúdo"))
    job, _ = build_job(database, FakeSummarizer(error=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        job.process({"mediaId": "media-1", "prompt": "resuma"})

    assert database.statuses == ["processing_summary", "failed_summary"]
    assert database.appended == []


def test_requires_prompt() -> None:
    database = FakeDatabase(make_media(status="transcribed", transcription="conteúdo"))
    job, _ = build_job(database)

    with pytest.raises(ValueError, match="prompt"):
        job.process({"mediaId": "media-1"})


def test_requires_media_id() -> None:
    job, _ = build_job(FakeDatabase(make_media()))

    with pytest.raises(ValueError, match="mediaId"):
        job.process({"prompt": "resuma"})


@pytest.mark.asyncio
async def test_call_runs_processor_from_job_data() -> None:
    database = FakeDatabase(make_media(status="transcribed", transcription="conteúdo"))
    job, _ = build_job(database)

    result = await job(FakeJob({"mediaId": "media-1", "prompt": "resuma"}), None)

    assert result["status"] == "summarized"
