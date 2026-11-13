"""#155: mosaico local 2:3 de portada de colección (sin red)."""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image

from zascarr.services import portada_coleccion as pc


def _jpeg(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 450), color).save(path, format="JPEG")
    return path


def test_mosaico_1_2_3_4_y_aspecto():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        rutas = [_jpeg(Path(tmp) / f"{i}.jpg", (i * 40, 20, 30)) for i in range(1, 5)]
        for n in (1, 2, 3, 4):
            datos = pc.componer_mosaico(rutas[:n])
            with Image.open(io.BytesIO(datos)) as img:
                assert img.format == "JPEG"
                assert (img.width, img.height) == (600, 900)


def test_portada_cacheada_orden_v3_externa_legado(tmp_path):
    sid = uuid4()
    _jpeg(tmp_path / "v3" / f"{sid}.jpg", (1, 2, 3))
    assert pc.portada_cacheada(tmp_path, sid) == tmp_path / "v3" / f"{sid}.jpg"
    _jpeg(tmp_path / "externa" / f"{sid}.jpg", (4, 5, 6))
    assert pc.portada_cacheada(tmp_path, sid) == tmp_path / "v3" / f"{sid}.jpg"
    (tmp_path / "v3" / f"{sid}.jpg").unlink()
    assert pc.portada_cacheada(tmp_path, sid) == tmp_path / "externa" / f"{sid}.jpg"


def test_huella_cambia_con_miembro_y_portada(tmp_path):
    covers = tmp_path / "covers"
    sid = uuid4()
    _jpeg(covers / "v3" / f"{sid}.jpg", (1, 2, 3))
    serie = SimpleNamespace(id=sid, sort_title="A", title="A")
    h1 = pc._huella([serie], covers)
    h2 = pc._huella([serie, SimpleNamespace(id=uuid4(), sort_title="B", title="B")], covers)
    assert h1 != h2
    _jpeg(covers / "v3" / f"{sid}.jpg", (9, 9, 9))
    assert pc._huella([serie], covers) != h1


def test_symlink_en_covers_no_cuenta_como_portada(tmp_path):
    sid = uuid4()
    fuera = tmp_path / "fuera.jpg"
    _jpeg(fuera, (1, 2, 3))
    enlace = tmp_path / "covers" / "v3" / f"{sid}.jpg"
    enlace.parent.mkdir(parents=True)
    enlace.symlink_to(fuera)
    assert pc.portada_cacheada(tmp_path / "covers", sid) is None


def test_imagen_demasiado_grande_no_se_decodifica(tmp_path):
    ruta = tmp_path / "grande.jpg"
    Image.new("RGB", (2200, 2000), (1, 2, 3)).save(ruta, format="JPEG")
    assert ruta.stat().st_size > 0
    assert pc._leer_jpeg(ruta) is None
    import pytest
    with pytest.raises(ValueError):
        pc.componer_mosaico([ruta])
