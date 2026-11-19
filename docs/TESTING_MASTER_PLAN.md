# Plan maestro de pruebas — ZascArr

- **Versión auditada:** 1.15.1 (`pyproject.toml`)
- **Fecha:** 2026-11-18
- **Ámbito:** pruebas unitarias, integración, contratos, operación, E2E manual y automatizada, seguridad y rendimiento en Raspberry Pi.
- **Estado:** plan vivo. Sustituye al marco genérico de QA que no tuvo en cuenta la suite existente.

## 0. Resumen ejecutivo

ZascArr no necesita un plan de pruebas «desde cero». Ya tiene una base poco habitual para un proyecto self-hosted:

- **10.387 casos recogidos** por `pytest` en **498 ficheros/recursos** dentro de `tests/`.
- **154 ficheros de test** que usan `TEST_DATABASE_URL`; el job de CI los ejecuta contra **PostgreSQL 15 real**, no contra SQLite.
- **53 ficheros** con pruebas de RAR real y `unar`/`lsar` 1.10.8.
- CI con suite unitaria, Postgres real, `ruff` + reglas de seguridad `S`, auditoría de CSS, `pip-audit` y build Docker **amd64 + ARM64**.
- `docs/TESTING_E2E.md` (17 secciones) y `docs/TESTING_NFR_Zascarr.md` (NFR-01 a NFR-20) ya cubren el recorrido manual y los requisitos no funcionales.

El problema no es falta de tests, sino **fiabilidad, foco y automatización de los huecos correctos**. Los dos huecos con más impacto inmediato son:

1. un **test de tokens inestable en CI** que convierte el gate de Postgres en intermitente;
2. la ausencia de **E2E de navegador automatizado** y de una prueba de **runtime ARM64/volumetría**.

## 1. Principios

1. **Riesgo primero, pirámide después.** No se persigue un porcentaje global de cobertura; se protege lo que puede perder archivos, corromper la base, exponer la app o romper la instalación.
2. **PostgreSQL real para lo que dependa de PostgreSQL.** `pg_trgm`, bloqueos, migraciones y transacciones no se validan con SQLite.
3. **La suite existente es el activo.** No se reescribe ni se marcan 10.000 tests con `unit`/`integration`/`e2e` sin necesidad; se seleccionan por ruta/fixture y se marcan solo los nuevos.
4. **Un test saltado no es un test pasado.** Los jobs críticos ya fallan si las pruebas de Postgres o RAR real no se ejecutan; se mantiene esa política.
5. **Los fixtures son datos, no copias de producción.** Nada de portadas, rutas personales ni credenciales reales en el repositorio.
6. **La seguridad es un gate, no una revisión final.** SSRF, path traversal, ZIP bomb, XSS, mass assignment y puerta legal se prueban en cada cambio que toque esas superficies.
7. **El usuario es «El Coleccionista».** Un error debe decir qué pasó y qué hacer; los tests de UI comprueban el texto visible, no solo el código HTTP.

## 2. Línea base comprobada

| Elemento | Estado real | Evidencia |
|---|---|---|
| Suite recogida | 10.387 casos | `pytest --collect-only -q` |
| Ficheros/recursos de test | 498 | `tests/` |
| Postgres real | 154 ficheros | `grep -l TEST_DATABASE_URL tests/*.py` |
| RAR real | 53 ficheros | pruebas con `unar`/`lsar` |
| Job unitario + RAR | verde | `.github/workflows/ci.yml` → `test` |
| Job Postgres 15 | verde, con un test intermitente | `postgres` |
| Lint/seguridad | verde | `ruff check src/` + `ruff check --select S src/` |
| Docker amd64 + ARM64 | verde | matriz `docker-build` |
| `pip-audit` | informativo, no bloquea | job `pip-audit` |
| Cobertura | no medida | sin `pytest-cov` ni `--cov` |
| E2E navegador | manual | `docs/TESTING_E2E.md` §13 |
| Marcadores `unit`/`integration`/`e2e` | inexistentes | `pyproject.toml` sin `markers` |
| Artefactos `.tmp-*`/`.log` versionados | corregido | PR #1138, gate de higiene en CI |

### 2.1 Hallazgo prioritario: test intermitente de tokens

`tests/test_tokens_limites_pg.py::TestRecorridoConElMayorContenidoPosible::test_clave_real_de_controles_titulo_id_descripcion_portada_y_100_parecidas` ha fallado en CI (dos ejecuciones) con una diferencia de unos 2.900 caracteres frente a `MAX_TOKEN_CANDIDATA`, y pasa en local. Es un **P0 de fiabilidad de CI**: mientras exista, cualquier PR puede quedar bloqueada por una causa ajena y se pierde la confianza en el gate. Debe reproducirse en el mismo entorno del job, corregirse el fixture o el cálculo, y añadirse una comprobación de que no vuelve a aparecer.

### 2.2 Hallazgo cerrado: higiene de repositorio

