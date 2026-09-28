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

import asyncio
import contextlib
import hashlib
import os
import tempfile
import threading
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import File, FileFormat, Issue, Publisher, Series
from zascarr.services import tagger as tagger_mod
from zascarr.services.tagger import (
    CADUCADO,
    ESCRITO,
    INVALIDO,
    PREVISTO,
    SALTADO,
    TaggerService,
)
from zascarr.utils import cbz as zcbz
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
            # El servicio puede haber revertido la sesión por su cuenta (corta
            # el lote si no se recupera): en ese caso ya no hay nada que revertir.
            if transaccion.is_active:
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

        async def _planificar_y_ensuciar(self, file, ctx=None, **kw):
            campos = await original(self, file, ctx, **kw)
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
        assert [r.file_id for r in informe.resultados] == [str(objetivo.id)]
        assert leer_comicinfo(ruta_otro) is None


class TestLimitNoSeAtasca:
    """`--limit` acota trabajo NUEVO. Si volviera siempre sobre los mismos
    ficheros, el resto de la biblioteca no recibiría nunca su turno."""

    @pytest.mark.asyncio
    async def test_veintiuno_con_dos_pasadas_de_veinte(self, db, tmp_path):
        archivos = []
        for i in range(21):
            sub = tmp_path / f"f{i:02d}"
            sub.mkdir()
            archivos.append(await _montar(db, sub))
        ids = [str(a.id) for a, _ in archivos]
        servicio = TaggerService(db)

        p1 = await servicio.run(limit=20, dry_run=False, file_ids=ids)

        assert p1.escritos == 20
        assert sum(1 for _, r in archivos if leer_comicinfo(r) is not None) == 20

        p2 = await servicio.run(limit=20, dry_run=False, file_ids=ids)

        assert p2.escritos == 1          # el que faltaba avanza…
        assert p2.ya_revisados == 20     # …y los otros no gastan cupo
        assert sum(1 for _, r in archivos if leer_comicinfo(r) is not None) == 21

    @pytest.mark.asyncio
    async def test_los_que_ya_estaban_al_dia_tambien_se_marcan(self, db, tmp_path):
        archivo, _ = await _montar(db, tmp_path, xml=XML_MANUAL)
        ids = [str(archivo.id)]
        servicio = TaggerService(db)
        await servicio.run(limit=20, dry_run=False, file_ids=ids)

        p2 = await servicio.run(limit=20, dry_run=False, file_ids=ids)

        assert p2.ya_revisados == 1
        assert p2.escritos == 0
        # Con `--file-id` se detalla aunque estuviera ya revisado (el
        # coleccionista pregunta por ese fichero en concreto).
        assert [r.motivo for r in p2.resultados] == [
            "ya revisado (sin cambios desde la última pasada)"]

    @pytest.mark.asyncio
    async def test_un_cambio_en_la_bd_vuelve_a_pendiente(self, db, tmp_path):
        """La marca guarda con qué datos se comparó: si la BD cambia, se
        revisa otra vez (el overlay propaga la corrección)."""
        archivo, ruta = await _montar(db, tmp_path)
        ids = [str(archivo.id)]
        servicio = TaggerService(db)
        await servicio.run(limit=20, dry_run=False, file_ids=ids)

        serie = (await db.execute(
            select(Series).join(Issue, Issue.series_id == Series.id)
            .where(Issue.id == archivo.issue_id)
        )).scalar_one()
        serie.title = "Thorgal (reedición)"

        p2 = await servicio.run(limit=20, dry_run=False, file_ids=ids)

        assert p2.ya_revisados == 0
        assert p2.escritos == 1
        root = ElementTree.fromstring(leer_comicinfo(ruta))
        assert root.findtext("Series") == "Thorgal (reedición)"

    @pytest.mark.asyncio
    async def test_sin_limite_revisa_todo(self, db, tmp_path):
        ids = []
        for i in range(3):
            sub = tmp_path / f"f{i}"
            sub.mkdir()
            a, _ = await _montar(db, sub)
            ids.append(str(a.id))
        informe = await TaggerService(db).run(limit=0, dry_run=False, file_ids=ids)
        assert informe.escritos == 3


