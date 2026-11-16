"""Sin número en el nombre: no se adivina, pero la serie se sugiere (UX 2026-11-16)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from zascarr.core.matcher import MatchStatus, SeriesHit, SeriesMatcher


def _triage(nombre: str):
    return SimpleNamespace(
        path=Path(nombre), strong_candidate=False, comic_info=None)


@pytest.mark.asyncio
async def test_sin_numero_pero_serie_reconocida_guarda_los_candidatos():
    serie_id = uuid4()
    matcher = SeriesMatcher(session=object())  # no consulta: find_* van mockeados
    matcher.find_alias = AsyncMock(return_value=None)
    matcher.find_series = AsyncMock(return_value=[
        SeriesHit(serie_id, "Sector Lejano", None, 0.92),
    ])

    resultado = await matcher.decide(
        _triage("Sector Lejano (Young Animals - ECC) [GVS] [22 Aniversario CRG].cbz"),
        extractor=lambda _n: ("Sector Lejano", None, None),
    )

    assert resultado.status is MatchStatus.UNSORTED
    assert [c.series_id for c in resultado.candidates] == [serie_id]
    assert "sin número" in resultado.notes[0]


@pytest.mark.asyncio
async def test_sin_titulo_ni_numero_sigue_sin_candidatos():
    matcher = SeriesMatcher(session=object())
    matcher.find_alias = AsyncMock(return_value=None)
    matcher.find_series = AsyncMock(return_value=[])

    resultado = await matcher.decide(
        _triage("_Las aventuras del capitan Torrezno_Escala Real.cbz"),
        extractor=lambda _n: (None, None, None),
    )

    assert resultado.status is MatchStatus.UNSORTED
    assert resultado.candidates == []
    assert "sin título/número" in resultado.notes[0]
