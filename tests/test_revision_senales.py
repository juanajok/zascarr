# ruff: noqa: E501
"""Propiedades de `RevisionCarpetas._senales` frente a un oráculo independiente (sin BD).

Revisión de #89: el cálculo de conflictos no puede dejar que una mayoría (el año o el título que dominan, la
serie más sugerida) oculte la discrepancia de un archivo minoritario. El oráculo recalcula, archivo a archivo
y sin reutilizar el código del servicio, qué archivos discrepan; el servicio debe señalarlos TODOS.
"""
from __future__ import annotations

import random
from uuid import UUID, uuid4

import pytest

from zascarr.core.carpetas import analizar_carpeta
from zascarr.core.matcher import normalize_title
from zascarr.services.revision_carpetas import (
    RevisionCarpetas,
    _Archivo,
    _Candidata,
)

SERIES: dict[UUID, tuple[str, int]] = {
    uuid4(): ("Flash", 1987), uuid4(): ("Flash", 1988), uuid4(): ("Flash", 2011), uuid4(): ("Impulse", 1995),
}
IDS = list(SERIES)
CARPETAS = [None, "Flash", "Flash (1987)", "Flash (2011)", "Flash (1999)", "Impulse (1995)", "Flash Vol2 (1987)"]
TITULOS = ["Flash", "Impulse", "Kid Flash"]
ANIOS = [None, None, 1987, 1988, 2011, 1995, 2020]


def _archivo(i: int, rng: random.Random) -> _Archivo:
    titulo = rng.choice(TITULOS)
    return _Archivo(
        id=f"f{i:03d}", nombre=f"{titulo} {i:02d}.cbz", sin_serie=False, carpetas=("Comics",), titulo=titulo,
        titulo_norm=normalize_title(titulo), anio=rng.choice(ANIOS), candidata=_Candidata(rng.choice(IDS), 1.0),
    )


def _senales(archivos, carpeta_nombre):
    carpeta = analizar_carpeta(carpeta_nombre) if carpeta_nombre else None
    distintas = len({a.candidata.series_id for a in archivos})
    from zascarr.services.revision_carpetas import PatronDeNombres
    patron = PatronDeNombres(titulo_dominante=None, proporcion=0.0, titulos_distintos=0)
    return RevisionCarpetas._senales(carpeta, distintas, patron, archivos, SERIES, tiene_contexto=bool(carpeta_nombre)), carpeta


def _oraculo_anio_archivo(archivos):
    """Los archivos cuyo propio año está a más de 1 del de SU serie sugerida."""
    return {a.id for a in archivos if a.anio and abs(a.anio - SERIES[a.candidata.series_id][1]) > 1}


def _oraculo_anio_carpeta(archivos, carpeta):
    if carpeta is None or not carpeta.anio:
        return set()
    return {a.id for a in archivos if abs(carpeta.anio - SERIES[a.candidata.series_id][1]) > 1}


def _oraculo_titulo(archivos, carpeta):
    # (la excepción del calificador de saga no entra: ninguna carpeta del corpus lo lleva)
    return {a.id for a in archivos if normalize_title(a.titulo) != normalize_title(SERIES[a.candidata.series_id][0])}


@pytest.mark.parametrize("semilla", range(400))
def test_ninguna_mayoria_oculta_una_discrepancia(semilla):
    rng = random.Random(semilla)
    carpeta_nombre = rng.choice(CARPETAS)
    archivos = [_archivo(i, rng) for i in range(rng.randint(1, 7))]
    senales, carpeta = _senales(archivos, carpeta_nombre)
    por_codigo = {s.codigo: s for s in senales}
    conflictos = [s for s in senales if s.severidad == "conflicto"]

    esperados_anio = _oraculo_anio_archivo(archivos) | _oraculo_anio_carpeta(archivos, carpeta)
    if esperados_anio:
        assert "anio_discrepa" in por_codigo, (carpeta_nombre, [(a.titulo, a.anio) for a in archivos])
        assert esperados_anio <= set(por_codigo["anio_discrepa"].archivos)
    else:
        assert "anio_discrepa" not in por_codigo

    esperados_titulo = _oraculo_titulo(archivos, carpeta)
    if esperados_titulo:
        assert "titulo_distinto" in por_codigo and esperados_titulo <= set(por_codigo["titulo_distinto"].archivos)
    else:
        assert "titulo_distinto" not in por_codigo

    # Un conflicto, el que sea, y «coincide_y_corrobora» no pueden convivir.
    if conflictos:
        assert "coincide_y_corrobora" not in por_codigo
    # Y si declara que coincide, TODOS los archivos coinciden en título y ninguno discrepa en año.
    if "coincide_y_corrobora" in por_codigo:
        assert not esperados_anio and not esperados_titulo
        assert all(a.anio is None or abs(a.anio - SERIES[a.candidata.series_id][1]) <= 1 for a in archivos)
