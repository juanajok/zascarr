# ruff: noqa: E501
"""#341: página de exportación, BOM/cabeceras y streaming sin acumular filas."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from zascarr.main import app
from zascarr.services.exportar import (
    BOM,
    CABECERAS_COLECCION,
    CABECERAS_DESEADOS,
    generar_csv,
)
from zascarr.web import exportar as exportar_web


def _texto(chunks: list[bytes]) -> str:
    return b"".join(chunks).decode("utf-8")


async def _recoger(filas, cabecera):
    return [trozo async for trozo in generar_csv(filas, cabecera)]


def test_pagina_muestra_ambas_descargas_y_aviso_de_copia():
    r = TestClient(app).get("/ui/exportar")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    assert "/ui/exportar/coleccion.csv" in r.text
    assert "/ui/exportar/deseados.csv" in r.text
    assert "no es una copia de seguridad" in r.text
    assert "copia real" in r.text
    assert "rutas del disco" in r.text
    assert "Descargar colección" in r.text and "Descargar deseados" in r.text


@pytest.mark.asyncio
async def test_csv_con_bom_cabeceras_y_tildes():
    async def filas():
        yield ("Thorgal", "1980", "Editorial", "americana", "1", "La magia", "CBZ", "tengo")

    chunks = await _recoger(filas(), CABECERAS_COLECCION)
    crudo = b"".join(chunks)
    assert crudo.startswith(BOM.encode("utf-8"))
    texto = crudo.decode("utf-8-sig")
    assert texto.splitlines()[0] == "Serie,Año,Editorial,Tradición,Número,Título,Formato,Estado"
    assert "Thorgal" in texto and "La magia" in texto
    assert crudo.decode("utf-8").startswith("\ufeff")
    assert "\r\n" in texto


@pytest.mark.asyncio
async def test_csv_vacio_solo_cabecera():
    async def vacio():
        if False:
            yield ()

    texto = _texto(await _recoger(vacio(), CABECERAS_DESEADOS))
    assert texto == BOM + "Serie,Número,Estado,Política de búsqueda,Notas\r\n"


@pytest.mark.asyncio
async def test_streaming_entrega_la_cabecera_sin_consumir_las_filas():
    consumidas = {"n": 0}

    async def filas():
        for i in range(50):
            consumidas["n"] += 1
            yield (f"S{i}", None, None, None, str(i), None, None, "tengo")

    genera = generar_csv(filas(), CABECERAS_COLECCION)
    primero = await anext(genera)
    assert primero.startswith(BOM.encode("utf-8"))
    assert consumidas["n"] == 0
    segundo = await anext(genera)
    assert consumidas["n"] == 1 and b"S0" in segundo
    await genera.aclose()


def test_descarga_streaming_coleccion_con_bom_y_privacidad(monkeypatch):
    filas = [("Thorgal", "1980", "americana", "Editorial", "1", "La magia",
              None, "cbz", False)]

    class _Sesion:
        async def stream(self, _stmt):
            async def _filas():
                for fila in filas:
                    yield fila
            return _filas()

    @asynccontextmanager
    async def _fabrica():
        yield _Sesion()

    monkeypatch.setattr(exportar_web, "async_session_factory", lambda: _fabrica())
    r = TestClient(app).get("/ui/exportar/coleccion.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers.get("cache-control") == "no-store"
    assert r.content.startswith(BOM.encode("utf-8"))
    assert "Thorgal" in r.text
    assert "/tmp/" not in r.text and "file_path" not in r.text
