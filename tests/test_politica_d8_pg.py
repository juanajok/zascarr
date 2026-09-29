"""D8 — generación y retirada de items de política, con un solo predicado,
contra Postgres real.

Aquí no se prueba el `WHERE` como cadena: se prueba **lo que queda en la
tabla**, que es donde están las trampas que la ficha enumera —

- el índice único parcial no mira el estado, así que un número `retirado` o
  `imported` sigue ocupando el hueco y hay que **reactivar**, no insertar;
- la retirada es un `UPDATE` atómico y **no** puede tocar lo que ya empezó
  (`SEARCHING`/`DOWNLOADING`) ni lo que pidió el coleccionista a mano;
- un item manual de serie que aparece **después** de la generación tiene que
  retirar los generados pendientes, que es el caso que la regla quería evitar
  desde el principio.

Se saltan sin `TEST_DATABASE_URL`, mismo patrón que `test_huecos_pg.py`:

    docker run --rm -d --name zascarr-pg-test -e POSTGRES_USER=test \\
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=zascarr_test \\
        -p 127.0.0.1:55432:5432 postgres:15
    TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55432/zascarr_test \\
        pytest tests/test_politica_d8_pg.py
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    LegalAcknowledgment,
    MetadataSource,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.legal import current_legal_version
from zascarr.services.orchestrator import Orchestrator, SincronizacionPolitica
from zascarr.services.politica import (
    MOTIVO_POLITICA_FUTUROS,
    MOTIVO_SERIE_EN_CURSO,
    querer_de_serie,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _exigir_bd_de_prueba(session) -> None:
    """Mismo guardarraíl que `test_huecos_pg.py`: un `TEST_DATABASE_URL`
    apuntado por error a una instalación real es un accidente demasiado caro."""
    nombre = (await session.execute(text("SELECT current_database()"))).scalar()
    if not nombre or "test" not in nombre.lower():
        raise RuntimeError(
            f"TEST_DATABASE_URL apunta a la base de datos «{nombre}», que no lleva "
            "'test' en el nombre. Este módulo está pensado para una base de pruebas."
        )


@pytest.fixture
async def db():
    """Sesión DENTRO de una transacción que SIEMPRE se revierte (nada de
    `DELETE FROM` sobre tablas compartidas — ver `test_huecos_pg.py`)."""
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL or ""))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        await _exigir_bd_de_prueba(session)
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


async def aceptar_aviso(db) -> None:
    """El ciclo de política está detrás de la puerta legal (ficha D8, caso 16):
    sin una fila con la versión vigente no se escribe nada."""
    db.add(LegalAcknowledgment(id=uuid4(), legal_version=current_legal_version()))
    await db.flush()


async def crear_serie(db, total_issues=None, policy=WishlistPolicy.MISSING, title="Serie D8",
                      metadata_source=MetadataSource.COMIC_VINE.value) -> Series:
    s = Series(id=uuid4(), title=title, tradition=ComicTradition.AMERICAN,
               total_issues=total_issues, metadata_source=metadata_source,
               wishlist_policy=policy)
    db.add(s)
    await db.flush()
    return s


async def crear_issue(db, series, numero, formato=IssueFormat.SINGLE_ISSUE,
                      archivos=(False,)) -> Issue:
    """`archivos`: un File por elemento; `True` = desaparecido del disco."""
    i = Issue(id=uuid4(), series_id=series.id, issue_number=numero, format=formato)
    db.add(i)
    await db.flush()
    for is_missing in archivos:
        db.add(File(id=uuid4(), issue_id=i.id, file_path=f"/lib/{uuid4()}.cbz",
                    file_name="x.cbz", file_format=FileFormat.CBZ, is_missing=is_missing))
    await db.flush()
    return i


async def crear_item(db, series, *, origen=WishlistOrigin.MANUAL, status=WishlistStatus.WANTED,
                     numero=None, issue_id=None) -> Wishlist:
    item = Wishlist(id=uuid4(), series_id=series.id, issue_id=issue_id, origen=origen,
                    status=status, numero=numero)
    db.add(item)
    await db.flush()
    return item


async def politica_de(db, series) -> list[tuple[int | None, WishlistStatus]]:
    """(numero, status) de los items de política, frescos de la BD.

    No se leen los objetos ORM ya cargados: la generación y la retirada escriben
    con SQL masivo, que **no** refresca la identidad en memoria — leer el objeto
    daría el valor viejo y la prueba pasaría por el motivo equivocado.
    """
    return list((await db.execute(
        select(Wishlist.numero, Wishlist.status)
        .where(Wishlist.series_id == series.id)
        .where(Wishlist.origen == WishlistOrigin.POLICY)
        .order_by(Wishlist.numero)
    )).all())


async def numeros_de_politica(db, series) -> list[int]:
    return [n for n, _ in await politica_de(db, series)]


async def estado_de(db, series, numero) -> WishlistStatus | None:
    return (await db.execute(
        select(Wishlist.status)
        .where(Wishlist.series_id == series.id, Wishlist.numero == numero)
    )).scalar_one_or_none()


async def añadir_manual_de_serie(db, series, status=WishlistStatus.WANTED) -> Wishlist:
    return await crear_item(db, series, status=status)


async def poner_politica(db, series, policy: WishlistPolicy) -> None:
    """Cambia la política por el ORM a propósito: un `UPDATE` por SQL crudo
    dejaría el objeto de la sesión con el valor viejo (la identidad no se
    refresca sola) y la prueba mediría algo que no pasa en producción."""
    series.wishlist_policy = policy
    await db.flush()


class TestGeneracionD8:
    """Casos 1, 2, 4, 7, 17 y 18 de la ficha: qué se materializa y qué no."""

    @pytest.mark.asyncio
    async def test_faltantes_genera_solo_los_que_faltan(self, db):
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=5)
        await crear_issue(db, s, "1", archivos=(False,))
        await crear_issue(db, s, "3", archivos=(False,))

        resultado = await Orchestrator(db).sync_policy_items()

        assert resultado.generados == 3
        assert resultado.retirados == 0
        assert await numeros_de_politica(db, s) == [2, 4, 5]

    @pytest.mark.asyncio
    async def test_no_computable_no_inventa_numeros(self, db):
        """Caso 2: manga de AniList (capítulos vs tomos) → nada, y el motivo."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        await crear_issue(db, s, "1", formato=IssueFormat.TRADE_PAPERBACK, archivos=(False,))

        orch = Orchestrator(db)
        querer = await querer_de_serie(db, s)
        resultado = await orch.sync_policy_items()

        assert querer.computable is False
        assert querer.numeros == frozenset()
        assert querer.motivo and "grapas" in querer.motivo
        assert resultado.generados == 0
        assert await politica_de(db, s) == []

    @pytest.mark.asyncio
    async def test_futuros_se_declara_y_no_genera(self, db):
        """Caso 4: reservado y no computable — se dice, no se inventa."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=5, policy=WishlistPolicy.FUTURE)

        orch = Orchestrator(db)
        querer = await querer_de_serie(db, s)
        resultado = await orch.sync_policy_items()

        assert resultado == SincronizacionPolitica(0, 0)
        assert querer.computable is False
        assert querer.motivo == MOTIVO_POLITICA_FUTUROS
        assert await politica_de(db, s) == []

    @pytest.mark.asyncio
    async def test_dos_ciclos_seguidos_no_duplican(self, db):
        """Caso 7: la política es declarativa; el segundo ciclo no repite."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)

        orch = Orchestrator(db)
        primero = await orch.sync_policy_items()
        segundo = await orch.sync_policy_items()

        assert (primero.generados, segundo.generados) == (3, 0)
        assert await numeros_de_politica(db, s) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_el_tope_acota_lo_que_se_materializa(self, db):
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=10)

        resultado = await Orchestrator(db).sync_policy_items(lote=4)

        assert resultado.generados == 4
        assert len(await numeros_de_politica(db, s)) == 4

    @pytest.mark.asyncio
    async def test_el_reparto_es_justo_entre_series(self, db):
        """Caso 17: una serie de 200 números no se lleva el cupo entero."""
        await aceptar_aviso(db)
        grande = await crear_serie(db, total_issues=200, title="Serie larga")
        pequena = await crear_serie(db, total_issues=3, title="Serie corta")

        resultado = await Orchestrator(db).sync_policy_items(lote=4)

        assert resultado.generados == 4
        assert len(await numeros_de_politica(db, grande)) == 2
        assert len(await numeros_de_politica(db, pequena)) == 2

    @pytest.mark.asyncio
    async def test_un_numero_retirado_se_reactiva_en_vez_de_duplicarse(self, db):
        """El índice único parcial NO mira el estado: volver a querer el 2
        después de retirarlo reactiva la misma fila (una sola por número)."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        orch = Orchestrator(db)
        await orch.sync_policy_items()
        await db.execute(text(
            "UPDATE wishlist SET status='retirado', added_at = now() - interval '1 day' "
            "WHERE series_id=:s AND numero=2"
        ).bindparams(s=s.id))
        viejo = (await db.execute(
            select(Wishlist.added_at).where(Wishlist.series_id == s.id, Wishlist.numero == 2)
        )).scalar_one()

        resultado = await orch.sync_policy_items()

        assert resultado.generados == 1
        assert await estado_de(db, s, 2) == WishlistStatus.WANTED
        nuevo = (await db.execute(
            select(Wishlist.added_at).where(Wishlist.series_id == s.id, Wishlist.numero == 2)
        )).scalar_one()
        assert nuevo > viejo, "added_at tiene que reiniciarse: el cierre compara con él"
        assert await numeros_de_politica(db, s) == [1, 2, 3]

    @pytest.mark.parametrize("estado", [WishlistStatus.DOWNLOADING, WishlistStatus.DOWNLOADED])
    @pytest.mark.asyncio
    async def test_lo_que_ya_empezo_no_se_reinicia(self, db, estado):
        """Ni una descarga en marcha ni una terminada y pendiente de importar se
        reinician al generar."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=1)
        await crear_item(db, s, origen=WishlistOrigin.POLICY, status=estado, numero=1)
        antes = (await db.execute(
            select(Wishlist.added_at).where(Wishlist.series_id == s.id))).scalar_one()

        resultado = await Orchestrator(db).sync_policy_items()

        assert resultado.generados == 0
        assert await estado_de(db, s, 1) == estado
        assert (await db.execute(
            select(Wishlist.added_at).where(Wishlist.series_id == s.id))).scalar_one() == antes

    @pytest.mark.asyncio
    async def test_un_failed_conserva_su_motivo_y_no_gasta_el_lote(self, db):
        """El fallo que señaló la revisión: `FAILED` no se reactiva.

        Reiniciarlo cada ciclo borraría su `last_error` —el motivo de D9
        desaparece justo cuando el coleccionista lo necesita— y gastaría el
        lote. `process_wishlist` ya lo reintenta tras el cooldown.
        """
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=4)
        orch = Orchestrator(db)
        assert (await orch.sync_policy_items(lote=3)).generados == 3   # 1, 2, 3
        await db.execute(text(
            "UPDATE wishlist SET status='failed', last_error='No se encontró nada' "
            "WHERE series_id=:s"
        ).bindparams(s=s.id))

        resultado = await orch.sync_policy_items(lote=1)

        # El lote entero se va al número que de verdad falta (el 4); los tres
        # fallidos ni se tocan ni consumen cupo.
        assert resultado.generados == 1
        assert await numeros_de_politica(db, s) == [1, 2, 3, 4]
        filas = list((await db.execute(
            select(Wishlist.numero, Wishlist.status, Wishlist.last_error)
            .where(Wishlist.series_id == s.id).order_by(Wishlist.numero))).all())
        assert [st for _, st, _ in filas[:3]] == [WishlistStatus.FAILED] * 3
        assert all(err == "No se encontró nada" for _, _, err in filas[:3])
        assert filas[3][1] == WishlistStatus.WANTED

    @pytest.mark.asyncio
    async def test_un_imported_cuyo_fichero_desaparecio_se_reactiva(self, db):
        """El número vuelve a ser hueco (no hay `File`): hay que pedirlo otra vez.
        Es uno de los dos estados que la generación SÍ puede reactivar."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=1)
        await crear_item(db, s, origen=WishlistOrigin.POLICY,
                         status=WishlistStatus.IMPORTED, numero=1)
        await db.execute(text(
            "UPDATE wishlist SET added_at = now() - interval '1 day' WHERE series_id=:s"
        ).bindparams(s=s.id))
        viejo = (await db.execute(
            select(Wishlist.added_at).where(Wishlist.series_id == s.id))).scalar_one()

        resultado = await Orchestrator(db).sync_policy_items()

        assert resultado.generados == 1
        assert await estado_de(db, s, 1) == WishlistStatus.WANTED
        assert (await db.execute(
            select(Wishlist.added_at).where(Wishlist.series_id == s.id))).scalar_one() > viejo

    @pytest.mark.asyncio
    async def test_materializar_dos_veces_el_mismo_numero_deja_una_sola_fila(self, db):
        """Lo que prueba: que el `ON CONFLICT` es idempotente. **No** prueba que
        dos ciclos solapados no dupliquen — eso es
        `test_dos_ciclos_solapados_de_verdad_no_duplican`, con dos conexiones."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=1)
        orch = Orchestrator(db)

        await orch._materializar(s, 1)
        await orch._materializar(s, 1)

        assert await numeros_de_politica(db, s) == [1]


