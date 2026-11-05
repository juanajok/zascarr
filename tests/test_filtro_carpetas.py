# ruff: noqa: E501
"""BL-FILT1 (#397): piezas del filtro de «Pendientes por carpeta» sin base de datos.

Cubre lo que es puro y por tanto se puede probar rápido, sin Postgres:

- La normalización de los parámetros de la URL (`_filtros_de_url`): valores inválidos
  → 200 con aviso, nunca 422/500 (AC-15/AC-16, parte sin HTML).
- La URL canónica de §3.3 y el contexto que viaja por el asistente (§6.1).
- El predicado del filtro (`RevisionCarpetas._pasa_filtro`): modelo de estados y
  pliegue del nombre (AC-07 y la tabla de AC-23, sin depender de la BD).
- El registro de acceso no lleva la query (AC-22, mecanismo de #361).
"""
from __future__ import annotations

import logging
from uuid import uuid4

from starlette.requests import Request

from zascarr.services.revision_carpetas import Grupo, PatronDeNombres, RevisionCarpetas
from zascarr.utils.log_acceso import MARCA_DE_QUERY_OMITIDA, SinQueryEnAcceso
from zascarr.web.contexto_carpetas import ContextoCarpetas
from zascarr.web.pendientes import _filtros_de_url, _url_de_carpetas


def _peticion(query: str = "") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/ui/pendientes/carpetas",
        "query_string": query.encode(), "headers": [],
    })


def _grupo(clave: str, estado: str = "sin_serie", *, por_confirmar: bool = False,
           en_conflicto: bool = False) -> Grupo:
    """Un `Grupo` mínimo para el predicado: no toca la BD."""
    return Grupo(
        clave=clave, carpeta_contextual=clave.rsplit("/", 1)[-1], ascendentes=[],
        carpeta_limpia=None, estado=estado, etiqueta=estado, n_archivos=1,
        patron_de_nombres=PatronDeNombres(titulo_dominante=None, proporcion=0.0, titulos_distintos=1),
        serie_sugerida=None, por_confirmar=por_confirmar, en_conflicto=en_conflicto,
        senales=[], archivos=[],
    )


class TestNormalizacionDeLaUrl:
    def test_filtro_valido_se_conserva(self):
        f = _filtros_de_url("  Batman  ", " sin_serie ", "1", "")
        assert (f["nombre"], f["estado"], f["por_confirmar"], f["en_conflicto"]) == (
            "Batman", "sin_serie", "1", "")
        assert f["activo"] is True and f["avisos"] == []

    def test_estado_invalido_se_descarta_con_aviso(self):
        for valor in ("inventado", "SIN_SERIE", " serie"):
            f = _filtros_de_url("", valor, "", "")
            assert f["estado"] == "" and f["avisos"], valor
        assert "El estado de la carpeta no es válido; se muestran todos los estados." in f["avisos"]

    def test_todas_es_sin_restriccion(self):
        f = _filtros_de_url("", "todas", "", "")
        assert f["estado"] == "" and f["avisos"] == [] and f["activo"] is False

    def test_marcas_solo_con_1(self):
        assert _filtros_de_url("", "", "1", "1")["por_confirmar"] == "1"
        for valor in ("2", "abc", "true", "0", ""):
            f = _filtros_de_url("", "", valor, valor)
            assert f["por_confirmar"] == "" and f["en_conflicto"] == ""
            assert f["avisos"] == []            # el control no emite otro valor: sin aviso

    def test_controles_y_longitud_con_los_avisos_de_283(self):
        controles = _filtros_de_url("Bat\x00man", "", "", "")
        assert controles["nombre"] == "Batman"
        assert "La búsqueda tenía caracteres no válidos; se han quitado." in controles["avisos"]
        larga = _filtros_de_url("x" * 250, "", "", "")
        assert len(larga["nombre"]) == 200
        assert "La búsqueda era demasiado larga; se han usado los primeros 200 caracteres." in larga["avisos"]

    def test_nombre_sin_palabras_avisa_y_sigue_activo(self):
        for texto in ("el", "los", "the", "¿?"):
            f = _filtros_de_url(texto, "", "", "")
            assert "El texto no contiene palabras que buscar; no se aplica el filtro de nombre." in f["avisos"]
            assert f["activo"] is True           # el filtro sigue activo para el recuento y el vacío

    def test_sin_filtro_no_hay_valores_ni_avisos(self):
        f = _filtros_de_url("", "", "", "")
        assert f["activo"] is False and f["avisos"] == []
        assert (f["nombre"], f["estado"], f["por_confirmar"], f["en_conflicto"]) == ("", "", "", "")


