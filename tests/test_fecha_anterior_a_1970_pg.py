# ruff: noqa: E501, F401, F811
"""Fecha anterior a 1970 (#142), de extremo a extremo (Postgres real y ficheros reales en `tmp`).

Tres clases de evidencia (como en #138, #139 y #144): unitaria (`test_fecha_anterior_a_1970.py`), HTTP (`TestHTTP`) y
recorrido completo (`TestRecorridoCompleto`): `/carpetas` → vista previa → token → `POST /api/revision/vinculacion` con
archivos reales cuya fecha se fija con `os.utime`. Antes: un solo archivo con fecha negativa entraba en el token y la
confirmación rechazaba TODO el token con `422 token_invalido`. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os

import pytest

from tests.test_numero_largo_del_nombre_pg import clave_del_grupo, por_nombre
from tests.test_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    confirmar,
    ent,
    estado_de_archivos,
    informes,
    numero_de,
)
from tests.test_vinculacion_previa_pg import (  # noqa: F401
    SECRETO,
    archivos,
    cliente,
    entorno,
    huella_disco,
    instantanea,
    previsualizar,
    serie_de_prueba,
    url_bd,
)
from zascarr.services.tokens_revision import verificar_token_vinculacion

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

NORMALES = ["Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz"]
ANTIGUO = "Flash 04 (1987).cbz"
CARPETA = "Comics/Flash (1987)"
CAUSA = "fecha_anterior_a_1970"


def poner_fecha(ent, nombre: str, ns: int) -> None:
    ruta = ent.lib / CARPETA / nombre
    os.utime(ruta, ns=(ns, ns))
    assert ruta.stat().st_mtime_ns == ns, "el sistema de archivos no conserva esa fecha"


async def grupo(ent, *nombres):
    ids = await archivos(ent, *(nombres or (*NORMALES, ANTIGUO)))
    return await clave_del_grupo(CARPETA), ids, await serie_de_prueba(ent)


def vinculable(f) -> bool:
    return f["motivos"] == [] and f["incluido_en_token"] is True and f["estado"] in ("se_vincularia", "con_conflicto_de_carpeta")


class TestHTTP:

    @pytest.mark.parametrize("ns", [-10**9, -1])
    async def test_un_archivo_con_fecha_anterior_a_1970_no_es_marcable_y_no_entra_en_el_token(self, ent, ns):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, ns)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        assert r.status_code == 200, r.text
        f = por_nombre(r)[ANTIGUO]
        assert f["estado"] == "origen_no_verificable" and f["causa"] == CAUSA and f["motivos"] == ["origen_no_verificable"]
        assert f["marcable"] is False and f["incluido_en_token"] is False
        assert "anterior a 1970" in f["texto"] and "No significa que haya desaparecido" in f["texto"]
        assert str(ns) not in f["texto"] and "1969" not in f["texto"]                     # no se enseña la fecha cruda
        firmados = verificar_token_vinculacion(r.json()["token"], SECRETO).archivos
        assert {a.id for a in firmados} == {str(ids[n]) for n in NORMALES}                 # el antiguo NO está

    async def test_la_fecha_exactamente_cero_si_es_vinculable(self, ent):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, 0)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        f = por_nombre(r)[ANTIGUO]
        assert vinculable(f) and f["causa"] is None
        firmados = verificar_token_vinculacion(r.json()["token"], SECRETO).archivos
        assert {(a.id, a.mtime_ns) for a in firmados if a.id == str(ids[ANTIGUO])} == {(str(ids[ANTIGUO]), 0)}
        c = await confirmar(r.json()["token"])
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["vinculados"] == 4

    async def test_una_fecha_muy_futura_no_se_toca_y_es_vinculable(self, ent):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, 10**19)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        assert vinculable(por_nombre(r)[ANTIGUO])
        c = await confirmar(r.json()["token"])
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["vinculados"] == 4

    async def test_si_solo_se_marca_el_archivo_antiguo_no_hay_token(self, ent):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, -10**9)
        r = await previsualizar(serie, clave=clave, marcados=[ids[ANTIGUO]])
        assert r.status_code == 200 and r.json()["token"] is None
        assert "Ninguno de los archivos marcados se puede vincular" in r.json()["motivo_sin_token"]

    async def test_un_archivo_que_no_existe_conserva_su_estado_aunque_su_fecha_fuera_antigua(self, ent):
        """Precedencia: sin archivo en disco manda `origen_no_encontrado`."""
        clave, ids, serie = await grupo(ent, *NORMALES)
        ids.update(await archivos(ent, ANTIGUO, en_disco=False))
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        assert por_nombre(r)[ANTIGUO]["estado"] == "origen_no_encontrado"

    async def test_un_numero_escrito_a_mano_no_arregla_una_fecha_antigua(self, ent):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, -10**9)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros={ids[ANTIGUO]: "9"})
        assert por_nombre(r)[ANTIGUO]["estado"] == "origen_no_verificable"


class TestRecorridoCompleto:

    async def test_lote_con_un_archivo_de_fecha_antigua_se_confirma_vinculando_los_validos_sin_mover_nada(self, ent):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, -10**9)
        antes_disco, antes_estado = huella_disco(ent.lib), await estado_de_archivos(ent.banco)
        antes_tablas = await instantanea(ent.banco)

        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        assert r.status_code == 200, r.text
        assert await informes(ent.banco) == [] and (await instantanea(ent.banco)) == antes_tablas      # solo lectura
        token = r.json()["token"]

        c = await confirmar(token)
        assert c.status_code == 200, c.text[:300]                                # antes: 422 token_invalido
        cuerpo = c.json()
        assert cuerpo["repetida"] is False and cuerpo["resultado"]["global"] == "vinculados_todos"
        assert cuerpo["resultado"]["totales"]["vinculados"] == 3

        despues = await estado_de_archivos(ent.banco)
        assert all(despues[n][0] and despues[n][1] == "manual" for n in NORMALES)
        assert despues[ANTIGUO][0] is None                                        # el antiguo SIGUE sin vincular
        assert {n: v[2] for n, v in despues.items()} == {n: v[2] for n, v in antes_estado.items()}   # rutas intactas
        assert huella_disco(ent.lib) == antes_disco                               # bytes, tamaño y fecha intactos
        assert await numero_de("local_aliases", ent.banco) == 0 and await numero_de("asignacion_operaciones", ent.banco) == 0
        guardado = await informes(ent.banco)
        assert len(guardado) == 1
        otra = await confirmar(token)
        assert otra.status_code == 200 and otra.json()["repetida"] is True and otra.json()["resultado"] == cuerpo["resultado"]
        assert await informes(ent.banco) == guardado

    async def test_tras_actualizar_la_fecha_y_repetir_la_vista_previa_el_archivo_se_vincula(self, ent):
        clave, ids, serie = await grupo(ent)
        poner_fecha(ent, ANTIGUO, -10**9)
        await confirmar((await previsualizar(serie, clave=clave, marcados=[ids[n] for n in NORMALES])).json()["token"])
        r = await previsualizar(serie, clave=clave, marcados=[ids[ANTIGUO]])
        assert por_nombre(r)[ANTIGUO]["causa"] == CAUSA
        poner_fecha(ent, ANTIGUO, 1_760_000_000_000_000_000)                       # «volviendo a copiarlo»
        r = await previsualizar(serie, clave=clave, marcados=[ids[ANTIGUO]])
        assert vinculable(por_nombre(r)[ANTIGUO])
        c = await confirmar(r.json()["token"])
        assert c.status_code == 200 and c.json()["resultado"]["global"] == "vinculados_todos"
        assert (await estado_de_archivos(ent.banco))[ANTIGUO][0] is not None
