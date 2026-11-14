# ruff: noqa: E501
"""
tests/test_pendientes.py

Suite de los endpoints HTMX de la bandeja de pendientes (B2). Sobrescribe
la dependencia get_db con una sesión falsa (patrón recomendado por
FastAPI) para no necesitar Postgres real — mismo motivo que test_web.py
usa TestClient sin `with`: evitar el lifespan real de la app.

El movimiento de archivos real ya está cubierto en test_asignacion_*_pg.py (servicio
recuperable) y test_review.py (camino heredado de B13/B15); aquí se
prueba el CONTRATO HTTP de cada ruta (200/404/400, qué fragmento HTML
devuelve cada una), no la lógica de negocio por duplicado.
"""
from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, FileFormat, Series
from zascarr.web.pendientes import RECONTAR_MENU


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows if isinstance(self._rows, int) else self._rows[0]


def cola_de(files: list) -> list:
    """Lo que consume `GET /ui/pendientes` (cursor, U12): el total, la lista y —si hay lista— cuántos van antes del
    primero. `imported_at` ADMITE NULL en la BD real (la migración inicial no pone NOT NULL); los archivos de
    estas pruebas no lo traen y se rellena para que el cursor tenga clave. El caso NULL real tiene su prueba
    con Postgres en `test_pendientes_navegacion_pg.py::TestImportedAtNulo`."""
    ahora = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    for f in files:
        f.imported_at = f.imported_at or ahora
    if not files:
        return [FakeExecResult(0), FakeExecResult([])]
    return [FakeExecResult(len(files)), FakeExecResult(files), FakeExecResult(0)]


class FakeSession:
    def __init__(self, get_map=None, exec_queue=None):
        self._get_map = get_map or {}
        self._exec_queue = list(exec_queue or [])
        self.flush = AsyncMock()
        self.commit = AsyncMock()

    async def get(self, model, id_):
        return self._get_map.get((model, id_))

    async def execute(self, _statement):
        return self._exec_queue.pop(0)

    def add(self, obj):
        pass


def override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    """Context manager minimal: sobrescribe get_db y lo restaura siempre,
    incluso si el test falla a medio camino."""
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


class TestPendientesIndex:

    def test_pagina_lista_archivos_pendientes(self):
        file = File(id=uuid4(), file_path="/lib/_Unsorted/batman misterioso 12.cbz",
                    file_name="batman misterioso 12.cbz", file_format=FileFormat.CBZ)
        with use_fake_session(FakeSession(exec_queue=cola_de([file]))) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "batman misterioso 12.cbz" in r.text

    def test_pagina_sin_pendientes_muestra_mensaje_vacio(self):
        with use_fake_session(FakeSession(exec_queue=cola_de([]))) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "Nada pendiente" in r.text

    def test_archivo_con_candidato_guardado_muestra_sugerencia(self):
        """B12: el matcher guardó un candidato por debajo del umbral en
        metadata_ — la tarjeta debe ofrecerlo como sugerencia de un clic,
        no obligar a rebuscar a mano."""
        sid = uuid4()
        file = File(
            id=uuid4(),
            file_path="/lib/_Unsorted/la patrulla x omnigold 12.cbz",
            file_name="la patrulla x omnigold 12.cbz",
            file_format=FileFormat.CBZ,
            metadata_={
                "match_status": "unsorted",
                "candidates": [
                    {
                        "series_id": str(sid),
                        "title": "La Patrulla-X",
                        "start_year": 1985,
                        "score": 0.62,
                    },
                ],
            },
        )
        with use_fake_session(FakeSession(exec_queue=cola_de([file]))) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "¿Es esta serie?" in r.text
        assert "La Patrulla-X" in r.text
        assert "62% de coincidencia" in r.text
        assert f'value="{sid}"' in r.text
        # En `_Unsorted` no se ofrece Vincular: fallaría siempre. Solo Organizar.
        assert "Vincular en su sitio" not in r.text
        # #723: la búsqueda manual no compite con la sugerencia; vive en un desplegable.
        assert '<details class="elegir-otra-serie">' in r.text
        assert "Elegir otra serie" in r.text

    def test_archivo_dentro_de_la_biblioteca_si_ofrece_vincular_en_sitio(self):
        sid = uuid4()
        file = File(
            id=uuid4(), file_path="/lib/Comics/Flash/Flash 01.cbz",
            file_name="Flash 01.cbz", file_format=FileFormat.CBZ,
            metadata_={"match_status": "unsorted",
                       "candidates": [{"series_id": str(sid), "title": "Flash", "score": 0.9}]},
        )
        with use_fake_session(FakeSession(exec_queue=cola_de([file]))) as client:
            r = client.get("/ui/pendientes")
        assert "Vincular en su sitio" in r.text
        assert f'hx-post="/ui/pendientes/{file.id}/vincular"' in r.text
        assert "solo funciona si esa publicación ya existe" in r.text

    def test_archivo_sin_candidatos_no_muestra_sugerencia(self):
        file = File(id=uuid4(), file_path="/lib/_Unsorted/algo.cbz", file_name="algo.cbz",
                    file_format=FileFormat.CBZ, metadata_={"match_status": "unsorted"})
        with use_fake_session(FakeSession(exec_queue=cola_de([file]))) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "¿Es esta serie?" not in r.text


