# ruff: noqa: E501
"""Tokens firmados de la superficie de revisión (`services/tokens_revision.py`): sin base de datos.

Dos capas, y las dos se prueban: la **firma** (propósito, contexto, caducidad: un token manipulado no se
acepta) y el **esquema** del contenido: un token con firma VÁLIDA sigue sin darse por bueno si sus campos no
tienen la forma esperada. Lo segundo no es protección contra un cliente que falsifique la firma (no puede),
sino una defensa de esquema: nadie debe poder convertir un `None` en la serie «None».
"""
from __future__ import annotations

import time

import pytest

from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.tokens_revision import (
    MAX_DESCRIPCION,
    PROPOSITO_CANDIDATA,
    TTL_SEGUNDOS,
    CandidataFirmada,
    crear_token,
    crear_token_candidata,
    verificar_token,
    verificar_token_candidata,
)

SECRETO = "clave-de-prueba-para-firmar"
CLAVE = "Comics/Flash (1987)"
VALIDO = {"fuente": "comic_vine", "id": "42", "titulo": "Flash", "anio": 1987, "tradicion": "american",
          "descripcion": "algo", "cover_url": "https://comicvine.gamespot.com/a/x.jpg"}


def firmado(**cambios):
    """Un token de candidata con FIRMA VÁLIDA y el contenido que se le diga (el resto, el del caso válido)."""
    datos = {**VALIDO, **cambios}
    return crear_token(PROPOSITO_CANDIDATA, CLAVE, datos, SECRETO)


def sin(campo):
    datos = {k: v for k, v in VALIDO.items() if k != campo}
    return crear_token(PROPOSITO_CANDIDATA, CLAVE, datos, SECRETO)


class TestContenidoConFirmaValida:

    def test_el_caso_valido_pasa(self):
        c = verificar_token_candidata(firmado(), CLAVE, SECRETO)
        assert c == CandidataFirmada("comic_vine", "42", "Flash", 1987, "american", "algo",
                                     "https://comicvine.gamespot.com/a/x.jpg")

    @pytest.mark.parametrize("campo", ["fuente", "id", "titulo", "tradicion"])
    @pytest.mark.parametrize("valor", [None, "", "   ", "\t\n", 5, 5.0, True, [], {}, ["x"]])
    def test_fuente_id_titulo_y_tradicion_exigen_una_cadena_real_y_no_vacia(self, campo, valor):
        """Antes se hacía `str(...)`: un `None` pasaba a ser la serie «None»."""
        assert verificar_token_candidata(firmado(**{campo: valor}), CLAVE, SECRETO) is None

    @pytest.mark.parametrize("campo", ["fuente", "id", "titulo", "tradicion"])
    def test_un_campo_obligatorio_ausente_se_rechaza(self, campo):
        assert verificar_token_candidata(sin(campo), CLAVE, SECRETO) is None

    @pytest.mark.parametrize("fuente", ["inventada", "COMIC_VINE", "comic vine", "manual-ish"])
    def test_la_fuente_debe_estar_en_la_enumeracion(self, fuente):
        assert verificar_token_candidata(firmado(fuente=fuente), CLAVE, SECRETO) is None

    @pytest.mark.parametrize("f", list(MetadataSource))
    def test_todas_las_fuentes_de_la_enumeracion_valen(self, f):
        assert verificar_token_candidata(firmado(fuente=f.value), CLAVE, SECRETO).fuente == f.value

    @pytest.mark.parametrize("tradicion", ["inventada", "AMERICAN", "american ", "americana", "other2"])
    def test_la_tradicion_se_valida_contra_la_enumeracion(self, tradicion):
        """Antes la tradición no se comprobaba: cualquier cadena pasaba."""
        assert verificar_token_candidata(firmado(tradicion=tradicion), CLAVE, SECRETO) is None

    @pytest.mark.parametrize("t", list(ComicTradition))
    def test_todas_las_tradiciones_de_la_enumeracion_valen(self, t):
        assert verificar_token_candidata(firmado(tradicion=t.value), CLAVE, SECRETO).tradicion == t.value

    @pytest.mark.parametrize("anio", [True, False, "1987", 1987.5, 19.0, [], {}, "", "abc"])
    def test_el_anio_debe_ser_un_entero_y_un_booleano_no_lo_es(self, anio):
        """`isinstance(True, int)` es verdadero en Python: un booleano no es un año."""
        assert verificar_token_candidata(firmado(anio=anio), CLAVE, SECRETO) is None

    @pytest.mark.parametrize("anio", [None, 0, 1987, 2100])
    def test_el_anio_puede_faltar_o_ser_un_entero(self, anio):
        assert verificar_token_candidata(firmado(anio=anio), CLAVE, SECRETO).anio == anio

    @pytest.mark.parametrize("campo", ["descripcion", "cover_url"])
    @pytest.mark.parametrize("valor", [5, True, [], {}, ["x"]])
    def test_los_opcionales_con_otro_tipo_se_rechazan(self, campo, valor):
        assert verificar_token_candidata(firmado(**{campo: valor}), CLAVE, SECRETO) is None

    @pytest.mark.parametrize("campo", ["descripcion", "cover_url"])
    def test_los_opcionales_pueden_ser_nulos_o_faltar(self, campo):
        assert verificar_token_candidata(firmado(**{campo: None}), CLAVE, SECRETO) is not None
        assert verificar_token_candidata(sin(campo), CLAVE, SECRETO) is not None

    def test_los_datos_que_no_son_un_objeto_se_rechazan(self):
        for datos in ([], "x", 5, None, ["a"]):
            t = crear_token(PROPOSITO_CANDIDATA, CLAVE, datos, SECRETO)       # type: ignore[arg-type]
            assert verificar_token_candidata(t, CLAVE, SECRETO) is None

    def test_la_descripcion_se_recorta_al_firmar(self):
        t = crear_token_candidata(CLAVE, CandidataFirmada("comic_vine", "1", "Flash", 1987, "american", "x" * 5000, None), SECRETO)
        assert len(verificar_token_candidata(t, CLAVE, SECRETO).descripcion) == MAX_DESCRIPCION


