"""BL-ETQ2b (#573): relectura del ComicInfo de la biblioteca registrada — Postgres real.

Cubre los AC de la tarjeta: lee solo CBZ (ZIP), aplica ETQ2 sin pisar `manual` ni resucitar
`oculta`, géneros solo si no había, idempotente, dry-run sin escritura, `.cbr` fuera y cerrojo
de ciclo compartido con importador/rescan. Los casos de parseo puro ya los cubre ETQ2.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Genre,
    Issue,
    IssueFormat,
    Series,
    Tag,
    series_tags,
)
from zascarr.services.backfill_comicinfo import ejecutar

URL = os.environ.get("TEST_DATABASE_URL")
pg = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def ent(url_bd, tmp_path):
    b = Banco(url_bd)
    await b.limpiar()
    async with b.motor.begin() as c:
        await c.execute(text("TRUNCATE tags, genres CASCADE"))
    lib = tmp_path / "biblioteca"
    lib.mkdir()
    yield SimpleNamespace(banco=b, lib=lib)
    await b.cerrar()


def _cbz(ruta: Path, *, tags: str | None = None, genero: str | None = None,
         comicinfo: bool = True, roto: bool = False) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not comicinfo:
        with zipfile.ZipFile(ruta, "w") as z:
            z.writestr("p.jpg", b"img")
        return ruta
    partes = ["<ComicInfo>"]
    if tags is not None:
        partes.append(f"<Tags>{tags}</Tags>")
    if genero is not None:
        partes.append(f"<Genre>{genero}</Genre>")
    partes.append("</ComicInfo>")
    contenido = "<ComicInfo><Tags>roto" if roto else "".join(partes)
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("ComicInfo.xml", contenido)
        z.writestr("p.jpg", b"img")
    return ruta


async def _serie(ent, titulo: str = "Serie") -> UUID:
    sid = uuid4()
    async with ent.banco.fabrica() as s:
        s.add(Series(id=sid, title=titulo, tradition=ComicTradition.AMERICAN))
        await s.commit()
    return sid


async def _issue(ent, series_id: UUID) -> UUID:
    iid = uuid4()
    async with ent.banco.fabrica() as s:
        s.add(Issue(id=iid, series_id=series_id, issue_number="1",
                    format=IssueFormat.SINGLE_ISSUE))
        await s.commit()
    return iid


async def _registrar(ent, issue_id: UUID, ruta: Path,
                     formato: FileFormat = FileFormat.CBZ) -> None:
    async with ent.banco.fabrica() as s:
        s.add(File(id=uuid4(), issue_id=issue_id, file_path=str(ruta),
                   file_name=ruta.name, file_format=formato))
        await s.commit()


async def _etiqueta_manual(ent, series_id: UUID, nombre: str) -> None:
    async with ent.banco.fabrica() as s:
        tag = Tag(id=uuid4(), name=nombre, namespace="etiqueta")
        s.add(tag)
        await s.flush()
        await s.execute(series_tags.insert().values(
            series_id=series_id, tag_id=tag.id, source="manual"))
        await s.commit()


async def _oculta(ent, series_id: UUID, nombre: str) -> None:
    async with ent.banco.fabrica() as s:
        tag = Tag(id=uuid4(), name=nombre, namespace="etiqueta")
        s.add(tag)
        await s.flush()
        await s.execute(series_tags.insert().values(
            series_id=series_id, tag_id=tag.id, source="comicinfo_xml", oculta=True))
        await s.commit()


async def _filas(ent):
    async with ent.banco.fabrica() as s:
        etiquetas = (await s.execute(
            select(Tag.name, series_tags.c.source, series_tags.c.oculta)
            .join(series_tags, series_tags.c.tag_id == Tag.id)
            .order_by(Tag.name)
        )).all()
        generos = (await s.execute(select(Genre.name).order_by(Genre.name))).scalars().all()
        return [(n, src, oc) for n, src, oc in etiquetas], list(generos)


@pg
class TestBackfillComicInfo:

    @pytest.mark.asyncio
    async def test_dry_run_cuenta_sin_escribir(self, ent):
        sid = await _serie(ent)
        iid = await _issue(ent, sid)
        await _registrar(ent, iid, _cbz(ent.lib / "a.cbz", tags="dark, Occult", genero="Horror"))
        await _registrar(ent, iid, _cbz(ent.lib / "b.cbz", tags="superman"))
        await _registrar(ent, iid, _cbz(ent.lib / "c.cbz", comicinfo=False))
        await _registrar(ent, iid, _cbz(ent.lib / "d.cbz", roto=True))
        roto = ent.lib / "e.cbz"
        roto.write_bytes(b"no es un zip")
        await _registrar(ent, iid, roto)
        await _registrar(ent, iid, ent.lib / "f.cbr", FileFormat.CBR)
        await _registrar(ent, iid, ent.lib / "g.cbz")  # no existe en disco

        informe = await ejecutar(aplicar=False, fabrica=ent.banco.fabrica)

        assert informe.cerrojo
        assert informe.mirados == 6
        assert informe.con_comicinfo == 2
        assert informe.con_tags == 2
        assert informe.con_genero == 1
        assert informe.sin_comicinfo == 1
        assert informe.xml_roto == 1
        assert informe.no_zip == 1
        assert informe.faltan == 1
        assert informe.cbr_registrados == 1
        assert informe.etiquetas_vistas == 3
        assert informe.generos_vistos == 1
        assert informe.series_con_datos == 1
        etiquetas, generos = await _filas(ent)
        assert etiquetas == [] and generos == []
        assert informe.etiquetas_aplicadas == 0

    @pytest.mark.asyncio
    async def test_aplica_sin_pisar_manual_y_es_idempotente(self, ent):
        sid = await _serie(ent)
        iid = await _issue(ent, sid)
        await _etiqueta_manual(ent, sid, "dark")
        ruta = _cbz(ent.lib / "a.cbz", tags="dark, Occult", genero="Horror")
        await _registrar(ent, iid, ruta)
        antes = ruta.stat().st_mtime_ns

        informe = await ejecutar(aplicar=True, fabrica=ent.banco.fabrica)
        assert informe.etiquetas_aplicadas == 1  # «dark» ya era manual; se añade «Occult»
        assert informe.generos_aplicados == 1
        assert informe.series_tocadas == 1
        etiquetas, generos = await _filas(ent)
        assert etiquetas == [("Occult", "comicinfo_xml", False),
                             ("dark", "manual", False)]
        assert generos == ["Horror"]

        segundo = await ejecutar(aplicar=True, fabrica=ent.banco.fabrica)
        assert segundo.etiquetas_aplicadas == 0
        assert segundo.generos_aplicados == 0
        assert (await _filas(ent))[0] == etiquetas
        assert ruta.stat().st_mtime_ns == antes  # solo lectura: el CBZ no se toca

    @pytest.mark.asyncio
    async def test_no_resucita_una_etiqueta_oculta(self, ent):
        sid = await _serie(ent)
        iid = await _issue(ent, sid)
        await _oculta(ent, sid, "vintage")
        await _registrar(ent, iid, _cbz(ent.lib / "a.cbz", tags="vintage"))

        await ejecutar(aplicar=True, fabrica=ent.banco.fabrica)
        etiquetas, _ = await _filas(ent)
        assert etiquetas == [("vintage", "comicinfo_xml", True)]

    @pytest.mark.asyncio
    async def test_cerrojo_ocupado_no_toca_nada(self, ent):
        sid = await _serie(ent)
        iid = await _issue(ent, sid)
        await _registrar(ent, iid, _cbz(ent.lib / "a.cbz", tags="dark"))
        conexion = await ent.banco.motor.connect()
        try:
            await conexion.execute(text("SELECT pg_advisory_lock(326, 2)"))
            informe = await ejecutar(aplicar=True, fabrica=ent.banco.fabrica)
            assert not informe.cerrojo
            assert informe.mirados == 0
            assert (await _filas(ent))[0] == []
        finally:
            await conexion.execute(text("SELECT pg_advisory_unlock(326, 2)"))
            await conexion.close()

    @pytest.mark.asyncio
    async def test_limite_procesa_solo_los_primeros(self, ent):
        sid = await _serie(ent)
        iid = await _issue(ent, sid)
        await _registrar(ent, iid, _cbz(ent.lib / "a.cbz", tags="uno"))
        await _registrar(ent, iid, _cbz(ent.lib / "b.cbz", tags="dos"))

        informe = await ejecutar(aplicar=False, fabrica=ent.banco.fabrica, limite=1)
        assert informe.mirados == 1
        assert informe.con_tags == 1
