# ruff: noqa: E501
"""Número largo extraído del nombre del archivo (#141): sin base de datos.

El defecto: la vista previa de la vinculación validaba el número que ESCRIBE la persona (`_numero_valido`: como mucho 20
caracteres, sin `\\n \\r \\t` ni NUL) pero no el que sale del NOMBRE del archivo. El parser no lo acota, así que un
`Tomo 111…1` de 30 dígitos aparecía como vinculable, entraba en el token y la confirmación rechazaba TODO el token
(`token_invalido`: el verificador exige ≤ 20 caracteres).

La corrección: el número del nombre pasa por la MISMA regla; si no la cumple se trata como AUSENTE (el archivo pasa a
«requiere número», con un motivo comprensible). No se trunca, no se cambia el parser, el verificador ni el límite de 20.

Aquí: el parser sigue sin acotar (la causa mecánica) y la regla que aplica la vista previa.
"""
from __future__ import annotations

import pytest

from zascarr.services.tokens_revision import MAX_NUMERO
from zascarr.services.vinculacion_previa import NumeroNoValidoError, VistaPreviaDeVinculacion
from zascarr.utils.naming import parse_comic_filename

LARGOS = [19, 20, 21, 30, 100]


class TestElParserNoAcotaElNumero:
    """La causa mecánica. Si algún día el parser acota el número, estas pruebas lo dirán (y la defensa de la vista
    previa seguirá siendo necesaria para el verificador, pero habrá que revisar el motivo)."""

    @pytest.mark.parametrize("k", LARGOS)
    def test_el_numero_del_nombre_tiene_la_longitud_que_traiga_el_nombre(self, k):
        assert len(parse_comic_filename(f"Tomo {'1' * k}.cbz").issue_number) == k

    def test_el_limite_de_20_es_el_del_verificador_y_el_de_la_persona(self):
        assert MAX_NUMERO == 20


class TestNumeroDelNombre:
    """`VistaPreviaDeVinculacion._numero_del_nombre(valor) -> (número utilizable o None, descartado)`."""

    @pytest.mark.parametrize("k", [1, 19, 20])
    def test_hasta_20_caracteres_se_acepta_tal_cual(self, k):
        assert VistaPreviaDeVinculacion._numero_del_nombre("1" * k) == ("1" * k, False)

    @pytest.mark.parametrize("k", [21, 30, 100])
    def test_mas_de_20_caracteres_se_trata_como_ausente_y_se_marca_descartado(self, k):
        assert VistaPreviaDeVinculacion._numero_del_nombre("1" * k) == (None, True)

    @pytest.mark.parametrize("valor", [None, "", "   "])
    def test_sin_numero_no_hay_nada_descartado(self, valor):
        assert VistaPreviaDeVinculacion._numero_del_nombre(valor) == (None, False)

    def test_no_se_trunca_nunca(self):
        numero, _ = VistaPreviaDeVinculacion._numero_del_nombre("1" * 30)
        assert numero is None

    @pytest.mark.parametrize("valor", ["1\n2", "1\r", "1\t2", "1\x002", "\x01" * 20, "é" * 20, "漢" * 20, "9" * 20, "12A", "1.5", "Annual 3"])
    def test_es_exactamente_la_regla_de_la_persona(self, valor):
        """Mismo resultado que `_numero_valido`: lo que la persona no puede escribir, el nombre tampoco lo impone."""
        try:
            esperado = (VistaPreviaDeVinculacion._numero_valido(valor) or None, False)
        except NumeroNoValidoError:
            esperado = (None, True)
        assert VistaPreviaDeVinculacion._numero_del_nombre(valor) == esperado

    def test_la_regla_de_la_persona_no_ha_cambiado(self):
        with pytest.raises(NumeroNoValidoError):
            VistaPreviaDeVinculacion._numero_valido("1" * 21)
        assert VistaPreviaDeVinculacion._numero_valido("1" * 20) == "1" * 20
