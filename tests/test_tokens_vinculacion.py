# ruff: noqa: E501
"""Token `vincular` (`services/tokens_revision.py`, rebanada 2c): sin base de datos.

Dos capas: la firma (propósito, contexto, caducidad) y el esquema del contenido, que se exige también con firma
válida. La confirmación (2d) recibirá SOLO el token: el contexto (la `clave` del grupo) se lee de dentro del token.
"""
from __future__ import annotations

import time
from uuid import uuid4

import pytest

from zascarr.models import IssueFormat
from zascarr.services.tokens_revision import (
    MAX_ARCHIVOS_FIRMADOS,
    PROPOSITO_ALTA,
    PROPOSITO_VINCULAR,
    TTL_SEGUNDOS,
    ArchivoFirmado,
    VinculacionFirmada,
    crear_token,
    crear_token_vinculacion,
    verificar_token_alta,
    verificar_token_vinculacion,
)

SECRETO = "clave-de-prueba-para-firmar"
CLAVE = "Comics/Flash (1987)"
SERIE, OP = str(uuid4()), str(uuid4())


def archivo(**kw) -> ArchivoFirmado:
    base = dict(id=str(uuid4()), numero="3", formato="single_issue", tamano=1234, mtime_ns=1_700_000_000_000_000_000)
    return ArchivoFirmado(**{**base, **kw})


def vinc(*archivos: ArchivoFirmado, clave=CLAVE) -> VinculacionFirmada:
    return VinculacionFirmada(clave, SERIE, OP, archivos or (archivo(),))


def datos(**cambios) -> dict:
    base = {"version": 2, "serie_id": SERIE, "operacion": OP, "archivos": [
        {"id": str(uuid4()), "numero": "3", "formato": "single_issue", "tamano": 10, "mtime_ns": 5, "conflictos": []}]}
    return {**base, **cambios}


def firmado(d: dict, clave=CLAVE) -> str:
    return crear_token(PROPOSITO_VINCULAR, clave, d, SECRETO)


class TestFirma:

    def test_ida_y_vuelta(self):
        a, b = archivo(numero="12A"), archivo(numero="1", formato="omnibus")
        v = verificar_token_vinculacion(crear_token_vinculacion(vinc(a, b), SECRETO), SECRETO)
        assert (v.clave, v.series_id, v.operacion) == (CLAVE, SERIE, OP)
        assert sorted(v.archivos, key=lambda x: x.id) == sorted([a, b], key=lambda x: x.id)

    def test_el_contexto_se_lee_del_token(self):
        for clave in ("A", "Comics/Otra (2000)", "x" * 900):
            assert verificar_token_vinculacion(crear_token_vinculacion(vinc(clave=clave), SECRETO), SECRETO).clave == clave

    def test_otro_proposito_no_sirve_y_al_reves(self):
        t = crear_token(PROPOSITO_ALTA, CLAVE, datos(), SECRETO)
        assert verificar_token_vinculacion(t, SECRETO) is None
        assert verificar_token_alta(crear_token_vinculacion(vinc(), SECRETO), SECRETO) is None

    def test_manipulado_otra_clave_o_basura(self):
        t = crear_token_vinculacion(vinc(), SECRETO)
        assert verificar_token_vinculacion(t, "otra") is None and verificar_token_vinculacion(t, "") is None
        for malo in (t[:-2] + "zz", t + "a", "", "x", None, 7, b"x", []):
            assert verificar_token_vinculacion(malo, SECRETO) is None, malo

    def test_caduca(self):
        t = crear_token_vinculacion(vinc(), SECRETO, ahora=1000)
        assert verificar_token_vinculacion(t, SECRETO, ahora=1000 + TTL_SEGUNDOS) is not None
        assert verificar_token_vinculacion(t, SECRETO, ahora=1000 + TTL_SEGUNDOS + 1) is None
        assert verificar_token_vinculacion(crear_token_vinculacion(vinc(), SECRETO, ahora=time.time() - 16 * 60), SECRETO) is None

    def test_lleva_su_caducidad(self):
        t = crear_token_vinculacion(vinc(), SECRETO, ahora=5000)
        assert verificar_token_vinculacion(t, SECRETO, ahora=5000).caduca == 5000 + TTL_SEGUNDOS

    def test_solo_lleva_los_campos_del_contrato_sin_rutas_ni_nombres_ni_hash(self):
        from zascarr.services.tokens_revision import verificar_token
        d = verificar_token(crear_token_vinculacion(vinc(), SECRETO), PROPOSITO_VINCULAR, CLAVE, SECRETO)
        assert set(d) == {"version", "serie_id", "operacion", "archivos"}
        assert set(d["archivos"][0]) == {"id", "numero", "formato", "tamano", "mtime_ns", "conflictos"}


