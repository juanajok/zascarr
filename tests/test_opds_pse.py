"""BL-LEC5 (#828): lectura por páginas desde OPDS-PSE (archivos sintéticos en `tmp_path`)."""
from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.test_pendientes import FakeExecResult, FakeSession, use_fake_session
from zascarr.config import get_settings
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series
from zascarr.services import auth as auth_mod
from zascarr.services import lector

ATOM = "{http://www.w3.org/2005/Atom}"
PSE = "{http://vaemendis.net/opds-pse/ns}"
REL = "http://vaemendis.net/opds-pse/stream"


@pytest.fixture(autouse=True)
def _auth_none(monkeypatch):
    ajustes = get_settings().model_copy(update={"auth_mode": "none"})
    monkeypatch.setattr(auth_mod, "get_settings", lambda: ajustes)


def _imagen(formato: str, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buf, format=formato)
    return buf.getvalue()


def _cbz(ruta, entradas: dict[str, bytes]):
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, datos in entradas.items():
            z.writestr(nombre, datos)
    return ruta


def _file(ruta, issue_id=None, **extra):
    return File(id=uuid4(), issue_id=issue_id or uuid4(), file_path=str(ruta),
                file_name=ruta.name, file_format=FileFormat.CBZ, metadata_={}, **extra)


# ── La numeración, en un solo sitio ──────────────────────────────────────────────────────
def test_conversion_de_numeracion_pse_a_lector():
    """OPDS-PSE 1.0 numera de 0 a N-1; el lector, de 1 a N."""
    assert lector.pagina_pse_a_lector(0) == 1
    assert lector.pagina_pse_a_lector(4) == 5


def test_ultima_leida_pse_omite_sin_empezar():
    assert lector.ultima_leida_pse(None) is None
    assert lector.ultima_leida_pse(0) is None
    assert lector.ultima_leida_pse(7) == 7


# ── Qué números anuncian PSE ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_numero_con_jpeg_anuncia_streaming_con_cuenta_y_ultima_leida(tmp_path):
    ruta = _cbz(tmp_path / "a.cbz", {"1.jpg": _imagen("JPEG"), "2.jpg": _imagen("JPEG")})
    f = _file(ruta)
    progreso = SimpleNamespace(issue_id=f.issue_id, file_id=None, current_page=2)
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([progreso])])
    res = await lector.streaming_de_numeros(db, [f.issue_id])
    assert res[f.issue_id] == lector.Streaming(str(f.id), 2, "image/jpeg", 2)


@pytest.mark.asyncio
async def test_numero_con_webp_no_anuncia_streaming(tmp_path):
    ruta = _cbz(tmp_path / "w.cbz", {"1.webp": _imagen("WEBP"), "2.webp": _imagen("WEBP")})
    f = _file(ruta)
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert await lector.streaming_de_numeros(db, [f.issue_id]) == {}


@pytest.mark.asyncio
async def test_paginas_mezcladas_con_webp_no_anuncian(tmp_path):
    """Basta una página que no sea JPEG/PNG/GIF para que no se anuncie (no se recodifica)."""
    ruta = _cbz(tmp_path / "m.cbz", {"1.jpg": _imagen("JPEG"), "2.webp": _imagen("WEBP")})
    f = _file(ruta)
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert await lector.streaming_de_numeros(db, [f.issue_id]) == {}


@pytest.mark.asyncio
async def test_rar_sin_cache_lista_no_se_anuncia_y_no_se_prepara(tmp_path, monkeypatch):
    """Anunciar un RAR sin preparar obligaría a esperar en la primera página."""
    ruta = tmp_path / "r.cbr"
    ruta.write_bytes(b"Rar!\x1a\x07\x00" + b"\0" * 600)
    f = File(id=uuid4(), issue_id=uuid4(), file_path=str(ruta), file_name="r.cbr",
             file_format=FileFormat.CBR, metadata_={"formato_contenido": {"firma": "rar"}})
    monkeypatch.setattr(lector, "_es_legible", lambda _f: True)
    preparar = []
    monkeypatch.setattr(lector.CACHE, "preparar", lambda *_a: preparar.append(1))
    monkeypatch.setattr(lector.CACHE, "_paginas", lambda _f: [])
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert await lector.streaming_de_numeros(db, [f.issue_id]) == {}
    assert preparar == []


