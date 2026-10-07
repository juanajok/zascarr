# ruff: noqa: E501
"""Token del alta (`services/tokens_revision.py`, rebanada 2b): sin base de datos.

La confirmación recibe SOLO el token. Dos capas: la **firma** (propósito, contexto, caducidad) y el **esquema** del
contenido, que se exige también con una firma válida (defensa de esquema, no contra un falsificador de firmas).
"""
from __future__ import annotations

import base64
import json
import time
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition
from zascarr.services.auth import sign_token
from zascarr.services.tokens_revision import (
    PROPOSITO_ALTA,
    PROPOSITO_CANDIDATA,
    TTL_SEGUNDOS,
    AltaFirmada,
    crear_token,
    crear_token_alta,
    verificar_token,
    verificar_token_alta,
)

SECRETO = "clave-de-prueba-para-firmar"
CLAVE = "Comics/Flash (1987)"
OP, SERIE = str(uuid4()), str(uuid4())
VALIDO = {"modo": "crear", "origen": "descubrir", "fuente": "comic_vine", "id": "796", "titulo": "Flash", "anio": 1987,
          "tradicion": "american", "descripcion": "algo", "cover_url": "https://comicvine.gamespot.com/a/x.jpg",
          "serie_id": None, "vistas": [str(uuid4())], "operacion": OP, "criterio": None}
MANUAL = {**VALIDO, "origen": "manual", "fuente": None, "id": None, "descripcion": None, "cover_url": None}


def firmado(base=VALIDO, **cambios) -> str:
    return crear_token(PROPOSITO_ALTA, CLAVE, {**base, **cambios}, SECRETO)


def sin(campo, base=VALIDO) -> str:
    return crear_token(PROPOSITO_ALTA, CLAVE, {k: v for k, v in base.items() if k != campo}, SECRETO)


def alta(**kw) -> AltaFirmada:
    """Alta de ejemplo (modo `crear`, sin criterio)."""
    base = dict(clave=CLAVE, modo="crear", origen="manual", fuente=None, id_externo=None, titulo="Flash", anio=1987,
                tradicion="american", descripcion=None, cover_url=None, serie_id=None, vistas=(), operacion=OP)
    return AltaFirmada(**{**base, **kw})


class TestFirma:

    def test_ida_y_vuelta(self):
        a = alta(origen="descubrir", fuente="gcd", id_externo="4120", descripcion="d", cover_url="https://x.example/y.jpg",
                 vistas=(SERIE, str(uuid4())))
        v = verificar_token_alta(crear_token_alta(a, SECRETO), SECRETO)
        assert v is not None and v.clave == CLAVE
        assert (v.modo, v.origen, v.fuente, v.id_externo, v.titulo, v.anio, v.tradicion) == (
            "crear", "descubrir", "gcd", "4120", "Flash", 1987, "american")
        assert v.descripcion == "d" and v.cover_url == "https://x.example/y.jpg" and v.operacion == OP
        assert sorted(v.vistas) == sorted(a.vistas)

    def test_el_contexto_es_la_clave_y_se_lee_del_propio_token(self):
        for clave in ("A", "Comics/Otra (2000)", "x" * 900):
            t = crear_token_alta(alta(clave=clave), SECRETO)
            assert verificar_token_alta(t, SECRETO).clave == clave
            assert verificar_token(t, PROPOSITO_ALTA, clave, SECRETO) is not None
            assert verificar_token(t, PROPOSITO_ALTA, clave + "x", SECRETO) is None     # otro contexto

    def test_otro_proposito_no_sirve(self):
        t = crear_token(PROPOSITO_CANDIDATA, CLAVE, VALIDO, SECRETO)
        assert verificar_token_alta(t, SECRETO) is None
        t2 = crear_token("vincular", CLAVE, VALIDO, SECRETO)
        assert verificar_token_alta(t2, SECRETO) is None
        assert verificar_token(crear_token_alta(alta(), SECRETO), PROPOSITO_CANDIDATA, CLAVE, SECRETO) is None

    def test_otra_clave_o_manipulado_o_basura_no_sirven(self):
        t = crear_token_alta(alta(), SECRETO)
        assert verificar_token_alta(t, "otra-clave") is None and verificar_token_alta(t, "") is None
        for malo in (t[:-2] + "zz", t + "a", "", "x", ".", None, 42, b"x", [], t.replace(".", "..")):
            assert verificar_token_alta(malo, SECRETO) is None, malo

    def test_caducado(self):
        t = crear_token_alta(alta(), SECRETO, ahora=1000)
        assert verificar_token_alta(t, SECRETO, ahora=1000 + TTL_SEGUNDOS) is not None
        assert verificar_token_alta(t, SECRETO, ahora=1000 + TTL_SEGUNDOS + 1) is None
        assert verificar_token_alta(crear_token_alta(alta(), SECRETO, ahora=time.time() - 16 * 60), SECRETO) is None

    def test_contexto_ausente_o_que_no_es_texto(self):
        for c in (None, "", 7, ["a"], {"a": 1}, True):
            cuerpo = base64.urlsafe_b64encode(json.dumps(
                {"p": PROPOSITO_ALTA, "c": c, "d": VALIDO, "exp": int(time.time()) + 600}).encode()).decode()
            assert verificar_token_alta(sign_token(cuerpo, SECRETO), SECRETO) is None, c
        sin_c = base64.urlsafe_b64encode(json.dumps(
            {"p": PROPOSITO_ALTA, "d": VALIDO, "exp": int(time.time()) + 600}).encode()).decode()
        assert verificar_token_alta(sign_token(sin_c, SECRETO), SECRETO) is None

    def test_el_token_lleva_solo_los_campos_del_contrato_sin_secretos_ni_sesion(self):
        datos = verificar_token(crear_token_alta(alta(), SECRETO), PROPOSITO_ALTA, CLAVE, SECRETO)
        assert set(datos) == {"modo", "origen", "fuente", "id", "titulo", "anio", "tradicion", "descripcion",
                              "cover_url", "serie_id", "vistas", "operacion", "criterio"}
        assert SECRETO not in json.dumps(datos)


