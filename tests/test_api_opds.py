# ruff: noqa: E501
"""#160 BL-C5: catálogo OPDS de solo catálogo (TestClient, sin PG)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.services import auth as auth_mod
from zascarr.services.auth import hash_password

ATOM = "{http://www.w3.org/2005/Atom}"
TIPO = "application/atom+xml;profile=opds-catalog;kind=navigation"


class R:
    def __init__(self, *, scalar=None, rows=None, escalares=None, uno=None):
        self._scalar = scalar
        self._rows = rows
        self._escalares = escalares
        self._uno = uno

    def scalar(self):
        return self._scalar

    def all(self):
        return self._rows or []

    def scalars(self):
        return SimpleNamespace(all=lambda: self._escalares or [])


class FakeSession:
    def __init__(self, queue):
        self.queue = list(queue)
        self.gets = {}

    async def execute(self, _statement):
        return self.queue.pop(0) if self.queue else R(scalar=None)

    async def get(self, _modelo, clave):
        return self.gets.get(clave)


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            async def _get_db():
                yield session
            app.dependency_overrides[get_db] = _get_db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


@pytest.fixture(autouse=True)
def _auth_none(monkeypatch):
    settings = get_settings().model_copy(update={"auth_mode": "none"})
    monkeypatch.setattr(auth_mod, "get_settings", lambda: settings)


def _serie(titulo="Batman & Robin <X>", **extra):
    s = Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN,
               description='Guion con & < > " \' y más', updated_at=datetime(2026, 1, 2, tzinfo=UTC))
    for k, v in extra.items():
        setattr(s, k, v)
    return s


def _parse(resp):
    return ET.fromstring(resp.content)


def test_raiz_es_feed_de_navegacion_valido():
    with use_fake_session(FakeSession([R(scalar=datetime(2026, 1, 2, tzinfo=UTC))])) as c:
        r = c.get("/opds")
    assert r.status_code == 200
    assert r.headers["content-type"] == TIPO
    feed = _parse(r)
    assert feed.tag == ATOM + "feed"
    titulos = [e.findtext(ATOM + "title") for e in feed.findall(ATOM + "entry")]
    assert titulos == ["Todas las series", "Por tradición", "Por editorial"]
    assert not any("acquisition" in (enlace.get("rel") or "") or "download" in (enlace.get("rel") or "")
                   for enlace in feed.iter(ATOM + "link"))


def test_series_paginadas_escapado_autores_y_sin_descargas():
    s = _serie()
    with use_fake_session(FakeSession([
        R(scalar=datetime(2026, 1, 2, tzinfo=UTC)),
        R(scalar=1),
        R(rows=[(s, 0, 0)]),
        R(rows=[(s.id, "Guionista & Cía")]),
    ])) as c:
        r = c.get("/opds/series?page=1")
    assert r.status_code == 200
    assert "Batman &amp; Robin &lt;X&gt;" in r.text
    feed = _parse(r)
    entrada = feed.find(ATOM + "entry")
    assert entrada.findtext(ATOM + "title") == "Batman & Robin <X>"
    assert entrada.findtext(f"{ATOM}author/{ATOM}name") == "Guionista & Cía"
    assert any(enlace.get("rel") == "alternate" and enlace.get("href", "").startswith("/ui/series/")
               for enlace in entrada.findall(ATOM + "link"))
    assert not any("acquisition" in (enlace.get("rel") or "") or "download" in (enlace.get("rel") or "")
                   for enlace in feed.iter(ATOM + "link"))
    assert ".cbz" not in r.text and "/media/" not in r.text and "sha256" not in r.text


def test_series_paginacion_links_y_out_of_range():
    with use_fake_session(FakeSession([
        R(scalar=datetime(2026, 1, 2, tzinfo=UTC)), R(scalar=120), R(rows=[]),
    ])) as c:
        r = c.get("/opds/series?page=99")
    assert r.status_code == 200
    feed = _parse(r)
    assert feed.find(ATOM + "entry") is None
    links = {enlace.get("rel"): enlace.get("href") for enlace in feed.findall(ATOM + "link")}
    assert links["previous"].startswith("/opds/series?page=98")


def test_detalle_serie_con_y_sin_numeros():
    s = _serie("Serie")
    # Rehacemos con la sesión del contexto para inyectar el get.
    session = FakeSession([R(escalares=[])])
    session.gets[s.id] = s
    with use_fake_session(session) as c:
        r = c.get(f"/opds/series/{s.id}")
    assert r.status_code == 200
    feed = _parse(r)
    assert feed.findtext(ATOM + "title") == "Serie"
    assert feed.find(ATOM + "entry") is None
    issue = SimpleNamespace(id=uuid4(), issue_number="1", title=None, updated_at=None,
                            synopsis=None, release_date=None)
    session = FakeSession([R(escalares=[issue])])
    session.gets[s.id] = s
    with use_fake_session(session) as c:
        r = c.get(f"/opds/series/{s.id}")
    assert r.status_code == 200
    assert "#1" in r.text


def test_tradiciones_y_editoriales():
    with use_fake_session(FakeSession([
        R(escalares=[ComicTradition.AMERICAN]), R(scalar=datetime(2026, 1, 2, tzinfo=UTC)),
    ])) as c:
        r = c.get("/opds/tradiciones")
    assert r.status_code == 200
    assert "Grapa americana" in r.text
    pid = uuid4()
    with use_fake_session(FakeSession([
        R(rows=[(pid, "Editorial & Cía")]), R(scalar=datetime(2026, 1, 2, tzinfo=UTC)),
    ])) as c:
        r = c.get("/opds/editoriales")
    assert r.status_code == 200
    assert "Editorial &amp; Cía" in r.text
    assert "publisher_id=" in r.text


def test_etag_y_304():
    with use_fake_session(FakeSession([
        R(scalar=datetime(2026, 1, 2, tzinfo=UTC)), R(scalar=1), R(rows=[]),
    ])) as c:
        r = c.get("/opds/series")
    etag = r.headers["etag"]
    assert r.headers["cache-control"] == "private, max-age=300"
    with use_fake_session(FakeSession([
        R(scalar=datetime(2026, 1, 2, tzinfo=UTC)), R(scalar=1), R(rows=[]),
    ])) as c:
        r2 = c.get("/opds/series", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.content == b""


def test_404_xml():
    with use_fake_session(FakeSession([])) as c:
        r = c.get("/opds/series/no-es-uuid")
    assert r.status_code == 404
    assert "application/xml" in r.headers["content-type"]
    assert "<error" in r.text


def test_auth_basic_401_y_200_sin_redireccion(monkeypatch):
    settings = get_settings().model_copy(update={
        "auth_mode": "password", "auth_password_hash": hash_password("secreta"),
        "secret_key": "s", "auth_session_version": 0,
    })
    monkeypatch.setattr(auth_mod, "get_settings", lambda: settings)
    with use_fake_session(FakeSession([R(scalar=datetime(2026, 1, 2, tzinfo=UTC))])) as c:
        r = c.get("/opds", follow_redirects=False)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == 'Basic realm="ZascArr"'
    assert r.headers["cache-control"] == "no-store"
    assert "location" not in r.headers
    with use_fake_session(FakeSession([R(scalar=datetime(2026, 1, 2, tzinfo=UTC))])) as c:
        r = c.get("/opds", auth=("", "secreta"))
    assert r.status_code == 200


def test_auth_basic_mala_401(monkeypatch):
    settings = get_settings().model_copy(update={
        "auth_mode": "password", "auth_password_hash": hash_password("secreta"),
        "secret_key": "s2", "auth_session_version": 0,
    })
    monkeypatch.setattr(auth_mod, "get_settings", lambda: settings)
    with use_fake_session(FakeSession([])) as c:
        r = c.get("/opds", auth=("", "mala"), follow_redirects=False)
    assert r.status_code == 401
    assert "location" not in r.headers