`.tmp-collect.txt` y `.tmp-full.log` estaban versionados en `main`. El PR #1138 los elimina, ignora `.tmp-*`, `.tmp/`, `*.log`, `*.dump` y `*.prof`, y añade un gate de CI que falla si vuelven a entrar, incluso con `git add -f`.

## 3. Mapa de riesgos y cobertura

Escala: **C** cerrado, **P** parcial, **H** hueco.

| ID | Riesgo | Cobertura actual | Estado | Acción |
|---|---|---|---|---|
| R1 | Pérdida/corrupción de tebeos en importación, dedupe o movimiento | `test_importer*`, `test_*duplicados*`, `test_restauracion*`, `docs/TESTING_E2E.md` §7/§11 | P | Probar explícitamente `EXDEV` entre descargas y biblioteca y restaurar un backup real |
| R2 | Bypass de puerta legal, auth o exposición LAN/proxy | `test_legal.py`, `test_auth*.py`, `test_cover_ssrf.py`, NFR-02/03/11/12/13 | C/P | Añadir `POST` directos a acciones protegidas sin aceptar la puerta; smoke de auth en proxy |
| R3 | Migración/upgrade/rollback destructivo | `test_migracion_*`, `test_backup_script.py`, `test_rollback_script.py`, `test_restaurar_produccion*` | P | Prueba destructiva real: versión N-1 → N → rollback con dump |
| R4 | Falso positivo del matcher fuzzy | `test_matcher_sql_pg.py`, `test_matcher_sin_numero.py`, `test_nombres_biblioteca.py`, `test_tradiciones_de_la_carpeta.py` | C/P | Corpus adversativo de títulos y revisión de umbrales |
| R5 | RAM/CPU/disco en Pi con CBZ/CBR grandes | Build ARM64; sin runtime ARM64 ni volumetría | H | Soak ARM64 con 2.000 CBZ/CBR y límite 512 MB |
| R6 | Rotura de fuentes externas o rate limit | Tests de clientes + RAR real; contratos de fuentes dispersos | P | Golden fixtures sanitizados y canario nocturno no bloqueante |
| R7 | Regresión de UI/HTMX/hotlinking | Amplia suite web, tests de CSS y de portadas; E2E manual | P | Smoke navegador P0 y comprobación de red saliente cero |
| R8 | Instalación/bootstrap/permisos | `test_bootstrap_rutas.py`, `test_bootstrap_usuario.py`, `test_rollback_script.py` | P | Instalación limpia + reejecución idempotente en contenedor/VM |

## 4. Niveles de prueba y qué se ejecuta

### 4.1 Unitarias y de lógica pura

- Parsers de nombres, números, tradiciones, normalización y huecos.
- Máquina de estados del orquestador, políticas, validadores y retención.
- Deben seguir sin red, sin Postgres y sin I/O pesado.
- Se ejecutan en el job `test`; no se añaden marcadores masivos: los nuevos tests pueden usar `@pytest.mark.unit` cuando aporte selección.

### 4.2 Integración con PostgreSQL 15

- Todo lo que use `pg_trgm`, transacciones, bloqueos, JSONB, migraciones o `asyncpg`.
- 154 ficheros ya declaran `TEST_DATABASE_URL`; el job `postgres` exige que no se salten.
- Los tests nuevos de base de datos llevan `TEST_DATABASE_URL` y se añaden a la lista que ejecuta `scripts/ci_postgres.py`.

### 4.3 Contratos y fixtures de fuentes

- Clientes de Comic Vine, AniList, Tebeosfera, GCD, Metron, Open Library y Fandom.
- Respuestas `429`, `503`, timeout, HTML roto y caché negativa.
- Golden fixtures **sanitizados** (sin datos personales ni contenido con derechos) para parser y normalización.
- Los tests de fuente no deben depender de la red en el gate de PR; el canario real va en nightly.

### 4.4 Operación e infraestructura

- `bootstrap.sh`: instalación limpia, reejecución idempotente, permisos y cambio de exposición.
- Migraciones: `upgrade head` sobre una base limpia y cadena completa.
- Backup/restore: crear datos → backup → retención → borrar/recrear → restaurar → consultar.
- Upgrade/rollback destructivo contra Docker + PostgreSQL reales, no solo dobles.
- El criterio de éxito no es «el script termina»: es que los datos y el healthcheck quedan correctos.

### 4.5 E2E de navegador

- Prioridad: **pocos flujos P0**, no una suite exhaustiva.
- Puerta legal, auth/proxy, importación visible, ficha con portada y wishlist mockeada.
- Playwright Python si se implanta; no requiere build de Node, pero añade navegador al runner. Debe ser un job separado y **no** bloquear el PR hasta estabilizarlo.
- La comprobación de **cero hotlinking** se hace observando peticiones externas del navegador.

## 5. Quality gates

### 5.1 En cada PR (bloqueante)

1. **Higiene:** sin `.tmp-*`, `*.log`, `*.dump` ni `*.prof` versionados.
2. **Lint/seguridad:** `ruff check src/` y `ruff check --select S src/`.
3. **CSS:** `scripts/auditar_css.py --strict`.
4. **Suite unitaria + RAR real:** sin fallos y con las pruebas `rar_real` ejecutadas.
5. **PostgreSQL 15 real:** sin fallos, sin saltadas y con los clientes de PG 15.
6. **Docker:** build amd64 y ARM64, centinela `.env` y versión de `unar`.