class TestComicInfoInvalido:
    """Un XML roto o ajeno no puede costar datos ni abortar el lote."""

    @pytest.mark.asyncio
    async def test_xml_ilegible_no_aborta_el_lote(self, db, tmp_path):
        (tmp_path / "roto").mkdir()
        (tmp_path / "bien").mkdir()
        roto, ruta_roto = await _montar(
            db, tmp_path / "roto", xml=b"<ComicInfo><Series>X</ComicInfo>")
        bien, ruta_bien = await _montar(db, tmp_path / "bien")
        antes = ruta_roto.read_bytes()

        informe = await TaggerService(db).run(
            limit=0, dry_run=False, file_ids=[str(roto.id), str(bien.id)])

        assert informe.invalidos == 1
        assert informe.escritos == 1                    # el siguiente SÍ se procesa
        assert ruta_roto.read_bytes() == antes          # y el roto queda intacto
        assert leer_comicinfo(ruta_bien) is not None

    @pytest.mark.asyncio
    async def test_raiz_ajena_no_se_sustituye(self, db, tmp_path):
        xml = b"<ComicInfoRaro><Algo>importante</Algo></ComicInfoRaro>"
        archivo, ruta = await _montar(db, tmp_path, xml=xml)

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert r.accion == INVALIDO
        assert leer_comicinfo(ruta) == xml

    @pytest.mark.asyncio
    async def test_dry_run_tambien_lo_reporta_sin_tocarlo(self, db, tmp_path):
        xml = b"<ComicInfo><Series>X</ComicInfo>"
        archivo, ruta = await _montar(db, tmp_path, xml=xml)
        r = await TaggerService(db).ejecutar(archivo, dry_run=True)
        assert r.accion == INVALIDO
        assert leer_comicinfo(ruta) == xml

    @pytest.mark.asyncio
    async def test_el_invalido_no_tapa_el_cupo_para_siempre(self, db, tmp_path):
        (tmp_path / "roto").mkdir()
        roto, _ = await _montar(db, tmp_path / "roto",
                                xml=b"<ComicInfo><Series>X</ComicInfo>")
        ids = [str(roto.id)]
        servicio = TaggerService(db)

        p1 = await servicio.run(limit=1, dry_run=False, file_ids=ids)
        p2 = await servicio.run(limit=1, dry_run=False, file_ids=ids)

        assert p1.invalidos == 1
        assert p2.ya_revisados == 1     # ya se sabe que está roto: no re-ocupa el cupo
        assert p2.invalidos == 0


