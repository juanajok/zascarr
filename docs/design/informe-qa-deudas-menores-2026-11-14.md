# Informe QA — Lote de deudas menores (2026-11-14)

**Rol:** QA · **Tarea:** task-34 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/deudas-menores`
**Rama:** `fix/deudas-menores`, SHA **`938654ea0001e4a51e07cfe15f6a7e22d42d4629`** (verificado con
`git rev-parse HEAD`; PR #805 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Postgres real: contenedor `zascarr-ux508-pg`
(`postgres:15-alpine` 15.19), base temporal `zascarr_qa_deudas_test` creada y borrada para QA.
El único fichero escrito es este informe; el scratch de QA (`.qa-deudas/`) se borra al terminar.

> **Nota:** la suite sin `TEST_DATABASE_URL` salta la prueba `_pg` nueva (1 skip documentado).
> Con `TEST_DATABASE_URL` esa prueba **falla**; es el único bloqueante de la entrega (ver §2-f).

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **6987 passed, 2284 skipped**, 4 warnings, 0 fallos | 339,89 s (wall 5:44) |
| `pytest -q` (suite completa, 2.ª pasada) | **6987 passed, 2284 skipped**, 4 warnings, 0 fallos | 320,45 s (wall 5:20) |
| `pytest -q tests/test_enricher.py tests/test_web_arcos.py tests/test_web_series.py tests/test_comic_book_herald.py tests/test_peticiones.py` | **239 passed** | 4,74 s (wall 6,18 s) |
| `pytest -q tests/test_reconciliacion_lecturas_pg.py` **sin** `TEST_DATABASE_URL` | 1 **skipped** (documentado) | 0,58 s |
| `pytest -q tests/test_reconciliacion_lecturas_pg.py` **con** `TEST_DATABASE_URL` | **1 failed** ← **BLOQUEANTE** | 2,78 s |
| `ruff check src/` | **All checks passed!** | — |

Los 2284 skips son los esperados sin `TEST_DATABASE_URL` (pruebas `*_pg`). Los 4 warnings son
preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en importer), ajenos al lote.
Las dos pasadas completas (sin URL) dan los mismos contadores y cero fallos: sin contaminación.
La prueba `_pg` nueva no puede pasar con Postgres real (§2-f), que es justo lo que pedía la
aceptación.

---

## 2. Aceptación

### (a) m-3: arco manual homónimo intacto y arco Fandom aparte, enricher idempotente — **PASA**

`services/enricher.py:_upsert_arc` busca primero por identidad real
`metadata_["fandom_dc"] == arco.page_title`; solo reutiliza por título un arco que ya es de
Fandom (`origen=="fandom_dc"` o legado con `fandom_dc`). Un arco manual u de otra fuente con el
mismo título no se adopta y se crea el arco de Fandom aparte (`enricher.py:999-1040`).
Pruebas: `tests/test_enricher.py:961-1068` (manual intacto, otra fuente intacta, idempotencia,
legado sin origen). Validación adicional **con Postgres real** (sonda propia, 4/4 OK): sembré una
serie/issue y un arco manual «Year One» con su enlace; tras `_upsert_arc` el arco manual conserva
`metadata_={"nota":"mío"}` y su `StoryArcIssue`, se crea un segundo arco Fandom con
`{"origen":"fandom_dc","fandom_dc":"Batman: Year One"}` y su enlace; la segunda pasada no duplica
arcos ni enlaces y no toca el manual.
Comando: `TEST_DATABASE_URL=… python .qa-deudas/e2e_m3_pg.py` → 4/4 OK.

### (b) m-1: aviso genérico incluye Fandom y la atribución CC-BY-SA se ve fuera de `<details>` — **PASA**

`web/templates/_legal_disclaimer.html` («metadata») menciona ahora «Comic Vine, AniList,
Tebeosfera **y DC/Marvel Database de Fandom**»; `web/templates/series_detail.html:48-56` deja el
aviso genérico dentro de `<details>` y pinta `aviso_de_atribucion(...)` **después** del cierre,
visible sin desplegar. Prueba: `test_web_series.py:1214+`
(`TestAtribucionFandomVisible`), y sonda propia sobre la estructura de la plantilla (aviso
genérico con Fandom dentro; atribución fuera; sin «BY-SA» dentro del desplegable).

### (c) m-2: listado `/ui/arcos` con aviso CC-BY-SA cuando hay arcos Fandom, `rel`, orden/paginación — **PASA**

`services/arcos.py:listar_arcos` selecciona `metadata->>'origen'`/`fandom_dc`, rellena
`ArcoResumen.origen` y `PaginaArcos.hay_fandom` sin cambiar `order_by(title, id)`, `offset` ni
`limit` (`arcos.py:45-110`). `web/templates/arcos.html:22-25` pinta el aviso CC-BY-SA (enlace a
la licencia con `rel="noopener noreferrer"`, enlace a `/legal`) solo si `pagina.hay_fandom`, y lo
coloca después del `<ul>` y antes de la paginación, sin alterar la lista. Pruebas:
`test_web_arcos.py:430+` (con y sin Fandom; orden `Year One` antes del aviso; `rel` y `/legal`).
Sonda propia: estructura de la plantilla y condiciones.

### (d) M-5: 304 como «304» («Sin cambios») y 400/404 como «4xx» — **PASA**

`utils/peticiones.py:364-370` registra `"304"` cuando el código es 304 (antes registraba `"4xx"`
también para 304); `services/cortesia_estado.py:42` añade `"304": "Sin cambios"` al mapa que pinta
Estado. Pruebas: `test_peticiones.py::Test304NoEs4xx` (304 → `"304"`; 400 y 404 → `"4xx"`).
Sonda propia (petición real por `pedir_con_cortesia` con transporte 304/400/404 y snapshot):
`304→304`, `400→4xx`, `404→4xx`; `RESULTADOS["304"]=="Sin cambios"`.

### (e) Categorías del feed: máx. 10, ≤100 caracteres y sin controles — **PASA**

`services/comicbook_herald.py:_categorias_de` (`:121-137`) colapsa espacios, descarta categorías
vacías o con caracteres de control (C0/DEL), recorta a 100 y corta a 10; `parsear_feed` la usa.
Pruebas: `test_comic_book_herald.py` (50 categorías largas → 10 y ≤100; categoría con `&#127;` y
`[2J` descartada). Sonda propia con XML de 50 categorías largas + control: 10/100/sin controles.

