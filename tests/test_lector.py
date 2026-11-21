"""Lector CBZ (BL-LEC1): servicio de páginas, progreso y pantalla."""
from __future__ import annotations

import io
import re
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from tests.test_pendientes import FakeExecResult, FakeSession, use_fake_session
from zascarr.core.importer_triage import parse_comic_info
from zascarr.main import app
from zascarr.models import File, FileFormat, Issue, ReadingStatus, Series
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


def test_el_lector_usa_el_cascaron_inmersivo():
    from pathlib import Path
    plantilla = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "web"
                 / "templates" / "lector.html").read_text(encoding="utf-8")
    for pieza in (
        'class="lector lector-escena',
        'id="lector-barra"',
        'class="lector-flecha lector-flecha-anterior"',
        'class="lector-flecha lector-flecha-siguiente"',
        'Ver el final',
        'Página anterior',
        'id="lector-menu-boton"',
        'href="/legal"',
        '<kbd>h</kbd>',
        'id="lector-brillo"',
        'id="lector-contraste"',
        'id="lector-sepia"',
        'id="lector-invertir"',
        'id="lector-imagen-reset"',
    ):
        assert pieza in plantilla, pieza

def test_opciones_lleva_su_propio_cierre_fijo_dentro_del_panel():
    """#1118: con el panel más alto que la pantalla, «Opciones» sale de la vista al desplazarlo;
    el cierre vive dentro del panel, en una cabecera fija, y los botones de modo se piden acotados
    (la raíz también lleva data-modo y cerraba Opciones al abrirla)."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1] / "src" / "zascarr"
    plantilla = (raiz / "web" / "templates" / "lector.html").read_text(encoding="utf-8")
    menu = plantilla.split('id="lector-menu"', 1)[1].split("</header>", 1)[0]
    assert 'id="lector-menu-cerrar"' in menu and "lector-menu-cabecera" in menu
    css = (raiz / "static" / "web.css").read_text(encoding="utf-8")
    cabecera = css.split(".lector-menu-cabecera {", 1)[1].split("}", 1)[0]
    assert "position: sticky" in cabecera and "top: 0" in cabecera
    js = (raiz / "static" / "lector.js").read_text(encoding="utf-8")
    assert 'querySelectorAll("[data-modo]")' not in js
    assert js.count("querySelectorAll(BOTONES_MODO)") == 2


def _cuerpo_de_regla(css: str, selector: str) -> str:
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert m, f"no existe la regla {selector}"
    return " ".join(m.group(1).split())


def test_la_pagina_de_fin_ocupa_la_escena_y_no_es_una_tarjeta():
    """BL-LEC3 decisión D: `#fin` es una página (inset, z-index, overflow), no una tarjeta abajo."""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static"
           / "web.css").read_text(encoding="utf-8")
    cuerpo = _cuerpo_de_regla(css, ".lector-fin")
    assert "position: absolute" in cuerpo
    assert "inset: 0" in cuerpo
    assert "z-index: 3" in cuerpo
    assert "overflow:" in cuerpo
    assert "background: var(--paper)" in cuerpo
    assert "bottom:" not in cuerpo and "translateX" not in cuerpo
    assert "top: 50%" not in cuerpo
    # La imagen y las flechas de la página se ocultan de verdad (display propio vence a [hidden]).
    assert ".lector-lienzo[hidden]" in css


def test_el_css_del_lector_oculta_el_marco_y_las_flechas_en_tactil():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static"
           / "web.css").read_text(encoding="utf-8")
    for pieza in (
        "body:has(.lector-escena) .side",
        'data-chrome="oculto"',
        "@media (hover: none)",
        "lector-flecha",
        "100dvh",
    ):
        assert pieza in css, pieza

def test_el_chrome_no_se_oculta_con_el_foco_dentro():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static"
          / "lector.js").read_text(encoding="utf-8")
    assert "focoEnChrome" in js
    assert "barra.contains(activo)" in js and "menu.contains(activo)" in js
    assert 'addEventListener("focusout"' in js


def test_los_controles_del_lector_tienen_foco_en_colores_forzados():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static"
           / "web.css").read_text(encoding="utf-8")
    assert "CanvasText" in css
    assert ".lector-flecha:focus-visible" in css


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


@pytest.mark.parametrize(("estado", "motivo", "status"), [
    pytest.param("preparando", "", 200, id="preparando"),
    pytest.param("error", "El archivo está protegido con contraseña; no se puede preparar.",
                 404, id="cifrado"),
    pytest.param("error", "El archivo necesita las demás partes del volumen; no se puede preparar.",
                 404, id="multivolumen"),
    pytest.param("error", "El archivo está dañado o no se puede leer.", 404, id="ilegible"),
    pytest.param("error", "El archivo no tiene páginas de imagen.", 404, id="sin-imagenes"),
    pytest.param("error", "Este tebeo es demasiado grande para prepararlo para leer.",
                 404, id="demasiado-grande"),
    pytest.param("error", "No hay espacio en la caché de lectura para preparar este tebeo.",
                 404, id="sin-espacio"),
    pytest.param("error", "El lector de CBR no está disponible en este equipo.",
                 404, id="sin-herramienta"),
])
def test_pantalla_rar_muestra_preparando(tmp_path, monkeypatch, estado, motivo, status):
    from zascarr.services.cache_lectura import Estado
    from zascarr.web import lector as wlector

    f = _rar_file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, title="Serie", metadata_={},
                            tradition=SimpleNamespace(value="american"))

    class Cache:
        async def preparar(self, _f):
            return Estado(estado, motivo)

    monkeypatch.setattr(wlector, "CACHE", Cache())
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie})
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert r.status_code == status
    assert r.headers["Cache-Control"] == "no-store"
    if motivo:
        assert motivo in r.text
        assert 'data-error-inicial' in r.text
    else:
        assert "Preparando el tebeo" in r.text
    assert f"/ui/leer/{f.id}/estado" in r.text
    assert 'id="lector-reintentar"' in r.text
    assert 'id="lector-error" role="alert"' in r.text
    assert f'href="/ui/series/{serie.id}/numero/{issue.id}"' in r.text


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


def _pantalla_con_siguiente(tmp_path, monkeypatch, estado, legal=True, pagina=None, leido=False):
    from zascarr.services.lector import (
        FALTA,
        LEER,
        SIN_SIGUIENTE,
        ArchivoDeLectura,
        Siguiente,
    )
    from zascarr.web import lector as wlector

    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, title="Serie", metadata_={},
                            tradition=SimpleNamespace(value="american"))
    if estado == LEER:
        siguiente = Siguiente(LEER, serie, 2, SimpleNamespace(id=uuid4()),
                              ArchivoDeLectura(str(uuid4()), "2.cbz", "CBZ"))
    elif estado == FALTA:
        siguiente = Siguiente(FALTA, serie, 2)
    else:
        siguiente = Siguiente(SIN_SIGUIENTE, serie=serie)

    async def _siguiente(*_a, **_k):
        return siguiente

    async def _ack(*_a, **_k):
        return legal

    monkeypatch.setattr(wlector, "siguiente_numero", _siguiente)
    monkeypatch.setattr(wlector, "is_acknowledged", _ack)
    progreso = None
    if pagina is not None:
        progreso = SimpleNamespace(
            current_page=pagina,
            status=ReadingStatus.COMPLETED if leido else ReadingStatus.READING,
        )
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie},
                     exec_queue=[FakeExecResult([progreso])])
    return f, db


def test_tarjeta_final_leer_se_pinta_en_servidor(tmp_path, monkeypatch):
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert r.status_code == 200
    assert 'id="fin"' in r.text and "hidden" in r.text
    assert "Siguiente: <strong>#2</strong>" in r.text
    assert "Leer el #2" in r.text


def test_tarjeta_final_ofrece_marcar_leido(tmp_path, monkeypatch):
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert "Marcar como leído" in r.text
    assert f'hx-post="/ui/leer/{f.id}/leido"' in r.text
    assert "Guardado: Leído" not in r.text


def test_marcar_leido_desde_la_tarjeta_usa_el_servicio_y_pinta_deshacer(tmp_path, monkeypatch):
    from zascarr.web import lector as wlector

    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    marcar = AsyncMock(return_value=None)
    monkeypatch.setattr(wlector, "marcar", marcar)
    with use_fake_session(db) as client:
        r = client.post(f"/ui/leer/{f.id}/leido", data={"operacion": "marcar"},
                        headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "Guardado: Leído" in r.text and "Deshacer" in r.text
    assert marcar.await_count == 1
    args = marcar.await_args.args
    assert args[2].value == "completed"
    assert marcar.await_args.kwargs["series_id"] is not None


def test_deshacer_leido_vuelve_a_leyendo(tmp_path, monkeypatch):
    from zascarr.web import lector as wlector

    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    marcar = AsyncMock(return_value=None)
    monkeypatch.setattr(wlector, "marcar", marcar)
    with use_fake_session(db) as client:
        r = client.post(f"/ui/leer/{f.id}/leido", data={"operacion": "deshacer"},
                        headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "Marcar como leído" in r.text and "Guardado: Leído" not in r.text
    assert marcar.await_args.args[2] is ReadingStatus.READING


def test_marcar_leido_sin_htmx_redirige_a_la_lectura(tmp_path, monkeypatch):
    from zascarr.web import lector as wlector

    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    monkeypatch.setattr(wlector, "marcar", AsyncMock(return_value=None))
    with use_fake_session(db) as client:
        r = client.post(f"/ui/leer/{f.id}/leido", data={"operacion": "marcar"},
                        follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/ui/leer/{f.id}"


def test_tarjeta_final_falta_sin_legal_lleva_al_aviso(tmp_path, monkeypatch):
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "falta", legal=False)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert "Te falta el" in r.text and "#2" in r.text
    # AC-10 (UATP-01): el enlace directo lleva el destino de vuelta al lector.
    assert f'href="/ui/legal?volver=%2Fui%2Fleer%2F{f.id}"' in r.text
    assert f'hx-post="/ui/leer/{f.id}/deseo"' not in r.text


def _bloque_fin(html: str) -> str:
    """El trozo de HTML de la página de fin, para no confundirla con el resto de la pantalla."""
    return html.split('id="fin"', 1)[1].split("</section>", 1)[0]


def test_el_fin_llega_en_el_html_oculto_sin_contenido_visible(tmp_path, monkeypatch):
    """FR-1/FR-28: el servidor pinta la página de fin oculta; solo el JS la abre con intención."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer", pagina=3)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert r.status_code == 200
    assert 'id="fin"' in r.text
    assert 'class="lector-fin" hidden' in r.text
    fin = _bloque_fin(r.text)
    assert "Fin del número" in fin
    assert "Has llegado al final" not in fin


