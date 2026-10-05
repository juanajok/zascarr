"""
tests/test_web_navegacion.py

V3 (Épica V): menú agrupado, barra inferior en móvil y contadores por fragmento.

Lo que estas pruebas protegen, en orden de gravedad:
  1. Los enlaces están SIEMPRE en el marcado y ningún fragmento puede reemplazarlos o borrarlos.
  2. El fragmento de contadores responde `204` vacío ante cualquier fallo (BD caída con la app en
     marcha, arranque degradado, sesión caducada) y nunca sirve datos sin sesión.
  3. `/estado` se conserva como diagnóstico, también con el arranque degradado.
  4. Las URL no cambian; cada título y cada <h1> coinciden con su entrada de menú.
"""
from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import auth as servicio_auth
from zascarr.services.auth import (
    _RUTAS_DIAGNOSTICO,
    COOKIE_NAME,
    RUTAS_FRAGMENTO_SILENCIOSO,
    crear_cookie_sesion,
    hash_password,
)
from zascarr.services.review import ReviewService
from zascarr.services.wishlist import WishlistService
from zascarr.web.menu import ENTRADAS, GRUPOS, entrada_activa
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
FRAGMENTO = "/ui/_nav/estado"


# ── utilidades ────────────────────────────────────────────────────────────────────────────
class _Arbol(HTMLParser):
    """Árbol mínimo: (tag, attrs, padres) por elemento, para razonar sobre ascendientes."""

    VACIOS = {"br", "meta", "link", "input", "img", "hr"}

    def __init__(self) -> None:
        super().__init__()
        self.pila: list[tuple[str, dict]] = []
        self.elementos: list[tuple[str, dict, tuple]] = []
        self.texto_por_elemento: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.elementos.append((tag, a, tuple(self.pila)))
        if tag not in self.VACIOS:
            self.pila.append((tag, a))

    def handle_endtag(self, tag):
        for i in range(len(self.pila) - 1, -1, -1):
            if self.pila[i][0] == tag:
                del self.pila[i:]
                break


def arbol(html: str) -> _Arbol:
    a = _Arbol()
    a.feed(html)
    return a


def clases(attrs: dict) -> set[str]:
    return set((attrs.get("class") or "").split())


@pytest.fixture(scope="module")
def env():
    return crear_templates().env


def menu(env, ruta: str) -> str:
    return env.from_string("{{ ui.menu(ruta) }}").render(ruta=ruta)


# ── falsos de sesión de BD (el patrón del repo: dependency_overrides[get_db]) ──────────────
class _Resultado:
    def __init__(self, valor=0):
        self.valor = valor

    def scalar(self):
        return self.valor

    def scalar_one(self):
        return self.valor

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def unique(self):
        return self

    def mappings(self):
        return self

    def __iter__(self):
        return iter([])


class SesionFalsa:
    """Sesión que responde `escalares` en orden a cada `execute` (y 0 después), o lanza `error`."""

    def __init__(self, escalares=(), error: Exception | None = None,
                 congelada: asyncio.Event | None = None):
        self.escalares = list(escalares)
        self.error = error
        self.congelada = congelada
        self.consultas: list = []
        self.rollbacks = 0
        self.commits = 0

    async def execute(self, stmt, *a, **k):
        self.consultas.append(stmt)
        if self.congelada is not None:
            await self.congelada.wait()      # BD congelada: no contesta hasta que el test la libera
        if self.error:
            raise self.error
        return _Resultado(self.escalares.pop(0) if self.escalares else 0)

    async def get(self, *a, **k):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def close(self):
        pass

    def add(self, *a):
        pass

    async def flush(self):
        pass


class FabricaFalsa:
    """Sustituye a `async_session_factory`: puede fallar en CADA fase del ciclo de la sesión
    (crearla, abrirla, consultar, cerrarla) o tardar más que el plazo, y cuenta lo que ocurre."""

    def __init__(self, escalares=(), *, al_crear=None, al_abrir=None, en_consulta=None,
                 al_cerrar=None, demora: float = 0.0, congelada: bool = False):
        self.liberar = asyncio.Event()
        self.congelada = congelada
        self.sesion = SesionFalsa(escalares, error=en_consulta,
                                  congelada=self.liberar if congelada else None)
        self.al_crear, self.al_abrir = al_crear, al_abrir
        self.al_cerrar, self.demora = al_cerrar, demora
        self.creadas = self.abiertas = self.cerradas = 0

    def __call__(self):
        self.creadas += 1
        if self.al_crear:
            raise self.al_crear
        return self

    async def __aenter__(self):
        if self.demora:
            await asyncio.sleep(self.demora)
        if self.al_abrir:
            raise self.al_abrir
        self.abiertas += 1      # como en Python: si __aenter__ falla, __aexit__ no se llama
        return self.sesion

    async def __aexit__(self, tipo, exc, tb):
        if self.congelada:
            await self.liberar.wait()        # el rollback sobre la conexión congelada no vuelve
        self.cerradas += 1
        if self.al_cerrar:
            raise self.al_cerrar
        return False


