"""B6 — servicio de etiquetado contra Postgres real.

Los casos de prueba de la ficha se comprueban aquí de punta a punta: BD + CBZ
de verdad en un directorio temporal. Se salta sin `TEST_DATABASE_URL`, mismo
patrón que `test_b8_pg.py` / `test_huecos_pg.py`.

    docker run --rm -d --name zascarr-pg-test -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=zascarr_test -p 55432:5432 postgres:15
    TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55432/zascarr_test \\
        pytest tests/test_b6_tagger_pg.py
"""
from __future__ import annotations

import hashlib
import os
import zipfile
from datetime import date
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import File, FileFormat, Issue, Publisher, Series
from zascarr.services.tagger import (
    CADUCADO,
    ESCRITO,
    PREVISTO,
    SALTADO,
    TaggerService,
)
from zascarr.utils.cbz import leer_comicinfo

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

PAGINAS = [f"p{i:03d}.jpg" for i in range(3)]
XML_MANUAL = b"<ComicInfo><Summary>Resumen escrito a mano</Summary></ComicInfo>"


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def db():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        nombre = (await session.execute(text("SELECT current_database()"))).scalar()
        if not nombre or "test" not in nombre.lower():
            raise RuntimeError(f"TEST_DATABASE_URL apunta a «{nombre}»; se niega.")
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _crear_cbz(ruta: Path, xml: bytes | None = None) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in PAGINAS:
            zf.writestr(p, f"pagina-{p}".encode())
        if xml is not None:
            zf.writestr("ComicInfo.xml", xml)
    return ruta


async def _montar(
    db, tmp_path: Path, *,
    xml: bytes | None = None,
    formato: FileFormat = FileFormat.CBZ,
    con_publisher: bool = True,
    con_release_date: bool = True,
    start_year: int | None = 1970,
    series_title: str = "Thorgal",
    issue_number: str | None = "1",
    volume: int = 1,
    synopsis: str | None = "Resumen de ZascArr",
    locked_issue: list[str] | None = None,
    locked_series: list[str] | None = None,
    metadata: dict | None = None,
):
    publisher = None
    if con_publisher:
        # `publishers.name` es UNIQUE: se reutiliza si ya existe en la transacción.
        publisher = (await db.execute(
            select(Publisher).where(Publisher.name == "Distrinovel")
        )).scalar_one_or_none()
        if publisher is None:
            publisher = Publisher(id=uuid4(), name="Distrinovel")
            db.add(publisher)
    serie = Series(
        id=uuid4(), title=series_title, start_year=start_year,
        publisher_id=publisher.id if publisher else None,
        locked_fields=locked_series or [],
    )
    db.add(serie)
    issue = Issue(
        id=uuid4(), series_id=serie.id, issue_number=issue_number, volume=volume,
        release_date=date(1980, 5, 1) if con_release_date else None,
        synopsis=synopsis, locked_fields=locked_issue or [],
    )
    db.add(issue)

    ruta = tmp_path / f"fichero.u{formato.value}"
    if formato is FileFormat.CBZ:
        _crear_cbz(ruta, xml)
    else:
        ruta.write_bytes(b"no es un zip")  # un CBR nunca se abre

    archivo = File(
        id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
        file_format=formato, file_size_bytes=ruta.stat().st_size,
        sha256_hash=_sha256(ruta), metadata_=metadata or {},
    )
    db.add(archivo)
    await db.flush()
    return archivo, ruta


def _acciones(resultado) -> dict:
    return {c.tag: c.accion.value for c in resultado.campos}


