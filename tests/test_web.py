"""
tests/test_web.py

Suite del esqueleto de la UI web (ADR 0001): router /ui, layout base,
HTMX vendorizado. Usa TestClient SIN entrar como context manager: así no
dispara el lifespan de la app real, que exige una conexión a PostgreSQL
que este entorno de tests no tiene — confirmado empíricamente antes de
escribir estos tests, no solo supuesto.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path, PurePosixPath

from fastapi.testclient import TestClient

from zascarr.main import STATIC_DIR, app

RAIZ = Path(__file__).resolve().parents[1]

# Cliente a nivel de módulo (fuera del alcance del conftest, que solo parchea
# TestClient durante cada test): se le dan el Host y el Origin que el
# middleware de seguridad espera, igual que hace el conftest por defecto.
client = TestClient(app, base_url="http://localhost", headers={"Origin": "http://localhost"})


class TestStaticAssets:

    def test_htmx_vendorizado_se_sirve_y_es_la_version_esperada(self):
        r = client.get("/static/vendor/htmx.min.js")
        assert r.status_code == 200
        assert 'this.version="4.0.0"' in r.text

    def test_css_de_la_ui_se_sirve(self):
        r = client.get("/static/web.css")
        assert r.status_code == 200

    def test_cada_font_face_apunta_a_un_woff2_que_se_sirve(self):
        """Una ruta de @font-face rota no da error visible: el navegador cae en silencio a
        Impact o a la fuente del sistema y en Android los titulares pierden la rotulación."""
        css = client.get("/static/web.css").text
        rutas = re.findall(r'url\("(/static/vendor/fonts/[^"]+\.woff2)"\)', css)
        assert len(rutas) == 3, rutas
        for ruta in rutas:
            r = client.get(ruta)
            assert r.status_code == 200, ruta
            assert r.content[:4] == b"wOF2", ruta

    def test_el_paquete_instalado_incluye_todo_static(self):
        """Mismo mecanismo que el bug de dashboard.html (E1): un fichero de `static/` que no
        casa con `package-data` existe en el árbol pero no en la imagen de Docker. Los README
        son para quien mantiene el repo y no viajan."""
        patrones = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"]["setuptools"]["package-data"]["zascarr"]
        paquete = STATIC_DIR.parent
        for fichero in STATIC_DIR.rglob("*"):
            if fichero.is_dir() or fichero.suffix == ".md":
                continue
            relativa = PurePosixPath(fichero.relative_to(paquete).as_posix())
            # Como setuptools, «*» no cruza carpetas: mismo número de tramos y cada tramo casa.
            assert any(len(relativa.parts) == len(PurePosixPath(p).parts) and relativa.match(p)
                       for p in patrones), relativa

    def test_cada_recurso_de_la_marca_se_sirve(self):
        """El logo va como fondo CSS y los favicons en el <head>: una ruta rota no da error
        visible, solo un hueco donde debería ir el estallido."""
        css = client.get("/static/web.css").text
        cabeza = (STATIC_DIR.parent / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        rutas = set(re.findall(r'url\("(/static/brand/[^"]+)"\)', css))
        rutas |= set(re.findall(r'href="(/static/brand/[^"]+)"', cabeza))
        assert len(rutas) == 4, rutas
        for ruta in rutas:
            assert client.get(ruta).status_code == 200, ruta

    def test_estado_e1_sigue_funcionando_tras_montar_static_y_ui(self):
        r = client.get("/estado")
        assert r.status_code == 200
        assert "ZascArr" in r.text

    def test_raiz_redirige_a_la_biblioteca(self):
        """Bug real (reportado): "/" mandaba a Estado en vez de a la
        biblioteca, sin forma de volver. Ahora "/" es solo un redirect."""
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/ui/"
