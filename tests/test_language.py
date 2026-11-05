from __future__ import annotations

import pytest

from echo_worker.providers.base import normalize_language


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("pt", "pt"),
        ("pt-BR", "pt"),
        ("pt_BR", "pt"),
        ("EN-us", "en"),
        ("  es-MX  ", "es"),
    ],
)
def test_normalize_language(value: str | None, expected: str | None) -> None:
    assert normalize_language(value) == expected
