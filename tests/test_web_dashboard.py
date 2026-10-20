"""
tests/test_web_dashboard.py

Suite del Inicio (vista principal /ui/): contrato HTTP y plantilla.
Las cifras (services/resumen.py) y los pasos (services/primeros_pasos.py, función pura) tienen sus
propias suites; aquí se comprueba que la plantilla PINTA lo que le dan, en cada estado, y que no
recalcula ni afirma de más. Las clases FakeSession/FakeResult las reutilizan otras suites.
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.inicio import Desglose, VistaInicio
from zascarr.services.library_adopter import EstadoAdopcion
from zascarr.services.primeros_pasos import (
    EstadoInicio,
    InformeDisco,
    calcular_primeros_pasos,
)
from zascarr.services.resumen import Completitud, ResumenBiblioteca


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeResult:
    """Resultado de una query: soporta .scalar(), .all() y .scalars().all()."""

    def __init__(self, *, scalar=None, rows=None, scalars=None):
        self._scalar = scalar
        self._rows = rows if rows is not None else []
        self._scalars = scalars if scalars is not None else []

    def scalar(self):
        return self._scalar

    def all(self):
        return self._rows

    def scalars(self):
        return _FakeScalars(self._scalars)


class FakeSession:
    def __init__(self, queue: list):
        self._queue = list(queue)

    async def execute(self, _statement):
        return self._queue.pop(0)


class CapturingSession(FakeSession):
    """Como FakeSession, pero guarda cada statement compilado — para
    verificar de verdad el WHERE que genera el código (B7: revisión de
    PR, 2026-09-26, sobre contadores de "lo tienes" sin filtrar
    is_missing), no solo lo que hace con una lista ya dada."""

    def __init__(self, queue: list):
        super().__init__(queue)
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return await super().execute(statement)


def _override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


FECHA = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


class _Primarios(HTMLParser):
    """Destinos de los `<a class="btn primary">`, separados según estén dentro de un <details>."""

    def __init__(self):
        super().__init__()
        self._details = 0
        self.dentro: list[str] = []
        self.fuera: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "details":
            self._details += 1
        if tag == "a" and "primary" in (a.get("class") or "").split():
            (self.dentro if self._details else self.fuera).append(a.get("href"))

    def handle_endtag(self, tag):
        if tag == "details":
            self._details -= 1


def _primarios_dentro_y_fuera_de_details(html: str) -> tuple[list[str], list[str]]:
    p = _Primarios()
    p.feed(html)
    return p.dentro, p.fuera


def vista(*, adopcion=EstadoAdopcion.SIN_TEBEOS, registrados=0, sin_clasificar=0, seguidas=0,
          informe=None, legal=False, fuente=False, series=0, con_archivos=0, con_recuento=0,
          huecos=0, completitud=None, ultimas=(), desglose=None, copias=0) -> VistaInicio:
    """`desglose` por defecto: lo registrado que no está por revisar, clasificado."""
    if desglose is None:
        desglose = Desglose(total=registrados, clasificados=max(registrados - sin_clasificar, 0),
                            por_revisar_presentes=min(sin_clasificar, registrados))
    pasos = calcular_primeros_pasos(EstadoInicio(
        adopcion=adopcion, archivos_registrados=registrados, archivos_sin_clasificar=sin_clasificar,
        series_seguidas=seguidas, informe=informe, aviso_legal_aceptado=legal,
        hay_fuente_de_busqueda=fuente))
    resumen = ResumenBiblioteca(
        total_series=series, series_con_archivos=con_archivos, archivos_registrados=registrados,
        series_con_recuento=con_recuento, huecos_pendientes=huecos, completitud=completitud,
        ultimas_series=tuple(ultimas))
    return VistaInicio(resumen=resumen, pasos=pasos, informe=informe,
                       archivos_sin_clasificar=sin_clasificar, registrados=desglose,
                       copias_descartadas=copias)


def pagina(v: VistaInicio) -> str:
    async def _cargar(_db):
        return v
    with use_fake_session(FakeSession([])) as client, \
            patch("zascarr.web.dashboard.cargar_inicio", _cargar):
        r = client.get("/ui/")
    assert r.status_code == 200
    return r.text


def texto(html: str, clase: str) -> str:
    """Texto visible del primer `<p class="{clase}">`, sin etiquetas ni espacios repetidos."""
    inicio = html.index(f'<p class="{clase}">')
    fragmento = html[inicio:html.index("</p>", inicio)]
    return " ".join(re.sub(r"<[^>]+>", "", fragmento).split())


class TestLayout:

    def test_responde_200_con_layout_htmx_y_nav(self):
        html = pagina(vista())
        assert "/static/vendor/htmx.min.js" in html
        # Nunca un CDN: ver docs/adr/0001-ui-stack.md.
        assert "cdn" not in html.lower()
        # V3: el menú es la barra de navegación nueva; sigue enlazando a Estado (/estado).
        assert '<nav class="nav" aria-label="Navegación principal">' in html
        assert 'href="/estado"' in html

    def test_un_solo_h1_y_es_inicio(self):
        html = pagina(vista())
        assert html.count("<h1>") == 1 and "<h1>Inicio</h1>" in html


class TestInstalacionNueva:
    """5 series · 0 % completitud · 0 pendientes eran ceros contradictorios (U2)."""

    def test_no_pinta_metricas_ni_porcentajes_ni_ceros(self):
        html = pagina(vista())
        assert "Tu colección ahora" not in html
        assert "metrics-grid" not in html
        assert "%" not in html.replace("100%", "")      # ni «0 %» ni «0%» en ninguna parte
        assert "Aún no hay tebeos en ZascArr" in html

    def test_ofrece_una_sola_accion_principal(self):
        html = pagina(vista())
        assert html.count('class="btn primary"') == 1
        assert 'class="btn primary" href="/ui/descubrir"' in html

    def test_el_paso_bloqueado_se_explica_sin_boton(self):
        html = pagina(vista())
        assert "No hemos encontrado tebeos (.cbz, .cbr)" in html
        assert "Aún no se puede" in html


class TestPasosEnLaPlantilla:

    def test_biblioteca_pendiente_es_la_accion_principal(self):
        html = pagina(vista(adopcion=EstadoAdopcion.PENDIENTE))
        assert 'class="btn primary" href="/ui/auditoria">Preparar mi biblioteca' in html
        assert html.count('class="btn primary"') == 1
        assert 'aria-current="step"' in html
        assert "Toca ahora" in html

    def test_con_pendientes_el_paso_cuenta_el_numero_y_enlaza(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=1542, sin_clasificar=137))
        assert "Revisa 137 tebeos que no hemos sabido clasificar" in html
        assert 'class="btn primary" href="/ui/pendientes">Revisar ahora' in html

    def test_los_opcionales_se_marcan_como_tales(self):
        html = pagina(vista(adopcion=EstadoAdopcion.PENDIENTE))
        assert html.count("Opcional") == 2

    def test_progreso_accesible_con_nombre(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=10, sin_clasificar=2))
        assert 'aria-label="Pasos hechos"' in html
        assert 'value="1"' in html and 'max="4"' in html

    def test_lo_basico_hecho_plega_la_lista(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=10))
        assert '<details class="pasos-plegados">' in html
        assert "Lo básico está hecho" in html

    def test_la_accion_recomendada_queda_fuera_del_bloque_plegado(self):
        """Un botón dentro de un <details> cerrado está en el HTML pero nadie lo ve ni lo alcanza
        con el teclado: con lo obligatorio hecho, la acción recomendada se ve SIN abrir nada."""
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=10))
        dentro, fuera = _primarios_dentro_y_fuera_de_details(html)
        assert fuera == ['/ui/descubrir'] and dentro == []

    def test_con_todo_hecho_y_sin_recomendacion_no_hay_botones_primarios(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=10, seguidas=2,
                            legal=True, fuente=True))
        assert _primarios_dentro_y_fuera_de_details(html) == ([], [])
        assert '<details class="pasos-plegados">' in html

    def test_la_lista_abierta_tiene_un_primario_y_fuera_de_details(self):
        html = pagina(vista(adopcion=EstadoAdopcion.PENDIENTE))
        assert _primarios_dentro_y_fuera_de_details(html) == ([], ["/ui/auditoria"])

    def test_el_boton_de_buscar_es_secundario(self):
        """Un envío ya no es amarillo por serlo (el amarillo es opt-in con `.primary`): el de
        buscar, que no es la acción principal del Inicio, no lo lleva."""
        html = pagina(vista())
        assert 'class="btn sm neutro">Buscar' in html
        inicio = html.index('id="q-inicio"')
        assert "primary" not in html[inicio:html.index("</form>", inicio)]

    def test_con_algo_por_hacer_la_lista_va_abierta(self):
        html = pagina(vista(adopcion=EstadoAdopcion.PENDIENTE))
        assert "pasos-plegados" not in html
        assert "Tu tebeoteca, paso a paso" in html


class TestProcedenciaDeLasCifras:

    def test_informe_sin_nada_registrado_no_pinta_ceros_junto_a_los_encontrados(self):
        """14 encontrados y «0 por revisar · nada sin clasificar» eran ceros contradictorios."""
        informe = InformeDisco(fecha=FECHA, archivos_leidos=14, archivos_comparados=4)
        html = pagina(vista(adopcion=EstadoAdopcion.PENDIENTE, informe=informe))
        assert "Tu colección ahora" not in html
        assert "nada sin clasificar" not in html
        assert texto(html, "subtitle") == "Aún no hay ningún tebeo registrado en ZascArr."
        assert texto(html, "procedencia muted") == "En tu disco había 14 el 3 de octubre de 2026."

    def test_sin_informe_dice_registrados_y_que_no_se_miro_el_disco(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=1542, series=3))
        assert "Tebeos registrados" in html
        assert "Tebeos encontrados" not in html
        assert texto(html, "procedencia muted") == (
            "Todavía no has mirado tu disco en busca de repetidos.")

    def test_con_informe_cita_fecha_y_distingue_de_los_registrados(self):
        informe = InformeDisco(fecha=FECHA, archivos_leidos=1542, archivos_comparados=432)
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=1500, series=3,
                            informe=informe))
        assert texto(html, "procedencia muted") == "En tu disco había 1542 el 3 de octubre de 2026."
        assert "Tebeos encontrados" not in html     # la tarjeta cuenta lo registrado, no el disco
        assert "432" not in html

    def test_un_informe_viejo_dice_cuanto_hace_y_ofrece_volver_a_mirar(self):
        """Caso real (2026-10-20): «Miramos tu disco el 28 de septiembre» sin más; nada decía que
        el dato tenía tres semanas ni cómo renovarlo desde el Inicio."""
        informe = InformeDisco(fecha=FECHA, archivos_leidos=1542, archivos_comparados=432)
        v = replace(vista(adopcion=EstadoAdopcion.HECHA, registrados=1325, informe=informe),
                    informe_hace="hace 3 semanas", informe_antiguo=True)
        html = pagina(v)
        assert "había <b>1542</b> el 3 de octubre de 2026 (hace 3 semanas)." in html
        assert '<a href="/ui/auditoria">Volver a mirar el disco</a>' in html

    def test_un_informe_reciente_no_invita_a_repetirlo(self):
        informe = InformeDisco(fecha=FECHA, archivos_leidos=1542, archivos_comparados=432)
        v = replace(vista(adopcion=EstadoAdopcion.HECHA, registrados=1325, informe=informe),
                    informe_hace="ayer", informe_antiguo=False)
        html = pagina(v)
        assert "(ayer)" in html
        assert "Volver a mirar el disco" not in html

    def test_informe_sin_adopcion_no_dice_que_la_biblioteca_este_registrada(self):
        informe = InformeDisco(fecha=FECHA, archivos_leidos=1542, archivos_comparados=432)
        html = pagina(vista(adopcion=EstadoAdopcion.PENDIENTE, informe=informe))
        assert "Tu biblioteca está registrada" not in html
        assert "Registra tu biblioteca" in html


class TestUnaCuentaQueCuadra:
    """Caso real (2026-10-20): «encontramos 1542 · registrados 1325», paso 1 «Hecho» y paso 2
    «Revisa 1322», sin que nada dijera cómo encajaban. Ahora la frase de entrada desglosa lo
    registrado en partes que suman el total, y lo del disco dice por qué no coincide."""

    CASO = Desglose(total=1325, clasificados=17, por_revisar_presentes=1308,
                    por_revisar_ausentes=14)

    def _caso(self, **kw):
        informe = InformeDisco(fecha=FECHA, archivos_leidos=1542, archivos_comparados=432)
        return pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=1325, sin_clasificar=1322,
                            informe=informe, desglose=self.CASO, series=3, **kw))

    def test_la_frase_de_entrada_desglosa_lo_registrado(self):
        assert texto(self._caso(), "subtitle") == (
            "Tienes 1325 tebeos registrados: 17 clasificados y 1308 por revisar. "
            "Otros 14 por revisar ya no están donde se registraron.")

    def test_cada_parte_enlaza_a_su_lista(self):
        html = self._caso()
        assert '<a href="/ui/biblioteca"><b>17</b> clasificados</a>' in html
        assert '<a href="/ui/pendientes"><b>1308</b> por revisar</a>' in html

    def test_el_paso_2_cuenta_la_lista_entera(self):
        assert "Revisa 1322 tebeos que no hemos sabido clasificar" in self._caso()

    def test_lo_del_disco_explica_las_copias_que_no_se_registraron(self):
        assert texto(self._caso(copias=217), "procedencia muted") == (
            "En tu disco había 1542 el 3 de octubre de 2026. Al registrarlos dejamos fuera "
            "217 copias idénticas: el mismo archivo no se registra dos veces.")

    def test_sin_copias_descartadas_no_inventa_explicacion(self):
        assert "copias idénticas" not in self._caso()

    def test_la_tarjeta_de_registrados_es_la_cifra_de_la_frase(self):
        html = self._caso()
        tarjeta = html[html.index('<div class="metric-card">'):]
        tarjeta = tarjeta[:tarjeta.index("</div>")]
        assert '<span class="metric-value">1325</span>' in tarjeta
        assert "17 ya clasificados" in tarjeta

    def test_el_paso_1_dice_que_clasificar_es_lo_siguiente(self):
        assert "clasificarlos es el paso siguiente" in self._caso()

    def test_cuatro_partes_con_comas_y_la_ultima_con_y(self):
        d = Desglose(total=10, clasificados=4, por_revisar_presentes=3, descartados=1)
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=10, sin_clasificar=3,
                            desglose=d))
        assert texto(html, "subtitle") == (
            "Tienes 10 tebeos registrados: 4 clasificados, 3 por revisar, "
            "2 con serie pero sin número y 1 descartado.")

    def test_una_sola_parte_dice_todos(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=5, sin_clasificar=5))
        assert texto(html, "subtitle") == "Tienes 5 tebeos registrados, todos por revisar."

    def test_un_solo_tebeo_en_singular(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=1))
        assert texto(html, "subtitle") == "Tienes 1 tebeo registrado, clasificado."


class TestHuecosYCompletitud:

    def test_sin_recuento_no_hay_porcentaje_ni_cero_huecos(self):
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=10, series=2,
                            con_archivos=2, con_recuento=0))
        assert "Aún no se pueden calcular" in html
        assert "Completitud" not in html
        assert "2 series sin recuento" in html
        assert "Números que te faltan" in html

    def test_con_recuento_dice_de_cuantas_series_y_cuantas_quedan_fuera(self):
        html = pagina(vista(
            adopcion=EstadoAdopcion.HECHA, registrados=60, series=5, con_archivos=5,
            con_recuento=2, huecos=38, completitud=Completitud(tienes=2, de=40, series=2)))
        assert "calculados en 2 series, según su recuento de grapas y la numeración actual" in html
        assert "Comic Vine" not in html.split("Números que te faltan")[1].split("</div>")[0]
        assert "tienes 2 de 40 (5 %)" in html
        assert "3 series sin recuento: de ellas no sabemos qué falta." in html

    def test_cero_huecos_con_series_sin_recuento_no_dice_coleccion_completa(self):
        html = pagina(vista(
            adopcion=EstadoAdopcion.HECHA, registrados=60, series=4, con_archivos=4,
            con_recuento=1, huecos=0, completitud=Completitud(tienes=10, de=10, series=1)))
        assert "3 series sin recuento" in html
        assert "completa" not in html.lower().replace("completitud", "")

    def test_un_cero_real_con_catalogo_si_se_muestra(self):
        html = pagina(vista(
            adopcion=EstadoAdopcion.HECHA, registrados=1, series=1, con_recuento=1, huecos=12,
            completitud=Completitud(tienes=0, de=12, series=1)))
        assert "tienes 0 de 12 (0 %)" in html


class TestBusquedaDeSeries:

    def test_formulario_get_a_descubrir_con_q(self):
        html = pagina(vista())
        assert '<form action="/ui/descubrir" method="get"' in html
        assert 'name="q"' in html
        assert "Buscar una serie" in html

    def test_ya_no_hay_busqueda_en_vivo_contra_deseados(self):
        html = pagina(vista())
        assert "/ui/wishlist/buscar-serie" not in html
        assert "resultados-wishlist" not in html

    def test_el_proposito_va_escrito_y_distingue_de_biblioteca(self):
        html = pagina(vista())
        assert "No busca entre lo que ya tienes" in html
        assert 'href="/ui/biblioteca">Biblioteca</a>' in html

    def test_la_caja_tiene_etiqueta_accesible(self):
        html = pagina(vista())
        assert 'for="q-inicio"' in html and 'id="q-inicio"' in html


class TestUltimasSeries:

    def test_pinta_las_series_y_portada_local(self):
        s = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011,
                   metadata_source=MetadataSource.COMIC_VINE.value)
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=2, series=1,
                            con_archivos=1, ultimas=[s]))
        assert "Batman" in html and f"/ui/series/{s.id}/portada" in html

    def test_ya_no_hay_tarjeta_de_actualizadas_recientemente(self):
        """Era len(ultimas), topado a 10: una cifra que no contaba lo que decía."""
        html = pagina(vista(adopcion=EstadoAdopcion.HECHA, registrados=2, series=1))
        assert "Actualizadas recientemente" not in html

    def test_sin_series_explica_cuando_apareceran(self):
        assert "Aún no hay series con archivos" in pagina(vista())
