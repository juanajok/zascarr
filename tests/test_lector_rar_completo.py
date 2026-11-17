"""Extracción ENTERA de RAR (BL-LEC4): topes, nombres saneados y fallos en llano."""
from __future__ import annotations

import os

import pytest

from zascarr.models import MotivoRar
from zascarr.utils import lector_rar


def _rar(tmp_path):
    p = tmp_path / "x.cbr"
    p.write_bytes(b"Rar!\x1a\x07\x00" + b"x" * 50)
    return p


def _listado():
    return lector_rar.Listado((
        lector_rar.EntradaRar(0, "01.jpg", 10, None, False, False),
        lector_rar.EntradaRar(1, "02.jpg", 10, None, False, False),
    ))


def test_extrae_y_ordena_nombres(tmp_path, monkeypatch):
    ruta = _rar(tmp_path)
    temporal = tmp_path / "tmp"
    temporal.mkdir()
    destino = tmp_path / "salida"

    def falso_listar(*_a, **_k):
        return _listado()

    def falso_ejecutar(_argv, **kw):
        (destino / "02.jpg").write_bytes(b"b" * 10)
        (destino / "01.jpg").write_bytes(b"a" * 10)
        return 0, b"", b""

    monkeypatch.setattr(lector_rar, "_localizar", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(lector_rar, "listar", falso_listar)
    monkeypatch.setattr(lector_rar, "_ejecutar_con_turno", falso_ejecutar)
    imagenes = lector_rar.extraer_completo(
        ruta, destino, temporal=temporal, timeout=10, max_bytes=1000, max_ficheros=10)
    assert [i.ruta.name for i in imagenes] == ["01.jpg", "02.jpg"]


def test_rechaza_symlink_en_la_salida(tmp_path, monkeypatch):
    ruta = _rar(tmp_path)
    temporal = tmp_path / "tmp"
    temporal.mkdir()
    destino = tmp_path / "salida"

    def falso_ejecutar(_argv, **kw):
        (destino / "01.jpg").write_bytes(b"a" * 10)
        os.symlink("/etc/passwd", destino / "malo.jpg")
        return 0, b"", b""

    monkeypatch.setattr(lector_rar, "_localizar", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(lector_rar, "listar", lambda *a, **k: _listado())
    monkeypatch.setattr(lector_rar, "_ejecutar_con_turno", falso_ejecutar)
    with pytest.raises(lector_rar.ErrorRar):
        lector_rar.extraer_completo(
            ruta, destino, temporal=temporal, timeout=10, max_bytes=1000, max_ficheros=10)


def test_sin_imagenes_falla(tmp_path, monkeypatch):
    ruta = _rar(tmp_path)
    temporal = tmp_path / "tmp"
    temporal.mkdir()
    monkeypatch.setattr(lector_rar, "_localizar", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(lector_rar, "listar", lambda *a, **k: lector_rar.Listado(()))
    with pytest.raises(lector_rar.ErrorRar) as exc:
        lector_rar.extraer_completo(
            ruta, tmp_path / "salida", temporal=temporal, timeout=10,
            max_bytes=1000, max_ficheros=10)
    assert exc.value.motivo is MotivoRar.SIN_IMAGENES


def test_rechaza_nombres_con_travesia_antes_de_unar(tmp_path, monkeypatch):
    ruta = _rar(tmp_path)
    temporal = tmp_path / "tmp"
    temporal.mkdir()
    llamadas = []

    def falso_listar(*_a, **_k):
        return lector_rar.Listado((
            lector_rar.EntradaRar(0, "../fuera.jpg", 10, None, False, False),))

    def falso_ejecutar(*_a, **_k):
        llamadas.append(1)
        return 0, b"", b""

    monkeypatch.setattr(lector_rar, "_localizar", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(lector_rar, "listar", falso_listar)
    monkeypatch.setattr(lector_rar, "_ejecutar_con_turno", falso_ejecutar)
    with pytest.raises(lector_rar.ErrorRar):
        lector_rar.extraer_completo(ruta, tmp_path / "salida", temporal=temporal,
                                     timeout=10, max_bytes=1000, max_ficheros=10)
    assert llamadas == []


def test_rechaza_enlace_del_listado_antes_de_unar(tmp_path, monkeypatch):
    ruta = _rar(tmp_path)
    temporal = tmp_path / "tmp"
    temporal.mkdir()
    llamadas = []

    def falso_listar(*_a, **_k):
        return lector_rar.Listado((
            lector_rar.EntradaRar(0, "01.jpg", 10, None, False, False, True),))

    def falso_ejecutar(*_a, **_k):
        llamadas.append(1)
        return 0, b"", b""

    monkeypatch.setattr(lector_rar, "_localizar", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(lector_rar, "listar", falso_listar)
    monkeypatch.setattr(lector_rar, "_ejecutar_con_turno", falso_ejecutar)
    with pytest.raises(lector_rar.ErrorRar):
        lector_rar.extraer_completo(ruta, tmp_path / "salida", temporal=temporal,
                                     timeout=10, max_bytes=1000, max_ficheros=10)
    assert llamadas == []
