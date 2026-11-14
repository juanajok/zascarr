# ruff: noqa: E501
"""
tests/test_web_series.py

Suite de la ficha de serie mínima (C2) — /ui/series/{id}. Solo lo que
pide C2: presentes/ausentes correctos, sin el bug de sort_order truncado
(ya cubierto a nivel de cálculo en test_api_series.py; aquí se prueba
que la página los renderiza).
"""
from __future__ import annotations

import re
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

    def scalar_one(self):
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
        # Cola ESTRICTA: si una ruta pide una consulta no declarada, falla.
        self._queue = list(queue)
        self._series = series
        self.flush = AsyncMock()
        self.added = []

    def add(self, objeto):
        self.added.append(objeto)

    async def execute(self, statement):
        # Las colecciones de la ficha se cargan en un fragmento aparte; si una
        # prueba antigua no lo declara, la consulta de pertenencia va vacía.
        if "collection_series" in str(statement):
            return FakeExecResult([])
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


def use_fake_session(session, *, ficha=True):
    # Las tres lecturas fijas de la ficha (#447) se declaran aquí, en el borde del test,
    # para que la sesión siga siendo estricta y una consulta inesperada falle.
    if ficha:
        session._queue.extend([FakeExecResult([]), FakeExecResult([]), FakeExecResult([]),
                               FakeExecResult([]), FakeExecResult([]), FakeExecResult([])])
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


