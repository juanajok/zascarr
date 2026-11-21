"""
tests/test_web_wishlist.py

Suite de los endpoints HTMX de la lista de deseos (D1). Mismo patrón que
test_pendientes.py: sobrescribe get_db con una sesión falsa, prueba el
CONTRATO HTTP (200/404/400, qué fragmento devuelve cada ruta), no la
lógica de negocio (ya cubierta en test_wishlist_service.py).
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, LegalAcknowledgment, Series, Wishlist, WishlistStatus
from zascarr.services.orchestrator import Orchestrator, crear_token_candidato
from zascarr.services.prowlarr import SearchResult


def _accepted() -> FakeExecResult:
    """Fila de la comprobación de aviso legal (gate de rutas de riesgo)
    — va SIEMPRE la primera en la cola de las rutas gateadas, antes que
    cualquier query propia del endpoint."""
    return FakeExecResult([LegalAcknowledgment(legal_version="x")])


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one(self):
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, get_map=None, exec_queue=None):
        self._get_map = get_map or {}
        self._exec_queue = list(exec_queue or [])
        self.flush = AsyncMock()
        self.added: list = []
        self.deleted: list = []

    async def get(self, model, id_):
        return self._get_map.get((model, id_))

    async def execute(self, _statement):
        return self._exec_queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)


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


def make_wishlist_item(series=None, status=WishlistStatus.WANTED) -> Wishlist:
    return Wishlist(id=uuid4(), series_id=series.id if series else None,
                    issue_id=None, status=status)


class TestIndex:

    def test_pagina_lista_items(self):
        series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
        item = make_wishlist_item(series)
        item.series = series
        item.issue = None
        # Segunda query de la ruta (D9): is_acknowledged, tras la de items.
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item]), _accepted()])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Sandman" in r.text
        assert "Aviso legal pendiente" not in r.text

    def test_pagina_vacia_muestra_mensaje(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([]), _accepted()])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Nada en la lista de deseos" in r.text

    def test_aviso_legal_pendiente_muestra_banner(self):
        """D9: el aviso legal pendiente es un banner global de la página,
        no un last_error inventado por fila (ver services/orchestrator.py)."""
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([]), FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Aviso legal pendiente" in r.text
        # AC-10 (UATP-01): el enlace directo lleva el destino de vuelta.
        assert 'href="/ui/legal?volver=%2Fui%2Fwishlist"' in r.text


    def test_un_deseo_que_espera_no_dice_buscando(self):
        """Caso real (2026-10-20): «Buscando…» en filas que nadie busca, con búsquedas en pausa."""
        series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
        item = make_wishlist_item(series, status=WishlistStatus.WANTED)
        item.series = series
        item.issue = None
        sesion = FakeSession(exec_queue=[FakeExecResult([item]), FakeExecResult([])])
        with use_fake_session(sesion) as client:
            r = client.get("/ui/wishlist")
        assert '<span class="chip">Por buscar</span>' in r.text
        # «Buscando…» sigue existiendo en el indicador de «Buscar ahora»; lo que no puede es ser el CHIP
        assert not re.search(r'class="chip[^"]*">(?:<span[^>]*>[^<]*</span> )?Buscando', r.text)

    def test_cada_estado_con_etiqueta_tiene_aspecto_y_downloaded_se_ve_como_downloading(self):
        """DOWNLOADED dice lo mismo que DOWNLOADING; con aspectos distintos se pintaba distinto.
        El aspecto sale de `services/estado_deseo.py` (V8), ya no de una regla CSS por estado."""
        from zascarr.services.estado_deseo import ASPECTO_DE_DESEO
        assert ASPECTO_DE_DESEO[WishlistStatus.DOWNLOADED] == ASPECTO_DE_DESEO[WishlistStatus.DOWNLOADING]
        assert set(ASPECTO_DE_DESEO) == set(WishlistStatus)


class CapturingSession(FakeSession):
    """Como FakeSession, pero guarda cada SELECT compilado con sus literales —
    para fijar el `WHERE` de verdad, no solo lo que el endpoint hace con una
    lista de resultados ya dada."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.statements: list[str] = []

    async def execute(self, statement):
        from sqlalchemy.dialects import postgresql
        self.statements.append(str(statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
        return await super().execute(statement)


class TestEstadosRetiradoD8:
    """D8: `retirado` es un estado nuevo. La revisión de estados tiene que
    cubrirlo en los tres sitios que los recorren: la etiqueta de la fila, el
    listado (que no debe llenarse de filas retiradas) y los ciclos del
    orquestador (ya cubiertos en test_orchestrator.py)."""

    def test_la_etiqueta_del_estado_existe(self):
        """Sin entrada en `_ESTADO_LABEL`, la UI enseñaría el valor crudo del
        enum («retirado») sin explicar que no falló nada."""
        from zascarr.web.wishlist import _ESTADO_LABEL
        assert WishlistStatus.RETIRADO in _ESTADO_LABEL
        assert "Retirado" in _ESTADO_LABEL[WishlistStatus.RETIRADO]

    def test_el_listado_excluye_los_retirados(self):
        session = CapturingSession(exec_queue=[FakeExecResult([]), _accepted()])
        with use_fake_session(session) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "status != 'retirado'" in session.statements[0], session.statements[0]


class TestBuscarSerie:

    def test_devuelve_resultados_como_fragmento(self):
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011)
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([series])])) as client:
            r = client.get("/ui/wishlist/buscar-serie?q=bat")
        assert r.status_code == 200
        assert "Batman" in r.text

    def test_sin_coincidencias(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist/buscar-serie?q=zzz")
        assert "Sin coincidencias" in r.text

    def test_el_boton_no_dice_anadido_si_la_peticion_falla(self):
        """OCTA-C2: el texto de éxito solo se pone con event.detail.successful."""
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([series])])) as client:
            r = client.get("/ui/wishlist/buscar-serie?q=bat")
        assert r.status_code == 200
        assert "event.detail.successful" in r.text
        assert "No se pudo añadir" in r.text


