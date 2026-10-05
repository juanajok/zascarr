# ruff: noqa: E501
"""Migración 0017 (`asignacion_operaciones`, ADR 0006): esquema, reservas, borrado y actualización — Postgres real.

Cada módulo trabaja en BDs efímeras propias (nada toca la compartida). Se saltan sin `TEST_DATABASE_URL`.
Lo que se fija aquí es el CONTRATO del esquema: el servicio de asignación (otra historia) se construirá encima.
"""
from __future__ import annotations

import asyncio
import os
import re
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    AsignacionEstado,
    AsignacionOperacion,
    ComicTradition,
    File,
    FileFormat,
    Issue,
    LocalAlias,
    MetadataSource,
    Series,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

VIVOS = {e.value for e in ASIGNACION_ESTADOS_VIVOS}
CERRADOS = {e.value for e in AsignacionEstado} - VIVOS
SHA = "a" * 64


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


class Banco:
    """Una BD concreta con atajos para sembrar y para insertar operaciones por SQL."""

    def __init__(self, url: str):
        self.url = url
        self.motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fab = async_sessionmaker(self.motor, expire_on_commit=False)

    async def limpiar(self):
        async with self.motor.begin() as c:
            await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, local_aliases, wishlist CASCADE"))

    async def serie_y_archivos(self, n: int = 1):
        async with self.fab() as s:
            serie = Series(id=uuid4(), title=f"Serie {uuid4().hex[:6]}", tradition=ComicTradition.AMERICAN)
            archivos = [File(id=uuid4(), file_path=f"/lib/_Unsorted/{uuid4().hex}.cbz", file_name="x.cbz",
                             file_format=FileFormat.CBZ, sha256_hash=SHA) for _ in range(n)]
            s.add(serie)
            s.add_all(archivos)
            await s.commit()
        return serie.id, [a.id for a in archivos]

    @staticmethod
    def params(file_id, serie_id, estado="preparada", destino=None, **kw):
        base = dict(id=uuid4(), f=file_id, s=serie_id, e=estado, o=f"/lib/_Unsorted/{uuid4().hex}.cbz",
                    d=destino or f"/lib/Comics/S/{uuid4().hex}.cbz", t="/lib/Comics/S/.t.part",
                    sz=100, mt=1, sha=SHA, n="12", fmt="single_issue")
        base.update(kw)
        return base

    SQL = ("INSERT INTO asignacion_operaciones (id, file_id, series_id, estado, origen, destino, temporal, "
           "size_bytes, mtime_ns, sha256, issue_number, formato) VALUES (:id, :f, :s, CAST(:e AS asignacion_estado), "
           ":o, :d, :t, :sz, :mt, :sha, :n, CAST(:fmt AS issue_format))")

    async def insertar(self, **p):
        async with self.motor.begin() as c:
            await c.execute(text(self.SQL), p)
        return p["id"]

    async def cerrar(self):
        await self.motor.dispose()


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    yield b
    await b.cerrar()


