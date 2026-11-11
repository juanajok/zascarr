# ruff: noqa: E501
"""`DiscoveryService.search_detallada` (MIT-M8-US01, #133): estados CERRADOS por fuente y capacidad.

El conjunto cerrado es `ok`, `sin_resultados`, `fallo_transitorio`, `configuracion_incompleta`,
`limite_de_cortesia` y `fuente_apagada`; la capacidad verificada en esta entrega es `busqueda`.
Una fuente apagada o sin configurar no se instancia ni se consulta, una que falla o limita no
tumba a las demás, y `search` conserva su contrato de siempre (tupla resultados/avisos).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from zascarr.models import MetadataSource
from zascarr.services.anilist import AniListResult
from zascarr.services.comic_vine import CVResult
from zascarr.services.discovery import (
    CAPACIDAD_BUSQUEDA,
    ESTADOS_DE_FUENTE,
    FUENTE_APAGADA,
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
    ORDEN_DE_FUENTES,
    Busqueda,
    DiscoveryService,
)
from zascarr.services.gcd import GCDResult
from zascarr.services.tebeosfera import TebeosferaResult
from zascarr.utils.cortesia import CortesiaEnEspera
from zascarr.utils.peticiones import ReintentosAgotados


def _ctx(valor):
    cliente = AsyncMock()
    cliente.__aenter__.return_value = cliente
    cliente.search_series = AsyncMock(return_value=valor)
    cliente.search_manga = AsyncMock(return_value=valor)
    return MagicMock(return_value=cliente)


def _roto(mensaje="caída"):
    cliente = AsyncMock()
    cliente.__aenter__.side_effect = RuntimeError(mensaje)
    return MagicMock(return_value=cliente)


def _limite(espera=42):
    cliente = AsyncMock()
    cliente.__aenter__.side_effect = CortesiaEnEspera("anilist", "anilist.co", espera, "cortesia")
    return MagicMock(return_value=cliente)


def _limite_429():
    cliente = AsyncMock()
    cliente.__aenter__.side_effect = ReintentosAgotados("anilist", 3, 429)
    return MagicMock(return_value=cliente)


def _ajustes(**kw) -> SimpleNamespace:
    base = dict(comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True, gcd_enabled=True,
                comicvine_api_key="clave")
    base.update(kw)
    return SimpleNamespace(**base)


CV = [CVResult(cv_id=1, name="Batman", start_year=2011)]
AL = [AniListResult(anilist_id=2, title_romaji="Naruto")]
TB = [TebeosferaResult(slug="thorgal_1981", title="Thorgal", kind="saga")]
GC = [GCDResult(gcd_id=3, name="Batman", language="es", country="ES")]


async def _busca(monkeypatch, *, ajustes=None, cv=None, al=None, tb=None, gc=None):
    monkeypatch.setattr("zascarr.services.discovery.get_settings", lambda: ajustes or _ajustes())
    with patch("zascarr.services.discovery.ComicVineClient", cv or _ctx(CV)), \
         patch("zascarr.services.discovery.AniListClient", al or _ctx(AL)), \
         patch("zascarr.services.discovery.TebeosferaClient", tb or _ctx(TB)), \
         patch("zascarr.services.discovery.GCDClient", gc or _ctx(GC)):
        return await DiscoveryService(db=MagicMock()).search_detallada("algo")


# ── 1. Estados diferenciados por fuente y capacidad ───────────────────────────────────────────

async def test_todas_ok(monkeypatch):
    b = await _busca(monkeypatch)
    # Las cuatro fuentes de siempre están OK; Metron y Open Library siguen apagadas por
    # defecto (no se configuran en este fixture y no deben consultarse).
    viejas = (MetadataSource.COMIC_VINE, MetadataSource.ANILIST,
              MetadataSource.TEBEOSFERA, MetadataSource.GCD)
    assert {f.value: b.fuentes[f.value] for f in viejas} == {
        f.value: FUENTE_OK for f in viejas}
    assert b.fuentes[MetadataSource.METRON.value] == FUENTE_APAGADA
    assert b.fuentes[MetadataSource.OPEN_LIBRARY.value] == FUENTE_APAGADA
    assert len(b.resultados) == 4 and b.avisos == []
    assert {d.estado for f, d in b.detalles.items() if f in {x.value for x in viejas}} == {
        FUENTE_OK}


async def test_el_conjunto_de_estados_es_cerrado(monkeypatch):
    """Solo existen los seis estados de #133; no se cuela `error` ni `apagada` heredados."""
    assert {
        "ok", "sin_resultados", "fallo_transitorio", "configuracion_incompleta",
        "limite_de_cortesia", "fuente_apagada",
    } == ESTADOS_DE_FUENTE
    b = await _busca(monkeypatch)
    assert set(b.fuentes.values()) <= ESTADOS_DE_FUENTE
    assert {d.estado for d in b.detalles.values()} <= ESTADOS_DE_FUENTE


