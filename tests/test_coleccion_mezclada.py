"""BL-INF11: archivos de colecciones distintas no comparten número."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from zascarr.services.archivos_por_numero import archivos_por_numero
from zascarr.utils.naming import clave_de_coleccion, parse_comic_filename


def test_el_subtitulo_antes_del_numero_no_se_pierde():
    parsed = parse_comic_filename("Superman - Godfall #01.cbr")
    assert parsed.series == "Superman" and parsed.issue_number == "1"
    assert parsed.subtitulo == "Godfall"


def test_el_titulo_despues_del_numero_no_cuenta_como_coleccion():
    assert clave_de_coleccion("Superman #01 - El origen.cbr") == clave_de_coleccion(
        "Superman #01.cbr")


def test_la_clave_distingue_colecciones_y_permite_copias():
    godfall = clave_de_coleccion("Superman - Godfall #01.cbr")
    origen = clave_de_coleccion("Superman - Origen Secreto #01.cbr")
    normal = clave_de_coleccion("Superman #01.cbr")
    copia = clave_de_coleccion("Superman #01 (copia).cbz")
    assert godfall != normal and origen != normal and godfall != origen
    assert copia == normal


def test_ediciones_de_la_misma_serie_comparten_clave():
    assert clave_de_coleccion("Superman Vol2 001 [SC][CRG].cbz") == \
        clave_de_coleccion("Superman #01.cbr")


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, *resultados):
        self._resultados = list(resultados)

    async def execute(self, *_a, **_k):
        return self._resultados.pop(0)


def _fila(nombre, issue_id):
    return SimpleNamespace(
        id=uuid4(), file_name=nombre, file_format=SimpleNamespace(value="cbz"),
        is_missing=False, metadata_source=None, metadata_={}, issue_id=issue_id,
        issue_number="1", sort_order=1.0, series_id=uuid4(),
        format=SimpleNamespace(value="single_issue"))


async def _numeros(*filas):
    sesion = _Sesion(_Resultado(list(filas)), _Resultado([]))
    return await archivos_por_numero(sesion, uuid4())


def test_un_numero_con_copias_del_mismo_titulo_no_esta_mezclado():
    issue_id = uuid4()
    resultado = asyncio.run(_numeros(
        _fila("Superman #01.cbz", issue_id), _fila("Superman #01 (copia).cbz", issue_id)))
    assert resultado[0].mezcla is False


def test_un_numero_con_titulos_distintos_se_marca_mezclado():
    issue_id = uuid4()
    resultado = asyncio.run(_numeros(
        _fila("Superman #01.cbz", issue_id), _fila("Superman - Godfall #01.cbz", issue_id)))
    assert resultado[0].mezcla is True


def test_la_ficha_avisa_cuando_el_numero_esta_mezclado():
    plantilla = (__import__("pathlib").Path(__file__).resolve().parents[1]
                 / "src/zascarr/web/templates/series_detail.html").read_text()
    assert "n.mezcla" in plantilla and "títulos distintos" in plantilla
