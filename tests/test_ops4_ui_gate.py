"""Estado actual de #443: el aviso de versión no ejecuta actualizaciones.

Estas pruebas no certifican el comportamiento de una futura implementación.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Match

from zascarr.database import get_db
from zascarr.main import app
from zascarr.web import estado


class _AccionesVersion(HTMLParser):
    """Recoge controles y destinos interactivos dentro de la sección de versión."""

    def __init__(self) -> None:
        super().__init__()
        self.en_version = False
        self.acciones: list[tuple[str, dict]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = dict(attrs)
        if tag == "section" and atributos.get("id") == "version":
            self.en_version = True
        if self.en_version and (tag in {"form", "button", "input", "a"}
                                or any(k.startswith("hx-") or k.startswith("on")
                                       for k in atributos)):
            self.acciones.append((tag, atributos))

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self.en_version:
            self.en_version = False


@pytest.fixture
def cliente(monkeypatch):
    class FakeSession:
        async def execute(self, _):
            raise RuntimeError("sin BD")

        async def rollback(self):
            pass

    async def fake_db():
        yield FakeSession()

    async def fake_copias(**_kwargs):
        return {"copias_error": True}

    monkeypatch.setattr(estado.aviso_version, "estado", lambda: "disponible")
    monkeypatch.setattr(estado, "contexto_copias", fake_copias)
    monkeypatch.setitem(app.dependency_overrides, get_db, fake_db)
    # Sin lifespan: no arranca tareas, base de datos ni clientes de red.
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def test_estado_avisa_version_disponible_sin_accion(cliente):
    respuesta = cliente.get("/estado")
    assert respuesta.status_code == 200
    assert 'id="version"' in respuesta.text
    assert "Hay una versión nueva" in respuesta.text
    parser = _AccionesVersion()
    parser.feed(respuesta.text)
    assert parser.acciones == []
    aviso = cliente.get("/ui/version/estado")
    assert aviso.status_code == 200
    assert aviso.json() == {"estado": "disponible"}


@pytest.mark.parametrize("ruta", ["/ui/version/estado", "/ui/version/actualizar",
                                   "/ui/actualizar", "/actualizar"])
def test_post_actualizacion_no_resuelve_ruta_ejecutable(cliente, ruta):
    # Match.FULL detecta también rutas parametrizadas, no solo igualdad de strings.
    # Se comprueba el enrutado: un middleware puede devolver 503 antes del 404.
    scope = {"type": "http", "method": "POST", "path": ruta, "root_path": ""}
    assert not [route for route in app.router.routes if route.matches(scope)[0] == Match.FULL]
