"""BL-C4 (#151): pantallas de sagas (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.arcos import (
    ArcoResumen,
    DetalleArco,
    FilaArco,
    PaginaArcos,
    ResultadoPedidoArco,
)


def _cliente(metadata=None):
    """Cliente con una BD falsa: `execute` devuelve el `metadata_` del arco (o None)."""
    async def _execute(_consulta):
        return SimpleNamespace(scalar_one_or_none=lambda: metadata)

    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
                              execute=_execute)
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_lista_de_sagas_muestra_orden_y_salto_de_series():
    pagina = PaginaArcos(
        [ArcoResumen("a1", "Court of Owls", True, 2, 2)], 1, 1, 1, 0, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=pagina)):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Court of Owls" in r.text and "2 series" in r.text
    assert "/ui/arcos/a1/portada.jpg" in r.text
    assert "0 de 2 leídos" in r.text


def test_detalle_lista_en_orden_de_lectura():
    filas = [
        FilaArco(1, "i1", "s1", "Batman", "1", None, "2011-01-01", True),
        FilaArco(2, "i2", "s2", "Nightwing", "2", None, None, False),
    ]
    detalle = DetalleArco("a1", "Court of Owls", "Sinopsis", True, filas, 2)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert r.text.index("Batman") < r.text.index("Nightwing")
    assert "En tu biblioteca" in r.text and "No disponible" in r.text
    assert "/ui/arcos/a1/portada.jpg" in r.text
    assert "0 de 2 números leídos" in r.text


def test_detalle_de_saga_atribuye_a_fandom_con_articulo_y_licencia():
    """SCR2 (AC-03/AC-16): un arco creado por el enricher enlaza su página y la licencia."""
    detalle = DetalleArco("a1", "Year One", None, False, [], 0)
    c = _cliente(metadata={"origen": "fandom_dc", "fandom_dc": "Batman: Year One"})
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'href="https://dc.fandom.com/wiki/Batman:_Year_One"' in r.text
    assert 'href="https://creativecommons.org/licenses/by-sa/3.0/"' in r.text
    assert "DC Database" in r.text and "Creative Commons BY-SA 3.0" in r.text


def test_detalle_de_saga_muestra_la_fuente_de_la_guia():
    """SCR3: una saga reconciliada de una guía enlaza su fuente (texto, no hotlinking)."""
    detalle = DetalleArco("a1", "Crisis on Infinite Earths", None, False, [], 0)
    url = ("https://comicbookreadingorders.com/dc/events/"
           "crisis-on-infinite-earths-reading-order/")
    c = _cliente(metadata={"origen": "reading_orders", "url": url})
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert f'href="{url}"' in r.text
    assert 'rel="noopener noreferrer"' in r.text
    assert "Comic Book Reading Orders" in r.text and "Guía de lectura" in r.text


def test_detalle_de_saga_no_pinta_una_url_de_fuente_peligrosa():
    """SecOps m-2: un `metadata_` manipulado con javascript:/data: no se pinta."""
    detalle = DetalleArco("a1", "Crisis", None, False, [], 0)
    for url in ("javascript:alert(1)", "data:text/html,x"):
        c = _cliente(metadata={"origen": "reading_orders", "url": url})
        try:
            with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
                r = c.get(f"/ui/arcos/{uuid4()}")
        finally:
            _cerrar()
        assert "Guía de lectura" not in r.text and "javascript:alert" not in r.text


def test_detalle_de_saga_manual_no_atribuye_a_fandom():
    detalle = DetalleArco("a1", "Saga mía", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200 and "creativecommons.org" not in r.text


def test_saga_sin_datos_muestra_estado_vacio():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(
                return_value=PaginaArcos([], 0, 1, 1, 0, 0))):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200 and "Todavía no hay sagas" in r.text


def test_formularios_crud_y_redirecciones(monkeypatch):
    from zascarr.services.arcos import DetalleArco, ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None,
                           is_crossover=False)
    detalle = DetalleArco(str(arco.id), "Saga", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.crear_arco", AsyncMock(
                return_value=ResultadoArco(True, arco=arco))):
            r = c.post("/ui/arcos/nueva", data={"title": "Saga"},
                       follow_redirects=False)
        assert r.status_code == 303 and str(arco.id) in r.headers["location"]
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            assert c.get(f"/ui/arcos/{arco.id}/editar").status_code == 200
            assert c.get(f"/ui/arcos/{arco.id}/eliminar").status_code == 200
        with patch("zascarr.web.arcos.agregar_numero", AsyncMock(
                return_value=ResultadoArco(True, arco=arco))):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batman", "numero": "1"},
                       follow_redirects=False)
        assert r.status_code == 303
    finally:
        _cerrar()


def test_c4_fuente_de_guia_valida_host_esquema_y_rutas():
    """SecOps c-4: la fuente se valida con la allowlist/validación del extractor."""
    from zascarr.web.arcos import fuente_de_guia

    buena = ("https://comicbookreadingorders.com/dc/events/"
             "crisis-on-infinite-earths-reading-order/")
    assert fuente_de_guia({"origen": "reading_orders", "url": buena}) is not None
    assert fuente_de_guia({"origen": "continuity_guide",
                           "url": "https://www.continuityguide.net/planetx"}) is not None
    assert fuente_de_guia({"origen": "reading_orders",
                           "url": "https://evil.example/dc/events/x-reading-order/"}) is None
    assert fuente_de_guia({"origen": "continuity_guide",
                           "url": "https://www.continuityguide.net/%2e%2e/x"}) is None
    assert fuente_de_guia({"origen": "continuity_guide",
                           "url": "https://www.continuityguide.net/planetx?format=json"}) is None
    con_credenciales = ("https://user:pass@comicbookreadingorders.com"
                        "/dc/events/x-reading-order/")
    assert fuente_de_guia({"origen": "reading_orders",
                           "url": con_credenciales}) is None
    assert fuente_de_guia({"origen": "fandom_dc",
                           "url": "https://dc.fandom.com/wiki/Batman"}) is None


# ── «Añadir un número» desde la ficha de la saga (task-24) ───────────────────────────────────

def _detalle_minimo(arco_id="a1"):
    return DetalleArco(arco_id, "Court of Owls", None, False, [], 0)


def test_detalle_ofrece_formulario_para_anadir_numero():
    detalle = _detalle_minimo()
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Añadir un número" in r.text
    assert 'action="/ui/arcos/a1/numeros"' in r.text
    for campo in ('name="serie"', 'name="numero"', 'name="orden"'):
        assert campo in r.text
    assert 'maxlength="500"' in r.text and 'maxlength="20"' in r.text
    assert "Tal como aparece en tu biblioteca" in r.text
    assert "Vacía = al final" in r.text
    # Acción secundaria: botón neutro, nunca `.primary`.
    assert '<button type="submit" class="btn ghost">Añadir número</button>' in r.text


def test_detalle_conserva_las_acciones_existentes():
    filas = [FilaArco(1, "i1", "s1", "Batman", "1", None, None, True)]
    detalle = DetalleArco("a1", "Court of Owls", None, False, filas, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    for texto in ("Editar la saga", "Eliminar la saga", "Subir una posición",
                  "Bajar una posición", "Quitar de la saga", "Añadir un número"):
        assert texto in r.text


def test_anadir_numero_valido_redirige_con_guardado_numero():
    from zascarr.services.arcos import ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None, is_crossover=False)
    agregar = AsyncMock(return_value=ResultadoArco(True, arco=arco))
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.agregar_numero", agregar):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batman", "numero": "1"},
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303
    assert r.headers["location"] == f"/ui/arcos/{arco.id}?guardado=numero"
    assert agregar.await_args.kwargs == {"serie": "Batman", "numero": "1", "orden": None}


def test_anadir_numero_con_posicion_la_pasa_al_servicio():
    from zascarr.services.arcos import ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None, is_crossover=False)
    agregar = AsyncMock(return_value=ResultadoArco(True, arco=arco))
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.agregar_numero", agregar):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batman", "numero": "1", "orden": "2"},
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303
    assert agregar.await_args.kwargs["orden"] == 2


def test_anadir_numero_con_posicion_no_numerica_va_al_final():
    from zascarr.services.arcos import ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None, is_crossover=False)
    agregar = AsyncMock(return_value=ResultadoArco(True, arco=arco))
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.agregar_numero", agregar):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batman", "numero": "1", "orden": "al-final"},
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and agregar.await_args.kwargs["orden"] is None


def test_anadir_numero_invalido_rerenderiza_aviso_y_conserva_valores():
    from zascarr.services.arcos import ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None, is_crossover=False)
    errores = {"serie": "No encuentro una única serie con ese nombre. "
                        "Escribe el título exacto."}
    agregar = AsyncMock(return_value=ResultadoArco(False, errores=errores))
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.agregar_numero", agregar), \
                patch("zascarr.web.arcos.detalle_arco",
                      AsyncMock(return_value=_detalle_minimo(str(arco.id)))):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batmanx", "numero": "7", "orden": "2"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "No encuentro una única serie con ese nombre." in r.text
    assert 'value="Batmanx"' in r.text
    assert 'value="7"' in r.text and 'value="2"' in r.text
    assert 'class="campo-error"' in r.text


def test_anadir_numero_error_general_del_servicio_usa_aviso_neutro():
    from zascarr.services.arcos import ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None, is_crossover=False)
    agregar = AsyncMock(return_value=ResultadoArco(
        False, errores={"general": "La saga ya no existe."}))
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.agregar_numero", agregar), \
                patch("zascarr.web.arcos.detalle_arco",
                      AsyncMock(return_value=_detalle_minimo(str(arco.id)))):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batman", "numero": "1"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "La saga ya no existe." in r.text and 'class="aviso' in r.text


def test_pedir_saga_muestra_boton_y_redirige_con_recuento():
    aid = str(uuid4())
    filas = [
        FilaArco(1, "i1", "s1", "Batman", "1", None, None, True),
        FilaArco(2, "i2", "s2", "Nightwing", "2", None, None, False),
    ]
    detalle = DetalleArco(aid, "Court of Owls", None, True, filas, 2)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{aid}")
        assert "Pedir los números que faltan" in r.text
        assert "al wishlist" not in r.text.lower()
        with patch("zascarr.web.arcos.pedir_arco", AsyncMock(
                return_value=ResultadoPedidoArco(True, anadidos=1, ya_pedidos=0,
                                                 en_biblioteca=1, total=2))):
            r = c.post(f"/ui/arcos/{aid}/pedir", follow_redirects=False)
        assert r.status_code == 303
        assert "guardado=pedido" in r.headers["location"]
        assert "anadidos=1" in r.headers["location"]
    finally:
        _cerrar()


def test_pedir_saga_sin_nuevos_muestra_aviso_neutro():
    aid = str(uuid4())
    detalle = DetalleArco(aid, "Court of Owls", None, True, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{aid}", params={
                "guardado": "pedido", "anadidos": "0", "ya_pedidos": "2",
                "en_biblioteca": "1"})
    finally:
        _cerrar()
    assert "No había números nuevos que pedir" in r.text
    assert "a tus deseados" not in r.text
    assert "autofocus" in r.text

# ── SCR5: «Novedades de Comic Book Herald» al final de Sagas en orden ─────────────────────

def _pagina_vacia():
    return PaginaArcos([], 1, 1, 0, 0, 1)


def test_la_pagina_de_sagas_no_pide_el_feed(monkeypatch):
    """#854 A: el GET de Sagas no puede hacer red para el feed de Herald."""
    def _no_debe_llamarse(*_a, **_k):
        raise AssertionError("el GET de Sagas no debe pedir el feed")

    monkeypatch.setattr("zascarr.web.arcos._novedades_de_herald", _no_debe_llamarse)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=_pagina_vacia())):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200