class TestEsquema:

    @pytest.mark.asyncio
    async def test_columnas_tipos_y_nulos(self, banco):
        async with banco.motor.connect() as c:
            filas = (await c.execute(text(
                "SELECT column_name, udt_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'asignacion_operaciones'"))).all()
        esperado = {
            "id": ("uuid", "NO"), "file_id": ("uuid", "YES"), "series_id": ("uuid", "YES"),
            "estado": ("asignacion_estado", "NO"), "origen": ("varchar", "NO"), "destino": ("varchar", "NO"),
            "temporal": ("varchar", "NO"), "size_bytes": ("int8", "NO"), "mtime_ns": ("int8", "NO"),
            "sha256": ("varchar", "NO"), "issue_number": ("varchar", "NO"), "formato": ("issue_format", "NO"),
            "aprender_alias": ("bool", "NO"), "epoca": ("int4", "NO"), "creada": ("timestamptz", "NO"),
            "actualizada": ("timestamptz", "NO"),
        }
        assert {f[0]: (f[1], f[2]) for f in filas} == esperado

    @pytest.mark.asyncio
    async def test_el_enum_tiene_exactamente_los_cuatro_estados_persistidos(self, banco):
        """Los RESULTADOS del servicio (reparacion_pendiente, asignado_limpieza_pendiente…) NO son estados."""
        async with banco.motor.connect() as c:
            valores = [r[0] for r in (await c.execute(text(
                "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'asignacion_estado' ORDER BY enumsortorder"))).all()]
        assert valores == ["preparada", "confirmada", "limpiada", "cancelada"]
        assert valores == [e.value for e in AsignacionEstado]
        assert {"preparada", "confirmada"} == VIVOS
        for resultado in ("reparacion_pendiente", "asignado_limpieza_pendiente", "pendiente", "destino_ocupado"):
            assert resultado not in valores

    @pytest.mark.asyncio
    async def test_los_indices_del_modelo_coinciden_con_los_de_la_tabla_en_todo(self, banco):
        """Nombre, unicidad, columnas (en orden) y predicado de CADA índice — no un subconjunto.

        LIMITACIÓN: del predicado se comparan los LITERALES de estado, no la expresión entera: detecta cambiar qué
        estados incluye, pero no distinguiría `IN` de `NOT IN` con los mismos literales. No es una comparación
        semántica completa, y el autogenerate de Alembic tampoco compara predicados."""
        async with banco.motor.connect() as c:
            filas = (await c.execute(text("""
                SELECT i.relname, ix.indisunique,
                       array_agg(a.attname ORDER BY k.ord) AS columnas,
                       pg_get_expr(ix.indpred, ix.indrelid) AS predicado
                FROM pg_index ix
                JOIN pg_class i ON i.oid = ix.indexrelid
                JOIN pg_class t ON t.oid = ix.indrelid
                JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
                WHERE t.relname = 'asignacion_operaciones' AND NOT ix.indisprimary
                GROUP BY i.relname, ix.indisunique, ix.indpred, ix.indrelid"""))).all()

        def literales(predicado):
            return frozenset(re.findall(r"'([a-z_]+)'", predicado)) if predicado else None
        en_bd = {f[0]: (f[1], tuple(f[2]), literales(f[3])) for f in filas}
        en_modelo = {}
        for ix in AsignacionOperacion.__table__.indexes:
            donde = ix.dialect_options["postgresql"]["where"]
            en_modelo[ix.name] = (bool(ix.unique), tuple(col.name for col in ix.columns),
                                  literales(str(donde)) if donde is not None else None)
        assert en_modelo == en_bd
        assert set(en_bd) == {"uq_asignacion_viva_por_archivo", "uq_asignacion_viva_por_destino",
                              "ix_asignacion_viva_creada", "ix_asignacion_file_id", "ix_asignacion_series_id"}
        assert en_bd["uq_asignacion_viva_por_destino"][2] == VIVOS

    @pytest.mark.asyncio
    async def test_columnas_y_comprobaciones_del_modelo_coinciden_con_la_tabla(self, banco):
        async with banco.motor.connect() as c:
            columnas = {r[0] for r in (await c.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'asignacion_operaciones'"))).all()}
            checks = {r[0] for r in (await c.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'asignacion_operaciones'::regclass AND contype = 'c'"))).all()}
        tabla = AsignacionOperacion.__table__
        assert {col.name for col in tabla.columns} == columnas
        assert {c.name for c in tabla.constraints if c.name and c.name.startswith("ck_")} == checks

    @pytest.mark.asyncio
    async def test_alembic_no_propone_ningun_cambio_para_esta_tabla(self, banco):
        """El autogenerate de Alembic compara columnas, tipos, nulos, índices y claves foráneas del modelo con la BD.

        Va en un SUBPROCESO con el entorno saneado: en este proceso `import alembic` resuelve al directorio
        `alembic/` del repo (el de las migraciones), no al paquete instalado."""
        import subprocess
        import sys

        from tests._pg import RAIZ, entorno_para_alembic
        guion = (
            "import asyncio, json\n"
            "from alembic.autogenerate import compare_metadata\n"
            "from alembic.migration import MigrationContext\n"
            "from sqlalchemy.ext.asyncio import create_async_engine\n"
            "from zascarr.database import Base\n"
            "import zascarr.models\n"
            "def comparar(c):\n"
            "    return compare_metadata(MigrationContext.configure(c, opts={'compare_type': True}), Base.metadata)\n"
            "async def main():\n"
            "    m = create_async_engine(__import__('os').environ['DATABASE_URL'])\n"
            "    async with m.connect() as c:\n"
            "        d = await c.run_sync(comparar)\n"
            "    await m.dispose()\n"
            "    print(json.dumps([repr(x) for x in d if 'asignacion_operaciones' in repr(x)]))\n"
            "asyncio.run(main())\n"
        )
        r = subprocess.run([sys.executable, "-c", guion], cwd=RAIZ, env=entorno_para_alembic(os.environ, banco.url),
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-1500:]
        assert r.stdout.strip().splitlines()[-1] == "[]", r.stdout

    @pytest.mark.asyncio
    @pytest.mark.parametrize("clave", ["archivo", "destino"])
    @pytest.mark.parametrize("estado", [e.value for e in AsignacionEstado])
    async def test_solo_los_estados_vivos_reservan(self, banco, clave, estado):
        """Para CADA estado persistido: ¿una segunda operación viva sobre lo mismo choca? Solo si el estado es vivo."""
        serie, (f1, f2) = await banco.serie_y_archivos(2)
        comun = f"/lib/Comics/S/{uuid4().hex}.cbz"
        if clave == "archivo":
            await banco.insertar(**banco.params(f1, serie, estado))
            segunda = banco.params(f1, serie, "preparada")
        else:
            await banco.insertar(**banco.params(f1, serie, estado, destino=comun))
            segunda = banco.params(f2, serie, "preparada", destino=comun)
        if estado in VIVOS:
            with pytest.raises(IntegrityError, match="uq_asignacion_viva_por_" + ("archivo" if clave == "archivo" else "destino")):
                await banco.insertar(**segunda)
        else:
            await banco.insertar(**segunda)           # lo cerrado no reserva

    @pytest.mark.asyncio
    @pytest.mark.parametrize("campo,valor", [
        ("sha", "A" * 64), ("sha", "a" * 63), ("sha", "zz" * 32), ("sz", -1), ("n", "   "),
        ("t", "IGUAL"), ("o", "IGUAL"),
    ])
    async def test_las_comprobaciones_rechazan_datos_incoherentes(self, banco, campo, valor):
        serie, (f1,) = await banco.serie_y_archivos()
        p = banco.params(f1, serie)
        if valor == "IGUAL":
            p[campo] = p["d"]                           # temporal u origen == destino
        else:
            p[campo] = valor
        with pytest.raises(IntegrityError, match="ck_asignacion"):
            await banco.insertar(**p)

    @pytest.mark.asyncio
    async def test_una_operacion_viva_exige_archivo_y_serie(self, banco):
        serie, (f1,) = await banco.serie_y_archivos()
        for estado in VIVOS:
            with pytest.raises(IntegrityError, match="ck_asignacion_viva_con_referencias"):
                await banco.insertar(**banco.params(None, serie, estado))
            with pytest.raises(IntegrityError, match="ck_asignacion_viva_con_referencias"):
                await banco.insertar(**banco.params(f1, None, estado))
        await banco.insertar(**banco.params(None, None, "limpiada"))     # el historial puede perderlos

    @pytest.mark.asyncio
    async def test_la_epoca_nace_en_cero_y_el_alias_se_aprende_por_defecto(self, banco):
        serie, (f1,) = await banco.serie_y_archivos()
        op = await banco.insertar(**banco.params(f1, serie))
        async with banco.fab() as s:
            o = await s.get(AsignacionOperacion, op)
        assert o.epoca == 0 and o.aprender_alias is True and o.estado is AsignacionEstado.PREPARADA


class TestReservasConcurrentes:

    async def _en_dos_sesiones(self, banco, p1, p2):
        """A inserta SIN confirmar; B intenta lo mismo y debe quedarse esperando al desenlace de A."""
        a = banco.fab()
        sa = await a.__aenter__()
        await sa.execute(text(banco.SQL), p1)

        async def segunda():
            async with banco.fab() as sb:
                await sb.execute(text(banco.SQL), p2)
                await sb.commit()
        tarea = asyncio.create_task(segunda())
        await asyncio.sleep(0.6)
        esperaba = not tarea.done()
        return a, sa, tarea, esperaba

    @pytest.mark.asyncio
    async def test_dos_sesiones_no_pueden_reclamar_el_mismo_archivo(self, banco):
        serie, (f1,) = await banco.serie_y_archivos()
        a, sa, tarea, esperaba = await self._en_dos_sesiones(
            banco, banco.params(f1, serie), banco.params(f1, serie))
        assert esperaba                                     # B espera: la reserva de A aún no está confirmada
        await sa.commit()
        await a.__aexit__(None, None, None)
        with pytest.raises(IntegrityError, match="uq_asignacion_viva_por_archivo"):
            await asyncio.wait_for(tarea, 30)

    @pytest.mark.asyncio
    async def test_dos_sesiones_no_pueden_reservar_el_mismo_destino(self, banco):
        serie, (f1, f2) = await banco.serie_y_archivos(2)
        destino = f"/lib/Comics/S/{uuid4().hex}.cbz"
        a, sa, tarea, esperaba = await self._en_dos_sesiones(
            banco, banco.params(f1, serie, destino=destino), banco.params(f2, serie, destino=destino))
        assert esperaba
        await sa.commit()
        await a.__aexit__(None, None, None)
        with pytest.raises(IntegrityError, match="uq_asignacion_viva_por_destino"):
            await asyncio.wait_for(tarea, 30)

    @pytest.mark.asyncio
    async def test_si_la_primera_se_revierte_la_segunda_puede_reservar(self, banco):
        serie, (f1,) = await banco.serie_y_archivos()
        a, sa, tarea, esperaba = await self._en_dos_sesiones(
            banco, banco.params(f1, serie), banco.params(f1, serie))
        assert esperaba
        await sa.rollback()
        await a.__aexit__(None, None, None)
        await asyncio.wait_for(tarea, 30)                  # ahora sí

    @pytest.mark.asyncio
    async def test_ocho_reclamos_simultaneos_del_mismo_archivo_dejan_uno(self, banco):
        serie, (f1,) = await banco.serie_y_archivos()

        async def reclamar():
            try:
                await banco.insertar(**banco.params(f1, serie))
                return "ok"
            except IntegrityError:
                return "choque"
        resultados = await asyncio.gather(*[reclamar() for _ in range(8)])
        assert sorted(resultados) == ["choque"] * 7 + ["ok"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cierre", ["limpiada", "cancelada"])
    async def test_cerrar_la_operacion_permite_una_nueva_reserva(self, banco, cierre):
        serie, (f1,) = await banco.serie_y_archivos()
        destino = f"/lib/Comics/S/{uuid4().hex}.cbz"
        op = await banco.insertar(**banco.params(f1, serie, destino=destino))
        with pytest.raises(IntegrityError):
            await banco.insertar(**banco.params(f1, serie, destino=destino))
        async with banco.motor.begin() as c:
            await c.execute(text("UPDATE asignacion_operaciones SET estado = CAST(:e AS asignacion_estado) WHERE id = :i"),
                            {"e": cierre, "i": op})
        await banco.insertar(**banco.params(f1, serie, destino=destino))          # mismo archivo y mismo destino

    @pytest.mark.asyncio
    async def test_una_reparacion_pendiente_no_libera_la_reserva(self, banco):
        """`reparacion_pendiente` es un RESULTADO: la operación sigue `confirmada`, viva, con su destino reservado."""
        serie, (f1, f2) = await banco.serie_y_archivos(2)
        destino = f"/lib/Comics/S/{uuid4().hex}.cbz"
        await banco.insertar(**banco.params(f1, serie, "confirmada", destino=destino))
        with pytest.raises(IntegrityError, match="uq_asignacion_viva_por_destino"):
            await banco.insertar(**banco.params(f2, serie, "preparada", destino=destino))
        with pytest.raises(IntegrityError, match="uq_asignacion_viva_por_archivo"):
            await banco.insertar(**banco.params(f1, serie, "preparada"))


class TestPoliticaDeBorrado:

    async def _con_issue_y_archivo(self, banco):
        serie, (f1,) = await banco.serie_y_archivos()
        async with banco.fab() as s:
            issue = Issue(id=uuid4(), series_id=serie, issue_number="12")
            s.add(issue)
            await s.flush()
            f = await s.get(File, f1)
            f.issue_id = issue.id
            await s.commit()
        return serie, f1, issue.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", sorted(VIVOS))
    async def test_borrar_un_archivo_con_operacion_viva_falla_y_no_pierde_nada(self, banco, estado):
        serie, (f1,) = await banco.serie_y_archivos()
        op = await banco.insertar(**banco.params(f1, serie, estado))
        with pytest.raises(IntegrityError, match="ck_asignacion_viva_con_referencias"):
            async with banco.motor.begin() as c:
                await c.execute(text("DELETE FROM files WHERE id = :f"), {"f": f1})
        async with banco.fab() as s:
            assert await s.get(File, f1) is not None
            o = await s.get(AsignacionOperacion, op)
            assert o is not None and o.file_id == f1 and o.estado.value == estado

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", sorted(VIVOS))
    async def test_borrar_una_serie_con_operacion_viva_falla_y_no_borra_nada(self, banco, estado):
        serie, f1, issue = await self._con_issue_y_archivo(banco)
        op = await banco.insertar(**banco.params(f1, serie, estado))
        with pytest.raises(IntegrityError):
            async with banco.motor.begin() as c:
                await c.execute(text("DELETE FROM series WHERE id = :s"), {"s": serie})
        async with banco.fab() as s:
            assert await s.get(Series, serie) is not None and await s.get(Issue, issue) is not None
            assert await s.get(File, f1) is not None and await s.get(AsignacionOperacion, op) is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", sorted(CERRADOS))
    async def test_con_la_operacion_cerrada_el_borrado_procede_y_queda_el_historial(self, banco, estado):
        serie, (f1,) = await banco.serie_y_archivos()
        p = banco.params(f1, serie, estado)
        op = await banco.insertar(**p)
        async with banco.motor.begin() as c:
            await c.execute(text("DELETE FROM files WHERE id = :f"), {"f": f1})
            await c.execute(text("DELETE FROM series WHERE id = :s"), {"s": serie})
        async with banco.fab() as s:
            o = await s.get(AsignacionOperacion, op)
        assert o is not None and o.file_id is None and o.series_id is None
        assert (o.origen, o.destino, o.sha256, o.estado.value) == (p["o"], p["d"], SHA, estado)      # historial íntegro


# ── Actualización y bajada, en BDs efímeras propias ────────────────────────────────────────────────

async def sembrar_a_0016(url: str) -> dict:
    """Datos reales del esquema ANTERIOR: serie, issues (con decisión manual), archivos, alias y wishlist."""
    from zascarr.models import Wishlist, WishlistStatus
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with fab() as s:
        serie = Series(id=uuid4(), title="Saga del Faro", tradition=ComicTradition.AMERICAN, start_year=2010)
        manual = Issue(id=uuid4(), series_id=serie.id, issue_number="12", locked_fields=["series_id", "issue_number"],
                       metadata_source=MetadataSource.MANUAL.value)
        otro = Issue(id=uuid4(), series_id=serie.id, issue_number="13")
        f_manual = File(id=uuid4(), file_path="/lib/Comics/Saga/Saga #012.cbz", file_name="Saga #012.cbz",
                        file_format=FileFormat.CBZ, sha256_hash=SHA, issue_id=manual.id,
                        metadata_source=MetadataSource.MANUAL.value, review_dismissed=False)
        f_ignorado = File(id=uuid4(), file_path="/lib/_Unsorted/suelto.cbz", file_name="suelto.cbz",
                          file_format=FileFormat.CBZ, sha256_hash="b" * 64, review_dismissed=True,
                          metadata_={"match_status": "unsorted", "review_motivo": "colision"})
        alias = LocalAlias(pattern_norm="saga del faro", series_id=serie.id)
        deseo = Wishlist(id=uuid4(), series_id=serie.id, status=WishlistStatus.WANTED)
        s.add(serie)
        await s.flush()
        s.add_all([manual, otro])
        await s.flush()
        s.add_all([f_manual, f_ignorado, alias, deseo])
        await s.commit()
        ids = {"serie": serie.id, "manual": manual.id, "f_manual": f_manual.id, "f_ignorado": f_ignorado.id}
    await motor.dispose()
    return ids


async def foto(url: str, ids: dict) -> dict:
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with fab() as s:
        f_m = await s.get(File, ids["f_manual"])
        f_i = await s.get(File, ids["f_ignorado"])
        i_m = await s.get(Issue, ids["manual"])
        res = dict(
            series=(await s.execute(text("SELECT count(*) FROM series"))).scalar(),
            issues=(await s.execute(text("SELECT count(*) FROM issues"))).scalar(),
            files=(await s.execute(text("SELECT count(*) FROM files"))).scalar(),
            alias=[a.pattern_norm for a in (await s.execute(select(LocalAlias))).scalars()],
            wishlist=(await s.execute(text("SELECT count(*) FROM wishlist"))).scalar(),
            f_manual=(f_m.file_path, f_m.issue_id, f_m.metadata_source, f_m.sha256_hash),
            f_ignorado=(f_i.review_dismissed, dict(f_i.metadata_)),
            i_manual=(i_m.metadata_source, list(i_m.locked_fields)),
        )
    await motor.dispose()
    return res


async def version(url: str) -> str:
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    async with motor.connect() as c:
        v = (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    await motor.dispose()
    return v


async def existe_tabla_y_tipo(url: str) -> tuple[bool, bool]:
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    async with motor.connect() as c:
        t = (await c.execute(text("SELECT to_regclass('public.asignacion_operaciones') IS NOT NULL"))).scalar()
        ty = (await c.execute(text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'asignacion_estado')"))).scalar()
    await motor.dispose()
    return t, ty


class TestActualizacionDesdeLa0016:

    @pytest.mark.asyncio
    async def test_actualizar_con_datos_sembrados_preserva_archivos_issues_alias_y_decisiones_manuales(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "0016")
            assert await existe_tabla_y_tipo(url) == (False, False)
            ids = await sembrar_a_0016(url)
            antes = await foto(url, ids)
            alembic(url, "upgrade", "head")
            assert await version(url) == "0017"
            assert await foto(url, ids) == antes                                 # NADA cambió
            assert antes["f_manual"][2] == "manual" and antes["f_ignorado"][0] is True
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            async with motor.connect() as c:
                assert (await c.execute(text("SELECT count(*) FROM asignacion_operaciones"))).scalar() == 0
            await motor.dispose()
            alembic(url, "upgrade", "head")                                      # idempotente
            assert await foto(url, ids) == antes


class TestBajada:
    """El downgrade es DESTRUCTIVO para las operaciones: se niega si hay vivas y descarta el historial si no."""

    async def _a_head_con_datos(self, url):
        migrar_a_head(url)
        ids = await sembrar_a_0016(url)
        return ids

    async def _insertar(self, url, estado, ids):
        b = Banco(url)
        try:
            await b.insertar(**b.params(ids["f_manual"], ids["serie"], estado))
        finally:
            await b.cerrar()

    @pytest.mark.asyncio
    async def test_sin_operaciones_baja_y_vuelve_a_subir_sin_tocar_los_datos(self):
        async with bd_efimera(URL) as url:
            ids = await self._a_head_con_datos(url)
            antes = await foto(url, ids)
            alembic(url, "downgrade", "0016")
            assert await version(url) == "0016" and await existe_tabla_y_tipo(url) == (False, False)
            assert await foto(url, ids) == antes
            alembic(url, "upgrade", "head")
            assert await existe_tabla_y_tipo(url) == (True, True) and await foto(url, ids) == antes

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", sorted(VIVOS))
    async def test_con_una_operacion_viva_se_niega_y_no_pierde_nada(self, estado):
        async with bd_efimera(URL) as url:
            ids = await self._a_head_con_datos(url)
            await self._insertar(url, estado, ids)
            r = alembic(url, "downgrade", "0016", estricto=False)
            assert r.returncode != 0 and "operaciones de asignación vivas" in r.stderr
            assert await version(url) == "0017" and await existe_tabla_y_tipo(url) == (True, True)
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            async with motor.connect() as c:
                assert (await c.execute(text("SELECT estado::text FROM asignacion_operaciones"))).scalar() == estado
            await motor.dispose()

    @pytest.mark.asyncio
    async def test_cerrada_la_operacion_ya_se_puede_bajar_y_se_pierde_el_historial(self):
        async with bd_efimera(URL) as url:
            ids = await self._a_head_con_datos(url)
            await self._insertar(url, "limpiada", ids)
            antes = await foto(url, ids)
            alembic(url, "downgrade", "0016")                                    # solo había historial
            assert await existe_tabla_y_tipo(url) == (False, False)              # el historial se DESCARTÓ
            assert await foto(url, ids) == antes                                 # y los datos de la colección, no

    @pytest.mark.asyncio
    async def test_bajar_dos_versiones_pasa_por_la_0017_sin_problemas(self):
        """Las pruebas de migración 0015/0016 bajan desde `head` atravesando esta migración."""
        async with bd_efimera(URL) as url:
            await self._a_head_con_datos(url)
            alembic(url, "downgrade", "0015")
            assert await version(url) == "0015"
            alembic(url, "upgrade", "head")
            assert await version(url) == "0017"


class TestBajadaConcurrente:
    """Revisión de #77: contar y borrar no pueden estar separados por una confirmación ajena."""

    @pytest.mark.asyncio
    async def test_una_operacion_viva_confirmada_durante_la_bajada_la_hace_negarse(self):
        async with bd_efimera(URL) as url:
            migrar_a_head(url)
            ids = await sembrar_a_0016(url)
            b = Banco(url)
            try:
                # Sesión A: inserta una operación viva y NO confirma todavía.
                a = b.fab()
                sa = await a.__aenter__()
                await sa.execute(text(b.SQL), b.params(ids["f_manual"], ids["serie"], "preparada"))
                # Sesión B: intenta bajar (en otro proceso, como `alembic downgrade`).
                bajada = asyncio.create_task(asyncio.to_thread(alembic, url, "downgrade", "0016", estricto=False))
                # B debe quedarse ESPERANDO el bloqueo de la tabla (no contar, ver cero y seguir).
                esperando = False
                for _ in range(100):
                    await asyncio.sleep(0.2)
                    async with b.motor.connect() as c:
                        esperando = (await c.execute(text(
                            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                            "AND query ILIKE 'LOCK TABLE asignacion_operaciones%'"))).scalar() > 0
                    if esperando:
                        break
                assert esperando, "la bajada no está esperando el bloqueo de la tabla"
                assert not bajada.done()
                await sa.commit()                                  # A confirma la operación viva
                await a.__aexit__(None, None, None)
                r = await asyncio.wait_for(bajada, 120)
            finally:
                await b.cerrar()
            assert r.returncode != 0 and "operaciones de asignación vivas" in r.stderr
            assert await version(url) == "0017" and await existe_tabla_y_tipo(url) == (True, True)
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            async with motor.connect() as c:
                assert (await c.execute(text("SELECT estado::text FROM asignacion_operaciones"))).scalar() == "preparada"
            await motor.dispose()

    @pytest.mark.asyncio
    async def test_si_la_otra_sesion_se_revierte_la_bajada_procede(self):
        async with bd_efimera(URL) as url:
            migrar_a_head(url)
            ids = await sembrar_a_0016(url)
            b = Banco(url)
            try:
                a = b.fab()
                sa = await a.__aenter__()
                await sa.execute(text(b.SQL), b.params(ids["f_manual"], ids["serie"], "preparada"))
                bajada = asyncio.create_task(asyncio.to_thread(alembic, url, "downgrade", "0016", estricto=False))
                await asyncio.sleep(2.0)
                assert not bajada.done()                          # sigue esperando a A
                await sa.rollback()
                await a.__aexit__(None, None, None)
                r = await asyncio.wait_for(bajada, 120)
            finally:
                await b.cerrar()
            assert r.returncode == 0, r.stderr[-500:]
            assert await version(url) == "0016" and await existe_tabla_y_tipo(url) == (False, False)