@pytest.fixture
def con_fabrica(monkeypatch):
    """Contexto: `with con_fabrica(FabricaFalsa(...)) as client`; el fragmento abre su sesión."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx(fabrica):
        monkeypatch.setattr("zascarr.web.navegacion.async_session_factory", fabrica)
        yield TestClient(app, follow_redirects=False)
    return _ctx


@pytest.fixture
def con_sesion():
    """Contexto: `with con_sesion(SesionFalsa(...)) as client`."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx(sesion):
        async def _get_db():
            yield sesion

        app.dependency_overrides[get_db] = _get_db
        try:
            yield TestClient(app, follow_redirects=False)
        finally:
            app.dependency_overrides.pop(get_db, None)
    return _ctx


# ── 1. datos del menú ─────────────────────────────────────────────────────────────────────
URLS_DE_SIEMPRE = {
    "inicio": "/ui/", "revisar": "/ui/pendientes", "biblioteca": "/ui/biblioteca",
    "duplicados": "/ui/auditoria", "descubrir": "/ui/descubrir", "deseados": "/ui/wishlist",
    "estado": "/estado", "ajustes": "/ui/ajustes",
}
ETIQUETAS = {
    "inicio": "Inicio", "revisar": "Por revisar", "biblioteca": "Biblioteca",
    "duplicados": "Duplicados", "descubrir": "Descubrir", "deseados": "Deseados",
    "estado": "Estado", "ajustes": "Ajustes",
}


class TestDatosDelMenu:

    def test_las_url_no_cambian(self):
        """Decisión 2 de la épica: cambian las etiquetas, no las rutas; `/estado` no se mueve."""
        assert {e.clave: e.url for e in ENTRADAS} == URLS_DE_SIEMPRE

    def test_etiquetas_y_grupos_de_la_ficha(self):
        assert {e.clave: e.etiqueta for e in ENTRADAS} == ETIQUETAS
        assert GRUPOS == ("Mi colección", "Añadir", "Sistema")
        por_grupo = {g: [e.etiqueta for e in ENTRADAS if e.grupo == g] for g in GRUPOS}
        assert por_grupo == {
            "Mi colección": ["Inicio", "Por revisar", "Biblioteca", "Duplicados"],
            "Añadir": ["Descubrir", "Deseados"],
            "Sistema": ["Estado", "Ajustes"],
        }

    def test_cada_entrada_apunta_a_una_ruta_que_existe(self):
        from starlette.routing import Match

        for e in ENTRADAS:
            alcance = {"type": "http", "path": e.url, "method": "GET"}
            assert any(r.matches(alcance)[0] == Match.FULL for r in app.routes), e.url

    def test_la_barra_inferior_tiene_cuatro_entradas_y_mas_guarda_el_resto(self):
        principales = [e.clave for e in ENTRADAS if e.movil_principal]
        assert principales == ["inicio", "revisar", "deseados", "estado"]
        assert len([e for e in ENTRADAS if not e.movil_principal]) == 4

    def test_solo_las_entradas_principales_llevan_contador(self):
        """Las secundarias salen dos veces en el DOM (barra y «Más»): un `id` de contador duplicado
        sería HTML inválido y el fragmento actualizaría solo una."""
        assert {e.clave: e.contador for e in ENTRADAS if e.contador} == {
            "revisar": "pendientes", "deseados": "deseados", "estado": "estado"}
        assert all(e.movil_principal for e in ENTRADAS if e.contador)

    @pytest.mark.parametrize("ruta,clave", [
        ("/ui/", "inicio"), ("/ui", "inicio"), ("/ui/pendientes", "revisar"),
        ("/ui/pendientes/abc/portada", "revisar"), ("/ui/biblioteca", "biblioteca"),
        ("/ui/biblioteca?page=2", "biblioteca"), ("/ui/series/123", "biblioteca"),
        ("/ui/auditoria", "duplicados"), ("/ui/descubrir", "descubrir"),
        ("/ui/wishlist", "deseados"), ("/estado", "estado"), ("/ui/ajustes", "ajustes"),
    ])
    def test_entrada_activa(self, ruta, clave):
        assert entrada_activa(ruta) == clave

    @pytest.mark.parametrize("ruta", [
        "/ui/legal", "/legal", "/login", "/", "/api/health", "/ui/pendientes-otra-cosa", "", None])
    def test_sin_entrada_activa(self, ruta):
        assert entrada_activa(ruta) is None


