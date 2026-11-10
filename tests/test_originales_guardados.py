"""BL-CNV2b: originales apartados de las conversiones (dónde, cuánto y liberar) en llano."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.conversion import ConversionDeArchivo
from zascarr.web import auditoria as web_aud

# ── Servicio: resumen (solo lectura del disco) ──────────────────────────────

def _servicio(tmp_path):
    return ConversionDeArchivo(None, secret="s",
                               settings=SimpleNamespace(library_path=tmp_path))


@pytest.mark.asyncio
async def test_resumen_cuenta_y_suma_los_originales(tmp_path):
    base = tmp_path / ".zascarr" / "originales"
    for carpeta, tamano in (("f1/o1", 1000), ("f2/o2", 2048)):
        destino = base / carpeta
        destino.mkdir(parents=True)
        (destino / "Tebeo.cbr").write_bytes(b"x" * tamano)

    assert await _servicio(tmp_path).resumen_originales() == (2, 3048)


@pytest.mark.asyncio
async def test_sin_originales_es_cero(tmp_path):
    assert await _servicio(tmp_path).resumen_originales() == (0, 0)


# ── Web: bloque de Duplicados y liberar con confirmación ────────────────────

class _Sesion:
    async def get(self, *_a, **_k):
        return None


class _Servicio:
    def __init__(self, *, originales=3, bytes_=3 * 1024 ** 3, borrados=300):
        self.originales, self.bytes, self.borrados = originales, bytes_, borrados
        self.vaciar_llamado: tuple | None = None

    async def resumen_originales(self):
        return self.originales, self.bytes

    async def vaciar_originales(self, lote):
        self.vaciar_llamado = (lote,)
        self.originales = max(0, self.originales - self.borrados)
        self.bytes = 0 if not self.originales else 1024
        return self.borrados


def _cliente(monkeypatch, servicio):
    async def _db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(web_aud, "ConversionDeArchivo", lambda *_a, **_k: servicio)
    return TestClient(app)


def test_el_bloque_explica_donde_esta_cuanto_ocupa_y_como_liberar(monkeypatch):
    servicio = _Servicio()
    cliente = _cliente(monkeypatch, servicio)
    try:
        r = cliente.get("/ui/auditoria/originales")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    texto = " ".join(r.text.split())
    assert "Originales guardados" in texto
    assert "carpeta oculta" in texto and ".zascarr" in texto
    assert ">3</strong> originales guardados" in texto
    assert ">3.0 GB</strong>" in texto
    assert 'name="confirmado"' in r.text
    assert 'hx-post="/ui/auditoria/originales/vaciar"' in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_liberar_sin_marcar_la_casilla_no_toca_nada(monkeypatch):
    servicio = _Servicio()
    cliente = _cliente(monkeypatch, servicio)
    try:
        r = cliente.post("/ui/auditoria/originales/vaciar", data={})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert "Marca la casilla" in r.text
    assert servicio.vaciar_llamado is None


def test_liberar_con_confirmacion_borra_una_tanda_y_cuenta_lo_que_queda(monkeypatch):
    servicio = _Servicio(originales=800, bytes_=8 * 1024 ** 3, borrados=500)
    cliente = _cliente(monkeypatch, servicio)
    try:
        r = cliente.post("/ui/auditoria/originales/vaciar", data={"confirmado": "1"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    assert servicio.vaciar_llamado == (web_aud.LOTE_LIBERAR,)
    assert "Liberados 500 originales" in r.text
    assert "Quedan 300" in r.text


def test_sin_originales_lo_dice_claro(monkeypatch):
    servicio = _Servicio(originales=0, bytes_=0)
    cliente = _cliente(monkeypatch, servicio)
    try:
        r = cliente.get("/ui/auditoria/originales")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert "No hay originales guardados" in r.text
    assert 'name="confirmado"' not in r.text