@pytest.mark.parametrize(("estado", "frase"), [
    pytest.param("leer", "Siguiente: <strong>#2</strong>", id="leer"),
    pytest.param("falta", "Te falta el <strong>#2</strong>", id="falta"),
    pytest.param("sin_siguiente", "No hay un número siguiente en tu biblioteca.",
                 id="sin_siguiente"),
])
def test_el_fin_se_pinta_oculto_en_los_tres_estados(tmp_path, monkeypatch, estado, frase):
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, estado)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    assert r.status_code == 200
    assert 'class="lector-fin" hidden' in r.text
    assert frase in _bloque_fin(r.text)


def test_la_pagina_de_fin_no_es_un_dialogo(tmp_path, monkeypatch):
    """FR-23/AC-16: es contenido (`section` + `aria-labelledby`), sin diálogo ni trampa de foco."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert '<section id="fin" class="lector-fin" hidden aria-labelledby="fin-titulo">' in r.text
    assert '<h2 id="fin-titulo"' in fin and 'tabindex="-1"' in fin
    assert 'class="titulo-frase"' not in fin
    assert 'role="dialog"' not in r.text
    assert "aria-modal" not in r.text


def test_el_control_de_avanzar_sigue_operativo_en_la_ultima_pagina(tmp_path, monkeypatch):
    """FR-2: en la última página el avance no está desactivado: abre el final y se llama
    «Ver el final»."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer", pagina=3)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    avance = re.search(r'<button[^>]*id="lector-siguiente"[^>]*>', r.text).group(0)
    assert 'aria-disabled="false"' in avance
    assert 'aria-label="Ver el final"' in avance

    f2, db2 = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer", pagina=1)
    with use_fake_session(db2) as client:
        r2 = client.get(f"/ui/leer/{f2.id}")
    retroceso = re.search(r'<button[^>]*id="lector-anterior"[^>]*>', r2.text).group(0)
    assert 'aria-disabled="true"' in retroceso
    assert 'aria-label="Página anterior"' in retroceso