async def test_las_cuatro_fuentes_siempre_aparecen_y_en_orden(monkeypatch):
    b = await _busca(monkeypatch, ajustes=_ajustes(
        comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False, gcd_enabled=False))
    assert list(b.fuentes) == [f.value for f in ORDEN_DE_FUENTES]
    assert list(b.detalles) == [f.value for f in ORDEN_DE_FUENTES]
    assert b.fuentes == {f.value: FUENTE_APAGADA for f in ORDEN_DE_FUENTES}
    assert b.resultados == [] and b.avisos == []


async def test_cada_detalle_corresponde_a_su_fuente_y_capacidad(monkeypatch):
    b = await _busca(monkeypatch, ajustes=_ajustes(gcd_enabled=False))
    assert set(b.detalles) == {f.value for f in ORDEN_DE_FUENTES}
    for nombre, detalle in b.detalles.items():
        assert detalle.fuente == nombre
        assert detalle.capacidad == CAPACIDAD_BUSQUEDA
        assert detalle.estado == b.fuentes[nombre]
        assert detalle.estado in ESTADOS_DE_FUENTE


async def test_la_capacidad_verificada_es_solo_busqueda(monkeypatch):
    """No se declaran metadatos ni portadas como capacidad verificada en esta entrega."""
    b = await _busca(monkeypatch)
    assert {d.capacidad for d in b.detalles.values()} == {CAPACIDAD_BUSQUEDA}
    assert CAPACIDAD_BUSQUEDA == "busqueda"


# ── 2. Fuente apagada sin tráfico ─────────────────────────────────────────────────────────────

async def test_una_fuente_apagada_no_se_consulta_y_las_demas_si(monkeypatch):
    cv = _ctx(CV)
    b = await _busca(monkeypatch, cv=cv, ajustes=_ajustes(comicvine_enabled=False))
    assert b.fuentes["comic_vine"] == FUENTE_APAGADA
    assert b.detalles["comic_vine"].motivo and "Ajustes" in b.detalles["comic_vine"].motivo
    assert {b.fuentes[k] for k in ("anilist", "tebeosfera", "gcd")} == {FUENTE_OK}
    cv.assert_not_called()                              # ni se instancia el cliente
    assert len(b.resultados) == 3


async def test_todas_apagadas_no_tocan_la_red_y_no_fingen_ausencia(monkeypatch):
    """Una búsqueda sin fuentes activas NO es «sin resultados» ni un fallo: es `fuente_apagada`."""
    clientes = {n: _ctx(v) for n, v in (("cv", CV), ("al", AL), ("tb", TB), ("gc", GC))}
    b = await _busca(monkeypatch, cv=clientes["cv"], al=clientes["al"], tb=clientes["tb"], gc=clientes["gc"],
                     ajustes=_ajustes(comicvine_enabled=False, anilist_enabled=False,
                                      tebeosfera_enabled=False, gcd_enabled=False))
    for cliente in clientes.values():
        cliente.assert_not_called()
        cliente.return_value.search_series.assert_not_called()
    assert set(b.fuentes.values()) == {FUENTE_APAGADA}
    assert b.resultados == []


# ── 3 y 8. Configuración incompleta, separada y sin tráfico ───────────────────────────────────