class TestReconciliacionMismoTamano:
    """El tamaño no basta para saber si el fichero es el mismo: si el reemplazo
    salió bien y el commit falló, un XML del mismo tamaño deja el hash obsoleto
    y mirar solo `file_size_bytes` no lo delata nunca."""

    @pytest.mark.asyncio
    async def test_mismo_tamano_y_hash_distinto_se_corrige_solo(self, db, tmp_path):
        archivo, ruta = await _montar(db, tmp_path)
        servicio = TaggerService(db)
        await servicio.ejecutar(archivo, dry_run=False)   # ya etiquetado
        size = archivo.file_size_bytes

        # Reemplazo correcto + commit fallido: la BD se queda con el hash viejo
        # y sin marca de revisión. El tamaño, casualmente, es el mismo.
        archivo.sha256_hash = "0" * 64
        archivo.metadata_ = {}
        assert archivo.file_size_bytes == ruta.stat().st_size

        r = await servicio.ejecutar(archivo, dry_run=False)

        assert r.accion == SALTADO        # el XML ya coincide: no se reescribe
        assert r.reconciliado is True     # pero la BD se corrige sola
        assert archivo.sha256_hash == _sha256(ruta)
        assert archivo.file_size_bytes == size

    @pytest.mark.asyncio
    async def test_la_marca_fresca_evita_hashear(self, db, tmp_path, monkeypatch):
        """El `stat` es lo que hace barata la pasada normal en la Pi."""
        archivo, _ = await _montar(db, tmp_path)
        servicio = TaggerService(db)
        await servicio.ejecutar(archivo, dry_run=False)

        hasheados: list = []
        real = tagger_mod._sha256
        monkeypatch.setattr(tagger_mod, "_sha256",
                            lambda p: (hasheados.append(p), real(p))[1])

        r = await servicio.ejecutar(archivo, dry_run=False)

        assert r.accion == SALTADO and r.reconciliado is False
        assert hasheados == []            # ni un SHA256: bastaba el stat

    @pytest.mark.asyncio
    async def test_stat_cambiado_fuerza_el_recalculo(self, db, tmp_path, monkeypatch):
        """Si el fichero se tocó desde la última revisión, sí se rehashea."""
        archivo, ruta = await _montar(db, tmp_path)
        servicio = TaggerService(db)
        await servicio.ejecutar(archivo, dry_run=False)
        os.utime(ruta, ns=(0, 10**18))    # alguien lo tocó después

        hasheados: list = []
        real = tagger_mod._sha256
        monkeypatch.setattr(tagger_mod, "_sha256",
                            lambda p: (hasheados.append(p), real(p))[1])

        r = await servicio.ejecutar(archivo, dry_run=False)

        assert r.accion == SALTADO
        assert hasheados == [ruta]


class TestFicheroAusente:
    """Un `File` cuya ruta ya no existe (borrado a mano, disco de red caído) no
    puede abortar el lote: es exactamente lo que protege la colección."""

    @pytest.mark.asyncio
    async def test_no_aborta_el_lote(self, db, tmp_path):
        (tmp_path / "seva").mkdir()
        ido, ruta_ido = await _montar(db, tmp_path)
        ruta_ido.unlink()
        bien, ruta_bien = await _montar(db, tmp_path / "seva")

        informe = await TaggerService(db).run(
            limit=0, dry_run=False, file_ids=[str(ido.id), str(bien.id)])

        assert informe.saltados == 1
        assert informe.escritos == 1
        assert leer_comicinfo(ruta_bien) is not None

    @pytest.mark.asyncio
    async def test_tampoco_en_simulacion(self, db, tmp_path):
        ido, ruta_ido = await _montar(db, tmp_path)
        ruta_ido.unlink()
        informe = await TaggerService(db).run(
            limit=0, dry_run=True, file_ids=[str(ido.id)])
        assert informe.saltados == 1

    @pytest.mark.asyncio
    async def test_no_gastan_cupo(self, db, tmp_path):
        """Si no, 25 rutas rotas dejarían fuera al resto de la biblioteca."""
        (tmp_path / "seva").mkdir()
        ids = []
        for i in range(25):
            sub = tmp_path / f"ido{i:02d}"
            sub.mkdir()
            ido, ruta = await _montar(db, sub)
            ruta.unlink()
            ido.imported_at = datetime(2020, 1, 1, tzinfo=UTC)  # van primero
            ids.append(str(ido.id))
        bien, ruta_bien = await _montar(db, tmp_path / "seva")
        bien.imported_at = datetime(2021, 1, 1, tzinfo=UTC)
        ids.append(str(bien.id))
        await db.flush()

        informe = await TaggerService(db).run(limit=1, dry_run=False, file_ids=ids)

        assert informe.escritos == 1
        assert leer_comicinfo(ruta_bien) is not None


