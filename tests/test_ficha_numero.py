# ruff: noqa: E501
"""#447: ficha de serie/número, autores y consultas fijas. Sin red."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.models import CreatorRole, FileFormat, IssueFormat
from zascarr.services.ficha_numero import (
    TEXTOS,
    cargar_ficha_numero,
    cargar_ficha_serie,
    partir_sinopsis,
)


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    async def execute(self, _s):
        self.llamadas += 1
        return self.respuestas.pop(0)


def _autor(nombre, rol, cantidad):
    return (rol, nombre, cantidad)


def _serie(**extra):
    base = dict(id=uuid4(), title="Thorgal", description="<p>Una <b>serie</b> de aventuras.</p>",
                start_year=1977, end_year=2000, publisher=SimpleNamespace(name="Norma"),
                metadata_source="comic_vine", locked_fields=[], metadata_={})
    base.update(extra)
    return SimpleNamespace(**base)


def _issue(**extra):
    base = dict(id=uuid4(), series_id=uuid4(), issue_number="3", title="El país Qâ",
                release_date=date(1981, 6, 1), page_count=48,
                synopsis="<p>Thorgal <i>llega</i> a un país.</p>",
                metadata_source="manual", credits=[], files=[])
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_ficha_serie_autores_principales_tope_y_texto_plano():
    serie = _serie()
    issues = [_issue(issue_number="1", files=[object()]), _issue(issue_number="2")]
    filas = [_autor("Ana", CreatorRole.WRITER, 9), _autor("Bea", CreatorRole.WRITER, 5),
             _autor("Carla", CreatorRole.WRITER, 2), _autor("Dani", CreatorRole.WRITER, 1),
             _autor("Eva", CreatorRole.PENCILER, 4)]
    db = _DB([_Res([serie]), _Res(issues), _Res(filas)])
    ficha = await cargar_ficha_serie(db, serie.id)
    assert ficha.sinopsis == "Una serie de aventuras."
    assert [a.nombre for a in ficha.autores["writer"]] == ["Ana", "Bea", "Carla"]
    assert ficha.autores["penciler"][0].numeros == 4
    assert [n.numero for n in ficha.numeros] == ["1", "2"]
    assert ficha.numeros[0].tiene_archivos is True
    assert db.llamadas == 3


@pytest.mark.asyncio
async def test_ficha_numero_agrupa_autores_archivos_y_texto_plano():
    serie = _serie()
    issue = _issue(credits=[
        SimpleNamespace(role=CreatorRole.WRITER, creator=SimpleNamespace(name="Ana")),
        SimpleNamespace(role=CreatorRole.PENCILER, creator=SimpleNamespace(name="Bea")),
    ], files=[
        SimpleNamespace(id=uuid4(), file_name="Thorgal 03.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=2 * 1048576, is_missing=False),
    ])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert ficha.sinopsis == "Thorgal llega a un país."
    assert ficha.autores["writer"] == ["Ana"] and ficha.autores["penciler"] == ["Bea"]
    assert ficha.archivos[0].nombre == "Thorgal 03.cbz"
    assert ficha.procedencia[TEXTOS["sinopsis"]] == "Puesto a mano"
    assert db.llamadas == 2


@pytest.mark.asyncio
async def test_ausencias_no_son_none():
    serie = _serie(description=None, publisher=None, start_year=None, end_year=None)
    issue = _issue(synopsis=None, release_date=None, page_count=None, credits=[], files=[])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert ficha.sinopsis == ""
    assert all("None" not in v for v in ficha.procedencia.values())
    assert TEXTOS["autores_numero"] not in ficha.procedencia


def test_recorte_de_sinopsis_a_40_palabras_sin_partir_palabra():
    texto = " ".join(f"p{i}" for i in range(60))
    visible, resto = partir_sinopsis(texto)
    assert visible.count(" ") == 39 and resto.startswith("p40")
    assert partir_sinopsis("Una frase corta") == ("Una frase corta", "")


def test_autores_principales_solo_guion_y_dibujo():
    serie = _serie()
    issue = _issue()
    filas = [_autor("Ana", CreatorRole.WRITER, 2), _autor("Bea", CreatorRole.PENCILER, 1),
             _autor("Color", CreatorRole.COLORIST, 9)]
    db = _DB([_Res([serie]), _Res([issue]), _Res(filas)])
    ficha = __import__("asyncio").run(cargar_ficha_serie(db, serie.id))
    assert set(ficha.autores) == {"writer", "penciler"}
    assert "colorist" not in ficha.autores


def test_formato_fecha_y_paginas_del_numero():
    serie = _serie()
    issue = _issue(page_count=1, format=IssueFormat.SINGLE_ISSUE)
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = __import__("asyncio").run(cargar_ficha_numero(db, serie.id, issue.id))
    assert ficha.formato == "grapa"
    assert ficha.fecha_larga == "1 de junio de 1981"
    assert ficha.paginas_texto == "1 página"
    assert ficha.tiene_datos is True
