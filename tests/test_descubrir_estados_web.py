# ruff: noqa: E501
"""U14 (#201) — Descubrir: ver que la búsqueda avanza y leer resultados limpios. Casos 1–7 de la ficha
`docs/design/benchmark-U14-descubrir-estados.md`; la verificación en NAVEGADOR (caso 8) está en `docs/design/ui-u14/`.

Sin base de datos ni red: el servicio de búsqueda se sustituye por una `Busqueda` ya calculada (el estado de cada fuente
lo prueba `tests/test_discovery_estados.py`); aquí se prueba lo que la WEB hace con ese estado.

Invariantes:
  · «Ningún resultado» NO se dice cuando TODAS las fuentes consultadas fallaron;
  · «las demás sí respondieron» solo se dice de las que dieron `ok`;
  · una fuente apagada o sin clave no es un fallo y no se mezcla con ellos;
  · el HTML de la fuente nunca se interpreta: se convierte a texto;
  · hay UNA sola región viva y se anuncia UNA vez por búsqueda.
"""
from __future__ import annotations

import html
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_web_css_contraste import _reglas
from tests.test_web_discovery import FakeSession, _resultado, use_fake_session
from zascarr.models import MetadataSource
from zascarr.services.discovery import (
    FUENTE_APAGADA,
    FUENTE_ERROR,
    FUENTE_OK,
    FUENTE_SIN_CLAVE,
    Busqueda,
)
from zascarr.web import descubrir_texto as dt

SECRETO = "secreto-de-prueba-para-firmar"
OK, ERR, OFF, SINCLAVE = FUENTE_OK, FUENTE_ERROR, FUENTE_APAGADA, FUENTE_SIN_CLAVE


def estados(cv=OK, al=OK, te=OK, gcd=OK) -> dict[str, str]:
    return {"comic_vine": cv, "anilist": al, "tebeosfera": te, "gcd": gcd}


def visible(t: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())


@pytest.fixture
def web(monkeypatch):
    import zascarr.web.discovery as w

    def ajustes(**kw):
        base = dict(secret_key=SECRETO, comicvine_enabled=True, comicvine_api_key="k", anilist_enabled=True,
                    tebeosfera_enabled=True, gcd_enabled=True)
        monkeypatch.setattr(w, "get_settings", lambda: SimpleNamespace(**{**base, **kw}))
    ajustes()
    return ajustes


def buscar(busqueda: Busqueda) -> str:
    with use_fake_session(FakeSession()) as client, \
         patch("zascarr.web.discovery.DiscoveryService.search_detallada", AsyncMock(return_value=busqueda)):
        r = client.get("/ui/descubrir/buscar", params={"q": "Mortadelo"})
    assert r.status_code == 200
    return r.text


# ── 3. Texto limpio ───────────────────────────────────────────────────────────────────────────
class TestTextoPlano:

    @pytest.mark.parametrize("crudo,esperado", [
        ("<p>Mortadelo <a href='/x'>Bruguera</a> &amp; Filemón</p><script>x()</script>", "Mortadelo Bruguera & Filemón"),
        ("<p>Uno.</p><p>Dos.</p>", "Uno. Dos."),
        ("Línea<br>siguiente<br/>y otra", "Línea siguiente y otra"),
        ("<style>p{color:red}</style>Texto", "Texto"),
        ("&lt;b&gt;no es una etiqueta&lt;/b&gt;", "<b>no es una etiqueta</b>"),
        ("  mucho \n\n  espacio\t\t ", "mucho espacio"),
        ("<ul><li>a</li><li>b</li></ul>", "a b"),
        ("Sin etiquetas", "Sin etiquetas"),
        ("", ""), (None, ""),
    ])
    def test_el_html_de_la_fuente_se_convierte_en_texto(self, crudo, esperado):
        assert dt.texto_plano(crudo) == esperado

    def test_un_html_roto_no_revienta_ni_deja_etiquetas(self):
        assert dt.texto_plano("<p>abierto <b>sin cerrar <a href=") == "abierto sin cerrar"   # etiqueta cortada: se descarta
        assert dt.texto_plano("<div><span>x</div>") == "x"
        assert dt.texto_plano("a < b y c > d") == "a < b y c > d"          # un «<» suelto NO es una etiqueta

    def test_la_tarjeta_muestra_la_descripcion_como_texto_plano(self, web):
        b = Busqueda([_resultado(description="<p>Mortadelo <a href='/e'>Bruguera</a> &amp; Filemón</p><script>x()</script>")],
                     [], estados())
        t = buscar(b)
        desc = re.search(r'<div class="discovery-card-desc">(.*?)</div>', t, re.S).group(1)
        assert html.unescape(desc).strip() == "Mortadelo Bruguera & Filemón"
        assert "&lt;p&gt;" not in t and "&lt;a href" not in t and "<script" not in t

    def test_una_descripcion_vacia_tras_limpiar_no_pinta_el_bloque(self, web):
        t = buscar(Busqueda([_resultado(description="<p> </p><br>")], [], estados()))
        assert "discovery-card-desc" not in t