def sin_otras(otras: int = 0) -> list[FakeExecResult]:
    """Las dos consultas de la cota (C6, N): números de ESTA serie ya buscándose/descargándose y deseos pendientes de las
    DEMÁS series con política. Solo se hacen con política activa, sin aviso pendiente, R > 0 y números que faltan."""
    return [FakeExecResult([]), FakeExecResult(otras)]


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
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "Thorgal" in r.text
        assert "#2" in r.text  # falta
        assert "#1" in r.text  # presente
        assert "#3" in r.text

    def test_enlace_anadir_numeros_del_disco(self):
        series = make_series(total_issues=3)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert f'href="/ui/pendientes/carpetas?serie={series.id}"' in r.text
        assert "Añadir números del disco" in r.text
        assert "Vincular no mueve ni renombra el archivo." in r.text

    def test_regresion_annual_1_5_no_oculta_el_hueco_del_1(self):
        series = make_series(total_issues=2)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([("1.5", "single_issue", True)]),
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "no se puede calcular huecos" in r.text


    def test_sin_poder_calcular_huecos_no_dice_que_este_completa(self):
        """Caso real (2026-10-20): 8 de 30 con un total que no cuenta grapas decía «Ningún hueco —
        la tienes completa». Sin cálculo fiable no hay «completa» ni «0 te faltan»."""
        series = make_series(total_issues=30, metadata_source=MetadataSource.ANILIST.value)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([("1", "single_issue", True), ("2", "single_issue", True)]),
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "la tienes completa" not in r.text
        assert "te faltan" not in r.text and "Te faltan" not in r.text
        assert "30 números según la fuente — 2 en tu biblioteca." in r.text
        assert ("No sabemos cuáles faltan: el total de la serie no consta como número de grapas"
                in r.text)

    def test_completa_solo_si_se_pudo_calcular(self):
        series = make_series(total_issues=2)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([("1", "single_issue", True), ("2", "single_issue", True)]),
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert "Ningún hueco — la tienes completa." in r.text
        assert "0 te faltan." in r.text


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
            acuse(), *sin_otras(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert r.status_code == 200
        assert "Búsqueda automática" in r.text
        assert "Faltan 3 números" in r.text
        assert "por ciclo" not in r.text and "25" not in re.sub(r"<[^>]+>", " ", r.text.split('id="politica-serie"', 1)[1])
        assert "unos 2 por hora como máximo" in r.text

    def test_una_serie_larga_no_inunda_la_seccion(self):
        series = make_series(total_issues=200)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            acuse(), *sin_otras(), retirados(), FakeExecResult([]),
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
            acuse(), *sin_otras(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "Números que aún no han salido" in r.text
        assert "todavía no disponible" in r.text   # la propia opción avisa, en llano
        assert "Todavía no se puede elegir" in r.text   # el motivo, en el detalle plegado
        visible = re.sub(r"<[^>]+>", " ", r.text.split('id="politica-serie"', 1)[1].split("politica-veredicto", 1)[0])
        assert "futuros" not in visible   # sin el valor interno a la vista

    def test_todos_no_se_ofrece(self):
        """Reservado hasta que D3 le dé significado: no es una opción que
        parezca funcionar y no haga nada."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            acuse(), *sin_otras(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "deseo de toda la serie" in r.text
        assert "Quítalo de la lista de deseos" in r.text

    def test_aviso_legal_pendiente_lo_dice(self):
        """Sin acuse el ciclo no genera ni busca: prometer búsquedas sin decirlo
        sería engañar."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            FakeExecResult([]), FakeExecResult([]),
            FakeExecResult([]),   # sin acuse
            retirados(), FakeExecResult([]),
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
            FakeExecResult([series]), FakeExecResult([]), acuse(), retirados(4), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")

        assert "4 números dejados de buscar por la política" in r.text

    def test_cambiar_a_faltantes_por_la_ui(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.NONE
        session = FakeSession([
            FakeExecResult([series]),   # búsqueda de la serie en el POST
            acuse(),                    # puerta legal (solo al ACTIVAR): se consulta una vez y se reutiliza
            FakeExecResult([]),         # manuales (predicado)
            FakeExecResult([]),         # poseídos (predicado)
            FakeExecResult([], rowcount=0),   # retirada (no hay nada que retirar)
            *sin_otras(),                     # cota: lo ya buscándose y las demás series
            retirados(),
        ])
        with use_fake_session(session, ficha=False) as client:
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
        with use_fake_session(session, ficha=False) as client:
            r = client.post(f"/ui/series/{series.id}/politica",
                            data={"wishlist_policy": "ninguno"})

        assert r.status_code == 200
        assert series.wishlist_policy == WishlistPolicy.NONE
        # Lo retirado AHORA y el acumulado se dicen por separado: confundirlos
        # mostraría «2» cuando en la serie ya había 3 más.
        assert "Se han dejado de buscar 2 números que estaban por buscar o sin resultados" in r.text
        assert "Lo que ya se estaba buscando o descargando termina" in r.text
        assert "5 números dejados de buscar por la política" in r.text

    def test_pasar_a_ninguno_con_un_solo_numero_usa_el_singular(self):
        """AC-03: el singular también se fija (la rama de `retirados_ahora == 1` de la plantilla)."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]), FakeExecResult([], rowcount=1), acuse(), retirados(1),
        ])
        with use_fake_session(session, ficha=False) as client:
            r = client.post(f"/ui/series/{series.id}/politica",
                            data={"wishlist_policy": "ninguno"})

        texto = " ".join(re.sub(r"<[^>]+>", " ", r.text).split())
        assert ("Se ha dejado de buscar 1 número que estaba por buscar o sin resultados. "
                "Lo que ya se estaba buscando o descargando termina.") in texto
        assert "aún no había empezado" not in texto and "Se han dejado de buscar 1 " not in texto

    def test_activar_politica_sin_aviso_no_escribe_nada(self):
        """C6 / FR-20: sin el aviso legal aceptado, ACTIVAR no escribe (ni la política ni la retirada) y responde con el
        fragmento SIN CAMBIOS, el aviso y el enlace a /ui/legal. Es 200 (htmx no intercambia los 4xx)."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.NONE
        session = FakeSession([
            FakeExecResult([series]),   # la serie
            FakeExecResult([]),         # puerta legal: SIN acuse
            retirados(),                # contexto del fragmento sin cambios (predicado NONE: sin más consultas)
        ])
        with use_fake_session(session, ficha=False) as client:
            r = client.post(f"/ui/series/{series.id}/politica", data={"wishlist_policy": "faltantes"})

        assert r.status_code == 200
        assert series.wishlist_policy == WishlistPolicy.NONE          # no se activó
        session.flush.assert_not_called()                             # y no se escribió nada
        assert session._queue == []                                   # ni se hizo la retirada (no hay más consultas)
        assert "No se ha activado: antes tienes que aceptar el aviso legal." in r.text
        assert 'href="/ui/legal"' in r.text
        assert "dejado de buscar" not in r.text

    def test_desactivar_politica_sin_aviso_si_funciona(self):
        """C6 / FR-21: desactivar nunca exige el aviso legal."""
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([], rowcount=2),   # retirada inmediata
            FakeExecResult([]),               # contexto: sin acuse (no se consultó antes para desactivar)
            retirados(2),
        ])
        with use_fake_session(session, ficha=False) as client:
            r = client.post(f"/ui/series/{series.id}/politica", data={"wishlist_policy": "ninguno"})

        assert r.status_code == 200
        assert series.wishlist_policy == WishlistPolicy.NONE
        assert "Se han dejado de buscar 2 números que estaban por buscar o sin resultados" in r.text
        assert "No se ha activado" not in r.text and 'href="/ui/legal"' not in r.text   # desactivar nunca choca con el aviso

    def test_activar_con_aviso_aceptado_sigue_funcionando_y_no_enlaza_la_pantalla_legal(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.NONE
        session = FakeSession([FakeExecResult([series]), acuse(), FakeExecResult([]), FakeExecResult([]),
                               FakeExecResult([], rowcount=0), *sin_otras(), retirados()])
        with use_fake_session(session, ficha=False) as client:
            r = client.post(f"/ui/series/{series.id}/politica", data={"wishlist_policy": "faltantes"})
        assert r.status_code == 200 and series.wishlist_policy == WishlistPolicy.MISSING
        assert 'href="/ui/legal"' not in r.text

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


class TestPresupuestoTextoU21:
    """U21 (#208): la ficha de serie también cumple el presupuesto de texto.

    La acción principal es el selector de política, no el enlace de vuelta ni
    el desplegable de fuentes: se mide el texto visible anterior a
    `#wishlist_policy`. El detalle de fuentes se excluye como contenido
    plegado.
    """

    def _render(self) -> str:
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
            FakeExecResult([]),
            FakeExecResult([]),
            acuse(), *sin_otras(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        main = re.search(r"<main\b[^>]*>(.*?)</main>", r.text, re.S)
        assert main is not None
        return main.group(1)

    @staticmethod
    def _texto(fragmento: str) -> str:
        return re.sub(r"<[^>]+>", " ", fragmento)

    def test_entrada_y_accion_principal_cumplen_el_umbral(self):
        html = self._render()
        entrada = re.search(r'<p class="series-intro">(.*?)</p>', html, re.S)
        assert entrada is not None
        assert self._texto(entrada.group(1)).strip() == (
            "Consulta tus números y ajusta la búsqueda automática."
        )
        assert len(re.findall(r"\w+", self._texto(entrada.group(1)))) <= 20

        antes = html.split('id="wishlist_policy"', 1)[0]
        # Presupuesto explícito de #304: .series-acciones tiene su propio límite
        # (test_presupuesto_de_la_accion_nueva); este cómputo mide la entrada de #208.
        antes = re.sub(r'<p class="series-acciones">.*?</p>', '', antes, flags=re.S)
        # BL-INF1 (#447): el bloque informativo va después de la cabecera y no compite
        # con el presupuesto de la entrada de #208.
        antes = re.sub(r'<section class="ficha-serie-datos".*?</section>', '', antes, flags=re.S)
        # BL-INF6: «Elegir portada» es un CONTROL de acción (abre el selector), como los botones de
        # `.series-acciones`: no es texto de entrada y no compite con el presupuesto de #208.
        antes = re.sub(r'<details class="elegir-portada".*?</details>', '', antes, flags=re.S)
        # El contenido de un <details> cerrado no cuenta, pero su <summary>
        # visible sí (contrato de medición de #208).
        antes = re.sub(
            r"<details\b[^>]*>\s*(<summary>.*?</summary>).*?</details>",
            r"\1",
            antes,
            flags=re.S,
        )
        palabras = re.findall(r"\w+", self._texto(antes))
        assert len(palabras) <= 50, (len(palabras), " ".join(palabras))

    def test_presupuesto_de_la_accion_nueva(self):
        html = self._render()
        accion = re.search(r'<p class="series-acciones">(.*?)</p>', html, re.S)
        assert accion is not None
        palabras = re.findall(r"\w+", self._texto(accion.group(1)))
        assert len(palabras) <= 24, (len(palabras), " ".join(palabras))
        assert "Añadir números del disco" in self._texto(accion.group(1))

    def test_la_accion_va_antes_que_el_listado(self):
        html = self._render()
        assert html.index('id="wishlist_policy"') < html.index("Te faltan")

    def test_las_fuentes_van_plegadas_y_no_se_pierden(self):
        html = self._render()
        detalle = re.search(
            r'<details class="series-fuentes">(.*?)</details>', html, re.S
        )
        assert detalle is not None
        assert "<summary>Fuentes y atribución</summary>" in detalle.group(1)
        assert "Los metadatos de esta ficha proceden de fuentes de terceros" in detalle.group(1)
        assert "Fuentes y atribución" not in html.split('id="politica-serie"', 1)[0].replace(
            "<summary>Fuentes y atribución</summary>", ""
        )

    def test_la_garantia_va_junto_al_selector_y_no_al_final(self):
        html = self._render()
        pos_select = html.index('id="wishlist_policy"')
        pos_efecto = html.index("politica-efecto")
        pos_veredicto = html.index("politica-veredicto")
        assert pos_select < pos_efecto < pos_veredicto
        assert "Se guarda al elegir. Si dejas de completar, lo ya empezado termina." in html
        assert "Guardar aplica la retirada" not in html

    def test_la_nota_de_futuros_va_junto_al_selector(self):
        html = self._render()
        assert html.index('id="wishlist_policy"') < html.index("politica-futuros")
        assert html.index("politica-futuros") < html.index("politica-veredicto")
        assert "Todavía no se puede elegir" in html

    def _bloque_politica(self) -> str:
        html = self._render()
        inicio = html.index('id="politica-serie"')
        return html[inicio:html.index("politica-veredicto", inicio)]

    def test_u21_una_sola_nota_visible_junto_al_selector_y_el_resto_plegado(self):
        """#296, criterio 1: entre el selector y el veredicto solo hay UNA nota fuera del `<details>`. «Una línea» se
        entiende como «una sola nota»: en el móvil (≈ 40 caracteres por renglón) puede ocupar dos renglones."""
        bloque = self._bloque_politica()
        fuera = re.sub(r"<details\b.*?</details>", "", bloque, flags=re.S)
        notas = re.findall(r'<p\b[^>]*\bclass="[^"]*\bpolitica-efecto\b[^"]*"[^>]*>(.*?)</p>', fuera, re.S)
        assert len(notas) == 1, notas
        linea = " ".join(self._texto(notas[0]).split())
        assert linea == "Se guarda al elegir. Si dejas de completar, lo ya empezado termina."
        assert len(linea) <= 80   # U21: una sola nota; puede ocupar dos renglones en móvil
        assert 'id="politica-futuros"' not in fuera   # el motivo va plegado (el selector solo lo referencia por aria-describedby)
        assert 'class="caption' not in fuera   # ya no hay cajas de aviso junto al selector (era el problema de #296)

    def test_u21_el_detalle_plegado_nombra_lo_que_contiene_y_lleva_el_motivo(self):
        bloque = self._bloque_politica()
        detalle = re.search(r'<details class="politica-detalles">(.*?)</details>', bloque, re.S)
        assert detalle is not None
        assert "<summary>¿Por qué una opción no se puede elegir?</summary>" in detalle.group(1)
        assert 'class="politica-detalles" open' not in bloque   # plegado de entrada
        plano = " ".join(self._texto(detalle.group(1)).split())
        assert ("Todavía no se puede elegir «Números que aún no han salido»: las fuentes de datos no avisan de los "
                "números antes de que salgan.") in plano
        assert plano.count(":") == 1   # un solo «:» en la frase (antes había dos encadenados)
        assert "futuros" not in plano and "política" not in plano   # ni el valor interno ni jerga

    def test_u21_futuros_sigue_deshabilitado_y_su_motivo_esta_en_el_detalle(self):
        """#296, criterio 2. El portador accesible del motivo es el `<details>`: el `title` de la `<option>` no se muestra
        en los selectores nativos del móvil ni lo anuncian de forma fiable los lectores de pantalla; se conserva por si
        ayuda, pero la prueba no lo da por suficiente."""
        bloque = self._bloque_politica()
        opcion = re.search(r'<option value="futuros"[^>]*>\s*(.*?)\s*</option>', bloque, re.S)
        assert opcion is not None and " disabled" in opcion.group(0)
        assert "Números que aún no han salido (todavía no disponible)" in " ".join(opcion.group(1).split())
        assert "deshabilitado" not in opcion.group(0)
        assert 'id="politica-futuros"' in bloque and "Todavía no se puede elegir" in bloque

    def test_u21_el_selector_esta_descrito_por_la_garantia_y_por_el_motivo(self):
        """Comprueba que aria-describedby referencia la garantía y el motivo mediante ids existentes y únicos.
        El anuncio efectivo con el detalle plegado requiere validación con lector de pantalla y sigue como NOT RUN."""
        bloque = self._bloque_politica()
        selector = re.search(r'<select\b[^>]*>', bloque)
        assert selector is not None
        ids = re.search(r'aria-describedby="([^"]+)"', selector.group(0)).group(1).split()
        assert set(ids) == {"politica-efecto", "politica-futuros"}
        for i in ids:
            assert len(re.findall(rf'\bid="{i}"', bloque)) == 1, f"el id {i} falta o está duplicado"

    def test_u21_no_se_pierde_que_guardar_es_inmediato(self):
        plano = " ".join(self._texto(self._bloque_politica()).split())
        assert "Se guarda al elegir" in plano and "lo ya empezado termina" in plano

    def test_ningun_parrafo_visible_va_en_mayusculas(self):
        html = self._render()
        for fragmento in re.findall(r"<p\b[^>]*>(.*?)</p>", html, re.S):
            texto = self._texto(fragmento).strip()
            letras = [c for c in texto if c.isalpha()]
            if len(letras) < 3:
                continue
            assert not all(c.isupper() for c in letras), texto


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


class TestPortadaDeRelleno:
    """#311: una serie que guardó la imagen de relleno de Comic Vine como `cover_url` (antes del arreglo)
    no la descarga ni la muestra: la tarjeta cae a su hueco propio (404 → `.cover-missing`)."""

    def test_el_relleno_guardado_no_se_descarga_ni_se_sirve(self, tmp_path, monkeypatch):
        from zascarr.config import get_settings

        series = make_series()
        series.cover_url = "https://comicvine.gamespot.com/a/uploads/scale_medium/11122/111222211/6373148-blank.png"
        settings = get_settings().model_copy(update={"covers_cache_path": tmp_path})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        descargas = []

        async def falsa(url, destino):
            descargas.append(url)
            return True
        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", falsa)

        session = CapturingSession([FakeExecResult([])], series=series)
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 404
        assert descargas == []


class TestTextosC6:
    """C6 (PR 2): qué entiende la persona en la ficha de serie.

    Cubre la cota (FR-09/10, ★1/★2), R=0 y aviso legal (FR-27/29), el motivo
    con nombre público y el dato técnico plegado (FR-11/26), y el efecto
    diferido (FR-13). Los textos exactos son los del Anexo A de la v1.5.
    """

    @staticmethod
    def _render(series, queue):
        session = FakeSession(queue)
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        return r.text

    def _ficha(self, series, *, computable=True, acuse_=True, cota=False, otras=0):
        queue = [FakeExecResult([series]), FakeExecResult([]), FakeExecResult([])]
        if computable:
            queue.append(FakeExecResult([]))
        queue.append(acuse() if acuse_ else FakeExecResult([]))
        if cota:
            queue.extend(sin_otras(otras))
        queue.extend([retirados(), FakeExecResult([])])
        return self._render(series, queue)

    @staticmethod
    def _bloque(html):
        return html.split('id="politica-serie"', 1)[1]

    def test_cota_una_hora(self):
        series = make_series(total_issues=1)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=True))
        assert "Falta 1 número." in bloque
        assert "unos 2 por hora como máximo" in bloque
        assert "(ahora, 1 por buscar)" in bloque
        assert "una hora" in bloque

    def test_cota_en_horas(self):
        series = make_series(total_issues=5)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=True))
        assert "Faltan 5 números." in bloque
        assert "unas 3 horas" in bloque

    def test_cota_limite_48_horas(self):
        series = make_series(total_issues=96)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=True))
        assert "unas 48 horas" in bloque

    def test_cota_salta_a_dias_hacia_abajo(self):
        series = make_series(total_issues=97)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=True))
        assert "unos 2 días" in bloque
        assert "3 días" not in bloque

    def test_cota_cuenta_las_otras_series(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=True, otras=7))
        assert "(ahora, 10 por buscar)" in bloque
        assert "unas 5 horas" in bloque

    def test_r_cero_no_promete_busquedas(self, monkeypatch):
        from zascarr.config import get_settings

        settings = get_settings().model_copy(update={"politica_busquedas_por_hora": 0})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=False))
        assert "desactivadas" in bloque
        assert "por hora" not in bloque
        assert "instalación" not in bloque

    def test_aviso_legal_tiene_precedencia_sobre_la_cota(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, acuse_=False, cota=False))
        assert "No se buscará ninguno hasta que aceptes el aviso legal." in bloque
        assert "por hora" not in bloque

    def test_motivo_con_nombre_publico_y_dato_tecnico_plegado(self):
        series = make_series(total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        series.wishlist_policy = WishlistPolicy.MISSING
        html = self._ficha(series, computable=False)
        bloque = self._bloque(html)
        assert "(viene de AniList)" in bloque
        assert "Ver el dato técnico" in bloque
        assert "Fuente registrada: <code>anilist</code>" in bloque
        sin_detalles = re.sub(r"<details\b.*?</details>", "", bloque, flags=re.S)
        assert "viene de AniList" in sin_detalles
        assert "<code>anilist</code>" not in sin_detalles

    def test_motivo_sin_total_no_lleva_dato_tecnico(self):
        series = make_series(total_issues=None)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False))
        assert "no tiene un total de números conocido" in bloque
        assert "Ver el dato técnico" not in bloque

    def test_motivo_sin_fuente_no_lleva_dato_tecnico(self):
        series = make_series(total_issues=120, metadata_source="fuente-rara")
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False))
        assert "(sin fuente)" in bloque
        assert "Ver el dato técnico" not in bloque

    def test_motivo_alta_a_mano(self):
        series = make_series(total_issues=120, metadata_source=MetadataSource.MANUAL.value)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False))
        assert "(alta a mano)" in bloque
        assert "Fuente registrada: <code>manual</code>" in bloque

    def test_efecto_diferido_sin_nombrar_la_fuente(self, monkeypatch):
        from zascarr.config import get_settings

        settings = get_settings().model_copy(update={"comicvine_enabled": True})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        series = make_series(total_issues=120, metadata_source=None)
        series.tradition = ComicTradition.AMERICAN
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False))
        assert "Si llega a conocerse el total" in bloque
        assert "Comic Vine" not in bloque

    def test_cabecera_y_un_solo_dato_tecnico(self):
        series = make_series(total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        series.wishlist_policy = WishlistPolicy.MISSING
        html = self._ficha(series, computable=False)
        assert "No sabemos cuáles faltan:" in html
        assert "(viene de AniList)" in html
        assert html.count("Ver el dato técnico") == 1

    def test_politica_ninguno_no_pinta_el_dato_tecnico(self):
        series = make_series(total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        series.wishlist_policy = WishlistPolicy.NONE
        html = self._render(
            series,
            [FakeExecResult([series]), FakeExecResult([]), acuse(), retirados(), FakeExecResult([])],
        )
        assert "En esta serie, «completar» tampoco podría buscar nada" in html
        assert "Ver el dato técnico" not in html

    def test_r_uno_usa_el_singular_del_anexo(self, monkeypatch):
        from zascarr.config import get_settings

        settings = get_settings().model_copy(update={"politica_busquedas_por_hora": 1})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        series = make_series(total_issues=1)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, cota=True))
        assert "un número por hora como máximo" in bloque
        assert "unos 1" not in bloque

    def test_el_aviso_legal_pendiente_gana_a_r_cero(self, monkeypatch):
        """Precedencia (FR-29): con el aviso sin aceptar y R = 0, se dice lo del aviso, no lo de R = 0."""
        from zascarr.config import get_settings

        settings = get_settings().model_copy(update={"politica_busquedas_por_hora": 0})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, acuse_=False, cota=False))
        assert "No se buscará ninguno hasta que aceptes el aviso legal." in bloque
        assert "desactivadas" not in bloque

    def test_el_efecto_diferido_no_se_promete_con_el_aviso_legal_pendiente(self, monkeypatch):
        """Sin aviso aceptado no habrá búsquedas aunque llegue el total: no se promete que ZascArr buscará."""
        from zascarr.config import get_settings

        settings = get_settings().model_copy(update={"comicvine_enabled": True})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        series = make_series(total_issues=120, metadata_source=None)
        series.tradition = ComicTradition.AMERICAN
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False, acuse_=False))
        assert "Si llega a conocerse el total" not in bloque

    def test_el_efecto_diferido_no_se_promete_con_r_cero(self, monkeypatch):
        """Con R = 0 ZascArr no buscará nada aunque llegue el total: no se promete."""
        from zascarr.config import get_settings

        settings = get_settings().model_copy(
            update={"comicvine_enabled": True, "politica_busquedas_por_hora": 0})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
        series = make_series(total_issues=120, metadata_source=None)
        series.tradition = ComicTradition.AMERICAN
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False))
        assert "Si llega a conocerse el total" not in bloque

    def test_sin_numeros_que_faltan_el_aviso_legal_no_habla_de_faltantes(self):
        """V6: el aviso legal solo gana con algo que buscar (`k >= 1`); con k = 0 se enseña el motivo y no
        «Faltan 0 números. No se buscará ninguno…»."""
        series = make_series(total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        series.wishlist_policy = WishlistPolicy.MISSING
        bloque = self._bloque(self._ficha(series, computable=False, acuse_=False))
        assert "(viene de AniList)" in bloque
        assert "Faltan 0" not in bloque and "No se buscará ninguno hasta que aceptes" not in bloque

class TestProcedenciaCamposC6:
    """#127: el bloque de procedencia no inventa origen ni expone ids internos."""

    def test_la_ficha_muestra_procedencia_y_bloqueo(self):
        series = make_series(total_issues=3)
        series.metadata_source = "comic_vine"
        # 987654, no 777: un UUID aleatorio puede contener «777» y hacía
        # fallar la aserción de que el id externo no se pinta.
        series.metadata_ = {"alta": {"origen": "descubrir", "fuente": "comic_vine",
                                     "id_externo": "987654", "fecha": "2026-11-06T10:00:00+00:00"}}
        series.comic_vine_id = 987654
        series.locked_fields = ["comic_vine_id"]
        session = FakeSession([FakeExecResult([series]), FakeExecResult([]), acuse(),
                               retirados(), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "De dónde sale cada dato" in r.text
        assert "Alta desde Comic Vine" in r.text
        assert "Protegido: el enriquecimiento no lo sobrescribe." in r.text
        assert "Protegido</strong> significa que el enriquecimiento no lo sobrescribe." in r.text
        assert "Identificador de la fuente" in r.text
        assert "987654" not in r.text   # el id externo no se pinta

    def test_sin_procedencia_lo_dice_en_vez_de_atribuir(self):
        series = make_series(total_issues=3)
        series.metadata_source = None
        session = FakeSession([FakeExecResult([series]), FakeExecResult([]), acuse(),
                               retirados(), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert "Origen no registrado" in r.text
        assert "No hay procedencia registrada" in r.text
        assert "significa que el enriquecimiento no lo sobrescribe" not in r.text
        assert "significa que lo has escrito tú" not in r.text


class TestVolverALaBiblioteca:
    """BL-IT03 (#286): vuelta al contexto o a Biblioteca, nunca a un destino abierto."""

    def _get(self, series, volver=None):
        params = {} if volver is None else {"volver": volver}
        session = FakeSession([FakeExecResult([series]), FakeExecResult([]), acuse(),
                               retirados(), FakeExecResult([])])
        with use_fake_session(session) as client:
            return client.get(f"/ui/series/{series.id}", params=params)

    def test_con_contexto_valido_vuelve_a_la_biblioteca(self):
        series = make_series(total_issues=3)
        destino = f"/ui/biblioteca?q=thor&page=2#serie-{series.id}"
        r = self._get(series, destino)
        assert r.status_code == 200
        assert 'href="/ui/biblioteca?q=thor&amp;page=2#serie-' in r.text
        assert "Volver a la biblioteca" in r.text

    def test_desde_una_coleccion_vuelve_a_la_coleccion(self):
        series = make_series(total_issues=3)
        destino = f"/ui/colecciones/{uuid4()}"
        r = self._get(series, destino)
        assert r.status_code == 200
        assert f'href="{destino}" class="back-link"' in r.text
        assert "Volver a la colección" in r.text


    def test_sin_contexto_ofrece_biblioteca_sin_inventar_busqueda(self):
        series = make_series(total_issues=3)
        r = self._get(series)
        assert r.status_code == 200
        assert 'href="/ui/biblioteca" class="back-link"' in r.text
        assert "← Biblioteca" in r.text

    def test_un_contexto_externo_o_manipulado_cae_a_biblioteca(self):
        series = make_series(total_issues=3)
        for valor in ("https%3A%2F%2Fevil.example", "%2F%2Fevil.example", "javascript%3Aalert(1)"):
            r = self._get(series, valor)
            assert r.status_code == 200
            assert 'href="/ui/biblioteca" class="back-link"' in r.text
            assert "evil" not in r.text and "javascript:" not in r.text

    def test_dos_contextos_distintos_no_se_mezclan(self):
        series = make_series(total_issues=3)
        uno = f"/ui/biblioteca?q=uno&page=1#serie-{series.id}"
        dos = f"/ui/biblioteca?q=dos&page=2#serie-{series.id}"
        r1 = self._get(series, uno)
        r2 = self._get(series, dos)
        assert "q=uno&amp;page=1" in r1.text and "q=dos" not in r1.text
        assert "q=dos&amp;page=2" in r2.text and "q=uno" not in r2.text

    def test_un_volver_demasiado_largo_cae_a_biblioteca_sin_422(self):
        series = make_series(total_issues=3)
        r = self._get(series, "/ui/biblioteca?q=" + "x" * 2100)
        assert r.status_code == 200
        assert 'href="/ui/biblioteca" class="back-link"' in r.text
        assert "← Biblioteca" in r.text

    def test_un_ancla_de_otra_serie_cae_a_biblioteca(self):
        series = make_series(total_issues=3)
        otra = uuid4()
        r = self._get(series, f"/ui/biblioteca?page=1#serie-{otra}")
        assert r.status_code == 200
        assert 'href="/ui/biblioteca" class="back-link"' in r.text

    def test_desde_la_vista_lista_vuelve_a_la_lista(self):
        series = make_series(total_issues=3)
        destino = f"/ui/biblioteca?vista=lista&page=2#serie-{series.id}"
        r = self._get(series, destino)
        assert r.status_code == 200
        assert "vista=lista&amp;page=2#serie-" in r.text
        assert "Volver a la biblioteca" in r.text


class TestEnriquecimientoEnFicha:
    """#128: la ficha ofrece revisar la propuesta, pero no la aplica sola."""

    def test_la_ficha_ofrece_revisar_los_cambios(self):
        series = make_series(total_issues=3)
        session = FakeSession([FakeExecResult([series]), FakeExecResult([]), acuse(),
                               retirados(), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "Revisar cambios de datos" in r.text
        assert f'action="/ui/series/{series.id}/enriquecimiento/previsualizar"' in r.text
        assert "No se aplica nada hasta que lo confirmes" in r.text


class TestEstadoColeccionWK2:
    """#340/BL-WK2: decisión reversible y exclusión de faltas en la ficha."""

    def test_marcar_no_completar_guarda_jsonb_sin_tocar_politica(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.NONE
        session = FakeSession([FakeExecResult([series]), FakeExecResult([series.id])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/coleccion",
                            data={"accion": "no_completar", "version": "0"},
                            follow_redirects=False)
        assert r.status_code == 303
        assert "coleccion=guardado" in r.headers["location"]
        assert series.wishlist_policy == WishlistPolicy.NONE

    def test_conflicto_d8_no_escribe_y_pide_confirmacion(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/coleccion",
                            data={"accion": "no_completar"}, follow_redirects=False)
        assert r.status_code == 303
        assert "coleccion=conflicto" in r.headers["location"]
        assert not (series.metadata_ or {}).get("coleccion")
        assert series.wishlist_policy == WishlistPolicy.MISSING

    def test_confirmar_conflicto_guarda_sin_cambiar_politica(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.ALL
        session = FakeSession([FakeExecResult([series]), FakeExecResult([series.id])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/coleccion",
                            data={"accion": "no_completar", "confirmar": "si", "version": "0"},
                            follow_redirects=False)
        assert r.status_code == 303
        assert "coleccion=guardado" in r.headers["location"]
        assert series.wishlist_policy == WishlistPolicy.ALL

    def test_revertir_deshace_la_decision_sin_tocar_politica(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        series.metadata_ = {"coleccion": {"no_completar": True, "version": 1}}
        session = FakeSession([FakeExecResult([series]), FakeExecResult([series.id])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/coleccion",
                            data={"accion": "revertir", "version": "1"},
                            follow_redirects=False)
        assert r.status_code == 303
        assert "coleccion=revertido" in r.headers["location"]
        assert series.wishlist_policy == WishlistPolicy.MISSING

    def test_version_obsoleta_redirige_a_ficha_con_layout(self):
        series = make_series(total_issues=3)
        session = FakeSession([FakeExecResult([series]), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{series.id}/coleccion",
                            data={"accion": "no_completar", "version": "0"},
                            follow_redirects=False)
        assert r.status_code == 303
        assert "coleccion=conflicto_version" in r.headers["location"]
        assert not (series.metadata_ or {}).get("coleccion")

        # La redirección vuelve a la ficha completa (no un partial), con foco.
        session2 = FakeSession([
            FakeExecResult([series]), FakeExecResult([]),
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session2) as client:
            ficha = client.get(r.headers["location"])
        assert ficha.status_code == 200
        assert "<html" in ficha.text and "<body" in ficha.text
        assert "Otra pestaña cambió esta serie" in ficha.text
        assert 'id="coleccion-serie"' in ficha.text and "tabindex=\"-1\" autofocus" in ficha.text
        assert ficha.text.count("autofocus") == 1

    def test_conflicto_d8_se_explica_y_ofrece_confirmacion(self):
        series = make_series(total_issues=3)
        series.wishlist_policy = WishlistPolicy.MISSING
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
            FakeExecResult([]),
            FakeExecResult([]),
            acuse(), *sin_otras(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}?coleccion=conflicto")
        assert r.status_code == 200
        assert "la política no se cambia sola" in r.text
        assert "Sí, no la voy a completar" in r.text
        assert 'name="confirmar" value="si"' in r.text

    def test_exito_muestra_aviso_y_foco_en_la_seccion(self):
        from zascarr.services.coleccion import marcar_no_completar
        series = make_series(total_issues=3)
        marcar_no_completar(series)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}?coleccion=guardado")
        assert "Guardado: sus huecos ya no cuentan como faltas." in r.text
        assert 'id="coleccion-serie"' in r.text
        assert 'tabindex="-1" autofocus' in r.text
        assert 'name="version" value="1"' in r.text

    def test_ficha_no_los_muestra_como_faltas(self):
        from zascarr.services.coleccion import marcar_no_completar
        series = make_series(total_issues=3)
        marcar_no_completar(series)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
            acuse(), retirados(), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "No la vas a completar" in r.text
        assert "Volver a completarla" in r.text
        assert "<h2>Te faltan</h2>" not in r.text
        assert "No la vas a completar. Sus huecos no cuentan como faltas" in r.text



@pytest.mark.parametrize("valor,etiqueta", [
    (WishlistPolicy.FUTURE, "Números futuros (todavía no disponible)"),
    (WishlistPolicy.ALL, "Todos los números (reservado)"),
])
def test_opcion_reservada_usa_etiqueta_no_valor_crudo(valor, etiqueta):
    """R2 #789: las opciones reservadas conservan su value real y se leen en llano."""
    from types import SimpleNamespace

    from zascarr.web.series import templates

    html = templates.env.get_template("_politica_serie.html").render(
        series=SimpleNamespace(id=uuid4()),
        politica_actual=valor,
        politica_actual_etiqueta=etiqueta,
        politicas_ofrecidas={},
        motivo_futuros="la fuente no publica números futuros",
        politica_efectiva=valor,
        politica_efectiva_etiqueta=etiqueta,
        coleccion_causa=None,
        veredicto=SimpleNamespace(tipo="ninguno", no_calculable=False),
        querer=SimpleNamespace(motivo=None, numeros=[]),
        lote=25,
        aviso_legal_pendiente=False,
        retirados=0,
        retirados_ahora=None,
    )
    assert f'value="{valor.value}"' in html
    assert etiqueta in html
    assert f">{valor.value}" not in html
