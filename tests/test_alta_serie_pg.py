# ruff: noqa: E501
"""Alta o reutilización de la serie (rebanada 2b) — pruebas de aceptación sobre Postgres real.

Contrato: `docs/design/rebanada-2-elegir-serie-y-vincular.md`, bloque B («Implementación 2b»). Lo que se prueba:
tokens (alterados, caducados, de otro propósito o contexto), alta manual sin red, vista previa sin escrituras,
reutilización por identificador exacto sin tocar la existente, posibles duplicados que se deciden (no en
silencio), colisiones nuevas entre vista previa y confirmación, altas simultáneas, procedencia e identidad
frente al enriquecedor, deshacer permitido y rechazado y que `files`, `issues`, rutas y nombres no cambian.
Ningún fichero existe en disco; ninguna fuente real se consulta. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import BIB, Banco, archivo
from zascarr.api import revision as api_revision
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Issue, Series
from zascarr.services import alta_serie, revision_carpetas
from zascarr.services.discovery import DiscoveryService
from zascarr.services.enricher import EnrichmentReport, EnrichmentService, SeriesMatch
from zascarr.services.tokens_revision import (
    AltaFirmada,
    CandidataFirmada,
    crear_token_alta,
    crear_token_candidata,
    verificar_token_alta,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

SECRETO = "clave-de-prueba-para-firmar"
PREV, ALTA = "/api/revision/serie/previsualizar", "/api/revision/serie"
CARPETA = "Comics/Flash (1987)"
CV_OK = "https://comicvine.gamespot.com/a/uploads/scale_large/1/11/cover.jpg"
SHA = "a" * 64


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    monkeypatch.setattr(revision_carpetas, "get_settings", lambda: SimpleNamespace(library_path=Path(BIB)))
    monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))

    async def sin_red(*a, **kw):
        raise AssertionError("el alta no puede buscar en las fuentes")
    monkeypatch.setattr(DiscoveryService, "search_detallada", sin_red)
    monkeypatch.setattr(DiscoveryService, "search", sin_red)

    reales: list[str] = []
    original = httpx.AsyncClient.send

    async def vigilado(self, request, **kw):
        if not isinstance(self._transport, httpx.ASGITransport):
            reales.append(request.url.host)
        return await original(self, request, **kw)
    monkeypatch.setattr(httpx.AsyncClient, "send", vigilado)

    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    await b.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 4)))
    contexto = SimpleNamespace(banco=b, red=reales)
    yield contexto
    app.dependency_overrides.pop(get_db, None)
    await contexto.banco.cerrar()          # el banco puede haberse sustituido (`reiniciar`)


def cliente(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                             headers={"Origin": "http://localhost"}, **kw)


async def post(ruta: str, cuerpo: dict, **kw) -> httpx.Response:
    async with cliente() as c:
        return await c.post(ruta, json=cuerpo, **kw)


def manual(titulo="Flash", anio=1987, tradicion="american", **kw) -> dict:
    return {"clave": CARPETA, "manual": {"titulo": titulo, "anio": anio}, "tradicion": tradicion, **kw}


def candidata_token(fuente="comic_vine", id_="796", titulo="Flash", anio=1987, tradicion="american",
                    clave=CARPETA, descripcion="Velocista.", cover=CV_OK, **kw) -> str:
    return crear_token_candidata(clave, CandidataFirmada(fuente, id_, titulo, anio, tradicion, descripcion, cover),
                                 SECRETO, **kw)


def desde_fuente(**kw) -> dict:
    tradicion = kw.pop("tradicion_elegida", "american")
    return {"clave": kw.pop("clave", CARPETA), "candidata": candidata_token(**kw), "tradicion": tradicion}


async def previsualizar_y_confirmar(cuerpo: dict) -> httpx.Response:
    v = await post(PREV, cuerpo)
    assert v.status_code == 200 and v.json()["token"], v.text
    return await post(ALTA, {"token": v.json()["token"]})


async def serie_en_bd(b: Banco, titulo: str | None = None) -> list[Series]:
    async with b.fabrica() as s:
        consulta = select(Series).order_by(Series.created_at, Series.title)
        if titulo:
            consulta = consulta.where(Series.title == titulo)
        return list((await s.execute(consulta)).scalars().all())


async def numero_de_series(b: Banco) -> int:
    async with b.fabrica() as s:
        return (await s.execute(text("SELECT count(*) FROM series"))).scalar_one()


async def instantanea(b: Banco) -> dict:
    """Todo lo que NO debe cambiar al dar de alta una serie: `files` e `issues` enteros (rutas y nombres incluidos)."""
    async with b.fabrica() as s:
        return {t: [tuple(r) for r in (await s.execute(text(f"SELECT * FROM {t} ORDER BY id"))).all()]
                for t in ("files", "issues", "wishlist", "asignacion_operaciones")}


async def operaciones(b: Banco) -> list[tuple]:
    """(operacion_id, series_id, estado, token_hasta, creada) de todos los comprobantes."""
    async with b.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text(
            "SELECT operacion_id::text, series_id::text, estado::text, token_hasta, creada FROM alta_operaciones "
            "ORDER BY creada, operacion_id"))).all()]


async def rutas(b: Banco) -> list[tuple[str, str]]:
    async with b.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text("SELECT file_path, file_name FROM files ORDER BY id"))).all()]


async def fila_de_serie(b: Banco, sid) -> tuple:
    async with b.fabrica() as s:
        return tuple((await s.execute(text("SELECT * FROM series WHERE id = :i"), {"i": sid})).one())


async def sembrar_serie(b: Banco, titulo="Flash", anio: int | None = 1987, tradicion=ComicTradition.AMERICAN,
                        **campos) -> UUID:
    sid = uuid4()
    async with b.fabrica() as s:
        s.add(Series(id=sid, title=titulo, start_year=anio, tradition=tradicion, **campos))
        await s.commit()
    return sid


def escrituras(b: Banco, desde: int) -> list[str]:
    return [q for q in b.sentencias[desde:] if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q, re.I)]


# ── Tokens ──────────────────────────────────────────────────────────────────────────────────────

class TestTokens:

    async def test_un_token_de_alta_alterado_se_rechaza_y_no_crea_nada(self, entorno):
        v = (await post(PREV, manual())).json()
        token = v["token"]
        raro = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
        for malo in (raro, token + "x", token[::-1], "inventado", "."):
            r = await post(ALTA, {"token": malo})
            assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido", malo
        assert await numero_de_series(entorno.banco) == 0

    async def test_un_token_de_alta_caducado_se_rechaza(self, entorno):
        v = (await post(PREV, manual())).json()
        assert (await post(ALTA, {"token": v["token"]})).status_code == 200      # con reloj real, vale
        viejo = crear_token_alta(AltaFirmada(
            clave=CARPETA, modo="crear", origen="manual", fuente=None, id_externo=None, titulo="Otra", anio=None,
            tradicion="american", descripcion=None, cover_url=None, serie_id=None, vistas=(),
            operacion=str(uuid4())), SECRETO, ahora=time.time() - 16 * 60)
        r = await post(ALTA, {"token": viejo})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert [s.title for s in await serie_en_bd(entorno.banco)] == ["Flash"]

    async def test_un_token_de_otro_proposito_no_sirve(self, entorno):
        """El token de una candidata (2a) no es un token de alta, y al revés."""
        r = await post(ALTA, {"token": candidata_token()})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        token_alta = (await post(PREV, manual())).json()["token"]
        r = await post(PREV, {"clave": CARPETA, "candidata": token_alta, "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await numero_de_series(entorno.banco) == 0

    async def test_una_candidata_de_otro_grupo_no_sirve_en_este(self, entorno):
        """El contexto del token de candidata es la `clave` del grupo."""
        await entorno.banco.sembrar(archivo("Comics/Otra/Otra 01.cbz"))
        r = await post(PREV, {"clave": "Comics/Otra", "candidata": candidata_token(clave=CARPETA),
                              "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"

    async def test_la_confirmacion_recibe_solo_el_token(self, entorno):
        """Nada de título, año ni tradición sueltos: un cuerpo con campos de más se rechaza y no cambia nada."""
        token = (await post(PREV, manual())).json()["token"]
        for extra in ({"titulo": "Colado"}, {"tradicion": "manga"}, {"anio": 1999}, {"id_externo": "1"},
                      {"cover_url": "http://127.0.0.1/x"}, {"description": "x"}):
            r = await post(ALTA, {"token": token, **extra})
            assert r.status_code == 422, extra
        assert (await post(ALTA, {})).status_code == 422
        assert await numero_de_series(entorno.banco) == 0

    async def test_sin_clave_del_servidor_es_503_y_no_se_escribe_nada(self, entorno, monkeypatch):
        token = (await post(PREV, manual())).json()["token"]
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=""))
        for ruta, cuerpo in ((PREV, manual()), (ALTA, {"token": token}),
                             (f"{ALTA}/{uuid4()}/deshacer", {"operacion_id": str(uuid4())})):
            assert (await post(ruta, cuerpo)).status_code == 503, ruta
        assert await numero_de_series(entorno.banco) == 0

    async def test_una_portada_no_permitida_dentro_de_un_token_valido_no_se_guarda(self, entorno):
        """La firma garantiza la integridad, no que la URL sea segura (H1): se revalida al dar de alta."""
        for cover in ("http://127.0.0.1:8080/x.jpg", "https://evil.example/x.jpg", "http://169.254.169.254/"):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            token = crear_token_alta(AltaFirmada(
                clave=CARPETA, modo="crear", origen="descubrir", fuente="comic_vine", id_externo="796", titulo="Flash",
                anio=1987, tradicion="american", descripcion=None, cover_url=cover, serie_id=None, vistas=(),
                operacion=str(uuid4())), SECRETO)
            assert (await post(ALTA, {"token": token})).status_code == 200
            assert (await serie_en_bd(entorno.banco))[0].cover_url is None, cover

    async def test_el_token_no_se_guarda_en_la_serie(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        await post(ALTA, {"token": token})
        guardado = json.dumps([s.metadata_ for s in await serie_en_bd(entorno.banco)])
        assert token not in guardado and token[:20] not in guardado
        assert not re.search(r"token|sesion|session|cookie", guardado, re.I)


# ── Alta manual: un camino completo, sin red ───────────────────────────────────────────────────────

class TestAltaManual:

    async def test_la_vista_previa_no_escribe_ni_usa_la_red(self, entorno):
        antes, sentencias = await instantanea(entorno.banco), len(entorno.banco.sentencias)
        r = await post(PREV, manual())
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        v = r.json()
        assert (v["accion"], v["origen"], v["fuente"], v["titulo"], v["anio"], v["tradicion"]) == (
            "crear", "manual", None, "Flash", 1987, "american")
        assert v["efectos"] == {"series_nuevas": 1, "numeros": 0, "archivos": 0} and v["token"]
        assert v["parecidas"] == [] and v["existente"] is None
        assert escrituras(entorno.banco, sentencias) == []
        assert await numero_de_series(entorno.banco) == 0 and await instantanea(entorno.banco) == antes
        assert entorno.red == []

    async def test_confirmar_crea_una_serie_con_su_procedencia_y_el_bloqueo_manual(self, entorno):
        r = await previsualizar_y_confirmar(manual("  Flash   Vol. 1 ", 1987, "american"))
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        cuerpo = r.json()
        assert (cuerpo["resultado"], cuerpo["repetida"], cuerpo["motivo"]) == ("creada", False, None)
        (s,) = await serie_en_bd(entorno.banco)
        assert str(s.id) == cuerpo["serie"]["series_id"] == cuerpo["deshacer"]["series_id"]
        assert (s.title, s.start_year, s.tradition) == ("Flash Vol. 1", 1987, ComicTradition.AMERICAN)
        # D10: manual → `metadata_source = 'manual'` (nadie la enriquece); ningún identificador externo
        assert s.metadata_source == "manual" and s.locked_fields == []
        assert (s.comic_vine_id, s.anilist_id, s.tebeosfera_slug, s.gcd_id) == (None,) * 4
        alta = s.metadata_["alta"]
        assert set(alta) == {"version", "origen", "fuente", "id_externo", "desde_grupo", "fecha", "tradicion_elegida",
                             "operacion_id"}
        assert (alta["version"], alta["origen"], alta["fuente"], alta["id_externo"], alta["desde_grupo"],
                alta["tradicion_elegida"]) == (1, "manual", None, None, CARPETA, True)
        assert alta["operacion_id"] == cuerpo["deshacer"]["operacion_id"] and alta["fecha"].endswith("+00:00")

    async def test_no_hay_red_ni_busquedas_ni_enriquecimiento_como_efecto(self, entorno):
        await previsualizar_y_confirmar(manual())
        assert entorno.red == []                  # (`search*` de las fuentes revientan si se llaman: ver `entorno`)
        (s,) = await serie_en_bd(entorno.banco)
        assert s.enrichment_attempted_at is None and s.wishlist_policy.value == "ninguno"

    async def test_solo_se_escribe_la_serie_y_su_comprobante_y_nada_en_files_ni_issues(self, entorno):
        antes = await instantanea(entorno.banco)
        v = (await post(PREV, manual())).json()
        n = len(entorno.banco.sentencias)
        assert (await post(ALTA, {"token": v["token"]})).status_code == 200
        todas = escrituras(entorno.banco, n)
        ins = [q for q in todas if re.match(r"\s*INSERT", q, re.I)]
        assert sorted(re.match(r"\s*INSERT INTO (\w+)", q, re.I).group(1) for q in ins) == [
            "alta_operaciones", "series"], ins
        # lo único más que se escribe es la purga acotada del propio comprobante
        assert all(re.match(r"\s*DELETE FROM alta_operaciones", q, re.I) for q in todas if q not in ins), todas
        despues = await instantanea(entorno.banco)
        assert despues == antes and despues["issues"] == []
        assert (r := await rutas(entorno.banco)) and all(Path(p).name == n for p, n in r)   # rutas y nombres

    async def test_la_tradicion_se_elige_y_no_tiene_valor_por_defecto(self, entorno):
        sin = {k: v for k, v in manual().items() if k != "tradicion"}
        assert (await post(PREV, sin)).status_code == 422
        assert (await post(PREV, manual(tradicion="inventada"))).status_code == 422
        assert (await post(PREV, manual(tradicion=None))).status_code == 422
        for t in ("manga", "tebeo", "franco_belgian"):
            v = (await post(PREV, manual(tradicion=t))).json()
            assert v["tradicion"] == t and v["tradicion_sugerida"] is None
        assert await numero_de_series(entorno.banco) == 0

    @pytest.mark.parametrize("cuerpo", [
        {"manual": {"titulo": "   "}}, {"manual": {"titulo": "!!! ???"}}, {"manual": {"titulo": "x" * 501}},
        {"manual": {"titulo": "Flash", "anio": 1799}}, {"manual": {"titulo": "Flash", "anio": 2101}},
        {"manual": {"titulo": "Flash", "anio": "mil"}}, {"manual": {"titulo": "Flash", "extra": 1}},
        {"manual": {"titulo": "Flash"}, "candidata": "x"}, {},
    ])
    async def test_datos_manuales_invalidos_o_ambiguos_son_422(self, entorno, cuerpo):
        r = await post(PREV, {"clave": CARPETA, "tradicion": "american", **cuerpo})
        assert r.status_code == 422
        assert await numero_de_series(entorno.banco) == 0

    async def test_un_grupo_que_no_existe_es_404(self, entorno):
        r = await post(PREV, {**manual(), "clave": "Comics/No existe"})
        assert r.status_code == 404
        assert await numero_de_series(entorno.banco) == 0

    async def test_el_anio_es_opcional(self, entorno):
        r = await previsualizar_y_confirmar(manual("Mortadelo", None, "tebeo"))
        assert r.status_code == 200
        assert (await serie_en_bd(entorno.banco, "Mortadelo"))[0].start_year is None


# ── Alta desde una fuente ────────────────────────────────────────────────────────────────────────

FUENTES = [("comic_vine", "796", "comic_vine_id", 796), ("anilist", "30002", "anilist_id", 30002),
           ("tebeosfera", "thorgal_1981_distrinovel", "tebeosfera_slug", "thorgal_1981_distrinovel"),
           ("gcd", "4120", "gcd_id", 4120)]


class TestAltaDesdeFuente:

    @pytest.mark.parametrize(("fuente", "id_", "campo", "valor"), FUENTES)
    async def test_crea_con_la_identidad_bloqueada_y_la_fuente_como_origen(self, entorno, fuente, id_, campo, valor):
        r = await previsualizar_y_confirmar(desde_fuente(fuente=fuente, id_=id_, titulo="Thorgal", anio=1981,
                                                         tradicion="franco_belgian"))
        assert r.status_code == 200 and r.json()["resultado"] == "creada"
        (s,) = await serie_en_bd(entorno.banco)
        assert getattr(s, campo) == valor and s.metadata_source == fuente
        assert s.locked_fields == [campo]                      # el enriquecedor no puede cambiar la identidad
        assert s.description == "Velocista." and s.cover_url == CV_OK
        alta = s.metadata_["alta"]
        assert (alta["origen"], alta["fuente"], alta["id_externo"], alta["version"]) == ("descubrir", fuente, id_, 1)
        otros = {"comic_vine_id", "anilist_id", "tebeosfera_slug", "gcd_id"} - {campo}
        assert all(getattr(s, o) is None for o in otros)

    async def test_la_tradicion_elegida_manda_sobre_la_sugerida(self, entorno):
        v = (await post(PREV, desde_fuente(tradicion="american", tradicion_elegida="manga"))).json()
        assert (v["tradicion"], v["tradicion_sugerida"]) == ("manga", "american")
        await post(ALTA, {"token": v["token"]})
        assert (await serie_en_bd(entorno.banco))[0].tradition == ComicTradition.MANGA

    async def test_la_vista_previa_con_una_candidata_no_escribe_ni_usa_la_red(self, entorno):
        n = len(entorno.banco.sentencias)
        assert (await post(PREV, desde_fuente())).status_code == 200
        assert escrituras(entorno.banco, n) == [] and entorno.red == []

    async def test_se_usa_solo_lo_que_dice_la_candidata_firmada(self, entorno):
        """Los datos del alta son los de la candidata que firmó el servidor: ni título, ni año, ni descripción ni
        portada pueden venir de fuera (la petición no los admite)."""
        for extra in ({"titulo": "Colado"}, {"anio": 1999}, {"cover_url": "http://127.0.0.1/x"},
                      {"description": "x"}, {"id_externo": "999"}):
            assert (await post(PREV, {**desde_fuente(), **extra})).status_code == 422, extra


# ── Reutilización por identificador exacto ───────────────────────────────────────────────────────

class TestReutilizacion:

    async def test_el_mismo_identificador_reutiliza_sin_modificar_la_existente(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash (CV)", 1999, comic_vine_id=796, description="Mía",
                                  metadata_source="manual", locked_fields=["description"])
        antes, fila = await instantanea(entorno.banco), await fila_de_serie(entorno.banco, sid)
        v = (await post(PREV, desde_fuente(titulo="Otro título", descripcion="Otra"))).json()
        assert (v["accion"], v["existente"]["series_id"]) == ("reutilizar", str(sid))
        assert v["efectos"]["series_nuevas"] == 0 and v["parecidas"] == []
        n = len(entorno.banco.sentencias)
        r = await post(ALTA, {"token": v["token"]})
        assert r.status_code == 200
        c = r.json()
        assert (c["resultado"], c["motivo"], c["serie"]["series_id"], c["deshacer"]) == (
            "reutilizada", "mismo_identificador", str(sid), None)
        assert escrituras(entorno.banco, n) == []
        assert await fila_de_serie(entorno.banco, sid) == fila and await instantanea(entorno.banco) == antes
        assert await numero_de_series(entorno.banco) == 1

    @pytest.mark.parametrize(("fuente", "id_", "campo", "valor"), FUENTES)
    async def test_cada_fuente_se_reconoce_por_su_campo(self, entorno, fuente, id_, campo, valor):
        sid = await sembrar_serie(entorno.banco, "Otra cosa", 1950, **{campo: valor})
        v = (await post(PREV, desde_fuente(fuente=fuente, id_=id_))).json()
        assert (v["accion"], v["existente"]["series_id"]) == ("reutilizar", str(sid))

    async def test_con_el_identificador_no_se_ofrece_crear_otra(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1987, comic_vine_id=796)
        v = (await post(PREV, {**desde_fuente(), "decision": "crear_igualmente"})).json()
        assert (v["accion"], v["existente"]["series_id"]) == ("reutilizar", str(sid))
        r = await post(ALTA, {"token": v["token"]})
        assert r.json()["resultado"] == "reutilizada" and await numero_de_series(entorno.banco) == 1

    async def test_si_la_serie_vista_desaparece_antes_de_confirmar_es_409_y_no_se_crea_otra(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1987, comic_vine_id=796)
        token = (await post(PREV, desde_fuente())).json()["token"]
        async with entorno.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series WHERE id = :i"), {"i": sid})
            await s.commit()
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "la_serie_ya_no_existe"
        assert await numero_de_series(entorno.banco) == 0


class TestIdentidadDeLaReutilizacion:
    """La reutilización por identificador se REVALIDA al confirmar; una elegida por la persona no se convierte
    después en «coincidencia por identificador»."""

    async def _vista_por_identificador(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1987, comic_vine_id=796)
        v = (await post(PREV, desde_fuente())).json()
        assert (v["accion"], v["existente"]["series_id"]) == ("reutilizar", str(sid))
        return sid, v["token"]

    @pytest.mark.parametrize("cambio", ["comic_vine_id = 797", "comic_vine_id = NULL", "comic_vine_id = NULL, anilist_id = 5"])
    async def test_si_la_serie_pierde_el_identificador_visto_es_409_sin_escrituras(self, entorno, cambio):
        sid, token = await self._vista_por_identificador(entorno)
        async with entorno.banco.fabrica() as s:
            await s.execute(text(f"UPDATE series SET {cambio} WHERE id = :i"), {"i": sid})
            await s.commit()
        fila, antes, n = await fila_de_serie(entorno.banco, sid), await instantanea(entorno.banco), len(entorno.banco.sentencias)
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "identificador_cambiado"
        assert "elegida" not in r.text and "resultado" not in r.json()
        assert escrituras(entorno.banco, n) == []
        assert await fila_de_serie(entorno.banco, sid) == fila and await instantanea(entorno.banco) == antes
        assert await numero_de_series(entorno.banco) == 1

    async def test_si_el_identificador_pasa_a_otra_serie_no_se_reutiliza_la_antigua_ni_se_redirige(self, entorno):
        sid, token = await self._vista_por_identificador(entorno)
        otra = await sembrar_serie(entorno.banco, "Otra", 2000)
        async with entorno.banco.fabrica() as s:
            await s.execute(text("UPDATE series SET comic_vine_id = NULL WHERE id = :i"), {"i": sid})
            await s.execute(text("UPDATE series SET comic_vine_id = 796 WHERE id = :i"), {"i": otra})
            await s.commit()
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "identificador_cambiado"
        assert str(otra) not in r.text

    async def test_si_el_identificador_sigue_igual_se_reutiliza_por_identificador(self, entorno):
        sid, token = await self._vista_por_identificador(entorno)
        c = (await post(ALTA, {"token": token})).json()
        assert (c["resultado"], c["motivo"], c["serie"]["series_id"]) == ("reutilizada", "mismo_identificador", str(sid))

    async def test_tras_rehacer_la_vista_previa_con_el_identificador_nuevo_se_decide_de_nuevo(self, entorno):
        sid, token = await self._vista_por_identificador(entorno)
        async with entorno.banco.fabrica() as s:
            await s.execute(text("UPDATE series SET comic_vine_id = NULL WHERE id = :i"), {"i": sid})
            await s.commit()
        assert (await post(ALTA, {"token": token})).status_code == 409
        v = (await post(PREV, desde_fuente())).json()          # ahora es una parecida sin identificador: hay que elegir
        assert (v["accion"], v["token"]) == ("elegir", None)

    async def test_una_parecida_elegida_nunca_se_atribuye_a_una_coincidencia_por_identificador(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1988)
        v = (await post(PREV, {**desde_fuente(), "decision": "reutilizar", "serie_id": str(sid)})).json()
        assert (v["accion"], v["decision"]) == ("reutilizar", "reutilizar")
        async with entorno.banco.fabrica() as s:               # después adquiere justo el identificador de la candidata
            await s.execute(text("UPDATE series SET comic_vine_id = 796 WHERE id = :i"), {"i": sid})
            await s.commit()
        c = (await post(ALTA, {"token": v["token"]})).json()
        assert (c["resultado"], c["motivo"]) == ("reutilizada", "elegida_por_la_persona")

    async def test_una_parecida_elegida_con_otro_identificador_sigue_siendo_eleccion(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1988, comic_vine_id=111)
        v = (await post(PREV, {**desde_fuente(), "decision": "reutilizar", "serie_id": str(sid)})).json()
        c = (await post(ALTA, {"token": v["token"]})).json()
        assert (c["motivo"], c["serie"]["series_id"]) == ("elegida_por_la_persona", str(sid))


# ── Posibles duplicados: la persona decide ─────────────────────────────────────────────────────────

class TestParecidas:

    async def test_una_parecida_obliga_a_decidir_y_no_emite_token(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1988)
        r = await post(PREV, manual(anio=1987))
        v = r.json()
        assert r.status_code == 200 and (v["accion"], v["token"], v["decision"]) == ("elegir", None, None)
        assert [p["series_id"] for p in v["parecidas"]] == [str(sid)] and v["parecidas"][0]["motivo"]
        assert v["efectos"]["series_nuevas"] == 0
        assert await numero_de_series(entorno.banco) == 1

    @pytest.mark.parametrize(("titulo_nuevo", "anio_nuevo", "titulo_viejo", "anio_viejo", "tradicion_vieja", "parecida"), [
        ("Flash", 1987, "Flash", 1987, ComicTradition.AMERICAN, True),
        ("Flash", 1987, "Flash", 1988, ComicTradition.AMERICAN, True),         # ±1
        ("Flash", 1988, "Flash", 1987, ComicTradition.AMERICAN, True),
        ("Flash", 1987, "Flash", 1989, ComicTradition.AMERICAN, False),        # año lejano
        ("Flash", 1987, "Flash", None, ComicTradition.AMERICAN, True),          # año desconocido: se avisa de más
        ("Flash", None, "Flash", 1987, ComicTradition.AMERICAN, True),
        ("Flash", 1987, "Flash", 1987, ComicTradition.MANGA, False),            # otra tradición
        ("The Flash", 1987, "Flash", 1987, ComicTradition.AMERICAN, True),      # el artículo no cuenta
        ("FLÁSH!", 1987, "Flash", 1987, ComicTradition.AMERICAN, True),         # mayúsculas, tildes y signos
        ("Flash", 1987, "Flash Gordon", 1987, ComicTradition.AMERICAN, False),
    ])
    async def test_la_regla_de_parecida(self, entorno, titulo_nuevo, anio_nuevo, titulo_viejo, anio_viejo,
                                        tradicion_vieja, parecida):
        await sembrar_serie(entorno.banco, titulo_viejo, anio_viejo, tradicion_vieja)
        v = (await post(PREV, manual(titulo_nuevo, anio_nuevo))).json()
        assert (v["accion"] == "elegir") is parecida and bool(v["parecidas"]) is parecida
        assert (v["token"] is None) is parecida

    async def test_decidir_crear_igualmente_da_token_y_crea_otra_sin_tocar_la_parecida(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1988)
        fila = await fila_de_serie(entorno.banco, sid)
        v = (await post(PREV, manual(decision="crear_igualmente"))).json()
        assert (v["accion"], v["decision"]) == ("crear", "crear_igualmente") and v["token"] and v["parecidas"]
        r = await post(ALTA, {"token": v["token"]})
        assert r.status_code == 200 and r.json()["resultado"] == "creada"
        assert await numero_de_series(entorno.banco) == 2 and await fila_de_serie(entorno.banco, sid) == fila

    async def test_decidir_usar_la_existente_no_crea_ni_modifica_nada(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1988)
        antes, fila = await instantanea(entorno.banco), await fila_de_serie(entorno.banco, sid)
        v = (await post(PREV, manual(decision="reutilizar", serie_id=str(sid)))).json()
        assert (v["accion"], v["existente"]["series_id"], v["decision"]) == ("reutilizar", str(sid), "reutilizar")
        n = len(entorno.banco.sentencias)
        c = (await post(ALTA, {"token": v["token"]})).json()
        assert (c["resultado"], c["motivo"], c["serie"]["series_id"]) == ("reutilizada", "elegida_por_la_persona", str(sid))
        assert escrituras(entorno.banco, n) == [] and await numero_de_series(entorno.banco) == 1
        assert await fila_de_serie(entorno.banco, sid) == fila and await instantanea(entorno.banco) == antes

    async def test_reutilizar_una_que_no_esta_entre_las_parecidas_es_422(self, entorno):
        parecida = await sembrar_serie(entorno.banco, "Flash", 1988)
        otra = await sembrar_serie(entorno.banco, "Batman", 1940)
        for cuerpo in (manual(decision="reutilizar", serie_id=str(otra)), manual(decision="reutilizar"),
                       manual(decision="reutilizar", serie_id=str(uuid4()))):
            r = await post(PREV, cuerpo)
            assert r.status_code == 422 and r.json()["detail"]["codigo"] == "decision_invalida", cuerpo
        assert (await post(PREV, manual(decision="inventada"))).status_code == 422
        # sin parecidas no hay nada que reutilizar por decisión
        await entorno.banco.limpiar()
        await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
        assert (await post(PREV, manual(decision="reutilizar", serie_id=str(parecida)))).status_code == 422

    async def test_decidir_crear_sin_parecidas_es_un_alta_normal(self, entorno):
        v = (await post(PREV, manual(decision="crear_igualmente"))).json()
        assert (v["accion"], v["decision"], bool(v["token"])) == ("crear", None, True)

    async def test_una_candidata_de_fuente_sin_el_identificador_tambien_exige_decidir(self, entorno):
        await sembrar_serie(entorno.banco, "Flash", 1987)               # sin ningún id externo
        v = (await post(PREV, desde_fuente())).json()
        assert (v["accion"], v["token"]) == ("elegir", None)

    async def test_el_orden_de_las_parecidas_es_fijo_y_no_hay_preseleccion(self, entorno):
        a = await sembrar_serie(entorno.banco, "Flash", 1988)
        b = await sembrar_serie(entorno.banco, "Flash", 1986)
        c = await sembrar_serie(entorno.banco, "Flash", 1987)
        v = (await post(PREV, manual())).json()
        assert [p["series_id"] for p in v["parecidas"]] == [str(b), str(c), str(a)]
        prohibidas = {"recomendada", "elegida", "seleccionada", "mejor", "score", "por_defecto"}
        assert prohibidas.isdisjoint(v) and all(prohibidas.isdisjoint(p) for p in v["parecidas"])


# ── Colisiones nuevas entre la vista previa y la confirmación ──────────────────────────────────────

class TestColisionesNuevas:

    async def test_aparece_una_parecida_despues_de_la_vista_previa_es_409(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        nueva = await sembrar_serie(entorno.banco, "Flash", 1988)
        r = await post(ALTA, {"token": token})
        d = r.json()["detail"]
        assert r.status_code == 409 and d["codigo"] == "aparecieron_parecidas"
        assert [p["series_id"] for p in d["nuevas"]] == [str(nueva)] and d["mensaje"]
        assert await numero_de_series(entorno.banco) == 1

    async def test_rehacer_la_vista_previa_la_enseña_y_permite_decidir(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        await sembrar_serie(entorno.banco, "Flash", 1987)
        assert (await post(ALTA, {"token": token})).status_code == 409
        v = (await post(PREV, manual(decision="crear_igualmente"))).json()
        assert (await post(ALTA, {"token": v["token"]})).json()["resultado"] == "creada"
        assert await numero_de_series(entorno.banco) == 2

    async def test_con_un_duplicado_aceptado_otra_parecida_nueva_tambien_se_rechaza(self, entorno):
        await sembrar_serie(entorno.banco, "Flash", 1988)
        token = (await post(PREV, manual(decision="crear_igualmente"))).json()["token"]
        otra = await sembrar_serie(entorno.banco, "Flash", 1986)
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and [p["series_id"] for p in r.json()["detail"]["nuevas"]] == [str(otra)]
        assert await numero_de_series(entorno.banco) == 2

    async def test_si_la_parecida_vista_desaparece_se_crea_igualmente(self, entorno):
        vista = await sembrar_serie(entorno.banco, "Flash", 1988)
        token = (await post(PREV, manual(decision="crear_igualmente"))).json()["token"]
        async with entorno.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series WHERE id = :i"), {"i": vista})
            await s.commit()
        assert (await post(ALTA, {"token": token})).json()["resultado"] == "creada"

    async def test_una_serie_de_otra_tradicion_o_de_otro_titulo_no_cuenta_como_nueva(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        await sembrar_serie(entorno.banco, "Flash", 1987, ComicTradition.MANGA)
        await sembrar_serie(entorno.banco, "Batman", 1987)
        assert (await post(ALTA, {"token": token})).json()["resultado"] == "creada"

    async def test_si_aparece_el_identificador_externo_se_reutiliza_en_vez_de_crear_o_fallar(self, entorno):
        token = (await post(PREV, desde_fuente())).json()["token"]
        existente = await sembrar_serie(entorno.banco, "Flash (la de otro)", 2005, comic_vine_id=796)
        r = await post(ALTA, {"token": token})
        c = r.json()
        assert r.status_code == 200 and (c["resultado"], c["motivo"], c["serie"]["series_id"]) == (
            "reutilizada", "mismo_identificador", str(existente))
        assert await numero_de_series(entorno.banco) == 1

    async def test_el_unique_del_identificador_se_trata_como_reutilizacion_no_como_500(self, entorno, monkeypatch):
        """H4: aunque la comprobación previa no vea la fila (carrera), el UNIQUE no llega como un 500."""
        token = (await post(PREV, desde_fuente())).json()["token"]
        existente = await sembrar_serie(entorno.banco, "Otra cosa distinta", 1950, comic_vine_id=796)
        real = alta_serie.AltaDeSerie._por_id_externo
        llamadas = []

        async def ciego_la_primera_vez(self, fuente, id_externo):
            llamadas.append(1)
            return None if len(llamadas) == 1 else await real(self, fuente, id_externo)
        monkeypatch.setattr(alta_serie.AltaDeSerie, "_por_id_externo", ciego_la_primera_vez)
        r = await post(ALTA, {"token": token})
        assert r.status_code == 200 and r.json()["resultado"] == "reutilizada"
        assert r.json()["serie"]["series_id"] == str(existente) and await numero_de_series(entorno.banco) == 1


# ── Altas simultáneas ───────────────────────────────────────────────────────────────────────────

class TestConcurrencia:

    async def test_dos_altas_manuales_de_flash_1987_y_1988_crean_una_y_la_otra_recibe_el_aviso(self, entorno):
        for ronda in range(6):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            t1 = (await post(PREV, manual(anio=1987))).json()["token"]
            t2 = (await post(PREV, manual(anio=1988))).json()["token"]
            r = await asyncio.gather(post(ALTA, {"token": t1}), post(ALTA, {"token": t2}))
            assert sorted(x.status_code for x in r) == [200, 409], (ronda, [x.text for x in r])
            perdedora = next(x for x in r if x.status_code == 409)
            assert perdedora.json()["detail"]["codigo"] == "aparecieron_parecidas"
            assert await numero_de_series(entorno.banco) == 1

    async def test_el_candado_es_del_titulo_normalizado_no_del_texto_exacto(self, entorno):
        """«Flash», «The Flash» y «FLÁSH!» son el mismo título normalizado: se serializan aunque el texto difiera."""
        for _ in range(4):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            tokens = [(await post(PREV, manual(t, 1987))).json()["token"] for t in ("Flash", "The Flash", "FLÁSH!")]
            r = await asyncio.gather(*(post(ALTA, {"token": t}) for t in tokens))
            assert sorted(x.status_code for x in r) == [200, 409, 409], [x.text for x in r]
            assert await numero_de_series(entorno.banco) == 1

    async def test_muchas_altas_a_la_vez_del_mismo_titulo_crean_una_sola(self, entorno):
        tokens = [(await post(PREV, manual(anio=1987 + i % 2))).json()["token"] for i in range(6)]
        r = await asyncio.gather(*(post(ALTA, {"token": t}) for t in tokens))
        assert sorted(x.status_code for x in r) == [200] + [409] * 5
        assert await numero_de_series(entorno.banco) == 1

    async def test_dos_altas_por_el_mismo_identificador_externo_crean_una_y_reutilizan_la_otra(self, entorno):
        for _ in range(4):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            t1 = (await post(PREV, desde_fuente())).json()["token"]
            t2 = (await post(PREV, desde_fuente())).json()["token"]
            r = await asyncio.gather(post(ALTA, {"token": t1}), post(ALTA, {"token": t2}))
            assert [x.status_code for x in r] == [200, 200], [x.text for x in r]
            assert sorted(x.json()["resultado"] for x in r) == ["creada", "reutilizada"]
            assert await numero_de_series(entorno.banco) == 1

    async def test_mismo_identificador_con_titulos_distintos_no_da_500(self, entorno):
        """Candados distintos (otro título normalizado): solo lo ordena el UNIQUE, que se trata como reutilización."""
        for _ in range(4):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            t1 = (await post(PREV, desde_fuente(titulo="Flash"))).json()["token"]
            t2 = (await post(PREV, desde_fuente(titulo="The Flash Revolution", anio=2001))).json()["token"]
            r = await asyncio.gather(post(ALTA, {"token": t1}), post(ALTA, {"token": t2}))
            assert [x.status_code for x in r] == [200, 200], [x.text for x in r]
            assert sorted(x.json()["resultado"] for x in r) == ["creada", "reutilizada"]
            assert await numero_de_series(entorno.banco) == 1

    async def test_una_candidata_de_fuente_frente_a_una_manual_del_mismo_titulo_crean_una(self, entorno):
        t1 = (await post(PREV, manual())).json()["token"]
        t2 = (await post(PREV, desde_fuente())).json()["token"]
        r = await asyncio.gather(post(ALTA, {"token": t1}), post(ALTA, {"token": t2}))
        assert sorted(x.status_code for x in r) == [200, 409]
        assert await numero_de_series(entorno.banco) == 1

    async def test_el_mismo_titulo_en_otra_tradicion_no_se_bloquea_aunque_comparta_candado(self, entorno):
        t1 = (await post(PREV, manual(tradicion="american"))).json()["token"]
        t2 = (await post(PREV, manual(tradicion="manga"))).json()["token"]
        r = await asyncio.gather(post(ALTA, {"token": t1}), post(ALTA, {"token": t2}))
        assert [x.status_code for x in r] == [200, 200] and await numero_de_series(entorno.banco) == 2

    async def test_titulos_distintos_no_se_serializan_entre_si(self, entorno):
        tokens = [(await post(PREV, manual(t, 1990))).json()["token"] for t in ("Alfa", "Beta", "Gamma", "Delta")]
        r = await asyncio.gather(*(post(ALTA, {"token": t}) for t in tokens))
        assert [x.status_code for x in r] == [200] * 4 and await numero_de_series(entorno.banco) == 4

    async def test_el_mismo_token_dos_veces_a_la_vez_o_seguidas_crea_una_y_devuelve_lo_mismo(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        r = await asyncio.gather(post(ALTA, {"token": token}), post(ALTA, {"token": token}))
        assert [x.status_code for x in r] == [200, 200] and await numero_de_series(entorno.banco) == 1
        ids = {x.json()["serie"]["series_id"] for x in r}
        assert len(ids) == 1 and {x.json()["resultado"] for x in r} == {"creada"}
        assert sorted(x.json()["repetida"] for x in r) == [False, True]
        seguida = await post(ALTA, {"token": token})
        assert seguida.status_code == 200 and seguida.json()["repetida"] is True
        assert seguida.json()["deshacer"] == r[0].json()["deshacer"] and await numero_de_series(entorno.banco) == 1


# ── Procedencia e identidad frente al enriquecedor ───────────────────────────────────────────────

class _Candidata:
    def __init__(self, nombre, cv_id, anio=None):
        self.name, self.cv_id, self.start_year, self.description = nombre, cv_id, anio, "Descripción de la fuente"
        self.image_url, self.count_of_issues = "https://comicvine.gamespot.com/x.jpg", 52


class ClienteCVFalso:
    def __init__(self, resultado):
        self.resultado, self.consultas = resultado, []

    async def search_series(self, titulo, limit=10):
        self.consultas.append(titulo)
        return [self.resultado] if self.resultado else []


async def enriquecer(banco: Banco, cliente_cv: ClienteCVFalso) -> EnrichmentReport:
    informe = EnrichmentReport()
    async with banco.fabrica() as s:
        await EnrichmentService(s)._enrich_series_batch(cliente_cv, None, None, 20, informe)
        await s.commit()
    return informe


class TestProcedenciaEIdentidad:

    async def test_una_serie_manual_no_la_toca_el_enriquecedor(self, entorno):
        await previsualizar_y_confirmar(manual("Flash", 1987))
        (antes,) = await serie_en_bd(entorno.banco)
        fila = await fila_de_serie(entorno.banco, antes.id)
        cv = ClienteCVFalso(_Candidata("Flash", 999999, 1987))
        await enriquecer(entorno.banco, cv)
        assert cv.consultas == [] and await fila_de_serie(entorno.banco, antes.id) == fila

    async def test_el_control_una_serie_sin_identidad_ni_bloqueo_si_se_enriquece(self, entorno):
        """Sin este control, las pruebas de arriba y de abajo podrían pasar por no ejecutar nada."""
        sid = await sembrar_serie(entorno.banco, "Flash", 1987)
        cv = ClienteCVFalso(_Candidata("Flash", 999999, 1987))
        await enriquecer(entorno.banco, cv)
        assert cv.consultas == ["Flash"]
        async with entorno.banco.fabrica() as s:
            assert (await s.get(Series, sid)).comic_vine_id == 999999

    async def test_una_serie_de_fuente_conserva_su_identificador_y_su_procedencia(self, entorno):
        await previsualizar_y_confirmar(desde_fuente(id_="796"))
        (antes,) = await serie_en_bd(entorno.banco)
        fila = await fila_de_serie(entorno.banco, antes.id)
        cv = ClienteCVFalso(_Candidata("Flash", 999999, 1987))
        await enriquecer(entorno.banco, cv)
        (despues,) = await serie_en_bd(entorno.banco)
        assert despues.comic_vine_id == 796 and despues.metadata_["alta"] == antes.metadata_["alta"]
        assert cv.consultas == [] and await fila_de_serie(entorno.banco, antes.id) == fila

    @pytest.mark.parametrize(("fuente", "id_", "campo", "valor"), FUENTES)
    async def test_aunque_el_enriquecedor_llegue_a_aplicar_un_match_no_cambia_la_identidad(
            self, entorno, fuente, id_, campo, valor):
        """`locked_fields` es la segunda barrera: si algún día se selecciona la serie, el id elegido no se sustituye."""
        await previsualizar_y_confirmar(desde_fuente(fuente=fuente, id_=id_, descripcion=None))
        async with entorno.banco.fabrica() as s:
            serie = (await s.execute(select(Series))).scalar_one()
            alta_antes = dict(serie.metadata_["alta"])
            EnrichmentService._apply_series_match(
                serie, SeriesMatch(source_id=424242 if campo != "tebeosfera_slug" else "otro_slug",
                                   description="De la fuente", cover_url=None, count_of_issues=10), campo, fuente)
            await s.commit()
        (despues,) = await serie_en_bd(entorno.banco)
        assert getattr(despues, campo) == valor and despues.metadata_source == fuente
        assert despues.metadata_["alta"] == alta_antes
        assert despues.description == "De la fuente"        # sí rellena los descriptivos que estaban vacíos

    async def test_un_escritor_que_fusiona_por_clave_no_pisa_la_procedencia(self, entorno):
        await previsualizar_y_confirmar(manual())
        (s,) = await serie_en_bd(entorno.banco)
        alta = dict(s.metadata_["alta"])
        nuevo = alta_serie.fusionar_metadata(s.metadata_, {"otra_cosa": {"x": 1}, "alta": {"version": 99}})
        assert nuevo["alta"] == alta and nuevo["otra_cosa"] == {"x": 1}
        assert alta_serie.fusionar_metadata({}, {"a": 1}) == {"a": 1}
        assert alta_serie.fusionar_metadata(None, {"a": 1}) == {"a": 1}

    async def test_la_api_de_series_no_deja_cambiar_la_procedencia(self, entorno):
        await previsualizar_y_confirmar(manual())
        (s,) = await serie_en_bd(entorno.banco)
        alta = dict(s.metadata_["alta"])
        async with cliente() as c:
            for cuerpo in ({"metadata_": {"alta": {}}}, {"metadata": {"alta": {}}}, {"locked_fields": []},
                           {"metadata_source": None}):
                await c.patch(f"/api/series/{s.id}", json=cuerpo)
        (despues,) = await serie_en_bd(entorno.banco)
        assert despues.metadata_["alta"] == alta and despues.metadata_source == "manual"


# ── Deshacer ────────────────────────────────────────────────────────────────────────────────────

async def crear_y_obtener(entorno, cuerpo=None) -> dict:
    r = await previsualizar_y_confirmar(cuerpo or manual())
    assert r.status_code == 200 and r.json()["deshacer"], r.text
    return r.json()["deshacer"]


def ruta_deshacer(sid) -> str:
    return f"{ALTA}/{sid}/deshacer"


class TestDeshacer:

    async def test_una_serie_recien_creada_se_deshace_y_no_toca_los_archivos(self, entorno):
        antes = await instantanea(entorno.banco)
        d = await crear_y_obtener(entorno)
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert r.json() == {"deshecho": True, "series_id": d["series_id"], "titulo": "Flash"}
        assert await numero_de_series(entorno.banco) == 0 and await instantanea(entorno.banco) == antes

    async def test_deshacer_dos_veces_la_segunda_es_404(self, entorno):
        d = await crear_y_obtener(entorno)
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).status_code == 200
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).status_code == 404

    async def test_repetir_el_token_de_una_operacion_creada_devuelve_su_resultado(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        a = (await post(ALTA, {"token": token})).json()
        b = (await post(ALTA, {"token": token})).json()
        assert (a["repetida"], b["repetida"]) == (False, True) and a["serie"] == b["serie"]
        assert a["deshacer"] == b["deshacer"] and await numero_de_series(entorno.banco) == 1

    async def test_un_reintento_atrasado_no_revierte_el_deshacer(self, entorno):
        """Antes (limitación conocida) el comprobante era la fila de `series`, y deshacer lo borraba: reenviar el
        token aún válido la recreaba. Ahora el comprobante es `alta_operaciones` y `deshecha` PREVALECE."""
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).status_code == 200
        for _ in range(2):
            r = await post(ALTA, {"token": token})
            assert r.status_code == 409 and r.json()["detail"]["codigo"] == "alta_deshecha"
            assert await numero_de_series(entorno.banco) == 0
        assert [(o[2]) for o in await operaciones(entorno.banco)] == ["deshecha"]

    async def test_se_puede_volver_a_dar_de_alta_despues_de_deshacer(self, entorno):
        d = await crear_y_obtener(entorno)
        await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert (await previsualizar_y_confirmar(manual())).json()["resultado"] == "creada"

    async def test_con_otra_operacion_no_se_deshace(self, entorno):
        d = await crear_y_obtener(entorno)
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": str(uuid4())})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_creada_por_esta_operacion"
        assert await numero_de_series(entorno.banco) == 1

    async def test_una_serie_que_ya_existia_y_se_reutilizo_nunca_se_borra(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1987, comic_vine_id=796)
        c = (await previsualizar_y_confirmar(desde_fuente())).json()
        assert c["resultado"] == "reutilizada" and c["deshacer"] is None
        for op in (str(uuid4()), str(sid), "00000000-0000-0000-0000-000000000000"):
            r = await post(ruta_deshacer(sid), {"operacion_id": op})
            assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_creada_por_esta_operacion", op
        assert await numero_de_series(entorno.banco) == 1

    async def test_una_serie_creada_por_el_flujo_y_luego_reutilizada_solo_se_deshace_con_la_operacion_que_la_creo(self, entorno):
        d = await crear_y_obtener(entorno, desde_fuente())
        reutilizada = (await previsualizar_y_confirmar(desde_fuente())).json()
        assert reutilizada["resultado"] == "reutilizada" and reutilizada["deshacer"] is None
        otra_op = await post(ruta_deshacer(d["series_id"]), {"operacion_id": str(uuid4())})
        assert otra_op.status_code == 409 and await numero_de_series(entorno.banco) == 1

    async def test_con_numeros_se_rechaza(self, entorno):
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=UUID(d["series_id"]), issue_number="1"))
            await s.commit()
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tiene_numeros"
        assert await numero_de_series(entorno.banco) == 1

    async def test_con_un_archivo_vinculado_se_rechaza_y_el_archivo_no_cambia(self, entorno):
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            issue = Issue(series_id=UUID(d["series_id"]), issue_number="1")
            s.add(issue)
            await s.flush()
            await s.execute(text("UPDATE files SET issue_id = :i WHERE id = (SELECT id FROM files ORDER BY id LIMIT 1)"),
                            {"i": issue.id})
            await s.commit()
        antes = await instantanea(entorno.banco)
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tiene_archivos"
        assert await instantanea(entorno.banco) == antes and await numero_de_series(entorno.banco) == 1

    async def test_con_una_operacion_de_asignacion_viva_se_rechaza(self, entorno):
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            fid = (await s.execute(text("SELECT id FROM files LIMIT 1"))).scalar_one()
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), "
                "'/o', '/d', '/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"),
                {"f": fid, "s": d["series_id"], "sha": SHA})
            await s.commit()
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "operacion_viva"
        assert await numero_de_series(entorno.banco) == 1

    async def test_con_deseados_se_rechaza(self, entorno):
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            await s.execute(text("INSERT INTO wishlist (id, series_id, status, priority) VALUES (gen_random_uuid(), :s, "
                                 "CAST('wanted' AS wishlist_status), 5)"), {"s": d["series_id"]})
            await s.commit()
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tiene_deseados"

    async def test_con_una_politica_de_busqueda_activada_se_rechaza(self, entorno):
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            await s.execute(text("UPDATE series SET wishlist_policy = CAST('faltantes' AS wishlist_policy) WHERE id = :i"),
                            {"i": d["series_id"]})
            await s.commit()
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tiene_deseados"

    async def test_peticiones_mal_formadas(self, entorno):
        d = await crear_y_obtener(entorno)
        assert (await post(ruta_deshacer(d["series_id"]), {})).status_code == 422
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": "no-es-uuid"})).status_code == 422
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"], "forzar": True})).status_code == 422
        assert (await post(ruta_deshacer("no-es-uuid"), {"operacion_id": d["operacion_id"]})).status_code == 422
        assert (await post(ruta_deshacer(uuid4()), {"operacion_id": d["operacion_id"]})).status_code == 404
        assert await numero_de_series(entorno.banco) == 1

    async def test_un_numero_que_se_esta_creando_a_la_vez_gana_al_deshacer(self, entorno):
        """Protección frente a concurrencia: quien inserta un número sin confirmar mantiene `FOR KEY SHARE` sobre
        la serie; deshacer (`FOR UPDATE`) espera, y al despertar ve el número y se niega."""
        d = await crear_y_obtener(entorno)
        sid = UUID(d["series_id"])
        async with entorno.banco.fabrica() as otro:
            issue = Issue(series_id=sid, issue_number="1")
            otro.add(issue)
            await otro.flush()                                   # sin commit todavía
            deshaciendo = asyncio.create_task(post(ruta_deshacer(sid), {"operacion_id": d["operacion_id"]}))
            await asyncio.sleep(0.5)
            assert not deshaciendo.done(), "deshacer no puede adelantarse a quien está creando un número"
            await otro.commit()
        r = await asyncio.wait_for(deshaciendo, 10)
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tiene_numeros"
        assert await numero_de_series(entorno.banco) == 1
        async with entorno.banco.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM issues"))).scalar_one() == 1

    async def test_quien_inserta_un_numero_espera_a_que_deshacer_termine(self, entorno):
        """El otro sentido: con la serie bloqueada por deshacer, no se le cuelga un número a una serie que va a
        desaparecer; al terminar, la inserción falla por la clave foránea (la serie ya no existe)."""
        d = await crear_y_obtener(entorno)
        sid = UUID(d["series_id"])
        async with entorno.banco.fabrica() as bloqueo:
            await bloqueo.execute(select(Series).where(Series.id == sid).with_for_update())   # «deshacer» a medias

            async def insertar():
                async with entorno.banco.fabrica() as s:
                    s.add(Issue(series_id=sid, issue_number="1"))
                    await s.commit()
            insercion = asyncio.create_task(insertar())
            await asyncio.sleep(0.5)
            assert not insercion.done()
            await bloqueo.execute(text("DELETE FROM series WHERE id = :i"), {"i": sid})
            await bloqueo.commit()
        with pytest.raises(Exception):               # noqa: B017 — IntegrityError del driver
            await asyncio.wait_for(insercion, 10)
        assert await numero_de_series(entorno.banco) == 0


# ── El comprobante de la operación (migración 0018) ─────────────────────────────────────────────

async def reiniciar(entorno, url_bd) -> None:
    """«Reiniciar»: otro motor y otra fábrica de sesiones, sin nada de la memoria anterior (el servicio no
    guarda estado en el proceso: lo que sobrevive es lo que está en Postgres)."""
    nuevo = Banco(url_bd)

    async def _get_db():
        async with nuevo.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    await entorno.banco.cerrar()
    entorno.banco = nuevo


def cliente_sin_excepciones() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://localhost", headers={"Origin": "http://localhost"})


async def envejecer(b: Banco, operacion: str, *, horas: int = 25, token_caducado: bool | None = None) -> None:
    """Retrasa `creada` y, si se pide, fija el token como caducado (True) o vigente (False)."""
    async with b.fabrica() as s:
        await s.execute(text("UPDATE alta_operaciones SET creada = now() - make_interval(hours => :h) "
                             "WHERE operacion_id = CAST(:o AS uuid)"), {"h": horas, "o": operacion})
        if token_caducado is not None:
            await s.execute(text("UPDATE alta_operaciones SET token_hasta = now() + make_interval(hours => :d) "
                                 "WHERE operacion_id = CAST(:o AS uuid)"),
                            {"d": -1 if token_caducado else 1, "o": operacion})
        await s.commit()


async def insertar_comprobantes(b: Banco, n: int, *, horas: int, token_caducado: bool, estado="creada") -> list[str]:
    ids = [str(uuid4()) for _ in range(n)]
    async with b.fabrica() as s:
        for i in ids:
            await s.execute(text(
                "INSERT INTO alta_operaciones (operacion_id, series_id, estado, token_hasta, creada) VALUES "
                "(CAST(:o AS uuid), gen_random_uuid(), CAST(:e AS alta_estado), now() + make_interval(hours => :d), "
                "now() - make_interval(hours => :h))"),
                {"o": i, "e": estado, "d": -1 if token_caducado else 1, "h": horas})
        await s.commit()
    return ids


async def ids_de_comprobantes(b: Banco) -> set[str]:
    return {o[0] for o in await operaciones(b)}


def operacion_de(token: str) -> str:
    return verificar_token_alta(token, SECRETO).operacion


class TestComprobanteDeLaOperacion:

    async def test_crear_registra_un_comprobante_minimo_en_la_misma_operacion(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        c = (await post(ALTA, {"token": token})).json()
        (op,) = await operaciones(entorno.banco)
        assert op[:3] == (operacion_de(token), c["serie"]["series_id"], "creada")
        assert op[3] > op[4]                                    # el token vale hasta después de crearse
        async with entorno.banco.fabrica() as s:
            columnas = {r[0] for r in (await s.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'alta_operaciones'"))).all()}
            fk = (await s.execute(text(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = 'alta_operaciones'::regclass AND contype = 'f'"))).scalar_one()
            fila = (await s.execute(text("SELECT alta_operaciones::text FROM alta_operaciones"))).scalar_one()
        assert columnas == {"operacion_id", "series_id", "estado", "token_hasta", "creada", "actualizada"}
        assert fk == 0                                          # borrar la serie NO borra su comprobante
        assert token not in fila and "Flash" not in fila and CARPETA not in fila

    async def test_la_reutilizacion_no_escribe_comprobante(self, entorno):
        await sembrar_serie(entorno.banco, "Flash", 1987, comic_vine_id=796)
        n = len(entorno.banco.sentencias)
        assert (await previsualizar_y_confirmar(desde_fuente())).json()["resultado"] == "reutilizada"
        assert await operaciones(entorno.banco) == [] and escrituras(entorno.banco, n) == []

    # ── Crear → deshacer → reenviar ──────────────────────────────────────────────────────────────

    async def test_crear_deshacer_y_reenviar_el_mismo_token_no_recrea_la_serie(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).raise_for_status()
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "alta_deshecha"
        assert await numero_de_series(entorno.banco) == 0
        (op,) = await operaciones(entorno.banco)
        assert (op[0], op[1], op[2]) == (d["operacion_id"], d["series_id"], "deshecha")

    async def test_el_deshacer_marca_la_operacion_en_la_misma_transaccion_que_el_borrado(self, entorno, monkeypatch):
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]

        async def falla(self, operacion_id):
            raise RuntimeError("fallo antes del commit")
        original = alta_serie.AltaDeSerie._marcar_deshecha
        monkeypatch.setattr(alta_serie.AltaDeSerie, "_marcar_deshecha", falla)
        async with cliente_sin_excepciones() as c:
            r = await c.post(ruta_deshacer(d["series_id"]), json={"operacion_id": d["operacion_id"]})
        assert r.status_code == 500
        assert await numero_de_series(entorno.banco) == 1                     # la serie sigue
        assert [o[2] for o in await operaciones(entorno.banco)] == ["creada"]  # y el comprobante no cambió
        monkeypatch.setattr(alta_serie.AltaDeSerie, "_marcar_deshecha", original)
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).status_code == 200
        assert [o[2] for o in await operaciones(entorno.banco)] == ["deshecha"]

    @pytest.mark.parametrize("donde", ["registrar", "commit"])
    async def test_un_fallo_antes_del_commit_no_deja_ni_serie_ni_comprobante(self, entorno, monkeypatch, donde):
        token = (await post(PREV, manual())).json()["token"]

        async def falla(*a, **kw):
            raise RuntimeError("fallo antes del commit")
        if donde == "registrar":
            original = alta_serie.AltaDeSerie._registrar_operacion
            monkeypatch.setattr(alta_serie.AltaDeSerie, "_registrar_operacion", falla)
        else:
            original = AsyncSession.commit
            monkeypatch.setattr(AsyncSession, "commit", falla)
        async with cliente_sin_excepciones() as c:
            r = await c.post(ALTA, json={"token": token})
        if donde == "registrar":
            monkeypatch.setattr(alta_serie.AltaDeSerie, "_registrar_operacion", original)
        else:
            monkeypatch.setattr(AsyncSession, "commit", original)
        assert r.status_code == 500
        assert await numero_de_series(entorno.banco) == 0 and await operaciones(entorno.banco) == []
        # y el reintento del mismo token funciona y crea UNA
        assert (await post(ALTA, {"token": token})).json()["resultado"] == "creada"
        assert await numero_de_series(entorno.banco) == 1 and len(await operaciones(entorno.banco)) == 1

    async def test_la_caducidad_guardada_es_la_del_token(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        await post(ALTA, {"token": token})
        (op,) = await operaciones(entorno.banco)
        assert int(op[3].timestamp()) == verificar_token_alta(token, SECRETO).caduca

    async def test_un_comprobante_incoherente_deshecho_con_la_serie_aun_viva_tampoco_da_permiso(self, entorno):
        """Defensa en profundidad: aunque algo dejara el comprobante `deshecha` con la serie todavía presente,
        deshacer se niega."""
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            await s.execute(text("UPDATE alta_operaciones SET estado = CAST('deshecha' AS alta_estado)"))
            await s.commit()
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_creada_por_esta_operacion"
        assert await numero_de_series(entorno.banco) == 1

    async def test_tras_un_fallo_la_sesion_queda_limpia_y_sin_candados(self, entorno, monkeypatch):
        """El servicio revierte ÉL MISMO ante cualquier fallo: la sesión no se queda con la transacción abierta ni
        con los candados consultivos (que se sueltan solo al terminar la transacción)."""
        async def candados(s) -> int:
            return (await s.execute(text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"))).scalar_one()

        async def falla(*a, **kw):
            raise RuntimeError("fallo")
        token = (await post(PREV, manual())).json()["token"]
        registrar = alta_serie.AltaDeSerie._registrar_operacion
        async with entorno.banco.fabrica() as s:
            monkeypatch.setattr(alta_serie.AltaDeSerie, "_registrar_operacion", falla)
            with pytest.raises(RuntimeError):
                await alta_serie.AltaDeSerie(s, secret=SECRETO).confirmar(token)
            assert await candados(s) == 0
        monkeypatch.setattr(alta_serie.AltaDeSerie, "_registrar_operacion", registrar)
        # un fallo al deshacer, con una sesión propia
        d = (await post(ALTA, {"token": token})).json()["deshacer"]

        async def falla_marcar(self, operacion_id):
            raise RuntimeError("fallo")
        async with entorno.banco.fabrica() as s:
            monkeypatch.setattr(alta_serie.AltaDeSerie, "_marcar_deshecha", falla_marcar)
            with pytest.raises(RuntimeError):
                await alta_serie.AltaDeSerie(s, secret=SECRETO).deshacer(UUID(d["series_id"]), UUID(d["operacion_id"]))
            assert await candados(s) == 0

    # ── Reiniciar ────────────────────────────────────────────────────────────────────────────────

    async def test_reiniciar_entre_crear_deshacer_y_reenviar_da_el_mismo_resultado(self, entorno, url_bd):
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        await reiniciar(entorno, url_bd)
        repetida = (await post(ALTA, {"token": token})).json()
        assert (repetida["resultado"], repetida["repetida"], repetida["deshacer"]) == ("creada", True, d)
        await reiniciar(entorno, url_bd)
        assert (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).status_code == 200
        await reiniciar(entorno, url_bd)
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "alta_deshecha"
        assert await numero_de_series(entorno.banco) == 0

    async def test_el_servicio_no_guarda_estado_en_el_proceso(self, entorno, url_bd):
        """Dos instancias independientes del servicio se comportan igual: el comprobante está en Postgres."""
        token = (await post(PREV, manual())).json()["token"]
        async with entorno.banco.fabrica() as s1:
            a = await alta_serie.AltaDeSerie(s1, secret=SECRETO).confirmar(token)
        async with entorno.banco.fabrica() as s2:
            b = await alta_serie.AltaDeSerie(s2, secret=SECRETO).confirmar(token)
        assert (a.repetida, b.repetida, a.serie) == (False, True, b.serie)

    # ── Concurrencia ─────────────────────────────────────────────────────────────────────────────

    async def test_repetir_y_deshacer_a_la_vez_dejan_un_resultado_consistente_sin_recrear(self, entorno):
        for ronda in range(8):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            token = (await post(PREV, manual())).json()["token"]
            d = (await post(ALTA, {"token": token})).json()["deshacer"]
            repetir, deshacer = await asyncio.gather(
                post(ALTA, {"token": token}),
                post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]}))
            assert deshacer.status_code == 200, (ronda, deshacer.text)
            assert repetir.status_code in (200, 409), (ronda, repetir.text)
            if repetir.status_code == 409:
                assert repetir.json()["detail"]["codigo"] == "alta_deshecha"
            assert await numero_de_series(entorno.banco) == 0
            assert [o[2] for o in await operaciones(entorno.banco)] == ["deshecha"]
            assert (await post(ALTA, {"token": token})).status_code == 409           # y no se recrea después

    async def test_un_deshacer_de_una_operacion_aun_no_confirmada_no_hace_nada_ni_la_envenena(self, entorno):
        for ronda in range(10):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            token = (await post(PREV, manual())).json()["token"]
            op = operacion_de(token)
            # Una operación aún no confirmada no tiene serie que deshacer (su id no se conoce todavía): el deshacer
            # no hace nada, no deja ningún comprobante `deshecha` y no impide confirmar y deshacer después.
            confirmar, deshacer = await asyncio.gather(
                post(ALTA, {"token": token}), post(ruta_deshacer(uuid4(), ), {"operacion_id": op}))
            assert confirmar.status_code == 200 and deshacer.status_code == 404, (ronda, confirmar.text, deshacer.text)
            assert await numero_de_series(entorno.banco) == 1
            assert [o[2] for o in await operaciones(entorno.banco)] == ["creada"]
            sid = confirmar.json()["serie"]["series_id"]
            assert (await post(ruta_deshacer(sid), {"operacion_id": op})).status_code == 200

    async def test_confirmar_y_deshacer_esperan_al_candado_de_su_operacion_y_solo_al_suyo(self, entorno):
        """El primer candado del orden común es el de la OPERACIÓN: quien lo tiene retiene a la confirmación (o
        repetición) y al deshacer de esa misma operación, y no a las de otras."""
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        otro = (await post(PREV, manual("Otra serie", 1999))).json()["token"]
        async with entorno.banco.fabrica() as sujeta:
            await sujeta.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('alta_op:' || :o, 0))"),
                                 {"o": d["operacion_id"]})
            repetir = asyncio.create_task(post(ALTA, {"token": token}))
            deshacer = asyncio.create_task(post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]}))
            ajena = await asyncio.wait_for(post(ALTA, {"token": otro}), 10)           # otra operación: no espera
            assert ajena.status_code == 200
            await asyncio.sleep(0.7)
            assert not repetir.done() and not deshacer.done()
            await sujeta.commit()                                                      # suelta el candado
        r, u = await asyncio.wait_for(asyncio.gather(repetir, deshacer), 30)
        assert u.status_code == 200 and r.status_code in (200, 409)
        assert await numero_de_series(entorno.banco) == 1                              # solo queda «Otra serie»

    async def test_mezcla_de_confirmar_repetir_y_deshacer_con_titulos_compartidos_no_se_bloquea(self, entorno):
        """Orden de bloqueos coherente (operación → título → serie): sin interbloqueo ni 500 bajo mezcla."""
        for _ in range(3):
            await entorno.banco.limpiar()
            await entorno.banco.sembrar(*(archivo(f"{CARPETA}/Flash {i:02d} (1987).cbz") for i in range(1, 3)))
            creadas = []
            for titulo in ("Alfa", "Beta", "Gamma"):
                t = (await post(PREV, manual(titulo, 1990))).json()["token"]
                creadas.append((t, (await post(ALTA, {"token": t})).json()["deshacer"]))
            # nuevas altas del MISMO título que las que se están repitiendo o deshaciendo (decididas como duplicados)
            nuevos = [(await post(PREV, manual(t, 1990, decision="crear_igualmente"))).json()["token"]
                      for t in ("Alfa", "Beta", "Delta")]
            tareas = [post(ALTA, {"token": creadas[0][0]}),                                      # repetir Alfa
                      post(ruta_deshacer(creadas[1][1]["series_id"]), {"operacion_id": creadas[1][1]["operacion_id"]}),
                      post(ruta_deshacer(creadas[0][1]["series_id"]), {"operacion_id": creadas[0][1]["operacion_id"]}),
                      post(ALTA, {"token": creadas[2][0]}),                                      # repetir Gamma
                      *(post(ALTA, {"token": t}) for t in nuevos)]
            r = await asyncio.wait_for(asyncio.gather(*tareas), 60)
            assert all(x.status_code in (200, 409) for x in r), [x.text for x in r]
            assert r[1].status_code == 200 and r[2].status_code == 200                           # los dos deshacer
            estados = {o[0]: o[2] for o in await operaciones(entorno.banco)}
            assert estados[creadas[0][1]["operacion_id"]] == estados[creadas[1][1]["operacion_id"]] == "deshecha"
            assert estados[creadas[2][1]["operacion_id"]] == "creada"
            for t, _ in creadas[:2]:                                                             # y no se recrean
                assert (await post(ALTA, {"token": t})).json()["detail"]["codigo"] == "alta_deshecha"

    # ── La serie borrada por otra vía ────────────────────────────────────────────────────────────

    async def test_si_la_serie_se_borro_por_otra_via_el_reintento_no_la_recrea(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        async with entorno.banco.fabrica() as s:                      # borrada por otra vía (p. ej. DELETE /api/series)
            await s.execute(text("DELETE FROM series WHERE id = :i"), {"i": d["series_id"]})
            await s.commit()
        r = await post(ALTA, {"token": token})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "alta_serie_ausente"
        assert await numero_de_series(entorno.banco) == 0
        assert [o[2] for o in await operaciones(entorno.banco)] == ["creada"]      # el comprobante sobrevivió

    # ── Reutilizar nunca da permiso para borrar ──────────────────────────────────────────────────

    async def test_la_operacion_de_una_reutilizacion_no_da_permiso_para_borrar_la_serie_reutilizada(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1987, comic_vine_id=796)
        v = (await post(PREV, desde_fuente())).json()
        op = operacion_de(v["token"])
        assert (await post(ALTA, {"token": v["token"]})).json()["resultado"] == "reutilizada"
        antes = await fila_de_serie(entorno.banco, sid)
        for operacion in (op, str(uuid4()), str(sid)):
            r = await post(ruta_deshacer(sid), {"operacion_id": operacion})
            assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_creada_por_esta_operacion", operacion
        assert await fila_de_serie(entorno.banco, sid) == antes and await operaciones(entorno.banco) == []

    async def test_la_operacion_que_creo_una_serie_no_borra_otra(self, entorno):
        ajena = await sembrar_serie(entorno.banco, "Batman", 1940)
        d = await crear_y_obtener(entorno)
        r = await post(ruta_deshacer(ajena), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_creada_por_esta_operacion"
        assert await numero_de_series(entorno.banco) == 2

    async def test_una_serie_con_la_procedencia_de_otra_operacion_sin_comprobante_no_se_borra(self, entorno):
        """El permiso lo da el COMPROBANTE, no un campo de la serie: una serie con `metadata.alta.operacion_id`
        pero sin comprobante (p. ej. anterior a la 0018 o purgada) no se puede deshacer."""
        d = await crear_y_obtener(entorno)
        async with entorno.banco.fabrica() as s:
            await s.execute(text("DELETE FROM alta_operaciones"))
            await s.commit()
        r = await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_creada_por_esta_operacion"
        assert await numero_de_series(entorno.banco) == 1

    # ── Retención y purga ────────────────────────────────────────────────────────────────────────

    async def test_la_purga_exige_las_dos_condiciones_y_no_toca_series(self, entorno):
        vieja_caducada = (await insertar_comprobantes(entorno.banco, 1, horas=25, token_caducado=True))[0]
        vieja_vigente = (await insertar_comprobantes(entorno.banco, 1, horas=25, token_caducado=False))[0]
        reciente_caducada = (await insertar_comprobantes(entorno.banco, 1, horas=1, token_caducado=True))[0]
        reciente_vigente = (await insertar_comprobantes(entorno.banco, 1, horas=1, token_caducado=False))[0]
        deshecha_vieja = (await insertar_comprobantes(entorno.banco, 1, horas=48, token_caducado=True, estado="deshecha"))[0]
        previas = await numero_de_series(entorno.banco)
        n = len(entorno.banco.sentencias)
        d = await crear_y_obtener(entorno)                                         # la purga corre al crear
        assert await ids_de_comprobantes(entorno.banco) == {vieja_vigente, reciente_caducada, reciente_vigente, d["operacion_id"]}
        assert vieja_caducada not in await ids_de_comprobantes(entorno.banco) and deshecha_vieja not in await ids_de_comprobantes(entorno.banco)
        assert await numero_de_series(entorno.banco) == previas + 1
        borrados = [q for q in entorno.banco.sentencias[n:] if re.match(r"\s*DELETE", q, re.I)]
        assert borrados and all("alta_operaciones" in q and "FROM series" not in q for q in borrados)

    async def test_la_purga_esta_acotada(self, entorno):
        from zascarr.services.alta_serie import LOTE_DE_PURGA
        await insertar_comprobantes(entorno.banco, LOTE_DE_PURGA + 50, horas=30, token_caducado=True)
        await crear_y_obtener(entorno)
        restantes = len(await operaciones(entorno.banco))
        assert restantes == 50 + 1                                                 # 100 purgadas, 50 viejas y la nueva

    async def test_un_comprobante_viejo_con_token_vigente_no_se_purga_y_sigue_impidiendo_la_recreacion(self, entorno):
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).raise_for_status()
        await envejecer(entorno.banco, d["operacion_id"], horas=30, token_caducado=False)   # 30 h, token aún válido
        await crear_y_obtener(entorno, manual("Otra", 1999))                                # dispara la purga
        assert d["operacion_id"] in await ids_de_comprobantes(entorno.banco)
        assert (await post(ALTA, {"token": token})).json()["detail"]["codigo"] == "alta_deshecha"

    async def test_tras_purgar_un_token_caducado_nunca_ejecuta_un_alta(self, entorno):
        """Sin comprobante (purgado) y con el token caducado, nada se ejecuta: hay que rehacer la vista previa."""
        token = (await post(PREV, manual())).json()["token"]
        async with entorno.banco.fabrica() as s:
            with pytest.raises(alta_serie.TokenInvalidoError):                     # reloj 16 min por delante
                await alta_serie.AltaDeSerie(s, secret=SECRETO, ahora=time.time() + 16 * 60).confirmar(token)
        assert await numero_de_series(entorno.banco) == 0 and await operaciones(entorno.banco) == []
        # el mismo token, creado en el pasado y ya caducado, tampoco: ni comprobante ni serie
        viejo = crear_token_alta(AltaFirmada(
            clave=CARPETA, modo="crear", origen="manual", fuente=None, id_externo=None, titulo="Vieja", anio=None,
            tradicion="american", descripcion=None, cover_url=None, serie_id=None, vistas=(),
            operacion=str(uuid4())), SECRETO, ahora=time.time() - 16 * 60)
        r = await post(ALTA, {"token": viejo})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await numero_de_series(entorno.banco) == 0 and await operaciones(entorno.banco) == []

    async def test_purgado_el_comprobante_de_una_operacion_el_token_vigente_se_distingue_del_caducado(self, entorno):
        """Documenta POR QUÉ la purga exige el token caducado: si se borrara el comprobante con el token aún
        vigente, el reintento recrearía la serie. Con el token caducado, el reloj lo impide."""
        token = (await post(PREV, manual())).json()["token"]
        d = (await post(ALTA, {"token": token})).json()["deshacer"]
        (await post(ruta_deshacer(d["series_id"]), {"operacion_id": d["operacion_id"]})).raise_for_status()
        async with entorno.banco.fabrica() as s:                                    # purga INDEBIDA, a mano
            await s.execute(text("DELETE FROM alta_operaciones"))
            await s.commit()
        async with entorno.banco.fabrica() as s:
            with pytest.raises(alta_serie.TokenInvalidoError):                      # caducado: no ejecuta
                await alta_serie.AltaDeSerie(s, secret=SECRETO, ahora=time.time() + 16 * 60).confirmar(token)
        assert await numero_de_series(entorno.banco) == 0


# ── Efectos laterales: nada fuera de `series` ────────────────────────────────────────────────────

class TestSinEfectosLaterales:

    async def test_vista_previa_y_confirmacion_dejan_files_issues_y_rutas_como_estaban(self, entorno):
        antes = await instantanea(entorno.banco)
        for cuerpo in (manual(), desde_fuente(fuente="anilist", id_="1", titulo="Berserk", tradicion_elegida="manga")):
            v = (await post(PREV, cuerpo)).json()
            assert (await post(ALTA, {"token": v["token"]})).status_code == 200
        despues = await instantanea(entorno.banco)
        assert despues == antes and len(despues["files"]) == 3 and despues["issues"] == []
        assert len(await rutas(entorno.banco)) == 3

    async def test_ninguna_escritura_en_la_vista_previa_con_todos_los_caminos(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1988)
        existente = await sembrar_serie(entorno.banco, "Thorgal", 1981, comic_vine_id=11)
        n = len(entorno.banco.sentencias)
        for cuerpo in (manual(), manual(decision="crear_igualmente"), manual(decision="reutilizar", serie_id=str(sid)),
                       desde_fuente(id_="11", titulo="Thorgal"), desde_fuente(id_="12", titulo="Otra")):
            assert (await post(PREV, cuerpo)).status_code == 200, cuerpo
        assert escrituras(entorno.banco, n) == [] and entorno.red == []
        assert existente

    async def test_la_confirmacion_de_un_alta_toma_los_candados_y_escribe_solo_la_serie_y_su_comprobante(self, entorno):
        v = (await post(PREV, manual())).json()
        n = len(entorno.banco.sentencias)
        await post(ALTA, {"token": v["token"]})
        sentencias = entorno.banco.sentencias[n:]
        assert any("pg_advisory_xact_lock" in q and "f_title_norm" in q for q in sentencias)
        tablas = {re.match(r"\s*(?:INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", q, re.I).group(1) for q in escrituras(entorno.banco, n)}
        assert tablas == {"series", "alta_operaciones"}              # la serie y su comprobante; nada más

    async def test_sin_sesion_es_401(self, entorno, monkeypatch):
        from zascarr.config import get_settings
        from zascarr.services.auth import hash_password
        ajustes = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        for ruta, cuerpo in ((PREV, manual()), (ALTA, {"token": "x"}), (ruta_deshacer(uuid4()), {"operacion_id": str(uuid4())})):
            r = await post(ruta, cuerpo)
            assert r.status_code == 401, ruta
        assert await numero_de_series(entorno.banco) == 0