class TestEsquemaConFirmaValida:

    def test_el_caso_valido_pasa(self):
        assert verificar_token_vinculacion(firmado(datos()), SECRETO) is not None

    @pytest.mark.parametrize("campo", ["serie_id", "operacion"])
    @pytest.mark.parametrize("valor", [None, "", "no-uuid", 5, True, [], str(uuid4()).upper(), str(uuid4()).replace("-", "")])
    def test_los_ids_son_uuid_canonicos(self, campo, valor):
        assert verificar_token_vinculacion(firmado(datos(**{campo: valor})), SECRETO) is None

    @pytest.mark.parametrize("archivos", [None, [], "x", 5, {}, [None], [5], ["x"], [[]]])
    def test_archivos_es_una_lista_no_vacia_de_objetos(self, archivos):
        assert verificar_token_vinculacion(firmado(datos(archivos=archivos)), SECRETO) is None

    def test_a_lo_sumo_cien_archivos(self):
        def lote(n):
            return [{"id": str(uuid4()), "numero": str(i), "formato": "single_issue", "tamano": 1, "mtime_ns": 1,
                     "conflictos": []} for i in range(n)]
        assert verificar_token_vinculacion(firmado(datos(archivos=lote(MAX_ARCHIVOS_FIRMADOS))), SECRETO) is not None
        assert verificar_token_vinculacion(firmado(datos(archivos=lote(MAX_ARCHIVOS_FIRMADOS + 1))), SECRETO) is None

    @pytest.mark.parametrize("campo", ["id", "numero", "formato", "tamano", "mtime_ns", "conflictos"])
    def test_cada_campo_del_archivo_es_obligatorio(self, campo):
        a = datos()["archivos"][0]
        a.pop(campo)
        assert verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO) is None

    @pytest.mark.parametrize("numero", [None, "", "  ", " 3", "3 ", 3, True, [], "1" * 21])
    def test_el_numero_es_texto_recortado_no_vacio_y_corto(self, numero):
        a = {**datos()["archivos"][0], "numero": numero}
        assert verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO) is None

    @pytest.mark.parametrize("formato", [None, "", "grapa", "SINGLE_ISSUE", 5, True])
    def test_el_formato_es_de_la_enumeracion(self, formato):
        a = {**datos()["archivos"][0], "formato": formato}
        assert verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO) is None
        for f in IssueFormat:
            b = {**datos()["archivos"][0], "formato": f.value}
            assert verificar_token_vinculacion(firmado(datos(archivos=[b])), SECRETO) is not None

    @pytest.mark.parametrize("campo", ["tamano", "mtime_ns"])
    @pytest.mark.parametrize("valor", [None, True, False, "5", 5.5, -1, [], {}])
    def test_tamano_y_mtime_son_enteros_no_negativos_y_no_booleanos(self, campo, valor):
        a = {**datos()["archivos"][0], campo: valor}
        assert verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO) is None

    def test_cero_es_un_tamano_valido(self):
        a = {**datos()["archivos"][0], "tamano": 0, "mtime_ns": 0}
        assert verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO) is not None

    def test_sin_ids_repetidos(self):
        a = datos()["archivos"][0]
        assert verificar_token_vinculacion(firmado(datos(archivos=[a, dict(a)])), SECRETO) is None

    @pytest.mark.parametrize(("n1", "n2"), [("5", "5"), ("5A", "5a"), ("5a", "5A"), ("Ab", "aB")])
    def test_sin_dos_archivos_con_el_mismo_numero_sin_distinguir_mayusculas(self, n1, n2):
        a = datos()["archivos"][0]
        b = {**a, "id": str(uuid4()), "numero": n2}
        a = {**a, "numero": n1}
        assert verificar_token_vinculacion(firmado(datos(archivos=[a, b])), SECRETO) is None

    def test_numeros_distintos_conservan_el_texto_presentado(self):
        a = {**datos()["archivos"][0], "numero": "5A"}
        b = {**a, "id": str(uuid4()), "numero": "6"}
        v = verificar_token_vinculacion(firmado(datos(archivos=[a, b])), SECRETO)
        assert sorted(x.numero for x in v.archivos) == ["5A", "6"]


