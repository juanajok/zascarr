"""#878: cancelar la búsqueda en curso y buscar varios deseos en lote (sin red)."""
from __future__ import annotations

from unittest.mock import AsyncMock
from urllib.parse import urlencode
from uuid import uuid4

from tests.test_web_wishlist import (
    FakeExecResult,
    FakeSession,
    _accepted,
    use_fake_session,
)
from zascarr.models import ComicTradition, Series, Wishlist, WishlistStatus
from zascarr.services.orchestrator import Orchestrator
from zascarr.services.prowlarr import SearchResult


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
    assert r.text.count("hx-swap-oob") >= 2
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
    assert "hx-swap-oob" not in r.text


def test_sin_seleccion_avisa_sin_buscar(monkeypatch):
    preview = AsyncMock()
    monkeypatch.setattr(Orchestrator, "preview_candidates", preview)
    with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
        r = client.post("/ui/wishlist/buscar-lote")
    assert r.status_code == 200 and "No has seleccionado ningún deseo" in r.text
    preview.assert_not_awaited()


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
    assert "no se ha enviado nada a tu programa de descargas" in texto.lower()
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
    assert "no se ha enviado nada a tu programa de descargas" in texto.lower()
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
