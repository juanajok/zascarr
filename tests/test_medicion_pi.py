"""Pruebas unitarias de la herramienta de medición E (#326).

No necesitan PostgreSQL ni la Pi: cubren los topes, la validación de la BD,
el montaje de solo lectura, la selección estratificada y el generador.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MEDICION = RAIZ / "scripts" / "medicion"


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


medir = _cargar("medir_pi", MEDICION / "medir_registro_incremental_pi.py")
generar = _cargar("preparar_sinteticos", MEDICION / "preparar_sinteticos.py")


def test_parse_bytes():
    assert medir.parse_bytes("15GiB") == 15 * 1024 ** 3
    assert medir.parse_bytes("100MB") == 100 * 1024 ** 2
    assert medir.parse_bytes("1.5g") == int(1.5 * 1024 ** 3)
    assert medir.parse_bytes("1024") == 1024
    with pytest.raises(argparse.ArgumentTypeError):
        medir.parse_bytes("mucho")


def test_validar_db_url_exige_test_y_tipo():
    base = "postgresql+asyncpg://u:p@localhost:5432/"
    assert medir.validar_db_url(base + "zascarr_medicion_ref_test_1", "search") == (
        "zascarr_medicion_ref_test_1"
    )
    assert medir.validar_db_url(base + "zascarr_medicion_reg_test_1", "register") == (
        "zascarr_medicion_reg_test_1"
    )
    with pytest.raises(medir.ErrorDeMedicion):
        medir.validar_db_url(base + "zascarr", "search")
    with pytest.raises(medir.ErrorDeMedicion):
        medir.validar_db_url(base + "zascarr_medicion_ref_test_1", "register")
    with pytest.raises(medir.ErrorDeMedicion):
        medir.validar_db_url(base + "produccion", "search")


def test_montaje_solo_lectura(tmp_path):
    montajes = tmp_path / "mounts"
    montajes.write_text(
        "/dev/root / ext4 rw,relatime 0 0\n"
        "/dev/sdc1 /media/library ext4 ro,relatime 0 0\n"
        "/dev/sda1 /media/Backup ext4 rw,relatime 0 0\n",
        encoding="utf-8",
    )
    assert medir.es_solo_lectura(Path("/media/library/sub"), mounts_path=montajes)
    assert not medir.es_solo_lectura(Path("/media/Backup/sub"), mounts_path=montajes)
    assert not medir.es_solo_lectura(Path("/tmp"), mounts_path=montajes)


def _sparse(path: Path, tamano: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.truncate(tamano)


def test_seleccion_estratificada_y_acotada(tmp_path):
    rutas = []
    for i in range(20):
        p = tmp_path / "pequenos" / f"p{i:02d}.cbz"
        _sparse(p, 1 * 1024 ** 2)
        rutas.append(p)
    for i in range(5):
        p = tmp_path / "medianos" / f"m{i:02d}.cbr"
        _sparse(p, 60 * 1024 ** 2)
        rutas.append(p)
    for i in range(3):
        p = tmp_path / "grandes" / f"g{i:02d}.cbz"
        _sparse(p, 400 * 1024 ** 2)
        rutas.append(p)

    elegidas, resumen = medir.seleccionar_muestra(
        rutas, max_files=10, max_bytes=500 * 1024 ** 2, seed=326
    )
    assert 0 < len(elegidas) <= 10
    assert resumen["bytes"] <= 500 * 1024 ** 2
    assert resumen["selected"] == len(elegidas)
    assert len(resumen["manifest_sha256"]) == 64
    assert sum(resumen["by_format"].values()) == len(elegidas)
    assert sum(resumen["by_size"].values()) == len(elegidas)

    elegidas2, resumen2 = medir.seleccionar_muestra(
        rutas, max_files=10, max_bytes=500 * 1024 ** 2, seed=326
    )
    assert [str(p) for p in elegidas] == [str(p) for p in elegidas2]
    assert resumen["manifest_sha256"] == resumen2["manifest_sha256"]


def test_seleccion_vacia():
    elegidas, resumen = medir.seleccionar_muestra(
        [], max_files=10, max_bytes=1024, seed=326
    )
    assert elegidas == []
    assert resumen["selected"] == 0
    assert len(resumen["manifest_sha256"]) == 64


def test_percentiles():
    assert medir._percentil([], 0.5) == 0.0
    assert medir._percentil([1.0], 0.95) == 1.0
    assert medir._percentil([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert medir._percentil([1.0, 2.0, 3.0, 4.0], 0.95) == pytest.approx(3.85)


def test_generador_crea_cbz_validos(tmp_path, capfd):
    out = tmp_path / "sinteticos"
    assert generar.main([
        "--out", str(out), "--prefix", "Viejos", "--count", "2", "--pages", "2",
    ]) == 0
    salida = json.loads(capfd.readouterr().out)
    assert salida["files"] == 2
    assert salida["bytes"] > 0
    assert "out" not in salida and str(tmp_path) not in json.dumps(salida)
    archivos = sorted(out.rglob("*.cbz"))
    assert len(archivos) == 2
    for archivo in archivos:
        with zipfile.ZipFile(archivo) as zf:
            assert "portada.jpg" in zf.namelist()
            assert zf.testzip() is None


def test_ventana_e_sintaxis():
    r = subprocess.run(
        ["bash", "-n", str(MEDICION / "ventana_e.sh")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(os.name == "nt", reason="permisos POSIX")
def test_generador_archivo_grande(tmp_path, capfd):
    out = tmp_path / "grandes"
    assert generar.main([
        "--out", str(out), "--prefix", "Grandes", "--count", "1", "--size-mb", "1",
    ]) == 0
    archivo = next(out.rglob("*.cbz"))
    assert archivo.stat().st_size >= 1024 ** 2
    with zipfile.ZipFile(archivo) as zf:
        assert "relleno.bin" in zf.namelist()
