# QA final — OPS4/#443 historia B, SHA `f34c30ba` (PR #1233, delta de cierre) (2026-11-22)

> **Rol QA · solo lectura.** SHA auditado **`f34c30baae79da05f1077b0594c206945b6cb413`**
> («test(ops): reponer cobertura durable y cerrar alcance apagado»), padre
> `3aa4ec1646ffb97c310e16c1a4dded8ab6318c74`; rama `feat/ops4-b-limpia-443`;
> PR **#1233** (base `main`), worktree `.worktrees/ops4-b-limpia`. Evidencia
> tomada con el **árbol rastreado limpio** (`git status --porcelain` vacío a
> las 19:22Z; ver nota de cierre por cambios ajenos posteriores). Esta QA **no
> ejecutó localmente** Pi, Docker real, PostgreSQL real, systemd del host,
> `update.sh`, el instalador ni ningún despliegue; **no ejecutó la suite
> completa** (la tarea lo prohíbe; CI sí la ejecutó sobre el SHA, §2). No se
> editó código. El único fichero escrito por esta QA es este informe.
> **No autoriza habilitar, instalar en la Pi ni desplegar**; la fusión apagada
> la decide el PO con este informe y el dictamen SecOps.

---

## 1. Veredicto

| Cuestión | Veredicto |
|---|---|
| **Fusionar apagado** (esta PR, bandera `false`) | **GO CON CONDICIONES C-F1…C-F6.** No hay P0/P1 de ejecución ni ruta alcanzable con los valores por defecto; el delta no toca código de producción salvo retirar un módulo que no se instalaba; **CI del SHA (merge ref) verde 5/5**, incluida suite y PostgreSQL real (§2). Las condiciones son de contratos de prueba, verdad documental, Ruff local y acto de fusión; ninguna cambia comportamiento. **Tal cual, sin cerrarlas o aceptarlas por escrito, el árbol no cumple CA-A-06/CA-A-08/CA-A-09/CA-A-10/CA-A-11/CA-A-12** (§4). |
| Declarar cerrada la **Parte A** (CA-A-01…15 / §6.2) | **NO-GO en este SHA** mientras C-F1…C-F6 sigan abiertas: la cobertura repuesta ejercita el namespace v3 muerto, TA-09 no está completa y la verdad documental (A5/CA-A-10) sigue sin cumplirse; hay además enlaces y recuentos incoherentes introducidos por el propio delta. |
| **Habilitar** (bandera `true`, socket/unidad, `update.sh` real) | **NO-GO absoluto.** B1–B10, CE-1…CE-12, I-1…I-9 y el runbook no están implementados/validados; la ruta encendida sigue sin probar (§6). No alcanzable con el valor por defecto. |
| **Despliegue** | **No autorizado.** Sin cambios de política: nada de `.env`/Compose desplegado, `--activar`, Pi ni `update.sh`. |

**Caducidad.** Este informe vale **solo** para `f34c30ba` con la función
deshabilitada. Caduca con cualquier commit, rebase o merge que cambie el SHA
(ver nota de cierre). El merge real sobre el `origin/main` vigente produce otro SHA.

---

## 2. Evidencia ejecutada

Entorno local: venv de pruebas del repo, **Python 3.14.4**, pytest 9.2.0,
ruff 0.17.4, `PYTHONPATH=.:src`, sin `TEST_DATABASE_URL`, sin Docker ni
systemd. `git rev-parse HEAD` = `f34c30ba…`; padre `3aa4ec16`; merge-base con
`origin/main` = `2c773e53…`; `origin/main` local = `3ce1bd5e` (28 commits por
delante de la base; ver C-F5).