**Objetivo de duración:** mantener el PR por debajo de ~15 minutos. El job de Postgres ya tarda unos 20-25 minutos; si crece, separar en dos jobs por dominio o usar un runner mayor, no relajar el gate.

### 5.2 En nightly

1. **Upgrade/rollback destructivo** desde el último tag publicado.
2. **Backup + restore real** con verificación de datos.
3. **Soak ARM64:** 2.000 CBZ/CBR, límite de memoria de Pi 4/5, tiempo de respuesta y conexiones `asyncpg`.
4. **Canario de fuentes externas:** 1 petición controlada por fuente; no bloqueante, con alerta.
5. **`pip-audit`:** revisar y decidir si pasa a bloqueante cuando la política de CVEs esté acordada.

### 5.3 En release

- 0 defectos P0/P1 abiertos.
- PR + nightly verdes.
- Backup/restore y upgrade/rollback ejecutados sobre la versión candidata.
- Revisión exploratoria manual de 15 minutos si cambió HTMX/CSS.
- Sin tests nuevos saltados sin issue y justificación.

## 6. Cobertura: cómo medirla sin convertirla en teatro

1. Añadir `pytest-cov` **solo al CI**, no a runtime.
2. Publicar la línea base por módulo (`importador`, `orquestador`, `seguridad`, `backup`) sin gate.
3. Fijar umbrales incrementales en esos módulos, no un 85 % global.
4. No excluir líneas para maquillar el número; las exclusiones se justifican en el propio test.
5. La cobertura no sustituye a los tests de contrato, backup ni E2E.

## 7. Hoja de ruta priorizada

### Iteración 1 — estabilizar el gate (P0)

- Corregir el test intermitente de tokens de Postgres.
- Repetir el job de Postgres 3 veces sobre el mismo SHA para medir flake.
- Añadir `pytest --durations=20` al job unitario (diagnóstico, no gate).
- Medir cobertura base de los cuatro módulos críticos.
- **Criterio de salida:** 3 ejecuciones consecutivas verdes del job de Postgres.

### Iteración 2 — P0 de datos y seguridad

- Test de bypass de puerta legal con `POST` directo (no solo por UI).
- Restore real de backup con datos verificables.
- `EXDEV` entre descarga y biblioteca.
- ZIP-slip y ZIP bomb con fixtures sintéticos; confirmar que ya están cubiertos o añadir el que falte.
- **Criterio de salida:** cada riesgo R1/R2/R3 tiene una prueba automatizada o un E2E manual enlazado.

### Iteración 3 — contratos y matcher

- Golden fixtures de Tebeosfera, Comic Vine, AniList y clientes de descarga.
- Caché negativa: segunda consulta sin red.
- Corpus adversativo de títulos para el matcher y revisión de umbrales.
- Canario nocturno de fuentes reales, no bloqueante.

### Iteración 4 — Pi y navegador

- Smoke Playwright de 4–5 flujos P0.
- Soak ARM64 con 2.000 CBZ/CBR y presupuesto de 512 MB.
- Upgrade/rollback real desde el tag anterior.
- **Criterio de salida:** release candidate pasa PR + nightly + restore/rollback.

## 8. Definition of Done de QA para una release

- 0 P0/P1 abiertos de pérdida de datos, corrupción de BD, migración o seguridad.
- PR y nightly verdes; sin tests críticos saltados.
- Backup + restore y upgrade/rollback verificados sobre la release candidata.
- Sin artefactos locales versionados.
- Sin hotlinking ni peticiones externas inesperadas en la biblioteca.
- Revisión manual de móvil/tablet si cambió la UI.
- El plan de pruebas se actualiza si cambia un riesgo, una fuente o un gate.

## 9. Lo que no se hace

- No usar SQLite para lógica que depende de Postgres.
- No añadir Playwright, `mypy` o cobertura como gates antes de medir su coste y estabilizarlos.
- No marcar 10.000 tests con etiquetas nuevas sin un objetivo de selección claro.
- No duplicar `bandit` con `ruff --select S`.
- No convertir el canario de fuentes en un gate bloqueante: las fuentes externas fallan por causas ajenas.
- No aceptar un test saltado como verde en Postgres/RAR real.

## 10. Evidencias y documentos relacionados

- `docs/TESTING_E2E.md` — recorrido manual completo y contratos de UI.
- `docs/TESTING_NFR_Zascarr.md` — NFR-01 a NFR-20.
- `.github/workflows/ci.yml` — gates reales de PR.
- `tests/conftest.py`, `tests/_pg.py` — infraestructura de Postgres y migraciones.
- `scripts/ci_postgres.py`, `scripts/ci_rar_real.py` — exigencias de ejecución real.
- `docs/BACKLOG.md` — deuda de upgrade/rollback y NFR pendientes.
- PR #1138 — higiene de artefactos locales.