class TestAnadir:

    def test_anade_y_devuelve_la_fila(self):
        series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
        item = make_wishlist_item(series)
        item.series = series
        item.issue = None
        session = FakeSession(exec_queue=[_accepted(), FakeExecResult([item])])
        with use_fake_session(session) as client:
            r = client.post("/ui/wishlist/anadir", data={"series_id": str(series.id)})
        assert r.status_code == 200
        assert "Thorgal" in r.text
        assert len(session.added) == 1

    def test_sin_aceptar_el_aviso_legal_da_403_con_hx_redirect(self):
        session = FakeSession(exec_queue=[FakeExecResult([])])  # sin acknowledgment
        with use_fake_session(session) as client:
            r = client.post("/ui/wishlist/anadir", data={"series_id": str(uuid4())})
        assert r.status_code == 403
        assert r.headers["hx-redirect"] == "/ui/legal"


class TestQuitar:

    def test_quitar_devuelve_vacio(self):
        item = Wishlist(id=uuid4())
        session = FakeSession(get_map={(Wishlist, item.id): item})
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/quitar")
        assert r.status_code == 200
        assert r.text == ""
        assert session.deleted == [item]

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/quitar")
        assert r.status_code == 404


class TestReintentar:

    def test_reintentar_devuelve_la_fila_actualizada(self):
        series = Series(id=uuid4(), title="Mortadelo", tradition=ComicTradition.TEBEO)
        item = Wishlist(id=uuid4(), series_id=series.id, status=WishlistStatus.FAILED)
        row_item = make_wishlist_item(series, status=WishlistStatus.WANTED)
        row_item.series = series
        row_item.issue = None
        session = FakeSession(
            get_map={(Wishlist, item.id): item},
            exec_queue=[_accepted(), FakeExecResult([row_item])],
        )
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/reintentar")
        assert r.status_code == 200
        assert "Mortadelo" in r.text

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/reintentar")
        assert r.status_code == 404


