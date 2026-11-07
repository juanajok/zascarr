"""#465 PR-1: detalle de edición de Tebeosfera y contraste sin red."""
from __future__ import annotations

import httpx
import pytest

from zascarr.models import IssueFormat, MetadataSource
from zascarr.services import detalle_edicion
from zascarr.services.detalle_edicion import (
    DetalleEdicion,
    DetalleEdicionService,
    contrastar,
)
from zascarr.services.estados_fuentes import CAPACIDAD_DETALLE
from zascarr.services.tebeosfera import (
    TebeosferaClient,
    TebeosferaColeccion,
    parse_collection,
)
from zascarr.utils import cortesia
from zascarr.utils.cortesia import CortesiaProceso


def fixture(nombre: str) -> str:
    from pathlib import Path
    return (Path(__file__).parent / "fixtures" / nombre).read_text(encoding="utf-8")


COLECCION = fixture("tebeosfera_coleccion_dragon_ball_1992.html")
SAGA = fixture("tebeosfera_saga_dragon_ball_1984.html")


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    async def dormir(self, s):
        self.t += s


class Ajustes:
    tebeosfera_rate_limit = 2.5
    tebeosfera_enabled = True


def cliente(transporte: httpx.BaseTransport, reloj: Reloj) -> TebeosferaClient:
    return TebeosferaClient(
        transporte=transporte, cortesia=CortesiaProceso(reloj=reloj, dormir=reloj.dormir),
        reloj=reloj, dormir=reloj.dormir,
    )


def test_parse_collection_extrae_campos_y_ausencias():
    detalle = parse_collection(COLECCION, url_ficha="https://www.tebeosfera.com/colecciones/db.html",
                               slug="db")
    assert detalle is not None
    assert (detalle.editorial, detalle.sello) == ("Grupo Planeta", "Planeta DeAgostini")
    assert (detalle.anio, detalle.anio_fin) == (1992, 1995)
    assert (detalle.numeracion_inicio, detalle.numeracion_fin) == (1, 153)
    assert detalle.formato_fuente == "CUADERNO / GRAPA [1-153]"
    assert detalle.pais == "ES"
    assert detalle.paginas is None
    assert detalle.numero_publicacion is None


def test_parse_saga_no_inventa_edicion():
    assert parse_collection(
        SAGA, url_ficha="https://www.tebeosfera.com/sagas/db.html", slug="db"
    ) is None


def test_parse_sin_entidad_no_lanza_y_deja_campos_ausentes():
    detalle = parse_collection(
        '<div class="row-fluid"><div>Fechas: 1992 - 1995</div>'
        '<div>Numeración: 1 a 153</div></div>',
        url_ficha="https://www.tebeosfera.com/colecciones/x.html", slug="x",
    )
    assert detalle is not None
    assert detalle.editorial is None and detalle.sello is None
    assert detalle.pais is None


@pytest.mark.asyncio
async def test_cliente_pide_una_sola_ficha_por_cortesia(monkeypatch):
    cortesia.reiniciar_para_pruebas()
    reloj = Reloj()
    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        return httpx.Response(200, text=COLECCION)

    monkeypatch.setattr("zascarr.services.tebeosfera.get_settings", lambda: Ajustes())
    monkeypatch.setattr("zascarr.config.get_settings", lambda: Ajustes())
    fake = cliente(httpx.MockTransport(handler), reloj)
    async with fake as c:
        detalle = await c.get_collection("db")
    assert detalle is not None
    assert peticiones == ["https://www.tebeosfera.com/colecciones/db.html"]
    assert detalle.peticiones == 1


@pytest.mark.asyncio
async def test_dos_fichas_se_espacian_por_la_cortesia_compartida(monkeypatch):
    cortesia.reiniciar_para_pruebas()
    reloj = Reloj()
    instantes = []
    peticiones = []

    def handler(request: httpx.Request) -> httpx.Response:
        instantes.append(reloj())
        peticiones.append(str(request.url))
        return httpx.Response(200, text=COLECCION)

    monkeypatch.setattr("zascarr.services.tebeosfera.get_settings", lambda: Ajustes())
    monkeypatch.setattr("zascarr.config.get_settings", lambda: Ajustes())
    fake = cliente(httpx.MockTransport(handler), reloj)
    async with fake as c:
        await c.get_collection("uno")
        await c.get_collection("dos")
    assert len(peticiones) == 2
    assert instantes[1] - instantes[0] >= 2.5


