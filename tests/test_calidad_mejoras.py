"""BL-D3 (#154): comparación de calidad y propuesta de mejora."""
from __future__ import annotations

from types import SimpleNamespace

from zascarr.services.calidad import (
    calidad_de_archivo,
    calidad_de_titulo,
    filtrar_mejoras,
)
from zascarr.services.prowlarr import SearchResult


def _archivo(**kw):
    base = {"source_tag": None, "width_px": None, "quality": None, "file_name": "a.cbz"}
    base.update(kw)
    return SimpleNamespace(**base)


def test_tiers_de_archivo_y_titulo():
    assert calidad_de_archivo(_archivo(source_tag="digital")).puntuacion == 3
    assert calidad_de_archivo(_archivo(width_px=1600)).puntuacion == 2
    assert calidad_de_archivo(_archivo(source_tag="scan")).puntuacion == 1
    assert calidad_de_archivo(_archivo()).puntuacion == 0
    assert calidad_de_titulo("Batman 001 (Digital) (2020).cbz").puntuacion == 3
    assert calidad_de_titulo("Batman 001 (Scan HD).cbr").puntuacion == 2
    assert calidad_de_titulo("Batman 001.cbz").puntuacion == 0


def _r(titulo, url="magnet:?xt=1", seeders=3):
    return SearchResult(titulo, "idx", url, 10_000_000, seeders, "comics")


def test_solo_ofrece_mismo_numero_serie_y_calidad_estrictamente_mejor():
    actual = _archivo(source_tag="scan", width_px=1000)   # nivel 1
    resultados = [
        _r("Batman 001 (Digital).cbz"),          # nivel 3, mismo número
        _r("Batman 002 (Digital).cbz"),          # otro número
        _r("Nightwing 001 (Digital).cbz"),       # otra serie
        _r("Batman 001 (Scan).cbz"),             # misma calidad, no mejora
    ]
    mejores = filtrar_mejoras(resultados, [actual], "1", "Batman")
    assert [m.resultado.title for m in mejores] == ["Batman 001 (Digital).cbz"]
    assert mejores[0].calidad.etiqueta == "alta"


def test_digital_solo_por_origen_y_la_resolucion_no_lo_finge():
    assert calidad_de_archivo(_archivo(source_tag="scan", width_px=2400)).puntuacion == 2
    assert calidad_de_archivo(_archivo(source_tag="digital")).puntuacion == 3
    # «Digitalizado» es un escaneo, no un digital: límites de palabra.
    assert calidad_de_titulo("Batman 001 (Digitalizado).cbz").puntuacion == 0
    assert calidad_de_titulo("Batman 001 (Digital).cbz").puntuacion == 3


def test_descarta_volumen_distinto_pack_y_variante():
    actual = _archivo(source_tag="scan", width_px=1000)
    resultados = [
        _r("Batman Vol. 3 001 (Digital).cbz"),          # volumen 3, no el 1
        _r("Batman 001 (Digital) (1 de 2).cbz"),        # pack parcial
        _r("Batman 001 (Digital) (Cover B).cbz"),       # variante
        _r("Batman 001 (Digital).cbz"),                 # válida
    ]
    mejores = filtrar_mejoras(resultados, [actual], "1", "Batman",
                              volumen=1, anio=2016)
    assert [m.resultado.title for m in mejores] == ["Batman 001 (Digital).cbz"]
