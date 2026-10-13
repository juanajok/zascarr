# ruff: noqa: E501, F401, F811
"""`POST /api/revision/serie/sin-carpeta/previsualizar`: el alta por API SIN carpeta de origen (I6 de #114, primer paso:
sustituto de `POST /api/series`) — Postgres real, por la aplicación real, sin red.

Se prueba el recorrido completo con las rutas de siempre: previsualizar (nueva) → confirmar (`POST /api/revision/serie`,
solo el token) → deshacer; que es lo MISMO que el alta con carpeta (tradición elegida, identificador exacto, parecidas que
decide la persona, comprobante, idempotencia); que NO acepta `clave`; y la receta de migración desde `POST /api/series`
(crear por el alta y completar con `PATCH`). Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.test_alta_serie_pg import (  # noqa: F401  (BD efímera y entorno sin red)
    ALTA,
    CARPETA,
    CV_OK,
    SECRETO,
    cliente,
    entorno,
    numero_de_series,
    post,
    sembrar_serie,
    serie_en_bd,
    url_bd,
)
from zascarr.models import AltaOperacion, ComicTradition
from zascarr.services.tokens_revision import (
    CLAVE_SIN_GRUPO,
    MAX_TOKEN_CANDIDATA_SIN_GRUPO,
    CandidataFirmada,
    crear_token_candidata,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

SIN_CARPETA = "/api/revision/serie/sin-carpeta/previsualizar"
AM = ComicTradition.AMERICAN


def manual(titulo="Flash", anio=1987, tradicion="american", **kw) -> dict:
    return {"manual": {"titulo": titulo, "anio": anio}, "tradicion": tradicion, **kw}


def candidata(clave=CLAVE_SIN_GRUPO, fuente="comic_vine", id_="796", titulo="Flash", anio=1987) -> str:
    return crear_token_candidata(clave, CandidataFirmada(fuente, id_, titulo, anio, "american", "Velocista.", CV_OK), SECRETO)


async def comprobantes(b) -> int:
    async with b.fabrica() as s:
        return len((await s.execute(select(AltaOperacion))).scalars().all())


class TestElRecorridoCompleto:
    @pytest.mark.asyncio
    async def test_previsualizar_no_escribe_nada_y_ofrece_crear(self, entorno):
        r = await post(SIN_CARPETA, manual())
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        v = r.json()
        assert v["accion"] == "crear" and v["origen"] == "manual" and v["token"]
        assert v["efectos"] == {"series_nuevas": 1, "numeros": 0, "archivos": 0}
        assert await numero_de_series(entorno.banco) == 0 and await comprobantes(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_se_confirma_con_la_ruta_de_siempre_y_solo_el_token(self, entorno):
        v = (await post(SIN_CARPETA, manual(tradicion="manga"))).json()
        r = await post(ALTA, {"token": v["token"]})
        assert r.status_code == 200 and r.json()["resultado"] == "creada" and r.json()["deshacer"]
        (s,) = await serie_en_bd(entorno.banco)
        assert (s.title, s.start_year, s.tradition, s.metadata_source) == ("Flash", 1987, ComicTradition.MANGA, "manual")
        assert s.metadata_["alta"]["desde_grupo"] is None and s.metadata_["alta"]["tradicion_elegida"] is True
        assert await comprobantes(entorno.banco) == 1

    @pytest.mark.asyncio
    async def test_repetir_la_confirmacion_no_crea_otra(self, entorno):
        token = (await post(SIN_CARPETA, manual())).json()["token"]
        a, b = await post(ALTA, {"token": token}), await post(ALTA, {"token": token})
        assert (a.json()["repetida"], b.json()["repetida"]) == (False, True)
        assert await numero_de_series(entorno.banco) == 1

    @pytest.mark.asyncio
    async def test_se_deshace_con_la_ruta_de_siempre(self, entorno):
        token = (await post(SIN_CARPETA, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        r = await post(f"/api/revision/serie/{d['series_id']}/deshacer", {"operacion_id": d["operacion_id"]})
        assert r.status_code == 200 and r.json()["deshecho"] is True
        assert await numero_de_series(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_receta_de_migracion_desde_post_api_series_crear_y_completar_con_patch(self, entorno):
        """Lo que hacía `POST /api/series` con descripción, estado y total: ahora alta + `PATCH`."""
        token = (await post(SIN_CARPETA, manual())).json()["token"]
        sid = (await post(ALTA, {"token": token})).json()["serie"]["series_id"]
        async with cliente() as c:
            r = await c.patch(f"/api/series/{sid}", json={"description": "Velocista.", "status": "completed", "total_issues": 12})
        # (el `get_db` de las pruebas no confirma; la respuesta es lo que ve quien llama, y el título no cambió)
        assert r.status_code == 200
        cuerpo = r.json()
        assert (cuerpo["title"], cuerpo["description"], cuerpo["status"], cuerpo["total_issues"]) == ("Flash", "Velocista.", "completed", 12)


class TestMismoContratoQueElAltaConCarpeta:
    @pytest.mark.asyncio
    async def test_la_tradicion_se_elige_y_no_hay_valor_por_defecto(self, entorno):
        r = await post(SIN_CARPETA, {"manual": {"titulo": "Flash", "anio": 1987}})
        assert r.status_code == 422 and await numero_de_series(entorno.banco) == 0
        assert (await post(SIN_CARPETA, manual(tradicion="inventada"))).status_code == 422

    @pytest.mark.asyncio
    async def test_no_acepta_clave_ni_campos_sueltos(self, entorno):
        assert (await post(SIN_CARPETA, manual(clave=CARPETA))).status_code == 422
        assert (await post(SIN_CARPETA, manual(comic_vine_id=1))).status_code == 422
        assert await numero_de_series(entorno.banco) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cuerpo", [
        {"tradicion": "american"},
        {"tradicion": "american", "manual": {"titulo": "Flash"}, "candidata": "x"},
    ])
    async def test_una_candidata_o_datos_a_mano_pero_no_ambos_ni_ninguno(self, entorno, cuerpo):
        r = await post(SIN_CARPETA, cuerpo)
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "datos_invalidos"

    @pytest.mark.asyncio
    async def test_una_candidata_sin_carpeta_crea_con_el_identificador_protegido(self, entorno):
        v = (await post(SIN_CARPETA, {"candidata": candidata(), "tradicion": "american"})).json()
        assert v["accion"] == "crear" and v["origen"] == "descubrir" and v["fuente"] == "comic_vine"
        await post(ALTA, {"token": v["token"]})
        (s,) = await serie_en_bd(entorno.banco)
        assert s.comic_vine_id == 796 and s.locked_fields == ["comic_vine_id"] and s.cover_url == CV_OK

    @pytest.mark.asyncio
    async def test_una_candidata_de_una_carpeta_no_vale(self, entorno):
        r = await post(SIN_CARPETA, {"candidata": candidata(clave=CARPETA), "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"

    @pytest.mark.asyncio
    async def test_una_candidata_mas_larga_que_el_maximo_sin_carpeta_se_rechaza_sin_efectos(self, entorno):
        r = await post(SIN_CARPETA, {"candidata": "a" * (MAX_TOKEN_CANDIDATA_SIN_GRUPO + 1), "tradicion": "american"})
        assert r.status_code == 422 and await numero_de_series(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_el_identificador_exacto_reutiliza_sin_tocar_la_existente(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Otro título", 2001, comic_vine_id=796)
        v = (await post(SIN_CARPETA, {"candidata": candidata(), "tradicion": "american"})).json()
        assert v["accion"] == "reutilizar" and v["existente"]["series_id"] == str(sid)
        r = await post(ALTA, {"token": v["token"]})
        assert r.json()["resultado"] == "reutilizada" and (await serie_en_bd(entorno.banco))[0].title == "Otro título"

    @pytest.mark.asyncio
    async def test_las_parecidas_las_decide_la_persona(self, entorno):
        sid = await sembrar_serie(entorno.banco, "FLASH", 1988)
        v = (await post(SIN_CARPETA, manual())).json()
        assert v["accion"] == "elegir" and v["token"] is None and [p["series_id"] for p in v["parecidas"]] == [str(sid)]
        crea = (await post(SIN_CARPETA, manual(decision="crear_igualmente"))).json()
        assert crea["accion"] == "crear" and (await post(ALTA, {"token": crea["token"]})).status_code == 200
        elige = (await post(SIN_CARPETA, manual(decision="reutilizar", serie_id=str(sid)))).json()
        assert elige["accion"] == "reutilizar"

    @pytest.mark.asyncio
    async def test_una_parecida_nueva_entre_la_vista_previa_y_la_confirmacion_da_409(self, entorno):
        token = (await post(SIN_CARPETA, manual())).json()["token"]
        await sembrar_serie(entorno.banco, "Flash", 1987)
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "aparecieron_parecidas"
        assert await numero_de_series(entorno.banco) == 1