class TestBuscarSerie:

    def test_devuelve_resultados_como_fragmento(self):
        series = Series(id=uuid4(), title="Batman",
                        tradition=ComicTradition.AMERICAN, start_year=2011)
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([series])])) as client:
            r = client.get(f"/ui/pendientes/{uuid4()}/buscar-serie?q=bat")
        assert r.status_code == 200
        assert "Batman" in r.text
        assert "2011" in r.text

    def test_sin_coincidencias(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get(f"/ui/pendientes/{uuid4()}/buscar-serie?q=zzz")
        assert "Sin coincidencias" in r.text


class TestLaAsignacionSeRotulaOrganizar:
    """I8 de #114: la asignación MUEVE y RENOMBRA el archivo (ADR 0007), así que se rotula «Organizar» y la pantalla lo dice
    EN CLARO (no solo en una ayuda al pasar el ratón, que en el móvil no existe). Solo cambia el texto: la ruta, los
    campos del formulario y el servicio son los de siempre."""

    @staticmethod
    def _botones_de_asignar(html: str) -> list[str]:
        import re
        formularios = re.findall(
            r'<form[^>]*hx-get="/ui/pendientes/[^"]+/asignar/previa"[^>]*>(.*?)</form>',
            html, re.S)
        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", re.search(r'<button[^>]*type="submit"[^>]*>.*?</button>', f, re.S).group(0))).strip()
                for f in formularios]

    @staticmethod
    def _texto_visible(html: str) -> str:
        """Lo que lee la persona: sin comentarios de plantilla, sin etiquetas (y por tanto sin atributos como `title`)."""
        import re
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"\{#.*?#\}", "", html, flags=re.S))).lower()

    def _tarjeta(self):
        sid = uuid4()
        file = File(id=uuid4(), file_path="/lib/_Unsorted/la patrulla x 12.cbz", file_name="la patrulla x 12.cbz",
                    file_format=FileFormat.CBZ,
                    metadata_={"match_status": "unsorted",
                               "candidates": [{"series_id": str(sid), "title": "La Patrulla-X", "start_year": 1985, "score": 0.62}]})
        with use_fake_session(FakeSession(exec_queue=cola_de([file]))) as client:
            return client.get("/ui/pendientes").text, file, sid

    def test_el_boton_de_la_sugerencia_se_rotula_organizar_y_la_tarjeta_dice_que_mueve_y_renombra(self):
        html, _, _ = self._tarjeta()
        (boton,) = self._botones_de_asignar(html)
        assert "organizar" in boton.lower()
        assert "mueve y renombra el archivo" in self._texto_visible(html)
        assert "Sí, es esta" not in html

    def test_el_boton_de_los_resultados_de_busqueda_dice_lo_mismo(self):
        series = [Series(id=uuid4(), title=t, tradition=ComicTradition.AMERICAN, start_year=y)
                  for t, y in (("Batman", 2011), ("Batman Begins", 2005))]
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult(series)])) as client:
            html = client.get(f"/ui/pendientes/{uuid4()}/buscar-serie?q=bat").text
        assert self._botones_de_asignar(html) == ["Ver antes de organizar", "Ver antes de organizar"]
        assert "«organizar» mueve y renombra el archivo" in self._texto_visible(html)
        assert ">Confirmar<" not in html

    def test_todo_formulario_que_asigna_se_rotula_organizar_y_su_plantilla_lo_explica(self):
        """Si alguien añade otro formulario que llame a `/asignar` con un texto engañoso, esto lo detecta."""
        from pathlib import Path

        import zascarr.web as web
        plantillas = Path(web.__file__).parent / "templates"
        con_previa = [p for p in plantillas.glob("*.html")
                      if "/asignar/previa" in p.read_text(encoding="utf-8")]
        assert {p.name for p in con_previa} == {"_tarjeta_pendiente.html", "_resultados_serie.html"}
        for p in con_previa:
            html = p.read_text(encoding="utf-8")
            botones = self._botones_de_asignar(html)
            assert botones and all("organizar" in b.lower() for b in botones), p.name
            assert "mueve y renombra el archivo" in self._texto_visible(html), p.name
            assert 'hx-post="/ui/pendientes/{{ c.file.id }}/asignar"' not in html, p.name
        previa = (plantillas / "_previa_asignacion.html").read_text(encoding="utf-8")
        assert 'hx-post="/ui/pendientes/{{ file_id }}/asignar"' in previa
        assert "Confirmar y organizar" in previa

    def test_el_recorrido_no_cambia_misma_ruta_y_mismos_campos(self):
        html, file, sid = self._tarjeta()
        assert f'hx-get="/ui/pendientes/{file.id}/asignar/previa"' in html
        assert f'name="series_id" value="{sid}"' in html and 'name="issue_number"' in html
        previa = (Path(__import__("zascarr.web", fromlist=["x"]).__file__).parent
                  / "templates" / "_previa_asignacion.html").read_text(encoding="utf-8")
        assert 'hx-post="/ui/pendientes/{{ file_id }}/asignar"' in previa


