# ruff: noqa: E501
"""BL-R2 (#231): qué observa el ciclo del importador al revisar la biblioteca y cómo se muestra. Sin Postgres.

Cubre los criterios 2, 3, 4, 7, 8 y 11 con sesiones falsas y ficheros reales en `tmp_path`; el resto (lectura del informe,
ciclos antiguos, orden y paginación) está en `tests/test_disponibilidad_pg.py`.
"""
from __future__ import annotations

import errno
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.test_importer import FakeSessionArchivos, make_cbz
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import File, ResultadoComprobacion
from zascarr.services.disponibilidad import EstadoComprobacion
from zascarr.services.importer import (
    CLAVE_COMPROBACION,
    ComprobacionBiblioteca,
    Importer,
    ImportReport,
    _existe,
)
from zascarr.web.routes import crear_templates

R = ResultadoComprobacion


def _file(ruta: Path, **kw) -> File:
    return File(id=uuid4(), file_path=str(ruta), file_name=ruta.name, file_format="cbz",
                is_missing=kw.pop("is_missing", False), **kw)


def _importer(library: Path, files: list[File]) -> tuple[Importer, FakeSessionArchivos]:
    importer = Importer.__new__(Importer)
    sesion = FakeSessionArchivos(files)
    importer._db = sesion
    importer._library = library
    return importer, sesion


class TestResultadoDeLaComprobacion:
    """El motivo de cada guardarraíl deja de ir solo al log: queda en el resultado del ciclo."""

    @pytest.mark.asyncio
    async def test_raiz_inexistente_queda_registrada_sin_marcar_bajas(self, tmp_path):
        f = _file(tmp_path / "no-existe" / "A.cbz")
        importer, _ = _importer(tmp_path / "no-existe", [f])

        c = await importer._comprobar_biblioteca()

        assert c.resultado is R.RAIZ_INACCESIBLE
        assert c.archivos_registrados == 1 and c.ausentes is None
        assert c.bajas_omitidas and c.desaparecidos == [] and c.reaparecidos == []
        assert f.is_missing is False and f.missing_since is None

    @pytest.mark.asyncio
    async def test_raiz_que_es_un_archivo_cuenta_como_inaccesible(self, tmp_path):
        no_carpeta = tmp_path / "biblioteca"
        no_carpeta.write_text("no soy una carpeta")
        importer, _ = _importer(no_carpeta, [_file(no_carpeta / "A.cbz")])

        assert (await importer._comprobar_biblioteca()).resultado is R.RAIZ_INACCESIBLE

    @pytest.mark.asyncio
    async def test_raiz_vacia_queda_registrada_sin_marcar_bajas(self, tmp_path):
        library = tmp_path / "lib"
        library.mkdir()
        f = _file(library / "A.cbz")
        importer, _ = _importer(library, [f])

        c = await importer._comprobar_biblioteca()

        assert c.resultado is R.RAIZ_VACIA and c.archivos_registrados == 1
        assert c.bajas_omitidas and f.is_missing is False

    @pytest.mark.asyncio
    async def test_desaparicion_masiva_registra_cuantos_faltaban(self, tmp_path):
        library = tmp_path / "lib"
        library.mkdir()
        make_cbz(library / "unico.cbz")  # la carpeta no está vacía: salta el guardarraíl de la mitad
        files = [_file(library / f"Falta {i}.cbz") for i in range(10)]
        importer, _ = _importer(library, files)

        c = await importer._comprobar_biblioteca()

        assert c.resultado is R.DESAPARICION_MASIVA
        assert (c.archivos_registrados, c.ausentes) == (10, 10)
        assert c.bajas_omitidas and all(f.is_missing is False for f in files)

    @pytest.mark.asyncio
    async def test_comprobada_cuenta_ausentes_y_aplica_las_bajas(self, tmp_path):
        library = tmp_path / "lib"
        library.mkdir()
        presentes = [library / f"P{i}.cbz" for i in range(9)]
        for p in presentes:
            make_cbz(p)
        falta = _file(library / "Falta.cbz")
        importer, _ = _importer(library, [*[_file(p) for p in presentes], falta])

        c = await importer._comprobar_biblioteca()

        assert c.resultado is R.COMPROBADA and not c.bajas_omitidas
        assert (c.archivos_registrados, c.ausentes) == (10, 1)
        assert c.desaparecidos == ["Falta.cbz"] and falta.is_missing is True

    @pytest.mark.asyncio
    async def test_sin_archivos_registrados_es_una_comprobacion_trivial_no_un_aviso(self, tmp_path):
        library = tmp_path / "lib"
        library.mkdir()
        importer, _ = _importer(library, [])

        c = await importer._comprobar_biblioteca()

        assert c.resultado is R.COMPROBADA and c.archivos_registrados == 0 and c.ausentes == 0

    def test_como_dict_es_json_y_lleva_ambito_resultado_recuento_y_fecha(self):
        c = ComprobacionBiblioteca(resultado=R.RAIZ_VACIA, fecha=datetime(2026, 10, 28, 3, 0, tzinfo=UTC),
                                   archivos_registrados=12)

        assert c.como_dict() == {
            "ambito": "biblioteca", "resultado": "raiz_vacia", "archivos_registrados": 12, "ausentes": None,
            "bajas_omitidas": True, "fecha": "2026-10-28T03:00:00+00:00"}

    def test_la_clave_no_colisiona_con_las_del_informe(self):
        assert CLAVE_COMPROBACION not in {"kind", "imported", "duplicates", "unsorted", "errors",
                                          "disappeared", "reappeared"}


