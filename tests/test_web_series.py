"""
tests/test_web_series.py

Suite de la ficha de serie mínima (C2) — /ui/series/{id}. Solo lo que
pide C2: presentes/ausentes correctos, sin el bug de sort_order truncado
(ya cubierto a nivel de cálculo en test_api_series.py; aquí se prueba
que la página los renderiza).
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource, Series, WishlistPolicy


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        # Un `select(func.count())` pasa el número directamente (no una lista),
        # así que `len()` no siempre está disponible.
        por_defecto = len(rows) if hasattr(rows, "__len__") else 0
        self.rowcount = rowcount if rowcount is not None else por_defecto

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar(self):
        """Para `select(func.count())` (D8, cuántos retirados): se pasa el
        número directamente, no una lista."""
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        """La consulta de números poseídos devuelve filas (número, formato,
        archivo disponible), no escalares."""
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


class CapturingSession(FakeSession):
    """Como FakeSession, pero guarda cada statement compilado — para
    verificar de verdad el WHERE que genera el código (B7: revisión de
    PR, 2026-09-26, sobre portada() eligiendo un File sin filtrar
    is_missing)."""

    def __init__(self, queue: list, series=None):
        super().__init__(queue, series)
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return await super().execute(statement)


def override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def make_series(total_issues=None, metadata_source=MetadataSource.COMIC_VINE.value) -> Series:
    """Comic Vine por defecto: es la única fuente cuyo `total_issues` está
    acreditado como recuento de grapas (ver `_UNIDAD_DE_GRAPA`)."""
    return Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                  total_issues=total_issues, start_year=1977,
                  metadata_source=metadata_source)


def acuse() -> FakeExecResult:
    """Fila del aviso legal aceptado — `_contexto_politica` lo consulta para no
    prometer búsquedas que el ciclo no va a hacer."""
    return FakeExecResult([object()])


def retirados(n: int = 0) -> FakeExecResult:
    """`select(func.count())` de items retirados (D8)."""
    return FakeExecResult(n)


class TestFichaSerie:

    def test_serie_inexistente_da_404(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.get(f"/ui/series/{uuid4()}")
        assert r.status_code == 404

    def test_muestra_huecos_y_presentes(self):
        series = make_series(total_issues=3)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([("1", "single_issue", True), ("3", "single_issue", True)]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "Thorgal" in r.text
        assert "#2" in r.text  # falta
        assert "#1" in r.text  # presente
        assert "#3" in r.text

    def test_regresion_annual_1_5_no_oculta_el_hueco_del_1(self):
        series = make_series(total_issues=2)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([("1.5", "single_issue", True)]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert "Te faltan" in r.text
        assert "#1" in r.text  # el 1.5 no lo cubre

    def test_omnibus_no_ocupa_el_hueco_de_la_grapa(self):
        """El ómnibus está en el catálogo, pero la grapa #12 sigue faltando."""
        series = make_series(total_issues=12)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([("12", "omnibus", True)]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert "Te faltan" in r.text
        assert "#12" in r.text

    def test_sin_total_issues_no_calcula_huecos(self):
        series = make_series(total_issues=None)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "no se puede calcular huecos" in r.text


class TestPoliticaBusquedaD8:
    """D8: el selector de la ficha de serie.

    La página no recalcula nada por su cuenta: el veredicto sale del mismo
    predicado que genera (`services/politica.querer_de_serie`), y el POST valida
    el valor contra una lista blanca — `todos` no se ofrece y `futuros` va
    deshabilitado con su motivo, pero además el servidor los rechaza.
    """

    def test_ficha_resume_los_numeros_que_buscara(self):
        """No lista un chip por número: resume el conteo y dice el tope por
        ciclo, que es lo que condiciona cuándo entrarán."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]),   # la serie
            FakeExecResult([]),         # poseídos (para pintar la ficha)
            FakeExecResult([]),         # manuales vivos (predicado)
            FakeExecResult([]),         # poseídos (predicado)
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert r.status_code == 200
        assert "Búsqueda automática" in r.text
        assert "Faltan 3 números" in r.text
        assert "25 por ciclo" in r.text

    def test_una_serie_larga_no_inunda_la_seccion(self):
        series = make_series(total_issues=200)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "Faltan 200 números" in r.text
        assert "politica-lista-corta" not in r.text

    def test_futuros_aparece_deshabilitado_con_su_motivo(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "Números que aún no han salido" in r.text
        assert "deshabilitado" in r.text
        assert "todavía no se puede aplicar" in r.text   # el motivo, visible

    def test_todos_no_se_ofrece(self):
        """Reservado hasta que D3 le dé significado: no es una opción que
        parezca funcionar y no haga nada."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert 'value="todos"' not in r.text

    def test_sin_poder_calcular_lo_dice(self):
        """No computable (AniList cuenta capítulos): se declara, no se inventa."""
        series = make_series(total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]),   # la serie
            FakeExecResult([]),         # poseídos (para pintar)
            FakeExecResult([]),         # manuales (predicado); huecos corta aquí
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "grapas" in r.text

    def test_manual_de_serie_vivo_lo_explica(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([(None, None)]),   # un item manual de serie vivo
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "no se generan números" in r.text

    def test_aviso_legal_pendiente_lo_dice(self):
        """Sin acuse el ciclo no genera ni busca: prometer búsquedas sin decirlo
        sería engañar."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            FakeExecResult([]),   # sin acuse
            retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "aviso legal está pendiente" in r.text

    def test_muestra_cuantos_retirados_hay(self):
        """El listado de deseos oculta los retirados: la ficha tiene que decir
        cuántos hay para que no desaparezcan sin rastro."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.NONE
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]), acuse(), retirados(4),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "4 números retirados" in r.text

    def test_cambiar_a_faltantes_por_la_ui(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.NONE
        session = FakeSession([
            FakeExecResult([series]),   # búsqueda de la serie en el POST
            FakeExecResult([]),         # manuales (predicado)
            FakeExecResult([]),         # poseídos (predicado)
            FakeExecResult([], rowcount=0),   # retirada (no hay nada que retirar)
            acuse(), retirados(),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/politica",
                            data={"wishlist_policy": "faltantes"})

        assert r.status_code == 200
        assert series.wishlist_policy == WishlistPolicy.MISSING
        assert "Faltan 3 números" in r.text

    def test_pasar_a_ninguno_retira_al_momento(self):
        """Efecto asimétrico (revisión de PR): la generación espera al ciclo,
        pero la retirada se aplica al guardar — cuando el coleccionista pide
        parar, no puede seguir buscándose hasta una hora."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]),                 # la serie
            FakeExecResult([], rowcount=2),           # la retirada inmediata
            acuse(),                                  # contexto (predicado NONE: sin consultas)
            retirados(5),                             # total acumulado de la serie
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/politica",
                            data={"wishlist_policy": "ninguno"})

        assert r.status_code == 200
        assert series.wishlist_policy == WishlistPolicy.NONE
        # Lo retirado AHORA y el acumulado se dicen por separado: confundirlos
        # mostraría «2» cuando en la serie ya había 3 más.
        assert "Se han retirado 2 números" in r.text
        assert "5 números retirados" in r.text

    @pytest.mark.parametrize("reservada", ["futuros", "todos"])
    def test_la_ui_rechaza_los_valores_reservados(self, reservada):
        """El `<select>` ya no los ofrece, pero un formulario manipulado
        tampoco los puede fijar."""
        series = make_series()
        with use_fake_session(FakeSession([FakeExecResult([series])])) as client:
            r = client.post(f"/ui/series/{series.id}/politica",
                            data={"wishlist_policy": reservada})

        assert r.status_code == 422
        assert series.wishlist_policy != WishlistPolicy.FUTURE

    def test_la_ui_rechaza_un_valor_inventado(self):
        series = make_series()
        with use_fake_session(FakeSession([FakeExecResult([series])])) as client:
            r = client.post(f"/ui/series/{series.id}/politica",
                            data={"wishlist_policy": "lo_que_sea"})

        assert r.status_code == 422

    def test_serie_inexistente_da_404(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.post(f"/ui/series/{uuid4()}/politica",
                            data={"wishlist_policy": "faltantes"})

        assert r.status_code == 404


class TestPortada:
    """B7 (revisión de PR, 2026-09-26): la cascada de portada elegía el
    primer File por sort_order sin comprobar is_missing — podía intentar
    (y fallar) extraer de un CBZ ya borrado en vez de probar el
    siguiente número disponible."""

    def test_consulta_de_candidato_filtra_is_missing(self, tmp_path, monkeypatch):
        from zascarr.config import get_settings

        series = make_series()
        series.cover_url = None
        settings = get_settings().model_copy(update={"covers_cache_path": tmp_path})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)

        session = CapturingSession([FakeExecResult([])], series=series)
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 404
        assert "is_missing" in session.statements[0]