@pytest.mark.asyncio
async def test_varios_archivos_usan_la_regla_de_lec1(tmp_path):
    """Un solo archivo por número: el último leído, si no el primero por nombre."""
    issue_id = uuid4()
    a = _file(_cbz(tmp_path / "a.cbz", {"1.jpg": _imagen("JPEG")}), issue_id)
    b = _file(_cbz(tmp_path / "b.cbz", {"1.jpg": _imagen("JPEG"), "2.jpg": _imagen("JPEG")}),
              issue_id)
    sin = FakeSession(exec_queue=[FakeExecResult([a, b]), FakeExecResult([])])
    assert (await lector.streaming_de_numeros(sin, [issue_id]))[issue_id].file_id == str(a.id)
    prog = SimpleNamespace(issue_id=issue_id, file_id=b.id, current_page=1)
    con = FakeSession(exec_queue=[FakeExecResult([a, b]), FakeExecResult([prog])])
    elegido = (await lector.streaming_de_numeros(con, [issue_id]))[issue_id]
    assert elegido.file_id == str(b.id) and elegido.count == 2


# ── El feed y el endpoint de páginas ─────────────────────────────────────────────────────
def _feed_con(tmp_path, *, current_page=None):
    serie = Series(id=uuid4(), title="Serie", tradition=ComicTradition.AMERICAN,
                   updated_at=datetime(2026, 1, 2, tzinfo=UTC))
    issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1",
                  updated_at=datetime(2026, 1, 2, tzinfo=UTC))
    f = _file(_cbz(tmp_path / "x.cbz", {"1.jpg": _imagen("JPEG"), "2.jpg": _imagen("JPEG"),
                                        "3.jpg": _imagen("JPEG")}), issue.id)
    progreso = ([SimpleNamespace(issue_id=issue.id, file_id=None, current_page=current_page)]
                if current_page is not None else [])
    cola = [FakeExecResult([issue]), FakeExecResult([f]), FakeExecResult(progreso)]
    db = FakeSession(exec_queue=cola, get_map={(Series, serie.id): serie})
    with use_fake_session(db) as c:
        return c.get(f"/opds/series/{serie.id}"), f


def test_el_feed_lleva_enlace_pse_sin_rutas_ni_descargas(tmp_path):
    r, f = _feed_con(tmp_path)
    assert r.status_code == 200
    feed = ET.fromstring(r.content)
    pse = [e for e in feed.iter(ATOM + "link") if e.get("rel") == REL]
    assert len(pse) == 1
    assert pse[0].get("href") == f"/opds/paginas/{f.id}/{{pageNumber}}"
    assert pse[0].get("type") == "image/jpeg"
    assert pse[0].get(PSE + "count") == "3"
    assert pse[0].get(PSE + "lastRead") is None  # sin empezar → se omite
    assert "xmlns:pse=\"http://vaemendis.net/opds-pse/ns\"" in r.text
    assert str(tmp_path) not in r.text and ".cbz" not in r.text
    assert not any("acquisition" in (e.get("rel") or "") for e in feed.iter(ATOM + "link"))


def test_el_feed_lleva_la_ultima_leida(tmp_path):
    r, _f = _feed_con(tmp_path, current_page=2)
    pse = [e for e in ET.fromstring(r.content).iter(ATOM + "link") if e.get("rel") == REL]
    assert pse[0].get(PSE + "lastRead") == "2"


