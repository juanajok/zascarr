# Informe QA — SCR1: robots.txt (RFC 9309) y caché HTTP condicional en PostgreSQL (2026-11-13)

**Rol:** QA · **Tarea:** task-15 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr1-robots-cache`
**Rama:** `feat/scr1-robots-cache`, HEAD **`0b5e60d8`** (igual que `origin/feat/scr1-robots-cache`;
PR #756 según el encargo, no consultada por red). Árbol limpio antes y después de la verificación.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2 + pytest-asyncio, ruff 0.17.5, protego 0.7.0).
No se ha modificado código ni tests; el único fichero escrito es este informe. El scratch de QA
(`.qa-scr1/`, logs y sonda) se borró al terminar.

> Nota de nombre: la descripción de la tarea pedía `informe-qa-SCR1-2026-11-14.md`; por indicación
> del Lead se usa la **fecha real** (2026-11-13) en el nombre y en la cabecera.

---

## 1. Regresión

### 1.1 Contadores y tiempos

| # | Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|---|
| 1 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6676 passed, 2271 skipped**, 4 warnings | 346,76 s (wall 5:50) |
| 2 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6676 passed, 2271 skipped**, 4 warnings | 333,61 s (wall 5:37) |
| 3 | `… pytest -q tests/test_cache_http.py tests/test_robots.py tests/test_fandom.py tests/test_migracion_http_cache_pg.py` | **68 passed, 2 skipped** | 2,26 s (wall 3,55 s) |
| 4 | `TEST_DATABASE_URL=… pytest -q tests/test_migracion_http_cache_pg.py` | **2 passed** | 11,08 s (wall 12,25 s) |

* Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
  contaminación entre pruebas.
* Los **2 skips** de la pasada aislada son las pruebas de Postgres de 0037 (`skipif not
  TEST_DATABASE_URL`). Los **2271 skips** de la suite completa son los esperados sin
  `TEST_DATABASE_URL` (113 ficheros `tests/*_pg.py` y pruebas dependientes de entorno).
* Conteo por fichero nuevo: `test_cache_http.py` 16, `test_robots.py` 16,
  `test_migracion_http_cache_pg.py` 2; `test_fandom.py` pasa de 32 a **36** (solo adiciones).

### 1.2 Postgres real (item 3 del encargo)

El entorno **no define** `TEST_DATABASE_URL`, pero había un contenedor Postgres corriendo y usable:
`zascarr-ux508-pg` (`postgres:15-alpine`, `127.0.0.1:55508`, PG 15.19, usuario con `CREATEDB`).
Creé una base de pruebas **nueva** (`zascarr_qa_scr1_test`), apunté `TEST_DATABASE_URL` a ella y:

* `conftest.py` la migró a `head` una vez (fixture de sesión);
* la prueba creó y borró sus propias BDs efímeras con `tests._pg.bd_efimera()`;
* **2 passed en 11,08 s**: ida y vuelta `0036 → head → 0036` (tabla, UNIQUE e índices) + alta/lectura
  del ORM + `CacheHttp` real (upsert, `renovar`, `purgar` selectivo).

La base temporal que creé se borra al terminar (`DROP DATABASE … WITH (FORCE)`); no queda estado en
el contenedor compartido.

### 1.3 Lint y warnings

* `ruff check src/` → **All checks passed!**
* `ruff check --select S src/` (bandit) → **All checks passed!**
* 4 warnings, ajenos a SCR1 y preexistentes: `Duplicate name: 'ComicInfo.xml'` (`test_b6_cbz`) y
  `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`
  (`test_importer`/`test_bucle_no_bloqueado`).

---

## 2. Aceptación por criterio

### (a) Hit vigente sin turno de cortesía ni socket — **PASA**

`utils/cache_http.py:350-363`: el hit se devuelve antes de cualquier `pedir_con_cortesia` y marca
`x-zascarr-cache: hit`. Prueba: `tests/test_cache_http.py:176-194`
(`test_hit_sin_turno_ni_socket`: 1 sola petición de red, llamadas de cortesía sin aumentar,
cabecera `hit` y `content-type` servido de la fila). Sonda independiente (a): 1 petición y 0 turnos.

### (b) Stale + ETag → 304 renueva sin bajar cuerpo — **PASA**

Validadores `If-None-Match`/`If-Modified-Since` en `cache_http.py:387-392`; un 304 se interpreta en
`:402-407` y `_devolver_revalidada` (`:493-508`) renueva `fetched_at`/`fresh_until`/`retain_until`,
conserva el cuerpo y sirve `x-zascarr-cache: revalidada`. Prueba: `test_cache_http.py:199-225`
(comprueba `If-None-Match: "abc"`, cuerpo idéntico, `body_zlib` intacto y `fresh_until` mayor).
Sonda (b): igual, `renovaciones == 1`.

### (c) 404 → negativa con TTL corto — **PASA**

`PoliticaCacheDominio.calcular_ventanas` (`cache_http.py:176-183`): negativa ⇒
`fresh_until = retain_until = ahora + ttl_negativo`; `_guardar_negativa` (`:511-524`) guarda
`is_negative=True`, sin cuerpo, y relanza `RespuestaNoTransitoria`. En Fandom, la política
`_POLITICA_CACHE` es 12 h y `codigos_negativos={404,410}` (`services/fandom.py:110-116`).
Prueba: `test_cache_http.py:230-252` (2.ª llamada sin red; a las 13 h vuelve a la red).
Sonda (c): `[404,404,404]`, 2 peticiones, fila negativa sin `body_zlib`.

### (d) 429/5xx/red NUNCA cacheados — **PASA**

Solo se escriben filas 2xx (positivas o negativas clasificadas) y negativas por código listado; los
transitorios se propagan (`ReintentosAgotados`, `RespuestaNoTransitoria`, `httpx.TransportError`) sin
fila. Prueba: `test_cache_http.py:258-281` parametrizada `429/500/red` (2 llamadas, `filas == {}`).
Sonda (d): los tres modos, 2 peticiones y 0 filas en cada uno.

### (e) Singleflight: 5 corrutinas → 1 petición — **PASA**

Candado de módulo por `url_hash`, ligado al bucle y débil (`cache_http.py:79-100`), doble
comprobación de caché tras adquirirlo (`:365-379`); timeout ⇒ `CortesiaEnEspera(..., "candado")`
(`:370-373`). Prueba: `test_cache_http.py:286-296` (5 `gather`, 1 petición, 4 respuestas `hit`);
también `:299-317` (5 URLs del mismo origen ⇒ 1 `/robots.txt`).
Sonda (e): 1 petición y 4 hits.

### (f) robots.txt: 200/403/404/5xx y `Crawl-delay` — **PASA**

Matriz RFC 9309 en `utils/robots.py:158-186`: 2xx ⇒ `Protego.parse(content[:512 KiB])` y
`can_fetch`; 4xx≠429 ⇒ `unavailable_allow` (12 h; cubre el 403 real de Fandom y el 404);
429/5xx/red/parse que lanza ⇒ `unreachable_disallow` (15 min, nunca permiso). `Crawl-delay` se
aplica **solo subiendo** el intervalo con `aplicar_crawl_delay` (`:93-105`) y se propaga a la
política del proceso (`cache_http.py:484-490`). Pruebas: `tests/test_robots.py:64-141` (200 con
`Disallow`+`Crawl-delay` y TTL 24 h; 401/403/404/410 permiten y cachean 12 h; 429/500/503 y red y
parse roto prohíben 15 min sin repedir), `:157-173` (singleflight por origen), `:178-184`
(`Crawl-delay` nunca acelera) y `test_cache_http.py:440-452` (4 s aplicados de verdad en la espera).
Sonda (f): `Crawl-delay: 4` ⇒ la cortesía duerme 4 s; 403 permite; 429/500/503 ⇒
`AccesoProhibidoPorRobots`.

### (g) Migración 0038 encadenada desde 0036 y downgrade que borra tabla/índices — **PASA**

`alembic/versions/20261113_0038_http_cache.py`: `revision="0037"`, `down_revision="0037"`
(l. 18-19); `upgrade` crea `http_cache` con sus 13 columnas, `UNIQUE uq_http_cache_url_hash` e
índices `ix_http_cache_domain`/`ix_http_cache_retain_until` (l. 24-43); `downgrade` borra los dos
índices y la tabla (l. 46-49). Cadena comprobada con `alembic.script.ScriptDirectory`: `heads =
['0037']`, `bases = ['0001']`, **37 revisiones** `0001…0037` sin huecos. Con Postgres real,
`tests/test_migracion_http_cache_pg.py:100-138`: `upgrade 0036` (no existe) → `head` (columnas,
UNIQUE, índices, versión `head`) → ORM inserta/lee → `downgrade 0036` (tabla fuera y versión
`0036`). El modelo `HttpCache` (`models/__init__.py:1149-1178`) mapea exactamente la migración.

### (h) `protego` es la única dependencia nueva — **PASA**

`pyproject.toml:21` añade solo `"protego>=0.7,<1"` (única línea de dependencias del commit;
`git diff HEAD~1 HEAD -- pyproject.toml`). No hay `requirements*.txt` ni otro manifiesto que tocar.
Los módulos nuevos solo importan stdlib + `httpx` + `sqlalchemy`/`structlog` (ya presentes) +
`protego`; versión instalada en el venv compartido: **protego 0.7.0**.

### (i) La integración en `services/fandom.py` no rompe `FuenteApagada`/`CortesiaEnEspera` — **PASA**

La rama con caché de `_api` (`fandom.py:787-810`) llama a `pedir_con_cache`, que mira la fuente
apagada **antes** de caché y robots (`cache_http.py:344-346`) y propaga `CortesiaEnEspera` sin
re-envolver (singleflight `:370-373`; robots `:484-486`). Sin `cache` inyectada el cliente conserva
el camino antiguo (`:787-797`). Las pruebas existentes de `test_fandom.py` siguen verdes
(`FuenteApagada`: l. 448; enricher/flujo: resto de la suite) y las nuevas (l. 589+) cubren
`missingtitle` cacheado negativo, `maxlag` no cacheado, 404 negativo y fuente apagada sin leer caché
ni pedir. Enricher: inyecta `CacheHttp(async_session_factory)` solo con Fandom activo y cliente real
(`enricher.py:303-319`); `main.py:172-182` purga una vez por ciclo tras el commit (con try/except
propio en `purgar_cache`). Todo verde en las dos pasadas completas.

### Comprobación independiente (12/12)

Además de ejecutar las pruebas del builder, ejecuté una **sonda propia** sobre `pedir_con_cache`
con una caché falsa escrita al efecto (no la `CacheHttpFalsa` del builder), relojes simulados y
`httpx.MockTransport`. Resultado: **12/12 OK** — (a) hit sin turno ni socket; (b) 304 renueva y
conserva cuerpo; (c) 404 negativo y caducidad; (d) 429/500/red sin fila; (e) singleflight 5→1;
(f) robots 200+`Crawl-delay` (4 s reales), 403 permite, 429/5xx prohíben; (g) canónica ordenada,
userinfo fuera, `api_key`→`REDACTADO` y hash distinto por clave; (h) `bypass_cache` va a red y
reescribe.

---

## 3. Observaciones (ninguna bloqueante)

**O1 — El cableado de la caché en el enricher no tiene prueba propia.** La spec (§8/§10) preveía
una prueba con espía de `FandomClient` que comprobara que el enricher pasa `cache`; no se añadió. El
código es correcto por lectura (`enricher.py:303-319`) y la suite no se rompe, pero una regresión
futura en ese cableado (p. ej. pasar `None` por error) no la detectaría ninguna prueba. Recomendado
un test de integración con `FakeSession` y flags Fandom encendidos. No es bloqueante para task-15.

**O2 — Deriva de nombres entre el plan de pruebas y lo implementado.** La spec hablaba de
`tests/_cache_falsa.py`, `tests/test_fandom_cache.py` y `tests/test_cache_http_pg.py`; la
implementación usa `CacheHttpFalsa` dentro de `tests/test_cache_http.py`, y las pruebas de Fandom
van dentro de `test_fandom.py`. La cobertura de los AC es equivalente (salvo O1); lo dejo escrito
para que no se busquen ficheros inexistentes.

**O3 — `tests/test_fandom.py` importa fakes de `tests.test_cache_http`.** Funciona (la pasada
aislada de `test_fandom.py` sale verde), pero acopla dos módulos de pruebas; mover `CacheHttpFalsa`
a un helper compartido evitaría el acoplamiento.

**O4 — Estado de robots en memoria y toggles.** El `GestorRobots` del proceso no se reinicia al
apagar/encender la fuente: tras un fallo puede quedar un bloqueo de hasta 15 min aunque la fuente
se apague y vuelva a encenderse. Es el TTL previsto por RFC 9309; solo lo anoto por si el producto
quiere reiniciarlo desde Ajustes en una historia futura.

**O5 — Alcance de Postgres en esta verificación.** La suite completa se ejecutó **sin**
`TEST_DATABASE_URL` (2271 skips esperados) porque el entorno del encargo no la aporta; la validación
real con Postgres se hizo focalizada en la migración 0038 + `CacheHttp` (2 passed), que es lo que
pedía el encargo. El resto de pruebas `_pg` no se ejecutó aquí.

---

## 4. Veredicto

**APTO.** SCR1 cumple los criterios (a)-(i): suite completa verde dos veces con contadores idénticos
(6676 passed / 2271 skipped), suites de SCR1 aisladas verdes (68 passed + 2 skips de Postgres),
migración 0038 y `CacheHttp` validados contra Postgres real (2 passed), `ruff` y `ruff --select S`
limpios, `protego` como única dependencia nueva y pruebas existentes intactas.
**Bloqueantes: ninguno.** Recomendaciones no bloqueantes: O1 (prueba del cableado de caché en el
enricher) y O3 (sacar los fakes a un helper).

---

## 5. Inventario del cambio revisado (`0b5e60d8`)

12 ficheros, **+1906 / −12** (las 12 supresiones son líneas modificadas de `fandom.py`/`enricher.py`,
no pruebas):
`pyproject.toml`, `alembic/versions/20261113_0038_http_cache.py`, `src/zascarr/main.py`,
`src/zascarr/models/__init__.py`, `src/zascarr/services/enricher.py`, `src/zascarr/services/fandom.py`,
`src/zascarr/utils/cache_http.py`, `src/zascarr/utils/robots.py`, `tests/test_cache_http.py`,
`tests/test_fandom.py`, `tests/test_migracion_http_cache_pg.py`, `tests/test_robots.py`.
`git diff HEAD~1 HEAD --numstat -- tests/`: **0 eliminaciones** en pruebas (solo adiciones).


---

## Nota post-fusión: renumeración de la migración (2026-11-13)

Al desplegar se detectó que **`0037` estaba duplicada** (otra historia —`borradores_revision`— la
ocupó en paralelo y `main` quedó con dos cabezas). La migración de esta historia se renumeró a
**`0038`** (`revision="0038"`, `down_revision="0037"`), sin cambios de SQL; la cadena queda
`0036 → 0037 (borradores) → 0038 (http_cache)`. Las referencias a `0037` en el cuerpo de este
informe deben leerse como la revisión `0038` de `http_cache`. Añadida la regresión
`tests/test_migraciones_cadena.py` (revisiones únicas, una sola cabeza y cadena lineal).
