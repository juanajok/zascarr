"""
tests/test_web_library.py

Suite de la biblioteca (C1) — /ui/biblioteca. Contrato HTTP, mismo
patrón que test_pendientes.py; la lógica de filtrado ya está cubierta
en test_series_service.py.
"""
from __future__ import annotations

import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from structlog.testing import capture_logs

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import Character, ComicTradition, Publisher, Series, StoryArc


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def all(self):
        return self._value


class FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return FakeScalarResult(self._value)

    def scalar(self):
        return self._value

    def all(self):
        return self._value


class FakeSession:
    def __init__(self, queue: list | None = None, error: Exception | None = None):
        self._queue = list(queue or [])
        self._error = error

    async def execute(self, _statement):
        if self._error is not None:
            raise self._error
        return self._queue.pop(0)


def override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def make_series(title="Batman") -> Series:
    return Series(id=uuid4(), title=title, tradition=ComicTradition.AMERICAN, start_year=2011)


class TestIndex:

    def test_pagina_lista_series(self):
        series = make_series("Batman")
        session = FakeSession([
            FakeExecResult([]),        # list_publishers_with_series
            FakeExecResult(1),         # count
            FakeExecResult([series]),  # items
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert "Batman" in r.text

    def test_lista_lleva_chip_previa(self):
        series = make_series("Batman")
        session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca?vista=lista")
        assert r.status_code == 200
        assert f'hx-get="/ui/series/{series.id}/previa"' in r.text
        assert f'hx-target="#previa-l-{series.id}"' in r.text

    def test_la_portada_de_la_rejilla_lleva_v2(self):
        """R-01 de BL-PORT1 (#300): sin `?v=2` el navegador puede pintar hasta 24 h la
        portada vieja tras desplegar la caché `v2`. La ruta ignora el query."""
        series = make_series("Batman")
        session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert f"/ui/series/{series.id}/portada?v=2" in r.text

    def test_la_tarjeta_dice_la_tradicion_como_el_filtro(self):
        """Caso real (2026-10-20): la tarjeta decía «franco_belgian»; el filtro, «Franco-belga»."""
        series = make_series("Thorgal")
        series.tradition = ComicTradition.FRANCO_BELGIAN
        session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        tarjeta = r.text[r.text.index('class="library-card-meta"'):]
        tarjeta = tarjeta[:tarjeta.index("</div>")]
        assert "Franco-belga (BD)" in tarjeta and "franco_belgian" not in tarjeta

    def test_los_buscadores_vacios_no_pintan_su_borde(self):
        """El desplegable vacío con borde dejaba una barra negra bajo «Buscar personaje / saga».

        V14 (#750) retiró `.filter-search-box` (ya sin uso); el mecanismo que lo sustituye es el
        mismo: el borde se pinta solo cuando la lista tiene resultados (`:not(:empty)`).
        """
        from zascarr.main import STATIC_DIR
        css = (STATIC_DIR / "web.css").read_text(encoding="utf-8")
        assert ".barra-panel-campos .series-results:not(:empty)" in css
        assert "border: var(--border-chip) solid var(--ink)" in css.split(
            ".barra-panel-campos .series-results:not(:empty)")[1].split("}")[0]

    def test_sin_editoriales_no_pinta_el_desplegable_vacio(self):
        """m4 de U18: sin editoriales no se ofrece un filtro que no filtra nada."""
        session = FakeSession([FakeExecResult([]), FakeExecResult(0), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert 'id="f-publisher"' not in r.text
        assert "Todas las editoriales" not in r.text

    def test_con_editoriales_si_pinta_el_desplegable(self):
        publisher = Publisher(id=uuid4(), name="Bruguera")
        session = FakeSession([
            FakeExecResult([publisher]),
            FakeExecResult(1),
            FakeExecResult([make_series("Mortadelo")]),
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert 'id="f-publisher"' in r.text
        assert "Todas las editoriales" in r.text
        assert "Bruguera" in r.text

    def test_pagina_vacia_muestra_mensaje(self):
        session = FakeSession([
            FakeExecResult([]),
            FakeExecResult(0),
            FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert "Tu biblioteca todavía no tiene series." in r.text

    def test_titulo_con_script_se_escapa(self):
        """XSS: un título con <script> debe renderizarse escapado por Jinja2,
        nunca como HTML ejecutable."""
        series = make_series('<script>alert(1)</script>')
        session = FakeSession([
            FakeExecResult([]),        # list_publishers_with_series
            FakeExecResult(1),         # count
            FakeExecResult([series]),  # items
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert "&lt;script&gt;" in r.text
        assert "<script>alert(1)</script>" not in r.text


class TestResultados:

    def test_fragmento_con_filtro_de_tradicion(self):
        series = make_series("Thorgal")
        session = FakeSession([FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=franco_belgian")
        assert r.status_code == 200
        assert "Thorgal" in r.text
        # Es un fragmento: no repite el layout completo (topnav).
        assert "ZascArr" not in r.text

    def test_campos_uuid_vacios_no_dan_422(self):
        """Regresión: el formulario de filtros manda publisher_id/
        character_id/story_arc_id como "" (campos ocultos sin valor)
        cuando no hay selección — no ausentes de la query string. Un
        UUID | None de FastAPI no acepta "" y daba 422 antes de este fix,
        encontrado probando en un navegador real, no con estos mocks."""
        series = make_series("Batman")
        session = FakeSession([FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get(
                "/ui/biblioteca/resultados"
                "?tradition=american&publisher_id=&character_id=&story_arc_id=&q="
            )
        assert r.status_code == 200
        assert "Batman" in r.text


class TestBuscarPersonajeYSaga:

    def test_buscar_personaje_sin_coincidencias(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-personaje?q=zzz")
        assert "Sin coincidencias" in r.text

    def test_buscar_saga_sin_coincidencias(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-saga?q=zzz")
        assert "Sin coincidencias" in r.text


# ── BL-IT01 (#283): filtros que se conservan, se retiran y se explican ───────


class TestFiltrosActivosYRecuento:
    """El fragmento que se intercambia trae el recuento y los chips; el
    recuento de la cabecera ya no puede quedarse viejo."""

    def test_el_fragmento_trae_recuento_y_chips(self):
        session = FakeSession([
            FakeExecResult([]),                        # editoriales
            FakeExecResult(2),                         # count
            FakeExecResult([make_series("A"), make_series("B")]),
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca?tradition=tebeo&q=thorgal")
        assert r.status_code == 200
        assert "2 series coinciden con estos filtros." in r.text
        assert "Tradición: Tebeo español" in r.text
        assert "Búsqueda: «thorgal»" in r.text
        assert 'aria-label="Quitar filtro: Tradición: Tebeo español"' in r.text
        assert "Limpiar filtros" in r.text

    def test_quitar_un_filtro_conserva_los_demas(self):
        publisher_id = uuid4()
        session = FakeSession([
            FakeExecResult(1),
            FakeExecResult([make_series("Thorgal")]),
            FakeExecResult("Bruguera"),                # nombre de la editorial
        ])
        with use_fake_session(session) as client:
            r = client.get(
                f"/ui/biblioteca/resultados?tradition=tebeo&publisher_id={publisher_id}"
            )
        assert r.status_code == 200
        enlaces = re.findall(r'href="(/ui/biblioteca\?[^"]*)"', r.text)
        sin_tradicion = next(u for u in enlaces if "publisher_id" in u and "tradition=" not in u)
        assert f"publisher_id={publisher_id}" in sin_tradicion
        sin_editorial = next(
            u for u in enlaces if "tradition=tebeo" in u and "publisher_id=" not in u
        )
        assert "page=1" in sin_editorial  # quitar un filtro vuelve a la página 1
        assert "quitar=tradition" in r.text
        assert "quitar=publisher_id" in r.text

    def test_limpiar_todos_es_una_accion_aparte(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=tebeo")
        assert 'href="/ui/biblioteca?page=1"' in r.text
        assert "quitar=todos" in r.text
        assert "Limpiar filtros" in r.text

    def test_retirar_el_chip_de_busqueda_limpia_el_campo_fuera_de_banda(self):
        """El campo de título vive fuera de #rejilla: si no se limpia, queda
        el texto viejo y el siguiente cambio reaplica un filtro retirado."""
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get(
                "/ui/biblioteca/resultados?page=1&quitar=q",
                headers={"HX-Request": "true"},
            )
        assert r.status_code == 200
        assert 'hx-swap-oob="outerHTML"' in r.text
        assert 'id="f-q"' in r.text
        assert 'value=""' in r.text
        assert "autofocus" in r.text
        assert r.headers["HX-Push-Url"] == "/ui/biblioteca?page=1"

    def test_vacio_conserva_los_filtros_y_ofrece_salida(self):
        session = FakeSession([FakeExecResult(0), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=tebeo")
        assert "Ninguna serie coincide con estos filtros." in r.text
        # Los chips siguen ahí: la consulta no se ha perdido.
        assert "Tradición: Tebeo español" in r.text
        assert "Prueba a quitar algún filtro" in r.text

    def test_biblioteca_vacia_sin_filtros_no_culpa_a_los_filtros(self):
        session = FakeSession([FakeExecResult([]), FakeExecResult(0), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert "Tu biblioteca todavía no tiene series." in r.text


class TestUrlCanonica:
    """La URL que empuja htmx es la de la página completa, no la del fragmento."""

    def test_coste_de_la_pagina_con_tres_filtros(self):
        """AC-08: editoriales (1) + count (1) + página (1) + nombre de
        personaje/saga (2); la editorial sale de la lista ya cargada."""
        editorial = Publisher(id=uuid4(), name="Bruguera")
        session = FakeSession([
            FakeExecResult([editorial]),          # editoriales
            FakeExecResult(1),                    # count
            FakeExecResult([make_series("A")]),   # página
            FakeExecResult("Batman"),             # nombre de personaje
            FakeExecResult("La Patrulla X"),      # nombre de saga
        ])
        with use_fake_session(session) as client:
            r = client.get(
                f"/ui/biblioteca?publisher_id={editorial.id}"
                f"&character_id={uuid4()}&story_arc_id={uuid4()}"
            )
        assert r.status_code == 200
        assert "Editorial: Bruguera" in r.text
        assert "Personaje: Batman" in r.text
        assert "Saga: La Patrulla X" in r.text
        assert not session._queue  # exactamente 5 SELECT, ni uno más

    def test_coste_del_fragmento_con_tres_filtros(self):
        """AC-08: count + página + 3 nombres = 5 SELECT, sin N+1."""
        session = FakeSession([
            FakeExecResult(1),
            FakeExecResult([make_series("A")]),
            FakeExecResult("Bruguera"),
            FakeExecResult("Batman"),
            FakeExecResult("La Patrulla X"),
        ])
        with use_fake_session(session) as client:
            r = client.get(
                f"/ui/biblioteca/resultados?publisher_id={uuid4()}"
                f"&character_id={uuid4()}&story_arc_id={uuid4()}"
            )
        assert r.status_code == 200
        assert "Editorial: Bruguera" in r.text
        assert "Personaje: Batman" in r.text
        assert "Saga: La Patrulla X" in r.text
        assert not session._queue  # count + página + 3 nombres, sin N+1

    def test_el_fragmento_empuja_la_pagina_completa(self):
        session = FakeSession([FakeExecResult(50), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=tebeo&page=2")
        assert r.headers["HX-Push-Url"] == "/ui/biblioteca?tradition=tebeo&page=2"
        assert r.headers["Cache-Control"] == "no-store"

    def test_la_pagina_uno_tambien_es_canonica(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=tebeo&page=1")
        assert r.headers["HX-Push-Url"] == "/ui/biblioteca?tradition=tebeo&page=1"

    def test_el_main_es_el_elemento_de_historial(self):
        session = FakeSession([FakeExecResult([]), FakeExecResult(0), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert "hx-history-elt" in r.text

    def test_paginacion_conserva_filtros_y_aria_current(self):
        session = FakeSession([FakeExecResult(50), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=tebeo&page=2")
        assert 'aria-current="page"' in r.text
        assert "page=3" in r.text
        assert "tradition=tebeo" in r.text

    def test_la_paginacion_no_depende_de_la_herencia_implicita_de_htmx4(self):
        """Bug real de la pasada de navegador (2026-11-05): htmx 4 trae
        `implicitInheritance: false`, así que `hx-target`/`hx-swap` del `<nav>`
        NO llegan a los enlaces. Sin atributos propios, el fragmento se
        intercambiaba DENTRO del enlace: quedaban dos rejillas y 30 tarjetas.
        Cada enlace de página debe llevar su target y swap."""
        session = FakeSession([FakeExecResult(50), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?page=1")
        enlace = re.search(r'<a href="[^"]*page=2"[^>]*>2</a>', r.text)
        assert enlace, "no se encontró el enlace a la página 2"
        assert 'hx-target="#rejilla"' in enlace.group(0)
        assert 'hx-swap="innerHTML"' in enlace.group(0)


class TestEntradasInvalidas:
    """Nunca 422/500 en la UI ni una biblioteca vacía que parezca real."""

    def test_tradicion_inexistente_se_quita_con_aviso(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=inventada")
        assert r.status_code == 200
        assert "La tradición de ese filtro no existe; se ha quitado." in r.text
        assert "A" in r.text

    def test_uuid_mal_formado_se_quita_con_aviso(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?character_id=no-es-uuid")
        assert r.status_code == 200
        assert "El filtro de personaje no es válido; se ha quitado." in r.text
        assert "A" in r.text

    def test_pagina_cero_se_corrige_con_aviso(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?page=0")
        assert r.status_code == 200
        assert "La página pedida no existe; se muestra la primera." in r.text

    def test_pagina_no_numerica_se_corrige_con_aviso(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?page=abc")
        assert r.status_code == 200
        assert "La página pedida no es válida; se muestra la primera." in r.text

    def test_q_con_caracteres_de_control_se_limpia(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?q=noir%00%0A")
        assert r.status_code == 200
        assert "La búsqueda tenía caracteres no válidos; se han quitado." in r.text

    def test_q_con_control_al_final_tambien_avisa(self):
        """Regresión: el `strip()` previo se comía el CRLF final y no avisaba."""
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?q=noir%0d%0a")
        assert r.status_code == 200
        assert "La búsqueda tenía caracteres no válidos; se han quitado." in r.text
        assert r.headers["HX-Push-Url"] == "/ui/biblioteca?q=noir&page=1"

    def test_quitar_desconocido_se_ignora(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get(
                "/ui/biblioteca/resultados?tradition=tebeo&quitar=desconocido",
                headers={"HX-Request": "true"},
            )
        assert r.status_code == 200
        assert 'hx-swap-oob="outerHTML"' not in r.text
        assert "autofocus" not in r.text

    def test_q_demasiado_larga_se_recorta(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?q=" + "a" * 201)
        assert r.status_code == 200
        assert (
            "La búsqueda era demasiado larga; se han usado los primeros 200 caracteres."
            in r.text
        )

    def test_pagina_posterior_al_final_se_corrige(self):
        session = FakeSession([FakeExecResult(50), FakeExecResult([make_series("A")])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?page=99")
        assert r.status_code == 200
        assert "La página pedida no existe; se muestra la última." in r.text
        assert r.headers["HX-Push-Url"] == "/ui/biblioteca?page=3"
        assert 'aria-current="page"' in r.text

    def test_fallo_de_bd_no_se_disfraza_de_biblioteca_vacia(self):
        session = FakeSession(error=SQLAlchemyError("boom"))
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=tebeo")
        assert r.status_code == 200
        assert "No se pudo cargar la biblioteca. Vuelve a intentarlo." in r.text
        assert "Ninguna serie coincide" not in r.text


class TestBusquedaPersonajeSagaConservaFiltros:

    def test_personaje_anade_su_filtro_sin_perder_los_demas(self):
        personaje = Character(id=uuid4(), name="Batman")
        publisher_id = uuid4()
        session = FakeSession([FakeExecResult([personaje])])
        with use_fake_session(session) as client:
            r = client.get(
                "/ui/biblioteca/buscar-personaje?personaje=bat"
                f"&tradition=tebeo&publisher_id={publisher_id}"
            )
        assert r.status_code == 200
        assert "Batman" in r.text
        assert "tradition=tebeo" in r.text
        assert f"publisher_id={publisher_id}" in r.text
        assert f"character_id={personaje.id}" in r.text

    def test_saga_anade_su_filtro_sin_perder_los_demas(self):
        saga = StoryArc(id=uuid4(), title="La Patrulla X")
        session = FakeSession([FakeExecResult([saga])])
        with use_fake_session(session) as client:
            r = client.get(
                "/ui/biblioteca/buscar-saga?saga=patrulla&tradition=tebeo"
            )
        assert r.status_code == 200
        assert "La Patrulla X" in r.text
        assert "tradition=tebeo" in r.text
        assert f"story_arc_id={saga.id}" in r.text

    def test_contrato_antiguo_con_q_sigue_funcionando(self):
        personaje = Character(id=uuid4(), name="Mortadelo")
        session = FakeSession([FakeExecResult([personaje])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-personaje?q=morta")
        assert "Mortadelo" in r.text

    def test_los_parciales_no_se_cachean(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-personaje?personaje=morta")
        assert r.headers["Cache-Control"] == "no-store"

    def test_personaje_con_caracteres_de_control_se_limpia(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-personaje?personaje=%00morta%0A")
        assert r.status_code == 200
        assert "Sin coincidencias" in r.text


class TestPrivacidadYLogs:
    """AC-07: los GET no escriben ni dejan valores del coleccionista en logs."""

    def test_la_busqueda_no_aparece_en_los_registros(self):
        session = FakeSession([FakeExecResult(1), FakeExecResult([make_series("A")])])
        with capture_logs() as registros, use_fake_session(session) as client:
            client.get("/ui/biblioteca/resultados?q=secreto-mio&tradition=tebeo")
        assert "secreto-mio" not in " ".join(str(evento) for evento in registros)

    def test_el_error_solo_registra_la_clase(self):
        session = FakeSession(error=SQLAlchemyError("boom"))
        with capture_logs() as registros, use_fake_session(session) as client:
            client.get("/ui/biblioteca/resultados?q=secreto-mio")
        texto = " ".join(str(evento) for evento in registros)
        assert "secreto-mio" not in texto
        assert "SQLAlchemyError" in texto


class TestContextoDeRetorno:
    """BL-IT03 (#286): la tarjeta recuerda la URL canónica y su ancla."""

    def test_la_tarjeta_lleva_volver_y_ancla_a_si_misma(self):
        from urllib.parse import parse_qs, unquote, urlsplit
        series = make_series("Thorgal")
        session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca?q=thor&page=1")
        href = re.search(rf'<a class="library-card" id="serie-{series.id}" href="([^"]+)"', r.text)
        assert href is not None
        url = href.group(1).replace("&amp;", "&")
        destino = unquote(parse_qs(urlsplit(url).query)["volver"][0])
        assert urlsplit(destino).path == "/ui/biblioteca"
        assert parse_qs(urlsplit(destino).query)["q"] == ["thor"]
        assert urlsplit(destino).fragment == f"serie-{series.id}"


class TestVistaLista:
    """BL-IT02 (#284): vista compacta sobre el mismo catálogo y la misma página."""

    def _index(self, series, *, params=""):
        session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/biblioteca{params}")
        return r, session

    def test_la_lista_no_genera_portadas_y_muestra_titulo_completo(self):
        series = make_series("Un título bastante largo para comparar sin portada")
        r, session = self._index(series, params="?vista=lista")
        assert r.status_code == 200
        assert 'class="library-lista"' in r.text
        assert "Un título bastante largo para comparar sin portada" in r.text
        assert f"/ui/series/{series.id}/portada" not in r.text
        assert "/portada" not in r.text
        assert not session._queue

    def test_encabezados_y_estado_actual(self):
        r, _ = self._index(make_series("Batman"), params="?vista=lista")
        assert "<caption class=\"sr\">Series de la biblioteca</caption>" in r.text
        for cabecera in ("Título", "Año", "Tradición", "Números"):
            assert f'<th scope="col">{cabecera}</th>' in r.text
        assert 'id="control-vista" class="barra-vista barra-vista-grupo" role="group"' in r.text
        assert '<span class="barra-vista-texto">Tarjetas</span>' in r.text
        assert '<span class="barra-vista-texto">Lista</span>' in r.text
        assert 'aria-current="page"' in r.text
        assert 'aria-label="Tarjetas"' in r.text
        assert 'aria-label="Lista"' in r.text

    def test_valor_desconocido_no_se_convierte_en_cero(self):
        series = make_series("Sin datos")
        series.start_year = None
        series.total_issues = None
        r, _ = self._index(series, params="?vista=lista")
        assert '<td data-label="Números">No consta</td>' in r.text
        assert '<td data-label="Año">No consta</td>' in r.text
        assert ">0</td>" not in r.text

    def test_misma_serie_y_misma_pagina_al_cambiar_de_vista(self):
        series = make_series("Batman")
        tarjetas, _ = self._index(series)
        lista, _ = self._index(series, params="?vista=lista")
        assert f'id="serie-{series.id}"' in tarjetas.text
        assert f'id="serie-{series.id}"' in lista.text
        assert "library-grid" in tarjetas.text
        assert "library-grid" not in lista.text

    def test_conserva_filtros_pagina_y_vuelta(self):
        series = make_series("Thorgal")
        session = FakeSession([
            FakeExecResult([]), FakeExecResult(50), FakeExecResult([series]),
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca?q=thor&tradition=tebeo&page=2&vista=lista")
        for parte in ("q=thor", "tradition=tebeo", "page=2", "vista=lista"):
            assert parte in r.text
        assert "page=3" in r.text
        assert "volver=%2Fui%2Fbiblioteca" in r.text

    def test_una_vista_invalida_vuelve_a_tarjetas_con_aviso(self):
        series = make_series("Batman")
        r, _ = self._index(series, params="?vista=inventada")
        assert "La presentación pedida no existe; se muestran tarjetas." in r.text
        assert "library-grid" in r.text and "library-lista" not in r.text

    def test_el_fragmento_lista_no_repite_layout(self):
        series = make_series("Batman")
        session = FakeSession([FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?vista=lista")
        assert "library-lista" in r.text and "ZascArr" not in r.text
        assert not session._queue


class TestOrdenDeterminista:
    """#284: con el mismo título/año, el id desempata; no se depende del orden de la BD."""

    @pytest.mark.asyncio
    async def test_el_servicio_desempata_por_id(self):
        from tests.test_series_service import FakeExecResult as SSResult
        from tests.test_series_service import FakeSession as SSSession
        from zascarr.services.series import SeriesService

        class Capturing(SSSession):
            def __init__(self, queue):
                super().__init__(queue)
                self.statements = []

            async def execute(self, statement):
                self.statements.append(str(statement))
                return await super().execute(statement)

        session = Capturing([SSResult(0), SSResult([])])
        await SeriesService(session).list_series()
        consulta = " ".join(session.statements)
        assert "ORDER BY coalesce(series.sort_title, series.title_norm)" in consulta
        assert "series.start_year" in consulta
        assert "series.id" in consulta


class TestEtiquetasBiblioteca:
    """BL-ETQ1b (#431): etiquetas como filtro más sobre #rejilla."""

    def test_filtra_y_excluye_con_chips(self):
        from zascarr.models import Tag
        tag = Tag(id=uuid4(), name="noir", namespace="etiqueta", name_norm="noir")
        escuela = Tag(id=uuid4(), name="escuela", namespace="etiqueta", name_norm="escuela")
        series = make_series("Noir")
        session = FakeSession([
            FakeExecResult([tag, escuela]),     # resolver
            FakeExecResult(1),                  # count
            FakeExecResult([series]),           # página
            FakeExecResult([(tag, 1)]),         # facetas
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?etiquetas=noir+-escuela")
        assert r.status_code == 200
        assert "noir" in r.text and "Sin escuela" in r.text
        assert "No conocemos la etiqueta" not in r.text
        assert "facetas-biblioteca" in r.text
        assert "1 serie con noir" in r.text

    def test_etiqueta_desconocida_no_rompe(self):
        session = FakeSession([
            FakeExecResult([]),                 # resolver
            FakeExecResult(0),                  # count
            FakeExecResult([]),                 # página
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?etiquetas=noirx")
        assert r.status_code == 200
        assert "No conocemos la etiqueta «noirx»" in r.text
        assert "Tu biblioteca todavía no tiene series." in r.text

    def test_sugerencias_muestran_conteo_y_acciones(self):
        from zascarr.models import Tag
        tag = Tag(id=uuid4(), name="noir", namespace="etiqueta", name_norm="noir")
        session = FakeSession([FakeExecResult([(tag, 34)])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/etiquetas/sugerir?etiquetas=noi")
        assert r.status_code == 200
        assert "noir" in r.text and "34 series" in r.text
        assert "Añadir" in r.text and "Excluir" in r.text
        assert "etiquetas=noir" in r.text and "etiquetas=-noir" in r.text


    def test_la_tarjeta_muestra_el_progreso_de_lectura(self):
        series = make_series("Batman")
        session = FakeSession([
            FakeExecResult([]),
            FakeExecResult(1),
            FakeExecResult([(series, 3, 8)]),   # (serie, leídos, total)
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert 'role="progressbar"' in r.text
        assert "38% leído · 3 de 8" in r.text
        assert 'aria-valuenow="38"' in r.text


def test_endpoint_previa_generica_200_404_y_fallback(monkeypatch):
    from pathlib import Path
    from unittest.mock import patch

    series = make_series("Batman")
    session = FakeSession()

    async def get(_modelo, clave):
        return series if clave == series.id else None

    session.get = get
    monkeypatch.setattr("zascarr.web.series.portada_cacheada", lambda *_a: None)
    with use_fake_session(session) as client:
        with patch("zascarr.web.series.portada_cacheada", return_value=Path("/covers/x.jpg")):
            r = client.get(f"/ui/series/{series.id}/previa")
            assert r.status_code == 200
            assert f"/ui/series/{series.id}/portada" in r.text
            assert r.headers["cache-control"] == "no-store"
        r404 = client.get(f"/ui/series/{uuid4()}/previa")
        assert r404.status_code == 404