class TestFalloDeLaDeteccion:
    """Criterio 11: una excepción NO se pierde en el log ni se presenta como «no pasó nada»."""

    @pytest.mark.asyncio
    async def test_la_excepcion_queda_en_el_informe_y_no_marca_bajas(self, tmp_path, monkeypatch):
        library = tmp_path / "lib"
        library.mkdir()
        f = _file(library / "A.cbz", is_missing=False)
        importer, sesion = _importer(library, [f])
        importer._scan_dirs = []

        async def revienta():
            raise RuntimeError("fallo inesperado")

        monkeypatch.setattr(importer, "_comprobar_biblioteca", revienta)
        persistidos: list = []
        sesion.add = persistidos.append

        informe = await importer.scan_and_import()

        assert informe.comprobacion.resultado is R.FALLO_DETECCION
        assert informe.comprobacion.archivos_registrados is None
        assert informe.disappeared == [] and informe.reappeared == [] and f.is_missing is False
        run = persistidos[0]
        assert run.details[CLAVE_COMPROBACION]["resultado"] == "fallo_deteccion"
        assert run.details[CLAVE_COMPROBACION]["bajas_omitidas"] is True
        assert "fallo inesperado" not in str(run.details[CLAVE_COMPROBACION])  # sin texto de la excepción

    @pytest.mark.asyncio
    async def test_persist_run_escribe_la_clave_junto_a_las_demas(self):
        importer = Importer.__new__(Importer)
        sesion = MagicMock(add=MagicMock(), flush=AsyncMock())
        importer._db = sesion
        informe = ImportReport(started_at=datetime.now(UTC), finished_at=datetime.now(UTC))
        informe.comprobacion = ComprobacionBiblioteca(resultado=R.COMPROBADA, fecha=datetime.now(UTC),
                                                      archivos_registrados=3, ausentes=0)

        await importer._persist_run(informe)

        run = sesion.add.call_args.args[0]
        assert run.details["disappeared"] == [] and run.details["imported"] == []
        assert run.details[CLAVE_COMPROBACION]["resultado"] == "comprobada"
        assert "kind" not in run.details  # es un ciclo del importador: así se distingue de auditoría/adopción

    @pytest.mark.skipif(os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="root salta los permisos")
    @pytest.mark.asyncio
    async def test_una_carpeta_sin_permiso_de_paso_hace_fallar_la_comprobacion_no_da_de_baja(self, tmp_path):
        """Prueba aparte pedida por el criterio 11. `Path.exists()` hasta 3.13 solo ignora ENOENT/ENOTDIR/EBADF/ELOOP:
        un EACCES SUBE y llega al cuarto camino (`fallo_deteccion`). Desde 3.14 `exists()` lo traga y devuelve
        False, lo que habría dado de baja archivos que solo están en una carpeta sin permiso. `_existe` fija el
        comportamiento para cualquier versión: un permiso denegado NO es ausencia."""
        library = tmp_path / "lib"
        cerrada = library / "cerrada"
        cerrada.mkdir(parents=True)
        make_cbz(library / "otro.cbz")
        f = _file(cerrada / "Dentro.cbz")
        importer, _ = _importer(library, [f])
        cerrada.chmod(0)
        try:
            with pytest.raises(PermissionError):
                await importer._comprobar_biblioteca()
        finally:
            cerrada.chmod(0o700)
        assert f.is_missing is False and f.missing_since is None


