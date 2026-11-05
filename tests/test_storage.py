from __future__ import annotations

from pathlib import Path

from helpers import make_media

from echo_worker.storage import build_destination


def test_build_destination_keeps_media_extension(tmp_path: Path) -> None:
    media = make_media(filename="entrevista.MP3")

    destination = build_destination(tmp_path, media)

    assert destination == tmp_path / "media-media-1.MP3"


def test_build_destination_falls_back_to_bin(tmp_path: Path) -> None:
    media = make_media(filename="sem-extensao")

    destination = build_destination(tmp_path, media)

    assert destination == tmp_path / "media-media-1.bin"
