"""Caché de extracción de CBR (BL-LEC4): clave, nombres saneados, concurrencia y cuota."""
from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import pytest

from zascarr.models import File, FileFormat
from zascarr.services import cache_lectura as cache
from zascarr.utils.lector_rar import ImagenExtraida


def _file(tmp_path, *, size=100, digest="a" * 64):
    ruta = tmp_path / "original.cbr"
    ruta.write_bytes(b"x" * size)
    return File(id=uuid4(), issue_id=uuid4(), file_path=str(ruta),
                file_name=ruta.name, file_format=FileFormat.CBR,
                file_size_bytes=size, sha256_hash=digest, metadata_={})


def _imagenes(tmp_path, cantidad=3):
    salida = []
    for i in range(1, cantidad + 1):
        p = tmp_path / f"entrada-{i}.jpg"
        p.write_bytes(b"imagen" * i)
        salida.append(ImagenExtraida(p, p.stat().st_size))
    return tuple(salida)


@pytest.mark.asyncio
async def test_prepara_renombra_a_indices_y_sirve_paginas(tmp_path, monkeypatch):
    f = _file(tmp_path)
    ajustes = cache.CacheLectura(tmp_path / "cache", 10_000_000, 10, 1_000_000, 100)

    def falso(_ruta, destino, **_kw):
        destino.mkdir(parents=True)
        imagenes = _imagenes(tmp_path)
        for imagen in imagenes:
            (destino / imagen.ruta.name).write_bytes(imagen.ruta.read_bytes())
        return tuple(ImagenExtraida(destino / i.ruta.name, i.tamano) for i in imagenes)

    monkeypatch.setattr(cache, "extraer_completo", falso)
    assert (await ajustes.preparar(f)).estado == "preparando"
    await asyncio.gather(*(ajustes.preparar(f) for _ in range(3)))
    for tarea in list(ajustes._tareas.values()):
        await tarea
    assert ajustes.estado(f).estado == "listo"
    final = ajustes.ruta(f)
    assert sorted(p.name for p in final.iterdir()) == ["00001.jpg", "00002.jpg", "00003.jpg"]
    datos, tipo = ajustes.leer_pagina(f, 1)
    assert datos and tipo == "image/jpeg"


@pytest.mark.asyncio
async def test_concurrencia_una_sola_extraccion(tmp_path, monkeypatch):
    f = _file(tmp_path)
    ajustes = cache.CacheLectura(tmp_path / "cache", 10_000_000, 10, 1_000_000, 100)
    llamadas = []

    def lento(_ruta, destino, **_kw):
        llamadas.append(1)
        time.sleep(0.05)
        destino.mkdir(parents=True)
        (destino / "x.jpg").write_bytes(b"x")
        return (ImagenExtraida(destino / "x.jpg", 1),)

    monkeypatch.setattr(cache, "extraer_completo", lento)
    resultados = await asyncio.gather(*(ajustes.preparar(f) for _ in range(3)))
    assert [r.estado for r in resultados] == ["preparando"] * 3
    await asyncio.gather(*list(ajustes._tareas.values()))
    assert len(llamadas) == 1


def test_hacer_sitio_borra_lo_mas_antiguo_sin_tocar_activo(tmp_path):
    base = tmp_path / "cache"
    base.mkdir()
    viejo, activo = base / "viejo", base / "activo"
    for d in (viejo, activo):
        d.mkdir()
        (d / "x.jpg").write_bytes(b"x" * 100)
    ahora = time.time()
    os.utime(viejo, (ahora - 4000, ahora - 4000))
    os.utime(activo, (ahora, ahora))
    ajustes = cache.CacheLectura(base, 250, 10, 1_000_000, 100)
    ajustes._hacer_sitio(100, "activo")
    assert not viejo.exists() and activo.exists()


def test_error_si_no_cabe(tmp_path):
    base = tmp_path / "cache"
    base.mkdir()
    activo = base / "activo"
    activo.mkdir()
    (activo / "x.jpg").write_bytes(b"x" * 100)
    ajustes = cache.CacheLectura(base, 50, 10, 1_000_000, 100)
    with pytest.raises(cache.CacheError):
        ajustes._hacer_sitio(100, "activo")


def test_barrer_temporales_solo_borra_tmp(tmp_path):
    base = tmp_path / "cache"
    (base / ".tmp-viejo").mkdir(parents=True)
    (base / "publicada").mkdir()
    assert cache.barrer_temporales(base) == 1
    assert (base / "publicada").exists()
