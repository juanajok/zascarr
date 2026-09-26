"""
tests/test_web_dashboard.py

Suite del dashboard de biblioteca (vista principal /ui/): contrato HTTP.
La lógica de negocio (enricher, huecos) ya está cubierta en sus propias
suites; aquí solo se comprueba que el endpoint renderiza el layout con las
métricas calculadas, usando una sesión falsa (mismo patrón que
test_web_library.py).
"""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeResult:
    """Resultado de una query: soporta .scalar(), .all() y .scalars().all()."""

    def __init__(self, *, scalar=None, rows=None, scalars=None):
        self._scalar = scalar
        self._rows = rows if rows is not None else []
        self._scalars = scalars if scalars is not None else []

    def scalar(self):
        return self._scalar

    def all(self):
        return self._rows

    def scalars(self):
        return _FakeScalars(self._scalars)


class FakeSession:
    def __init__(self, queue: list):
        self._queue = list(queue)

    async def execute(self, _statement):
        return self._queue.pop(0)


class CapturingSession(FakeSession):
    """Como FakeSession, pero guarda cada statement compilado — para
    verificar de verdad el WHERE que genera el código (B7: revisión de
    PR, 2026-09-26, sobre contadores de "lo tienes" sin filtrar
    is_missing), no solo lo que hace con una lista ya dada."""

    def __init__(self, queue: list):
        super().__init__(queue)
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return await super().execute(statement)


def _override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def _empty_session() -> FakeSession:
    """Cola de resultados para un dashboard sin datos (7 queries en orden)."""
    return FakeSession([
        FakeResult(scalar=0),    # total_series
        FakeResult(scalar=0),    # series_con_archivos
        FakeResult(scalar=0),    # total_issues
        FakeResult(scalar=0),    # issues_importados
        FakeResult(rows=[]),     # series_totales
        FakeResult(rows=[]),     # sort_orders
        FakeResult(scalars=[]),  # ultimas_series
    ])


class TestDashboard:

    def test_responde_200_con_layout_htmx_y_nav(self):
        with use_fake_session(_empty_session()) as client:
            r = client.get("/ui/")
        assert r.status_code == 200
        assert "/static/vendor/htmx.min.js" in r.text
        # Nunca un CDN: ver docs/adr/0001-ui-stack.md.
        assert "cdn" not in r.text.lower()
        assert '<nav class="topnav">' in r.text
        assert 'href="/estado">Estado</a>' in r.text  # nav enlaza a E1

    def test_vacio_muestra_estado_vacio(self):
        with use_fake_session(_empty_session()) as client:
            r = client.get("/ui/")
        assert "Aún no hay series importadas" in r.text

    def test_metricas_con_datos_reales(self):
        series = Series(id=uuid4(), title="Batman",
                        tradition=ComicTradition.AMERICAN, start_year=2011)
        # 40 números esperados, 2 presentes → 38 huecos y 95% si 38 importados.
        session = FakeSession([
            FakeResult(scalar=3),     # total_series
            FakeResult(scalar=2),     # series_con_archivos
            FakeResult(scalar=40),    # total_issues
            FakeResult(scalar=38),    # issues_importados
            FakeResult(rows=[(series.id, 40)]),           # series_totales
            FakeResult(rows=[(series.id, 1.0), (series.id, 2.0)]),  # sort_orders
            FakeResult(scalars=[series]),                 # ultimas_series
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/")

        assert r.status_code == 200
        assert "Batman" in r.text          # aparece en "últimas actualizaciones"
        assert "95%" in r.text             # 38/40
        assert "38" in r.text              # huecos pendientes
        assert "Series en la biblioteca" in r.text
        assert "Números pendientes" in r.text

    def test_contadores_de_archivos_filtran_is_missing(self):
        """B7 (revisión de PR, 2026-09-26): un File is_missing=True ya no
        es "lo tienes" — series_con_archivos, issues_importados y las
        últimas series actualizadas deben excluirlo, o borrar un tebeo a
        mano seguiría contando en el dashboard."""
        session = CapturingSession([
            FakeResult(scalar=0), FakeResult(scalar=0), FakeResult(scalar=0), FakeResult(scalar=0),
            FakeResult(rows=[]), FakeResult(rows=[]), FakeResult(scalars=[]),
        ])
        with use_fake_session(session) as client:
            client.get("/ui/")

        # series_con_archivos (índice 1), issues_importados (índice 3),
        # y la subquery de últimas series (compilada dentro del SELECT
        # final, índice 6) son las tres consultas que cruzan con File.
        assert "is_missing" in session.statements[1]
        assert "is_missing" in session.statements[3]
        assert "is_missing" in session.statements[6]