class TestUrlCanonica:
    def test_orden_y_omision_de_vacios(self):
        filtros = {"nombre": "batman", "estado": "sin_serie", "por_confirmar": "1",
                   "en_conflicto": "", "activo": True, "avisos": []}
        url = _url_de_carpetas(limite=10, serie="s-1", filtros=filtros, desplazamiento=20)
        assert url == ("/ui/pendientes/carpetas?limite=10&serie=s-1&nombre=batman"
                       "&estado=sin_serie&por_confirmar=1&desplazamiento=20")

    def test_sin_filtro_es_la_url_de_siempre(self):
        filtros = {"nombre": "", "estado": "", "por_confirmar": "", "en_conflicto": "",
                   "activo": False, "avisos": []}
        assert _url_de_carpetas(limite=50, serie="", filtros=filtros) == "/ui/pendientes/carpetas?limite=50"
        assert _url_de_carpetas(limite=2, serie="", filtros=filtros) == "/ui/pendientes/carpetas?limite=2"
        assert (_url_de_carpetas(limite=2, serie="", filtros=filtros, desplazamiento=4)
                == "/ui/pendientes/carpetas?limite=2&desplazamiento=4")

    def test_quitar_filtro_conserva_serie_y_limite(self):
        filtros = {"nombre": "batman", "estado": "", "por_confirmar": "", "en_conflicto": "", "activo": True}
        sin_filtro = {**filtros, "nombre": ""}
        assert _url_de_carpetas(limite=50, serie="s-1", filtros=sin_filtro) == (
            "/ui/pendientes/carpetas?limite=50&serie=s-1")
        assert _url_de_carpetas(limite=50, serie="", filtros=filtros) == (
            "/ui/pendientes/carpetas?limite=50&nombre=batman")


class TestContextoDelAsistente:
    def test_lee_y_reconstruye_los_siete_valores(self):
        ctx = ContextoCarpetas.desde(_peticion(
            "nombre=batman&estado=sin_serie&por_confirmar=1&en_conflicto=1"
            "&serie=s-1&limite=10&desplazamiento=20"))
        assert ctx.query == ("&nombre=batman&estado=sin_serie&por_confirmar=1"
                             "&en_conflicto=1&serie=s-1&limite=10&desplazamiento=20")
        assert ctx.campos == [("nombre", "batman"), ("estado", "sin_serie"),
                              ("por_confirmar", "1"), ("en_conflicto", "1"),
                              ("serie", "s-1"), ("limite", "10"),
                              ("desplazamiento", "20")]

    def test_limite_50_y_desplazamiento_0_no_viajan(self):
        ctx = ContextoCarpetas.desde(_peticion("nombre=x&limite=50&desplazamiento=0"))
        assert ctx.query == "&nombre=x"
        assert ctx.url("/ui/pendientes/carpetas") == "/ui/pendientes/carpetas?nombre=x"

    def test_valores_invalidos_se_descartan(self):
        ctx = ContextoCarpetas.desde(_peticion(
            "estado=INVENTADO&por_confirmar=2&limite=x&desplazamiento=-3&serie="))
        assert ctx.estado == "" and ctx.por_confirmar == "" and ctx.limite == ""
        assert ctx.desplazamiento == "" and ctx.serie == "" and ctx.query == ""

    def test_une_con_el_separador_correcto(self):
        ctx = ContextoCarpetas.desde(_peticion("nombre=x&estado=mixto"))
        assert ctx.url("/ui/x") == "/ui/x?nombre=x&estado=mixto"
        assert ctx.url("/ui/x?clave=1") == "/ui/x?clave=1&nombre=x&estado=mixto"
        assert ctx.con(estado="").url("/ui/x") == "/ui/x?nombre=x"