def test_pagina_opds_es_cero_basada_y_devuelve_los_mismos_bytes_y_etag_que_ui(tmp_path):
    f = _file(_cbz(tmp_path / "p.cbz", {
        "1.jpg": _imagen("JPEG", (10, 10, 10)), "2.jpg": _imagen("JPEG", (200, 10, 10))}))
    db = FakeSession(get_map={(File, f.id): f})
    with use_fake_session(db) as c:
        opds0 = c.get(f"/opds/paginas/{f.id}/0")
        opds1 = c.get(f"/opds/paginas/{f.id}/1")
        ui1 = c.get(f"/ui/leer/{f.id}/pagina/1")
        ui2 = c.get(f"/ui/leer/{f.id}/pagina/2")
    assert opds0.status_code == 200 and opds0.content == ui1.content
    assert opds1.content == ui2.content
    assert opds0.headers["etag"] == ui1.headers["etag"]
    assert opds0.headers["cache-control"].startswith("private")
    assert opds0.headers["content-type"] == "image/jpeg"


def test_pagina_opds_fuera_de_rango_negativa_y_no_numerica_dan_404(tmp_path):
    f = _file(_cbz(tmp_path / "p.cbz", {"1.jpg": _imagen("JPEG")}))
    db = FakeSession(get_map={(File, f.id): f})
    with use_fake_session(db) as c:
        assert c.get(f"/opds/paginas/{f.id}/1").status_code == 404   # solo existe la 0
        assert c.get(f"/opds/paginas/{f.id}/-1").status_code == 404
        assert c.get(f"/opds/paginas/{f.id}/x").status_code == 404
        assert c.get("/opds/paginas/no-es-uuid/0").status_code == 404


def test_pagina_opds_de_archivo_inexistente_o_sin_numero_da_404(tmp_path):
    suelto = File(id=uuid4(), issue_id=None, file_path=str(tmp_path / "s.cbz"),
                  file_name="s.cbz", file_format=FileFormat.CBZ, metadata_={})
    db = FakeSession(get_map={(File, suelto.id): suelto})
    with use_fake_session(db) as c:
        assert c.get(f"/opds/paginas/{suelto.id}/0").status_code == 404
        assert c.get(f"/opds/paginas/{uuid4()}/0").status_code == 404


def test_pagina_opds_webp_no_se_sirve_sin_recodificar(tmp_path):
    f = _file(_cbz(tmp_path / "w.cbz", {"1.webp": _imagen("WEBP")}))
    db = FakeSession(get_map={(File, f.id): f})
    with use_fake_session(db) as c:
        assert c.get(f"/opds/paginas/{f.id}/0").status_code == 404


def test_pagina_opds_sin_credenciales_da_401(tmp_path, monkeypatch):
    """Con contraseña activa, la ruta de páginas cuelga de `/opds` y exige la Basic."""
    from zascarr.services.auth import hash_password
    ajustes = get_settings().model_copy(update={
        "auth_mode": "password", "auth_password_hash": hash_password("pw"),
        "secret_key": "s", "auth_session_version": 0})
    monkeypatch.setattr(auth_mod, "get_settings", lambda: ajustes)
    from zascarr.main import app
    r = TestClient(app).get(f"/opds/paginas/{uuid4()}/0", follow_redirects=False)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == 'Basic realm="ZascArr"'
    assert "location" not in r.headers


def test_pagina_opds_solo_acepta_la_forma_canonica_de_la_url(tmp_path):
    """N-1 de SecOps: una página, una URL (sin espacios, signos, ceros ni dígitos Unicode)."""
    f = _file(_cbz(tmp_path / "c.cbz", {"1.jpg": _imagen("JPEG")}))
    db = FakeSession(get_map={(File, f.id): f})
    with use_fake_session(db) as c:
        assert c.get(f"/opds/paginas/{f.id}/0").status_code == 200
        for malo in ("00", "+0", "%200", "٠", "0%20"):
            assert c.get(f"/opds/paginas/{f.id}/{malo}").status_code == 404, malo
        assert c.get(f"/opds/paginas/{str(f.id).upper()}/0").status_code == 404
        assert c.get(f"/opds/paginas/{str(f.id).replace('-', '')}/0").status_code == 404


