# ruff: noqa: E501
"""#418 (BL-PORT3) commit 2: el lector de RAR con `unar` REAL y tres RAR mínimos (AC-07, AC-05 real).

Los tres ficheros de `tests/fixtures/rar/` se crearon a mano con `rar` (no es libre y no se puede
generar aquí): ver `tests/fixtures/rar/LEEME.md` para su contenido exacto y el comando. Las imágenes
son sintéticas. Estas pruebas se SALTAN si falta `unar` o un fixture, y la CI lo trata como un fallo
(`scripts/ci_rar_real.py`): una prueba saltada no es una pasada.
"""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tests._rar_hostiles import CASOS, ESPERADO, generar
from zascarr.models import MotivoRar
from zascarr.utils import lector_rar
from zascarr.utils.lector_rar import ErrorRar, carpeta_temporal, listar
from zascarr.utils.portada_rar import portada_de_rar

FIXTURES = Path(__file__).parent / "fixtures" / "rar"
NOMBRES = ["minimo_rar4.cbr", "minimo_rar5.cbr", "solido_rar4.cbr"]

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
    try:
        jpeg, tipo = portada_de_rar(_fixture(nombre), tmp_path / "covers", ancho=600)
    except ErrorRar as exc:
        # diagnóstico: el lector no conserva el mensaje (podría llevar rutas); aquí sí se ve cómo contesta unar
        salida = tmp_path / "diag"
        salida.mkdir()
        for orden in (["unar", "-v"], ["lsar", "-j", str(_fixture(nombre))],
                      ["unar", "-D", "-f", "-i", "-o", str(salida), str(_fixture(nombre)), "0"]):
            p = subprocess.run(orden, capture_output=True, text=True, cwd=tmp_path)   # noqa: S603
            print(f"{orden[0]} rc={p.returncode}\nstdout={p.stdout[:600]!r}\nstderr={p.stderr[:600]!r}")
        pytest.fail(f"{nombre}: {exc.motivo.value}; salida de lsar/unar arriba")
    assert tipo == "image/jpeg"
    with Image.open(io.BytesIO(jpeg)) as img:
        img.load()
        assert img.width <= 600
        r, g, b = img.convert("RGB").getpixel((img.width // 2, img.height // 2))
    assert r > 150 and g < 100 and b < 100          # 01.jpg es rojo (LEEME.md)
    assert not (tmp_path / "covers" / ".rar-tmp").exists() or not list((tmp_path / "covers" / ".rar-tmp").iterdir())


@pytest.mark.xfail(strict=True, raises=ErrorRar, reason=(
    "limitación de unar: no extrae un RAR 5 SÓLIDO (creado con rar 7.11): «Attempted to read more data "
    "than was available». Medido con unar/lsar 1.10.1 (el que empaqueta Debian bookworm, imagen de "
    "producción) y con 1.10.8 (runner de CI). Efecto: `ilegible` → marca de fallo → cascada, sin 500. "
    "Si una versión futura lo arregla, esta prueba pasa a XPASS y (strict) falla: hay que retirar el xfail."))
def test_rar_real_un_rar5_solido_no_se_lee_limitacion_conocida_de_unar(tmp_path):
    jpeg, _ = portada_de_rar(_fixture("solido_rar5.cbr"), tmp_path / "covers", ancho=600)
    assert jpeg


def test_rar_real_el_enlace_simbolico_se_extrae_como_enlace_dentro_del_destino(tmp_path):
    """SecOps (opcional): `unar` directo sobre el RAR del enlace deja un SYMLINK en el destino, no un fichero:
    por eso el lector (que lo rechaza con `lstat`) es la línea de defensa y no `unar`."""
    ruta = generar(tmp_path / "entrada", "enlace.cbr")
    destino = tmp_path / "salida"
    destino.mkdir()
    p = subprocess.run(["unar", "-D", "-f", "-i", "-o", str(destino), str(ruta), "0"],   # noqa: S603
                       capture_output=True, text=True, cwd=tmp_path)
    enlaces = [x for x in destino.rglob("*") if x.is_symlink()]
    assert p.returncode == 0 and len(enlaces) == 1, f"rc={p.returncode} {p.stdout!r}"
    assert not (tmp_path / "etc").exists()                  # y nada fuera del destino


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


def _foto(raiz: Path) -> set[str]:
    return {str(p.relative_to(raiz)) for p in raiz.rglob("*")}


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_rar_real_hostil_da_el_resultado_esperado_y_no_escribe_fuera(caso, tmp_path):
    """M-3 y N-1 (SecOps, generador v2): traversal, ruta absoluta, comodines, salto de línea, enlace simbólico y dos
    tamaños que mienten, leídos con `unar` REAL. Cada caso da el resultado ESPERADO (`ESPERADO`, no «cualquier
    motivo»: si un `unar` sanea distinto, la prueba falla y hay que documentarlo, no suavizarla); nunca aparece
    nada fuera del temporal, el temporal se borra, ningún nombre llega al mensaje del error y no hay otra
    excepción que `ErrorRar`."""
    ruta = generar(tmp_path / "entrada", caso)
    covers = tmp_path / "covers"
    covers.mkdir()
    antes = _foto(tmp_path)
    try:
        jpeg, _ = portada_de_rar(ruta, covers, ancho=600)
        resultado = "portada"
        assert jpeg
    except ErrorRar as exc:
        assert "secops" not in str(exc).lower() and "passwd" not in str(exc).lower()
        assert exc.motivo in set(MotivoRar)
        resultado = exc.motivo.value
    assert resultado == ESPERADO[caso], f"{caso}: salió {resultado!r}, se esperaba {ESPERADO[caso]!r}"
    nuevos = _foto(tmp_path) - antes
    assert nuevos <= {".rar-tmp"} | {"covers/.rar-tmp"}, f"escribió fuera del temporal: {sorted(nuevos)}"
    assert not list((covers / ".rar-tmp").iterdir()) if (covers / ".rar-tmp").exists() else True
    assert not list(Path("/tmp").glob("secops-*")), "escribió en /tmp fuera del destino"
