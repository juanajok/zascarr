# ruff: noqa: E501
"""`core/carpetas.py` — lectura pura del nombre de las carpetas (rebanada 1). Sin BD, sin disco.

La cobertura de `limpiar_carpeta` viene de `tests/test_medir_carpetas.py` (donde vivía antes de moverse al
núcleo, para que la comparta el servicio de revisión).
"""
from __future__ import annotations

import pytest

from zascarr.core.carpetas import (
    CONTENEDORES,
    UMBRAL_AUTOR_O_CONTENEDOR,
    analizar_carpeta,
    dividir_ruta,
    es_contenedor,
    limpiar_carpeta,
    texto_incluye,
)


class TestLimpiarCarpeta:

    @pytest.mark.parametrize("carpeta,titulo,anio", [
        ("Flash (1987)", "Flash", 1987),
        ("JSA (1999)", "JSA", 1999),
        ("Arrowsmith (COMPLETO)(CRG)", "Arrowsmith", None),
        ("Superman Vol2 (Ed.Zinco)(1987-96)", "Superman Vol2", 1987),
        ("Locke & Key [HD]", "Locke & Key", None),
        ("Green Lantern - Saga de Geoff Johns", "Green Lantern - Saga de Geoff Johns", None),
    ])
    def test_titulo_y_anio(self, carpeta, titulo, anio):
        t, a, _ = limpiar_carpeta(carpeta)
        assert (t, a) == (titulo, anio)

    def test_las_etiquetas_se_separan_no_se_pierden(self):
        _, _, etiquetas = limpiar_carpeta("Arrowsmith (COMPLETO)(CRG)")
        assert etiquetas == ["(COMPLETO)", "(CRG)"]


class TestContenedores:
    """Decisión de revisión (2026-10-06): lista FIJA, `_*` más seis nombres, sin acentos ni mayúsculas."""

    def test_la_lista_es_exactamente_la_decidida(self):
        assert frozenset({"varios", "revisar", "otros", "specials", "omnibus"}) == CONTENEDORES

    @pytest.mark.parametrize("nombre", [
        "_Omnibus", "_Unsorted", "_", "varios", "Varios", "REVISAR", "Otros", "Specials", "Omnibus", "Ómnibus",
    ])
    def test_son_contenedores(self, nombre):
        assert es_contenedor(nombre)

    @pytest.mark.parametrize("nombre", [
        "Batman", "Otros Mundos", "Omnibus de Marvel", "Variedades", "Specials Vol 2", "X_Men",
    ])
    def test_no_lo_son(self, nombre):
        # Solo cuenta el nombre ENTERO: «Otros Mundos» es una serie, no un cajón de sastre.
        assert not es_contenedor(nombre)

    def test_el_umbral_inicial_es_el_decidido(self):
        assert UMBRAL_AUTOR_O_CONTENEDOR == 20


class TestAnalizarCarpeta:

    def test_saga_de_un_autor(self):
        c = analizar_carpeta("Batman - Saga de Scott Snyder (2019)")
        assert (c.titulo, c.anio, c.volumen, c.calificadores) == ("Batman", 2019, None, ["Saga de Scott Snyder"])
        assert c.titulo_completo == "Batman - Saga de Scott Snyder"

    def test_volumen_y_edicion(self):
        c = analizar_carpeta("Superman Vol2 (Ed.Zinco)(1987-96)")
        assert (c.titulo, c.anio, c.volumen) == ("Superman", 1987, 2)
        assert c.calificadores == ["Ed.Zinco", "Vol 2"]

    def test_edicion_dentro_del_titulo(self):
        c = analizar_carpeta("Capitan America Omnigold")
        assert c.titulo == "Capitan America" and c.calificadores == ["Omnigold"]

    def test_una_editorial_no_es_un_calificador_de_serie(self):
        c = analizar_carpeta("Inferno (Panini)(2022)")
        assert c.titulo == "Inferno" and c.anio == 2022
        assert c.calificadores == [] and c.etiquetas == ["(Panini)"]

    def test_un_nombre_que_empieza_por_ed_no_es_una_edicion(self):
        # «(Eduardo)» no es «(Ed.…)»: no se inventan calificadores.
        assert analizar_carpeta("Historias (Eduardo)").calificadores == []

    def test_las_etiquetas_de_release_no_son_calificadores(self):
        c = analizar_carpeta("Arrowsmith (COMPLETO)(CRG)")
        assert c.calificadores == [] and c.etiquetas == ["(COMPLETO)", "(CRG)"]

    def test_sin_adornos(self):
        c = analizar_carpeta("Absolute Batman (2024)")
        assert (c.titulo, c.anio, c.volumen, c.calificadores) == ("Absolute Batman", 2024, None, [])


class TestDividirRuta:

    def test_carpeta_de_serie_bajo_la_tradicion(self):
        d = dividir_ruta(("Comics", "Batman (2016)"))
        assert (d.clave, d.contextual, d.ascendentes) == ("Comics/Batman (2016)", "Batman (2016)", ("Comics",))

    def test_se_salta_el_contenedor_subiendo(self):
        d = dividir_ruta(("Comics", "_Omnibus", "Dinastia y Potencias de X"))
        assert d.contextual == "Dinastia y Potencias de X"
        assert d.ascendentes == ("Comics", "_Omnibus")

    def test_un_contenedor_dentro_de_la_serie_no_roba_el_contexto(self):
        d = dividir_ruta(("Comics", "Batman (2016)", "Extras"))
        assert d.contextual == "Extras"           # «Extras» no está en la lista fija: no se adivina
        d = dividir_ruta(("Comics", "Batman (2016)", "_Extras"))
        assert d.contextual == "Batman (2016)" and d.ascendentes == ("Comics",)

    def test_todo_contenedores_no_hay_contexto(self):
        d = dividir_ruta(("Comics", "_Omnibus", "Varios"))
        assert d.contextual is None and d.ascendentes == ("Comics", "_Omnibus", "Varios")

    def test_directamente_en_la_tradicion(self):
        d = dividir_ruta(("Comics",))
        assert d.clave == "Comics" and d.contextual is None

    def test_en_la_raiz(self):
        d = dividir_ruta(())
        assert d.clave == "." and d.contextual is None and d.ascendentes == ()

    def test_la_clave_distingue_tradiciones(self):
        a = dividir_ruta(("Graphic Novels", "Carlos Gimenez"))
        b = dividir_ruta(("Tebeos", "Carlos Giménez"))
        assert a.clave != b.clave


class TestTextoIncluye:

    @pytest.mark.parametrize("completo,parte", [
        ("Batman - Saga de Scott Snyder", "Saga de Scott Snyder"),
        ("Superman Vol 2", "Vol 2"),
        ("Superman Vol2", "Vol 2"),               # pegado o separado, es lo mismo
        ("La Patrulla-X", "patrulla x"),
        ("Giménez", "gimenez"),
    ])
    def test_incluye(self, completo, parte):
        assert texto_incluye(completo, parte)

    @pytest.mark.parametrize("completo,parte", [
        ("BATMAN", "Saga de Scott Snyder"),
        ("Superman", "Vol 2"),
        ("Superman Vol 12", "Vol 2"),             # 2 no está dentro de 12 como palabra
        ("Batman", ""),
    ])
    def test_no_incluye(self, completo, parte):
        assert not texto_incluye(completo, parte)
