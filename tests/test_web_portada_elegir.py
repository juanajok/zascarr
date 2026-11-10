"""BL-INF6 (#592): panel «Elegir portada» (rutas web con FakeSession)."""
from __future__ import annotations

import re
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.web import series as web


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = (rowcount if rowcount is not None
                         else (len(rows) if hasattr(rows, "__len__") else 0))

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, queue: list, series=None):
        self._queue = list(queue)
        self._series = series
        self.flush = AsyncMock()

    async def execute(self, _statement):
        return self._queue.pop(0)

    async def get(self, _model, _id):
        return self._series


def _use(session):
    async def _db():
        yield session

    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)

    return _Ctx()


def _series(**extra) -> Series:
    serie = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                   metadata_={}, locked_fields=[], cover_url=None,
                   metadata_source="comic_vine")
    for clave, valor in extra.items():
        setattr(serie, clave, valor)
    return serie


def _covers(tmp_path, *, externa=False, serie=None, ancho=900):
    covers = tmp_path / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    if externa:
        ruta = covers / "externa" / f"{serie.id}.jpg"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (ancho, ancho * 2), (200, 30, 40)).save(ruta, "JPEG")
    return covers


def _cbz(ruta, *, ancho=900, color=(10, 90, 160)):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    Image.new("RGB", (ancho, ancho * 2), color).save(buffer, "JPEG")
    import zipfile
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", buffer.getvalue())
    return ruta


def _ajustes(tmp_path):
    return get_settings().model_copy(update={"covers_cache_path": tmp_path / "covers"})


def _panel_queue(numeros=(), archivos=()) -> list:
    return [FakeExecResult(list(numeros)), FakeExecResult(list(archivos))]


# ── GET del panel (perezoso) ─────────────────────────────────────────────────────────────────────

def test_la_ficha_no_pide_el_panel_ni_pinta_miniaturas_hasta_desplegarlo():
    from tests.test_web_series import (
        FakeExecResult as R,
    )
    from tests.test_web_series import (
        FakeSession as S,
    )
    from tests.test_web_series import (
        acuse,
        make_series,
        retirados,
        sin_otras,
        use_fake_session,
    )
    from zascarr.models import WishlistPolicy

    serie = make_series(total_issues=3)
    serie.wishlist_policy = WishlistPolicy.MISSING
    session = S([
        R([serie]), R([]), R([]), R([]), acuse(), *sin_otras(), retirados(), R([]),
    ])
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{serie.id}")

    assert r.status_code == 200
    assert f'hx-get="/ui/series/{serie.id}/portada/elegir"' in r.text
    assert 'hx-trigger="toggle once"' in r.text and 'id="elegir-portada"' in r.text
    assert "Elegir portada" in r.text
    # Nada de miniaturas en el HTML de la ficha: se piden al abrir el panel.
    assert "/previa.jpg" not in r.text
    assert 'loading="lazy"' not in r.text
    assert 'id="portada-serie"' in r.text
    assert f'/ui/series/{serie.id}/portada?v=2' in r.text