def test_la_pagina_de_fin_conserva_la_vuelta_tras_cada_accion(tmp_path, monkeypatch):
    """FR-4/FR-15: «Quedarme» vive fuera de #fin-acciones y Deseados no borra la vuelta."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "falta", legal=True)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert "Quedarme en esta página" in fin
    assert 'id="fin-quedarme"' in fin
    assert "Volver a la serie" in fin
    assert fin.index('id="fin-quedarme"') > fin.index("Volver a la serie")
    assert 'id="fin-deseo"' in fin
    assert 'hx-target="#fin-deseo"' in fin
    assert 'hx-target="#fin-acciones"' not in fin.split('id="fin-deseo"', 1)[1]


def test_la_portada_del_siguiente_no_se_pide_al_llegar(tmp_path, monkeypatch):
    """FR-12: la portada se hidrata al abrir la página de fin; el HTML inicial no lleva `src`."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert re.search(r'data-portada-url="/ui/series/[0-9a-f-]+/numero/[0-9a-f-]+/portada\.jpg"',
                     fin)
    portada = fin.split('id="fin-portada"', 1)[1].split("</div>", 1)[0]
    assert "<img" not in portada
    assert 'alt=""' not in portada


def test_fin_sin_siguiente_no_ofrece_deseados_ni_leer(tmp_path, monkeypatch):
    """FR-11/AC-9."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "sin_siguiente")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert "No hay un número siguiente en tu biblioteca." in fin
    assert "Leer el #" not in fin
    assert "Añadir a Deseados" not in fin
    assert "Marcar como leído" in fin
    assert "Volver a la serie" in fin


def test_fin_falta_conserva_la_puerta_legal(tmp_path, monkeypatch):
    """FR-10/AC-7/AC-8: sin aviso, enlace a la puerta legal; con aviso, formulario a #fin-deseo."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "falta", legal=False)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert f'href="/ui/legal?volver=%2Fui%2Fleer%2F{f.id}"' in fin
    assert f'hx-post="/ui/leer/{f.id}/deseo"' not in fin
    assert "Antes tienes que leer y aceptar el aviso legal" in fin

    f2, db2 = _pantalla_con_siguiente(tmp_path, monkeypatch, "falta", legal=True)
    with use_fake_session(db2) as client:
        r2 = client.get(f"/ui/leer/{f2.id}")
    fin2 = _bloque_fin(r2.text)
    assert f'hx-post="/ui/leer/{f2.id}/deseo"' in fin2
    assert 'hx-target="#fin-deseo"' in fin2
    assert "Antes tienes que leer y aceptar el aviso legal" not in fin2


