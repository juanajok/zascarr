"""BL-R7 (#236): pantalla de vistas de trabajo (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.vistas_trabajo import FilaVista, PaginaVista, ResumenVista
from zascarr.web import vistas_trabajo as web


def _cliente():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def _resumen():
    return [
        ResumenVista("sin-identificar", "Sin identificar", "Archivos sin publicación.",
                     "/ui/vistas/sin-identificar", 4),
        ResumenVista("dudosas", "Identificación dudosa", "Identificación no segura.",
                     "/ui/vistas/dudosas", 2),
        ResumenVista("discrepancias", "Con discrepancias", "Propuesta distinta pendiente.",
                     "/ui/vistas/discrepancias", 0),
        ResumenVista("no-disponibles", "No disponibles", "No se encuentran en su ruta.",
                     "/ui/no-disponibles", 1),
        ResumenVista("variantes", "Con varias variantes", "Varios contenidos del mismo número.",
                     "/ui/vistas/variantes", 3),
    ]


def _pagina(clave="sin-identificar", filas=None, total=1):
    filas = filas or [FilaVista("Superman #1.cbz", "Sin serie asignada", "CBZ", 1024,
                                "/ui/pendientes")]
    paginas = max(1, (total + 49) // 50)
    return PaginaVista(clave, "Sin identificar", "Archivos sin publicación.", filas, total,
                       1, paginas, 0, len(filas))


def test_hub_muestra_las_cinco_vistas_con_recuentos():
    c = _cliente()
    try:
        with patch.object(web, "resumen_de_vistas", AsyncMock(return_value=_resumen())):
            r = c.get("/ui/vistas")
    finally:
        _cerrar()
    assert r.status_code == 200
    for titulo in ("Sin identificar", "Identificación dudosa", "Con discrepancias",
                   "No disponibles", "Con varias variantes"):
        assert titulo in r.text
    assert "4" in r.text and "/ui/vistas/variantes" in r.text and "/ui/no-disponibles" in r.text


def test_una_vista_lista_filas_y_pagina():
    c = _cliente()
    try:
        with patch.object(web, "listar_vista",
                          AsyncMock(return_value=_pagina(total=51))):
            r = c.get("/ui/vistas/sin-identificar")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Superman #1.cbz" in r.text and "Sin serie asignada" in r.text
    assert "mostrando 1–1" in r.text          # una sola fila en esta página
    assert "Página 1 de 2" in r.text


def test_una_vista_sin_resultados_no_parece_un_error():
    c = _cliente()
    try:
        with patch.object(web, "listar_vista",
                          AsyncMock(return_value=_pagina(filas=[], total=0))):
            r = c.get("/ui/vistas/dudosas")
    finally:
        _cerrar()
    assert r.status_code == 200 and "No hay nada en esta vista" in r.text


def test_no_disponibles_redirige_a_su_pantalla():
    c = _cliente()
    try:
        r = c.get("/ui/vistas/no-disponibles", follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and r.headers["location"] == "/ui/no-disponibles"


def test_una_clave_desconocida_da_404():
    c = _cliente()
    try:
        r = c.get("/ui/vistas/lo-que-sea")
    finally:
        _cerrar()
    assert r.status_code == 404
