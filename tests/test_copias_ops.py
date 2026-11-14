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


def test_estado_en_marcha_sondea_y_no_recambia_el_boton_ni_el_listado(cliente):
    c, a = cliente
    r = c.get("/ui/copias/estado")
    assert r.status_code == 200 and 'hx-trigger="every 5s"' not in r.text
    _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time()) - 30})
    r = c.get("/ui/copias/estado")
    assert 'hx-trigger="every 5s"' in r.text and "Copia en marcha" in r.text
    assert 'id="copia-accion"' not in r.text                        # el botón ya está deshabilitado: no se recambia
    assert "copias-items" not in r.text and "<details" not in r.text   # el sondeo no toca el listado
    assert r.headers["cache-control"] == "no-store"


def test_al_terminar_el_sondeo_recambia_boton_y_listado_por_piezas_sin_cerrar_el_details(cliente):
    c, a = cliente
    _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time()) - 60})
    _escribir(a, "status.json", {"status": "ok", "last_attempt_at_epoch": int(time.time()) - 5})
    _escribir(a, "copias.json", {"schema": 1, "copias": [{"creada_epoch": int(time.time()) - 5, "bytes": 1024, "fuera_del_disco": False}]})
    t = c.get("/ui/copias/estado").text
    assert 'hx-trigger="every 5s"' not in t
    assert 'id="copia-accion" hx-swap-oob="outerHTML"' in t and "disabled" not in t
    assert 'id="copias-n" hx-swap-oob="outerHTML"' in t and 'id="copias-items" hx-swap-oob="outerHTML"' in t
    assert "<details" not in t and "aria-live" not in t                # nunca se recambia el <details> ni la zona viva


def test_pedir_acepta_deshabilita_el_boton_y_lleva_el_foco_al_estado(cliente, monkeypatch):
    c, a = cliente

    async def aceptar(s):
        _escribir(a, "ops-status.json", {"schema": 1, "pedida_epoch": int(time.time())})
        return CodigoOps.ACEPTADA

    monkeypatch.setattr(ops_host, "pedir_copia", aceptar)
    t = c.post("/ui/copias/pedir").text
    assert 'id="copia-estado"' in t and 'tabindex="-1" autofocus' in t
    assert 'id="boton-copia"' in t and "disabled" in t and 'aria-describedby="copia-garantia copia-estado"' in t
    assert "aria-live" not in t


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
    assert 'id="copia-accion"' not in r.text and 'autofocus' not in r.text      # el botón sigue habilitado y con el foco


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
    assert "Copias guardadas" in t and '<span id="copias-n">(1)</span>' in t and "también en el disco de respaldo: sí" in t
    bloque = t[t.index('<section id="copias"'):]
    bloque = bloque[:bloque.index("</section>")]
    assert "Más información" in bloque and "Para quien instaló ZascArr" not in bloque and "sudo bash" not in bloque   # ya está activado
    # la zona aria-live contiene #copia-estado: lo recambiado queda dentro y la zona no se recambia
    assert t.index('id="copia-anuncio" aria-live="polite"') < t.index('id="copia-estado"')
    assert "primary" not in t[t.index('id="boton-copia"') - 120:t.index('id="boton-copia"') + 80]   # el botón es neutro


def test_sin_auxiliar_el_detalle_dice_como_activarlo(ajustes, monkeypatch):
    from zascarr.main import app

    monkeypatch.setattr(ops_host, "auxiliar_disponible", lambda s: False)
    r = TestClient(app).get("/ui/copias/estado")
    assert "no está activado" in r.text
    v = ops_host.resolver_estado(ajustes.s, AHORA, disponible=False)
    html = web_copias_bloque(v)
    assert "Para quien instaló ZascArr" in html and "sudo bash scripts/instalar_ops.sh" in html