def test_marcar_leido_desde_la_pagina_de_fin_sigue_siendo_explicito(tmp_path, monkeypatch):
    """D-LEC-2/FR-14: leer el final no marca nada; el botón explícito es el único camino."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer", pagina=3)
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert "Marcar como leído" in fin
    assert "Guardado: Leído" not in fin
    assert db.commit.await_count == 0


def test_un_solo_principal_en_la_pagina_de_fin(tmp_path, monkeypatch):
    """D-LEC-8: «Leer el #K» (o Deseados) es el único principal; Marcar leído es neutro."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    assert fin.count("btn primary") == 1
    assert "Leer el #2" in fin
    assert '<button type="submit" class="btn" data-lector-leido="false">' in fin

    f2, db2 = _pantalla_con_siguiente(tmp_path, monkeypatch, "falta", legal=False)
    with use_fake_session(db2) as client:
        r2 = client.get(f"/ui/leer/{f2.id}")
    fin2 = _bloque_fin(r2.text)
    assert fin2.count("btn primary") == 1
    assert "Añadir a Deseados" in fin2


def test_los_textos_de_la_pagina_de_fin_son_los_especificados(tmp_path, monkeypatch):
    """FR-13 y §5.2: los textos visibles de la tabla son literales."""
    f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "leer")
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
    fin = _bloque_fin(r.text)
    for pieza in ("Fin del número", "Has terminado el #1. Siguiente: <strong>#2</strong>.",
                  "Leer el #2", "Quedarme en esta página", "Marcar como leído",
                  "Volver a la serie"):
        assert pieza in fin, pieza


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
    assert r.headers["cache-control"] == "no-store"
    assert db.commit.await_count == 0


def test_guardar_progreso_rellena_page_count_solo_si_falta_y_un_archivo(tmp_path):
    f = _file(tmp_path)
    issue = Issue(id=f.issue_id, series_id=uuid4(), issue_number="1", volume=1,
                  page_count=None, metadata_={})

    class Db(FakeSession):
        def add(self, obj):
            pass

    db = Db(get_map={(File, f.id): f, (Issue, issue.id): issue},
            exec_queue=[FakeExecResult(1), FakeExecResult([])])
    import asyncio
    asyncio.run(lector.guardar_progreso(db, f.id, 2))
    assert issue.page_count == 3
    assert issue.metadata_["page_count_origen"] == "lector"


