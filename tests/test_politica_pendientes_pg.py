"""C6 (PR 2): `pendientes_de_buscar` contra Postgres real.

Los dobles de sesión no ejecutan el SQL, así que quitar un filtro (serie, origen, estado, política)
cambiaba la N de la cota sin que ninguna prueba lo notase. Aquí se siembran series y deseos reales y
se comprueba el valor exacto. Datos y mutaciones (M1..M10) de la revisión de SecOps sobre #412.
Sin `TEST_DATABASE_URL` se salta, como el resto de pruebas con Postgres.

Valor esperado: N = 11 = 7 propias + 4 de otras.
- Serie propia (MISSING), `Querer` fijado con los números 1..10: ítems de POLÍTICA en WANTED(1),
  FAILED(2), SEARCHING(3), DOWNLOADING(4), DOWNLOADED(5), RETIRADO(6), IMPORTED(7) y un ítem MANUAL
  en SEARCHING con el número 9 → propias = 10 − {3, 4, 5} = 7.
- Otras con política activa: «missing» con 2 WANTED + 1 FAILED de política = 3; «todos» (ALL) con
  1 WANTED = 1.
- No cuentan: «ninguno» (política NINGUNO), «manual» (MISSING pero ítems MANUAL), «ya buscada»
  (MISSING con ítems de política ya buscados o terminados), «futuros» (FUTUROS) y los WANTED/FAILED
  de la propia serie (no se cuentan dos veces).

Mutaciones (una a una sobre `services/politica.py::pendientes_de_buscar`; las detecta todas):
M1 quitar `series_id == series.id` de lo ya en marcha; M2 quitar `origen == POLICY` ahí; M3 y M4
`ESTADOS_YA_BUSCADOS` sin SEARCHING / sin DOWNLOADED; M5 quitar `series_id != series.id` de las
demás; M6 quitar `origen == POLICY` ahí; M7 añadir SEARCHING a sus estados; M8 quitar FAILED; M9
quitar el filtro de política; M10 política solo MISSING (sin ALL).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    ComicTradition,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.politica import Querer, pendientes_de_buscar

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")]

POLITICA, MANUAL = WishlistOrigin.POLICY, WishlistOrigin.MANUAL
WANTED, FAILED = WishlistStatus.WANTED, WishlistStatus.FAILED
SEARCHING, DOWNLOADING = WishlistStatus.SEARCHING, WishlistStatus.DOWNLOADING
DOWNLOADED, RETIRADO, IMPORTED = (
    WishlistStatus.DOWNLOADED, WishlistStatus.RETIRADO, WishlistStatus.IMPORTED)


@pytest.fixture
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


async def test_n_cuenta_solo_lo_pendiente_de_las_series_con_politica_activa(url_bd):
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        def serie(titulo, politica):
            nueva = Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN,
                           wishlist_policy=politica)
            s.add(nueva)
            return nueva

        propia = serie("Propia", WishlistPolicy.MISSING)        # la serie de la ficha
        missing = serie("Otra missing", WishlistPolicy.MISSING)
        ninguno = serie("Otra ninguno", WishlistPolicy.NONE)
        todos = serie("Otra todos", WishlistPolicy.ALL)
        manual = serie("Otra missing manual", WishlistPolicy.MISSING)
        ya_buscada = serie("Otra missing ya buscada", WishlistPolicy.MISSING)
        futuros = serie("Otra futuros", WishlistPolicy.FUTURE)
        await s.flush()

        def deseo(de, numero, origen, estado):
            s.add(Wishlist(id=uuid4(), series_id=de.id, numero=numero, origen=origen,
                           status=estado, search_query="q"))

        # propia: POLICY en todos los estados + un manual SEARCHING en el 9
        estados = (WANTED, FAILED, SEARCHING, DOWNLOADING, DOWNLOADED, RETIRADO, IMPORTED)
        for numero, estado in enumerate(estados, start=1):
            deseo(propia, numero, POLITICA, estado)
        deseo(propia, 9, MANUAL, SEARCHING)
        # otras series que cuentan: 3 + 1
        for numero, estado in enumerate((WANTED, WANTED, FAILED), start=1):
            deseo(missing, numero, POLITICA, estado)
        deseo(todos, 1, POLITICA, WANTED)
        # otras series que no cuentan
        for numero in range(1, 4):
            deseo(ninguno, numero, POLITICA, WANTED)             # política ninguno
        for numero in range(1, 5):
            deseo(manual, numero, MANUAL, WANTED)                # manuales
        ya = (SEARCHING, DOWNLOADING, RETIRADO, IMPORTED, DOWNLOADED)
        for numero, estado in enumerate(ya, start=1):
            deseo(ya_buscada, numero, POLITICA, estado)          # ya buscadas o terminadas
        for numero in (1, 2):
            deseo(futuros, numero, POLITICA, WANTED)             # futuros
        await s.commit()

        n = await pendientes_de_buscar(s, propia, Querer(frozenset(range(1, 11)), True))
    await motor.dispose()
    assert n == 11
