# ruff: noqa: E501
"""Snapshot publicable y filas de Estado/Ajustes (#134, PR-2; AC-09/AC-18)."""
from __future__ import annotations

from zascarr.services.cortesia_estado import (
    NOTA_BLOQUEOS,
    filas_cortesia,
    snapshot_publico,
    texto_politica_ajustes,
)


class Ajustes:
    comicvine_enabled = True
    anilist_enabled = False
    tebeosfera_enabled = True
    gcd_enabled = False
    forum_enabled = True
    forum_url = ""
    comicvine_rate_limit = 1.0
    anilist_rate_limit = 1.5
    tebeosfera_rate_limit = 2.5
    gcd_rate_limit = 2.0
    forum_rate_limit = 2.0


def _fuente(nombre: str, **kw) -> dict:
    base = dict(fuente=nombre, nombre=nombre.title(), habilitada=True, intervalo_min_s=1.0,
                max_intentos=3, max_redirecciones=3, esperando_ahora=0,
                siguiente_hueco_s=0.0, bloqueada_hasta_s=None, bloqueo_motivo=None,
                ultimos_intentos=[])
    base.update(kw)
    return base


def _snapshot(**kw) -> dict:
    datos = {
        "coordinacion": "proceso",
        "generado": "2026-11-05T15:00:00+00:00",
        "fuentes": [
            _fuente("comicvine", bloqueada_hasta_s=7.0, bloqueo_motivo="429",
                    esperando_ahora=2,
                    ultimos_intentos=[{"hace_s": 3.2, "intento": 2, "resultado": "429",
                                       "espera_s": 2.0}]),
            _fuente("anilist", habilitada=False, siguiente_hueco_s=1.5),
            _fuente("tebeosfera", siguiente_hueco_s=2.4),
            _fuente("gcd", habilitada=False),
            _fuente("foro", habilitada=False),
            _fuente("portada", intervalo_min_s=2.5),
        ],
        "hosts": [
            {"host": "https://comicvine.gamespot.com:443", "fuentes": ["comicvine"],
             "intervalo_min_s": 1.0, "esperando_ahora": 0, "siguiente_hueco_s": 0.0,
             "bloqueada_hasta_s": 7.0},
            {"host": "https://cdn.cbsistatic.com:443", "fuentes": ["comicvine", "portada"],
             "intervalo_min_s": 1.0, "esperando_ahora": 0, "siguiente_hueco_s": 0.0,
             "bloqueada_hasta_s": None},
            {"host": "https://10.0.0.5:8443", "fuentes": ["comicvine"],
             "intervalo_min_s": 1.0, "esperando_ahora": 0, "siguiente_hueco_s": 0.0,
             "bloqueada_hasta_s": None},
            {"host": "no-es-un-origen", "fuentes": [], "intervalo_min_s": 1.0,
             "esperando_ahora": 0, "siguiente_hueco_s": 0.0, "bloqueada_hasta_s": None},
        ],
    }
    datos.update(kw)
    return datos


class ServicioFalso:
    def __init__(self, datos): self._datos = datos
    def snapshot(self, _ajustes=None): return self._datos


class TestSnapshotPublico:
    def test_solo_publica_hosts_de_la_allowlist_y_sin_esquema_ni_puerto(self):
        datos = snapshot_publico(Ajustes(), servicio=ServicioFalso(_snapshot()))
        hosts = [h["host"] for h in datos["hosts"]]
        assert hosts == ["comicvine.gamespot.com", "cdn.cbsistatic.com"]
        assert all("://" not in h and ":" not in h for h in hosts)
        assert datos["coordinacion"] == "proceso"

    def test_no_hay_url_query_claves_ni_esquema_en_el_json(self):
        datos = snapshot_publico(Ajustes(), servicio=ServicioFalso(_snapshot()))
        serializado = repr(datos)
        assert "://" not in serializado
        for prohibido in ("api_key", "Authorization", "Cookie", "?q=", "Location"):
            assert prohibido not in serializado
        assert {f["fuente"] for f in datos["fuentes"]} == {
            "comicvine", "anilist", "tebeosfera", "gcd", "foro", "portada"}

    def test_hosts_repetidos_por_origen_se_unen_por_nombre(self):
        datos = snapshot_publico(Ajustes(), servicio=ServicioFalso(_snapshot(hosts=[
            {"host": "https://comicvine.gamespot.com:443", "fuentes": ["comicvine"],
             "intervalo_min_s": 1.0, "esperando_ahora": 0, "siguiente_hueco_s": 0.0,
             "bloqueada_hasta_s": None},
            {"host": "http://comicvine.gamespot.com:80", "fuentes": ["portada"],
             "intervalo_min_s": 2.5, "esperando_ahora": 0, "siguiente_hueco_s": 0.0,
             "bloqueada_hasta_s": None},
        ])))
        assert len(datos["hosts"]) == 1
        assert datos["hosts"][0]["host"] == "comicvine.gamespot.com"
        assert datos["hosts"][0]["fuentes"] == ["comicvine", "portada"]
        assert datos["hosts"][0]["intervalo_min_s"] == 2.5