# ── 2. el HTML del menú ───────────────────────────────────────────────────────────────────
class TestMenuHtml:

    def test_los_enlaces_de_cada_grupo_en_orden(self, env):
        a = arbol(menu(env, "/ui/"))
        grupos = [(at["aria-label"]) for t, at, _ in a.elementos if "nav-grupo" in clases(at)]
        assert grupos == list(GRUPOS)
        enlaces = [at["href"] for t, at, padres in a.elementos
                   if t == "a" and any("nav-grupo" in clases(p[1]) for p in padres)]
        assert enlaces == [e.url for e in ENTRADAS]

    def test_la_navegacion_tiene_nombre(self, env):
        nav = next(at for t, at, _ in arbol(menu(env, "/ui/")).elementos if t == "nav")
        assert nav["aria-label"] == "Navegación principal"

    @pytest.mark.parametrize("entrada", ENTRADAS, ids=[e.clave for e in ENTRADAS])
    def test_aria_current_en_la_entrada_activa(self, env, entrada):
        a = arbol(menu(env, entrada.url))
        actuales = [at["href"] for t, at, _ in a.elementos if at.get("aria-current") == "page"]
        # Las secundarias están dos veces (barra y panel «Más»); CSS muestra solo una por tamaño,
        # la oculta no existe para el lector de pantalla: en cada vista hay UNA.
        assert actuales == [entrada.url] * (1 if entrada.movil_principal else 2)

    def test_en_una_pagina_sin_entrada_no_hay_aria_current(self, env):
        assert "aria-current" not in menu(env, "/ui/legal")

    def test_mas_marca_cuando_la_pagina_actual_esta_dentro(self, env):
        assert "nav-mas-activa" in menu(env, "/ui/ajustes")
        assert "nav-mas-activa" not in menu(env, "/ui/pendientes")

    def test_el_panel_mas_tiene_exactamente_las_secundarias(self, env):
        a = arbol(menu(env, "/ui/"))
        en_panel = [at["href"] for t, at, padres in a.elementos
                    if t == "a" and any("nav-mas-panel" in clases(p[1]) for p in padres)]
        assert en_panel == [e.url for e in ENTRADAS if not e.movil_principal]

    def test_mas_es_un_details_nativo_sin_javascript(self, env):
        a = arbol(menu(env, "/ui/"))
        assert any(t == "details" and "nav-mas" in clases(at) for t, at, _ in a.elementos)
        assert any(t == "summary" for t, _, _ in a.elementos)
        assert "<script" not in menu(env, "/ui/") and "onclick" not in menu(env, "/ui/")

    def test_el_nombre_largo_sigue_para_el_lector_aunque_en_movil_se_vea_el_corto(self, env):
        a = arbol(menu(env, "/ui/"))
        largo = [at for t, at, _ in a.elementos if "nav-largo" in clases(at)]
        corto = [at for t, at, _ in a.elementos if "nav-corto" in clases(at)]
        assert len(largo) == len(corto) == 1
        assert corto[0]["aria-hidden"] == "true" and "aria-hidden" not in largo[0]
        assert "Por revisar" in menu(env, "/ui/") and "Revisar" in menu(env, "/ui/")

    def test_los_iconos_son_decorativos(self, env):
        a = arbol(menu(env, "/ui/"))
        iconos = [at for t, at, _ in a.elementos if "ico" in clases(at)]
        assert iconos and all(at.get("aria-hidden") == "true" for at in iconos)

    def test_los_contadores_son_marcadores_ocultos_con_id(self, env):
        a = arbol(menu(env, "/ui/"))
        marcadores = {at["id"]: at for t, at, _ in a.elementos
                      if str(at.get("id", "")).startswith("cnt-")}
        assert set(marcadores) == {"cnt-pendientes", "cnt-deseados", "cnt-estado"}
        assert all("hidden" in at for at in marcadores.values())

    def test_ids_unicos(self, env):
        ids = [at["id"] for _, at, _ in arbol(menu(env, "/ui/")).elementos if "id" in at]
        assert len(ids) == len(set(ids))


class TestLosEnlacesNoDependenDelFragmento:
    """El requisito central: nada que llegue por HTMX puede reemplazar ni borrar un enlace."""

    def test_el_sondeo_pide_sin_intercambiar_y_cada_30_s(self, env):
        a = arbol(menu(env, "/ui/"))
        sondeo = next(at for _, at, _ in a.elementos if "nav-sondeo" in clases(at))
        assert sondeo["hx-get"] == FRAGMENTO
        # Cada 30 s, y de inmediato cuando Por revisar cambia (asignar / ignorar envían ese evento).
        assert sondeo["hx-trigger"] == "load, every 30s, zascarr:pendientes from:body"
        assert sondeo["hx-swap"] == "none"

    def test_ningun_enlace_cuelga_de_un_elemento_htmx(self, env):
        a = arbol(menu(env, "/ui/"))
        for t, at, padres in a.elementos:
            if t == "a":
                assert not any(k.startswith("hx-") for _, p in padres for k in p), at["href"]

    def test_el_sondeo_no_contiene_nada(self, env):
        """Un elemento sin hijos: no hay nada dentro que un intercambio pudiera sustituir."""
        a = arbol(menu(env, "/ui/"))
        sondeo = [(t, at) for t, at, _ in a.elementos if "nav-sondeo" in clases(at)]
        hijos = [t for t, at, padres in a.elementos
                 if any("nav-sondeo" in clases(p[1]) for p in padres)]
        assert len(sondeo) == 1 and hijos == []

    def test_solo_un_elemento_del_menu_hace_peticiones(self, env):
        a = arbol(menu(env, "/ui/"))
        assert len([1 for _, at, _ in a.elementos if "hx-get" in at or "hx-post" in at]) == 1

    def test_el_fragmento_no_lleva_ningun_enlace_ni_ningun_swap_que_no_sea_fuera_de_banda(
            self, env):
        html = env.get_template("_nav_contadores.html").render(
            pendientes=3, deseados=2, atencion=True)
        a = arbol(html)
        raiz = [at for _, at, padres in a.elementos if not padres]
        assert not [1 for t, _, _ in a.elementos if t == "a"]
        assert all(at.get("hx-swap-oob") == "true" for at in raiz)
        assert {at["id"] for at in raiz} == {"cnt-pendientes", "cnt-deseados", "cnt-estado"}