class TestBuscarAhora:
    """D10: ver candidatos reales antes de enviar nada a descargar."""

    def test_muestra_los_candidatos_encontrados(self, monkeypatch):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        monkeypatch.setattr(
            Orchestrator, "preview_candidates",
            AsyncMock(return_value=[SearchResult(
                title="Batman #1.cbz", indexer="test", download_url="magnet:?xt=urn:btih:abc",
                size_bytes=52_428_800, seeders=12, category="comics",
            )]),
        )
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
        assert r.status_code == 200
        assert "Batman #1.cbz" in r.text
        assert "Descargar este" in r.text
        assert "CBZ" in r.text
        # UX 2026-11-16: cada candidato identificable y el envío reemplaza SOLO su <li>,
        # para poder descargar varios sin perder la lista.
        assert f'id="candidato-{item.id}-0"' in r.text
        assert 'name="indice" value="0"' in r.text
        assert 'hx-target="closest li"' in r.text

    def test_sin_candidatos_muestra_el_motivo_de_d9(self, monkeypatch):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED,
                        last_error="No se encontró nada en las fuentes activas")
        monkeypatch.setattr(Orchestrator, "preview_candidates", AsyncMock(return_value=[]))
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
        assert r.status_code == 200
        assert "No se encontró nada en las fuentes activas" in r.text

    def test_sin_query_construible_da_mensaje_generico(self, monkeypatch):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        monkeypatch.setattr(Orchestrator, "preview_candidates", AsyncMock(return_value=None))
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
        assert r.status_code == 200
        assert "No se pudo construir la búsqueda" in r.text

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/buscar-ahora")
        assert r.status_code == 404

    def test_sin_aceptar_el_aviso_legal_da_403_con_hx_redirect(self):
        session = FakeSession(exec_queue=[FakeExecResult([])])  # sin acknowledgment
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/buscar-ahora")
        assert r.status_code == 403
        assert r.headers["hx-redirect"] == "/ui/legal"


class TestCancelarBusqueda:

    def test_devuelve_vacio_sin_tocar_la_bd(self):
        """Cancelar tras ver candidatos no deja nada a medias: ni
        siquiera hace falta tocar la sesión."""
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/cancelar-busqueda")
        assert r.status_code == 200
        assert r.text == ""


