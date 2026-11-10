# ruff: noqa: E501
"""CNV5-1/#482: contrato puro de capacidades, elegibilidad, normalización y presupuesto."""
from __future__ import annotations

import pytest

from zascarr.core.comicinfo_write import CAMPOS_GESTIONADOS
from zascarr.core.propuestas_comicinfo import (
    CAMPOS_IDENTIDAD,
    CAPACIDADES,
    ESPERA_MAX_S,
    MAX_LISTA,
    MAX_PETICIONES_POR_ACCION,
    MAX_PETICIONES_POR_FUENTE,
    MAX_PUBLISHER,
    MAX_SUMMARY,
    PAGECOUNT_MAX,
    PAGECOUNT_MIN,
    YEAR_MAX,
    YEAR_MIN,
    EstadoPropuesta,
    FuenteComicInfo,
    NivelDato,
    Presupuesto,
    ResultadoFuente,
    campo_elegible,
    campos_elegibles,
    construir_propuesta,
    crear_opcion,
    estado_es_error,
    estado_es_vacio,
    fuentes_elegibles,
    fuentes_para_tradicion,
    normalizar_texto,
    normalizar_valor,
    resultado_fuente,
    role_a_tag,
    sin_peticiones,
)
from zascarr.models import ComicTradition, CreatorRole
from zascarr.services.estados_fuentes import (
    FUENTE_APAGADA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
)


def test_matriz_solo_campos_de_valor_y_niveles():
    assert all(set(capacidades) <= set(CAMPOS_GESTIONADOS) for capacidades in CAPACIDADES.values())
    assert not (set().union(*(set(c) for c in CAPACIDADES.values())) & CAMPOS_IDENTIDAD)
    assert CAPACIDADES[FuenteComicInfo.COMIC_VINE]["Publisher"] is NivelDato.SERIE
    assert CAPACIDADES[FuenteComicInfo.COMIC_VINE]["Summary"] is NivelDato.NUMERO
    assert CAPACIDADES[FuenteComicInfo.ANILIST]["Year"] is NivelDato.SERIE
    assert CAPACIDADES[FuenteComicInfo.TEBEOSFERA]["PageCount"] is NivelDato.NUMERO
    assert CAPACIDADES[FuenteComicInfo.GCD]["Publisher"] is NivelDato.SERIE
    assert "Genre" not in campos_elegibles()       # ningún cliente lo devuelve hoy


def test_identidad_y_language_iso_nunca_elegibles():
    for tag in CAMPOS_GESTIONADOS:
        if tag in ("Series", "Number", "Volume", "LanguageISO"):
            assert not campo_elegible(tag), tag
            valor, motivo = normalizar_valor(tag, "x")
            assert valor is None and motivo
        else:
            assert tag in campos_elegibles() or tag == "Genre"


def test_fuentes_por_tradicion_apagadas_y_sin_trafico():
    assert set(fuentes_para_tradicion(ComicTradition.AMERICAN)) == {
        FuenteComicInfo.COMIC_VINE}
    assert FuenteComicInfo.ANILIST in fuentes_para_tradicion(ComicTradition.MANGA)
    assert FuenteComicInfo.TEBEOSFERA in fuentes_para_tradicion(ComicTradition.TEBEO)
    assert FuenteComicInfo.GCD in fuentes_para_tradicion(ComicTradition.FUMETTI)
    assert fuentes_elegibles([], ComicTradition.AMERICAN) == ()
    assert fuentes_elegibles(["anilist"], ComicTradition.AMERICAN) == ()
    activas = fuentes_elegibles([FuenteComicInfo.COMIC_VINE, FuenteComicInfo.ANILIST],
                                ComicTradition.AMERICAN)
    assert activas == (FuenteComicInfo.COMIC_VINE,)
    estados = sin_peticiones([], ComicTradition.MANGA)
    assert all(r.estado == FUENTE_APAGADA and r.peticiones == 0 for r in estados)


def test_normalizacion_texto_html_y_topes():
    assert normalizar_texto("<p>Hola <b>mundo</b></p>\n  <script>x</script>") == "Hola mundo"
    assert normalizar_texto("   ") is None
    assert normalizar_valor("Summary", "<p>" + "a" * MAX_SUMMARY + "</p>")[0] == "a" * MAX_SUMMARY
    assert normalizar_valor("Summary", "a" * (MAX_SUMMARY + 1))[1] is not None
    assert len(normalizar_valor("Publisher", "P" * MAX_PUBLISHER)[0]) == MAX_PUBLISHER
    assert normalizar_valor("Publisher", "P" * (MAX_PUBLISHER + 1))[0] is None