# ── 3. páginas: título, h1, aria-current, salto de contenido ──────────────────────────────
PAGINAS = [
    ("inicio", "/ui/"), ("revisar", "/ui/pendientes"), ("biblioteca", "/ui/biblioteca"),
    ("duplicados", "/ui/auditoria"), ("descubrir", "/ui/descubrir"),
    ("deseados", "/ui/wishlist"), ("estado", "/estado"), ("ajustes", "/ui/ajustes"),
]


class TestPaginas:

    @pytest.mark.parametrize("clave,ruta", PAGINAS, ids=[p[0] for p in PAGINAS])
    def test_titulo_y_h1_coinciden_con_la_entrada_del_menu(self, con_sesion, clave, ruta):
        """U7: el nombre del menú, el <title> y el <h1> son el mismo."""
        etiqueta = ETIQUETAS[clave]
        with con_sesion(SesionFalsa()) as client:
            r = client.get(ruta)
        assert r.status_code == 200
        titulo = re.search(r"<title>(.*?)</title>", r.text, re.S).group(1).strip()
        h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", r.text, re.S)
        assert titulo == f"{etiqueta} — ZascArr"
        assert [x.strip() for x in h1] == [etiqueta]

    @pytest.mark.parametrize("clave,ruta", PAGINAS, ids=[p[0] for p in PAGINAS])
    def test_la_entrada_activa_es_la_de_la_pagina(self, con_sesion, clave, ruta):
        with con_sesion(SesionFalsa()) as client:
            r = client.get(ruta)
        a = arbol(r.text)
        url = URLS_DE_SIEMPRE[clave]
        assert {at["href"] for t, at, _ in a.elementos if at.get("aria-current") == "page"} == {url}

    @pytest.mark.parametrize("ruta", ["/ui/legal", "/legal"])
    def test_las_paginas_legales_no_marcan_ninguna_entrada(self, con_sesion, ruta):
        with con_sesion(SesionFalsa()) as client:
            r = client.get(ruta)
        assert r.status_code == 200 and "aria-current" not in r.text

    @pytest.mark.parametrize("ruta", [p[1] for p in PAGINAS] + ["/ui/legal", "/legal"])
    def test_estructura_comun(self, con_sesion, ruta):
        """Salto al contenido el primero; <main id="main">; un solo <h1>; el menú y su sondeo."""
        with con_sesion(SesionFalsa()) as client:
            r = client.get(ruta)
        a = arbol(r.text)
        primero = next(at for t, at, _ in a.elementos if t == "a")
        assert "skip" in clases(primero) and primero["href"] == "#main"
        main = next(at for t, at, _ in a.elementos if t == "main")
        assert main["id"] == "main" and main.get("tabindex") == "-1"
        assert len([1 for t, _, _ in a.elementos if t == "h1"]) == 1
        assert sum(1 for t, at, _ in a.elementos if t == "nav") == 1
        assert FRAGMENTO in r.text

    def test_la_ficha_de_serie_cuelga_de_biblioteca_y_tiene_titulo(self):
        assert entrada_activa("/ui/series/00000000-0000-0000-0000-000000000000") == "biblioteca"
        fuente = (PLANTILLAS / "series_detail.html").read_text(encoding="utf-8")
        assert "{% block title %}{{ series.title }} — ZascArr{% endblock %}" in fuente

    def test_el_login_no_lleva_menu_ni_sondeo(self):
        """`login.html` es autónoma (no hereda de base.html): V3 no la toca."""
        html = (PLANTILLAS / "login.html").read_text(encoding="utf-8")
        assert 'extends "base.html"' not in html and "ui.menu" not in html and FRAGMENTO not in html

    def test_cerrar_sesion_solo_con_la_autenticacion_activa(self, con_sesion, monkeypatch):
        for modo, esperado in (("none", False), ("password", True)):
            ajustes = get_settings().model_copy(update={"auth_mode": modo})
            monkeypatch.setattr("zascarr.web.routes.get_settings", lambda a=ajustes: a)
            with con_sesion(SesionFalsa()) as client:
                # Con auth activa hay que tener sesión para ver la página.
                monkeypatch.setattr("zascarr.services.auth.get_settings", lambda a=ajustes: a)
                if modo == "password":
                    ajustes = ajustes.model_copy(update={
                        "auth_password_hash": hash_password("x"), "secret_key": "s"})
                    monkeypatch.setattr("zascarr.services.auth.get_settings", lambda a=ajustes: a)
                    client.cookies.set(COOKIE_NAME, crear_cookie_sesion("s"))
                r = client.get("/ui/descubrir")
            assert r.status_code == 200
            a = arbol(r.text)
            hay = any(t == "form" and at.get("action") == "/logout" for t, at, _ in a.elementos)
            assert hay is esperado, modo
            if esperado:
                assert any(t == "button" and "btn-logout" in clases(at) for t, at, _ in a.elementos)


