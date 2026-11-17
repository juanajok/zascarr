# Builder BL-OPS2 — cierre de hallazgos de SecOps (TDD)

- **Fecha:** 2026-11-17
- **Autor:** Builder (TDD), a partir del informe `secops-BL-OPS2-2026-11-17.md` (SecOps) y de `especificacion-BL-OPS2.md` (v1.4).
- **Worktree:** `/mnt/Datos/Documentos/wt-ops2builder` (detached en `929aa6c8`, base `fix/ops2-bloqueantes`; el merge de la PR #1031, `5cf947b4`, es ancestro).
- **Rama:** `feat/ops2-builder` (commits nuevos sobre `929aa6c8`). **Sin fusión ni despliegue.**
- **SHA del código y las pruebas:** `a39af25859ce20c168f8309ce8258c91e048d4c3`. El **head del PR** añade encima solo este documento (mismo árbol de código y pruebas): QA debe revalidar el head, sin parches manuales.
- **Naturaleza:** cambios de código + pruebas. **No** se ha tocado la Pi, producción, los informes de SecOps/QA, ni el worktree principal.

---

## 1. Resumen

| Hallazgo | Estado | Cómo se cerró |
|---|---|---|
| F-03 (alto) | **PASS** | Restauración con base nueva `zascarr_restaurando`, comprobación con la app sirviendo y cambio por `ALTER DATABASE … RENAME`; la base viva no se destruye (BR-06). Vuelta atrás por renombrado. |
| F-04 (alto) | **PASS** | La seguridad se **relee con la app parada** (FR-20.6) y la copia previa se toma **también con la app parada** (FR-21). |
| F-06 (alto) | **PASS** | `ops-restaurar.json` escrito por fases (códigos y números), `config.py` + compose + lector en la app; estados «en marcha/sin noticias/hecha/fallida/no arrancó». |
| F-07 (alto) | **PASS** | Estado de la restauración separado del de copia (`accion`), sin botones «Restaurar…» mientras hay operación, `POST` que no contacta, aviso en `/login`. |
| F-15 (medio) | **PASS** | Recuentos genéricos de **todos** los bloques `COPY public.*` del dump (AC-51), con prueba de tabla nueva y de carga parcial. |
| F-18 (medio) | **PASS (local) / NOT RUN en Pi** | Límites v2 con reloj inyectado + paridad de umbrales + **T-10/T-21 con PostgreSQL real** (proyecto Compose aislado, renombrado real). |
| F-16 (medio) | **PASS (estático)** | Unidad endurecida, sin `/opt/zascarr` en `ReadWritePaths`, timeout 45 min sin `RuntimeMaxSec`; prueba estática ampliada. |
| F-21 (bajo) | **PASS (parcial)** | Tipos estrictos del manifiesto en la lista propia (`bytes`/`schema` booleanos, sha no-hex). Queda fuera comparar SHA/bytes del dump en el auxiliar (el script revalida antes de tocar nada). |
| F-22 (bajo) | **PASS (parcial)** | `trap` de limpieza de los temporales con la fila vigente; probado en los caminos normales. `SIGKILL` sigue siendo límite documentado. |
| F-23 (bajo) | **PASS (parcial)** | ADR 0023 y `SECURITY.md` describen el flujo real. La spec v1.4 aprobada sigue citando el ADR 0019 (no se toca el documento aprobado; nota en §6). |
| F-08 (F-18) | **PASS** | El bloqueo de prueba dura de verdad 30 min desde el último fallo; paridad contra `reautenticacion.py`. |
| QA VM: `DOCKER_CONFIG` | **PASS** | `Environment=` en la unidad + export en el wrapper; prueba estática. |
| QA VM: `@BACKUP_DIR@` | **PASS** | El instalador lo resuelve del entorno/`.env` o al valor por defecto; se niega a instalar una unidad con marcadores. |
| QA VM: `HEALTH_URL` | **PASS** | Unidad y wrapper fijan `http://127.0.0.1:8000/api/health` (sobreescribible). |
| QA VM: dollar-quoting | **PASS** | El literal es `$tag$…$tag$::jsonb`; probado con PostgreSQL real y con una prueba de forma sobre el SQL generado. |

**Bugs reales que destapó el TDD (no eran solo cobertura):**

1. **Dollar-quoting mal formado** en la reaplicación (`$tag` … `$tag::jsonb`): PostgreSQL lo rechaza con `syntax error`. Un `psql` falso lo ocultaba. Corregido y probado contra PostgreSQL real.
2. **`psql_en` dentro de `while read`** consumía la sustitución de procesos: los recuentos genéricos solo procesaban la primera tabla. Corregido con `</dev/null`.
3. **Bloqueo de fallos de 30 min** no implementado (F-08): se reutilizaba la ventana de 15 min. Corregido.
4. **Contadores con `time.time()`** (no el reloj inyectado): los topes no se podían probar con un reloj falso. Corregido.
5. **`fuentes_heredadas`** se validaba como array cuando el tipo real de `config.py`/`runtime_settings.py` es booleano: habría rechazado cualquier restauración real.
6. **`tomar_cerrojo_operaciones` devolvía 0 con el cerrojo ocupado** en el patrón `if ! …; then rc=$?` (el `$?` era el de la negación). Corregido con `|| rc=$?`; la prueba de AC-36 exige 75.
7. **`@BACKUP_DIR@` vacío** en la unidad instalada (QA en la VM).
8. **`DOCKER_CONFIG`/`HEALTH_URL`** sin llegar al wrapper con `ProtectHome=true` (QA en la VM).

---

## 2. Método TDD

Para cada cambio: **test que falla → rojo demostrado → implementación mínima → verde → suite de alcance**. No se ha borrado ni debilitado ninguna prueba existente; las dos pruebas de producción del fichero antiguo se **adaptaron** al flujo nuevo (mismo nombre y mismas aserciones sobre la mezcla de seguridad), justificado en §4.

Intérprete y entorno de las ejecuciones (sin `TEST_DATABASE_URL` en esta máquina):

```
PYTHONPATH="$PWD/src" ZASCARR_PRUEBAS=1 OPS_LOCK_FILE=/tmp/lock-builder-tests \
  /mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python -m pytest -p no:cacheprovider -q <ficheros>
```

`ZASCARR_PRUEBAS=1` + `OPS_LOCK_FILE` es el **único** cambio permitido en el arnés de `tests/test_restaurar_datos.py` (AC-34): el cerrojo se toma en todos los modos.

### 2.1 F-03/F-04/F-15 — flujo de producción

- **Rojo:** `pytest tests/test_restaurar_produccion.py` → **12 failed** (el script antiguo hacía `stop → dropdb → createdb → psql` y no escribía `ops-restaurar.json`; el falso aborta las lecturas de seguridad y `pg_dump` si la app no está parada).
- **Implementación:** `scripts/restaurar_datos.sh` rama `--produccion` con base nueva, comprobaciones, parada, relectura de seguridad, reaplicación + relectura, copia previa con la app parada, renombrado, arranque y vuelta atrás; estado por fases con `printf` + `mv`.
- **Verde:** `pytest tests/test_restaurar_produccion.py` → **12 passed** (29,87 s).
- **Regresión del modo antiguo:** `pytest tests/test_restaurar_datos.py` → **53 passed**; la única prueba adaptada es `test_produccion_conserva_seguridad_vigente_y_claves_de_la_copia` (arnés nuevo; mismas aserciones de mezcla FR-34).

### 2.2 F-06/F-07 — estado y UI

- **Rojo:** `pytest tests/test_restauracion_estado.py` → **1 failed, 33 errors** (no existían `resolver_restauracion`, `EstadoRestaurar`, `aviso_de_login`, ni el campo de config; `GET /estado` no pintaba el estado).
- **Verde:** **34 passed**. Suites de UI/auth juntas: **392 passed** antes de las últimas adiciones (F-16/F-21/F-22 y QA VM), ver §2.7.

### 2.3 F-18 — límites v2 y PostgreSQL real

- **Rojo (parcial):** las pruebas nuevas de límites fallaron primero con **`ContadorIlegible`** (el auxiliar leía el reloj real, no el inyectado) y con **`bloqueo_temporal` → `aceptada` a los 15 min** (bloqueo efectivo más corto de 30 min). Ambos eran bugs reales.
- **Verde:** `pytest tests/test_ops_auxiliar.py tests/test_ops_paridad.py` → **92 passed**; tras F-21, **87 passed** en el fichero del auxiliar.
- **PostgreSQL real** (`tests/test_restaurar_produccion_pg.py`, Docker local, proyecto Compose aislado, sin tocar producción/Pi): **2 passed** (61,17 s). Ejecuta el script real de punta a punta con renombrado real:
  - contraseña A (copia) → B (vigente): **B vale y A no**, `secret_key` vigente, `auth_session_version = max(7,3)+1 = 8`, `base_url` vigente, `*_enabled`/webhook vigentes, claves de integración de la copia; fila escrita después del dump desaparece; `zascarr_previa`/`zascarr_restaurando` no quedan; `rollback-safety` 0600 y legible; estado `hecha` con recuentos.
  - fila vigente **hostil** (comillas, `$$`, barra, salto de línea, Unicode): vuelve byte a byte.
  - Esta prueba destapó el dollar-quoting y el consumo de `stdin` de `psql_en` (ambos corregidos).

### 2.4 QA VM — `@BACKUP_DIR@`

- **Rojo:** test de la unidad instalada → `assert '/var/backups/zascarr/postgres' in unidad` falla (marcador sustituido por vacío).
- **Verde:** `pytest tests/test_instalar_ops.py` → **19 passed**; prueba de que no queda ningún marcador `@…@`, que `ReadWritePaths` lleva `@BACKUP_STATUS_DIR@` y el `BACKUP_DIR` real (por defecto o el del `.env`), y que el instalador aborta si quedara un marcador.

### 2.5 F-21 / F-22 / F-16

- **Rojo F-21:** `true`/`-1` aceptados como `bytes` y `schema` booleano aceptado → test falla; **verde** tras tipos estrictos (`87 passed`).
- **F-22:** la prueba del fallo cerrado de `jsonb` comprueba que el `trap` no deja `seguridad.*` en `BACKUP_DIR` (caminos normales).
- **F-16:** prueba estática de endurecimiento de `zascarr-restaurar@.service` (sin `/opt/zascarr`, `Requires`, `Protect*`, `UMask`, timeout 45 min, sin `RuntimeMaxSec`).

### 2.6 QA VM — `DOCKER_CONFIG`, `HEALTH_URL` y dollar-quoting

- **Rojo:** la prueba estática del wrapper/unidad falla (`DOCKER_CONFIG`/`HEALTH_URL` ausentes).
- **Implementación:** `Environment=DOCKER_CONFIG=/run/zascarr-ops/docker` y `Environment=HEALTH_URL=http://127.0.0.1:8000/api/health` en la unidad (y `ReadWritePaths` para el directorio de Docker); el wrapper repite ambos como respaldo (`${…:-…}`).
- **Verde:** `pytest tests/test_instalar_ops.py` → **19 passed**.
- **Dollar-quoting:** prueba de forma sobre el SQL que el script escribe en el `psql` (regex `$tag$…$tag$::jsonb`) además de la prueba con PostgreSQL real. El código ya emite `$tag$` en ambos extremos.

### 2.7 Suites de alcance (última ejecución completa)

```
14 ficheros de alcance + PostgreSQL real:
pytest tests/test_restauracion_estado.py tests/test_copias_ops.py tests/test_restauracion_ops2.py \
       tests/test_auth.py tests/test_auth_hx_redirect.py tests/test_auth_limites.py \
       tests/test_restaurar_produccion.py tests/test_restaurar_produccion_pg.py \
       tests/test_restaurar_datos.py tests/test_instalar_ops.py tests/test_ops_auxiliar.py \
       tests/test_ops_paridad.py tests/test_health.py tests/test_estado_copia_fallida.py
→ ver §7 (resultado literal al cerrar)
```

Antes de las últimas adiciones: **392 passed, 5 warnings in 94,90 s** (sin el fichero PG, que se ejecuta aparte por Docker).

---

## 3. Cambios por fichero

| Fichero | Qué |
|---|---|
| `scripts/restaurar_datos.sh` | Rama `--produccion` nueva (base nueva, comprobaciones, parada, seguridad releída y reaplicada con `$tag$…$tag$`, copia previa con la app parada, renombrado y vuelta atrás, `ops-restaurar.json` por fases, `omitida.json` con `accion:"restaurar"`, recuentos genéricos AC-51); `psql_en` con `</dev/null`; cerrojo 75 corregido; `fuentes_heredadas` booleano; `DOCKER_CONFIG`/`HEALTH_URL` no aplican aquí (unidad/wrapper). |
| `scripts/instalar_ops.sh` | `BACKUP_DIR` resuelto del entorno/`.env`/valor por defecto; aborta si un marcador `@…@` queda sin sustituir. |
| `deploy/systemd/zascarr-restaurar@.service` | `Environment=DOCKER_CONFIG=…`, `Environment=HEALTH_URL=…`, `ReadWritePaths` con el directorio de Docker; endurecimiento completo y timeout 45 min (ya en la base). |
| `deploy/ops/restaurar-produccion.sh` | `export DOCKER_CONFIG` y `export HEALTH_URL` por defecto (sobreescribibles). |
| `deploy/ops/zascarr_ops.py` | Reloj inyectado en `_leer_epocas`; bloqueo de 30 min real; tipos estrictos en `listar_copias`. |
| `src/zascarr/config.py` | `ops_restaurar_status_file`. |
| `docker-compose.yml` | `OPS_RESTAURAR_STATUS_FILE` (sin volúmenes nuevos). |
| `src/zascarr/services/ops_host.py` | `EstadoRestaurar`/`VistaRestaurar`, `resolver_restauracion`, `aviso_de_login`, `miles`, `CAUSAS_RESTAURAR`; filtro de `accion` en `omitida`. |
| `src/zascarr/services/restauracion.py` | `ofrecer(..., permitir=False)` y comprobación de restauración en marcha antes de la contraseña. |
| `src/zascarr/web/copias.py` y plantillas | Estado de restauración en el bloque de copias, sin botones mientras hay operación, botón de copia deshabilitado, aviso en `/login`, confirmación sin formulario si hay otra en marcha. |
| `src/zascarr/web/auth.py` + `login.html` | Aviso FR-32 (solo fichero, sin fecha). |
| `docs/adr/0023-…`, `SECURITY.md` | Flujo real y límites (F-23). |
| `tests/` | Nuevos: `test_restaurar_produccion.py` (+ `_restaurar_produccion.py`), `test_restaurar_produccion_pg.py`, `test_restauracion_estado.py`; ampliados: `test_restaurar_datos.py` (una prueba adaptada), `test_instalar_ops.py`, `test_ops_auxiliar.py`, `test_ops_paridad.py`, `test_restauracion_ops2.py` (arnés). |

---

## 4. Pruebas existentes adaptadas (justificación)

- `tests/test_restaurar_datos.py::test_produccion_conserva_seguridad_vigente_y_claves_de_la_copia`: **mismo nombre y mismas aserciones** sobre la mezcla FR-34, pero el arnés pasa a `tests/_restaurar_produccion.py` porque el flujo antiguo (drop/recarga) ya no existe (F-03). No se ha tocado ninguna otra prueba de ese fichero.
- `tests/test_restauracion_ops2.py`: el fixture usaba un `Settings` mínimo; se añade el mock de `resolver_restauracion` para el nuevo paso (3) de FR-03. Las aserciones no cambian.
- `tests/test_instalar_ops.py::test_las_unidades_cumplen_fr29_y_fr01`: se amplía la prueba de tmpfiles/instalador ya existente para el `BACKUP_DIR`; no se elimina nada.

---

## 5. Comandos ejecutados (evidencia literal)

```
# Rojo F-03/F-04 (antes de implementar)
pytest -q tests/test_restaurar_produccion.py
→ 12 failed, 1 warning in 4.74s

# Verde
pytest -q tests/test_restaurar_produccion.py
→ 12 passed, 1 warning in 29.87s

# Modo antiguo intacto
pytest -q tests/test_restaurar_datos.py
→ 53 passed, 1 warning in 29.33s

# Rojo F-06/F-07
pytest -q tests/test_restauracion_estado.py
→ 1 failed, 33 errors

# Verde F-06/F-07
pytest -q tests/test_restauracion_estado.py
→ 34 passed, 1 warning in 4.90s

# Alcance UI/auth
pytest -q tests/test_copias_ops.py tests/test_restauracion_ops2.py tests/test_restauracion_estado.py \
         tests/test_auth.py tests/test_auth_hx_redirect.py tests/test_auth_limites.py tests/test_health.py
→ 191 passed (2 fallos de arnés corregidos) ; después, 392 passed en el conjunto de alcance

# Auxiliar + paridad (F-18/F-08/F-21)
pytest -q tests/test_ops_auxiliar.py tests/test_ops_paridad.py
→ 92 passed ; después 87 passed en el fichero del auxiliar (con F-21)

# PostgreSQL real (T-10/T-21)
pytest -q tests/test_restaurar_produccion_pg.py
→ 2 passed, 1 warning in 61.17s

# Instalador (QA BACKUP_DIR + DOCKER_CONFIG/HEALTH_URL)
pytest -q tests/test_instalar_ops.py
→ rojo (BACKUP_DIR) ; verde 19 passed

# Sintaxis de shell
bash -n scripts/restaurar_datos.sh scripts/instalar_ops.sh deploy/ops/restaurar-produccion.sh
→ sin salida (OK)
```

---

## 6. PASS / FAIL / NOT RUN

### PASS

- F-03, F-04, F-06, F-07, F-15, F-08 (bloqueo 30 min), F-16 (estático), F-21 (tipos estrictos), F-23 (ADR/SECURITY).
- QA VM: dollar-quoting, `@BACKUP_DIR@`, `DOCKER_CONFIG`, `HEALTH_URL`.
- C-10 invertida con PostgreSQL real (contraseña A→B, `max+1`, integraciones de la copia, política vigente, hostiles).
- AC-51: tabla nueva del dump contada sin tocar el script; tabla cargada a medias detectada.
- AC-31/AC-32/AC-33/AC-36/AC-45 (unitarias con `docker` falso y la real de AC-45 con PG).
- AC-34: modo sin `--produccion` con las mismas aserciones y el arnés solo con `ZASCARR_PRUEBAS=1`+`OPS_LOCK_FILE`.

### FAIL / parcial (declarado, no PASS)

- **F-18 en la Pi / systemd real:** **NOT RUN** (requiere Pi y root). El T-10/T-21 con PostgreSQL real se ha ejecutado en Docker local, no en la Pi.
- **F-22:** el `trap` cubre los caminos normales; un `SIGKILL`/corte puede dejar temporales 0600 con la fila vigente y la app parada (límite documentado en el ADR).
- **F-21:** queda sin hacer la comparación SHA/bytes del manifiesto con el dump en el auxiliar (el script revalida antes de tocar nada; la lista es informativa).
- **F-23:** la spec v1.4 aprobada sigue citando el ADR 0019; no se edita el documento aprobado (nota para el PO).
- **Límite v2:** el tope de línea v2 es 4096 B (necesario para 512 B UTF-8 escapados; el arnés y el auxiliar coinciden y hay paridad), frente a los 1024 B literales de FR-06. Se documenta como desviación consciente de F-19 en lugar de recortar contraseñas con emoji (AC-07).

### NOT RUN

- Pi, systemd real, socket real, `docker exec` desde la unidad del auxiliar, `systemd-analyze security`, tiempos/RAM/parada reales (NFR-01…NFR-05), navegador con la app parada (P-6).
- QA revalidando el SHA final (pendiente, es el objetivo de este PR draft).
- CI con `TEST_DATABASE_URL` (en esta máquina no está definida; la prueba PG usa Docker y se salta si no hay Docker).

---

## 7. Resultado literal de la suite final

Ejecutada sobre el árbol de este commit (incluye las dos pruebas con PostgreSQL real; Docker local):

```
pytest -q tests/test_restauracion_estado.py tests/test_copias_ops.py tests/test_restauracion_ops2.py \
       tests/test_auth.py tests/test_auth_hx_redirect.py tests/test_auth_limites.py \
       tests/test_restaurar_produccion.py tests/test_restaurar_produccion_pg.py \
       tests/test_restaurar_datos.py tests/test_instalar_ops.py tests/test_ops_auxiliar.py \
       tests/test_ops_paridad.py tests/test_health.py tests/test_estado_copia_fallida.py
→ 398 passed, 5 warnings in 132.27s (0:02:12)
```

(«5 warnings» son `DeprecationWarning` de Starlette/httpx y de `fork()` en las pruebas de concurrencia; ninguna es un
fallo. Las pruebas PG se saltan solas si no hay Docker.)

---

## 8. Commits y PR

- `728f331b` — la unidad conoce `BACKUP_DIR` (QA/F-16).
- `cbadf854` — flujo de producción con base nueva, renombrado y copia previa con la app parada (F-03/F-04/F-15); dollar-quoting y `psql_en` (F-18).
- `b7578caf` — estado de la restauración en UI y aviso `/login` (F-06/F-07).
- `c261cbf5` — límites v2 con reloj inyectado, bloqueo de 30 min y PostgreSQL real (F-18/F-08).
- `b567f8ca` — tipos estrictos de la lista, F-16/F-22.
- `b226d4fb` — ADR 0023 y SECURITY (F-23).
- `a39af25859ce20c168f8309ce8258c91e048d4c3` — `DOCKER_CONFIG`/`HEALTH_URL` (QA VM): **SHA del código y las pruebas**. Este documento va en el commit de encima (head del PR).
- **Rama:** `feat/ops2-builder`; **PR draft a `main`:** ver enlace en el mensaje al Lead. **No fusionado, no desplegado.**

---

## 9. Riesgos y notas para SecOps/QA

1. **Cambio de flujo real:** ahora hay dos bases (`zascarr_restaurando`, `zascarr_previa`) y renombrado; verificar en la Pi (`P-3`) los reintentos y que no quede `_previa`/`_fallida` (bloquean la siguiente restauración a propósito).
2. **`DOCKER_CONFIG=/run/zascarr-ops/docker`**: el directorio lo crea tmpfiles/instalador (0700 root); la unidad lo añade a `ReadWritePaths`. Si una instalación antigua no tiene el tmpfiles aplicado, reejecutar `systemd-tmpfiles --create`.
3. **`HEALTH_URL`** fijo a 8000 en la unidad; si el operador publica la app en otro puerto, debe ajustar la unidad (documentado en el propio comentario).
4. **Vuelta atrás:** `recuperacion_fallida` exige copia previa > 0 y datos en `_previa` o `_fallida`; es algo más laxa que el texto literal de FR-22 (que nombra solo `_previa`), porque en el deshacer la previa puede haberse renombrado ya. Se documenta para la revisión.
5. **Harness:** `tests/test_restaurar_datos.py` requiere `ZASCARR_PRUEBAS=1` y `OPS_LOCK_FILE` (AC-34); en CI hay que exportarlos para esa suite.
6. **Prueba PG con Docker:** se salta sin Docker. En CI con `TEST_DATABASE_URL` no se ha probado (no hay cliente `psql` en el host); si el CI lo tiene, se puede portar el helper `tests/_pg.py`.
7. **No se ha tocado** el worktree principal, la Pi, producción, los informes de SecOps/QA, ni `docs/design/especificacion-BL-OPS2.md`.