class TestRetiradaD8:
    """Casos 11, 14 y 15 más el de la revisión: un item manual de serie que
    aparece DESPUÉS tiene que retirar los generados pendientes."""

    @pytest.mark.asyncio
    async def test_un_numero_que_llega_deja_de_quererse(self, db):
        """Caso 11: la política es declarativa, no una acción de una sola vez."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        orch = Orchestrator(db)
        await orch.sync_policy_items()
        await crear_issue(db, s, "2", archivos=(False,))

        resultado = await orch.sync_policy_items()

        assert resultado.retirados == 1
        assert await estado_de(db, s, 2) == WishlistStatus.RETIRADO
        assert await numeros_de_politica(db, s) == [1, 2, 3]   # retirado, no borrado

    @pytest.mark.asyncio
    async def test_pasar_a_ninguno_retira_lo_pendiente_pero_no_lo_manual(self, db):
        """Caso 14: se retiran los generados pendientes; el manual sigue igual."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        orch = Orchestrator(db)
        assert (await orch.sync_policy_items()).generados == 3
        manual = await crear_item(db, s, status=WishlistStatus.WANTED, numero=9)

        await poner_politica(db, s, WishlistPolicy.NONE)
        resultado = await orch.sync_policy_items()

        assert resultado.retirados == 3
        assert await estado_de(db, s, 1) == WishlistStatus.RETIRADO
        assert await estado_de(db, s, 9) == WishlistStatus.WANTED
        assert (await db.execute(
            select(Wishlist.origen).where(Wishlist.id == manual.id))).scalar_one() \
            == WishlistOrigin.MANUAL

    @pytest.mark.asyncio
    async def test_lo_que_ya_empezo_no_se_retira(self, db):
        """Caso 14, la otra mitad: DOWNLOADING no se toca. SEARCHING tampoco:
        hay una búsqueda en vuelo y marcarlo `retirado` sería mentir (D9)."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        orch = Orchestrator(db)
        await orch.sync_policy_items()
        await db.execute(text(
            "UPDATE wishlist SET status='downloading' WHERE series_id=:s AND numero=2"
        ).bindparams(s=s.id))
        await db.execute(text(
            "UPDATE wishlist SET status='searching' WHERE series_id=:s AND numero=3"
        ).bindparams(s=s.id))
        await poner_politica(db, s, WishlistPolicy.NONE)

        resultado = await orch.sync_policy_items()

        assert resultado.retirados == 1                     # solo el 1, que no empezó
        assert await estado_de(db, s, 1) == WishlistStatus.RETIRADO
        assert await estado_de(db, s, 2) == WishlistStatus.DOWNLOADING
        assert await estado_de(db, s, 3) == WishlistStatus.SEARCHING

    @pytest.mark.asyncio
    async def test_item_manual_de_serie_bloquea_la_generacion(self, db):
        """Caso 15: mientras exista uno vivo, no se genera por número."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        await añadir_manual_de_serie(db, s)

        orch = Orchestrator(db)
        querer = await querer_de_serie(db, s)
        resultado = await orch.sync_policy_items()

        assert querer.numeros == frozenset()
        assert querer.motivo == MOTIVO_SERIE_EN_CURSO
        assert resultado.generados == 0
        assert await politica_de(db, s) == []

    @pytest.mark.asyncio
    async def test_item_manual_de_serie_posterior_retira_los_generados(self, db):
        """El caso que añadió la revisión: los generados ya existían cuando el
        coleccionista añadió el item de serie. Sin esto se buscaría la serie
        genérica *y además* cada número — la duplicación que la regla evita."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        orch = Orchestrator(db)
        assert (await orch.sync_policy_items()).generados == 3

        manual = await añadir_manual_de_serie(db, s)
        resultado = await orch.sync_policy_items()

        assert resultado.generados == 0
        assert resultado.retirados == 3
        assert [st for _, st in await politica_de(db, s)] == [WishlistStatus.RETIRADO] * 3
        assert (await db.execute(
            select(Wishlist.status).where(Wishlist.id == manual.id))).scalar_one() \
            == WishlistStatus.WANTED

    @pytest.mark.asyncio
    async def test_el_manual_posterior_no_retira_lo_que_ya_descarga(self, db):
        """...salvo lo que ya está DOWNLOADING, que no se puede deshacer."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        orch = Orchestrator(db)
        await orch.sync_policy_items()
        await db.execute(text(
            "UPDATE wishlist SET status='downloading' WHERE series_id=:s AND numero=1"
        ).bindparams(s=s.id))

        await añadir_manual_de_serie(db, s)
        resultado = await orch.sync_policy_items()

        assert resultado.retirados == 2
        assert await estado_de(db, s, 1) == WishlistStatus.DOWNLOADING
        assert await estado_de(db, s, 2) == WishlistStatus.RETIRADO
        assert await estado_de(db, s, 3) == WishlistStatus.RETIRADO

    @pytest.mark.asyncio
    async def test_un_manual_de_numero_ocupa_ese_numero(self, db):
        """El índice único no cubre los manuales: si el coleccionista ya pidió
        el 2 a mano, la política no genera otro item para el 2."""
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3)
        issue = await crear_issue(db, s, "2", archivos=())   # catalogado, sin fichero → hueco
        await crear_item(db, s, status=WishlistStatus.WANTED, issue_id=issue.id)

        orch = Orchestrator(db)
        querer = await querer_de_serie(db, s)
        resultado = await orch.sync_policy_items()

        assert 2 not in querer.numeros
        assert resultado.generados == 2
        assert await numeros_de_politica(db, s) == [1, 3]