class TestExiste:
    def test_ruta_inexistente_es_ausencia(self, tmp_path):
        assert _existe(str(tmp_path / "no-esta.cbz")) is False

    def test_ruta_bajo_un_archivo_es_ausencia(self, tmp_path):
        archivo = tmp_path / "archivo"
        archivo.write_text("x")
        assert _existe(str(archivo / "dentro.cbz")) is False  # ENOTDIR

    def test_ruta_presente(self, tmp_path):
        (tmp_path / "A.cbz").write_text("x")
        assert _existe(str(tmp_path / "A.cbz")) is True

    def test_nul_en_la_ruta_no_existe(self):
        assert _existe("a\x00b") is False

    @pytest.mark.parametrize("codigo", [errno.EACCES, errno.EIO, errno.ESTALE, errno.ETIMEDOUT])
    def test_otros_errores_no_prueban_ausencia(self, monkeypatch, codigo):
        def stat(_ruta):
            raise OSError(codigo, os.strerror(codigo))
        monkeypatch.setattr("zascarr.services.importer.os.stat", stat)
        with pytest.raises(OSError):
            _existe("/mnt/biblioteca/A.cbz")


# --- Presentación -----------------------------------------------------------------------------------------------------

def _html(d: EstadoComprobacion | None, **extra) -> str:
    templates = crear_templates()
    from zascarr.web.disponibilidad import registrar_filtros
    registrar_filtros(templates)
    plantilla = templates.env.get_template("_disponibilidad_aviso.html")
    return plantilla.render(d=d, no_disponibles=extra.get("no_disponibles", 0))


AHORA = datetime.now(UTC)