def test_el_panel_muestra_las_candidatas_con_su_origen(tmp_path, monkeypatch):
    serie = _series(cover_url="https://comicvine.gamespot.com/a/portada.jpg")
    _covers(tmp_path, externa=True, serie=serie)
    ajustes = _ajustes(tmp_path)
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    issue_id, file_id = uuid4(), uuid4()
    session = FakeSession(_panel_queue(
        numeros=[(issue_id, "3")],
        archivos=[(issue_id, file_id, f"/b/{serie.id}/3.cbz", None)],
    ), series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada/elegir")

    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    assert "Del archivo del nº 3" in r.text
    assert "De Comic Vine" in r.text
    assert "Usar esta portada" in r.text
    assert "Solo cambia la portada en ZascArr; no se escribe en los CBZ." in r.text
    assert "Cancelar" in r.text
    assert "Cargando" not in r.text
    # Miniaturas perezosas de BL-INF4 y de la externa cacheada.
    assert f'src="/ui/series/{serie.id}/numero/{issue_id}/previa.jpg"' in r.text
    assert f'src="/ui/series/{serie.id}/portada/externa.jpg"' in r.text
    assert r.text.count('loading="lazy"') == 3      # actual + número + externa
    assert f'action="/ui/series/{serie.id}/portada/elegir"' in r.text
    assert 'hx-post="/ui/series/' in r.text
    assert "covers<|>" not in r.text


def test_sin_candidatas_avisa_y_no_pinta_ninguna_imagen(tmp_path, monkeypatch):
    serie = _series(cover_url=None)
    covers = _covers(tmp_path)
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession(_panel_queue(), series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada/elegir")

    assert r.status_code == 200
    assert "No hay más portadas que elegir" in r.text
    assert "Usar esta portada" not in r.text
    # Ni imagen rota ni `<img>` de una portada que no existe.
    assert "<img" not in r.text


def test_la_version_de_la_portada_cambia_si_el_archivo_elegido_se_reemplaza(tmp_path, monkeypatch):
    serie = _series()
    ajustes = _ajustes(tmp_path)
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    file_id = uuid4()
    serie.metadata_ = {"portada": {"tipo": "archivo", "file_id": str(file_id),
                                   "fecha": "2026-11-10T10:00:00+00:00"}}

    def _panel(mtime: int) -> str:
        session = FakeSession(
            [FakeExecResult([]), FakeExecResult([(file_id, "/b/1.cbz", None, mtime)])],
            series=serie)
        with _use(session) as client:
            respuesta = client.get(f"/ui/series/{serie.id}/portada/elegir")
        assert respuesta.status_code == 200
        return re.search(r"portada\?v=([0-9a-f]+)", respuesta.text).group(1)

    assert _panel(1_000) != _panel(2_000)


# ── POST: elegir ────────────────────────────────────────────────────────────────────────────────

def _post_archivo(tmp_path, monkeypatch, *, cbz_ancho=900, roto=False):
    serie = _series()
    ajustes = _ajustes(tmp_path)
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    cbz = tmp_path / "Tebeo 01.cbz"
    if roto:
        cbz.write_bytes(b"no es un zip")
    else:
        _cbz(cbz, ancho=cbz_ancho)
    issue_id, file_id = uuid4(), uuid4()
    return serie, cbz, issue_id, file_id


def test_elegir_una_portada_de_archivo_la_persiste_y_regenera_la_cache(tmp_path, monkeypatch):
    serie, cbz, issue_id, file_id = _post_archivo(tmp_path, monkeypatch)
    session = FakeSession(
        [FakeExecResult([(file_id, str(cbz), None)])]        # archivos del número
        + _panel_queue(numeros=[(issue_id, "1")],            # panel repintado: lista de números
                       archivos=[(issue_id, file_id, str(cbz), None)])
        + [FakeExecResult([(file_id, str(cbz), None, 1)])],  # versión: el archivo elegido
        series=serie,
    )

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/elegir",
                        data={"tipo": "archivo", "issue_id": str(issue_id),
                              "file_id": str(file_id)})

    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    assert "Portada cambiada." in r.text
    assert "no se ha escrito, movido ni renombrado ningún archivo" in r.text
    eleccion = serie.metadata_["portada"]
    assert eleccion["tipo"] == "archivo" and eleccion["file_id"] == str(file_id)
    assert "fecha" in eleccion
    assert "cover_url" in serie.locked_fields
    v3 = tmp_path / "covers" / "v3" / f"{serie.id}.jpg"
    assert v3.is_file()
    with Image.open(v3) as img:
        assert img.width == 600          # 600 px, sin ampliar; el original era 900
    assert cbz.exists()                   # la biblioteca no se toca
    # La cabecera se refresca por OOB y el panel enseña la portada elegida.
    assert 'hx-swap-oob="true"' in r.text and 'id="portada-serie"' in r.text
    assert "Es la portada elegida." in r.text


def test_elegir_un_archivo_que_no_da_portada_no_cambia_nada(tmp_path, monkeypatch):
    serie, cbz, issue_id, file_id = _post_archivo(tmp_path, monkeypatch, roto=True)
    session = FakeSession(
        [FakeExecResult([(file_id, str(cbz), None)])] + _panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/elegir",
                        data={"tipo": "archivo", "issue_id": str(issue_id),
                              "file_id": str(file_id)})

    assert r.status_code == 200
    assert "No se ha podido sacar la portada de ese archivo" in r.text
    assert "portada" not in serie.metadata_
    assert "cover_url" not in serie.locked_fields
    assert not (tmp_path / "covers" / "v3" / f"{serie.id}.jpg").exists()


def test_elegir_un_archivo_que_ya_no_esta_avisa_sin_cambiar_nada(tmp_path, monkeypatch):
    serie = _series()
    ajustes = _ajustes(tmp_path)
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession([FakeExecResult([])] + _panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/elegir",
                        data={"tipo": "archivo", "issue_id": str(uuid4()),
                              "file_id": str(uuid4())})

    assert r.status_code == 200
    assert "Esa portada ya no está disponible" in r.text
    assert "portada" not in serie.metadata_


def test_elegir_un_archivo_con_identificadores_invalidos_no_cambia_nada(tmp_path, monkeypatch):
    serie = _series()
    ajustes = _ajustes(tmp_path)
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession(_panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/elegir",
                        data={"tipo": "archivo", "issue_id": "no", "file_id": "tampoco"})

    assert r.status_code == 200 and "Esa portada ya no está disponible" in r.text
    assert "portada" not in serie.metadata_


def test_elegir_la_portada_externa_cacheada(tmp_path, monkeypatch):
    serie = _series(cover_url="https://comicvine.gamespot.com/a/portada.jpg")
    covers = _covers(tmp_path, externa=True, serie=serie, ancho=400)
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession(_panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/elegir",
                        data={"tipo": "externa", "url": serie.cover_url})

    assert r.status_code == 200 and "Portada cambiada." in r.text
    eleccion = serie.metadata_["portada"]
    assert eleccion["tipo"] == "externa" and eleccion["url"] == serie.cover_url
    assert "cover_url" in serie.locked_fields
    assert "Es la portada elegida." in r.text
    # Sigue siendo un JPEG válido y no se amplía (Pillow no inventa píxeles).
    with Image.open(covers / "externa" / f"{serie.id}.jpg") as img:
        assert img.width == 400
    # La externa NO va a `covers/v3/`: esa clave es solo para portadas sacadas de un archivo.
    assert not (covers / "v3" / f"{serie.id}.jpg").exists()


def test_una_url_externa_manipulada_no_cambia_nada(tmp_path, monkeypatch):
    serie = _series(cover_url="https://comicvine.gamespot.com/a/portada.jpg")
    covers = _covers(tmp_path, externa=True, serie=serie)
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession(_panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/elegir",
                        data={"tipo": "externa", "url": "https://evil.example/x.jpg"})

    assert r.status_code == 200 and "Esa portada ya no está disponible" in r.text
    assert "portada" not in serie.metadata_


def test_la_portada_externa_se_sirve_como_miniatura_del_selector(tmp_path, monkeypatch):
    serie = _series()
    covers = _covers(tmp_path, externa=True, serie=serie)
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession([], series=serie)

    with _use(session) as client:
        ok = client.get(f"/ui/series/{serie.id}/portada/externa.jpg")
        falta = client.get(f"/ui/series/{uuid4()}/portada/externa.jpg")

    assert ok.status_code == 200 and ok.headers["content-type"].startswith("image/jpeg")
    assert ok.headers["Cache-Control"] == "private, max-age=86400"
    assert ok.headers["ETag"]
    assert falta.status_code == 404 and falta.headers["Cache-Control"] == "no-store"


def test_ver_mas_numeros_devuelve_la_siguiente_tanda(tmp_path, monkeypatch):
    serie = _series()
    covers = _covers(tmp_path)
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    issue_id, file_id = uuid4(), uuid4()
    session = FakeSession(
        [FakeExecResult([(issue_id, "13")]),
         FakeExecResult([(issue_id, file_id, "/b/13.cbz", None)])],
        series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada/candidatas", params={"desde": 12})

    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    assert "portada-candidatas-mas" in r.text
    assert "Del archivo del nº 13" in r.text
    assert "Ver más números" not in r.text        # no hay más: el botón desaparece


def test_volver_a_la_portada_automatica_borra_la_eleccion_y_la_v3(tmp_path, monkeypatch):
    serie = _series()
    covers = _covers(tmp_path)
    v3 = covers / "v3" / f"{serie.id}.jpg"
    v3.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (600, 900), (1, 2, 3)).save(v3, "JPEG")
    file_id = uuid4()
    serie.metadata_ = {"portada": {"tipo": "archivo", "file_id": str(file_id),
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    serie.locked_fields = ["cover_url"]
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    issue_id = uuid4()
    session = FakeSession(
        _panel_queue(numeros=[(issue_id, "1")],
                     archivos=[(issue_id, uuid4(), "/b/1.cbz", None)]),
        series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/quitar")

    assert r.status_code == 200
    assert "Portada automática otra vez" in r.text
    assert "portada" not in serie.metadata_
    assert "cover_url" not in serie.locked_fields
    assert not v3.exists()
    # La cabecera vuelve al separador de siempre.
    assert f'/ui/series/{serie.id}/portada?v=2' in r.text


def test_volver_a_la_automatica_tras_elegir_la_externa_conserva_la_v3(tmp_path, monkeypatch):
    serie = _series(cover_url="https://comicvine.gamespot.com/a/portada.jpg")
    covers = _covers(tmp_path, externa=True, serie=serie)
    v3 = covers / "v3" / f"{serie.id}.jpg"
    v3.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (600, 900), (1, 2, 3)).save(v3, "JPEG")
    serie.metadata_ = {"portada": {"tipo": "externa", "url": serie.cover_url,
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    serie.locked_fields = ["cover_url"]
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession(_panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/quitar")

    assert r.status_code == 200 and "Portada automática otra vez" in r.text
    assert "portada" not in serie.metadata_
    assert v3.exists()          # la v3 no la creó la elección externa: no se toca


def test_quitar_sin_eleccion_lo_dice_y_no_cambia_nada(tmp_path, monkeypatch):
    serie = _series()
    covers = _covers(tmp_path)
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.portada_serie.get_settings", lambda: ajustes)
    session = FakeSession(_panel_queue(), series=serie)

    with _use(session) as client:
        r = client.post(f"/ui/series/{serie.id}/portada/quitar")

    assert r.status_code == 200
    assert "No hay una portada elegida a mano que quitar" in r.text
    assert serie.metadata_ == {} and serie.locked_fields == []


# ── Cascada: la elección manda (prioridad 0) ───────────────────────────────────────────────────

def test_la_eleccion_externa_gana_a_la_previa_con_ancho_suficiente(tmp_path, monkeypatch):
    """#435 sirve la «previa ≥ 300 px» antes de la `v3`; la elección manual va antes que todo."""
    serie = _series(cover_url="https://comicvine.gamespot.com/a/portada.jpg")
    covers = _covers(tmp_path, externa=True, serie=serie)
    anterior = covers / f"{serie.id}.jpg"
    Image.new("RGB", (400, 600), (0, 255, 0)).save(anterior, "JPEG")
    serie.metadata_ = {"portada": {"tipo": "externa", "url": serie.cover_url,
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession([], series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada")

    esperado = (covers / "externa" / f"{serie.id}.jpg").read_bytes()
    assert r.status_code == 200 and r.content == esperado


def test_la_eleccion_de_archivo_sirve_la_v3_sin_volver_a_extraer(tmp_path, monkeypatch):
    serie = _series()
    covers = _covers(tmp_path)
    v3 = covers / "v3" / f"{serie.id}.jpg"
    v3.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (600, 900), (1, 2, 3)).save(v3, "JPEG")
    file_id = uuid4()
    serie.metadata_ = {"portada": {"tipo": "archivo", "file_id": str(file_id),
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession(
        [FakeExecResult([(file_id, "/b/1.cbz", None, v3.stat().st_mtime_ns - 10)])],
        series=serie)

    def _no_debe_extraer(*_a, **_k):
        raise AssertionError("la caché está al día: no se vuelve a abrir el archivo")

    with patch.object(web, "_primera_portada", _no_debe_extraer), _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada")

    assert r.status_code == 200 and r.content == v3.read_bytes()


def test_la_eleccion_de_archivo_se_rematerializa_si_el_archivo_cambio(tmp_path, monkeypatch):
    """La elección es una REFERENCIA: si el CBZ se reemplaza, la portada se vuelve a sacar."""
    serie = _series()
    covers = _covers(tmp_path)
    v3 = covers / "v3" / f"{serie.id}.jpg"
    v3.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (600, 900), (9, 9, 9)).save(v3, "JPEG")
    antes = v3.read_bytes()
    cbz = _cbz(tmp_path / "nuevo.cbz", ancho=900, color=(200, 30, 40))
    file_id = uuid4()
    serie.metadata_ = {"portada": {"tipo": "archivo", "file_id": str(file_id),
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession(
        [FakeExecResult([(file_id, str(cbz), None, v3.stat().st_mtime_ns + 10_000)])],
        series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada")

    assert r.status_code == 200
    with Image.open(BytesIO(r.content)) as img:
        assert img.width == 600
    assert r.content != antes                    # se materializó de nuevo desde el CBZ


def test_si_el_archivo_elegido_desaparecio_cae_a_la_cascada(tmp_path, monkeypatch):
    serie = _series(cover_url=None)
    covers = _covers(tmp_path)
    file_id = uuid4()
    serie.metadata_ = {"portada": {"tipo": "archivo", "file_id": str(file_id),
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession(
        [FakeExecResult([]),                       # archivo_de_portada: ya no está
         FakeExecResult([])],                      # cascada: no hay archivos
        series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada")

    assert r.status_code == 404
    assert serie.metadata_["portada"]["file_id"] == str(file_id)   # la elección se conserva


def test_la_eleccion_externa_sin_cache_cae_a_la_cascada(tmp_path, monkeypatch):
    serie = _series(cover_url="https://comicvine.gamespot.com/a/portada.jpg")
    covers = _covers(tmp_path)
    serie.metadata_ = {"portada": {"tipo": "externa", "url": serie.cover_url,
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession([FakeExecResult([])], series=serie)

    async def _sin_red(*_a, **_k):
        return False

    with patch.object(web, "fetch_and_cache_cover", _sin_red), _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada")

    assert r.status_code == 404
    assert serie.metadata_["portada"]["tipo"] == "externa"          # no se borra


def test_una_eleccion_con_metadatos_invalidos_se_ignora(tmp_path, monkeypatch):
    serie = _series(cover_url=None)
    covers = _covers(tmp_path)
    serie.metadata_ = {"portada": {"tipo": "archivo", "file_id": "no-uuid",
                                   "fecha": "2026-11-10T10:00:00+00:00"}}
    ajustes = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: ajustes)
    session = FakeSession([FakeExecResult([])], series=serie)

    with _use(session) as client:
        r = client.get(f"/ui/series/{serie.id}/portada")

    assert r.status_code == 404
