# ruff: noqa: E501
"""CNV5-3: sesión efímera de propuestas (TTL, claves opacas, elecciones, sin escritura)."""
from __future__ import annotations

import pytest

from zascarr.core.propuestas_comicinfo import (
    EstadoPropuesta,
    FuenteComicInfo,
    NivelDato,
    OpcionPropuesta,
    PropuestaCampo,
    ResultadoFuente,
)
from zascarr.services.propuestas_comicinfo_sesion import (
    TTL_SESION_S,
    AlmacenPropuestas,
    SesionCaducadaError,
)


def _propuesta(tag="Year", actual=None):
    return PropuestaCampo(
        tag, actual, (OpcionPropuesta("1980", FuenteComicInfo.COMIC_VINE, NivelDato.SERIE,
                                      "https://comicvine.example/v"),),
        EstadoPropuesta.ANADIR)


class _Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


def _crear(almacen, *, bloqueados=None):
    return almacen.crear(
        file_id="f", serie_id="s", ruta="/media/library/a.cbz", tamano=10, mtime_ns=20,
        sha256="a" * 64,
        propuestas=(_propuesta(), PropuestaCampo(
            "Publisher", None, (OpcionPropuesta("Editorial", FuenteComicInfo.GCD, NivelDato.SERIE),),
            EstadoPropuesta.ANADIR)),
        estados=(ResultadoFuente(FuenteComicInfo.COMIC_VINE, "ok"),
                 ResultadoFuente(FuenteComicInfo.GCD, "fuente_apagada", 0, "Apagada")),
        avisos=(), bloqueados=bloqueados)


def test_claves_opacas_y_eleccion_valida():
    almacen = AlmacenPropuestas(reloj=_Reloj())
    sesion = _crear(almacen)
    assert sesion.resumen == "Has elegido 0 cambios de 2 campos con propuesta."
    clave = next(iter(sesion.claves_por_tag["Year"]))
    assert clave != "1980" and len(clave) == 32
    almacen.elegir(sesion.operacion_id, "Year", clave)
    assert sesion.resumen.startswith("Has elegido 1 cambios")
    campos = {c.tag: c for c in sesion.campos_ui()}
    assert campos["Year"].opciones[0].procedencia == "https://comicvine.example/v"
    with pytest.raises(KeyError):
        almacen.elegir(sesion.operacion_id, "Year", "inventada")
    with pytest.raises(KeyError):
        almacen.elegir(sesion.operacion_id, "Number", clave)


def test_conservar_quita_la_eleccion():
    almacen = AlmacenPropuestas(reloj=_Reloj())
    sesion = _crear(almacen)
    clave = next(iter(sesion.claves_por_tag["Year"]))
    almacen.elegir(sesion.operacion_id, "Year", clave)
    almacen.elegir(sesion.operacion_id, "Year", None)
    assert sesion.elecciones == {}


def test_ttl_y_tope_de_sesiones():
    reloj = _Reloj()
    almacen = AlmacenPropuestas(ttl=100, maximo=2, reloj=reloj)
    s1 = _crear(almacen)
    assert almacen.obtener(s1.operacion_id) is s1
    reloj.ahora += TTL_SESION_S
    with pytest.raises(SesionCaducadaError):
        almacen.obtener(s1.operacion_id)
    s2 = _crear(almacen)
    s3 = _crear(almacen)
    assert len(almacen._datos) <= 2
    assert s2.operacion_id in almacen._datos and s3.operacion_id in almacen._datos


def test_bloqueado_no_tiene_opciones_y_url_no_segura_se_omite():
    almacen = AlmacenPropuestas(reloj=_Reloj())
    sesion = almacen.crear(
        file_id="f", serie_id="s", ruta="/a.cbz", tamano=1, mtime_ns=2, sha256="a" * 64,
        propuestas=(
            PropuestaCampo("Year", "1980", (), EstadoPropuesta.BLOQUEADO),
            PropuestaCampo("Summary", None, (OpcionPropuesta(
                "Texto", FuenteComicInfo.COMIC_VINE, NivelDato.NUMERO,
                "javascript:alert(1)"),), EstadoPropuesta.ANADIR),
        ), bloqueados={"Year"})
    campos = {c.tag: c for c in sesion.campos_ui()}
    assert campos["Year"].bloqueado and not campos["Year"].opciones
    assert campos["Summary"].opciones[0].procedencia is None