class TestMensajes:
    def test_sin_dato_no_dice_todo_disponible(self):
        html = _html(EstadoComprobacion())
        assert "Sin dato de última comprobación válida" in html
        assert "todo disponible" not in html.lower() and "disponibles todos" not in html.lower()

    @pytest.mark.parametrize("resultado", [R.RAIZ_INACCESIBLE, R.RAIZ_VACIA, R.DESAPARICION_MASIVA, R.FALLO_DETECCION])
    def test_si_no_se_pudo_comprobar_dice_sin_verificar_y_no_afirma_causas(self, resultado):
        d = EstadoComprobacion(resultado=resultado, fecha=AHORA, archivos_registrados=20, ausentes=15, ultima_valida=None)
        html = _html(d)

        assert "Disponibilidad actual sin verificar" in html
        assert "No se han marcado archivos como no encontrados en esta comprobación" in html
        assert "Sin dato de última comprobación válida" in html  # no consta una anterior
        for causa in ("desmont", "perdido", "se han perdido", "pérdida", "borrado"):
            assert causa not in html.lower()

    def test_raiz_vacia_describe_lo_observado_sin_afirmar_desmontaje(self):
        html = _html(EstadoComprobacion(resultado=R.RAIZ_VACIA, fecha=AHORA, archivos_registrados=5))
        assert "estaba vacía" in html and "desmont" not in html.lower()

    def test_la_ultima_valida_solo_se_enseña_si_consta(self):
        con = _html(EstadoComprobacion(resultado=R.RAIZ_INACCESIBLE, fecha=AHORA, ultima_valida=AHORA))
        sin = _html(EstadoComprobacion(resultado=R.RAIZ_INACCESIBLE, fecha=AHORA))
        assert "Última comprobación válida:" in con and "Sin dato de última comprobación válida" not in con
        assert "Última comprobación válida:" not in sin and "Sin dato de última comprobación válida" in sin

    def test_comprobada_dice_cuantas_rutas_se_miraron(self):
        html = _html(EstadoComprobacion(resultado=R.COMPROBADA, fecha=AHORA, archivos_registrados=120, ausentes=3))
        assert "120 rutas" in html and "3 no estaban" in html
        assert "sin verificar" not in html


class TestPulidoVisual:
    """Hallazgos de la validación en navegador real (2026-10-28): paréntesis anidados, una caja dentro de otra caja y un
    enlace suelto de 16 px de alto."""

    @pytest.mark.parametrize("resultado", [R.RAIZ_INACCESIBLE, R.RAIZ_VACIA, R.DESAPARICION_MASIVA, R.FALLO_DETECCION])
    def test_la_fecha_no_queda_entre_parentesis_dentro_de_otros(self, resultado):
        html = _html(EstadoComprobacion(resultado=resultado, fecha=AHORA, archivos_registrados=20, ausentes=15,
                                        ultima_valida=AHORA))
        plano = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        assert "(hoy))" not in plano and "((" not in plano
        assert not re.search(r"\([^()]*\([^()]*\)", plano), plano

    def test_el_aviso_no_mete_una_caja_dentro_de_otra(self):
        html = _html(EstadoComprobacion(resultado=R.RAIZ_VACIA, fecha=AHORA, ultima_valida=AHORA))
        assert 'class="caption' not in html   # `.caption` es una caja con borde: dentro de un aviso era caja en caja
        assert "Última comprobación válida:" in html

    def test_el_enlace_a_la_lista_en_estado_es_un_objetivo_tactil_y_no_texto_suelto(self):
        plantilla = Path(__file__).resolve().parents[1] / "src/zascarr/web/templates/estado.html"
        enlaces = re.findall(r'<a class="([^"]*)" href="/ui/no-disponibles">', plantilla.read_text(encoding="utf-8"))
        assert enlaces and all("btn" in c.split() for c in enlaces)   # `.btn` mide ≥ 44 px (test_web_movil)


class TestListaAccesible:
    """Validación con el árbol de accesibilidad (2026-10-28): una `<nav>` sin enlaces es una región vacía para un lector."""

    @staticmethod
    def _lista(monkeypatch, *, despues: str | None, siguiente: str | None) -> str:
        from zascarr.services import disponibilidad as servicio
        from zascarr.services.disponibilidad import ArchivoNoDisponible, PaginaNoDisponibles
        pagina = PaginaNoDisponibles(
            archivos=[ArchivoNoDisponible(id="1", nombre="A.cbz", desde=AHORA, serie="Serie", numero="1")],
            total=1, siguiente=siguiente)
        d = EstadoComprobacion(resultado=R.COMPROBADA, fecha=AHORA, archivos_registrados=5, ausentes=1, ultima_valida=AHORA)

        async def ultima(_db):
            return d

        async def listar(_db, _despues=None, limite=100):
            return pagina

        monkeypatch.setattr(servicio, "ultima_comprobacion", ultima)
        monkeypatch.setattr(servicio, "listar_no_disponibles", listar)
        cliente = _cliente(SesionSoloLectura(MagicMock()))
        return cliente.get("/ui/no-disponibles", params={"despues": despues} if despues else None).text

    def test_una_sola_pagina_no_pinta_la_nav_de_paginacion(self, monkeypatch):
        html = self._lista(monkeypatch, despues=None, siguiente=None)
        assert "A.cbz" in html and "<nav class=\"pagination\"" not in html

    def test_con_siguiente_o_en_otra_pagina_si_hay_nav_con_enlaces(self, monkeypatch):
        con_siguiente = self._lista(monkeypatch, despues=None, siguiente="tok")
        assert '<nav class="pagination"' in con_siguiente and 'rel="next"' in con_siguiente
        otra = self._lista(monkeypatch, despues="x", siguiente=None)
        assert '<nav class="pagination"' in otra and "Volver al principio" in otra


