"""Lector CBZ (BL-LEC1): servicio de páginas, progreso y pantalla."""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from tests.test_pendientes import FakeExecResult, FakeSession, use_fake_session
from zascarr.core.importer_triage import parse_comic_info
from zascarr.main import app
from zascarr.models import File, FileFormat, Issue, Series
from zascarr.services import lector


def _jpeg(color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buf, format="JPEG")
    return buf.getvalue()


def _cbz(tmp_path):
    ruta = tmp_path / "lectura.cbz"
    with zipfile.ZipFile(ruta, "w") as z:
        for i in (2, 1, 10):
            z.writestr(f"{i:03d}.jpg", _jpeg((i * 20, 30, 30)))
    return ruta


def _file(tmp_path):
    return File(id=uuid4(), issue_id=uuid4(), file_path=str(_cbz(tmp_path)),
                file_name="lectura.cbz", file_format=FileFormat.CBZ, metadata_={})


@pytest.mark.asyncio
async def test_listado_natural_y_pagina_por_indice(tmp_path):
    f = _file(tmp_path)
    db = FakeSession(get_map={(File, f.id): f})
    assert await lector.total_paginas(db, f.id) == 3
    p1 = await lector.pagina(db, f.id, 1)
    p2 = await lector.pagina(db, f.id, 2)
    assert p1.content_type == "image/jpeg" and p1.etag != p2.etag
    assert len(p1.datos) > 0 and p1.datos != p2.datos


@pytest.mark.asyncio
async def test_pagina_fuera_de_rango_y_archivo_no_zip(tmp_path):
    f = _file(tmp_path)
    db = FakeSession(get_map={(File, f.id): f})
    with pytest.raises(lector.PaginaFueraDeRangoError):
        await lector.pagina(db, f.id, 0)
    f2 = File(id=uuid4(), issue_id=uuid4(), file_path=str(tmp_path / "x.pdf"),
              file_name="x.pdf", file_format=FileFormat.PDF, metadata_={})
    db2 = FakeSession(get_map={(File, f2.id): f2})
    with pytest.raises(lector.ArchivoNoLegibleError):
        await lector.pagina(db2, f2.id, 1)


@pytest.mark.asyncio
async def test_archivos_legibles_por_db(tmp_path):
    f = _file(tmp_path)
    cbr = File(id=uuid4(), issue_id=f.issue_id, file_path=str(tmp_path / "x.cbr"),
               file_name="x.cbr", file_format=FileFormat.CBR, metadata_={})
    db = FakeSession(exec_queue=[FakeExecResult([f, cbr])])
    filas = await lector.archivos_legibles(db, f.issue_id)
    assert [a.id for a in filas] == [str(f.id), str(cbr.id)]


def test_pantalla_y_pagina(tmp_path, monkeypatch):
    from zascarr.services.lector import SIN_SIGUIENTE, Siguiente
    from zascarr.web import lector as wlector

    async def _sin(*_a, **_k):
        return Siguiente(SIN_SIGUIENTE)

    async def _ack(*_a, **_k):
        return True

    monkeypatch.setattr(wlector, "siguiente_numero", _sin)
    monkeypatch.setattr(wlector, "is_acknowledged", _ack)
    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, title="Serie", metadata_={},
                            tradition=SimpleNamespace(value="american"))
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie},
                     exec_queue=[FakeExecResult([None])])
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
        assert r.status_code == 200
        assert 'data-total="3"' in r.text and "/pagina/1" in r.text
        p = client.get(f"/ui/leer/{f.id}/pagina/1")
        assert p.status_code == 200 and p.headers["content-type"].startswith("image/jpeg")
        assert p.headers["x-content-type-options"] == "nosniff"
        r304 = client.get(f"/ui/leer/{f.id}/pagina/1",
                          headers={"If-None-Match": p.headers["etag"]})
        assert r304.status_code == 304
        assert client.get(f"/ui/leer/{f.id}/pagina/0").status_code == 404
        assert client.get(f"/ui/leer/{f.id}/pagina/99").status_code == 404


def test_guardar_progreso_recorta_y_marca_leyendo(tmp_path):
    f = _file(tmp_path)
    añadidos = []

    class Db(FakeSession):
        def add(self, obj):
            añadidos.append(obj)

    db = Db(get_map={(File, f.id): f}, exec_queue=[FakeExecResult([])])
    import asyncio
    asyncio.run(lector.guardar_progreso(db, f.id, 99))
    assert db.commit.await_count == 1
    p = añadidos[0]
    assert p.current_page == 3 and p.file_id == f.id
    assert p.status.value == "reading"