class TestBloqueoPorFichero:
    """El bloqueo tiene que sobrevivir al `os.replace`.

    Un `flock` sobre el propio CBZ no sirve: va con el *inodo*, y el reemplazo
    instala uno nuevo. La secuencia que lo rompe es la del revisor: A bloquea el
    inodo viejo → B se queda esperando ese mismo inodo → A reemplaza la ruta → C
    abre el inodo **nuevo** y entra sin esperar a nadie → cuando A suelta, B
    adquiere el bloqueo del inodo viejo (ya huérfano) y B y C reconstruyen la
    misma ruta a la vez, pudiendo borrarse los temporales entre sí.
    """

    def _motores(self):
        return [create_async_engine(_url_asyncpg(TEST_DATABASE_URL)) for _ in range(3)]

    @pytest.mark.asyncio
    async def test_tres_escritores_alrededor_de_un_replace_real(
        self, tmp_path, monkeypatch,
    ):
        ruta = _crear_cbz(tmp_path / "a.cbz")
        clave = uuid4()

        activos = 0
        maximo = 0
        creados: set[str] = set()
        borrados_activos: list[str] = []

        a_punto_de_reemplazar = threading.Event()   # A va a sustituir la ruta
        b_listo = threading.Event()                 # B ya espera al inodo viejo
        reemplazado = threading.Event()             # la ruta ya es el inodo nuevo
        puede_terminar = threading.Event()          # A puede salir de la sección

        real_verificar = zcbz._verificar
        real_reescribir = zcbz.reescribir_con_xml
        real_mkstemp = tempfile.mkstemp
        real_limpia = zcbz._limpiar_temporales_viejos

        def _mkstemp(*args, **kwargs):
            fd, nombre = real_mkstemp(*args, **kwargs)
            creados.add(nombre)
            return fd, nombre

        def _limpia(path):
            # Antes de borrar, anota qué temporales existen: si alguno de los
            # que ha creado un escritor vivo desaparece, es que este borrado se
            # ha colado en su sección crítica.
            antes = [p for p in path.parent.iterdir() if p.name.endswith(zcbz.SUFIJO_TMP)]
            real_limpia(path)
            for p in antes:
                if not p.exists() and str(p) in creados:
                    borrados_activos.append(str(p))

        def _verificar_lento(*args, **kwargs):
            real_verificar(*args, **kwargs)
            a_punto_de_reemplazar.set()
            b_listo.wait(timeout=5)                 # el hilo de A espera aquí

        def _reescribir_con_pausa(*args, **kwargs):
            real_reescribir(*args, **kwargs)
            reemplazado.set()
            puede_terminar.wait(timeout=5)          # ventana DESPUÉS del reemplazo

        monkeypatch.setattr(zcbz, "tempfile", tempfile)
        monkeypatch.setattr(zcbz.tempfile, "mkstemp", _mkstemp)
        monkeypatch.setattr(zcbz, "_limpiar_temporales_viejos", _limpia)
        monkeypatch.setattr(zcbz, "_verificar", _verificar_lento)
        monkeypatch.setattr(zcbz, "reescribir_con_xml", _reescribir_con_pausa)

        motores = self._motores()

        async def _escritor(engine, etiqueta):
            nonlocal activos, maximo
            async with tagger_mod.bloqueo_de_fichero(engine, clave):
                activos += 1
                maximo = max(maximo, activos)
                try:
                    await asyncio.to_thread(
                        zcbz.reescribir_con_xml, ruta,
                        f"<ComicInfo><Series>{etiqueta}</Series></ComicInfo>".encode())
                finally:
                    activos -= 1

        try:
            # A entra y se queda a punto de reemplazar.
            tarea_a = asyncio.ensure_future(_escritor(motores[0], "A"))
            while not a_punto_de_reemplazar.is_set():
                await asyncio.sleep(0.01)

            # B llega ANTES del reemplazo: abre el inodo viejo y espera.
            tarea_b = asyncio.ensure_future(_escritor(motores[1], "B"))
            await asyncio.sleep(0.2)
            b_listo.set()

            # A reemplaza la ruta y se queda dentro de la sección crítica.
            while not reemplazado.is_set():
                await asyncio.sleep(0.01)

            # C llega DESPUÉS: es el que se colaba por el inodo nuevo.
            tarea_c = asyncio.ensure_future(_escritor(motores[2], "C"))
            await asyncio.sleep(0.4)

            # Con el bloqueo por inodo, C ya estaría dentro (maximo == 2).
            assert activos == 1, "dos escritores a la vez en el mismo CBZ"
            assert borrados_activos == []

            puede_terminar.set()
            await asyncio.wait_for(asyncio.gather(tarea_a, tarea_b, tarea_c), timeout=10)
        finally:
            puede_terminar.set()
            for motor in motores:
                await motor.dispose()

        assert maximo == 1
        assert activos == 0
        assert borrados_activos == []
        with zipfile.ZipFile(ruta) as zf:
            nombres = [i.filename for i in zf.infolist()]
            assert zf.testzip() is None
        assert nombres.count("ComicInfo.xml") == 1
        assert all(p in nombres for p in PAGINAS)
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(zcbz.SUFIJO_TMP)]

    @pytest.mark.asyncio
    async def test_clave_estable_para_el_mismo_fichero(self):
        identificador = uuid4()
        assert tagger_mod._clave_de(identificador) == tagger_mod._clave_de(str(identificador))
        assert tagger_mod._clave_de(identificador) != tagger_mod._clave_de(uuid4())

    @pytest.mark.asyncio
    async def test_el_servicio_escribe_bajo_el_bloqueo(self, db, tmp_path, monkeypatch):
        archivo, ruta = await _montar(db, tmp_path)
        eventos: list[str] = []
        real_bloqueo = tagger_mod.bloqueo_de_fichero
        real_reescribir = zcbz.reescribir_con_xml

        @contextlib.asynccontextmanager
        async def _espia(engine, file_id):
            eventos.append(f"entra:{file_id}")
            async with real_bloqueo(engine, file_id):
                eventos.append("dentro")
                yield
            eventos.append("sale")

        def _reescribir_espia(*args, **kwargs):
            eventos.append("reemplaza")
            return real_reescribir(*args, **kwargs)

        monkeypatch.setattr(tagger_mod, "bloqueo_de_fichero", _espia)
        monkeypatch.setattr(zcbz, "reescribir_con_xml", _reescribir_espia)

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert r.accion == ESCRITO
        assert eventos == [f"entra:{archivo.id}", "dentro", "reemplaza", "sale"]

    @pytest.mark.asyncio
    async def test_la_simulacion_no_toma_el_bloqueo(self, db, tmp_path, monkeypatch):
        archivo, _ = await _montar(db, tmp_path)
        eventos: list[str] = []
        real_bloqueo = tagger_mod.bloqueo_de_fichero

        @contextlib.asynccontextmanager
        async def _espia(engine, file_id):
            eventos.append("bloquea")
            async with real_bloqueo(engine, file_id):
                yield

        monkeypatch.setattr(tagger_mod, "bloqueo_de_fichero", _espia)
        await TaggerService(db).ejecutar(archivo, dry_run=True)
        assert eventos == []