@pytest.mark.asyncio
async def test_la_medida_de_un_zip_se_reutiliza_y_se_invalida_al_cambiar(tmp_path, monkeypatch):
    """N-3: el segundo feed no vuelve a abrir el ZIP; si el archivo cambia, se mide de nuevo."""
    lector._MEDIDAS.clear()
    ruta = _cbz(tmp_path / "k.cbz", {"1.jpg": _imagen("JPEG")})
    f = _file(ruta)
    llamadas = []
    original = lector._listado
    monkeypatch.setattr(lector, "_listado", lambda p: llamadas.append(p) or original(p))
    for _ in range(2):
        db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
        assert (await lector.streaming_de_numeros(db, [f.issue_id]))[f.issue_id].count == 1
    assert len(llamadas) == 1
    _cbz(ruta, {"1.jpg": _imagen("JPEG"), "2.jpg": _imagen("JPEG")})
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert (await lector.streaming_de_numeros(db, [f.issue_id]))[f.issue_id].count == 2
    assert len(llamadas) == 2


@pytest.mark.asyncio
async def test_el_feed_mide_un_tope_de_archivos_nuevos_por_peticion(tmp_path, monkeypatch):
    lector._MEDIDAS.clear()
    monkeypatch.setattr(lector, "MAX_MEDIDAS_NUEVAS", 2)
    archivos = [_file(_cbz(tmp_path / f"{i}.cbz", {"1.jpg": _imagen("JPEG")})) for i in range(5)]
    ids = [f.issue_id for f in archivos]
    total: dict = {}
    for ronda in range(3):
        db = FakeSession(exec_queue=[FakeExecResult(archivos), FakeExecResult([])])
        res = await lector.streaming_de_numeros(db, ids)
        assert len(res) == min(5, 2 * (ronda + 1))   # 2, 4, 5: se completa con las peticiones
        total = res
    assert len(total) == 5


@pytest.mark.asyncio
async def test_un_error_de_disco_pasajero_no_se_memoriza_como_sin_streaming(tmp_path, monkeypatch):
    """N-4: un OSError transitorio (USB ocupado) no deja el número sin anunciar hasta que cambie."""
    lector._MEDIDAS.clear()
    f = _file(_cbz(tmp_path / "t.cbz", {"1.jpg": _imagen("JPEG")}))
    original = lector._listado

    def _falla(p):
        raise lector.ArchivoNoLegibleError("No se pudo leer el archivo.") from OSError("ocupado")

    monkeypatch.setattr(lector, "_listado", _falla)
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert await lector.streaming_de_numeros(db, [f.issue_id]) == {}
    assert not lector._MEDIDAS
    monkeypatch.setattr(lector, "_listado", original)
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert (await lector.streaming_de_numeros(db, [f.issue_id]))[f.issue_id].count == 1


@pytest.mark.asyncio
async def test_un_zip_danado_si_se_memoriza_como_sin_streaming(tmp_path):
    lector._MEDIDAS.clear()
    ruta = tmp_path / "roto.cbz"
    ruta.write_bytes(b"PK\x03\x04 no es un zip")
    f = _file(ruta)
    db = FakeSession(exec_queue=[FakeExecResult([f]), FakeExecResult([])])
    assert await lector.streaming_de_numeros(db, [f.issue_id]) == {}
    assert list(lector._MEDIDAS.values()) == [None]


def test_el_vaciado_concurrente_de_la_memoria_no_da_keyerror(tmp_path, monkeypatch):
    """N-5: la memoria se lee con una sola operación (`.get`), no comprobando y luego indexando."""
    lector._MEDIDAS.clear()
    f = _file(_cbz(tmp_path / "c.cbz", {"1.jpg": _imagen("JPEG")}))
    st = f.file_path
    lector._medir_todos({f.issue_id: f})

    class Vaciada(dict):
        def __contains__(self, k):
            r = super().__contains__(k)
            self.clear()
            return r

    monkeypatch.setattr(lector, "_MEDIDAS", Vaciada(lector._MEDIDAS))
    assert lector._medir_todos({f.issue_id: f})[f.issue_id][0] == 1
    assert st
