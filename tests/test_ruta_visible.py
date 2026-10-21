# ruff: noqa: E501
"""La ruta que se le ENSEÑA a la persona es la del host (HOST_LIBRARY_DIR), no la del contenedor (`/media/library`)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from zascarr.config import Settings
from zascarr.utils.ruta_visible import ruta_visible

BIB = "/media/library"
HOST = "/media/WDElements/Tebeos"
RAIZ = Path(__file__).resolve().parents[1]


class TestTraduccion:

    def test_cambia_el_prefijo_de_la_biblioteca_por_el_del_host(self):
        r = ruta_visible("/media/library/Comics/The Wicked + The Divine (2014)/The Wicked + The Divine 001.cbr", biblioteca=BIB, host=HOST)
        assert r == "/media/WDElements/Tebeos/Comics/The Wicked + The Divine (2014)/The Wicked + The Divine 001.cbr"

    @pytest.mark.parametrize("host", ["", "   ", None])
    def test_sin_host_se_devuelve_la_ruta_tal_cual(self, host):
        assert ruta_visible("/media/library/a.cbz", biblioteca=BIB, host=host or "") == "/media/library/a.cbz"

    def test_si_el_host_es_el_mismo_no_cambia_nada(self):
        assert ruta_visible("/media/library/a.cbz", biblioteca=BIB, host="/media/library/") == "/media/library/a.cbz"

    def test_barras_finales_no_duplican_separadores(self):
        assert ruta_visible("/media/library/a.cbz", biblioteca=BIB + "/", host=HOST + "/") == HOST + "/a.cbz"

    def test_la_propia_biblioteca(self):
        assert ruta_visible(BIB, biblioteca=BIB, host=HOST) == HOST

    def test_una_carpeta_hermana_con_el_mismo_prefijo_no_cuelga_de_la_biblioteca(self):
        assert ruta_visible("/media/library2/a.cbz", biblioteca=BIB, host=HOST) == "/media/library2/a.cbz"

    def test_una_ruta_de_fuera_de_la_biblioteca_no_se_toca(self):
        assert ruta_visible("/media/downloads/a.cbz", biblioteca=BIB, host=HOST) == "/media/downloads/a.cbz"

    def test_solo_cambia_el_prefijo_aunque_el_resto_lo_repita(self):
        r = ruta_visible("/media/library/media/library/a.cbz", biblioteca=BIB, host=HOST)
        assert r == HOST + "/media/library/a.cbz"

    def test_usa_la_configuracion_por_defecto(self, monkeypatch):
        from zascarr.utils import ruta_visible as modulo
        monkeypatch.setattr(modulo, "get_settings", lambda: Settings(library_path=BIB, host_library_dir=HOST))
        assert ruta_visible("/media/library/a.cbz") == HOST + "/a.cbz"


class TestConfiguracionYCompose:

    def test_host_library_dir_se_lee_del_entorno(self, monkeypatch):
        monkeypatch.setenv("HOST_LIBRARY_DIR", HOST)
        assert Settings().host_library_dir == HOST

    def test_por_defecto_esta_vacia(self, monkeypatch):
        monkeypatch.delenv("HOST_LIBRARY_DIR", raising=False)
        assert Settings(_env_file=None).host_library_dir == ""

    def test_compose_le_pasa_al_contenedor_la_ruta_real(self):
        texto = (RAIZ / "docker-compose.yml").read_text()
        assert re.search(r"^\s*- HOST_LIBRARY_DIR=\$\{HOST_LIBRARY_DIR:-\}\s*$", texto, re.M)
        # y sigue montándola donde la app la lee
        assert "${HOST_LIBRARY_DIR:-/media/library}:/media/library" in texto
