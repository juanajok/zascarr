# ruff: noqa: E501
"""BL-OPS2 (#443): validación manual, reautenticación y oferta de restaurar."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zascarr.models import CodigoOps
from zascarr.services import restauracion
from zascarr.services.reautenticacion import Reauth, ResultadoReauth

COPIA = "backup-20260101_120000"
BUENA = [{"id": COPIA, "revision": "0046", "verificada": True}]


@pytest.fixture()
def ajustes(monkeypatch):
    s = SimpleNamespace(auth_mode="password")
    monkeypatch.setattr(restauracion.ops_host, "leer_copias", lambda _s: BUENA)
    monkeypatch.setattr(restauracion.ops_host, "resolver_estado",
                        lambda _s: SimpleNamespace(en_marcha=False))
    monkeypatch.setattr(restauracion, "revision_actual", AsyncMock(return_value="0046"))
    return s


def test_ofrece_solo_copias_verificadas_y_de_la_misma_revision():
    copias = [
        {"id": COPIA, "revision": "0046", "verificada": True},
        {"id": "backup-20260102_120000", "revision": "0045", "verificada": True},
        {"id": "backup-20260103_120000", "revision": "0046", "verificada": False},
    ]
    salida = restauracion.ofrecer(copias, "0046", "password")
    assert [c["restaurable"] for c in salida] == [True, False, False]
    assert "otra versión" in salida[1]["motivo"]


@pytest.mark.asyncio
async def test_orden_de_validacion(ajustes):
    db = object()
    assert (await restauracion.solicitar(
        db, ajustes, copia="../../x", contrasena="x", entiendo=True))[0] is CodigoOps.COPIA_DESCONOCIDA
    assert (await restauracion.solicitar(
        db, ajustes, copia=COPIA, contrasena="", entiendo=True))[0] is CodigoOps.PRUEBA_INVALIDA
    assert (await restauracion.solicitar(
        db, ajustes, copia=COPIA, contrasena="x" * 513, entiendo=True))[0] is CodigoOps.PRUEBA_INVALIDA
    assert (await restauracion.solicitar(
        db, ajustes, copia=COPIA, contrasena="x", entiendo=False))[0] is CodigoOps.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_sin_contrasena_activada_no_contacta(ajustes, monkeypatch):
    ajustes.auth_mode = "none"
    llamada = AsyncMock(return_value=CodigoOps.ACEPTADA)
    monkeypatch.setattr(restauracion.ops_host, "pedir_restaurar", llamada)
    codigo, _ = await restauracion.solicitar(
        object(), ajustes, copia=COPIA, contrasena="x", entiendo=True)
    assert codigo is CodigoOps.AUTENTICACION_NO_ACTIVADA and not llamada.called


@pytest.mark.asyncio
async def test_reauth_incorrecta_no_contacta(ajustes, monkeypatch):
    monkeypatch.setattr(restauracion, "comprobar_contrasena_actual",
                        AsyncMock(return_value=ResultadoReauth(Reauth.INCORRECTA)))
    llamada = AsyncMock(return_value=CodigoOps.ACEPTADA)
    monkeypatch.setattr(restauracion.ops_host, "pedir_restaurar", llamada)
    codigo, _ = await restauracion.solicitar(
        object(), ajustes, copia=COPIA, contrasena="mala", entiendo=True)
    assert codigo is CodigoOps.PRUEBA_INVALIDA and not llamada.called


@pytest.mark.asyncio
async def test_acierto_envia_una_peticion_v2(ajustes, monkeypatch):
    monkeypatch.setattr(restauracion, "comprobar_contrasena_actual",
                        AsyncMock(return_value=ResultadoReauth(Reauth.OK)))
    llamada = AsyncMock(return_value=CodigoOps.ACEPTADA)
    monkeypatch.setattr(restauracion.ops_host, "pedir_restaurar", llamada)
    codigo, mensaje = await restauracion.solicitar(
        object(), ajustes, copia=COPIA, contrasena="correcta", entiendo=True)
    assert codigo is CodigoOps.ACEPTADA and "en marcha" in mensaje
    llamada.assert_awaited_once()


def test_rutas_no_ecoan_la_contrasena_y_validan_el_id():
    from fastapi.testclient import TestClient

    from zascarr.main import app

    cliente = TestClient(app)
    assert cliente.get("/ui/copias/restaurar/no-es-una-copia").status_code == 404
    r = cliente.post("/ui/copias/restaurar", data={
        "copia": "backup-20260101_120000", "contrasena": "CENTINELA-SECRETO",
        "entiendo": ""})
    assert r.status_code == 200
    assert "CENTINELA-SECRETO" not in r.text
    assert "Marca que entiendes" in r.text
