"""#418 (BL-PORT3) commit 2: el lector de RAR con `unar` REAL y tres RAR mínimos (AC-07, AC-05 real).

Los tres ficheros de `tests/fixtures/rar/` se crearon a mano con `rar` (no es libre y no se puede
generar aquí): ver `tests/fixtures/rar/LEEME.md` para su contenido exacto y el comando. Las imágenes
son sintéticas. Estas pruebas se SALTAN si falta `unar` o un fixture, y la CI lo trata como un fallo
(`scripts/ci_rar_real.py`): una prueba saltada no es una pasada.
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

from zascarr.models import MotivoRar
from zascarr.utils import lector_rar
from zascarr.utils.lector_rar import ErrorRar, carpeta_temporal, listar
from zascarr.utils.portada_rar import portada_de_rar

FIXTURES = Path(__file__).parent / "fixtures" / "rar"
NOMBRES = ["minimo_rar4.cbr", "minimo_rar5.cbr", "solido_rar5.cbr"]

pytestmark = pytest.mark.skipif(
    shutil.which("unar") is None or shutil.which("lsar") is None, reason="unar/lsar no instalados")


def _fixture(nombre: str) -> Path:
    ruta = FIXTURES / nombre
    if not ruta.exists():
        pytest.skip(f"falta el fixture {nombre} (se crea a mano: tests/fixtures/rar/LEEME.md)")
    return ruta


@pytest.mark.parametrize("nombre", NOMBRES)
def test_rar_real_el_listado_trae_el_crc32_de_cada_pagina(nombre, tmp_path):
    """Supuesto S-1 de la spec: `lsar -j` da índice, nombre, tamaño y CRC32 por entrada. Si falta el
    CRC, la verificación de contenido de FR-05 se queda solo en `Image.load()`: que falle aquí."""
    with carpeta_temporal(tmp_path / "t") as tmp:
        lis = listar(_fixture(nombre), temporal=tmp)
    paginas = [e for e in lis.entradas if e.nombre.lower().endswith(".jpg")]
    assert len(paginas) >= 2
    assert all(e.crc32 is not None and e.tamano > 0 for e in paginas)


@pytest.mark.parametrize("nombre", NOMBRES)
def test_rar_real_la_portada_es_la_primera_pagina_y_decodifica(nombre, tmp_path):
    jpeg, tipo = portada_de_rar(_fixture(nombre), tmp_path / "covers", ancho=600)
    assert tipo == "image/jpeg"
    with Image.open(io.BytesIO(jpeg)) as img:
        img.load()
        assert img.width <= 600
        r, g, b = img.convert("RGB").getpixel((img.width // 2, img.height // 2))
    assert r > 150 and g < 100 and b < 100          # 01.jpg es rojo (LEEME.md)
    assert not (tmp_path / "covers" / ".rar-tmp").exists() or not list((tmp_path / "covers" / ".rar-tmp").iterdir())


def test_rar_real_un_archivo_truncado_no_da_portada(tmp_path):
    """Trampa medida en #308: `lsar` lista un truncado con código 0. No debe salir una portada."""
    original = _fixture("minimo_rar5.cbr").read_bytes()
    truncado = tmp_path / "truncado.cbr"
    truncado.write_bytes(original[: len(original) // 2])
    with pytest.raises(ErrorRar) as exc:
        portada_de_rar(truncado, tmp_path / "covers", ancho=600)
    assert exc.value.motivo in {MotivoRar.ILEGIBLE, MotivoRar.SIN_IMAGENES}


def test_rar_real_la_herramienta_esta_disponible():
    assert lector_rar.disponible() is True
