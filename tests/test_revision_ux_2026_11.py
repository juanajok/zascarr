"""Revisión de UI/UX de 2026-11-12 contra el sistema de diseño: una regresión por hallazgo.

Cada prueba lleva el nombre del mecanismo que falló al revisar la app con una biblioteca de prueba
(22 CBZ, Chromium a 1280 y 375 px).
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from zascarr.main import app
from zascarr.models import MetadataSource
from zascarr.services.registro_biblioteca import EstadoRegistro, FaseRegistro
from zascarr.web import discovery
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1] / "src" / "zascarr"
PLANTILLAS = RAIZ / "web" / "templates"
CSS = (RAIZ / "static" / "web.css").read_text(encoding="utf-8")


def _regla(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no hay regla para {selector}"
    return " ".join(m.group(1).split())


def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


class TestLasBusquedasRespondenAlEscribirNoSoloAlSoltarUnaTecla:
    """`keyup` no salta al pegar con el ratón, al elegir un autocompletado ni con algunos
    teclados del móvil: la búsqueda se quedaba muda. `input` salta con cualquier forma de
    escribir."""

    def test_ninguna_busqueda_depende_solo_de_keyup(self):
        malas = []
        for p in sorted(PLANTILLAS.glob("*.html")):
            for disparo in re.findall(r'hx-trigger="([^"]*)"', p.read_text(encoding="utf-8")):
                if "keyup" in disparo and "input" not in disparo:
                    malas.append(f"{p.name}: {disparo}")
        assert not malas, "búsquedas que solo responden a keyup:\n  " + "\n  ".join(malas)

    def test_la_busqueda_de_por_revisar_usa_input(self):
        t = (PLANTILLAS / "_tarjeta_pendiente.html").read_text(encoding="utf-8")
        assert 'hx-trigger="input changed delay:400ms, search"' in t


class TestUnSoloBotonPrincipalEnDuplicados:
    """Con la biblioteca sin registrar salían tres amarillos a la vez: revisar, registrar y
    reescanear. El principal es el que hace avanzar la tarea del Inicio (registrar); los otros dos
    son neutros."""

    def test_revisar_y_reescanear_son_neutros(self):
        botones = {
            "auditoria.html": r"<button[^>]*>\s*Revisar mi biblioteca",
            "_rescan_biblioteca.html": r'<button[^>]*aria-describedby="rescan-aviso"[^>]*>',
        }
        for nombre, patron in botones.items():
            boton = re.search(patron, (PLANTILLAS / nombre).read_text(encoding="utf-8"))
            assert boton, nombre
            assert "primary" not in boton.group(0), f"{nombre}: {boton.group(0)}"


class TestElResumenDelRegistroNoCuentaCeros:
    """«0 con serie sugerida (falta confirmar…)» explicaba algo que no había pasado; y
    «1 repetidos»."""

    def _render(self, **kw) -> str:
        reg = EstadoRegistro(fase=FaseRegistro.TERMINADO, total=22, procesados=22, **kw)
        return _texto(crear_templates().get_template("_auditoria_registro.html").render(reg=reg))

    def test_sin_series_sugeridas_no_se_nombran(self):
        t = self._render(sin_identificar=21, repetidos=1)
        assert "con serie sugerida" not in t
        assert "21 sin identificar" in t

    def test_un_repetido_va_en_singular(self):
        t = self._render(sin_identificar=21, repetidos=1)
        assert "1 repetido (" in t and "1 repetidos" not in t

    def test_con_series_sugeridas_se_siguen_explicando(self):
        t = self._render(registrados=3, sin_identificar=2, repetidos=2)
        assert "3 con serie sugerida" in t and "no están clasificados" in t
        assert "2 repetidos" in t


class TestSinFuentesCrearAManoEsElCamino:
    """Con todas las fuentes apagadas (lo que trae una instalación nueva, ADR 0013) la única forma
    de dar de alta una serie estaba plegada al final de la página, y «Ajustes» no era un enlace."""

    def test_el_alta_a_mano_se_enseña_abierta_y_ajustes_es_un_enlace(self, monkeypatch):
        monkeypatch.setattr(discovery, "fuentes_que_se_consultan", lambda _settings: [])
        r = TestClient(app).get("/ui/descubrir")
        assert r.status_code == 200 and "No hay ninguna fuente activa" in r.text
        assert '<details class="alta-a-mano" open>' in r.text
        assert '<a href="/ui/ajustes">Ajustes</a>' in r.text

    def test_con_alguna_fuente_el_alta_a_mano_sigue_plegada(self, monkeypatch):
        monkeypatch.setattr(discovery, "fuentes_que_se_consultan",
                            lambda _settings: [MetadataSource.COMIC_VINE])
        r = TestClient(app).get("/ui/descubrir")
        assert '<details class="alta-a-mano">' in r.text


class TestLaMaquetacionNoSeRompe:
    def test_la_ficha_pone_los_datos_al_lado_de_la_portada(self):
        """Sin base propia, el bloque de datos bajaba debajo de la portada incluso a 1280 px."""
        regla = _regla(".series-header > div")
        assert "flex: 1 1 20rem" in regla and "min-width: 0" in regla

    def test_la_ficha_no_lleva_estilos_en_linea(self):
        ficha = (PLANTILLAS / "series_detail.html").read_text(encoding="utf-8")
        assert 'style="display:inline"' not in ficha
        assert "display: inline" in _regla(".anio-titulo")

    def test_ignorar_va_al_pie_de_la_tarjeta(self):
        assert "margin-top: auto" in _regla(".pending-body > .btn-ignorar")
        assert "flex: 1" in _regla(".pending-body")

    def test_el_especial_sin_numero_no_se_sale_de_la_tarjeta(self):
        regla = _regla(".especial-input")
        assert "width: 100%" in regla and "min-width: 0" in regla

    def test_las_otras_formas_de_revisar_van_en_una_fila(self):
        t = (PLANTILLAS / "pendientes.html").read_text(encoding="utf-8")
        assert '<div class="acciones-fila" role="group" aria-label="Otras formas de revisar">' in t
        assert "flex-wrap: wrap" in _regla(".acciones-fila")