class TestGateLegalD8:
    """Caso 16: generar también es "facilitar descargas" — sin acuse, nada."""

    @pytest.mark.asyncio
    async def test_sin_acuse_no_se_escribe_ni_una_fila(self, db):
        s = await crear_serie(db, total_issues=3)

        resultado = await Orchestrator(db).sync_policy_items()

        assert resultado == SincronizacionPolitica(0, 0)
        assert await politica_de(db, s) == []


class TestPredicadoUnicoD8:
    """El predicado es la fuente única: lo que dice `querer_de_serie` es
    exactamente lo que acaba (o no) en la tabla."""

    @pytest.mark.asyncio
    async def test_querer_y_tabla_coinciden(self, db):
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=4)
        # Solo el ómnibus del 2: no cubre la grapa 2, así que sigue siendo hueco.
        await crear_issue(db, s, "2", formato=IssueFormat.OMNIBUS, archivos=(False,))

        orch = Orchestrator(db)
        querer = await querer_de_serie(db, s)
        await orch.sync_policy_items()

        assert querer.numeros == frozenset({1, 2, 3, 4})
        assert set(await numeros_de_politica(db, s)) == set(querer.numeros)
        assert all(st == WishlistStatus.WANTED for _, st in await politica_de(db, s))

    @pytest.mark.asyncio
    async def test_ninguno_no_quiere_nada_pero_no_es_un_error(self, db):
        await aceptar_aviso(db)
        s = await crear_serie(db, total_issues=3, policy=WishlistPolicy.NONE)

        querer = await querer_de_serie(db, s)

        assert querer.numeros == frozenset()
        assert querer.computable is True
        assert querer.motivo is None


