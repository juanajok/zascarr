# ruff: noqa: E501, F401, F811
"""Descubrir en DOS PASOS sobre Postgres real (I2 de #114): buscar → revisar → crear → deshacer, por la aplicación real.

Lo que se prueba, por HTTP y con las fuentes simuladas (nada sale a la red): que **revisar no escribe**; que la tradición la
elige la persona (no la sugerencia de la fuente); que crear delega en `AltaDeSerie` (procedencia, identificador protegido,
comprobante, deshacer, idempotencia); que el identificador exacto reutiliza sin tocar; que las parecidas las decide la
persona y que las nuevas entre la vista previa y la confirmación se rechazan; que los tokens inválidos y los cuerpos
antiguos no crean nada; y que dos confirmaciones a la vez no duplican ni dan un 500. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import os
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, text

import zascarr.web.discovery as web_discovery
from tests.test_alta_serie_pg import (  # noqa: F401  (BD efímera y entorno sin red)
    CARPETA,
    CV_OK,
    SECRETO,
    cliente,
    entorno,
    numero_de_series,
    sembrar_serie,
    serie_en_bd,
    url_bd,
)
from zascarr.models import AltaOperacion, ComicTradition, Issue, MetadataSource, Series
from zascarr.services.discovery import DiscoveryResult, DiscoveryService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(autouse=True)
def _clave_de_firma_web(monkeypatch, entorno):
    monkeypatch.setattr(web_discovery, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))


def resultado(**kw) -> DiscoveryResult:
    base = dict(source=MetadataSource.COMIC_VINE, external_id="796", title="Flash", start_year=1987,
                description="Velocista.", cover_url=CV_OK, site_url=None, tradition_guess=ComicTradition.AMERICAN)
    return DiscoveryResult(**{**base, **kw})


async def buscar(monkeypatch, *resultados) -> str:
    monkeypatch.setattr(DiscoveryService, "search", AsyncMock(return_value=(list(resultados), [])))
    async with cliente() as c:
        r = await c.get("/ui/descubrir/buscar", params={"q": "flash"})
    assert r.status_code == 200, r.text
    return r.text


def valor(html: str, nombre: str, n: int = 0) -> str:
    return re.findall(rf'name="{nombre}" value="([^"]*)"', html)[n]


async def post(ruta: str, **campos):
    async with cliente() as c:
        return await c.post(ruta, data=campos)


async def revisar(candidata: str, tradition: str = "american", **extra):
    return await post("/ui/descubrir/revisar", candidata=candidata, tradition=tradition, **extra)


async def comprobantes(b) -> int:
    async with b.fabrica() as s:
        return len((await s.execute(select(AltaOperacion))).scalars().all())


async def crear_flash(monkeypatch, tradition="american", **kw) -> tuple[str, str]:
    """(candidata, token de alta) de una vista previa limpia de «Flash»."""
    html = await buscar(monkeypatch, resultado(**kw))
    candidata = valor(html, "candidata")
    v = await revisar(candidata, tradition)
    assert v.status_code == 200 and 'name="token"' in v.text, v.text
    return candidata, valor(v.text, "token")


class TestRevisarNoEscribeNada:
    @pytest.mark.asyncio
    async def test_la_vista_previa_ofrece_crear_con_la_tradicion_elegida_y_no_escribe(self, entorno, monkeypatch):
        html = await buscar(monkeypatch, resultado(tradition_guess=ComicTradition.AMERICAN))
        v = await revisar(valor(html, "candidata"), "manga")                 # la persona elige MANGA, la fuente sugería americana
        assert v.status_code == 200
        assert "Crear serie vacía" in v.text and "Tradición elegida: <strong>Manga</strong>" in v.text
        assert "sin números ni archivos" in v.text
        assert await numero_de_series(entorno.banco) == 0 and await comprobantes(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_revisar_pide_la_tradicion_y_no_acepta_una_vacia(self, entorno, monkeypatch):
        html = await buscar(monkeypatch, resultado())
        r = await post("/ui/descubrir/revisar", candidata=valor(html, "candidata"), tradition="")
        assert r.status_code == 422 and await numero_de_series(entorno.banco) == 0


class TestCrear:
    @pytest.mark.asyncio
    async def test_crea_la_serie_con_la_tradicion_elegida_el_identificador_protegido_y_la_procedencia(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch, "manga")
        r = await post("/ui/descubrir/crear", token=token)
        assert r.status_code == 200 and "creada" in r.text and "Ver ficha" in r.text and "Deshacer" in r.text
        assert "Añadir a deseados" in r.text
        (s,) = await serie_en_bd(entorno.banco)
        assert (s.title, s.start_year, s.tradition, s.comic_vine_id) == ("Flash", 1987, ComicTradition.MANGA, 796)
        assert s.metadata_source == "comic_vine" and s.locked_fields == ["comic_vine_id"] and s.cover_url == CV_OK
        alta = s.metadata_["alta"]
        assert alta["origen"] == "descubrir" and alta["desde_grupo"] is None and alta["tradicion_elegida"] is True
        assert await comprobantes(entorno.banco) == 1

    @pytest.mark.asyncio
    async def test_no_exige_aceptacion_legal(self, entorno, monkeypatch):
        """Catalogar metadatos no es descargar: ni revisar ni crear devuelven 403 por falta de aceptación legal."""
        _, token = await crear_flash(monkeypatch)
        assert (await post("/ui/descubrir/crear", token=token)).status_code == 200

    @pytest.mark.asyncio
    async def test_el_slug_de_tebeosfera_se_guarda_como_texto(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch, "franco_belgian", source=MetadataSource.TEBEOSFERA,
                                     external_id="thorgal_1981_distrinovel", title="Thorgal", start_year=1981, cover_url=None)
        await post("/ui/descubrir/crear", token=token)
        (s,) = await serie_en_bd(entorno.banco)
        assert (s.tebeosfera_slug, s.comic_vine_id, s.anilist_id, s.gcd_id) == ("thorgal_1981_distrinovel", None, None, None)

    @pytest.mark.asyncio
    async def test_una_portada_no_permitida_nunca_llega_a_la_serie(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch, cover_url="http://127.0.0.1:9091/x.jpg")
        await post("/ui/descubrir/crear", token=token)
        assert (await serie_en_bd(entorno.banco))[0].cover_url is None

    @pytest.mark.asyncio
    async def test_repetir_la_confirmacion_no_crea_otra_y_lo_dice(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch)
        a, b = await post("/ui/descubrir/crear", token=token), await post("/ui/descubrir/crear", token=token)
        assert "ya se había creado" in b.text and a.status_code == b.status_code == 200
        assert await numero_de_series(entorno.banco) == 1 and await comprobantes(entorno.banco) == 1


class TestIdentificadorExacto:
    @pytest.mark.asyncio
    async def test_reutiliza_la_serie_que_ya_tiene_ese_identificador_sin_tocarla(self, entorno, monkeypatch):
        sid = await sembrar_serie(entorno.banco, "Otro título", 2001, comic_vine_id=796)
        html = await buscar(monkeypatch, resultado())
        v = await revisar(valor(html, "candidata"), "american")
        assert "Usar esta serie" in v.text and str(sid) in v.text
        r = await post("/ui/descubrir/crear", token=valor(v.text, "token"))
        assert "ya estaba en tu biblioteca" in r.text and "Deshacer" not in r.text
        (s,) = await serie_en_bd(entorno.banco)
        assert s.title == "Otro título" and await comprobantes(entorno.banco) == 0


class TestParecidas:
    @pytest.mark.asyncio
    async def test_la_persona_elige_entre_reutilizar_una_parecida_o_crear_otra(self, entorno, monkeypatch):
        sid = await sembrar_serie(entorno.banco, "FLASH", 1988)
        html = await buscar(monkeypatch, resultado())
        cand = valor(html, "candidata")
        v = await revisar(cand, "american")
        assert "Series que ya tienes y se parecen" in v.text and 'name="token"' not in v.text      # sin token hasta decidir
        assert "Es distinta: crear otra" in v.text and str(sid) in v.text
        assert await numero_de_series(entorno.banco) == 1
        elige = await revisar(cand, "american", decision="reutilizar", serie_id=str(sid))
        assert "Usar esta serie" in elige.text
        assert "ya estaba en tu biblioteca" in (await post("/ui/descubrir/crear", token=valor(elige.text, "token"))).text
        crea = await revisar(cand, "american", decision="crear_igualmente")
        assert "Crear serie vacía" in crea.text
        assert "creada" in (await post("/ui/descubrir/crear", token=valor(crea.text, "token"))).text
        assert await numero_de_series(entorno.banco) == 2

    @pytest.mark.asyncio
    async def test_una_parecida_que_aparece_entre_la_vista_previa_y_la_confirmacion_no_se_crea_en_silencio(self, entorno, monkeypatch):
        cand, token = await crear_flash(monkeypatch)
        await sembrar_serie(entorno.banco, "Flash", 1987)                    # aparece después de la vista previa
        r = await post("/ui/descubrir/crear", token=token, candidata=cand, tradition="american")
        assert r.status_code == 200 and "Han aparecido series parecidas" in r.text and "Revisar de nuevo" in r.text
        assert await numero_de_series(entorno.banco) == 1 and await comprobantes(entorno.banco) == 0


class TestEntradasInvalidas:
    @pytest.mark.asyncio
    async def test_un_token_de_alta_manipulado_no_crea_nada(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch)
        manipulado = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        r = await post("/ui/descubrir/crear", token=manipulado)
        assert r.status_code == 200 and "no es válido o ha caducado" in r.text
        assert await numero_de_series(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_un_token_de_alta_caducado_no_crea_nada(self, entorno, monkeypatch):
        import time

        from zascarr.services import tokens_revision
        original = tokens_revision.time.time
        monkeypatch.setattr(tokens_revision.time, "time", lambda: original() - 3600)
        _, token = await crear_flash(monkeypatch)                          # firmado «hace una hora»
        monkeypatch.setattr(tokens_revision.time, "time", original)
        r = await post("/ui/descubrir/crear", token=token)
        assert "ha caducado" in r.text and await numero_de_series(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_una_candidata_de_un_grupo_no_sirve_en_descubrir(self, entorno, monkeypatch):
        from zascarr.services.tokens_revision import CandidataFirmada, crear_token_candidata
        de_grupo = crear_token_candidata(CARPETA, CandidataFirmada("comic_vine", "796", "Flash", 1987, "american", None, None), SECRETO)
        r = await revisar(de_grupo, "american")
        assert r.status_code == 200 and "no es válida o ha caducado" in r.text and 'name="token"' not in r.text

    @pytest.mark.asyncio
    async def test_la_ruta_antigua_de_un_clic_no_crea_nada(self, entorno, monkeypatch):
        r = await post("/ui/descubrir/crear", source="comic_vine", external_id="796", title="Flash", tradition="american")
        assert r.status_code == 422 and await numero_de_series(entorno.banco) == 0


class TestDeshacer:
    @pytest.mark.asyncio
    async def test_deshace_la_serie_que_creo_la_operacion_y_el_token_no_la_recrea(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch)
        creada = await post("/ui/descubrir/crear", token=token)
        d = await post("/ui/descubrir/deshacer", series_id=valor(creada.text, "series_id"), operacion_id=valor(creada.text, "operacion_id"))
        assert d.status_code == 200 and "ya no está en tu biblioteca" in d.text
        assert await numero_de_series(entorno.banco) == 0
        assert "se creó y se deshizo" in (await post("/ui/descubrir/crear", token=token)).text
        assert await numero_de_series(entorno.banco) == 0

    @pytest.mark.asyncio
    async def test_no_deshace_si_ya_tiene_numeros(self, entorno, monkeypatch):
        _, token = await crear_flash(monkeypatch)
        creada = await post("/ui/descubrir/crear", token=token)
        sid = valor(creada.text, "series_id")
        async with entorno.banco.fabrica() as s:
            s.add(Issue(series_id=sid, issue_number="1"))
            await s.commit()
        d = await post("/ui/descubrir/deshacer", series_id=sid, operacion_id=valor(creada.text, "operacion_id"))
        assert "ya tiene números" in d.text and await numero_de_series(entorno.banco) == 1

    @pytest.mark.asyncio
    async def test_una_operacion_ajena_no_deshace_la_serie(self, entorno, monkeypatch):
        """El identificador de la serie no basta: hace falta el de la operación que LA creó."""
        sid = await sembrar_serie(entorno.banco, "Otra", 2000)
        d = await post("/ui/descubrir/deshacer", series_id=str(sid), operacion_id=str(uuid4()))
        assert "no la creó esta operación" in d.text and await numero_de_series(entorno.banco) == 1


class TestConcurrencia:
    @pytest.mark.asyncio
    async def test_dos_confirmaciones_a_la_vez_con_el_mismo_identificador_no_duplican_ni_dan_error(self, entorno, monkeypatch):
        cand, t1 = await crear_flash(monkeypatch)
        v2 = await revisar(cand, "american")                              # otra vista previa del MISMO resultado
        t2 = valor(v2.text, "token")
        r1, r2 = await asyncio.gather(post("/ui/descubrir/crear", token=t1), post("/ui/descubrir/crear", token=t2))
        assert r1.status_code == r2.status_code == 200
        assert await numero_de_series(entorno.banco) == 1
        assert sorted(("creada" in r.text and "ya estaba" not in r.text) for r in (r1, r2)) == [False, True]
