"""#1035: favorito en tarjetas y ficha."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app


class _Db:
    def __init__(self, serie):
        self.serie = serie

    async def get(self, _modelo, _id):
        return self.serie

    async def flush(self):
        return None

    async def commit(self):
        return None


def _cliente(favorite=False):
    serie = SimpleNamespace(id=uuid4(), favorite=favorite, title="Las aventuras de Batman")
    async def _db():
        yield _Db(serie)
    app.dependency_overrides[get_db] = _db
    return TestClient(app), serie


def test_hx_devuelve_fragmento_y_alterna():
    cliente, serie = _cliente()
    try:
        r = cliente.post(f"/ui/series/{serie.id}/favorito",
                         headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'aria-pressed="true"' in r.text and "<svg" in r.text
        assert "Quitar de favoritas" in r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_sin_hx_sigue_redirigiendo():
    cliente, serie = _cliente()
    try:
        r = cliente.post(f"/ui/series/{serie.id}/favorito", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/ui/series/")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_tarjeta_y_ficha_incluyen_boton():
    from pathlib import Path
    rejilla = Path("src/zascarr/web/templates/_rejilla_biblioteca.html").read_text()
    ficha = Path("src/zascarr/web/templates/series_detail.html").read_text()
    frag = Path("src/zascarr/web/templates/_favorito_boton.html").read_text()
    assert 'include "_favorito_boton.html"' in rejilla and "library-card-wrap" in rejilla
    assert 'include "_favorito_boton.html"' in ficha
    assert "hx-post" in frag and "aria-pressed" in frag and "favorito-btn" in frag


def test_hx_ficha_texto_visible_y_tarjeta_compacta():
    cliente, serie = _cliente()
    try:
        ficha = cliente.post(f"/ui/series/{serie.id}/favorito",
                             data={"origen": "ficha", "favorito-ficha": "1"},
                             headers={"HX-Request": "true"})
        assert "Quitar de favoritas" in ficha.text
        assert "favorito-btn-ficha" in ficha.text
        assert 'class="sr"' not in ficha.text
        tarjeta = cliente.post(f"/ui/series/{serie.id}/favorito",
                               headers={"HX-Request": "true"})
        assert '<span class="sr">' in tarjeta.text
        assert "aria-pressed" in tarjeta.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_css_favorito_44_y_sin_tapar_titulo():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text()
    assert ".favorito-btn" in css and "width: 44px" in css and "height: 44px" in css
    assert ".library-card-wrap .favorito-form" in css and "position: absolute" in css
    assert "top: var(--space-2)" in css
    # En la ficha es una acción más de la fila: botón neutro de 40 px (44 en táctil, regla general).
    assert ".favorito-btn-ficha {\n  width: auto; height: auto; min-height: 40px;" in css
    assert "white-space: nowrap" in css


def test_el_boton_tiene_id_estable_para_que_htmx_devuelva_el_foco():
    """#1122: htmx 4 solo restaura el foco tras un `outerHTML` a un elemento enfocado CON `id`;
    sin él, tras pulsar Favorito con el teclado el foco caía en `<body>` (medido en navegador)."""
    cliente, serie = _cliente()
    try:
        for cabeceras in ({}, {"origen": "ficha", "favorito-ficha": "1"}):
            r = cliente.post(f"/ui/series/{serie.id}/favorito", data=cabeceras,
                             headers={"HX-Request": "true"})
            assert f'<button type="submit" id="favorito-{serie.id}"' in r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_el_cambio_se_anuncia_en_una_region_viva_que_ya_estaba_en_la_pagina():
    """#1122: el anuncio llega por intercambio fuera de banda al CONTENIDO de una región `status`
    estable (una región insertada ya con su texto no se anuncia de forma fiable)."""
    from pathlib import Path
    cliente, serie = _cliente()
    try:
        marcada = cliente.post(f"/ui/series/{serie.id}/favorito", headers={"HX-Request": "true"})
        assert ('<div id="anuncio-favorito" hx-swap-oob="innerHTML">'
                'Marcada como favorita: Las aventuras de Batman</div>') in marcada.text
        quitada = cliente.post(f"/ui/series/{serie.id}/favorito", headers={"HX-Request": "true"})
        assert "Quitada de favoritas: Las aventuras de Batman" in quitada.text
    finally:
        app.dependency_overrides.pop(get_db, None)
    plantillas = Path("src/zascarr/web/templates")
    region = ('<div id="anuncio-favorito" class="sr" role="status" aria-live="polite" '
              'aria-atomic="true"></div>')
    biblioteca = (plantillas / "biblioteca.html").read_text()
    ficha = (plantillas / "series_detail.html").read_text()
    assert region in ficha
    # Fuera de `#rejilla` (que se sustituye entera al filtrar): si no, el anuncio se perdería.
    assert region in biblioteca
    assert biblioteca.index(region) < biblioteca.index('<div id="rejilla">')
    assert 'id="anuncio-favorito"' not in (plantillas / "_rejilla_biblioteca.html").read_text()


def test_quitar_de_la_coleccion_empieza_por_su_texto_visible_y_lleva_el_titulo():
    """#1122 (WCAG 2.5.3): el nombre accesible contiene el texto visible, al principio, y añade
    el título para distinguir filas. «Quitar X de la colección» no contenía el texto visible."""
    import re
    from pathlib import Path
    html = Path("src/zascarr/web/templates/coleccion_detalle.html").read_text()
    botones = re.findall(r'<button[^>]*aria-label="([^"]*)"[^>]*>([^<]*)</button>', html)
    quitar = [(n, v.strip()) for n, v in botones if v.strip().startswith("Quitar")]
    assert {v for _, v in quitar} == {"Quitar de la colección", "Quitar serie"}
    for nombre, visible in quitar:
        assert nombre.startswith(visible + ": ") and "{{ s.title }}" in nombre, nombre
