"""La actualización desde Estado se anuncia, pero aún no se puede ejecutar."""
from __future__ import annotations

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.web import estado


class SectionParser(HTMLParser):
    """Recoge solo la sección de actualización y sus atributos."""

    def __init__(self) -> None:
        super().__init__()
        self.inside = False
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "section" and values.get("id") == "actualizacion":
            self.inside = True
        if self.inside:
            self.elements.append((tag, values))

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self.inside:
            self.inside = False

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.text.append(data)


@pytest.mark.parametrize("version", ["disponible", "actualizada", "comprobando", "desconocida"])
def test_actualizacion_siempre_visible_inerte_y_accesible(monkeypatch, version: str) -> None:
    monkeypatch.setattr(estado.aviso_version, "estado", lambda: version)

    class FakeSession:
        async def execute(self, _):
            raise RuntimeError("sin BD")

        async def rollback(self):
            pass

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            response = client.get("/estado")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    parser = SectionParser()
    parser.feed(response.text)
    elements = parser.elements
    assert elements[0][1]["aria-labelledby"] == "actualizacion-titulo"
    assert any(attrs.get("id") == "actualizacion-titulo" for _, attrs in elements)
    assert "no está disponible" in " ".join(parser.text)
    assert "No se instalará nada" in " ".join(parser.text)
    buttons = [attrs for tag, attrs in elements if tag == "button"]
    assert len(buttons) == 1
    assert "disabled" in buttons[0] and buttons[0].get("type") == "button"
    assert buttons[0].get("aria-describedby") == "actualizacion-no-disponible"
    assert any(attrs.get("id") == "actualizacion-no-disponible" for _, attrs in elements)
    assert not any(tag in {"form", "script", "a"} for tag, _ in elements)
    assert not any(key.startswith(("hx-", "on")) or key in {"form", "formaction"}
                   for _, attrs in elements for key in attrs)
    assert 'id="version-aviso" aria-live="polite"' in response.text
