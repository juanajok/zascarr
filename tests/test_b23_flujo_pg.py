"""B23: una serie nueva recibe el primer número al importar (simulación del alta)."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests._raices_pg import allowlist, sembrar_raiz
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, File, Issue, Series
from zascarr.services import importer as mod
from zascarr.services.importer import Importer

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _jpeg(i: int) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (200, 300), (i * 20 % 255, 90, 160)).save(b, "JPEG")
    return b.getvalue()


def un_zip(ruta: Path, paginas: int = 4) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        for i in range(paginas):
            z.writestr(f"p{i:03d}.jpg", _jpeg(i))
    return ruta


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd, tmp_path, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    lib, descargas = tmp_path / "biblioteca", tmp_path / "descargas"
    lib.mkdir()
    descargas.mkdir()
    ajustes = SimpleNamespace(
        library_path=lib,
        transmission_download_dir=str(tmp_path / "transmission"),
        amule_incoming_dir=str(tmp_path / "amule"),
        downloads_path=descargas,
        import_create_missing_issue=True,
        import_convert_cbr=False,
        naming_enabled=False,
        naming_preset="clasico",
        naming_padding=0,
        secret_key="x" * 64,
        forum_enabled=False, forum_url="", forum_username="",
        blog_feed_enabled=False, blog_feed_url="",
    )
    monkeypatch.setattr(mod, "get_settings", lambda: ajustes)
    allowlist(monkeypatch, lib)
    await sembrar_raiz(b.fabrica, lib)
    yield SimpleNamespace(banco=b, lib=lib, descargas=descargas)
    await b.cerrar()


async def serie_vacia(entorno, titulo="Flash", anio=1987) -> str:
    async with entorno.banco.fabrica() as s:
        serie = Series(id=uuid4(), title=titulo, start_year=anio,
                       tradition=ComicTradition.AMERICAN, wishlist_policy="ninguno")
        s.add(serie)
        await s.commit()
        return str(serie.id)


async def importar(entorno):
    async with entorno.banco.fabrica() as s:
        informe = await Importer(s).scan_and_import()
        await s.commit()
        return informe


async def test_serie_nueva_sin_catalogo_crea_el_numero_al_importar(entorno):
    sid = await serie_vacia(entorno)
    origen = un_zip(entorno.descargas / "Flash 001 (1987).cbz")

    informe = await importar(entorno)

    async with entorno.banco.fabrica() as s:
        issue = (await s.execute(select(Issue).where(Issue.series_id == sid))).scalar_one()
        (fila,) = (await s.execute(select(File))).scalars().all()
    assert informe.errors == [] and informe.unsorted == []
    assert issue.issue_number == "1"
    assert fila.issue_id == issue.id
    assert not origen.exists()
    assert Path(fila.file_path).is_relative_to(entorno.lib)
    assert "Flash #001" in fila.file_name


async def test_serie_ya_catalogada_no_inventa_otro_numero(entorno):
    sid = await serie_vacia(entorno)
    async with entorno.banco.fabrica() as s:
        s.add(Issue(series_id=sid, issue_number="001"))
        await s.commit()
    un_zip(entorno.descargas / "Flash 001.cbz")

    informe = await importar(entorno)

    async with entorno.banco.fabrica() as s:
        (issue,) = (await s.execute(select(Issue))).scalars().all()
        (fila,) = (await s.execute(select(File))).scalars().all()
    assert informe.errors == []
    assert issue.issue_number == "001"
    assert fila.issue_id == issue.id


async def test_cbr_importado_se_convierte_y_el_origen_de_descargas_ya_no_esta(entorno, monkeypatch):
    from zascarr.services import conversion
    from zascarr.services.compartidos import Decision, EstadoComparticion

    async def _no_compartido(*_a, **_k):
        return Decision(EstadoComparticion.NO_COMPARTIDO, "prueba", ())

    monkeypatch.setattr(conversion, "estado_de_comparticion", _no_compartido)
    ajustes = mod.get_settings()
    monkeypatch.setattr(ajustes, "import_convert_cbr", True, raising=False)
    monkeypatch.setattr(conversion, "get_settings", lambda: SimpleNamespace(
        library_path=entorno.lib, secret_key="x" * 64,
        transmission_enabled=False, amule_enabled=False, carpetas_compartidas=[]))

    await serie_vacia(entorno)
    # Un ZIP con extensión .cbr: la conversión D5 lo renombra sin necesitar `unar`.
    origen = un_zip(entorno.descargas / "Flash 001 (1987).cbr")

    informe = await importar(entorno)

    async with entorno.banco.fabrica() as s:
        (fila,) = (await s.execute(select(File))).scalars().all()
    assert informe.errors == []
    assert not origen.exists() and not any(entorno.descargas.iterdir())
    assert fila.file_format.value == "cbz"
    assert fila.file_name.endswith(".cbz")
    assert Path(fila.file_path).exists()
    assert not list(entorno.lib.rglob("*.cbr"))


async def test_flujo_elegir_candidato_descargar_importar(entorno, monkeypatch):
    from zascarr.models import Wishlist, WishlistStatus
    from zascarr.services import orchestrator as orch_mod
    from zascarr.services.orchestrator import Orchestrator
    from zascarr.services.prowlarr import SearchResult

    sid = await serie_vacia(entorno)
    async with entorno.banco.fabrica() as s:
        item = Wishlist(series_id=sid, priority=5)
        s.add(item)
        await s.commit()
        item_id = item.id

    enviados: list[str] = []
    candidatos = [
        SearchResult("Flash 001 (1987) (Digital).cbz", "Indexer A",
                     "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 100, 12, "Comics"),
        SearchResult("Flash 001 (1987) (Digital).cbz", "Indexer B",
                     "magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", 100, 30, "Comics"),
    ]

    class ProwlarrFalso:
        async def search(self, query, categories=None, indexer_ids=None):
            return candidatos

    class TransmissionFalso:
        async def add_torrent(self, url, download_dir=None):
            enviados.append(url)
            return {"hashString": "hash-falso", "name": "Flash 001"}

    ajustes = mod.get_settings()
    ajustes.prowlarr_enabled = True
    ajustes.prowlarr_url = "http://prowlarr.test"
    ajustes.prowlarr_api_key = "clave"
    ajustes.prowlarr_indexer_ids = ""
    ajustes.transmission_enabled = True
    ajustes.amule_enabled = False
    monkeypatch.setattr(orch_mod, "get_settings", lambda: ajustes)

    async with entorno.banco.fabrica() as s:
        orch = Orchestrator(s)
        orch._prowlarr = ProwlarrFalso()
        orch._transmission = TransmissionFalso()
        item = await s.get(Wishlist, item_id)
        vistos = await orch.preview_candidates(item)
        assert len(vistos) == 2
        elegido = vistos[-1]
        assert await orch.send_manual_candidate(item, elegido)
        assert enviados == [elegido.download_url]
        assert item.status == WishlistStatus.DOWNLOADING
        await s.commit()

    # La descarga "termina": llega el CBZ a Descargas.
    un_zip(entorno.descargas / "Flash 001 (1987).cbz")
    informe = await importar(entorno)
    async with entorno.banco.fabrica() as s:
        (fila,) = (await s.execute(select(File))).scalars().all()
        issue = (await s.execute(select(Issue))).scalar_one()
    assert informe.errors == [] and fila.issue_id == issue.id
    assert not any(entorno.descargas.iterdir())


async def test_especial_y_pack_no_crean_numero(entorno):
    await serie_vacia(entorno, titulo="Flash")
    un_zip(entorno.descargas / "Flash Especial 1.cbz", paginas=5)
    un_zip(entorno.descargas / "Flash 001-003.cbz", paginas=4)

    informe = await importar(entorno)

    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(Issue))).scalars().all() == []
        filas = (await s.execute(select(File))).scalars().all()
    assert len(informe.unsorted) == 2
    assert all("_Unsorted" in f.file_path for f in filas)


async def test_opt_in_apagado_no_crea_numero(entorno, monkeypatch):
    monkeypatch.setattr(mod.get_settings(), "import_create_missing_issue", False)
    await serie_vacia(entorno)
    un_zip(entorno.descargas / "Flash 001 (1987).cbz")

    await importar(entorno)

    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(Issue))).scalars().all() == []


async def test_nombre_sin_numero_no_crea_numero(entorno):
    await serie_vacia(entorno)
    un_zip(entorno.descargas / "Flash.cbz")

    await importar(entorno)

    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(Issue))).scalars().all() == []