def test_ruta_de_progreso_devuelve_204_y_guarda_la_pagina(tmp_path):
    f = _file(tmp_path)
    añadidos = []

    class Db(FakeSession):
        def add(self, obj):
            añadidos.append(obj)

    db = Db(get_map={(File, f.id): f}, exec_queue=[FakeExecResult([])])
    with use_fake_session(db):
        from fastapi.testclient import TestClient
        r = TestClient(app).post(f"/ui/leer/{f.id}/progreso", data={"pagina": "99"})
    assert r.status_code == 204 and añadidos[0].current_page == 3


def test_la_ficha_tiene_el_enlace_de_leer_sin_escribir():
    from pathlib import Path
    t = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "web"
         / "templates" / "issue_detail.html").read_text(encoding="utf-8")
    assert "lector_archivo" in t and "/ui/leer/" in t
    assert "Continuar (pág." in t


def test_comicinfo_lee_manga():
    info = parse_comic_info(b'<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>')
    assert info.manga == "YesAndRightToLeft"


@pytest.mark.asyncio
async def test_sentido_prioridad_serie_comicinfo_tradicion(tmp_path, monkeypatch):
    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, metadata_={},
                            tradition=SimpleNamespace(value="manga"))
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie})
    monkeypatch.setattr(lector, "_manga_del_archivo", lambda _p: None)
    assert await lector.sentido_de_lectura(db, f.id) == ("rtl", "tradicion")
    monkeypatch.setattr(lector, "_manga_del_archivo",
                        lambda _p: "YesAndRightToLeft")
    assert await lector.sentido_de_lectura(db, f.id) == ("rtl", "comicinfo")
    serie.metadata_ = {"lector_sentido": "ltr"}
    assert await lector.sentido_de_lectura(db, f.id) == ("ltr", "serie")


@pytest.mark.asyncio
async def test_guardar_sentido_por_serie(tmp_path):
    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, metadata_={"otro": 1},
                            tradition=SimpleNamespace(value="american"))
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie})
    await lector.guardar_sentido(db, f.id, "rtl")
    assert serie.metadata_ == {"otro": 1, "lector_sentido": "rtl"}
    assert db.commit.await_count == 1


def test_js_lector_tiene_los_contratos_de_lec2():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static"
          / "lector.js").read_text(encoding="utf-8")
    for pieza in ("localStorage", "Math.abs(dx) >= 50", "2 * Math.abs(dy)",
                  "requestFullscreen", "touch-action"):
        assert pieza in js or pieza in (Path(__file__).resolve().parents[1] / "src"
                                        / "zascarr" / "static" / "web.css").read_text()


def test_ruta_sentido_guarda_por_serie(tmp_path):
    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, metadata_={},
                            tradition=SimpleNamespace(value="american"))
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie})
    with use_fake_session(db):
        from fastapi.testclient import TestClient
        r = TestClient(app).post(f"/ui/leer/{f.id}/sentido", data={"sentido": "rtl"})
    assert r.status_code == 204
    assert serie.metadata_["lector_sentido"] == "rtl"


@pytest.mark.asyncio
async def test_un_cbz_convertido_con_formato_viejo_es_legible(tmp_path):
    f = _file(tmp_path)
    f.metadata_ = {"conversion": {"estado": "convertida"},
                   "formato_contenido": {"firma": "rar", "contrato": 1}}
    db = FakeSession(exec_queue=[FakeExecResult([f])])
    filas = await lector.archivos_legibles(db, f.issue_id)
    assert [a.id for a in filas] == [str(f.id)]


def test_comicinfo_roto_no_tumba_el_lector(tmp_path):
    ruta = tmp_path / "roto.cbz"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("ComicInfo.xml", b"<ComicInfo><Manga>YesAndRightToLeft")
        z.writestr("01.jpg", _jpeg())
    assert lector._manga_del_archivo(ruta) is None


def test_comicinfo_demasiado_grande_se_ignora(tmp_path):
    ruta = tmp_path / "grande.cbz"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("ComicInfo.xml", b"<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>"
                                   + b" " * (lector.MAX_COMICINFO_BYTES + 10))
        z.writestr("01.jpg", _jpeg())
    assert lector._manga_del_archivo(ruta) is None