@pytest.mark.asyncio
async def test_servicio_mapea_apagada_sin_peticion(monkeypatch):
    monkeypatch.setattr(detalle_edicion, "fuente_habilitada", lambda _f: False)
    r = await DetalleEdicionService().detalle_tebeosfera("db")
    assert r.estado.capacidad == CAPACIDAD_DETALLE
    assert r.estado.estado == "fuente_apagada"
    assert r.detalle is None


@pytest.mark.asyncio
async def test_servicio_normaliza_y_marca_campos_ausentes(monkeypatch):
    monkeypatch.setattr(detalle_edicion, "fuente_habilitada", lambda _f: True)

    class FakeClient:
        async def get_collection(self, slug):
            return TebeosferaColeccion(
                slug=slug, url_ficha=f"https://www.tebeosfera.com/colecciones/{slug}.html",
                editorial="Planeta DeAgostini", anio=2006, pais="ES",
                numeracion_inicio=1, numeracion_fin=34,
                formato_fuente="cartoné", peticiones=1,
            )

    r = await DetalleEdicionService().detalle_tebeosfera("db", cliente=FakeClient())
    assert r.estado.estado == "ok"
    assert r.detalle is not None
    assert r.detalle.fuente is MetadataSource.TEBEOSFERA
    assert r.detalle.formato is IssueFormat.HARDCOVER
    assert "idioma" in r.detalle.campos_ausentes
    assert "numero_publicacion" in r.detalle.campos_ausentes


def etiqueta(**cambios):
    base = {
        "editorial": "Planeta DeAgostini", "anio": 2006, "numero": None,
        "pais": "ES", "idioma": "es", "formato": None,
        "identidad_acreditada": True, "unidad_esperada": "edicion",
    }
    base.update(cambios)
    return base


def detalle(**cambios) -> DetalleEdicion:
    base = dict(
        fuente=MetadataSource.TEBEOSFERA, external_id="db", metodo="tebeosfera.get_collection",
        editorial="Planeta DeAgostini", anio=2006, pais="ES", idioma=None,
        formato=None, campos_ausentes=frozenset({"idioma", "numero_publicacion"}),
        peticiones=1,
    )
    base.update(cambios)
    return DetalleEdicion(**base)


def test_contraste_verificado_con_editorial_y_anio():
    c = contrastar(detalle(), etiqueta())
    assert c.resultado == "coincidencia_verificada"
    assert c.campos_requeridos == ("editorial", "anio")


def test_contraste_anio_distinto_es_incorrecto():
    c = contrastar(detalle(anio=1992), etiqueta())
    assert c.resultado == "incorrecto"
    assert "anio_distinto" in c.motivos


def test_contraste_numero_ausente_es_ambiguo():
    c = contrastar(detalle(), etiqueta(numero="15", unidad_esperada="numero"))
    assert c.resultado == "ambiguo"
    assert "numero_ausente" in c.motivos


def test_contraste_editorial_parecida_es_ambigua():
    c = contrastar(detalle(editorial="Panini"), etiqueta(editorial="Panini España"))
    assert c.resultado == "ambiguo"
    assert "editorial_parecida" in c.motivos


def test_contraste_editorial_distinta_es_incorrecta():
    c = contrastar(detalle(editorial="Viz"), etiqueta())
    assert c.resultado == "incorrecto"
    assert "editorial_distinta" in c.motivos


def test_contraste_pais_distinto_es_incorrecto():
    c = contrastar(detalle(pais="US"), etiqueta())
    assert c.resultado == "incorrecto"
    assert "pais_distinto" in c.motivos


def test_contraste_formato_distinto_es_ambiguo():
    c = contrastar(detalle(formato=IssueFormat.SINGLE_ISSUE), etiqueta(formato="album"))
    assert c.resultado == "ambiguo"
    assert "formato_distinto" in c.motivos


def test_contraste_etiqueta_no_acreditada_no_da_veredicto():
    c = contrastar(detalle(), etiqueta(identidad_acreditada=False))
    assert c.resultado is None
    assert c.motivos == ("no_acreditada",)


def test_contraste_sin_detalle_no_da_veredicto():
    assert contrastar(None, etiqueta()).resultado is None
