# ruff: noqa: E501
"""Caracterización (spike #305): lo que ZascArr hace HOY con cada contenedor. NO defiende que sea lo deseable: fija el punto de partida
medido en la ficha `docs/design/benchmark-formatos-contenedor.md`, para que cualquier cambio de comportamiento (leer `.rar`, detectar por
contenido, etc.) rompa estas pruebas a propósito y obligue a actualizar la ficha. Sintético: ni biblioteca real ni red."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("banco_formatos_comportamiento", RAIZ / "scripts" / "medicion" / "banco_formatos_comportamiento.py")
banco = importlib.util.module_from_spec(_spec)
sys.modules["banco_formatos_comportamiento"] = banco
_spec.loader.exec_module(banco)


@pytest.fixture(scope="module")
def filas():
    return {f.nombre: f for f in banco.medir()}


class TestHoy:

    def test_el_importador_solo_recorre_las_extensiones_de_comic(self, filas):
        assert {n for n, f in filas.items() if f.lo_lista_el_importador} == {"a.cbz", "k.cbr"}

    def test_un_zip_con_extension_zip_se_lee_pero_no_se_recorre(self, filas):
        f = filas["b.zip"]          # `triage` lo abre (extensión .zip) pero `COMIC_EXTS` no incluye `.zip`: nunca llega al triaje
        assert (f.lo_lista_el_importador, f.lee_comicinfo, f.da_portada) == (False, True, True)

    def test_la_decision_es_por_la_extension_no_por_el_contenido(self, filas):
        c = filas["c_sin_ext"]      # un ZIP legible sin extensión: ni se lista ni se lee, aunque su contenido sea un tebeo
        assert (c.lo_lista_el_importador, c.lee_comicinfo, c.da_portada) == (False, False, False)
        assert c.file_format == "" and any("triaje solo por filename" in w for w in c.avisos_triaje)

    def test_un_rar_o_cbr_nunca_se_abre_solo_se_hashea(self, filas):
        k, j = filas["k.cbr"], filas["j.rar"]
        assert (k.lo_lista_el_importador, k.tiene_hash, k.lee_comicinfo, k.da_portada) == (True, True, False, False)
        assert (j.lo_lista_el_importador, j.tiene_hash, j.lee_comicinfo) == (False, True, False)

    def test_la_auditoria_avisa_de_rar_y_7z_y_de_la_doble_extension_pero_no_del_tar_ni_del_sin_extension(self, filas):
        assert filas["j.rar"].auditoria.startswith("formato no soportado (RAR")
        assert filas["d.cbz.rar"].auditoria.startswith("doble extensión (.cbz.rar)")
        for nombre in ("g.tar", "h_tar_sin_ext", "i.cbt", "c_sin_ext", "k.cbr"):
            assert filas[nombre].auditoria == "—", nombre

    @pytest.mark.skipif(not banco.hay_7z(), reason="requiere `7z`")
    def test_7z_se_avisa_con_extension_y_no_sin_ella(self, filas):
        assert filas["e.7z"].auditoria.startswith("formato no soportado (7Z")
        assert filas["f_7z_sin_ext"].auditoria == "—" and not filas["f_7z_sin_ext"].lo_lista_el_importador

    def test_ningun_contenedor_que_no_sea_zip_da_portada_ni_comicinfo(self, filas):
        for nombre, f in filas.items():
            if nombre not in ("a.cbz", "b.zip"):
                assert (f.lee_comicinfo, f.da_portada) == (False, False), nombre