class TestEnviarCandidato:
    """D10: el token liga el candidato a ESTE item y caduca — hallazgo de
    revisión (2026-09-26), ver services/orchestrator.py::crear_token_candidato.
    Ya no se reconstruye el candidato a partir de campos sueltos del
    formulario, así que estos tests fabrican el mismo token que emitiría
    el servidor, y comprueban que manipularlo lo invalida."""

    SECRETO = "clave-de-prueba-tests"

    def _candidato(self) -> SearchResult:
        return SearchResult(
            title="Batman #1.cbz", indexer="test", download_url="magnet:?xt=urn:btih:abc",
            size_bytes=52428800, seeders=12, category="comics",
        )

    def _token(self, item_id) -> str:
        return crear_token_candidato(item_id, self._candidato(), self.SECRETO)

    @pytest.fixture(autouse=True)
    def _con_secret_key(self, monkeypatch):
        settings = get_settings().model_copy(update={"secret_key": self.SECRETO})
        monkeypatch.setattr("zascarr.web.wishlist.get_settings", lambda: settings)

    def test_envia_el_candidato_elegido_y_devuelve_la_fila(self, monkeypatch):
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
        item = Wishlist(id=uuid4(), series_id=series.id, status=WishlistStatus.WANTED)
        row_item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
        row_item.id = item.id   # `_get_row` lo busca por id: el estado es el MISMO ítem
        row_item.series = series
        row_item.issue = None
        enviado = AsyncMock(return_value=True)
        monkeypatch.setattr(Orchestrator, "send_manual_candidate", enviado)
        session = FakeSession(
            get_map={(Wishlist, item.id): item},
            exec_queue=[_accepted(), FakeExecResult([row_item])],
        )
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/enviar-candidato",
                            data={"token": self._token(item.id)})
        assert r.status_code == 200
        assert "Batman" in r.text
        enviado.assert_awaited_once()
        candidato_enviado = enviado.await_args.args[1]
        assert candidato_enviado.title == "Batman #1.cbz"
        assert candidato_enviado.download_url == "magnet:?xt=urn:btih:abc"
        # El resto de candidatos NO se pierde: solo se actualiza el estado (OOB) y este li.
        assert f'hx-swap-oob="outerHTML:#estado-fila-{item.id}"' in r.text
        assert f'id="candidato-{item.id}-0"' in r.text
        assert "candidato-enviado" in r.text
        assert "Enviado" in r.text and "a la cola de descarga" in r.text
        assert 'class="wishlist-row"' not in r.text

    def test_item_inexistente_da_404(self):
        item_id = uuid4()
        with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
            r = client.post(f"/ui/wishlist/{item_id}/enviar-candidato",
                            data={"token": self._token(item_id)})
        assert r.status_code == 404

    def test_token_de_otro_item_se_rechaza(self):
        """El hallazgo central de la revisión: un token válido pero
        emitido para OTRO item no debe servir para este — nunca se
        reconstruye el candidato sin comprobar el item_id."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        otro_item_id = uuid4()
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/enviar-candidato",
                            data={"token": self._token(otro_item_id)})
        assert r.status_code == 400

    def test_token_manipulado_se_rechaza(self):
        """Cambiar un solo carácter del payload firmado (p. ej. la URL de
        descarga) invalida la firma entera — no se puede colar una URL
        distinta a la que de verdad se mostró."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        token = self._token(item.id)
        manipulado = token[:-1] + ("0" if token[-1] != "0" else "1")
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/enviar-candidato",
                            data={"token": manipulado})
        assert r.status_code == 400

    def test_token_de_otro_secreto_se_rechaza(self):
        """Equivalente a un token caducado/de una instalación distinta:
        firmado con una clave que no es la actual."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        token = crear_token_candidato(item.id, self._candidato(), "otra-clave-distinta")
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/enviar-candidato", data={"token": token})
        assert r.status_code == 400

    def test_doble_confirmacion_no_reenvia(self, monkeypatch):
        """El item ya no está en un estado accionable (DOWNLOADING) tras
        el primer envío — send_manual_candidate() debe rechazar un
        segundo envío del mismo token dentro de su ventana de validez,
        no solo el propio Orchestrator lo hace: aquí se comprueba que el
        router deja pasar la llamada y es Orchestrator quien decide."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.DOWNLOADING)
        row_item = make_wishlist_item(status=WishlistStatus.DOWNLOADING)
        real = AsyncMock(wraps=None, return_value=False)
        monkeypatch.setattr(Orchestrator, "send_manual_candidate", real)
        session = FakeSession(
            get_map={(Wishlist, item.id): item},
            exec_queue=[_accepted(), FakeExecResult([row_item])],
        )
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/enviar-candidato",
                            data={"token": self._token(item.id)})
        assert r.status_code == 200  # el router siempre responde con la fila...
        real.assert_awaited_once()   # ...pero delega el rechazo real a Orchestrator

    def test_sin_aceptar_el_aviso_legal_da_403_con_hx_redirect(self):
        item_id = uuid4()
        session = FakeSession(exec_queue=[FakeExecResult([])])  # sin acknowledgment
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item_id}/enviar-candidato",
                            data={"token": self._token(item_id)})
        assert r.status_code == 403
        assert r.headers["hx-redirect"] == "/ui/legal"


def test_index_avisa_si_prowlarr_esta_incompleto(monkeypatch):
    """D9 (2026-11-11): Prowlarr encendido sin URL/clave no se presenta como «sin resultados»."""
    settings = get_settings().model_copy(update={
        "prowlarr_enabled": True, "prowlarr_url": "", "prowlarr_api_key": ""})
    monkeypatch.setattr("zascarr.web.wishlist.get_settings", lambda: settings)
    with use_fake_session(FakeSession(exec_queue=[FakeExecResult([]), _accepted()])) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert "Prowlarr está encendido pero le falta la URL o la clave" in r.text
    assert "Revisar Prowlarr en Ajustes" in r.text