def test_el_marcado_de_novedades_es_perezoso():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=_pagina_vacia())):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'hx-get="/ui/arcos/novedades-herald"' in r.text
    assert 'hx-trigger="revealed once"' in r.text
    assert 'id="novedades-herald-contenido"' in r.text
    assert 'aria-live="polite"' in r.text
    assert 'id="novedades-herald-cargando"' in r.text
    assert 'class="novedades-esqueleto"' in r.text
    assert 'class="esqueleto-fila"' in r.text
    assert 'hx-indicator="#novedades-herald-cargando"' in r.text


def _novedades() -> list:
    from datetime import UTC, datetime

    from zascarr.services.comicbook_herald import HeraldItem

    return [
        HeraldItem("Año Uno de Batman: por dónde empezar",
                   "https://www.comicbookherald.com/batman-year-one-reading-order/",
                   datetime(2026, 11, 8, 9, 0, tzinfo=UTC)),
        HeraldItem("La Patrulla-X de Claremont",
                   "https://www.comicbookherald.com/x-men-claremont-reading-order/", None),
    ]


def test_el_parcial_de_novedades_pinta_los_items():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos._novedades_de_herald",
                   AsyncMock(return_value=_novedades())):
            r = c.get("/ui/arcos/novedades-herald")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert "Novedades de Comic Book Herald" in r.text
    assert 'href="https://www.comicbookherald.com/batman-year-one-reading-order/"' in r.text
    assert 'target="_blank"' in r.text and 'rel="noopener noreferrer"' in r.text
    assert "se abre en otra pestaña" in r.text and "08/11/2026" in r.text
    assert 'class="novedades-lista"' in r.text