def web_copias_bloque(v):
    from zascarr.web.copias import templates

    return templates.get_template("_copias_bloque.html").render(v=v, copias=None, mensaje_pedir="", foco=False, oob_accion=False, oob=False)


# ── F-6 (SecOps): épocas desmesuradas ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("campo,fichero", [("last_attempt_at_epoch", "status.json"), ("omitida_epoch", "omitida.json"),
                                          ("pedida_epoch", "ops-status.json")])
def test_una_epoca_enorme_no_tumba_el_estado_ni_deja_en_marcha(ajustes, campo, fichero):
    _escribir(ajustes, fichero, {"status": "ok", campo: 10**20, "schema": 1})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.estado not in (EstadoCopia.EN_MARCHA,) and v.habilitado


def test_pedida_muy_en_el_futuro_no_deja_la_copia_en_marcha(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA + 10_000})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert not v.en_marcha and v.habilitado


def test_el_formateo_de_horas_no_falla_con_cifras_absurdas():
    assert isinstance(ops_host.hora_llana(10**20, AHORA), str)
    assert isinstance(ops_host._dia_llano(10**20), str)


def test_las_rutas_no_dan_500_con_epocas_enormes(cliente):
    c, a = cliente
    _escribir(a, "status.json", {"status": "ok", "last_attempt_at_epoch": 10**20})
    _escribir(a, "omitida.json", {"omitida_epoch": 10**20})
    _escribir(a, "copias.json", {"schema": 1, "copias": [{"creada_epoch": 10**20, "bytes": 5, "fuera_del_disco": True}]})
    assert c.get("/ui/copias/estado").status_code == 200
    assert c.post("/ui/copias/pedir").status_code == 200


# ── textos de resultado (UX) ─────────────────────────────────────────────────────────────────────
def test_el_fallo_no_repite_ni_se_contradice(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA - 600})
    _escribir(ajustes, "status.json", {"status": "failed", "error": "verify_failed", "last_attempt_at_epoch": AHORA - 300})
    m = ops_host.resolver_estado(ajustes.s, AHORA, True).mensaje
    assert m == ops_host.CAUSAS_COPIA["verify_failed"] and "falló" not in m
    _escribir(ajustes, "status.json", {"status": "failed", "error": "disk_full", "last_attempt_at_epoch": AHORA - 300})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.mensaje.startswith("La copia falló. No hay sitio") and v.nivel == "warn"


def test_manifest_failed_no_es_un_fallo_la_copia_es_valida(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "pedida_epoch": AHORA - 600})
    _escribir(ajustes, "status.json", {"status": "failed", "error": "manifest_failed", "last_attempt_at_epoch": AHORA - 300})
    v = ops_host.resolver_estado(ajustes.s, AHORA, True)
    assert v.estado == EstadoCopia.CON_AVISO and v.nivel == "amber"
    assert v.mensaje.startswith("Copia hecha ") and "con un aviso: no se pudo anotar en el registro de copias. Avisa a quien instaló ZascArr." in v.mensaje
    assert "falló" not in v.mensaje


def test_el_resultado_usa_el_componente_de_aviso_con_glifo(cliente):
    c, a = cliente
    _escribir(a, "status.json", {"status": "failed", "error": "disk_full", "last_attempt_at_epoch": int(time.time()) - 5})
    t = c.get("/ui/copias/estado").text
    assert "aviso warn" in t and 'aria-hidden="true">!</span>' in t
    assert 'role="alert"' not in t                                       # la zona aria-live ya lo anuncia
    assert 'class="caption"' not in t


def test_las_epocas_se_acotan_al_ano_2100():
    assert ops_host._epoch(10**20) is None and ops_host._epoch(ops_host.EPOCA_MAX + 1) is None
    assert ops_host._epoch(ops_host.EPOCA_MAX) == ops_host.EPOCA_MAX and ops_host._epoch(0) == 0
    assert ops_host._epoch(-1) is None and ops_host._epoch(True) is None and ops_host._epoch("5") is None