# ── 4. el fragmento de contadores ─────────────────────────────────────────────────────────
def _sin_seguridad(monkeypatch, atencion: bool = False):
    monkeypatch.setattr(
        "zascarr.web.navegacion.estado_de_seguridad", lambda: {"atencion": atencion})


class TestFragmento:

    def test_con_datos_devuelve_los_marcadores_y_libera_la_sesion(self, con_fabrica, monkeypatch):
        _sin_seguridad(monkeypatch, True)
        fabrica = FabricaFalsa([14, 6])
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)

        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        a = arbol(r.text)
        por_id = {at["id"]: at for _, at, padres in a.elementos if not padres}
        assert set(por_id) == {"cnt-pendientes", "cnt-deseados", "cnt-estado"}
        assert all("hidden" not in at for at in por_id.values())
        assert "14" in r.text and "6" in r.text
        assert "por revisar" in r.text and "deseados" in r.text and "necesita atención" in r.text
        # Camino correcto: una sesión, abierta y cerrada, y NUNCA un commit (es de solo lectura).
        assert (fabrica.creadas, fabrica.abiertas, fabrica.cerradas) == (1, 1, 1)
        assert fabrica.sesion.commits == 0 and len(fabrica.sesion.consultas) == 2

    def test_a_cero_se_oculta_en_vez_de_mostrar_cero(self, con_fabrica, monkeypatch):
        _sin_seguridad(monkeypatch, False)
        with con_fabrica(FabricaFalsa([0, 0])) as client:
            r = client.get(FRAGMENTO)

        assert r.status_code == 200
        por_id = {at["id"]: at for _, at, padres in arbol(r.text).elementos if not padres}
        assert len(por_id) == 3 and all("hidden" in at for at in por_id.values())
        assert ">0<" not in r.text and "0" not in re.sub(r"<[^>]+>", "", r.text)

    def test_mas_de_mil_se_muestra_999_mas(self, con_fabrica):
        with con_fabrica(FabricaFalsa([5000, 1])) as client:
            r = client.get(FRAGMENTO)
        assert "999+" in r.text and "5000" not in r.text

    def test_cada_contador_usa_el_mismo_numero_que_la_lista(self, con_fabrica):
        """Primero pendientes, después deseados."""
        with con_fabrica(FabricaFalsa([7, 3])) as client:
            r = client.get(FRAGMENTO)
        pend = re.search(r'id="cnt-pendientes"[^>]*>(\d+)', r.text).group(1)
        dese = re.search(r'id="cnt-deseados"[^>]*>(\d+)', r.text).group(1)
        assert (pend, dese) == ("7", "3")

    def test_la_ruta_no_usa_la_dependencia_generica_get_db(self, con_fabrica):
        """`get_db` adquiere ANTES del cuerpo y hace `commit` DESPUÉS de responder: dos fases fuera
        de cualquier `try` del manejador. El fragmento es de solo lectura y abre su propia sesión.
        Prueba por comportamiento: con `get_db` ROTO el fragmento funciona igual."""
        import inspect

        from zascarr.web import navegacion

        async def get_db_roto():
            raise AssertionError("el fragmento no debe usar get_db")
            yield   # pragma: no cover

        app.dependency_overrides[get_db] = get_db_roto
        try:
            with con_fabrica(FabricaFalsa([2, 3])) as client:
                r = client.get(FRAGMENTO)
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 200 and "2" in r.text
        assert list(inspect.signature(navegacion.contadores_del_menu).parameters) == ["request"]
        assert not hasattr(navegacion, "get_db")


#: cada fase del ciclo de la sesión puede fallar: todas acaban en 204 vacío
FALLOS_DE_SESION = {
    "al crear la sesión": {"al_crear": OSError("sin fábrica")},
    "al abrirla (conectar)": {"al_abrir": OperationalError("SELECT 1", {}, Exception("refused"))},
    "al abrirla (OSError)": {"al_abrir": OSError("connection refused")},
    "en la primera consulta": {"en_consulta": OperationalError("SELECT", {}, Exception("closed"))},
    "en la consulta (otra)": {"en_consulta": RuntimeError("cualquier cosa")},
    "al liberarla": {"al_cerrar": OSError("el cierre también falla")},
}


