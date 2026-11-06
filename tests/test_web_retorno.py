"""BL-IT03 (#286): URL de retorno local, validada y sin historial paralelo."""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

import pytest

from zascarr.web.retorno import url_de_ficha, volver_segura


def test_la_url_de_la_ficha_lleva_la_biblioteca_y_el_ancla():
    sid = uuid4()
    url = url_de_ficha(sid, "/ui/biblioteca?q=thorgal&page=2")
    assert url.startswith(f"/ui/series/{sid}?volver=")
    destino = unquote(urlsplit(url).query.removeprefix("volver="))
    partes = urlsplit(destino)
    assert partes.path == "/ui/biblioteca"
    assert parse_qs(partes.query) == {"q": ["thorgal"], "page": ["2"]}
    assert partes.fragment == f"serie-{sid}"


@pytest.mark.parametrize("valor", [
    "https://evil.example/ui/biblioteca",
    "//evil.example/ui/biblioteca",
    "javascript:alert(1)",
    "/ui/biblioteca/../admin",
    "/ui/series/123",
    "/ui/biblioteca?q=x&desconocido=1",
    "/ui/biblioteca?q=x#otro",
    "/ui/biblioteca?q=x#serie-no-es-uuid",
    "/ui/biblioteca?q=\x00",
])
def test_volver_rechaza_destinos_no_contratados(valor):
    assert volver_segura(valor) is None


def test_volver_acepta_el_contrato_de_la_biblioteca():
    valor = "/ui/biblioteca?q=thorgal&tradition=manga&page=2#serie-" + str(uuid4())
    assert volver_segura(valor) == valor


def test_volver_sin_fragmento_tambien_vale():
    assert volver_segura("/ui/biblioteca?page=1") == "/ui/biblioteca?page=1"


def test_volver_de_mas_de_2000_caracteres_se_rechaza():
    assert volver_segura("/ui/biblioteca?q=" + "x" * 1990) is None


def test_el_ancla_debe_ser_la_de_esta_ficha():
    sid, otra = uuid4(), uuid4()
    assert volver_segura(f"/ui/biblioteca?page=1#serie-{sid}", sid) is not None
    assert volver_segura(f"/ui/biblioteca?page=1#serie-{otra}", sid) is None


def test_volver_acepta_la_vista_lista():
    sid = uuid4()
    valor = f"/ui/biblioteca?vista=lista&page=2#serie-{sid}"
    assert volver_segura(valor, sid) == valor
