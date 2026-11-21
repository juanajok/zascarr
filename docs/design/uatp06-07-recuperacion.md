# Rechazar una copia dañada y recuperar catálogo y archivos (UATP-06/07, A6)

> **Estado:** especificación para implementar y acreditar. **Este documento NO declara cumplidas
> UATP-06 [#1144](https://github.com/juanajok/zascarr/issues/1144) ni UATP-07
> [#1145](https://github.com/juanajok/zascarr/issues/1145).** No implementa código, no cambia
> contratos vigentes por sí solo, no crea ADR y no decide por el PO. Las decisiones D-1…D-6 de §3
> son **recomendaciones de SPEC.writer**; la implementación y la evidencia son tareas aparte.
>
> **Insumos:** benchmark de task-61 (SCOUT.bench, 2026-11-21, solo lectura), épica
> [#1141](https://github.com/juanajok/zascarr/issues/1141) (incluye las evidencias del piloto
> `A6/resultado.md` y `A6/evidencia/resultado.txt`), BL-OPS1/2/3 [#443](https://github.com/juanajok/zascarr/issues/443),
> [`especificacion-BL-OPS2.md`](especificacion-BL-OPS2.md), [`backup-334.md`](backup-334.md),
> [`uatp08-readiness.md`](uatp08-readiness.md) y ADR 0025
> ([`docs/adr/0025-aviso-de-version-observacional.md`](../adr/0025-aviso-de-version-observacional.md)).
>
> **Base contrastada:** `origin/main` = **`3eb38cd2`** (2026-11-21), con `d5f26df5` como referencia
> de `origin/main` en los documentos vecinos. El implementador debe ramificar desde `origin/main`,
> no desde una copia local atrasada.
>
> **Único escritor de este documento:** SPEC.writer. No toca código, tests, otras docs ni
> `docs/BACKLOG.md`.

## 0. Resumen ejecutivo

**Lo que ya existe (PASS, leído en `3eb38cd2`).** `restaurar_datos.sh` tiene un preflight serio:
SHA-256, bytes, schema del manifiesto, revisión de Alembic, gzip, cabecera de `pg_dump` y cuatro
tablas, **antes** de crear la base de restauración. El modo `--produccion` escribe
`ops-restaurar.json` en cada fase con códigos cerrados, incluido `base_en_su_sitio`, y el lector de
la interfaz ya traduce `copia_no_valida` a «Esa copia está dañada, así que no se ha usado. Elige
otra.» (§2). El flujo positivo con copia válida está probado con Docker falso y, opcionalmente,
con PostgreSQL real.

**Lo que falta y bloquea la acreditación.**

1. **Pruebas de producción del caso negativo.** Los tests de preflight existentes son del modo
   aislado ([`tests/test_restaurar_datos.py:382-459`](../../tests/test_restaurar_datos.py:382)) y
   no recorren `--produccion`, ni `ops-restaurar.json`, ni el estado intacto, ni la ausencia de
   eventos de contenedor. El harness de producción ya registra eventos
   ([`tests/_restaurar_produccion.py:34-35`](../../tests/_restaurar_produccion.py:34)), pero no hay
   ningún caso que los use como aserción de «no se tocó nada» (§2.6, T-06).
2. **La copia de archivos no existe en el producto.** `backup.sh` solo hace `pg_dump`
   ([`scripts/backup.sh:12`](../../scripts/backup.sh:12)) y `probar_restauracion.sh` solo restaura
   el dump en una base desechable ([`scripts/probar_restauracion.sh:1-10`](../../scripts/probar_restauracion.sh:1)).
   UATP-07 exige «restaurar el catálogo **y la copia de archivos** en un destino vacío»; hoy es un
   paso externo no documentado. La decisión D-1 lo convierte en procedimiento manual verificable.
3. **No hay versión de la copia.** El manifiesto guarda `codigo_desplegado_sha_completo` (HEAD) y
   `alembic`, pero no `app_version` ni el `BUILD_SHA` de la imagen
   ([`scripts/_comun.sh:303-344`](../../scripts/_comun.sh:303)); `ops-restaurar.json` no declara
   ninguna versión ([`scripts/restaurar_datos.sh:55-80`](../../scripts/restaurar_datos.sh:55)).
   `app_version` es un literal `1.15.1` ([`src/zascarr/config.py:408`](../../src/zascarr/config.py:408))
   y la identidad real de la imagen es `BUILD_SHA`
   ([`Dockerfile:31-33`](../../Dockerfile:31), ADR 0025), que hoy no se lee. D-2 define
   `version_de_la_copia` como la tupla **BUILD_SHA + HEAD + app_version + Alembic**, nunca solo
   «1.15.1».
4. **El diagnóstico no sobrevive al intento.** `ops-restaurar.json` se reescribe en cada intento y
   no tiene id de intento ni la comprobación concreta que falló; el fallo negativo se queda en un
   `copia_no_valida` genérico. D-5 añade `intento`, `comprobacion`, `copia_version` y un registro
   acotado por intento.
5. **`A6` no existe.** La épica cita `A6/resultado.md` y `A6/evidencia/resultado.txt`; no constan
   ni en el repo ni en el árbol de trabajo. D-4 fija su ubicación, formato y reglas de redacción.
6. **La tabla ausente solo se detecta a medias.** El preflight exige cuatro tablas
   (`alembic_version`, `series`, `files`, `wishlist`); `issues` no está en esa lista. Un dump sin
   `issues` puede superar el preflight y fallar después de `createdb`/carga, ya con eventos de
   contenedor. D-6 propone la enmienda mínima de FR-17(d) para añadir `issues`; N-03b la prueba.

**Veredicto de esta spec:** UATP-06 es **especificable y acreditable** con los contratos actuales
más los cambios aditivos de §4 y la enmienda D-6; UATP-07 es **especificable solo como
procedimiento manual documentado** (D-1), con la salvedad de la cláusula «tag sin lector» (D-3).
Ninguna de las dos puede declararse cumplida sin ejecutar A6 (§7) sobre una candidata identificada.

---

## 1. Alcance / no alcance

**Dentro.**

| Pieza | Qué se especifica |
|---|---|
| UATP-06 | Matriz negativa SHA/gzip/tabla, instantánea antes/después, cero eventos de contenedor, resultado `copia_no_valida` + `base_en_su_sitio`, control positivo y diagnóstico por intento. |
| UATP-07 | Copia de archivos **manual documentada** (raíces, destino vacío, mtime, inventario, sha256 testigo, orden) y reapertura en la página guardada tras restaurar catálogo + archivos. |
| Versión | `version_de_la_copia` = `BUILD_SHA` de la imagen + `HEAD` + `app_version` + revisión de Alembic; manifiesto y `ops-restaurar.json`; tags T0/T1/C. |
| A6 | `A6/resultado.md`, `A6/evidencia/resultado.txt`, catálogo de comprobaciones, formato, comandos, PASS/FAIL/NOT RUN y prohibición de secretos. |
| Contratos aditivos | §4: manifiesto, `ops-restaurar.json`, `ops-restaurar-intentos.jsonl`; sin migración, sin dependencias nuevas, sin tocar la biblioteca. |

**Fuera de alcance (explícito).**

- **Herramienta de producto para copiar archivos.** No se añade a `backup.sh`, no se crea un
  comando de restauración de archivos, no se toca la biblioteca desde ZascArr. Si el PO quiere
  herramienta, es otra historia (D-1).
- **Cubrir portadas, `.env`, credenciales, configuración del host, el volumen de PostgreSQL,
  `update_*` ni `rollback-safety_*`.** La copia de archivos es solo de las raíces de biblioteca.
- **Resumen de recuperación en la interfaz (fecha/versión/omitido/comprobaciones).** Es UATP-08
  [#1146](https://github.com/juanajok/zascarr/issues/1146); esta spec solo deja los datos que
  UATP-08 necesitará.
- **Restaurar desde tags antiguos.** El script exige el mismo HEAD y la misma revisión de Alembic;
  no se rebaja esa garantía.
- **Borrar copias, retención, «deshacer» una restauración, actualizar código o desplegar.**
- **Migraciones, dependencias nuevas, JS nuevo, cambios de UI.** Ninguno hace falta para los
  criterios de UATP-06/07.
- **Medir la biblioteca en cada pintado o escanearla.** El coste en Pi (CLAUDE.md §4) prohíbe
  escaneos fuera del ensayo.

---

## 2. Estado real (PASS = leído en `3eb38cd2`; NOT RUN = no ejecutado aquí)

### 2.1 Preflight de `restaurar_datos.sh`

| # | Comprobación | Dónde | ¿Antes del primer evento de contenedor? |
|---|---|---|---|
| 1 | Cerrojo único de operaciones | `scripts/restaurar_datos.sh:122-133` | Sí (no es Docker). |
| 2 | `docker`, `git`, `jq`, `gzip`, `sha256sum`, `stat`, `curl`, `awk` presentes | `:154` | Sí. |
| 3 | `REPO_DIR`, `ENV_FILE`, `COMPOSE_FILE`, `BACKUP_DIR`, `DB_NAME`, `DB_USER` explícitos | `:157-159` | Sí. |
| 4 | `--produccion` rechaza opciones de ensayo y valida `--copia` | `:166-172` | Sí. |
| 5 | `git` árbol limpio y `HEAD == --sha` (en producción, HEAD) | `:210-226` | Sí. |
| 6 | `docker compose config` declara el proyecto esperado (`zascarr` en producción) | `:229-252` | **Es cliente, no evento de contenedor**; permitido. |
| 7 | Manifiesto existe, es JSON, `schema == 1`, declara `sha256` y `bytes` válidos | `:234-260` | Sí. |
| 8 | SHA-256 del dump y bytes coinciden; sidecar `.sha256` si existe | `:261-271` | Sí. |
| 9 | Alembic del manifiesto contra la esperada; commit del manifiesto contra HEAD | `:273-282` | Sí. |
| 10 | `gzip -t` | `:312-315` | Sí. |
| 11 | Cabecera de `pg_dump`, tabla `alembic_version`, `series`, `files`, `wishlist`, y `version_num` | `:317-328` | Sí. |
| 12 | Alembic del dump y de la BD actual contra la esperada | `:330-353` | **La BD actual se lee con `docker compose exec`**, después de todo lo anterior. |

**Conclusión.** Las comprobaciones de contenido (7–11) ocurren antes del primer `exec`/`stop`/`up`.
El único contacto con Docker antes es `docker compose config`, que no crea, arranca, para ni ejecuta
contenedores. La matriz de §5 puede exigir «cero eventos de contenedor» sin reordenar el script.

**Límite.** La lista explícita de tablas es de **cuatro** (`:325-327`). `issues` solo se cuenta en la
fase de base nueva (`verificar_base_nueva`, `:482-505`), después de `createdb`/carga. De ahí D-6 y
N-03b.

### 2.2 Resultado y diagnóstico actuales

- `ops-restaurar.json` lo escribe solo `restaurar_datos.sh`, con `printf` + `mv` atómico, `0644`,
  y `|| true` para no romper la restauración (`:55-80`). Campos actuales: `schema`, `copia`,
  `copia_epoch`, `inicio_epoch`, `actualizado_epoch`, `fase`, `resultado`, `error`,
  `base_en_su_sitio`, `recuentos`. Solo códigos y números (FR-24 de BL-OPS2, `:122`).
- En producción, el estado se activa **antes** de las comprobaciones de contenido
  (`:150-151`), así que un fallo de preflight sí deja `ops-restaurar.json` con `fallida`,
  `error=copia_no_valida` y `base_en_su_sitio=true`.
- `fallo_pre` deja la base viva intacta y borra la base nueva si existía (`:506-524`).
- El lector de la interfaz traduce `copia_no_valida` a causa y acción cerradas
  ([`src/zascarr/services/ops_host.py:463-478`](../../src/zascarr/services/ops_host.py:463)) y
  pinta `base_en_su_sitio=false` con aviso
  ([`ops_host.py:568-577`](../../src/zascarr/services/ops_host.py:568)).
- **Gaps:** no hay `intento` (dos intentos son indistinguibles), no hay `comprobacion` (SHA, gzip y
  tabla comparten `copia_no_valida`), no hay `copia_version`, y el fichero se sobrescribe: el
  intento fallido anterior desaparece cuando se intenta otra copia.

### 2.3 Versión

| Dato | Hoy | Evidencia |
|---|---|---|
| `HEAD` del checkout | `codigo_desplegado_sha_completo` en el manifiesto | `scripts/_comun.sh:318-335` |
| Revisión de Alembic | `alembic` en el manifiesto | `scripts/_comun.sh:319-333` |
| `BUILD_SHA` de la imagen | Existe en el contenedor (`ENV BUILD_SHA`), pero **no se escribe** en el manifiesto ni en el estado | `Dockerfile:31-33`, `docker-compose.yml:110`; ADR 0025 |
| `app_version` | Literal `1.15.1`; `/api/health` lo devuelve como `version` | `src/zascarr/config.py:408`, `src/zascarr/api/health.py:459` |
| `ops-restaurar.json` | Sin versión | `scripts/restaurar_datos.sh:55-80` |
| `copias.json` | `revision` (Alembic), pero sin versión; FR-16 prohíbe hashes y rutas | `scripts/_comun.sh:362-397` |

`app_version` **no es identidad**: sigue siendo `1.15.1` aunque el código haya avanzado. La
identidad de la imagen es `BUILD_SHA` (ADR 0025). Por eso `version_de_la_copia` es una tupla y no
un semver (§3 D-2, §4.1).

### 2.4 Copia de archivos

| Superficie | Qué hace | Qué no hace |
|---|---|---|
| `scripts/backup.sh` | `pg_dump`, verifica gzip/cabecera/tablas, firma SHA-256, manifiesto, copia offsite, retención | **No copia la biblioteca** (`:12`); no toca CBZ/CBR. |
| `scripts/probar_restauracion.sh` | Restaura el dump en `zascarr_restore_<TS>_<pid>` y comprueba recuentos; borra la base al final | No sustituye la base viva, no escribe `ops-restaurar.json`, no toca archivos (`:1-10`). |
| `restaurar_datos.sh --produccion` | Restaura solo el catálogo; el aviso de BL-OPS2 lo dice y deja la biblioteca intacta | No restaura archivos ni portadas (FR-35(e), `especificacion-BL-OPS2.md:148`). |

Por tanto, la «copia de archivos» de UATP-07 es hoy inexistente en el producto: D-1 la convierte en
un **paso manual documentado y verificado**, no en una función de ZascArr.

### 2.5 Tags y candidata

| Tag | Commit | ¿Lector (`web/lector.py`)? | ¿Restauración de producción (`ops_host`/`--produccion`)? | ¿Alembic? |
|---|---|---|---|---|
| `v1.15.1` | `4f6ccdd3` (2026-10-01) | **No** (`git ls-tree` vacío) | **No** | Hasta `0016`; no puede arrancar con un dump actual (`0052`). |
| `v1.1.0` | `6e8419c8` (2026-09-24) | No | No | Aún más antigua. |
| `v1.0.0` | `16b39adc` (2026-09-24) | No | No | Aún más antigua. |
| `main` actual | `3eb38cd2` (2026-11-21) | Sí (`dd0cba1f`, 2026-11-17) | Sí (`ddf78cde`, 2026-11-17) | `0052`. |

**Consecuencia.** No existe ningún tag publicado que sirva a la vez para «abrir el CBZ» y
«restaurar». El piloto de la épica se ejecutó sobre `main@62bd4e81` (2026-11-18), no sobre un tag.
D-3 fija T0/T1/C y la lectura honesta de la cláusula «tag anterior».

### 2.6 Cobertura actual de pruebas

| Qué | Estado | Evidencia |
|---|---|---|
| Preflight aislado: hash, bytes, manifiesto ausente/schema, Alembic, árbol sucio | **Probado** | `tests/test_restaurar_datos.py:382-489` |
| Flujo de producción: orden, renombrado, copia previa, fallos, seguridad | **Probado** con Docker falso | `tests/test_restaurar_produccion.py:49-278`, `tests/_restaurar_produccion.py` |
| PostgreSQL real del flujo de producción | **Probado si `TEST_DATABASE_URL`; si no, skip** | `tests/test_restaurar_produccion_pg.py:227` |
| Lector de estado y causas | **Probado** | `tests/test_restauracion_estado.py:65-131` |
| **Matriz negativa de producción (SHA, gzip, tabla) con estado intacto y cero eventos** | **No existe** | — |
| **`intento`/`comprobacion`/`copia_version` y registro por intento** | **No existe** | — |
| **Copia de archivos, mtime, testigo, reapertura** | **No existe** | — |
| **`A6`** | **No existe** | — |

---

## 3. Decisiones (recomendaciones de SPEC.writer; decide el PO)

### D-1 — ¿La copia de archivos es herramienta o paso manual documentado?

**Pregunta.** UATP-07 pide restaurar «el catálogo y la copia de archivos». ¿Se implementa una
herramienta en el producto o se documenta como paso externo?

**Opciones.**

- **(a) Paso manual documentado y verificado (recomendada).** Un procedimiento de recuperación con
  `rsync` en el host, destino vacío, comprobación de mtime/inventario/sha256 testigo, ejecutado por
  quien instala ZascArr. No toca código del producto; la evidencia se acredita en A6.
- **(b) Herramienta en `backup.sh`/`restaurar_datos.sh` que copie y restaure archivos.** Da más
  comodidad, pero añade al producto un coste y un riesgo nuevos: la biblioteca puede ser de cientos
  de GB, el cron de las 04:00 no debe copiarla sin control de espacio, el contenedor es de solo
  lectura para la app y no hay estrategia incremental ni retención de archivos. Es una historia
  propia, no una ampliación de UATP-07.
- **(c) No hacer nada y rebajar el CA.** Dejaría UATP-07 acreditada a medias y contradiría el issue.

**Recomendación (a).** Motivos: el producto no restaura archivos por diseño (BL-OPS2 §0); la
evidencia se puede producir con herramientas del sistema operativo; el riesgo de una copia a medias
es mayor que el de un paso manual bien guiado; y el presupuesto de la Pi no admite otra copia
automática sin diseño. **Consecuencia:** runbook §6, sin cambios en `backup.sh`; si el PO quiere
herramienta, se abre otra historia con su benchmark §13 y su presupuesto de disco.
**Afecta a:** alcance de UATP-07 y del producto; no a esta entrega de código.

### D-2 — ¿Qué es `version_de_la_copia` y de dónde sale?

**Pregunta.** «Versión» puede ser `app_version` (semver), el SHA del código, la revisión de Alembic
o una combinación. Hoy no hay ningún dato en `ops-restaurar.json` y `app_version` es estático.

**Opciones.**

- **(a) Tupla declarativa, aditiva y nunca bloqueante (recomendada).**
  `version_de_la_copia = {head, build_sha, app_version, alembic}`.
  - `head`: `git rev-parse HEAD` del checkout que hizo la copia (ya existe como
    `codigo_desplegado_sha_completo`).
  - `build_sha`: `BUILD_SHA` de la imagen que estaba en marcha; se lee con
    `docker compose exec -T zascarr printenv BUILD_SHA`; si la app está parada o el build fue
    manual, `null`.
  - `app_version`: `[project].version` de `pyproject.toml`; si no se puede leer, `null`. Un test
    de CI exige que coincida con `Settings.app_version`.
  - `alembic`: `alembic_version` de la BD (ya existe).
  Se escribe en el manifiesto para copias nuevas y se copia a `ops-restaurar.json` como
  `copia_version`. **Nunca bloquea una restauración**: la autoridad de compatibilidad sigue siendo
  la revisión de Alembic. Copias antiguas sin el campo → `copia_version: null` → «versión no
  consta»; no se infiere.
- **(b) Solo `app_version` (semver).** Insuficiente: hoy vale `1.15.1` para todo el código y no
  identifica el build; el issue pide declarar la versión de la candidata y la que abre el archivo.
  **Descartada.**
- **(c) SHA en `copias.json` y en la lista de la interfaz.** Rompe FR-16 («sin hashes») y no es
  legible para el coleccionista. **Descartada** salvo enmienda expresa.
- **(d) Exigir la tupla como precondición (rechazar si falta o si `build_sha != head`).** Haría
  irrestaurables las copias antiguas y los builds manuales; contradice «no inferir» y el objetivo
  de recuperar. **No recomendada.** Si el PO la elige, hay que enmendar FR-17(d) y añadir un
  código de error nuevo (ver D-6).

**Recomendación (a).** **Consecuencia:** cambios aditivos en `_comun.sh` y
`restaurar_datos.sh` (§4), sin migración, sin UI nueva en esta historia y sin romper lectores.
**Afecta a:** `scripts/_comun.sh`, `scripts/restaurar_datos.sh`, `tests/test_backup_script.py`,
`tests/test_restaurar_produccion.py`, nuevo test de versión.

### D-3 — Tags T0/T1/C y la cláusula «tag anterior sin lector»

**Pregunta.** UATP-07 dice: «Si el tag de partida carece del lector, comprobar la apertura y la
reanudación en una versión soportada que sí lo incluya, además de acreditar el arranque y el estado
recuperado en el tag anterior». ¿Qué tags se usan?

**Hechos.** `v1.15.1` no tiene lector **ni** restauración y su cabeza de Alembic es `0016`
(§2.5). Sin lector no se puede «avanzar a una página intermedia y guardar progreso» antes del
backup; sin restauración no se puede restaurar el catálogo; y con una cabeza de Alembic distinta no
puede arrancar contra un dump actual. La cláusula, leída al pie de la letra con los tags
publicados, **no es ejecutable**.

**Opciones.**

- **(a) Tres referencias y lectura honesta (recomendada).**
  - **T0 = `v1.15.1`** (tag publicado): se acredita **la ausencia** de lector y de restauración
    (`git ls-tree`), no la apertura. Es la prueba documental de que no sirve de baseline.
  - **T1 = tag anotado `uat-base-<fecha>`** sobre el SHA de `origin/main` desde el que se ramifica
    la candidata: incluye lector y restauración; en él se acredita el arranque y el estado
    recuperado (catálogo, relaciones, progreso) tras restaurar.
  - **C = tag anotado `uat-candidata-<fecha>`** sobre el SHA final: en él se acredita la apertura
    del CBZ en la página guardada.
  La cláusula «tag sin lector» se documenta como **no aplicable/ejecutable con los tags reales** y
  se eleva al PO; el resto del CA (apertura y reanudación en versión soportada + arranque y estado
  recuperado en la anterior) queda acreditado con T1 y C.
- **(b) Fabricar un tag intermedio entre la introducción de `restaurar_datos.sh` (2026-10-29) y el
  lector (2026-11-17).** Existió el script aislado, pero no la restauración desde interfaz y, sobre
  todo, **no se puede guardar progreso sin lector**. No resuelve la contradicción y añade un tag
  artificial. **No recomendada.**
- **(c) Rebajar el CA y no acreditar la cláusula.** Deja UATP-07 incompleta; debe decidirlo el PO,
  no el implementador.

**Recomendación (a) + decisión del PO sobre la cláusula literal.** Si el PO exige la letra, la
historia queda bloqueada: no hay tag publicado que cumpla ambos lados. **Consecuencia:** A6
registra V-01 (identidad de C), V-02 (ausencia en T0), V-03 (T1 arranca y conserva el estado) y
R-03 (C abre y reanuda); la cláusula literal se marca `NOT RUN motivo=tag_anterior_sin_lector_ni_restore`
hasta que el PO decida. **Afecta a:** alcance de UATP-07 y al texto del issue #1145.

### D-4 — ¿Dónde viven `A6/resultado.md` y `A6/evidencia/resultado.txt`?

**Pregunta.** La épica los cita como evidencias del piloto, pero no existen. ¿Se guardan en el repo
o fuera?

**Opciones.**

- **(a) En el repo, versionados y saneados (recomendada):**
  `docs/uat/A6/resultado.md` y `docs/uat/A6/evidencia/resultado.txt`, enlazados desde #1144, #1145,
  #1141 y esta spec. La evidencia completa y el entorno privado pueden quedar fuera; la copia del
  repo no lleva secretos, rutas absolutas, IPs ni nombres de host.
- **(b) Solo adjuntos al issue.** Se pierde la revisión por diff y el enlace estable; el issue se
  cierra sin evidencia versionada.
- **(c) Solo fuera del repo (carpeta privada del piloto).** No es reproducible por otro mantenedor
  y la épica quedaría con enlaces muertos.

**Recomendación (a).** **Consecuencia:** dos ficheros nuevos (y, si hace falta, un `README.md` que
fije la convención A-N); el runbook §7. **Afecta a:** entregables de la implementación y al cierre
de #1144/#1145.

### D-5 — «Diagnóstico persistente por intento»: ¿qué se guarda y dónde?

**Pregunta.** `ops-restaurar.json` se sobrescribe. Si el primer intento falla y el segundo también,
solo se conserva el último. ¿Cómo se identifica y conserva cada intento sin secretos?

**Opciones.**

- **(a) Id de intento + comprobación en el estado actual + registro acotado (recomendada).**
  - `ops-restaurar.json` gana `intento` (16 hex aleatorios), `comprobacion` (código cerrado o
    `null`) y `copia_version` (objeto de D-2 o `null`). El lector actual ignora claves
    desconocidas y no pinta cadenas libres.
  - Nuevo `BACKUP_STATUS_DIR/ops-restaurar-intentos.jsonl`: una línea JSON por intento terminado
    (`hecha`/`fallida`), con los mismos códigos e `intento`; máximo 20 líneas (las más recientes),
    `0644`, escritura atómica, sin rutas, hashes ni secretos. No lo lee la app en esta historia.
- **(b) Solo añadir `intento` al fichero actual.** Identifica el último, pero el anterior se pierde;
  no cumple «el intento fallido conserva la evidencia».
- **(c) Un fichero por intento (`ops-restaurar-<intento>.json`).** Crecimiento sin cota y limpieza
  frágil; más superficie y más ficheros que retener. **Descartada.**

**Recomendación (a).** **Consecuencia:** enmienda de FR-24 de BL-OPS2 (tres claves aditivas y un
fichero de auditoría), tests T-06-03/T-06-04, sin migración. **Afecta a:**
`scripts/restaurar_datos.sh`, `tests/test_restaurar_produccion.py`,
`docs/design/especificacion-BL-OPS2.md`.

### D-6 — ¿Se enmienda FR-17(d)? (tabla `issues`)

**Pregunta.** UATP-06 pide que una copia con **tabla ausente** se rechace antes de reemplazar. El
preflight solo exige cuatro tablas y `issues` se queda fuera. ¿Se amplía?

**Hechos.** Un dump sin `series` se rechaza en el preflight con `copia_no_valida`
(`:325-327`). Un dump sin `issues` puede pasar el preflight; si además los `files` apuntan a issues
inexistentes, falla en `verificar_base_nueva` con `verificacion_fallida`, **después** de
`createdb zascarr_restaurando` y de cargar (eventos de contenedor); si no hay filas que lo delaten,
podría incluso completar el flujo con un catálogo incompleto.

**Opciones.**

- **(a) Enmienda mínima de FR-17(d) (recomendada).** Añadir `issues` a la lista explícita de tablas
  del preflight (`alembic_version`, `series`, `issues`, `files`, `wishlist`). Es una línea en el
  bucle de `:325-327` y una fila en FR-17(d) y AC-34 de BL-OPS2. Un dump válido siempre tiene `issues`
  (existe desde la migración `0001`): no rompe copias buenas, solo rechaza antes las corruptas.
  N-03b lo prueba con cero eventos.
- **(b) No enmendar.** La matriz cumple con `series` (N-03a) y el resto de tablas queda como límite
  aceptado; N-03b se marca `NOT RUN` y el cero-eventos no cubre `issues`.
- **(c) Validar el esquema completo de tablas antes de Docker.** Más fuerte, pero exige mantener una
  lista de tablas y versiones que envejece con cada migración; el recuento genérico ya lo cubre en
  la base nueva. **No recomendada para esta historia.**

**Recomendación (a).** **Consecuencia:** un cambio acotado y probado; FR-17(d) se enmienda en
BL-OPS2; no se añade código de error (`copia_no_valida` + `comprobacion=tablas_dump`). **Afecta a:**
`scripts/restaurar_datos.sh`, `docs/design/especificacion-BL-OPS2.md`, tests de producción y
aislados. **Si el PO elige (b)**, N-03b queda NOT RUN y la spec no se declara completa.

### 3.1 Resumen de decisiones

| ID | Decisión | Recomendación | Bloquea |
|---|---|---|---|
| D-1 | Copia de archivos: manual o herramienta | Manual documentada y verificada | Alcance de UATP-07 |
| D-2 | Semántica y fuente de `version_de_la_copia` | Tupla declarativa `{head, build_sha, app_version, alembic}`; nunca bloquea | AC-07-08, A6 V-01 |
| D-3 | Tags T0/T1/C y cláusula «tag anterior» | Tres referencias; cláusula literal al PO | AC-07-09, A6 V-02/V-03 |
| D-4 | Ubicación de A6 | `docs/uat/A6/…` versionado y saneado | Prueba de cierre |
| D-5 | Diagnóstico por intento | `intento` + `comprobacion` + `copia_version` + `.jsonl` acotado | AC-06-06 |
| D-6 | FR-17(d): añadir `issues` | Sí, enmienda mínima | N-03b, cero-eventos |

---

## 4. Contrato de datos propuesto (aditivo, sin migración)

> **Propuesta, no aprobada.** Nada de esto está implementado. Respeta las invariantes de BL-OPS1/2:
> los ficheros de estado los escribe **solo** el host; la app solo lee; nada de rutas, hashes,
> secretos ni texto libre; escritura atómica; el lector tolera claves desconocidas y tipos erróneos.

### 4.1 Manifiesto de copia (`MANIFIESTO-backup_<TS>.json`)

Se conserva `schema: 1` y todos los campos actuales. Se añade **una** clave opcional:

```json
"version_de_la_copia": {
  "head": "<40 hex minúsculas o null>",
  "build_sha": "<40 hex minúsculas o null>",
  "app_version": "1.15.1",
  "alembic": "0052"
}
```

Reglas:

- `head` sale de `git rev-parse HEAD`; `alembic` de `alembic_version`; `app_version` de
  `[project].version` de `pyproject.toml`; `build_sha` de `docker compose exec -T zascarr printenv
  BUILD_SHA` con `timeout 5` si está disponible.
- Cada valor se valida con su regex; si no cumple o la lectura falla, se escribe `null` (nunca se
  aborta la copia por no poder declarar la versión).
- Si no hay `.git` (copia sin repo), `head` y `build_sha` pueden ser `null`; `alembic` y
  `app_version` siguen siendo legibles.
- **Compatibilidad:** `restaurar_datos.sh` actual no lee la clave; las copias viejas no la tienen.
  No se reescriben manifiestos antiguos. Los consumidores nuevos deben tratar ausencia/`null` como
  «no consta».
- **Duplicidad controlada:** `head` y `alembic` deben coincidir con
  `codigo_desplegado_sha_completo` y `alembic` del mismo manifiesto; un test lo exige. No se
  eliminan los campos planos para no romper a los lectores actuales.

### 4.2 `ops-restaurar.json`

Se conserva `schema: 1` y todos los campos actuales. Se añaden tres claves:

| Campo | Tipo | Regla |
|---|---|---|
| `intento` | string o `null` | 16 hex minúsculas, generado una vez por ejecución (`od -An -N8 -tx1 /dev/urandom`); identifica el intento. |
| `comprobacion` | string o `null` | Código de §4.4 de la comprobación que falló; `null` si el fallo no es de contenido o el intento terminó bien. |
| `copia_version` | objeto o `null` | Copia validada de `version_de_la_copia` del manifiesto; `null` si no consta. Solo las cuatro claves y sus regex; nada de texto libre. |

- `recuentos` sigue siendo `null` salvo `hecha`; `base_en_su_sitio` conserva su semántica.
- Un `die` del preflight escribe `fallida`, `error` cerrado, `comprobacion` y
  `base_en_su_sitio=true`; no escribe `recuentos`.
- El lector actual (`ops_host.resolver_restauracion`) ignora las claves nuevas: no hay cambio de UI
  en esta historia.

### 4.3 `ops-restaurar-intentos.jsonl`

Un fichero de auditoría **solo del host**, una línea JSON por intento terminado:

```json
{"schema":1,"intento":"a1b2c3d4e5f60718","copia":"backup-20261121_040000","copia_epoch":1763704800,
 "copia_version":{"head":"…","build_sha":"…","app_version":"1.15.1","alembic":"0052"},
 "inicio_epoch":1763704900,"fin_epoch":1763704912,"fase":"verificando","resultado":"fallida",
 "error":"copia_no_valida","comprobacion":"tablas_dump","base_en_su_sitio":true}
```

- Se escribe **una vez** por intento terminal (`hecha` o `fallida`), con `printf` + `>>`; si no se
  puede, no falla la restauración.
- Se conservan las **20** líneas más recientes: reescritura atómica (`temporal` + `mv`), `0644`.
- Solo códigos, números, booleanos, UUID/hex y los cuatro valores de versión; nunca rutas, nombres
  de fichero, hashes de archivos, salida de comandos, contraseñas ni valores de `runtime_settings`.
- No lo lee la app en UATP-06/07. UATP-08 podrá leerlo si el PO lo pide; su lector deberá tratar
  códigos desconocidos como «no consta».

### 4.4 Códigos de `comprobacion` (lista cerrada)

| Código | Comprobación | `error` asociado |
|---|---|---|
| `existencia_copia` | El dump existe y no está vacío | `copia_no_encontrada` |
| `manifiesto` | Manifiesto existe, es JSON y `schema` entendido | `copia_no_valida` |
| `sha256_copia` | SHA-256 del dump contra el manifiesto (y sidecar) | `copia_no_valida` |
| `bytes_copia` | Tamaño del dump contra el manifiesto | `copia_no_valida` |
| `codigo_manifest` | El manifiesto acredita el commit/HEAD actual | `copia_no_valida` |
| `gzip_cabecera` | `gzip -t` | `copia_no_valida` |
| `cabecera_pg_dump` | Cabecera de `pg_dump` | `copia_no_valida` |
| `tablas_dump` | Tablas explícitas del preflight y `version_num` | `copia_no_valida` |
| `alembic_revision` | Revisión del manifiesto/dump/BD actual | `revision_distinta` |

- Un código nuevo exige fila aquí y prueba de que se escribe; uno desconocido no rompe la UI (no se
  pinta en esta historia).
- `comprobacion` **no** sustituye a `error`: `error` es la causa de cara a la persona;
  `comprobacion` es el detalle cerrado de qué comprobación falló.
- **No se añade ningún `error` nuevo.** `copia_no_valida` sigue cubriendo SHA/gzip/tabla.

### 4.5 Compatibilidad y no-regresión

- `schema` sigue en `1` en manifiesto y estado; los campos son aditivos.
- FR-24 de BL-OPS2 se enmienda para listar las tres claves y el `.jsonl`; FR-16/FR-28
  (`copias.json`) **no** cambian.
- `tests/test_copias_json.py`, `tests/test_restauracion_estado.py`, `tests/test_ops_paridad.py` y
  las pruebas de BL-OPS1/2 deben seguir pasando sin cambios de aserción.
- Sin migración de Alembic, sin dependencia nueva, sin JS nuevo, sin escritura en la biblioteca.

---

## 5. UATP-06 — Matriz negativa y estado intacto

### 5.1 Preparación del ensayo

Entorno **E-A6**: instalación aislada de la candidata C (proyecto Compose distinto, puerto distinto,
volúmenes distintos), con `auth_mode=password` (el flujo de producción lo exige) y una contraseña de
prueba que no se escribe en A6. La ruta de restauración es la de producción, con las variables
documentadas en `deploy/ops/restaurar-produccion.sh` y, si el proyecto no se llama `zascarr`, con
`ZASCARR_PRUEBAS=1` + `PROYECTO_PRODUCCION=<nombre>` (FR-17.f de BL-OPS2). La instalación real no se
toca.

Datos testigo (semilla reproducible, §7.1):

- 1 serie, 1 número y 1 archivo testigo `ARCHIVO-A` (CBZ multipágina) con UUID fijos;
- al menos otra serie/número/archivo para que los recuentos no sean triviales;
- 1 fila `reading_progress` con `file_id` del testigo, `current_page=P` (P intermedia), estado
  `reading`, escrita por el lector real (no por SQL directo);
- una copia válida **B0** creada por `backup.sh` y ofrecida en «Copias de seguridad». Si E-A6 no
  tiene disco offsite, `backup.sh` escribe la copia local, el manifiesto y `copias.json` y después
  termina con error `offsite_mount_missing` (estado `failed`/`offsite=false`). El runbook ejecuta
  `backup.sh || true` y comprueba que B0 y su manifiesto existen; A6 registra el motivo y no invalida
  B0. La copia local no se considera válida si no existe o no pasa `gzip -t`.
- para que una copia dañada aparezca en la lista sin editar JSON a mano, se **duplica** B0 con otro
  `<TS>`, se muta el duplicado y se regenera `copias.json` con el mismo escritor del producto
  (`escribir_copias_json`, `scripts/_comun.sh:367`). **B0 no se muta**: sigue siendo la copia válida
  que debe sobrevivir a todos los intentos.

Huella testigo de UATP-06: UUID de serie/número/archivo, `files.file_size_bytes`,
`files.file_mtime_ns`, `files.sha256_hash`, `reading_progress.current_page` y
`reading_progress.file_id`. No se escriben rutas ni títulos en A6.

### 5.2 Matriz (todas las filas son obligatorias)

| ID | Mutación de la copia | Qué debe fallar | `error` | `comprobacion` | `base_en_su_sitio` | Eventos de contenedor | Texto de la persona |
|---|---|---|---|---|---|---|---|
| **N-01** | Manifiesto con `sha256` alterado y dump intacto (equivale a un dump dañado con manifiesto viejo) | SHA-256 antes de gzip | `copia_no_valida` | `sha256_copia` | `true` | 0 | «Esa copia está dañada, así que no se ha usado. Elige otra.» |
| **N-02** | `.sql.gz` truncado a la mitad y manifiesto con `sha256`/`bytes` recalculados y sidecar `.sha256` recalculado o ausente (para que el SHA pase y falle gzip) | `gzip -t` | `copia_no_valida` | `gzip_cabecera` | `true` | 0 | ídem |
| **N-03a** | Dump sin el bloque `COPY public.series`, recomprimido, manifiesto y sidecar recalculados | Tabla explícita ausente | `copia_no_valida` | `tablas_dump` | `true` | 0 | ídem |
| **N-03b** | Dump sin el bloque `COPY public.issues`, recomprimido, manifiesto y sidecar recalculados | Tabla explícita ausente (**requiere D-6(a)**) | `copia_no_valida` | `tablas_dump` | `true` | 0 | ídem |
| **N-04** | Copia válida B0 (control positivo) | Nada; debe completar | `null` | `null` | `true` | Los del flujo aprobado | «Copia del … restaurada: N series, N números y N archivos anotados…» |

Reglas de la matriz:

- **N-02 y N-03 se preparan en laboratorio** recalculando el manifiesto para aislar la comprobación
  que se quiere probar. En producción, la corrupción normal suele fallar antes por SHA; eso no quita
  valor a la fila: prueba que, si el SHA coincide, gzip/tabla también rechazan.
- Cada fila se ejecuta **desde el mismo camino de producción** (`restaurar_datos.sh --produccion
  --copia <TS>` o la acción «Restaurar…» de la interfaz). No se acepta un `--dump` de ensayo como
  evidencia de UATP-06.
- Al menos **N-01 se ejecuta desde la interfaz** para acreditar el resultado y la acción de la
  persona; las demás pueden ejecutarse por el mismo script con la evidencia de estado.
- Después de cada fila, B0 debe seguir existiendo, con el mismo SHA-256, y seguir ofrecida en
  `copias.json`. El intento fallido no borra la copia buena anterior.
- N-04 se ejecuta **después** de las negativas, con B0 (o una copia buena recreada), y completa el
  flujo: la historia no se acredita si el positivo no funciona en la misma candidata.

### 5.3 Instantánea antes/después (el «estado intacto»)

Antes de cada fila y después de ella se toma la misma instantánea canónica (helper §7.1). Campos y
comparación:

| Grupo | Qué se anota | Comparación exigida |
|---|---|---|
| Código | `git rev-parse HEAD`, árbol limpio (sí/no) | Idénticos. |
| BD | `alembic_version`; `count(*)` de `series`, `issues`, `files`, `reading_progress`, `runtime_settings`, `library_roots` | Idénticos. |
| Testigo | UUID y campos de §5.1 | Idénticos byte a byte. |
| Salud | JSON de `/api/health`: `status`, `version`, `checks`, `warnings`, `seguridad` | Idéntico (misma respuesta, salvo campos volátiles declarados; ver nota). |
| Copias | SHA-256 de B0, de su manifiesto y de `status.json` | Idénticos. |
| Estado | `copias.json`: B0 presente y `verificada=true`; `ops-restaurar.json` y `.jsonl` | `copias.json` no pierde B0; el estado **cambia** solo por el intento (es esperado). |
| Archivos | SHA-256 e `mtime` del CBZ testigo | Idénticos. |
| Contenedores | `docker inspect` de `zascarr` y `postgres`: `State.Status`, `RestartCount`, `StartedAt` | Idénticos. |

Nota sobre `/api/health`: `warnings` puede incluir el aviso de backup por la edad de la última copia
o el de versión; si cambia por el reloj, se comparan **solo** `status`, `version` y cada
`checks.*`, y se documenta el motivo en A6. Cualquier cambio de `checks.database` a distinto de
`ok` es FAIL.

### 5.4 Cero eventos de contenedor

Se exige **cero** eventos de contenedor durante N-01…N-03b, además de cero comandos de escritura a
la BD:

- **Docker falso (tests):** `FAKE_EVENTOS` vacío tras la ejecución, y `FAKE_LOG` con una sola
  entrada, `docker compose … config`; ninguna de `exec`, `stop`, `up`, `run`, `create`, `start`,
  `restart`, `rm`, `createdb`, `dropdb`, `pg_dump`, `psql` con escritura. La prueba debe fallar si
  aparece cualquiera.
- **A6 real:** un `docker events` en segundo plano, con filtros de `create`, `start`, `stop`,
  `kill`, `die`, `destroy`, `exec_create` y `exec_start`, sobre el proyecto E-A6; al terminar,
  **0 líneas**. `docker compose config` no emite eventos; se permite.
- **BD:** ninguna sentencia que escriba (`INSERT/UPDATE/DELETE/ALTER/CREATE/DROP`); el preflight
  solo lee. En el ensayo real, `pg_stat_database.xact_commit` puede subir por la lectura/health;
  no se usa como prueba de escritura.
- **Prohibido reordenar el script** para leer la BD actual antes de las comprobaciones de contenido:
  eso introduciría un `exec` antes del rechazo y rompería el criterio.

### 5.5 Resultado y acción para la persona

- La causa visible es la de `CAUSAS_RESTAURAR["copia_no_valida"]`: «Esa copia está dañada, así que
  no se ha usado. **Elige otra.**» (`src/zascarr/services/ops_host.py:466`). La lista de copias está
  en la misma pantalla de Estado; no hace falta una ruta nueva.
- `base_en_su_sitio` es `true` y **no** se muestra el aviso de «podría no responder» (ese aviso es
  solo para `false`).
- El intento debe quedar identificado en `ops-restaurar.json` y en `ops-restaurar-intentos.jsonl`
  con `intento`, `copia`, `error`, `comprobacion`, `copia_version` (si consta) y épocas. Sin
  secretos: el estado no lleva rutas, hashes ni credenciales (FR-24).
- Un intento fallido **no** impide el siguiente: el cerrojo se libera y otra copia puede
  seleccionarse; `copias.json` no se reescribe por el fallo.

### 5.6 Criterios de aceptación (UATP-06)

- **AC-06-01.** Dada una copia con SHA incorrecto, gzip truncado o tabla explícita ausente, CUANDO se
  intenta restaurar por el camino de producción, ENTONCES se rechaza **antes** de crear, parar o
  ejecutar ningún contenedor y antes de tocar la base viva, con `error=copia_no_valida`,
  `comprobacion` de §5.2 y `base_en_su_sitio=true`.
- **AC-06-02.** ENTONCES no hay eventos de contenedor ni sentencias de escritura en la BD durante el
  intento; solo `docker compose config` puede ejecutarse.
- **AC-06-03.** ENTONCES la instantánea de §5.3 es idéntica antes y después: filas testigo, revisión
  de Alembic, salud, copia válida B0 y CBZ testigo; `copias.json` sigue ofreciendo B0.
- **AC-06-04.** ENTONCES la persona ve la causa y la acción «Elige otra» y no ve el aviso de base
  fuera de su sitio.
- **AC-06-05.** ENTONCES el fallo no borra ni altera B0 ni su manifiesto, y un intento posterior con
  B0 completa el flujo.
- **AC-06-06.** ENTONCES cada intento fallido queda identificado y persistido en
  `ops-restaurar.json` y en `ops-restaurar-intentos.jsonl` (máximo 20), con códigos cerrados y sin
  secretos; dos intentos distintos tienen `intento` distinto y el anterior no se pierde.
- **AC-06-07.** ENTONCES el control positivo N-04 restaura catálogo con los recuentos esperados y
  `ops-restaurar.json` dice `hecha`, `base_en_su_sitio=true` y `recuentos` correctos.
- **AC-06-08.** ENTONCES A6 registra N-01…N-04, la instantánea y los comandos con PASS/FAIL/NOT RUN
  (§7), enlazado desde #1144.
- **AC-06-09.** ENTONCES no se ha añadido migración, dependencia ni escritura en la biblioteca, y las
  pruebas de BL-OPS1/2 siguen pasando.

---

## 6. UATP-07 — Copia de archivos manual y reapertura en la página guardada

### 6.1 Decisión y alcance de la copia

Se adopta D-1(a): **paso manual documentado**. El procedimiento copia **solo las raíces de
biblioteca** declaradas en la instalación. Quedan fuera: portadas cacheadas (`covers/`), `.env`,
credenciales, configuración del host, el volumen de PostgreSQL, los dumps de copia y cualquier
archivo fuera de una raíz de biblioteca. La copia se hace en el host, como root o con permisos de
lectura/escritura suficientes, y **nunca** desde el contenedor de la app (que es de solo lectura).

### 6.2 Raíces: cuáles y cómo se identifican

Fuente de verdad en la instalación:

- `library_roots` de la BD (filas `enabled`): `path` (ruta del contenedor) y `host_path` (ruta del
  host, solo para mostrar) — [`src/zascarr/models/__init__.py:811-846`](../../src/zascarr/models/__init__.py:811).
- `.env` / Compose: `HOST_LIBRARY_DIR` (raíz por defecto) y `HOST_LIBRARY_ROOTS` (lista paralela a
  `LIBRARY_ROOTS`) — [`src/zascarr/config.py:202-214`](../../src/zascarr/config.py:202),
  [`.env.example:63-72`](../../.env.example:63), [`docker-compose.yml:143-148`](../../docker-compose.yml:143).

Regla del runbook:

1. Listar las raíces habilitadas con `path`, `host_path` y `is_default`.
2. Para cada una: si `host_path` está vacío y es la raíz por defecto, usar `HOST_LIBRARY_DIR`; si
   sigue vacío, **abortar** con un mensaje claro: no se inventa una ruta. El operador debe declararla
   en Ajustes antes del ensayo.
3. Rechazar raíces anidadas entre sí (`A` dentro de `B`), raíces que sean `/`, la home del usuario o
   un punto de montaje de Docker/VPN, y raíces que no estén montadas (`mountpoint -q`) o no sean
   legibles.
4. Etiquetar cada raíz en A6 como `R1`, `R2`… (sin ruta absoluta); la ruta real solo aparece en la
   consola privada del operador.

### 6.3 Destino vacío y distinto

- El destino debe estar **vacío**: `find "$DEST" -mindepth 1 -maxdepth 1 -print -quit` sin salida.
  Si no lo está, **abortar**; no se usa `--delete`.
- Debe estar en un **sistema de archivos distinto** de cada origen (`stat -c %d` distinto), montado y
  escribible, y no puede estar dentro de un origen ni contenerlo.
- Debe conservar **mtime con nanosegundos** (ext4/btrfs/XFS). En exFAT/NTFS la precisión puede
  perderse: se registra como FAIL de F-02, no como «aceptable».
- Debe haber espacio suficiente para el inventario completo más un 10 % (se mide con `du -sb` y
  `df -B1`).
- El destino se monta en el entorno aislado en la **misma ruta de contenedor** que tenía la
  instalación (por ejemplo, `/media/library`), porque `files.file_path` guarda rutas del
  contenedor. La ruta del host puede cambiar; la del contenedor, no.

### 6.4 Orden del ensayo

El orden recomendado es **copiar archivos → restaurar catálogo → arrancar/verificar**, con la app
parada durante la copia y la restauración:

1. **Quiescencia.** Parar el contenedor de la app de E-A6 (`docker compose stop zascarr`), dejar
   PostgreSQL en marcha. No hay importador, lector ni escritura de la app durante la copia.
2. **Copia de la BD.** Ejecutar `backup.sh` (o la unidad equivalente) para obtener B0; verifica
   gzip/cabecera/tablas y escribe el manifiesto con `version_de_la_copia`. B0 es la copia que se
   restaurará.
3. **Copia de archivos.** `rsync -aHAX --numeric-ids` (o `-aH` si el FS no soporta ACL/xattr) desde
   cada raíz a su destino vacío, **sin `--delete`**, sin seguir enlaces simbólicos (`-l`), con
   `--info=progress2` y registro en la consola privada. Los enlaces simbólicos se copian como
   enlaces; los hardlinks se preservan con `-H`.
4. **Verificación de la copia.** Inventario y testigo (§6.5) **antes** de arrancar nada.
5. **Restaurar catálogo.** Con la app parada o con el flujo de producción de la candidata
   (`restaurar_datos.sh --produccion --copia <TS>`), restaurar B0 en el entorno aislado; el script
   para la app, comprueba y arranca. La biblioteca destino ya está completa.
6. **Arrancar y verificar** la ficha, el lector y la página guardada (§6.7); después, el estado de
   salud.

Por qué este orden: el catálogo apunta a rutas que deben existir al arrancar; si se restaura antes de
copiar, el importador/auditoría pueden ver la biblioteca vacía y marcar «no disponible» o actuar
sobre un desfase (R-7 de BL-OPS2). Copiar primero evita ese estado intermedio. La app está parada
durante los pasos que escriben.

### 6.5 Mtime, inventario y sha256 testigo

- **Mtime.** Para cada raíz, antes y después:
  `find "$RAIZ" -type f -printf '%P\0%T@\0%s\0' | sort -z | sha256sum`. El hash debe ser idéntico.
  Además, `stat -c '%y'` del CBZ testigo debe ser idéntico con nanosegundos.
- **Inventario.** Número de ficheros y bytes totales por raíz, antes y después; deben coincidir.
  No se escribe la lista de rutas en A6 (solo el hash y los recuentos).
- **sha256 testigo (obligatorio).** SHA-256 del CBZ testigo (y de la página P extraída, §6.7) antes
  y después. Es la «huella testigo» del issue. Un cambio es FAIL.
- **sha256 de todos los archivos (opcional, costoso).** Solo si la biblioteca es pequeña o el
  operador acepta el tiempo: `find … -exec sha256sum` con hash final. Si no se ejecuta, se marca
  `NOT RUN motivo=coste`; no invalida el ensayo, pero el A6 debe decirlo. El inventario
  mtime+tamaño es el nivel obligatorio.
- **No** se usa el hash de `files.sha256_hash` como sustituto del testigo del disco: se comparan
  ambos y deben coincidir.

### 6.6 Catálogo restaurado

Después de restaurar B0 en E-A6:

- `alembic_version` = la del manifiesto y la que espera la candidata;
- recuentos de `series`, `issues`, `files`, `reading_progress`, `runtime_settings` y
  `library_roots` iguales a los de B0;
- vínculos `files.issue_id → issues.id`, `issues.series_id → series.id` y `files.file_path` sin
  huérfanos;
- `files.sha256_hash` del testigo = hash del archivo copiado;
- `reading_progress` del testigo conserva `file_id`, `current_page=P`, `status` y `last_read_at`
  (si estaba).

El script ya comprueba recuentos genéricos y huérfanos (`restaurar_datos.sh:482-505`); A6 añade la
comprobación del testigo y de la página.

### 6.7 Reapertura en la página guardada (comprobaciones exactas)

Antes del backup (con la app de E-A6 en marcha):

1. Crear un CBZ multipágina determinista `ARCHIVO-A` con ≥ 5 páginas (fixture §7.1).
2. Registrarlo en el catálogo (serie/número/archivo) con el camino que tendrá en el contenedor.
3. Abrir el lector en la candidata C, avanzar a la página **P = 3** (o una intermedia distinta de 1 y
   del total) y esperar el `POST /ui/leer/<file_id>/progreso` con `pagina=3` → 204
   ([`src/zascarr/web/lector.py:181-188`](../../src/zascarr/web/lector.py:181)).
4. Registrar en A6: `file_id`, `issue_id`, `P`, `total_paginas`, `sha256` del CBZ, `sha256` de la
   página P y `reading_progress.current_page`.

Comprobaciones antes y **después** de la recuperación:

| ID | Comprobación | Cómo |
|---|---|---|
| R-01 | La ficha ofrece continuar en la página guardada | `GET /ui/series/<series_id>/numero/<issue_id>` contiene `Continuar (pág. 3)` ([`issue_detail.html:22`](../../src/zascarr/web/templates/issue_detail.html:22)). |
| R-02 | El lector abre en esa página | `GET /ui/leer/<file_id>` contiene `data-pagina="3"`, `data-total="<N>"` y `src="/ui/leer/<file_id>/pagina/3"` ([`lector.html:7,20,78`](../../src/zascarr/web/templates/lector.html:7)). |
| R-03 | La página servida es del archivo correcto | `GET /ui/leer/<file_id>/pagina/3` → 200, tipo imagen, y `sha256` de los bytes = testigo de la página P. |
| R-04 | El archivo es el restaurado | `files.file_path` del `file_id` existe; `sha256sum` del archivo = `files.sha256_hash` = testigo del CBZ. |
| R-05 | Relaciones y progreso coinciden | `files.issue_id`, `issues.id`, `reading_progress` (mismo `file_id`, `current_page=3`, estado) sin huérfanos. |

Si R-01/R-02/R-03 fallan, UATP-07 **no** se acredita aunque el catálogo tenga los recuentos.

### 6.8 Versión declarada (la que abre el archivo)

A6 declara, para T1 y C:

| Campo | Fuente | Regla |
|---|---|---|
| `tag` | `git tag -a` | T1 = `uat-base-<fecha>`, C = `uat-candidata-<fecha>`; anotados, no ligeros. |
| `tag_commit` | `git rev-parse <tag>^{commit}` | Debe ser el SHA de la imagen que se ejecuta. |
| `head` | `git rev-parse HEAD` | Igual a `tag_commit`. |
| `build_sha` | `docker compose exec -T zascarr printenv BUILD_SHA` | 40 hex; igual a `head`; si está vacío, **FAIL de identidad**, no se puede cerrar. |
| `app_version` | `pyproject.toml` y `/api/health.version` | Deben coincidir; no identifica por sí sola. |
| `alembic` | `alembic_version` de la BD restaurada | Igual al manifiesto y a la cabeza de la candidata. |
| `image_id` | `docker image inspect --format '{{.Id}}'` | Se registra para soporte; no es identidad de código. |

Regla de redacción: **nunca** se declara la copia solo como «1.15.1». Si falta `build_sha`, se dice
«identidad de la imagen no consta» y V-01 es FAIL (no PASS parcial).

### 6.9 La cláusula del tag anterior

Ver D-3. A6 registra:

- **V-01** identidad de C (tupla de §6.8, igualdad tag/HEAD/BUILD_SHA);
- **V-02** `v1.15.1` no tiene lector ni restauración: `git ls-tree -r v1.15.1 --name-only` no
  devuelve `src/zascarr/web/lector.py` ni `src/zascarr/services/ops_host.py`, y su Alembic llega a
  `0016`; se acredita la **ausencia** (PASS como comprobación de ausencia), no la apertura;
- **V-03** T1 arranca con el catálogo restaurado y conserva el estado (recuentos, testigo,
  `reading_progress`). Condición: T1 y C comparten revisión de Alembic (en esta historia no hay
  migración, así que deberían compartirla). Si no la comparten, T1 no puede arrancar contra B0:
  V-03 se marca `NOT RUN motivo=alembic_distinta` y UATP-07 queda bloqueada, sin inventar un
  arranque;
- **R-03** C abre y reanuda en P (la prueba funcional de UATP-07).

La frase literal «si el tag de partida carece del lector…» se marca
`NOT RUN motivo=tag_anterior_sin_lector_ni_restore` hasta que el PO decida D-3. No se inventa un
tag ni se manipula la base para simularlo.

### 6.10 Criterios de aceptación (UATP-07)

- **AC-07-01.** CUANDO se prepara la recuperación, ENTONCES existe un runbook que identifica las
  raíces de biblioteca, exige destino vacío en otro sistema de archivos y copia solo esas raíces,
  sin tocar portadas, `.env`, configuración ni PostgreSQL.
- **AC-07-02.** ENTONCES la copia preserva mtime (nanosegundos) e inventario (ficheros y bytes) de
  cada raíz; la comprobación se hace antes y después y queda en A6.
- **AC-07-03.** ENTONCES el sha256 testigo del CBZ y de la página P coincide antes y después; el
  inventario completo opcional se marca ejecutado o NOT RUN con motivo.
- **AC-07-04.** ENTONCES se restaura el catálogo B0 en el entorno aislado y los recuentos, la
  revisión de Alembic y los vínculos coinciden con B0, sin huérfanos.
- **AC-07-05.** ENTONCES la ficha ofrece «Continuar (pág. P)» y el lector abre en P del `file_id`
  testigo.
- **AC-07-06.** ENTONCES la página P servida tiene el mismo sha256 que antes de la copia, y
  `files.sha256_hash` coincide con el archivo restaurado.
- **AC-07-07.** ENTONCES las relaciones y el progreso (`reading_progress`) coinciden con los
  registrados antes del backup.
- **AC-07-08.** ENTONCES A6 declara `version_de_la_copia` con BUILD_SHA + HEAD + app_version + Alembic
  de T1 y C; no se acepta «1.15.1» como única versión; si falta un dato, se declara «no consta».
- **AC-07-09.** ENTONCES se cumple una de estas dos: (i) el PO aprueba D-3(a) y A6 acredita V-02,
  V-03 y R-03; o (ii) el PO exige la letra del CA y la historia queda bloqueada y documentada, sin
  declarar cumplida UATP-07.
- **AC-07-10.** ENTONCES A6 enlaza `A6/resultado.md` y `A6/evidencia/resultado.txt` desde #1145, con
  PASS/FAIL/NOT RUN y sin secretos.
- **AC-07-11.** ENTONCES no hay migración, dependencia, JS ni cambio de UI, y la biblioteca no se
  modifica desde ZascArr.

---

## 7. Evidencia A6

### 7.1 Ubicación y artefactos

| Ruta | Contenido | Versionado |
|---|---|---|
| `docs/uat/A6/resultado.md` | Resumen del ensayo, tabla de comprobaciones, decisión D-3, versión, resultados | Sí |
| `docs/uat/A6/evidencia/resultado.txt` | Transcripción canónica: `CHECK` + comandos + salida saneada | Sí |
| `docs/uat/A6/fixture/` | Semilla reproducible: `sembrar.sql`/`sembrar.sh` con UUID fijos y `crear_cbz.py` (stdlib) que genera `ARCHIVO-A` determinista con P páginas; opcional si ya existe un fixture equivalente | Sí |
| `docs/uat/README.md` | Convención A-N, redacción y estados (opcional) | Sí |

Los dos primeros son **obligatorios**. La épica #1141 enlaza `A6/resultado.md` y
`A6/evidencia/resultado.txt`; la spec fija que su raíz es `docs/uat/`. Si el PO prefiere evidencia
privada, el repo conserva la copia saneada y el enlace del issue debe apuntar a ella; no se acepta
un enlace muerto.

### 7.2 Formato de `A6/resultado.md`

Encabezado obligatorio (tabla):

| Campo | Regla |
|---|---|
| Historias | UATP-06 #1144, UATP-07 #1145, épica #1141 |
| Fecha/hora | ISO 8601 con zona (`2026-11-21T20:30:00+01:00`), no «hoy» |
| Entorno | Alias (`E-A6`, `P-01`); sin hostname, IP, usuario ni ruta absoluta |
| Candidata | Tag C, `tag_commit`, `build_sha`, `app_version`, `alembic`, `image_id` |
| Baseline | Tag T1 y sus mismos campos |
| Tag antiguo | T0 `v1.15.1`; ausencia verificada |
| Decisión D-3 | Aprobada por el PO: sí/no; si no, estado del CA |
| Resultado global | `PASS`, `FAIL` o `NOT RUN` con la regla de §7.6 |

Cuerpo:

1. **Resumen** de 3–6 frases: qué se ejecutó, qué pasó y qué queda pendiente.
2. **Tabla de comprobaciones** con columnas: `ID`, `Qué comprueba`, `Esperado`, `Obtenido`,
   `PASS/FAIL/NOT RUN`, `Evidencia` (enlace a la línea de `resultado.txt`). Cada fila referencia un
   `CHECK` de §7.4; no hay filas sin `CHECK`.
3. **Instantánea** antes/después de §5.3: tabla con los grupos y el resultado de la comparación.
4. **Versión** de §6.8: tabla de igualdades.
5. **Copia de archivos**: raíces R1/R2, destino D1 (etiquetas, sin rutas), FS, espacio, inventario y
   testigo.
6. **Reapertura**: file_id, P, total, página y hashes.
7. **Pendientes y bloqueos**: lo `NOT RUN`, con `motivo` cerrado y qué falta.
8. **Enlaces**: #1144, #1145, #1141, esta spec y el PR/commit de la implementación.

### 7.3 Formato de `A6/evidencia/resultado.txt`

Texto plano UTF-8, líneas ≤ 200 caracteres, sin tabuladores. Cabecera:

```
# A6 — Evidencia de recuperación (UATP-06/UATP-07)
# Generado: 2026-11-21T20:30:00+01:00
# Entorno: E-A6 (alias; sin hostname/IP/ruta)
# Candidata: tag=uat-candidata-20261121 tag_commit=<40hex> build_sha=<40hex> app_version=1.15.1 alembic=0052
# Baseline: tag=uat-base-20261121 tag_commit=<40hex> ...
# Tag antiguo: v1.15.1 (sin lector ni restauración)
# Comando general: bash scripts/uat/a6_recuperacion.sh ... (o los comandos de §7.5)
```

Después, **una línea por comprobación** con formato fijo:

```
CHECK <ID> <PASS|FAIL|NOT RUN> [clave=valor ...]
```

Reglas:

- `ID` es el de §7.4. `PASS`/`FAIL`/`NOT RUN` en mayúsculas.
- Valores: solo códigos cerrados, enteros, booleanos, UUID, hashes hex, `tag`, `build_sha`,
  `app_version`, `alembic`, `file_id`, `pagina`, `total`, `sha256_*`. Nada de texto libre.
- `NOT RUN` exige `motivo=<cerrado>`: `sin_entorno`, `sin_tag`, `tag_anterior_sin_lector_ni_restore`,
  `sin_disco_secundario`, `coste`, `no_aplica`, `pendiente_po`.
- Los comandos y su salida van en bloques delimitados:
  ```
  $ <comando exacto>
  <salida saneada>
  ```
  El comando no lleva contraseñas, tokens, `-e` con secretos ni `cat .env`. La salida se redacta con
  `<redactado>` para todo lo que no sea código/número/hash/UUID (ver §7.6).
- El fichero debe poder regenerarse; si se edita a mano, se anota `# edición manual: <motivo>` y no
  cuenta como PASS sin comando.

### 7.4 Catálogo de comprobaciones A6

| ID | Comprobación | Obligatoria |
|---|---|---|
| **V-01** | Identidad de C: `tag_commit == head == build_sha`; `app_version` coincide con pyproject/health; `alembic` coincide con el manifiesto | Sí |
| **V-02** | T0 `v1.15.1` sin lector ni restauración (ausencia verificada; no se intenta abrir) | Sí |
| **V-03** | T1 arranca con el catálogo restaurado y conserva recuentos/testigo/progreso | Sí (D-3(a)) |
| **N-01** | SHA incorrecto → `copia_no_valida`/`sha256_copia`/base `true`/0 eventos | Sí |
| **N-02** | gzip truncado → `copia_no_valida`/`gzip_cabecera`/base `true`/0 eventos | Sí |
| **N-03a** | Falta `series` → `copia_no_valida`/`tablas_dump`/base `true`/0 eventos | Sí |
| **N-03b** | Falta `issues` → ídem (requiere D-6(a)) | Sí si D-6(a); NOT RUN si (b) |
| **N-04** | Control positivo con B0 → `hecha`, recuentos, base `true` | Sí |
| **S-01** | Instantánea §5.3 idéntica antes/después en N-01…N-03 | Sí |
| **S-02** | `copias.json` sigue ofreciendo B0 y su SHA-256 no cambia | Sí |
| **S-03** | Sin eventos de contenedor y sin escrituras a la BD en N-01…N-03 | Sí |
| **D-01** | B0 y su manifiesto intactos después de cada fallo | Sí |
| **F-01** | Raíces identificadas; destino vacío, distinto FS, espacio suficiente | Sí |
| **F-02** | Mtime e inventario idénticos antes/después | Sí |
| **F-03** | sha256 testigo del CBZ y de la página P idéntico | Sí |
| **F-04** | Inventario sha256 completo (opcional) o `NOT RUN motivo=coste` | No (pero se declara) |
| **R-01** | Ficha ofrece «Continuar (pág. P)» | Sí |
| **R-02** | Lector abre en `data-pagina=P` del `file_id` testigo | Sí |
| **R-03** | Página P con sha256 testigo; archivo restaurado con `files.sha256_hash` correcto | Sí |
| **R-04** | Relaciones y `reading_progress` coinciden; sin huérfanos | Sí |
| **R-05** | Recuentos y Alembic del catálogo restaurado coinciden con B0 | Sí |
| **A-01** | `resultado.md` y `resultado.txt` existen, están enlazados y sus timestamps coinciden | Sí |
| **A-02** | Sin secretos: grep de §7.6 sin coincidencias | Sí |
| **A-03** | `ops-restaurar.json` y `.jsonl` de los intentos con `intento`/`comprobacion`/`copia_version` | Sí |
| **A-04** | Toda comprobación obligatoria del catálogo tiene línea `CHECK`; ninguna sin comando | Sí |

### 7.5 Comandos mínimos (runbook)

A6 debe incluir los comandos ejecutados; estos son el mínimo reproducible. `<...>` son variables del
operador; nunca se pegan credenciales.

0. **Identidad y tags**
   ```
   git fetch --tags origin
   git rev-parse HEAD
   git rev-parse <TAG>^{commit}
   git cat-file -t <TAG>                 # debe ser "tag" (anotado)
   git ls-tree -r v1.15.1 --name-only | grep -E 'web/lector.py|services/ops_host.py' || true
   docker compose -p <PROYECTO> exec -T zascarr printenv BUILD_SHA
   docker image inspect <IMAGEN> --format '{{.Id}} {{.Config.Labels}}'
   curl -fsS http://127.0.0.1:<PUERTO>/api/health | jq '{status,version,checks}'
   ```
1. **Semilla y B0**
   ```
   bash docs/uat/A6/fixture/sembrar.sh <PROYECTO>
   docker compose -p <PROYECTO> stop zascarr
   sudo bash scripts/backup.sh || true        # sin offsite: escribe B0 y sale con error de offsite
   test -s <BACKUP_DIR>/backup_<TS>.sql.gz && test -s <BACKUP_DIR>/MANIFIESTO-backup_<TS>.json
   docker compose -p <PROYECTO> start zascarr
   ```
2. **Instantánea**
   ```
   bash scripts/uat/a6_recuperacion.sh snapshot --proyecto <PROYECTO> --file-id <UUID> --issue-id <UUID> > antes.json
   ```
3. **Filas negativas** (una por copia mutada; la interfaz para N-01)
   ```
   bash scripts/uat/a6_recuperacion.sh mutar --caso sha256|gzip|tabla-series|tabla-issues --origen <B0> --destino <BACKUP_DIR>
   sudo -E bash scripts/restaurar_datos.sh --produccion --copia <TS>   # o la acción «Restaurar…»
   cat /var/lib/zascarr/backup-status/ops-restaurar.json
   tail -n 1 /var/lib/zascarr/backup-status/ops-restaurar-intentos.jsonl
   ```
4. **Instantánea después y comparación**
   ```
   bash scripts/uat/a6_recuperacion.sh snapshot --proyecto <PROYECTO> --file-id <UUID> --issue-id <UUID> > despues.json
   bash scripts/uat/a6_recuperacion.sh comparar antes.json despues.json
   ```
5. **Eventos**
   ```
   docker events --since <inicio> --until <fin> \
     --filter event=create --filter event=start --filter event=stop --filter event=kill \
     --filter event=die --filter event=destroy --filter event=exec_create --filter event=exec_start \
     --filter label=com.docker.compose.project=<PROYECTO>
   ```
6. **Copia de archivos y verificación**
   ```
   findmnt -T <DESTINO>
   test -z "$(find <DESTINO> -mindepth 1 -maxdepth 1 -print -quit)"
   rsync -aHAX --numeric-ids --info=progress2 <RAIZ>/ <DESTINO>/
   bash scripts/uat/a6_recuperacion.sh inventario --raiz <RAIZ> --testigo <ARCHIVO-A>
   ```
7. **Reapertura**
   ```
   curl -fsS -b <COOKIE> http://127.0.0.1:<PUERTO>/ui/series/<SERIE>/numero/<NUMERO> | grep 'Continuar (pág.')'
   curl -fsS -b <COOKIE> http://127.0.0.1:<PUERTO>/ui/leer/<FILE_ID> | grep 'data-pagina="3"'
   curl -fsS -b <COOKIE> http://127.0.0.1:<PUERTO>/ui/leer/<FILE_ID>/pagina/3 | sha256sum
   ```
   El lector exige sesión; la cookie se obtiene del login y **no** se copia en A6.
8. **Cierre y enlaces**
   ```
   bash scripts/uat/a6_recuperacion.sh sanitizar docs/uat/A6/evidencia/resultado.txt
   grep -nE 'DB_PASSWORD|SECRET|TOKEN|api[_-]?key|auth_password|webhook|BEGIN (RSA|OPENSSH)' docs/uat/A6/… || true
   ```

`scripts/uat/a6_recuperacion.sh` es una herramienta de **host**, solo lectura salvo `mutar`
(que escribe copias de laboratorio) y `inventario`; no se empaqueta en la imagen, no la usa la app y
no añade dependencias (bash, coreutils, rsync ya presentes en el host). Si no se implementa, los
comandos equivalentes se ejecutan a mano y se copian a `resultado.txt`; el formato no cambia.

### 7.6 Reglas de secretos y datos personales

Prohibido en `resultado.md` y `resultado.txt`:

- contraseñas, hashes de contraseña (`pbkdf2_sha256$…`), `secret_key`, tokens, `api_key`,
  `webhook_url`, cookies, claves de Prowlarr/Transmission/aMule, contenido de `.env` o
  `runtime_settings`;
- rutas absolutas del host (`/home/…`, `/mnt/…`, `/media/…`), nombres de host, IPs, usuarios,
  nombres reales de series/números y nombres de fichero;
- salida cruda de `docker inspect` (puede llevar variables de entorno), `psql` sin recortar o
  `env`.

Permitido: UUID, hashes SHA-256, tamaños, recuentos, épocas, códigos cerrados, `tag`, `build_sha`,
`app_version`, `alembic`, `image_id`, resultados PASS/FAIL/NOT RUN.

La comprobación A-02 ejecuta al menos:
`grep -nE 'DB_PASSWORD|PASSWORD=|SECRET|TOKEN|api[_-]?key|auth_password|webhook|/home/|/mnt/|/media/|([0-9]{1,3}\\.){3}[0-9]{1,3}'`.
Si hay coincidencia, se redacta o se elimina; no se publica el fichero hasta que A-02 pase.

### 7.7 Regla de cierre

- **PASS global** solo si todas las comprobaciones obligatorias están en PASS y A-02 no tiene
  coincidencias.
- **FAIL** si alguna obligatoria falla; se corrige y se repite el ensayo completo (no se parchea la
  evidencia).
- **NOT RUN** si falta entorno, tag, disco o decisión del PO; se listan los motivos. Un `NOT RUN` en
  una comprobación obligatoria **impide** declarar cumplida la historia; no se convierte en PASS por
  «lo demás funciona».
- A6 no se fabrica: si no se ejecutó, se dice `NOT RUN`. La evidencia de una ejecución anterior no
  vale para un SHA distinto; si cambia el código, se repite.

---

## 8. Casos de prueba (TDD)

Todas las filas están **NOT RUN** en esta spec: no hay implementación. Las que deben escribirse
primero y fallar por la razón correcta están marcadas **TDD-first**. *(La rama
`feat/uatp0607-recuperacion` implementa T-06-01…T-06-06, T-07-01…T-07-03 y T-07-05; el estado
real, con lo que sigue NOT RUN, está en §14.)*

| ID | Tipo | Qué comprueba | Dónde | Estado |
|---|---|---|---|---|
| **T-06-01** | Script (Docker falso) **TDD-first** | N-01: manifiesto con SHA alterado → RC≠0, `copia_no_valida`, `comprobacion=sha256_copia`, `base_en_su_sitio=true`, `recuentos=null`; estado escrito y `.jsonl` con una línea | `tests/test_restaurar_produccion.py` | NOT RUN |
| **T-06-02** | Script **TDD-first** | N-02: gzip truncado con manifiesto recalculado → `comprobacion=gzip_cabecera`; mismo estado | ídem | NOT RUN |
| **T-06-03** | Script **TDD-first** | N-03a: falta `series` → `comprobacion=tablas_dump`; N-03b: falta `issues` → ídem (si D-6(a)) | ídem | NOT RUN |
| **T-06-04** | Script **TDD-first** | Cero eventos: `FAKE_EVENTOS` vacío y `FAKE_LOG` solo con `config`; ninguna base nueva, ningún `stop`/`up`; el test falla si aparece un evento | `tests/_restaurar_produccion.py` + `test_restaurar_produccion.py` | NOT RUN |
| **T-06-05** | Script | `intento` distinto entre dos ejecuciones; `.jsonl` conserva el primero, máximo 20, `0644`, sin temporales; `copia_version` copiada del manifiesto; sin secretos | ídem | NOT RUN |
| **T-06-06** | Unit (lector de estado) | `ops-restaurar.json` con las claves nuevas no rompe `resolver_restauracion`; causa/acción de `copia_no_valida`; `comprobacion` no se pinta; ficheros hostiles no dan 500 | `tests/test_restauracion_estado.py` | NOT RUN |
| **T-06-07** | PG real (opcional) | Instantánea real: testigo/counts/alembic/health antes/después; sin `createdb`/`dropdb` | `tests/test_restaurar_produccion_pg.py` (skip sin `TEST_DATABASE_URL`) | NOT RUN |
| **T-06-08** | Regresión | Copia válida B0 sigue completando el flujo; pruebas BL-OPS1/2 y `ruff check src/` | CI | NOT RUN |
| **T-07-01** | Unit **TDD-first** | `escribir_manifiesto` escribe `version_de_la_copia` con HEAD/Alembic/app_version/build_sha; `head`/`alembic` coinciden con los campos planos; si falta BUILD_SHA, `null` y la copia no falla | `tests/test_backup_script.py` o nuevo `tests/test_version_copia.py` | NOT RUN |
| **T-07-02** | Unit | `app_version` de `pyproject.toml` == `Settings.app_version`; regex de semver; un cambio de una sola fuente rompe el test | ídem | NOT RUN |
| **T-07-03** | Script | `restaurar_datos.sh` copia `version_de_la_copia` a `copia_version`; un manifiesto sin la clave deja `null`; un objeto hostil no llega al estado | `tests/test_restaurar_produccion.py` | NOT RUN |
| **T-07-04** | Runbook/E2E | F-01…F-03: raíces, destino vacío/distinto, mtime, inventario y testigo; se ejecuta en E-A6 y produce A6 | A6 | NOT RUN |
| **T-07-05** | Web (FakeSession) | R-01/R-02: la ficha muestra «Continuar (pág. P)» y el lector `data-pagina=P` tras restaurar; regresión de reapertura ya existente | `tests/test_web_series.py`, `tests/test_lector.py` | NOT RUN |
| **T-07-06** | A6/UAT | R-03/R-04: página P con hash testigo y `files.sha256_hash`; relaciones y progreso | A6 | NOT RUN |
| **T-07-07** | Estático | Sin migración, sin dependencia nueva, sin JS nuevo, sin escritura en la biblioteca; `ruff check src/` | CI/A6 | NOT RUN |
| **T-07-08** | Docs/UAT | `docs/uat/A6/resultado.md` y `evidencia/resultado.txt` existen, enlazados, sin secretos; A-01/A-02 | A6 | NOT RUN |

**Orden TDD recomendado.** T-06-01…T-06-04 (fallan hoy por falta de `comprobacion`/`intento` y de
tests de producción) → implementación de §4 → T-06-05/T-06-06 → T-07-01/T-07-02 → T-07-03 →
runbook/A6 (T-07-04…T-07-08). No se empieza por el runbook: sin los datos de §4, A6 no puede
declarar la versión ni el intento.

---

## 9. Dependencias y orden de implementación

1. **PO:** aprobar o rechazar D-1…D-6 (§3). Sin D-3 no se puede cerrar UATP-07; sin D-6 no hay
   N-03b; sin D-5 no hay diagnóstico por intento. D-1/D-2/D-4 son recomendaciones con impacto bajo.
2. **Código (TDD):** §4 (manifiesto, estado, `.jsonl`) y, si D-6(a), añadir `issues` a la lista de
   tablas. Único escritor del código en una tarea aparte; esta spec no lo toca.
3. **Pruebas:** T-06/T-07; primero en rojo, luego verdes; `ruff check src/`.
4. **Runbook/A6:** fixture, comandos, ejecución en E-A6, evidencia, saneado, enlaces en
   #1144/#1145/#1141.
5. **UATP-08:** consume `copia_version`, `intento` y `comprobacion`; no se adelanta aquí.

**Dependencias externas:** ninguna nueva. No hace falta Docker socket nuevo, ni root en la app, ni
red. La copia de archivos usa `rsync` del host; si no está instalado, se documenta su instalación en
el runbook (paquete del sistema, no dependencia Python).

---

## 10. Riesgos y límites

| ID | Riesgo | Mitigación / decisión |
|---|---|---|
| **R-01** | La copia manual de archivos se olvida o se hace a medias. | Runbook obligatorio, destino vacío y verificación de inventario/testigo; UATP-08 debe decir que la copia de la BD no incluye archivos (S1-04 de `uatp08-readiness.md:179`). |
| **R-02** | El destino no preserva mtime (exFAT/NTFS) o no es distinto. | F-01/F-02 exigen FS Linux y `st_dev` distinto; si no, FAIL, no «aceptable». |
| **R-03** | El sha256 completo de la biblioteca es caro en Pi. | Obligatorio solo el testigo + inventario mtime/tamaño; el completo es opcional y se declara `NOT RUN motivo=coste`. |
| **R-04** | Copias antiguas sin `version_de_la_copia` y builds manuales sin `BUILD_SHA`. | `null` = «no consta»; nunca se infiere; V-01 exige `build_sha` para que el ensayo PASS. |
| **R-05** | Los tags publicados no permiten la cláusula literal de UATP-07. | D-3: T0/T1/C + decisión del PO; A6 V-02/V-03/R-03; no se fabrica evidencia. |
| **R-06** | `issues` ausente no se detecta antes de Docker sin D-6(a). | Enmienda mínima; N-03b; si el PO no la aprueba, se documenta el límite y N-03b queda NOT RUN. |
| **R-07** | El `.jsonl` de intentos crece o filtra datos. | Máximo 20 líneas, códigos cerrados, sin rutas/hashes/secretos, `0644`, sin fallar la restauración si no se puede escribir. |
| **R-08** | El estado se sobrescribe y se pierde el intento anterior. | D-5(a): `intento` + `.jsonl`; el test T-06-05 exige dos intentos y conserva ambos. |
| **R-09** | Reordenar el preflight para leer la BD antes de las comprobaciones rompe el cero-eventos. | Prohibido en §5.4; T-06-04 falla si aparece un `exec` antes del rechazo. |
| **R-10** | A6 se convierte en un texto inventado o en un PASS parcial. | §7.7: PASS solo con comando+salida; NOT RUN no se convierte; A-04 exige línea por comprobación. |
| **R-11** | El runbook toca la instalación real. | E-A6 aislado (proyecto, puerto y volúmenes distintos); la instalación real no se toca; `restaurar_datos.sh` exige proyecto `zascarr` en producción, así que el ensayo usa el nombre aislado con `ZASCARR_PRUEBAS=1`/`PROYECTO_PRODUCCION`. |
| **R-12** | El positivo requiere autenticación activa y árbol limpio. | E-A6 con `auth_mode=password`, tag limpio y árbol sin cambios; se documenta como precondición, no como excusa. |
| **R-13** | La UI no muestra `intento`/`comprobacion` (no es su historia). | Aceptado; UATP-08 los consumirá. El diagnóstico de soporte vive en el `.jsonl` y en `ops-restaurar.json`; no se promete en pantalla. |
| **R-14** | El `app_version` estático `1.15.1` puede inducir a error. | Regla §6.8: nunca solo semver; identidad = BUILD_SHA+HEAD; test T-07-02 evita que pyproject/config se separen. |

---

## 11. Fuera de alcance (resumen)

- Herramienta de copia/restauración de archivos en el producto (D-1).
- Copia de portadas, `.env`, credenciales, configuración, volumen de PostgreSQL, `update_*` y
  `rollback-safety_*`.
- Resumen de recuperación en la interfaz, fechas absolutas y «omitido» (UATP-08).
- Restaurar desde tags antiguos o rebajar la comprobación de HEAD/Alembic.
- Borrar copias, retención, «deshacer», actualizar o desplegar.
- Migraciones, dependencias nuevas, JS nuevo, cambios de UI, escaneo de la biblioteca.
- Acreditar UATP-06/07 sin A6: este documento no lo hace.

---

## 12. Evidencia leída para esta spec (PASS/NOT RUN)

| Comprobación | Estado | Dónde |
|---|---|---|
| Preflight y orden de comprobaciones | PASS (leído) | `scripts/restaurar_datos.sh:234-355` |
| Estado `ops-restaurar.json` y `fallo_pre` | PASS (leído) | `scripts/restaurar_datos.sh:55-80`, `:506-524` |
| Manifiesto actual (HEAD+Alembic) | PASS (leído) | `scripts/_comun.sh:303-344` |
| `backup.sh` solo PostgreSQL | PASS (leído) | `scripts/backup.sh:9-12`, `:254-261` |
| `probar_restauracion.sh` solo base desechable | PASS (leído) | `scripts/probar_restauracion.sh:1-10` |
| `app_version` literal y `BUILD_SHA` de imagen | PASS (leído) | `src/zascarr/config.py:408`, `Dockerfile:31-33`, `docker-compose.yml:110` |
| Causas y lector de estado | PASS (leído) | `src/zascarr/services/ops_host.py:463-478`, `:568-577` |
| Progreso y reapertura del lector | PASS (leído) | `src/zascarr/models/__init__.py:1269-1291`, `src/zascarr/web/lector.py:41-80`, `lector.html:7,20,78` |
| Tags publicados sin lector/restauración | PASS (verificado con `git ls-tree`) | §2.5 |
| Tests de producción del caso negativo | **NOT RUN / no existen** | `tests/test_restaurar_produccion.py` |
| Copia de archivos, A6 y ejecución en Pi | **NOT RUN** | — |
| A6 real, Pi, navegador, `docker events` | **NOT RUN** | — |

---

## 13. Resumen para el PO y el implementador

- **Qué se entrega:** una spec ejecutable de UATP-06 (matriz negativa, estado intacto, cero eventos,
  diagnóstico por intento) y UATP-07 (copia de archivos manual, reapertura en P, versión declarada,
  A6).
- **Qué no se entrega:** código, tests, A6 ni declaración de cumplimiento.
- **Decisiones que bloquean:** D-1 (manual vs herramienta), D-2 (tupla de versión), D-3 (tags y
  cláusula literal), D-4 (A6 en repo), D-5 (intento/`.jsonl`), D-6 (añadir `issues` a FR-17(d)).
- **Primer paso del implementador:** escribir T-06-01…T-06-04 en rojo; después §4; después
  T-07-01/T-07-02; el runbook/A6 al final.
- **Cierre:** solo con A6 PASS completo y enlazado desde #1144/#1145. Mientras falte una comprobación
  obligatoria, UATP-06/07 no están cumplidas.

---

## 14. Estado de implementación en `feat/uatp0607-recuperacion` (TDD)

> **Nota de implementación, no de cumplimiento.** Este apartado no cambia ninguna decisión del PO ni
> declara cumplidas UATP-06 [#1144] ni UATP-07 [#1145]: la acreditación sigue exigiendo ejecutar A6
> (§7) sobre una candidata identificada. Fija lo que ya está en la rama para que QA/PO sepan qué
> probar y qué falta.

### 14.1 Implementado (contrato aditivo de §4, D-6 y FR-17(d))

| Pieza | Dónde | Tests |
|---|---|---|
| `version_de_la_copia = {head, build_sha, app_version, alembic}` en el manifiesto; `null` = «no consta»; `head`/`alembic` duplican los campos planos | `scripts/_comun.sh::escribir_manifiesto` (+ `leer_app_version`, `leer_build_sha`) | T-07-01/T-07-02 en `tests/test_backup_script.py`, `tests/test_version_copia.py` |
| `intento` (16 hex, una vez por ejecución), `comprobacion` (código cerrado de §4.4) y `copia_version` (tupla saneada del manifiesto) en `ops-restaurar.json` | `scripts/restaurar_datos.sh::estado_restaurar`, `sanear_copia_version` | T-06-01…T-06-05, T-07-03 en `tests/test_restaurar_produccion.py` |
| `ops-restaurar-intentos.jsonl`: una línea por intento terminal, máx. 20, `0644`, atómico, sin rutas/hashes/secretos; si no se puede escribir no falla la restauración | `scripts/restaurar_datos.sh::registrar_intento_jsonl` | T-06-05 |
| Códigos de `comprobacion` implementados | `existencia_copia`, `manifiesto`, `sha256_copia`, `bytes_copia`, `codigo_manifest`, `gzip_cabecera`, `cabecera_pg_dump`, `tablas_dump`, `alembic_revision`; `null` en fallos de fase | T-06-01/T-06-02/T-06-03 |
| Preflight exige la tabla `issues` (D-6(a) / FR-17(d) enmendado) | bucle de tablas de `restaurar_datos.sh` | T-06-03 (`issues`), `test_dump_sin_una_tabla_del_preflight_aborta_antes_de_tocar` |
| FR-17(d): relee HEAD **y** árbol al final de `--produccion`; si cambió, `fallida`/`unexpected`/`base_en_su_sitio:true`, no se borra la previa y no se declara terminada | `restaurar_datos.sh::ejecutar_produccion` (paso 9 bis) | `test_si_el_head_cambia_al_final_se_falla_cerrado`, `test_si_el_arbol_se_ensucia_al_final_se_falla_cerrado` |
| Matriz negativa de producción con cero eventos de contenedor, base/health/filas intactas y B0 intacta | `tests/_restaurar_produccion.py` (marcadores en el docker/git falsos) | `test_una_copia_danada_se_rechaza_antes_de_tocar_contenedores_ni_base` (N-01/N-02/N-03a/N-03b) |
| Reapertura en la página guardada (FakeSession) | — | `tests/test_lector.py::test_el_lector_reabre_en_la_pagina_guardada_tras_restaurar` |
| Claves nuevas toleradas por el lector de estado (no se pintan) | sin cambios en `services/ops_host.py` | T-06-06 en `tests/test_restauracion_estado.py` |

Contrato tal como queda implementado (ejemplos, sin valores reales):

```json
"version_de_la_copia": {"head": "<40 hex o null>", "build_sha": "<40 hex o null>",
                        "app_version": "1.15.1", "alembic": "0052"}
```

```json
{"schema":1,"intento":"a1b2c3d4e5f60718","copia":"backup-20261121_040000","copia_epoch":0,
 "inicio_epoch":0,"actualizado_epoch":0,"fase":"verificando","resultado":"fallida",
 "error":"copia_no_valida","comprobacion":"tablas_dump","base_en_su_sitio":true,
 "copia_version":null,"recuentos":null}
```

### 14.2 Recomendaciones aplicadas

- **D-1(a), manual:** documentado en `docs/TESTING_E2E.md` §17; **no** se añade herramienta de copia
  ni restauración de archivos, ni se toca `backup.sh`/la biblioteca.
- **D-2(a), tupla nunca bloqueante:** un manifiesto sin la clave o con un objeto hostil deja
  `copia_version: null`; la restauración no se bloquea y la autoridad sigue siendo Alembic.
- **D-4, A6 en el repo:** la ubicación propuesta no cambia; los ficheros de evidencia **no existen
  todavía** en esta rama (ver §14.3).
- **D-5(a), diagnóstico por intento:** implementado como en §4.2/§4.3.
- **D-6(a), tabla `issues`:** implementada; un dump sin `issues` se rechaza en el preflight con
  `copia_no_valida` + `comprobacion=tablas_dump` antes de cualquier evento de contenedor.
- **D-3, tags y cláusula del tag antiguo:** **pendiente del PO**; el código no fabrica tags ni
  simula la cláusula. Nada de esta rama la acredita.

### 14.3 Pendiente para acreditar (NOT RUN en esta rama)

- **A6 real** sobre E-A6: N-01…N-04 con `docker events` (0 líneas), S-01…S-03, D-01, F-01…F-04,
  R-01…R-05, V-01…V-03, A-01…A-04 (T-07-04, T-07-06, T-07-08).
- **`docs/uat/A6/resultado.md` y `docs/uat/A6/evidencia/resultado.txt`**: no creados; no se escribe
  evidencia sin ejecución (§7.7).
- **Tag T1/C y decisión D-3**: sin tag publicado que cumpla la letra del CA; se eleva al PO.
- **T-06-07 (PostgreSQL real)**: sigue saltándose sin `TEST_DATABASE_URL`; el arnés de Docker falso
  cubre el orden y el estado, no el dump real.
- **Enmienda documental de BL-OPS2** (FR-17(d) con `issues`, FR-24 con las tres claves y el `.jsonl`):
  recomendada por D-5/D-6 y **no aplicada** en la spec de BL-OPS2 por esta rama.
- **T-07-07 estático:** `ruff check src/` pasa y no hay migración, dependencia, JS ni escritura en la
  biblioteca; la parte de A6 se acredita al ejecutar.

### 14.4 Evidencia de la implementación (reproducible, sin E-A6)

```bash
bash -n scripts/_comun.sh && bash -n scripts/restaurar_datos.sh
pytest -q tests/test_restaurar_produccion.py tests/test_backup_script.py \
  tests/test_version_copia.py tests/test_restaurar_datos.py \
  tests/test_restauracion_estado.py tests/test_lector.py
ruff check src/
```

Resultado en la rama: **206 tests** de las suites tocadas en verde (incluye 27 de
`test_restaurar_produccion.py`), `ruff check src/` sin hallazgos y la suite BL-OPS1/2
(`test_backup_script`, `test_copias_json`, `test_restauracion_ops2`, `test_ops_paridad`,
`test_update_hook_restauracion`, `test_instalar_ops`) sin cambios de aserción.
