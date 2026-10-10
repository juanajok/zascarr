# ruff: noqa: E501, F401, F811
"""Número largo extraído del nombre (#141), de extremo a extremo (Postgres real y ficheros reales en `tmp`).

Tres clases de evidencia (como en #138 y #139): unitaria (`test_numero_largo_del_nombre.py`), HTTP (`TestHTTP`) y
recorrido completo (`TestRecorridoCompleto`): `/carpetas` → vista previa → token → `POST /api/revision/vinculacion`, con
un archivo `Tomo 111…1` de 30 dígitos junto a otros normales. Antes: la vista previa lo daba por vinculable, el token lo
incluía y la confirmación rechazaba TODO el token con `422 token_invalido`. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

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
LARGO = "Tomo " + "1" * 30 + ".cbz"
CARPETA = "Comics/Flash (1987)"


async def clave_del_grupo(carpeta: str) -> str:
    """La `clave` que da la superficie de revisión (se lee de `/carpetas`)."""
    async with cliente() as c:
        r = await c.get("/api/revision/carpetas")
    claves = [g["clave"] for g in r.json()["grupos"] if g["clave"] == carpeta]
    assert len(claves) == 1, [g["clave"] for g in r.json()["grupos"]]
    return claves[0]


async def grupo_con_numero_largo(ent, *nombres):
    ids = await archivos(ent, *(nombres or (*NORMALES, LARGO)))
    clave = await clave_del_grupo(CARPETA)
    serie = await serie_de_prueba(ent)
    return clave, ids, serie


def por_nombre(r):
    return {a["nombre"]: a for a in r.json()["archivos"]}


def vinculable(f) -> bool:
    """Sin impedimentos (un `Tomo` en una carpeta de «Flash» sale `con_conflicto_de_carpeta`: es vinculable, con aviso)."""
    return f["motivos"] == [] and f["incluido_en_token"] is True and f["estado"] in ("se_vincularia", "con_conflicto_de_carpeta")


class TestHTTP:

    async def test_el_archivo_con_numero_largo_no_es_vinculable_y_no_entra_en_el_token(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        assert r.status_code == 200, r.text
        largo = por_nombre(r)[LARGO]
        assert largo["estado"] == "requiere_numero" and largo["motivos"] == ["requiere_numero"]
        assert largo["numero"] is None and largo["numero_del_nombre"] is None and largo["numero_origen"] == "ninguno"
        assert largo["marcable"] is False and largo["incluido_en_token"] is False
        assert "20 caracteres" in largo["texto"] and "escríbelo" in largo["texto"]
        assert all(por_nombre(r)[n]["estado"] == "se_vincularia" for n in NORMALES)
        firmados = verificar_token_vinculacion(r.json()["token"], SECRETO).archivos
        assert {a.id for a in firmados} == {str(ids[n]) for n in NORMALES}                   # el largo NO está

    async def test_el_motivo_no_exhibe_el_numero_entero(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent, "Tomo " + "7" * 100 + ".cbz")
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        t = r.json()["archivos"][0]["texto"]
        assert "7" * 21 not in t and "20 caracteres" in t

    @pytest.mark.parametrize("k,vinculable_", [(19, True), (20, True), (21, False), (100, False)])
    async def test_los_limites_19_20_21_y_100(self, ent, k, vinculable_):
        nombre = "Tomo " + "1" * k + ".cbz"
        clave, ids, serie = await grupo_con_numero_largo(ent, "Flash 01 (1987).cbz", nombre)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        f = por_nombre(r)[nombre]
        assert globals()["vinculable"](f) is vinculable_ and (f["numero"] == "1" * k) is vinculable_
        assert r.json()["token"]
        c = await confirmar(r.json()["token"])
        assert c.status_code == 200, c.text[:200]
        assert c.json()["resultado"]["totales"]["vinculados"] == (2 if vinculable_ else 1)

    async def test_el_mismo_archivo_con_un_numero_escrito_a_mano_valido_si_es_vinculable(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros={ids[LARGO]: "5"})
        f = por_nombre(r)[LARGO]
        assert vinculable(f) and f["numero"] == "5" and f["numero_origen"] == "persona"
        c = await confirmar(r.json()["token"])
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["vinculados"] == 4

    async def test_un_numero_a_mano_de_mas_de_20_sigue_rechazado_como_antes(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros={ids[LARGO]: "1" * 21})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "numero_no_valido"

    async def test_un_archivo_sin_numero_en_el_nombre_conserva_el_texto_de_siempre(self, ent):
        """El motivo específico es SOLO para el número descartado; sin número en el nombre sigue «falta el número»."""
        clave, ids, serie = await grupo_con_numero_largo(ent, "Flash 01 (1987).cbz", "Flash sin numero.cbz")
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        f = por_nombre(r)["Flash sin numero.cbz"]
        assert f["estado"] == "requiere_numero" and f["numero_origen"] == "ninguno"
        assert f["texto"] == "Falta el número: escríbelo para poder vincularlo." and "20 caracteres" not in f["texto"]

    async def test_si_solo_se_marca_el_archivo_largo_no_hay_token(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent)
        r = await previsualizar(serie, clave=clave, marcados=[ids[LARGO]])
        assert r.status_code == 200 and r.json()["token"] is None
        assert "Ninguno de los archivos marcados se puede vincular" in r.json()["motivo_sin_token"]

    async def test_borrar_a_mano_el_numero_del_nombre_largo_no_cambia_el_texto_a_uno_engañoso(self, ent):
        """Si la persona vacía el número, el motivo es el de siempre («falta el número»), no el del nombre."""
        clave, ids, serie = await grupo_con_numero_largo(ent)
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros={ids[LARGO]: ""})
        f = por_nombre(r)[LARGO]
        assert f["estado"] == "requiere_numero" and f["numero_origen"] == "persona" and "20 caracteres" not in f["texto"]


class TestRecorridoCompleto:

    async def test_lote_con_un_numero_largo_se_confirma_vinculando_los_validos_sin_mover_nada(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent)
        antes_disco, antes_estado = huella_disco(ent.lib), await estado_de_archivos(ent.banco)
        antes_tablas = await instantanea(ent.banco)

        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()))
        assert r.status_code == 200, r.text
        assert await informes(ent.banco) == []                                   # la vista previa no escribe el informe
        assert (await instantanea(ent.banco)) == antes_tablas                    # ni nada más
        token = r.json()["token"]

        c = await confirmar(token)
        assert c.status_code == 200, c.text[:300]                                # antes: 422 token_invalido
        cuerpo = c.json()
        assert cuerpo["repetida"] is False and cuerpo["resultado"]["global"] == "vinculados_todos"
        assert cuerpo["resultado"]["totales"] == {"vinculados": 3, "ya_estaban": 0, "omitidos": 0, "issues_creados": 3,
                                                  "con_conflicto_incluidos": 0}

        despues = await estado_de_archivos(ent.banco)
        assert all(despues[n][0] and despues[n][1] == "manual" for n in NORMALES)        # vinculados
        assert despues[LARGO][0] is None                                                # el largo SIGUE sin vincular
        assert {n: v[2] for n, v in despues.items()} == {n: v[2] for n, v in antes_estado.items()}   # RUTAS INTACTAS
        assert huella_disco(ent.lib) == antes_disco                                     # bytes, tamaño y fecha
        assert await numero_de("local_aliases", ent.banco) == 0 and await numero_de("asignacion_operaciones", ent.banco) == 0

        guardado = await informes(ent.banco)
        assert len(guardado) == 1                                                       # el informe de siempre, uno
        otra = await confirmar(token)
        assert otra.status_code == 200 and otra.json()["repetida"] is True and otra.json()["resultado"] == cuerpo["resultado"]
        assert await informes(ent.banco) == guardado

    async def test_despues_se_puede_vincular_el_largo_escribiendo_su_numero(self, ent):
        clave, ids, serie = await grupo_con_numero_largo(ent)
        await confirmar((await previsualizar(serie, clave=clave, marcados=[ids[n] for n in NORMALES])).json()["token"])
        r = await previsualizar(serie, clave=clave, marcados=[ids[LARGO]], numeros={ids[LARGO]: "4"})
        c = await confirmar(r.json()["token"])
        assert c.status_code == 200 and c.json()["resultado"]["global"] == "vinculados_todos"
        assert (await estado_de_archivos(ent.banco))[LARGO][0] is not None
