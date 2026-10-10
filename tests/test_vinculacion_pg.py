# ruff: noqa: E501, F401, F811
"""`POST /api/revision/vinculacion` (rebanada 2d) — pruebas de aceptación sobre Postgres real y ficheros reales en `tmp`.

Contrato: `docs/design/rebanada-2-elegir-serie-y-vincular.md` («Contrato técnico de 2d»). Criterios de aceptación, no
garantías ya demostradas: la concurrencia se OBSERVA (si aparece un interbloqueo donde se esperaba ninguno, se
informa, no se fuerza el orden). Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import builtins
import io
import json
import os
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_vinculacion_previa_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    archivos,
    cliente,
    entorno,
    escrituras,
    huella_disco,
    instantanea,
    por_nombre_json,
    previsualizar,
    serie_de_prueba,
    url_bd,
)
from tests.test_vinculacion_previa_pg import (
    RUTA as RUTA_PREVIA,
)
from zascarr.api import revision as api_revision
from zascarr.models import File, FileFormat, Issue, IssueFormat
from zascarr.services import vinculacion
from zascarr.services.tokens_revision import (
    PROPOSITO_ALTA,
    ArchivoFirmado,
    VinculacionFirmada,
    crear_token,
    crear_token_vinculacion,
    verificar_token_vinculacion,
)
from zascarr.services.vinculacion import VinculacionDeArchivos

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

RUTA = "/api/revision/vinculacion"
SHA = "a" * 64


@pytest.fixture
async def ent(entorno, monkeypatch):
    monkeypatch.setattr(vinculacion, "get_settings", lambda: SimpleNamespace(library_path=entorno.lib))
    return entorno


async def post(ruta: str, cuerpo: dict) -> httpx.Response:
    async with cliente() as c:
        return await c.post(ruta, json=cuerpo)


async def confirmar(token: str) -> httpx.Response:
    return await post(RUTA, {"token": token})


async def token_de(serie, marcados, **extra) -> str:
    r = await previsualizar(serie, marcados=list(marcados), **extra)
    assert r.status_code == 200 and r.json()["token"], r.text
    return r.json()["token"]


async def firmar(ent, serie, items, *, clave=CLAVE, ahora=None, **kw) -> str:
    """Un token `vincular` a mano: items = [(id_archivo, número, formato, conflictos)] con la huella REAL de cada archivo."""
    firmados = []
    async with ent.banco.fabrica() as s:
        for fid, numero, *resto in items:
            formato = resto[0] if resto else "single_issue"
            conflictos = tuple(resto[1]) if len(resto) > 1 else ()
            ruta = (await s.execute(text("SELECT file_path FROM files WHERE id = :i"), {"i": fid})).scalar_one()
            st = os.stat(ruta)
            firmados.append(ArchivoFirmado(str(fid), numero, formato, st.st_size, st.st_mtime_ns, conflictos))
    return crear_token_vinculacion(VinculacionFirmada(clave, str(serie), str(uuid4()), tuple(firmados)), SECRETO,
                                   ahora=ahora, **kw)


async def numero_de(tabla: str, b) -> int:
    async with b.fabrica() as s:
        return (await s.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar_one()


async def estado_de_archivos(b) -> dict[str, tuple]:
    async with b.fabrica() as s:
        return {n: (str(i) if i else None, ms, p) for n, i, ms, p in (await s.execute(text(
            "SELECT file_name, issue_id, metadata_source, file_path FROM files"))).all()}


async def informes(b) -> list[tuple]:
    async with b.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text(
            "SELECT operacion_id::text, series_id::text, resultado, token_hasta, creada FROM vinculacion_operaciones "
            "ORDER BY creada"))).all()]


def por_id(r: httpx.Response) -> dict[str, dict]:
    return {a["id"]: a for a in r.json()["resultado"]["archivos"]}


# ── Ejecución ───────────────────────────────────────────────────────────────────────────────────

class TestEjecucion:

    async def test_vincula_en_su_sitio_sin_tocar_ficheros_ni_leer_contenido_ni_red(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz")
        token = await token_de(serie, ids.values())
        antes_disco, antes_rutas = huella_disco(ent.lib), await estado_de_archivos(ent.banco)

        intentos: list[str] = []
        raiz = str(ent.lib)

        def vigilado(real):
            def _open(f, *a, **kw):
                if isinstance(f, (str, os.PathLike)) and str(f).startswith(raiz):
                    intentos.append(str(f))
                    raise AssertionError("vincular no puede abrir ni leer ficheros")
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
            r = await confirmar(token)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
        c = r.json()
        assert intentos == []
        assert (c["resultado"]["global"], c["repetida"]) == ("vinculados_todos", False)
        assert c["resultado"]["totales"] == {"vinculados": 3, "ya_estaban": 0, "omitidos": 0, "issues_creados": 3,
                                             "con_conflicto_incluidos": 0}
        despues = await estado_de_archivos(ent.banco)
        assert all(despues[n][0] and despues[n][1] == "manual" for n in antes_rutas)        # vinculados, procedencia manual
        assert {n: v[2] for n, v in despues.items()} == {n: v[2] for n, v in antes_rutas.items()}   # RUTAS INTACTAS
        assert huella_disco(ent.lib) == antes_disco                                       # bytes, tamaño y mtime intactos
        async with ent.banco.fabrica() as s:
            assert [r[:3] for r in (await s.execute(text(
                "SELECT file_name, file_path, file_format::text FROM files ORDER BY file_name"))).all()] == [
                (n, str(ent.lib / "Comics/Flash (1987)" / n), "cbz") for n in sorted(ids)]

    async def test_el_issue_se_crea_con_los_mismos_campos_que_la_asignacion_menos_la_ruta(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Omnigold 5 (1987).cbz")
        await confirmar(await token_de(serie, ids.values()))
        async with ent.banco.fabrica() as s:
            filas = (await s.execute(text(
                "SELECT issue_number, format::text, locked_fields, volume, series_id::text FROM issues ORDER BY issue_number"))).all()
        assert [(r[0], r[1], list(r[2]), r[3], r[4]) for r in filas] == [
            ("1", "single_issue", ["series_id", "issue_number"], 1, str(serie)),
            ("5", filas[1][1], ["series_id", "issue_number"], 1, str(serie))]
        assert filas[1][1] != "single_issue"                                          # la edición del nombre (B15)

    async def test_procedencia_por_archivo_v1_sin_token_ni_sesion_y_fusion_no_sustitucion(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = metadata || '{\"otra_clave\": 7, \"review_motivo\": \"x\"}'::jsonb"))
            await s.commit()
        token = await token_de(serie, ids.values())
        await confirmar(token)
        async with ent.banco.fabrica() as s:
            meta = (await s.execute(text("SELECT metadata FROM files"))).scalar_one()
        v = meta["vinculo"]
        assert meta["otra_clave"] == 7 and meta["match_status"] == "unsorted"            # lo anterior se conserva
        assert set(v) == {"version", "operacion_id", "fecha", "serie_id", "numero", "formato", "issue_creado", "conflictos", "previo"}
        assert (v["version"], v["numero"], v["formato"], v["issue_creado"], v["serie_id"]) == (1, "1", "single_issue", True, str(serie))
        assert v["previo"] == {"match_status": "unsorted", "review_motivo": "x"} and v["conflictos"] == []
        assert token not in json.dumps(meta) and "sesion" not in json.dumps(meta).lower()

    async def test_reutiliza_un_issue_existente_sin_archivo_de_la_misma_edicion(self, ent):
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:
            issue = Issue(series_id=serie, issue_number="1", format=IssueFormat.SINGLE_ISSUE)
            s.add(issue)
            await s.commit()
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        c = (await confirmar(await token_de(serie, ids.values()))).json()
        assert c["resultado"]["totales"]["issues_creados"] == 0 and c["resultado"]["archivos"][0]["issue_creado"] is False
        assert await numero_de("issues", ent.banco) == 1
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT issue_id::text FROM files"))).scalar_one() == str(issue.id)

    async def test_el_numero_conserva_el_texto_presentado(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        await confirmar(await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "5A")]))
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT issue_number FROM issues"))).scalar_one() == "5A"

    async def test_no_aprende_alias_ni_toca_nada_ajeno(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        antes = await instantanea(ent.banco)
        await confirmar(await token_de(serie, ids.values()))
        despues = await instantanea(ent.banco)
        assert despues["local_aliases"] == antes["local_aliases"] == [] and despues["wishlist"] == antes["wishlist"]
        assert despues["asignacion_operaciones"] == antes["asignacion_operaciones"] == []
        assert despues["series"] == antes["series"]

    async def test_el_informe_se_guarda_con_ids_y_sin_nombres_rutas_ni_token(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash (1987).cbz")
        token = await token_de(serie, [ids["Flash 01 (1987).cbz"]])
        await confirmar(token)
        (op, sid, resultado, hasta, creada), = await informes(ent.banco)
        texto = json.dumps(resultado, ensure_ascii=False)
        assert sid == str(serie) and resultado["version"] == 1 and resultado["operacion_id"] == op
        for prohibido in ("Flash 01", "Flash (1987)", str(ent.lib), token, "comics/"):
            assert prohibido.lower() not in texto.lower(), prohibido
        assert [a["id"] for a in resultado["archivos"]] == [str(ids["Flash 01 (1987).cbz"])]
        assert int(hasta.timestamp()) == verificar_token_vinculacion(token, SECRETO).caduca      # la del propio token
        async with ent.banco.fabrica() as s:       # sin clave foránea: el informe no depende de la serie
            assert (await s.execute(text(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = 'vinculacion_operaciones'::regclass AND contype = 'f'"))).scalar_one() == 0

    async def test_los_nombres_actuales_son_presentacion_y_no_parte_del_informe(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        c = (await confirmar(await token_de(serie, ids.values()))).json()
        assert c["presentacion"]["nombres_actuales"] == {str(ids["Flash 01 (1987).cbz"]): "Flash 01 (1987).cbz"}
        assert "nombres_actuales" not in c["resultado"] and "nombre" not in json.dumps(c["resultado"])


# ── Idempotencia, reinicio, caducidad y purga ───────────────────────────────────────────────────

class TestIdempotencia:

    async def test_repetir_devuelve_el_mismo_informe_sin_ejecutar_nada(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        a = (await confirmar(token)).json()
        antes = await instantanea(ent.banco)
        n = len(ent.banco.sentencias)
        b = (await confirmar(token)).json()
        assert (a["repetida"], b["repetida"]) == (False, True) and a["resultado"] == b["resultado"]
        assert [q for q in escrituras(ent.banco, n) if "advisory" not in q] == [] and await instantanea(ent.banco) == antes
        (_, _, guardado, *_), = await informes(ent.banco)
        assert documento_canonico(guardado) == documento_canonico(b["resultado"])      # el documento persistido

    async def test_doble_envio_simultaneo_ejecuta_una_vez_y_los_dos_responden_200(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        r = await asyncio.gather(confirmar(token), confirmar(token))
        assert [x.status_code for x in r] == [200, 200] and sorted(x.json()["repetida"] for x in r) == [False, True]
        assert r[0].json()["resultado"] == r[1].json()["resultado"]
        assert await numero_de("issues", ent.banco) == 2 and len(await informes(ent.banco)) == 1

    async def test_tras_reiniciar_el_resultado_sale_de_postgres(self, ent, url_bd):
        from tests.test_alta_serie_pg import reiniciar
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash (1987).cbz")
        token = await token_de(serie, ids.values())
        a = (await confirmar(token)).json()
        await reiniciar(ent, url_bd)
        b = (await confirmar(token)).json()
        assert b["repetida"] is True and a["resultado"] == b["resultado"]

    async def test_un_token_caducado_con_informe_devuelve_el_informe(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1")])
        a = (await confirmar(token)).json()
        async with ent.banco.fabrica() as s:       # el token «caduca»: se adelanta su caducidad y se retrasa la creación
            pass
        servicio_tarde = time.time() + 16 * 60
        async with ent.banco.fabrica() as s:
            b = await VinculacionDeArchivos(s, secret=SECRETO, ahora=servicio_tarde).confirmar(token)
        assert b.repetida is True and b.resultado.model_dump(by_alias=True) == a["resultado"]

    async def test_un_token_caducado_sin_informe_es_410_y_no_ejecuta(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1")], ahora=time.time() - 16 * 60)
        r = await confirmar(token)
        assert r.status_code == 410 and r.json()["detail"]["codigo"] == "token_caducado"
        assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []

    async def test_purga_acotada_con_las_dos_condiciones_y_tras_purgar_el_caducado_es_410(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        # un informe antiguo y caducado, uno antiguo con token vigente, uno reciente y caducado
        viejo_caducado, viejo_vigente, reciente_caducado = (str(uuid4()) for _ in range(3))
        async with ent.banco.fabrica() as s:
            for op, horas, vigente in ((viejo_caducado, 30, False), (viejo_vigente, 30, True), (reciente_caducado, 1, False)):
                await s.execute(text(
                    "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta, creada) VALUES "
                    "(CAST(:o AS uuid), gen_random_uuid(), CAST('{}' AS jsonb), now() + make_interval(hours => :v), "
                    "now() - make_interval(hours => :h))"), {"o": op, "v": 1 if vigente else -1, "h": horas})
            await s.commit()
        previas = await numero_de("series", ent.banco)
        r = await confirmar(await token_de(serie, [ids["Flash 02 (1987).cbz"]]))        # dispara la purga
        assert r.status_code == 200
        restantes = {i[0] for i in await informes(ent.banco)}
        assert viejo_caducado not in restantes and {viejo_vigente, reciente_caducado} <= restantes
        assert await numero_de("series", ent.banco) == previas and await numero_de("issues", ent.banco) == 1

    async def test_purgar_un_informe_y_reenviar_su_token_caducado_es_410(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1")])
        assert (await confirmar(token)).status_code == 200
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        async with ent.banco.fabrica() as s:
            with pytest.raises(vinculacion.TokenCaducadoError):
                await VinculacionDeArchivos(s, secret=SECRETO, ahora=time.time() + 16 * 60).confirmar(token)
        assert await numero_de("issues", ent.banco) == 1                                  # nada nuevo

    async def test_si_no_se_vincula_nada_el_informe_tambien_se_guarda_y_es_definitivo(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        ruta = ent.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz"
        oculto = ruta.with_suffix(".oculto")
        ruta.rename(oculto)
        a = (await confirmar(token)).json()
        assert a["resultado"]["global"] == "nada_vinculado" and a["resultado"]["archivos"][0]["motivo"] == "origen_no_encontrado"
        oculto.rename(ruta)                                   # el problema desaparece, pero el resultado es definitivo
        b = (await confirmar(token)).json()
        assert b["repetida"] is True and b["resultado"] == a["resultado"] and await numero_de("issues", ent.banco) == 0
        c = (await confirmar(await token_de(serie, ids.values()))).json()                  # otra vista previa sí lo vincula
        assert c["resultado"]["global"] == "vinculados_todos"

    async def test_un_fallo_inesperado_no_deja_vinculos_issues_ni_informe_y_el_reintento_ejecuta(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        real = VinculacionDeArchivos._vincular_archivo
        llamadas = []

        async def falla_en_el_segundo(self, *a, **kw):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError("fallo inesperado a mitad")
            return await real(self, *a, **kw)
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", falla_en_el_segundo)
        r = await confirmar(token)
        assert r.status_code == 500 and r.json()["detail"]["codigo"] == "error_inesperado"
        assert "RuntimeError" not in r.text and str(ent.lib) not in r.text
        assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []
        assert all(v[0] is None for v in (await estado_de_archivos(ent.banco)).values())      # ningún vínculo
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", real)
        assert (await confirmar(token)).json()["resultado"]["global"] == "vinculados_todos"

    async def test_un_fallo_al_guardar_el_informe_tampoco_deja_nada(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        real = VinculacionDeArchivos._purgar

        async def falla(self):
            raise RuntimeError("fallo tras vincular, antes del commit")
        monkeypatch.setattr(VinculacionDeArchivos, "_purgar", falla)
        assert (await confirmar(token)).status_code == 500
        assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []
        assert all(v[0] is None for v in (await estado_de_archivos(ent.banco)).values())
        monkeypatch.setattr(VinculacionDeArchivos, "_purgar", real)
        assert (await confirmar(token)).status_code == 200


def documento_canonico(d: dict) -> str:
    """Igualdad del DOCUMENTO JSON (no de los bytes de la respuesta HTTP): se compara su forma canónica."""
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


# ── Token, autenticación y forma de la petición ─────────────────────────────────────────────────

class TestToken:

    async def test_tokens_invalidos_son_422_y_no_ejecutan_nada(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        bueno = await token_de(serie, ids.values())
        alta = crear_token(PROPOSITO_ALTA, CLAVE, {"x": 1}, SECRETO)
        antiguo = crear_token("vincular", CLAVE, {"serie_id": str(serie), "operacion": str(uuid4()), "archivos": [
            {"id": str(ids["Flash 01 (1987).cbz"]), "numero": "1", "formato": "single_issue", "tamano": 1, "mtime_ns": 1}]}, SECRETO)
        for malo in (bueno[:-3] + "zzz", "inventado", alta, antiguo, bueno + "x"):
            r = await confirmar(malo)
            assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido", malo[:20]
        assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []

    async def test_la_peticion_solo_admite_el_token(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        for extra in ({"numeros": {}}, {"marcados": []}, {"series_id": str(serie)}, {"numero": "9"}):
            assert (await post(RUTA, {"token": token, **extra})).status_code == 422
        assert (await post(RUTA, {})).status_code == 422 and await informes(ent.banco) == []

    async def test_sin_clave_del_servidor_es_503(self, ent, monkeypatch):
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=""))
        assert (await confirmar("x")).status_code == 503

    async def test_sin_sesion_es_401(self, ent, monkeypatch):
        from zascarr.config import get_settings
        from zascarr.services.auth import hash_password
        ajustes = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        assert (await confirmar("x")).status_code == 401

    async def test_la_serie_ya_no_existe_es_409_y_no_deja_fila(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series"))
            await s.commit()
        r = await confirmar(token)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "la_serie_ya_no_existe"
        assert await informes(ent.banco) == []


# ── Reverificación: cada impedimento previsto, por archivo ───────────────────────────────────────

class TestReverificacion:

    async def _lote(self, ent, *nombres):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, *nombres)
        return serie, ids, await token_de(serie, ids.values())

    async def test_archivo_inexistente(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM files WHERE file_name = 'Flash 01 (1987).cbz'"))
            await s.commit()
        a = por_id(await confirmar(token))
        assert a[str(ids["Flash 01 (1987).cbz"])]["motivo"] == "archivo_inexistente"
        assert a[str(ids["Flash 02 (1987).cbz"])]["estado"] == "vinculado"

    async def test_descartado(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET review_dismissed = true WHERE file_name = 'Flash 01 (1987).cbz'"))
            await s.commit()
        a = por_id(await confirmar(token))
        assert a[str(ids["Flash 01 (1987).cbz"])]["motivo"] == "descartado"

    async def test_operacion_de_asignacion_viva(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"),
                {"f": ids["Flash 01 (1987).cbz"], "s": serie, "sha": SHA})
            await s.commit()
        c = (await confirmar(token)).json()
        a = {x["id"]: x for x in c["resultado"]["archivos"]}
        assert a[str(ids["Flash 01 (1987).cbz"])]["motivo"] == "en_curso" and c["resultado"]["global"] == "vinculados_parcialmente"
        assert (await estado_de_archivos(ent.banco))["Flash 01 (1987).cbz"][0] is None

    async def test_origen_no_encontrado_y_no_verificable(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz")
        (ent.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz").unlink()
        carpeta = ent.lib / "Comics/Flash (1987)"
        os.chmod(carpeta, 0)
        try:
            sin_permiso = por_id(await confirmar(token))
        finally:
            os.chmod(carpeta, 0o755)
        assert {a["motivo"] for a in sin_permiso.values()} == {"origen_no_verificable"}
        # con el permiso de vuelta, un token NUEVO distingue «no encontrado» (el fichero se borró) de los demás
        nuevo = await firmar(ent, serie, [(ids["Flash 02 (1987).cbz"], "2")])
        (ent.lib / "Comics/Flash (1987)/Flash 02 (1987).cbz").unlink()
        a = por_id(await confirmar(nuevo))
        assert next(iter(a.values()))["motivo"] == "origen_no_encontrado"

    async def test_la_huella_distinta_se_omite_como_cambio_desde_la_vista_previa(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        ruta = ent.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz"
        ruta.write_bytes(ruta.read_bytes() + b"mas")                         # cambia el tamaño
        a = por_id(await confirmar(token))
        assert a[str(ids["Flash 01 (1987).cbz"])]["motivo"] == "cambio_desde_la_vista_previa"
        assert a[str(ids["Flash 02 (1987).cbz"])]["estado"] == "vinculado"

    async def test_solo_el_mtime_distinto_tambien_se_omite(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz")
        ruta = ent.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz"
        st = ruta.stat()
        os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        assert next(iter(por_id(await confirmar(token)).values()))["motivo"] == "cambio_desde_la_vista_previa"

    async def test_la_ruta_registrada_cambia_tras_el_stat_no_se_aplica_la_huella_vieja(self, ent, monkeypatch):
        """Pausa DESPUÉS del `stat`; otra sesión cambia `file_path` (y el fichero nuevo tiene otra huella); al reanudar,
        ese archivo se omite y no se le aplica la huella de la ruta anterior."""
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        pausa, seguir = asyncio.Event(), asyncio.Event()

        async def gancho():
            pausa.set()
            await seguir.wait()
        monkeypatch.setattr(VinculacionDeArchivos, "_gancho_tras_stat", staticmethod(gancho))
        tarea = asyncio.create_task(confirmar(token))
        await asyncio.wait_for(pausa.wait(), 10)
        nueva = ent.lib / "Comics/Flash (1987)/otro sitio.cbz"
        (ent.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz").rename(nueva)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET file_path = :p WHERE file_name = 'Flash 01 (1987).cbz'"), {"p": str(nueva)})
            await s.commit()
        seguir.set()
        c = (await asyncio.wait_for(tarea, 20)).json()
        a = {x["id"]: x for x in c["resultado"]["archivos"]}
        assert a[str(ids["Flash 01 (1987).cbz"])]["motivo"] == "cambio_desde_la_vista_previa"
        assert a[str(ids["Flash 02 (1987).cbz"])]["estado"] == "vinculado"
        assert (await estado_de_archivos(ent.banco))["Flash 01 (1987).cbz"][0] is None

    async def test_ya_vinculado_al_mismo_issue_es_idempotente_y_a_otro_nunca_se_reasigna(self, ent):
        serie = await serie_de_prueba(ent)
        otra = await serie_de_prueba(ent, "Batman", 1940)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz")
        token = await token_de(serie, ids.values())
        async with ent.banco.fabrica() as s:
            mismo = Issue(series_id=serie, issue_number="1", format=IssueFormat.SINGLE_ISSUE)
            otro_numero = Issue(series_id=serie, issue_number="99", format=IssueFormat.SINGLE_ISSUE)
            otra_serie = Issue(series_id=otra, issue_number="3", format=IssueFormat.SINGLE_ISSUE)
            s.add_all([mismo, otro_numero, otra_serie])
            await s.flush()
            for nombre, issue in (("Flash 01 (1987).cbz", mismo), ("Flash 02 (1987).cbz", otro_numero), ("Flash 03 (1987).cbz", otra_serie)):
                await s.execute(text("UPDATE files SET issue_id = :i WHERE file_name = :n"), {"i": issue.id, "n": nombre})
            await s.commit()
            esperado = {"Flash 01 (1987).cbz": mismo.id, "Flash 02 (1987).cbz": otro_numero.id, "Flash 03 (1987).cbz": otra_serie.id}
        c = (await confirmar(token)).json()
        a = {x["id"]: x for x in c["resultado"]["archivos"]}
        assert a[str(ids["Flash 01 (1987).cbz"])]["estado"] == "ya_estaba_vinculado"
        assert a[str(ids["Flash 02 (1987).cbz"])]["motivo"] == "ya_vinculado_a_otro"
        assert a[str(ids["Flash 03 (1987).cbz"])]["motivo"] == "ya_vinculado_a_otro"
        assert c["resultado"]["totales"]["ya_estaban"] == 1 and c["resultado"]["totales"]["vinculados"] == 0
        assert c["resultado"]["global"] == "vinculados_parcialmente"
        for nombre, issue_id in esperado.items():                                    # NADA se reasignó
            assert (await estado_de_archivos(ent.banco))[nombre][0] == str(issue_id)

    async def test_un_archivo_vinculado_a_otro_issue_nunca_pasa_a_un_issue_existente_del_numero_pedido(self, ent):
        """El `Issue` del número pedido SÍ existe (vacío) y el archivo está vinculado a otro: no se reasigna."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 02 (1987).cbz")
        async with ent.banco.fabrica() as s:
            destino = Issue(series_id=serie, issue_number="2", format=IssueFormat.SINGLE_ISSUE)
            actual = Issue(series_id=serie, issue_number="99", format=IssueFormat.SINGLE_ISSUE)
            s.add_all([destino, actual])
            await s.flush()
            await s.execute(text("UPDATE files SET issue_id = :i"), {"i": actual.id})
            await s.commit()
        c = (await confirmar(await firmar(ent, serie, [(ids["Flash 02 (1987).cbz"], "2")]))).json()
        assert c["resultado"]["archivos"][0]["motivo"] == "ya_vinculado_a_otro"
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT issue_id::text FROM files"))).scalar_one() == str(actual.id)
            assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id = :i"), {"i": destino.id})).scalar_one() == 0

    async def test_colision_de_edicion_numero_ya_existe_y_numero_ambiguo(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz", "Flash 04 (1987).cbz")
        token = await token_de(serie, ids.values())
        async with ent.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="1", format=IssueFormat.OMNIBUS))                 # otra edición
            ocupado = Issue(series_id=serie, issue_number="2", format=IssueFormat.SINGLE_ISSUE)
            s.add(ocupado)
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE, volume=1))   # dos volúmenes
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE, volume=2))
            await s.flush()
            s.add(File(id=uuid4(), file_path="/otra/ruta.cbz", file_name="ruta.cbz", file_format=FileFormat.CBZ, issue_id=ocupado.id))
            await s.commit()
        antes = await numero_de("issues", ent.banco)
        a = por_id(await confirmar(token))
        assert [a[str(ids[n])]["motivo"] for n in ("Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz")] == [
            "colision_de_edicion", "numero_ya_existe", "numero_ambiguo"]
        assert a[str(ids["Flash 04 (1987).cbz"])]["estado"] == "vinculado"
        assert await numero_de("issues", ent.banco) == antes + 1               # solo se creó el del 4; no se tocó ninguno

    async def test_global_parcial_o_nada_nunca_anuncia_exito(self, ent):
        serie, ids, token = await self._lote(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        for n in ids:
            (ent.lib / "Comics/Flash (1987)" / n).unlink()
        c = (await confirmar(token)).json()
        assert c["resultado"]["global"] == "nada_vinculado" and c["resultado"]["totales"]["omitidos"] == 2
        assert c["resultado"]["totales"]["vinculados"] == 0

    async def test_lote_mixto_se_vincula_lo_demas_y_el_informe_cuenta_cada_estado(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, *(f"Flash {i:02d} (1987).cbz" for i in range(1, 7)))
        token = await token_de(serie, ids.values())
        d = ent.lib / "Comics/Flash (1987)"
        (d / "Flash 01 (1987).cbz").unlink()                                              # origen ausente
        (d / "Flash 02 (1987).cbz").write_bytes(b"cambia")                                # huella
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET review_dismissed = true WHERE file_name = 'Flash 03 (1987).cbz'"))
            await s.commit()
        c = (await confirmar(token)).json()
        assert c["resultado"]["totales"] == {"vinculados": 3, "ya_estaban": 0, "omitidos": 3, "issues_creados": 3, "con_conflicto_incluidos": 0}
        assert c["resultado"]["global"] == "vinculados_parcialmente"
        assert sorted(a["motivo"] for a in c["resultado"]["archivos"] if a["motivo"]) == [
            "cambio_desde_la_vista_previa", "descartado", "origen_no_encontrado"]


# ── Conflictos de contexto: firmados, no recalculados ───────────────────────────────────────────

class TestConflictos:

    async def test_los_conflictos_vistos_en_la_vista_previa_salen_en_el_informe(self, ent):
        serie = await serie_de_prueba(ent, "Flash", 1987)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 10 (1999).cbz")
        r = (await previsualizar(serie, marcados=list(ids.values()))).json()
        firmados = {a.id: a.conflictos for a in verificar_token_vinculacion(r["token"], SECRETO).archivos}
        assert firmados[str(ids["Flash 01 (1987).cbz"])] == () and firmados[str(ids["Flash 10 (1999).cbz"])] != ()
        c = (await confirmar(r["token"])).json()
        a = {x["id"]: x for x in c["resultado"]["archivos"]}
        assert a[str(ids["Flash 10 (1999).cbz"])]["conflictos"] == list(firmados[str(ids["Flash 10 (1999).cbz"])])
        assert a[str(ids["Flash 01 (1987).cbz"])]["conflictos"] == []
        assert c["resultado"]["totales"]["con_conflicto_incluidos"] == 1
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT metadata->'vinculo'->'conflictos' FROM files WHERE file_name = 'Flash 10 (1999).cbz'"))).scalar_one() == list(firmados[str(ids["Flash 10 (1999).cbz"])])

    async def test_los_codigos_firmados_salen_aunque_el_conflicto_ya_no_exista(self, ent):
        """Se informa de lo que la persona VIO, no de lo que se recalcule ahora."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1", "single_issue", ["titulo_distinto"])])
        c = (await confirmar(token)).json()
        assert c["resultado"]["archivos"][0]["conflictos"] == ["titulo_distinto"]
        assert c["resultado"]["totales"]["con_conflicto_incluidos"] == 1

    async def test_un_omitido_con_conflicto_no_cuenta_como_incluido_pero_consta(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", en_disco=True)
        token = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1", "single_issue", ["titulo_distinto"])])
        (ent.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz").unlink()
        c = (await confirmar(token)).json()
        assert c["resultado"]["totales"]["con_conflicto_incluidos"] == 0
        assert c["resultado"]["archivos"][0]["conflictos"] == ["titulo_distinto"]


# ── Informe inmutable ───────────────────────────────────────────────────────────────────────────

class TestInmutabilidad:

    async def test_un_update_del_informe_falla_y_el_delete_de_la_purga_no(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        await confirmar(await token_de(serie, ids.values()))
        async with ent.banco.fabrica() as s:
            with pytest.raises(DBAPIError, match="inmutable"):
                await s.execute(text("UPDATE vinculacion_operaciones SET resultado = '{}'::jsonb"))
            await s.rollback()
            with pytest.raises(DBAPIError, match="inmutable"):
                await s.execute(text("UPDATE vinculacion_operaciones SET series_id = gen_random_uuid()"))
            await s.rollback()
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        assert await informes(ent.banco) == []

    async def test_renombrar_un_archivo_despues_no_cambia_el_resultado_solo_la_presentacion(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        a = (await confirmar(token)).json()
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET file_name = 'otro nombre.cbz'"))
            await s.commit()
        b = (await confirmar(token)).json()
        assert documento_canonico(a["resultado"]) == documento_canonico(b["resultado"])
        assert list(b["presentacion"]["nombres_actuales"].values()) == ["otro nombre.cbz"] and a["presentacion"] != b["presentacion"]


# ── Ocupación del Issue: el doble vínculo imposible ─────────────────────────────────────────────

class TestOcupacionDelIssue:

    async def test_cinco_a_y_cinco_a_minuscula_no_permiten_un_doble_vinculo(self, ent):
        """Las dos variantes son LA MISMA clave: se serializan, se buscan juntas y la segunda ve el Issue ocupado."""
        for ronda in range(5):
            await ent.banco.limpiar()
            serie = await serie_de_prueba(ent)
            ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
            t1 = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "5A")])
            t2 = await firmar(ent, serie, [(ids["Flash 02 (1987).cbz"], "5a")])
            r = await asyncio.gather(confirmar(t1), confirmar(t2))
            assert [x.status_code for x in r] == [200, 200], (ronda, [x.text for x in r])
            estados = sorted(x.json()["resultado"]["archivos"][0]["estado"] + ":" + str(x.json()["resultado"]["archivos"][0]["motivo"]) for x in r)
            assert estados == ["omitido:numero_ya_existe", "vinculado:None"], (ronda, estados)
            assert await numero_de("issues", ent.banco) == 1
            async with ent.banco.fabrica() as s:
                assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one() == 1

    async def test_un_issue_existente_con_otra_capitalizacion_se_encuentra_y_no_se_duplica(self, ent):
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:
            existente = Issue(series_id=serie, issue_number="5a", format=IssueFormat.SINGLE_ISSUE)
            s.add(existente)
            await s.commit()
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        c = (await confirmar(await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "5A")]))).json()
        assert c["resultado"]["archivos"][0]["estado"] == "vinculado" and c["resultado"]["archivos"][0]["issue_creado"] is False
        assert await numero_de("issues", ent.banco) == 1
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT issue_id::text FROM files"))).scalar_one() == str(existente.id)

    @pytest.mark.parametrize("issue_previo", ["inexistente", "vacio"])
    async def test_dos_archivos_el_mismo_numero_a_la_vez_gana_uno_y_nunca_se_vinculan_los_dos(self, ent, issue_previo):
        for ronda in range(6):
            await ent.banco.limpiar()
            serie = await serie_de_prueba(ent)
            if issue_previo == "vacio":
                async with ent.banco.fabrica() as s:
                    s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE))
                    await s.commit()
            ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
            t1 = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "3")])
            t2 = await firmar(ent, serie, [(ids["Flash 02 (1987).cbz"], "3")])
            r = await asyncio.gather(confirmar(t1), confirmar(t2))
            assert [x.status_code for x in r] == [200, 200], (ronda, [x.text for x in r])
            motivos = sorted(str(x.json()["resultado"]["archivos"][0]["motivo"]) for x in r)
            assert motivos == ["None", "numero_ya_existe"], (ronda, motivos)
            assert await numero_de("issues", ent.banco) == 1
            async with ent.banco.fabrica() as s:
                assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one() == 1

    async def test_un_issue_con_volume_nulo_se_encuentra_y_no_se_duplica(self, ent):
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE))
            await s.flush()
            await s.execute(text("UPDATE issues SET volume = NULL"))
            await s.commit()
        ids = await archivos(ent, "Flash 03 (1987).cbz")
        c = (await confirmar(await token_de(serie, ids.values()))).json()
        assert c["resultado"]["archivos"][0]["estado"] == "vinculado" and c["resultado"]["archivos"][0]["issue_creado"] is False
        assert await numero_de("issues", ent.banco) == 1

    async def test_issues_del_mismo_numero_en_volumenes_distintos_o_nulo_son_ambiguos_y_no_se_toca_ninguno(self, ent):
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE, volume=1))
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE, volume=2))
            await s.commit()
        ids = await archivos(ent, "Flash 03 (1987).cbz")
        antes = await instantanea(ent.banco)
        c = (await confirmar(await firmar(ent, serie, [(ids["Flash 03 (1987).cbz"], "3")]))).json()
        assert c["resultado"]["archivos"][0]["motivo"] == "numero_ambiguo" and c["resultado"]["global"] == "nada_vinculado"
        despues = await instantanea(ent.banco)
        assert despues["issues"] == antes["issues"] and despues["files"] == antes["files"]            # no se modifica ninguno

    async def test_claves_solapadas_en_orden_distinto_no_se_bloquean_entre_si(self, ent):
        """Candados de número tomados siempre en orden: dos lotes que comparten números sin coincidir en el orden
        de sus archivos no se interbloquean."""
        for ronda in range(4):
            await ent.banco.limpiar()
            serie = await serie_de_prueba(ent)
            ids = await archivos(ent, *(f"Flash {i:02d} (1987).cbz" for i in range(1, 9)))
            def n(i, ids=ids):
                return ids[f"Flash {i:02d} (1987).cbz"]
            t1 = await firmar(ent, serie, [(n(1), "3"), (n(2), "4"), (n(3), "5"), (n(4), "6")])
            t2 = await firmar(ent, serie, [(n(5), "6"), (n(6), "5"), (n(7), "4"), (n(8), "3")])
            r = await asyncio.wait_for(asyncio.gather(confirmar(t1), confirmar(t2)), 60)
            assert [x.status_code for x in r] == [200, 200], (ronda, [x.text for x in r])
            assert await numero_de("issues", ent.banco) == 4
            async with ent.banco.fabrica() as s:
                assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one() == 4
                assert (await s.execute(text("SELECT max(c) FROM (SELECT count(*) c FROM files WHERE issue_id IS NOT NULL GROUP BY issue_id) t"))).scalar_one() == 1


# ── Concurrencia: tokens, deshacer, organizar y la serie ────────────────────────────────────────

async def alta_manual(ent) -> tuple[UUID, str]:
    """Una serie creada por la rebanada 2b (con comprobante): (series_id, operacion_id) para poder deshacerla."""
    v = (await post("/api/revision/serie/previsualizar", {"clave": CLAVE, "manual": {"titulo": "Flash", "anio": 1987},
                                                          "tradicion": "american"})).json()
    c = (await post("/api/revision/serie", {"token": v["token"]})).json()
    return UUID(c["serie"]["series_id"]), c["deshacer"]["operacion_id"]


class TestConcurrencia:

    async def test_tokens_distintos_sobre_el_mismo_archivo_el_segundo_no_reasigna(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        t_mismo = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1")])
        t_igual = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "1")])
        t_otro = await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], "7")])
        r = [await confirmar(t_mismo), await confirmar(t_igual), await confirmar(t_otro)]
        e = [x.json()["resultado"]["archivos"][0] for x in r]
        assert (e[0]["estado"], e[1]["estado"], e[2]["motivo"]) == ("vinculado", "ya_estaba_vinculado", "ya_vinculado_a_otro")
        assert await numero_de("issues", ent.banco) == 1                      # el «7» no creó nada
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM issues WHERE issue_number = '7'"))).scalar_one() == 0

    async def test_tokens_distintos_sobre_el_mismo_archivo_a_la_vez(self, ent):
        for ronda in range(5):
            await ent.banco.limpiar()
            serie = await serie_de_prueba(ent)
            ids = await archivos(ent, "Flash 01 (1987).cbz")
            ts = [await firmar(ent, serie, [(ids["Flash 01 (1987).cbz"], n)]) for n in ("1", "1", "2")]
            r = await asyncio.gather(*(confirmar(t) for t in ts))
            assert all(x.status_code == 200 for x in r), (ronda, [x.text for x in r])
            vinculados = [x for x in r if x.json()["resultado"]["archivos"][0]["estado"] == "vinculado"]
            assert len(vinculados) == 1
            async with ent.banco.fabrica() as s:
                assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one() == 1
            assert await numero_de("issues", ent.banco) == 1

    async def test_deshacer_el_alta_a_la_vez_que_vincular_nunca_deja_archivos_vinculados_a_una_serie_borrada(self, ent):
        resultados = set()
        for _ in range(8):
            await ent.banco.limpiar()
            ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
            serie, op = await alta_manual(ent)
            token = await token_de(serie, ids.values())
            v, d = await asyncio.gather(confirmar(token), post(f"/api/revision/serie/{serie}/deshacer", {"operacion_id": op}))
            async with ent.banco.fabrica() as s:
                series = (await s.execute(text("SELECT count(*) FROM series"))).scalar_one()
                vinculados = (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one()
                huerfanos = (await s.execute(text("SELECT count(*) FROM issues i WHERE NOT EXISTS (SELECT 1 FROM series s WHERE s.id = i.series_id)"))).scalar_one()
            assert huerfanos == 0
            if v.status_code == 200:                                          # vincular primero: deshacer se niega
                assert d.status_code == 409 and d.json()["detail"]["motivo"] in ("tiene_archivos", "tiene_numeros")
                assert series == 1 and vinculados == 2
                resultados.add("vincular_primero")
            else:                                                             # deshacer primero: vincular da 409
                assert v.status_code == 409 and v.json()["detail"]["codigo"] == "la_serie_ya_no_existe" and d.status_code == 200
                assert series == 0 and vinculados == 0 and await informes(ent.banco) == []
                resultados.add("deshacer_primero")
        assert resultados                         # se observó al menos uno de los dos órdenes legítimos

    async def test_con_la_serie_bloqueada_desde_fuera_vincular_espera_y_si_se_borra_es_409(self, ent):
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:                                  # un Issue existente: se REUTILIZARÁ
            s.add(Issue(series_id=serie, issue_number="1", format=IssueFormat.SINGLE_ISSUE))
            await s.commit()
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        async with ent.banco.fabrica() as externa:
            await externa.execute(text("SELECT id FROM series WHERE id = :i FOR UPDATE"), {"i": serie})
            tarea = asyncio.create_task(confirmar(token))
            await asyncio.sleep(0.8)
            assert not tarea.done(), "vincular debe esperar a quien tiene la serie FOR UPDATE, aunque solo reutilice números"
            await externa.execute(text("DELETE FROM issues"))
            await externa.execute(text("DELETE FROM series WHERE id = :i"), {"i": serie})
            await externa.commit()
        r = await asyncio.wait_for(tarea, 20)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "la_serie_ya_no_existe"
        assert await informes(ent.banco) == []

    async def test_vincular_retiene_la_serie_for_share_y_el_deshacer_espera(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        parado, seguir = asyncio.Event(), asyncio.Event()

        async def gancho():
            parado.set()
            await seguir.wait()
        monkeypatch.setattr(VinculacionDeArchivos, "_gancho_con_filas_bloqueadas", staticmethod(gancho))
        tarea = asyncio.create_task(confirmar(token))
        await asyncio.wait_for(parado.wait(), 10)
        async with ent.banco.fabrica() as otra:
            otra_tarea = asyncio.create_task(otra.execute(text("SELECT id FROM series WHERE id = :i FOR UPDATE"), {"i": serie}))
            await asyncio.sleep(0.7)
            assert not otra_tarea.done()                      # FOR UPDATE espera al FOR SHARE de vincular
            seguir.set()
            r = await asyncio.wait_for(tarea, 20)
            await asyncio.wait_for(otra_tarea, 20)
            await otra.rollback()
        assert r.status_code == 200

    async def test_organizar_ya_vivo_es_en_curso_y_no_escribe(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('confirmada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids["Flash 01 (1987).cbz"], "s": serie, "sha": SHA})
            await s.commit()
        c = (await confirmar(token)).json()
        assert c["resultado"]["archivos"][0]["motivo"] == "en_curso" and await numero_de("issues", ent.banco) == 0

    async def test_organizar_que_nace_mientras_vincular_retiene_el_archivo_espera_y_gana_despues(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        parado, seguir = asyncio.Event(), asyncio.Event()

        async def gancho():
            parado.set()
            await seguir.wait()
        monkeypatch.setattr(VinculacionDeArchivos, "_gancho_con_filas_bloqueadas", staticmethod(gancho))
        tarea = asyncio.create_task(confirmar(token))
        await asyncio.wait_for(parado.wait(), 10)

        async def nace_organizar():
            async with ent.banco.fabrica() as s:
                await s.execute(text(
                    "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                    "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                    "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids["Flash 01 (1987).cbz"], "s": serie, "sha": SHA})
                await s.commit()
        organizar = asyncio.create_task(nace_organizar())
        await asyncio.sleep(0.8)
        assert not organizar.done(), "la operación viva de organizar debe esperar a que vincular suelte el archivo"
        seguir.set()
        r = await asyncio.wait_for(tarea, 20)
        await asyncio.wait_for(organizar, 20)
        assert r.json()["resultado"]["archivos"][0]["estado"] == "vinculado"
        assert await numero_de("asignacion_operaciones", ent.banco) == 1             # organizar existe DESPUÉS y prevalece

    async def test_tres_sesiones_vincular_retiene_la_serie_organizar_el_archivo_y_deshacer_espera(self, ent):
        """El escenario real, observado: no se fuerza el orden. S2 (organizar) retiene el archivo; S1 (vincular) toma
        la serie y espera al archivo; S3 (deshacer) espera por la serie. S2 pide entonces un Issue (KEY SHARE de la
        serie) con el FOR UPDATE de S3 ya en cola."""
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        serie, op = await alta_manual(ent)
        token = await token_de(serie, ids.values())
        archivo = ids["Flash 01 (1987).cbz"]
        cronologia: list[str] = []
        async with ent.banco.fabrica() as organizar:
            await organizar.execute(text("SELECT id FROM files WHERE id = :f FOR UPDATE"), {"f": archivo})      # S2
            s1 = asyncio.create_task(confirmar(token))                                                          # S1
            await asyncio.sleep(0.7)
            assert not s1.done()
            s3 = asyncio.create_task(post(f"/api/revision/serie/{serie}/deshacer", {"operacion_id": op}))        # S3
            await asyncio.sleep(0.7)
            assert not s3.done() and not s1.done()
            # S2 crea su Issue (necesita KEY SHARE sobre la serie) y enlaza el archivo: ¿se bloquea tras el FOR UPDATE en cola?
            t0 = time.monotonic()
            nuevo = (await asyncio.wait_for(organizar.execute(text(
                "INSERT INTO issues (id, series_id, issue_number, volume) VALUES (gen_random_uuid(), :s, '1', 1) RETURNING id"),
                {"s": serie}), 8)).scalar_one()
            cronologia.append(f"organizar_inserta_issue:{time.monotonic() - t0:.2f}s")
            await organizar.execute(text("UPDATE files SET issue_id = :i WHERE id = :f"), {"i": nuevo, "f": archivo})
            await organizar.commit()
        v = await asyncio.wait_for(s1, 30)
        d = await asyncio.wait_for(s3, 30)
        assert not any(s.startswith("organizar_inserta_issue") and float(s.split(":")[1][:-1]) > 5 for s in cronologia), cronologia
        assert v.status_code == 200 and v.json()["resultado"]["archivos"][0]["motivo"] == "ya_vinculado_a_otro" or \
            v.json()["resultado"]["archivos"][0]["estado"] == "ya_estaba_vinculado"
        assert d.status_code == 409 and d.json()["detail"]["motivo"] in ("tiene_archivos", "tiene_numeros")
        async with ent.banco.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM series"))).scalar_one() == 1
            assert (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one() == 1

    async def test_un_interbloqueo_provocado_se_observa_y_la_integridad_se_mantiene_sea_cual_sea_la_victima(self, ent):
        """Prueba de INTEGRACIÓN, observacional: Postgres elige la víctima (en la práctica, la sesión que lleva más
        esperando), y eso NO es una propiedad garantizada del servicio. Se comprueba la integridad en cualquier caso;
        la respuesta 503 y el rollback del servicio se demuestran de forma determinista con la inyección de `40P01`."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        ordenados = sorted(ids.values(), key=str)
        primero, segundo = ordenados[0], ordenados[1]
        victima_x = False
        async with ent.banco.fabrica() as x:
            await x.execute(text("SELECT id FROM files WHERE id = :f FOR UPDATE"), {"f": segundo})      # X retiene el 2.º
            servicio = asyncio.create_task(confirmar(token))                                              # bloquea el 1.º y espera el 2.º
            await asyncio.sleep(0.5)
            try:
                await asyncio.wait_for(x.execute(text("SELECT id FROM files WHERE id = :f FOR UPDATE"), {"f": primero}), 20)
                await x.commit()
            except DBAPIError:
                victima_x = True                                          # Postgres eligió la sesión de la prueba
                await x.rollback()
        r = await asyncio.wait_for(servicio, 30)
        if victima_x:                                                     # el servicio acabó con normalidad
            assert r.status_code == 200 and r.json()["resultado"]["global"] == "vinculados_todos"
            assert await numero_de("issues", ent.banco) == 2 and len(await informes(ent.banco)) == 1
        else:                                                             # el servicio fue la víctima
            assert r.status_code == 503 and r.json()["detail"]["codigo"] == "conflicto_de_bloqueo"
            assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []
            assert all(v[0] is None for v in (await estado_de_archivos(ent.banco)).values())
            assert (await confirmar(token)).status_code == 200            # el mismo token se puede repetir

    async def test_un_error_de_interbloqueo_inyectado_responde_503_sin_efectos(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        real = VinculacionDeArchivos._vincular_archivo

        class OrigError(Exception):
            sqlstate = "40P01"

        async def interbloqueo(self, *a, **k):
            raise DBAPIError("UPDATE files ...", {}, OrigError("deadlock detected"))
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", interbloqueo)
        r = await confirmar(token)
        assert r.status_code == 503 and r.json()["detail"]["codigo"] == "conflicto_de_bloqueo"
        assert r.headers["retry-after"] == "1"
        assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", real)
        assert (await confirmar(token)).status_code == 200


class TestBloqueosYSesionLimpia:

    async def test_vincular_espera_a_quien_retiene_la_fila_del_issue(self, ent):
        """La fila del `Issue` se bloquea `FOR UPDATE`: quien la retiene (p. ej. un organizar que le enlaza un archivo)
        hace esperar a vincular, y al despertar este vuelve a contar la ocupación."""
        serie = await serie_de_prueba(ent)
        async with ent.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE))
            await s.commit()
        ids = await archivos(ent, "Flash 03 (1987).cbz", "Flash 09 (1987).cbz")
        token = await firmar(ent, serie, [(ids["Flash 03 (1987).cbz"], "3")])
        async with ent.banco.fabrica() as externa:
            await externa.execute(text("SELECT id FROM issues WHERE issue_number = '3' FOR UPDATE"))
            tarea = asyncio.create_task(confirmar(token))
            await asyncio.sleep(0.8)
            assert not tarea.done(), "vincular debe esperar a la fila del Issue"
            await externa.execute(text("UPDATE files SET issue_id = (SELECT id FROM issues WHERE issue_number = '3') WHERE file_name = 'Flash 09 (1987).cbz'"))
            await externa.commit()                          # la ocupación cambia mientras esperaba
        r = await asyncio.wait_for(tarea, 20)
        assert r.json()["resultado"]["archivos"][0]["motivo"] == "numero_ya_existe"      # volvió a contar DESPUÉS de esperar

    async def _sesion_limpia(self, ent, token, sesion_falla, monkeypatch, excepcion):
        async def candados(s) -> int:
            return (await s.execute(text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"))).scalar_one()

        async def falla(self, *a, **k):
            raise excepcion
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", falla)
        async with ent.banco.fabrica() as s:
            with pytest.raises(type(excepcion)):
                await VinculacionDeArchivos(s, secret=SECRETO).confirmar(token)
            assert not s.in_transaction()                                  # el servicio revirtió ÉL MISMO...
            assert await candados(s) == 0                                  # ...y no quedan candados consultivos

    async def test_tras_un_fallo_inesperado_la_sesion_queda_sin_transaccion_ni_candados(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        await self._sesion_limpia(ent, await token_de(serie, ids.values()), None, monkeypatch, RuntimeError("fallo"))

    async def test_tras_un_error_de_bd_que_no_es_interbloqueo_tambien(self, ent, monkeypatch):
        class OrigError(Exception):
            sqlstate = "23505"
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        await self._sesion_limpia(ent, await token_de(serie, ids.values()), None, monkeypatch,
                                  DBAPIError("INSERT ...", {}, OrigError("duplicate key")))

    async def test_tras_un_interbloqueo_la_sesion_tambien_queda_limpia(self, ent, monkeypatch):
        class OrigError(Exception):
            sqlstate = "40P01"
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())

        async def falla(self, *a, **k):
            raise DBAPIError("UPDATE ...", {}, OrigError("deadlock detected"))
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", falla)
        async with ent.banco.fabrica() as s:
            with pytest.raises(vinculacion.ConflictoDeBloqueoError):
                await VinculacionDeArchivos(s, secret=SECRETO).confirmar(token)
            assert not s.in_transaction()

    async def test_si_la_fila_no_se_puede_vincular_es_un_fallo_inesperado_y_no_un_exito_silencioso(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        async with ent.banco.fabrica() as s:
            issue = Issue(series_id=serie, issue_number="1", format=IssueFormat.SINGLE_ISSUE)
            s.add(issue)
            await s.flush()
            await s.execute(text("UPDATE files SET issue_id = :i"), {"i": issue.id})      # YA vinculada: el UPDATE no encaja
            await s.commit()
        firmado = ArchivoFirmado(str(ids["Flash 01 (1987).cbz"]), "1", "single_issue", 1, 1)
        async with ent.banco.fabrica() as s:
            f = SimpleNamespace(metadata_={})
            with pytest.raises(RuntimeError, match="no se pudo vincular"):
                await VinculacionDeArchivos(s, secret=SECRETO)._vincular_archivo(firmado, f, issue.id, False, serie, uuid4())

    async def test_la_purga_esta_acotada_a_cien_por_ejecucion(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        async with ent.banco.fabrica() as s:
            for _ in range(130):
                await s.execute(text(
                    "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta, creada) VALUES "
                    "(gen_random_uuid(), gen_random_uuid(), CAST('{}' AS jsonb), now() - interval '2 hours', now() - interval '30 hours')"))
            await s.commit()
        assert (await confirmar(await token_de(serie, ids.values()))).status_code == 200
        assert len(await informes(ent.banco)) == 30 + 1                     # 100 purgadas; quedan 30 viejas y la nueva


async def sin_cambios(ent, antes: dict) -> None:
    """Una respuesta de «no se ha cambiado nada» tiene que ser CIERTA: cero vínculos, cero `Issue`s nuevos, cero informe."""
    assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []
    assert all(v[0] is None for v in (await estado_de_archivos(ent.banco)).values())
    assert await instantanea(ent.banco) == antes


class TestFalloDespuesDeLaRespuestaPreparada:
    """La respuesta (con su presentación) se prepara ANTES del commit: si falla, todavía se revierte todo. Y un fallo
    desde que se pide el commit no puede anunciar «no se ha cambiado nada»."""

    async def test_un_fallo_al_leer_los_nombres_durante_la_primera_ejecucion_revierte_todo(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        antes = await instantanea(ent.banco)
        real = VinculacionDeArchivos._nombres

        async def falla(self, ids):
            raise RuntimeError("fallo al leer los nombres")
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", falla)
        r = await confirmar(token)
        assert r.status_code == 500 and r.json()["detail"]["codigo"] == "error_inesperado"
        assert "no se ha cambiado nada" in r.json()["detail"]["mensaje"]            # y es VERDAD:
        await sin_cambios(ent, antes)
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", real)
        assert (await confirmar(token)).json()["resultado"]["global"] == "vinculados_todos"      # el reintento ejecuta

    async def test_un_fallo_al_construir_la_respuesta_durante_la_primera_ejecucion_revierte_todo(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        antes = await instantanea(ent.banco)
        real = VinculacionDeArchivos.__dict__["_respuesta"]

        def falla(*a, **k):
            raise RuntimeError("fallo al construir la respuesta")
        monkeypatch.setattr(VinculacionDeArchivos, "_respuesta", staticmethod(falla))
        r = await confirmar(token)
        assert r.status_code == 500 and "no se ha cambiado nada" in r.json()["detail"]["mensaje"]
        await sin_cambios(ent, antes)
        monkeypatch.setattr(VinculacionDeArchivos, "_respuesta", real)
        assert (await confirmar(token)).status_code == 200

    async def test_un_fallo_de_presentacion_al_repetir_no_cambia_ni_borra_el_informe(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        primero = (await confirmar(token)).json()
        real = VinculacionDeArchivos._nombres

        async def falla(self, ids):
            raise RuntimeError("fallo")
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", falla)
        assert (await confirmar(token)).status_code == 500
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", real)
        assert len(await informes(ent.banco)) == 1 and (await confirmar(token)).json()["resultado"] == primero["resultado"]

    async def test_un_fallo_tras_pedir_el_commit_no_anuncia_que_no_se_cambio_nada_y_el_reintento_devuelve_el_informe(self, ent, monkeypatch):
        """La operación SÍ quedó confirmada pero no se pudo entregar la respuesta."""
        from sqlalchemy.ext.asyncio import AsyncSession
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        real_commit = AsyncSession.commit
        llamadas = []

        async def commit_y_luego_falla(self):
            await real_commit(self)                 # el commit llega a Postgres...
            llamadas.append(1)
            raise ConnectionError("se perdió la conexión al confirmar")      # ...pero la aplicación no se entera
        monkeypatch.setattr(AsyncSession, "commit", commit_y_luego_falla)
        r = await confirmar(token)
        monkeypatch.setattr(AsyncSession, "commit", real_commit)
        assert llamadas and r.status_code == 503 and r.json()["detail"]["codigo"] == "resultado_incierto"
        assert r.headers["retry-after"] == "1"
        texto = r.text.lower()
        assert "no se ha cambiado nada" not in texto and "mismo token" in texto
        # y de hecho SÍ hay efectos: vínculos, Issues e informe
        assert await numero_de("issues", ent.banco) == 2 and len(await informes(ent.banco)) == 1
        assert all(v[0] is not None for v in (await estado_de_archivos(ent.banco)).values())
        # el reintento con el mismo token devuelve el informe persistido
        b = (await confirmar(token)).json()
        assert b["repetida"] is True and b["resultado"]["global"] == "vinculados_todos"
        assert await numero_de("issues", ent.banco) == 2

    async def test_un_fallo_tras_pedir_el_commit_que_no_llego_a_confirmar_tambien_es_incierto_y_el_reintento_ejecuta(self, ent, monkeypatch):
        """Si el commit falla de verdad (nada confirmado) tampoco se afirma «sin cambios»: no se puede saber desde fuera.
        El reintento con el mismo token aplica la vinculación (no hay informe)."""
        from sqlalchemy.ext.asyncio import AsyncSession
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())
        real_commit = AsyncSession.commit

        async def falla(self):
            raise ConnectionError("se cayó antes de confirmar")
        monkeypatch.setattr(AsyncSession, "commit", falla)
        r = await confirmar(token)
        monkeypatch.setattr(AsyncSession, "commit", real_commit)
        assert r.status_code == 503 and r.json()["detail"]["codigo"] == "resultado_incierto"
        assert "no se ha cambiado nada" not in r.text.lower()
        assert (await confirmar(token)).json()["resultado"]["global"] == "vinculados_todos"

    async def test_una_cancelacion_antes_o_despues_del_commit_no_se_convierte_en_resultado_incierto(self, ent, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())

        async def cancela(self):
            raise asyncio.CancelledError()
        with monkeypatch.context() as m:                                    # antes del commit: se revierte todo
            m.setattr(VinculacionDeArchivos, "_purgar", cancela)
            async with ent.banco.fabrica() as s:
                with pytest.raises(asyncio.CancelledError):
                    await VinculacionDeArchivos(s, secret=SECRETO).confirmar(token)
        assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []

        real_commit = AsyncSession.commit

        async def commit_y_cancela(self):
            await real_commit(self)
            raise asyncio.CancelledError()
        with monkeypatch.context() as m:                                    # tras pedir el commit: sigue siendo una cancelación
            m.setattr(AsyncSession, "commit", commit_y_cancela)
            async with ent.banco.fabrica() as s:
                with pytest.raises(asyncio.CancelledError):
                    await VinculacionDeArchivos(s, secret=SECRETO).confirmar(token)
        assert (await confirmar(token)).json()["repetida"] is True          # la operación sí quedó confirmada


class TestTamanoDelToken:
    """El límite del cuerpo es el del MAYOR token que la vista previa puede emitir (calculado), no una cifra elegida."""

    async def _grupo_de_cien(self, ent, carpeta="Comics/Flash (1987)"):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 101)), carpeta=carpeta)
        return serie, ids

    async def test_cien_archivos_con_numeros_del_1_al_100_se_aceptan_de_extremo_a_extremo(self, ent):
        """El caso que el límite de 20.000 rechazaba: vista previa → token → POST de confirmación."""
        serie, ids = await self._grupo_de_cien(ent)
        r = await previsualizar(serie, marcados=list(ids.values()))
        token = r.json()["token"]
        assert r.json()["totales"]["a_vincular"] == 100
        c = await confirmar(token)
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["vinculados"] == 100

    async def test_el_token_del_caso_de_la_revision_20445_caracteres_no_se_rechaza_por_tamano(self, ent):
        """100 archivos, números 1–100, single_issue, 100 MB, mtime normal y sin conflictos: 20.445 caracteres, que el
        límite anterior de 20.000 habría rechazado con 422 aunque la vista previa pudiera emitirlo."""
        serie = await serie_de_prueba(ent)
        archivos_firmados = tuple(ArchivoFirmado(str(uuid4()), str(i), "single_issue", 100_000_000, 1_760_000_000_000_000_000)
                                  for i in range(1, 101))
        token = crear_token_vinculacion(VinculacionFirmada("Comics/Flash (1987)", str(serie), str(uuid4()), archivos_firmados), SECRETO)
        assert len(token) > 20000
        c = await confirmar(token)
        assert c.status_code == 200 and c.json()["resultado"]["global"] == "nada_vinculado"      # aceptado; los archivos no existen

    async def test_cien_archivos_con_conflictos_firmados_numeros_y_clave_cerca_de_los_limites(self, ent):
        from zascarr.services.tokens_revision import MAX_TOKEN_VINCULACION
        carpeta = "Comics/" + "x" * 240 + "/" + "y" * 240 + "/Flash (1987)"            # una clave larga (≈ 500 caracteres)
        serie = await serie_de_prueba(ent, "Batman", 1940)                              # todos los archivos contradicen la serie
        ids = await archivos(ent, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 101)), carpeta=carpeta)
        clave = carpeta
        numeros = {fid: "9" * 17 + f"{i:03d}" for i, fid in enumerate(ids.values())}      # 20 caracteres cada uno
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros=numeros)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        firmados = verificar_token_vinculacion(token, SECRETO).archivos
        assert len(firmados) == 100 and all(len(a.numero) == 20 for a in firmados) and all(a.conflictos for a in firmados)
        assert 20000 < len(token) <= MAX_TOKEN_VINCULACION                                # por encima del límite antiguo
        c = await confirmar(token)
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["con_conflicto_incluidos"] == 100

    def test_el_limite_es_el_peor_caso_calculado_con_los_codigos_reales_de_senal(self):
        import re

        from zascarr.models import IssueFormat
        from zascarr.services import revision_carpetas
        from zascarr.services.tokens_revision import (
            CODIGOS_DE_SENAL,
            EPOCA_DEL_PEOR_CASO,
            MAX_ARCHIVOS_FIRMADOS,
            MAX_CLAVE_GRUPO,
            MAX_NUMERO,
            MAX_TOKEN_VINCULACION,
        )
        fuente = Path(revision_carpetas.__file__).read_text(encoding="utf-8")
        assert set(CODIGOS_DE_SENAL) == set(re.findall(r'codigo="([a-z_]+)"', fuente)), "hay códigos de señal nuevos: actualiza CODIGOS_DE_SENAL"
        formato = max((f.value for f in IssueFormat), key=len)
        grande = 2**63 - 1                                                             # tamaño: off_t de 64 bits con signo
        mtime = (2**63 - 1) * 10**9 + 999_999_999                                       # mtime_ns: time_t de 64 bits × 10**9 + nsec
        ident = str(uuid4())
        pesados = [chr(o) for o in (*range(1, 8), *range(14, 28))]                     # controles de SEIS bytes admitidos
        peor = crear_token_vinculacion(VinculacionFirmada(
            "\x01" * MAX_CLAVE_GRUPO, ident, ident, tuple(                              # clave de controles, tal cual
                ArchivoFirmado(str(uuid4()), "\x01" * (MAX_NUMERO - 2) + pesados[i // 21] + pesados[i % 21], formato, grande, mtime, CODIGOS_DE_SENAL)
                for i in range(MAX_ARCHIVOS_FIRMADOS))), SECRETO, ahora=EPOCA_DEL_PEOR_CASO)
        assert len(peor) == MAX_TOKEN_VINCULACION                                   # ver también test_tokens_vinculacion_limite.py
        assert verificar_token_vinculacion(peor, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    async def test_el_limite_esta_acotado_un_caracter_mas_se_rechaza_en_la_validacion(self, ent):
        from zascarr.services.tokens_revision import MAX_TOKEN_VINCULACION
        justo = await confirmar("a" * MAX_TOKEN_VINCULACION)
        assert justo.status_code == 422 and isinstance(justo.json()["detail"], dict)         # pasa la validación; no es un token
        de_mas = await confirmar("a" * (MAX_TOKEN_VINCULACION + 1))
        assert de_mas.status_code == 422 and isinstance(de_mas.json()["detail"], list)       # rechazado por tamaño

    async def test_el_alta_y_la_candidata_no_se_ven_afectadas_por_el_limite_de_vinculacion(self, ent):
        from zascarr.services.tokens_revision import MAX_TOKEN_VINCULACION
        assert 40000 < MAX_TOKEN_VINCULACION < 100000                                            # acotado, no infinito


class TestSinReintentoAutomatico:

    async def test_un_fallo_que_no_es_interbloqueo_no_se_convierte_en_503(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz")
        token = await token_de(serie, ids.values())

        class OrigError(Exception):
            sqlstate = "23505"

        async def otra(self, *a, **k):
            raise DBAPIError("INSERT ...", {}, OrigError("duplicate key"))
        monkeypatch.setattr(VinculacionDeArchivos, "_vincular_archivo", otra)
        r = await confirmar(token)
        assert r.status_code == 500 and r.json()["detail"]["codigo"] == "error_inesperado"
        assert await informes(ent.banco) == []

    async def test_los_logs_no_llevan_rutas_ni_nombres(self, ent, caplog):
        import logging

        import structlog
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        token = await token_de(serie, ids.values())
        (ent.lib / "Comics/Flash (1987)/Flash 02 (1987).cbz").unlink()
        caplog.set_level(logging.DEBUG)
        with structlog.testing.capture_logs() as registros:
            assert (await confirmar(token)).status_code == 200
            assert (await confirmar(token)).status_code == 200
        volcado = " ".join([rec.getMessage() + str(getattr(rec, "args", "")) for rec in caplog.records] + [str(x) for x in registros])
        for secreto in ("Flash 01", "Flash 02", str(ent.lib), "Comics/Flash", token[:30]):
            assert secreto not in volcado, secreto