class TestCualquierFalloEs204:
    """El contrato publicado dice «cualquier fallo»: se prueba en TODAS las fases, no solo en las
    consultas (la versión anterior dejaba fuera abrir y cerrar la sesión: venían de `get_db`)."""

    @pytest.mark.parametrize("fase", list(FALLOS_DE_SESION))
    def test_204_vacio_sin_cuerpo_de_error(self, con_fabrica, fase):
        fabrica = FabricaFalsa([14, 6], **FALLOS_DE_SESION[fase])
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)

        assert r.status_code == 204 and r.content == b""
        assert r.headers["cache-control"] == "no-store"
        assert fabrica.sesion.commits == 0
        # lo que se llegó a abrir se cerró (no se filtran sesiones)
        assert fabrica.cerradas == fabrica.abiertas

    def test_si_falla_al_liberar_no_se_sirven_numeros_de_una_sesion_dudosa(self, con_fabrica):
        fabrica = FabricaFalsa([14, 6], al_cerrar=OSError("x"))
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)
        assert r.status_code == 204 and "14" not in r.text and len(fabrica.sesion.consultas) == 2

    def test_un_fallo_de_renderizado_tambien_es_204(self, con_fabrica, monkeypatch):
        def roto(*a, **k):
            raise RuntimeError("plantilla rota")

        monkeypatch.setattr("zascarr.web.navegacion.templates.TemplateResponse", roto)
        fabrica = FabricaFalsa([1, 1])
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)
        assert r.status_code == 204 and r.content == b"" and fabrica.cerradas == 1

    def test_un_fallo_en_el_estado_de_seguridad_tambien_es_204(self, con_fabrica, monkeypatch):
        def roto():
            raise ValueError("ajustes ilegibles")

        monkeypatch.setattr("zascarr.web.navegacion.estado_de_seguridad", roto)
        with con_fabrica(FabricaFalsa([1, 1])) as client:
            assert client.get(FRAGMENTO).status_code == 204

    def test_una_bd_que_no_contesta_a_tiempo_es_204_y_no_deja_la_peticion_colgada(
            self, con_fabrica, monkeypatch):
        """Un fallo más: sin plazo, una BD que no responde dejaría peticiones colgadas."""
        import time

        monkeypatch.setattr("zascarr.web.navegacion.PLAZO_SEGUNDOS", 0.05)
        fabrica = FabricaFalsa([14, 6], demora=5)
        inicio = time.monotonic()
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)

        assert r.status_code == 204 and r.content == b""
        assert time.monotonic() - inicio < 2          # no esperó los 5 s de la BD
        assert fabrica.cerradas == fabrica.abiertas

    def test_el_log_no_lleva_datos_solo_la_clase_del_error(self, con_fabrica):
        from structlog.testing import capture_logs

        fabrica = FabricaFalsa(en_consulta=OSError("/ruta/secreta/x"))
        with capture_logs() as logs, con_fabrica(fabrica) as c:
            c.get(FRAGMENTO)
        evento = next(e for e in logs if e["event"] == "nav_contadores_no_disponibles")
        assert evento["error"] == "OSError" and "secreta" not in str(evento)

    def test_cancelar_la_peticion_no_se_traga(self, con_fabrica):
        """`CancelledError` no es un fallo que ocultar (el cliente se fue): no pasa a 204."""
        fabrica = FabricaFalsa([1, 1], al_abrir=asyncio.CancelledError())
        with con_fabrica(fabrica) as client, pytest.raises(BaseException):  # noqa: B017, PT011
            client.get(FRAGMENTO)


# ── 5. autenticación y arranque degradado ─────────────────────────────────────────────────
def _con_auth(monkeypatch):
    ajustes = get_settings().model_copy(update={
        "auth_mode": "password", "auth_password_hash": hash_password("x"), "secret_key": "s"})
    monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
    return ajustes


class TestAutenticacion:

    def test_sin_sesion_es_204_vacio_y_no_se_abre_la_sesion_de_bd(self, con_fabrica, monkeypatch):
        """Ni datos ni redirección a /login (htmx la seguiría e intercambiaría su página). Ni
        siquiera se llama a la fábrica de sesiones: no hay conexión que abrir sin sesión válida."""
        _con_auth(monkeypatch)
        fabrica = FabricaFalsa([14, 6])
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)

        assert r.status_code == 204 and r.content == b""
        assert "location" not in r.headers
        assert fabrica.creadas == 0 and fabrica.abiertas == 0 and fabrica.sesion.consultas == []

    def test_con_la_cookie_de_otra_clave_tampoco(self, con_fabrica, monkeypatch):
        _con_auth(monkeypatch)
        fabrica = FabricaFalsa([14, 6])
        with con_fabrica(fabrica) as client:
            client.cookies.set(COOKIE_NAME, crear_cookie_sesion("OTRA-CLAVE"))
            r = client.get(FRAGMENTO)
        assert r.status_code == 204 and fabrica.creadas == 0

    def test_con_sesion_valida_si_responde(self, con_fabrica, monkeypatch):
        _con_auth(monkeypatch)
        fabrica = FabricaFalsa([14, 6])
        with con_fabrica(fabrica) as client:
            client.cookies.set(COOKIE_NAME, crear_cookie_sesion("s"))
            r = client.get(FRAGMENTO)
        assert r.status_code == 200 and "14" in r.text and fabrica.cerradas == 1

    def test_el_resto_de_ui_sigue_redirigiendo_a_login(self, con_sesion, monkeypatch):
        """La excepción es solo del fragmento; el contrato de A6 para /ui/* no cambia."""
        _con_auth(monkeypatch)
        with con_sesion(SesionFalsa()) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")

    def test_no_es_una_ruta_de_diagnostico_ni_una_exenta(self):
        """Las de diagnóstico se sirven sin comprobar la sesión en arranque degradado."""
        assert FRAGMENTO in RUTAS_FRAGMENTO_SILENCIOSO
        assert FRAGMENTO not in _RUTAS_DIAGNOSTICO
        assert FRAGMENTO not in servicio_auth._RUTAS_EXENTAS
        assert frozenset({FRAGMENTO}) == RUTAS_FRAGMENTO_SILENCIOSO