# ── 4. Fuente legible ─────────────────────────────────────────────────────────────────────────
class TestFuenteLegible:

    @pytest.mark.parametrize("valor,etiqueta", [("comic_vine", "Comic Vine"), ("anilist", "AniList"),
                                                ("tebeosfera", "Tebeosfera"), ("gcd", "GCD")])
    def test_la_etiqueta_en_llano(self, valor, etiqueta):
        assert dt.etiqueta_fuente(valor) == etiqueta

    def test_un_valor_desconocido_no_enseña_su_identificador(self):
        assert dt.etiqueta_fuente("fuente_nueva_x") == "otra fuente"

    def test_cada_fuente_de_busqueda_tiene_etiqueta(self):
        from zascarr.services.discovery import ORDEN_DE_FUENTES
        assert all(dt.etiqueta_fuente(f.value) != "otra fuente" for f in ORDEN_DE_FUENTES)

    def test_la_tarjeta_dice_el_nombre_y_no_el_identificador(self, web):
        t = buscar(Busqueda([_resultado(source=MetadataSource.COMIC_VINE)], [], estados()))
        v = visible(t)
        assert "Comic Vine" in v
        assert "comic_vine" not in v.lower() and not re.search(r"\b[a-z]+_[a-z_]+\b", v)


# ── 7. Errores por fuente, en llano ───────────────────────────────────────────────────────────
class TestErroresPorFuente:

    def test_una_fuente_caida_dice_cual_y_que_las_demas_si_respondieron(self):
        r = dt.resumir(estados(cv=ERR), 4)
        assert r.avisos == ["No respondió Comic Vine. Los resultados de AniList, Tebeosfera y GCD sí se han consultado."]

    def test_dos_caidas_se_enumeran_y_el_verbo_concuerda(self):
        r = dt.resumir(estados(cv=ERR, gcd=ERR), 2)
        assert r.avisos == ["No respondieron Comic Vine y GCD. Los resultados de AniList y Tebeosfera sí se han consultado."]

    def test_tres_caidas_y_una_sola_que_responde(self):
        r = dt.resumir(estados(cv=ERR, al=ERR, te=ERR), 1)
        assert r.avisos == ["No respondieron Comic Vine, AniList y Tebeosfera. El resultado de GCD sí se ha consultado."]

    def test_si_todas_fallan_no_se_dice_que_no_hay_coincidencias(self, web):
        b = Busqueda([], ["x"], estados(cv=ERR, al=ERR, te=ERR, gcd=ERR))
        r = dt.resumir(b.fuentes, 0)
        assert "ninguna fuente" in r.avisos[0].lower() and "Ningún resultado" not in r.anuncio
        assert r.anuncio == r.avisos[0], "el anuncio no repite la misma frase dos veces"
        v = visible(buscar(b))
        assert "Sin coincidencias" not in v and "No respondió ninguna fuente" in v

    def test_apagada_y_sin_clave_no_son_fallos(self):
        r = dt.resumir(estados(cv=SINCLAVE, al=OFF, te=OK, gcd=OK), 3)
        assert not any("No respondi" in a for a in r.avisos)
        assert r.avisos == ["Comic Vine no está configurado: añade su clave en Ajustes para incluirlo en la búsqueda."]
        assert "AniList" not in " ".join(r.avisos)

    def test_un_fallo_y_una_fuente_sin_clave_se_dicen_los_dos(self):
        r = dt.resumir(estados(cv=SINCLAVE, al=ERR, te=OK, gcd=OK), 1)
        assert len(r.avisos) == 2 and "No respondió AniList" in r.avisos[0] and "Comic Vine no está configurado" in r.avisos[1]
        assert "Los resultados de Tebeosfera y GCD sí se han consultado" in r.avisos[0]

    def test_todo_apagado_lo_dice_en_vez_de_sin_coincidencias(self):
        r = dt.resumir(estados(cv=OFF, al=OFF, te=OFF, gcd=OFF), 0)
        assert "ninguna fuente activa" in " ".join(r.avisos).lower() and "Ningún resultado" not in r.anuncio
        assert r.anuncio == r.avisos[0]

    def test_ningun_aviso_lleva_codigos_internos(self):
        for e in (estados(cv=ERR), estados(cv=SINCLAVE), estados(cv=ERR, al=ERR, te=ERR, gcd=ERR), estados(cv=OFF, al=OFF, te=OFF, gcd=OFF)):
            for a in dt.resumir(e, 0).avisos + [dt.resumir(e, 0).anuncio]:
                assert not re.search(r"COMIC_VINE|comic_vine|\.env|API_KEY|Traceback|Exception|Error\b", a), a

    def test_el_aviso_de_la_pantalla_no_es_el_texto_antiguo_del_servicio(self, web):
        """La web explica el estado ella misma; los avisos del servicio (con `.env`) ya no se pintan."""
        b = Busqueda([], ["Comic Vine no está configurado — añade COMICVINE_API_KEY en tu .env para incluirlo en la búsqueda."],
                     estados(cv=SINCLAVE))
        t = buscar(b)
        assert "COMICVINE_API_KEY" not in t and ".env" not in t and "Ajustes" in visible(t)

    def test_los_resultados_de_las_fuentes_que_si_respondieron_se_muestran(self, web):
        b = Busqueda([_resultado(source=MetadataSource.ANILIST, title="Naruto")], ["x"], estados(cv=ERR))
        v = visible(buscar(b))
        assert "Naruto" in v and "No respondió Comic Vine" in v


