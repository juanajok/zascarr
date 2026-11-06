# ruff: noqa: E501
"""U14 (#201) + MIT-M8-US01 (#133) — Descubrir: ver que la búsqueda avanza y leer resultados limpios, con el
estado CERRADO de cada fuente y capacidad.

Sin base de datos ni red: el servicio de búsqueda se sustituye por una `Busqueda` ya calculada (los estados y su
clasificación los prueba `tests/test_discovery_estados.py`); aquí se prueba lo que la WEB hace con ellos.

Invariantes:
  · «Ningún resultado» NO se dice cuando todas las fuentes fallaron; solo si alguna respondió sin coincidencias;
  · «las demás sí respondieron» solo se dice de las que respondieron;
  · apagada, sin configurar y límite de cortesía no son fallos y no se mezclan con ellos;
  · el motivo lo escribe el servicio; el reintento solo aparece si el contrato lo trae;
  · una capacidad no verificada no se presenta como disponible;
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
    CAPACIDAD_BUSQUEDA,
    ESTADOS_DE_FUENTE,
    FUENTE_APAGADA,
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
    Busqueda,
    EstadoFuente,
)
from zascarr.web import descubrir_texto as dt

SECRETO = "secreto-de-prueba-para-firmar"
OK, SIN, FALLO, CONFIG, LIMITE, OFF = (
    FUENTE_OK, FUENTE_SIN_RESULTADOS, FUENTE_FALLO_TRANSITORIO,
    FUENTE_CONFIGURACION_INCOMPLETA, FUENTE_LIMITE_DE_CORTESIA, FUENTE_APAGADA)

MOTIVOS = {
    FUENTE_APAGADA: "Está apagada en Ajustes.",
    FUENTE_CONFIGURACION_INCOMPLETA: "Falta su clave en Ajustes.",
    FUENTE_FALLO_TRANSITORIO: "No ha respondido ahora mismo.",
    FUENTE_LIMITE_DE_CORTESIA: "Ha pedido esperar antes de volver a consultarla.",
    FUENTE_SIN_RESULTADOS: "Ha respondido, pero no hay coincidencias.",
}


def estados(cv=OK, al=OK, te=OK, gcd=OK) -> dict[str, str]:
    return {"comic_vine": cv, "anilist": al, "tebeosfera": te, "gcd": gcd}


def detalles(estados_: dict[str, str], reintentos: dict[str, int] | None = None) -> dict[str, EstadoFuente]:
    return {nombre: EstadoFuente(fuente=nombre, capacidad=CAPACIDAD_BUSQUEDA, estado=estado,
                                 motivo=MOTIVOS.get(estado),
                                 reintentar_en=(reintentos or {}).get(nombre))
            for nombre, estado in estados_.items()}


def busqueda(resultados, *, avisos=(), estados_: dict[str, str] | None = None,
             reintentos: dict[str, int] | None = None) -> Busqueda:
    e = estados_ if estados_ is not None else estados()
    return Busqueda(resultados, list(avisos), dict(e), detalles(e, reintentos))


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


def buscar(b: Busqueda) -> str:
    with use_fake_session(FakeSession()) as client, \
         patch("zascarr.web.discovery.DiscoveryService.search_detallada", AsyncMock(return_value=b)):
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
        b = busqueda([_resultado(description="<p>Mortadelo <a href='/e'>Bruguera</a> &amp; Filemón</p><script>x()</script>")])
        t = buscar(b)
        desc = re.search(r'<div class="discovery-card-desc">(.*?)</div>', t, re.S).group(1)
        assert html.unescape(desc).strip() == "Mortadelo Bruguera & Filemón"
        assert "&lt;p&gt;" not in t and "&lt;a href" not in t and "<script" not in t

    def test_una_descripcion_vacia_tras_limpiar_no_pinta_el_bloque(self, web):
        t = buscar(busqueda([_resultado(description="<p> </p><br>")]))
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
        t = buscar(busqueda([_resultado(source=MetadataSource.COMIC_VINE)]))
        v = visible(t)
        assert "Comic Vine" in v
        assert "comic_vine" not in v.lower() and not re.search(r"\b[a-z]+_[a-z_]+\b", v)


# ── 1. Estado por fuente y capacidad (#133) ──────────────────────────────────────────────────

class TestEstadoPorFuente:

    def test_el_estado_visible_usa_el_conjunto_cerrado(self):
        assert set(dt.ESTADOS_VISIBLES) == ESTADOS_DE_FUENTE

    def test_se_muestra_fuente_capacidad_estado_y_motivo(self, web):
        b = busqueda([], estados_=estados(cv=OK, al=LIMITE, te=CONFIG, gcd=OFF),
                     reintentos={"anilist": 30})
        v = visible(buscar(b))
        assert "Comic Vine · búsqueda: ha respondido" in v
        assert "AniList · búsqueda: ha pedido esperar" in v
        assert "Tebeosfera · búsqueda: sin configurar" in v
        assert "GCD · búsqueda: apagada en Ajustes" in v
        assert "Ha pedido esperar antes de volver a consultarla." in v
        assert "Falta su clave en Ajustes." in v
        assert "Está apagada en Ajustes." in v
        assert "Puedes reintentar en 30 s." in v

    def test_el_reintento_solo_se_pinta_si_el_contrato_lo_trae(self, web):
        sin_plazo = visible(buscar(busqueda([], estados_=estados(al=LIMITE))))
        con_plazo = visible(buscar(busqueda([], estados_=estados(al=LIMITE), reintentos={"anilist": 15})))
        assert "Puedes reintentar" not in sin_plazo
        assert "Puedes reintentar en 15 s." in con_plazo

    def test_una_fuente_apagada_no_se_presenta_como_un_fallo(self, web):
        v = visible(buscar(busqueda([], estados_=estados(gcd=OFF))))
        assert "GCD · búsqueda: apagada en Ajustes" in v
        assert "No respondió GCD" not in v and "No han respondido" not in v

    def test_una_capacidad_no_verificada_no_se_presenta_como_disponible(self):
        assert dt.etiqueta_capacidad(CAPACIDAD_BUSQUEDA) == "búsqueda"
        assert dt.etiqueta_capacidad("metadatos") == "capacidad no verificada"
        visibles = dt.detalles_visibles({"comic_vine": EstadoFuente(
            fuente="comic_vine", capacidad="metadatos", estado=OK)})
        assert visibles[0].capacidad == "capacidad no verificada"
        assert visibles[0].capacidad != "disponible"


# ── 7. Errores por fuente, en llano y sin mezclar ────────────────────────────────────────────
class TestErroresPorFuente:

    def test_una_fuente_caida_dice_cual_y_que_las_demas_si_respondieron(self):
        r = dt.resumir(estados(cv=FALLO), 4, detalles(estados(cv=FALLO)))
        assert r.avisos == ["No respondió Comic Vine. Los resultados de AniList, Tebeosfera y GCD sí se han consultado."]

    def test_dos_caidas_se_enumeran_y_el_verbo_concuerda(self):
        r = dt.resumir(estados(cv=FALLO, gcd=FALLO), 2, detalles(estados(cv=FALLO, gcd=FALLO)))
        assert r.avisos == ["No respondieron Comic Vine y GCD. Los resultados de AniList y Tebeosfera sí se han consultado."]

    def test_tres_caidas_y_una_sola_que_responde(self):
        r = dt.resumir(estados(cv=FALLO, al=FALLO, te=FALLO), 1, detalles(estados(cv=FALLO, al=FALLO, te=FALLO)))
        assert r.avisos == ["No respondieron Comic Vine, AniList y Tebeosfera. El resultado de GCD sí se ha consultado."]

    def test_si_todas_fallan_no_se_dice_que_no_hay_coincidencias(self, web):
        e = estados(cv=FALLO, al=FALLO, te=FALLO, gcd=FALLO)
        r = dt.resumir(e, 0, detalles(e))
        assert "ninguna fuente" in r.avisos[0].lower() and "Ningún resultado" not in r.anuncio
        assert r.anuncio == r.avisos[0], "el anuncio no repite la misma frase dos veces"
        v = visible(buscar(busqueda([], estados_=e)))
        assert "Sin coincidencias" not in v and "No respondió ninguna fuente" in v

    def test_apagada_y_sin_configurar_no_son_fallos_y_se_dicen_aparte(self):
        e = estados(cv=CONFIG, al=OFF, te=OK, gcd=OK)
        r = dt.resumir(e, 3, detalles(e))
        assert not any("No respondi" in a for a in r.avisos)
        assert r.avisos == [
            "Comic Vine no está configurado: añade su clave en Ajustes para incluirlo en la búsqueda.",
            "Apagada en Ajustes: AniList.",
        ]

    def test_un_fallo_y_una_fuente_sin_configurar_se_dicen_los_dos(self):
        e = estados(cv=CONFIG, al=FALLO, te=OK, gcd=OK)
        r = dt.resumir(e, 1, detalles(e))
        assert len(r.avisos) == 2 and "No respondió AniList" in r.avisos[0] and "Comic Vine no está configurado" in r.avisos[1]
        assert "Los resultados de Tebeosfera y GCD sí se han consultado" in r.avisos[0]

    def test_el_limite_de_cortesia_es_aparte_y_solo_da_plazo_si_consta(self):
        e = estados(al=LIMITE, te=OK, gcd=OK)
        con = dt.resumir(e, 1, detalles(e, {"anilist": 20}))
        sin = dt.resumir(e, 1, detalles(e))
        assert con.avisos == ["AniList ha pedido esperar antes de volver a consultarla. Puedes reintentar en 20 s."]
        assert sin.avisos == ["AniList ha pedido esperar antes de volver a consultarla."]
        assert "No respondió" not in con.avisos[0]

    def test_todo_apagado_lo_dice_en_vez_de_sin_coincidencias(self):
        e = estados(cv=OFF, al=OFF, te=OFF, gcd=OFF)
        r = dt.resumir(e, 0, detalles(e))
        assert "ninguna fuente activa" in " ".join(r.avisos).lower() and "Ningún resultado" not in r.anuncio
        assert r.anuncio == r.avisos[0]

    def test_ningun_aviso_lleva_codigos_internos(self):
        for e in (estados(cv=FALLO), estados(cv=CONFIG), estados(al=LIMITE),
                  estados(cv=FALLO, al=FALLO, te=FALLO, gcd=FALLO),
                  estados(cv=OFF, al=OFF, te=OFF, gcd=OFF)):
            for a in dt.resumir(e, 0, detalles(e)).avisos + [dt.resumir(e, 0, detalles(e)).anuncio]:
                assert not re.search(r"COMIC_VINE|comic_vine|\.env|API_KEY|Traceback|Exception|Error\b", a), a

    def test_el_aviso_de_la_pantalla_no_es_el_texto_antiguo_del_servicio(self, web):
        """La web explica el estado ella misma; los avisos del servicio (con `.env`) ya no se pintan."""
        b = busqueda([], avisos=["Comic Vine no está configurado — añade COMICVINE_API_KEY en tu .env para incluirlo en la búsqueda."],
                     estados_=estados(cv=CONFIG))
        t = buscar(b)
        assert "COMICVINE_API_KEY" not in t and ".env" not in t and "Ajustes" in visible(t)

    def test_los_resultados_de_las_fuentes_que_si_respondieron_se_muestran(self, web):
        b = busqueda([_resultado(source=MetadataSource.ANILIST, title="Naruto")], estados_=estados(cv=FALLO))
        v = visible(buscar(b))
        assert "Naruto" in v and "No respondió Comic Vine" in v


# ── 2. Resultado anunciado ────────────────────────────────────────────────────────────────────
class TestResultadoAnunciado:

    @pytest.mark.parametrize("n,esperado", [(0, "Ningún resultado."), (1, "1 resultado."), (3, "3 resultados.")])
    def test_el_recuento_en_el_anuncio(self, n, esperado):
        e = estados(SIN, SIN, SIN, SIN) if n == 0 else estados()
        assert dt.resumir(e, n, detalles(e)).anuncio.startswith(esperado)

    def test_sin_resultados_de_una_fuente_que_respondio_si_permite_decirlo(self):
        e = estados(cv=SIN, al=FALLO, te=SIN, gcd=OFF)
        a = dt.resumir(e, 0, detalles(e)).anuncio
        assert a.startswith("Ningún resultado.") and "No respondió AniList" in a

    def test_el_anuncio_incluye_el_fallo(self):
        e = estados(cv=FALLO)
        a = dt.resumir(e, 2, detalles(e)).anuncio
        assert a.startswith("2 resultados.") and "No respondió Comic Vine" in a

    def test_la_pagina_tiene_una_region_viva_fuera_del_destino(self, web):
        with use_fake_session(FakeSession()) as client:
            t = client.get("/ui/descubrir").text
        regiones = re.findall(r'<div id="descubrir-estado"[^>]*>', t)
        assert len(regiones) == 1
        assert 'aria-live="polite"' in regiones[0] and 'aria-atomic="true"' in regiones[0]
        assert 'class="sr"' in regiones[0]               # solo para el lector: no duplica lo que se ve
        assert len(re.findall(r'aria-live=|role="status"|role="alert"', t.split("<main", 1)[-1])) == 1
        destino = re.search(r'<div id="resultados-descubrir"[^>]*>(.*?)</div>', t, re.S).group(1)
        assert "aria-live" not in destino                       # la región NO es el destino: no se lee la lista entera

    def test_la_respuesta_actualiza_el_contenido_de_la_region_y_no_la_sustituye(self, web):
        """Regresión del mecanismo (revisión de #217): `hx-swap-oob="true"` es `outerHTML` en htmx 4 y sustituiría el
        propio elemento. Tiene que ser `innerHTML`: se conserva el nodo y solo cambia lo que contiene."""
        t = buscar(busqueda([_resultado(), _resultado(external_id="2", title="Superman")]))
        etiquetas = re.findall(r'<div id="descubrir-estado"[^>]*>', t)
        assert len(etiquetas) == 1
        assert 'hx-swap-oob="innerHTML"' in etiquetas[0]
        assert 'hx-swap-oob="true"' not in etiquetas[0] and "outerHTML" not in etiquetas[0]
        oob = re.search(r'<div id="descubrir-estado"[^>]*>(.*?)</div>', t, re.S).group(1)
        assert "2 resultados." in visible(oob)
        # los atributos de la región viven SOLO en la página: la respuesta no puede traer una segunda región
        assert "aria-live" not in etiquetas[0] and "aria-atomic" not in etiquetas[0]
        # el recuento VISIBLE existe y no se lee dos veces (el lector ya tiene la región)
        assert re.search(r'<p class="discovery-count" aria-hidden="true">2 resultados</p>', t)
        resto = re.sub(r'<div id="descubrir-estado".*?</div>', "", t, flags=re.S)
        assert not re.search(r'aria-live=|role="status"|role="alert"', resto), "se anunciaría dos veces"

    def test_la_estrategia_de_la_region_viva_nunca_es_outer(self, web):
        """Para CUALQUIER resultado de la búsqueda (con resultados, sin coincidencias, todas fallan) la estrategia es
        `innerHTML`: la región de la página nunca se reemplaza."""
        casos = [busqueda([_resultado()]), busqueda([], estados_=estados(SIN, SIN, SIN, SIN)),
                 busqueda([], estados_=estados(FALLO, FALLO, FALLO, FALLO))]
        for b in casos:
            t = buscar(b)
            assert re.findall(r'hx-swap-oob="([^"]*)"', t) == ["innerHTML"]

    def test_la_region_de_la_pagina_es_unica_y_lleva_sus_atributos(self, web):
        with use_fake_session(FakeSession()) as client:
            t = client.get("/ui/descubrir").text
        etiqueta = re.search(r'<div id="descubrir-estado"[^>]*>', t).group(0)
        assert 'aria-live="polite"' in etiqueta and 'aria-atomic="true"' in etiqueta and 'class="sr"' in etiqueta
        assert "hx-swap-oob" not in etiqueta         # la página no es una respuesta fuera de banda


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

    def test_la_pagina_explica_los_estados_sin_jerga(self, web):
        v = visible(self._pagina())
        assert "¿Qué significa el estado de cada fuente?" in v
        assert "no es un fallo" in v and "tampoco significa que esté caída" in v
        assert "capacidad" not in v.lower() and "metadatos" not in v.lower()

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
        t = buscar(busqueda([_resultado(title="Batman", source=MetadataSource.COMIC_VINE)]))
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
        t = buscar(busqueda([_resultado()]))
        sel = re.search(r'<select name="tradition" required aria-label="Tradición">', t)
        assert sel and '<option value="" selected disabled>' in t


def test_la_ruta_sigue_respondiendo_sin_resultados_ni_avisos(web):
    e = estados(SIN, SIN, SIN, SIN)
    with use_fake_session(FakeSession()) as client, \
         patch("zascarr.web.discovery.DiscoveryService.search_detallada",
               AsyncMock(return_value=busqueda([], estados_=e))):
        r = client.get("/ui/descubrir/buscar", params={"q": "zzz"})
    v = visible(r.text)
    assert r.status_code == 200 and "Sin coincidencias en Comic Vine, AniList, Tebeosfera y GCD." in v


# ── #134 §6.5: aviso de espera por cortesía desde `limite_de_cortesia` (sin estado nuevo) ───

class TestAvisoDeCortesia:

    def test_si_no_se_consulto_ninguna_por_cortesia_manda_la_frase_agregada(self):
        e = estados(cv=LIMITE, al=LIMITE, te=LIMITE, gcd=LIMITE)
        r = dt.resumir(e, 0, detalles(e))
        assert r.anuncio.startswith(
            "Todavía no se ha consultado ninguna fuente: hay que esperar por cortesía.")
        assert "Ningún resultado" not in r.anuncio

    def test_la_ui_muestra_el_aviso_6_5_con_estimacion(self, web):
        b = busqueda([], estados_=estados(cv=OK, al=LIMITE, te=OK, gcd=OK))
        b.detalles["anilist"] = EstadoFuente(
            fuente="anilist", capacidad=CAPACIDAD_BUSQUEDA, estado=LIMITE,
            motivo=("No se ha consultado: hay que esperar ~12 s por cortesía. "
                    "No se ha enviado nada; vuelve a intentarlo en un momento."),
            reintentar_en=12)
        v = visible(buscar(b))
        assert "hay que esperar ~12 s por cortesía" in v
        assert "No se ha enviado nada; vuelve a intentarlo en un momento." in v
        assert "Puedes reintentar en 12 s." in v
        assert "No respondió" not in v
