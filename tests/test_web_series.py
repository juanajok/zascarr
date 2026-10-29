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
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
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
            acuse(), retirados(), FakeExecResult([]),
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
        assert "Se guarda al elegir. Si dejas de buscar, se para al momento." in html
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
        assert linea == "Se guarda al elegir. Si dejas de buscar, se para al momento."
        assert len(linea) <= 60
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
        assert "Se guarda al elegir" in plano and "se para al momento" in plano

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