# ── 2. Resultado anunciado ────────────────────────────────────────────────────────────────────
class TestResultadoAnunciado:

    @pytest.mark.parametrize("n,esperado", [(0, "Ningún resultado."), (1, "1 resultado."), (3, "3 resultados.")])
    def test_el_recuento_en_el_anuncio(self, n, esperado):
        assert dt.resumir(estados(), n).anuncio.startswith(esperado)

    def test_el_anuncio_incluye_el_fallo(self):
        a = dt.resumir(estados(cv=ERR), 2).anuncio
        assert a.startswith("2 resultados.") and "No respondió Comic Vine" in a

    def test_la_pagina_tiene_una_region_viva_fuera_del_destino(self, web):
        with use_fake_session(FakeSession()) as client:
            t = client.get("/ui/descubrir").text
        regiones = re.findall(r'<div id="descubrir-estado"[^>]*>', t)
        assert len(regiones) == 1
        assert 'aria-live="polite"' in regiones[0] and 'aria-atomic="true"' in regiones[0]
        assert 'class="region-viva sr"' in regiones[0]               # solo para el lector: no duplica lo que se ve
        assert len(re.findall(r'aria-live=|role="status"|role="alert"', t.split("<main", 1)[-1])) == 1
        destino = re.search(r'<div id="resultados-descubrir"[^>]*>(.*?)</div>', t, re.S).group(1)
        assert "aria-live" not in destino                       # la región NO es el destino: no se lee la lista entera

    def test_la_respuesta_actualiza_la_region_por_hx_swap_oob_y_no_trae_otra(self, web):
        t = buscar(Busqueda([_resultado(), _resultado(external_id="2", title="Superman")], [], estados()))
        oob = re.findall(r'<div id="descubrir-estado"[^>]*>(.*?)</div>', t, re.S)
        assert len(oob) == 1 and "2 resultados." in visible(oob[0])
        etiqueta = re.search(r'<div id="descubrir-estado"[^>]*>', t).group(0)
        assert 'hx-swap-oob="true"' in etiqueta and 'aria-live="polite"' in etiqueta and 'aria-atomic="true"' in etiqueta
        assert 'class="region-viva sr"' in etiqueta
        # el recuento VISIBLE existe y no se lee dos veces (el lector ya tiene la región)
        assert re.search(r'<p class="discovery-count" aria-hidden="true">2 resultados</p>', t)
        resto = re.sub(r'<div id="descubrir-estado".*?</div>', "", t, flags=re.S)
        assert not re.search(r'aria-live=|role="status"|role="alert"', resto), "se anunciaría dos veces"

    def test_la_region_de_la_respuesta_es_la_misma_que_la_de_la_pagina(self, web):
        with use_fake_session(FakeSession()) as client:
            pagina = re.search(r'<div id="descubrir-estado"[^>]*>', client.get("/ui/descubrir").text).group(0)
        resp = re.search(r'<div id="descubrir-estado"[^>]*>', buscar(Busqueda([_resultado()], [], estados()))).group(0)
        quitar = lambda s: re.sub(r'\s*hx-swap-oob="true"', "", s)           # noqa: E731
        assert quitar(resp) == quitar(pagina)