class TestVidaDelBloqueo:
    """`pg_advisory_xact_lock` en una conexión dedicada: el bloqueo lo suelta el
    fin de ESA transacción, no un `unlock` que puede no llegar a ejecutarse."""

    async def _libre(self, engine, clave, timeout: float = 3.0) -> bool:
        """¿Se puede volver a tomar la clave desde otra conexión?"""
        async with engine.connect() as otra:
            while timeout > 0:
                tomado = await otra.execute(
                    text("SELECT pg_try_advisory_xact_lock(:clave)"),
                    {"clave": tagger_mod._clave_de(clave)})
                if tomado.scalar():
                    return True
                await asyncio.sleep(0.05)
                timeout -= 0.05
        return False

    @pytest.mark.asyncio
    async def test_se_suelta_al_terminar_normalmente(self):
        engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
        clave = uuid4()
        try:
            async with tagger_mod.bloqueo_de_fichero(engine, clave):
                pass
            assert await self._libre(engine, clave)
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_se_suelta_aunque_la_transaccion_aborte(self):
        """El caso que `pg_advisory_lock` no cubría: si la transacción acaba
        abortada, un `unlock` explícito fallaría y el bloqueo de sesión podría
        seguir pegado a una conexión reutilizable del pool."""
        engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
        clave = uuid4()
        try:
            with pytest.raises(DBAPIError):
                async with tagger_mod.bloqueo_de_fichero(engine, clave) as conn:
                    await conn.execute(text("SELECT 1/0"))  # aborta la transacción

            assert await self._libre(engine, clave)
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_se_suelta_si_el_cuerpo_revienta(self):
        engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
        clave = uuid4()
        try:
            with pytest.raises(RuntimeError):
                async with tagger_mod.bloqueo_de_fichero(engine, clave):
                    raise RuntimeError("boom")
            assert await self._libre(engine, clave)
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_no_reutiliza_la_conexion_de_la_sesion(self, db, tmp_path, monkeypatch):
        """El bloqueo vive en su propia transacción corta, no en la del lote:
        si no, se retendría hasta el commit final."""
        archivo, _ = await _montar(db, tmp_path)
        conexion_sesion = await (await db.connection()).get_raw_connection()
        vistas = []
        real = tagger_mod.bloqueo_de_fichero

        @contextlib.asynccontextmanager
        async def _espia(engine, file_id):
            async with real(engine, file_id) as conn:
                vistas.append(await conn.get_raw_connection())
                yield conn

        with monkeypatch.context() as m:
            m.setattr(tagger_mod, "bloqueo_de_fichero", _espia)
            await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert vistas and vistas[0] is not conexion_sesion