class TestFirmaPropositoContextoYCaducidad:

    def test_otro_contexto_otra_clave_u_otro_proposito_no_valen(self):
        t = firmado()
        assert verificar_token_candidata(t, "Comics/Otra", SECRETO) is None
        assert verificar_token_candidata(t, CLAVE, "otra-clave") is None
        assert verificar_token(t, "alta", CLAVE, SECRETO) is None

    def test_un_token_manipulado_o_roto_no_se_acepta(self):
        cuerpo, firma = firmado().rsplit(".", 1)
        for malo in (cuerpo + "A." + firma, cuerpo + "." + firma[:-1] + ("0" if firma[-1] != "0" else "1"),
                     "", "basura", "a.b", firmado()[::-1], cuerpo, "." + firma, None, 5, b"x"):
            assert verificar_token_candidata(malo, CLAVE, SECRETO) is None, malo     # type: ignore[arg-type]

    def test_sin_clave_no_se_firma_ni_se_verifica(self):
        with pytest.raises(ValueError):
            crear_token(PROPOSITO_CANDIDATA, CLAVE, {}, "")
        assert verificar_token(firmado(), PROPOSITO_CANDIDATA, CLAVE, "") is None


class TestCaducidadConRelojInyectado:
    """`ahora or time.time()` trataba un reloj inyectado de valor CERO como «sin reloj»."""

    def test_caduca_a_los_quince_minutos_con_el_reloj_inyectado(self):
        t = crear_token(PROPOSITO_CANDIDATA, CLAVE, VALIDO, SECRETO, ahora=1000.0)
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO, ahora=1000.0 + TTL_SEGUNDOS - 1) is not None
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO, ahora=1000.0 + TTL_SEGUNDOS + 1) is None

    def test_un_reloj_inyectado_de_valor_cero_se_respeta(self):
        t = crear_token(PROPOSITO_CANDIDATA, CLAVE, VALIDO, SECRETO, ahora=0)
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO, ahora=0) is not None
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO, ahora=TTL_SEGUNDOS + 1) is None
        # con el reloj REAL (muy posterior a 0) ese token ya habría caducado: no se confunde un 0 con «sin reloj»
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO) is None

    def test_el_reloj_real_se_usa_si_no_se_inyecta(self):
        t = crear_token(PROPOSITO_CANDIDATA, CLAVE, VALIDO, SECRETO)
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO) is not None
        assert verificar_token(t, PROPOSITO_CANDIDATA, CLAVE, SECRETO, ahora=time.time() + TTL_SEGUNDOS + 5) is None

    def test_una_caducidad_que_no_es_un_entero_se_rechaza(self):
        import base64
        import json

        from zascarr.services.auth import sign_token
        for exp in (True, "9999999999", None, 1e12, [], {}):
            cuerpo = base64.urlsafe_b64encode(json.dumps(
                {"p": PROPOSITO_CANDIDATA, "c": CLAVE, "d": VALIDO, "exp": exp}).encode()).decode()
            assert verificar_token(sign_token(cuerpo, SECRETO), PROPOSITO_CANDIDATA, CLAVE, SECRETO, ahora=0) is None, exp
