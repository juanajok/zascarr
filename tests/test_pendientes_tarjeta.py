# ruff: noqa: E501
"""U12 (#199) — la tarjeta de «Por revisar» a escala: portada en tres casos, nombre íntegro y texto del Inicio.
Casos 9–15 de la ficha `docs/design/benchmark-U12-pendientes-escala.md`. Sin Postgres: la lista se alimenta con la
sesión falsa del resto de pruebas de Por revisar; la verificación en NAVEGADOR a 375 px está en `docs/design/ui-u12/`.

Los tres casos de portada (decisión de producto del revisor de #213):
  · AUSENCIA CONOCIDA: la extensión no tiene extractor → ni `<img>`, ni petición `/portada`, ni bloque;
  · DISPONIBILIDAD DESCONOCIDA: es `.cbz`/`.zip` → `<img loading="lazy" alt="">` sin `aspect-ratio` y sin `onerror`:
    si falla, mide 0 px y no deja hueco;
  · DISPONIBLE: va DEBAJO del nombre, que no queda fuera del primer pantallazo.
Rechazado: devolver 200 con un SVG, y abrir o hacer `stat` de archivos al renderizar.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient  # noqa: F401  (lo usa `use_fake_session`)

from tests.test_pendientes import FakeSession, cola_de, use_fake_session
from tests.test_web_css_contraste import CSS_RUTA, _reglas
from zascarr.models import File, FileFormat
from zascarr.utils.cover import (
    EXTENSIONES_CON_PORTADA,
    extract_cover_thumbnail,
    puede_tener_portada,
)


def _archivo(nombre: str, formato: FileFormat) -> File:
    return File(id=uuid4(), file_path=f"/lib/_Unsorted/{nombre}", file_name=nombre, file_format=formato,
                metadata_={"match_status": "unsorted"})


def _tarjetas(*archivos: File) -> dict[str, str]:
    with use_fake_session(FakeSession(exec_queue=cola_de(list(archivos)))) as client:
        r = client.get("/ui/pendientes")
    assert r.status_code == 200
    salida = {}
    for f in archivos:
        m = re.search(rf'<div class="pending-card" id="card-{f.id}">(.*?)\n  </div>\n', r.text, re.S)
        assert m, f"no se encontró la tarjeta de {f.file_name}"
        salida[f.file_name] = m.group(1)
    return salida


# ── 9. Ausencia conocida ──────────────────────────────────────────────────────────────────────
class TestAusenciaConocida:

    @pytest.mark.parametrize("nombre,formato", [
        ("Flash 01.cbr", FileFormat.CBR), ("Flash 02.cb7", FileFormat.CB7),
        ("Flash 03.pdf", FileFormat.PDF), ("Flash 04.epub", FileFormat.EPUB)])
    def test_sin_extractor_no_hay_img_ni_peticion_ni_bloque(self, nombre, formato):
        t = _tarjetas(_archivo(nombre, formato))[nombre]
        assert "<img" not in t and "/portada" not in t and 'class="cover' not in t
        assert nombre in t                                         # el resto de la tarjeta sigue

    def test_el_predicado_es_el_mismo_que_el_del_extractor(self, tmp_path: Path):
        """Si el predicado dijera «puede» y el extractor «no» (o al revés), la pantalla mentiría. Se comprueba con
        archivos reales: para cada extensión, el extractor da una miniatura SI Y SOLO SI el predicado lo permite."""
        from io import BytesIO

        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (40, 60), (200, 50, 50)).save(buf, format="PNG")
        for sufijo in (".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".pdf", ".epub"):
            ruta = tmp_path / f"x{sufijo}"
            with zipfile.ZipFile(ruta, "w") as z:                  # mismo contenido para todas
                z.writestr("001.png", buf.getvalue())
            hay_miniatura = extract_cover_thumbnail(ruta) is not None
            assert puede_tener_portada(ruta.name) is hay_miniatura, sufijo
            assert (sufijo in EXTENSIONES_CON_PORTADA) is hay_miniatura, sufijo

    def test_el_predicado_no_distingue_mayusculas_ni_toca_el_disco(self):
        assert puede_tener_portada("FLASH 01.CBZ") and not puede_tener_portada("Flash 01.CBR")
        assert not puede_tener_portada("sin_extension")


# ── 10. Disponibilidad desconocida: sin hueco y sin onerror ───────────────────────────────────
class TestDisponibilidadDesconocida:

    def test_un_cbz_pide_la_portada_con_carga_diferida_y_sin_onerror(self):
        t = _tarjetas(_archivo("Flash 01.cbz", FileFormat.CBZ))["Flash 01.cbz"]
        img = re.search(r"<img[^>]*>", t, re.S).group(0)
        assert 'loading="lazy"' in img and 'alt=""' in img and 'class="cover"' in img
        assert "onerror" not in t and "cover-missing" not in t

    def test_la_regla_de_la_portada_no_reserva_espacio(self):
        """Medido en Chrome 154 (docs/design/benchmark-U12-experimento): con `aspect-ratio` una imagen rota ocupa su
        bloque; sin él y con `height: auto` mide 0 px. Esta prueba fija el mecanismo, no el resultado en el navegador."""
        reglas = [d for s, d in _reglas() if s.strip() == ".pending-card .cover"]
        assert reglas, "no hay regla para la portada de la tarjeta"
        for d in reglas:
            assert "aspect-ratio" not in d and d.get("height") == "auto", d
        assert not any("cover-missing" in s and "pending-card" in s for s, _ in _reglas())

    def test_ninguna_plantilla_de_pendientes_usa_onerror(self):
        plantillas = CSS_RUTA.parents[1] / "web" / "templates"
        for nombre in ("_tarjeta_pendiente.html", "pendientes.html"):
            assert "onerror" not in (plantillas / nombre).read_text("utf-8"), nombre


# ── 11. Disponible: debajo del nombre ─────────────────────────────────────────────────────────
class TestPortadaBajoElNombre:

    def test_el_nombre_va_antes_que_la_portada_en_el_orden_de_lectura(self):
        t = _tarjetas(_archivo("Flash 01.cbz", FileFormat.CBZ))["Flash 01.cbz"]
        assert t.index('class="filename"') < t.index("<img")

    def test_la_portada_tiene_un_tope_de_ancho_para_no_empujar_las_acciones(self):
        reglas = [d for s, d in _reglas() if s.strip() == ".pending-card .cover"]
        assert reglas and all("max-width" in d or "width" in d for d in reglas)
        ancho = reglas[0].get("width", "") + reglas[0].get("max-width", "")
        assert "120px" in ancho or "40%" in ancho, ancho


# ── 12. Nombre íntegro ────────────────────────────────────────────────────────────────────────
class TestNombreIntegro:

    def test_el_nombre_no_se_corta_con_elipsis_y_se_parte_si_no_cabe(self):
        reglas = [d for s, d in _reglas() if s.strip() == ".filename"]
        assert reglas
        for d in reglas:
            assert d.get("white-space") != "nowrap" and d.get("text-overflow") != "ellipsis", d
            assert d.get("overflow-wrap") == "anywhere", d

    def test_el_nombre_largo_sin_espacios_llega_entero_al_html(self):
        largo = "Los_Guardianes_del_Alba_Omnigold_Edicion_Especial_Integral_Tomo_" + "x" * 80 + ".cbz"
        t = _tarjetas(_archivo(largo, FileFormat.CBZ))[largo]
        assert f'<div class="filename" title="{largo}">{largo}</div>' in t


# ── 13. Inicio ────────────────────────────────────────────────────────────────────────────────
class TestTextoDelInicio:

    def test_no_promete_resolverlos_uno_a_uno_y_usa_el_texto_acordado(self):
        from zascarr.services import primeros_pasos
        fuente = Path(primeros_pasos.__file__).read_text("utf-8")
        assert "uno a uno" not in fuente.lower()
        assert "Revisa los archivos pendientes y elige a qué serie pertenecen." in fuente


# ── 14. Teclado ───────────────────────────────────────────────────────────────────────────────
class TestPaginadorNativo:

    def test_los_enlaces_son_anclas_nativas_y_cada_nav_tiene_su_nombre(self):
        from tests.test_pendientes import FakeExecResult
        archivos = [_archivo(f"Flash {i:02d}.cbz", FileFormat.CBZ) for i in range(3)]
        archivos_con_fecha = cola_de(archivos)
        # forzar «hay siguiente»: total mayor que lo mostrado
        archivos_con_fecha[0] = FakeExecResult(120)
        with use_fake_session(FakeSession(exec_queue=archivos_con_fecha)) as client:
            t = client.get("/ui/pendientes").text
        navs = re.findall(r'<nav class="pend-paginas[^"]*" aria-label="([^"]+)"', t)
        assert len(navs) == 2 and len(set(navs)) == 2, navs     # dos landmarks con nombre distinto
        assert re.search(r'<a class="pend-siguiente" href="/ui/pendientes\?despues=', t)