class TestArranqueDegradado:

    @pytest.fixture
    def degradado(self, monkeypatch):
        monkeypatch.setattr(app.state, "db_degraded", True, raising=False)

    def test_el_fragmento_es_204_y_no_el_503_html(self, degradado, con_fabrica):
        fabrica = FabricaFalsa([1, 1])
        with con_fabrica(fabrica) as client:
            r = client.get(FRAGMENTO)
        assert r.status_code == 204 and r.content == b"" and fabrica.creadas == 0

    def test_el_fragmento_es_204_con_o_sin_sesion_y_nunca_sirve_datos(
            self, degradado, con_fabrica, monkeypatch):
        _con_auth(monkeypatch)
        fabrica = FabricaFalsa([14, 6])
        with con_fabrica(fabrica) as client:
            client.cookies.set(COOKIE_NAME, crear_cookie_sesion("s"))
            r = client.get(FRAGMENTO)
        assert r.status_code == 204 and fabrica.creadas == 0

    def test_estado_sigue_sirviendose_como_diagnostico(self, degradado, con_sesion):
        """Decisión 2 de la épica: `/estado` se queda en `/estado` y funciona con la BD caída."""
        with con_sesion(SesionFalsa()) as client:
            r = client.get("/estado")
        assert r.status_code == 200 and "Estado" in r.text
        a = arbol(r.text)
        assert any(at.get("href") == "/estado" and at.get("aria-current") == "page"
                   for t, at, _ in a.elementos)

    def test_el_resto_de_ui_sigue_dando_el_503_de_e6(self, degradado, con_sesion):
        with con_sesion(SesionFalsa()) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 503 and "Base de datos no lista" in r.text


# ── 6. los recuentos usan el filtro de la lista que cuentan ───────────────────────────────
def _donde(stmt) -> str:
    return str(stmt.whereclause.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestRecuentos:

    @pytest.mark.asyncio
    async def test_pendientes_cuenta_con_el_mismo_filtro_que_la_lista(self):
        sesion = SesionFalsa([0])
        servicio = ReviewService.__new__(ReviewService)
        servicio.db = sesion
        await servicio.count_pending()
        await servicio.pending_files()
        recuento, lista = sesion.consultas
        assert _donde(recuento) == _donde(lista)
        assert "review_dismissed" in _donde(lista) and "unsorted" in _donde(lista)

    @pytest.mark.asyncio
    async def test_el_recuento_no_tiene_el_tope_de_50_de_la_lista(self):
        sesion = SesionFalsa([0])
        servicio = ReviewService.__new__(ReviewService)
        servicio.db = sesion
        await servicio.count_pending()
        sql = str(sesion.consultas[0].compile(dialect=postgresql.dialect()))
        assert "count(" in sql.lower() and "LIMIT" not in sql.upper()

    @pytest.mark.asyncio
    async def test_deseados_no_cuenta_los_retirados(self):
        sesion = SesionFalsa([0])
        servicio = WishlistService(sesion)
        await servicio.count_active()
        donde = _donde(sesion.consultas[0])
        assert "wishlist.status != 'retirado'" in donde


# ── 7. CSS: lo que el menú promete ────────────────────────────────────────────────────────
def _reglas() -> dict[str, str]:
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    return {" ".join(s.split()): c for s, c in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)}


class TestCssDelShell:

    @pytest.mark.parametrize("selector", [
        ".app", ".side", ".nav", ".nav-grupo", ".nav-enlace", ".nav-enlace[aria-current=\"page\"]",
        ".badge", ".badge.hot", ".dot", ".nav-mas", ".nav-mas-panel", ".skip", ".skip:focus", ".sr",
        ".side-foot .btn-logout",
    ])
    def test_existe_la_regla(self, selector):
        assert any(selector in s.split(", ") or selector == s for s in _reglas()), selector

    def test_los_marcadores_ocultos_siguen_ocultos_pese_al_display_de_autor(self):
        """`[hidden]` pierde frente a `.badge { display: … }` si no se repite la regla."""
        assert any(".badge[hidden]" in s and ".dot[hidden]" in s for s in _reglas())

    def test_el_contenido_ocupa_la_columna_entera_en_la_rejilla(self):
        """Medido en navegador: con `margin: 0 auto` un hijo de la rejilla deja de estirarse y se
        encoge a su contenido (el Inicio quedaba en 736 px y el resto en 1036, a 1280 de ancho)."""
        regla = _reglas()[".app > .content"]
        assert "width: 100%" in regla and "min-width: 0" in regla

    def test_el_foco_no_queda_tapado_por_la_barra_inferior(self):
        assert re.search(r"html\s*\{\s*scroll-padding-bottom:\s*\d+px", CSS)

    def test_en_movil_se_oculta_lo_secundario_y_se_muestra_mas(self):
        bloque = CSS[CSS.index("@media (max-width: 860px)"):]
        assert ".grp, .nav-secundaria { display: none; }" in bloque
        assert ".nav-mas { display: block;" in bloque
        assert "position: fixed" in bloque and "bottom: 0" in bloque

    def test_el_nombre_largo_no_se_pierde_para_el_lector(self):
        bloque = CSS[CSS.index("@media (max-width: 860px)"):]
        regla = re.search(r"\.nav-largo\s*\{([^}]*)\}", bloque).group(1)
        assert "display: none" not in regla and "clip: rect(0 0 0 0)" in regla

    def test_las_clases_antiguas_del_menu_siguen_existiendo(self):
        """`.topnav` y compañía se retiran en V14, no antes."""
        for c in ("topnav", "brand", "btn-logout", "nav-logout"):
            assert f".{c}" in CSS


