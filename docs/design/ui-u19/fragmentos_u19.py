#!/usr/bin/env python3
# ruff: noqa: E501
"""Genera el fragmento de `POST .../asistente/buscar` que `capturar_u19.py` sirve al navegador (fuentes SIMULADAS).

Se ejecuta con el Python DEL PROYECTO. Lo produce la RUTA REAL (plantilla, macros, formularios de elegir) con `buscar_a_ritmo`
sustituido por una respuesta ya calculada: no se consulta ninguna fuente (el ensayo las tiene apagadas a propósito y Tebeosfera es
una asociación sin ánimo de lucro). Los tokens de las candidatas los firma la clave del ensayo, que se lee de un fichero que NO se
imprime ni se guarda en el repositorio.

    python docs/design/ui-u19/fragmentos_u19.py CLAVE_DEL_ENSAYO.txt SERIE_ID_LOCAL "Mundo Cobalto" fragmentos.json
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.descubrimiento_grupo import (
    Candidata,
    Coincidencia,
    GrupoResumen,
    RespuestaDescubrir,
    SerieLocal,
    SerieParecida,
)
from zascarr.services.tokens_revision import candidata_firmable, crear_token_candidata
from zascarr.web import asistente_carpetas

CLAVE_GRUPO = "_Unsorted"


def main(fichero_clave: str, serie_id: str, titulo_local: str, salida: str) -> None:
    secreto = open(fichero_clave, encoding="utf-8").read().strip()

    def tok(id_, titulo, anio):
        return crear_token_candidata(CLAVE_GRUPO, candidata_firmable("comic_vine", id_, titulo, anio, "american", None, None), secreto)

    parecida = SerieParecida(series_id=serie_id, titulo=titulo_local, anio=2015, tradicion="american", motivo="mismo_titulo")
    candidatas = [
        Candidata(token=tok("4050", "Mundo Cobalto", 2015), fuente="comic_vine", titulo="Mundo Cobalto", anio=2015,
                  tradicion_sugerida="american", sitio_url=None, portada=None, descripcion="Serie de ensayo (simulada).",
                  ya_en_biblioteca=None, parecidas_locales=[parecida], coincidencia_con_la_carpeta=Coincidencia(en_conflicto=False, senales=[])),
        Candidata(token=tok("9001", "Mundo Cobalto Integral", 2020), fuente="tebeosfera", titulo="Mundo Cobalto Integral", anio=2020,
                  tradicion_sugerida="tebeo", sitio_url=None, portada=None, descripcion=None,
                  ya_en_biblioteca=None, parecidas_locales=[], coincidencia_con_la_carpeta=Coincidencia(en_conflicto=False, senales=[])),
    ]
    respuesta = RespuestaDescubrir(
        consulta="Mundo Cobalto", consulta_propuesta="Mundo Cobalto", grupo=GrupoResumen(clave=CLAVE_GRUPO, carpeta_contextual=None, n_archivos=6),
        fuentes={"comic_vine": "ok", "anilist": "apagada", "tebeosfera": "ok", "gcd": "apagada"}, avisos=[], candidatas=candidatas)

    async def falsa(db, clave, consulta):
        return respuesta

    async def _db():
        yield None
    app.dependency_overrides[get_db] = _db
    try:
        with patch.object(asistente_carpetas, "buscar_a_ritmo", falsa), \
                patch.object(asistente_carpetas, "get_settings", lambda: SimpleNamespace(secret_key=secreto)):
            c = TestClient(app, base_url="http://localhost")
            r = c.post("/ui/pendientes/carpetas/asistente/buscar", data={"clave": CLAVE_GRUPO, "consulta": "Mundo Cobalto"},
                       headers={"HX-Request": "true", "Origin": "http://localhost"})
            assert r.status_code == 200, r.text[:300]
    finally:
        app.dependency_overrides.pop(get_db, None)
    json.dump({"buscar": r.text, "token_comic_vine": candidatas[0].token}, open(salida, "w", encoding="utf-8"), ensure_ascii=False)
    print("fragmento:", len(r.text), "bytes;", r.text.count("Elegir esta serie"), "candidatas")


if __name__ == "__main__":
    main(*sys.argv[1:5])
