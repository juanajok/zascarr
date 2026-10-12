# ruff: noqa: E501
"""El alta SIN grupo de carpeta (I1 de #114): contexto firmado, límites de token recalculados y separación del alta con grupo.

Sin base de datos. El contrato que se fija:
- el contexto sin grupo (`CLAVE_SIN_GRUPO`) no puede ser el de ningún grupo (lleva un NUL, que una ruta no puede tener) y un
  token de un contexto no sirve en el otro, ni en candidata ni en alta;
- el máximo del token sin grupo se CALCULA con las mismas funciones reales de serialización y firma (no se resta ni se
  elige): es la longitud del mayor token sin grupo que el servidor puede emitir, el verificador lo acepta y cabe siempre en
  los límites que ya tienen `POST /api/revision/serie/previsualizar` y `POST /api/revision/serie`;
- los límites CON grupo no han cambiado;
- el alta con grupo rechaza la clave reservada sin tocar la base.
"""
from __future__ import annotations

import inspect

import pytest

from zascarr.api.revision import PeticionConfirmarAlta, PeticionPrevisualizarAlta
from zascarr.models import ComicTradition
from zascarr.services import tokens_revision as t
from zascarr.services.alta_serie import AltaDeSerie, DatosManuales, GrupoNoEncontradoError
from zascarr.services.discovery import CAMPO_ID_EXTERNO
from zascarr.services.tokens_revision import (
    ANIO_MIN_FIRMABLE,
    CLAVE_SIN_GRUPO,
    EPOCA_DEL_PEOR_CASO,
    MAX_COVER_URL,
    MAX_DESCRIPCION,
    MAX_ID_EXTERNO,
    MAX_PARECIDAS_FIRMADAS,
    MAX_TITULO,
    MAX_TOKEN_ALTA,
    MAX_TOKEN_ALTA_SIN_GRUPO,
    MAX_TOKEN_CANDIDATA,
    MAX_TOKEN_CANDIDATA_SIN_GRUPO,
    AltaFirmada,
    CandidataFirmada,
    crear_token_alta,
    crear_token_candidata,
    verificar_token_alta,
    verificar_token_candidata,
)

SECRETO = "clave-de-prueba-para-firmar"
GRUPO = "Comics/Flash (1987)"
IDENT = "00000000-0000-4000-8000-000000000000"
CH = "\U0001F600"


def candidata_maxima() -> CandidataFirmada:
    fuente = max((m.value for m in CAMPO_ID_EXTERNO), key=len)
    tradicion = max((c.value for c in ComicTradition), key=len)
    return CandidataFirmada(fuente, CH * MAX_ID_EXTERNO, CH * MAX_TITULO, ANIO_MIN_FIRMABLE, tradicion,
                            CH * MAX_DESCRIPCION, CH * MAX_COVER_URL)


def alta_maxima(clave: str, **kw) -> AltaFirmada:
    fuente = max((m.value for m in CAMPO_ID_EXTERNO), key=len)
    tradicion = max((c.value for c in ComicTradition), key=len)
    base = dict(clave=clave, origen="descubrir", fuente=fuente, id_externo=CH * MAX_ID_EXTERNO, titulo=CH * MAX_TITULO,
                anio=ANIO_MIN_FIRMABLE, tradicion=tradicion, descripcion=CH * MAX_DESCRIPCION, cover_url=CH * MAX_COVER_URL,
                operacion=IDENT)
    vistas = tuple(f"{i:08d}-0000-4000-8000-000000000000" for i in range(MAX_PARECIDAS_FIRMADAS))
    return AltaFirmada(**{**dict(modo="crear", serie_id=None, vistas=vistas), **base, **kw})


class TestElContextoReservado:
    def test_ninguna_ruta_puede_ser_la_clave_reservada(self):
        assert "\x00" in CLAVE_SIN_GRUPO                       # una ruta de Linux (y un `text` de Postgres) no admite el NUL

    def test_una_candidata_sin_grupo_no_vale_en_un_grupo_y_al_reves(self):
        c = CandidataFirmada("comic_vine", "796", "Flash", 1987, "american", None, None)
        sin = crear_token_candidata(CLAVE_SIN_GRUPO, c, SECRETO)
        con = crear_token_candidata(GRUPO, c, SECRETO)
        assert verificar_token_candidata(sin, CLAVE_SIN_GRUPO, SECRETO) == c
        assert verificar_token_candidata(sin, GRUPO, SECRETO) is None
        assert verificar_token_candidata(con, CLAVE_SIN_GRUPO, SECRETO) is None

    def test_el_token_de_alta_conserva_su_contexto(self):
        a = alta_maxima(CLAVE_SIN_GRUPO, vistas=(), origen="manual", fuente=None, id_externo=None)
        sin = verificar_token_alta(crear_token_alta(a, SECRETO), SECRETO)
        con = verificar_token_alta(crear_token_alta(alta_maxima(GRUPO, vistas=(), origen="manual", fuente=None, id_externo=None), SECRETO), SECRETO)
        assert sin is not None and sin.clave == CLAVE_SIN_GRUPO
        assert con is not None and con.clave == GRUPO