class TestFilasDeEstado:
    def _filas(self):
        return filas_cortesia(snapshot_publico(Ajustes(), servicio=ServicioFalso(_snapshot())),
                              Ajustes())

    def test_bloqueo_espera_apagada_y_sin_configurar(self):
        filas = {f["fuente"]: f for f in self._filas()["filas"]}
        assert filas["Comicvine"]["estado"] == "Bloqueada temporalmente (~7 s)"
        assert filas["Comicvine"]["clase"] == "warn"
        assert filas["Comicvine"]["proxima"] == "En ~7 s"
        assert filas["Comicvine"]["reintentos"] == "Nos pidió esperar hace ~4 s"   # ceil(3.2) = 4
        assert filas["Anilist"]["estado"] == "Apagada"
        assert filas["Anilist"]["clase"] == "neutral"
        assert filas["Anilist"]["proxima"] == "—"
        assert filas["Foro"]["estado"] == "Sin configurar"
        assert filas["Tebeosfera"]["estado"] == "En espera (~3 s)"   # ceil(2.4) = 3
        assert "Portada" not in filas                                # no es fila de fuente

    def test_nota_de_bloqueo_y_de_apagada(self):
        contexto = self._filas()
        assert contexto["hay_bloqueos"] is True
        assert contexto["fuentes_bloqueadas"] == ["Comicvine"]
        assert contexto["nota_bloqueos"] == NOTA_BLOQUEOS
        assert contexto["nota_apagada"] == "No se consulta ni se reintenta."
        assert "no les preguntemos" in contexto["nota_bloqueos"]
        assert "puede que sigan sin responder" in contexto["nota_bloqueos"]
        assert "otra copia" in contexto["coordinacion"]
        assert "cada una espera por su cuenta" in contexto["coordinacion"]

    def test_los_intentos_no_ensenan_codigos_http(self):
        contexto = self._filas()
        for fila in contexto["filas"]:
            assert "429" not in fila["reintentos"]
            assert "4xx" not in fila["reintentos"]
            assert "5xx" not in fila["reintentos"]

    def test_apagadas_no_cuentan_como_fallo(self):
        contexto = self._filas()
        apagadas = [f for f in contexto["filas"] if f["estado"] == "Apagada"]
        assert apagadas and all(f["clase"] == "neutral" for f in apagadas)
        assert all(f["nota_apagada"] for f in apagadas)


class TestPoliticaDeAjustes:
    def test_usa_los_valores_de_config_no_escritos_a_mano(self):
        ajustes = Ajustes()
        ajustes.comicvine_rate_limit = 1.0
        ajustes.anilist_rate_limit = 1.5
        ajustes.gcd_rate_limit = 2.0
        contexto = texto_politica_ajustes(ajustes)
        assert ("Cortesía: Comic Vine 1 s y 3 intentos; AniList 1,5 s y 3; "
                "Tebeosfera 2,5 s y 1; GCD 2 s y 2.") in contexto["politica"]
        assert "sitio del que vienen y no se reintentan" in contexto["politica"]
        assert "cada una espera por su cuenta" in contexto["coordinacion"]

    def test_dice_que_fuentes_estan_apagadas(self):
        contexto = texto_politica_ajustes(Ajustes())
        assert contexto["apagadas"] == ["AniList", "GCD"]
        assert contexto["nota_apagada"] == "No se consulta ni se reintenta."


class TestDocumentoDeCoordinacion:
    def test_el_doc_y_claude_declaran_proceso_unico_y_sin_coordinacion(self):
        from pathlib import Path
        raiz = Path(__file__).resolve().parents[1]
        doc = (raiz / "docs" / "design" / "cortesia-compartida.md").read_text(encoding="utf-8")
        claude = (raiz / "CLAUDE.md").read_text(encoding="utf-8")
        for texto in ("un solo proceso", "No hay detección de multi-worker", "otras instalaciones",
                      "coordinacion", "no se coordinan"):
            assert texto in doc.replace("coordinación", "coordinacion"), texto
        assert "docs/design/cortesia-compartida.md" in claude
        assert "un solo\n  proceso" in claude or "un solo proceso" in claude