class TestFragmentoDeRecuento:
    """El elemento que hace que el menú recuente «Por revisar» al sustituirse la tarjeta. Se prueba su CONTENIDO
    literal y que apunta a la ruta REAL del menú: las demás pruebas comparan con la constante y, si esta cambiara,
    seguirían pasando."""

    def test_pide_al_cargar_la_ruta_real_del_menu_y_no_intercambia_nada(self):
        from zascarr.web.navegacion import router as router_menu
        ruta_real = next(r.path for r in router_menu.routes if r.path.endswith("/estado"))
        assert ruta_real == "/ui/_nav/estado"
        assert f'hx-get="{ruta_real}"' in RECONTAR_MENU
        assert 'hx-trigger="load"' in RECONTAR_MENU          # se pide una vez, al incorporarse al DOM
        assert 'hx-swap="none"' in RECONTAR_MENU             # no cambia nada visible (los contadores van fuera de banda)
        assert " hidden" in RECONTAR_MENU                     # inerte para quien mira y para un lector de pantalla

    def test_no_depende_de_cabeceras_hx_trigger(self):
        """Mecanismo retirado: htmx 4 despacha esa cabecera sobre el elemento origen, que ya no está en el DOM
        tras el reemplazo, y el evento no llega a `body`."""
        import inspect

        import zascarr.web.pendientes as modulo
        assert "HX-Trigger" not in inspect.getsource(modulo).replace("`HX-Trigger`", "")


class TestIgnorar:

    def test_ignorar_devuelve_vacio_para_eliminar_la_tarjeta(self, tmp_path):
        file = File(id=uuid4(), file_path=str(tmp_path / "x.cbz"), file_name="x.cbz",
                    file_format=FileFormat.CBZ, review_dismissed=False)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.post(f"/ui/pendientes/{file.id}/ignorar")
        assert r.status_code == 200
        assert r.text == RECONTAR_MENU          # la tarjeta desaparece; el menú recuenta
        assert file.review_dismissed is True

    def test_ignorar_confirma_antes_de_responder(self, tmp_path):
        """Regresión del mecanismo: el `commit` de `get_db` llega DESPUÉS de responder, y el menú
        pide su contador en cuanto llega la respuesta: contaría todavía el archivo ignorado."""
        file = File(id=uuid4(), file_path=str(tmp_path / "x.cbz"), file_name="x.cbz",
                    file_format=FileFormat.CBZ, review_dismissed=False)
        session = FakeSession(get_map={(File, file.id): file})
        with use_fake_session(session) as client:
            client.post(f"/ui/pendientes/{file.id}/ignorar")
        assert session.commit.await_count >= 1

    def test_archivo_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/pendientes/{uuid4()}/ignorar")
        assert r.status_code == 404