class TestLosLimitesRecalculados:
    def test_el_maximo_sin_grupo_es_la_longitud_del_mayor_token_sin_grupo(self):
        assert len(crear_token_candidata(CLAVE_SIN_GRUPO, candidata_maxima(), "x" * 32, ahora=EPOCA_DEL_PEOR_CASO)) == MAX_TOKEN_CANDIDATA_SIN_GRUPO
        assert len(crear_token_alta(alta_maxima(CLAVE_SIN_GRUPO), "x" * 32, ahora=EPOCA_DEL_PEOR_CASO)) == MAX_TOKEN_ALTA_SIN_GRUPO

    def test_el_mayor_token_sin_grupo_se_verifica(self):
        assert verificar_token_candidata(crear_token_candidata(CLAVE_SIN_GRUPO, candidata_maxima(), SECRETO), CLAVE_SIN_GRUPO, SECRETO) is not None
        assert verificar_token_alta(crear_token_alta(alta_maxima(CLAVE_SIN_GRUPO), SECRETO), SECRETO) is not None

    def test_los_valores_exactos(self):
        """Documentan el cálculo: el contexto pasa de 1000 controles de seis bytes a diez caracteres (uno de ellos de seis
        bytes), y el token baja `(6000 - 15) * 4 / 3 = 7.980` caracteres."""
        assert (MAX_TOKEN_CANDIDATA, MAX_TOKEN_ALTA) == (20313, 25681)                       # con grupo: NO han cambiado
        assert (MAX_TOKEN_CANDIDATA_SIN_GRUPO, MAX_TOKEN_ALTA_SIN_GRUPO) == (12333, 17701)
        assert MAX_TOKEN_CANDIDATA - MAX_TOKEN_CANDIDATA_SIN_GRUPO == MAX_TOKEN_ALTA - MAX_TOKEN_ALTA_SIN_GRUPO == 7980

    def test_un_token_sin_grupo_cabe_siempre_en_los_limites_que_ya_tienen_los_puntos_de_entrada(self):
        assert MAX_TOKEN_CANDIDATA_SIN_GRUPO < MAX_TOKEN_CANDIDATA and MAX_TOKEN_ALTA_SIN_GRUPO < MAX_TOKEN_ALTA
        cand = crear_token_candidata(CLAVE_SIN_GRUPO, candidata_maxima(), SECRETO)
        alta = crear_token_alta(alta_maxima(CLAVE_SIN_GRUPO), SECRETO)
        PeticionPrevisualizarAlta(clave="x", candidata=cand, tradicion="american")           # no lanza: cabe en el cuerpo
        PeticionConfirmarAlta(token=alta)

    @pytest.mark.parametrize("campo,sobra", [("titulo", CH), ("id_externo", CH), ("cover_url", CH)])
    def test_las_cotas_de_cada_campo_siguen_siendo_las_de_antes(self, campo, sobra):
        """Un carácter por encima de la cota de un campo: el verificador rechaza el token también sin grupo. (La descripción
        no: al firmar se recorta a `MAX_DESCRIPCION`, así que nunca puede pasarse.)"""
        a = alta_maxima(CLAVE_SIN_GRUPO, **{campo: getattr(alta_maxima(CLAVE_SIN_GRUPO), campo) + sobra})
        assert verificar_token_alta(crear_token_alta(a, SECRETO), SECRETO) is None

    def test_el_calculo_de_los_limites_con_grupo_no_depende_de_la_clave_por_defecto(self):
        assert t._longitud_peor_caso_del_token_de_candidata() == MAX_TOKEN_CANDIDATA
        assert t._longitud_peor_caso_del_token_de_alta() == MAX_TOKEN_ALTA


class _BaseQueNoSeToca:
    """Una «sesión» que falla si se la usa: el alta con grupo debe rechazar la clave reservada ANTES de consultar."""
    def __getattr__(self, nombre):
        raise AssertionError(f"no debía tocar la base ({nombre})")


class TestElAltaConGrupoNoCambia:
    @pytest.mark.asyncio
    async def test_la_clave_reservada_no_es_un_grupo_y_se_rechaza_sin_consultar(self):
        with pytest.raises(GrupoNoEncontradoError):
            await AltaDeSerie(_BaseQueNoSeToca(), secret=SECRETO).previsualizar(
                CLAVE_SIN_GRUPO, tradicion=ComicTradition.AMERICAN, manual=DatosManuales("Flash", 1987))

    def test_la_tradicion_sigue_sin_valor_por_defecto_tambien_sin_grupo(self):
        """G2: la tradición se elige."""
        for metodo in (AltaDeSerie.previsualizar, AltaDeSerie.previsualizar_sin_grupo):
            assert inspect.signature(metodo).parameters["tradicion"].default is inspect.Parameter.empty

    def test_no_hay_ninguna_ruta_nueva(self):
        """I1 no cambia la interfaz ni añade endpoints: el servicio sin grupo es lo único nuevo."""
        from zascarr.main import app
        rutas = {ruta for ruta in app.openapi()["paths"] if "/revision" in ruta}
        assert {"/api/revision/serie", "/api/revision/serie/previsualizar"} <= rutas
        assert not any("sin_grupo" in ruta or "sin-grupo" in ruta for ruta in rutas)
