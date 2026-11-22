# Entender a qué momento vuelve la recuperación (UATP-08 / #1146)

> **Estado:** implementación TDD (task-70/71, 2026-11-22). `restaurar_datos.sh` persiste de forma
> aditiva `recuentos_previos`, `fuera` (solo diferencias no negativas), `comprobaciones` cerradas y
> `version_arrancada` (leída de `/api/health` tras el arranque); `copias.json` y la UI exponen la
> versión, el alcance y el resumen estable. Queda **NOT RUN** la evidencia real de navegador y
> restauración sobre una instalación; no se declara la historia cumplida sin ella.
>
> **Decisiones:** D-1…D-5 de §3 son **recomendaciones de SPEC.writer**. No están aprobadas por el PO
> y no autorizan implementar por sí solas. La opción recomendada va primero en cada decisión.
>
> **Insumos:** [#1146 · UATP-08](https://github.com/juanajok/zascarr/issues/1146) (abierta),
> [#1141 · épica UATP](https://github.com/juanajok/zascarr/issues/1141) (abierta),
> [#1145 · UATP-07](https://github.com/juanajok/zascarr/issues/1145) (**cerrada** el 2026-11-22),
> [#1144 · UATP-06](https://github.com/juanajok/zascarr/issues/1144) (**cerrada** el 2026-11-22),
> [`docs/design/uatp08-readiness.md`](uatp08-readiness.md) (readiness previo, 2026-11-21),
> [`docs/design/uatp06-07-recuperacion.md`](uatp06-07-recuperacion.md) (spec de UATP-06/07),
> [`docs/uat/A6/resultado.md`](../uat/A6/resultado.md) (evidencia real A6, **PASS** 25/25
> comprobaciones obligatorias; único `NOT RUN`: `N-01-systemd-host`).
>
> **Base leída:** `origin/main` = **`9fe0be06`** (2026-11-22), con A6 ya fusionada
> (`c4eff468`, 2026-11-22) y UATP-07 fusionada (`2c773e53`, 2026-11-22). **El checkout local puede
> estar atrasado** (esta spec se escribió con el árbol en `3eb38cd2`): el implementador debe
> ramificar desde `origin/main`, no desde una copia local, y comprobar que existen
> `docs/uat/A6/` y los campos de UATP-07 del §1.1.
>
> **Escritura:** solo `docs/design/uatp08-momento-recuperacion.md`. Sin código, sin tests, sin
> `docs/BACKLOG.md`, sin ADR y sin tocar la evidencia A6.

---

## 0. Resumen ejecutivo

**Lo que ya existe (leído en `origin/main@9fe0be06`).** UATP-07 dejó los **datos** que UATP-08
necesita, pero no la capa que los explica:

- el manifiesto de cada copia nueva lleva
  `version_de_la_copia = {head, build_sha, app_version, alembic}` (`scripts/_comun.sh::escribir_manifiesto`);
- `ops-restaurar.json` lleva `intento` (16 hex), `comprobacion` (código cerrado) y `copia_version`
  (tupla saneada o `null`) (`scripts/restaurar_datos.sh::estado_restaurar`);
- la restauración real de A6 dejó un estado `hecha` con la tupla completa, y un fallo real por la
  interfaz (`copia_no_valida` / `sha256_copia`) que la persona vio como «Esa copia está dañada…»;
- **la interfaz sigue sin pintar nada de eso**: la lista muestra fecha relativa y tamaño; la
  confirmación, «Vas a volver a los datos del {fecha}» sin año ni hora; el resultado, tres
  recuentos y una causa; no hay «fuera de la copia», ni comprobaciones, ni versión que arrancó, ni
  identidad de intento. `copias.json` **no** lleva la versión: solo `revision` (Alembic).

**Lo que añade UATP-08.** Una capa de producto, sin migración y sin dependencias:

1. **Antes de confirmar:** fecha y hora **absolutas con año** (zona del servidor), versión de la
   copia —`head`/`build_sha`/`app_version`/Alembic, o «no consta»—, alcance honesto (la copia trae
   el catálogo; **no** trae los archivos de la biblioteca, las portadas ni la configuración) y
   aviso de qué cambios posteriores se pierden.
2. **Después de reiniciar:** ruta estable `/ui/copias/restauracion` con el resumen: copia y fecha,
   recuperado (series/números/archivos **anotados**), **fuera de la copia** con los recuentos de
   antes y después (lo que UAT-31 necesita), versión que arrancó, comprobaciones que sustentan el
   resultado y, en fallo, diagnóstico con identidad de copia e intento y próximo paso.
3. **Contrato aditivo** en `copias.json`, `ops-restaurar.json` y `/api/health`, con listas cerradas
   y sin rutas, secretos ni hashes de contenido en la superficie.

**Veredicto.** UATP-08 es **especificable hoy** porque UATP-07 está cerrada con A6 y la versión ya
existe. **No es acreditable hoy**: las cinco decisiones de §3 están pendientes, no hay
implementación y UAT-31 no se ha ejecutado. Este documento **no** dice que UATP-08 esté cumplida, ni
parcialmente.

---

## 1. Problema y resultado esperado

### 1.1 Lo que ya existe y se puede usar como insumo

| Pieza | Dónde | Estado | Qué aporta a UATP-08 |
|---|---|---|---|
| Tupla de versión de la copia | `scripts/_comun.sh::escribir_manifiesto` (manifiesto, `schema: 1`) | **PASS** (leído y en A6) | `head`, `build_sha`, `app_version`, `alembic`; `null` = «no consta»; nunca bloquea la copia |
| `intento`, `comprobacion`, `copia_version` | `scripts/restaurar_datos.sh::estado_restaurar` | **PASS** (leído y en A6) | identidad del intento, comprobación que falló y versión de la copia en el estado de la restauración |
| Registro por intento | `ops-restaurar-intentos.jsonl` (máx. 20) | **PASS** (A6) | auditoría de soporte; UATP-08 puede leerlo o no (recomendado: **no** en esta historia) |
| Estado `hecha` real | `docs/uat/A6/evidencia/ops-restaurar-n04.json` | **PASS** | `copia_version` completa + `recuentos` 2/2/2 |
| Fallo real por interfaz | `docs/uat/A6/evidencia/pasada2/n01-ui-resumen.txt` | **PASS (ensayo)** | `fallida` / `copia_no_valida` / `sha256_copia`; la persona ve «Esa copia está dañada… Elige otra.» |
| Versión declarada de la candidata | `docs/uat/A6/resultado.md` | **PASS** | `tag_commit = head = build_sha = 2c773e53…`, `app_version=1.15.1`, `alembic=0052` |
| Fecha/hora y formato | `src/zascarr/services/ops_host.py:270-291` | **PASS** (leído) | `hora_llana` relativa y `_dia_llano` sin año; hay que añadir la absoluta |
| Lista de copias | `ops_host.py:401-423`, `_copias_items.html:9` | **PASS** (leído) | fecha relativa, tamaño, disco; `revision` calculada pero no pintada; **sin versión** |
| Confirmación | `_restaurar_confirmar.html:5-6,16-18` | **PASS** (leído) | fecha relativa y genérica; sin versión ni alcance; «cambios posteriores» sin ejemplos |
| Resultado y fallo | `ops_host.py:449-480,519-578`, `_copias_estado.html:11-14` | **PASS** (leído) | causa+acción; recuentos solo al final; sin versión, sin comprobaciones, sin identidad de intento |
| `copias.json` | `scripts/_comun.sh:366-397`; `especificacion-BL-OPS1.md:191-193` (FR-16) | **PASS** (leído) | `id`, `creada_epoch`, `bytes`, `fuera_del_disco`, `verificada`, `revision`; **FR-16 prohíbe hashes** |

### 1.2 Lo que falta y es exactamente UATP-08

| Hueco (del readiness) | Qué se ve hoy | Qué exige #1146 | Lo cubre |
|---|---|---|---|
| Fecha/hora absoluta (S1-01) | «hoy/ayer/el 4 de noviembre»; el éxito, sin año ni hora | «identifica la copia con fecha» | AC-08-01 |
| Versión de la copia (S1-02) | Nada en la confirmación; `revision` sin pintar; `version_de_la_copia` no llega a la app | «…y versión» | AC-08-02; D-1 |
| Alcance catálogo/archivos (S1-04) | «Tu biblioteca, tus archivos y el acceso no cambian» (ambiguo) | «indica el alcance de catálogo y archivos» | AC-08-03 |
| Cambios posteriores (S1-05) | «Se perderán los cambios posteriores» sin un solo ejemplo | «advierte qué cambios posteriores podrían perderse» | AC-08-04 |
| Resumen tras reiniciar (S1-06) | Un mensaje en `/estado`; el POST solo dice «en marcha» | «un resumen utilizable distingue recuperado, omitido y fallo» | AC-08-05/06/07 |
| Fuera de la copia con magnitud | No existe | «por qué esa fila quedó fuera» (UAT-31) | AC-08-07/08; D-4 |
| Versión que arrancó (S1-03) | No se registra; solo la versión actual de la app | «la versión que volvió a arrancar» | AC-08-09; D-3 |
| Comprobaciones (S1-07) | Solo 3 recuentos; el script comprueba 9+ cosas | «qué comprobaciones sustentan el resultado» | AC-08-10; D-2 |
| Fallo con identidad (S1-08) | causa+acción, pero sin copia, fecha absoluta, versión ni intento | «diagnóstico y próximo paso… aunque se haya recuperado parte» | AC-08-11 |
| Robustez y accesibilidad | No hay pantalla; no hay criterio | CA1–CA3, U21, CLAUDE.md §6 | AC-08-12/13 |

### 1.3 Resultado esperado

La persona que va a restaurar entiende **a qué momento vuelve** antes de escribir la contraseña:
qué copia es (fecha, hora, versión), qué contiene y qué no, y qué se pierde. Después del reinicio
encuentra, sin leer logs ni JSON, un resumen que distingue **recuperado / fuera de la copia / fallo**,
dice qué versión arrancó y qué se comprobó, y —si falló— identifica el intento y ofrece el siguiente
paso. UAT-31 se acredita cuando una persona explica, **a partir del resumen**, por qué una fila
añadida después de la copia quedó fuera.

---

## 2. Alcance / no alcance

### 2.1 Dentro

| Pieza | Qué cambia |
|---|---|
| `src/zascarr/services/ops_host.py` | `fecha_absoluta`; `leer_copias` con versión y fecha absoluta; `VistaRestaurar` con `copia`, `copia_epoch`, `copia_version`, `recuentos_previos`, `version_arrancada`, `intento`, `comprobacion`, `comprobaciones`; validación cerrada y tolerante |
| `src/zascarr/web/copias.py` | `GET /ui/copias/restauracion` (ruta estable, solo lectura, `no-store`) y enlaces desde Estado; la confirmación y la lista usan los campos nuevos |
| Plantillas | `_copias_items.html`, `_restaurar_confirmar.html`, `_copias_estado.html`, `_restaurar_resultado.html`, `login.html`, `_componentes.html` y **nueva** `restauracion_resumen.html` |
| `src/zascarr/api/health.py` | Añade `build_sha` (string o `null`) al payload de `/api/health` para que el script capture la versión que arrancó (D-3; si el PO prefiere no ampliar el payload, la alternativa es leer `BUILD_SHA` del contenedor) |
| `scripts/_comun.sh` | `escribir_copias_json` copia la tupla saneada del manifiesto a cada entrada de `copias.json` |
| `scripts/restaurar_datos.sh` | `recuentos_previos`, `version_arrancada` y `comprobaciones` en `ops-restaurar.json`; sin tocar la semántica de fases ni la seguridad |
| Tests | Ver §7; actualización de los tests de contrato existentes (`test_copias_json.py`, `test_copias_ops.py`) y nuevos casos |
| Docs | Enmienda de FR-16/AC-21 (BL-OPS1), FR-24/FR-29/FR-32 (BL-OPS2), `docs/TESTING_E2E.md` (bloque UATP-08/UAT-31), `docs/uat/A6/` (pasada 3), `docs/BACKLOG.md` al cerrar y `docs/design/ui-migracion.md` (inventario de plantillas) |

### 2.2 Fuera de alcance (explícito)

- **Restaurar los archivos de la biblioteca desde ZascArr.** BL-OPS2 solo restaura el catálogo; la
  copia de archivos es el procedimiento manual de UATP-07 (`docs/TESTING_E2E.md` §17.4). UATP-08 solo
  **declara** que quedan fuera.
- **Escanear o medir la biblioteca** al pintar. Ni `du`, ni `find`, ni consultar disponibilidad. En
  la Pi eso paga el presupuesto de RAM/IO y mezcla «restaurar la base» con «restaurar los CBZ».
- **Medir qué filas concretas cambiaron** después de la copia. Los recuentos pre/post dan magnitud,
  no identidad; una fila borrada y otra añadida pueden dejar el mismo total. Se declara el límite
  (§9).
- **Borrar copias, retención, «deshacer» una restauración, actualizar el código o desplegar.**
- **Migraciones, dependencias nuevas, JS nuevo o build de Node.**
- **Cambiar la decisión de BL-OPS2** (solo catálogo; contraseña vigente; biblioteca intacta) ni el
  estado de ADR 0023 (sigue «propuesto. No desplegado»).
- **Acreditar UATP-08 sin ejecutar UAT-31** o reutilizar la evidencia de UATP-07 como si fuera la de
  esta historia.
- **Arreglar `N-01-systemd-host`** (NOT RUN de A6 por falta de root/systemd en el host aislado): es
  infraestructura del host, no UATP-08.

### 2.3 No-goals de producto

No se promete una lista exacta de lo que se pierde, ni un «catálogo parcial», ni restaurar archivos,
ni conservar cambios posteriores, ni identificar la fila concreta de UAT-31. Tampoco se muestra la
contraseña, el hash de la contraseña, `secret_key`, rutas, nombres de fichero ni la salida de los
scripts.

---

## 3. Decisiones D-1…D-5 (recomendaciones; decide el PO)

> Ninguna decisión está aprobada. Sin decisión, la implementación no empieza. Si el PO rechaza una
> recomendación, se aplica la opción elegida y se ajustan AC/tests; el resto del documento sigue
> siendo el marco.

### D-1 — ¿Cómo llega la versión de la copia a la lista y a la confirmación?

**Pregunta.** La tupla `{head, build_sha, app_version, alembic}` existe en el **manifiesto**, pero el
contenedor de la app solo tiene montado el directorio de estado (`/run/backup-status`), **no**
`BACKUP_DIR`: no puede leer el manifiesto. `copias.json` es el único puente, y FR-16/AC-21 dicen
«sin hashes».

**Opciones.**

- **(a) Ampliar `copias.json` con `version_de_la_copia` (recomendada).** Cada entrada gana la tupla,
  copiada del manifiesto y **saneada** por `escribir_copias_json`. Se enmiendan FR-16 y AC-21 para
  distinguir «hashes de contenido o de archivos» (siguen prohibidos) de «identidad de versión del
  código» (la tupla, admitida). La lista muestra `app_version` + revisión (compacto); la
  confirmación muestra la tupla completa, con `head`/`build_sha` en el detalle técnico colapsado.
  Es la única opción que permite cumplir CA1 con la tupla **antes** de confirmar.
- **(b) Solo `app_version` y `revision` en `copias.json`.** No añade hashes; la lista/confirmación
  muestran «1.15.1 · revisión 0052» y la confirmación no puede enseñar `head`/`build_sha`. CA1 queda
  **débil**: no se identifica el build; «1.15.1» no es la identidad (ADR 0025).
- **(c) No mostrar versión; solo fecha.** No cumple CA1. **No recomendada.**
- **(d) Fichero nuevo `copias-version.json`.** Evita tocar FR-16, pero crea un contrato y una
  sincronización nuevos entre dos ficheros que pueden desincronizarse. Peor que (a).

**Recomendación: (a).** **Consecuencia:** enmienda documental de FR-16/AC-21; cambio en
`scripts/_comun.sh`; actualización de `tests/test_copias_json.py:64`; ningún cambio de esquema ni de
seguridad. Si el PO elige (b), el AC-08-02 se acredita de forma parcial y la spec debe decirlo; el
resto del resumen (post-restaurar) sigue mostrando la tupla desde `ops-restaurar.json`.

**Afecta a:** `scripts/_comun.sh`, `scripts/backup.sh` (solo llama), `services/ops_host.py`,
`web/copias.py`, `_copias_items.html`, `_restaurar_confirmar.html`, tests de FR-16,
`docs/design/especificacion-BL-OPS1.md` (FR-16/AC-21).

### D-2 — ¿Cómo se exponen las comprobaciones que sustentan el resultado?

**Pregunta.** El script comprueba integridad, formato, tablas, revisión, seguridad, copia previa,
recuentos genéricos, vínculos huérfanos y health, pero solo persiste **la comprobación que falló**
(`comprobacion`). Para el éxito no queda constancia de qué se ejecutó, y `codigo_manifest` **no se
ejecuta** en `--produccion`: decir «todo comprobado» sin matiz sería falso.

**Opciones.**

- **(a) Persistir `comprobaciones` (recomendada).** Array cerrado de 14 entradas
  `{codigo, estado}` (`ok | fallo | no_ejecutada`) en `ops-restaurar.json`, escrito por el script al
  terminar. La UI resume en llano («se comprobó la copia y la base restaurada») y el detalle
  colapsado enseña cada código con su estado. `comprobacion` se conserva para compatibilidad (el
  primer fallo de contenido) y debe coincidir con el `fallo` del array.
- **(b) Derivar del estado existente.** Con `resultado`, `fase` y `comprobacion` se puede inferir
  «las anteriores ok, la que falló fallo, las posteriores no ejecutadas», pero exige codificar en el
  lector el orden interno del script (acoplamiento frágil) y no distingue `codigo_manifest` en
  producción. **Descartada.**
- **(c) Solo `comprobacion`.** No cumple CA2 («qué comprobaciones sustentan el resultado»).
  **Descartada.**

**Recomendación: (a).** **Consecuencia:** una tabla cerrada de códigos en esta spec (§4.5), un
escritor de array en el script y un lector tolerante; sin coste en Pi (14 entradas). **Afecta a:**
`scripts/restaurar_datos.sh`, `services/ops_host.py`, `restauracion_resumen.html`, tests del script y
del lector.

### D-3 — ¿Qué es «la versión que arrancó» y cómo se conserva?

**Pregunta.** CA2 pide «la versión que volvió a arrancar». La app actual reporta `version` en
`/api/health` (semver, hoy `1.15.1`), pero **no** el build; y si la app se actualiza después de
restaurar, leer la versión en el momento de pintar el resumen mentiría sobre lo que arrancó.

**Opciones.**

- **(a) Persistir `version_arrancada` como tupla (recomendada).**
  `{head, build_sha, app_version, alembic}`, capturada por el script **al confirmar el health** de la
  restauración: `head` = `HEAD_ANTES` (ya validado), `alembic` = la revisión restaurada (ya leída),
  `app_version` = `version` de `/api/health`, `build_sha` = `build_sha` de `/api/health` (campo nuevo
  y aditivo, o `BUILD_SHA` del contenedor si el PO prefiere no tocar el payload). Solo en `hecha`; si
  no se puede leer, `null` y «no consta» (nunca se bloquea ni se infiere).
- **(b) Solo `app_version` desde health.** Barato, pero no identifica el build y contradice la regla
  de UATP-07 («nunca solo 1.15.1»; R-14). CA2 quedaría débil.
- **(c) Pintar la versión actual de la app al leer el resumen.** Fácil, pero si se actualizó después
  el resumen dice una versión que **no** fue la que arrancó. **Descartada.**
- **(d) Leer `BUILD_SHA` con un `docker exec` extra.** Sin cambio de payload; añade un evento de
  contenedor y una lectura más. Aceptable como alternativa si SecOps prefiere no publicar
  `build_sha` en `/api/health`.

**Recomendación: (a).** Si el PO/SecOps prefiere no ampliar `/api/health`, (a) con la fuente de (d).
**Consecuencia:** `api/health.py` añade `build_sha` (nulo si no consta; ADR 0025 ya publica el SHA en
`/estado`), el script persiste la tupla en `ops-restaurar.json`, el lector la valida y el resumen la
muestra. **Afecta a:** `api/health.py`, `restaurar_datos.sh`, `ops_host.py`, `tests/test_health.py`,
tests del script.

### D-4 — ¿Qué alcance de catálogo y archivos se declara, y cómo se explica UAT-31?

**Pregunta.** La copia contiene solo la base de datos. La biblioteca (CBZ/CBR/PDF/EPUB), las
portadas y la configuración del equipo quedan fuera. ¿Se declara «sin medir», se mide el disco o se
miden los cambios posteriores con recuentos?

**Opciones.**

- **(a) Declaración honesta + recuentos pre/post desde la copia de seguridad previa (recomendada).**
  Texto fijo de alcance (catálogo sí; archivos/portadas/configuración no; ZascArr no toca la
  biblioteca) y, para los cambios posteriores, dos juegos de recuentos **que el script ya tiene**:
  `recuentos` (lo que trae la copia) y `recuentos_previos` (lo que había en la base viva al
  restaurar, leído de la inspección del dump `rollback-safety`, sin consultas nuevas ni escaneo). El
  resumen muestra ambos y dice «lo anotado después de la copia no vuelve». Es lo que permite que
  UAT-31 se explique desde el resumen: si después de la copia se añadió una fila, los recuentos
  previos son mayores; la fecha de la copia y la diferencia lo hacen comprensible.
- **(b) Solo declaración, sin cifras.** Texto correcto, pero UAT-31 se queda en «porque la copia es
  anterior» sin magnitud; CA2 no pide cifras de cambios, pero la prueba de cierre sí se vuelve
  explicativa a medias. Es la recomendación del readiness D-4(a) antes de tener UATP-07.
- **(c) Escanear o medir la biblioteca** para decir cuántos archivos «faltan». Confunde «restaurar
  la base» con «restaurar los CBZ», puede costar caro en la Pi y da resultados aproximados.
  **Descartada** para esta historia.

**Recomendación: (a).** La lista de «fuera de la copia» es **cerrada y de producto** (§4.6); no se
persiste un array `omitido` mientras todos sus `n` sean `null`, para no crear una verdad duplicada
que nunca varía. Si el PO quiere medir archivos, es otra historia (con presupuesto de Pi).
**Consecuencia:** `recuentos_previos` en `ops-restaurar.json` (desde `inspeccionar` del dump de
seguridad, que ya se ejecuta), textos de confirmación y resumen, UAT-31 en §8. **Afecta a:**
`restaurar_datos.sh`, `ops_host.py`, plantillas, AC-08-03/04/07/08, UAT-31.

### D-5 — ¿Dónde vive el resumen después de reiniciar?

**Pregunta.** Durante la restauración la app se para y se reinicia; el POST solo puede decir «en
marcha». ¿Dónde lee la persona el resultado final, sin depender de que no cierre la pestaña?

**Opciones.**

- **(a) Ruta estable `/ui/copias/restauracion` + enlaces (recomendada).** `GET` sin efectos, bajo la
  autenticación existente, `Cache-Control: no-store`; lee `ops-restaurar.json` y pinta el resumen o
  el diagnóstico. Enlaces desde el bloque de Estado (cuando hay estado terminal) y desde el aviso de
  `/login` (con `next` para que, tras entrar, se aterrice en el resumen). El bloque compacto de
  `/estado` se conserva.
- **(b) Solo el bloque de `/estado`.** Menos trabajo, pero la persona tiene que volver a Estado; el
  aviso de `/login` sigue sin enlace y el resumen queda enterrado si no se vuelve.
- **(c) Página solo cuando hay fallo.** El éxito se queda en Estado; CA2 pide resumen también en
  éxito. **Descartada.**

**Recomendación: (a).** **Consecuencia:** ruta nueva en `web/copias.py`, plantilla
`restauracion_resumen.html`, enlaces en `_copias_estado.html` y `login.html`, pruebas de auth y
`no-store`. Sin migración. **Afecta a:** FR-29/FR-32 de BL-OPS2 (aditivo), navegación de Estado,
`docs/design/ui-migracion.md`.

### 3.6 Resumen de decisiones

| ID | Decisión | Recomendación | Bloquea |
|---|---|---|---|
| D-1 | Versión de la copia en lista/confirmación | Ampliar `copias.json` con la tupla + enmienda FR-16/AC-21 | AC-08-02, CA1 |
| D-2 | Comprobaciones | Persistir `comprobaciones` cerradas en `ops-restaurar.json` | AC-08-10, CA2 |
| D-3 | Versión que arrancó | Persistir tupla al confirmar health (con `build_sha` de health) | AC-08-09, CA2 |
| D-4 | Alcance y cambios posteriores | Declaración + `recuentos_previos` desde el dump de seguridad | AC-08-03/04/07/08, UAT-31 |
| D-5 | Dónde vive el resumen | Ruta estable + enlaces desde Estado y `/login` | AC-08-05, CA2 |

---

## 4. Contrato de datos propuesto

> **Propuesta, no aprobada.** Aditiva, sin migración. Respeta las invariantes de BL-OPS1/2: los
> ficheros de estado los escribe **solo** el host; la app solo lee; nada de rutas, nombres de fichero,
> hashes de contenido, secretos ni texto libre; escritura atómica (`temporal` + `mv`), `0644`; el
> lector tolera claves desconocidas y tipos erróneos. `schema` sigue en **1** en los dos ficheros
> (como UATP-06/07; no se sube a 2).

### 4.1 Principios

1. **Solo listas cerradas, números, booleanos y `null`.** Nada de cadenas libres del fichero al HTML.
2. **Nada de hashes de contenido en la superficie.** La única excepción son `head`/`build_sha` de
   `version_de_la_copia`/`version_arrancada`: son **identidad del código**, no del dump ni de los
   archivos, y solo se admiten dentro de esos objetos (D-1/D-3). El `sha256` del dump y los hashes de
   archivos siguen prohibidos.
3. **Compatibilidad hacia atrás.** Copias/estados antiguos sin un campo → `null` → «no consta»;
   nunca se infiere.
4. **Sin coste en Pi.** El resumen se compone de ficheros pequeños ya existentes; no escanea la
   biblioteca ni consulta la base para pintar. `recuentos_previos` se obtiene de una inspección que
   el script ya hace.
5. **El script es el único escritor** de `ops-restaurar.json` y `copias.json` (este último vía
   `backup.sh`); la app no escribe estado de operaciones.

### 4.2 `copias.json` (D-1)

Se conserva la lista cerrada de FR-16 y el campo `revision`. Se **propone** añadir, a cada entrada:

| Campo | Tipo | Regla |
|---|---|---|
| `version_de_la_copia` | objeto o `null` | **Siempre presente** como clave. Objeto con exactamente `{head, build_sha, app_version, alembic}`; cada valor con su regex o `null`; si el objeto no es válido, `null`. |

- `head` y `build_sha`: `^[0-9a-f]{40}$`; `app_version`: `^[0-9]+\.[0-9]+\.[0-9]+$`; `alembic`:
  `^[0-9]{4}$`.
- Lo escribe `escribir_copias_json` copiando y **saneando** `version_de_la_copia` del manifiesto; un
  manifiesto sin la clave (copias anteriores a UATP-07) deja `null`.
- Siguen prohibidos: `ruta`, `backup`, `sha256` del dump, `origin`, `commit` suelto, nombres de
  fichero. `head`/`build_sha` van **solo** dentro del objeto de versión.
- La enmienda de FR-16/AC-21 (BL-OPS1) se redacta así: «…cada una con `id`, `creada_epoch`, `bytes`,
  `fuera_del_disco`, `verificada`, `revision` y `version_de_la_copia` (identidad del código de la
  copia o `null`). **Sin rutas, sin nombres de fichero y sin hashes de contenido ni de archivos**; la
  identidad de versión del código no es un hash de contenido y se admite solo dentro de ese objeto.»
- Se mantiene: hasta 30 entradas, las más recientes; sin `update_*` ni `rollback-safety_*`; `0644`;
  atómico; nunca hace fallar la copia.

Ejemplo:

```json
{
  "schema": 1,
  "copias": [
    {
      "id": "backup-20261122_131744",
      "creada_epoch": 1795349857,
      "bytes": 17818,
      "fuera_del_disco": false,
      "verificada": true,
      "revision": "0052",
      "version_de_la_copia": {
        "head": "2c773e53c235812adabc76e76cd3b111d04d4026",
        "build_sha": "2c773e53c235812adabc76e76cd3b111d04d4026",
        "app_version": "1.15.1",
        "alembic": "0052"
      }
    },
    {
      "id": "backup-20260110_040000",
      "creada_epoch": 1768010400,
      "bytes": 16890,
      "fuera_del_disco": true,
      "verificada": true,
      "revision": "0038",
      "version_de_la_copia": null
    }
  ]
}
```

### 4.3 `ops-restaurar.json` (D-2/D-3/D-4)

Se conserva `schema: 1` y **todos** los campos actuales, incluidos los de UATP-06/07:
`copia`, `copia_epoch`, `inicio_epoch`, `actualizado_epoch`, `fase`, `resultado`, `error`,
`base_en_su_sitio`, `recuentos`, `intento`, `comprobacion`, `copia_version`.

Campos nuevos (aditivos, cerrados, sin texto libre):

| Campo | Tipo | Cuándo | Regla |
|---|---|---|---|
| `recuentos_previos` | objeto o `null` | terminal, si la copia de seguridad previa se inspeccionó | `{series, issues, files}` con tres enteros >= 0; **nunca** texto. Es la base viva **antes** de cambiar, no la copia |
| `version_arrancada` | objeto o `null` | solo `hecha` | Misma tupla y regex que `version_de_la_copia`; cada valor puede ser `null`; si no se pudo leer, `null` entero |
| `comprobaciones` | array o `null` | terminal (`hecha`/`fallida`) | Hasta 14 objetos `{codigo, estado}`; `codigo` de §4.5; `estado` ∈ `ok`, `fallo`, `no_ejecutada`; orden fijo; en `en_curso`, `null` |

Reglas:

- `recuentos` sigue siendo `{series, issues, files}` y solo con `hecha`; `recuentos_previos` puede
  existir también en un fallo posterior a la copia previa, pero la UI solo lo usa en `hecha` y en el
  fallo parcial con `base_en_su_sitio=false` si consta.
- `version_arrancada` se **captura** después de `esperar_health` y se incluye en el estado final
  `hecha`; si la lectura extra falla, `null` y la restauración no se bloquea. No depende de que se
  borre o no la base previa.
- `comprobaciones` no sustituye a `comprobacion`: `comprobacion` sigue siendo el código de la
  comprobación de **contenido** que falló (o `null` en fallos de fase, como hoy); el array lo
  amplía. Un test exige que, si `comprobacion` no es `null`, aparezca como `fallo` en el array.
- Si no se puede escribir el estado, la restauración no falla (como hoy). Sin rutas, sin salida de
  `psql`, sin valores de seguridad.

> Los valores de los ejemplos de §4.3 son **ilustrativos** (tomados de A6 o inventados): no son
> evidencia de una ejecución de UATP-08.

Ejemplo de éxito (con campos nuevos):

```json
{
  "schema": 1,
  "intento": "b728b7c350e0d35c",
  "copia": "backup-20261122_130727",
  "copia_epoch": 1795349247,
  "inicio_epoch": 1795349360,
  "actualizado_epoch": 1795349379,
  "fase": "arrancando",
  "resultado": "hecha",
  "error": null,
  "comprobacion": null,
  "base_en_su_sitio": true,
  "copia_version": {
    "head": "2c773e53c235812adabc76e76cd3b111d04d4026",
    "build_sha": "2c773e53c235812adabc76e76cd3b111d04d4026",
    "app_version": "1.15.1",
    "alembic": "0052"
  },
  "recuentos": {"series": 2, "issues": 2, "files": 2},
  "recuentos_previos": {"series": 3, "issues": 2, "files": 2},
  "version_arrancada": {
    "head": "2c773e53c235812adabc76e76cd3b111d04d4026",
    "build_sha": "2c773e53c235812adabc76e76cd3b111d04d4026",
    "app_version": "1.15.1",
    "alembic": "0052"
  },
  "comprobaciones": [
    {"codigo": "existencia_copia", "estado": "ok"},
    {"codigo": "manifiesto", "estado": "ok"},
    {"codigo": "sha256_copia", "estado": "ok"},
    {"codigo": "bytes_copia", "estado": "ok"},
    {"codigo": "codigo_manifest", "estado": "no_ejecutada"},
    {"codigo": "gzip_cabecera", "estado": "ok"},
    {"codigo": "cabecera_pg_dump", "estado": "ok"},
    {"codigo": "tablas_dump", "estado": "ok"},
    {"codigo": "alembic_revision", "estado": "ok"},
    {"codigo": "recuentos_nueva", "estado": "ok"},
    {"codigo": "vinculos_huerfanos", "estado": "ok"},
    {"codigo": "seguridad_conservada", "estado": "ok"},
    {"codigo": "copia_previa", "estado": "ok"},
    {"codigo": "health", "estado": "ok"}
  ]
}
```

Ejemplo de fallo de contenido (SHA):

```json
{
  "schema": 1,
  "intento": "50be24773dfc345d",
  "copia": "backup-20261122_130801",
  "copia_epoch": 1795349281,
  "inicio_epoch": 1795349307,
  "actualizado_epoch": 1795349307,
  "fase": "verificando",
  "resultado": "fallida",
  "error": "copia_no_valida",
  "comprobacion": "sha256_copia",
  "base_en_su_sitio": true,
  "copia_version": {
    "head": "2c773e53c235812adabc76e76cd3b111d04d4026",
    "build_sha": "2c773e53c235812adabc76e76cd3b111d04d4026",
    "app_version": "1.15.1",
    "alembic": "0052"
  },
  "recuentos": null,
  "recuentos_previos": null,
  "version_arrancada": null,
  "comprobaciones": [
    {"codigo": "existencia_copia", "estado": "ok"},
    {"codigo": "manifiesto", "estado": "ok"},
    {"codigo": "sha256_copia", "estado": "fallo"},
    {"codigo": "bytes_copia", "estado": "no_ejecutada"},
    {"codigo": "codigo_manifest", "estado": "no_ejecutada"},
    {"codigo": "gzip_cabecera", "estado": "no_ejecutada"},
    {"codigo": "cabecera_pg_dump", "estado": "no_ejecutada"},
    {"codigo": "tablas_dump", "estado": "no_ejecutada"},
    {"codigo": "alembic_revision", "estado": "no_ejecutada"},
    {"codigo": "recuentos_nueva", "estado": "no_ejecutada"},
    {"codigo": "vinculos_huerfanos", "estado": "no_ejecutada"},
    {"codigo": "seguridad_conservada", "estado": "no_ejecutada"},
    {"codigo": "copia_previa", "estado": "no_ejecutada"},
    {"codigo": "health", "estado": "no_ejecutada"}
  ]
}
```

### 4.4 `/api/health` (D-3)

Se **propone** añadir una clave aditiva:

```json
{"status": "ok", "version": "1.15.1", "build_sha": "<40 hex o null>", "checks": {"database": "ok"}}
```

- `build_sha` sale de `Settings.build_sha` (`config.py:414`; `BUILD_SHA` de la imagen, ADR 0025) y se
  serializa como `null` si está vacío.
- No cambia ningún otro campo ni la semántica de `status`/`checks`; no es un secreto (ADR 0025 ya
  publica el SHA en `/estado`). Si SecOps prefiere no ampliar el payload público, el script lee
  `BUILD_SHA` con `docker compose exec -T zascarr printenv BUILD_SHA` (**alternativa D-3(d)**).

### 4.5 Lista cerrada de `comprobaciones` (D-2)

Orden de ejecución; `codigo`/`estado`; qué comprueba y cuándo se considera crítica.

| # | `codigo` | Qué comprueba | ¿Obligatoria en producción? |
|---|---|---|---|
| 1 | `existencia_copia` | El dump existe y no está vacío | Sí |
| 2 | `manifiesto` | Manifiesto existe, es JSON, `schema` entendido y campos válidos | Sí |
| 3 | `sha256_copia` | SHA-256 del dump contra el manifiesto (y sidecar) | Sí |
| 4 | `bytes_copia` | Tamaño del dump contra el manifiesto | Sí |
| 5 | `codigo_manifest` | El manifiesto acredita el HEAD actual (solo modo aislado) | **No**: en `--produccion` se marca `no_ejecutada` |
| 6 | `gzip_cabecera` | `gzip -t` | Sí |
| 7 | `cabecera_pg_dump` | Cabecera de `pg_dump` | Sí |
| 8 | `tablas_dump` | Tablas del preflight (`alembic_version`, `series`, `issues`, `files`, `wishlist`) y `version_num` | Sí |
| 9 | `alembic_revision` | Revisión del manifiesto/dump/BD actual | Sí |
| 10 | `recuentos_nueva` | Recuentos genéricos de cada bloque `COPY` en la base nueva | Sí |
| 11 | `vinculos_huerfanos` | Cero huérfanos en la base nueva | Sí |
| 12 | `seguridad_conservada` | La seguridad vigente se conserva (FR-18/FR-34) | Sí |
| 13 | `copia_previa` | Copia de seguridad previa escrita y verificada | Sí |
| 14 | `health` | `/api/health` 200 con `checks.database == "ok"` | Sí |

- **Estados:** `ok`, `fallo`, `no_ejecutada`. El array se emite en terminal: las anteriores al fallo
  son `ok`, la que falla `fallo`, las posteriores `no_ejecutada`. En éxito, todas `ok` salvo
  `codigo_manifest` en producción.
- Las comprobaciones 10–14 **no** están hoy en el catálogo de `comprobacion` de UATP-06 (§4.4); se
  añaden solo al array. `comprobacion` sigue limitado a las 9 de contenido; un fallo de salud deja
  `comprobacion=null` y `health=fallo` en el array.
- Un código nuevo exige fila aquí, prueba de que se escribe y de que la UI lo pinta; uno desconocido
  se descarta sin romper y la UI no lo muestra.
- Solo el **estado**, nunca el valor del hash, la salida de `psql` ni el contenido del dump.

### 4.6 Lista cerrada de «fuera de la copia» (D-4)

Lista de **producto** (no persistida; el lector la compone):

| `codigo` | Texto de superficie (llano) | `n` |
|---|---|---|
| `archivos_biblioteca` | Los archivos de tu biblioteca: CBZ, CBR, PDF o EPUB | `null` (no se escanea) |
| `portadas` | Las portadas guardadas | `null` |
| `configuracion` | La configuración del equipo: acceso, contraseña y exposición | `null` |
| `cambios_posteriores` | Lo anotado después de la copia | `null`; la magnitud va en los recuentos pre/post |

- **En el CA2, «omitido» es esta lista.** En superficie se dice «Queda fuera de la copia», que es
  más claro para el coleccionista; el contrato interno puede seguir llamándolo `omitido`.
- **No existe** `catalogo_parcial`: el catálogo es todo o nada. La UI no debe insinuar lo contrario.
- La declaración de alcance (catálogo sí; archivos/portadas/configuración no; ZascArr no los toca) es
  fija y se muestra en la confirmación y en el resumen.
- Si el PO quiere medir archivos o portadas, se añadirá un `n` medido en una historia aparte; hoy no
  se inventa.

### 4.7 Compatibilidad y no-regresión

- `schema`: **1** en los dos ficheros; los campos son aditivos. El lector de la app acepta ficheros
  antiguos (sin los campos) y con tipos erróneos.
- `tests/test_copias_json.py` (claves exactas) y `tests/test_copias_ops.py` (claves de
  `leer_copias`) se actualizan; el resto de BL-OPS1/2 debe seguir pasando sin cambios de aserción.
- Sin migración de Alembic, sin dependencia nueva, sin JS nuevo y sin escritura en la biblioteca.
- `ops-restaurar-intentos.jsonl` no cambia en esta historia (la app no lo lee).

---

## 5. Interfaz: rutas, plantillas y textos

### 5.1 Lista de copias (`_copias_items.html`)

Cada entrada muestra, en este orden:

1. **Fecha y hora absolutas:** `22/11/2026 a las 13:07` (helper `fecha_absoluta`; zona del
   servidor). **Nunca** «hoy/ayer» como única referencia.
2. Tamaño y «también en el disco de respaldo: sí/no» (como hoy).
3. **Versión de la copia**, en una línea `.caption`:
   - con `app_version` y `alembic`: «Versión 1.15.1 · revisión 0052»;
   - con solo uno: «Versión 1.15.1» o «Revisión 0052»;
   - sin datos o `null`: «Versión no consta».
4. Botón «Restaurar…» o el motivo (como hoy).

- Una vez por bloque, en el `<summary>` de «Copias guardadas» o en un `.caption` del bloque: «Las
  horas son del servidor.» (S2-03).
- La versión se toma del objeto saneado; si el fichero no la trae, no se deduce de `revision`.

### 5.2 Confirmación (`_restaurar_confirmar.html`)

**Textos exactos** (el orden importa):

- `h1`: «Restaurar una copia».
- Subtítulo: «Vas a volver a los datos del **{fecha_absoluta}** (hora del servidor).»
- Línea de versión: «{versión de la copia}»; si `null`: «Versión no consta. Esta copia es de antes
  de que ZascArr anotara la versión.»
- Aviso (`ui.aviso("warn", …)`, sin cambios de fondo): «ZascArr se parará uno o dos minutos. Tu
  biblioteca, tus archivos y el acceso actual no cambian; la copia restaurada no puede traer
  contraseñas ni sesiones antiguas.»
- **Alcance:** «Esta copia contiene lo que ZascArr tiene anotado: series, números, fichas y progreso
  de lectura. No contiene los archivos de tu biblioteca (CBZ, CBR, PDF o EPUB), las portadas ni la
  configuración del equipo; ZascArr no los toca al restaurar.»
- **Cambios posteriores:** «Se pierden los cambios posteriores a esa copia: series, números,
  ediciones y progreso anotados después. Mover o renombrar archivos que haya hecho ZascArr no se
  deshace.»
- Casilla: «Entiendo que se pierden los cambios posteriores a esa copia.» (se conserva).
- Botón: «Restaurar esta copia». Enlace secundario: «No restaurar».
- `<details><summary>Para quien instaló ZascArr</summary>`:
  - identidad completa de la copia: `copia` (id), `head`, `build_sha`, `app_version`, `alembic`, cada
    uno o «no consta»; si toda la tupla es `null`: «No consta: copia anterior a que ZascArr anotara
    la versión.»
  - «La copia se verifica antes de tocar la base; la actual se guarda primero y se puede recuperar si
    falla. La operación la ejecuta el auxiliar del host, no la aplicación.»
- La versión principal muestra `app_version` + revisión; los hashes van **solo** en el detalle
  colapsado. La confirmación no repite la contraseña ni la guarda.

**Presupuesto de texto.** Esta pantalla supera el umbral orientativo de 50 palabras antes de la
primera acción (U21): CA1 exige cuatro datos visibles y el aviso de seguridad de BL-OPS2 ya existía.
Se reduce a lo imprescindible y el detalle técnico va a `<details>`; se declara como **excepción de
UX** en §9 para que el PO/UX decidan si acortar más. No se mueve al `<details>` nada que CA1 exija
ver antes de confirmar.

### 5.3 Resumen (`GET /ui/copias/restauracion`, nueva `restauracion_resumen.html`)

- Ruta bajo `/ui` (autenticación existente), `Cache-Control: no-store`; solo lee
  `ops-restaurar.json` (y, si acaso, los ficheros de estado ya leídos por el lector); no toca la base,
  no escanea el disco, no contacta con el auxiliar.
- Si no hay datos: página con `ui.estado_vacio("No hay ninguna restauración que contar", "Cuando
  restaures una copia, aquí verás cómo fue.")` y enlace a Estado. **No** un 404 que parezca roto.
- Si `en_marcha`: aviso «Hay una restauración en marcha.» + mensaje existente + enlace a Estado. No
  hay sondeo en esta página (el POST ya lo hace; la app puede estar reiniciándose).
- Si `sin_noticias`/`no_arranco`: aviso correspondiente + enlace a Estado.
- Si `hecha`, la página se compone así (todo en llano, sin JSON):

| Bloque | Contenido |
|---|---|
| `h1` | «Copia restaurada» |
| Subtítulo | «ZascArr volvió a los datos del {fecha_absoluta} (hora del servidor).» |
| Recuperado | «{series} series, {issues} números y {files} archivos anotados.» + `.caption`: «Son registros de tu biblioteca, no archivos comprobados en el disco.» Si no constan: «No consta el detalle de lo recuperado.» |
| Versión que arrancó | «{app_version} · revisión {alembic}» o «No consta.» + detalle con `head`/`build_sha` o «no consta»; `.caption`: «La restauración es anterior a que ZascArr anotara esta versión.» solo si `null` |
| Queda fuera de la copia | Lista cerrada de §4.6, con una frase por categoría. **No** se dice «catálogo parcial» |
| Cambios posteriores | Si hay `recuentos_previos`: «Antes de restaurar había {prev.series} series, {prev.issues} números y {prev.files} archivos anotados. Esta copia trae {series}, {issues} y {files}: lo anotado después de la copia no vuelve.» Si no consta: «No consta cuánto había antes de restaurar.» `.caption`: «Las cifras son registros anotados; no dicen qué fila cambió.» |
| Comprobaciones | «Se comprobó la copia antes de usarla y la base restaurada antes de arrancar.» (solo si `hecha`; si la lista no consta, «No consta qué se comprobó.»). Detalle colapsado con los 14 códigos y su estado |
| Para quien instaló ZascArr | `copia` (id), `intento`, `copia_version`, `version_arrancada`, `comprobacion` (si la hay), estados; **nunca** contraseñas, rutas, `sha256` del dump ni salida de scripts |
| Enlace | «Volver a Estado» (secundario) |

- Si `fallo`, la misma ruta pinta el diagnóstico:

| Bloque | Contenido |
|---|---|
| `h1` | «No se pudo restaurar la copia» |
| Aviso | `ui.aviso("warn", mensaje)` con la causa+acción existente; si `base_en_su_sitio is False`, además «ZascArr podría no responder ahora mismo.» |
| Qué ha pasado | «La restauración no se completó. Aunque el resto del sistema siga funcionando, esta copia no se ha aplicado.» Si `base_en_su_sitio is True`: «Tus datos siguen como estaban.» Si `False`: «ZascArr no pudo volver atrás solo; los datos de antes están en la copia previa. Avisa a quien instaló ZascArr cuanto antes.» |
| La copia que se intentó | «Copia del {fecha_absoluta} · {versión}»; si la fecha o la versión no constan, «fecha no consta» / «versión no consta»; id e `intento` en el detalle |
| Próximo paso | Enlace principal «Elige otra copia» a `/estado#copias`; enlace «Volver a Estado»; si `base_en_su_sitio is False`, «Avisa a quien instaló ZascArr» (texto, no enlace) |
| Para quien instaló ZascArr | `intento`, `error`, `comprobacion`, `comprobaciones` (estados), `copia_version`; **nunca** hashes de contenido, rutas ni salida de scripts |

- Un fallo **nunca** se pinta como éxito ni al revés; `hecha` solo si el fichero dice `hecha`. Un
  fallo con `base_en_su_sitio=false` sigue siendo un fallo, no un «recuperado parcial».
- Esta página no usa `hx-*` ni JS; es una lectura estática tras el reinicio.

### 5.4 Estado y aviso de `/login`

- **Estado** (`_copias_estado.html`): se conserva el bloque compacto y su `aria-live`; cuando
  `vr.estado` es `hecha` o `fallo`, se añade debajo un enlace «Ver el resumen de la restauración» a
  `/ui/copias/restauracion`. El mensaje de `hecha` pasa a fecha absoluta (helper), manteniendo los
  recuentos y «Entra con tu contraseña de siempre».
- **`/login`** (FR-32): el aviso sigue siendo el texto actual, **sin fecha** (es público). Debajo,
  si hay aviso, un enlace «Entra y verás qué se restauró» con
  `href="/login?next=%2Fui%2Fcopias%2Frestauracion"`; el middleware de autenticación y `next` ya
  soportan el destino, así que tras escribir la contraseña se aterriza en el resumen. No se añade
  fecha ni datos de la copia al aviso público.
- **POST aceptado** (`_restaurar_resultado.html`): se mantiene «Restauración en marcha. ZascArr se
  reiniciará en uno o dos minutos.» y se añade una frase sin enlace: «Cuando vuelva, entra: el
  resumen te espera.» (No se pone un enlace que estaría muerto mientras la app se reinicia.)

### 5.5 Fechas, zona y formatos

- `fecha_absoluta(epoch)` → `dd/mm/aaaa a las HH:MM` en la zona del **servidor**
  (`datetime.fromtimestamp(...).astimezone()`), con horas y minutos; épocas inválidas →
  «fecha no disponible» (nunca una cifra cruda). Se usa en lista, confirmación, Estado y resumen.
- Una vez por pantalla/bloque se declara «(hora del servidor)»; no hay selector de zona por usuario.
- `hora_llana` se conserva para los mensajes que no son de decisión («Copia hecha hoy a las…»,
  «La copia de la noche del…»); no se usa como única fecha de la copia que se va a restaurar.
- `miles()` se conserva para los recuentos (separador español).

### 5.6 Accesibilidad y superficie (AC-08-13)

- 320 px sin scroll horizontal; textos y versiones largas envuelven (sin `white-space: nowrap` en la
  identidad).
- Teclado: enlaces y botones alcanzables; foco visible; `<details>` nativo; sin trampa de foco.
- Texto informativo >= 14 px (`.875rem`); no se introduce texto por debajo del mínimo; se reutilizan
  clases existentes (`.caption`, `.muted`, `.group`, `ui.aviso`, `ui.grupo`). Si UX pide una clase
  nueva, se declara en el sistema de diseño y en `test_web_css_contraste`.
- Ambos temas (`prefers-color-scheme`); contraste comprobado como el resto.
- Sin JS nuevo; sin `hx-confirm` (la confirmación ya es una página); una sola acción principal por
  pantalla: la confirmación conserva «Restaurar esta copia» como única acción que avanza; el resumen
  de éxito no tiene principal; el de fallo tiene «Elige otra copia» como principal y «Volver a
  Estado» como secundaria.
- La página del resumen es estática; no necesita `aria-live`. El bloque de Estado ya lo tiene.

### 5.7 Sin secretos, rutas ni hashes de contenido

- **Puede aparecer:** id de copia (`backup-YYYYMMDD_HHMMSS`), fecha/hora, versión (`app_version`),
  revisión Alembic, `head`/`build_sha` (solo detalle), recuentos, códigos cerrados, `intento`
  (16 hex) y estados.
- **Nunca aparece:** contraseña, `auth_password_hash`, `secret_key`, `runtime_settings`, rutas
  (`/var`, `/home`, `/mnt`, `BACKUP_DIR`), nombre del dump (`backup_*.sql.gz`), `MANIFIESTO-*`,
  `sha256` del dump, sidecar, salida de `psql`/scripts, JSON crudo del fichero ni texto libre.
- El lector valida cada campo con su regex/lista y descarta lo desconocido; las plantillas solo
  pintan catálogo y valores ya validados.
- Prueba explícita: el HTML de lista, confirmación y resumen no contiene rutas, nombres de dump,
  `sha256` del dump ni secretos (ver T-08-12).

---

## 6. Criterios de aceptación (UATP-08)

> Todos **NOT RUN**: no hay implementación. La numeración es local a esta spec.

- **AC-08-01 (fecha y hora).** CUANDO se abre la lista de copias o la confirmación de una copia,
  ENTONCES la fecha se muestra como `dd/mm/aaaa a las HH:MM`, con año y hora, en la zona del servidor
  declarada; no se usa «hoy/ayer» como única referencia en la decisión.
- **AC-08-02 (versión de la copia).** ENTONCES la lista muestra la versión (semver + revisión, o «no
  consta») y la confirmación muestra la tupla `head`/`build_sha`/`app_version`/`alembic`, cada valor
  o «no consta», con los hashes solo en el detalle colapsado; una copia antigua sin el dato dice «no
  consta» y **no se infiere** de la revisión ni del SHA actual. Sin D-1(a) aprobada, este AC se
  acredita de forma parcial (semver+revisión) y se declara.
- **AC-08-03 (alcance).** ENTONCES la confirmación y el resumen dicen que la copia contiene el
  catálogo (series, números, fichas y progreso) y que **no** contiene los archivos de la biblioteca,
  las portadas ni la configuración, y que ZascArr no toca la biblioteca al restaurar. No se insinúa
  que los CBZ estén dentro.
- **AC-08-04 (cambios posteriores).** ENTONCES la confirmación advierte con ejemplos (series, números,
  ediciones, progreso) y añade que mover/renombrar archivos hechos por ZascArr **no** se deshace (R-7
  de BL-OPS2). No promete una lista exacta de filas.
- **AC-08-05 (resumen persistente).** CUANDO termina una restauración, ENTONCES existe
  `/ui/copias/restauracion`, alcanzable después del reinicio y desde Estado y `/login`, bajo
  autenticación y con `no-store`, que muestra el resumen sin depender de la pestaña del POST.
- **AC-08-06 (recuperado).** ENTONCES el resumen muestra series, números y archivos **anotados**
  recuperados, coincidentes con la base restaurada, y distingue «anotados» de «archivos del disco».
- **AC-08-07 (fuera de la copia).** ENTONCES el resumen muestra la lista cerrada de §4.6 (archivos de
  biblioteca, portadas, configuración, cambios posteriores) sin texto libre; no declara «catálogo
  parcial» ni promete que los archivos estén.
- **AC-08-08 (magnitud para UAT-31).** CUANDO constan `recuentos` y `recuentos_previos`, ENTONCES el
  resumen muestra ambos («antes de restaurar había…; esta copia trae…») y la fecha de la copia, para
  que una persona explique por qué una fila añadida después quedó fuera; no se atribuye la diferencia
  a una fila concreta.
- **AC-08-09 (versión que arrancó).** ENTONCES el resumen muestra la tupla capturada al terminar
  (`app_version` + revisión y, en detalle, `head`/`build_sha`) o «no consta»; no usa la versión actual
  de la app como sustituto.
- **AC-08-10 (comprobaciones).** ENTONCES el resumen permite saber qué comprobaciones sustentan el
  resultado mediante los códigos/estados de §4.5; en éxito todas las obligatorias están `ok` y
  `codigo_manifest` puede ser `no_ejecutada`; nunca se muestran hashes de contenido, rutas ni salida
  de scripts.
- **AC-08-11 (fallo).** CUANDO falla, ENTONCES el resultado se identifica como fallo —aunque el resto
  del sistema funcione—, da causa y acción del catálogo, dice si la base vigente está en su sitio en
  llano, y ofrece «Elige otra copia» y, si `base_en_su_sitio=false`, «Avisa a quien instaló ZascArr»;
  el detalle incluye copia, fecha absoluta, versión o «no consta» e `intento`, sin secretos.
- **AC-08-12 (robustez).** Dados ficheros ausentes, estados antiguos (`schema: 1` sin los campos),
  claves desconocidas, tipos erróneos, códigos desconocidos, listas enormes o épocas futuras,
  ENTONCES la UI no da 500, no pinta valores libres y usa «no consta»/«causa desconocida»; un
  `comprobacion` desconocido no se pinta.
- **AC-08-13 (accesibilidad).** ENTONCES lista, confirmación y resumen son usables a 320 px, con
  teclado, foco visible, texto >= 14 px, ambos temas, una sola acción principal y sin JS nuevo.
- **AC-08-14 (no regresión).** ENTONCES no hay migración, dependencia ni JS nuevos; la restauración
  sigue restaurando solo el catálogo y no toca la biblioteca; FR-16/AC-21 se enmiendan solo si D-1(a)
  se aprueba; las pruebas de BL-OPS1/2 y de UATP-06/07 siguen pasando.
- **AC-08-15 (UAT-31).** CUANDO se ejecuta el protocolo de §8 sobre una candidata identificada,
  ENTONCES una persona explica a partir del resumen por qué la fila añadida después de la copia quedó
  fuera, y la evidencia queda en A6; sin ejecución, UATP-08 queda NOT RUN.
- **AC-08-16 (no declarar de más).** ENTONCES el resumen no dice «restaurado y comprobado» si falta
  una comprobación obligatoria, no dice «no se perdió nada» y no convierte un `null` en un cero ni un
  `fallo` en éxito.

---

## 7. Casos de prueba

> Todas las filas están **NOT RUN** en esta spec. Las marcadas **TDD-first** deben escribirse antes
> de implementar y fallar por la razón correcta. Los ficheros de test que se citan son los de
> `origin/main@9fe0be06`.

| ID | Tipo | Qué comprueba | Dónde | Estado |
|---|---|---|---|---|
| **T-08-01** | Unit (servicio) **TDD-first** | `fecha_absoluta`: `dd/mm/aaaa a las HH:MM`, año, hora, zona del servidor; `TZ` distinta cambia el resultado; época inválida no lanza; nunca «hoy/ayer» | `tests/test_copias_ops.py` (junto a `test_la_hora_se_pinta_en_la_zona_del_servidor:112`) | NOT RUN |
| **T-08-02** | Unit (servicio) **TDD-first** | `leer_copias`: claves exactas nuevas (`fecha_absoluta`, `version`), tupla válida, `null` para copia antigua, objeto hostil → `null`; no pinta hashes de contenido | `tests/test_copias_ops.py:131-141` | NOT RUN |
| **T-08-03** | Unit (servicio) **TDD-first** | `resolver_restauracion` con `copia`, `copia_version`, `recuentos_previos`, `version_arrancada`, `intento`, `comprobacion`, `comprobaciones`: válidos, ausentes, `schema` viejo, tipos hostiles, códigos desconocidos, listas > 14, épocas futuras; no 500 y no pinta valores libres; `comprobacion` = `fallo` del array | `tests/test_restauracion_estado.py:330-380` (base) | NOT RUN |
| **T-08-04** | Web (FakeSession) | Lista y confirmación: fecha absoluta, versión (o «no consta»), alcance, cambios posteriores, detalle con `head`/`build_sha`; una copia antigua no infiere; no aparece contraseña, ruta, dump ni `sha256` | `tests/test_copias_ops.py` / nuevo `tests/test_web_uatp08.py` | NOT RUN |
| **T-08-05** | Web (ruta) **TDD-first** | `GET /ui/copias/restauracion`: 200 con sesión, redirección a `/login?next=…` sin ella, `no-store`, `sin_datos`/`en_marcha`/`sin_noticias`/`hecha`/`fallo`/`base false`; enlaces «Ver el resumen» y «Elige otra copia» | nuevo `tests/test_web_uatp08.py` | NOT RUN |
| **T-08-06** | Web (login/Estado) | El aviso de `/login` sigue sin fecha y añade el enlace con `next`; el bloque de Estado añade el enlace solo en terminal; `hecha` usa fecha absoluta y conserva recuentos/miles | `tests/test_restauracion_estado.py:283-310` | NOT RUN |
| **T-08-07** | Script (host) **TDD-first** | `escribir_copias_json`: cada entrada lleva `version_de_la_copia` saneada o `null`; manifiesto antiguo → `null`; objeto hostil → `null`; sin rutas/nombres/hash del dump; claves exactas actualizadas (FR-16/AC-21) | `tests/test_copias_json.py:52-66` | NOT RUN |
| **T-08-08** | Script (host) **TDD-first** | `estado_restaurar`: `recuentos_previos` (desde la inspección del dump de seguridad), `version_arrancada` (solo `hecha`, con `build_sha`), `comprobaciones` (14, orden, estados; `codigo_manifest` `no_ejecutada` en producción; fallo → `fallo` + posteriores `no_ejecutada`; `comprobacion` coherente); atómico, `0644`, sin secretos/rutas | `tests/test_restaurar_produccion.py` (extensión; ver `:431`, `:466`, `:485`) | NOT RUN |
| **T-08-09** | Script (host) | Un fallo de salud deja `version_arrancada=null`, `comprobaciones[health]=fallo` y `base_en_su_sitio` correcto; un fallo antes de la copia previa deja `recuentos_previos=null` | `tests/test_restaurar_produccion.py` | NOT RUN |
| **T-08-10** | PG real | UAT-31 de datos: copiar, añadir una fila después, restaurar; `recuentos_previos` > `recuentos` en la tabla tocada; `version_arrancada` y `comprobaciones` coherentes. Skip sin `TEST_DATABASE_URL` | `tests/test_restaurar_produccion_pg.py` | NOT RUN |
| **T-08-11** | Unit (app) | `/api/health` incluye `build_sha` (o `null`); no cambia `version`, `status` ni `checks`; la suite de health sigue pasando | `tests/test_health.py` | NOT RUN |
| **T-08-12** | Web/estático | Saneado: el HTML de lista, confirmación y resumen no contiene `/home`, `/mnt`, `/var`, `BACKUP_DIR`, `.sql.gz`, `MANIFIESTO-`, el `sha256` del dump, `password`, `secret` ni salida de `psql`; solo los hashes de identidad permitidos | `tests/test_web_uatp08.py` | NOT RUN |
| **T-08-13** | E2E (Chrome real) | Lista/confirmación/resumen a 320, 390 y escritorio; ambos temas; teclado, foco, sin scroll horizontal; capturas; UAT-31 (§8) con la explicación del agente | `docs/TESTING_E2E.md` (bloque nuevo) + A6 | NOT RUN |
| **T-08-14** | Regresión | Suite no-PG; `test_copias_ops`, `test_copias_json`, `test_restauracion_estado`, `test_restaurar_produccion`, `test_ops_paridad`, `test_update_hook_restauracion`, `test_health`; `ruff check src/`; sin migración/dependencia/JS nuevos | CI | NOT RUN |
| **T-08-15** | Rendimiento (Pi) | La página del resumen se pinta solo con ficheros pequeños; sin consulta a la base, sin escaneo de la biblioteca, sin picos de RAM (medición en Pi; si no se ejecuta, NOT RUN `motivo=coste`) | Pi | NOT RUN |

**Orden TDD recomendado:** T-08-01/T-08-02/T-08-03 (lector y fechas) → T-08-05 (ruta) → T-08-07
(copias.json) → T-08-08/T-08-09 (estado) → T-08-11 (health) → T-08-04/T-08-06/T-08-12 (web) →
T-08-10/T-08-13/T-08-15 (evidencia y Pi) → T-08-14 en cada paso.

**Comandos de referencia (cuando exista implementación):**

```bash
pytest -q tests/test_copias_ops.py tests/test_copias_json.py \
  tests/test_restauracion_estado.py tests/test_restaurar_produccion.py \
  tests/test_health.py tests/test_web_uatp08.py
pytest -q tests/test_restaurar_produccion_pg.py   # requiere TEST_DATABASE_URL
ruff check src/
bash -n scripts/_comun.sh && bash -n scripts/restaurar_datos.sh
```

**Prueba que debe fallar antes de implementar:** T-08-01, T-08-02, T-08-03, T-08-05, T-08-07 y
T-08-08.

---

## 8. Evidencia de cierre: UAT-31

> **No ejecutada.** Esta sección fija cómo se acredita; no es evidencia. La evidencia de UATP-08 se
> registra en [`docs/uat/A6/resultado.md`](../uat/A6/resultado.md) porque #1146 la nombra, **sin
> reescribir** lo ya acreditado de UATP-06/07 (se añade una pasada 3 y un bloque UAT-31). Si el PO
> prefiere un `docs/uat/A8/` separado, es un cambio de ubicación, no de contenido; el enlace de
> #1146 debe seguir funcionando.

### 8.1 Entorno y candidata

- **E-A6** aislado (proyecto Compose distinto, puertos y volúmenes propios, `auth_mode=password`),
  con la **candidata de UATP-08** (tag anotado `uat-candidata-<fecha>`); nunca la Pi ni datos reales.
- Identidad declarada en la cabecera de A6 y en la evidencia: `tag_commit`, `head`, `build_sha`,
  `app_version`, `alembic`, `image_id`. No se declara la copia solo como «1.15.1».
- Fixture sintético determinista (serie, número, archivo, progreso) como en A6; sin rutas reales.
- La app con la implementación de UATP-08; el estado contiene `recuentos_previos`,
  `version_arrancada` y `comprobaciones`; `copias.json` contiene `version_de_la_copia` (si D-1(a))
  y la lista lo muestra.

### 8.2 Protocolo UAT-31 (paso a paso)

1. **Semilla y copia.** Crear la copia B0 con `backup.sh` sobre la fixture; comprobar
   `version_de_la_copia` en el manifiesto y en `copias.json`; anotar los recuentos de partida.
2. **Fila añadida después de la copia.** Por la interfaz (no por SQL), añadir una fila de catálogo
   (una serie) o registrar un archivo, de forma que la base viva quede con **un** registro más en
   `series` (o `files`). Anotar el delta esperado y la hora.
3. **Antes de confirmar.** Abrir «Restaurar…» de B0 y capturar: fecha/hora absoluta, versión de la
   copia (tupla o «no consta»), alcance, cambios posteriores, y capturas a 320/390/escritorio. Si la
   confirmación no muestra la versión, AC-08-02 no se acredita.
4. **Restaurar.** Ejecutar la restauración desde la interfaz (contraseña actual + casilla). Esperar
   al reinicio.
5. **Después de reiniciar.** Abrir `/ui/copias/restauracion` (o el enlace del aviso de `/login` /
   Estado) y capturar: copia y fecha, recuperado (los recuentos de B0), «antes de restaurar había…»
   (con la fila añadida), versión que arrancó, comprobaciones y, en su caso, el fallo. Capturas a
   320/390/escritorio y ambos temas.
6. **Explicación del agente.** Una persona distinta de quien implementó (rol UAT) explica **con sus
   palabras**, mirando solo el resumen, por qué la fila añadida después de la copia quedó fuera.
   Debe apoyarse en: la fecha/hora de la copia, la diferencia entre «antes» y «recuperado» y la frase
   «lo anotado después de la copia no vuelve». Se registra la explicación literal (saneada) y se
   marca si necesitó ayuda externa (si la necesitó, el resumen no es «utilizable» y UAT-31 es FAIL).
7. **Saneado y cierre.** Aplicar el grep de saneado de §7.6 de `uatp06-07-recuperacion.md`;
   enlazar desde #1146 y #1141; añadir la línea `CHECK UAT-31 PASS|FAIL|NOT RUN` al `resultado.txt`
   de A6 y la fila a la tabla de comprobaciones.

### 8.3 Artefactos de evidencia

| Artefacto | Dónde | Contenido |
|---|---|---|
| `resultado.md` | `docs/uat/A6/resultado.md` (bloque «Ampliación pasada 3 · UAT-31») | cabecera con la candidata y la versión; tabla de comprobaciones UAT-31; enlaces; PASS/FAIL/NOT RUN |
| `evidencia/uat31/uat31.txt` | `docs/uat/A6/evidencia/uat31/` | comandos saneados, salida, recuentos, `jq` del estado (sin rutas), línea `CHECK` |
| `evidencia/uat31/estado-hecha.json` | ídem | copia **saneada** de `ops-restaurar.json` con los campos nuevos |
| `evidencia/uat31/confirmation.txt` | ídem | texto visible de la confirmación (fecha, versión, alcance, cambios) |
| `evidencia/uat31/resumen.txt` | ídem | texto visible del resumen (recuperado, antes, fuera, versión, comprobaciones) |
| `evidencia/uat31/explicacion.md` | ídem | explicación literal del agente UAT y si necesitó ayuda |
| `evidencia/uat31/capturas/` | ídem | PNG a 320/390/escritorio, ambos temas |

Sin rutas absolutas, hostnames, IPs, usuarios, nombres reales de archivo ni secretos; las cifras y la
identidad de la candidata sí. Las capturas no muestran la contraseña.

### 8.4 Criterio de PASS

- AC-08-01…16 con evidencia **ejecutada** (no «leída»), salvo AC-08-02 si D-1(b) y AC-08-09 si
  D-3(b): en esos casos se declaran parciales y el PASS no puede ser pleno.
- UAT-31 PASS: la explicación es correcta y sostenida por el resumen; si la persona necesita leer
  logs o JSON para explicarlo, FAIL.
- Cualquier `NOT RUN` en una comprobación obligatoria **impide** declarar UATP-08 cumplida; no se
  convierte en PASS por «lo demás funciona». La suite verde no acredita UAT-31.

### 8.5 Lo que esta spec **no** declara

No hay implementación, no hay tests ejecutados y no hay evidencia UAT-31. **UATP-08 no está
cumplida, ni parcialmente.** A6 sigue siendo la evidencia de UATP-06/07; esta spec no la modifica ni
la reutiliza como cierre de UATP-08.

---

## 9. Límites y riesgos

### 9.1 Límites declarados

1. **La copia no contiene la biblioteca.** Ni CBZ/CBR/PDF/EPUB, ni portadas, ni `.env`, ni
   credenciales, ni la configuración del host. Restaurarlos es el procedimiento manual de UATP-07;
   UATP-08 solo lo declara.
2. **No se escanea la biblioteca** para pintar: los recuentos son de catálogo (filas), no de archivos
   del disco.
3. **Los recuentos pre/post no identifican filas.** Una fila borrada y otra añadida pueden dejar el
   mismo total; UAT-31 se explica por fecha y magnitud, no por identidad de la fila. Si no hay
   `recuentos_previos` (fallo antes de la copia previa), no se muestra la comparación.
4. **Copias y estados antiguos** no tienen `version_de_la_copia`/`version_arrancada`: «no consta»;
   nunca se infiere del estado actual. `head`/`build_sha` pueden ser `null` en builds manuales.
5. **Zona horaria:** la del servidor; no hay selector por usuario. Se declara en la pantalla.
6. **Si la app no responde** (`base_en_su_sitio=false`), la ruta del resumen no es alcanzable: el
   diagnóstico visible es el del POST/login y, si vuelve, el de Estado. No se promete una pantalla
   que la app caída no puede servir.
7. **Pi/real:** el rendimiento del resumen no se mide aquí; T-08-15 queda NOT RUN si no se ejecuta en
   Pi. ADR 0023 sigue «propuesto. No desplegado»: el flujo está probado en E-A6, no en una Pi real.
8. **`N-01-systemd-host`** de A6 sigue NOT RUN (sin root/systemd en el host aislado); UATP-08 no lo
   arregla.
9. **El `intento` no es una prueba criptográfica**: es un identificador del fichero del host; la app
   confía en los ficheros de estado (misma frontera que BL-OPS1/2).
10. **Presupuesto de texto:** la confirmación supera el umbral orientativo de 50 palabras porque CA1
    exige cuatro datos visibles; se declara como excepción para que UX/PO decidan.
11. **Sin borrado, retención, «deshacer», actualización ni despliegue.**

### 9.2 Riesgos

| ID | Riesgo | Mitigación |
|---|---|---|
| R-1 | D-1(a) no se aprueba y CA1 queda débil | La spec permite (b) y lo declara; no se implementa la tupla sin enmienda de FR-16/AC-21 |
| R-2 | Los hashes de identidad confunden a la persona o se leen como secretos | Solo en el detalle colapsado, con texto «identidad del código»; nunca hashes de contenido |
| R-3 | Formatos de fecha divergen entre lista, confirmación y resumen | Un único helper `fecha_absoluta`; T-08-01 con dos `TZ` |
| R-4 | El resumen declara «omitido» de más o «catálogo parcial» | Lista cerrada §4.6; AC-08-07/16; sin `n` inventado |
| R-5 | Los recuentos pre/post se interpretan como «qué se perdió» | Texto «la diferencia es magnitud, no qué fila»; AC-08-08; límite 3 |
| R-6 | La ruta del resumen no se descubre tras el reinicio | Enlaces desde Estado y `/login`; AC-08-05; T-08-05/06 |
| R-7 | La pantalla del resumen se cae o tarda en Pi | Solo ficheros pequeños, sin BD/escaneo; T-08-15; el bloque de Estado sigue como respaldo |
| R-8 | Se reutiliza A6 de UATP-06/07 como cierre de UATP-08 | Pasada 3 + UAT-31 ejecutados; §8.5; no se convierte NOT RUN en PASS |
| R-9 | El estado se corrompe o el script no puede escribirlo | Escritura atómica y tolerante como hoy; la restauración no falla por el estado (`T-08-08`) |
| R-10 | UAT-31 se hace con datos reales o se inventa | E-A6 aislado, fixture sintética, evidencia enlazada; §8.2/8.4 |
| R-11 | El enlace de `/login` introduce fecha o datos en la página pública | El aviso sigue sin fecha; el enlace solo lleva `next`; T-08-06 |
| R-12 | El array de comprobaciones se acopla al orden del script y se rompe al cambiarlo | Lista cerrada + orden fijo en contrato; T-08-03/08; un código nuevo exige fila y prueba |
| R-13 | `version_arrancada` se pinta con la versión actual si falta | El lector no consulta la app; si falta, «no consta»; T-08-03 |

### 9.3 Preguntas abiertas

- **Q-1:** ¿La evidencia de UATP-08 vive en A6 (como dice #1146) o en un `docs/uat/A8/` propio? Esta
  spec propone A6, pasada 3; el enlace de #1146 debe seguir siendo válido.
- **Q-2:** ¿Aprueba el PO la enmienda de FR-16/AC-21 para `head`/`build_sha` en `copias.json`
  (D-1(a)) o prefiere solo semver+revisión (D-1(b))?
- **Q-3:** ¿Se añade `build_sha` a `/api/health` (D-3(a)) o se lee del contenedor (D-3(d)) por
  criterio de SecOps?
- **Q-4:** ¿El resumen debe enlazarse también desde el Inicio/dashboard, no solo desde Estado y
  `/login`? (No es necesario para CA2; se puede añadir sin coste.)
- **Q-5:** ¿Se acepta la excepción de presupuesto de texto de la confirmación (§5.2) o UX propone un
  texto más corto manteniendo los cuatro datos de CA1?

---

## 10. Dependencias, orden de implementación y enmiendas

### 10.1 Orden

1. **PO:** aprobar/rechazar D-1…D-5. Sin D-1 no se toca FR-16; sin D-3 no se añade `build_sha`; sin
   D-5 no hay ruta. Las decisiones no autorizan a implementar por sí solas: hace falta la historia en
   «En curso» y la PR.
2. **TDD, contrato y lector:** T-08-01/T-08-02/T-08-03 en rojo → `ops_host.py` + `fecha_absoluta`.
3. **Script:** `copias.json` (T-08-07) y `ops-restaurar.json` (T-08-08/T-08-09); `health` (T-08-11).
4. **Web:** ruta/template y textos (T-08-04/T-08-05/T-08-06/T-08-12).
5. **Docs:** enmiendas de §10.2 y `docs/TESTING_E2E.md` (bloque UATP-08/UAT-31).
6. **Evidencia:** E-A6 pasada 3 + UAT-31 (§8); A6 y enlaces de issues.
7. **Cierre:** `docs/BACKLOG.md` con la nota mecánica (CLAUDE.md §9) y PASS/FAIL/NOT RUN explícitos.

### 10.2 Enmiendas documentales necesarias

| Doc | Enmienda |
|---|---|
| `docs/design/especificacion-BL-OPS1.md` | FR-16: añadir `version_de_la_copia` a la lista cerrada y aclarar «sin hashes de contenido ni de archivos; la identidad de versión del código se admite en ese objeto». AC-21: la lista muestra versión (semver/revisión) y nunca rutas/hashes de contenido |
| `docs/design/especificacion-BL-OPS2.md` | FR-24: añadir `recuentos_previos`, `version_arrancada`, `comprobaciones` (aditivo, `schema: 1`). FR-29: el estado terminal enlaza al resumen. FR-32: el aviso de `/login` enlaza al resumen tras entrar, sin fecha |
| `docs/design/uatp06-07-recuperacion.md` | Nota de que UATP-08 amplía el contrato de §4.2 con `recuentos_previos`, `version_arrancada` y `comprobaciones`; no se reescribe lo acreditado |
| `docs/TESTING_E2E.md` | Bloque nuevo «UATP-08: resumen de recuperación y UAT-31» con comandos, capturas y saneado |
| `docs/uat/A6/resultado.md` + `evidencia/uat31/` | Pasada 3 y UAT-31 (§8) |
| `docs/design/ui-migracion.md` | Inventario: ruta `/ui/copias/restauracion`, plantilla `restauracion_resumen.html`, cambios en lista/confirmación/login |
| `docs/BACKLOG.md` | Al cerrar: UATP-08 «Hecho» con la nota de cómo se acreditó (no antes) |

No hay ADR: no cambia arquitectura, ni modelo, ni seguridad; solo se añaden campos de estado, una
ruta de lectura y textos. Si el PO considera que D-1/D-3 cambian un contrato público, se documenta en
las specs de BL-OPS1/2, no en un ADR nuevo.

### 10.3 Ficheros que tocará la implementación (orientativo)

- `src/zascarr/services/ops_host.py`, `src/zascarr/web/copias.py`, `src/zascarr/api/health.py`.
- `src/zascarr/web/templates/`: `_componentes.html`, `_copias_items.html`,
  `_restaurar_confirmar.html`, `_copias_estado.html`, `_restaurar_resultado.html`, `login.html`,
  `restauracion_resumen.html` (nueva).
- `scripts/_comun.sh`, `scripts/restaurar_datos.sh`.
- `tests/`: `test_copias_ops.py`, `test_copias_json.py`, `test_restauracion_estado.py`,
  `test_restaurar_produccion.py`, `test_restaurar_produccion_pg.py`, `test_health.py`, nuevo
  `test_web_uatp08.py`.
- Docs de §10.2. **Nada** de `alembic/versions/`, dependencias, JS ni biblioteca.

### 10.4 Definición de «lista para desarrollar» y de «hecho»

**Lista para desarrollar (DoR, no cumplida hoy):** D-1…D-5 registradas en #1146 por el PO (o
declaradas nulas con su motivo); base `origin/main` con A6; ninguna otra PR abierta que toque
`copias.json`/`ops-restaurar.json` sin coordinar; AC/tests de §6/§7 aceptados por PO y UX.

**Hecho (DoD, no cumplido hoy):** PR propia fusionada con TDD y sin migración/dependencias/JS;
T-08-01…T-08-14 en verde (T-08-15 PASS o NOT RUN declarado con motivo); E2E Chrome a 320/390/
escritorio y ambos temas con capturas; UAT-31 **PASS** con la explicación del agente y la evidencia
en A6 enlazada desde #1146/#1141; enmiendas de §10.2 aplicadas; matriz de AC con PASS/FAIL/NOT RUN y
**ningún NOT RUN en una comprobación obligatoria**; `docs/BACKLOG.md` actualizado con la nota
mecánica. Solo entonces se podrá declarar UATP-08 cumplida; este documento no lo hace.

---

## 11. Benchmark

No se repite el benchmark: [`docs/design/uatp08-readiness.md`](uatp08-readiness.md) §9 ya hizo la
ficha nivel 1 (Sonarr `v4.0.20.3014` / `develop@51a2412`, Kavita `v0.9.1.4` /
`develop@7f97cdca`) con vigencia hasta el **2027-01-20** o hasta que cambien las referencias o la
historia. Conclusiones que esta spec hereda:

- **Adoptar** listar copias con fecha/tamaño y acción «Restaurar…» (ya existe).
- **Adaptar** la versión incrustada al crear la copia: en ZascArr va al manifiesto y a
  `copias.json`/estado, no al nombre del fichero.
- **Descartar** la fecha relativa como única referencia y la restauración manual sin resumen.
- **Mejorar sobre lo propio** el resumen recuperado/omitido/fallo con comprobaciones e identidad: no
  hay referencia que lo cubra; ZascArr ya tiene los datos.
- **No escanear la biblioteca** para «omitido» (coste Pi; confusión catálogo/archivos).

Barrera legal: Sonarr y Kavita son GPL-3.0; solo se toman patrones, no código, y no se añade
dependencia.

---

## 12. Referencias y evidencia leída

**Código y contratos (base `origin/main@9fe0be06`; ficheros de UATP-07 ya fusionados):**

- `src/zascarr/services/ops_host.py`: fechas (`:270-291`), `leer_copias` (`:401-423`), mensajes de
  restauración (`:449-480`), `VistaRestaurar` (`:488-509`), `resolver_restauracion` (`:519-578`),
  aviso de `/login` (`:581-592`).
- `src/zascarr/web/copias.py`: `contexto_bloque` (`:52`), rutas (`:106,111,145,171`).
- Plantillas `_copias_items.html:9`, `_restaurar_confirmar.html:5-6,16-18`,
  `_copias_estado.html:11-14`, `_restaurar_resultado.html`, `_copias_bloque.html`,
  `_copias_lista.html`, `login.html:15`.
- `scripts/_comun.sh`: `leer_app_version`/`leer_build_sha` (`:301-338`), manifiesto (`:340-365`),
  `escribir_copias_json` (`:366-397`).
- `scripts/restaurar_datos.sh`: estado (`:57-200`), preflight (`:234-355`), inspección del dump
  (`:390-466`), `CONTEO_REST` (`:478`), `esperar_health` (`:522`), verificación de la base nueva
  (`:593-618`), producción (`:660-830`), éxito (`:822`), copia previa (`:760-780`).
- `src/zascarr/api/health.py:470-484` (payload `version`/`checks`); `src/zascarr/config.py:412-414`
  (`app_version`, `build_sha`).
- `src/zascarr/services/restauracion.py` (`ofrecer`, `solicitar`, `revision_actual`).
- `docs/design/especificacion-BL-OPS1.md:191-193` (FR-16), `:346` (AC-21).
- `docs/design/especificacion-BL-OPS2.md:122` (FR-24), `:130` (FR-29), `:133` (FR-32), `:237`
  (AC-41); `:352` (R-7).
- `docs/uat/A6/resultado.md`, `docs/uat/A6/evidencia/{resultado.txt,versiones.txt,negativas.json,instantaneas.json}`,
  `docs/uat/A6/evidencia/pasada2/{restauracion-ui.txt,n01-ui-resumen.txt,ops-restaurar-n01-ui.json,
  t1-arranque.txt,versiones-t1.txt}`.

**Pruebas leídas (base `origin/main`):** `tests/test_copias_ops.py:112,131-141`,
`tests/test_copias_json.py:52-66`, `tests/test_restauracion_estado.py:65-131,330-380`,
`tests/test_restaurar_produccion.py:390-525`, `tests/test_restaurar_produccion_pg.py`,
`tests/test_version_copia.py`, `tests/test_health.py:110-145`, `tests/test_restaurar_datos.py`.

**Issues comprobadas con `gh` el 2026-11-22:** #1146 **abierta** (sin comentarios de decisión del
PO); #1145 y #1144 **cerradas** el 2026-11-22; #1141 abierta. La épica y #1146 citan `A6/resultado.md`
como evidencia; A6 existe en `origin/main` desde `c4eff468` (2026-11-22).

**Estado de esta entrega:** documento de especificación únicamente. **No** hay rama de código, **no**
hay PR, **no** se ejecutan pruebas, **no** se modifica otro fichero y **no** se declara cumplida
UATP-08.