| Comprobación | Resultado |
|---|---|
| Selección OPS4/instalador: `pytest -q tests/test_ops4_*.py tests/test_instalar_ops4.py` | **389 recogidas, 389 passed, 0 failed** (11,98 s) |
| Nuevos/ampliados: `tests/test_ops4_registro_repeticiones.py tests/test_ops4_alcance_apagado.py tests/test_ops4_aislamiento.py` | **39 passed, 0 failed** (28 + 3 + 8; 1,52 s) |
| Colección de la suite completa (solo `--collect-only`, sin ejecutar) | **11401 recogidas** = 8947 + 2454, la aritmética exacta de los documentos actualizados |
| Ruff CI-equivalente: `ruff check src/` y `ruff check --select S src/` | **All checks passed!** |
| Ruff ficheros tocados: `ruff check tests/test_ops4_*.py tests/test_instalar_ops4.py tests/_host_v4.py` | **1 hallazgo nuevo: E501 en `tests/test_ops4_aislamiento.py:88`** (102 > 100; CI solo lintea `src/`, §4 H-F7) |
| Ruff `deploy/ops/*.py` | All checks passed; `--select S deploy/ops/*.py`: 2 hallazgos **preexistentes** (S603/S607 en `zascarr_actualizar_aux.py:201-202`, argv y `PATH` fijos; CI solo escanea `src/`) |
| `bash -n scripts/instalar_actualizacion_ops4.sh`; `git diff --check` | OK; limpio |
| CI de la PR, run [45059996418](https://github.com/juanajok/zascarr/actions/runs/45059996418), `head_sha` = `f34c30ba`, evento `pull_request` (checkout del **merge ref**: `f34c30ba` + base del momento `9fe0be06`), Python 3.11 | **5/5 SUCCESS**: ruff 19:18:45Z, *Suite unitaria* 19:25:50Z, *Pruebas con Postgres real* 19:33:10Z, build amd64 19:19:45Z, build ARM64 19:19:34Z. `mergeable_state: clean` al cierre. Recuentos de CI no extraídos (API de logs exige auth); la cifra 8947/2454 **no se ha reproducido localmente** (NOT RUN) |

**Coherencia de cifras.** La colección local 11401 = 8947 + 2454 es exactamente
la aritmética declarada; la selección dirigida da 389 (364 previas +28 registro
+3 TA-09 +3 aislamiento −9 retirados de protocolo) y **389/389 pasan**. La
suite completa **no** se ha ejecutado aquí; CI del SHA sí está verde, pero el
merge ref se calculó contra la base de las 19:18Z: con el `origin/main` local
actual (`3ce1bd5e`) el merge ref es otro y su CI **NOT RUN** (C-F5).

**Delta desde `3aa4ec16`:** 19 ficheros, +852/−136. Rename
`deploy/ops/admision_v4_actualizar_ops4.py` → `tests/_host_v4.py` (95 % de
similitud); tests nuevos `test_ops4_alcance_apagado.py` (32 líneas, 3 casos) y
`test_ops4_registro_repeticiones.py` (216 líneas, 15 funciones / 28 casos);
`test_ops4_aislamiento.py` de 5 a 8 casos; `test_ops4_protocolo_v4.py` de 21 a
12 casos (−9: se retiran las pruebas de la admisión movida); imports adaptados
en transporte/UI; 9 documentos `ops4-*` + ADR 0026 con recuentos/nota; y los
informes SecOps/QA de `3aa4ec16` ya versionados.

---

## 3. Delta verificado (lo pedido)

### 3.1 Admisión movida a `tests/_host_v4.py` — correcto

- `deploy/ops/admision_v4_actualizar_ops4.py` **ya no existe**; el contenido vive
  en `tests/_host_v4.py` con docstring nuevo «Doble de host para tests; no se
  instala» (diff de 4 líneas, 95 % de similitud).
- El **instalador no lo copia**: copia una lista fija de cuatro módulos
  (`scripts/instalar_actualizacion_ops4.sh:148-151`) y el auxiliar importa
  exactamente esos cuatro (`zascarr_actualizar_aux.py:21-61`); ninguna
  referencia en `scripts/`, `src/` ni en los entrypoints.
- El doble **no se empaqueta** (paquete en `src/`) ni **se recoge como test**
  (sin prefijo `test_`; lo importan `test_ops4_transporte_v4.py:15` y
  `test_ops4_ui_actualizacion.py:125`).
- Único residuo: **enlace roto nuevo** en `docs/design/ops4-protocolo-v4.md:25`,
  que sigue apuntando al módulo retirado (H-F4).
- El E2E de la UI sigue **simulando** el host con el doble; el `procesar` real
  del auxiliar y el socket real siguen **NOT RUN** (fase de habilitación).

### 3.2 28 casos del registro durable — pasan, pero prueban el namespace v3

`tests/test_ops4_registro_repeticiones.py`: **28/28 recogidos y verdes**
(15 funciones parametrizadas). Cubren, sobre el núcleo compartido
`_reclamar_marca` (`deploy/ops/registro_repeticiones_ops4.py:48-93`):

- creación exclusiva, marca vacía, modo `0600`, repetición, marca persistente
  y descriptor del llamador intacto;
- orden `fsync` fichero → directorio; fallo de `fsync` en cada etapa sin borrar
  la marca y sin filtrar el mensaje; callback que no acredita `sync` ⇒ deniega;
- `id` inválido/`None`/`True`/mayúsculas…; nombre existente symlink/FIFO/dir
  sin seguirlo; directorio escribible por grupo; descriptor inválido o de
  fichero; `ENOSPC`; rename del directorio sin redirigir; 8 hilos (una sola
  reclamación); 8 procesos independientes + reapertura; fallos en
  `dup`/`fstat`/`close`; sin fugas de FD.

**Matiz crítico (H-F1):** todos los casos llaman a `registro.reclamar_id` →
`solicitud-<id>` (namespace **v3 experimental, sin llamadores**), no a
`reclamar_autorizacion`/`crear_reclamador_durable` → `autorizacion-<id>`, que es
el consumo que usa el host. El flujo vivo sí tiene cobertura indirecta en
`tests/test_ops4_autorizacion_compuesta.py:345-460` (aceptada/repetida, otro
id, otra clave, reapertura, fallo del registro), pero la **separación explícita
de prefijos** que se perdió con la limpieza sigue sin probarse.

### 3.3 Barreras de aislamiento ampliadas (5 → 8)

Nuevas en `tests/test_ops4_aislamiento.py`:

- `test_la_app_no_importa_el_codigo_privilegiado_del_host` (líneas 66-70):
  prohíbe `deploy.ops`/`from deploy` en `src/zascarr`.
- `test_el_instalador_copia_todo_lo_que_importa_el_auxiliar` (73-84): fija los
  cuatro módulos del auxiliar y exige que aparezcan en el instalador.
- `test_el_auxiliar_y_la_unidad_usan_python_aislado` (87-91): `/usr/bin/python3
  -I`, sin `PYTHONPATH` y `ReadWritePaths` coherente.

Son barreras reales y útiles, pero **no cierran literalmente** CA-A-06/CA-A-08
(H-F3): no calculan el cierre transitivo, no comparan la lista exacta del
instalador y no incluyen los imports del finalizador.

### 3.4 TA-09 (`tests/test_ops4_alcance_apagado.py`, 3 casos)

Cubre: bandera `false` literal en `config.py` y Compose
(`docker-compose.yml:164`); `systemctl enable` ausente del instalador;
`[Install]` ausente en las tres unidades; `update.sh` ausente de auxiliar y
`main.py`. Comparado con la spec (TA-09, §6.2) **faltan**: prueba estática de
ausencia de migración Alembic nueva y de `.env` de producción; `ExecStartPost`
está cubierto por TA-01 (`test_ops4_unidades.py:38-42`,
`test_instalar_ops4.py:149-162`). Además, la aserción sobre el instalador es
vacua: `assert "update.sh" not in texto or "instalar" in ruta.name` es siempre
cierta para `instalar_actualizacion_ops4.sh` (H-F2).

### 3.5 Recuentos 389 / 8947 — coherentes, con la salvedad de ejecución

- **389** = casos de la selección OPS4/instalador, verificados pasando (arriba).
- **8947 / 2454**: la colección local da 11401 = 8947 + 2454; los documentos
  actualizados usan esas cifras. La **ejecución** de la suite completa no se ha
  reproducido en esta QA (NOT RUN); CI del SHA está verde. La sustitución masiva
  de cifras ha dejado incoherencias históricas (§4 H-F4).

### 3.6 No se ha colado Parte B — correcto

- El delta **no toca** `src/`, `scripts/`, `docker-compose.yml`, `.env.example`
  ni `alembic/`; en `deploy/` solo aparece el borrado del módulo no instalado.
- Bandera `false` por defecto (`src/zascarr/config.py:286`) y en Compose
  (`docker-compose.yml:164`); `POST /ui/actualizar` devuelve **404 antes de
  leer la clave** (`src/zascarr/web/actualizacion.py:80-81`).
- Unidades sin `[Install]`; instalador sin `enable` (`--activar` solo
  `systemctl start` no persistente); sin migración Alembic
  (`git diff origin/main...HEAD -- alembic/versions/` vacío); sin `OPS4_*` en
  `.env.example`; sin `.env`, claves ni sockets versionados; sin cambios en
  `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py`;
  sin ficheros de Parte B (reconciliación, fases, reserva, sandbox) en la rama.
- `src/zascarr` no importa `deploy.ops` (test nuevo + `grep`); la app ve
  `/run/zascarr-ops` montado `ro`.

---

## 4. Hallazgos

**H-F1 — P2 · La cobertura repuesta ejercita el namespace muerto v3.**
`tests/test_ops4_registro_repeticiones.py` usa `registro.reclamar_id`
(21 ocurrencias; **0** a `reclamar_autorizacion`/`crear_reclamador_durable` en el
fichero) y comprueba `solicitud-<id>`. El control instalado es
`reclamar_autorizacion` (`autorizacion-<id>`, usado por
`crear_reclamador_durable`, `registro_repeticiones_ops4.py:96-115,174-191`);
sus fallos de `fsync`/disco/descriptor solo están cubiertos a través del núcleo
compartido y de los E2E de composición, no en su namespace. Tampoco se prueba
la **separación de namespaces** que el QA anterior dio por perdida, y
`PREFIJO_SOLICITUD_V3`/`reclamar_id` siguen en el módulo **instalado** (la
condición C1 anterior pedía retirarlo o justificarlo por escrito en la PR).
Mitigación: el núcleo `_reclamar_marca` es común y el flujo vivo tiene E2E; es
deuda de verificación, no defecto de ejecución.

**H-F2 — P2 · TA-09 incompleta respecto de su spec.**
Faltan la prueba de ausencia de migración Alembic nueva y la de `.env` de
producción (spec TA-09), y la aserción sobre `update.sh` en el instalador es
tautológica (`tests/test_ops4_alcance_apagado.py:23`). `ExecStartPost` queda
cubierto fuera de TA-09 (TA-01). CA-A-12 exige además las pruebas estáticas obligatorias de A, y TA-09 es una de ellas.

**H-F3 — P2 · CA-A-06/CA-A-08 no quedan literalmente acreditados.**
`test_el_instalador_copia_todo_lo_que_importa_el_auxiliar`
(`tests/test_ops4_aislamiento.py:73-84`) es una **lista fija de cuatro
módulos** con comprobación de subcadena en el instalador, no un cálculo del
cierre transitivo comparado con la lista/modos de copia; no incluye los
imports del finalizador y `test_instalar_ops4.py:46-49` sigue comprobando tres
módulos (el escritor solo por subcadena en la barrera nueva). La spec exige que
«cualquier diferencia haga fallar la prueba».

**H-F4 — P2 · La documentación no cuenta aún la verdad del SHA (A5/CA-A-10) y
el delta introduce incoherencias nuevas.** En el árbol de `f34c30ba`:

- **Enlace roto nuevo**: `ops4-protocolo-v4.md:25` apunta al módulo retirado;
  el mismo documento conserva «21 casos» (`:37`; hoy 12) y «No hay socket,
  ruta web, auxiliar ni unidad» (`:42`).
- `ops4-matriz-evidencia.md:11`: dos repeticiones históricas distintas dicen
  ahora ambas «8947/2454»; cita 37 enlaces a tests de los que **23 no existen**
  (más documentos retirados); `:40` describe `test_ops4_protocolo_v4.py` como
  si aún probara replay y consumo durable real, retirados en este delta.
- `ops4-validacion-suite-2026-11-20.md:24` y `:117` dicen 8947/2454, pero
  `:91` mantiene «se repitió después de esta corrección: 8880/2431»: el mismo
  hito tiene dos resultados contradictorios.
- `ops4-instalador.md:24` «8 casos» (hoy 11); `ops4-autorizacion-app-host.md:92`
  «47 de registro durable» y `:96-97` «el contrato permanece sin importar».
- Frases de estado obsoletas sin tocar: `ops4-transporte-v4.md:4,34`,
  `ops4-solicitud-v4.md:4`, `ops4-autorizacion-app-host.md:7`; docstrings de
  módulos instalados que dicen «no instalado/no conectado»
  (`registro_repeticiones_ops4.py:1`, `zascarr_actualizar_aux.py:2,7`,
  `clave_autorizacion.py:1`, `estado_actualizacion.py:3`).
- `docs/adr/0026:51` sigue enlazando `secops-ops4-verificacion-final-2026-11-21.md`,
  que no está en el árbol.
- El **cuerpo de la PR** sigue declarando «8922 passed / 2454 skipped» y «364
  passed»; solo un comentario lleva 8947/389 (CA-A-12/A10).

**H-F5 — P2 · A4/CA-A-09 parcial.** El delta añadió la nota «Desviación de
Compose» en ADR 0026 (`:54-58`), pero la spec A4 pedía también la nota en
`ops4-ui-integracion.md` (no está) y CA-A-09 exige prueba estática de que el
ADR/doc contienen la nota y de que ninguna otra variable `OPS4_*` cambia de
valor; TA-09 no lo comprueba.

**H-F6 — P2 · A6/CA-A-11 no consta para el SHA final.** En el árbol de
`f34c30ba` no hay dictamen SecOps de `f34c30ba` (el versionado dictamina
`3aa4ec16` y se declara caducado con cualquier commit). Tampoco hay enlace al
dictamen en la PR; la PR sigue **draft** (`draft: true` al cierre). Existe un
informe SecOps del SHA final escrito por otro rol **fuera del árbol rastreado**
(nota de cierre); no forma parte del SHA ni de la PR en el momento de esta
auditoría. Además, cualquier commit para versionarlo cambia el SHA y exige
re-dictamen (paradoja A6/CF-3, ver C-F5).

**H-F7 — P3 · Ruff local de tests tocados falla (nuevo).** E501
(102 > 100) en `tests/test_ops4_aislamiento.py:88`; como CI solo lintea `src/`,
CI sigue verde, pero la afirmación «Ruff sobre los ficheros tocados» deja de ser
cierta en este SHA (el árbol anterior la tenía limpia).

**Sin hallazgos (positivo).** No hay defecto de ejecución con la bandera
apagada; el delta **reduce** superficie (módulo no instalado fuera de
`deploy/ops`), no añade rutas, no toca claves/sockets/permisos, no migra y no
habilita nada. El doble de host no se instala ni se recoge como test. La suite
dirigida y la CI del SHA están verdes.

---

## 5. Condiciones

**Para fusionar apagado (GO condicionado; solo tests/docs/evidencia, ninguna
abre ruta de ejecución):**

1. **C-F1 (CA-A-06/CA-A-08/registro).** Completar o aceptar por escrito como
   deuda caducable: (a) portar la separación explícita de prefijos
   `autorizacion-`/`solicitud-` y las negativas de
   `abrir_directorio_autorizaciones` (`uid`/modo/enlace/fichero/inexistente);
   o parametrizar la suite nueva para el namespace vivo; (b) barreras «el
   emisor no hace E/S ni red», «el verificador no lee hashes/BD»;
   (c) sustituir la lista fija por un test que **calcule el cierre transitivo**
   de imports de los entrypoints (auxiliar y finalizador) y lo compare con la
   lista/modos del instalador.
2. **C-F2 (CA-A-10/A5).** Corregir el enlace roto nuevo
   (`ops4-protocolo-v4.md:25`), los recuentos («21 casos», «8 casos», «47 de
   registro»), las frases de estado y docstrings, los 23 enlaces muertos de la
   matriz, el enlace de ADR 0026 y la narrativa de recuentos contradictoria
   (`matriz:11`, `validacion-suite:24/91/117`); actualizar el cuerpo de la PR.
   Alternativa admitida por los informes previos: declarar la deuda documental
   por escrito en la PR/merge.
3. **C-F3 (TA-09/A7).** Añadir a `test_ops4_alcance_apagado.py` la ausencia de
   migración Alembic nueva y de `.env` de producción, y arreglar la aserción
   vacua de `update.sh`; o declararlo.
4. **C-F4 (Ruff local).** Corregir el E501 de
   `tests/test_ops4_aislamiento.py:88` o dejar constancia de que CI no lintea
   `tests/` (no bloquea CI).
5. **C-F5 (A6/CA-A-11 y SHA).** Registrar y enlazar desde la PR el dictamen
   SecOps del SHA que se fusiona (o un addendum firmado para este delta de
   tests/docs + retirada de módulo no instalado), marcar la PR «ready» y
   re-ejecutar CI sobre el merge ref del `origin/main` vigente (`3ce1bd5e`);
   hoy ese merge ref no está probado. Si se añade cualquier commit, el SHA
   cambia y el dictamen/CI deben repetirse.
6. **C-F6 (acto de fusión).** La fusión **no** debe ejecutar el instalador (ni
   `--dry-run` sobre host real), `--activar`, `systemctl start/enable`,
   `update.sh`, ni tocar `.env`, Compose desplegado, systemd, Pi o Docker; no
   poner `OPS4_ACTUALIZACION_HABILITADA=true`. El mensaje de merge debe decir
   «integrada, apagada por defecto; habilitar exige B1–B10, CE, revisión
   SecOps y autorización expresa».

**Para habilitar (NO-GO absoluto):** B1–B10 implementadas y verificadas,
CE-1…CE-12 e I-1…I-9 resueltas/declaradas, B4 (host aislado con `update.sh`
real, Docker/PostgreSQL y systemd desechables), migración de estado 1→2 y
reconciliación, reserva atómica del cerrojo, sandbox/refresco, UI de último
intento (B7), runbook de activación y el cierre de los P1 de la ruta
encendida del informe anterior (formulario con `auth_mode=password`,
`auth none`, `pollVersion`, copy de resultado) y probarla; dictamen SecOps del
SHA final y autorización expresa del PO. Nada de esto se autoriza aquí.

---

## 6. NOT RUN (declarado, no PASS)

- **Suite completa** y **Python 3.11 en local**: no ejecutadas por esta QA (la
  tarea lo prohíbe). Solo se ejecutó la selección dirigida (389) y la
  colección completa (11401). La cifra 8947/2454 es la declarada/calculada, no
  reproducida aquí.
- **PostgreSQL real local**, Docker real local, `TEST_DATABASE_URL`: no
  ejecutados; el job de CI del SHA sí está verde.
- **CI del merge ref actual** (`f34c30ba` + `origin/main` local `3ce1bd5e`):
  NOT RUN; la CI observada usó la base de las 19:18Z (`9fe0be06`). Recuentos
  de CI: no extraídos (API de logs requiere auth).
- `systemd-analyze verify`; systemd del host; socket/unidad reales; instalador
  sobre host real o Pi (con y sin `--activar`); `update.sh` real; Pi; navegador
  real y anchos 1280/375; lector de pantalla; cobertura (`coverage`); cualquier
  despliegue, provisión de clave o cambio de `.env`/Compose desplegado.
- **Socket real contra el `procesar` real**: el E2E de UI sigue usando el doble
  `admitir_v4`; la ruta app→host real es de habilitación.
- **Dictamen SecOps del SHA final**: no versionado en `f34c30ba` (ver H-F6 y
  nota de cierre).

---

## 7. Nota de cierre (worktree compartido)

Todas las ejecuciones de prueba/ruff y la colección de esta QA se hicieron con
el árbol rastreado limpio del SHA `f34c30ba` (comprobado `git status
--porcelain` vacío a las 19:22Z). Al terminar la sesión aparecieron en el
worktree cambios **no rastreados/ajenos a este SHA** de otros roles:

- `?? docs/design/secops-ops4-b-final-f34c30ba-2026-11-22.md` (20:26 local):
  informe SecOps del SHA final, fuera del árbol versionado.
- `M docs/adr/0026-actualizacion-manual-confianza-main.md` (ADR 0026),
  `M docs/design/ops4-instalador.md`, `M docs/design/ops4-protocolo-v4.md`,
  `M tests/test_ops4_aislamiento.py` (20:31:58 local): correcciones en curso
  del enlace de ADR, «11 casos», enlace de protocolo y E501.

**No están auditadas**: no forman parte de `f34c30ba` y este informe no las
cubre. Si se commitean, el SHA cambia y C-F5/A6 exigen revalidación del SH nuevo
(árbol limpio, CI y dictamen). El dictamen SecOps no rastreado **no** se
considera constancia en el SHA para CA-A-11.

**Gestión:** único fichero escrito por esta QA: este. No se modificó código ni
se ejecutó nada del host. **Este informe no concede GO de habilitación ni de
despliegue**; el GO de fusión apagada queda condicionado a C-F1…C-F6 y a la
decisión del PO. La actualización sigue integrada y **deshabilitada por
defecto**.
