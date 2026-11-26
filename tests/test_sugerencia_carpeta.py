"""BL-PARSE3 (F2): la carpeta sugiere la serie en «Por revisar».

Especificación: `docs/design/especificacion-BL-PARSE3.md`. Sin Postgres: la consulta de hermanos se
sustituye por filas fijas; su semántica real está en `test_sugerencia_carpeta_pg.py`.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from zascarr.models import File, FileFormat
from zascarr.services.sugerencia_carpeta import sugerencias_por_carpeta

FLASH = "/lib/Comics/Flash (1987)"


def _pendiente(nombre: str, carpeta: str = FLASH) -> File:
    return File(id=uuid4(), file_path=f"{carpeta}/{nombre}", file_name=nombre,
                file_format=FileFormat.CBZ, metadata_={"match_status": "unsorted"})


def _fila(carpeta: str, titulo: str, n: int, sid=None):
    return SimpleNamespace(carpeta=carpeta, series_id=sid or uuid4(), title=titulo,
                           start_year=1987, hermanos=n)


def _db(*filas) -> AsyncMock:
    db = AsyncMock()
    res = MagicMock()
    res.all = MagicMock(return_value=list(filas))
    db.execute = AsyncMock(return_value=res)
    return db


@pytest.mark.asyncio
async def test_tres_hermanos_unanimes_sugieren_su_serie():
    """C1: tres hermanos con número, todos en la misma serie."""
    sid = uuid4()
    f = _pendiente("Flash 12.cbz")
    s = await sugerencias_por_carpeta(_db(_fila(FLASH, "Flash", 3, sid)), [f])
    assert s[f.id].series_id == sid
    assert s[f.id].title == "Flash"
    assert s[f.id].start_year == 1987
    assert s[f.id].hermanos == 3


@pytest.mark.asyncio
async def test_menos_de_tres_hermanos_no_sugiere():
    """C2: con dos hermanos no hay evidencia suficiente."""
    f = _pendiente("Flash 12.cbz")
    assert await sugerencias_por_carpeta(_db(_fila(FLASH, "Flash", 2)), [f]) == {}


@pytest.mark.asyncio
async def test_hermanos_no_unanimes_no_sugiere():
    """C3: hermanos en dos series: la carpeta no es homogénea."""
    f = _pendiente("Flash 12.cbz")
    db = _db(_fila(FLASH, "Flash", 5), _fila(FLASH, "Flash Annual", 1))
    assert await sugerencias_por_carpeta(db, [f]) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("nombre, serie", [
    ("Flash Annual 03.cbz", "Flash"),        # anual en la carpeta de la serie madre
    ("Flash 03.cbz", "Flash Annual"),        # y al revés
])
async def test_la_guarda_de_anual_frena(nombre, serie):
    """C4: un anual solo se sugiere con una serie anual, como en el matcher."""
    f = _pendiente(nombre)
    assert await sugerencias_por_carpeta(_db(_fila(FLASH, serie, 4)), [f]) == {}


@pytest.mark.asyncio
async def test_una_consulta_por_pagina():
    """C5: una página con pendientes de varias carpetas hace una sola consulta."""
    otra = "/lib/Comics/Batman (1940)"
    pagina = [_pendiente("Flash 12.cbz"), _pendiente("Flash 13.cbz"),
              _pendiente("Batman 400.cbz", otra)]
    db = _db(_fila(FLASH, "Flash", 3), _fila(otra, "Batman", 7))
    s = await sugerencias_por_carpeta(db, pagina)
    assert db.execute.await_count == 1
    assert {s[f.id].title for f in pagina} == {"Flash", "Batman"}


@pytest.mark.asyncio
async def test_sin_pendientes_no_consulta():
    db = _db()
    assert await sugerencias_por_carpeta(db, []) == {}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("nombre, sugiere", [
    ("Flash 12.cbz", True),                                   # con número: sí
    ("Flash Volumen 88 (880-890).cbz", True),                 # tomo con rango de capítulos: sí
    ("Flash - Dossier Negro.cbz", False),                     # sin número
    ("Flash Especial Verano.cbz", False),                     # especial
    ("Flash Century 1910.cbz", False),                        # el «número» es un año
    ("Flash - Free Comic Book Day.cbz", False),               # promocional sin número
])
async def test_solo_sugiere_con_numero_y_sin_especial(nombre, sugiere):
    """C10 (R2b): en una carpeta homogénea, lo que queda pendiente suele ser lo que no encaja."""
    f = _pendiente(nombre)
    s = await sugerencias_por_carpeta(_db(_fila(FLASH, "Flash", 5)), [f])
    assert (f.id in s) is sugiere
