"""BL-IT03 (#286) + UATP-02: retorno local, canónico, con foco y sin historial."""
from __future__ import annotations

import inspect
from urllib.parse import parse_qs, parse_qsl, unquote, urlsplit
from uuid import uuid4

import pytest

from zascarr.web.library import (
    PARAMETROS_DE_BIBLIOTECA,
    Filtros,
    _leer_filtros,
    _qs,
)
from zascarr.web.library import (
    router as library_router,
)
from zascarr.web.retorno import MAX_VOLVER, url_de_ficha, volver_segura


def _filtros(**kw) -> Filtros:
    return _leer_filtros(
        kw.get("page", "1"), kw.get("q", ""), kw.get("tradition", ""),
        kw.get("publisher_id", ""), kw.get("character_id", ""),
        kw.get("story_arc_id", ""), kw.get("vista", ""), kw.get("etiquetas", ""),
        kw.get("leido", ""), kw.get("orden", ""), kw.get("coleccion", ""),
        author_id=kw.get("author_id", ""), favoritos=kw.get("favoritos", ""),
        idioma=kw.get("idioma", ""), edicion=kw.get("edicion", ""),
        anio_desde=kw.get("anio_desde", ""), anio_hasta=kw.get("anio_hasta", ""),
        densidad=kw.get("densidad", ""), modo=kw.get("modo", ""),
        naturaleza=kw.get("naturaleza", ""), formato=kw.get("formato", ""),
        puntuacion=kw.get("puntuacion", ""),
    )


def _canonica(**kw) -> str:
    filtros = _filtros(**kw)
    return _qs(filtros, page=filtros.page)


def _destino(query: str, sid) -> str:
    return f"/ui/biblioteca?{query}&foco={sid}#serie-{sid}"


def test_allowlist_derivada_de_la_ruta_y_sincronizada():
    ruta = next(r for r in library_router.routes
                if r.path == "/ui/biblioteca" and "GET" in r.methods)
    reales = {param.alias or param.name for param in ruta.dependant.query_params}
    assert reales == PARAMETROS_DE_BIBLIOTECA
    assert "foco" in PARAMETROS_DE_BIBLIOTECA
    firma = set(inspect.signature(_leer_filtros).parameters)
    assert firma == PARAMETROS_DE_BIBLIOTECA - {"foco"}
    completo = Filtros(
        q="thor", tradition="manga", publisher_id=str(uuid4()),
        character_id=str(uuid4()), story_arc_id=str(uuid4()),
        author_id=str(uuid4()), favorito=True, language="es",
        edition_kind="oficial", year_from="1990", year_to="2000",
        etiquetas="x", leido="si", orden="reciente", coleccion="completa",
        vista="lista", densidad="grande", modo="escaparate",
        naturaleza="regular", formato="grapa", puntuacion="con",
    )
    claves = {nombre for nombre, _ in parse_qsl(_qs(completo, page=2))}
    assert claves | {"foco"} == PARAMETROS_DE_BIBLIOTECA


def test_la_url_de_la_ficha_lleva_estado_foco_y_ancla():
    sid = uuid4()
    url = url_de_ficha(sid, "/ui/biblioteca?q=thorgal&page=2")
    destino = unquote(urlsplit(url).query.removeprefix("volver="))
    partes = urlsplit(destino)
    assert partes.path == "/ui/biblioteca"
    assert parse_qs(partes.query) == {
        "q": ["thorgal"], "page": ["2"], "foco": [str(sid)]}
    assert partes.fragment == f"serie-{sid}"
    assert volver_segura(destino, sid) == destino


@pytest.mark.parametrize("campos", [
    {}, {"q": "thor"}, {"tradition": "manga"},
    {"publisher_id": "00000000-0000-0000-0000-000000000001"},
    {"character_id": "00000000-0000-0000-0000-000000000002"},
    {"story_arc_id": "00000000-0000-0000-0000-000000000003"},
    {"author_id": "00000000-0000-0000-0000-000000000004"},
    {"favoritos": "1"}, {"idioma": "es"}, {"edicion": "oficial"},
    {"anio_desde": "1990"}, {"anio_hasta": "2000"},
    {"etiquetas": "x"}, {"leido": "si"}, {"orden": "reciente"},
    {"coleccion": "completa"}, {"vista": "lista"},
    {"densidad": "grande"}, {"modo": "escaparate"},
    {"naturaleza": "regular"}, {"formato": "grapa"}, {"puntuacion": "con"},
    {"page": "2"},
])
def test_cada_filtro_canonico_vuelve_entero(campos):
    if campos.get("modo") == "escaparate":
        campos = {"modo": "escaparate"}
    sid = uuid4()
    query = _canonica(**campos)
    destino = _destino(query, sid)
    assert volver_segura(destino, sid) == destino