class TestEsquemaConFirmaValida:
    """Una firma válida no basta: cada campo debe tener la forma esperada."""

    def test_el_caso_valido_pasa(self):
        for base in (VALIDO, MANUAL, {**VALIDO, "modo": "reutilizar", "serie_id": SERIE, "criterio": "identificador"},
                     {**VALIDO, "modo": "reutilizar", "serie_id": SERIE, "criterio": "eleccion"},
                     {**MANUAL, "modo": "reutilizar", "serie_id": SERIE, "criterio": "eleccion"}):
            assert verificar_token_alta(firmado(base), SECRETO) is not None

    @pytest.mark.parametrize("campo", ["modo", "origen", "titulo", "tradicion"])
    @pytest.mark.parametrize("valor", [None, "", "   ", 7, True, [], {}])
    def test_los_obligatorios_son_cadenas_reales_no_vacias(self, campo, valor):
        assert verificar_token_alta(firmado(**{campo: valor}), SECRETO) is None
        assert verificar_token_alta(sin(campo), SECRETO) is None

    @pytest.mark.parametrize("valor", ["otro", "CREAR", "borrar", "", None])
    def test_modo_solo_crear_o_reutilizar(self, valor):
        assert verificar_token_alta(firmado(modo=valor), SECRETO) is None

    @pytest.mark.parametrize("valor", ["otro", "Manual", "api", "", None])
    def test_origen_solo_descubrir_o_manual(self, valor):
        assert verificar_token_alta(firmado(origen=valor), SECRETO) is None

    @pytest.mark.parametrize("valor", ["inventada", "AMERICAN", "Manga", ""])
    def test_la_tradicion_es_una_de_la_enumeracion(self, valor):
        assert verificar_token_alta(firmado(tradicion=valor), SECRETO) is None
        assert all(verificar_token_alta(firmado(tradicion=t.value), SECRETO) for t in ComicTradition)

    @pytest.mark.parametrize("fuente", [None, "", "inventada", "manual", "comicinfo_xml", 7, True])
    def test_desde_una_fuente_solo_con_una_fuente_con_identificador(self, fuente):
        assert verificar_token_alta(firmado(fuente=fuente), SECRETO) is None

    @pytest.mark.parametrize("id_", [None, "", "  ", 796, True, []])
    def test_desde_una_fuente_el_id_es_texto_no_vacio(self, id_):
        assert verificar_token_alta(firmado(id=id_), SECRETO) is None

    @pytest.mark.parametrize("campo", ["fuente", "id"])
    def test_a_mano_no_lleva_fuente_ni_identificador(self, campo):
        valor = "comic_vine" if campo == "fuente" else "1"
        assert verificar_token_alta(firmado(MANUAL, **{campo: valor}), SECRETO) is None

    def test_reutilizar_exige_la_serie_y_el_criterio(self):
        assert verificar_token_alta(firmado(modo="reutilizar", serie_id=None, criterio="eleccion"), SECRETO) is None
        assert verificar_token_alta(firmado(modo="reutilizar", criterio="eleccion"), SECRETO) is None
        assert verificar_token_alta(firmado(modo="reutilizar", serie_id=SERIE), SECRETO) is None       # sin criterio

    @pytest.mark.parametrize("criterio", [None, "", "id", "Identificador", "automatico", 7, True, [], {}])
    def test_el_criterio_de_una_reutilizacion_es_uno_de_los_dos(self, criterio):
        assert verificar_token_alta(firmado(modo="reutilizar", serie_id=SERIE, criterio=criterio), SECRETO) is None

    def test_por_identificador_solo_si_viene_de_una_fuente(self):
        assert verificar_token_alta(firmado(MANUAL, modo="reutilizar", serie_id=SERIE, criterio="identificador"),
                                    SECRETO) is None
        assert verificar_token_alta(firmado(MANUAL, modo="reutilizar", serie_id=SERIE, criterio="eleccion"),
                                    SECRETO) is not None

    @pytest.mark.parametrize("criterio", ["identificador", "eleccion", "", 7])
    def test_crear_no_lleva_criterio(self, criterio):
        assert verificar_token_alta(firmado(criterio=criterio), SECRETO) is None
        assert verificar_token_alta(firmado(criterio=None), SECRETO) is not None

    @pytest.mark.parametrize("valor", ["", "no-es-uuid", 5, True, [], str(uuid4()).upper(), str(uuid4()).replace("-", ""), "x" * 36])
    def test_los_ids_de_serie_son_uuid_en_su_forma_canonica(self, valor):
        assert verificar_token_alta(firmado(modo="reutilizar", serie_id=valor), SECRETO) is None
        assert verificar_token_alta(firmado(vistas=[valor]), SECRETO) is None
        assert verificar_token_alta(firmado(operacion=valor), SECRETO) is None

    @pytest.mark.parametrize("valor", [None, "x", 5, {}, "uuid", [None], [1], [[]]])
    def test_vistas_es_una_lista_de_uuid(self, valor):
        assert verificar_token_alta(firmado(vistas=valor), SECRETO) is None

    def test_operacion_obligatoria(self):
        assert verificar_token_alta(sin("operacion"), SECRETO) is None
        assert verificar_token_alta(sin("vistas"), SECRETO) is None

    @pytest.mark.parametrize("anio", [True, False, "1987", 1987.5, [], {}])
    def test_el_anio_es_entero_y_no_booleano(self, anio):
        assert verificar_token_alta(firmado(anio=anio), SECRETO) is None

    def test_el_anio_es_opcional(self):
        assert verificar_token_alta(firmado(anio=None), SECRETO).anio is None
        assert verificar_token_alta(sin("anio"), SECRETO).anio is None

    @pytest.mark.parametrize("campo", ["descripcion", "cover_url"])
    @pytest.mark.parametrize("valor", [5, True, [], {}])
    def test_los_opcionales_son_texto_o_nulos(self, campo, valor):
        assert verificar_token_alta(firmado(**{campo: valor}), SECRETO) is None

    def test_datos_que_no_son_un_objeto(self):
        for datos in ([], "x", 5, None, True):
            t = crear_token(PROPOSITO_ALTA, CLAVE, datos, SECRETO)
            assert verificar_token_alta(t, SECRETO) is None

    def test_la_descripcion_se_recorta(self):
        t = crear_token_alta(alta(origen="descubrir", fuente="gcd", id_externo="1", descripcion="x" * 5000), SECRETO)
        assert len(verificar_token_alta(t, SECRETO).descripcion) == 1000
