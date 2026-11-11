"""BL-R5 (#234): pantalla de resolución por identificador (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import (
    CAPACIDAD_DETALLE,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
    DiscoveryResult,
    EstadoFuente,
)
from zascarr.services.identificadores import Identificador, ResolucionIdentificador

SECRETO = "secreto-de-prueba-identificador"


def _cliente():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def _resultado() -> DiscoveryResult:
    return DiscoveryResult(
        source=MetadataSource.COMIC_VINE, external_id="12345", title="Superman",
        start_year=1987, description="<p>Una serie.</p>", cover_url=None,
        site_url="https://comicvine.gamespot.com/volume/4050-12345/",
        tradition_guess=ComicTradition.AMERICAN)


def _resolver(resolucion):
    return patch("zascarr.web.discovery.DiscoveryService.resolver_identificador",
                 AsyncMock(return_value=resolucion)), \
           patch("zascarr.web.discovery.get_settings",
                 lambda: SimpleNamespace(secret_key=SECRETO))


def test_una_serie_encontrada_por_identificador_pide_confirmacion():
    ident = Identificador(MetadataSource.COMIC_VINE, "12345")
    resolucion = ResolucionIdentificador(
        camino="identificador", identificador=ident, resultado=_resultado(),
        estado=EstadoFuente(fuente="comic_vine", capacidad=CAPACIDAD_DETALLE,
                            estado=FUENTE_OK),
        motivo="Encontrada por identificador en comic_vine.")
    p1, p2 = _resolver(resolucion)
    c = _cliente()
    try:
        with p1, p2:
            r = c.get("/ui/descubrir/identificador", params={"identificador": "cv:12345"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Encontrada por identificador" in r.text
    assert "sin buscar por título" in r.text
    assert "name=\"candidata\"" in r.text          # candidata firmada, no alta automática
    assert "Superman" in r.text


def test_un_error_de_la_fuente_no_se_presenta_como_inexistente():
    ident = Identificador(MetadataSource.COMIC_VINE, "12345")
    resolucion = ResolucionIdentificador(
        camino="error", identificador=ident,
        estado=EstadoFuente(fuente="comic_vine", capacidad=CAPACIDAD_DETALLE,
                            estado=FUENTE_FALLO_TRANSITORIO,
                            motivo="No ha respondido ahora mismo."),
        motivo="No ha respondido ahora mismo.")
    p1, p2 = _resolver(resolucion)
    c = _cliente()
    try:
        with p1, p2:
            r = c.get("/ui/descubrir/identificador", params={"identificador": "cv:12345"})
    finally:
        _cerrar()
    assert "No ha respondido ahora mismo" in r.text
    assert "no existe" not in r.text.lower()
    assert "candidata" not in r.text


def test_un_identificador_inexistente_si_lo_dice_sin_ofrecer_candidata():
    ident = Identificador(MetadataSource.GCD, "999")
    resolucion = ResolucionIdentificador(
        camino="sin_resultado", identificador=ident,
        estado=EstadoFuente(fuente="gcd", capacidad=CAPACIDAD_DETALLE,
                            estado=FUENTE_SIN_RESULTADOS,
                            motivo="La fuente ha respondido, pero ese identificador no existe."),
        motivo="Ese identificador no existe en la fuente.")
    p1, p2 = _resolver(resolucion)
    c = _cliente()
    try:
        with p1, p2:
            r = c.get("/ui/descubrir/identificador", params={"identificador": "gcd:999"})
    finally:
        _cerrar()
    assert "no existe" in r.text.lower()
    assert "candidata" not in r.text


def test_una_forma_invalida_avisa_sin_consultar():
    resolucion = ResolucionIdentificador(
        camino="invalido", motivo="Pega un identificador o el enlace de una ficha.")
    p1, p2 = _resolver(resolucion)
    c = _cliente()
    try:
        with p1, p2:
            r = c.get("/ui/descubrir/identificador", params={"identificador": ""})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Pega un identificador" in r.text


def test_una_serie_ya_local_enlaza_sin_ofrecer_candidata():
    ident = Identificador(MetadataSource.TEBEOSFERA, "superman")
    local = SimpleNamespace(id=uuid4(), title="Superman")
    resolucion = ResolucionIdentificador(
        camino="ya_local", identificador=ident, ya_local=local,
        motivo="Esa serie ya está en tu biblioteca.")
    p1, p2 = _resolver(resolucion)
    c = _cliente()
    try:
        with p1, p2:
            r = c.get("/ui/descubrir/identificador", params={"identificador": "tb:superman"})
    finally:
        _cerrar()
    assert f"/ui/series/{local.id}" in r.text
    assert "ya está en tu biblioteca" in r.text
