# ruff: noqa: E501
"""Token `retirar_serie` (BL-SER1, #303): propósito propio, contexto = serie, esquema estricto y tamaño acotado."""
from __future__ import annotations

import base64
import json
from uuid import uuid4

from zascarr.services.auth import sign_token
from zascarr.services.tokens_revision import (
    MAX_TOKEN_RETIRADA,
    PROPOSITO_ALTA,
    PROPOSITO_DESVINCULAR,
    PROPOSITO_RETIRAR,
    PROPOSITO_VINCULAR,
    RetiradaFirmada,
    crear_token,
    crear_token_retirada,
    verificar_token_desvinculacion,
    verificar_token_retirada,
    verificar_token_vinculacion,
)

SECRETO = "clave-de-prueba-para-firmar"
AHORA = 1_800_000_000.0


def firmada(**kw) -> RetiradaFirmada:
    base = dict(series_id=str(uuid4()), huella="ab" * 32, operacion=str(uuid4()))
    return RetiradaFirmada(**{**base, **kw})


def _con_datos(d: RetiradaFirmada, **cambios) -> str:
    datos = {"version": 1, "serie_id": d.series_id, "huella": d.huella, "operacion": d.operacion, **cambios}
    datos = {k: v for k, v in datos.items() if v is not ...}
    return crear_token(PROPOSITO_RETIRAR, d.series_id, datos, SECRETO, ahora=AHORA)


def test_ida_y_vuelta():
    d = firmada()
    v = verificar_token_retirada(crear_token_retirada(d, SECRETO, ahora=AHORA), SECRETO, ahora=AHORA)
    assert v is not None and (v.series_id, v.huella, v.operacion) == (d.series_id, d.huella, d.operacion)


def test_caduca_a_los_15_minutos_y_se_puede_leer_caducado():
    t = crear_token_retirada(firmada(), SECRETO, ahora=AHORA)
    assert verificar_token_retirada(t, SECRETO, ahora=AHORA + 15 * 60 - 1) is not None
    assert verificar_token_retirada(t, SECRETO, ahora=AHORA + 15 * 60 + 1) is None
    assert verificar_token_retirada(t, SECRETO, ahora=AHORA + 15 * 60 + 1, ignorar_caducidad=True) is not None


def test_otra_clave_o_manipulado_no_vale():
    t = crear_token_retirada(firmada(), SECRETO, ahora=AHORA)
    assert verificar_token_retirada(t, "otra-clave", ahora=AHORA) is None
    malo = t[:-1] + ("0" if t[-1] != "0" else "1")
    assert verificar_token_retirada(malo, SECRETO, ahora=AHORA) is None
    assert verificar_token_retirada("", SECRETO) is None and verificar_token_retirada("basura", SECRETO) is None


def test_el_proposito_no_se_intercambia():
    d = firmada()
    ret = crear_token_retirada(d, SECRETO, ahora=AHORA)
    # un token de otro propósito no se acepta como retirada
    for prop in (PROPOSITO_DESVINCULAR, PROPOSITO_VINCULAR, PROPOSITO_ALTA):
        ajeno = crear_token(prop, d.series_id, {"version": 1}, SECRETO, ahora=AHORA)
        assert verificar_token_retirada(ajeno, SECRETO, ahora=AHORA) is None
    # un token de retirada no sirve para verificar como otro propósito
    assert verificar_token_desvinculacion(ret, SECRETO, ahora=AHORA) is None
    assert verificar_token_vinculacion(ret, SECRETO, ahora=AHORA) is None


def test_el_contexto_es_la_serie_y_no_se_puede_cambiar():
    d = firmada()
    v = verificar_token_retirada(_con_datos(d), SECRETO, ahora=AHORA)
    assert v is not None and v.series_id == d.series_id
    t = crear_token(PROPOSITO_RETIRAR, "no-es-un-uuid", {"version": 1}, SECRETO, ahora=AHORA)
    assert verificar_token_retirada(t, SECRETO, ahora=AHORA) is None


def test_esquema_estricto():
    d = firmada()
    assert verificar_token_retirada(_con_datos(d), SECRETO, ahora=AHORA) is not None
    for malo in (dict(version=2), dict(version="1"), dict(version=True), dict(serie_id="x"), dict(serie_id=None),
                 dict(operacion=""), dict(huella="AB" * 32), dict(huella="ab" * 31), dict(huella=None), dict(huella=12)):
        assert verificar_token_retirada(_con_datos(d, **malo), SECRETO, ahora=AHORA) is None, malo
    for ausente in ("version", "serie_id", "operacion", "huella"):
        assert verificar_token_retirada(_con_datos(d, **{ausente: ...}), SECRETO, ahora=AHORA) is None, ausente


def test_un_token_de_otra_serie_no_sirve():
    d = firmada()
    otra = firmada()
    t = crear_token_retirada(d, SECRETO, ahora=AHORA)
    # El mismo token no se puede aplicar a otra serie: el contexto firmado es la serie.
    v = verificar_token_retirada(t, SECRETO, ahora=AHORA)
    assert v is not None
    assert v.series_id == d.series_id and v.series_id != otra.series_id


def test_datos_que_no_son_un_objeto_no_rompen():
    crudo = json.dumps({"p": PROPOSITO_RETIRAR, "c": str(uuid4()), "d": [1], "exp": int(AHORA) + 900}).encode()
    assert verificar_token_retirada(sign_token(base64.urlsafe_b64encode(crudo).decode(), SECRETO), SECRETO, ahora=AHORA) is None


def test_el_limite_del_cuerpo_es_el_peor_caso_emitible():
    ident = "ffffffff-ffff-4fff-bfff-ffffffffffff"
    peor = crear_token_retirada(RetiradaFirmada(ident, "f" * 64, ident), "x" * 64, ahora=10**10)
    assert len(peor) <= MAX_TOKEN_RETIRADA
    assert len(crear_token_retirada(firmada(), SECRETO, ahora=AHORA)) <= MAX_TOKEN_RETIRADA