def test_el_parcial_sin_novedades_devuelve_vacio():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos._novedades_de_herald", AsyncMock(return_value=[])):
            r = c.get("/ui/arcos/novedades-herald")
    finally:
        _cerrar()
    assert r.status_code == 200 and "Novedades de Comic Book Herald" not in r.text
    assert "<ul" not in r.text and "<section" not in r.text


def test_el_parcial_con_la_fuente_apagada_no_hace_red(monkeypatch):
    modulo = __import__("zascarr.web.arcos", fromlist=["arcos"])
    monkeypatch.setattr(modulo, "fuente_habilitada", lambda *_a, **_k: False)
    monkeypatch.setattr(modulo, "ComicBookHeraldClient", None)
    c = _cliente()
    try:
        r = c.get("/ui/arcos/novedades-herald")
    finally:
        _cerrar()
    assert r.status_code == 200 and "Novedades" not in r.text


def test_el_parcial_ante_un_fallo_devuelve_200_vacio(monkeypatch):
    class ClienteQueFalla:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def novedades(self):
            raise RuntimeError("sin red")

    modulo = __import__("zascarr.web.arcos", fromlist=["arcos"])
    monkeypatch.setattr(modulo, "fuente_habilitada", lambda *_a, **_k: True)
    monkeypatch.setattr(modulo, "ComicBookHeraldClient", ClienteQueFalla)
    c = _cliente()
    try:
        r = c.get("/ui/arcos/novedades-herald")
    finally:
        _cerrar()
    assert r.status_code == 200 and "Novedades" not in r.text