def _rar_file(tmp_path):
    ruta = tmp_path / "lectura.cbr"
    ruta.write_bytes(b"Rar!\x1a\x07\x00" + b"x" * 20)
    return File(id=uuid4(), issue_id=uuid4(), file_path=str(ruta),
                file_name=ruta.name, file_format=FileFormat.CBR,
                metadata_={"formato_contenido": {"firma": "rar", "contrato": 1}})


def test_un_cbr_rar_es_legible_para_el_lector(tmp_path):
    f = _rar_file(tmp_path)
    assert lector._es_legible(f) is True


def test_pantalla_rar_muestra_preparando(tmp_path, monkeypatch):
    from zascarr.services.cache_lectura import Estado
    from zascarr.web import lector as wlector

    f = _rar_file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, title="Serie", metadata_={},
                            tradition=SimpleNamespace(value="american"))

    class Cache:
        async def preparar(self, _f):
            return Estado("preparando")

    monkeypatch.setattr(wlector, "CACHE", Cache())
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie})
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert r.status_code == 200
    assert "Preparando el tebeo" in r.text
    assert f"/ui/leer/{f.id}/estado" in r.text


def test_estado_rar_listo(tmp_path, monkeypatch):
    from zascarr.services.cache_lectura import Estado
    from zascarr.web import lector as wlector

    f = _rar_file(tmp_path)

    class Cache:
        def estado(self, _f):
            return Estado("listo")

    monkeypatch.setattr(wlector, "CACHE", Cache())
    db = FakeSession(get_map={(File, f.id): f})
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}/estado")
    assert r.status_code == 200 and r.json() == {"estado": "listo", "motivo": ""}


def _pantalla_con_siguiente(tmp_path, monkeypatch, estado, legal=True):
    from zascarr.services.lector import FALTA, LEER, ArchivoDeLectura, Siguiente
    from zascarr.web import lector as wlector

    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, title="Serie", metadata_={},
                            tradition=SimpleNamespace(value="american"))
    siguiente = (Siguiente(LEER, serie, 2, SimpleNamespace(id=uuid4()),
                           ArchivoDeLectura(str(uuid4()), "2.cbz", "CBZ"))
                 if estado == LEER else Siguiente(FALTA, serie, 2))

    async def _siguiente(*_a, **_k):
        return siguiente

    async def _ack(*_a, **_k):
        return legal

    monkeypatch.setattr(wlector, "siguiente_numero", _siguiente)
    monkeypatch.setattr(wlector, "is_acknowledged", _ack)
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie},
                     exec_queue=[FakeExecResult([None])])
    return f, db


def test_tarjeta_final_leer_se_pinta_en_servidor(tmp_path, monkeypatch):
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert r.status_code == 200
    assert 'id="fin"' in r.text and "hidden" in r.text
    assert "Siguiente: <strong>#2</strong>" in r.text
    assert "Leer el #2" in r.text


def test_tarjeta_final_falta_sin_legal_lleva_al_aviso(tmp_path, monkeypatch):
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "falta", legal=False)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert "Te falta el" in r.text and "#2" in r.text
    assert 'href="/ui/legal"' in r.text
    assert 'hx-post="/ui/leer/"' not in r.text


def test_anadir_a_deseos_reutiliza_wishlist(tmp_path):
    from zascarr.services.legal import require_legal_acknowledgment

    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue})
    app.dependency_overrides[require_legal_acknowledgment] = lambda: None
    try:
        with use_fake_session(db) as client:
            r = client.post(f"/ui/leer/{f.id}/deseo")
        assert r.status_code == 200 and "Añadido a Deseados" in r.text
        assert db.commit.await_count == 1
    finally:
        app.dependency_overrides.pop(require_legal_acknowledgment, None)


def test_deseo_sin_aviso_legal_da_403_y_no_escribe(tmp_path):
    f = _file(tmp_path)
    db = FakeSession(exec_queue=[FakeExecResult([])])
    with use_fake_session(db) as client:
        r = client.post(f"/ui/leer/{f.id}/deseo")
    assert r.status_code == 403
    assert r.headers["hx-redirect"] == "/ui/legal"
    assert db.commit.await_count == 0
