"""B20: exportación de una colección a disco (Postgres real + tmp_path)."""
from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import (
    Collection,
    CollectionAutoSearch,
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    Series,
)
from zascarr.services import exportacion_kavita as svc

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="requiere TEST_DATABASE_URL")


def _url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def db():
    engine = create_async_engine(_url(TEST_DATABASE_URL or ""))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


async def sembrar(db, tmp_path: Path, *, archivos=("Flash 1",)):
    coleccion = Collection(id=uuid4(), name="Grapas", auto_search=CollectionAutoSearch.HEREDAR)
    serie = Series(id=uuid4(), title="Flash", tradition=ComicTradition.AMERICAN,
                   total_issues=3, wishlist_policy="ninguno")
    db.add_all([coleccion, serie])
    await db.flush()
    serie.collection_id = coleccion.id
    lib = tmp_path / "lib"
    lib.mkdir()
    for i, nombre in enumerate(archivos, start=1):
        ruta = lib / f"{nombre}.cbz"
        ruta.write_bytes(b"contenido " + str(i).encode())
        issue = Issue(id=uuid4(), series_id=serie.id, issue_number=str(i), title="El origen",
                      format=IssueFormat.SINGLE_ISSUE)
        db.add(issue)
        await db.flush()
        db.add(File(id=uuid4(), issue_id=issue.id, file_path=str(ruta),
                    file_name=ruta.name, file_format=FileFormat.CBZ,
                    file_size_bytes=ruta.stat().st_size,
                    sha256_hash=hashlib.sha256(ruta.read_bytes()).hexdigest()))
    await db.flush()
    return coleccion, serie


def ajustes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(
        export_path=tmp_path / "export", library_path=tmp_path / "lib",
        downloads_path=tmp_path / "downloads", amule_incoming_dir=tmp_path / "incoming",
        carpetas_compartidas=[]))


async def test_exporta_hardlink_manifiesto_run_y_no_toca_origen(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    origen = next((tmp_path / "lib").glob("*.cbz"))
    antes = (hashlib.sha256(origen.read_bytes()).hexdigest(), origen.stat().st_mtime_ns)
    resumen = await svc.exportar_coleccion(db, coleccion.id)
    destino = Path(resumen.destino) / "Flash" / "Flash 001 - El origen.cbz"
    assert destino.exists() and destino.stat().st_ino == origen.stat().st_ino
    assert (Path(resumen.destino) / "_zascarr_manifest.json").exists()
    assert resumen.materializados == 1 and resumen.errores == 0
    assert (hashlib.sha256(origen.read_bytes()).hexdigest(), origen.stat().st_mtime_ns) == antes
    run = (await db.execute(
        select(svc.ImportRun).where(svc.ImportRun.id == resumen.run_id))).scalar_one_or_none()
    assert run is not None and run.details["kind"] == "export"


async def test_reexportar_es_idempotente_y_no_rehace(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    await svc.exportar_coleccion(db, coleccion.id)
    destino = next((tmp_path / "export").rglob("*.cbz"))
    antes = destino.stat().st_mtime_ns
    resumen = await svc.exportar_coleccion(db, coleccion.id)
    assert resumen.materializados == 0 and resumen.errores == 0
    assert resumen.saltados == 1 and resumen.modo == "hardlink"
    assert destino.stat().st_mtime_ns == antes
    import json
    manifiesto = next((tmp_path / "export").rglob("_zascarr_manifest.json"))
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    assert datos["files"][0]["status"] == "skip" and datos["files"][0]["mode"] == "skip"


async def test_deriva_no_pisa_el_destino_editado(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    await svc.exportar_coleccion(db, coleccion.id, copiar=True)
    destino = next((tmp_path / "export").rglob("*.cbz"))
    destino.write_bytes(b"editado a mano")
    resumen = await svc.exportar_coleccion(db, coleccion.id)
    assert resumen.deriva == 1 and destino.read_bytes() == b"editado a mano"


async def test_copiar_aislado_fuerza_copy_y_no_es_hardlink(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    resumen = await svc.exportar_coleccion(db, coleccion.id, copiar=True)
    assert resumen.materializados == 1 and resumen.modo == "copy"
    destino = next((tmp_path / "export").rglob("*.cbz"))
    original = next((tmp_path / "lib").glob("*.cbz"))
    assert destino.stat().st_ino != original.stat().st_ino


async def test_fallback_a_copia_si_exdev(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    original = os.link

    def link_exdev(src, dest, *a, **k):
        if str(tmp_path / "lib") in str(src):
            raise OSError(errno.EXDEV, "cross-device")
        return original(src, dest, *a, **k)
    monkeypatch.setattr(svc.os, "link", link_exdev)
    resumen = await svc.exportar_coleccion(db, coleccion.id)
    assert resumen.materializados == 1 and resumen.bytes_copiados > 0
    assert resumen.modo == "copy"
    destino = next((tmp_path / "export").rglob("*.cbz"))
    assert destino.read_bytes() == next((tmp_path / "lib").glob("*.cbz")).read_bytes()
    monkeypatch.setattr(svc.os, "link", original)


async def test_espacio_insuficiente_aborta_sin_manifiesto(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    monkeypatch.setattr(
        svc.os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    monkeypatch.setattr(svc.shutil, "disk_usage", lambda _p: SimpleNamespace(free=1))
    with pytest.raises(svc.EspacioInsuficienteError):
        await svc.exportar_coleccion(db, coleccion.id)
    assert not any((tmp_path / "export").rglob("_zascarr_manifest.json"))


async def test_coleccion_vacia_escribe_manifiesto(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path, archivos=())
    resumen = await svc.exportar_coleccion(db, coleccion.id)
    assert resumen.materializados == 0
    assert (tmp_path / "export" / "Grapas" / "_zascarr_manifest.json").exists()


async def test_parche_comicinfo_se_rechaza(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    with pytest.raises(svc.ParcheComicInfoNoDisponibleError):
        await svc.exportar_coleccion(db, coleccion.id, patch_comicinfo=True)
    assert not (tmp_path / "export").exists()


async def test_fuente_symlink_se_omite_y_se_reporta(db, tmp_path, monkeypatch):
    ajustes(tmp_path, monkeypatch)
    coleccion, _ = await sembrar(db, tmp_path)
    real = next((tmp_path / "lib").glob("*.cbz"))
    enlace = tmp_path / "lib" / "enlace.cbz"
    enlace.symlink_to(real)
    from sqlalchemy import update

    from zascarr.models import File
    async with db.begin_nested():
        await db.execute(update(File).values(file_path=str(enlace), file_name=enlace.name))
    resumen = await svc.exportar_coleccion(db, coleccion.id)
    assert resumen.materializados == 0 and resumen.omitidos >= 1