async def test_la_fuente_apagada_no_instancia_el_cliente_del_feed(monkeypatch):
    from zascarr.web import arcos as modulo

    monkeypatch.setattr(modulo, "fuente_habilitada", lambda *_a, **_k: False)
    monkeypatch.setattr(modulo, "ComicBookHeraldClient", None)   # si se usara, reventaría
    assert await modulo._novedades_de_herald() == []


async def test_un_fallo_del_feed_no_pinta_nada_y_no_lanza(monkeypatch):
    from zascarr.web import arcos as modulo

    class ClienteQueFalla:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def novedades(self):
            raise RuntimeError("sin red")

    monkeypatch.setattr(modulo, "fuente_habilitada", lambda *_a, **_k: True)
    monkeypatch.setattr(modulo, "ComicBookHeraldClient", ClienteQueFalla)
    assert await modulo._novedades_de_herald() == []



# ── SCR2 m-2: aviso CC-BY-SA en el listado cuando hay arcos de Fandom ─────────────────────

def test_el_listado_avisa_de_la_licencia_si_hay_arcos_de_fandom():
    pagina = PaginaArcos(
        [ArcoResumen("a1", "Year One", False, 2, 1, origen="fandom_dc")],
        1, 1, 1, 0, 1, hay_fandom=True)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=pagina)), \
                patch("zascarr.web.arcos._novedades_de_herald", AsyncMock(return_value=[])):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "DC/Marvel Database" in r.text and "BY-SA 3.0" in r.text
    assert 'href="https://creativecommons.org/licenses/by-sa/3.0/"' in r.text
    assert 'rel="noopener noreferrer"' in r.text
    assert 'href="/legal"' in r.text
    # Sin cambiar el orden de la lista.
    assert r.text.index("Year One") < r.text.index("DC/Marvel Database")


