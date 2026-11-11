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
    ArchivoDeNumero,
    FichaSerie,
    NumeroEnlace,
    cargar_ficha_numero,
    cargar_ficha_serie,
    clasificar_archivos,
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


def _autor(nombre, rol, cantidad, fuente="comic_vine"):
    return (rol, nombre, fuente, cantidad)


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
        SimpleNamespace(role=CreatorRole.WRITER, creator=SimpleNamespace(name="Ana", metadata_source="manual")),
        SimpleNamespace(role=CreatorRole.PENCILER, creator=SimpleNamespace(name="Bea", metadata_source="manual")),
    ], files=[
        SimpleNamespace(id=uuid4(), file_name="Thorgal 03.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=2 * 1048576, is_missing=False),
    ])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert ficha.sinopsis == "Thorgal llega a un país."
    assert ficha.autores["writer"] == ["Ana"] and ficha.autores["penciler"] == ["Bea"]
    assert ficha.archivos[0].nombre == "Thorgal 03.cbz"
    assert ficha.procedencia[TEXTOS["sinopsis"]]["origen"] == "Puesto a mano"
    assert "Thorgal" in ficha.procedencia[TEXTOS["sinopsis"]]["valor"]
    assert db.llamadas == 2


@pytest.mark.asyncio
async def test_ausencias_no_son_none():
    serie = _serie(description=None, publisher=None, start_year=None, end_year=None)
    issue = _issue(synopsis=None, release_date=None, page_count=None, credits=[], files=[])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert ficha.sinopsis == ""
    assert all("None" not in d["origen"] and "None" not in d["valor"]
               for d in ficha.procedencia.values())
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


def test_enlace_para_numero_normaliza_ceros_y_prefiere_con_archivo():
    ficha = FichaSerie(serie=_serie(), sinopsis="", numeros=[
        NumeroEnlace(id="sin-archivo", numero="01", tiene_archivos=False),
        NumeroEnlace(id="con-archivo", numero="1", tiene_archivos=True),
    ])
    assert ficha.enlace_para_numero("1").id == "con-archivo"
    assert ficha.enlace_para_numero("01").id == "con-archivo"
    assert ficha.enlace_para_numero("9") is None


def test_formato_reutiliza_tabla_compartida():
    from zascarr.services.ficha_numero import FORMATOS_LEGIBLES
    from zascarr.web.asistente_vinculacion import FORMATOS_LEGIBLES as WEB
    assert FORMATOS_LEGIBLES is WEB
    assert FORMATOS_LEGIBLES["hardcover"] == "tomo en tapa dura"
    assert FORMATOS_LEGIBLES["manga_tankobon"] == "tomo de manga"


def _issue_con_creditos(fuentes):
    return _issue(credits=[
        SimpleNamespace(role=CreatorRole.WRITER,
                        creator=SimpleNamespace(name=f"A{i}", metadata_source=f))
        for i, f in enumerate(fuentes)])


@pytest.mark.asyncio
async def test_origen_autores_numero_sale_de_creditos():
    serie = _serie()
    issue = _issue_con_creditos([None])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    # Sin fuente en el crédito no se atribuye al issue (manual).
    assert ficha.procedencia[TEXTOS["autores_numero"]]["origen"] == "Origen no registrado"


@pytest.mark.asyncio
async def test_origen_autores_numero_mezcla_y_manual():
    serie = _serie()
    issue = _issue_con_creditos(["manual", "anilist"])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert ficha.procedencia[TEXTOS["autores_numero"]]["origen"] == "Varias fuentes"

    issue = _issue_con_creditos(["comic_vine", "comic_vine"])
    db = _DB([_Res([issue]), _Res([serie])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert ficha.procedencia[TEXTOS["autores_numero"]]["origen"] == "Comic Vine"


@pytest.mark.asyncio
async def test_autores_principales_sin_atribuir_si_falta_una_fuente():
    serie = _serie()
    issue = _issue()
    filas = [_autor("Ana", CreatorRole.WRITER, 2, "comic_vine"),
             _autor("Bea", CreatorRole.PENCILER, 1, None)]
    db = _DB([_Res([serie]), _Res([issue]), _Res(filas)])
    ficha = await cargar_ficha_serie(db, serie.id)
    assert ficha.origen_autores == "Origen no registrado"
    assert ficha.autores_texto == "Guion: Ana; Dibujo: Bea"


def test_archivos_del_numero_en_orden_natural_unitario():
    serie = _serie()
    issue = _issue(files=[
        SimpleNamespace(id=uuid4(), file_name="2.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=1, is_missing=False),
        SimpleNamespace(id=uuid4(), file_name="10.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=1, is_missing=False),
        SimpleNamespace(id=uuid4(), file_name="1.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=1, is_missing=False),
    ])
    db = _DB([_Res([issue]), _Res([serie]), _Res([])])
    ficha = __import__("asyncio").run(cargar_ficha_numero(db, serie.id, issue.id))
    assert [a.nombre for a in ficha.archivos] == ["1.cbz", "2.cbz", "10.cbz"]


def _archivo(nombre, sha, formato="cbz"):
    return ArchivoDeNumero(id=str(uuid4()), nombre=nombre, formato=formato,
                           tamano=1024, falta_en_disco=False, sha256=sha)


def test_bl_r6_copia_variante_y_sin_comprobar():
    copia = clasificar_archivos([_archivo("a.cbz", "x" * 64), _archivo("b.cbz", "x" * 64)])
    assert [a.clasificacion for a in copia] == ["copia", "copia"]
    variante = clasificar_archivos([_archivo("a.cbz", "x" * 64), _archivo("b.cbz", "y" * 64)])
    assert [a.clasificacion for a in variante] == ["variante", "variante"]
    sin_comprobar = clasificar_archivos([_archivo("a.cbz", None), _archivo("b.cbz", None)])
    assert [a.clasificacion for a in sin_comprobar] == ["sin_comprobar", "sin_comprobar"]
    assert clasificar_archivos([_archivo("solo.cbz", "x" * 64)])[0].clasificacion == ""


@pytest.mark.asyncio
async def test_bl_r6_otras_publicaciones_con_el_mismo_numero_son_ediciones():
    serie = _serie()
    issue = _issue(files=[
        SimpleNamespace(id=uuid4(), file_name="a.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=1, is_missing=False, sha256_hash="a" * 64),
        SimpleNamespace(id=uuid4(), file_name="b.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=2, is_missing=False, sha256_hash="b" * 64),
    ], volume=1, format=IssueFormat.SINGLE_ISSUE)
    otra = _issue(issue_number="3", volume=2, format=IssueFormat.HARDCOVER,
                  files=[SimpleNamespace(id=uuid4(), file_name="tomo.cbz")])
    db = _DB([_Res([issue]), _Res([serie]), _Res([issue, otra])])
    ficha = await cargar_ficha_numero(db, serie.id, issue.id)
    assert [a.clasificacion for a in ficha.archivos] == ["variante", "variante"]
    assert len(ficha.otras_ediciones) == 1
    assert ficha.otras_ediciones[0].volumen == 2
    assert ficha.otras_ediciones[0].formato == "tomo en tapa dura"
