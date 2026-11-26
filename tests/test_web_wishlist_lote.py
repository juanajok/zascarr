"""#878: cancelar la búsqueda en curso y buscar varios deseos en lote (sin red)."""
from __future__ import annotations

from unittest.mock import AsyncMock
from urllib.parse import urlencode
from uuid import uuid4

from starlette.requests import Request

from tests.test_web_wishlist import (
    FakeExecResult,
    FakeSession,
    _accepted,
    use_fake_session,
)
from zascarr.config import get_settings
from zascarr.models import ComicTradition, Series, Wishlist, WishlistStatus
from zascarr.services.orchestrator import Orchestrator, crear_token_candidato
from zascarr.services.prowlarr import SearchResult
from zascarr.web.wishlist import buscar_ahora, buscar_lote, enviar_candidato


def _item(con_relaciones: bool = True, *, id_=None, status=WishlistStatus.WANTED):
    serie = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
    item = Wishlist(id=id_ or uuid4(), status=status, search_query="Sandman")
    item.series = serie if con_relaciones else None
    item.issue = None
    return item


def _lote(client, ids):
    return client.post(
        "/ui/wishlist/buscar-lote",
        content=urlencode([("item_id", str(ident)) for ident in ids]),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


def _candidato() -> SearchResult:
    return SearchResult(title="Sandman #1.cbz", indexer="test",
                        download_url="magnet:?xt=urn:btih:abc", size_bytes=1024,
                        seeders=3, category="comics")


def _request_desconectado() -> Request:
    """Doble de cliente ASGI: el navegador ya cerró la conexión.

    El handler no se cancela por recibir `http.disconnect` (medido con uvicorn 0.54.0);
    estas pruebas fijan ese comportamiento sin depender de un servidor real.
    """
    async def receive():
        return {"type": "http.disconnect"}

    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/ui/wishlist",
        "raw_path": b"/ui/wishlist",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }, receive)


def _index(client, item):
    sesion = FakeSession(exec_queue=[FakeExecResult([item]), _accepted()])
    return sesion, client


def test_la_pagina_tiene_checkbox_solo_para_buscables():
    item = _item()
    with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item]), _accepted()])) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert f'name="item_id" value="{item.id}"' in r.text
    assert 'aria-label="Seleccionar Sandman"' in r.text or 'aria-label="Seleccionar ' in r.text


def test_la_pagina_tiene_barra_de_lote_y_resultado():
    item = _item()
    with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item]), _accepted()])) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert 'hx-post="/ui/wishlist/buscar-lote"' in r.text
    assert 'hx-include="#wishlist-list input[name=\'item_id\']:checked"' in r.text
    assert 'hx-target="#resultado-lote"' in r.text
    assert 'id="buscando-lote"' in r.text and "Buscando seleccionados" in r.text
    assert 'id="resultado-lote" aria-live="polite"' in r.text
    assert 'id="form-lote"' in r.text and 'id="boton-buscar-lote"' in r.text
    assert 'hx-disable="find #boton-buscar-lote"' in r.text
    assert 'id="cancelar-lote"' in r.text and "Dejar de esperar la tanda" in r.text
    assert 'hx-get="/ui/wishlist/aviso-cancelado-lote"' in r.text
    assert 'hx-target="#aviso-cancelado-lote"' in r.text
    assert 'id="aviso-cancelado-lote"' in r.text
    assert "htmx.trigger('#form-lote', 'htmx:abort')" in r.text


def test_el_boton_buscar_ahora_se_puede_cancelar():
    item = _item()
    with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item]), _accepted()])) as client:
        r = client.get("/ui/wishlist")
    assert r.status_code == 200
    assert f'id="boton-buscar-{item.id}"' in r.text
    assert "htmx:abort" in r.text and f"boton-buscar-{item.id}" in r.text
    assert "Dejar de esperar" in r.text
    assert 'aria-label="Dejar de esperar la búsqueda de Sandman"' in r.text
    assert 'hx-get="/ui/wishlist/aviso-cancelado"' in r.text
    assert f'hx-target="#aviso-cancelado-{item.id}"' in r.text
    assert f'id="aviso-cancelado-{item.id}"' in r.text
    assert "lo ya enviado no se deshace" not in r.text