### (f) `tests/test_reconciliacion_lecturas_pg.py` con Postgres real — **FALLA (BLOQUEANTE)**

La prueba existe y **se salta correctamente** sin `TEST_DATABASE_URL` (`1 skipped`), pero con
`TEST_DATABASE_URL` apuntando a una base de pruebas **falla**:

```
pytest -q tests/test_reconciliacion_lecturas_pg.py
FAILED tests/test_reconciliacion_lecturas_pg.py::test_reconciliar_guia_pg_crea_arco_en_orden_e_es_idempotente
RuntimeError: asyncio.run() cannot be called from a running event loop
  tests/_pg.py:129: bd_efimera_sync → asyncio.run(_crear_efimera(url_base))
```

Causa: la prueba está marcada `pytest.mark.asyncio` (test `async`) y dentro usa
`bd_efimera_sync`, que llama a `asyncio.run()`; no se puede anidar en el bucle de pytest-asyncio.
`tests/_pg.py` ya ofrece `bd_efimera` **async** (context manager) para este caso. No he modificado
código: el arreglo es del builder (usar `async with bd_efimera(URL) as url` o convertir la prueba
en síncrona). Es la única prueba nueva que valida la idempotencia real con Postgres, así que el
criterio (f) no se cumple aunque el resto del lote esté bien.

### (g) Sin tocar `web/ajustes.py`/`models`/migraciones — **PASA**

`git diff HEAD~1 HEAD --name-only | grep -E "web/ajustes|models|alembic"` → **sin resultados**.
Los 14 ficheros del commit son servicios (`arcos.py`, `comicbook_herald.py`, `cortesia_estado.py`,
`enricher.py`, `peticiones.py`), 3 plantillas y 6 ficheros de pruebas (una nueva `_pg`). El resto de
la suite queda intacta (6987 passed en la pasada completa sin URL).

---

## 3. Observaciones

**O1 — El único bloqueante es el fallo de la prueba `_pg` (f).** No es una regresión funcional de
la reconciliación (la sonda E2E propia con Postgres real demuestra que la reconciliación sigue
siendo idempotente y no toca la biblioteca: 4/4 OK), sino un defecto de la prueba nueva
(`bd_efimera_sync` dentro de un test async). Al no poder pasar con Postgres, la aceptación (f) no
se cumple y el veredicto es **no apto** hasta corregirlo. Fix esperado: `async with
bd_efimera(URL) as url:` dentro del test, o hacer el test síncrono y mover el cuerpo async a
`asyncio.run`/helper; es un cambio pequeño.