def _peticion() -> Request:
    return Request({"type": "http", "method": "GET", "path": FRAGMENTO, "headers": [],
                    "query_string": b"", "app": app})


class TestBdCongelada:
    """La BD ACEPTA la conexión y no contesta (`docker pause` en el ensayo; un disco o red que se
    cuelgan). Cancelar la consulta no basta: liberar la sesión hace un `rollback` sobre esa misma
    conexión y también se cuelga. Con un `asyncio.timeout` alrededor de todo, el fragmento NO
    respondía (medido en el stack real: curl cortó a los 20 s con un plazo de 5). Estas pruebas
    modelan esa BD: consulta que no vuelve y cierre que tampoco."""

    @pytest.fixture
    def corto(self, monkeypatch):
        from zascarr.web import navegacion

        monkeypatch.setattr(navegacion, "PLAZO_SEGUNDOS", 0.05)
        monkeypatch.setattr(navegacion, "_calculo_en_curso", None)
        return navegacion

    @pytest.mark.asyncio
    async def test_responde_204_sin_esperar_a_la_limpieza(self, corto, monkeypatch):
        fabrica = FabricaFalsa([1, 1], congelada=True)
        monkeypatch.setattr(corto, "async_session_factory", fabrica)
        try:
            # Con `wait_for` de 2 s: una respuesta que dependiera del cierre colgado lo agotaría.
            r = await asyncio.wait_for(corto.contadores_del_menu(_peticion()), timeout=2)
            assert r.status_code == 204 and r.body == b""
            assert fabrica.cerradas == 0 and not corto._calculo_en_curso.done()   # sigue limpiando
        finally:
            fabrica.liberar.set()
            await asyncio.wait({corto._calculo_en_curso}, timeout=2)

    @pytest.mark.asyncio
    async def test_los_sondeos_no_se_apilan_contra_una_bd_que_no_contesta(self, corto, monkeypatch):
        fabrica = FabricaFalsa([1, 1], congelada=True)
        monkeypatch.setattr(corto, "async_session_factory", fabrica)
        try:
            respuestas = [await corto.contadores_del_menu(_peticion()) for _ in range(5)]
            assert [r.status_code for r in respuestas] == [204] * 5
            assert fabrica.creadas == 1          # UNA sesión, no cinco
        finally:
            fabrica.liberar.set()
            await asyncio.wait({corto._calculo_en_curso}, timeout=2)

    @pytest.mark.asyncio
    async def test_las_peticiones_concurrentes_comparten_el_trabajo(self, corto, monkeypatch):
        monkeypatch.setattr(corto, "PLAZO_SEGUNDOS", 2)
        fabrica = FabricaFalsa([14, 6], demora=0.05)
        monkeypatch.setattr(corto, "async_session_factory", fabrica)

        a, b, c = await asyncio.gather(*(corto.contadores_del_menu(_peticion()) for _ in range(3)))

        assert [a.status_code, b.status_code, c.status_code] == [200, 200, 200]
        assert fabrica.creadas == 1 and fabrica.cerradas == 1 and fabrica.sesion.commits == 0
        assert b"14" in a.body and a.body == b.body == c.body      # el mismo resultado

    @pytest.mark.asyncio
    async def test_cuando_la_bd_vuelve_el_siguiente_sondeo_funciona(self, corto, monkeypatch):
        fabrica = FabricaFalsa([14, 6], congelada=True)
        monkeypatch.setattr(corto, "async_session_factory", fabrica)
        r1 = await corto.contadores_del_menu(_peticion())
        assert r1.status_code == 204
        # la BD se descongela: la tarea abandonada termina sola (con sus números, que se tiran)
        fabrica.liberar.set()
        await asyncio.wait({corto._calculo_en_curso}, timeout=2)
        assert corto._calculo_en_curso.done() and fabrica.cerradas == 1

        nueva = FabricaFalsa([21, 9])
        monkeypatch.setattr(corto, "async_session_factory", nueva)
        monkeypatch.setattr(corto, "PLAZO_SEGUNDOS", 2)
        r2 = await corto.contadores_del_menu(_peticion())
        assert r2.status_code == 200 and b"21" in r2.body and nueva.creadas == 1

    @pytest.mark.asyncio
    async def test_una_tarea_de_otro_bucle_no_bloquea_el_fragmento(self, corto, monkeypatch):
        """Cada bucle (cada TestClient) crea la suya: no se espera una tarea de un bucle cerrado."""
        class Ajena:
            def done(self):
                return False

            def get_loop(self):
                return object()

        monkeypatch.setattr(corto, "_calculo_en_curso", Ajena())
        monkeypatch.setattr(corto, "PLAZO_SEGUNDOS", 2)
        monkeypatch.setattr(corto, "async_session_factory", FabricaFalsa([1, 1]))
        assert (await corto.contadores_del_menu(_peticion())).status_code == 200
