# ruff: noqa: E501
"""BL-OPS1 FR-32 / T-17 / AC-31: la app y el auxiliar del host no pueden divergir en el protocolo."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from zascarr.models import CodigoOps, OpsAccion
from zascarr.services import ops_host

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("zascarr_ops_paridad", RAIZ / "deploy" / "ops" / "zascarr_ops.py")
aux = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aux)


def test_acciones_y_codigos_coinciden():
    assert {a.value for a in OpsAccion} == {aux.ACCION_COPIA, aux.ACCION_RESTAURAR}
    assert set(aux.UNIDADES) == {aux.ACCION_COPIA, aux.ACCION_RESTAURAR}
    assert {c.value for c in CodigoOps} == set(aux.CODIGOS)


def test_limites_y_version_coinciden():
    assert ops_host.VERSION == aux.VERSION
    assert ops_host.VERSION_RESTAURAR == aux.VERSION_RESTAURAR
    assert ops_host.MAX_BYTES_RESTAURAR == aux.MAX_BYTES_RESTAURAR
    assert ops_host.MAX_BYTES_V1 == aux.MAX_BYTES_V1
    assert ops_host.CADUCIDAD_S == aux.CADUCIDAD_S
    assert ops_host.PURGA_VISTOS_S == aux.PURGA_VISTOS_S
    assert ops_host.ENTRE_COPIAS_S == aux.ENTRE_COPIAS_S
    assert ops_host.LIMITE_DIARIO == aux.LIMITE_DIARIO
    assert ops_host.LIMITE_RESTAURACIONES == aux.LIMITE_RESTAURACIONES
    assert ops_host.ENTRE_RESTAURACIONES_S == aux.RESTAURACION_ESPERA_S


def test_la_firma_es_la_misma_y_el_orden_de_los_campos_tambien():
    clave = bytes(range(32))
    assert ops_host.firma_de(clave, 1, "a" * 32, "copia", 1_800_000_000) == aux.firma_de(clave, 1, "a" * 32, "copia", 1_800_000_000)
    assert ops_host.CLAVES_FIRMA == ("v", "id", "accion", "creada")


def test_una_peticion_de_la_app_la_acepta_el_esquema_del_auxiliar():
    linea, id_ = ops_host.construir_peticion(bytes(range(32)), ahora=1_800_000_000)
    cuerpo = aux.parsear(linea)
    assert cuerpo is not None and cuerpo["id"] == id_ and cuerpo["accion"] == "copia"
    assert cuerpo["firma"] == aux.firma_de(bytes(range(32)), 1, id_, "copia", 1_800_000_000)


def test_la_ruta_del_cerrojo_es_la_misma_en_los_tres_sitios():
    texto = (RAIZ / "scripts" / "_cerrojo.sh").read_text(encoding="utf-8")
    assert f'OPS_LOCK_FILE_PRODUCCION="{aux.RUTA_CERROJO}"' in texto
    assert ops_host.RUTA_CERROJO == aux.RUTA_CERROJO


def test_el_mensaje_de_demasiado_pronto_sale_de_la_constante():
    assert f"{aux.ENTRE_COPIAS_S // 60} minutos" in ops_host.MENSAJES_PEDIR[CodigoOps.DEMASIADO_PRONTO]


def test_cada_codigo_rechazado_tiene_mensaje_y_aceptada_no():
    assert set(ops_host.MENSAJES_PEDIR) == set(CodigoOps) - {CodigoOps.ACEPTADA}


def test_completitud_de_causas_ac45():
    """Todo código que los scripts pueden escribir y todo el de `_BACKUP_ERRORES` tiene causa; no sobra ninguna."""
    from zascarr.api.health import _BACKUP_ERRORES

    emitidos: set[str] = set()
    patron = re.compile(r'(?:OFFSITE_ERROR|ANCHOR_ERROR|VERIFY_ERROR_CODE|codigo)="([a-z_]+)"|escribir_estado "(?:failed|degraded)" "([a-z_]+)"')
    for f in (RAIZ / "scripts").glob("*.sh"):
        for a, b in patron.findall(f.read_text(encoding="utf-8")):
            emitidos.add(a or b)
    assert emitidos, "la búsqueda no encontró ningún código: el patrón ya no vale"
    assert emitidos <= set(_BACKUP_ERRORES)
    assert emitidos <= set(ops_host.CAUSAS_COPIA)
    assert set(ops_host.CAUSAS_COPIA) | ops_host.RESERVADOS_NO_EMITIDOS == set(_BACKUP_ERRORES)
    assert {"status_write_failed"} == ops_host.RESERVADOS_NO_EMITIDOS


def test_los_umbrales_de_fallos_y_bloqueo_coinciden_con_la_app():
    """AC-39/F-08: 5 fallos/15 min y bloqueo de 30 min son los mismos en el auxiliar y en la app."""
    from zascarr.services import reautenticacion

    assert aux.UMBRAL_FALLOS == reautenticacion.UMBRAL_FALLOS
    assert aux.VENTANA_FALLOS_S == reautenticacion.VENTANA_S
    assert aux.BLOQUEO_FALLOS_S == reautenticacion.BLOQUEO_S


def test_la_firma_v2_y_la_peticion_de_restaurar_coinciden():
    clave = bytes(range(32))
    assert ops_host.firma_restaurar_de(clave, 2, "a" * 32, "backup-20260101_120000",
                                       1_800_000_000, "secreta") == aux.firma_de(
        clave, 2, "a" * 32, "restaurar", 1_800_000_000,
        "backup-20260101_120000", "secreta")
    linea, id_ = ops_host.construir_peticion_restaurar(
        clave, "backup-20260101_120000", "secreta", ahora=1_800_000_000)
    cuerpo = aux.parsear(linea)
    assert cuerpo is not None and cuerpo["id"] == id_ and cuerpo["v"] == 2
    assert cuerpo["prueba"] == "secreta"