class TestFalloDeBdEnElLote:
    """Un fallo de BD a mitad de lote no puede dejar la sesión envenenada ni
    anunciar que el lote siguió mientras los siguientes fallan en cadena."""

    @pytest.mark.asyncio
    async def test_un_error_de_bd_corta_el_lote_con_mensaje_claro(self, db, tmp_path, monkeypatch):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "c").mkdir()
        primero, _ = await _montar(db, tmp_path / "a")
        envenenado, _ = await _montar(db, tmp_path / "b")
        tercero, _ = await _montar(db, tmp_path / "c")
        ids = [str(x.id) for x in (primero, envenenado, tercero)]

        real = TaggerService._poner_marca

        def _envenenar(self, file, ctx, st, sha, resultado):
            real(self, file, ctx, st, sha, resultado)
            if str(file.id) == str(envenenado.id):
                # Error REAL de PostgreSQL: UNIQUE(files.file_path).
                file.file_path = primero.file_path

        monkeypatch.setattr(TaggerService, "_poner_marca", _envenenar)

        informe = await TaggerService(db).run(limit=0, dry_run=False, file_ids=ids)

        assert informe.abortado is not None          # se corta y se dice…
        assert "se reconcilian" in informe.abortado   # …con qué queda pendiente
        assert informe.errores == 1
        # Y NO se sigue: no hay ficheros posteriores con error en cadena.
        assert len(informe.resultados) == informe.escritos + 1

    @pytest.mark.asyncio
    async def test_un_error_que_no_toca_la_bd_no_corta_el_lote(self, db, tmp_path, monkeypatch):
        """Un fallo de un fichero que deja la sesión sana se apunta y se sigue."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        roto, _ = await _montar(db, tmp_path / "a")
        sano, ruta_sano = await _montar(db, tmp_path / "b")
        ids = [str(roto.id), str(sano.id)]

        real = TaggerService._poner_marca

        def _revienta(self, file, ctx, st, sha, resultado):
            if str(file.id) == str(roto.id):
                raise ValueError("fallo tonto de un fichero")
            real(self, file, ctx, st, sha, resultado)

        monkeypatch.setattr(TaggerService, "_poner_marca", _revienta)

        informe = await TaggerService(db).run(limit=0, dry_run=False, file_ids=ids)

        assert informe.abortado is None
        assert informe.errores == 1
        assert informe.escritos == 1
        assert leer_comicinfo(ruta_sano) is not None