def test_guardar_progreso_no_pisa_page_count_ni_escribe_con_varios_archivos(tmp_path):
    f = _file(tmp_path)
    issue = Issue(id=f.issue_id, series_id=uuid4(), issue_number="1", volume=1,
                  page_count=7, metadata_={"page_count_origen": "comicinfo"})

    class Db(FakeSession):
        def add(self, obj):
            pass

    db = Db(get_map={(File, f.id): f, (Issue, issue.id): issue},
            exec_queue=[FakeExecResult([])])
    import asyncio
    asyncio.run(lector.guardar_progreso(db, f.id, 1))
    assert issue.page_count == 7
    assert issue.metadata_["page_count_origen"] == "comicinfo"

    issue2 = Issue(id=f.issue_id, series_id=uuid4(), issue_number="1", volume=1,
                   page_count=None, metadata_={})
    db2 = Db(get_map={(File, f.id): f, (Issue, issue2.id): issue2},
             exec_queue=[FakeExecResult(2), FakeExecResult([])])
    asyncio.run(lector.guardar_progreso(db2, f.id, 1))
    assert issue2.page_count is None and "page_count_origen" not in issue2.metadata_


class TestUatp03AsaYFoco:
    """UATP-03: asa descubrible, foco sin forzar, reapertura y RTL."""

    def test_el_asa_esta_en_el_html_con_aria_icono_y_oculto(self, tmp_path, monkeypatch):
        f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "sin_siguiente")
        with use_fake_session(db) as client:
            r = client.get(f"/ui/leer/{f.id}")
        assert r.status_code == 200
        assert 'id="lector-asa"' in r.text
        assert 'aria-label="Mostrar los controles"' in r.text
        assert 'aria-controls="lector-barra"' in r.text
        bloque = r.text.split('id="lector-asa"', 1)[1].split("</button>", 1)[0]
        assert "<svg" in bloque
        assert "hidden" in r.text.split('id="lector-asa"', 1)[1].split(">", 1)[0]

    def test_la_ayuda_menciona_la_lengueta_y_el_centro(self, tmp_path, monkeypatch):
        f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "sin_siguiente")
        with use_fake_session(db) as client:
            r = client.get(f"/ui/leer/{f.id}")
        assert "toca la lengüeta de arriba o el centro de la página" in r.text

    def test_volver_al_numero_es_el_primer_control_y_no_desborda(self):
        from pathlib import Path

        html = Path("src/zascarr/web/templates/lector.html").read_text(encoding="utf-8")
        inicio = html.index('class="lector-barra"')
        volver = html.index('class="back-link lector-volver"', inicio)
        assert volver < html.index('class="lector-identidad"', inicio)
        assert volver < html.index('id="lector-zoom-menos"', inicio)
        assert volver < html.index('id="lector-menu-boton"', inicio)
        css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
        bloque = css.split(".lector-volver {", 1)[1].split("}", 1)[0]
        assert "min-height: 44px" in bloque
        assert "white-space: nowrap" not in bloque

    def test_css_del_asa_es_44x44_y_solo_con_chrome_oculto(self):
        from pathlib import Path

        css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
        bloque = css.split(".lector-asa {", 1)[1].split("}", 1)[0]
        assert "min-width: 44px" in bloque and "min-height: 44px" in bloque
        assert "z-index: 4" in bloque
        assert '[data-chrome="oculto"] .lector-asa' in css
        assert "body:has(.lector-escena) .skip" in css
        assert "[data-chrome=\"oculto\"] .lector-asa" in css

    @pytest.mark.parametrize(("guardada", "esperada"), [
        (None, "1"), (2, "2"), (99, "3"), (0, "1"), (-5, "1"),
    ])
    def test_reabrir_usa_la_pagina_guardada_acotada(
            self, tmp_path, monkeypatch, guardada, esperada):
        f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "sin_siguiente",
                                        pagina=guardada)
        with use_fake_session(db) as client:
            r = client.get(f"/ui/leer/{f.id}")
        assert r.status_code == 200
        assert f'data-pagina="{esperada}"' in r.text
        assert f"/pagina/{esperada}" in r.text
        assert f"Página {esperada} de 3" in r.text

    def test_render_rtl_tiene_sentido_etiquetas_y_origen(self, tmp_path, monkeypatch):
        from zascarr.web import lector as wlector

        async def _rtl(*_a, **_k):
            return "rtl", "serie"

        monkeypatch.setattr(wlector, "sentido_de_lectura", _rtl)
        f, db = _pantalla_con_siguiente(tmp_path, monkeypatch, "sin_siguiente")
        with use_fake_session(db) as client:
            r = client.get(f"/ui/leer/{f.id}")
        assert r.status_code == 200
        assert 'data-sentido="rtl"' in r.text
        assert 'aria-label="Página siguiente"' in r.text or 'aria-label="Ver el final"' in r.text
        assert "Sentido: derecha a izquierda" in r.text
        assert "Sentido guardado para esta serie." in r.text
