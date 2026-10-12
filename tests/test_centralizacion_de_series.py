# ruff: noqa: E501
"""Centralización de las decisiones de creación y edición de series (#113): delegación y constructores. Sin base de datos.

Criterio 1 de #113: «dados los mismos datos, UI y API delegan en el mismo servicio». Aquí se fija, sin Postgres:
- QUÉ entradas construyen una `Series` (el recuento de `Series(...)` fuera del servicio de alta);
- que cada entrada acordada llama al servicio común (y no a una lógica propia);
- que la detección de colisiones y su candado son UNA sola definición compartida.

**Excepción declarada (A1, #113):** `POST /api/series` (`api/series.py::create_series`) construye la `Series` en el propio
router y NO delega: está fuera de las entradas acordadas, marcado como obsoleto (I3, #169) y su retirada es de I6 (#114).
Cuando se retire, este fichero debe actualizarse: el recuento baja a un único constructor.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import zascarr
import zascarr.web.discovery as web_discovery
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition
from zascarr.services import alta_serie, edicion_serie
from zascarr.services.alta_serie import ResultadoAlta, VistaPreviaAlta
from zascarr.services.descubrimiento_grupo import SerieLocal

RAIZ = Path(zascarr.__file__).parent

#: ÚNICOS lugares de `src/` que construyen una `Series(...)`: el servicio de alta y, por excepción A1, `POST /api/series`.
CONSTRUCTORES_ESPERADOS = {
    ("services/alta_serie.py", "_crear_en_transaccion"): 1,     # AltaDeSerie: el camino de creación común
    ("api/series.py", "create_series"): 1,                       # C3: obsoleto, FUERA de la centralización (A1)
}


def _constructores_de_series() -> dict[tuple[str, str], int]:
    """Cuántos `Series(...)` hay en `src/`, por fichero y función que los contiene (AST: no se engaña con comentarios)."""
    hallados: dict[tuple[str, str], int] = {}
    for ruta in RAIZ.rglob("*.py"):
        rel = ruta.relative_to(RAIZ).as_posix()
        if rel.startswith("models/"):
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for funcion in ast.walk(arbol):
            if not isinstance(funcion, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for nodo in ast.walk(funcion):
                if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == "Series"):
                    hallados[(rel, funcion.name)] = hallados.get((rel, funcion.name), 0) + 1
    return hallados


class TestQuienConstruyeUnaSerie:
    def test_solo_el_servicio_de_alta_y_la_ruta_excluida_construyen_una_serie(self):
        assert _constructores_de_series() == CONSTRUCTORES_ESPERADOS

    def test_ni_descubrir_ni_la_edicion_ni_el_alta_por_api_construyen_una_serie_por_su_cuenta(self):
        fuera = {f for f, _ in _constructores_de_series()}
        assert not {"web/discovery.py", "services/discovery.py", "services/edicion_serie.py", "api/revision.py",
                    "services/descubrimiento_libre.py"} & fuera

    def test_la_excepcion_a1_es_la_ruta_obsoleta(self):
        """La única entrada fuera del servicio común está declarada obsoleta en el esquema (I3)."""
        assert app.openapi()["paths"]["/api/series"]["post"]["deprecated"] is True


class TestUnaSolaDefinicionDeLaColision:
    def test_la_edicion_y_el_alta_comparten_la_deteccion_y_el_candado(self):
        assert edicion_serie.buscar_parecidas is alta_serie.buscar_parecidas
        assert edicion_serie.bloquear_titulo is alta_serie.bloquear_titulo

    @pytest.mark.asyncio
    async def test_el_metodo_del_alta_delega_en_la_funcion_compartida(self):
        llamadas = []

        async def falsa(db, titulo, anio, tradicion, *, excluir):
            llamadas.append((titulo, anio, tradicion, excluir))
            return []
        with patch.object(alta_serie, "buscar_parecidas", falsa):
            await alta_serie.AltaDeSerie(db=None, secret="x")._parecidas("Flash", 1987, ComicTradition.AMERICAN, excluir=None)
        assert llamadas == [("Flash", 1987, ComicTradition.AMERICAN, None)]


class _Sesion:
    async def execute(self, *a, **k):
        raise AssertionError("la ruta no debía consultar la base: delega en el servicio")


@pytest.fixture
def cliente(monkeypatch):
    async def _get_db():
        yield _Sesion()
    app.dependency_overrides[get_db] = _get_db
    monkeypatch.setattr(web_discovery, "get_settings", lambda: SimpleNamespace(secret_key="secreto-de-prueba"))
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _vista() -> VistaPreviaAlta:
    return VistaPreviaAlta(accion="crear", origen="descubrir", fuente="comic_vine", titulo="Flash", anio=1987,
                           tradicion="american", tradicion_sugerida="american", existente=None, parecidas=[],
                           decision=None, resumen="r", efectos={"series_nuevas": 1, "numeros": 0, "archivos": 0}, token="T")


class TestCadaEntradaDelegaEnElServicioComun:
    def test_descubrir_revisar_llama_a_previsualizar_sin_grupo_con_lo_que_recibe(self, cliente):
        falso = AsyncMock(return_value=_vista())
        with patch.object(alta_serie.AltaDeSerie, "previsualizar_sin_grupo", falso):
            r = cliente.post("/ui/descubrir/revisar", data={"candidata": "CAND", "tradition": "manga"})
        assert r.status_code == 200
        falso.assert_awaited_once()
        assert falso.await_args.kwargs["tradicion"] == ComicTradition.MANGA and falso.await_args.kwargs["candidata"] == "CAND"

    def test_descubrir_crear_llama_a_confirmar_solo_con_el_token(self, cliente):
        resultado = ResultadoAlta(resultado="creada", serie=SerieLocal(series_id="9", titulo="Flash", anio=1987, tradicion="american"),
                                  repetida=False, motivo=None, deshacer=None)
        falso = AsyncMock(return_value=resultado)
        with patch.object(alta_serie.AltaDeSerie, "confirmar", falso):
            r = cliente.post("/ui/descubrir/crear", data={"token": "TOKEN-DE-ALTA"})
        assert r.status_code == 200
        falso.assert_awaited_once_with("TOKEN-DE-ALTA")

    def test_descubrir_deshacer_llama_al_deshacer_del_servicio(self, cliente):
        from uuid import uuid4

        from zascarr.services.alta_serie import ResultadoDeshacer
        sid, op = uuid4(), uuid4()
        falso = AsyncMock(return_value=ResultadoDeshacer(deshecho=True, series_id=str(sid), titulo="Flash"))
        with patch.object(alta_serie.AltaDeSerie, "deshacer", falso):
            r = cliente.post("/ui/descubrir/deshacer", data={"series_id": str(sid), "operacion_id": str(op)})
        assert r.status_code == 200
        falso.assert_awaited_once_with(sid, op)

    def test_el_alta_por_api_llama_a_previsualizar_y_confirmar_del_servicio(self, monkeypatch):
        import zascarr.api.revision as api_revision
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key="secreto-de-prueba"))

        async def _get_db():
            yield MagicMock()
        app.dependency_overrides[get_db] = _get_db
        try:
            previsualizar = AsyncMock(return_value=_vista())
            confirmar = AsyncMock(return_value=ResultadoAlta(
                resultado="creada", serie=SerieLocal(series_id="9", titulo="Flash", anio=1987, tradicion="american"),
                repetida=False, motivo=None, deshacer=None))
            with patch.object(alta_serie.AltaDeSerie, "previsualizar", previsualizar), \
                 patch.object(alta_serie.AltaDeSerie, "confirmar", confirmar):
                c = TestClient(app)
                p = c.post("/api/revision/serie/previsualizar",
                           json={"clave": "Comics/X", "manual": {"titulo": "Flash", "anio": 1987}, "tradicion": "american"})
                k = c.post("/api/revision/serie", json={"token": "TOKEN"})
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert p.status_code == 200 and k.status_code == 200
        previsualizar.assert_awaited_once()
        confirmar.assert_awaited_once_with("TOKEN")

    def test_el_alta_por_api_sin_carpeta_llama_a_previsualizar_sin_grupo(self, monkeypatch):
        import zascarr.api.revision as api_revision
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key="secreto-de-prueba"))

        async def _get_db():
            yield MagicMock()
        app.dependency_overrides[get_db] = _get_db
        try:
            falso = AsyncMock(return_value=_vista())
            with patch.object(alta_serie.AltaDeSerie, "previsualizar_sin_grupo", falso):
                r = TestClient(app).post("/api/revision/serie/sin-carpeta/previsualizar",
                                         json={"manual": {"titulo": "Flash", "anio": 1987}, "tradicion": "manga"})
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 200
        falso.assert_awaited_once()
        assert falso.await_args.kwargs["tradicion"] == ComicTradition.MANGA

    def test_patch_de_identidad_delega_en_edicion_de_serie(self, monkeypatch):
        from uuid import uuid4

        async def _get_db():
            yield MagicMock()
        app.dependency_overrides[get_db] = _get_db
        try:
            falso = AsyncMock(side_effect=edicion_serie.SerieCambiadaError())
            with patch.object(edicion_serie.EdicionDeSerie, "actualizar", falso):
                r = TestClient(app).patch(f"/api/series/{uuid4()}", json={"title": "Otro", "vistas": []})
        finally:
            app.dependency_overrides.pop(get_db, None)
        falso.assert_awaited_once()
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "serie_cambiada"