@pytest.mark.asyncio
async def test_dos_ciclos_solapados_de_verdad_no_duplican():
    """Caso 18, de verdad: dos conexiones, cada una con su transacción, intentan
    materializar el mismo número a la vez.

    La garantía es de la BASE (índice único parcial) y el `DO UPDATE` con
    `WHERE status IN ('retirado','imported')` impide que la perdedora reinicie
    la fila que la ganadora acaba de crear.

    Se sale del fixture con rollback a propósito: hacen falta COMMIT de verdad
    para que la segunda conexión vea (o choque con) la fila. Por eso limpia lo
    suyo a mano, incluido el acuse legal, que si no contaminaría a los tests que
    comprueban que sin acuse no se escribe nada.
    """
    motor = create_async_engine(_url_asyncpg(TEST_DATABASE_URL or ""))
    sesion = async_sessionmaker(motor, expire_on_commit=False)
    sid, ack_id = uuid4(), uuid4()

    async def materializar():
        async with sesion() as s:
            serie = await s.get(Series, sid)
            await Orchestrator(s)._materializar(serie, 1)
            await s.commit()

    try:
        async with sesion() as s:
            await _exigir_bd_de_prueba(s)
            s.add(Series(id=sid, title="Solape D8", tradition=ComicTradition.AMERICAN,
                         total_issues=1, metadata_source=MetadataSource.COMIC_VINE.value,
                         wishlist_policy=WishlistPolicy.MISSING))
            s.add(LegalAcknowledgment(id=ack_id, legal_version=current_legal_version()))
            await s.commit()

        await asyncio.gather(materializar(), materializar())

        async with sesion() as s:
            filas = list((await s.execute(
                select(Wishlist.numero, Wishlist.status)
                .where(Wishlist.series_id == sid))).all())
        assert filas == [(1, WishlistStatus.WANTED)]
    finally:
        async with sesion() as s:
            await s.execute(text("DELETE FROM wishlist WHERE series_id=:s").bindparams(s=sid))
            await s.execute(text("DELETE FROM series WHERE id=:s").bindparams(s=sid))
            await s.execute(text("DELETE FROM legal_acknowledgments WHERE id=:i")
                            .bindparams(i=ack_id))
            await s.commit()
        await motor.dispose()
