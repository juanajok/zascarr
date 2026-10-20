# ruff: noqa: E501
"""Token `desvincular` (BL-R1a, ADR 0014): propósito propio, contexto = archivo, esquema estricto y tamaño acotado."""
from __future__ import annotations

import base64
import json
from uuid import uuid4

from zascarr.services.auth import sign_token
from zascarr.services.tokens_revision import (
    MAX_TOKEN_DESVINCULACION,
    PROPOSITO_DESVINCULAR,
    ArchivoFirmado,
    DesvinculacionFirmada,
    VinculacionFirmada,
    crear_token,
    crear_token_desvinculacion,
    crear_token_vinculacion,
    verificar_token_desvinculacion,
    verificar_token_vinculacion,
)

SECRETO = "clave-de-prueba-para-firmar"
AHORA = 1_800_000_000.0


def firmada(**kw) -> DesvinculacionFirmada:
    base = dict(file_id=str(uuid4()), issue_id=str(uuid4()), series_id=str(uuid4()), vinculo_operacion=str(uuid4()),
                huella="ab" * 32, operacion=str(uuid4()))
    return DesvinculacionFirmada(**{**base, **kw})


def _con_datos(d: DesvinculacionFirmada, **cambios) -> str:
    """Un token FIRMADO de verdad pero con los datos alterados: prueba el esquema, no la firma."""
    datos = {"version": 1, "issue_id": d.issue_id, "serie_id": d.series_id, "vinculo_operacion": d.vinculo_operacion,
             "huella": d.huella, "operacion": d.operacion, **cambios}
    datos = {k: v for k, v in datos.items() if v is not ...}
    return crear_token(PROPOSITO_DESVINCULAR, d.file_id, datos, SECRETO, ahora=AHORA)


def test_ida_y_vuelta():
    d = firmada()
    v = verificar_token_desvinculacion(crear_token_desvinculacion(d, SECRETO, ahora=AHORA), SECRETO, ahora=AHORA)
    assert v is not None and (v.file_id, v.issue_id, v.series_id, v.vinculo_operacion, v.huella, v.operacion) == (
        d.file_id, d.issue_id, d.series_id, d.vinculo_operacion, d.huella, d.operacion)


def test_caduca_a_los_15_minutos_y_se_puede_leer_caducado():
    t = crear_token_desvinculacion(firmada(), SECRETO, ahora=AHORA)
    assert verificar_token_desvinculacion(t, SECRETO, ahora=AHORA + 900 - 1) is not None
    assert verificar_token_desvinculacion(t, SECRETO, ahora=AHORA + 901) is None
    assert verificar_token_desvinculacion(t, SECRETO, ahora=AHORA + 901, ignorar_caducidad=True) is not None


def test_otra_clave_o_manipulado_no_vale():
    t = crear_token_desvinculacion(firmada(), SECRETO, ahora=AHORA)
    assert verificar_token_desvinculacion(t, "otra-clave", ahora=AHORA) is None
    assert verificar_token_desvinculacion(t[:-2] + "00", SECRETO, ahora=AHORA) is None
    assert verificar_token_desvinculacion("", SECRETO) is None and verificar_token_desvinculacion("basura", SECRETO) is None


def test_el_proposito_no_se_intercambia_con_vincular_ni_alta():
    d = firmada()
    desv = crear_token_desvinculacion(d, SECRETO, ahora=AHORA)
    assert verificar_token_vinculacion(desv, SECRETO, ahora=AHORA) is None                    # no sirve para vincular
    vinc = crear_token_vinculacion(VinculacionFirmada(
        "Carpeta", str(uuid4()), str(uuid4()), (ArchivoFirmado(str(uuid4()), "1", "single_issue", 1, 1),)), SECRETO, ahora=AHORA)
    assert verificar_token_desvinculacion(vinc, SECRETO, ahora=AHORA) is None                 # ni al revés
    ajeno = crear_token("alta", d.file_id, {"version": 1}, SECRETO, ahora=AHORA)
    assert verificar_token_desvinculacion(ajeno, SECRETO, ahora=AHORA) is None


def test_el_contexto_es_el_archivo_y_no_se_puede_cambiar():
    d = firmada()
    # El mismo cuerpo firmado con el contexto de OTRO archivo es otro token: el contexto se lee del propio token, así que
    # lo que se comprueba es que el `file_id` que sale es el firmado y que un contexto que no es un UUID no vale.
    assert verificar_token_desvinculacion(_con_datos(d), SECRETO, ahora=AHORA).file_id == d.file_id
    t = crear_token(PROPOSITO_DESVINCULAR, "no-es-un-uuid", {"version": 1}, SECRETO, ahora=AHORA)
    assert verificar_token_desvinculacion(t, SECRETO, ahora=AHORA) is None


def test_esquema_estricto():
    d = firmada()
    assert verificar_token_desvinculacion(_con_datos(d), SECRETO, ahora=AHORA) is not None
    for malo in (dict(version=2), dict(version="1"), dict(version=True), dict(issue_id="x"), dict(issue_id=None),
                 dict(serie_id=7), dict(vinculo_operacion="X" * 36), dict(operacion=""), dict(huella="AB" * 32),
                 dict(huella="ab" * 31), dict(huella=None), dict(huella=12)):
        assert verificar_token_desvinculacion(_con_datos(d, **malo), SECRETO, ahora=AHORA) is None, malo
    for ausente in ("version", "issue_id", "serie_id", "vinculo_operacion", "huella", "operacion"):
        assert verificar_token_desvinculacion(_con_datos(d, **{ausente: ...}), SECRETO, ahora=AHORA) is None, ausente


def test_datos_que_no_son_un_objeto_no_rompen():
    crudo = json.dumps({"p": PROPOSITO_DESVINCULAR, "c": str(uuid4()), "d": [1], "exp": int(AHORA) + 900}).encode()
    assert verificar_token_desvinculacion(sign_token(base64.urlsafe_b64encode(crudo).decode(), SECRETO), SECRETO, ahora=AHORA) is None


def test_el_limite_del_cuerpo_es_el_peor_caso_emitible():
    ident = "ffffffff-ffff-4fff-bfff-ffffffffffff"
    peor = crear_token_desvinculacion(DesvinculacionFirmada(ident, ident, ident, ident, "f" * 64, ident), "x" * 64, ahora=10**10)
    assert len(peor) <= MAX_TOKEN_DESVINCULACION < 700
    # Un token normal cabe con holgura.
    assert len(crear_token_desvinculacion(firmada(), SECRETO, ahora=AHORA)) <= MAX_TOKEN_DESVINCULACION
