# ruff: noqa: E501, F401, F811
"""Deshacer la vinculación de un archivo (BL-R1a, #253) — pruebas de aceptación sobre Postgres real y ficheros reales en `tmp`.

Contrato: `docs/design/bl-r1-deshacer-vinculacion.md` (§3 y §5, grupos 1–8) y ADR 0014 (Aceptado). Los archivos se vinculan con el
recorrido REAL de «vincular en su sitio» (vista previa y confirmación), así que `metadata.vinculo` es el que escribe el servicio.
Se saltan sin `TEST_DATABASE_URL`. El grupo 9 del contrato (navegador real, sin JS) es de BL-R1b: aquí NO SE EJECUTA.
"""
from __future__ import annotations

import asyncio
import builtins
import hashlib
import io
import json
import os
import re
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text

from tests.test_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    SHA,
    archivos,
    cliente,
    confirmar,
    ent,
    entorno,
    huella_disco,
    instantanea,
    numero_de,
    serie_de_prueba,
    token_de,
    url_bd,
)
from zascarr.api import revision as api_revision
from zascarr.models import File
from zascarr.services import desvinculacion
from zascarr.services.desvinculacion import DesvinculacionDeArchivo, huella_de
from zascarr.services.review import ReviewService
from zascarr.services.tokens_revision import (
    DesvinculacionFirmada,
    crear_token_desvinculacion,
    crear_token_vinculacion,
    verificar_token_desvinculacion,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

PREVIA = "/api/revision/desvinculacion/previsualizar"
DESHACER = "/api/revision/desvinculacion"
F1 = "Flash 01 (1987).cbz"
F2 = "Flash 02 (1987).cbz"


# ── Ayudas ──────────────────────────────────────────────────────────────────────────────────────

async def previa(file_id) -> httpx.Response:
    async with cliente() as c:
        return await c.post(PREVIA, json={"file_id": str(file_id)})


async def deshacer(token: str) -> httpx.Response:
    async with cliente() as c:
        return await c.post(DESHACER, json={"token": token})


async def fila(b, file_id) -> dict:
    async with b.fabrica() as s:
        r = (await s.execute(text(
            "SELECT issue_id, review_dismissed, metadata_source, metadata, file_path, file_name, file_size_bytes, sha256_hash, is_missing "
            "FROM files WHERE id = :i"), {"i": file_id})).mappings().first()
        return dict(r)


async def vinculado(ent, *nombres, serie=None, metadata_source=None, numeros=None):
    """Registra los archivos, los vincula con el recorrido real y devuelve (serie, ids). `metadata_source` previo opcional."""
    serie = serie or await serie_de_prueba(ent)
    ids = await archivos(ent, *nombres)
    if metadata_source is not None:
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata_source = :m"), {"m": metadata_source})
            await s.commit()
    extra = {"numeros": {k: v for k, v in numeros.items()}} if numeros else {}
    r = await api_previa_vinculacion(serie, ids.values(), **extra)
    assert r.status_code == 200 and r.json()["token"], r.text
    c = await confirmar(r.json()["token"])
    assert c.status_code == 200 and c.json()["resultado"]["global"] == "vinculados_todos", c.text
    return serie, ids


async def vinculado_sin_procedencia(ent, *nombres, serie=None, numero="1", metadata=None, metadata_source=None):
    """Archivos con `issue_id` pero SIN `metadata.vinculo`: lo que dejan el importador, «Por revisar» (uno a uno), «organizar»
    (V6a) o una vinculación anterior a 2d. Devuelve (serie, issue_id, ids)."""
    serie = serie or await serie_de_prueba(ent)
    ids = await archivos(ent, *nombres)
    iid = uuid4()
    async with ent.banco.fabrica() as s:
        await s.execute(text("INSERT INTO issues (id, series_id, issue_number, volume, format) VALUES (:i, :s, :n, 1, 'single_issue')"),
                        {"i": iid, "s": serie, "n": numero})
        await s.execute(text("UPDATE files SET issue_id = :i, metadata_source = :m, metadata = CAST(:d AS jsonb)"),
                        {"i": iid, "m": metadata_source, "d": json.dumps(metadata or {"match_status": "matched", "match_score": 0.93,
                                                                                    "notes": "coincidencia por nombre", "candidates": []})})
        await s.commit()
    return serie, iid, ids


async def api_previa_vinculacion(serie, marcados, **extra) -> httpx.Response:
    from tests.test_vinculacion_previa_pg import previsualizar
    return await previsualizar(serie, marcados=list(marcados), **extra)


async def token_desv(file_id) -> str:
    r = await previa(file_id)
    assert r.status_code == 200 and r.json()["token"], r.text
    return r.json()["token"]


def escrituras(b, desde: int) -> list[str]:
    """INSERT/UPDATE/DELETE emitidos desde `desde` (los candados consultivos no cuentan como escritura de datos)."""
    return [q for q in b.sentencias[desde:] if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q, re.I)]


def firmar_desv(fila_, *, issue_id, series_id, vinculo_operacion, ahora=None, operacion=None, **cambios) -> str:
    d = DesvinculacionFirmada(
        file_id=str(cambios.pop("file_id")), issue_id=str(issue_id), series_id=str(series_id),
        vinculo_operacion=str(vinculo_operacion),
        huella=cambios.pop("huella", huella_de(fila_["file_path"], fila_["file_size_bytes"], fila_["sha256_hash"])),
        operacion=str(operacion or uuid4()))
    return crear_token_desvinculacion(d, SECRETO, ahora=ahora)


async def pendientes(ent) -> int:
    async with ent.banco.fabrica() as s:
        return await ReviewService(s).count_pending()


async def issues_de(b) -> list[tuple]:
    async with b.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text(
            "SELECT id::text, series_id::text, issue_number, format::text FROM issues ORDER BY id"))).all()]


# ── Grupo 1: deshacer feliz ─────────────────────────────────────────────────────────────────────