def test_normalizacion_listas_dedupe_casefold_y_tope():
    valor, motivo = normalizar_valor("Writer", ["Ana", " ana ", "", "Bob"])
    assert valor == "Ana, Bob" and motivo is None
    valor, motivo = normalizar_valor("Writer", ["A" * (MAX_LISTA + 1)])
    assert valor is None and motivo is not None
    assert normalizar_valor("Genre", ["Acción", "acción"])[0] is None  # sin capacidad hoy


def test_year_y_pagecount_bordes():
    for valor in (YEAR_MIN, YEAR_MAX):
        assert normalizar_valor("Year", valor) == (str(valor), None)
    for valor in (YEAR_MIN - 1, YEAR_MAX + 1, "dosmil", True):
        assert normalizar_valor("Year", valor)[0] is None
    assert normalizar_valor("PageCount", PAGECOUNT_MIN) == ("1", None)
    assert normalizar_valor("PageCount", PAGECOUNT_MAX) == ("10000", None)
    for valor in (0, -1, PAGECOUNT_MAX + 1, "veinticuatro", False):
        assert normalizar_valor("PageCount", valor)[0] is None


def test_crear_opcion_y_propuesta_estados():
    opcion = crear_opcion("Year", 1980, fuente=FuenteComicInfo.COMIC_VINE,
                          nivel=NivelDato.SERIE)
    assert opcion is not None and opcion.valor == "1980"
    assert opcion.nivel is NivelDato.SERIE        # el nivel explícito manda
    vacia = crear_opcion("Year", 99, fuente=FuenteComicInfo.COMIC_VINE,
                         nivel=NivelDato.NUMERO)
    assert vacia is not None and vacia.valor == "" and vacia.motivo

    p = construir_propuesta("Year", None, [opcion])
    assert p.estado is EstadoPropuesta.ANADIR and len(p.opciones) == 1
    igual = construir_propuesta("Year", "1980", [opcion])
    assert igual.estado is EstadoPropuesta.YA_COINCIDE
    distinto = construir_propuesta("Year", "1970", [opcion])
    assert distinto.estado is EstadoPropuesta.PROPONER_SUSTITUCION
    bloqueado = construir_propuesta("Year", "1970", [opcion], bloqueado=True)
    assert bloqueado.estado is EstadoPropuesta.BLOQUEADO and not bloqueado.opciones
    duplicado = construir_propuesta(
        "Year", None, [opcion, crear_opcion("Year", 1980, fuente=FuenteComicInfo.COMIC_VINE,
                                            nivel=NivelDato.NUMERO)])
    assert len(duplicado.opciones) == 1


def test_estados_cerrados_y_presupuesto():
    assert estado_es_vacio(FUENTE_SIN_RESULTADOS) and estado_es_vacio(FUENTE_APAGADA)
    assert estado_es_error(FUENTE_FALLO_TRANSITORIO)
    assert resultado_fuente(FuenteComicInfo.ANILIST, FUENTE_OK).estado == FUENTE_OK
    with pytest.raises(ValueError):
        ResultadoFuente(FuenteComicInfo.ANILIST, "inventado")
    assert (MAX_PETICIONES_POR_ACCION, MAX_PETICIONES_POR_FUENTE, ESPERA_MAX_S) == (5, 3, 3.0)
    p = Presupuesto()
    assert p.cabe(FuenteComicInfo.COMIC_VINE, 3)
    assert p.anotar(FuenteComicInfo.COMIC_VINE, 3)
    assert not p.cabe(FuenteComicInfo.COMIC_VINE, 1)      # tope por fuente
    assert p.anotar(FuenteComicInfo.ANILIST, 1)
    assert p.anotar(FuenteComicInfo.GCD, 1)
    assert p.agotado and not p.anotar(FuenteComicInfo.TEBEOSFERA)


def test_mapeo_de_roles():
    assert role_a_tag(CreatorRole.WRITER) == "Writer"
    assert role_a_tag(CreatorRole.TRANSLATOR) == "Translator"
    assert role_a_tag("otro") is None


def test_el_modulo_es_puro_sin_orm_config_ni_red(monkeypatch):
    """#610: importar el módulo NO debe cargar models/database/config/httpx/clientes."""
    import os
    import subprocess
    import sys

    codigo = """
import sys
import zascarr.core.propuestas_comicinfo
prohibidos = [
    "zascarr.models", "zascarr.database", "zascarr.config", "httpx",
    "zascarr.services.comic_vine", "zascarr.services.anilist",
    "zascarr.services.tebeosfera", "zascarr.services.gcd",
    "zascarr.services.discovery",
]
cargados = sorted(m for m in prohibidos if m in sys.modules)
assert not cargados, cargados
"""
    env = dict(os.environ)
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env["PYTHONPATH"] = os.path.join(raiz, "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-c", codigo], cwd=raiz, env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