def test_todos_los_filtros_juntos_vuelven_enteros():
    sid = uuid4()
    query = _canonica(
        q="thor", tradition="manga", favoritos="1", idioma="es",
        edicion="oficial", anio_desde="1990", anio_hasta="2000",
        etiquetas="x", leido="si", orden="reciente", coleccion="completa",
        vista="lista", naturaleza="regular", formato="grapa",
        puntuacion="con", densidad="grande", page="2")
    destino = _destino(query, sid)
    assert volver_segura(destino, sid) == destino


@pytest.mark.parametrize("query", [
    "page=0", "page=01", "page=%C2%B2", "page=%D9%A3",
    "anio_desde=199&page=1", "anio_desde=2001&anio_hasta=2000&page=1",
    "vista=tarjetas&page=1", "orden=titulo&page=1",
    "q=" + "x" * 201 + "&page=1",
    "page=1&page=2", "page=1&x=1",
    "tradition=inexistente&page=1",
    "etiquetas=" + " ".join(f"t{i}" for i in range(13)) + "&page=1",
])
def test_query_no_canonica_se_rechaza(query):
    sid = uuid4()
    assert volver_segura(f"/ui/biblioteca?{query}#serie-{sid}", sid) is None


@pytest.mark.parametrize("valor", [
    "///ui/biblioteca", "//ui/biblioteca", "//evil.example/ui/biblioteca",
    "https://evil.example/ui/biblioteca", "javascript:alert(1)",
    "/\\ui/biblioteca", "/ui/biblioteca\\",
    " /ui/biblioteca", "\t/ui/biblioteca", "/ui/biblioteca?q=x%0a&page=1",
    "/ui/biblioteca/%2e%2e", "/ui/%2e%2e/ui/biblioteca",
    "/ui/biblioteca%2f", "/ui/biblioteca?page=1&foco=x",
])
def test_volver_rechaza_destinos_hostiles(valor):
    assert volver_segura(valor) is None


def test_el_ancla_debe_ser_la_de_esta_ficha():
    sid, otra = uuid4(), uuid4()
    assert volver_segura(
        _destino(_canonica(page="1"), sid), sid) is not None
    assert volver_segura(
        _destino(_canonica(page="1"), otra), sid) is None
    assert volver_segura(
        f"/ui/biblioteca?page=1#serie-{otra}", sid) is None


def test_volver_sin_foco_sigue_valiendo():
    sid = uuid4()
    valor = f"/ui/biblioteca?page=1#serie-{sid}"
    assert volver_segura(valor) == valor
    assert volver_segura(valor, sid) == valor


def test_volver_sin_query_es_la_forma_por_defecto():
    assert volver_segura("/ui/biblioteca") == "/ui/biblioteca"
    assert volver_segura("/ui/biblioteca?") is None
    assert volver_segura("/ui/biblioteca#") is None


def test_volver_acepta_la_ficha_de_una_coleccion_sin_query_ni_ancla():
    cid = uuid4()
    valor = f"/ui/colecciones/{cid}"
    assert volver_segura(valor) == valor
    assert volver_segura(valor + "#x") is None
    assert volver_segura("/ui/colecciones/no-es-uuid") is None


def test_volver_acepta_el_estado_de_una_coleccion():
    from zascarr.web.colecciones import _url_ficha

    cid = uuid4()
    query = _url_ficha(cid, "thor", "manga", [], 2, "tarjetas").split("?", 1)[1]
    valor = f"/ui/colecciones/{cid}?{query}"
    assert volver_segura(valor) == valor


@pytest.mark.parametrize("query", [
    "serie_ids=" + str(uuid4()), "cambio_vista=1",
    "pagina=0", "pagina=²", "vista=otra", "q=x&desconocido=1",
    "pagina=1&pagina=2",
])
def test_estado_de_coleccion_invalido_se_rechaza(query):
    cid = uuid4()
    assert volver_segura(f"/ui/colecciones/{cid}?{query}") is None


def test_una_url_canonica_larga_se_acepta_y_otra_mayor_no():
    sid = uuid4()
    valor = _destino(_canonica(q="ñ" * 200, page="1"), sid)
    assert len(valor) < MAX_VOLVER
    assert volver_segura(valor, sid) == valor
    assert volver_segura("/ui/biblioteca?q=" + "x" * (MAX_VOLVER + 1)) is None