class TestDeshacerFeliz:

    async def test_deshace_y_el_archivo_vuelve_a_por_revisar_sin_tocar_nada_mas(self, ent, monkeypatch):
        serie, ids = await vinculado(ent, F1, metadata_source="comicinfo_xml")
        fid = ids[F1]
        antes = await fila(ent.banco, fid)
        issues_antes = await issues_de(ent.banco)
        disco = huella_disco(ent.lib)
        assert antes["issue_id"] is not None and antes["metadata_source"] == "manual" and "vinculo" in antes["metadata"]
        assert await pendientes(ent) == 0
        vinculo_viejo = antes["metadata"]["vinculo"]

        token = await token_desv(fid)
        intentos: list[str] = []
        raiz = str(ent.lib)

        def vigilado(real):
            def _open(f, *a, **kw):
                if isinstance(f, (str, os.PathLike)) and str(f).startswith(raiz):
                    intentos.append(str(f))
                    raise AssertionError("deshacer no puede abrir ni leer ficheros")
                return real(f, *a, **kw)
            return _open

        def sin_red(*a, **k):
            raise AssertionError("acceso a la red")
        with monkeypatch.context() as m:
            m.setattr(builtins, "open", vigilado(builtins.open))
            m.setattr(io, "open", vigilado(io.open))
            m.setattr(os, "open", vigilado(os.open))
            m.setattr(socket.socket, "connect", sin_red)
            m.setattr(httpx.AsyncHTTPTransport, "handle_async_request", sin_red)
            r = await deshacer(token)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
        c = r.json()
        assert intentos == []
        assert (c["resultado"], c["motivo"], c["file_id"], c["serie_id"], c["numero"]) == ("deshecho", None, str(fid), str(serie), "1")

        despues = await fila(ent.banco, fid)
        assert despues["issue_id"] is None and despues["review_dismissed"] is False
        assert "vinculo" not in despues["metadata"] and despues["metadata"]["match_status"] == "unsorted"
        assert despues["metadata_source"] == "comicinfo_xml"                                   # D8: lo que había
        (entrada,) = despues["metadata"]["vinculo_historial"]
        assert {k: v for k, v in entrada.items() if k != "deshecho"} == vinculo_viejo         # procedencia ÍNTEGRA
        assert entrada["deshecho"]["operacion_id"] == c["operacion_id"] and entrada["deshecho"]["fecha"] == c["fecha"]
        # Ni una columna más de la fila cambió, ni el fichero, ni el Issue (D1: el número creado se conserva).
        for k in ("file_path", "file_name", "file_size_bytes", "sha256_hash", "is_missing"):
            assert despues[k] == antes[k]
        assert huella_disco(ent.lib) == disco                                                  # bytes, tamaño y mtime idénticos
        assert await issues_de(ent.banco) == issues_antes and len(issues_antes) == 1
        assert await pendientes(ent) == 1                                                     # el MISMO filtro de la lista y el menú
        async with ent.banco.fabrica() as s:
            assert [f.id for f in await ReviewService(s).pending_files()] == [fid]

    async def test_el_vinculo_nuevo_guarda_el_metadata_source_previo(self, ent):
        # Criterio 7: cambio aditivo en `_vincular_archivo`; la CLAVE existe aunque el valor previo sea nulo.
        _, ids = await vinculado(ent, F1, metadata_source="tebeosfera")
        previo = (await fila(ent.banco, ids[F1]))["metadata"]["vinculo"]["previo"]
        assert previo == {"match_status": "unsorted", "review_motivo": None, "metadata_source": "tebeosfera"}

    async def test_conserva_el_resto_de_metadata_fusionando(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = metadata || '{\"otra_clave\": 7, \"review_motivo\": \"x\"}'::jsonb"))
            await s.commit()
        await deshacer(await token_desv(fid))
        meta = (await fila(ent.banco, fid))["metadata"]
        assert meta["otra_clave"] == 7 and meta["review_motivo"] == "x"

    @pytest.mark.parametrize("estado", ["unsorted", "matched", "manual", None, "raro"])
    async def test_cualquier_match_status_previo_termina_en_unsorted_y_pendiente(self, ent, estado):
        # R2: nunca «ni vinculado ni pendiente», con los valores posibles de `match_status` (y uno inventado).
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        async with ent.banco.fabrica() as s:
            if estado is None:
                await s.execute(text("UPDATE files SET metadata = metadata - 'match_status'"))
            else:
                await s.execute(text("UPDATE files SET metadata = metadata || jsonb_build_object('match_status', CAST(:e AS text))"),
                                {"e": estado})
            await s.execute(text("UPDATE files SET review_dismissed = true"))      # y descartado: tras deshacer vuelve a verse
            await s.commit()
        assert (await deshacer(await token_desv(fid))).json()["resultado"] == "deshecho"
        assert await pendientes(ent) == 1

    async def test_d8_vinculo_antiguo_sin_metadata_source_previo_restaura_null(self, ent):
        _, ids = await vinculado(ent, F1, metadata_source="comicinfo_xml")
        fid = ids[F1]
        async with ent.banco.fabrica() as s:      # un vínculo ANTERIOR a BL-R1a: `previo` sin la clave `metadata_source`
            await s.execute(text("UPDATE files SET metadata = metadata #- '{vinculo,previo,metadata_source}'"))
            await s.commit()
        assert "metadata_source" not in (await fila(ent.banco, fid))["metadata"]["vinculo"]["previo"]
        await deshacer(await token_desv(fid))
        assert (await fila(ent.banco, fid))["metadata_source"] is None

    async def test_d8_vinculo_nuevo_con_previo_nulo_restaura_null(self, ent):
        _, ids = await vinculado(ent, F1)             # sin `metadata_source` previo
        fid = ids[F1]
        antes = (await fila(ent.banco, fid))
        assert antes["metadata"]["vinculo"]["previo"]["metadata_source"] is None and antes["metadata_source"] == "manual"
        await deshacer(await token_desv(fid))
        assert (await fila(ent.banco, fid))["metadata_source"] is None

    async def test_is_missing_si_se_puede_deshacer(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET is_missing = true, missing_since = now()"))
            await s.commit()
        p = (await previa(fid)).json()
        assert p["puede_deshacer"] is True and p["archivo"]["falta_en_disco"] is True
        assert (await deshacer(p["token"])).json()["resultado"] == "deshecho"
        assert (await fila(ent.banco, fid))["is_missing"] is True                  # la marca de desaparecido NO se toca

    async def test_el_fichero_puede_no_estar_en_disco(self, ent):
        # Deshacer no hace `stat` ni lee nada: funciona aunque el fichero ya no esté.
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        ruta = Path((await fila(ent.banco, fid))["file_path"])
        ruta.unlink()
        assert (await deshacer(await token_desv(fid))).json()["resultado"] == "deshecho"


# ── Vista previa ────────────────────────────────────────────────────────────────────────────────

class TestVistaPrevia:

    async def test_solo_lectura_cero_escrituras_cero_candados_y_cero_ficheros(self, ent, monkeypatch):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        await previa(fid)                                   # calienta el pool
        antes, disco, n = await instantanea(ent.banco), huella_disco(ent.lib), len(ent.banco.sentencias)
        intentos: list[str] = []
        raiz = str(ent.lib)

        def vigilado(real):
            def _open(f, *a, **kw):
                if isinstance(f, (str, os.PathLike)) and str(f).startswith(raiz):
                    intentos.append(str(f))
                    raise AssertionError("la vista previa no puede abrir ficheros")
                return real(f, *a, **kw)
            return _open
        stats: list[str] = []
        real_stat = os.stat

        def espia(ruta, *a, **kw):
            if str(ruta).startswith(raiz):
                stats.append(str(ruta))
            return real_stat(ruta, *a, **kw)

        def sin_red(*a, **k):
            raise AssertionError("acceso a la red")
        with monkeypatch.context() as m:
            m.setattr(builtins, "open", vigilado(builtins.open))
            m.setattr(io, "open", vigilado(io.open))
            m.setattr(os, "open", vigilado(os.open))
            m.setattr(os, "stat", espia)
            m.setattr(socket.socket, "connect", sin_red)
            r = await previa(fid)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert intentos == [] and stats == []
        assert [q for q in ent.banco.sentencias[n:] if not re.match(r"\s*SELECT\b", q, re.I)] == []        # solo SELECT
        assert not any("pg_advisory" in q or "FOR UPDATE" in q.upper() or "FOR SHARE" in q.upper() for q in ent.banco.sentencias[n:])
        assert await instantanea(ent.banco) == antes and huella_disco(ent.lib) == disco

    async def test_contenido_de_la_vista_previa(self, ent):
        serie, ids = await vinculado(ent, F1, F2)
        fid = ids[F1]
        p = (await previa(fid)).json()
        assert p["puede_deshacer"] is True and p["bloqueo"] is None and p["file_id"] == str(fid)
        n = p["numero"]
        assert (n["serie_id"], n["serie_titulo"], n["numero"], n["creado_por_la_vinculacion"]) == (str(serie), "Flash", "1", True)
        assert (n["se_queda_sin_archivos"], n["otros_archivos"], n["lecturas"], n["deseados"], n["deseados_abiertos"]) == (True, 0, 0, 0, 0)
        a = p["archivo"]
        antes = await fila(ent.banco, fid)
        assert (a["ruta"], a["nombre"], a["tamano"], a["sha256"], a["falta_en_disco"]) == (
            antes["file_path"], antes["file_name"], antes["file_size_bytes"], antes["sha256_hash"], False)
        assert p["vinculado_el"] == antes["metadata"]["vinculo"]["fecha"]
        assert "otra operación aparte" in p["aviso"] and "puede cancelarse o fallar" in p["aviso"] and "Por revisar" in p["aviso"]
        assert verificar_token_desvinculacion(p["token"], SECRETO).file_id == str(fid)

    async def test_otros_archivos_lecturas_y_deseados_se_cuentan(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        async with ent.banco.fabrica() as s:
            iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": fid})).scalar_one()
            await s.execute(text("INSERT INTO files (id, issue_id, file_path, file_name, file_format) VALUES (:i, :n, '/otro.cbz', 'otro.cbz', 'cbz')"),
                            {"i": uuid4(), "n": iid})
            await s.execute(text("INSERT INTO reading_progress (id, issue_id, status, current_page) VALUES (:i, :n, 'reading', 3)"),
                            {"i": uuid4(), "n": iid})
            for estado in ("wanted", "imported"):
                await s.execute(text("INSERT INTO wishlist (id, issue_id, status, priority) VALUES (:i, :n, CAST(:e AS wishlist_status), 5)"),
                                {"i": uuid4(), "n": iid, "e": estado})
            await s.commit()
        n = (await previa(fid)).json()["numero"]
        assert (n["otros_archivos"], n["se_queda_sin_archivos"], n["lecturas"], n["deseados"], n["deseados_abiertos"]) == (1, False, 1, 2, 1)

    async def test_vinculo_con_numero_existente_no_creado_por_la_vinculacion(self, ent):
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:
            await s.execute(text("INSERT INTO issues (id, series_id, issue_number, volume, format) VALUES (:i, :s, '1', 1, 'single_issue')"),
                            {"i": uuid4(), "s": serie})
            await s.commit()
        _, ids = await vinculado(ent, F1, serie=serie)
        n = (await previa(ids[F1])).json()["numero"]
        assert n["creado_por_la_vinculacion"] is False

    async def test_archivo_inexistente_es_404_con_su_codigo(self, ent):
        r = await previa(uuid4())
        assert r.status_code == 404 and r.json()["detail"]["codigo"] == "archivo_inexistente"

    async def test_no_vinculado_bloquea_sin_token(self, ent):
        ids = await archivos(ent, F1)
        p = (await previa(ids[F1])).json()
        assert p["puede_deshacer"] is False and p["token"] is None and p["numero"] is None
        assert p["bloqueo"]["codigo"] == "no_vinculado" and "ningún número" in p["bloqueo"]["mensaje"]

    async def test_sin_procedencia_ya_no_bloquea_cualquier_vinculo_se_puede_deshacer(self, ent):
        # BL-R1 (revisión de D9, 2026-10-23): da igual por dónde se vinculó (importador, «Por revisar», «organizar» o antes de 2d).
        _, _, ids = await vinculado_sin_procedencia(ent, F1)
        p = (await previa(ids[F1])).json()
        assert p["puede_deshacer"] is True and p["bloqueo"] is None and p["token"]
        assert p["procedencia"] == "desconocida" and p["vinculado_el"] is None
        assert p["numero"]["numero"] == "1" and p["numero"]["creado_por_la_vinculacion"] is False   # de qué número es, y que no consta que lo creara

    async def test_con_procedencia_registrada_la_vista_previa_lo_dice(self, ent):
        _, ids = await vinculado(ent, F1)
        assert (await previa(ids[F1])).json()["procedencia"] == "registrada"

    async def test_vinculo_incoherente_con_la_serie_del_issue_cuenta_como_procedencia_desconocida(self, ent):
        _, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = jsonb_set(metadata, '{vinculo,serie_id}', to_jsonb(CAST(:o AS text)))"),
                            {"o": str(uuid4())})
            await s.commit()
        p = (await previa(ids[F1])).json()
        assert p["puede_deshacer"] is True and p["procedencia"] == "desconocida" and p["token"]

    @pytest.mark.parametrize("vinculo", ["null", '"texto"', "[]", "{}", '{"operacion_id": "no-uuid", "serie_id": "x"}'])
    async def test_vinculo_malformado_cuenta_como_procedencia_desconocida_sin_romper(self, ent, vinculo):
        _, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = jsonb_set(metadata, '{vinculo}', CAST(:v AS jsonb))"), {"v": vinculo})
            await s.commit()
        r = await previa(ids[F1])
        assert r.status_code == 200 and r.json()["puede_deshacer"] is True and r.json()["procedencia"] == "desconocida" and r.json()["token"]

    @pytest.mark.parametrize("estado", ["preparada", "confirmada"])
    async def test_asignacion_viva_bloquea_en_curso(self, ent, estado):
        serie, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                f"mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('{estado}' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids[F1], "s": serie, "sha": SHA})
            await s.commit()
        p = (await previa(ids[F1])).json()
        assert p["bloqueo"]["codigo"] == "en_curso" and p["token"] is None

    async def test_asignacion_ya_terminada_no_bloquea(self, ent):
        serie, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('limpiada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids[F1], "s": serie, "sha": SHA})
            await s.commit()
        assert (await previa(ids[F1])).json()["puede_deshacer"] is True

    async def test_peticion_con_campos_de_mas_o_id_invalido_es_422(self, ent):
        async with cliente() as c:
            assert (await c.post(PREVIA, json={"file_id": str(uuid4()), "x": 1})).status_code == 422
            assert (await c.post(PREVIA, json={"file_id": "no-es-uuid"})).status_code == 422
            assert (await c.post(PREVIA, json={})).status_code == 422


# ── Token y petición ────────────────────────────────────────────────────────────────────────────

class TestToken:

    async def test_un_token_de_vincular_no_sirve_para_deshacer_ni_al_reves(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, F1)
        r = await api_previa_vinculacion(serie, ids.values())
        vinc = r.json()["token"]
        assert (await deshacer(vinc)).json()["detail"]["codigo"] == "token_invalido"
        _, ids2 = await vinculado(ent, F2, serie=serie)
        desv = await token_desv(ids2[F2])
        c = await confirmar(desv)
        assert c.status_code == 422 and c.json()["detail"]["codigo"] == "token_invalido"

    @pytest.mark.parametrize("token", ["", "basura", "a.b", "x" * 50])
    async def test_token_invalido_o_manipulado_es_422_sin_escribir(self, ent, token):
        _, ids = await vinculado(ent, F1)
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        r = await deshacer(token)
        assert r.status_code == 422
        assert escrituras(ent.banco, n) == [] and await instantanea(ent.banco) == antes

    async def test_token_demasiado_largo_o_campos_de_mas_es_422(self, ent):
        async with cliente() as c:
            assert (await c.post(DESHACER, json={"token": "x" * 5000})).status_code == 422
            assert (await c.post(DESHACER, json={"token": "x", "file_id": str(uuid4())})).status_code == 422

    async def test_token_manipulado_un_caracter_no_vale(self, ent):
        _, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        malo = t[:-1] + ("0" if t[-1] != "0" else "1")
        assert (await deshacer(malo)).status_code == 422
        assert (await fila(ent.banco, ids[F1]))["issue_id"] is not None

    async def test_sin_clave_del_servidor_503(self, ent, monkeypatch):
        _, ids = await vinculado(ent, F1)
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=""))
        assert (await previa(ids[F1])).status_code == 503
        assert (await deshacer("x")).status_code == 503

    async def test_caducado_sin_comprobante_es_410_y_no_escribe(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        f = await fila(ent.banco, fid)
        v = f["metadata"]["vinculo"]
        viejo = firmar_desv(f, file_id=fid, issue_id=f["issue_id"], series_id=v["serie_id"], vinculo_operacion=v["operacion_id"],
                            ahora=time.time() - 3600)
        antes = await instantanea(ent.banco)
        r = await deshacer(viejo)
        assert r.status_code == 410 and r.json()["detail"]["codigo"] == "token_caducado"
        assert r.json()["detail"]["puede_haberse_aplicado"] is False
        assert await instantanea(ent.banco) == antes

    async def test_caducado_con_comprobante_devuelve_el_mismo_resultado(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        f = await fila(ent.banco, fid)
        v = f["metadata"]["vinculo"]
        op = uuid4()
        viejo = firmar_desv(f, file_id=fid, issue_id=f["issue_id"], series_id=v["serie_id"], vinculo_operacion=v["operacion_id"],
                            ahora=time.time() - 3600, operacion=op)
        # Se aplica con el token VIGENTE equivalente (misma operación): hace falta firmarlo ahora.
        vigente = firmar_desv(f, file_id=fid, issue_id=f["issue_id"], series_id=v["serie_id"], vinculo_operacion=v["operacion_id"],
                              operacion=op)
        primero = (await deshacer(vigente)).json()
        r = await deshacer(viejo)
        assert r.status_code == 200 and r.json()["resultado"] == "ya_deshecho" and r.json()["fecha"] == primero["fecha"]


# ── Grupo 2: idempotencia y recuperación ────────────────────────────────────────────────────────

class TestIdempotencia:

    async def test_repetir_el_mismo_token_devuelve_lo_mismo_y_no_escribe(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        primero = (await deshacer(t)).json()
        despues, n = await fila(ent.banco, fid), len(ent.banco.sentencias)
        segundo = await deshacer(t)
        assert segundo.status_code == 200
        s = segundo.json()
        assert s["resultado"] == "ya_deshecho" and s["operacion_id"] == primero["operacion_id"]
        assert (s["fecha"], s["serie_id"], s["numero"], s["file_id"]) == (primero["fecha"], primero["serie_id"], primero["numero"], primero["file_id"])
        assert escrituras(ent.banco, n) == []
        assert await fila(ent.banco, fid) == despues
        assert len(despues["metadata"]["vinculo_historial"]) == 1

    async def test_repetir_sigue_siendo_ya_deshecho_aunque_el_archivo_se_vuelva_a_vincular(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        await deshacer(t)
        r = await api_previa_vinculacion(serie, [fid], numeros={fid: "7"})
        await confirmar(r.json()["token"])
        assert (await fila(ent.banco, fid))["issue_id"] is not None
        assert (await deshacer(t)).json()["resultado"] == "ya_deshecho"            # el token viejo NO deshace el vínculo nuevo
        assert (await fila(ent.banco, fid))["issue_id"] is not None

    async def test_fallo_antes_del_commit_no_cambia_nada_y_se_puede_repetir(self, ent, monkeypatch):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        antes = await instantanea(ent.banco)

        async def falla():
            raise RuntimeError("fallo inesperado con filas bloqueadas")
        monkeypatch.setattr(DesvinculacionDeArchivo, "_gancho_con_filas_bloqueadas", staticmethod(falla))
        r = await deshacer(t)
        assert r.status_code == 500 and r.json()["detail"]["codigo"] == "error_inesperado"
        assert "fallo inesperado" not in r.text and str(fid) not in r.text                   # sin detalles internos
        assert await instantanea(ent.banco) == antes
        monkeypatch.undo()
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        assert (await deshacer(t)).json()["resultado"] == "deshecho"

    async def test_el_where_del_update_es_la_ultima_defensa_si_la_fila_cambia_dentro_de_la_transaccion(self, ent, monkeypatch):
        # Defensa en profundidad: con la fila bloqueada nadie más puede cambiarla, pero el UPDATE comprueba el vínculo en su
        # WHERE y exige `rowcount == 1`. Se simula un cambio DENTRO de la misma transacción, entre la comprobación y el UPDATE.
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        antes = await fila(ent.banco, fid)
        real = desvinculacion._asignacion_viva

        async def viva_y_cambia(db, file_id):
            r = await real(db, file_id)
            await db.execute(text("UPDATE files SET issue_id = NULL WHERE id = :f"), {"f": file_id})
            return r
        monkeypatch.setattr(desvinculacion, "_asignacion_viva", viva_y_cambia)
        r = await deshacer(t)
        assert r.status_code == 500 and r.json()["detail"]["codigo"] == "error_inesperado"
        assert await fila(ent.banco, fid) == antes                                       # rollback completo

    async def test_fallo_incierto_tras_pedir_el_commit_se_resuelve_releyendo_la_fila(self, ent, monkeypatch):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        from sqlalchemy.ext.asyncio import AsyncSession
        real = AsyncSession.commit
        pedido = {"n": 0}

        async def commit_y_cae(self):
            pedido["n"] += 1
            await real(self)
            if pedido["n"] == 1:
                raise ConnectionError("se perdió la respuesta del commit")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_cae)
        r = await deshacer(t)
        assert r.status_code == 503 and r.json()["detail"]["codigo"] == "resultado_incierto"
        assert "no se ha cambiado nada" not in r.text.lower()                               # NUNCA «no se ha cambiado nada»
        assert (await fila(ent.banco, fid))["issue_id"] is None                              # (de hecho sí se aplicó)
        monkeypatch.undo()
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        r2 = await deshacer(t)
        assert r2.status_code == 200 and r2.json()["resultado"] == "ya_deshecho"
        assert len((await fila(ent.banco, fid))["metadata"]["vinculo_historial"]) == 1

    async def test_fallo_incierto_cuando_no_se_aplico_la_repeticion_lo_aplica(self, ent, monkeypatch):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        from sqlalchemy.ext.asyncio import AsyncSession
        pedido = {"n": 0}

        async def commit_que_cae_antes(self):
            pedido["n"] += 1
            if pedido["n"] == 1:
                raise ConnectionError("cayó antes de confirmar")
            return await real(self)
        real = AsyncSession.commit
        monkeypatch.setattr(AsyncSession, "commit", commit_que_cae_antes)
        r = await deshacer(t)
        assert r.status_code == 503 and r.json()["detail"]["codigo"] == "resultado_incierto"
        assert (await fila(ent.banco, fid))["issue_id"] is not None                          # no se aplicó
        monkeypatch.undo()
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        assert (await deshacer(t)).json()["resultado"] == "deshecho"


# ── Grupo 3: cambios entre la vista previa y la confirmación ────────────────────────────────────

class TestCambioDesdeLaVistaPrevia:

    async def _caso(self, ent, sql: str, params=None):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        async with ent.banco.fabrica() as s:
            await s.execute(text(sql), {"f": fid, **(params or {})})
            await s.commit()
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        r = await deshacer(t)
        assert r.status_code == 200, r.text
        c = r.json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "cambio_desde_la_vista_previa"), c
        assert escrituras(ent.banco, n) == [] and await instantanea(ent.banco) == antes        # sin escribir ni pisar nada
        return fid

    async def test_otra_ruta(self, ent):
        await self._caso(ent, "UPDATE files SET file_path = file_path || '.mov' WHERE id = :f")

    async def test_otro_tamano(self, ent):
        await self._caso(ent, "UPDATE files SET file_size_bytes = coalesce(file_size_bytes, 0) + 1 WHERE id = :f")

    async def test_otro_hash(self, ent):
        await self._caso(ent, "UPDATE files SET sha256_hash = :h WHERE id = :f", {"h": "b" * 64})

    async def test_otra_operacion_de_vinculo(self, ent):
        await self._caso(ent, "UPDATE files SET metadata = jsonb_set(metadata, '{vinculo,operacion_id}', to_jsonb(CAST(:o AS text))) WHERE id = :f",
                         {"o": str(uuid4())})

    async def test_reasignado_a_otro_numero(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        otro = uuid4()
        async with ent.banco.fabrica() as s:
            await s.execute(text("INSERT INTO issues (id, series_id, issue_number, volume, format) VALUES (:i, :s, '9', 1, 'single_issue')"),
                            {"i": otro, "s": serie})
            await s.execute(text("UPDATE files SET issue_id = :i WHERE id = :f"), {"i": otro, "f": fid})
            await s.commit()
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "cambio_desde_la_vista_previa")
        assert str((await fila(ent.banco, fid))["issue_id"]) == str(otro)

    async def test_ya_no_esta_vinculado(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET issue_id = NULL WHERE id = :f"), {"f": fid})
            await s.commit()
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "no_vinculado") and "ningún número" in c["mensaje"]

    async def test_el_archivo_ya_no_existe(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM files WHERE id = :f"), {"f": fid})
            await s.commit()
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "archivo_inexistente")

    async def test_la_serie_ya_no_existe(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series WHERE id = :s"), {"s": serie})
            await s.commit()
        c = (await deshacer(t)).json()
        assert c["resultado"] == "omitido" and c["motivo"] in ("no_vinculado", "cambio_desde_la_vista_previa")
        assert (await fila(ent.banco, fid))["issue_id"] is None
        assert "vinculo_historial" not in (await fila(ent.banco, fid))["metadata"]           # no se inventa un comprobante

    async def test_asignacion_viva_aparecida_despues_de_la_vista_previa(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": fid, "s": serie, "sha": SHA})
            await s.commit()
        antes = await fila(ent.banco, fid)
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "en_curso")
        assert await fila(ent.banco, fid) == antes

    async def test_vinculo_quitado_a_mano_es_cambio_y_no_se_inventa_nada(self, ent):
        await self._caso(ent, "UPDATE files SET metadata = metadata - 'vinculo' WHERE id = :f")


# ── Grupo 4: concurrencia ───────────────────────────────────────────────────────────────────────

class TestConcurrencia:

    async def test_doble_envio_simultaneo_deshace_una_vez_y_repite_la_otra(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        rs = await asyncio.gather(*(deshacer(t) for _ in range(6)))
        assert [r.status_code for r in rs] == [200] * 6, [r.text for r in rs]
        resultados = sorted(r.json()["resultado"] for r in rs)
        assert resultados == ["deshecho"] + ["ya_deshecho"] * 5
        assert len({r.json()["fecha"] for r in rs}) == 1
        assert len((await fila(ent.banco, fid))["metadata"]["vinculo_historial"]) == 1

    async def test_dos_vistas_previas_dos_operaciones_solo_una_deshace(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t1, t2 = await token_desv(fid), await token_desv(fid)
        rs = await asyncio.gather(deshacer(t1), deshacer(t2))
        assert all(r.status_code == 200 for r in rs), [r.text for r in rs]
        estados = sorted((r.json()["resultado"], r.json()["motivo"]) for r in rs)
        assert estados == [("deshecho", None), ("omitido", "no_vinculado")]
        assert len((await fila(ent.banco, fid))["metadata"]["vinculo_historial"]) == 1

    async def test_deshacer_frente_a_vincular_el_mismo_archivo_no_interbloquea_y_queda_coherente(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        from tests.test_vinculacion_pg import firmar
        t_desv = await token_desv(fid)
        t_vinc = await firmar(ent, serie, [(fid, "1")])
        rs = await asyncio.gather(deshacer(t_desv), confirmar(t_vinc))
        assert [r.status_code for r in rs] == [200, 200], [r.text for r in rs]
        f = await fila(ent.banco, fid)
        historial = f["metadata"].get("vinculo_historial", [])
        if f["issue_id"] is None:                                    # ganó deshacer y el vincular no encontró nada que hacer / falló
            assert "vinculo" not in f["metadata"] and len(historial) == 1
        else:                                                        # vinculó DESPUÉS de deshacer, o deshacer se omitió
            assert "vinculo" in f["metadata"]
        assert not (f["issue_id"] is None and "vinculo" in f["metadata"])         # nunca «ni vinculado ni sin procedencia»
        assert not (f["issue_id"] is not None and "vinculo" not in f["metadata"])

    async def test_deshacer_frente_a_borrar_la_serie_espera_al_candado_de_la_serie(self, ent, monkeypatch):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        orden: list[str] = []

        async def retener():
            orden.append("filas bloqueadas")
            await asyncio.sleep(0.6)
            orden.append("fin retención")
        monkeypatch.setattr(DesvinculacionDeArchivo, "_gancho_con_filas_bloqueadas", staticmethod(retener))

        async def borrar():
            while "filas bloqueadas" not in orden:
                await asyncio.sleep(0.02)
            async with ent.banco.fabrica() as s:
                await s.execute(text("DELETE FROM series WHERE id = :s"), {"s": serie})
                await s.commit()
            orden.append("serie borrada")
        r, _ = await asyncio.gather(deshacer(t), borrar())
        assert r.status_code == 200 and r.json()["resultado"] == "deshecho", r.text
        assert orden == ["filas bloqueadas", "fin retención", "serie borrada"]        # el borrado esperó (serie FOR SHARE)
        f = await fila(ent.banco, fid)
        assert f["issue_id"] is None and len(f["metadata"]["vinculo_historial"]) == 1

    async def test_deshacer_espera_a_una_edicion_concurrente_de_la_fila(self, ent):
        # El candado del archivo (`FOR UPDATE`): una escritura concurrente sobre la misma fila no se pierde ni se pisa.
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        t = await token_desv(fid)
        async with ent.banco.fabrica() as otra:
            await otra.execute(text("SELECT id FROM files WHERE id = :f FOR UPDATE"), {"f": fid})
            tarea = asyncio.create_task(deshacer(t))
            await asyncio.sleep(0.4)
            assert not tarea.done()                                                   # bloqueada esperando la fila
            await otra.execute(text("UPDATE files SET metadata = metadata || '{\"nota\": 1}'::jsonb WHERE id = :f"), {"f": fid})
            await otra.commit()
        r = await asyncio.wait_for(tarea, 10)
        assert r.json()["resultado"] == "deshecho"
        meta = (await fila(ent.banco, fid))["metadata"]
        assert meta["nota"] == 1 and "vinculo" not in meta                            # la escritura ajena sobrevive

    async def test_sin_interbloqueos_en_una_tanda_mixta(self, ent):
        serie = await serie_de_prueba(ent)
        nombres = [f"Flash {i:02d} (1987).cbz" for i in range(1, 7)]
        _, ids = await vinculado(ent, *nombres, serie=serie)
        tokens = [await token_desv(i) for i in ids.values()]
        rs = await asyncio.gather(*(deshacer(t) for t in tokens), *(deshacer(t) for t in tokens))
        assert all(r.status_code == 200 for r in rs), [r.text for r in rs if r.status_code != 200]
        assert sorted(r.json()["resultado"] for r in rs) == ["deshecho"] * 6 + ["ya_deshecho"] * 6
        assert await pendientes(ent) == 6


# ── Grupo 5: cadena ─────────────────────────────────────────────────────────────────────────────

class TestCadena:

    async def test_vincular_deshacer_vincular_a_otro_numero_y_deshacer_otra_vez(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        primero = (await fila(ent.banco, fid))["metadata"]["vinculo"]
        r1 = (await deshacer(await token_desv(fid))).json()
        assert r1["resultado"] == "deshecho" and await numero_de("issues", ent.banco) == 1          # D1: el número se conserva
        # Vuelve a vincular por el recorrido existente, a otro número.
        rv = await api_previa_vinculacion(serie, [fid], numeros={fid: "9"})
        assert rv.status_code == 200 and rv.json()["token"], rv.text
        assert (await confirmar(rv.json()["token"])).json()["resultado"]["global"] == "vinculados_todos"
        f = await fila(ent.banco, fid)
        v2 = f["metadata"]["vinculo"]
        assert v2["numero"] == "9" and v2["operacion_id"] != primero["operacion_id"] and f["issue_id"] is not None
        assert f["metadata"]["vinculo_historial"][0]["numero"] == "1"                              # sin pérdida
        assert await numero_de("issues", ent.banco) == 2 and f["metadata"]["match_status"] == "unsorted"
        r2 = (await deshacer(await token_desv(fid))).json()
        assert r2["resultado"] == "deshecho" and r2["numero"] == "9"
        h = (await fila(ent.banco, fid))["metadata"]["vinculo_historial"]
        assert [e["numero"] for e in h] == ["1", "9"]
        assert [e["deshecho"]["operacion_id"] for e in h] == [r1["operacion_id"], r2["operacion_id"]]
        assert await numero_de("issues", ent.banco) == 2                                           # ninguno se retira

    async def test_el_numero_conservado_se_puede_reutilizar_al_volver_a_vincular(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        await deshacer(await token_desv(fid))
        rv = await api_previa_vinculacion(serie, [fid])
        c = (await confirmar(rv.json()["token"])).json()
        assert c["resultado"]["archivos"][0]["issue_creado"] is False and await numero_de("issues", ent.banco) == 1


# ── Grupo 6: el historial no se pisa ────────────────────────────────────────────────────────────

class TestHistorialIntacto:

    async def test_los_demas_escritores_de_metadata_no_borran_el_historial(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        await deshacer(await token_desv(fid))
        historial = (await fila(ent.banco, fid))["metadata"]["vinculo_historial"]
        from zascarr.services.importer import _reenlazar_fila
        from zascarr.services.tagger import TaggerService
        async with ent.banco.fabrica() as s:
            f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
            # tagger: marca de etiquetado (fusión sobre lo leído)
            ctx = SimpleNamespace(huella=lambda: {})
            st = SimpleNamespace(st_size=1, st_mtime_ns=1)
            TaggerService._poner_marca(SimpleNamespace(), f, ctx, st, "x" * 64, "etiquetado")
            # importer: reenlaza la fila de un fichero que reaparece (limpia solo `comicinfo_*`)
            f.original_sha256 = "c" * 64
            await _reenlazar_fila(f, SimpleNamespace(sha256="c" * 64), Path(f.file_path))
            await s.commit()
        meta = (await fila(ent.banco, fid))["metadata"]
        assert meta["vinculo_historial"] == historial and meta["match_status"] == "unsorted"

    async def test_review_service_al_colisionar_edicion_no_borra_el_historial(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        await deshacer(await token_desv(fid))
        historial = (await fila(ent.banco, fid))["metadata"]["vinculo_historial"]
        async with ent.banco.fabrica() as s:
            f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
            f.metadata_ = {**(f.metadata_ or {}), "review_motivo": "colision"}       # el patrón de `review.py`
            await s.commit()
        assert (await fila(ent.banco, fid))["metadata"]["vinculo_historial"] == historial

    async def test_vincular_de_nuevo_conserva_el_historial_previo(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        await deshacer(await token_desv(fid))
        historial = (await fila(ent.banco, fid))["metadata"]["vinculo_historial"]
        rv = await api_previa_vinculacion(serie, [fid], numeros={fid: "4"})
        await confirmar(rv.json()["token"])
        assert (await fila(ent.banco, fid))["metadata"]["vinculo_historial"] == historial


# ── Grupo 7: efectos colaterales ────────────────────────────────────────────────────────────────

# ── Grupo 10: vínculos SIN procedencia (BL-R1, revisión de D9, 2026-10-23) ─────────────────────────

class TestSinProcedencia:
    """«Desvincular debería ser posible desde cualquier sitio, se vinculara como se vinculara»: importador, «Por revisar» (uno a
    uno), «organizar» (V6a) o una vinculación anterior a 2d. Sin `metadata.vinculo` no hay procedencia que restaurar, pero sí
    un estado ACTUAL que firmar (`issue_id` + huella) y una entrada de historial que lo deja dicho."""

    async def test_deshace_un_vinculo_del_importador_y_lo_deja_dicho_en_el_historial(self, ent):
        serie, iid, ids = await vinculado_sin_procedencia(ent, F1, metadata_source="comicvine")
        fid = ids[F1]
        antes = await fila(ent.banco, fid)
        disco, issues_antes = huella_disco(ent.lib), await issues_de(ent.banco)

        c = (await deshacer(await token_desv(fid))).json()
        assert (c["resultado"], c["motivo"], c["serie_id"], c["numero"]) == ("deshecho", None, str(serie), "1")

        despues = await fila(ent.banco, fid)
        assert despues["issue_id"] is None and despues["review_dismissed"] is False
        assert despues["metadata"]["match_status"] == "unsorted" and "vinculo" not in despues["metadata"]
        assert despues["metadata_source"] is None                                  # D8: no consta lo anterior → NULL
        assert despues["metadata"]["match_score"] == 0.93                          # fusión: el resto de metadata no se pierde
        (entrada,) = despues["metadata"]["vinculo_historial"]
        assert entrada["procedencia"] == "desconocida"
        assert (entrada["serie_id"], entrada["issue_id"], entrada["numero"]) == (str(serie), str(iid), "1")
        assert entrada["previo"] == {"match_status": "matched", "metadata_source": "comicvine"}     # lo que había, como evidencia
        assert entrada["deshecho"]["operacion_id"] == c["operacion_id"] and entrada["deshecho"]["fecha"] == c["fecha"]
        for k in ("file_path", "file_name", "file_size_bytes", "sha256_hash", "is_missing"):
            assert despues[k] == antes[k], k
        assert huella_disco(ent.lib) == disco and await issues_de(ent.banco) == issues_antes      # ni el fichero ni el Issue (D1)
        assert await pendientes(ent) == 1                                                             # vuelve a «Por revisar»

    async def test_repetir_el_mismo_token_devuelve_lo_mismo_y_no_escribe(self, ent):
        _, _, ids = await vinculado_sin_procedencia(ent, F1)
        t = await token_desv(ids[F1])
        primero = (await deshacer(t)).json()
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        segundo = (await deshacer(t)).json()
        assert (primero["resultado"], segundo["resultado"]) == ("deshecho", "ya_deshecho")
        assert escrituras(ent.banco, n) == [] and await instantanea(ent.banco) == antes
        assert len((await fila(ent.banco, ids[F1]))["metadata"]["vinculo_historial"]) == 1

    async def test_un_vinculo_no_valido_se_conserva_como_evidencia_y_se_quita(self, ent):
        _, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = jsonb_set(metadata, '{vinculo,serie_id}', to_jsonb(CAST(:o AS text)))"),
                            {"o": str(uuid4())})
            await s.commit()
        c = (await deshacer(await token_desv(ids[F1]))).json()
        assert c["resultado"] == "deshecho"
        despues = await fila(ent.banco, ids[F1])
        assert "vinculo" not in despues["metadata"]
        (entrada,) = despues["metadata"]["vinculo_historial"]
        assert entrada["procedencia"] == "desconocida" and entrada["vinculo_no_valido"]["operacion_id"]

    async def test_si_aparece_una_procedencia_despues_de_la_vista_previa_es_un_cambio(self, ent):
        # Se vio «sin procedencia» y, antes de confirmar, alguien vinculó el archivo con el recorrido de «vincular en su sitio».
        serie, iid, ids = await vinculado_sin_procedencia(ent, F1)
        t = await token_desv(ids[F1])
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = metadata || jsonb_build_object('vinculo', jsonb_build_object("
                                 "'operacion_id', CAST(:o AS text), 'serie_id', CAST(:s AS text), 'numero', '1'))"),
                            {"o": str(uuid4()), "s": str(serie)})
            await s.commit()
        antes = await fila(ent.banco, ids[F1])
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "cambio_desde_la_vista_previa")
        assert await fila(ent.banco, ids[F1]) == antes

    async def test_si_se_reasigna_a_otro_numero_despues_de_la_vista_previa_es_un_cambio(self, ent):
        serie, _, ids = await vinculado_sin_procedencia(ent, F1)
        t = await token_desv(ids[F1])
        otro = uuid4()
        async with ent.banco.fabrica() as s:
            await s.execute(text("INSERT INTO issues (id, series_id, issue_number, volume, format) VALUES (:i, :s, '9', 1, 'single_issue')"),
                            {"i": otro, "s": serie})
            await s.execute(text("UPDATE files SET issue_id = :i"), {"i": otro})
            await s.commit()
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "cambio_desde_la_vista_previa")
        assert str((await fila(ent.banco, ids[F1]))["issue_id"]) == str(otro)

    async def test_si_el_numero_cambia_de_serie_despues_de_la_vista_previa_es_un_cambio(self, ent):
        serie, iid, ids = await vinculado_sin_procedencia(ent, F1)
        t = await token_desv(ids[F1])
        otra = await serie_de_prueba(ent, "Otra", 1990)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE issues SET series_id = :s WHERE id = :i"), {"s": otra, "i": iid})
            await s.commit()
        c = (await deshacer(t)).json()
        assert (c["resultado"], c["motivo"]) == ("omitido", "cambio_desde_la_vista_previa")
        assert (await fila(ent.banco, ids[F1]))["issue_id"] is not None

    async def test_una_asignacion_viva_sigue_bloqueando_aunque_no_haya_procedencia(self, ent):
        serie, _, ids = await vinculado_sin_procedencia(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids[F1], "s": serie, "sha": SHA})
            await s.commit()
        p = (await previa(ids[F1])).json()
        assert p["puede_deshacer"] is False and p["bloqueo"]["codigo"] == "en_curso" and p["token"] is None

    async def test_un_token_de_un_vinculo_sin_procedencia_no_sirve_para_otro_archivo(self, ent):
        _, _, ids = await vinculado_sin_procedencia(ent, F1, F2)
        t = await token_desv(ids[F1])
        assert (await fila(ent.banco, ids[F2]))["issue_id"] is not None
        await deshacer(t)
        assert (await fila(ent.banco, ids[F2]))["issue_id"] is not None          # solo se deshizo el suyo

    async def test_el_importador_no_lo_vuelve_a_vincular_un_archivo_desvinculado_es_un_duplicado_de_si_mismo(self, ent):
        """El riesgo de abrir D9: que un vínculo AUTOMÁTICO desvinculado vuelva a quedar vinculado en el siguiente ciclo. El
        importador solo crea filas para contenido NUEVO; con el mismo contenido y el fichero presente, el archivo ya
        registrado cuenta como copia presente y se descarta como duplicado: nunca se re-vincula."""
        from zascarr.core.importer_triage import sha256_streaming
        from zascarr.services.importer import _triage_and_match

        serie, _, ids = await vinculado_sin_procedencia(ent, F1)
        ruta = Path((await fila(ent.banco, ids[F1]))["file_path"])
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET sha256_hash = :h WHERE id = :f"), {"h": sha256_streaming(ruta), "f": ids[F1]})
            await s.commit()
        assert (await deshacer(await token_desv(ids[F1]))).json()["resultado"] == "deshecho"

        async with ent.banco.fabrica() as s:
            resultado = await _triage_and_match(s, ruta)
        assert resultado.duplicate_of == F1 and resultado.result is None and resultado.recuperar is None
        assert (await fila(ent.banco, ids[F1]))["issue_id"] is None


class TestEfectosColaterales:

    async def test_el_numero_sin_archivos_reaparece_como_hueco_y_las_lecturas_no_se_tocan(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        async with ent.banco.fabrica() as s:
            iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": fid})).scalar_one()
            await s.execute(text("INSERT INTO reading_progress (id, issue_id, status, current_page) VALUES (:i, :n, 'reading', 3)"),
                            {"i": uuid4(), "n": iid})
            await s.commit()
        lecturas_antes = await instantanea(ent.banco)
        await deshacer(await token_desv(fid))
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id = :i"), {"i": iid})).scalar_one() == 0   # hueco
            assert (await s.execute(text("SELECT status::text, current_page FROM reading_progress"))).all() == [("reading", 3)]
        despues = await instantanea(ent.banco)
        assert despues["issues"] == lecturas_antes["issues"] and despues["series"] == lecturas_antes["series"]

    async def test_un_deseado_abierto_de_ese_numero_no_cambia(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        async with ent.banco.fabrica() as s:
            iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": fid})).scalar_one()
            await s.execute(text("INSERT INTO wishlist (id, issue_id, status, priority) VALUES (:i, :n, 'wanted', 5)"),
                            {"i": uuid4(), "n": iid})
            await s.commit()
        antes = (await instantanea(ent.banco))["wishlist"]
        await deshacer(await token_desv(fid))
        assert (await instantanea(ent.banco))["wishlist"] == antes

    async def test_otro_archivo_del_mismo_numero_sigue_vinculado(self, ent):
        _, ids = await vinculado(ent, F1)
        fid = ids[F1]
        otro = uuid4()
        async with ent.banco.fabrica() as s:
            iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": fid})).scalar_one()
            await s.execute(text("INSERT INTO files (id, issue_id, file_path, file_name, file_format) VALUES (:i, :n, '/otro.cbz', 'otro.cbz', 'cbz')"),
                            {"i": otro, "n": iid})
            await s.commit()
        assert (await deshacer(await token_desv(fid))).json()["resultado"] == "deshecho"
        assert (await fila(ent.banco, otro))["issue_id"] == iid

    async def test_solo_cambia_la_fila_de_ese_archivo(self, ent):
        _, ids = await vinculado(ent, F1, F2)
        antes = await fila(ent.banco, ids[F2])
        await deshacer(await token_desv(ids[F1]))
        assert await fila(ent.banco, ids[F2]) == antes