def test_sin_arcos_de_fandom_no_se_pinta_el_aviso():
    pagina = PaginaArcos([ArcoResumen("a1", "Saga manual", False, 1, 1)], 1, 1, 1, 0, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=pagina)), \
                patch("zascarr.web.arcos._novedades_de_herald", AsyncMock(return_value=[])):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200 and "DC/Marvel Database" not in r.text


class _FakeFandom:
    def __init__(self, *_a, **_k):
        self.search = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def search_pages(self, _consulta, limit=8):
        return self.search


def test_busqueda_en_fuentes_renderiza_resultados_y_enlace_previa():
    from zascarr.services.fandom import FandomSearchPage
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.fuente_habilitada", return_value=True), \
             patch("zascarr.web.arcos.FandomClient", _FakeFandom), \
             patch.object(_FakeFandom, "search_pages", AsyncMock(
                 return_value=[FandomSearchPage("Batman: Year One", "Un arco")])):
            r = c.get("/ui/arcos/buscar?q=Batman")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Batman: Year One" in r.text
    assert "/ui/arcos/buscar/preview?page_title=" in r.text


def test_preview_renderiza_coincidencias_y_confirmacion():
    from zascarr.services.arcos_fuentes import FilaArcoFandom, PreviaArcoFandom
    previa = PreviaArcoFandom("Batman: Year One", "Batman: Year One", [
        FilaArcoFandom("p", "Batman Vol 1", "404", "s1", "Batman", "i1", True),
        FilaArcoFandom("p2", "Batman Vol 1", "405", faltan=True),
    ], 1, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.fuente_habilitada", return_value=True), \
             patch("zascarr.web.arcos.FandomClient", _FakeFandom), \
             patch("zascarr.web.arcos.previsualizar_arco_fandom",
                   AsyncMock(return_value=previa)):
            r = c.get("/ui/arcos/buscar/preview?page_title=Batman%3A+Year+One")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Batman #404" in r.text and "No está en tu biblioteca" in r.text
    assert 'name="confirmo"' in r.text and "crear o actualizar" in r.text
    assert "dc.fandom.com/wiki/Batman:_Year_One" in r.text


