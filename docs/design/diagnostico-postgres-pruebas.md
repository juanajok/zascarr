# Diagnóstico: tres fallos de las pruebas de Postgres real

> Origen: al cerrar V4 quedaron anotados tres fallos de `pytest` con `TEST_DATABASE_URL`, «ya presentes en
> `main`», sin causa. Antes de V6a (que trabaja sobre transacciones, movimientos de archivos e integridad)
> se diagnosticaron. **Conclusión: ninguno es un defecto de producción; no se toca `src/`.**

## Entorno de la investigación

Postgres **15.19** (`postgres:15-alpine`, el de `docker-compose.yml`), contenedor **propio y vacío**
(`zascarr_diag_pg`, `127.0.0.1:15440`), no el Postgres de pruebas compartido. Python 3.14.4, SQLAlchemy 2.1.1,
alembic 1.20.0, asyncpg 0.31.0, FastAPI 0.142.2, Starlette 1.7.0, pytest 9.1.1, pytest-asyncio 1.4.0 (la CI
usa Python 3.11 y las versiones que resuelva `pip install -e ".[dev]"`: **no se ha reproducido con ellas**).
Código: `main` en `aba2d5c`. Comando: `pytest -q -p no:randomly` con `TEST_DATABASE_URL`.

## Los tres casos

| Prueba | Síntoma | Causa comprobada |
|---|---|---|
| `test_health_db_pg.py::TestArranqueDegradadoPg::test_bd_sin_esquema_arranca_y_sirve_solo_diagnostico` | sobre una BD **migrada**: `AssertionError: assert 'ok' == 'migration_required'`; sobre una **vacía**: pasa | La prueba lee la BD **compartida** (`public`) y exige que esté **sin migrar** (arranque degradado, E6). Las demás pruebas de Postgres exigen **esa misma BD migrada**. Son incompatibles: en una base virgen pasa ésta y fallan ~100 de las demás. **El código de arranque degradado es correcto**: la prueba ejercita el camino previsto, pero sobre el estado equivocado. |
| `test_migracion_d8_pg.py::test_los_items_que_ya_existian_quedan_manual_y_sin_numero` | sobre BD vacía: `Destination 0014 is not a valid downgrade target from current head(s)`; con la raíz del repo en `PYTHONPATH`: `No module named alembic.__main__; 'alembic' is a package and cannot be directly executed` | Dos causas, ninguna de la migración. (1) Hace `downgrade 0014` **desde `head`** y nadie migraba antes la BD (precondición no escrita). (2) `PYTHONSAFEPATH=1` evita que el directorio `alembic/` de la raíz sombree el paquete instalado **solo si la raíz no llega por otro camino**; al lanzar `pytest` con `PYTHONPATH=src:.` (para que `import tests` funcione) el subproceso heredaba la raíz. |
| `test_migracion_integridad_pg.py::test_las_filas_que_ya_existian_quedan_con_original_sha256_null` | ídem | Ídem. **La garantía (`original_sha256` NULL en filas antiguas) se cumple**: con las dos causas corregidas, la prueba pasa sin tocar la aserción. |

## Una corrección a lo que se dijo antes

En la PR #70 se informó de que «las mismas tres fallan en `main` y en la rama». **Para las dos pruebas de
migración, ese resultado estaba contaminado por mi propia invocación**: lancé `PYTHONPATH=$PWD/src:$PWD`, con
la raíz del repo, que provoca la causa (2). Con `PYTHONPATH=src` y la BD migrada, **solo falla la de arranque
degradado**. La comparación `main` ↔ rama seguía siendo válida (no las introducía #70), pero «tres fallos
preexistentes» sobrestimaba lo que había en `main`: eran uno real de **diseño de la prueba**, y dos que
dependían de cómo se lanzaba.

## Matriz medida (suite completa, 1.795 pruebas con Postgres)

| BD de partida / `PYTHONPATH` | Antes | Después |
|---|---|---|
| migrada · `src` | 1 fallo (arranque degradado) | **0** |
| migrada · `src:raíz` | 3 fallos | **0** |
| vacía · `src:raíz` | 103 fallos | **0** |
| sin `TEST_DATABASE_URL` (como la CI actual) | 1.654 passed, 141 skipped | igual |

«Después» se repitió dos veces seguidas sobre la misma BD: no deja basura (0 bases `…efimera…`) ni la deja a
medias.

## Qué cambia (solo `tests/`)

- `tests/_pg.py`: el contrato escrito. La BD de `TEST_DATABASE_URL` se **migra a `head` una vez por sesión**
  (`conftest.py`); una prueba que necesita otro estado crea la suya con `bd_efimera()` (se borra al salir,
  también si la prueba falla); todo se niega a tocar una BD cuyo nombre no lleve «test».
- `test_health_db_pg`: el arranque degradado corre sobre su **propia BD vacía**.
- `test_migracion_*_pg`: usan `_pg.alembic`, cuyo entorno quita la raíz del repo de `PYTHONPATH`.
- `tests/test_pg_ciclo_de_vida.py` (14): entorno saneado (con una comprobación que documenta el
  mecanismo original: sin sanear, el subproceso falla con `alembic.__main__`), guardas de nombre, BD
  compartida en `head`, efímera vacía/migrable/borrada incluso si la prueba falla.

## Lo que sigue sin hacerse

La CI **no** ejecuta estas pruebas (se saltan sin `TEST_DATABASE_URL`): es el siguiente paso, aparte.
Tampoco se reprodujo con Python 3.11 ni con las versiones exactas que instala la CI.
