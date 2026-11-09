"""ETQ2 (#538): `<Tags>`/`<Genre>` de ComicInfo al importar — Postgres real.

Cubre el contrato de AC-21: lectura con `source='comicinfo_xml'`, géneros solo
si la serie no tenía, topes de §7.4 con aviso (sin abortar el ciclo),
idempotencia, precedencia de `manual` y no resucitar una etiqueta oculta.

Los casos de parseo corren sin BD; los de servicio e importador se saltan sin
`TEST_DATABASE_URL`, como el resto de pruebas de Postgres.
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.core.importer_triage import parse_comic_info
from zascarr.models import (
    ComicTradition,
    Genre,
    Issue,
    IssueFormat,
    Series,
    Tag,
    series_genres,
    series_tags,
)
from zascarr.services import importer as mod
from zascarr.services.etiquetas_comicinfo import aplicar_comicinfo
from zascarr.services.importer import Importer

URL = os.environ.get("TEST_DATABASE_URL")
pg = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


# ── Parseo y topes (sin BD) ──────────────────────────────────────────────────

class TestParseoComicInfo:

    def test_lee_tags_y_generos_separados_por_coma(self):
        info = parse_comic_info(
            b"<ComicInfo><Tags>dark, Occult,  </Tags>"
            b"<Genre>Horror, Suspense</Genre></ComicInfo>"
        )
        assert info.tags == ["dark", "Occult"]
        assert info.genres == ["Horror", "Suspense"]
        assert info.warnings == []

    def test_tope_de_200_valores_por_campo(self):
        tags = ", ".join(f"t{i}" for i in range(250))
        info = parse_comic_info(f"<ComicInfo><Tags>{tags}</Tags></ComicInfo>".encode())
        assert len(info.tags) == 200
        assert any("más de 200 valores" in w for w in info.warnings)

    def test_ignora_valores_de_mas_de_64_caracteres(self):
        info = parse_comic_info(
            f"<ComicInfo><Tags>ok, {'x' * 65}</Tags></ComicInfo>".encode()
        )
        assert info.tags == ["ok"]
        assert any("más de 64 caracteres" in w for w in info.warnings)

    def test_campo_de_mas_de_32_kib_se_recorta(self):
        tags = ", ".join(["a"] * 20000)  # ~40 KB
        info = parse_comic_info(f"<ComicInfo><Tags>{tags}</Tags></ComicInfo>".encode())
        assert len(info.tags) <= 200
        assert any("supera 32 KiB" in w for w in info.warnings)

    def test_xml_roto_sigue_lanzando_parse_error(self):
        from xml.etree.ElementTree import ParseError
        with pytest.raises(ParseError):
            parse_comic_info(b"<ComicInfo><Tags>sin cerrar</ComicInfo>")


# ── Servicio e importador (Postgres real) ────────────────────────────────────

@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def ent(url_bd, tmp_path, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    async with b.motor.begin() as c:
        # `series` se trunca con CASCADE, pero tags/genres no cuelgan de series.
        await c.execute(text("TRUNCATE tags, genres CASCADE"))
    lib, descargas = tmp_path / "biblioteca", tmp_path / "descargas"
    lib.mkdir()
    descargas.mkdir()
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(
        library_path=lib,
        transmission_download_dir=str(tmp_path / "transmission"),
        amule_incoming_dir=str(tmp_path / "amule"),
        downloads_path=descargas,
    ))
    yield SimpleNamespace(banco=b, lib=lib, descargas=descargas)
    await b.cerrar()


async def serie_con_numero(ent, titulo="Flash", anio=1987, numero="23"):
    async with ent.banco.fabrica() as s:
        serie = Series(id=uuid4(), title=titulo, start_year=anio,
                       tradition=ComicTradition.AMERICAN)
        s.add(serie)
        await s.flush()
        issue = Issue(series_id=serie.id, issue_number=numero,
                      format=IssueFormat.SINGLE_ISSUE)
        s.add(issue)
        await s.commit()
        return serie.id, issue.id


def cbz_con_comicinfo(ruta: Path, *, serie="Flash", numero="23",
                      tags: str | None = None, genero: str | None = None) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    partes = ["<ComicInfo>", f"<Series>{serie}</Series>",
              f"<Number>{numero}</Number>"]
    if tags is not None:
        partes.append(f"<Tags>{tags}</Tags>")
    if genero is not None:
        partes.append(f"<Genre>{genero}</Genre>")
    partes.append("</ComicInfo>")
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        z.writestr("ComicInfo.xml", "".join(partes))
        buffer = io.BytesIO()
        Image.new("RGB", (60, 90), (10, 90, 160)).save(buffer, "JPEG")
        z.writestr("p000.jpg", buffer.getvalue())
    return ruta


async def filas_de_la_serie(ent, series_id):
    async with ent.banco.fabrica() as s:
        etiquetas = (await s.execute(
            select(Tag.name, series_tags.c.source, series_tags.c.weight,
                   series_tags.c.oculta)
            .join(series_tags, series_tags.c.tag_id == Tag.id)
            .where(series_tags.c.series_id == series_id)
            .order_by(Tag.name)
        )).all()
        generos = (await s.execute(
            select(Genre.name)
            .join(series_genres, series_genres.c.genre_id == Genre.id)
            .where(series_genres.c.series_id == series_id)
            .order_by(Genre.name)
        )).scalars().all()
        return etiquetas, list(generos)


@pg
class TestServicio:

    @pytest.mark.asyncio
    async def test_crea_etiquetas_con_su_fuente_y_generos(self, ent):
        sid, _ = await serie_con_numero(ent)
        async with ent.banco.fabrica() as s:
            resultado = await aplicar_comicinfo(
                s, sid, tags=["dark", "Occult", "dark"], genres=["Horror"])
            await s.commit()

        assert resultado.etiquetas == 2
        assert resultado.generos == 1
        etiquetas, generos = await filas_de_la_serie(ent, sid)
        assert [(n, src, w, oc) for n, src, w, oc in etiquetas] == [
            ("Occult", "comicinfo_xml", None, False),
            ("dark", "comicinfo_xml", None, False),
        ]
        assert generos == ["Horror"]

    @pytest.mark.asyncio
    async def test_es_idempotente(self, ent):
        sid, _ = await serie_con_numero(ent)
        async with ent.banco.fabrica() as s:
            await aplicar_comicinfo(s, sid, tags=["dark"], genres=["Horror"])
            await s.commit()
        async with ent.banco.fabrica() as s:
            segundo = await aplicar_comicinfo(s, sid, tags=["dark"], genres=["Horror"])
            await s.commit()

        assert segundo.etiquetas == 0
        assert segundo.generos == 0
        etiquetas, generos = await filas_de_la_serie(ent, sid)
        assert len(etiquetas) == 1 and generos == ["Horror"]

    @pytest.mark.asyncio
    async def test_no_pisa_una_etiqueta_manual(self, ent):
        sid, _ = await serie_con_numero(ent)
        async with ent.banco.fabrica() as s:
            tag = Tag(id=uuid4(), name="dark", namespace="etiqueta")
            s.add(tag)
            await s.flush()
            await s.execute(series_tags.insert().values(
                series_id=sid, tag_id=tag.id, source="manual", weight=None,
                oculta=False))
            await s.commit()
        async with ent.banco.fabrica() as s:
            resultado = await aplicar_comicinfo(s, sid, tags=["dark"], genres=[])
            await s.commit()

        assert resultado.etiquetas == 0
        etiquetas, _ = await filas_de_la_serie(ent, sid)
        assert etiquetas == [("dark", "manual", None, False)]

    @pytest.mark.asyncio
    async def test_no_resucita_una_etiqueta_oculta(self, ent):
        sid, _ = await serie_con_numero(ent)
        async with ent.banco.fabrica() as s:
            tag = Tag(id=uuid4(), name="dark", namespace="etiqueta")
            s.add(tag)
            await s.flush()
            await s.execute(series_tags.insert().values(
                series_id=sid, tag_id=tag.id, source="comicinfo_xml", weight=None,
                oculta=True))
            await s.commit()
        async with ent.banco.fabrica() as s:
            resultado = await aplicar_comicinfo(s, sid, tags=["dark"], genres=[])
            await s.commit()

        assert resultado.etiquetas == 0
        etiquetas, _ = await filas_de_la_serie(ent, sid)
        assert etiquetas == [("dark", "comicinfo_xml", None, True)]

    @pytest.mark.asyncio
    async def test_generos_solo_si_la_serie_no_tenia(self, ent):
        sid, _ = await serie_con_numero(ent)
        async with ent.banco.fabrica() as s:
            drama = Genre(id=uuid4(), name="Drama")
            s.add(drama)
            await s.flush()
            await s.execute(series_genres.insert().values(
                series_id=sid, genre_id=drama.id))
            await s.commit()
        async with ent.banco.fabrica() as s:
            resultado = await aplicar_comicinfo(s, sid, tags=[], genres=["Horror"])
            await s.commit()

        assert resultado.generos == 0
        _, generos = await filas_de_la_serie(ent, sid)
        assert generos == ["Drama"]

    @pytest.mark.asyncio
    async def test_reutiliza_el_genero_sin_duplicar_por_mayusculas(self, ent):
        sid, _ = await serie_con_numero(ent)
        async with ent.banco.fabrica() as s:
            s.add(Genre(id=uuid4(), name="Horror"))
            await s.commit()
        async with ent.banco.fabrica() as s:
            await aplicar_comicinfo(s, sid, tags=[], genres=["horror"])
            await s.commit()

        async with ent.banco.fabrica() as s:
            total = (await s.execute(
                select(Genre).where(Genre.name.ilike("horror")))).scalars().all()
        assert len(total) == 1
        _, generos = await filas_de_la_serie(ent, sid)
        assert generos == ["Horror"]


@pg
class TestImportador:

    @pytest.mark.asyncio
    async def test_un_cbz_con_tags_y_genre_llega_a_su_serie(self, ent):
        sid, _ = await serie_con_numero(ent)
        cbz_con_comicinfo(ent.descargas / "Flash 023 (1987).cbz",
                          tags="dark, Occult", genero="Horror")
        async with ent.banco.fabrica() as s:
            informe = await Importer(s).scan_and_import()
            await s.commit()

        assert not informe.errors
        assert any("Flash 023" in linea for linea in informe.imported)
        etiquetas, generos = await filas_de_la_serie(ent, sid)
        assert [(n, src) for n, src, _w, _o in etiquetas] == [
            ("Occult", "comicinfo_xml"), ("dark", "comicinfo_xml")]
        assert generos == ["Horror"]

    @pytest.mark.asyncio
    async def test_no_escribe_ni_un_byte_del_cbz(self, ent):
        sid, _ = await serie_con_numero(ent)
        origen = cbz_con_comicinfo(
            ent.descargas / "Flash 023 (1987).cbz", tags="dark", genero="Horror")
        antes = origen.read_bytes()
        async with ent.banco.fabrica() as s:
            informe = await Importer(s).scan_and_import()
            await s.commit()

        assert not informe.errors
        movido = next(p for p in ent.lib.rglob("*.cbz"))
        assert movido.read_bytes() == antes
        with zipfile.ZipFile(movido) as z:
            assert "<Tags>dark</Tags>" in z.read("ComicInfo.xml").decode()

    @pytest.mark.asyncio
    async def test_los_topes_dejan_aviso_sin_abortar_el_ciclo(self, ent):
        sid, _ = await serie_con_numero(ent)
        tags = ", ".join(f"t{i:03d}" for i in range(300))
        cbz_con_comicinfo(ent.descargas / "Flash 023 (1987).cbz", tags=tags)
        async with ent.banco.fabrica() as s:
            informe = await Importer(s).scan_and_import()
            await s.commit()

        assert not informe.errors
        linea = next(x for x in informe.imported if "Flash 023" in x)
        assert "ComicInfo:" in linea and "más de 200 valores" in linea
        etiquetas, _ = await filas_de_la_serie(ent, sid)
        assert len(etiquetas) == 200
