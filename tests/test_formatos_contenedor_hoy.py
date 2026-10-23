# ruff: noqa: E501
"""Caracterización (spike #305, actualizada a propósito por #307): lo que ZascArr hace con cada contenedor. NO defiende que sea lo deseable:
fija el comportamiento medido en la ficha `docs/design/benchmark-formatos-contenedor.md` y el contrato `docs/design/contrato-307-formato-por-contenido.md`,
para que cualquier cambio (leer `.rar`, etc.) rompa estas pruebas a propósito y obligue a actualizar los documentos. Sintético: ni biblioteca real ni red.

Cambios de #307 respecto al estado «de hoy» original: un `.cbr` cuyo CONTENIDO es un ZIP con imágenes se lee (ComicInfo, portada); un `.cbz` que
es un RAR se avisa con causa y acción; `.tar`, `.cbt` y los contenedores sin extensión se avisan en la auditoría (antes: silencio)."""
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
        assert {n for n, f in filas.items() if f.lo_lista_el_importador} == {"a.cbz", "k.cbr", "l.cbr", "m.cbz"}

    def test_un_zip_con_extension_zip_se_lee_pero_no_se_recorre(self, filas):
        f = filas["b.zip"]          # `triage` lo abre (extensión .zip) pero `COMIC_EXTS` no incluye `.zip`: nunca llega al triaje
        assert (f.lo_lista_el_importador, f.lee_comicinfo, f.da_portada) == (False, True, True)

    def test_un_zip_sin_extension_sigue_sin_listarse_ni_leerse_pero_ahora_se_avisa(self, filas):
        c = filas["c_sin_ext"]      # D1 del contrato: no se registra (exigiría migrar el enum y dejaría al tagger escribir en él); se AVISA
        assert (c.lo_lista_el_importador, c.lee_comicinfo, c.da_portada) == (False, False, False)
        assert c.file_format == "" and any("triaje solo por filename" in w for w in c.avisos_triaje)
        assert "no acaba en .cbz, así que ZascArr no lo registra" in c.auditoria

    def test_un_cbr_que_por_dentro_es_un_zip_con_imagenes_se_lee_sin_tocarlo(self, filas):
        """El caso principal de #307 (56 ficheros en la biblioteca real): la extensión dice RAR, el contenido es un ZIP."""
        oculto = filas["l.cbr"]
        assert (oculto.lo_lista_el_importador, oculto.tiene_hash, oculto.da_portada) == (True, True, True)
        assert oculto.file_format == "cbr"                                  # la extensión DECLARADA no cambia
        assert oculto.auditoria == "—" and not any("solo por filename" in w for w in oculto.avisos_triaje)

    def test_un_cbz_que_es_un_rar_se_avisa_con_causa_y_accion(self, filas):
        m = filas["m.cbz"]
        assert (m.tiene_hash, m.lee_comicinfo, m.da_portada) == (True, False, False)
        assert m.auditoria.startswith("Se llama .cbz, pero por dentro es un .cbr (RAR)") and "no puede sacarle la portada" in m.auditoria

    def test_un_rar_o_cbr_nunca_se_abre_solo_se_hashea(self, filas):
        k, j = filas["k.cbr"], filas["j.rar"]
        assert (k.lo_lista_el_importador, k.tiene_hash, k.lee_comicinfo, k.da_portada) == (True, True, False, False)
        assert (j.lo_lista_el_importador, j.tiene_hash, j.lee_comicinfo) == (False, True, False)

    def test_la_auditoria_avisa_de_rar_7z_tar_cbt_doble_extension_y_contenedores_sin_extension(self, filas):
        assert filas["j.rar"].auditoria.startswith("Es un archivo .rar: ZascArr no lo registra")
        assert filas["d.cbz.rar"].auditoria.startswith("doble extensión (.cbz.rar)")
        assert filas["g.tar"].auditoria.startswith("ZascArr no usa este formato (TAR)")
        assert filas["i.cbt"].auditoria.startswith("ZascArr no usa este formato (CBT)")
        assert "(TAR) que ZascArr no usa" in filas["h_tar_sin_ext"].auditoria                       # un TAR no tiene final de tebeo que sugerir
        assert filas["k.cbr"].auditoria == "—"                                                      # RAR de verdad llamado .cbr: como siempre

    @pytest.mark.skipif(not banco.hay_7z(), reason="requiere `7z`")
    def test_7z_se_avisa_con_extension_y_no_sin_ella(self, filas):
        assert filas["e.7z"].auditoria.startswith("Es un archivo .7z: ZascArr no lo registra")
        assert "no acaba en .cb7" in filas["f_7z_sin_ext"].auditoria and not filas["f_7z_sin_ext"].lo_lista_el_importador

    def test_ningun_contenedor_que_no_sea_zip_da_portada_ni_comicinfo(self, filas):
        for nombre, f in filas.items():
            if nombre not in ("a.cbz", "b.zip", "l.cbr"):
                assert (f.lee_comicinfo, f.da_portada) == (False, False), nombre
