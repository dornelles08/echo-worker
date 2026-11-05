from __future__ import annotations

import pytest
from helpers import FakeDatabase, FakeJob, FakeStorage, FakeTranscriber, make_media

from echo_worker.jobs.transcription import TranscriptionJob


def build_job(
    database: FakeDatabase,
    transcriber: FakeTranscriber | None = None,
    temp_dir: str = "/tmp/echo-worker-tests",
) -> tuple[TranscriptionJob, FakeStorage, FakeTranscriber]:
    storage = FakeStorage()
    transcriber = transcriber or FakeTranscriber()
    job = TranscriptionJob(
        database=database,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        transcriber=transcriber,
        temp_dir=temp_dir,
    )

    return job, storage, transcriber


def test_transcribes_and_debits_usage() -> None:
    database = FakeDatabase(make_media())
    job, storage, transcriber = build_job(database)

    result = job.process({"mediaId": "media-1"})

    assert result["status"] == "transcribed"
    assert result["segments"] == 1
    assert result["minutesDebited"] == 2
    assert database.statuses == ["processing_transcription", "transcribed"]
    assert database.debited == ["media-1"]
    assert len(storage.downloaded) == 1
    assert transcriber.calls[0][1:] == ("pt-BR", None)


def test_skips_already_transcribed_media_but_keeps_debit_retry() -> None:
    database = FakeDatabase(
        make_media(
            status="transcribed",
            transcription="já transcrito",
        )
    )
    job, storage, _ = build_job(database)

    result = job.process({"mediaId": "media-1"})

    assert result == {"mediaId": "media-1", "status": "skipped", "minutesDebited": 2}
    assert database.statuses == []
    assert database.debited == ["media-1"]
    assert storage.downloaded == []


def test_marks_failure_and_reraises() -> None:
    database = FakeDatabase(make_media())
    job, _, _ = build_job(database, FakeTranscriber(error=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        job.process({"mediaId": "media-1"})

    assert database.statuses == ["processing_transcription", "failed_transcription"]
    assert database.debited == []


def test_requires_media_id() -> None:
    job, _, _ = build_job(FakeDatabase(make_media()))

    with pytest.raises(ValueError, match="mediaId"):
        job.process({})


@pytest.mark.asyncio
async def test_call_runs_processor_from_job_data() -> None:
    database = FakeDatabase(make_media())
    job, _, _ = build_job(database)

    result = await job(FakeJob({"mediaId": "media-1"}), "token")

    assert result["status"] == "transcribed"
