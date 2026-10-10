# ruff: noqa: E501
"""Fecha anterior a 1970 (#142): sin base de datos.

El defecto: `stat` devuelve un `st_mtime_ns` NEGATIVO para un archivo con fecha anterior a 1970; la vista previa lo copiaba
al token y el verificador exige `mtime_ns >= 0`, así que la confirmación rechazaba TODO el token (`token_invalido`).

La corrección (contrato escrito en #142): se defiende la vista previa. Un archivo con `mtime_ns < 0` pasa a
`origen_no_verificable` con la causa `fecha_anterior_a_1970`: no es marcable ni entra en el token. **El verificador, el
formato del token y `MAX_TOKEN_VINCULACION` no cambian.** Exactamente 0 es vinculable; las fechas futuras no se tocan.
"""
from __future__ import annotations

import os
import stat as _stat
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest

from zascarr.services.tokens_revision import (
    EPOCA_DEL_PEOR_CASO,
    MAX_MTIME_NS_STAT,
    ArchivoFirmado,
    VinculacionFirmada,
    crear_token_vinculacion,
    verificar_token_vinculacion,
)
from zascarr.services.vinculacion_previa import (
    TEXTOS_NO_VERIFICABLE,
    Causa,
    _comprobar_origenes,
)

SECRETO = "clave-de-prueba-para-firmar"
IDENT = "00000000-0000-4000-8000-000000000000"
CAUSA = "fecha_anterior_a_1970"


def falso_stat(mtime_ns: int, modo: int = _stat.S_IFREG | 0o644):
    return lambda ruta: SimpleNamespace(st_mode=modo, st_size=123, st_mtime_ns=mtime_ns)


def origen(mtime_ns: int, **kw):
    return _comprobar_origenes({"f": "/biblioteca/Comics/x.cbz"}, Path("/biblioteca"), falso_stat(mtime_ns, **kw))["f"]


def token_con(mtime_ns: int) -> str:
    firmado = ArchivoFirmado("00000000-0000-4000-8000-000000000001", "1", "single_issue", 123, mtime_ns)
    return crear_token_vinculacion(VinculacionFirmada("Comics/x", IDENT, IDENT, (firmado,)), SECRETO, ahora=EPOCA_DEL_PEOR_CASO)


class TestLaCausaDelVerificador:
    """La causa mecánica: el verificador sigue exigiendo `>= 0` (y no se cambia)."""

    def test_el_verificador_acepta_cero_y_futuras(self):
        for m in (0, 1, 10**19, MAX_MTIME_NS_STAT):
            assert verificar_token_vinculacion(token_con(m), SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None, m

    @pytest.mark.parametrize("m", [-1, -10**9, -2**63])
    def test_el_verificador_rechaza_las_negativas(self, m):
        assert verificar_token_vinculacion(token_con(m), SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is None


class TestOrigenSegunLaFecha:

    @pytest.mark.parametrize("m", [0, 1, 1_760_000_000_000_000_000, 10**19, 10**27, MAX_MTIME_NS_STAT])
    def test_cero_y_positivas_son_verificables_y_se_copian_tal_cual(self, m):
        o = origen(m)
        assert (o.estado, o.mtime_ns, o.tamano, o.causa) == ("ok", m, 123, None)

    @pytest.mark.parametrize("m", [-1, -10**9, -86_400 * 10**9, -(2**63)])
    def test_negativas_son_no_verificables_con_la_causa_nueva(self, m):
        o = origen(m)
        assert o.estado == "no_verificable" and o.causa == CAUSA

    def test_la_frontera_es_exactamente_menor_que_cero(self):
        assert origen(0).estado == "ok" and origen(-1).estado == "no_verificable"

    def test_una_ruta_que_no_es_un_archivo_conserva_su_causa_aunque_la_fecha_sea_negativa(self):
        """Precedencia: la fecha solo decide cuando el archivo existe y es un archivo normal."""
        o = origen(-10**9, modo=_stat.S_IFDIR | 0o755)
        assert (o.estado, o.causa) == ("no_verificable", "no_es_un_archivo")


class TestTextoYEsquema:

    def test_la_causa_esta_en_el_esquema_y_tiene_texto(self):
        assert CAUSA in get_args(Causa) and CAUSA in TEXTOS_NO_VERIFICABLE

    def test_las_causas_de_antes_siguen_ahi(self):
        assert {"permiso", "error_de_lectura", "biblioteca_no_accesible", "no_es_un_archivo"} <= set(get_args(Causa))

    def test_el_texto_es_comprensible_y_no_muestra_ninguna_fecha_ni_numero(self):
        t = TEXTOS_NO_VERIFICABLE[CAUSA]
        assert "anterior a 1970" in t and "No significa que haya desaparecido" in t and "repite la vista previa" in t
        assert not any(c.isdigit() for c in t.replace("1970", ""))

    def test_todas_las_causas_tienen_texto(self):
        assert set(get_args(Causa)) == set(TEXTOS_NO_VERIFICABLE)


class TestElVerificadorYElFormatoNoCambian:
    def test_el_formato_y_el_limite_del_token_siguen_como_estaban(self):
        from zascarr.services.tokens_revision import MAX_TOKEN_VINCULACION, VERSION_TOKEN_VINCULAR
        assert (VERSION_TOKEN_VINCULAR, MAX_TOKEN_VINCULACION) == (2, 73229)

    def test_un_token_real_con_fecha_cero_se_verifica(self, tmp_path):
        f = tmp_path / "a.cbz"
        f.write_bytes(b"x")
        os.utime(f, ns=(0, 0))
        assert f.stat().st_mtime_ns == 0 and origen(f.stat().st_mtime_ns).estado == "ok"