# --- Rutas (sesión falsa) ---------------------------------------------------------------------------------------------

class SesionQueFalla:
    """Cualquier consulta lanza: la base no contesta."""

    def __init__(self):
        self.rollback = AsyncMock()
        self.commit = AsyncMock()
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.consultas = 0

    async def execute(self, _sentencia):
        self.consultas += 1
        raise ConnectionError("se cortó la conexión con /srv/secreto/ruta")


class SesionSoloLectura:
    """Responde a las consultas de lectura y deja constancia de cualquier escritura."""

    def __init__(self, primera, segunda=None):
        self._cola = [primera] + ([segunda] if segunda is not None else [])
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.delete = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.sentencias: list = []

    async def execute(self, sentencia):
        self.sentencias.append(sentencia)
        return self._cola.pop(0) if self._cola else MagicMock()


def _cliente(sesion):
    async def _get_db():
        yield sesion
    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _sin_overrides():
    yield
    app.dependency_overrides.pop(get_db, None)


class TestRutas:
    def test_lista_con_lectura_fallida_dice_que_no_pudo_leer_y_no_parece_vacia(self):
        sesion = SesionQueFalla()
        r = _cliente(sesion).get("/ui/no-disponibles")

        assert r.status_code == 503
        assert "No se ha podido leer la lista" in r.text
        assert "Ningún archivo figura como no disponible" not in r.text
        assert "todo disponible" not in r.text.lower().replace("no significa que todo esté disponible", "")
        assert "/srv/secreto" not in r.text  # nada de la excepción llega a la pantalla

    def test_estado_sigue_sirviendose_si_la_base_no_contesta_y_lo_dice(self):
        r = _cliente(SesionQueFalla()).get("/estado")

        assert r.status_code == 200
        assert "No se ha podido leer el resultado de la última revisión" in r.text
        assert "Esto no significa que todo esté disponible" in r.text
        assert "/srv/secreto" not in r.text

    def test_abrir_la_lista_solo_hace_consultas_de_lectura(self):
        """Criterio 8: ni escritura ni comprobación. La sesión falsa registra cualquier `add`/`flush`/`delete`; el
        servicio no llama a `Path.exists` (no recibe ninguna ruta de disco que comprobar)."""
        ultimo = MagicMock()
        ultimo.first.return_value = None  # sin ningún ciclo con la clave: «sin dato»
        total = MagicMock()
        total.scalar_one.return_value = 0
        pagina = MagicMock()
        pagina.all.return_value = []
        sesion = SesionSoloLectura(ultimo, total)
        sesion._cola.append(pagina)

        r = _cliente(sesion).get("/ui/no-disponibles")

        assert r.status_code == 200
        assert "Sin dato de última comprobación válida" in r.text
        sesion.add.assert_not_called()
        sesion.flush.assert_not_awaited()
        sesion.delete.assert_not_awaited()
        for s in sesion.sentencias:
            texto = str(s).upper()
            assert texto.startswith("SELECT"), texto[:60]
