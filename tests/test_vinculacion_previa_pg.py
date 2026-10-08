# ruff: noqa: E501
"""`POST /api/revision/vinculacion/previsualizar` (rebanada 2c) — pruebas de aceptación sobre Postgres real y
ficheros reales en un directorio temporal.

Contrato: `docs/design/rebanada-2-elegir-serie-y-vincular.md`, bloque C («Implementación 2c») y ADR 0007. Lo que se
prueba: cero escrituras, cero red, cero lecturas de contenido (ni hash) y ficheros intactos; selección inicial vacía
y token solo con una selección ejecutable; cada estado y su precedencia; los errores de disco (no encontrado frente a
no verificable); conflictos minoritarios visibles; el límite de 100; cambios de número, serie y selección reflejados
en la vista y en el token; autenticación, `no-store` y logs sin rutas ni nombres. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import builtins
import errno
import hashlib
import io
import logging
import os
import re
import shutil
import socket
import threading
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import structlog
from sqlalchemy import text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.api import revision as api_revision
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, FileFormat, Issue, IssueFormat, Series
from zascarr.services import revision_carpetas, vinculacion_previa
from zascarr.services.tokens_revision import verificar_token_vinculacion
from zascarr.services.vinculacion_previa import LIMITE_ARCHIVOS

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

SECRETO = "clave-de-prueba-para-firmar"
RUTA = "/api/revision/vinculacion/previsualizar"
CLAVE = "Comics/Flash (1987)"
SHA = "a" * 64


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd, monkeypatch, tmp_path):
    b = Banco(url_bd)
    await b.limpiar()
    lib = tmp_path / "biblioteca"
    lib.mkdir()
    monkeypatch.setattr(revision_carpetas, "get_settings", lambda: SimpleNamespace(library_path=lib))
    monkeypatch.setattr(vinculacion_previa, "get_settings", lambda: SimpleNamespace(library_path=lib))
    monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))

    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    yield SimpleNamespace(banco=b, lib=lib)
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


def cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                             headers={"Origin": "http://localhost"})


async def previsualizar(serie, *, clave=CLAVE, numeros=None, marcados=None, **extra) -> httpx.Response:
    cuerpo = {"clave": clave, "series_id": str(serie), **extra}
    if numeros is not None:
        cuerpo["numeros"] = {str(k): v for k, v in numeros.items()}
    if marcados is not None:
        cuerpo["marcados"] = [str(m) for m in marcados]
    async with cliente() as c:
        return await c.post(RUTA, json=cuerpo)


async def serie_de_prueba(entorno, titulo="Flash", anio=1987, **campos) -> UUID:
    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title=titulo, start_year=anio, tradition=ComicTradition.AMERICAN, **campos))
        await s.commit()
    return sid


async def archivos(entorno, *nombres: str, carpeta="Comics/Flash (1987)", en_disco=True, **campos) -> dict[str, UUID]:
    """Registra (y crea en disco) un archivo por nombre. Devuelve nombre → id."""
    ids: dict[str, UUID] = {}
    async with entorno.banco.fabrica() as s:
        for n in nombres:
            ruta = entorno.lib / carpeta / n
            if en_disco:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(f"contenido de {n}".encode() * 7)
            f = File(id=uuid4(), file_path=str(ruta), file_name=n, file_format=FileFormat.CBZ,
                     metadata_={"match_status": "unsorted"}, **campos)
            s.add(f)
            ids[n] = f.id
        await s.commit()
    return ids


def por_id(r: httpx.Response) -> dict[str, dict]:
    return {a["id"]: a for a in r.json()["archivos"]}


def por_nombre(r: httpx.Response) -> dict[str, dict]:
    return {a["nombre"]: a for a in r.json()["archivos"]}


async def instantanea(b: Banco) -> dict:
    async with b.fabrica() as s:
        return {t: [tuple(r) for r in (await s.execute(text(f"SELECT * FROM {t} ORDER BY 1"))).all()]
                for t in ("files", "issues", "series", "asignacion_operaciones", "alta_operaciones", "local_aliases", "wishlist")}


def huella_disco(lib: Path) -> dict[str, tuple[int, int, bytes]]:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes()) for p in sorted(lib.rglob("*")) if p.is_file()}


def escrituras(b: Banco, desde: int) -> list[str]:
    return [q for q in b.sentencias[desde:] if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q, re.I) or "pg_advisory" in q]


# ── Sin efectos: solo lectura ───────────────────────────────────────────────────────────────────

class TestSoloLectura:

    async def test_cero_escrituras_cero_red_cero_contenido_y_ficheros_intactos(self, entorno, monkeypatch):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz")
        await previsualizar(serie)                               # calienta el pool: la conexión ya existe
        antes_bd, antes_disco, n = await instantanea(entorno.banco), huella_disco(entorno.lib), len(entorno.banco.sentencias)
        raiz = str(entorno.lib)

        intentos: list[str] = []

        def vigilado(real):
            def _open(f, *a, **kw):
                if isinstance(f, (str, os.PathLike)) and str(f).startswith(raiz):
                    intentos.append(str(f))
                    raise AssertionError("la vista previa no puede abrir ni leer ficheros de la biblioteca")
                return real(f, *a, **kw)
            return _open
        with monkeypatch.context() as m:                          # los vigilantes solo durante la petición
            m.setattr(builtins, "open", vigilado(builtins.open))
            m.setattr(io, "open", vigilado(io.open))
            m.setattr(os, "open", vigilado(os.open))
            m.setattr(os, "scandir", vigilado(os.scandir))               # tampoco se recorren carpetas
            calculos: list[str] = []
            if hasattr(hashlib, "file_digest"):
                m.setattr(hashlib, "file_digest", lambda *a, **k: calculos.append("hash"))

            def sin_red(*a, **k):
                raise AssertionError("acceso a la red")
            m.setattr(socket.socket, "connect", sin_red)
            m.setattr(httpx.HTTPTransport, "handle_request", sin_red)
            m.setattr(httpx.AsyncHTTPTransport, "handle_async_request", sin_red)
            r = await previsualizar(serie, marcados=list(ids.values()))
        assert r.status_code == 200, r.text
        assert intentos == [] and calculos == []
        assert escrituras(entorno.banco, n) == []
        assert await instantanea(entorno.banco) == antes_bd
        assert huella_disco(entorno.lib) == antes_disco                      # bytes, tamaño y mtime idénticos

    async def test_no_crea_issues_ni_aprende_alias_ni_toca_files(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        antes = await instantanea(entorno.banco)
        r = await previsualizar(serie, marcados=list(ids.values()), numeros={ids["Flash 01 (1987).cbz"]: "7"})
        assert r.status_code == 200 and r.json()["token"]
        despues = await instantanea(entorno.banco)
        assert despues == antes and despues["issues"] == [] and despues["local_aliases"] == []

    async def test_solo_se_llama_a_stat_y_en_un_hilo_aparte(self, entorno, monkeypatch):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:02d} (1987).cbz" for i in range(1, 6)))
        llamadas: list[tuple[str, int]] = []
        real = os.stat

        def espia(ruta, *a, **kw):
            if str(ruta).startswith(str(entorno.lib)):
                llamadas.append((str(ruta), threading.get_ident()))
            return real(ruta, *a, **kw)
        monkeypatch.setattr(os, "stat", espia)
        assert (await previsualizar(serie)).status_code == 200
        propias = [h for r, h in llamadas if r != str(entorno.lib)]
        assert len(propias) == 5 and all(h != threading.get_ident() for _, h in llamadas)   # nunca en el bucle de eventos

    async def test_sin_destino_ni_movimientos_en_la_respuesta(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        texto = (await previsualizar(serie)).text.lower()
        for prohibida in ("destino", "mover", "moverá", "renombr", "ruta_nueva", "sha256", "hash"):
            assert prohibida not in texto, prohibida

    async def test_las_consultas_son_constantes_con_20_y_con_100_archivos(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 21)))
        n = len(entorno.banco.sentencias)
        assert (await previsualizar(serie)).status_code == 200
        pocas = len(entorno.banco.sentencias) - n
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(21, 101)))
        n = len(entorno.banco.sentencias)
        assert (await previsualizar(serie)).status_code == 200
        muchas = len(entorno.banco.sentencias) - n
        assert pocas == muchas and muchas <= 8


# ── Selección y token ───────────────────────────────────────────────────────────────────────────

class TestSeleccionYToken:

    async def test_todo_empieza_sin_marcar_y_sin_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz")
        r = await previsualizar(serie)
        c = r.json()
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert c["token"] is None and c["motivo_sin_token"] == "No has marcado ningún archivo."
        assert all(not a["marcado"] and not a["incluido_en_token"] for a in c["archivos"])
        assert all(a["marcable"] for a in c["archivos"]) and c["totales"]["marcados"] == 0 and c["totales"]["sin_marcar"] == 3
        assert not {"seleccionado_por_defecto", "preseleccionado", "recomendado", "por_defecto"} & set(c)

    async def test_marcar_un_archivo_ejecutable_emite_el_token_con_lo_que_se_vio(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        elegido = ids["Flash 02 (1987).cbz"]
        c = (await previsualizar(serie, marcados=[elegido])).json()
        assert c["motivo_sin_token"] is None and c["totales"]["a_vincular"] == 1 and c["totales"]["marcados"] == 1
        v = verificar_token_vinculacion(c["token"], SECRETO)
        assert v is not None and (v.clave, v.series_id) == (CLAVE, str(serie))
        (a,) = v.archivos
        real = (entorno.lib / "Comics/Flash (1987)/Flash 02 (1987).cbz").stat()
        assert (a.id, a.numero, a.formato, a.tamano, a.mtime_ns) == (str(elegido), "2", "single_issue", real.st_size, real.st_mtime_ns)
        assert UUID(v.operacion)

    async def test_el_token_es_v2_y_lleva_los_conflictos_vistos_o_una_lista_vacia(self, entorno):
        serie = await serie_de_prueba(entorno, "Flash", 1987)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 10 (1999).cbz")
        c = (await previsualizar(serie, marcados=list(ids.values()))).json()
        from zascarr.services.tokens_revision import verificar_token
        datos = verificar_token(c["token"], "vincular", CLAVE, SECRETO)
        assert datos["version"] == 2 and all("conflictos" in a for a in datos["archivos"])
        firmados = {a.id: a.conflictos for a in verificar_token_vinculacion(c["token"], SECRETO).archivos}
        assert firmados[str(ids["Flash 01 (1987).cbz"])] == () and firmados[str(ids["Flash 10 (1999).cbz"])]
        vistos = {s["codigo"] for a in c["archivos"] if a["nombre"] == "Flash 10 (1999).cbz" for s in a["conflictos"] if s["severidad"] == "conflicto"}
        assert set(firmados[str(ids["Flash 10 (1999).cbz"])]) == vistos

    async def test_el_token_solo_lleva_lo_marcado_y_ejecutable(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz", "Flash (1987).cbz")
        c = (await previsualizar(serie, marcados=[ids["Flash 01 (1987).cbz"], ids["Flash (1987).cbz"]])).json()
        a = por_nombre_json(c)
        assert a["Flash (1987).cbz"]["marcado"] and not a["Flash (1987).cbz"]["incluido_en_token"]    # marcado, bloqueado
        assert c["totales"]["marcados"] == 2 and c["totales"]["a_vincular"] == 1 and c["totales"]["marcados_bloqueados"] == 1
        assert [x.id for x in verificar_token_vinculacion(c["token"], SECRETO).archivos] == [str(ids["Flash 01 (1987).cbz"])]

    async def test_el_token_lleva_la_edicion_de_cada_archivo(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Omnigold 5 (1987).cbz", "Flash 06 (1987).cbz")
        c = (await previsualizar(serie, marcados=list(ids.values()))).json()
        formatos = {a["nombre"]: a["formato"] for a in c["archivos"]}
        firmados = {a.id: a.formato for a in verificar_token_vinculacion(c["token"], SECRETO).archivos}
        assert firmados == {str(ids[n]): f for n, f in formatos.items()} and len(set(firmados.values())) == 2

    async def test_solo_bloqueados_marcados_no_dan_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash (1987).cbz")
        c = (await previsualizar(serie, marcados=list(ids.values()))).json()
        assert c["token"] is None and "Ninguno de los archivos marcados se puede vincular" in c["motivo_sin_token"]

    async def test_no_hay_ningun_marcado_de_antemano_ni_con_un_unico_archivo(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        c = (await previsualizar(serie)).json()
        assert c["archivos"][0]["marcado"] is False and c["token"] is None

    async def test_un_token_de_vinculacion_no_sirve_como_otro_proposito(self, entorno):
        from zascarr.services.tokens_revision import verificar_token_alta, verificar_token_candidata
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        token = (await previsualizar(serie, marcados=list(ids.values()))).json()["token"]
        assert verificar_token_alta(token, SECRETO) is None and verificar_token_candidata(token, CLAVE, SECRETO) is None
        assert verificar_token_vinculacion(token, "otra-clave") is None and verificar_token_vinculacion(token[:-2] + "zz", SECRETO) is None


def por_nombre_json(c: dict) -> dict[str, dict]:
    return {a["nombre"]: a for a in c["archivos"]}


# ── Estados y precedencia ───────────────────────────────────────────────────────────────────────

class TestEstados:

    async def test_numero_ausente(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash (1987).cbz")
        a = (await previsualizar(serie, marcados=list(ids.values()))).json()["archivos"][0]
        assert (a["estado"], a["motivos"], a["numero"], a["numero_origen"]) == ("requiere_numero", ["requiere_numero"], None, "ninguno")
        assert a["marcable"] is False and "Falta el número" in a["texto"]

    async def test_el_numero_editado_por_la_persona_resuelve_el_estado_y_se_marca_como_suyo(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash (1987).cbz")
        fid = ids["Flash (1987).cbz"]
        a = (await previsualizar(serie, numeros={fid: " 12 "})).json()["archivos"][0]
        assert (a["estado"], a["numero"], a["numero_origen"], a["numero_del_nombre"]) == ("se_vincularia", "12", "persona", None)

    async def test_borrar_el_numero_editado_vuelve_a_pedirlo(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 05 (1987).cbz")
        a = (await previsualizar(serie, numeros={ids["Flash 05 (1987).cbz"]: ""})).json()["archivos"][0]
        assert (a["estado"], a["numero"], a["numero_del_nombre"]) == ("requiere_numero", None, "5")

    async def test_numero_repetido_en_el_grupo_bloquea_a_todos_los_que_lo_comparten(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 03 (1987).cbz", "Flash 03 (1987)(1).cbz", "Flash 04 (1987).cbz")
        c = (await previsualizar(serie, marcados=list(ids.values()))).json()
        a = por_nombre_json(c)
        assert a["Flash 03 (1987).cbz"]["estado"] == a["Flash 03 (1987)(1).cbz"]["estado"] == "numero_repetido_en_el_grupo"
        assert a["Flash 04 (1987).cbz"]["estado"] == "se_vincularia"
        assert c["totales"]["a_vincular"] == 1 and c["totales"]["marcados_bloqueados"] == 2

    async def test_el_repetido_no_distingue_mayusculas(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        numeros = {ids["Flash 01 (1987).cbz"]: "5A", ids["Flash 02 (1987).cbz"]: "5a"}
        sin_marcar = por_nombre_json((await previsualizar(serie, numeros=numeros)).json())
        assert all(x["repetido_con"] for x in sin_marcar.values())                       # se identifican
        marcados = por_nombre_json((await previsualizar(serie, numeros=numeros, marcados=list(ids.values()))).json())
        assert {x["estado"] for x in marcados.values()} == {"numero_repetido_en_el_grupo"}

    async def test_editar_un_numero_repetido_lo_resuelve(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 03 (1987).cbz", "Flash 03 (1987)(1).cbz")
        a = por_nombre_json((await previsualizar(serie, numeros={ids["Flash 03 (1987)(1).cbz"]: "30"})).json())
        assert a["Flash 03 (1987).cbz"]["estado"] == a["Flash 03 (1987)(1).cbz"]["estado"] == "se_vincularia"

    async def test_numero_que_ya_tiene_un_archivo_en_la_serie(self, entorno):
        serie = await serie_de_prueba(entorno)
        async with entorno.banco.fabrica() as s:
            issue = Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE)
            s.add(issue)
            await s.flush()
            s.add(File(id=uuid4(), file_path="/otra/ruta.cbz", file_name="ruta.cbz", file_format=FileFormat.CBZ, issue_id=issue.id))
            await s.commit()
        await archivos(entorno, "Flash 03 (1987).cbz")
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert (a["estado"], a["marcable"]) == ("numero_ya_existe", False) and "ya tiene 1 archivo" in a["texto"]

    async def test_un_issue_de_la_serie_sin_archivos_se_reutilizaria_y_no_bloquea(self, entorno):
        serie = await serie_de_prueba(entorno)
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE))
            await s.commit()
        await archivos(entorno, "Flash 03 (1987).cbz")
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert (a["estado"], a["marcable"], a["issue_existente"]) == ("se_vincularia", True, True)

    async def test_colision_de_edicion(self, entorno):
        """Mismo número que un `Issue` de la serie con otra edición (B15: grapa #12 frente a Omnigold 12)."""
        serie = await serie_de_prueba(entorno)
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="12", format=IssueFormat.OMNIBUS))
            await s.commit()
        await archivos(entorno, "Flash 12 (1987).cbz")
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert (a["estado"], a["marcable"]) == ("colision_de_edicion", False)
        assert "otra edición" in a["texto"] and "omnibus" in a["texto"]

    async def test_numero_ambiguo_si_la_serie_tiene_varios_issues_con_esa_clave(self, entorno):
        serie = await serie_de_prueba(entorno)
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE, volume=1))
            s.add(Issue(series_id=serie, issue_number="3", format=IssueFormat.SINGLE_ISSUE, volume=2))
            await s.commit()
        await archivos(entorno, "Flash 03 (1987).cbz")
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert (a["estado"], a["marcable"]) == ("numero_ambiguo", False) and "más de un número" in a["texto"]

    async def test_la_colision_de_edicion_no_distingue_mayusculas(self, entorno):
        serie = await serie_de_prueba(entorno)
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=serie, issue_number="5a", format=IssueFormat.OMNIBUS))
            await s.commit()
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        a = (await previsualizar(serie, numeros={ids["Flash 01 (1987).cbz"]: "5A"})).json()["archivos"][0]
        assert a["estado"] == "colision_de_edicion" and a["numero"] == "5A"          # se conserva el texto presentado

    async def test_la_edicion_sale_del_nombre(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Omnigold 5 (1987).cbz", "Flash 06 (1987).cbz")
        a = por_nombre_json((await previsualizar(serie)).json())
        assert a["Omnigold 5 (1987).cbz"]["formato"] != a["Flash 06 (1987).cbz"]["formato"] == "single_issue"

    async def test_registro_ya_vinculado_se_muestra_y_no_se_puede_marcar(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        async with entorno.banco.fabrica() as s:
            issue = Issue(series_id=serie, issue_number="9")
            s.add(issue)
            await s.flush()
            vinculado = File(id=uuid4(), file_path=str(entorno.lib / "Comics/Flash (1987)/Flash 09 (1987).cbz"),
                             file_name="Flash 09 (1987).cbz", file_format=FileFormat.CBZ, issue_id=issue.id)
            s.add(vinculado)
            await s.commit()
        c = (await previsualizar(serie, marcados=[vinculado.id])).json()
        a = por_id_json(c)[str(vinculado.id)]
        assert (a["estado"], a["marcable"], a["marcado"], a["incluido_en_token"]) == ("ya_vinculado", False, True, False)
        assert c["token"] is None

    async def test_un_archivo_ajeno_al_grupo_es_422(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        otro = (await archivos(entorno, "Batman 01.cbz", carpeta="Comics/Batman (1940)"))["Batman 01.cbz"]
        for cuerpo in ({"marcados": [otro]}, {"numeros": {otro: "1"}}, {"marcados": [uuid4()]}):
            r = await previsualizar(serie, **cuerpo)
            assert r.status_code == 422 and r.json()["detail"]["codigo"] == "archivo_ajeno_al_grupo", cuerpo

    async def test_operacion_de_asignacion_viva(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        async with entorno.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"),
                {"f": ids["Flash 01 (1987).cbz"], "s": serie, "sha": SHA})
            await s.commit()
        a = por_nombre_json((await previsualizar(serie, marcados=list(ids.values()))).json())
        assert (a["Flash 01 (1987).cbz"]["estado"], a["Flash 01 (1987).cbz"]["marcable"]) == ("en_curso", False)
        assert a["Flash 02 (1987).cbz"]["estado"] == "se_vincularia"

    async def test_una_operacion_cerrada_no_bloquea(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        async with entorno.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('limpiada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"),
                {"f": ids["Flash 01 (1987).cbz"], "s": serie, "sha": SHA})
            await s.commit()
        assert (await previsualizar(serie)).json()["archivos"][0]["estado"] == "se_vincularia"

    async def test_precedencia_con_varios_impedimentos(self, entorno):
        """Sin archivo en disco, sin número y con una operación viva: el estado es el primero de la lista de
        precedencia y TODOS los impedimentos constan, en orden."""
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash (1987).cbz", en_disco=False)
        async with entorno.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('confirmada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"),
                {"f": ids["Flash (1987).cbz"], "s": serie, "sha": SHA})
            await s.commit()
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert a["estado"] == "en_curso" and a["motivos"] == ["en_curso", "origen_no_encontrado", "requiere_numero"]

    async def test_origen_ausente_antes_que_numero_y_numero_antes_que_repetido(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 05 (1987).cbz", en_disco=False)
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert a["estado"] == "origen_no_encontrado" and a["motivos"] == ["origen_no_encontrado"]
        assert "pendiente de verificar" in a["texto"]
        ids = await archivos(entorno, "Flash 07 (1987).cbz", "Flash 07 (1987)(1).cbz")
        b = por_nombre_json((await previsualizar(serie, marcados=list(ids.values()))).json())
        assert b["Flash 07 (1987).cbz"]["estado"] == "numero_repetido_en_el_grupo"


def por_id_json(c: dict) -> dict[str, dict]:
    return {a["id"]: a for a in c["archivos"]}


# ── Errores de disco ────────────────────────────────────────────────────────────────────────────

class TestErroresDeDisco:

    async def test_no_encontrado_no_es_lo_mismo_que_no_verificable(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", en_disco=False)
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert (a["estado"], a["causa"]) == ("origen_no_encontrado", None)

    async def test_sin_permiso_no_afirma_que_haya_desaparecido(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        carpeta = entorno.lib / "Comics/Flash (1987)"
        os.chmod(carpeta, 0)
        try:
            a = (await previsualizar(serie, marcados=[])).json()["archivos"][0]
        finally:
            os.chmod(carpeta, 0o755)
        assert (a["estado"], a["causa"], a["marcable"]) == ("origen_no_verificable", "permiso", False)
        assert "No significa que haya desaparecido" in a["texto"] and "no hay ningún archivo" not in a["texto"]

    async def test_un_fallo_de_lectura_del_disco_es_no_verificable(self, entorno, monkeypatch):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        real = os.stat

        def falla(ruta, *a, **kw):
            if str(ruta).endswith("Flash 01 (1987).cbz"):
                raise OSError(errno.EIO, "Input/output error")
            return real(ruta, *a, **kw)
        monkeypatch.setattr(os, "stat", falla)
        a = por_nombre_json((await previsualizar(serie)).json())
        assert (a["Flash 01 (1987).cbz"]["estado"], a["Flash 01 (1987).cbz"]["causa"]) == ("origen_no_verificable", "error_de_lectura")
        assert a["Flash 02 (1987).cbz"]["estado"] == "se_vincularia"
        assert "error de lectura" in a["Flash 01 (1987).cbz"]["texto"] and "No significa que haya desaparecido" in a["Flash 01 (1987).cbz"]["texto"]

    async def test_la_biblioteca_inaccesible_hace_a_todos_no_verificables(self, entorno):
        """Un volumen que no responde no es una colección de archivos desaparecidos."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        shutil.rmtree(entorno.lib)                                              # «disco desmontado»
        c = (await previsualizar(serie, marcados=[])).json()
        assert {a["estado"] for a in c["archivos"]} == {"origen_no_verificable"}
        assert {a["causa"] for a in c["archivos"]} == {"biblioteca_no_accesible"}
        assert "volumen" not in c["archivos"][0]["texto"] and "desmontado" in c["archivos"][0]["texto"]

    async def test_una_ruta_que_no_es_un_archivo_es_no_verificable(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", en_disco=False)
        (entorno.lib / "Comics/Flash (1987)/Flash 01 (1987).cbz").mkdir(parents=True)
        a = (await previsualizar(serie, marcados=list(ids.values()))).json()["archivos"][0]
        assert (a["estado"], a["causa"]) == ("origen_no_verificable", "no_es_un_archivo")

    async def test_varios_ausentes_a_la_vez_avisan_de_que_puede_ser_el_disco(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:02d} (1987).cbz" for i in range(1, 8)), en_disco=False)
        (entorno.lib / "Comics").mkdir(parents=True)                           # la biblioteca responde, los archivos no
        c = (await previsualizar(serie)).json()
        aviso = [s for s in c["avisos_de_grupo"] if s["codigo"] == "ningun_origen_encontrado"]
        assert aviso and "no es que hayan desaparecido" in aviso[0]["texto"]
        assert {a["estado"] for a in c["archivos"]} == {"origen_no_encontrado"}

    async def test_pocos_ausentes_no_lanzan_el_aviso_del_disco(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", en_disco=False)
        (entorno.lib / "Comics").mkdir(parents=True)
        c = (await previsualizar(serie)).json()
        assert {a["estado"] for a in c["archivos"]} == {"origen_no_encontrado"}
        assert not [s for s in c["avisos_de_grupo"] if s["codigo"] == "ningun_origen_encontrado"]

    async def test_ambos_bloquean_la_seleccion_y_no_dan_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", en_disco=False)
        c = (await previsualizar(serie, marcados=list(ids.values()))).json()
        assert c["token"] is None and c["totales"]["marcados_bloqueados"] == 2


# ── Conflictos con la serie elegida ─────────────────────────────────────────────────────────────

class TestConflictos:

    async def test_un_conflicto_minoritario_es_visible_aunque_la_mayoria_coincida(self, entorno):
        serie = await serie_de_prueba(entorno, "Flash", 1987)
        nombres = [f"Flash {i:02d} (1987).cbz" for i in range(1, 10)] + ["Flash 10 (1999).cbz"]
        await archivos(entorno, *nombres)
        c = (await previsualizar(serie)).json()
        a = por_nombre_json(c)
        minoritario = a["Flash 10 (1999).cbz"]
        assert minoritario["estado"] == "con_conflicto_de_carpeta" and minoritario["marcable"] is True
        assert any(s["severidad"] == "conflicto" for s in minoritario["conflictos"])
        assert all(not a[n]["conflictos"] or all(s["severidad"] != "conflicto" for s in a[n]["conflictos"]) for n in nombres[:-1])
        assert c["totales"]["por_estado"]["con_conflicto_de_carpeta"] == 1 and c["totales"]["por_estado"]["se_vincularia"] == 9

    async def test_marcar_un_archivo_con_conflicto_es_decision_de_la_persona_y_consta(self, entorno):
        serie = await serie_de_prueba(entorno, "Flash", 1987)
        ids = await archivos(entorno, "Flash 10 (1999).cbz", "Flash 01 (1987).cbz")
        c = (await previsualizar(serie, marcados=[ids["Flash 10 (1999).cbz"]])).json()
        assert c["totales"]["a_vincular"] == 1 and c["token"]
        assert por_nombre_json(c)["Flash 10 (1999).cbz"]["incluido_en_token"] is True

    async def test_las_senales_se_recalculan_contra_la_serie_elegida(self, entorno):
        coherente = await serie_de_prueba(entorno, "Flash", 1987)
        otra = await serie_de_prueba(entorno, "Batman", 1940)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        con_flash = (await previsualizar(coherente)).json()
        con_batman = (await previsualizar(otra)).json()
        assert {a["estado"] for a in con_flash["archivos"]} == {"se_vincularia"}
        assert {a["estado"] for a in con_batman["archivos"]} == {"con_conflicto_de_carpeta"}
        assert all(any(s["codigo"] == "titulo_distinto" for s in a["conflictos"]) for a in con_batman["archivos"])
        assert con_flash["serie"]["titulo"] == "Flash" and con_batman["serie"]["titulo"] == "Batman"

    async def test_los_avisos_de_grupo_son_las_senales_de_la_rebanada_1_sin_archivos_concretos(self, entorno):
        serie = await serie_de_prueba(entorno, "Flash", 1987)
        await archivos(entorno, "Flash 01 (1987).cbz")
        c = (await previsualizar(serie)).json()
        assert all(not s["archivos"] for s in c["avisos_de_grupo"])


# ── Cambios reflejados ──────────────────────────────────────────────────────────────────────────

class TestCambiosReflejados:

    async def test_cambiar_un_numero_cambia_la_vista_y_el_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        fid = ids["Flash 01 (1987).cbz"]
        a = (await previsualizar(serie, marcados=[fid])).json()
        b = (await previsualizar(serie, marcados=[fid], numeros={fid: "11"})).json()
        assert a["archivos"][0]["numero"] == "1" and b["archivos"][0]["numero"] == "11" and b["archivos"][0]["numero_origen"] == "persona"
        assert verificar_token_vinculacion(a["token"], SECRETO).archivos[0].numero == "1"
        assert verificar_token_vinculacion(b["token"], SECRETO).archivos[0].numero == "11"
        assert a["token"] != b["token"]

    async def test_cambiar_la_seleccion_cambia_la_vista_y_el_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        uno = (await previsualizar(serie, marcados=[ids["Flash 01 (1987).cbz"]])).json()
        dos = (await previsualizar(serie, marcados=list(ids.values()))).json()
        ninguno = (await previsualizar(serie, marcados=[])).json()
        assert [len(verificar_token_vinculacion(t, SECRETO).archivos) for t in (uno["token"], dos["token"])] == [1, 2]
        assert ninguno["token"] is None and (uno["totales"]["marcados"], dos["totales"]["marcados"]) == (1, 2)

    async def test_cambiar_la_serie_cambia_la_vista_y_el_token(self, entorno):
        a_ = await serie_de_prueba(entorno, "Flash", 1987)
        b_ = await serie_de_prueba(entorno, "Batman", 1940)
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        ta = (await previsualizar(a_, marcados=list(ids.values()))).json()
        tb = (await previsualizar(b_, marcados=list(ids.values()))).json()
        assert verificar_token_vinculacion(ta["token"], SECRETO).series_id == str(a_)
        assert verificar_token_vinculacion(tb["token"], SECRETO).series_id == str(b_)
        assert (ta["serie"]["titulo"], tb["serie"]["titulo"]) == ("Flash", "Batman")

    async def test_la_serie_elegida_decide_los_estados_por_numero(self, entorno):
        """El mismo archivo choca con los `Issue` de una serie y no con los de otra."""
        a_ = await serie_de_prueba(entorno, "Flash", 1987)
        b_ = await serie_de_prueba(entorno, "Flash (otra)", 1987)
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=b_, issue_number="1", format=IssueFormat.OMNIBUS))
            await s.commit()
        await archivos(entorno, "Flash 01 (1987).cbz")
        assert (await previsualizar(a_)).json()["archivos"][0]["estado"] == "se_vincularia"
        assert (await previsualizar(b_)).json()["archivos"][0]["estado"] == "colision_de_edicion"

    async def test_dos_vistas_previas_dan_tokens_independientes_y_los_dos_verifican(self, entorno):
        """Documenta la semántica vigente (ficha 2c, «Sustitución de tokens»): emitir un token nuevo NO invalida los
        anteriores en el servidor; cada uno es una fotografía firmada que caduca a los 15 min. La invalidación
        del anterior exigiría persistencia y está pendiente de decisión para 2d."""
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        t1 = (await previsualizar(serie, marcados=list(ids.values()))).json()["token"]
        t2 = (await previsualizar(serie, marcados=list(ids.values()), numeros={ids["Flash 01 (1987).cbz"]: "5"})).json()["token"]
        v1, v2 = verificar_token_vinculacion(t1, SECRETO), verificar_token_vinculacion(t2, SECRETO)
        assert v1 and v2 and v1.operacion != v2.operacion and v1.archivos[0].numero == "1" and v2.archivos[0].numero == "5"


# ── Límite de 100 ───────────────────────────────────────────────────────────────────────────────

class TestLimite:

    async def test_a_lo_sumo_100_archivos_y_el_resto_explicado(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 131)))
        c = (await previsualizar(serie)).json()
        p = c["pagina"]
        assert (p["maximo"], p["en_el_grupo"], p["tratados"], p["desde"], p["hasta"], p["hay_mas"], p["cursor"]) == (
            LIMITE_ARCHIVOS, 130, 100, 1, 100, True, None)
        assert p["siguiente"] and "130 archivos" in p["texto"] and "valen solo para los archivos de esta página" in p["texto"]
        assert len(c["archivos"]) == 100                                          # el resto solo consta en el recuento

    async def test_un_archivo_marcado_fuera_de_la_pagina_sale_explicado_y_sin_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 131)))
        fuera = ids["Flash 125 (1987).cbz"]
        c = (await previsualizar(serie, marcados=[fuera])).json()
        a = por_id_json(c)[str(fuera)]
        assert (a["estado"], a["marcable"], a["marcado"], a["incluido_en_token"]) == ("fuera_de_la_pagina", False, True, False)
        assert str(LIMITE_ARCHIVOS) in a["texto"] and c["token"] is None
        assert len(c["archivos"]) == 101

    async def test_los_stat_estan_acotados_a_100_mas_la_biblioteca(self, entorno, monkeypatch):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 131)))
        n_stat: list[str] = []
        real = os.stat

        def espia(ruta, *a, **kw):
            if str(ruta).startswith(str(entorno.lib)):
                n_stat.append(str(ruta))
            return real(ruta, *a, **kw)
        monkeypatch.setattr(os, "stat", espia)
        assert (await previsualizar(serie)).status_code == 200
        assert len([r for r in n_stat if r != str(entorno.lib)]) == 100

    async def test_los_cien_primeros_se_eligen_por_nombre_y_id(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 131)))
        nombres = [a["nombre"] for a in (await previsualizar(serie)).json()["archivos"]]
        assert nombres == sorted(nombres) and nombres[0] == "Flash 001 (1987).cbz" and nombres[-1] == "Flash 100 (1987).cbz"


# ── Copias: elegir una sin falsear su número ────────────────────────────────────────────────────

class TestCopiasDelMismoNumero:
    """Dos copias del número 3: la vista las identifica, pero la persona puede vincular UNA y dejar la otra pendiente.
    Lo único imposible es llevar las dos en la misma selección ejecutable. Nada elige, fusiona ni elimina una copia."""

    NOMBRES = ("Flash 03 (1987).cbz", "Flash 03 (1987)(1).cbz")

    async def _preparar(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, *self.NOMBRES, "Flash 04 (1987).cbz")
        return serie, ids

    async def test_ninguna_marcada_las_identifica_a_las_dos_sin_bloquear(self, entorno):
        serie, ids = await self._preparar(entorno)
        c = (await previsualizar(serie)).json()
        a = por_nombre_json(c)
        for n in self.NOMBRES:
            otro = ids[next(x for x in self.NOMBRES if x != n)]
            assert a[n]["repetido_con"] == [str(otro)] and a[n]["estado"] == "se_vincularia" and a[n]["marcable"] is True
            assert "no los dos a la vez" in a[n]["texto"]
        assert a["Flash 04 (1987).cbz"]["repetido_con"] == [] and c["totales"]["numeros_repetidos"] == 2
        assert c["token"] is None

    @pytest.mark.parametrize("elegida", NOMBRES)
    async def test_marcar_solo_una_copia_permite_vincularla_y_deja_la_otra_pendiente(self, entorno, elegida):
        serie, ids = await self._preparar(entorno)
        c = (await previsualizar(serie, marcados=[ids[elegida]])).json()
        a = por_nombre_json(c)
        otra = next(n for n in self.NOMBRES if n != elegida)
        assert (a[elegida]["estado"], a[elegida]["incluido_en_token"]) == ("se_vincularia", True)
        assert (a[otra]["marcado"], a[otra]["incluido_en_token"], a[otra]["estado"]) == (False, False, "se_vincularia")
        firmados = verificar_token_vinculacion(c["token"], SECRETO).archivos
        assert [(x.id, x.numero) for x in firmados] == [(str(ids[elegida]), "3")]           # sin falsear el número
        assert c["totales"]["a_vincular"] == 1 and c["totales"]["marcados_bloqueados"] == 0

    async def test_marcar_las_dos_las_bloquea_a_las_dos_y_no_elige_por_la_persona(self, entorno):
        serie, ids = await self._preparar(entorno)
        c = (await previsualizar(serie, marcados=[ids[n] for n in self.NOMBRES])).json()
        a = por_nombre_json(c)
        for n in self.NOMBRES:
            assert (a[n]["estado"], a[n]["marcable"], a[n]["incluido_en_token"]) == ("numero_repetido_en_el_grupo", False, False)
            assert "marca solo uno" in a[n]["texto"]
        assert c["token"] is None and c["totales"]["marcados_bloqueados"] == 2

    async def test_dos_marcadas_y_una_tercera_distinta_solo_lleva_la_tercera(self, entorno):
        serie, ids = await self._preparar(entorno)
        c = (await previsualizar(serie, marcados=list(ids.values()))).json()
        firmados = verificar_token_vinculacion(c["token"], SECRETO).archivos
        assert [x.id for x in firmados] == [str(ids["Flash 04 (1987).cbz"])] and c["totales"]["marcados_bloqueados"] == 2

    async def test_desmarcar_una_de_las_dos_resuelve_el_conflicto(self, entorno):
        serie, ids = await self._preparar(entorno)
        ambas = (await previsualizar(serie, marcados=[ids[n] for n in self.NOMBRES])).json()
        una = (await previsualizar(serie, marcados=[ids[self.NOMBRES[0]]])).json()
        assert ambas["token"] is None and una["token"]

    async def test_una_copia_marcada_pero_bloqueada_por_otro_motivo_no_bloquea_a_la_otra(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 03 (1987).cbz")
        sin_disco = await archivos(entorno, "Flash 03 (1987)(1).cbz", en_disco=False)
        c = (await previsualizar(serie, marcados=[ids["Flash 03 (1987).cbz"], sin_disco["Flash 03 (1987)(1).cbz"]])).json()
        a = por_nombre_json(c)
        assert a["Flash 03 (1987).cbz"]["estado"] == "se_vincularia" and a["Flash 03 (1987)(1).cbz"]["estado"] == "origen_no_encontrado"
        assert c["token"] and [x.id for x in verificar_token_vinculacion(c["token"], SECRETO).archivos] == [str(ids["Flash 03 (1987).cbz"])]

    async def test_tres_copias_dos_marcadas_bloquean_solo_a_esas_dos(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 03 (1987).cbz", "Flash 03 (1987)(1).cbz", "Flash 03 (1987)(2).cbz")
        marcadas = [ids["Flash 03 (1987).cbz"], ids["Flash 03 (1987)(2).cbz"]]
        a = por_nombre_json((await previsualizar(serie, marcados=marcadas)).json())
        assert {n: x["estado"] for n, x in a.items()} == {
            "Flash 03 (1987).cbz": "numero_repetido_en_el_grupo", "Flash 03 (1987)(1).cbz": "se_vincularia",
            "Flash 03 (1987)(2).cbz": "numero_repetido_en_el_grupo"}
        assert all(len(x["repetido_con"]) == 2 for x in a.values())

    async def test_el_numero_editado_a_mano_cuenta_igual_para_el_repetido(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        numeros = {ids["Flash 01 (1987).cbz"]: "9", ids["Flash 02 (1987).cbz"]: "9"}
        una = (await previsualizar(serie, numeros=numeros, marcados=[ids["Flash 01 (1987).cbz"]])).json()
        ambas = (await previsualizar(serie, numeros=numeros, marcados=list(ids.values()))).json()
        assert una["token"] and ambas["token"] is None

    async def test_vincular_una_copia_no_obliga_a_cambiar_el_numero_de_la_otra(self, entorno):
        """Lo que se quería evitar: tener que falsear una copia como «30» para poder elegir la otra."""
        serie, ids = await self._preparar(entorno)
        c = (await previsualizar(serie, marcados=[ids[self.NOMBRES[1]]])).json()
        assert c["token"] and all(a["numero_origen"] == "nombre" for a in c["archivos"])


# ── Páginas: llegar a los registros posteriores aunque los primeros estén bloqueados ─────────────

class TestPaginas:

    async def _grupo_con_los_cien_primeros_bloqueados(self, entorno, total=130):
        """Los 100 primeros por nombre NO existen en disco (bloqueados); los demás sí."""
        serie = await serie_de_prueba(entorno)
        bloqueados = await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 101)), en_disco=False)
        ejecutables = await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(101, total + 1)))
        return serie, bloqueados, ejecutables

    async def test_con_los_cien_primeros_bloqueados_se_llega_a_los_siguientes_y_se_previsualiza_uno(self, entorno):
        serie, bloqueados, ejecutables = await self._grupo_con_los_cien_primeros_bloqueados(entorno)
        p1 = (await previsualizar(serie, marcados=list(bloqueados.values()))).json()
        assert {a["estado"] for a in p1["archivos"]} == {"origen_no_encontrado"}
        assert p1["token"] is None and p1["pagina"]["hay_mas"] and p1["pagina"]["siguiente"]

        p2 = (await previsualizar(serie, cursor=p1["pagina"]["siguiente"], marcados=[ejecutables["Flash 105 (1987).cbz"]])).json()
        pg = p2["pagina"]
        assert (pg["desde"], pg["hasta"], pg["tratados"], pg["hay_mas"], pg["siguiente"], pg["en_el_grupo"]) == (101, 130, 30, False, None, 130)
        assert [a["nombre"] for a in p2["archivos"]][0] == "Flash 101 (1987).cbz" and len(p2["archivos"]) == 30
        v = verificar_token_vinculacion(p2["token"], SECRETO)
        assert [(a.id, a.numero) for a in v.archivos] == [(str(ejecutables["Flash 105 (1987).cbz"]), "105")]

    async def test_el_token_y_la_seleccion_valen_solo_para_la_pagina(self, entorno):
        serie, bloqueados, ejecutables = await self._grupo_con_los_cien_primeros_bloqueados(entorno)
        p1 = (await previsualizar(serie)).json()
        # en la primera página, un archivo de la segunda: consta, no es marcable y no entra en un token
        c = (await previsualizar(serie, marcados=[ejecutables["Flash 105 (1987).cbz"]])).json()
        a = por_id_json(c)[str(ejecutables["Flash 105 (1987).cbz"])]
        assert (a["estado"], a["marcado"], a["marcable"], a["incluido_en_token"]) == ("fuera_de_la_pagina", True, False, False)
        assert c["token"] is None
        # y en la segunda, uno de la primera
        d = (await previsualizar(serie, cursor=p1["pagina"]["siguiente"], marcados=[bloqueados["Flash 001 (1987).cbz"]])).json()
        assert por_id_json(d)[str(bloqueados["Flash 001 (1987).cbz"])]["estado"] == "fuera_de_la_pagina" and d["token"] is None

    async def test_los_numeros_editados_valen_solo_para_los_archivos_de_la_pagina(self, entorno):
        serie, bloqueados, ejecutables = await self._grupo_con_los_cien_primeros_bloqueados(entorno)
        p1 = (await previsualizar(serie)).json()
        c = (await previsualizar(serie, cursor=p1["pagina"]["siguiente"], numeros={ejecutables["Flash 110 (1987).cbz"]: "7"},
                                 marcados=[ejecutables["Flash 110 (1987).cbz"]])).json()
        assert verificar_token_vinculacion(c["token"], SECRETO).archivos[0].numero == "7"

    async def test_tres_paginas_se_recorren_sin_huecos_ni_solapes_y_en_orden(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 251)))
        vistos, cursor, paginas = [], None, 0
        while True:
            c = (await previsualizar(serie, cursor=cursor)).json()
            vistos += [a["nombre"] for a in c["archivos"]]
            paginas += 1
            cursor = c["pagina"]["siguiente"]
            if not cursor:
                break
        assert paginas == 3 and vistos == sorted(vistos) and len(vistos) == len(set(vistos)) == 250

    async def test_el_cursor_sigue_valiendo_si_otros_archivos_se_vinculan_entre_peticiones(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 131)))
        p1 = (await previsualizar(serie)).json()
        async with entorno.banco.fabrica() as s:                       # se vinculan 10 de la primera página
            issue = Issue(series_id=serie, issue_number="999")
            s.add(issue)
            await s.flush()
            await s.execute(text("UPDATE files SET issue_id = :i WHERE file_name = ANY(:n)"),
                            {"i": issue.id, "n": [f"Flash {i:03d} (1987).cbz" for i in range(1, 11)]})
            await s.commit()
        p2 = (await previsualizar(serie, cursor=p1["pagina"]["siguiente"])).json()
        assert [a["nombre"] for a in p2["archivos"]] == [f"Flash {i:03d} (1987).cbz" for i in range(101, 131)]
        assert p2["pagina"]["en_el_grupo"] == 120 and p2["pagina"]["desde"] == 91 and p2["pagina"]["hasta"] == 120
        assert ids

    async def test_un_cursor_al_final_da_una_pagina_vacia_sin_error(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 4)))
        ultimo = (await previsualizar(serie)).json()["archivos"][-1]
        import base64
        import json
        cursor = base64.urlsafe_b64encode(json.dumps([ultimo["nombre"], ultimo["id"]]).encode()).decode()
        c = (await previsualizar(serie, cursor=cursor)).json()
        assert c["archivos"] == [] and c["pagina"]["tratados"] == 0 and c["pagina"]["desde"] == 0 and c["token"] is None

    @pytest.mark.parametrize("cursor", ["", "x", "no-es-base64!!", "W10=", "WyJhIl0=", "WzEsMl0=", "WyJhIiwgIm5vLXV1aWQiXQ=="])
    async def test_un_cursor_mal_formado_es_422(self, entorno, cursor):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        r = await previsualizar(serie, cursor=cursor)
        if cursor == "":
            assert r.status_code == 200                                # vacío = sin cursor
        else:
            assert r.status_code == 422 and r.json()["detail"]["codigo"] == "cursor_no_valido"

    async def test_un_ajeno_al_grupo_sigue_siendo_422_con_cursor(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 131)))
        otro = (await archivos(entorno, "Batman 01.cbz", carpeta="Comics/Batman (1940)"))["Batman 01.cbz"]
        p1 = (await previsualizar(serie)).json()
        r = await previsualizar(serie, cursor=p1["pagina"]["siguiente"], marcados=[otro])
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "archivo_ajeno_al_grupo"

    async def test_las_consultas_siguen_siendo_constantes_con_cursor(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 201)))
        p1 = (await previsualizar(serie)).json()
        n = len(entorno.banco.sentencias)
        assert (await previsualizar(serie, cursor=p1["pagina"]["siguiente"])).status_code == 200
        assert len(entorno.banco.sentencias) - n <= 8


# ── Rutas, validación, autenticación y logs ─────────────────────────────────────────────────────

class TestContratoYSeguridad:

    async def test_la_ruta_actual_es_relativa_a_la_biblioteca(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        a = (await previsualizar(serie)).json()["archivos"][0]
        assert a["ruta_actual"] == "Comics/Flash (1987)/Flash 01 (1987).cbz" and a["fuera_de_la_biblioteca"] is False
        assert str(entorno.lib) not in str((await previsualizar(serie)).json())

    @pytest.mark.parametrize("cuerpo", [
        {}, {"clave": "x"}, {"clave": CLAVE}, {"clave": CLAVE, "series_id": "no-es-uuid"},
        {"clave": "", "series_id": str(uuid4())}, {"clave": CLAVE, "series_id": str(uuid4()), "extra": 1},
        {"clave": CLAVE, "series_id": str(uuid4()), "marcados": ["no-uuid"]},
        {"clave": CLAVE, "series_id": str(uuid4()), "numeros": {"no-uuid": "1"}},
        {"clave": CLAVE, "series_id": str(uuid4()), "numeros": {str(uuid4()): 5}},
        {"clave": CLAVE, "series_id": str(uuid4()), "marcados": [str(uuid4())] * 1001},
    ])
    async def test_peticiones_mal_formadas_son_422(self, entorno, cuerpo):
        async with cliente() as c:
            assert (await c.post(RUTA, json=cuerpo)).status_code == 422

    async def test_un_numero_demasiado_largo_o_con_saltos_es_422(self, entorno):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz")
        for malo in ("1" * 21, "1\n2", "1\x002"):
            r = await previsualizar(serie, numeros={ids["Flash 01 (1987).cbz"]: malo})
            assert r.status_code == 422 and r.json()["detail"]["codigo"] == "numero_no_valido", repr(malo)

    async def test_grupo_o_serie_inexistentes_son_404(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        r = await previsualizar(serie, clave="Comics/No existe")
        assert r.status_code == 404 and r.json()["detail"]["codigo"] == "grupo_no_encontrado"
        r = await previsualizar(uuid4())
        assert r.status_code == 404 and r.json()["detail"]["codigo"] == "serie_no_encontrada"

    async def test_sin_clave_del_servidor_es_503(self, entorno, monkeypatch):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=""))
        assert (await previsualizar(serie)).status_code == 503

    async def test_sin_sesion_es_401_y_no_se_filtra_nada(self, entorno, monkeypatch):
        from zascarr.config import get_settings
        from zascarr.services.auth import hash_password
        ajustes = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        r = await previsualizar(serie)
        assert r.status_code == 401 and "Flash 01" not in r.text

    async def test_las_cabeceras_son_no_store_tambien_en_los_errores_de_validacion_del_servicio(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        assert (await previsualizar(serie)).headers["cache-control"] == "no-store"

    async def test_los_logs_no_llevan_rutas_ni_nombres(self, entorno, caplog):
        serie = await serie_de_prueba(entorno)
        ids = await archivos(entorno, "Flash 01 (1987).cbz", "Flash (1987).cbz", "Flash 09 (1987).cbz", en_disco=True)
        shutil.rmtree(entorno.lib / "Comics/Flash (1987)/Flash 09 (1987).cbz", ignore_errors=True)
        (entorno.lib / "Comics/Flash (1987)/Flash 09 (1987).cbz").unlink(missing_ok=True)
        caplog.set_level(logging.DEBUG)
        with structlog.testing.capture_logs() as registros:
            r = await previsualizar(serie, marcados=list(ids.values()))
        assert r.status_code == 200
        volcado = " ".join([rec.getMessage() + str(getattr(rec, "args", "")) for rec in caplog.records]
                           + [str(x) for x in registros])
        for secreto in ("Flash 01", "Flash 09", str(entorno.lib), "Comics/Flash", "biblioteca"):
            assert secreto not in volcado, secreto