# ── 1. Progreso visible ───────────────────────────────────────────────────────────────────────
class TestProgreso:

    def _pagina(self) -> str:
        with use_fake_session(FakeSession()) as client:
            return client.get("/ui/descubrir").text

    def test_el_indicador_nombra_las_fuentes_que_se_consultan(self, web):
        t = self._pagina()
        m = re.search(r'<p id="buscando-descubrir"([^>]*)>(.*?)</p>', t, re.S)
        assert m, "falta el indicador"
        assert visible(m.group(2)) == "Buscando en Comic Vine, AniList, Tebeosfera y GCD…"
        assert 'class="htmx-indicator indicador-diferido"' in m.group(1)

    def test_el_campo_lo_enlaza_con_hx_indicator(self, web):
        campo = re.search(r'<input type="search"[^>]*>', self._pagina(), re.S).group(0)
        assert 'hx-indicator="#buscando-descubrir"' in campo

    @pytest.mark.parametrize("kw,texto", [
        (dict(gcd_enabled=False), "Buscando en Comic Vine, AniList y Tebeosfera…"),
        (dict(comicvine_api_key=""), "Buscando en AniList, Tebeosfera y GCD…"),       # encendida pero sin clave: no se consulta
        (dict(comicvine_enabled=False, tebeosfera_enabled=False, gcd_enabled=False), "Buscando en AniList…"),
        (dict(anilist_enabled=False, tebeosfera_enabled=False, gcd_enabled=False), "Buscando en Comic Vine…"),
    ])
    def test_solo_se_nombran_las_fuentes_encendidas(self, web, kw, texto):
        web(**kw)
        assert texto in visible(self._pagina())

    def test_sin_ninguna_fuente_no_hay_indicador_y_se_dice(self, web):
        web(comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False, gcd_enabled=False)
        t = self._pagina()
        assert "buscando-descubrir" not in t and "ninguna fuente activa" in visible(t).lower()

    def test_el_indicador_se_oculta_a_los_lectores_y_aparece_con_retardo_en_la_hoja(self, web):
        t = self._pagina()
        assert 'aria-hidden="true"' in re.search(r'<p id="buscando-descubrir"([^>]*)>', t).group(1)
        base = next(d for s, d in _reglas() if s.strip() == ".htmx-indicator.indicador-diferido")
        assert base.get("transition") == "none"                    # al terminar, desaparece sin retardo
        activo = next(d for s, d in _reglas() if s.strip() == ".htmx-indicator.indicador-diferido.htmx-request")
        tr = activo["transition"]
        assert re.search(r"opacity 0s linear \.4s", tr) and re.search(r"visibility 0s linear \.4s", tr), tr


# ── 6. Enlace externo y 5. controles del sistema ──────────────────────────────────────────────
class TestEnlaceYControles:

    def test_el_enlace_dice_adonde_lleva_y_que_abre_otra_pestana(self, web):
        t = buscar(Busqueda([_resultado(title="Batman", source=MetadataSource.COMIC_VINE)], [], estados()))
        a = re.search(r'<a href="https://comicvine[^"]*"[^>]*>.*?</a>', t, re.S).group(0)
        assert 'aria-label="Ver la ficha de «Batman» en Comic Vine (se abre en otra pestaña)"' in a
        assert 'rel="noopener noreferrer"' in a and 'target="_blank"' in a
        assert '<span aria-hidden="true">↗</span>' in a

    def test_el_select_de_tradicion_tiene_estilo_del_sistema_y_no_el_nativo(self):
        reglas = [d for s, d in _reglas() if s.strip() == ".discovery-card-actions select"]
        assert reglas, "el selector de tradición no tiene regla propia: sale el control nativo"
        d = reglas[0]
        assert d.get("background") == "var(--paper)" and d.get("color") == "var(--ink)"
        assert d.get("border") == "2px solid var(--ink)" and "min-height" in d and float(d["min-height"][:-2]) >= 40

    def test_el_select_conserva_su_nombre_accesible_y_no_viene_preseleccionado(self, web):
        t = buscar(Busqueda([_resultado()], [], estados()))
        sel = re.search(r'<select name="tradition" required aria-label="Tradición">', t)
        assert sel and '<option value="" selected disabled>' in t


def test_la_ruta_sigue_respondiendo_sin_resultados_ni_avisos(web):
    with use_fake_session(FakeSession()) as client, \
         patch("zascarr.web.discovery.DiscoveryService.search_detallada", AsyncMock(return_value=Busqueda([], [], estados()))):
        r = client.get("/ui/descubrir/buscar", params={"q": "zzz"})
    v = visible(r.text)
    assert r.status_code == 200 and "Sin coincidencias en Comic Vine, AniList, Tebeosfera y GCD." in v
