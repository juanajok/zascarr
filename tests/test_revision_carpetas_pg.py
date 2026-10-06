# ruff: noqa: E501
"""`GET /api/revision/carpetas` (rebanada 1a) — pruebas de aceptación sobre Postgres real.

Contrato en `docs/design/rebanada-1-superficie-de-revision.md`; los números de las clases/pruebas siguen
el de esa ficha. Los nombres de series y carpetas imitan la forma de la biblioteca real (títulos publicados);
ninguna ruta es de nadie y NINGÚN fichero existe en disco: la superficie no puede depender de él.
Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import builtins
import json
import logging
import os
import re
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series
from zascarr.services import revision_carpetas
from zascarr.services.review import ReviewService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

BIB = "/biblioteca-de-prueba"
RUTA = "/api/revision/carpetas"
ETIQUETAS_FIJAS = {
    "sin_serie": "Sin serie",
    "serie_sugerida": "Serie sugerida, falta confirmar número y edición",
}


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


class Banco:
    """Una BD de prueba con su fabrica de sesiones, un contador de sentencias y atajos para sembrar."""

    def __init__(self, url: str):
        self.motor = create_async_engine(url_asyncpg(url))      # con pool: la conexión se calienta una vez
        self.fabrica = async_sessionmaker(self.motor, expire_on_commit=False)
        self.sentencias: list[str] = []

        @event.listens_for(self.motor.sync_engine, "before_cursor_execute")
        def _contar(conn, cursor, statement, parameters, context, executemany):
            self.sentencias.append(statement)

    async def limpiar(self):
        async with self.motor.begin() as c:
            await c.execute(text(
                "TRUNCATE asignacion_operaciones, files, issues, series, local_aliases, import_runs CASCADE"))

    async def serie(self, titulo: str, anio: int | None = None) -> UUID:
        sid = uuid4()
        async with self.fabrica() as s:
            s.add(Series(id=sid, title=titulo, tradition=ComicTradition.AMERICAN, start_year=anio))
            await s.commit()
        return sid

    async def sembrar(self, *archivos: File):
        async with self.fabrica() as s:
            s.add_all(archivos)
            await s.commit()

    async def cerrar(self):
        await self.motor.dispose()


def candidatas(sid: UUID, titulo: str, anio: int | None, score: float = 1.0) -> list[dict]:
    return [{"series_id": str(sid), "title": titulo, "start_year": anio, "score": score}]


def archivo(ruta: str, *, estado: str = "unsorted", cands=None, issue_id=None, descartado: bool = False,
            absoluta: bool = False) -> File:
    """Un `File` en `ruta` (relativa a la biblioteca de prueba). El fichero NO existe en disco."""
    meta: dict = {"match_status": estado}
    if cands is not None:
        meta["candidates"] = cands
    formato = FileFormat.CBR if ruta.lower().endswith(".cbr") else FileFormat.CBZ
    return File(
        id=uuid4(), file_path=ruta if absoluta else f"{BIB}/{ruta}", file_name=ruta.rsplit("/", 1)[-1],
        file_format=formato, metadata_=meta, issue_id=issue_id, review_dismissed=descartado,
    )


@pytest.fixture
async def banco(url_bd, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    monkeypatch.setattr(revision_carpetas, "get_settings", lambda: SimpleNamespace(library_path=Path(BIB)))

    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    yield b
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


def cliente(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost",
        headers={"Origin": "http://localhost"}, **kw,
    )


async def consultar(params: dict | None = None) -> dict:
    async with cliente() as c:
        r = await c.get(RUTA, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def grupo(resp: dict, clave: str) -> dict:
    encontrados = [g for g in resp["grupos"] if g["clave"] == clave]
    assert len(encontrados) == 1, [g["clave"] for g in resp["grupos"]]
    return encontrados[0]


def codigos(g: dict) -> list[str]:
    return [s["codigo"] for s in g["senales"]]


# ── Agrupación y alcance (1-5) ────────────────────────────────────────────────────────────────────

class TestAgrupacionYAlcance:

    async def test_1_misma_carpeta_limpia_en_tradiciones_distintas_son_dos_grupos(self, banco):
        await banco.sembrar(
            archivo("Graphic Novels/Carlos Gimenez/Paracuellos 01.cbz"),
            archivo("Tebeos/Carlos Giménez/Paracuellos 02.cbz"),
        )
        r = await consultar()
        assert sorted(g["clave"] for g in r["grupos"]) == [
            "Graphic Novels/Carlos Gimenez", "Tebeos/Carlos Giménez"]
        assert r["totales"]["grupos"] == 2

    async def test_2_el_contenedor_no_es_la_carpeta_contextual(self, banco):
        await banco.sembrar(
            archivo("Comics/_Omnibus/Dinastia y Potencias de X/Dinastia 01.cbz"),
            archivo("Comics/_Omnibus/Suelto 01.cbz"),                 # solo contenedores
            archivo("Comics/Ómnibus/Varios 01.cbz"),                  # sin acentos ni mayúsculas
        )
        r = await consultar()
        g = grupo(r, "Comics/_Omnibus/Dinastia y Potencias de X")
        assert g["carpeta_contextual"] == "Dinastia y Potencias de X"
        assert g["ascendentes"] == ["Comics", "_Omnibus"]
        assert "sin_contexto_de_carpeta" not in codigos(g)
        solo = grupo(r, "Comics/_Omnibus")
        assert solo["carpeta_contextual"] is None and solo["carpeta_limpia"] is None
        assert "sin_contexto_de_carpeta" in codigos(solo)
        assert grupo(r, "Comics/Ómnibus")["carpeta_contextual"] is None

    async def test_3_archivos_directamente_en_la_tradicion_o_en_la_raiz(self, banco):
        await banco.sembrar(archivo("Comics/Suelto 01.cbz"), archivo("Raiz 01.cbz"))
        r = await consultar()
        for clave in ("Comics", "."):
            g = grupo(r, clave)
            assert g["carpeta_contextual"] is None and "sin_contexto_de_carpeta" in codigos(g)

    async def test_4_el_recuento_de_sin_serie_es_el_del_menu(self, banco):
        sid = await banco.serie("Batman", 2016)
        await banco.sembrar(
            *(archivo(f"Comics/A/Cosa {i:02d}.cbz") for i in range(5)),
            *(archivo(f"Comics/B/Otra {i:02d}.cbz") for i in range(2)),
            *(archivo(f"Comics/Batman (2016)/Batman {i:02d}.cbz", estado="direct",
                      cands=candidatas(sid, "Batman", 2016)) for i in range(1, 4)),
        )
        r = await consultar()
        async with banco.fabrica() as s:
            menu = await ReviewService(s).count_pending()
        sin_serie = [a for g in r["grupos"] for a in g["archivos"] if a["estado"] == "sin_serie"]
        assert menu == 7 and len(sin_serie) == menu == r["totales"]["sin_serie"]
        sugeridos = [a for g in r["grupos"] for a in g["archivos"] if a["estado"] == "serie_sugerida"]
        assert len(sugeridos) == r["totales"]["serie_sugerida"] == 3     # y NO cuentan en el menú

    async def test_5_descartados_y_con_issue_no_aparecen(self, banco):
        sid = await banco.serie("Batman", 2016)
        async with banco.fabrica() as s:
            issue = Issue(series_id=sid, issue_number="1")
            s.add(issue)
            await s.commit()
            issue_id = issue.id
        visible = archivo("Comics/X/Visible 01.cbz")
        await banco.sembrar(
            visible,
            archivo("Comics/X/Descartado 01.cbz", descartado=True),
            archivo("Comics/X/ConIssue 01.cbz", estado="direct", issue_id=issue_id),
            archivo("Comics/X/SugeridoDescartado 01.cbz", estado="direct", descartado=True,
                    cands=candidatas(sid, "Batman", 2016)),
        )
        r = await consultar()
        ids = {a["id"] for g in r["grupos"] for a in g["archivos"]}
        assert ids == {str(visible.id)}


# ── Los 17 y el conflicto (6-9) ───────────────────────────────────────────────────────────────────

NOMBRES_SAGA = [
    f"Batman - Saga Scott Snyder {n:02d} - El Tribunal de los Buhos [SC][CRG].cbr" for n in range(1, 10)]


class TestLosDiecisieteYElConflicto:

    async def test_6_batman_saga_con_candidata_de_otro_anio_es_un_conflicto(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(*(
            archivo(f"Comics/Batman - Saga de Scott Snyder (2019)/{n}", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)) for n in NOMBRES_SAGA))
        r = await consultar()
        g = grupo(r, "Comics/Batman - Saga de Scott Snyder (2019)")
        assert (g["estado"], g["etiqueta"]) == ("serie_sugerida", ETIQUETAS_FIJAS["serie_sugerida"])
        assert g["por_confirmar"] is True and g["en_conflicto"] is True
        assert codigos(g) == ["anio_discrepa", "calificador_de_carpeta"]
        assert {s["severidad"] for s in g["senales"]} == {"conflicto"}
        assert "2019" in g["senales"][0]["texto"] and "2025" in g["senales"][0]["texto"]
        assert "Saga de Scott Snyder" in g["senales"][1]["texto"]
        assert g["serie_sugerida"]["titulo"] == "BATMAN" and g["serie_sugerida"]["anio"] == 2025
        assert g["carpeta_limpia"] == {
            "titulo": "Batman", "anio": 2019, "volumen": None, "calificadores": ["Saga de Scott Snyder"]}
        assert g["n_archivos"] == 9 and len(g["archivos"]) == 9           # todos, son pocos
        # Nunca se preselecciona nada ni se declara lista: ni campo, ni estado.
        assert g["estado"] in {"sin_serie", "serie_sugerida", "mixto"}
        assert not PALABRAS_PROHIBIDAS.search(json.dumps([g["etiqueta"], g["senales"]], ensure_ascii=False))
        assert {"serie_elegida", "serie_preseleccionada", "asignar"}.isdisjoint(g)

    async def test_7_absolute_batman_corrobora_pero_sigue_por_confirmar(self, banco):
        sid = await banco.serie("Absolute Batman", 2024)
        await banco.sembrar(*(
            archivo(f"Comics/Absolute Batman (2024)/Absolute Batman {n:02d} [CRG].cbz", estado="direct",
                    cands=candidatas(sid, "Absolute Batman", 2024)) for n in range(1, 10)))
        g = grupo(await consultar(), "Comics/Absolute Batman (2024)")
        assert g["por_confirmar"] is True            # falta el número: siempre en el conjunto B
        assert g["en_conflicto"] is False
        assert codigos(g) == ["coincide_y_corrobora"]
        assert g["senales"][0]["severidad"] == "informativa"

    async def test_8_titulo_exacto_sin_ano_ni_volumen_no_se_da_por_bueno(self, banco):
        sid = await banco.serie("Flash", 1987)
        await banco.sembrar(*(
            archivo(f"Comics/Flash/Flash {n:03d}.cbz", estado="direct", cands=candidatas(sid, "Flash", 1987))
            for n in range(1, 4)))
        g = grupo(await consultar(), "Comics/Flash")
        assert g["en_conflicto"] is True and g["por_confirmar"] is True
        assert codigos(g) == ["titulo_exacto_sin_corroboracion"]
        assert "coincide_y_corrobora" not in codigos(g)

    async def test_8b_el_ano_de_los_nombres_tambien_corrobora(self, banco):
        sid = await banco.serie("Flash", 1987)
        await banco.sembrar(*(
            archivo(f"Comics/Flash/Flash {n:03d} (1987).cbz", estado="direct", cands=candidatas(sid, "Flash", 1987))
            for n in range(1, 4)))
        g = grupo(await consultar(), "Comics/Flash")
        assert g["en_conflicto"] is False and codigos(g) == ["coincide_y_corrobora"]

    async def test_8c_una_serie_cuyo_titulo_lleva_el_calificador_no_discrepa(self, banco):
        sid = await banco.serie("Batman - Saga de Scott Snyder", 2019)
        await banco.sembrar(archivo(
            "Comics/Batman - Saga de Scott Snyder (2019)/Batman 01.cbz", estado="direct",
            cands=candidatas(sid, "Batman - Saga de Scott Snyder", 2019)))
        g = grupo(await consultar(), "Comics/Batman - Saga de Scott Snyder (2019)")
        assert "calificador_de_carpeta" not in codigos(g) and "anio_discrepa" not in codigos(g)

    async def test_8d_el_volumen_de_la_carpeta_es_un_calificador_si_la_serie_no_lo_lleva(self, banco):
        sid = await banco.serie("Superman", 1987)
        await banco.sembrar(archivo(
            "Comics/Superman Vol2 (Ed.Zinco)(1987-96)/Superman 010.cbz", estado="direct",
            cands=candidatas(sid, "Superman", 1987)))
        g = grupo(await consultar(), "Comics/Superman Vol2 (Ed.Zinco)(1987-96)")
        assert g["en_conflicto"] is True
        assert "calificador_de_carpeta" in codigos(g)
        texto = next(s["texto"] for s in g["senales"] if s["codigo"] == "calificador_de_carpeta")
        assert "Vol 2" in texto and "Ed.Zinco" in texto
        assert "coincide_y_corrobora" not in codigos(g)       # el año coincide, pero el conflicto manda

    async def test_8e_varias_series_candidatas_en_un_grupo_es_un_conflicto_visible(self, banco):
        a, b = await banco.serie("Flash", 1987), await banco.serie("Flash", 2011)
        await banco.sembrar(
            archivo("Comics/Flash (1987)/Flash 01.cbz", estado="direct", cands=candidatas(a, "Flash", 1987)),
            archivo("Comics/Flash (1987)/Flash 02.cbz", estado="direct", cands=candidatas(a, "Flash", 1987)),
            archivo("Comics/Flash (1987)/Flash 03.cbz", estado="fuzzy", cands=candidatas(b, "Flash", 2011, 0.9)),
        )
        g = grupo(await consultar(), "Comics/Flash (1987)")
        assert g["en_conflicto"] is True and "candidatas_distintas" in codigos(g)
        assert g["serie_sugerida"]["anio"] == 1987            # la que más archivos sugieren
        assert g["serie_sugerida"]["puntuacion"] == 1.0

    async def test_la_puntuacion_del_grupo_es_la_menor_no_la_mayor(self, banco):
        sid = await banco.serie("Flash", 1987)
        await banco.sembrar(
            archivo("Comics/Flash (1987)/Flash 01.cbz", estado="direct", cands=candidatas(sid, "Flash", 1987, 1.0)),
            archivo("Comics/Flash (1987)/Flash 02.cbz", estado="fuzzy", cands=candidatas(sid, "Flash", 1987, 0.8)),
        )
        g = grupo(await consultar(), "Comics/Flash (1987)")
        assert g["serie_sugerida"]["puntuacion"] == 0.8       # no se exagera la confianza

    async def test_9_carpeta_de_autor_o_contenedor(self, banco):
        obras = ["Alfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta", "Iota", "Kappa",
                 "Lambda", "Mu", "Nu", "Xi", "Omicron", "Pi", "Rho", "Sigma", "Tau", "Upsilon"]
        await banco.sembrar(
            *(archivo(f"Comics/Autor Famoso/Obra {o} 01.cbz") for o in obras),          # 20: en el umbral
            *(archivo(f"Comics/Autor Menor/Obra {o} 01.cbz") for o in obras[:19]),      # 19: por debajo
        )
        r = await consultar()
        g = grupo(r, "Comics/Autor Famoso")
        assert "carpeta_de_autor_o_contenedor" in codigos(g)
        assert next(s for s in g["senales"] if s["codigo"] == "carpeta_de_autor_o_contenedor")["severidad"] == "aviso"
        assert g["en_conflicto"] is False                    # es un aviso, no una contradicción
        assert g["serie_sugerida"] is None                   # la carpeta no se propone como serie
        assert g["patron_de_nombres"]["titulos_distintos"] == 20
        assert "carpeta_de_autor_o_contenedor" not in codigos(grupo(r, "Comics/Autor Menor"))

    async def test_mixto_une_sin_serie_y_serie_sugerida_en_una_carpeta(self, banco):
        sid = await banco.serie("Absolute Batman", 2024)
        await banco.sembrar(
            archivo("Comics/Absolute Batman (2024)/Absolute Batman 01.cbz", estado="direct",
                    cands=candidatas(sid, "Absolute Batman", 2024)),
            archivo("Comics/Absolute Batman (2024)/Extra 01.cbz"),
            archivo("Comics/Absolute Batman (2024)/Extra 02.cbz"),
        )
        g = grupo(await consultar(), "Comics/Absolute Batman (2024)")
        assert g["estado"] == "mixto" and g["por_confirmar"] is True
        assert g["etiqueta"] == revision_carpetas.ETIQUETAS["mixto"]
        assert sorted(a["estado"] for a in g["archivos"]) == ["serie_sugerida", "sin_serie", "sin_serie"]
        assert g["serie_sugerida"]["titulo"] == "Absolute Batman"

    async def test_sin_serie_no_sugiere_nada_ni_esta_por_confirmar(self, banco):
        await banco.sembrar(archivo("Comics/Patrulla X (Panini)/Inferno 01.cbz"))
        g = grupo(await consultar(), "Comics/Patrulla X (Panini)")
        assert (g["estado"], g["etiqueta"]) == ("sin_serie", ETIQUETAS_FIJAS["sin_serie"])
        assert g["serie_sugerida"] is None and g["por_confirmar"] is False and g["en_conflicto"] is False

    async def test_las_catorce_filas_previas_son_sin_serie_agrupadas_por_su_carpeta_antigua(self, banco):
        """Decisión 4: son filas `is_missing` cuyo fichero ya no está donde dice la BD. La superficie no mira el
        disco, así que no puede afirmar que existan: salen como «Sin serie» en su carpeta antigua."""
        f = archivo("Comics/Carpeta Antigua/Algo 01.cbz")
        f.is_missing = True
        await banco.sembrar(f)
        g = grupo(await consultar(), "Comics/Carpeta Antigua")
        assert g["estado"] == "sin_serie" and g["n_archivos"] == 1


# ── Datos incómodos ───────────────────────────────────────────────────────────────────────────────

class TestDatosIncomodos:

    async def test_candidatas_mal_formadas_no_rompen_nada(self, banco):
        sid = await banco.serie("Batman", 2016)
        await banco.sembrar(
            archivo("Comics/M/Cadena 01.cbz", estado="direct", cands="esto no es una lista"),
            archivo("Comics/M/SinId 01.cbz", estado="direct", cands=[{"nope": 1}, None, "x"]),
            archivo("Comics/M/IdRoto 01.cbz", estado="direct", cands=[{"series_id": "no-es-uuid", "score": 1}]),
            archivo("Comics/M/Bien 01.cbz", estado="direct", cands=candidatas(sid, "Batman", 2016)),
            archivo("Comics/M/Vacia 01.cbz", estado="direct", cands=[]),
            archivo("Comics/M/Ausente 01.cbz", estado="direct"),
        )
        r = await consultar()
        nombres = {a["nombre"] for g in r["grupos"] for a in g["archivos"]}
        assert nombres == {"Bien 01.cbz"}
        # Lista con elementos pero ninguna utilizable: se CUENTAN, no se esconden.
        assert r["totales"]["candidata_inexistente"] == 2 and r["totales"]["serie_sugerida"] == 1

    async def test_una_candidata_cuya_serie_ya_no_existe_se_cuenta_y_no_se_muestra(self, banco):
        await banco.sembrar(archivo("Comics/R/Huerfana 01.cbz", estado="direct",
                                    cands=candidatas(uuid4(), "Borrada", 2000)))
        r = await consultar()
        assert r["grupos"] == [] and r["totales"]["candidata_inexistente"] == 1
        assert r["totales"]["serie_sugerida"] == 0

    async def test_una_ruta_fuera_de_la_biblioteca_se_agrupa_por_su_ruta_completa(self, banco):
        await banco.sembrar(archivo("/otro/sitio/Comics/Algo/Cosa 01.cbz", absoluta=True))
        r = await consultar()
        assert [g["clave"] for g in r["grupos"]] == ["otro/sitio/Comics/Algo"]

    async def test_la_muestra_de_archivos_es_de_veinte_pero_el_recuento_es_completo(self, banco):
        await banco.sembrar(*(archivo(f"Comics/Larga/Cosa {i:03d}.cbz") for i in range(45)))
        g = grupo(await consultar(), "Comics/Larga")
        assert g["n_archivos"] == 45 and len(g["archivos"]) == 20
        assert [a["nombre"] for a in g["archivos"]] == sorted(a["nombre"] for a in g["archivos"])

    async def test_patron_de_nombres(self, banco):
        await banco.sembrar(
            archivo("Comics/P/Flash 01.cbz"), archivo("Comics/P/Flash 02.cbz"),
            archivo("Comics/P/Flash 03.cbz"), archivo("Comics/P/Impulse 01.cbz"),
        )
        p = grupo(await consultar(), "Comics/P")["patron_de_nombres"]
        assert p == {"titulo_dominante": "Flash", "proporcion": 0.75, "titulos_distintos": 2}


# ── Orden, paginación y determinismo (13) ─────────────────────────────────────────────────────────

class TestOrdenYPaginacion:

    async def _sembrar_variado(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Zeta/Z 01.cbz"),
            *(archivo(f"Comics/Beta/B {i:02d}.cbz") for i in range(3)),
            *(archivo(f"Comics/Alfa/A {i:02d}.cbz") for i in range(3)),
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct", cands=candidatas(sid, "BATMAN", 2025)),
        )

    async def test_conflictos_primero_luego_mas_archivos_luego_clave(self, banco):
        await self._sembrar_variado(banco)
        r = await consultar()
        assert [g["clave"] for g in r["grupos"]] == [
            "Comics/Batman (2019)", "Comics/Alfa", "Comics/Beta", "Comics/Zeta"]

    async def test_13_dos_llamadas_devuelven_lo_mismo(self, banco):
        await self._sembrar_variado(banco)
        a, b = await consultar(), await consultar()
        a.pop("generado"), b.pop("generado")
        assert a == b

    async def test_13b_el_orden_de_insercion_no_cambia_el_resultado(self, banco, url_bd):
        archivos = [archivo(f"Comics/C{i % 4}/Cosa {i:02d}.cbz") for i in range(12)]
        await banco.sembrar(*archivos)
        antes = await consultar()
        await banco.limpiar()
        await banco.sembrar(*reversed([
            File(id=f.id, file_path=f.file_path, file_name=f.file_name, file_format=f.file_format,
                 metadata_=f.metadata_) for f in archivos]))
        despues = await consultar()
        antes.pop("generado"), despues.pop("generado")
        assert antes == despues

    async def test_13c_el_resultado_no_depende_del_orden_en_que_la_bd_entregue_las_filas(self, banco, monkeypatch):
        """Dos grupos empatados en tamaño y sin conflicto: solo la clave los ordena. Si el orden dependiera de la BD
        (o del desempate), cambiaría al entregarse las filas al revés o barajadas."""
        await banco.sembrar(*(archivo(f"Comics/{c}/Cosa {i:02d}.cbz") for c in ("Beta", "Alfa", "Gamma") for i in range(3)))
        normal = await consultar()
        leer = revision_carpetas.RevisionCarpetas._leer

        for transformar in (lambda f: f[::-1], lambda f: sorted(f, key=lambda a: a.id)):
            async def barajado(self, _t=transformar):
                return _t(await leer(self))
            monkeypatch.setattr(revision_carpetas.RevisionCarpetas, "_leer", barajado)
            otro = await consultar()
            normal_sin, otro_sin = dict(normal, generado=None), dict(otro, generado=None)
            assert otro_sin == normal_sin
        assert [g["clave"] for g in normal["grupos"]] == ["Comics/Alfa", "Comics/Beta", "Comics/Gamma"]

    async def test_paginacion_de_grupos_con_totales_completos(self, banco):
        await banco.sembrar(*(archivo(f"Comics/G{i}/Cosa 01.cbz") for i in range(5)))
        completa = await consultar()
        pagina = await consultar({"limite": 2, "desplazamiento": 2})
        assert pagina["totales"] == completa["totales"] and pagina["totales"]["grupos"] == 5
        assert pagina["pagina"] == {"limite": 2, "desplazamiento": 2}
        assert [g["clave"] for g in pagina["grupos"]] == [g["clave"] for g in completa["grupos"][2:4]]
        fuera = await consultar({"desplazamiento": 99})
        assert fuera["grupos"] == [] and fuera["totales"]["grupos"] == 5

    @pytest.mark.parametrize("params", [{"limite": 0}, {"limite": 1001}, {"desplazamiento": -1}, {"limite": "x"}])
    async def test_parametros_invalidos_son_422(self, banco, params):
        async with cliente() as c:
            assert (await c.get(RUTA, params=params)).status_code == 422


# ── Solo lectura, sin disco ni red, y coste constante (10-12) ─────────────────────────────────────

TABLAS = ("files", "series", "issues", "import_runs", "asignacion_operaciones", "local_aliases")


async def _huella(banco) -> dict[str, tuple]:
    async with banco.fabrica() as s:
        return {t: tuple((await s.execute(text(
            f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x"
        ))).one()) for t in TABLAS}


class TestSoloLecturaYCoste:

    async def test_10_cero_escrituras(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct", cands=candidatas(sid, "BATMAN", 2025)),
        )
        await consultar()                                    # calienta la conexión
        antes = await _huella(banco)
        banco.sentencias.clear()
        await consultar()
        assert banco.sentencias, "no se ha ejecutado ninguna consulta: la prueba no mide nada"
        no_select = [s for s in banco.sentencias if not s.lstrip().upper().startswith(("SELECT", "WITH"))]
        assert no_select == []
        assert await _huella(banco) == antes

    async def test_11_cero_disco_y_cero_red(self, banco, monkeypatch):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct", cands=candidatas(sid, "BATMAN", 2025)),
        )
        esperado = await consultar()                         # también calienta la conexión
        accesos: list[str] = []

        def vigilar(modulo, nombre):
            real = getattr(modulo, nombre)

            def vigilado(p, *a, **k):
                if str(p).startswith(BIB) or "Cosa 01" in str(p) or "Batman (2019)" in str(p):
                    accesos.append(f"{nombre}({p})")
                    raise AssertionError(f"{nombre} sobre la biblioteca: {p}")
                return real(p, *a, **k)
            monkeypatch.setattr(modulo, nombre, vigilado)

        for nombre in ("stat", "lstat", "scandir", "listdir"):
            vigilar(os, nombre)
        for nombre in ("exists", "is_file", "stat", "iterdir", "resolve"):
            vigilar(Path, nombre)
        vigilar(builtins, "open")

        def sin_red(*a, **k):
            raise AssertionError("acceso a la red")
        monkeypatch.setattr(socket.socket, "connect", sin_red)
        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", sin_red)
        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", sin_red)

        obtenido = await consultar()
        assert accesos == []
        esperado.pop("generado"), obtenido.pop("generado")
        assert obtenido == esperado

    async def test_11b_el_modulo_no_importa_nada_capaz_de_tocar_disco_o_red(self):
        fuente = Path(revision_carpetas.__file__).read_text(encoding="utf-8")
        for prohibido in ("shutil", "zipfile", "subprocess", "httpx", "aiohttp", "requests", "socket",
                          "os.stat", ".exists(", ".stat(", "open(", "resolve("):
            assert prohibido not in fuente, prohibido

    @staticmethod
    async def _sembrar_masivo(banco, n: int):
        # Varias series candidatas: una consulta por serie o por archivo haría crecer el número de sentencias.
        series = [await banco.serie(f"Serie {k:02d}", 2000 + k) for k in range(8)]
        grandes = [archivo(f"Comics/Carpeta {i % 100:03d}/Cosa {i:05d}.cbz") for i in range(n)]
        sugeridos = [
            archivo(f"Comics/Sug {i % 20:02d}/Serie {i % 8:02d} {i:05d}.cbz", estado="direct",
                    cands=candidatas(series[i % 8], f"Serie {i % 8:02d}", 2000 + i % 8))
            for i in range(max(n // 10, 8))
        ]
        await banco.sembrar(*grandes, *sugeridos)

    async def test_12_numero_de_consultas_constante_y_respuesta_rapida(self, banco):
        await self._sembrar_masivo(banco, 20)                # 20 + 8 filas
        await consultar()                                    # calienta la conexión
        banco.sentencias.clear()
        await consultar()
        pocas = len(banco.sentencias)

        await banco.limpiar()
        await self._sembrar_masivo(banco, 1820)              # 1.820 + 182 = 2.002 filas
        banco.sentencias.clear()
        inicio = time.perf_counter()
        r = await consultar()
        segundos = time.perf_counter() - inicio
        muchas = len(banco.sentencias)

        assert r["totales"]["sin_serie"] + r["totales"]["serie_sugerida"] == 1820 + 182
        assert pocas == muchas <= 3, (pocas, muchas)
        assert segundos < 1.0, f"{segundos:.2f} s con 2.000 filas"


# ── Contrato y seguridad (14-16) ──────────────────────────────────────────────────────────────────

CLAVES_RESPUESTA = {"generado", "totales", "pagina", "grupos"}
CLAVES_TOTALES = {"sin_serie", "serie_sugerida", "grupos", "candidata_inexistente"}
CLAVES_GRUPO = {
    "clave", "carpeta_contextual", "ascendentes", "carpeta_limpia", "estado", "etiqueta", "n_archivos",
    "patron_de_nombres", "serie_sugerida", "por_confirmar", "en_conflicto", "senales", "archivos",
}
PALABRAS_PROHIBIDAS = re.compile(r"\b(reconocid\w*|clasificad\w*|lista)\b", re.IGNORECASE)


class TestContratoYSeguridad:

    async def test_14_esquema_estable_y_etiquetas_exactas(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            *(archivo(f"Comics/Batman - Saga de Scott Snyder (2019)/{n}", estado="direct",
                      cands=candidatas(sid, "BATMAN", 2025)) for n in NOMBRES_SAGA[:3]),
        )
        async with cliente() as c:
            r = await c.get(RUTA)
        assert r.headers["cache-control"] == "no-store"
        cuerpo = r.json()
        assert set(cuerpo) == CLAVES_RESPUESTA and set(cuerpo["totales"]) == CLAVES_TOTALES
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", cuerpo["generado"])
        assert all(type(v) is int for v in cuerpo["totales"].values())
        for g in cuerpo["grupos"]:
            assert set(g) == CLAVES_GRUPO
            assert isinstance(g["clave"], str) and isinstance(g["ascendentes"], list)
            assert isinstance(g["n_archivos"], int) and isinstance(g["por_confirmar"], bool)
            assert isinstance(g["en_conflicto"], bool)
            assert set(g["patron_de_nombres"]) == {"titulo_dominante", "proporcion", "titulos_distintos"}
            for s in g["senales"]:
                assert set(s) == {"codigo", "severidad", "texto"}
                assert s["severidad"] in {"conflicto", "aviso", "informativa"}
            for a in g["archivos"]:
                assert set(a) == {"id", "nombre", "estado"} and UUID(a["id"])
            assert g["etiqueta"] == revision_carpetas.ETIQUETAS[g["estado"]]
        con_serie = next(g for g in cuerpo["grupos"] if g["estado"] == "serie_sugerida")
        assert set(con_serie["serie_sugerida"]) == {"series_id", "titulo", "anio", "puntuacion"}
        assert set(con_serie["carpeta_limpia"]) == {"titulo", "anio", "volumen", "calificadores"}
        # Etiquetas exactas: las dos del contrato, tal cual.
        assert revision_carpetas.ETIQUETAS["sin_serie"] == ETIQUETAS_FIJAS["sin_serie"]
        assert revision_carpetas.ETIQUETAS["serie_sugerida"] == ETIQUETAS_FIJAS["serie_sugerida"]
        assert revision_carpetas.ETIQUETAS["por_confirmar"] == "por confirmar"
        assert revision_carpetas.ETIQUETAS["en_conflicto"] == "en conflicto"
        # Y ni una palabra que prometa lo que no se sabe (se mira el texto que genera la superficie).
        textos = list(revision_carpetas.ETIQUETAS.values()) + [
            s["texto"] for g in cuerpo["grupos"] for s in g["senales"]] + [g["etiqueta"] for g in cuerpo["grupos"]]
        assert [t for t in textos if PALABRAS_PROHIBIDAS.search(t)] == []

    async def test_15_sin_sesion_no_hay_datos(self, banco, monkeypatch):
        from zascarr.config import get_settings
        from zascarr.services.auth import hash_password
        ajustes = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        await banco.sembrar(archivo("Comics/Sin/Cosa 01.cbz"))
        async with cliente() as c:
            sin = await c.get(RUTA)
            mala = await c.get(RUTA, auth=("x", "equivocada"))
            buena = await c.get(RUTA, auth=("x", "secreta"))
        for r in (sin, mala):
            assert r.status_code == 401 and "Cosa 01" not in r.text and "grupos" not in r.text
        assert buena.status_code == 200 and buena.json()["totales"]["sin_serie"] == 1

    async def test_16_no_registra_rutas_ni_nombres(self, banco, caplog, capfd):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/CarpetaSecretaQ9/ArchivoSecretoQ9 01.cbz"),
            archivo("Comics/CarpetaSecretaQ9/Batman 01.cbz", estado="direct", cands=candidatas(sid, "BATMAN", 2025)),
        )
        with caplog.at_level(logging.DEBUG):
            await consultar()
        salida = capfd.readouterr()
        for visible in (caplog.text, salida.out, salida.err):
            assert "SecretaQ9" not in visible and "SecretoQ9" not in visible and BIB not in visible