def test_dos_items_devuelven_dos_paneles_oob(monkeypatch):
    item1, item2 = _item(), _item(id_=uuid4())
    monkeypatch.setattr(Orchestrator, "preview_candidates",
                        AsyncMock(return_value=[_candidato()]))
    sesion = FakeSession(get_map={(Wishlist, item1.id): item1,
                                  (Wishlist, item2.id): item2},
                         exec_queue=[_accepted()])
    with use_fake_session(sesion) as client:
        r = _lote(client, [item1.id, item2.id])
    assert r.status_code == 200
    assert "Se buscaron 2 deseos" in r.text
    assert r.text.count('hx-swap-oob="outerHTML:#candidatos-') == 2
    assert f'id="candidatos-{item1.id}"' in r.text and f'id="candidatos-{item2.id}"' in r.text
    assert "Sandman #1.cbz" in r.text
    assert item1.status == WishlistStatus.WANTED      # no se toca el estado


def test_mas_de_ocho_no_busca(monkeypatch):
    preview = AsyncMock()
    monkeypatch.setattr(Orchestrator, "preview_candidates", preview)
    ids = [str(uuid4()) for _ in range(9)]
    with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
        r = _lote(client, ids)
    assert r.status_code == 200
    assert "máximo por tanda es 8" in r.text
    preview.assert_not_awaited()
    # La tanda rechazada también retira el aviso anterior de «dejar de esperar».
    assert 'id="aviso-cancelado-lote"' in r.text
    assert 'hx-swap-oob="true"' in r.text


def test_sin_seleccion_avisa_sin_buscar(monkeypatch):
    preview = AsyncMock()
    monkeypatch.setattr(Orchestrator, "preview_candidates", preview)
    with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
        r = client.post("/ui/wishlist/buscar-lote")
    assert r.status_code == 200 and "No has seleccionado ningún deseo" in r.text
    preview.assert_not_awaited()
    assert 'id="aviso-cancelado-lote"' in r.text and 'hx-swap-oob="true"' in r.text


def test_un_id_inexistente_se_salta_con_nota(monkeypatch):
    item = _item()
    monkeypatch.setattr(Orchestrator, "preview_candidates",
                        AsyncMock(return_value=[_candidato()]))
    sesion = FakeSession(get_map={(Wishlist, item.id): item},
                         exec_queue=[_accepted()])
    with use_fake_session(sesion) as client:
        r = _lote(client, [item.id, uuid4()])
    assert r.status_code == 200
    assert "Se buscaron 1 deseo" in r.text and "ya no estaban en la lista" in r.text


def test_la_ruta_no_toca_relaciones_perezosas(monkeypatch):
    """Regresión MissingGreenlet 2026-11-17: no se llama a `_row(item)`."""
    item = _item(con_relaciones=False)
    item.search_query = "Sandman"

    class ItemSinRelaciones:
        id = item.id
        search_query = "Sandman"
        status = WishlistStatus.WANTED
        last_error = None

        @property
        def series(self):
            raise AssertionError("la ruta no debe leer item.series")

        @property
        def issue(self):
            raise AssertionError("la ruta no debe leer item.issue")

    monkeypatch.setattr(Orchestrator, "preview_candidates",
                        AsyncMock(return_value=[_candidato()]))
    sesion = FakeSession(get_map={(Wishlist, item.id): ItemSinRelaciones()},
                         exec_queue=[_accepted()])
    with use_fake_session(sesion) as client:
        r = _lote(client, [item.id])
    assert r.status_code == 200 and "Resultados encontrados" in r.text


def test_el_aviso_de_la_busqueda_deja_de_esperar_sin_prometer_cancelar():
    with use_fake_session(FakeSession()) as client:
        r = client.get("/ui/wishlist/aviso-cancelado")
    assert r.status_code == 200
    texto = " ".join(r.text.split())
    assert "Has dejado de esperar la búsqueda" in texto
    assert "puede seguir consultando las fuentes" in texto
    assert "esta búsqueda no envía nada al programa de descargas" in texto.lower()
    assert "el ciclo automático puede enviar por su cuenta" in texto
    assert "Descargas en curso" in texto and "Transmission/aMule" in texto
    assert "no se guardan" in texto
    assert 'href="/ui/wishlist"' in texto
    assert "se cancela" not in r.text


