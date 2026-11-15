"""Corte B: el importer resuelve la raíz de la tradición antes de mover (#156).

Sin BD real: dobles del triaje/matcher y una foto de raíces explícita.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.core.importer_triage import TriageResult
from zascarr.core.matcher import MatchResult, MatchStatus
from zascarr.models import ComicTradition, Series
from zascarr.services import importer as mod
from zascarr.services.importer import Importer, ImportReport
from zascarr.services.raices import FotoDeRaices, Montaje
from zascarr.utils.espacio import EspacioInsuficienteError


class FakeResult:
    def __init__(self, serie):
        self._serie = serie

    def scalar_one_or_none(self):
        return self._serie


class FakeDb:
    def __init__(self, serie=None):
        self.serie = serie
        self.added = []

    async def execute(self, _stmt):
        return FakeResult(self.serie)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


def raiz(tmp_path, tradicion, *, name="Biblioteca", default=False, enabled=True):
    path = tmp_path / name.lower().replace(" ", "-")
    path.mkdir(exist_ok=True)
    return SimpleNamespace(
        id=uuid4(), name=name, path=str(path), host_path=None,
        enabled=enabled, is_default=default,
        traditions=[SimpleNamespace(tradition=t) for t in tradicion],
    )


def foto(*raices):
    return FotoDeRaices(list(raices), validar=False)


def serie(tradicion=ComicTradition.AMERICAN, title="Batman"):
    return Series(id=uuid4(), title=title, start_year=2011, tradition=tradicion)


def preparar(tmp_path, monkeypatch, *, raices, result=None, serie_obj=None):
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(
        library_path=tmp_path / "library",
        transmission_download_dir=str(tmp_path / "downloads"),
        amule_incoming_dir=str(tmp_path / "amule"),
        downloads_path=tmp_path / "downloads",
    ))
    src = tmp_path / "Batman 001.cbz"
    src.write_bytes(b"x")
    tr = TriageResult(path=src, sha256="a" * 64)
    result = result or MatchResult(
        MatchStatus.DIRECT, series_id=serie_obj.id if serie_obj else None, issue_id=None)
    outcome = SimpleNamespace(
        tr=tr, result=result, error_lectura=None, recuperar=None, duplicate_of=None,
        cohorte_explicacion=None, edition_kind=None)
    async def triage(_db, _path, _pista=None):
        return outcome
    monkeypatch.setattr(mod, "_triage_and_match", triage)
    db = FakeDb(serie_obj)
    imp = Importer(db, foto_raices=foto(*raices))
    return imp, db, src


@pytest.mark.asyncio
async def test_importa_en_la_raiz_de_la_tradicion(tmp_path, monkeypatch):
    usa = raiz(tmp_path, [ComicTradition.AMERICAN], name="EEUU")
    manga = raiz(tmp_path, [ComicTradition.MANGA], name="Manga")
    s = serie()
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[usa, manga], serie_obj=s)
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert report.errors == []
    f = db.added[0]
    assert f.root_id == usa.id
    assert f.file_path.startswith(str(usa.path))
    assert str(manga.path) not in str(f.file_path)
    assert str(f.file_path).endswith("Comics/Batman (2011)/Batman 001.cbz")
    assert not src.exists()


@pytest.mark.asyncio
async def test_tradicion_sin_raiz_no_mueve_ni_crea_fila(tmp_path, monkeypatch):
    manga = raiz(tmp_path, [ComicTradition.MANGA], name="Manga")
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[manga], serie_obj=serie())
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert src.exists() and db.added == []
    assert "no tiene una raíz asignada" in report.errors[0]


@pytest.mark.asyncio
async def test_unsorted_va_a_la_raiz_por_defecto(tmp_path, monkeypatch):
    default = raiz(tmp_path, [ComicTradition.AMERICAN], name="Default", default=True)
    imp, db, src = preparar(
        tmp_path, monkeypatch, raices=[default],
        result=MatchResult(MatchStatus.UNSORTED), serie_obj=None)
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    f = db.added[0]
    assert f.root_id == default.id
    assert f.file_path == str(tmp_path / "default" / "_Unsorted" / "Batman 001.cbz")
    assert not src.exists()


@pytest.mark.asyncio
async def test_raiz_deshabilitada_no_mueve(tmp_path, monkeypatch):
    r = raiz(tmp_path, [ComicTradition.AMERICAN], name="Apagada", enabled=False)
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[r], serie_obj=serie())
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert src.exists() and db.added == [] and "deshabilitada" in report.errors[0]


@pytest.mark.asyncio
async def test_raiz_llena_no_mueve(tmp_path, monkeypatch):
    r = raiz(tmp_path, [ComicTradition.AMERICAN], name="Llena")
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[r], serie_obj=serie())

    def sin_espacio(*_a, **_kw):
        raise EspacioInsuficienteError(bytes_libres=0, bytes_necesarios=1, contexto="x")
    monkeypatch.setattr(mod, "comprobar_espacio", sin_espacio)
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert src.exists() and db.added == [] and "espacio" in report.errors[0]


@pytest.mark.asyncio
async def test_no_usa_default_si_la_tradicion_no_tiene_raiz(tmp_path, monkeypatch):
    default = raiz(tmp_path, [ComicTradition.MANGA], name="Default", default=True)
    imp, db, src = preparar(
        tmp_path, monkeypatch, raices=[default],
        serie_obj=serie(ComicTradition.AMERICAN))
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert src.exists() and db.added == [] and "no tiene una raíz" in report.errors[0]


@pytest.mark.asyncio
async def test_raiz_ausente_no_mueve_ni_crea_fila(tmp_path, monkeypatch):
    r = raiz(tmp_path, [ComicTradition.AMERICAN], name="Ausente")
    r.path = str(tmp_path / "no-existe")
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[r], serie_obj=serie())
    # La foto se construye con validación real para comprobar existencia.
    monkeypatch.setattr("zascarr.services.raices.rutas_autorizadas",
                        lambda: [Montaje(path=str(tmp_path))])
    imp._foto_raices = FotoDeRaices([r])
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert src.exists() and db.added == []
    assert "no existe" in report.errors[0]


@pytest.mark.asyncio
async def test_raiz_se_deshabilita_entre_dos_archivos(tmp_path, monkeypatch):
    r = raiz(tmp_path, [ComicTradition.AMERICAN], name="Biblioteca")
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[r], serie_obj=serie())
    monkeypatch.setattr("zascarr.services.raices.rutas_autorizadas",
                        lambda: [Montaje(path=str(tmp_path))])
    imp._foto_raices = FotoDeRaices([r])
    first = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, first)
    assert db.added and db.added[0].root_id is not None
    r.enabled = False
    segundo = tmp_path / "Batman 002.cbz"
    segundo.write_bytes(b"y")
    second = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(segundo, second)
    assert segundo.exists() and len(db.added) == 1
    assert "deshabilitada" in second.errors[0]


@pytest.mark.asyncio
async def test_error_no_filtra_la_ruta_absoluta_en_el_informe(tmp_path, monkeypatch):
    r = raiz(tmp_path, [ComicTradition.AMERICAN], name="Biblioteca")
    imp, db, src = preparar(tmp_path, monkeypatch, raices=[r], serie_obj=serie())

    def falla(_ruta, _n, _ctx):
        raise OSError(f"fallo en {src}")
    monkeypatch.setattr(mod, "comprobar_espacio", falla)
    report = ImportReport(started_at=datetime.now(UTC))
    await imp._import_file(src, report)
    assert str(src) not in " ".join(report.errors)
    assert str(tmp_path) not in " ".join(report.errors)
