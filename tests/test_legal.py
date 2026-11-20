"""
tests/test_legal.py

Suite del blindaje legal: aceptación del aviso y la dependencia que la
exige. Solo gatea rutas que disparan red/descarga (ver services/legal.py
y su docstring) — biblioteca/pendientes/ficha de serie no llevan esto.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import LegalAcknowledgment
from zascarr.services.legal import (
    RETORNO_LEGAL_POR_DEFECTO,
    current_legal_version,
    get_acknowledgment,
    is_acknowledged,
    require_legal_acknowledgment,
    resolver_destino_legal,
    volver_legal,
)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.flush = AsyncMock()
        self.added: list = []

    async def execute(self, _statement):
        return FakeExecResult(self._rows)

    def add(self, obj):
        self.added.append(obj)


class TestTextoDelAviso:
    """Caso real (2026-10-20): el aviso enseñaba «[web:168]» y listas como párrafos con guiones.
    Se limpió el propio LEGAL.md (no al pintarlo): cambia `legal_version` y hay que volver a
    aceptarlo."""

    def test_el_fichero_no_lleva_marcas_de_cita(self):
        from zascarr.services.legal import LEGAL_MD_PATH, render_legal_html
        assert "[web:" not in LEGAL_MD_PATH.read_text(encoding="utf-8")
        assert "[web:" not in render_legal_html()

    def test_cada_lista_va_separada_de_su_frase_y_sale_como_lista(self):
        """Python-Markdown exige una línea en blanco antes de una lista."""
        import re

        from zascarr.services.legal import LEGAL_MD_PATH, render_legal_html
        crudo = LEGAL_MD_PATH.read_text(encoding="utf-8")
        assert not re.search(r"^(?![ \t]*[-*] |[ \t]*\|)[^\n]*\S[^\n]*\n[-*] ", crudo, re.M)
        assert "<p>Esto significa que:</p>\n<ul>" in render_legal_html()

    def test_la_version_es_el_hash_del_fichero(self):
        """Lo que se acepta es el fichero: cambiarlo obliga a aceptar de nuevo."""
        import hashlib

        from zascarr.services.legal import LEGAL_MD_PATH, current_legal_version
        crudo = LEGAL_MD_PATH.read_text(encoding="utf-8")
        assert current_legal_version() == hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


class TestVersion:

    def test_version_estable_entre_llamadas(self):
        assert current_legal_version() == current_legal_version()

    def test_version_no_esta_vacia(self):
        assert len(current_legal_version()) > 0


class TestAcknowledgment:

    @pytest.mark.asyncio
    async def test_no_aceptado_sin_filas(self):
        session = FakeSession(rows=[])
        assert await is_acknowledged(session) is False
        assert await get_acknowledgment(session) is None

    @pytest.mark.asyncio
    async def test_aceptado_con_fila_de_la_version_actual(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(UTC))
        session = FakeSession(rows=[ack])
        assert await is_acknowledged(session) is True

    @pytest.mark.asyncio
    async def test_acknowledge_anade_una_fila_con_la_version_actual(self):
        from zascarr.services.legal import acknowledge
        session = FakeSession()
        ack = await acknowledge(session)
        assert ack.legal_version == current_legal_version()
        assert session.added == [ack]


def _request(path="/ui/wishlist", method="POST", query="", headers=None):
    cabeceras = [(b"host", b"localhost")]
    cabeceras.extend(headers or [])
    return Request({
        "type": "http", "method": method, "path": path,
        "query_string": query.encode(), "headers": cabeceras,
    })


def override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


class TestRequireLegalAcknowledgment:

    @pytest.mark.asyncio
    async def test_lanza_403_con_hx_redirect_si_no_aceptado(self):
        session = FakeSession(rows=[])
        request = _request(headers=[
            (b"hx-request", b"true"),
            (b"hx-current-url", b"http://localhost/ui/wishlist"),
        ])
        with pytest.raises(HTTPException) as exc_info:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "legal_acknowledgment_required"
        assert exc_info.value.headers["HX-Redirect"] == "/ui/legal?volver=%2Fui%2Fwishlist"
        assert exc_info.value.headers["Cache-Control"] == "no-store"

    @pytest.mark.asyncio
    async def test_no_lanza_si_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version())
        session = FakeSession(rows=[ack])
        await require_legal_acknowledgment(request=_request(), db=session)  # no debe lanzar

    @pytest.mark.asyncio
    async def test_formulario_normal_bajo_ui_recibe_303_al_wizard(self):
        """Sin htmx y con `Accept: text/html`, el navegador no debe ver el JSON 403."""
        session = FakeSession(rows=[])
        request = _request(path="/ui/series/x/numero/y/mejorar",
                           headers=[(b"accept", b"text/html")])
        with pytest.raises(HTTPException) as exc_info:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc_info.value.status_code == 303
        assert exc_info.value.headers["Location"] == "/ui/legal"
        assert exc_info.value.headers["Cache-Control"] == "no-store"
        assert "HX-Redirect" not in exc_info.value.headers

    @pytest.mark.asyncio
    @pytest.mark.parametrize("acepta", [b"application/json", b"text/html"])
    async def test_la_api_nunca_redirige_al_wizard(self, acepta):
        session = FakeSession(rows=[])
        request = _request(path="/api/wishlist", headers=[(b"accept", acepta)])
        with pytest.raises(HTTPException) as exc_info:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "legal_acknowledgment_required"
        assert exc_info.value.headers["Cache-Control"] == "no-store"
        assert "Location" not in exc_info.value.headers


class TestApiLegalStatus:

    def test_no_aceptado(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/api/legal/status")
        assert r.status_code == 200
        assert r.json()["accepted"] is False

    def test_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(UTC))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/api/legal/status")
        assert r.json()["accepted"] is True


class TestApiLegalAccept:

    def test_sin_acknowledged_true_da_400(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post("/api/legal/accept", json={"acknowledged": False})
        assert r.status_code == 400

    def test_con_acknowledged_true_registra(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post("/api/legal/accept", json={"acknowledged": True})
        assert r.status_code == 201
        assert len(session.added) == 1


class TestUiLegal:

    def test_wizard_muestra_formulario_si_no_aceptado(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/ui/legal")
        assert r.status_code == 200
        assert "Aceptar y continuar" in r.text
        assert r.headers["cache-control"] == "no-store"

    def test_wizard_muestra_estado_si_ya_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(UTC))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/ui/legal")
        assert "aceptado" in r.text.lower()
        assert r.headers["cache-control"] == "no-store"

    def test_accept_sin_las_tres_casillas_no_registra(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post("/ui/legal/accept", data={"acepto_1": "true"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/legal?falta=1"
        assert r.headers["cache-control"] == "no-store"
        assert session.added == []

    def test_accept_con_las_tres_casillas_registra_y_redirige(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true"},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == RETORNO_LEGAL_POR_DEFECTO
        assert r.headers["cache-control"] == "no-store"
        assert len(session.added) == 1

    def test_legal_full_renderiza_markdown(self):
        with use_fake_session(FakeSession()) as client:
            r = client.get("/legal")
        assert r.status_code == 200
        assert "Aviso Legal" in r.text
        assert "<h1>" in r.text or "<h2>" in r.text


_SERIE = "00000000-0000-0000-0000-000000000001"
_NUMERO = "00000000-0000-0000-0000-000000000002"
_ARCHIVO = "00000000-0000-0000-0000-000000000003"
_CONTEXTO_BIBLIOTECA = "/ui/biblioteca%3Fq%3Dflash%26vista%3Dlista"


class TestVolverLegal:
    """Contrato §3.2/§3.3: lista CERRADA de páginas y parámetros. Lo que no
    está en la lista es `None`; el llamador usa el respaldo."""

    @pytest.mark.parametrize("destino", [
        "/ui/wishlist",
        "/ui/wishlist?",
        "/ui/descubrir?q=flash",
        "/ui/descubrir/identificador?identificador=urn%3Aisbn%3A9788467900000",
        "/ui/mejoras",
        "/ui/mejoras?pagina=2",
        f"/ui/series/{_SERIE}",
        f"/ui/series/{_SERIE}?volver={_CONTEXTO_BIBLIOTECA}",
        f"/ui/series/{_SERIE}/numero/{_NUMERO}",
        f"/ui/leer/{_ARCHIVO}",
    ])
    def test_destinos_permitidos_se_devuelven_tal_cual(self, destino):
        assert volver_legal(destino) == destino

    @pytest.mark.parametrize("destino", [
        None, "", "/", "//", "//ui/wishlist", "///ui/wishlist", "////ui/wishlist",
        "//evil.example/ui/wishlist",
        "https://evil.example/ui/wishlist",
        "javascript:alert(1)",
        "data:text/html,x",
        "ui/wishlist",
        "/api/health",
        "/ui/legal",
        "/ui/legal?volver=/ui/wishlist",
        # La Biblioteca es el respaldo, no una entrada de la lista.
        "/ui/biblioteca",
        "/ui/biblioteca?q=flash&vista=lista",
        # Retrocesos y segmentos codificados: el navegador los normaliza antes de pedirlos.
        "/ui/../api/health",
        "/ui/%2e%2e/api/health",
        "/ui/%2E%2E/wishlist",
        "/ui/wishlist/%2e%2e/legal",
        "/ui/wishlist%2f..%2flegal",
        "/ui/wishlist/./x",
        # Separadores y controles que el parser de URL no ve como segmentos.
        "/ui\\wishlist",
        "/ui/wishlist\\",
        "/ui/wishlist ",
        "/ui/wishlist\t",
        "/ui/wishlist\n",
        "/ui/wishlist\r",
        "/ui/wishlist\x00",
        "/ui/wishlist%00",
        "/ui/wishlist%20",
        # Páginas y parámetros fuera de la lista cerrada.
        "/ui/desconocida",
        "/ui/wishlist?q=flash",
        "/ui/mejoras?foo=bar",
        "/ui/mejoras?guardado=escaneado",
        "/ui/mejoras?pagina=0",
        "/ui/mejoras?pagina=abc",
        "/ui/mejoras?pagina=1&pagina=2",
        "/ui/mejoras?=x",
        f"/ui/series/{_SERIE}?guardado=guardado",
        f"/ui/series/{_SERIE}?nota=si",
        f"/ui/series/{_SERIE}?coleccion=x",
        f"/ui/series/{_SERIE}/numero/{_NUMERO}?guardado=numero",
        "/ui/series/not-a-uuid",
        "/ui/wishlist#frag",
        "/ui/descubrir?q=" + "x" * 201,
        "/ui/descubrir/identificador?identificador=" + "x" * 501,
    ])
    def test_destinos_rechazados_devuelven_none(self, destino):
        assert volver_legal(destino) is None

    def test_el_valor_por_defecto_es_biblioteca(self):
        assert RETORNO_LEGAL_POR_DEFECTO == "/ui/biblioteca"


class TestResolucionDelDestino:
    """Prioridad §3.1: explícito > `HX-Current-URL` > `Referer` > respaldo."""

    def test_explicito_gana_a_las_cabeceras(self):
        request = _request(headers=[
            (b"hx-current-url", b"http://localhost/ui/mejoras?pagina=2"),
            (b"referer", b"http://localhost/ui/leer/" + _ARCHIVO.encode()),
        ])
        assert resolver_destino_legal(request, "/ui/wishlist") == "/ui/wishlist"

    def test_explicito_invalido_pasa_al_siguiente_candidato(self):
        request = _request(headers=[(b"hx-current-url", b"http://localhost/ui/mejoras?pagina=2")])
        assert resolver_destino_legal(request, "///ui/wishlist") == "/ui/mejoras?pagina=2"

    def test_sin_explicito_usa_la_url_actual_htmx(self):
        request = _request(headers=[
            (b"hx-current-url", b"http://localhost/ui/mejoras?pagina=2"),
            (b"referer", b"http://localhost/ui/wishlist"),
        ])
        assert resolver_destino_legal(request) == "/ui/mejoras?pagina=2"

    def test_hx_invalido_o_ajeno_pasa_al_referer_local(self):
        request = _request(headers=[
            (b"hx-current-url", b"http://evil.example/ui/wishlist"),
            (b"referer", b"http://localhost/ui/mejoras?pagina=2"),
        ])
        assert resolver_destino_legal(request) == "/ui/mejoras?pagina=2"

    def test_todo_invalido_devuelve_none(self):
        request = _request(headers=[
            (b"hx-current-url", b"http://localhost///ui/wishlist"),
            (b"referer", b"http://localhost/ui/%2e%2e/api/health"),
        ])
        assert resolver_destino_legal(request) is None

    def test_la_url_de_la_peticion_no_es_candidata(self):
        request = _request(path="/ui/wishlist", method="GET")
        assert resolver_destino_legal(request) is None


class TestUatp01RetornoDelAviso:
    def test_aceptar_desde_deseados_vuelve_a_la_pagina_real(self):
        """La ruta real es `/ui/wishlist` (no `/ui/deseados`): se comprueba el
        Location y que el destino responde 200, no solo que la redirección sea
        interna."""
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true",
                      "volver": "/ui/wishlist"},
                follow_redirects=True,
            )
        assert len(session.added) == 1
        assert r.status_code == 200
        assert r.url.path == "/ui/wishlist"
        assert "Deseados" in r.text

    def test_aceptar_conserva_el_estado_de_la_vista(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true",
                      "volver": "/ui/mejoras?pagina=2"},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/mejoras?pagina=2"
        assert r.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize("destino", [
        "https://evil.example/x",
        "//evil.example/x",
        "///ui/wishlist",
        "/ui/legal",
        "/ui/../api/health",
        "/ui/%2e%2e/api/health",
        "/ui/desconocida",
        "/ui/wishlist?q=flash",
        "/ui/biblioteca?q=flash",
        "/api/health",
    ])
    def test_destino_invalido_cae_al_respaldo_local(self, destino):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true",
                      "volver": destino},
                follow_redirects=False,
            )
        assert r.headers["location"] == RETORNO_LEGAL_POR_DEFECTO
        assert r.headers["cache-control"] == "no-store"
        assert len(session.added) == 1

    def test_falta_conserva_el_destino_y_lo_explica(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "volver": "/ui/wishlist"},
                follow_redirects=False,
            )
        assert r.headers["location"] == (
            "/ui/legal?volver=%2Fui%2Fwishlist&falta=1")
        assert r.headers["cache-control"] == "no-store"
        assert session.added == []

    def test_falta_con_un_destino_invalido_no_arrastra_la_manipulacion(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "volver": "//evil.example/x"},
                follow_redirects=False,
            )
        assert r.headers["location"] == "/ui/legal?falta=1"
        assert session.added == []

    def test_wizard_conserva_destino_en_el_formulario(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/ui/legal?volver=%2Fui%2Fwishlist")
        assert 'name="volver" value="/ui/wishlist"' in r.text

    def test_wizard_con_destino_invalido_pinta_el_respaldo(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/ui/legal?volver=%2F%2Fevil.example%2Fx")
        assert r.status_code == 200
        assert 'name="volver" value="/ui/biblioteca"' in r.text

    def test_acceso_directo_acepta_y_vuelve_al_respaldo(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true"},
                follow_redirects=False,
            )
        assert r.headers["location"] == RETORNO_LEGAL_POR_DEFECTO

    def test_ya_aceptado_usa_el_volver_validado(self):
        """La rama «ya aceptado» enlazaba siempre a Biblioteca; debe usar el
        destino validado que llegó en la URL."""
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(UTC))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/ui/legal?volver=%2Fui%2Fwishlist")
        assert r.status_code == 200
        assert '<a class="back-link" href="/ui/wishlist">' in r.text

    def test_ya_aceptado_con_destino_invalido_enlaza_a_biblioteca(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(UTC))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/ui/legal?volver=//evil.example/x")
        assert r.status_code == 200
        assert '<a class="back-link" href="/ui/biblioteca">' in r.text

    @pytest.mark.asyncio
    async def test_el_gate_conserva_la_pagina_htmx(self):
        session = FakeSession(rows=[])
        request = _request(headers=[
            (b"hx-request", b"true"),
            (b"hx-current-url", b"http://localhost/ui/wishlist"),
        ])
        with pytest.raises(HTTPException) as exc:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc.value.headers["HX-Redirect"] == "/ui/legal?volver=%2Fui%2Fwishlist"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cabecera,valor", [
        ("hx-current-url", b"http://localhost///ui/wishlist"),
        ("hx-current-url", b"http://localhost/ui/%2e%2e/api/health"),
        ("referer", b"http://localhost/ui/../api/health"),
        ("referer", b"http://evil.example/ui/wishlist"),
    ])
    async def test_el_gate_no_arrastra_una_url_actual_manipulada(self, cabecera, valor):
        session = FakeSession(rows=[])
        request = _request(headers=[(b"hx-request", b"true"),
                                    (cabecera.encode(), valor)])
        with pytest.raises(HTTPException) as exc:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc.value.headers["HX-Redirect"] == "/ui/legal"

    @pytest.mark.asyncio
    async def test_el_gate_usa_el_referer_local_si_no_hay_url_actual(self):
        session = FakeSession(rows=[])
        request = _request(path="/ui/series/x/numero/y/mejorar",
                           headers=[(b"accept", b"text/html"),
                                    (b"referer", b"http://localhost/ui/mejoras?pagina=2")])
        with pytest.raises(HTTPException) as exc:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == (
            "/ui/legal?volver=%2Fui%2Fmejoras%3Fpagina%3D2")

    @pytest.mark.asyncio
    async def test_el_gate_no_usa_una_url_actual_de_otro_host(self):
        """El host de `HX-Current-URL` debe ser el de la petición: una URL de
        otro origen no decide adónde se vuelve aunque su ruta sea local."""
        session = FakeSession(rows=[])
        request = _request(headers=[
            (b"hx-request", b"true"),
            (b"hx-current-url", b"http://evil.example/ui/wishlist"),
        ])
        with pytest.raises(HTTPException) as exc:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc.value.headers["HX-Redirect"] == "/ui/legal"

    def test_falta_con_destino_invalido_no_promete_conservarlo(self):
        """El aviso no puede decir «tu destino se conserva» si se cayó a Biblioteca."""
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/ui/legal?volver=//evil.example/x&falta=1")
        assert r.status_code == 200
        assert "tu destino se conserva" not in r.text
        assert "Falta marcar alguna de las tres casillas." in r.text

    def test_el_403_del_gate_no_se_cachea(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.post("/ui/wishlist/anadir",
                            data={"series_id": _SERIE},
                            headers={"HX-Request": "true"})
        assert r.status_code == 403
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["hx-redirect"] == "/ui/legal"
        assert r.json()["detail"] == "legal_acknowledgment_required"

    def test_un_formulario_normal_no_ve_el_json_403(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.post(
                "/ui/wishlist/anadir", data={"series_id": _SERIE},
                headers={"Accept": "text/html"}, follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/legal"
        assert r.headers["cache-control"] == "no-store"

    def test_el_gate_no_reintenta_la_accion_protegida(self):
        from unittest.mock import patch

        with use_fake_session(FakeSession(rows=[])) as client, patch(
                "zascarr.web.wishlist.WishlistService.add",
                new_callable=AsyncMock) as add:
            r = client.post("/ui/wishlist/anadir",
                            data={"series_id": _SERIE},
                            headers={"HX-Request": "true"})
        assert r.status_code == 403
        add.assert_not_awaited()
