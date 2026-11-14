"""SCR4 — script de diagnóstico del foro: sin credenciales en pantalla (AC-DIA-1…4)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from zascarr.services.forum_scraper import ForumFloodControl

RAIZ = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "diagnostico_foro", RAIZ / "scripts" / "diagnostico_foro.py")
diagnostico = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(diagnostico)

BASE = "http://foro.example/forum"
CONTRASENA = "CLAVE_CANARIA_9f3"
COOKIE = "member_id=1; pass_hash=SECRETO_HASH; s=SESION_CANARIA"


def _ajustes(**kw):
    base = dict(forum_enabled=True, forum_url=BASE, forum_username="lector",
                forum_password=CONTRASENA)
    base.update(kw)
    return SimpleNamespace(**base)


async def _sin_espera(_segundos: float) -> None:
    return None


class ScraperFalso:
    """Scraper sin red con la misma superficie que usa el script."""

    def __init__(self, *, login=True, resultados=1, flood=None, tema=False):
        self.login_ok = login
        self.flood = flood
        self.resultados = resultados
        self.tema = tema
        self.estado_entrada = 200
        self.charset_entrada = ("text/html", "iso8859-1", "iso8859-1")
        self.cookies_recibidas = 2
        self.llamadas = 0

    async def login(self, _usuario: str, _clave: str) -> bool:
        self.llamadas += 1
        if self.flood is not None:
            raise ForumFloodControl("foro.example:80", self.flood)
        return self.login_ok

    async def use_ipb_search(self, _consulta: str, *, abrir_temas: bool = True):
        self.llamadas += 1
        if self.flood is not None:
            raise ForumFloodControl("foro.example:80", self.flood)
        return [SimpleNamespace(topic_url=f"{BASE}/index.php?showtopic=1")
                for _ in range(self.resultados)]

    async def leer_tema(self, _url: str):
        self.llamadas += 1
        return SimpleNamespace(ed2k_links=["ed2k://x"] if self.tema else [],
                               magnet_links=[])


def _ejecutar(ajustes, scraper, argv=()):
    lineas: list[str] = []
    fabricado: list[object] = []

    def fabrica(_ajustes):
        fabricado.append(_ajustes)
        return scraper

    codigo = diagnostico.main(list(argv), ajustes=ajustes, fabrica=fabrica,
                              salida=lineas.append, dormir=_sin_espera)
    return codigo, "\n".join(lineas), fabricado


# ── AC-DIA-1: sin configurar → explicación, exit 2 y 0 peticiones ─────────────────────────

@pytest.mark.parametrize("vacio", [
    {"forum_enabled": False}, {"forum_url": ""}, {"forum_username": ""},
    {"forum_password": ""},
])
def test_ac_dia_1_sin_configurar_sale_con_dos_y_no_pide_nada(vacio):
    codigo, salida, fabricado = _ejecutar(_ajustes(**vacio), ScraperFalso())
    assert codigo == 2 and fabricado == []
    assert "Faltan datos" in salida and "No se ha hecho ninguna petición" in salida


# ── AC-DIA-2: la contraseña, las cookies y s= nunca aparecen ──────────────────────────────

def test_ac_dia_2_no_imprime_contrasena_ni_cookies_ni_sesion():
    codigo, salida, _ = _ejecutar(_ajustes(), ScraperFalso())
    assert codigo == 0
    for secreto in (CONTRASENA, "SECRETO_HASH", "SESION_CANARIA", COOKIE, "s="):
        assert secreto not in salida
    assert "lector" not in salida


# ── AC-DIA-3: flood → exit 4 con segundos y sin muestra ──────────────────────────────────

def test_ac_dia_3_flood_sale_con_cuatro_segundos_y_sin_muestra():
    codigo, salida, _ = _ejecutar(_ajustes(), ScraperFalso(flood=42.0))
    assert codigo == 4
    assert "Flood: SÍ (~42 s)" in salida and "reintenta en 47 s" in salida
    assert "muestra" not in salida


# ── AC-DIA-4: salida copiable con los tres pasos y la conclusión ─────────────────────────

def test_ac_dia_4_la_salida_es_copiable_con_los_tres_pasos():
    codigo, salida, _ = _ejecutar(_ajustes(), ScraperFalso(resultados=7))
    assert codigo == 0
    assert "ZascArr — diagnóstico del foro (SCR4)" in salida
    assert "[1] Entrada: HTTP 200" in salida
    assert "charset meta: iso8859-1" in salida
    assert "[2] Login: OK (cookies recibidas: 2; no se imprimen)" in salida
    assert "[3] Búsqueda «Año Uno»" in salida and "resultados: 7" in salida
    assert "muestra: tema (sin título)" in salida
    assert "Conclusión: charset OK; sin flood; 7 resultados." in salida
    assert "no pegues el .env" in salida


def test_leer_tema_anade_un_paso_sin_imprimir_enlaces():
    codigo, salida, _ = _ejecutar(_ajustes(), ScraperFalso(resultados=1, tema=True),
                                  argv=["--leer-tema"])
    assert codigo == 0
    assert "[4] Tema: ed2k sí | magnet no" in salida
    assert "ed2k://" not in salida


def test_login_no_confirmado_sale_con_cinco():
    codigo, salida, _ = _ejecutar(_ajustes(), ScraperFalso(login=False))
    assert codigo == 5
    assert "Login: NO confirmado" in salida
    assert "No se ha buscado nada." in salida