async def test_comic_vine_sin_clave_es_configuracion_incompleta_sin_trafico(monkeypatch):
    cv = _ctx(CV)
    b = await _busca(monkeypatch, cv=cv, ajustes=_ajustes(comicvine_api_key=""))
    assert b.fuentes["comic_vine"] == FUENTE_CONFIGURACION_INCOMPLETA
    assert b.detalles["comic_vine"].motivo and "clave" in b.detalles["comic_vine"].motivo
    assert b.detalles["comic_vine"].estado != FUENTE_FALLO_TRANSITORIO
    cv.assert_not_called()
    assert b.fuentes["anilist"] == FUENTE_OK and len(b.resultados) == 3


async def test_la_configuracion_incompleta_no_se_confunde_con_un_fallo(monkeypatch):
    b = await _busca(monkeypatch, ajustes=_ajustes(comicvine_api_key=""))
    assert b.fuentes["comic_vine"] == FUENTE_CONFIGURACION_INCOMPLETA != FUENTE_FALLO_TRANSITORIO
    assert any("Comic Vine" in a and "no está configurado" in a for a in b.avisos)


# ── 4. Éxito vacío ≠ error ────────────────────────────────────────────────────────────────────

async def test_una_fuente_que_responde_sin_resultados_es_sin_resultados(monkeypatch):
    b = await _busca(monkeypatch, tb=_ctx([]))
    assert b.fuentes["tebeosfera"] == FUENTE_SIN_RESULTADOS
    assert b.detalles["tebeosfera"].motivo and "coincidencias" in b.detalles["tebeosfera"].motivo
    assert b.fuentes["comic_vine"] == FUENTE_OK and len(b.resultados) == 3
    assert not any("Tebeosfera" in a for a in b.avisos)     # ausencia de datos no es un aviso de fallo


# ── 5. Fallo transitorio ──────────────────────────────────────────────────────────────────────

async def test_una_fuente_caida_es_fallo_transitorio_y_no_tumba_las_demas(monkeypatch):
    b = await _busca(monkeypatch, tb=_roto())
    assert b.fuentes["tebeosfera"] == FUENTE_FALLO_TRANSITORIO
    assert b.detalles["tebeosfera"].motivo and "No ha respondido" in b.detalles["tebeosfera"].motivo
    assert {b.fuentes[k] for k in ("comic_vine", "anilist", "gcd")} == {FUENTE_OK}
    assert any("Tebeosfera" in a for a in b.avisos) and len(b.resultados) == 3


# ── 6 y 7. Límite de cortesía, separado del fallo y sin plazo inventado ──────────────────────

async def test_el_limite_de_cortesia_con_plazo_lo_conserva(monkeypatch):
    b = await _busca(monkeypatch, al=_limite(42))
    assert b.fuentes["anilist"] == FUENTE_LIMITE_DE_CORTESIA
    detalle = b.detalles["anilist"]
    assert detalle.reintentar_en == 42 and "esperar" in detalle.motivo
    assert b.fuentes["anilist"] != FUENTE_FALLO_TRANSITORIO
    assert any("AniList" in a and "esperar" in a for a in b.avisos)
    assert len(b.resultados) == 3


async def test_el_limite_de_cortesia_sin_plazo_no_inventa_uno(monkeypatch):
    b = await _busca(monkeypatch, al=_limite_429())
    assert b.fuentes["anilist"] == FUENTE_LIMITE_DE_CORTESIA
    assert b.detalles["anilist"].reintentar_en is None


# ── Contrato de siempre y consulta vacía ──────────────────────────────────────────────────────

async def test_search_conserva_su_contrato_de_pareja(monkeypatch):
    monkeypatch.setattr("zascarr.services.discovery.get_settings", _ajustes)
    with patch("zascarr.services.discovery.ComicVineClient", _ctx(CV)), \
         patch("zascarr.services.discovery.AniListClient", _ctx(AL)), \
         patch("zascarr.services.discovery.TebeosferaClient", _ctx(TB)), \
         patch("zascarr.services.discovery.GCDClient", _ctx(GC)):
        r, a = await DiscoveryService(db=MagicMock()).search("algo")
    assert isinstance(r, list) and a == [] and len(r) == 4


