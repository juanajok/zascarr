# ruff: noqa: E501
"""BL-DUP3 (#266): resolver una carpeta repetida sobre FS real + PG."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ApartadoOperacion
from zascarr.services.apartado_duplicados import ApartadoDuplicadosService, GrupoEntrada
from zascarr.services.carpetas_duplicadas import (
    analizar_par,
    apartar_carpeta_vacia,
    deshacer_carpeta,
    previsualizar_carpetas,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
SECRET = "secreto-de-prueba-carpetas"


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    async with b.motor.begin() as c:
        await c.execute(text("TRUNCATE apartado_grupos, apartado_operaciones CASCADE"))
    yield b
    await b.cerrar()


def _arbol(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    for carpeta in (a, b):
        (carpeta / "comun-1.cbz").write_bytes(b"comun-1")
        (carpeta / "comun-2.cbz").write_bytes(b"comun-2")
    (a / "solo-a.cbz").write_bytes(b"solo-a")
    (b / "solo-b.cbz").write_bytes(b"solo-b")
    (a / "distinto.cbz").write_bytes(b"version-a")
    (b / "distinto.cbz").write_bytes(b"version-b")
    return a, b


@pytest.mark.asyncio
async def test_detalle_distingue_comunes_identicos_distintos_y_solos(banco, tmp_path):
    a, b = _arbol(tmp_path)
    d = await analizar_par(str(a), str(b), tmp_path)
    assert [x.nombre for x in d.comunes_identicos] == ["comun-1.cbz", "comun-2.cbz"]
    assert [x.nombre for x in d.comunes_distintos] == ["distinto.cbz"]
    assert d.solo_en_a == ("solo-a.cbz",)
    assert d.solo_en_b == ("solo-b.cbz",)
    assert d.quedara_vacia is False


@pytest.mark.asyncio
async def test_confirmar_solo_aparta_comunes_identicos_y_deshacer(banco, tmp_path):
    a, b = _arbol(tmp_path)
    async with banco.fabrica() as s:
        vista = await previsualizar_carpetas(
            s, str(a), str(b), "a", library=tmp_path, secret=SECRET)
        assert vista.archivos == 2 and not (tmp_path / ".zascarr").exists()
        operaciones = []
        for entrada in vista.entradas:
            datos = json.loads(entrada.grupo_json)
            servicio = ApartadoDuplicadosService(
                s, settings=type("_S", (), {"library_path": tmp_path, "secret_key": SECRET})(),
                secret=SECRET)
            resultado = await servicio.confirmar(
                entrada.token, [GrupoEntrada(datos["sha256"], tuple(datos["rutas"]),
                                             int(datos["keep_index"]))])
            assert resultado.estado == "confirmada"
            operaciones.append(resultado.operacion)
        op = (await s.execute(select(ApartadoOperacion))).scalars().first()
        assert op is not None
        # Los comunes de B se han apartado; lo distinto y lo solo suyo siguen.
        assert (a / "comun-1.cbz").exists() and not (b / "comun-1.cbz").exists()
        assert (a / "distinto.cbz").read_bytes() == b"version-a"
        assert (b / "distinto.cbz").read_bytes() == b"version-b"
        assert (b / "solo-b.cbz").exists()
        assert (a / "solo-a.cbz").exists()
        servicio = ApartadoDuplicadosService(
            s, settings=type("_S", (), {"library_path": tmp_path, "secret_key": SECRET})(),
            secret=SECRET)
        for operacion in operaciones:
            assert (await servicio.deshacer(operacion)).estado == "deshecha"
        assert (b / "comun-1.cbz").exists() and (b / "comun-2.cbz").exists()
        assert (b / "comun-1.cbz").stat().st_ino != (a / "comun-1.cbz").stat().st_ino
        assert (b / "comun-2.cbz").stat().st_ino != (a / "comun-2.cbz").stat().st_ino


@pytest.mark.asyncio
async def test_subconjunto_deja_carpeta_vacia_y_se_puede_deshacer(banco, tmp_path):
    completa = tmp_path / "Completa"
    parcial = tmp_path / "Parcial"
    completa.mkdir()
    parcial.mkdir()
    for nombre in ("01.cbz", "02.cbz"):
        (completa / nombre).write_bytes(nombre.encode())
        (parcial / nombre).write_bytes(nombre.encode())
    async with banco.fabrica() as s:
        vista = await previsualizar_carpetas(
            s, str(completa), str(parcial), "a", library=tmp_path, secret=SECRET)
        assert vista.quedara_vacia is True
        for entrada in vista.entradas:
            datos = json.loads(entrada.grupo_json)
            await ApartadoDuplicadosService(
                s, settings=type("_S", (), {"library_path": tmp_path, "secret_key": SECRET})(),
                secret=SECRET).confirmar(
                    entrada.token, [GrupoEntrada(datos["sha256"], tuple(datos["rutas"]),
                                                 int(datos["keep_index"]))])
        assert not any(parcial.iterdir())
        operacion = await apartar_carpeta_vacia(
            s, str(parcial), library=tmp_path, secret=SECRET)
        assert not parcial.exists()
        op = await s.get(ApartadoOperacion, __import__("uuid").UUID(operacion))
        assert op is not None and op.modo == "carpeta"
        await deshacer_carpeta(s, operacion, library=tmp_path)
        assert parcial.is_dir() and not any(parcial.iterdir())


@pytest.mark.asyncio
async def test_anidamiento_redundante_se_puede_comparar(banco, tmp_path):
    exterior = tmp_path / "Serie"
    interior = exterior / "Completa"
    interior.mkdir(parents=True)
    (exterior / "01.cbz").write_bytes(b"uno")
    (interior / "01.cbz").write_bytes(b"uno")
    d = await analizar_par(str(exterior), str(interior), tmp_path)
    assert [x.nombre for x in d.comunes_identicos] == ["01.cbz"]
    assert d.solo_en_a == () and d.solo_en_b == ()
    assert d.quedara_vacia is True
