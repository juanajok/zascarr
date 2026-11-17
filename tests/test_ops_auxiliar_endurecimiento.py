# ruff: noqa: E501
"""BL-OPS1, bloque 2: cierres de SecOps (F-3, F-4, F-5, N-2) y huecos de mutación de QA sobre el auxiliar."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from tests.test_ops_auxiliar import AHORA, CLAVE, Lanzador, _id, correr, estado, ops, peticion  # noqa: F401


# ── F-3: una unidad `failed` es libre; las ocupadas, no; las raras, falla cerrado ─────────────────
@pytest.mark.parametrize("salida,esperado", [
    ("inactive\n", "aceptada"), ("failed\n", "aceptada"),
    ("activating\n", "operacion_en_curso"), ("active\n", "operacion_en_curso"),
    ("reloading\n", "operacion_en_curso"), ("deactivating\n", "operacion_en_curso"),
    ("maintenance\n", "no_disponible"), ("", "no_disponible"), ("inactive failed\n", "no_disponible"),
    ("unknown\n", "no_disponible"),
])
def test_cada_estado_de_la_unidad_tiene_su_respuesta(estado, salida, esperado):
    lanz = Lanzador()
    lanz.estado_unidad = lambda unidad: salida.strip()
    r = ops.procesar(peticion(), AHORA, CLAVE, estado, lanz)
    assert r.codigo == esperado
    if esperado == "no_disponible":
        assert r.diario == "estado_unidad_desconocido" and lanz.iniciadas == []


def test_el_lanzador_lee_la_salida_de_is_active_no_el_codigo():
    def falso(args, **kw):
        return subprocess.CompletedProcess(args, 3, stdout="failed\n")        # `failed` sale con código 3

    assert ops.LanzadorSystemd(ejecutar=falso).estado_unidad("zascarr-backup.service") == "failed"


def test_las_llamadas_a_systemctl_llevan_los_mismos_descriptores_y_tiempo():
    """FR-09 / O18 / N-2: `is-active` y `start` con stdin y stderr a DEVNULL, `close_fds` y tiempo máximo de 5 s."""
    vistos = []

    def falso(args, **kw):
        vistos.append(kw)
        return subprocess.CompletedProcess(args, 0, stdout="inactive\n")

    lanz = ops.LanzadorSystemd(ejecutar=falso)
    lanz.estado_unidad("u")
    lanz.iniciar("u")
    for kw in vistos:
        assert kw["stdin"] == subprocess.DEVNULL and kw["stderr"] == subprocess.DEVNULL
        assert kw["close_fds"] is True and kw["timeout"] == 5 and not kw.get("shell")
    assert vistos[1]["stdout"] == subprocess.DEVNULL


def test_un_fallo_al_iniciar_no_consume_el_intento(estado):
    """FR-10 (reembolso, AC-50): si `systemctl start` falla no se anota en `aceptadas` y se puede reintentar enseguida,
    pero el `id` queda gastado (un solo uso)."""
    r, _ = correr(peticion(id_=_id(1)), estado, Lanzador(inicia=False))
    assert r.diario == "inicio_fallido" and not os.path.exists(estado.ruta_aceptadas)
    assert correr(peticion(id_=_id(1)), estado)[0].codigo == "repetida"
    assert correr(peticion(id_=_id(2)), estado)[0].codigo == "aceptada"


# ── F-4: nada de lo que llegue puede matar al auxiliar sin respuesta ──────────────────────────────
def test_un_sustituto_suelto_en_accion_es_esquema_invalido_sin_excepcion(estado):
    linea = ('{"v":1,"id":"%s","accion":"\\ud800","creada":%d,"firma":"%s"}\n' % (_id(1), AHORA, "0" * 64)).encode()
    assert ops.parsear(linea) is None
    r, lanz = correr(linea, estado)
    assert r.codigo == "esquema_invalido" and lanz.iniciadas == []


@pytest.mark.parametrize("fallo", [subprocess.TimeoutExpired("systemctl", 10), FileNotFoundError("systemctl")])
@pytest.mark.parametrize("donde", ["cerrojo_ocupado", "estado_unidad", "iniciar"])
def test_systemctl_que_falla_responde_no_disponible(estado, fallo, donde):
    class Roto(Lanzador):
        pass

    def lanza(*a, **k):
        raise fallo

    lanz = Roto()
    setattr(lanz, donde, lanza)
    r = ops.procesar(peticion(), AHORA, CLAVE, estado, lanz)
    assert r.codigo == "no_disponible" and r.diario == "systemctl_fallo"
    assert not os.path.exists(estado.ruta_aceptadas) and not os.path.exists(estado.ruta_ops_status)


def test_una_excepcion_inesperada_en_main_responde_no_disponible(monkeypatch, estado):
    escrito = []
    monkeypatch.setattr(ops, "leer_linea", lambda fd, tiempo_s=5: b"x\n")
    monkeypatch.setattr(ops, "leer_clave", lambda ruta: CLAVE)
    monkeypatch.setattr(ops, "uid_del_par", lambda fd: -1)
    monkeypatch.setattr(ops, "procesar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(os, "write", lambda fd, datos: escrito.append(datos) or len(datos))
    assert ops.main() == 0
    assert json.loads(escrito[0])["codigo"] == "no_disponible"
    assert "boom" not in json.dumps(escrito[0].decode())


# ── huecos de mutación de QA ──────────────────────────────────────────────────────────────────────
def test_la_firma_es_exactamente_hmac_de_v_id_accion_creada_con_barras():
    esperado = hmac.new(CLAVE, f"1|{'a' * 32}|copia|{AHORA}".encode(), hashlib.sha256).hexdigest()
    assert ops.firma_de(CLAVE, 1, "a" * 32, "copia", AHORA) == esperado
    assert ops.firma_de(CLAVE, 1, "a" * 32, "copia", AHORA) != ops.firma_de(CLAVE, 1, "a" * 32, "copia", AHORA + 1)


@pytest.mark.parametrize("id_", ["a" * 32 + "zz", "a" * 31, "a" * 33, "A" * 32, "a" * 32 + "\n", "../" + "a" * 29])
def test_el_id_se_valida_entero_no_por_prefijo(id_):
    """Un `id` con basura al final no puede llegar a la ruta de `vistos` (fullmatch, no match)."""
    cuerpo = {"v": 1, "id": id_, "accion": "copia", "creada": AHORA, "firma": "0" * 64}
    assert ops.parsear(json.dumps(cuerpo).encode() + b"\n") is None


def test_modos_de_los_ficheros_de_estado(estado):
    correr(peticion(id_=_id(1)), estado)
    assert stat.S_IMODE(os.stat(estado.ruta_aceptadas).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.join(estado.dir_vistos, _id(1))).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(estado.dir_vistos).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(estado.ruta_ops_status).st_mode) == 0o644
    assert stat.S_IMODE(os.stat(os.path.join(estado.dir_estado, "aceptacion.lock")).st_mode) == 0o600


def test_purga_de_vistos_a_los_300_s_y_poda_de_aceptadas_a_24_h(estado):
    correr(peticion(id_=_id(1)), estado)
    viejo = os.path.join(estado.dir_vistos, _id(1))
    correr(peticion(id_=_id(2), creada=AHORA + 301), estado, ahora=AHORA + 301)
    assert not os.path.exists(viejo)
    correr(peticion(id_=_id(3), creada=AHORA + 86400 + 400), estado, ahora=AHORA + 86400 + 400)
    assert all(t > AHORA + 400 for t in json.loads(Path(estado.ruta_aceptadas).read_text()))


@pytest.mark.parametrize("variante", ["firma", "caducada", "esquema", "repetida", "accion"])
def test_ninguna_rechazada_escribe_ops_status(estado, variante):
    if variante == "repetida":
        estado.marcar_visto(_id(9), AHORA)
    linea = {
        "firma": peticion(firma="0" * 64), "caducada": peticion(creada=AHORA - 500),
        "esquema": b"basura\n", "repetida": peticion(id_=_id(9)), "accion": peticion(accion="restaurar"),
    }[variante]
    r, _ = correr(linea, estado)
    assert r.resultado == "rechazada" and not os.path.exists(estado.ruta_ops_status)


def test_si_la_aceptacion_esta_ocupada_mas_de_5_s_es_no_disponible_y_no_se_cuenta(estado, monkeypatch):
    import fcntl

    monkeypatch.setattr(ops, "BLOQUEO_ESPERA_S", 0.2)
    monkeypatch.setattr(estado, "bloqueo", lambda espera_s=0.2, _b=estado.bloqueo: _b(0.2))
    fd = os.open(os.path.join(estado.dir_estado, "aceptacion.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        r, lanz = correr(peticion(), estado)
    finally:
        os.close(fd)
    assert r.codigo == "no_disponible" and r.diario == "aceptacion_ocupada" and lanz.iniciadas == []
    assert not os.path.exists(estado.ruta_aceptadas) and not os.path.exists(estado.ruta_ops_status)