async def test_consulta_vacia_no_busca_y_no_finge_estados():
    b = await DiscoveryService(db=MagicMock()).search_detallada("   ")
    assert b.resultados == [] and b.avisos == []
    assert set(b.fuentes.values()) == {FUENTE_APAGADA}
    assert all(d.estado == FUENTE_APAGADA and "No se ha consultado" in d.motivo
               for d in b.detalles.values())


def test_una_busqueda_construida_a_mano_completa_detalles_sin_inventar():
    """Compatibilidad: quien solo daba `fuentes` sigue funcionando; las fuentes ausentes no se inventan."""
    b = Busqueda([], [], {"comic_vine": FUENTE_SIN_RESULTADOS})
    assert set(b.detalles) == {"comic_vine"}
    assert b.detalles["comic_vine"].estado == FUENTE_SIN_RESULTADOS
    assert b.detalles["comic_vine"].capacidad == CAPACIDAD_BUSQUEDA
    assert b.detalles["comic_vine"].motivo is None and b.detalles["comic_vine"].reintentar_en is None


# ── 6. Recuperación explícita (la apagada que se enciende vuelve a consultarse) ───────────────

async def test_una_fuente_apagada_que_se_enciende_vuelve_a_consultarse(monkeypatch):
    ajustes = _ajustes(comicvine_enabled=False)
    cv = _ctx(CV)
    monkeypatch.setattr("zascarr.services.discovery.get_settings", lambda: ajustes)
    with patch("zascarr.services.discovery.ComicVineClient", cv), \
         patch("zascarr.services.discovery.AniListClient", _ctx(AL)), \
         patch("zascarr.services.discovery.TebeosferaClient", _ctx(TB)), \
         patch("zascarr.services.discovery.GCDClient", _ctx(GC)):
        primera = await DiscoveryService(db=MagicMock()).search_detallada("algo")
        assert primera.fuentes["comic_vine"] == FUENTE_APAGADA
        cv.assert_not_called()

        ajustes.comicvine_enabled = True          # el servicio (Ajustes) la reactiva
        segunda = await DiscoveryService(db=MagicMock()).search_detallada("algo")

    assert segunda.fuentes["comic_vine"] == FUENTE_OK
    cv.return_value.search_series.assert_called_once()
    assert len(segunda.resultados) == 4


# ── 2. Ni identificadores internos ni causas inventadas en los motivos ────────────────────────

async def test_los_motivos_son_texto_para_la_persona_sin_identificadores(monkeypatch):
    b = await _busca(monkeypatch, ajustes=_ajustes(comicvine_api_key=""),
                     al=_limite(30), tb=_roto(), gc=_ctx([]))
    textos = [d.motivo for d in b.detalles.values() if d.motivo] + b.avisos
    assert textos
    for texto in textos:
        assert "comic_vine" not in texto and "COMIC_VINE" not in texto
        assert ".env" not in texto and "API_KEY" not in texto
        assert "Traceback" not in texto and "RuntimeError" not in texto
        assert "http://" not in texto and "https://" not in texto


# ── #134 §6.5: la espera por cortesía NO es un estado nuevo; es `limite_de_cortesia` ─────────

async def test_cortesia_en_espera_es_limite_de_cortesia_con_el_aviso_6_5(monkeypatch):
    b = await _busca(monkeypatch, al=_limite(42))
    assert b.fuentes["anilist"] == FUENTE_LIMITE_DE_CORTESIA
    assert "espera" not in b.fuentes.values()
    detalle = b.detalles["anilist"]
    assert detalle.estado == FUENTE_LIMITE_DE_CORTESIA and detalle.reintentar_en == 42
    assert "por cortesía" in detalle.motivo and "No se ha enviado nada" in detalle.motivo
    assert "~42 s" in detalle.motivo
    assert b.fuentes["anilist"] != FUENTE_FALLO_TRANSITORIO


async def test_la_espera_sin_estimacion_no_inventa_segundos(monkeypatch):
    b = await _busca(monkeypatch, al=_limite(0))
    detalle = b.detalles["anilist"]
    assert b.fuentes["anilist"] == FUENTE_LIMITE_DE_CORTESIA
    assert detalle.reintentar_en is None and "~" not in detalle.motivo
    assert "hay que esperar por cortesía" in detalle.motivo
