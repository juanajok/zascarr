"""
tests/test_pendientes.py

Suite de los endpoints HTMX de la bandeja de pendientes (B2). Sobrescribe
la dependencia get_db con una sesión falsa (patrón recomendado por
FastAPI) para no necesitar Postgres real — mismo motivo que test_web.py
usa TestClient sin `with`: evitar el lifespan real de la app.

El movimiento de archivos real (assign_to_series con tmp_path) ya está
cubierto en test_review.py contra el servicio directamente; aquí se
prueba el CONTRATO HTTP de cada ruta (200/404/400, qué fragmento HTML
devuelve cada una), no la lógica de negocio por duplicado.
"""
from __future__ import annotations

import zipfile
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, FileFormat, Series


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


class FakeSession:
    def __init__(self, get_map=None, exec_queue=None):
        self._get_map = get_map or {}
        self._exec_queue = list(exec_queue or [])
        self.flush = AsyncMock()

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
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([file])])) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "batman misterioso 12.cbz" in r.text

    def test_pagina_sin_pendientes_muestra_mensaje_vacio(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
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
                    {"series_id": str(sid), "title": "La Patrulla-X", "start_year": 1985, "score": 0.62},
                ],
            },
        )
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([file])])) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "¿Es esta serie?" in r.text
        assert "La Patrulla-X" in r.text
        assert "62% de coincidencia" in r.text
        assert f'value="{sid}"' in r.text

    def test_archivo_sin_candidatos_no_muestra_sugerencia(self):
        file = File(id=uuid4(), file_path="/lib/_Unsorted/algo.cbz", file_name="algo.cbz",
                    file_format=FileFormat.CBZ, metadata_={"match_status": "unsorted"})
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([file])])) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        assert "¿Es esta serie?" not in r.text


class TestBuscarSerie:

    def test_devuelve_resultados_como_fragmento(self):
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011)
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([series])])) as client:
            r = client.get(f"/ui/pendientes/{uuid4()}/buscar-serie?q=bat")
        assert r.status_code == 200
        assert "Batman" in r.text
        assert "2011" in r.text

    def test_sin_coincidencias(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get(f"/ui/pendientes/{uuid4()}/buscar-serie?q=zzz")
        assert "Sin coincidencias" in r.text


class TestIgnorar:

    def test_ignorar_devuelve_vacio_para_eliminar_la_tarjeta(self, tmp_path):
        file = File(id=uuid4(), file_path=str(tmp_path / "x.cbz"), file_name="x.cbz",
                    file_format=FileFormat.CBZ, review_dismissed=False)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.post(f"/ui/pendientes/{file.id}/ignorar")
        assert r.status_code == 200
        assert r.text == ""
        assert file.review_dismissed is True

    def test_archivo_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/pendientes/{uuid4()}/ignorar")
        assert r.status_code == 404


class TestAsignar:

    def test_serie_inexistente_da_400(self, tmp_path):
        file = File(id=uuid4(), file_path=str(tmp_path / "x.cbz"), file_name="x.cbz",
                    file_format=FileFormat.CBZ)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.post(f"/ui/pendientes/{file.id}/asignar",
                            data={"series_id": str(uuid4()), "issue_number": "5"})
        assert r.status_code == 400

    def test_numero_vacio_da_400(self, tmp_path):
        file = File(id=uuid4(), file_path=str(tmp_path / "x.cbz"), file_name="x.cbz",
                    file_format=FileFormat.CBZ)
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
        session = FakeSession(get_map={(File, file.id): file, (Series, series.id): series})
        with use_fake_session(session) as client:
            r = client.post(f"/ui/pendientes/{file.id}/asignar",
                            data={"series_id": str(series.id), "issue_number": "   "})
        assert r.status_code == 400


class TestPortada:

    def test_extraida_correctamente(self, tmp_path):
        path = tmp_path / "comic.cbz"
        with zipfile.ZipFile(path, "w") as zf:
            # 1x1 JPEG válido mínimo (suficiente para que Pillow lo abra).
            from PIL import Image
            import io
            buf = io.BytesIO()
            Image.new("RGB", (10, 10), color="red").save(buf, format="JPEG")
            zf.writestr("001.jpg", buf.getvalue())

        file = File(id=uuid4(), file_path=str(path), file_name="comic.cbz", file_format=FileFormat.CBZ)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.get(f"/ui/pendientes/{file.id}/portada")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_archivo_sin_miniatura_da_404(self, tmp_path):
        path = tmp_path / "roto.cbz"
        path.write_bytes(b"no es un zip")
        file = File(id=uuid4(), file_path=str(path), file_name="roto.cbz", file_format=FileFormat.CBZ)
        with use_fake_session(FakeSession(get_map={(File, file.id): file})) as client:
            r = client.get(f"/ui/pendientes/{file.id}/portada")
        assert r.status_code == 404

    def test_archivo_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.get(f"/ui/pendientes/{uuid4()}/portada")
        assert r.status_code == 404
