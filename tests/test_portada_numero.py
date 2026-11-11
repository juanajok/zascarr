"""BL-INF4 (#590): miniatura de portada por número (servicio, sin BD real)."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from zascarr.services import portada_numero


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, filas):
        self._filas = filas

    async def execute(self, *_a, **_k):
        return _Resultado(self._filas)


def _covers(tmp_path) -> Path:
    return tmp_path / "covers"


def _settings(tmp_path):
    return SimpleNamespace(covers_cache_path=_covers(tmp_path), lector_rar_enabled=False)


def _cbz(ruta: Path) -> Path:
    buffer = io.BytesIO()
    Image.new("RGB", (80, 120), (10, 90, 160)).save(buffer, "JPEG")
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", buffer.getvalue())
        z.writestr("002.jpg", buffer.getvalue())
    return ruta


@pytest.mark.asyncio
async def test_genera_la_miniatura_y_la_cachea_por_archivo(tmp_path):
    cbz = _cbz(tmp_path / "Tebeo 01.cbz")
    file_id = uuid4()
    sesion = _Sesion([(file_id, str(cbz), None)])
    ajustes = _settings(tmp_path)

    ruta = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)

    assert ruta is not None and ruta.is_file()
    assert ruta.name == f"{file_id}.jpg"
    assert ruta.read_bytes().startswith(b"\xff\xd8")
    # La biblioteca no se toca.
    assert cbz.exists()


@pytest.mark.asyncio
async def test_la_segunda_vez_no_vuelve_a_extraer(tmp_path, monkeypatch):
    cbz = _cbz(tmp_path / "Tebeo 01.cbz")
    sesion = _Sesion([(uuid4(), str(cbz), None)])
    ajustes = _settings(tmp_path)
    primera = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)

    def _no_debe_llamarse(*_a, **_k):
        raise AssertionError("no debería extraer otra vez")

    monkeypatch.setattr(portada_numero, "extract_cover_thumbnail", _no_debe_llamarse)
    segunda = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)

    assert segunda == primera and segunda.is_file()


@pytest.mark.asyncio
async def test_numero_sin_archivos_no_tiene_previa(tmp_path):
    ajustes = _settings(tmp_path)
    assert await portada_numero.ruta_previa(_Sesion([]), uuid4(), uuid4(), settings=ajustes) is None


@pytest.mark.asyncio
async def test_archivo_que_no_es_zip_no_tiene_previa(tmp_path):
    roto = tmp_path / "roto.cbz"
    roto.write_bytes(b"no es un zip")
    ajustes = _settings(tmp_path)
    assert await portada_numero.ruta_previa(
        _Sesion([(uuid4(), str(roto), None)]), uuid4(), uuid4(), settings=ajustes) is None


@pytest.mark.asyncio
async def test_la_ficha_usa_su_propia_cache_a_600(tmp_path):
    cbz = _cbz(tmp_path / "Tebeo 01.cbz")
    fid = uuid4()
    sesion = _Sesion([(fid, str(cbz), None)])
    ajustes = _settings(tmp_path)

    previa = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)
    ficha = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), ancho=600, settings=ajustes)

    assert previa is not None and ficha is not None
    assert previa.name == f"{fid}.jpg" and ficha.name == f"{fid}-600.jpg"
    assert previa != ficha and previa.is_file() and ficha.is_file()


@pytest.mark.asyncio
async def test_con_el_lector_apagado_no_se_manda_el_rar(tmp_path, monkeypatch):
    cbr = tmp_path / "Tebeo 01.cbr"
    cbr.write_bytes(b"Rar!\x1a\x07\x00" + b"0" * 32)
    fid = uuid4()
    llamadas: list[int] = []
    monkeypatch.setattr(portada_numero, "es_rar_candidato", lambda *_a, **_k: True)
    monkeypatch.setattr(portada_numero, "lector_rar_disponible", lambda: True)

    def _portada(*_a, **_k):
        llamadas.append(1)
        return b"\xff\xd8\xff\xd9", "image/jpeg"

    monkeypatch.setattr(portada_numero, "portada_de_rar", _portada)
    apagado = _settings(tmp_path)
    assert apagado.lector_rar_enabled is False
    assert await portada_numero.ruta_previa(
        _Sesion([(fid, str(cbr), None)]), uuid4(), uuid4(), settings=apagado) is None
    assert llamadas == []

    encendido = _settings(tmp_path)
    encendido.lector_rar_enabled = True
    assert await portada_numero.ruta_previa(
        _Sesion([(fid, str(cbr), None)]), uuid4(), uuid4(), settings=encendido) is not None
    assert llamadas == [1]


class _SesionConRollback(_Sesion):
    def __init__(self, filas):
        super().__init__(filas)
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_libera_la_conexion_antes_de_generar(tmp_path):
    cbz = _cbz(tmp_path / "Tebeo 01.cbz")
    sesion = _SesionConRollback([(uuid4(), str(cbz), None)])
    await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=_settings(tmp_path))
    assert sesion.rollbacks == 1


@pytest.mark.asyncio
async def test_sustituir_el_archivo_invalida_la_miniatura(tmp_path, monkeypatch):
    cbz = _cbz(tmp_path / "Tebeo 01.cbz")
    fid = uuid4()
    sesion = _Sesion([(fid, str(cbz), None)])
    ajustes = _settings(tmp_path)
    primera = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)
    assert primera is not None
    # Mismo file_id, archivo distinto (mtime/tamaño): la huella invalida la caché.
    cbz.write_bytes(b"contenido nuevo")
    extraidas = []
    monkeypatch.setattr(portada_numero, "_generar", lambda *a, **k: extraidas.append(1) or None)
    segunda = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)
    assert segunda is None and extraidas == [1]


@pytest.mark.asyncio
async def test_sin_portada_no_repite_la_extraccion(tmp_path, monkeypatch):
    roto = tmp_path / "roto.cbz"
    roto.write_bytes(b"no es un zip")
    sesion = _Sesion([(uuid4(), str(roto), None)])
    ajustes = _settings(tmp_path)
    primera = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)
    assert primera is None

    def _no_debe_llamarse(*_a, **_k):
        raise AssertionError("no debería extraer otra vez")

    monkeypatch.setattr(portada_numero, "_generar", _no_debe_llamarse)
    segunda = await portada_numero.ruta_previa(sesion, uuid4(), uuid4(), settings=ajustes)
    assert segunda is None


@pytest.mark.asyncio
async def test_no_hay_mas_de_dos_generaciones_simultaneas(tmp_path, monkeypatch):
    import asyncio
    import threading
    import time

    activos = 0
    maximo = 0
    candado = threading.Lock()
    archivos = []
    sesiones = []
    for i in range(4):
        cbz = _cbz(tmp_path / f"Tebeo {i}.cbz")
        fid = uuid4()
        archivos.append((fid, str(cbz), None))
        sesiones.append(_Sesion([(fid, str(cbz), None)]))
    ajustes = _settings(tmp_path)

    def _lento(lista, *_a, **_k):
        nonlocal activos, maximo
        with candado:
            activos += 1
            maximo = max(maximo, activos)
        time.sleep(0.08)
        with candado:
            activos -= 1
        return b"\xff\xd8\xff\xd9", lista[0][0]

    monkeypatch.setattr(portada_numero, "_generar", _lento)
    await asyncio.gather(*(portada_numero.ruta_previa(
        sesion, uuid4(), uuid4(), settings=ajustes) for sesion in sesiones))
    assert maximo <= 2