def test_el_aviso_de_la_tanda_deja_de_esperar_sin_prometer_cancelar():
    with use_fake_session(FakeSession()) as client:
        r = client.get("/ui/wishlist/aviso-cancelado-lote")
    assert r.status_code == 200
    texto = " ".join(r.text.split())
    assert "Has dejado de esperar la tanda" in texto
    assert "hasta 8" in texto
    assert "incluidos los que aún no había empezado" in texto
    assert "los que no haya empezado no se buscan" not in texto
    assert "esta tanda no envía nada al programa de descargas" in texto.lower()
    assert "el ciclo automático puede enviar por su cuenta" in texto
    assert "Descargas en curso" in texto and "Transmission/aMule" in texto
    assert "no se guardan" in texto
    assert 'href="/ui/wishlist"' in texto


def test_buscar_ahora_no_envia_nada_al_cliente_de_descargas(monkeypatch):
    """UXA-13b: la búsqueda solo consulta fuentes; el envío es «Sí, descargar»."""
    item = _item()
    send = AsyncMock()
    monkeypatch.setattr(Orchestrator, "preview_candidates",
                        AsyncMock(return_value=[_candidato()]))
    monkeypatch.setattr(Orchestrator, "send_manual_candidate", send)
    sesion = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
    with use_fake_session(sesion) as client:
        r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
    assert r.status_code == 200
    send.assert_not_awaited()


def test_buscar_lote_no_envia_nada_al_cliente_de_descargas(monkeypatch):
    item = _item()
    send = AsyncMock()
    monkeypatch.setattr(Orchestrator, "preview_candidates",
                        AsyncMock(return_value=[_candidato()]))
    monkeypatch.setattr(Orchestrator, "send_manual_candidate", send)
    sesion = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
    with use_fake_session(sesion) as client:
        r = _lote(client, [item.id])
    assert r.status_code == 200
    send.assert_not_awaited()


async def test_buscar_ahora_sigue_si_el_cliente_desconecta(monkeypatch):
    """Doble ASGI: `http.disconnect` no cancela el handler (uvicorn 0.54.0)."""
    item = _item()
    preview = AsyncMock(return_value=[_candidato()])
    monkeypatch.setattr(Orchestrator, "preview_candidates", preview)
    sesion = FakeSession(get_map={(Wishlist, item.id): item})
    await buscar_ahora(item.id, _request_desconectado(), sesion)
    preview.assert_awaited_once()


async def test_buscar_lote_sigue_con_todos_si_el_cliente_desconecta(monkeypatch):
    """La tanda no se detiene al cerrar el navegador: recorre los 8 seleccionados."""
    item1, item2 = _item(), _item(id_=uuid4())
    preview = AsyncMock(return_value=[_candidato()])
    monkeypatch.setattr(Orchestrator, "preview_candidates", preview)
    sesion = FakeSession(get_map={(Wishlist, item1.id): item1,
                                  (Wishlist, item2.id): item2})
    await buscar_lote(_request_desconectado(), [item1.id, item2.id], sesion)
    assert preview.await_count == 2


async def test_enviar_candidato_puede_completar_si_el_cliente_desconecta(monkeypatch):
    """El envío manual no tiene control de cancelación: el handler puede terminarlo."""
    secreto = "clave-de-prueba-tests"
    settings = get_settings().model_copy(update={"secret_key": secreto})
    monkeypatch.setattr("zascarr.web.wishlist.get_settings", lambda: settings)
    item = _item()
    row_item = _item(id_=item.id, status=WishlistStatus.DOWNLOADING)
    enviado = AsyncMock(return_value=True)
    monkeypatch.setattr(Orchestrator, "send_manual_candidate", enviado)
    sesion = FakeSession(
        get_map={(Wishlist, item.id): item},
        exec_queue=[FakeExecResult([row_item])],
    )
    token = crear_token_candidato(item.id, _candidato(), secreto)
    await enviar_candidato(item.id, _request_desconectado(), sesion, token, 0)
    enviado.assert_awaited_once()