class TestEscritura:

    @pytest.mark.asyncio
    async def test_escribe_los_campos_deseados(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert r.accion == ESCRITO
        root = ElementTree.fromstring(leer_comicinfo(ruta))
        assert root.findtext("Series") == "Thorgal"
        assert root.findtext("Number") == "1"
        assert root.findtext("Volume") == "1"
        assert root.findtext("Year") == "1980"
        assert root.findtext("Publisher") == "Distrinovel"
        assert root.findtext("Summary") == "Resumen de ZascArr"

    @pytest.mark.asyncio
    async def test_conserva_las_paginas(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)
        await TaggerService(db).ejecutar(archivo, dry_run=False)
        with zipfile.ZipFile(ruta) as zf:
            nombres = [i.filename for i in zf.infolist()]
        assert all(p in nombres for p in PAGINAS)

    @pytest.mark.asyncio
    async def test_es_idempotente(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)
        servicio = TaggerService(db)
        await servicio.ejecutar(archivo, dry_run=False)
        after = _sha256(ruta)

        r = await servicio.ejecutar(archivo, dry_run=False)

        assert r.accion == SALTADO
        assert _sha256(ruta) == after

    @pytest.mark.asyncio
    async def test_hash_y_tamano_actualizados(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)
        await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert archivo.sha256_hash == _sha256(ruta)
        assert archivo.file_size_bytes == ruta.stat().st_size

    @pytest.mark.asyncio
    async def test_numero_ausente_no_se_inventa(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path, issue_number=None)
        r = await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert _acciones(r)["Number"] == "sin_dato"
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Number") is None


class TestYearYLanguage:

    @pytest.mark.asyncio
    async def test_year_es_el_de_release_date_no_start_year(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path, start_year=1970)
        await TaggerService(db).ejecutar(archivo, dry_run=False)
        root = ElementTree.fromstring(leer_comicinfo(ruta))
        assert root.findtext("Year") == "1980"  # no 1970

    @pytest.mark.asyncio
    async def test_sin_release_date_year_manual_intacto(self, db, tmp_path):
        xml = b"<ComicInfo><Year>1955</Year></ComicInfo>"
        archivo, ruta = await _montar(db, tmp_path, xml=xml, con_release_date=False)

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert _acciones(r)["Year"] == "sin_dato"
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Year") == "1955"

    @pytest.mark.asyncio
    async def test_language_iso_no_se_genera(self, db, tmp_path):
        """La tradición no acredita el idioma del ejemplar."""
        archivo, ruta = await _montar(db, tmp_path)
        await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("LanguageISO") is None

    @pytest.mark.asyncio
    async def test_language_iso_existente_se_preserva(self, db, tmp_path):
        xml = b"<ComicInfo><LanguageISO>es</LanguageISO></ComicInfo>"
        archivo, ruta = await _montar(db, tmp_path, xml=xml)
        await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("LanguageISO") == "es"


class TestProcedencia:

    @pytest.mark.asyncio
    async def test_no_pisa_un_resumen_manual(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path, xml=XML_MANUAL)
        r = await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert _acciones(r)["Summary"] == "conserva"
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Summary") == \
            "Resumen escrito a mano"

    @pytest.mark.asyncio
    async def test_overlay_tras_haber_escrito_zascarr(self, db, tmp_path):
        """Con rastro de autoría, el valor obsoleto de ZascArr sí se actualiza."""
        xml = b"<ComicInfo><Summary>Resumen viejo de ZascArr</Summary></ComicInfo>"
        archivo, ruta = await _montar(
            db, tmp_path, xml=xml,
            metadata={"comicinfo_propio": {"Summary": "Resumen viejo de ZascArr"}},
        )

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert _acciones(r)["Summary"] == "cambia"
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Summary") == \
            "Resumen de ZascArr"

    @pytest.mark.asyncio
    async def test_deja_rastro_de_autoria(self, db, tmp_path):
        archivo, _ = await _montar(db, tmp_path)
        await TaggerService(db).ejecutar(archivo, dry_run=False)
        propio = archivo.metadata_["comicinfo_propio"]
        assert propio["Series"] == "Thorgal"
        assert propio["Summary"] == "Resumen de ZascArr"
        assert "LanguageISO" not in propio

    @pytest.mark.asyncio
    async def test_no_overwrite_no_actualiza_ni_con_prueba(self, db, tmp_path):
        xml = b"<ComicInfo><Summary>Resumen viejo de ZascArr</Summary></ComicInfo>"
        archivo, ruta = await _montar(
            db, tmp_path, xml=xml,
            metadata={"comicinfo_propio": {"Summary": "Resumen viejo de ZascArr"}},
        )
        r = await TaggerService(db).ejecutar(archivo, dry_run=False, solo_rellenar=True)
        assert _acciones(r)["Summary"] == "conserva"
        assert _acciones(r)["Series"] == "cambia"  # el vacío sí se rellena


class TestBloqueos:

    @pytest.mark.asyncio
    async def test_locked_fields_no_se_sobrescribe(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path, locked_issue=["synopsis"])

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert _acciones(r)["Summary"] == "bloqueado"
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Summary") is None
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Series") == "Thorgal"

    @pytest.mark.asyncio
    async def test_locked_del_serie_bloquea_el_campo(self, db, tmp_path):
        archivo, _ = await _montar(db, tmp_path, locked_series=["title"])
        r = await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert _acciones(r)["Series"] == "bloqueado"


class TestFormatos:

    @pytest.mark.asyncio
    async def test_cbr_no_se_toca(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path, formato=FileFormat.CBR)
        antes = ruta.read_bytes()
        r = await TaggerService(db).ejecutar(archivo, dry_run=False)
        assert r.accion == SALTADO
        assert "CBZ" in r.motivo
        assert ruta.read_bytes() == antes


class TestSimulacion:

    @pytest.mark.asyncio
    async def test_dry_run_no_escribe_nada(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)
        antes_sha, antes_mtime = _sha256(ruta), ruta.stat().st_mtime_ns

        r = await TaggerService(db).ejecutar(archivo, dry_run=True)

        assert r.accion == PREVISTO
        assert _sha256(ruta) == antes_sha
        assert ruta.stat().st_mtime_ns == antes_mtime
        assert leer_comicinfo(ruta) is None
        assert archivo.sha256_hash == antes_sha

    @pytest.mark.asyncio
    async def test_dry_run_lista_las_tres_decisiones(self, db, tmp_path):
        xml = (b"<ComicInfo><Series>Thorgal</Series>"
               b"<Summary>Resumen escrito a mano</Summary></ComicInfo>")
        archivo, _ = await _montar(db, tmp_path, xml=xml)
        r = await TaggerService(db).ejecutar(archivo, dry_run=True)
        acciones = _acciones(r)
        assert acciones["Series"] == "ya_coincide"
        assert acciones["Summary"] == "conserva"   # procedencia desconocida
        assert acciones["Publisher"] == "cambia"   # vacío → se rellena
        assert acciones["LanguageISO"] == "sin_dato"

    @pytest.mark.asyncio
    async def test_un_solo_plan_entre_simulacion_y_ejecucion(self, db, tmp_path):
        archivo, _ = await _montar(db, tmp_path, xml=XML_MANUAL)
        servicio = TaggerService(db)

        previsto = await servicio.ejecutar(archivo, dry_run=True)
        aplicado = await servicio.ejecutar(archivo, dry_run=False)

        assert previsto.campos == aplicado.campos
        assert previsto.accion == PREVISTO and aplicado.accion == ESCRITO

    @pytest.mark.asyncio
    async def test_plan_caduca_si_el_cbz_cambia(self, db, tmp_path, monkeypatch):
        """Entre previsualizar y aplicar, otro proceso tocó el CBZ."""
        archivo, ruta = await _montar(db, tmp_path)
        original = TaggerService.planificar

        async def _planificar_y_ensuciar(self, file, **kw):
            campos = await original(self, file, **kw)
            with zipfile.ZipFile(ruta, "a") as zf:  # alguien añadió una página
                zf.writestr("p999.jpg", b"intruso")
            return campos

        monkeypatch.setattr(TaggerService, "planificar", _planificar_y_ensuciar)

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert r.accion == CADUCADO
        assert leer_comicinfo(ruta) is None  # no se aplicó el plan viejo
        with zipfile.ZipFile(ruta) as zf:
            assert "p999.jpg" in zf.namelist()


class TestReconciliacion:

    @pytest.mark.asyncio
    async def test_hash_obsoleto_se_reconcilia_sin_reescribir(self, db, tmp_path):
        """Reemplazo correcto + commit fallido: la siguiente pasada cuadra la BD."""
        archivo, ruta = await _montar(db, tmp_path)
        servicio = TaggerService(db)

        # El reemplazo ocurrió (lo hizo un proceso que luego no pudo commitear),
        # pero el `File` sigue con el hash y el tamaño viejos.
        r = await servicio.ejecutar(archivo, dry_run=False)
        assert r.accion == ESCRITO
        bueno, size = archivo.sha256_hash, archivo.file_size_bytes
        archivo.sha256_hash = "0" * 64
        archivo.file_size_bytes = 1
        archivo.metadata_ = {}  # y sin rastro de autoría, como si no se guardó
        contenido = ruta.read_bytes()

        r2 = await servicio.ejecutar(archivo, dry_run=False)

        assert r2.accion == SALTADO          # el XML ya coincide, no se reescribe
        assert r2.reconciliado is True
        assert ruta.read_bytes() == contenido
        assert archivo.sha256_hash == bueno
        assert archivo.file_size_bytes == size

    @pytest.mark.asyncio
    async def test_dry_run_informa_del_desfase_sin_tocar_la_sesion(self, db, tmp_path):
        """«No escribe nada» vale también para la BD: el dry-run no corrige."""
        archivo, _ = await _montar(db, tmp_path)
        servicio = TaggerService(db)
        await servicio.ejecutar(archivo, dry_run=False)
        archivo.sha256_hash = "0" * 64
        archivo.file_size_bytes = 1

        r = await servicio.ejecutar(archivo, dry_run=True)

        assert r.reconciliado is True           # lo reporta…
        assert archivo.sha256_hash == "0" * 64  # …pero no lo cambia
        assert archivo.file_size_bytes == 1

    @pytest.mark.asyncio
    async def test_reconciliar_todo_fuerza_el_recalculo(self, db, tmp_path):
        archivo, _ = await _montar(db, tmp_path)
        servicio = TaggerService(db)
        await servicio.ejecutar(archivo, dry_run=False)
        bueno = archivo.sha256_hash
        archivo.sha256_hash = "0" * 64  # mismo tamaño, hash mentiroso

        informe = await servicio.run(reconciliar_todo=True, dry_run=False)

        assert informe.reconciliados == 1
        assert archivo.sha256_hash == bueno


class TestInforme:

    @pytest.mark.asyncio
    async def test_run_dry_run_no_escribe_y_cuenta(self, db, tmp_path):
        archivo, _ = await _montar(db, tmp_path)
        informe = await TaggerService(db).run(dry_run=True, file_ids=[archivo.id])
        assert informe.previstos == 1
        assert informe.escritos == 0
        assert "previstos" in informe.resumen()

    @pytest.mark.asyncio
    async def test_run_apply_escribe(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)
        informe = await TaggerService(db).run(dry_run=False, file_ids=[archivo.id])
        assert informe.escritos == 1
        assert leer_comicinfo(ruta) is not None

    @pytest.mark.asyncio
    async def test_run_por_file_id(self, db, tmp_path):
        (tmp_path / "otro").mkdir()
        objetivo, _ = await _montar(db, tmp_path)
        otro, ruta_otro = await _montar(db, tmp_path / "otro")
        informe = await TaggerService(db).run(
            dry_run=False, file_ids=[objetivo.id],
        )
        assert [r.file_id for r in informe.resultados] == [objetivo.id]
        assert leer_comicinfo(ruta_otro) is None
