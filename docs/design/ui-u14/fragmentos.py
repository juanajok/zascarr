#!/usr/bin/env python3
# ruff: noqa: E501
"""Genera los fragmentos de `/ui/descubrir/buscar` que `capturar_u14.py` sirve al navegador.

Se ejecuta con el Python DEL PROYECTO (necesita `zascarr` y sus dependencias). Cada fragmento lo produce la RUTA REAL
(plantilla, filtros, región viva…) con `DiscoveryService.search_detallada` sustituido por una `Busqueda` ya calculada: así
no se consulta ninguna fuente externa (el ensayo las tiene apagadas a propósito y Tebeosfera es una asociación sin ánimo de
lucro). Lo que se prueba en el navegador es la presentación, no las fuentes.

    python docs/design/ui-u14/fragmentos.py docs/design/ui-u14/fragmentos.json
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import Busqueda, DiscoveryResult, ProcedenciaTradicion

OK, ERR, OFF, SINCLAVE = "ok", "error", "apagada", "sin_clave"


def res(fuente, titulo, descripcion, n):
    return DiscoveryResult(
        source=fuente, external_id=str(n), title=titulo, start_year=1958, description=descripcion, cover_url=None,
        site_url=f"https://comicvine.gamespot.com/{n}/", tradition_guess=ComicTradition.AMERICAN,
        tradition_provenance=ProcedenciaTradicion.POR_DEFECTO)


ESCENARIOS = {
    "con_resultados_y_una_caida": Busqueda(
        [res(MetadataSource.COMIC_VINE, "Mortadelo y Filemón", "<p>Mortadelo <a href=\"/e/1\">Bruguera</a> &amp; Filemón, "
             "agentes de la <b>T.I.A.</b></p><script>alert(1)</script>", 1),
         res(MetadataSource.TEBEOSFERA, "Mortadelo", "<p>Edición española.</p>", 2)],
        [], {"comic_vine": OK, "anilist": ERR, "tebeosfera": OK, "gcd": OK}),
    "todas_fallan": Busqueda([], [], {"comic_vine": ERR, "anilist": ERR, "tebeosfera": ERR, "gcd": ERR}),
    "sin_coincidencias": Busqueda([], [], {"comic_vine": OK, "anilist": OK, "tebeosfera": OK, "gcd": OK}),
    "sin_clave_y_una_caida": Busqueda([], [], {"comic_vine": SINCLAVE, "anilist": OK, "tebeosfera": ERR, "gcd": OK}),
}


def main(salida: str) -> None:
    class Sesion:
        async def execute(self, _):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=None)
            return r

    async def _db():
        yield Sesion()
    app.dependency_overrides[get_db] = _db
    import zascarr.web.discovery as web
    datos = {}
    try:
        # La página con las cuatro fuentes encendidas (el ensayo las tiene apagadas a propósito).
        web.get_settings = lambda: SimpleNamespace(
            secret_key="secreto-de-ensayo", comicvine_enabled=True, comicvine_api_key="clave-de-ensayo",
            anilist_enabled=True, tebeosfera_enabled=True, gcd_enabled=True)
        c = TestClient(app, base_url="http://localhost")   # sin `with`: no se ejecuta el arranque (no hay BD aquí)
        datos["pagina"] = c.get("/ui/descubrir").text
        for nombre, busqueda in ESCENARIOS.items():
            with patch("zascarr.web.discovery.DiscoveryService.search_detallada", AsyncMock(return_value=busqueda)):
                datos[nombre] = c.get("/ui/descubrir/buscar", params={"q": "Mortadelo"}).text
    finally:
        app.dependency_overrides.pop(get_db, None)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    print({k: len(v) for k, v in datos.items()})


if __name__ == "__main__":
    main(sys.argv[1])