**O2 — Cobertura de m-3 en pruebas commiteadas.** Las pruebas de `test_enricher.py` usan una
`FakeSession` que *simula* las dos consultas por texto SQL; no tocan Postgres. La sonda E2E con
Postgres real (arriba) cubre el caso manual/enlaces/idempotencia, pero no queda como regresión de
CI. Recomendación: añadir el caso a la prueba `_pg` de reconciliación o a una nueva `_pg` de
enricher cuando se corrija (f).

---

## 4. Veredicto

**NO APTO.** El lote de deudas cumple (a), (b), (c), (d), (e) y (g) con evidencia, la suite completa
sin `TEST_DATABASE_URL` está verde **dos veces** (6987 passed / 2284 skipped cada una) y
`ruff check src/` limpio; pero la aceptación (f)
**falla de forma reproducible** con Postgres real:
`tests/test_reconciliacion_lecturas_pg.py::test_reconciliar_guia_pg_crea_arco_en_orden_e_es_idempotente`
lanza `RuntimeError: asyncio.run() cannot be called from a running event loop` porque el test
async usa `bd_efimera_sync`. **Bloqueante único** (defecto de la prueba, no de la lógica); corregir
y volver a ejecutar con `TEST_DATABASE_URL` antes de la revisión de SecOps.

---

## 5. Comandos reproducibles

```
cd .worktrees/deudas-menores
PYTHONPATH=src … -m pytest -q                                   # suite completa
PYTHONPATH=src … -m pytest -q tests/test_enricher.py tests/test_web_arcos.py \
    tests/test_web_series.py tests/test_comic_book_herald.py tests/test_peticiones.py
PYTHONPATH=src … -m ruff check src/
# Con Postgres de pruebas:
TEST_DATABASE_URL=postgresql://…/zascarr_qa_deudas_test PYTHONPATH=src … \
    -m pytest -q tests/test_reconciliacion_lecturas_pg.py       # FALLA (bloqueante)
TEST_DATABASE_URL=… PYTHONPATH=src … python .qa-deudas/e2e_m3_pg.py  # 4/4 OK (m-3 real)
```

---

## 6. Inventario del cambio revisado (`938654ea`)

14 ficheros, **+401 / −14**: `services/arcos.py`, `services/comicbook_herald.py`,
`services/cortesia_estado.py`, `services/enricher.py`, `utils/peticiones.py`,
`web/templates/{_legal_disclaimer,arcos,series_detail}.html`,
`tests/{test_comic_book_herald,test_enricher,test_peticiones,test_reconciliacion_lecturas_pg,
test_web_arcos,test_web_series}.py`. Sin cambios en `web/ajustes.py`, `models/` ni `alembic/`.

---

## Addendum — reconfirmación del bloqueante (f) (2026-11-14)

**SHA con el fix:** `15a6e908bfad81546830981fc031469c8925eaa4` (PR #805). El único cambio
funcional respecto a `938654ea` es en `tests/test_reconciliacion_lecturas_pg.py`: pasa de
`bd_efimera_sync` a `async with bd_efimera(URL)`, que es la versión async; **no** se toca la
lógica de la prueba ni el servicio de reconciliación.

Reproducción propia con Postgres real (contenedor `zascarr-ux508-pg`, PG 15.19; base de pruebas
`zascarr_qa_deudas_fix_test` creada y borrada para esta comprobación):

```
TEST_DATABASE_URL=postgresql://…@127.0.0.1:55508/zascarr_qa_deudas_fix_test \
PYTHONPATH=src … -m pytest -q tests/test_reconciliacion_lecturas_pg.py
→ 1 passed in 5.11s        (antes: RuntimeError: asyncio.run() …)

PYTHONPATH=src … -m pytest -q tests/test_reconciliacion_lecturas_pg.py   # sin TEST_DATABASE_URL
→ 1 skipped in 0.59s       (skip documentado, como exige la aceptación)
```

`git diff 938654ea..15a6e908 -- tests/test_reconciliacion_lecturas_pg.py` confirma que solo
cambian el import y el `with`; el resto del lote y sus evidencias (a)-(e), (g) del informe
siguen válidos. **Veredicto actualizado: APTO para `15a6e908`**; el bloqueante (f) queda cerrado.
