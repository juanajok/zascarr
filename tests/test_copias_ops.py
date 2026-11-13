# ruff: noqa: E501
"""BL-OPS1 (bloque 3): `services/ops_host.py` y la interfaz de «Hacer una copia ahora» (AC-13…AC-24, AC-38/45)."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.models import CodigoOps
from zascarr.services import ops_host
from zascarr.services.ops_host import EstadoCopia

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("zascarr_ops_c", RAIZ / "deploy" / "ops" / "zascarr_ops.py")
aux = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aux)

CLAVE = bytes(range(32))
AHORA = 1_800_000_000


@pytest.fixture()
def ajustes(tmp_path, monkeypatch):
    estado = tmp_path / "estado"
    estado.mkdir()
    s = get_settings()
    for campo, nombre in (("backup_status_file", "status.json"), ("ops_status_file", "ops-status.json"),
                          ("copias_file", "copias.json"), ("omitida_file", "omitida.json")):
        monkeypatch.setattr(s, campo, str(estado / nombre))
    monkeypatch.setattr(s, "ops_socket_file", str(tmp_path / "ops.sock"))
    monkeypatch.setattr(s, "ops_key_file", str(tmp_path / "ops.key"))
    (tmp_path / "ops.key").write_text(CLAVE.hex() + "\n")
    return SimpleNamespace(s=s, dir=estado, tmp=tmp_path)


def _escribir(a, nombre: str, datos):
    (a.dir / nombre).write_text(json.dumps(datos))


# ── el estado (FR-22) ────────────────────────────────────────────────────────────────────────────
def test_sin_socket_no_activado_y_sin_boton(ajustes):
    v = ops_host.resolver_estado(ajustes.s, AHORA, disponible=False)
    assert v.estado == EstadoCopia.NO_ACTIVADO and not v.boton
    assert "no está activado en este equipo" in v.mensaje


def test_en_marcha_y_sin_noticias_a_los_35_minutos(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA - 60})
    _escribir(ajustes, "status.json", {"status": "ok", "last_attempt_at_epoch": AHORA - 86400})
    v = ops_host.resolver_estado(ajustes.s, AHORA, disponible=True)
    assert v.estado == EstadoCopia.EN_MARCHA and v.en_marcha and not v.habilitado
    v = ops_host.resolver_estado(ajustes.s, AHORA + 36 * 60 - 60, disponible=True)       # AC-19: 36 min
    assert v.estado == EstadoCopia.SIN_NOTICIAS and v.habilitado and not v.en_marcha
    assert "No hay noticias de la copia" in v.mensaje


def test_hecha_con_aviso_y_fallo_con_causa_cerrada(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA - 600})
    _escribir(ajustes, "status.json", {"status": "ok", "last_attempt_at_epoch": AHORA - 300})
    assert ops_host.resolver_estado(ajustes.s, AHORA, True).estado == EstadoCopia.HECHA        # AC-24
    _escribir(ajustes, "status.json", {"status": "failed", "error": "disk_full", "last_attempt_at_epoch": AHORA - 300})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.estado == EstadoCopia.FALLO and "Libera espacio" in v.mensaje
    _escribir(ajustes, "status.json", {"status": "degraded", "error": "anchor_sync_failed", "last_attempt_at_epoch": AHORA - 300})
    assert ops_host.resolver_estado(ajustes.s, AHORA, True).estado == EstadoCopia.CON_AVISO


def test_una_cadena_libre_del_fichero_no_se_pinta(ajustes):
    """AC-20 / C-13: un código que no está en el mapa sale como causa genérica, sin la cadena del fichero."""
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA - 600})
    _escribir(ajustes, "status.json", {"status": "failed", "error": "<script>CAUSA-INVENTADA", "last_attempt_at_epoch": AHORA - 300})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert "CAUSA-INVENTADA" not in v.mensaje and "No se sabe por qué falló" in v.mensaje
    for raro in (["x"], {"a": 1}, 7, None):
        _escribir(ajustes, "status.json", {"status": "failed", "error": raro, "last_attempt_at_epoch": AHORA - 300})
        assert "No se sabe por qué falló" in ops_host.resolver_estado(ajustes.s, AHORA, True).mensaje


def test_la_copia_pedida_que_no_arranco_por_omitida(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA - 120})
    _escribir(ajustes, "status.json", {"status": "ok", "last_attempt_at_epoch": AHORA - 86400})
    _escribir(ajustes, "omitida.json", {"schema": 1, "omitida_epoch": AHORA - 100, "motivo": "operacion_en_curso"})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.estado == EstadoCopia.NO_ARRANCO and v.habilitado and not v.en_marcha
    assert "había otra tarea en marcha" in v.mensaje


def test_la_copia_nocturna_omitida_se_dice_con_el_dia(ajustes):
    _escribir(ajustes, "status.json", {"status": "ok", "last_attempt_at_epoch": AHORA - 86400})
    _escribir(ajustes, "omitida.json", {"schema": 1, "omitida_epoch": AHORA - 100, "motivo": "operacion_en_curso"})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.nocturna_omitida.startswith("La copia de la noche del ") and "se omitió" in v.nocturna_omitida


def test_ficheros_ausentes_o_corruptos_no_fallan(ajustes):
    (ajustes.dir / "status.json").write_text("{no es json")
    (ajustes.dir / "ops-status.json").write_text("[1,2]")
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.estado == EstadoCopia.DIARIO and v.habilitado


def test_la_hora_se_pinta_en_la_zona_del_servidor(monkeypatch):
    """UX: hoy / ayer / fecha, según `TZ` del servidor; dos zonas en torno a la medianoche dan días distintos."""
    epoch = 1_799_999_400
    try:
        resultados = {}
        for tz in ("Europe/Madrid", "Pacific/Auckland"):
            monkeypatch.setenv("TZ", tz)
            time.tzset()
            resultados[tz] = ops_host.hora_llana(epoch, epoch + 60)
        assert resultados["Europe/Madrid"] != resultados["Pacific/Auckland"]
        monkeypatch.setenv("TZ", "Europe/Madrid")
        time.tzset()
        assert ops_host.hora_llana(epoch - 86400, epoch).startswith("ayer a las ")
        assert ops_host.hora_llana(epoch - 5 * 86400, epoch).startswith("el ")
    finally:
        monkeypatch.undo()
        time.tzset()


def test_el_listado_trae_fecha_tamano_y_nada_mas(ajustes):
    copias = [{"id": "backup-1", "creada_epoch": AHORA - i * 3600, "bytes": 1024 * 1024 * (i + 1),
               "fuera_del_disco": i % 2 == 0, "verificada": True, "ruta": "/secreto/ruta", "sha256": "ab" * 32}
              for i in range(40)]
    _escribir(ajustes, "copias.json", {"schema": 1, "copias": copias})
    lista = ops_host.leer_copias(ajustes.s, AHORA)
    assert len(lista) == 30                                  # AC-21
    assert set(lista[0]) == {"creada_epoch", "fecha", "tamano", "fuera_del_disco"}
    assert "secreto" not in json.dumps(lista) and "ab" * 32 not in json.dumps(lista)
    (ajustes.dir / "copias.json").write_text("roto")
    assert ops_host.leer_copias(ajustes.s, AHORA) is None
    (ajustes.dir / "copias.json").unlink()
    assert ops_host.leer_copias(ajustes.s, AHORA) is None


# ── el cliente (FR-19) ───────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cliente_sin_clave_o_sin_socket_es_no_disponible(ajustes):
    (ajustes.tmp / "ops.key").unlink()
    assert await ops_host.pedir_copia(ajustes.s) is CodigoOps.NO_DISPONIBLE
    (ajustes.tmp / "ops.key").write_text("zz")
    assert await ops_host.pedir_copia(ajustes.s) is CodigoOps.NO_DISPONIBLE
    (ajustes.tmp / "ops.key").write_text(CLAVE.hex())
    assert await ops_host.pedir_copia(ajustes.s) is CodigoOps.NO_DISPONIBLE          # el socket no existe


@pytest.mark.asyncio
async def test_cliente_respuesta_de_otro_id_o_rara_es_no_disponible(ajustes):
    async def otro_id(ruta, peticion):
        return json.dumps({"v": 1, "id": "0" * 32, "resultado": "aceptada", "codigo": "aceptada"}).encode() + b"\n"

    async def rara(ruta, peticion):
        return b"hola\n"

    async def inventado(ruta, peticion):
        id_ = json.loads(peticion)["id"]
        return json.dumps({"v": 1, "id": id_, "resultado": "x", "codigo": "otra_cosa"}).encode() + b"\n"

    for falso in (otro_id, rara, inventado):
        assert await ops_host.pedir_copia(ajustes.s, conversar=falso) is CodigoOps.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_cliente_tiempo_total(ajustes, monkeypatch):
    monkeypatch.setattr(ops_host, "TIEMPO_TOTAL_S", 0.2)

    async def colgado(ruta, peticion):
        await asyncio.sleep(30)

    t0 = time.monotonic()
    assert await ops_host.pedir_copia(ajustes.s, conversar=colgado) is CodigoOps.NO_DISPONIBLE
    assert time.monotonic() - t0 < 3


class _Lanzador:
    def __init__(self):
        self.iniciadas: list[str] = []

    def cerrojo_ocupado(self):
        return False

    def estado_unidad(self, unidad):
        return "inactive"

    def iniciar(self, unidad):
        self.iniciadas.append(unidad)
        return True


def _servidor_real(ruta: str, estado, lanzador):
    """Un socket Unix real con el `procesar` del auxiliar detrás (una conexión)."""
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(ruta)
    srv.listen(1)

    def atender():
        conn, _ = srv.accept()
        with conn:
            linea = aux.leer_linea(conn.fileno(), tiempo_s=2)
            r = aux.procesar(linea, int(time.time()), CLAVE, estado, lanzador)
            conn.sendall(r.linea())
        srv.close()

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    return hilo


@pytest.mark.asyncio
async def test_la_app_y_el_auxiliar_real_se_entienden_por_un_socket(ajustes):
    (ajustes.tmp / "run").mkdir()
    estado = aux.EstadoOps(str(ajustes.tmp / "run"), str(ajustes.dir))
    lanzador = _Lanzador()
    hilo = _servidor_real(str(ajustes.tmp / "ops.sock"), estado, lanzador)
    assert await ops_host.pedir_copia(ajustes.s) is CodigoOps.ACEPTADA
    hilo.join(3)
    assert lanzador.iniciadas == ["zascarr-backup.service"]
    assert json.loads((ajustes.dir / "ops-status.json").read_text())["resultado"] == "aceptada"


@pytest.mark.asyncio
async def test_el_cliente_no_registra_clave_firma_ni_cuerpo(ajustes):
    import structlog

    async def aceptar(ruta, peticion):
        id_ = json.loads(peticion)["id"]
        return json.dumps({"v": 1, "id": id_, "resultado": "aceptada", "codigo": "aceptada"}).encode() + b"\n"

    async def falla(ruta, peticion):
        raise OSError("/ruta/secreta")

    with structlog.testing.capture_logs() as logs:
        await ops_host.pedir_copia(ajustes.s, conversar=aceptar)
        await ops_host.pedir_copia(ajustes.s, conversar=falla)
    texto = json.dumps(logs, default=str)
    assert CLAVE.hex() not in texto and "firma" not in texto and "/ruta/secreta" not in texto
    assert {x["event"] for x in logs} == {"ops.copia_pedida", "ops.no_disponible"}


# ── la interfaz ──────────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def cliente(ajustes, monkeypatch):
    from zascarr.main import app

    monkeypatch.setattr(ops_host, "auxiliar_disponible", lambda s: True)
    return TestClient(app), ajustes


def test_estado_en_marcha_sondea_y_sin_marcha_no(cliente):
    c, a = cliente
    r = c.get("/ui/copias/estado")
    assert r.status_code == 200 and 'hx-trigger="every 5s"' not in r.text
    _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time()) - 30})
    r = c.get("/ui/copias/estado")
    assert 'hx-trigger="every 5s"' in r.text and "Copia en marcha" in r.text
    assert "disabled" in r.text                                            # el botón, por hx-swap-oob
    assert "Copias guardadas" not in r.text                               # el sondeo no recambia el listado
    assert r.headers["cache-control"] == "no-store"


def test_el_fragmento_no_lleva_la_zona_aria_live_y_el_boton_se_enlaza(cliente):
    c, a = cliente
    _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time()) - 30})
    t = c.get("/ui/copias/estado").text
    assert "aria-live" not in t                                           # la zona vive fuera de lo recambiado
    assert 'id="boton-copia"' in t and 'aria-describedby="copia-garantia copia-estado"' in t


def test_pedir_acepta_envia_una_peticion_y_dice_en_marcha(cliente, monkeypatch):
    c, a = cliente
    enviadas = []

    async def aceptar(s):
        enviadas.append(1)
        _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time())})
        return CodigoOps.ACEPTADA

    monkeypatch.setattr(ops_host, "pedir_copia", aceptar)
    r = c.post("/ui/copias/pedir")
    assert r.status_code == 200 and len(enviadas) == 1
    assert "Copia en marcha" in r.text and 'hx-trigger="every 5s"' in r.text      # AC-14


def test_pedir_con_copia_en_marcha_no_envia_nada(cliente, monkeypatch):
    c, a = cliente
    _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time()) - 10})
    enviar = AsyncMock(return_value=CodigoOps.ACEPTADA)
    monkeypatch.setattr(ops_host, "pedir_copia", enviar)
    r = c.post("/ui/copias/pedir")
    assert r.status_code == 200 and "Copia en marcha" in r.text
    enviar.assert_not_called()                                              # AC-18 / FR-24


@pytest.mark.parametrize("codigo,texto", [
    (CodigoOps.OPERACION_EN_CURSO, "otra tarea de mantenimiento"),
    (CodigoOps.DEMASIADO_PRONTO, "dentro de 5 minutos"),
    (CodigoOps.LIMITE_DIARIO, "máximo de copias en un día"),
    (CodigoOps.FIRMA_INVALIDA, "No se pudo pedir la copia"),
    (CodigoOps.NO_DISPONIBLE, "No se pudo pedir la copia"),
])
def test_cada_rechazo_se_dice_en_llano_sin_el_codigo(cliente, monkeypatch, codigo, texto):
    c, _ = cliente
    monkeypatch.setattr(ops_host, "pedir_copia", AsyncMock(return_value=codigo))
    r = c.post("/ui/copias/pedir")
    assert texto in r.text and codigo.value not in r.text


def test_sin_auxiliar_no_hay_boton_y_pedir_no_hace_nada(ajustes, monkeypatch):
    from zascarr.main import app

    monkeypatch.setattr(ops_host, "auxiliar_disponible", lambda s: False)
    enviar = AsyncMock()
    monkeypatch.setattr(ops_host, "pedir_copia", enviar)
    r = TestClient(app).post("/ui/copias/pedir")
    assert r.status_code == 200 and "boton-copia" not in r.text and "no está activado" in r.text
    enviar.assert_not_called()                                              # AC-13


def test_no_existe_ninguna_ruta_de_copias_bajo_api():
    """AC-16: ni `POST /api/copias/pedir` ni equivalente (ni en el esquema OpenAPI ni al llamarlas)."""
    from zascarr.main import app

    assert not any(p.startswith("/api") and "copia" in p for p in app.openapi()["paths"])
    assert "/ui/copias/pedir" in app.openapi()["paths"]
    c = TestClient(app)
    for ruta in ("/api/copias/pedir", "/api/copias", "/api/copia", "/api/ops/copia", "/api/copias/estado"):
        assert c.post(ruta).status_code in (404, 405), ruta


@pytest.mark.sin_origen
def test_pedir_desde_otro_origen_es_403(ajustes, monkeypatch):
    from zascarr.main import app

    r = TestClient(app, base_url="http://127.0.0.1:8000").post("/ui/copias/pedir", headers={"Origin": "https://mal.example"})
    assert r.status_code == 403


def test_estado_pinta_el_bloque_con_la_zona_aria_live_fuera(cliente, monkeypatch):
    from zascarr.database import get_db
    from zascarr.main import app
    from zascarr.web import estado as web_estado

    c, a = cliente
    _escribir(a, "copias.json", {"schema": 1, "copias": [{"creada_epoch": int(time.time()) - 60, "bytes": 5 * 1024 * 1024, "fuera_del_disco": True}]})

    async def _db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(web_estado.disponibilidad, "ultima_comprobacion", AsyncMock(return_value=SimpleNamespace(sin_dato=True)))
    monkeypatch.setattr(web_estado.disponibilidad, "contar_no_disponibles", AsyncMock(return_value=0))
    monkeypatch.setattr(web_estado.cobertura, "calcular", AsyncMock(side_effect=RuntimeError("x")))
    try:
        r = c.get("/estado")
    finally:
        app.dependency_overrides.pop(get_db, None)
    t = r.text
    assert r.status_code == 200
    assert "ZascArr guarda una copia de tus datos cada noche. Puedes hacer una ahora." in t
    assert "Copias guardadas (1)" in t and "también en el disco de respaldo: sí" in t
    assert "Para quien instaló ZascArr" in t and "sudo bash scripts/instalar_ops.sh" in t
    # la zona aria-live contiene #copia-estado: lo recambiado queda dentro y la zona no se recambia
    assert t.index('id="copia-anuncio" aria-live="polite"') < t.index('id="copia-estado"')
    assert "primary" not in t[t.index('id="boton-copia"') - 120:t.index('id="boton-copia"') + 80]   # el botón es neutro
