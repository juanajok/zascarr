# ruff: noqa: E501
"""#480: huella del plan y token de ComicInfo (sin BD ni archivos reales)."""
from __future__ import annotations

import hashlib
from uuid import uuid4

from zascarr.core.comicinfo_write import Accion, CampoPlan
from zascarr.services.comicinfo_ficha import (
    PROPOSITO_COMICINFO,
    _campos_desde_token,
    _campos_para_token,
    _huella,
)
from zascarr.services.tokens_revision import crear_token, verificar_token


def _campos():
    return [CampoPlan("Series", Accion.CAMBIA, None, "Thorgal"),
            CampoPlan("Number", Accion.YA_COINCIDE, "1", "1")]


def test_huella_estable_y_sensible_al_plan():
    a = _huella(_campos())
    assert a == _huella(_campos())
    otros = [CampoPlan("Series", Accion.CAMBIA, None, "Otro")]
    assert _huella(otros) != a


def test_campos_ida_y_vuelta():
    crudo = _campos_para_token(_campos())
    assert _campos_desde_token(crudo) == _campos()
    assert _campos_desde_token([["Series", "cambia", None, "x"]]) == [
        CampoPlan("Series", Accion.CAMBIA, None, "x")]
    assert _campos_desde_token([["Series", "inventada", None, "x"]]) is None


def test_token_ligado_al_archivo_y_caducidad():
    file_id = str(uuid4())
    datos = {"version": 1, "operacion": str(uuid4()), "ruta": "/media/library/a.cbz",
             "tamano": 10, "mtime_ns": 20, "sha256": "a" * 64,
             "campos": _campos_para_token(_campos()), "huella": _huella(_campos())}
    token = crear_token(PROPOSITO_COMICINFO, file_id, datos, "x" * 32, ahora=1000.0)
    assert verificar_token(token, PROPOSITO_COMICINFO, file_id, "x" * 32, ahora=1001.0)
    assert verificar_token(token, PROPOSITO_COMICINFO, str(uuid4()), "x" * 32, ahora=1001.0) is None
    assert verificar_token(token, PROPOSITO_COMICINFO, file_id, "x" * 32, ahora=10**9) is None


def test_huella_no_confunde_campos():
    assert hashlib.sha256(repr(_campos_para_token(_campos())).encode()).hexdigest() != _huella(_campos())