class TestAsignar:

    def test_numero_vacio_da_400(self, tmp_path):
        file = File(id=uuid4(), file_path=str(tmp_path / "x.cbz"), file_name="x.cbz",
                    file_format=FileFormat.CBZ)
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
        session = FakeSession(get_map={(File, file.id): file, (Series, series.id): series})
        with use_fake_session(session) as client:
            r = client.post(f"/ui/pendientes/{file.id}/asignar",
                            data={"series_id": str(series.id), "issue_number": "   "})
        assert r.status_code == 400

    # Las pruebas de «serie inexistente» y de la colisión de ediciones (B15) pasaron a
    # `tests/test_pendientes_asignar_pg.py`: el endpoint ya no asigna con la sesión de la petición
    # (usa el servicio recuperable, ADR 0006, con sus propias sesiones), así que una sesión simulada
    # no las alcanza. Con Postgres real sí se prueba que el motivo sobrevive a cerrar la sesión.


class TestPortada:

    def test_extraida_correctamente(self, tmp_path):
        path = tmp_path / "comic.cbz"
        with zipfile.ZipFile(path, "w") as zf:
            # 1x1 JPEG válido mínimo (suficiente para que Pillow lo abra).
            import io

            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (10, 10), color="red").save(buf, format="JPEG")
            zf.writestr("001.jpg", buf.getvalue())

        file = File(id=uuid4(), file_path=str(path),
                    file_name="comic.cbz", file_format=FileFormat.CBZ)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.get(f"/ui/pendientes/{file.id}/portada")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_regresion_240_sin_escribir_cache_y_etag_del_origen(self, tmp_path):
        """AC-03 (FR-17): «Por revisar» sigue a 240, sin escribir en `covers/` y con el
        ETag del `mtime` del fichero ORIGEN (no el de una caché)."""
        import io

        from PIL import Image

        path = tmp_path / "comic.cbz"
        buf = io.BytesIO()
        Image.new("RGB", (1600, 2400), color="red").save(buf, format="JPEG")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("001.jpg", buf.getvalue())

        file = File(id=uuid4(), file_path=str(path),
                    file_name="comic.cbz", file_format=FileFormat.CBZ)
        antes = set(tmp_path.iterdir())
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.get(f"/ui/pendientes/{file.id}/portada")

        assert r.status_code == 200
        with Image.open(io.BytesIO(r.content)) as img:
            assert img.width <= 240
        assert r.headers["etag"] == f'"{path.stat().st_mtime}"'
        assert set(tmp_path.iterdir()) == antes, "«Por revisar» no escribe caché en disco"

    def test_archivo_sin_miniatura_da_404(self, tmp_path):
        path = tmp_path / "roto.cbz"
        path.write_bytes(b"no es un zip")
        file = File(id=uuid4(), file_path=str(path),
                    file_name="roto.cbz", file_format=FileFormat.CBZ)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.get(f"/ui/pendientes/{file.id}/portada")
        assert r.status_code == 404

    def test_archivo_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.get(f"/ui/pendientes/{uuid4()}/portada")
        assert r.status_code == 404


class TestPreviaAsignacion:
    """F1 (#636/#272): el destino se enseña antes; la vista previa no escribe y el POST queda para confirmar."""

    def test_la_previa_ensena_carpeta_y_nombre_final_sin_escribir(self, tmp_path, monkeypatch):
        path = tmp_path / "x.cbz"
        path.write_bytes(b"contenido")
        file = File(id=uuid4(), file_path=str(path), file_name="x.cbz",
                    file_format=FileFormat.CBZ)
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN,
                        start_year=2011)
        session = FakeSession(get_map={(File, file.id): file, (Series, series.id): series},
                              exec_queue=[FakeExecResult([]), FakeExecResult([])])
        monkeypatch.setattr("zascarr.web.pendientes.get_settings",
                            lambda: SimpleNamespace(library_path=tmp_path / "library"))
        with use_fake_session(session) as client:
            r = client.get(f"/ui/pendientes/{file.id}/asignar/previa",
                           params={"series_id": str(series.id), "issue_number": "12"})
        assert r.status_code == 200
        assert "Esto es lo que pasará" in r.text
        assert "Batman (2011)" in r.text
        assert "Batman #012.cbz" in r.text
        assert "Confirmar y organizar" in r.text
        assert session.commit.await_count == 0

    def test_numero_vacio_avisa_sin_consultar_ni_escribir(self):
        file = File(id=uuid4(), file_path="/no/existe.cbz", file_name="x.cbz",
                    file_format=FileFormat.CBZ)
        series = Series(id=uuid4(), title="Batman")
        session = FakeSession(get_map={(File, file.id): file, (Series, series.id): series})
        with use_fake_session(session) as client:
            r = client.get(f"/ui/pendientes/{file.id}/asignar/previa",
                           params={"series_id": str(series.id), "issue_number": "  "})
        assert r.status_code == 200 and "Escribe el número" in r.text
        assert session.commit.await_count == 0