def test_importar_redirige_con_guardado_importada():
    from zascarr.services.arcos_fuentes import (
        PreviaArcoFandom,
        ResultadoImportacionArco,
    )
    arco_id = uuid4()
    previa = PreviaArcoFandom("Batman: Year One", "Batman: Year One", [], 0, 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.fuente_habilitada", return_value=True), \
             patch("zascarr.web.arcos.FandomClient", _FakeFandom), \
             patch("zascarr.web.arcos.previsualizar_arco_fandom",
                   AsyncMock(return_value=previa)), \
             patch("zascarr.web.arcos.importar_arco_fandom", AsyncMock(
                 return_value=ResultadoImportacionArco(str(arco_id), 1, 0, 2))):
            r = c.post("/ui/arcos/buscar/importar", data={
                "page_title": "Batman: Year One", "confirmo": "1"},
                follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303
    assert r.headers["location"] == f"/ui/arcos/{arco_id}?guardado=importada"


def test_fuente_apagada_no_hace_red_ni_500():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.fuente_habilitada", return_value=False):
            r = c.get("/ui/arcos/buscar?q=Batman")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "está apagada" in r.text


def test_aviso_importada_al_volver_al_arco():
    detalle = DetalleArco("a1", "Year One", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}?guardado=importada")
    finally:
        _cerrar()
    assert r.status_code == 200 and "importada desde Fandom" in r.text


def test_importar_sin_confirmacion_conserva_la_previa():
    from zascarr.services.arcos_fuentes import FilaArcoFandom, PreviaArcoFandom
    previa = PreviaArcoFandom("Batman: Year One", "Batman: Year One", [
        FilaArcoFandom("p", "Batman Vol 1", "404", faltan=True),
    ], 0, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.fuente_habilitada", return_value=True), \
             patch("zascarr.web.arcos.FandomClient", _FakeFandom), \
             patch("zascarr.web.arcos.previsualizar_arco_fandom",
                   AsyncMock(return_value=previa)), \
             patch("zascarr.web.arcos.importar_arco_fandom", AsyncMock()) as importar:
            r = c.post("/ui/arcos/buscar/importar", data={
                "page_title": "Batman: Year One"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Marca la confirmación" in r.text
    assert "Batman Vol 1 #404" in r.text
    importar.assert_not_awaited()


def test_portada_de_saga_redirige_a_la_portada_local_del_numero():
    arco_id = uuid4()
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.primera_portada_de_arco",
                   AsyncMock(return_value=("s1", "i1"))):
            r = c.get(f"/ui/arcos/{arco_id}/portada.jpg", follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 307
    assert r.headers["location"] == "/ui/series/s1/numero/i1/portada.jpg"
    assert "http://" not in r.headers["location"] and "https://" not in r.headers["location"]


def test_portada_de_saga_sin_miembros_responde_404_sin_cache():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.primera_portada_de_arco", AsyncMock(return_value=None)):
            r = c.get(f"/ui/arcos/{uuid4()}/portada.jpg", follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"


# --- UXA-17 (#1134): vacío, apagada, espera y fallo con salida propia y un solo principal ---

def _buscar(*, activa=True, buscar=None):
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.fuente_habilitada", return_value=activa), \
             patch("zascarr.web.arcos.FandomClient", _FakeFandom), \
             patch("zascarr.web.arcos.buscar_arcos_fandom", buscar or AsyncMock(return_value=[])):
            return c.get("/ui/arcos/buscar?q=Batman").text
    finally:
        _cerrar()


def _principales(html: str) -> int:
    import re
    return len(re.findall(r'class="btn primary"', html))


def test_uxa17_apagada_lleva_a_ajustes_sin_formulario_de_busqueda():
    html = _buscar(activa=False)
    assert "/ui/ajustes#ajustes-metadatos" in html and "<form" not in html.split("<main")[-1]
    assert _principales(html) == 1 and "crear una saga a mano" in html


def test_uxa17_vacio_no_culpa_a_la_fuente_y_ofrece_crear_o_importar():
    html = _buscar()
    assert "La fuente funciona" in html and "apagada" not in html
    assert "/ui/arcos/nueva" in html and "/ui/arcos/importar-guia" in html
    assert _principales(html) == 1


def test_uxa17_espera_se_distingue_del_fallo():
    from zascarr.utils.cortesia import CortesiaEnEspera
    espera = _buscar(buscar=AsyncMock(side_effect=CortesiaEnEspera("fandom", "dc", 9.0)))
    fallo = _buscar(buscar=AsyncMock(side_effect=RuntimeError("x")))
    assert "espaciar las consultas" in espera and "no ha respondido" not in espera
    assert "no ha respondido" in fallo and "espaciar" not in fallo
    for html in (espera, fallo):
        assert "Volver a buscar" in html and _principales(html) == 1
        assert "crear una saga a mano" in html


def test_uxa17_con_resultados_no_aparece_ningun_aviso_de_fallo():
    from zascarr.services.fandom import FandomSearchPage
    html = _buscar(buscar=AsyncMock(return_value=[FandomSearchPage("Batman: Year One", "x")]))
    assert "Batman: Year One" in html and "no ha respondido" not in html