class TestVersionYConflictos:
    """Ausencia de `conflictos` NO significa «ninguno»: el token es versionado y los tokens de 2c se rechazan."""

    @pytest.mark.parametrize("version", [None, 1, 3, 0, "2", True, 2.0, [], {}])
    def test_solo_la_version_2(self, version):
        assert verificar_token_vinculacion(firmado(datos(version=version)), SECRETO) is None

    def test_un_token_de_2c_sin_version_ni_conflictos_se_rechaza(self):
        antiguo = {"serie_id": SERIE, "operacion": OP, "archivos": [
            {"id": str(uuid4()), "numero": "3", "formato": "single_issue", "tamano": 10, "mtime_ns": 5}]}
        assert verificar_token_vinculacion(firmado(antiguo), SECRETO) is None

    def test_conflictos_vacios_son_validos_y_explicitos(self):
        v = verificar_token_vinculacion(firmado(datos()), SECRETO)
        assert v.archivos[0].conflictos == ()

    def test_los_codigos_firmados_se_conservan(self):
        a = {**datos()["archivos"][0], "conflictos": ["titulo_distinto", "anio_archivo"]}
        v = verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO)
        assert v.archivos[0].conflictos == ("titulo_distinto", "anio_archivo")

    @pytest.mark.parametrize("conflictos", [None, "x", 5, {}, [None], [5], [""], ["  "], [" x"], ["x "], ["a", "a"],
                                           ["x" * 61], [["a"]], ["a"] * 2, [f"c{i}" for i in range(21)]])
    def test_conflictos_mal_formados_se_rechazan(self, conflictos):
        a = {**datos()["archivos"][0], "conflictos": conflictos}
        assert verificar_token_vinculacion(firmado(datos(archivos=[a])), SECRETO) is None

    def test_ida_y_vuelta_con_conflictos(self):
        a = archivo(conflictos=("anio_archivo",))
        v = verificar_token_vinculacion(crear_token_vinculacion(vinc(a), SECRETO), SECRETO)
        assert v.archivos[0].conflictos == ("anio_archivo",)


class TestCaducidadIgnorada:

    def test_un_token_caducado_se_lee_solo_si_se_pide_y_la_firma_sigue_valiendo(self):
        t = crear_token_vinculacion(vinc(), SECRETO, ahora=1000)
        tarde = 1000 + TTL_SEGUNDOS + 100
        assert verificar_token_vinculacion(t, SECRETO, ahora=tarde) is None
        v = verificar_token_vinculacion(t, SECRETO, ahora=tarde, ignorar_caducidad=True)
        assert v is not None and v.operacion == OP and v.caduca == 1000 + TTL_SEGUNDOS
        assert verificar_token_vinculacion(t, "otra", ahora=tarde, ignorar_caducidad=True) is None
        assert verificar_token_vinculacion(t[:-2] + "zz", SECRETO, ahora=tarde, ignorar_caducidad=True) is None

    def test_datos_que_no_son_un_objeto(self):
        for d in ([], "x", 5, None, True):
            assert verificar_token_vinculacion(crear_token(PROPOSITO_VINCULAR, CLAVE, d, SECRETO), SECRETO) is None
