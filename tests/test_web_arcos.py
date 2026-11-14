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
        assert "Pedir los números que faltan (1)" in r.text
        with patch("zascarr.web.arcos.pedir_arco", AsyncMock(
                return_value=ResultadoPedidoArco(True, anadidos=1, ya_pedidos=0,
                                                 en_biblioteca=1, total=2))):
            r = c.post(f"/ui/arcos/{aid}/pedir", follow_redirects=False)
        assert r.status_code == 303
        assert "guardado=pedido" in r.headers["location"]
        assert "anadidos=1" in r.headers["location"]
    finally:
        _cerrar()