class TestPredicadoDelFiltro:
    """AC-07 y la tabla de AC-23 sin BD: el predicado es el mismo que usa el servicio."""

    @staticmethod
    def _pasa(grupo: Grupo, *, nombre: str = "", estado: str = "",
              por_confirmar: bool = False, en_conflicto: bool = False) -> bool:
        from zascarr.core.matcher import normalize_title
        return RevisionCarpetas._pasa_filtro(
            grupo, normalize_title(nombre), estado, por_confirmar, en_conflicto)

    def test_estado_excluyente(self):
        a = _grupo("Q/A", "mixto", por_confirmar=True, en_conflicto=False)
        b = _grupo("Q/B", "mixto", por_confirmar=True, en_conflicto=True)
        c = _grupo("Q/C", "sin_serie", por_confirmar=False, en_conflicto=True)
        d = _grupo("Q/D", "sin_serie", por_confirmar=False, en_conflicto=False)
        assert [g.clave for g in (a, b, c, d) if self._pasa(g, estado="mixto")] == ["Q/A", "Q/B"]
        assert [g.clave for g in (a, b, c, d) if self._pasa(g, en_conflicto=True)] == ["Q/B", "Q/C"]
        assert [g.clave for g in (a, b, c, d)
                if self._pasa(g, estado="mixto", en_conflicto=True)] == ["Q/B"]
        assert [g.clave for g in (a, b, c, d) if self._pasa(g, por_confirmar=True)] == ["Q/A", "Q/B"]
        # (c) sin serie con conflicto: `mixto` no es «en conflicto» (el modelo no lo confunde).
        assert not self._pasa(c, estado="mixto")

    def test_nombre_y_estado_se_combinan_con_y(self):
        sugerida = _grupo("Comics/Batman (2019)", "serie_sugerida", por_confirmar=True)
        sin = _grupo("Comics/Batman Sin Serie", "sin_serie")
        assert self._pasa(sugerida, nombre="batman", estado="sin_serie") is False
        assert self._pasa(sin, nombre="batman", estado="sin_serie") is True

    def test_tabla_de_pliegue_de_la_normalizacion(self):
        # (clave, consulta, ¿coincide?) — exactamente la tabla de AC-23.
        casos = [
            ("Q/Straße", "ß", True), ("Q/Straße", "ss", False), ("Q/Strasse", "ss", True),
            ("Q/Søren", "ø", True), ("Q/Søren", "o", False),
            ("Q/Æon", "æ", True), ("Q/Æon", "ae", False),
            ("Q/Œuvre", "œ", True), ("Q/Œuvre", "oe", False),
            ("Q/Đorđe", "đ", True), ("Q/Đorđe", "d", False),
            ("Q/Łódź", "ł", True), ("Q/Łódź", "l", False),
            ("Q/Guðrún", "ð", True), ("Q/Guðrún", "d", False),
            ("Q/Þór", "þ", True), ("Q/Þór", "th", False),
            ("Q/Ħal", "ħ", True), ("Q/Ħal", "h", False),
            ("Q/Kırmızı", "ı", True), ("Q/Kırmızı", "i", False),
            ("Q/Istanbul", "I", True),
            ("Q/½", "½", True), ("Q/½", "1/2", True), ("Q/½", "12", False),
        ]
        for clave, consulta, coincide in casos:
            assert self._pasa(_grupo(clave), nombre=consulta) is coincide, (clave, consulta)

    def test_articulos_y_puntuacion(self):
        assert self._pasa(_grupo("Comics/Los Vengadores"), nombre="vengadores") is True
        assert self._pasa(_grupo("Comics/El Sandman"), nombre="sandman") is True
        assert self._pasa(_grupo("Comics/S.H.I.E.L.D."), nombre="shield") is True
        # Un nombre que normaliza a vacío no restringe: la vista ya avisa.
        for articulo in ("el", "los", "the"):
            assert self._pasa(_grupo("Comics/El Sandman"), nombre=articulo) is True


class TestPrivacidadDelRegistroDeAcceso:
    def test_la_query_con_el_filtro_no_sale_en_el_registro_de_acceso(self):
        registro = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:5", "GET",
             "/ui/pendientes/carpetas?nombre=CENTINELA-PRIV-9Q&estado=inventado", "1.1", 200), None)
        assert SinQueryEnAcceso().filter(registro) is True
        assert "CENTINELA-PRIV-9Q" not in registro.getMessage()
        assert "/ui/pendientes/carpetas" in registro.getMessage()
        assert registro.getMessage().endswith(MARCA_DE_QUERY_OMITIDA + ' HTTP/1.1" 200')