def _candidato_de_prueba() -> SearchResult:
    return SearchResult(
        title="Batman #1.cbz", indexer="test", download_url="magnet:?xt=urn:btih:abc",
        size_bytes=52428800, seeders=12, category="comics",
    )


def test_buscar_ahora_avisa_de_que_puede_tardar_y_se_deshabilita():
    """UX 2026-11-16: con el foro espaciado, la búsqueda manual tarda ~1-2 min; debe verse
    que trabaja (indicador con aria-live) y el botón no debe poder pulsarse dos veces."""
    series = Series(id=uuid4(), title="DC K.O.", tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.WANTED)
    item.series = series
    item.issue = None
    sesion = FakeSession(exec_queue=[FakeExecResult([item]), FakeExecResult([])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert 'hx-post="/ui/wishlist/' in r.text and "buscar-ahora" in r.text
    assert 'hx-disable="this"' in r.text
    assert 'role="status" aria-live="polite"' in r.text
    assert "puede tardar hasta 2 minutos" in r.text


def test_anadir_deseo_inserta_la_fila_sin_recargar_la_pagina(monkeypatch):
    """UX 2026-11-16: el botón recargaba con un hook que no se ejecutaba y la fila
    no aparecía hasta refrescar a mano. Ahora se inserta al final de la lista."""
    series = Series(id=uuid4(), title="DC K.O.", tradition=ComicTradition.AMERICAN)
    monkeypatch.setattr(
        "zascarr.web.wishlist.WishlistService.search_series",
        AsyncMock(return_value=[series]))
    with use_fake_session(FakeSession()) as client:
        r = client.get("/ui/wishlist/buscar-serie", params={"q": "DC"})
    assert r.status_code == 200
    assert 'hx-target="#wishlist-list" hx-swap="beforeend"' in r.text
    assert "window.location.reload" not in r.text
    assert "this.disabled = true" in r.text


def test_un_deseo_descargado_se_puede_marcar_como_conseguido():
    """Descarga manual que quedó en _Unsorted: el deseo no puede quedarse
    «Descargando…» para siempre (2026-11-16)."""
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Sector Lejano", tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    item.series = series
    item.issue = None
    fila = make_wishlist_item(series, status=WishlistStatus.IMPORTED)
    fila.id = item.id
    fila.series = series
    fila.issue = None
    sesion = FakeSession(get_map={(Wishlist, item.id): item},
                         exec_queue=[FakeExecResult([fila])])
    with use_fake_session(sesion) as client:
        r = client.post(f"/ui/wishlist/{item.id}/marcar-conseguido")
    assert r.status_code == 200
    assert item.status is WishlistStatus.IMPORTED
    assert item.downloaded_at is not None
    assert item.last_error is None

def test_la_fila_descargando_ofrece_ya_lo_tengo():
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Sector Lejano", tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    item.series = series
    item.issue = None
    sesion = FakeSession(exec_queue=[FakeExecResult([item]), FakeExecResult([])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert "Ya lo tengo" in r.text
    assert "/marcar-conseguido" in r.text


def test_la_pagina_explica_sin_ruido_y_resume_la_lista():
    """Pasada UI/UX 2026-11-16: introducción corta, «cómo funciona» plegado,
    indicador del buscador y resumen de la lista."""
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    item.series = series
    item.issue = None
    sesion = FakeSession(exec_queue=[FakeExecResult([item]), FakeExecResult([])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert "¿Cómo funciona?" in r.text
    assert "Buscando series…" in r.text
    assert "1 deseo" in r.text and "1 en descarga" in r.text
    assert 'aria-label="Quitar Sandman de Deseados"' in r.text
    assert 'aria-label="Marcar Sandman como conseguido"' in r.text

def test_los_candidatos_muestran_cabecera_y_el_boton_dice_que_descarga(monkeypatch):
    item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
    serie = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
    item.series_id = serie.id
    monkeypatch.setattr(
        Orchestrator, "preview_candidates",
        AsyncMock(return_value=[_candidato_de_prueba()]))
    session = FakeSession(get_map={(Wishlist, item.id): item},
                          exec_queue=[_accepted(), FakeExecResult([item])])
    with use_fake_session(session) as client:
        r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
    assert r.status_code == 200
    assert "1 resultado" in " ".join(r.text.split())
    assert "Cerrar lista" in r.text
    assert 'hx-disable="this"' in r.text
    assert 'aria-label="Descargar Batman #1.cbz"' in r.text


def test_un_deseo_ya_descargado_dice_descargado_no_descargando():
    """DOWNLOADED es «terminó la descarga, falta importar»; decir
    «Descargando…» confundía con DOWNLOADING (pasada UI/UX 2026-11-16)."""
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADED)
    item.series = series
    item.issue = None
    sesion = FakeSession(exec_queue=[FakeExecResult([item]), FakeExecResult([])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist")
    assert "Descargado" in r.text
    assert "Descargando…" not in r.text


def test_el_panel_de_progreso_lee_transmission_una_vez(monkeypatch):
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Absolute Wonder Woman",
                    tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    item.series = series
    item.issue = None
    item.download_backend = "transmission"
    item.download_ref = "ABC123"
    otro = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    otro.series = series
    otro.issue = None
    otro.download_backend = "amule"
    otro.download_ref = "ED2KHASH"

    cliente = AsyncMock()
    cliente.list_torrents.return_value = [
        {"hashString": "abc123", "percentDone": 0.4}]
    monkeypatch.setattr("zascarr.web.wishlist.TransmissionClient",
                        lambda: cliente)
    ajustes = get_settings().model_copy(update={"transmission_enabled": True})
    monkeypatch.setattr("zascarr.web.wishlist.get_settings", lambda: ajustes)
    sesion = FakeSession(exec_queue=[FakeExecResult([item, otro])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist/progreso")
    assert r.status_code == 200
    assert "40%" in r.text and "aMule" in r.text
    assert cliente.list_torrents.await_count == 1

def test_el_panel_de_progreso_no_pide_nada_sin_descargas():
    sesion = FakeSession(exec_queue=[FakeExecResult([])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist/progreso")
    assert r.status_code == 200 and r.text == ""

def test_la_pagina_carga_el_panel_de_progreso():
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    item.series = series
    item.issue = None
    sesion = FakeSession(exec_queue=[FakeExecResult([item]), FakeExecResult([])])
    with use_fake_session(sesion) as client:
        r = client.get("/ui/wishlist")
    assert 'hx-get="/ui/wishlist/progreso"' in r.text
    assert "every 30s" in r.text


def test_buscar_ahora_no_accede_a_relaciones_sin_precargar(monkeypatch):
    """Regresión 2026-11-17: `_row(item)` sobre un `db.get` sin eager lanzaba
    MissingGreenlet en async y la búsqueda devolvía 500. La ruta no debe tocar
    `item.series`/`item.issue`; con un objeto que falla si se accede, responde 200."""
    item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED, search_query="Absolute Batman")
    serie = Series(id=uuid4(), title="Absolute Batman", tradition=ComicTradition.AMERICAN)
    item.series_id = serie.id

    # Un `Wishlist` real no permitiría este parche por el descriptor de SQLAlchemy,
    # así que se simula el acceso perezoso con un objeto mínimo para la ruta.
    class ItemSinRelaciones:
        id = item.id
        search_query = "Absolute Batman"
        status = WishlistStatus.WANTED
        last_error = None

        @property
        def series(self):  # pragma: no cover - debe fallar si se llama
            raise AssertionError("la ruta no debe leer item.series sin eager")

        @property
        def issue(self):  # pragma: no cover - idem
            raise AssertionError("la ruta no debe leer item.issue sin eager")

    monkeypatch.setattr(Orchestrator, "preview_candidates",
                        AsyncMock(return_value=[_candidato_de_prueba()]))
    sesion = FakeSession(get_map={(Wishlist, item.id): ItemSinRelaciones()},
                         exec_queue=[_accepted()])
    with use_fake_session(sesion) as client:
        r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
    assert r.status_code == 200
    assert "Resultados encontrados" in r.text


class TestConsultaEnLaUrl:
    """UATP-01b (#1199): la consulta de búsqueda viaja en `?q=`."""

    def _pagina(self, monkeypatch, q, series=()):
        monkeypatch.setattr(
            "zascarr.web.wishlist.WishlistService.search_series",
            AsyncMock(return_value=list(series)))
        cola = [FakeExecResult([]), _accepted()]
        with use_fake_session(FakeSession(exec_queue=cola)) as client:
            return client.get("/ui/wishlist", params={"q": q} if q is not None else None)

    def test_q_rellena_el_campo_y_pinta_los_resultados_sin_js(self, monkeypatch):
        serie = Series(
            id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011)
        r = self._pagina(monkeypatch, "bat", [serie])
        assert r.status_code == 200
        assert 'id="q-deseados" value="bat"' in r.text
        assert re.search(r'id="resultados-wishlist" class="series-results" aria-live="polite">\s*<ul', r.text)
        assert "Batman" in r.text

    def test_q_sin_coincidencias_lo_dice(self, monkeypatch):
        r = self._pagina(monkeypatch, "zzz")
        assert "Sin coincidencias" in r.text

    @pytest.mark.parametrize("q", [None, "", "   "])
    def test_sin_consulta_es_la_pagina_de_siempre(self, monkeypatch, q):
        r = self._pagina(monkeypatch, q)
        assert r.status_code == 200
        assert 'id="resultados-wishlist" class="series-results" aria-live="polite"></div>' in r.text
        assert "Sin coincidencias" not in r.text

    def test_q_de_201_caracteres_se_ignora(self, monkeypatch):
        r = self._pagina(monkeypatch, "x" * 201)
        assert r.status_code == 200
        assert "x" * 201 not in r.text
        assert "Sin coincidencias" not in r.text

    def test_q_con_html_se_escapa(self, monkeypatch):
        r = self._pagina(monkeypatch, '"><script>alert(1)</script>')
        assert "<script>alert(1)" not in r.text
        assert "&lt;script&gt;" in r.text

    def test_el_aviso_legal_pendiente_vuelve_con_la_consulta(self, monkeypatch):
        monkeypatch.setattr(
            "zascarr.web.wishlist.WishlistService.search_series", AsyncMock(return_value=[]))
        with use_fake_session(
                FakeSession(exec_queue=[FakeExecResult([]), FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist", params={"q": "bat man"})
        assert 'href="/ui/legal?volver=%2Fui%2Fwishlist%3Fq%3Dbat%2Bman"' in r.text

    def test_buscar_serie_actualiza_la_url_de_la_pagina(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist/buscar-serie", params={"q": "bat man"})
        assert r.headers["HX-Replace-Url"] == "/ui/wishlist?q=bat+man"

    def test_buscar_serie_vacia_deja_la_url_limpia(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist/buscar-serie", params={"q": " "})
        assert r.headers["HX-Replace-Url"] == "/ui/wishlist"
class TestUatp04Referencias:
    """UATP-04: referencia única, enlace a ficha y nombres accesibles."""

    def _index(self, *items):
        return FakeSession(exec_queue=[FakeExecResult(list(items)), _accepted()])

    def test_row_usa_reference_name_con_fallback_title(self):
        from zascarr.web.wishlist import _row

        con_ref = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        con_ref.reference_name = "Flash (1987)"
        item = make_wishlist_item(con_ref)
        item.series = con_ref
        item.issue = None
        row = _row(item)
        assert row["referencia"] == "Flash (1987)"
        assert row["enlace_ficha"] == (
            f"/ui/series/{con_ref.id}?volver=%2Fui%2Fwishlist")

        sin_ref = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        sin_ref.reference_name = None
        item2 = make_wishlist_item(sin_ref)
        item2.series = sin_ref
        item2.issue = None
        row2 = _row(item2)
        assert row2["referencia"] == "Flash"
        assert "(1987)" not in row2["referencia"]

    def test_row_anade_number_key_y_enlaza_a_la_serie(self):
        from types import SimpleNamespace

        from zascarr.web.wishlist import _row

        series = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        series.reference_name = "Flash (1987)"
        item = make_wishlist_item(series)
        item.series = None
        item.issue = SimpleNamespace(series=series, number_key="7", issue_number="7b")
        row = _row(item)
        assert row["referencia"] == "Flash (1987) #7"
        assert row["enlace_ficha"].startswith(f"/ui/series/{series.id}?volver=")

    def test_indice_distingue_dos_flash_y_enlaza(self):
        uno = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        uno.reference_name = "Flash (1987)"
        dos = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        dos.reference_name = "Flash (2011)"
        items = []
        for serie in (uno, dos):
            item = make_wishlist_item(serie)
            item.series = serie
            item.issue = None
            items.append(item)
        with use_fake_session(self._index(*items)) as client:
            r = client.get("/ui/wishlist")
        assert "Flash (1987)" in r.text and "Flash (2011)" in r.text
        assert f'href="/ui/series/{uno.id}?volver=%2Fui%2Fwishlist"' in r.text
        assert f'href="/ui/series/{dos.id}?volver=%2Fui%2Fwishlist"' in r.text
        for referencia in ("Flash (1987)", "Flash (2011)"):
            assert f'aria-label="Seleccionar {referencia}"' in r.text
            assert f'aria-label="Quitar {referencia} de Deseados"' in r.text

    def test_anadir_devuelve_la_misma_referencia_y_enlace(self):
        series = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        series.reference_name = "Flash (1987)"
        item = make_wishlist_item(series)
        item.series = series
        item.issue = None
        fila = FakeExecResult([item])
        sesion = FakeSession(exec_queue=[_accepted(), fila])
        with use_fake_session(sesion) as client:
            r = client.post("/ui/wishlist/anadir", data={"series_id": str(series.id)})
        assert r.status_code == 200
        assert "Flash (1987)" in r.text
        assert f'/ui/series/{series.id}?volver=%2Fui%2Fwishlist' in r.text

    def test_selector_usa_referencia_y_boton_con_nombre_unico(self):
        series = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
        series.reference_name = "Flash (1987)"
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([series])])) as client:
            r = client.get("/ui/wishlist/buscar-serie?q=flash")
        assert "Flash (1987)" in r.text
        assert '<span data-texto>Añadir a deseados</span>' in r.text
        assert "Añadir a deseados</span><span class=\"sr\">: Flash (1987)" in r.text
        assert "querySelector('[data-texto]')" in r.text
        assert "this.textContent" not in r.text

    def test_resultados_es_region_viva(self):
        with use_fake_session(self._index()) as client:
            r = client.get("/ui/wishlist")
        assert 'id="resultados-wishlist" class="series-results" aria-live="polite"' in r.text
        assert 'role="status"' in r.text  # el indicador existente, sin duplicar


def test_progreso_usa_la_referencia(monkeypatch):
    from zascarr.models import WishlistStatus

    series = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN)
    series.reference_name = "Flash (1987)"
    item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
    item.series = series
    item.issue = None
    item.download_backend = "transmission"
    item.download_ref = "ABC"
    cliente = AsyncMock()
    cliente.list_torrents.return_value = [{"hashString": "abc", "percentDone": 0.4}]
    monkeypatch.setattr("zascarr.web.wishlist.TransmissionClient", lambda: cliente)
    ajustes = get_settings().model_copy(update={"transmission_enabled": True})
    monkeypatch.setattr("zascarr.web.wishlist.get_settings", lambda: ajustes)
    with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item])])) as client:
        r = client.get("/ui/wishlist/progreso")
    assert "Flash (1987)" in r.text
    assert 'aria-label="Progreso de Flash (1987)"' in r.text
