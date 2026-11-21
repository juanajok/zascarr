# Readiness UATP-08 — Entender a qué momento vuelve la recuperación

> **Este documento NO es una especificación de implementación y NO declara cumplida UATP-08.**
> No implementa código, no cambia contratos vigentes, no crea ADR y no decide por el PO.
> Su único fin es fijar el estado real, las lagunas y las decisiones que deben tomarse antes
> de que [#1146](https://github.com/juanajok/zascarr/issues/1146) pueda especificarse y, más
> tarde, implementarse y acreditarse. Todo lo que aquí se propone es **borrador**.

| Dato | Valor |
|---|---|
| Historia | **UATP-08 · Entender a qué momento vuelve la recuperación** — P2 · talla S |
| Issue | [#1146](https://github.com/juanajok/zascarr/issues/1146) (épica [#1141](https://github.com/juanajok/zascarr/issues/1141)) |
| Dependencia declarada | **UATP-07 [#1145](https://github.com/juanajok/zascarr/issues/1145)** — P0, abierto, **sin implementación conocida** |
| Insumo | Informe de readiness task-48 (SCOUT.bench) + verificación directa sobre `origin/main` (código, specs, issues) |
| Relacionadas | #443 (BL-OPS1/2/3), [#1144](https://github.com/juanajok/zascarr/issues/1144) (UATP-06) |
| Base contrastada | `origin/main` @ `d5f26df57830d11b42a24c1e5bd4b60a96a2b9d0` (2026-11-21) |
| Fecha / autor | 2026-11-21 · SPEC.writer |
| Escritura | solo `docs/design/uatp08-readiness.md` |

**Veredicto de readiness: NO LISTA para especificar todavía.** Hay tres bloqueos duros, y
ninguno se cierra escribiendo código de UATP-08:

1. **UATP-07 no está implementada**: #1145 está abierto, sin rama, sin PR, sin comentarios y sin evidencia
   ([comprobado con `gh` el 2026-11-21](#12-dependencia-uatp-07)). Su parte de «restaurar la
   copia de archivos en un destino vacío» tampoco tiene procedimiento documentado en el producto:
   `backup.sh` solo copia PostgreSQL y `probar_restauracion.sh` solo restaura el dump en una base
   desechable, sin tocar archivos.
2. **La evidencia de cierre `A6` no existe** en el repositorio ni en el árbol de trabajo; en los
   issues solo se cita como evidencia: la épica menciona `A6/resultado.md` y
   `A6/evidencia/resultado.txt`, pero los ficheros no constan ([§4](#4-criterios-no-acreditables)).
   Cualquier criterio que los cite es **no acreditable** hasta que se recreen y se enlacen.
3. **El contrato actual no puede expresar lo que pide la historia**: ni versión de la copia, ni
   versión que volvió a arrancar, ni alcance, ni resumen recuperado/omitido/fallo, ni
   comprobaciones, ni diagnóstico con identidad. Existe el *plumbing* de BL-OPS1/2, no la capa de
   comprensión ([§2](#2-estado-actual-leído-en-originmaind5f26df5)).

Antes de especificar hacen falta las **decisiones D-1…D-7** del PO ([§5](#5-decisiones-que-debe-tomar-el-po-d-1d-7))
y, si el PO elige la opción que parece necesaria para el CA1, una **enmienda expresa de FR-16/FR-28**
([D-2](#d-2--qué-es-versión-de-la-copia-y-de-dónde-sale)). Nada de eso está hecho.

---

## 1. Dependencia

### 1.1 Cadena de dependencia real

| Eslabón | Estado leído | Qué aporta a UATP-08 | Qué falta |
|---|---|---|---|
| **UATP-07 [#1145](https://github.com/juanajok/zascarr/issues/1145)** | **Abierto.** Sin comentarios, sin PR enlazada y sin rama `uatp07`/`uatp08` en el checkout (2026-11-21) | El ensayo de recuperación que UATP-08 debe explicar: restaurar catálogo **y copia de archivos** en un destino vacío, reabrir el tebeo en su página guardada y acreditar la versión que abre | Todo: procedimiento de copia de archivos, ejecución, evidencia y la identidad de versión |
| **#443 BL-OPS2** (restaurar desde la interfaz) | Fusionada en `origin/main` (`ddf78cde`, 2026-11-17) | Flujo real de restauración: confirmación, petición firmada `v=2`, `restaurar_datos.sh --produccion`, `ops-restaurar.json` | ADR 0023 sigue **«propuesto. No desplegado»** (`docs/adr/0023-restaurar-copia-desde-interfaz.md:3`); la prueba real en la Pi es NOT RUN |
| **#443 BL-OPS1** (auxiliar del host) | Fusionada; ADR 0021 **propuesto**, instalación explícita con `scripts/instalar_ops.sh` | Canal por socket, cerrojo, estado de copia, `copias.json` | No está instalado por defecto; sin Pi verificada |
| **#443 BL-OPS3** (reautenticación) | Fusionada | La restauración exige la contraseña actual | Sin impacto directo en UATP-08 |
| **UATP-06 [#1144](https://github.com/juanajok/zascarr/issues/1144)** | Abierto | Caso negativo de copia dañada; alimenta el diagnóstico de fallo | No es dependencia declarada, pero sin su escenario el CA3 se acredita con ficción, no con un ensayo |

BL-OPS1/2 están **implementadas en `origin/main` y tienen pruebas en la suite (leídas, no ejecutadas aquí)**, pero eso no es lo mismo que «el flujo está
desplegado y acreditado en la candidata». UATP-08 pide entender el resultado de una recuperación
real; esa recuperación aún no se ha ejecutado con evidencia.

### 1.2 Dependencia UATP-07

#1145 exige, literalmente:

- crear un CBZ multipágina, avanzar a una página intermedia y guardar progreso **antes** del backup;
- «Restaurar el catálogo **y la copia de archivos** en un destino vacío»;
- tras reiniciar, la ficha ofrece continuar en esa página y el lector muestra esa página **del
  archivo correcto**;
- «Registrar que las relaciones, el progreso y la huella coinciden»;
- declarar **la versión que abre el archivo**, con un caso de tag sin lector.

Tres consecuencias para UATP-08:

1. **El producto no restaura archivos.** BL-OPS2 restaura **solo la base de datos** y deja la
   biblioteca intacta (`docs/design/especificacion-BL-OPS2.md` §0 y FR-35(e)); `backup.sh` solo
   hace `pg_dump` y `probar_restauracion.sh` solo toca PostgreSQL. La «copia de archivos» de
   UATP-07 es, hoy, un paso externo no documentado. Sin él, el «alcance de catálogo y archivos»
   del CA1 de UATP-08 no tiene un referente verificable: ¿se habla de la copia de la base, de una
   copia manual de la biblioteca o de ambas?
2. **La «huella testigo» es evidencia del ensayo, no un dato de producto.** No hay que pintarla en
   la UI; sí hay que decidir si el resumen de UATP-08 puede afirmar que la huella coincide o solo
   remitir al ensayo. La recomendación es lo segundo ([D-4](#d-4--qué-alcance-de-catálogo-y-archivos-declara-el-resumen)).
3. **La «versión que abre el archivo»** del CA de UATP-07 y la «versión que volvió a arrancar» de
   UATP-08 no son el mismo dato: la primera es la versión de la candidata que ejecuta el ensayo; la
   segunda, la que quedó en marcha tras restaurar. El contrato propuesto debe distinguirlas
   ([D-2](#d-2--qué-es-versión-de-la-copia-y-de-dónde-sale)), o la historia dirá «versión» para dos
   conceptos distintos.

### 1.3 Qué significa «depende de UATP-07» en la práctica

No es un bloqueo administrativo: UATP-08 no puede acreditar su prueba de cierre (UAT-31, una fila
añadida después de la copia, explicada a partir del resumen) porque:

- no hay recuperación de archivos ejecutada que sirva de contexto,
- no existe el resumen que hay que explicar,
- no existe `A6` donde constaría,
- la fila añadida después de la copia es precisamente un **cambio posterior**, y el producto hoy
  solo dice «se perderán los cambios posteriores» sin poder detallar ni un ejemplo
  (S1-05, §3.1).

Especificar UATP-08 antes de UATP-07 produciría una spec sobre una recuperación imaginaria.

---

## 2. Estado actual (leído en `origin/main@d5f26df5`)

### 2.1 Lo que ya existe y se puede leer

| Superficie | Qué muestra hoy | Evidencia |
|---|---|---|
| Listado «Copias de seguridad» de `/estado` | Fecha relativa, tamaño, «también en el disco de respaldo: sí/no» y botón «Restaurar…». **No muestra versión, ni id, ni revisiones.** | `src/zascarr/web/templates/_copias_items.html:9`; el lector sí calcula `revision` (`src/zascarr/services/ops_host.py:417`), pero la plantilla no la usa |
| Confirmación «Restaurar una copia» | «Vas a volver a los datos del {fecha}. Se perderán los cambios posteriores.»; aviso «ZascArr se parará uno o dos minutos. Tu biblioteca, tus archivos y el acceso actual no cambian…»; contraseña y casilla «Entiendo…» | `src/zascarr/web/templates/_restaurar_confirmar.html:5-6,16-18` |
| Resultado inmediato del POST | «Restauración en marcha. ZascArr se reiniciará en uno o dos minutos.» y enlace a Estado si no se aceptó | `src/zascarr/services/restauracion.py` (`solicitar`); `src/zascarr/web/templates/_restaurar_resultado.html` |
| Estado de la restauración | Bloque en `/estado` con «en marcha / sin noticias / hecha / fallo»; al terminar: «Copia del {día} restaurada: N series, N números y N archivos anotados…» | `src/zascarr/web/templates/_copias_estado.html:11-14`; `src/zascarr/services/ops_host.py:454-478` |
| Aviso de `/login` | «Se restauró una copia. Entra con tu contraseña de siempre.» (sin fecha, por ser público) | `src/zascarr/services/ops_host.py:458,581-592` |
| Diagnóstico de fallo | Catálogo cerrado de causa + acción (`CAUSAS_RESTAURAR`) y, si `base_en_su_sitio=false`, «ZascArr podría no responder ahora mismo» | `src/zascarr/services/ops_host.py:463-478`, `:568-577` |
| Estado persistido | `ops-restaurar.json` con fases y, al terminar, `recuentos` de **series, números y archivos anotados** | `scripts/restaurar_datos.sh:55-80` (escritor), `:699-704` (éxito) |

### 2.2 Qué comprueba realmente la restauración

El script **sí** hace comprobaciones serias antes de tocar la base viva:

| Comprobación | Dónde | ¿Se expone hoy? |
|---|---|---|
| SHA-256 del dump contra el manifiesto | `scripts/restaurar_datos.sh:261-264` | No; solo se usa para fallar |
| gzip, cabecera de `pg_dump` y tablas presentes | `scripts/restaurar_datos.sh` (verificación previa) | No |
| Revisión de Alembic del manifiesto y del dump | `scripts/restaurar_datos.sh:273-275,330-332` | No |
| Recuentos genéricos de **cada bloque `COPY`** y vínculos huérfanos en la base nueva | `scripts/restaurar_datos.sh:482-505` | Solo 3 números (`series`, `issues`, `files`) al final |
| Health con `checks.database == ok` | `scripts/restaurar_datos.sh:409-421` | No; el payload de health ya lleva `version` (`src/zascarr/api/health.py:459`), pero no se guarda |

Es decir: **el resultado está sustentado por comprobaciones, pero la persona no puede verlas**. Ese
es el hueco exacto de «qué comprobaciones sustentan el resultado» del CA2.

### 2.3 Qué está probado y qué no

| Cobertura | Estado | Evidencia |
|---|---|---|
| Lector de estado, mensajes de hecha/fallo, recuentos, zona horaria | Probado | `tests/test_restauracion_estado.py:65-131` |
| `copias.json` sin rutas ni hashes, 30 entradas, manifiesto corrupto | Probado | `tests/test_copias_json.py:1,52-66`; claves exactas en `:64` |
| Oferta de copias restaurables y orden de validación | Probado | `tests/test_restauracion_ops2.py:31-...` |
| Script de producción con `docker` falso, fallos, renombrado, cerrojo | Probado | `tests/test_restaurar_produccion.py:49-278` |
| Restauración real con PostgreSQL (proyecto aislado) | Probado si `TEST_DATABASE_URL`; si no, skip | `tests/test_restaurar_produccion_pg.py:227` |
| Fecha/hora absoluta con año, versión, resumen recuperado/omitido/fallo, comprobaciones, diagnóstico con identidad | **No existe** | — |
| Navegador real, Pi, systemd, ensayo de UATP-07 y evidencia A6 | **NOT RUN / no consta** | ADR 0023:3; UATP-07 sin rama; `A6` ausente |

### 2.4 Formatos actuales que importan

- `hora_llana` produce `«hoy a las 10:35»`, `«ayer a las 23:10»` o `«el 4 de noviembre a las 23:10»`
  **en la zona del servidor**: nunca incluye el año (`src/zascarr/services/ops_host.py:270-284`).
- `_dia_llano` produce solo día y mes (`:286-291`) y es lo que usa el mensaje de éxito
  (`:454-456`): el resultado final **no tiene ni hora ni año**.
- `copias.json` (FR-16) es una lista cerrada de `id`, `creada_epoch`, `bytes`, `fuera_del_disco`,
  `verificada` y, desde FR-28, `revision`; **sin rutas, sin nombres de fichero y sin hashes**
  (`docs/design/especificacion-BL-OPS1.md:191-193`; `docs/design/especificacion-BL-OPS2.md:129`).
- El manifiesto del backup **sí** guarda `codigo_desplegado_sha_completo` (SHA del commit) y
  `alembic`, pero la app no lo lee: el contenedor solo tiene montado el directorio de estado
  (`/run/backup-status`), no `BACKUP_DIR`.
- `app_version` existe (`src/zascarr/config.py:408`, hoy `1.15.1`), pero **no se escribe en el
  manifiesto** ni en `copias.json` ni en `ops-restaurar.json`.

---

## 3. Lagunas S1/S2

**Definición usada aquí.**

- **S1** — laguna que **impide acreditar** alguno de los tres criterios de #1146 o su prueba de
  cierre. No se cierra en la spec: exige decisión del PO, cambio de contrato o evidencia que hoy
  no existe.
- **S2** — laguna de coherencia o de superficie que no impide acreditar un criterio una vez
  cerrados los S1, pero que debe resolverse en la misma entrega para que el resultado sea
  utilizable y no genere deuda.

### 3.1 S1 — bloqueantes de acreditación

| ID | Laguna | Qué hay hoy | Por qué bloquea | Cierre |
|---|---|---|---|---|
| **S1-01** | **Fecha/hora absoluta** | `hoy`/`ayer`/«el D de M» sin año en confirmación; el éxito usa solo día y mes | El CA1 pide «fecha y versión»; el CA2, «el punto de copia». Sin año, una copia de enero puede ser de este año o del anterior; sin hora, no se distingue la copia de las 04:00 de una manual del mismo día | D-2/UX; formato absoluto con año y zona declarada; pruebas con `TZ` |
| **S1-02** | **Versión de la copia** | `revision` (Alembic) existe en `copias.json` pero la UI no la pinta; el manifiesto tiene el SHA del commit, pero la app no lo lee; FR-16 prohíbe hashes en `copias.json` | El CA1 exige identificar la copia «con fecha y versión». Hoy no hay ningún dato de versión en la confirmación; para copias viejas no hay `app_version` en el manifiesto | D-2 (semántica y fuente); posible enmienda de FR-16/FR-28 |
| **S1-03** | **Versión que volvió a arrancar** | No se registra. `/api/health` ya devuelve `version`, y `esperar_health` lo consulta, pero no lo guarda | El CA2 exige «la versión que volvió a arrancar». Mostrar la versión actual en el momento de leer el resumen puede ser otra si hubo actualización entre medias | D-2; guardar `version_arrancada` desde `/api/health` al terminar |
| **S1-04** | **Alcance catálogo/archivos** | El aviso dice «tu biblioteca, tus archivos y el acceso actual no cambian»; no dice **qué contiene la copia** ni que los archivos/portadas/`.env` quedan fuera | El CA1 exige «indica el alcance de catálogo y archivos». El texto actual es cierto para la restauración de la base, pero se lee como si los archivos estuvieran dentro; en el ensayo de UATP-07 (archivos restaurados aparte) es directamente ambiguo | D-4; texto de alcance; UATP-07 debe documentar la copia de archivos |
| **S1-05** | **Cambios posteriores** | «Se perderán los cambios posteriores» (sin ejemplos, sin magnitud) y la casilla «Entiendo…» repite lo mismo | El CA1 exige «advierte qué cambios posteriores podrían perderse»; hoy no se puede decir ni un ejemplo verificado (registros, ediciones, progreso) ni que mover/renombrar archivos hecho por ZascArr **no** se deshace (R-7, `docs/design/especificacion-BL-OPS2.md:352`) | D-6 |
| **S1-06** | **Resumen recuperado/omitido/fallo** | Solo `recuentos` de series/números/archivos anotados en `/estado`; no hay «omitido», ni resumen de fallo parcial, ni superficie tras reiniciar (el POST solo dice «en marcha») | El CA2 exige que el resumen «distinga recuperado, omitido y fallo» y muestre el punto de copia y la versión. Hoy no hay resumen; hay un mensaje | D-3, D-5; contrato de §6 |
| **S1-07** | **Comprobaciones** | El script verifica SHA, gzip, cabecera, tablas, revisión, recuentos genéricos, huérfanos y health, pero solo persiste el resultado y 3 recuentos | El CA2 exige «qué comprobaciones sustentan el resultado». Sin datos, la UI no puede distinguir «restaurada y comprobada» de «restaurada y no comprobada» | Contrato §6 (`comprobaciones`); D-3 |
| **S1-08** | **Diagnóstico con identidad y próximo paso** | Hay causa+acción cerrada (`CAUSAS_RESTAURAR`), pero el fallo no muestra id de copia, fecha absoluta, versión ni un código de soporte; `unexpected` cae en genérico; el enlace es «Volver a Estado», no «elegir otra copia» | El CA3 exige «diagnóstico y próximo paso» y quedar «identificado como fallo aunque se haya recuperado parte». Identificar el fallo sin identificar **de qué copia y de qué intento** no permite soporte ni repetir el caso | D-7; contrato §6 |

### 3.2 S2 — coherencia y superficie

| ID | Laguna | Detalle | Cierre |
|---|---|---|---|
| **S2-01** | La confirmación no muestra el **id** de la copia ni su tamaño | Solo la fecha; la lista sí tiene id (para la URL) | Texto de confirmación |
| **S2-02** | «Archivos anotados» puede confundirse con archivos del disco | El glosario distingue archivo (fichero) de registro; «anotados» no está explicado en la pantalla (`CLAUDE.md` §14) | Copy/UX; spec de textos |
| **S2-03** | La zona horaria no se declara | `hora_llana` usa la zona del servidor; hay prueba (`tests/test_copias_ops.py:112`), pero la pantalla no dice «hora del servidor» | Formato absoluto de D-2/UX |
| **S2-04** | El aviso de `/login` no enlaza al resumen | Es público y no puede llevar fecha; tras entrar, la persona puede no volver a Estado | D-3 (ruta estable + enlace) |
| **S2-05** | El fallo no ofrece «elegir otra copia» | «Volver a Estado» es un paso más; la lista es la acción natural | D-7/UX |
| **S2-06** | No hay criterio de accesibilidad/320 px para el resumen | No existe la pantalla; hay que fijarlo en la spec (una principal, foco, `aria-live`, sin JS) | Spec/UX |

### 3.3 Lo que **no** es una laguna (para no confundir alcance)

- Restaurar **solo** el catálogo y no tocar la biblioteca es una decisión deliberada de BL-OPS2
  (`especificacion-BL-OPS2.md` §0, FR-35(e)), no un bug de UATP-08.
- La restauración no trae contraseñas ni sesiones antiguas: es FR-34/FR-35, correcto.
- No hay que mostrar rutas, nombres de fichero ni hashes: FR-16 y C-13 lo prohíben. La versión de
  D-2 debe encajar en esa prohibición o enmendarla expresamente ([D-2](#d-2--qué-es-versión-de-la-copia-y-de-dónde-sale)).

---

## 4. Criterios no acreditables

Ningún criterio de #1146 es acreditable hoy. La tabla distingue «existe el flujo» de «UATP-08 está
cumplida»: lo primero es cierto en parte; lo segundo, no.

| Criterio de #1146 | ¿Acreditable hoy? | Motivo | Qué haría falta |
|---|---|---|---|
| **CA1** — antes de confirmar, identificar la copia con fecha y versión, alcance catálogo/archivos y aviso de cambios posteriores | **NO** | Fecha relativa sin año; versión ausente; alcance ambiguo; cambios posteriores genéricos (S1-01, S1-02, S1-04, S1-05) | D-2, D-4, D-6; texto y contrato |
| **CA2** — al finalizar, resumen que distingue recuperado, omitido y fallo; punto de copia; versión que volvió a arrancar; comprobaciones | **NO** | No hay resumen persistente ni «omitido»; no se registra versión de arranque; no se exponen comprobaciones (S1-03, S1-06, S1-07) | D-2, D-3, D-5; contrato §6; ruta de resumen |
| **CA3** — fallo con diagnóstico y próximo paso, identificado como fallo aunque se haya recuperado parte | **NO (parcial)** | Hay causa+acción y `base_en_su_sitio`, pero falta identidad de copia/intento y código de soporte; «recuperado parte» no se expresa (S1-08) | D-7; contrato §6; caso negativo de UATP-06 |
| **Prueba de cierre UAT-31** — fila añadida después de la copia; explicar a partir del resumen por qué quedó fuera; evidencia `A6/resultado.md` | **NO** | `A6` no existe; UATP-07 no se ha ejecutado; el resumen que hay que explicar no existe; «cambios posteriores» no se detalla | Recrear A6; cerrar UATP-07; D-6; resumen |
| **Evidencia `A6/evidencia/resultado.txt`** | **NO** | No consta en el repo ni en el árbol; en los issues solo se cita como evidencia pendiente | Definir su ubicación y enlazarla; no vale un texto fabricado |
| **Ensayo de UATP-07** (catálogo + archivos, página guardada, huella, versión que abre) | **NO** | #1145 abierto sin implementación ni procedimiento de copia de archivos | Ejecutarlo y enlazar su evidencia |
| **«La versión que abre el archivo»** (UATP-07) vs **«la versión que volvió a arrancar»** (UATP-08) | **NO aclarado** | Hoy «versión» no está definida y los dos criterios pueden estar hablando de cosas distintas | D-2 |

**Lo que sí se puede afirmar hoy sin mentir:** el flujo de restauración de BL-OPS2 existe en
`origin/main`, está probado en la suite y su lector de estado pinta «en marcha / hecha / fallo» con
causa y acción. **No** se puede afirmar que UATP-08 esté cumplida, ni parcialmente, ni que
`A6` exista.

---

## 5. Decisiones que debe tomar el PO (D-1…D-7)

Las recomendaciones son del SPEC.writer; **decide el PO**. Ninguna decisión autoriza implementar:
solo desbloquean la especificación. La opción recomendada va primero.

### D-1 — ¿UATP-08 es producto, runbook o ambos?

**Pregunta.** El CA1 dice «el **procedimiento** identifica…», lo que puede cumplirse con un
runbook de recuperación y evidencia, sin tocar la UI. El CA2 («un resumen utilizable») y el CA3
(«un fallo ofrece diagnóstico») suenan a producto. ¿Qué se entrega?

**Opciones.**

- **(a) Ambos, acotados (recomendada).** Una ruta de resumen en el producto (fecha absoluta,
  versión, alcance, resumen y diagnóstico) **más** un runbook de recuperación que fije el ensayo,
  la copia de archivos externa y la evidencia UAT-31. El producto no restaura archivos.
- **(b) Solo runbook.** No se toca código; todo se acredita con documento y evidencia. Riesgo:
  el CA2/CA3 quedan como «lo que hizo el operador», no como comportamiento del producto, y la
  persona que restaura sigue sin ver el resumen en la app.
- **(c) Solo producto.** Se implementa la UI y se deja el ensayo para UATP-07. Riesgo: el CA1
  habla de procedimiento y la prueba de cierre exige una ejecución real; sin runbook no hay
  evidencia reproducible.

**Recomendación.** (a). El producto ya tiene el flujo; lo que falta es que la persona pueda
entenderlo. El runbook es lo que hace la evidencia repetible y lo que conecta con UATP-07.
**Consecuencia:** si (a), UATP-08 toca `services/ops_host.py`, `web/copias.py`, plantillas y
scripts de estado, y necesita un runbook nuevo. **Afecta a:** alcance de la historia, DoR, PRs.

### D-2 — ¿Qué es «versión» de la copia y de dónde sale?

**Pregunta.** «Versión» puede ser (i) la revisión de Alembic, (ii) la versión semver de la app,
(iii) el SHA del código, o (iv) una combinación. Hoy solo existe la (i) en `copias.json`; la (iii)
está en el manifiesto, que la app no puede leer; la (ii) no se guarda en ningún sitio del backup.

**Opciones.**

- **(a) Semver + revisión de Alembic; SHA solo en detalle técnico colapsado; `null` = «no consta»
  (recomendada).** Añadir `app_version` al manifiesto para copias nuevas y `version` (semver,
  nullable) a `copias.json`/`ops-restaurar.json`. Para copias antiguas, «versión no consta»: no se
  infiere. El SHA del commit (si se quiere para soporte) va en el detalle técnico, nunca en la
  lista pública. **Exige enmendar FR-16/FR-28** para añadir `version` a la lista cerrada (no es un
  hash) y adaptar `tests/test_copias_json.py:64`.
- **(b) Solo revisión de Alembic.** No se toca FR-16; la confirmación muestra «revisión 0041».
  Riesgo: para el coleccionista «0041» no es una versión, y el CA1 pide identificar la copia con
  versión; quedaría acreditado de forma débil o no acreditado.
- **(c) SHA en `copias.json`.** Rompe FR-16 («sin hashes») y añade un identificador que no es
  legible para el coleccionista. **Descartada** salvo que el PO cambie la regla expresamente.
- **(d) No mostrar versión y rebajar el CA1.** Permitiría no tocar FR-16, pero contradice el issue
  y la prueba de cierre. **No recomendada.**

**Recomendación.** (a), con `version = null` y texto «versión no consta» cuando el manifiesto no
la traiga. **Consecuencia:** enmienda documental de FR-16/FR-28 + `app_version` en el manifiesto de
copias nuevas; ninguna migración. **Afecta a:** `scripts/_comun.sh::escribir_manifiesto`,
`scripts/_comun.sh::escribir_copias_json`, `services/ops_host.py`, tests de FR-16.

### D-3 — ¿Dónde vive el resumen después de restaurar?

**Pregunta.** Durante la restauración la app se para y se reinicia; el POST solo puede decir «en
marcha». ¿Dónde lee la persona el resultado final?

**Opciones.**

- **(a) Ruta estable `/ui/copias/restauracion` (o similar) + enlace desde Estado y desde el aviso
  de `/login` tras autenticarse (recomendada).** GET sin efectos, detrás de la autenticación
  existente, `no-store`; lee `ops-restaurar.json` y pinta resumen o diagnóstico. Sobrevive a
  cerrar la pestaña y a una actualización posterior (si se conserva el fichero).
- **(b) Solo el bloque de `/estado` (hoy).** Menos trabajo, pero la persona tiene que volver a
  Estado; el aviso de `/login` no enlaza; si se pierde el momento, el resumen queda enterrado.
- **(c) Página solo cuando hay fallo.** El éxito se queda en Estado. Riesgo: el CA2 pide resumen
  también en éxito.

**Recomendación.** (a), con enlace desde Estado y desde `/login` (sin fecha en el aviso público).
**Consecuencia:** ruta nueva en `web/copias.py`, plantilla y pruebas; sin migración.
**Afecta a:** FR-29/FR-32 de BL-OPS2 y a la navegación de Estado.

### D-4 — ¿Qué alcance de catálogo y archivos declara el resumen?

**Pregunta.** La copia contiene solo la base de datos. La biblioteca (CBZ/CBR), las portadas y la
configuración del equipo quedan fuera. ¿Cómo se declara, y se mide algo del disco?

**Opciones.**

- **(a) Declaración honesta, sin medir el disco (recomendada).** «Esta copia contiene el catálogo
  (series, números, fichas y progreso). No contiene los archivos de tu biblioteca, las portadas ni
  la configuración; ZascArr no los toca al restaurar.» El runbook de UATP-07 documenta la copia de
  archivos como paso externo. No se escanea la biblioteca al pintar (Pi, CLAUDE.md §4).
- **(b) Medir el estado de los archivos en el resumen** (faltantes, sin fila) reutilizando
  disponibilidad/auditoría. Riesgo: escaneo caro, resultados aproximados, y confunde «restaurar la
  base» con «restaurar la biblioteca».
- **(c) Silencio: no hablar de archivos.** Riesgo: la persona cree que la copia incluye sus CBZ.

**Recomendación.** (a) ahora; si el PO quiere medición, historia aparte con presupuesto de Pi.
**Consecuencia:** texto de confirmación/resumen y runbook. **Afecta a:** CA1, CA2, UATP-07.

### D-5 — ¿Qué significa «omitido» en el resumen?

**Pregunta.** La restauración del catálogo es **todo o nada** (si algo falla, no se cambia la base).
Entonces «omitido» no puede significar «filas que no se restauraron» salvo en un fallo. ¿Qué
categorías entran?

**Opciones.**

- **(a) Lista cerrada de lo que queda fuera de la copia (recomendada):**
  `archivos_biblioteca`, `portadas`, `configuracion`, `cambios_posteriores`. Cada una con `n`
  cuando se pueda medir y `null` cuando no; nunca texto libre. No se inventa «catálogo parcial».
- **(b) Omitido = filas no restauradas.** Solo tendría sentido en un fallo parcial; hoy el diseño
  evita ese estado. Podría confundir y prometer una granularidad que no existe.
- **(c) No usar la palabra «omitido».** El CA2 la exige; habría que rebajar el criterio.

**Recomendación.** (a), con la frase «no se ha omitido ningún dato del catálogo; queda fuera lo
que no contiene la copia». **Consecuencia:** contrato `omitido` cerrado; pruebas de que un catálogo
restaurado no declara omisiones falsas. **Afecta a:** CA2, contrato §6.

### D-6 — «Cambios posteriores»: ¿aviso genérico o medición?

**Pregunta.** El CA1 pide advertir «qué cambios posteriores podrían perderse». La copia tiene
fecha; la base viva puede tener actividad posterior. ¿Se cuenta o se explica?

**Opciones.**

- **(a) Aviso genérico con ejemplos verificados (recomendada):** registros y ediciones hechos en
  ZascArr, progreso de lectura; y una frase específica de que mover/renombrar archivos hecho por
  ZascArr **no** se deshace (R-7). Coste cero, sin consultas caras, sin prometer precisión.
- **(b) Medir actividad posterior** con agregados por `created_at`/`updated_at` de las tablas
  principales desde `copia_epoch`. Más útil, pero aproximado (no todas las tablas tienen las
  mismas marcas), puede ser caro y puede mentir por omisión.
- **(c) Ambas:** genérico + un único agregado barato si existe índice; si no, `null`.

**Recomendación.** (a) para esta historia; (b)/(c) solo si el PO acepta el coste y el límite de
precisión. **Consecuencia:** texto de confirmación; si (b), consulta nueva en la app **antes** de
restaurar (solo lectura) y prueba de rendimiento en Pi. **Afecta a:** CA1, S1-05.

### D-7 — Diagnóstico con identidad y próximo paso

**Pregunta.** El fallo ya tiene causa+acción. ¿Qué identidad se añade para que la persona y quien
le ayude puedan repetir el caso sin leer logs?

**Opciones.**

- **(a) Identidad de copia e intento (recomendada):** id de copia (`backup-…`), fecha/hora
  absoluta, versión (o «no consta»), `error` como **código para soporte** con formato cerrado
  (`R-<TS>-<error>`), `intento` (id de `ops-status.json` si consta) y `base_en_su_sitio` en llano.
  Sin rutas, sin secretos, sin hashes; el detalle técnico va colapsado («Para quien instaló
  ZascArr»).
- **(b) Solo causa+acción (hoy).** Insuficiente para el CA3 y para soporte.
- **(c) Volcar el código `error` en claro en la pantalla principal.** Puede ser jerga para el
  coleccionista; mejor en detalle colapsado y con texto llano delante.

**Recomendación.** (a); el próximo paso incluye «Elige otra copia» con enlace a la lista y, si
`base_en_su_sitio=false`, «Avisa a quien instaló ZascArr». **Consecuencia:** contrato §6 y textos;
pruebas de códigos desconocidos. **Afecta a:** CA3, S1-08.

### 5.1 Resumen de decisiones

| ID | Decisión | Recomendación | Bloquea |
|---|---|---|---|
| D-1 | Producto / runbook / ambos | Ambos, acotados | Alcance y DoR |
| D-2 | Semántica y fuente de «versión» | Semver + revisión; SHA en detalle; enmienda FR-16/FR-28 | CA1 |
| D-3 | Dónde vive el resumen | Ruta estable + enlaces | CA2 |
| D-4 | Alcance catálogo/archivos | Declaración honesta sin escaneo | CA1, CA2 |
| D-5 | Semántica de «omitido» | Lista cerrada de lo que queda fuera | CA2 |
| D-6 | Cambios posteriores | Aviso genérico con ejemplos + R-7 | CA1 |
| D-7 | Diagnóstico con identidad | Copia + intento + código de soporte | CA3 |

---

## 6. Contrato de datos propuesto

> **Propuesta, no aprobada.** Nada de esto está implementado. Respeta las invariantes de BL-OPS2:
> los ficheros de estado los escribe **solo** el host; la app solo lee; nada de rutas, nombres de
> fichero, hashes, secretos ni texto libre; escritura atómica (`temporal` + `mv`), `0644`, y el
> lector tolera claves desconocidas y tipos erróneos sin romper.

### 6.1 Principios

1. **Solo códigos, números, booleanos y `null`.** Nada de cadenas libres del fichero al HTML.
2. **Aditivo.** `schema` sube a `2` en `ops-restaurar.json`; el lector deberá aceptar `1` y `2` (si `1`, se
   comporta como hoy). `copias.json` sigue en `schema: 1`.
3. **Nada de hashes en la superficie.** `comprobaciones` lleva el **resultado** (`ok/fallo`), no el
   SHA; `copias.json` no gana hashes (FR-16 salvo D-2(a)).
4. **Compatibilidad hacia atrás.** Copias antiguas sin `version` → `null` → «no consta»; nunca se
   infiere.
5. **Sin coste en Pi.** El resumen se compone de ficheros pequeños ya existentes; no escanea la
   biblioteca ni consulta la base para pintar.

### 6.2 `copias.json` (lista; solo si D-2(a))

Se mantiene la lista cerrada de FR-16 y el campo `revision` de FR-28. Se **propone** añadir:

| Campo | Tipo | Regla |
|---|---|---|
| `version` | string o `null` | Semver `^[0-9]+\.[0-9]+\.[0-9]+$`; `null` si el manifiesto no la trae. **No es un hash.** |

- Sigue prohibido: `ruta`, `backup`, `sha256`, `origin`, `commit`, nombres de fichero.
- Máximo 30 entradas, más recientes; sin copias `update_*` ni `rollback-safety_*`.
- Si el PO elige D-2(b), este campo **no** se añade y la confirmación solo puede mostrar la
  revisión de Alembic (CA1 queda débil; ver D-2).

### 6.3 Manifiesto (solo copias nuevas)

Añadir `app_version` (semver) al manifiesto de `escribir_manifiesto` para que las copias nuevas
puedan declarar su versión. Las copias antiguas no lo tienen: `copias.json.version = null` y
«versión no consta». **No** se reescriben manifiestos antiguos.

### 6.4 `ops-restaurar.json` — propuesta de `schema: 2`

Campos actuales que se conservan sin cambio semántico:

| Campo | Tipo | Nota |
|---|---|---|
| `schema` | entero | `2` en el nuevo escritor; el lector acepta `1` |
| `copia` | string | `backup-YYYYMMDD_HHMMSS` |
| `copia_epoch` | entero | instante de la copia; la UI lo pinta absoluto |
| `inicio_epoch`, `actualizado_epoch` | enteros | fases y obsolescencia (FR-25) |
| `fase`, `resultado`, `error` | códigos | listas cerradas actuales |
| `base_en_su_sitio` | bool o `null` | ya existe |
| `recuentos` | objeto o `null` | `series`, `issues`, `files` con `hecha` |

Campos nuevos propuestos (todos aditivos, cerrados, sin texto libre):

| Campo | Tipo | Cuándo | Regla |
|---|---|---|---|
| `copia_revision` | string o `null` | toda la ejecución | `^[A-Za-z0-9_.-]{1,64}$`, tomada del manifiesto |
| `copia_version` | string o `null` | toda la ejecución | semver de D-2, o `null` |
| `version_arrancada` | string o `null` | solo `hecha` | `version` leída de `/api/health` tras arrancar (`src/zascarr/api/health.py:459`); no se infiere |
| `intento` | string o `null` | toda la ejecución | id de `ops-status.json` (`secrets.token_hex(16)`), si consta; sirve para soporte |
| `comprobaciones` | array de objetos | al terminar (éxito o fallo) | `[{"codigo": …, "estado": "ok"/"aviso"/"fallo"/"no_ejecutada"}]`; lista cerrada de códigos (§6.5) |
| `omitido` | array de objetos | al terminar | `[{"codigo": …, "n": entero o null}]`; lista cerrada (§6.6) |

Sin campos nuevos para el diagnóstico: la UI lo compone con `copia`, `copia_epoch`,
`copia_version`, `intento`, `error` y `base_en_su_sitio`. El `id` de soporte se **deriva**
(`R-<TS>-<error>`), no se guarda, para no duplicar verdad.

### 6.5 Códigos de `comprobaciones` (lista cerrada)

`sha256_copia`, `gzip_cabecera`, `tablas_dump`, `alembic_revision`, `recuentos_genericos`,
`vinculos_huerfanos`, `health`.

- Solo el **estado**, nunca el valor del hash ni la salida de `psql`.
- Las comprobaciones que no llegaron a ejecutarse llevan `no_ejecutada` (no se omiten).
- La UI puede plegarlas en «Para quien instaló ZascArr»; el resumen llano dice «se comprobó la
  copia y la base restaurada» solo si las críticas están en `ok`.
- Códigos nuevos exigen fila en la spec y prueba de que la UI los pinta; uno desconocido no rompe
  y cae en «no consta».

### 6.6 Códigos de `omitido` (lista cerrada)

| Código | Significado | `n` |
|---|---|---|
| `archivos_biblioteca` | Los CBZ/CBR no van dentro de la copia y ZascArr no los toca | `null` salvo que D-4(b) mida |
| `portadas` | Las portadas cacheadas no se restauran | `null` |
| `configuracion` | `.env`, credenciales y exposición no se restauran; se conserva lo vigente | `null` |
| `cambios_posteriores` | Lo anotado/edita/leído después de la copia no vuelve | `null` salvo D-6(b) |

- **No existe** `catalogo_parcial`: el catálogo es todo o nada. La UI no debe insinuar lo contrario.
- `n` es un entero o `null`; nunca una frase.

### 6.7 Ejemplo (éxito)

```json
{
  "schema": 2,
  "copia": "backup-20261120_040000",
  "copia_epoch": 1763611200,
  "copia_revision": "0041",
  "copia_version": "1.15.1",
  "inicio_epoch": 1763614800,
  "actualizado_epoch": 1763614980,
  "fase": "arrancando",
  "resultado": "hecha",
  "error": null,
  "base_en_su_sitio": true,
  "intento": "3f2a8c1d4b5e6f708192a3b4c5d6e7f8",
  "recuentos": {"series": 42, "issues": 1230, "files": 1180},
  "version_arrancada": "1.15.1",
  "omitido": [
    {"codigo": "archivos_biblioteca", "n": null},
    {"codigo": "portadas", "n": null},
    {"codigo": "configuracion", "n": null},
    {"codigo": "cambios_posteriores", "n": null}
  ],
  "comprobaciones": [
    {"codigo": "sha256_copia", "estado": "ok"},
    {"codigo": "gzip_cabecera", "estado": "ok"},
    {"codigo": "tablas_dump", "estado": "ok"},
    {"codigo": "alembic_revision", "estado": "ok"},
    {"codigo": "recuentos_genericos", "estado": "ok"},
    {"codigo": "vinculos_huerfanos", "estado": "ok"},
    {"codigo": "health", "estado": "ok"}
  ]
}
```

### 6.8 Ejemplo (fallo)

```json
{
  "schema": 2,
  "copia": "backup-20261120_040000",
  "copia_epoch": 1763611200,
  "copia_revision": "0041",
  "copia_version": null,
  "inicio_epoch": 1763614800,
  "actualizado_epoch": 1763614812,
  "fase": "verificando",
  "resultado": "fallida",
  "error": "copia_no_valida",
  "base_en_su_sitio": true,
  "intento": "3f2a8c1d4b5e6f708192a3b4c5d6e7f8",
  "recuentos": null,
  "version_arrancada": null,
  "omitido": [],
  "comprobaciones": [
    {"codigo": "sha256_copia", "estado": "fallo"},
    {"codigo": "gzip_cabecera", "estado": "no_ejecutada"}
  ]
}
```

### 6.9 Composición en la interfaz (propuesta)

- **Fecha absoluta:** `dd/mm/aaaa a las HH:MM` en la zona del servidor, con `(hora del servidor)`
  una vez por pantalla; nunca «hoy/ayer» en el momento de decidir. Prueba explícita con `TZ`
  distinta (como `tests/test_copias_ops.py:112`).
- **Confirmación:** id de copia, fecha/hora absoluta, versión + revisión, alcance y aviso de
  cambios posteriores; «Entiendo…» se conserva; una sola acción principal.
- **Resumen:** ruta estable; punto de copia; «Recuperado» (recuentos), «Queda fuera» (códigos de
  `omitido`), «Comprobaciones» (plegadas), «Versión en marcha» (`version_arrancada`); en fallo,
  «No se pudo restaurar» + causa + acción + código de soporte + `base_en_su_sitio`.
- **Sin secretos:** ni contraseña, ni rutas, ni hashes, ni salida de scripts. Detalle técnico solo
  en `<details>`.
- **Accesibilidad:** texto ≥ 14 px, foco visible, `aria-live` para el estado, 320 px, ambos temas,
  sin JS nuevo; una sola acción principal por pantalla (`CLAUDE.md` §6).

---

## 7. AC borrador

> **Borrador, no aprobado.** No son AC de una spec aprobada; sirven para que el PO y UX discutan
> y para que la spec futura no invente. Ninguno está implementado ni acreditado. La numeración es
> local a este documento.

- **AC-B01 (identificar la copia).** CUANDO la persona abra la confirmación de una copia
  restaurable, ENTONCES verá, como mínimo: id de copia, fecha y hora **absolutas con año**, zona
  horaria declarada, versión semver (o «versión no consta») y revisión de Alembic. No se usará
  «hoy/ayer» como única referencia.
- **AC-B02 (alcance).** ENTONCES la pantalla dirá qué contiene la copia (catálogo: series, números,
  fichas y progreso) y qué no (archivos de la biblioteca, portadas, configuración), y que ZascArr
  no toca la biblioteca al restaurar. No afirmará ni insinuará que los CBZ están dentro.
- **AC-B03 (cambios posteriores).** ENTONCES el aviso explicará, con ejemplos, qué se pierde
  (registros, ediciones, progreso de lectura anotados después) y que mover/renombrar archivos
  hecho por ZascArr **no** se deshace. No prometerá una lista exacta si D-6(a).
- **AC-B04 (resumen tras reiniciar).** CUANDO termine una restauración con éxito, ENTONCES existirá
  una superficie persistente (ruta propia) alcanzable después del reinicio, con el punto de copia
  (fecha/hora absolutas), la versión que volvió a arrancar y los recuentos recuperados. No
  dependerá de que la persona no cierre la pestaña.
- **AC-B05 (recuperado).** ENTONCES «recuperado» se expresará con los recuentos de series, números
  y archivos anotados, coincidentes con la base restaurada; el texto distinguirá «archivos
  anotados» de archivos en disco.
- **AC-B06 (omitido).** ENTONCES el resumen dirá qué queda fuera con una lista cerrada (archivos de
  biblioteca, portadas, configuración, cambios posteriores), sin texto libre; no declarará
  «catálogo parcial» si la restauración fue todo o nada.
- **AC-B07 (fallo identificado).** CUANDO falle, ENTONCES el resultado se identificará como fallo
  aunque parte del sistema se haya recuperado; dirá la causa, la acción y si la base vigente está
  en su sitio (`base_en_su_sitio`), en llano.
- **AC-B08 (comprobaciones).** ENTONCES el resumen permitirá saber qué comprobaciones sustentan el
  resultado (copia, revisión, recuentos, huérfanos, health) mediante códigos y estados; nunca
  mostrará hashes, rutas ni salida de scripts.
- **AC-B09 (diagnóstico con identidad).** CUANDO falle, ENTONCES el diagnóstico incluirá id de
  copia, fecha/hora absoluta, versión (o «no consta»), código de soporte con formato cerrado,
  intento si consta, y un próximo paso; un código desconocido caerá en un texto genérico sin
  mentir.
- **AC-B10 (robustez).** Dados ficheros de estado ausentes, antiguos (`schema: 1`), con campos
  desconocidos, tipos erróneos, épocas futuras o copias sin versión, ENTONCES la UI no dará 500,
  no pintará valores libres y usará «no consta»/«causa desconocida» según corresponda.
- **AC-B11 (accesibilidad y superficie).** ENTONCES confirmación y resumen serán usables a 320 px,
  con teclado, con texto ≥ 14 px, en ambos temas, con una sola acción principal y sin JS nuevo.
- **AC-B12 (no regresión).** ENTONCES no habrá migración ni dependencia nueva; la restauración
  seguirá restaurando solo el catálogo y no tocará la biblioteca; FR-16 seguirá intacto salvo la
  enmienda aprobada en D-2(a); las pruebas existentes de BL-OPS1/2 seguirán pasando.

**No-goals del borrador:** restaurar archivos de la biblioteca desde ZascArr; «deshacer» una
restauración; borrar copias; actualizar el código; medir la biblioteca en cada pintado; mostrar
hashes, rutas o secretos; desplegar en la Pi sin ventana y autorización.

---

## 8. Pruebas futuras (ninguna ejecutada)

Todas las filas están **NOT RUN**: no hay implementación. La tabla fija qué habrá que probar y
dónde, para que la spec no deje huecos.

| ID | Tipo | Qué comprueba | Dónde | Estado |
|---|---|---|---|---|
| T-08-01 | Unit (servicio) | Fecha absoluta con año y `TZ` distinta; nunca «hoy/ayer» en la decisión | `tests/test_restauracion_estado.py` o nuevo `tests/test_uatp08_fechas.py` | NOT RUN |
| T-08-02 | Unit (servicio) | `resolver_restauracion` con `schema: 2`, `version`, `copia_version`, `version_arrancada`, `omitido`, `comprobaciones`; `schema: 1` sigue funcionando | `tests/test_restauracion_estado.py` | NOT RUN |
| T-08-03 | Unit (servicio) | Ficheros hostiles: cadenas largas, HTML, tipos erróneos, épocas futuras, listas enormes, códigos desconocidos | `tests/test_restauracion_estado.py` (patrón `:156`) | NOT RUN |
| T-08-04 | Unit (servicio) | Copia antigua sin `version` → «versión no consta»; nunca se infiere | nuevo | NOT RUN |
| T-08-05 | Web (FakeSession) | Confirmación muestra id, fecha absoluta, versión/revisión, alcance y aviso de cambios posteriores; no muestra secretos | `tests/test_copias_ops.py` o nuevo `tests/test_web_uatp08.py` | NOT RUN |
| T-08-06 | Web | Resumen de éxito y de fallo; ruta estable detrás de auth; `no-store`; sin sesión redirige; enlaces desde Estado y `/login` | nuevo | NOT RUN |
| T-08-07 | Script (host) | `ops-restaurar.json` escribe los campos nuevos con `schema: 2`, atómico, `0644`, solo códigos/números, sin rutas/hashes/secretos | `tests/test_restaurar_produccion.py` (extensión) | NOT RUN |
| T-08-08 | Script (host) | En fallo antes del cambio: `base_en_su_sitio: true`, `omitido` vacío o correcto, comprobaciones `no_ejecutada`; en `recuperacion_fallida`: `false` | `tests/test_restaurar_produccion.py:136-278` (extensión) | NOT RUN |
| T-08-09 | PG real | Restauración completa con una fila añadida después de la copia: recuentos y resumen cuadran; el resumen no afirma que la fila está | `tests/test_restaurar_produccion_pg.py` (extensión) | NOT RUN |
| T-08-10 | PG real / aislado | Ensayo de UATP-07: catálogo + copia de archivos en destino vacío; página guardada; huella; versión que abre | runbook nuevo + evidencia externa | NOT RUN |
| T-08-11 | Navegador E2E | Confirmación y resumen a 320 px, ambos temas, teclado, `aria-live`, foco; sin JS nuevo; capturas | `docs/TESTING_E2E.md` §13 (nuevo bloque) | NOT RUN |
| T-08-12 | UAT / evidencia | UAT-31: fila añadida después de la copia; el agente explica a partir del resumen por qué quedó fuera; `A6/resultado.md` + `A6/evidencia/resultado.txt` | evidencia a definir ([§10](#10-condición-de-desbloqueo)) | NOT RUN |
| T-08-13 | Regresión | FR-16/FR-28 (`tests/test_copias_json.py:64`), ops (`test_ops_paridad.py`), estado y `/login`; suite no-PG; `ruff check src/` | CI | NOT RUN |
| T-08-14 | Rendimiento (Pi) | El resumen se pinta desde ficheros pequeños, sin escanear biblioteca ni consultar la base; sin picos de RAM | Pi / medición | NOT RUN |

**Prueba que debe fallar antes de implementar** (TDD): T-08-01 (fecha absoluta), T-08-02
(`schema: 2`), T-08-04 («no consta»), T-08-06 (ruta de resumen) y T-08-07 (escritura del nuevo
contrato) deben escribirse primero y fallar por la razón correcta.

---

## 9. Benchmark nivel 1

> Ficha breve de `docs/design/benchmark-referencias.md` (nivel 1: ≤ 2 referencias, sin matriz).
> **Es insumo, no aprobación.** No se ha ejecutado nada de las referencias: solo se ha leído
> código y documentación (**NOT RUN**). Caduca el **2027-01-20** (≈ 60 días) o antes si cambian
> las referencias o la historia.

**Historia / problema observado.** UATP-08: antes de restaurar hay que entender a qué momento se
vuelve; después, distinguir recuperado/omitido/fallo y saber qué versión arrancó y qué
comprobaciones lo sustentan. Hoy ZascArr muestra fecha relativa, tres recuentos y causa+acción;
no muestra versión, alcance, omitido, comprobaciones ni identidad ([§2](#2-estado-actual-leído-en-originmaind5f26df5)).

**Datos reales y medición de partida.**

- Copia actual: `copias.json` con `id`, `creada_epoch`, `bytes`, `fuera_del_disco`, `verificada`,
  `revision`; UI pinta fecha, tamaño y disco de respaldo (`_copias_items.html:9`).
- Resultado: `MSG_REST_HECHA` con día y mes + 3 recuentos (`ops_host.py:454-456`).
- Diagnóstico: 14 causas + genérica (`CAUSAS_RESTAURAR`, `:463-478`), sin identidad.
- No hay escaneo de biblioteca ni cifras de «omitido».

**Referencias consultadas (leídas, no ejecutadas; acceso 2026-11-21).**

1. **Sonarr** — ciclo operativo de backup/restore. Versión de referencia: release `v4.0.20.3014`
   (2026-09-16) y código `develop@51a2412af235197ce15d7d4a17c053a8e2c26609`:
   - [`Backups.tsx`](https://github.com/Sonarr/Sonarr/blob/develop/frontend/src/System/Backup/Backups.tsx):
     tabla con tipo (`scheduled`/`manual`/`update`), nombre, tamaño y fecha; botones Backup now /
     Restore backup.
   - [`BackupRow.tsx`](https://github.com/Sonarr/Sonarr/blob/develop/frontend/src/System/Backup/BackupRow.tsx):
     fecha **relativa** (`RelativeDateCell`), nombre del fichero, tamaño; icono por tipo.
   - [`RestoreBackupModalContent.tsx`](https://github.com/Sonarr/Sonarr/blob/develop/frontend/src/System/Backup/RestoreBackupModalContent.tsx):
     confirmación «Would you like to restore backup {name}?» y pasos Restore → Restart → Reload.
   - [`Backup.cs`](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Backup/Backup.cs):
     el modelo de backup solo tiene `Name`, `Type`, `Size`, `Time`; **no tiene versión ni resumen**.
   - [`BackupService.cs`](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Backup/BackupService.cs):
     el nombre del zip lleva la versión (`sonarr_backup_v{BuildInfo.Version}_{fecha}.zip`) y el zip
     incluye un `INFO` con versión y fecha (`CreateVersionInfo`), pero la lista/restauración **no
     lo muestran**; `GetBackups` no lee el contenido.
2. **Kavita** — servidor de biblioteca de cómics. Versión de referencia: release `v0.9.1.4`
   (2026-09-02) y código `develop@7f97cdcab559ed9b0f12351f26527a2c6aeac680`:
   - [`BackupService.cs`](https://github.com/Kareadita/Kavita/blob/develop/Kavita.Services/BackupService.cs):
     escribe `kavita_backup_v{BuildInfo.Version}_{fecha}.zip` en el directorio de backups; la
     versión va en el nombre, no en una pantalla de resultado.
   - Restauración **manual**: parar Kavita, descomprimir el zip en `config` (issue
     [#1251](https://github.com/Kareadita/Kavita/issues/1251), discussion
     [#3016](https://github.com/Kareadita/Kavita/discussions/3016)). No hay UI de restore ni
     resumen de recuperado/omitido.

**Cómo lo resuelve cada una.** Sonarr ofrece un ciclo operativo claro (listar, restaurar,
reiniciar, recargar) pero **no** explica el contenido ni el resultado: el modelo de backup no
guarda versión, y la confirmación solo repite el nombre. Kavita guarda la versión en el nombre del
zip y deja la restauración al operador; tampoco hay resumen. Ninguna de las dos responde a «¿qué
cambios posteriores quedan fuera?» ni a «¿qué comprobaciones sustentan el resultado?».

**Supuestos de su modelo que NO valen en ZascArr.**

- Sonarr usa SQLite y un `config` propio; ZascArr usa PostgreSQL + biblioteca externa + auxiliar
  del host (ADR 0021/0023). La comparación es de patrón, no de código.
- Sonarr puede restaurar desde la UI sin reautenticación fuerte; ZascArr exige contraseña actual
  (BL-OPS3) y no puede leer `BACKUP_DIR` desde el contenedor.
- Fecha relativa de Sonarr no sirve para decidir: el CA1 exige fecha/hora absoluta.

**Resultado por idea.**

| Idea | Resultado | Motivo |
|---|---|---|
| Listar copias con tipo/fecha/tamaño y botón «Restaurar…» | **Adoptar** | ZascArr ya lo tiene; confirma el patrón |
| Confirmación + pasos Restore → Restart → Reload | **Adaptar** | ZascArr no puede prometer «Reload» (la app se reinicia y el POST se pierde); hace falta ruta estable (D-3) |
| Versión incrustada al crear la copia (nombre/`INFO` de Sonarr) | **Adaptar** | En ZascArr no va en el nombre; va al manifiesto/estado, sin hashes en `copias.json` (D-2) |
| Mostrar fecha relativa como única referencia | **Descartar** | Insuficiente para el CA1 y para decidir; se necesita absoluta con año |
| Restauración manual descomprimiendo (Kavita) | **Descartar** | ZascArr tiene flujo firmado más seguro; no se rebaja |
| Resumen recuperado/omitido/fallo, comprobaciones y diagnóstico | **Mejorar (sobre lo propio)** | Ninguna referencia lo cubre; ZascArr ya tiene los datos (fases, checks, recuentos) y solo le falta exponerlos; evidencia: `Backup.cs` sin versión, `GetBackups` sin contenido, Kavita sin UI de restore |
| Escanear la biblioteca para medir «omitido» | **Descartar (por ahora)** | Coste en Pi y confusión con la restauración del catálogo; se declara alcance (D-4) |

**Invariantes de ZascArr.** No mentir (versión «no consta» si falta), no borrar, confirmación
explícita, coste mínimo en Pi (solo ficheros pequeños), sin hotlinking, sin secretos en superficie.

**Casos de prueba antes de implementar.** Los de [§8](#8-pruebas-futuras-ninguna-ejecutada),
empezando por fecha absoluta, `schema: 2` y «versión no consta».

**Barrera legal.** Sonarr es **GPL-3.0** y Kavita es **GPL-3.0**. Solo se toman patrones; no se
reutiliza código ni se añade dependencia. Cualquier reutilización futura exigiría revisar el
fichero y sus avisos (CLAUDE.md §13).

**NOT RUN.** No se ejecutó Sonarr ni Kavita; no se probó su restore en un entorno real. La ficha
se basa en código y documentación, y las versiones citadas son las de la consulta, no una prueba
de comportamiento.

**Decisión final / ADR.** No procede ADR: no cambia arquitectura. Decide el PO con D-1…D-7.

---

## 10. Condición de desbloqueo

UATP-08 pasa de «no lista» a «lista para especificar» solo cuando se cumplan **todas** estas
condiciones, en este orden:

1. **UATP-07 cerrada con evidencia.** [#1145](https://github.com/juanajok/zascarr/issues/1145)
   implementada/ejecutada según su propio criterio: catálogo **y** copia de archivos en destino
   vacío, página guardada, huella y versión que abre; con el procedimiento de copia de archivos
   documentado y reproducible. **No** basta con que el flujo de BL-OPS2 exista.
2. **A6 recreada y enlazada.** Deben existir `A6/resultado.md` y `A6/evidencia/resultado.txt` (o
   la ubicación que el PO fije) y estar enlazadas desde #1141/#1145/#1146. La evidencia debe ser
   reproducible por otra persona, con copia, versión, comprobaciones y resultado; no vale un texto
   redactado a posteriori.
3. **Decisiones D-1…D-7 registradas** en #1146 (o en ADR si el PO considera que D-2/D-3 cambian
   arquitectura). Sin decisión, la spec no puede fijar contrato ni textos.
4. **Enmiendas aprobadas si aplican.** Si D-2(a): enmienda de FR-16/FR-28 para `version` (semver,
   nullable, sin hashes) y actualización de `tests/test_copias_json.py:64`. Si D-3: ruta nueva y
   ajuste de FR-29/FR-32. Sin enmienda, no se toca el contrato.
5. **Spec nueva y DoR.** Escribir `docs/design/uatp08-*.md` a partir de este readiness y del
   borrador de AC, con criterios verificables, contrato aprobado, pruebas y NOT RUN explícitos;
   revisión de PO, UX y Seguridad antes de pasar a «Lista para desarrollar».
6. **Implementación en PR propia**, con tests primero, sobre el contrato aprobado, sin mezclar
   UATP-07 ni UATP-06. Nada de implementar «para ver si funciona» antes de 1–4.
7. **Acreditación final.** Matriz de AC con PASS/FAIL/NOT RUN, evidencia UAT-31 y enlace a A6. Solo
   entonces se podrá decir que UATP-08 está cumplida; **este documento no lo dice**.

**Qué NO desbloquea UATP-08:**

- escribir código de la UI sin decisiones (produce una spec de facto no aprobada);
- enmendar FR-16 «de paso» o meter el SHA en `copias.json` sin decisión del PO;
- recrear A6 con datos sintéticos sin ejecutar el ensayo;
- copiar la evidencia de UATP-07 o firmar su criterio sin ejecutarlo;
- declarar «cumplida» porque el flujo de restauración ya existe (existe el *plumbing*, no la capa
  de comprensión);
- ejecutar solo la suite: las pruebas verdes no acreditan un UAT que no se ha corrido.

---

## 11. Riesgos y preguntas abiertas

| Riesgo | Descripción | Mitigación propuesta |
|---|---|---|
| R-1 | La CA habla de «el procedimiento»; si se decide solo producto o solo runbook, la acreditación puede quedar coja | D-1 explícita; spec con alcance cerrado |
| R-2 | FR-16 es una lista cerrada con prueba exacta de claves; añadir `version` la cambia | D-2(a) con enmienda documental y tests actualizados; nada de hashes |
| R-3 | `app_version` no es identidad del código (ADR 0025); mostrarla como «versión» puede mentir en builds manuales | Semver para el coleccionista + «no consta»; SHA solo en detalle técnico o no mostrar |
| R-4 | A6 puede recrearse de forma artificial | Formato de evidencia reproducible y revisión; enlazar el ensayo, no un relato |
| R-5 | El resumen «recuperado» puede dar falsa confianza si no distingue archivos | D-4 y D-5; texto explícito de alcance |
| R-6 | La ruta de resumen tras reiniciar debe quedar detrás de auth y sin caché | Reutilizar middleware; `no-store`; pruebas de sesión |
| R-7 | Escanear la biblioteca al pintar castiga la Pi (512 MB) | D-4(a): sin escaneo; si se mide, historia aparte con presupuesto |

**Preguntas abiertas (no decididas).**

- Q-1: ¿Dónde vive la evidencia A6 (repo, issue, entorno de UAT)? Sin ubicación, no es verificable.
- Q-2: ¿La «copia de archivos» de UATP-07 es un paso manual documentado o una herramienta nueva?
- Q-3: Si se actualiza ZascArr después de restaurar, ¿el resumen debe conservar «la versión que
  arrancó entonces» o se acepta que muestre la actual? (Recomendación: guardar
  `version_arrancada`).
- Q-4: ¿Se permite mostrar el SHA corto en el detalle técnico? ADR 0025 lo usa como identidad; el
  colector no lo necesita.

---

## 12. Referencias y evidencia leída

**Código y contratos (base `origin/main@d5f26df5`; ficheros idénticos en el árbol de trabajo a
2026-11-21):**

- `src/zascarr/services/ops_host.py` — fechas (`:270-291`), mensajes de restauración (`:446-478`),
  `VistaRestaurar` (`:488`), `resolver_restauracion` (`:519-579`), aviso de `/login` (`:581-592`),
  `leer_copias` (`:401-423`).
- `src/zascarr/services/restauracion.py` — `ofrecer` (`:41-63`), `solicitar` (`:65-...`).
- `src/zascarr/web/copias.py` — rutas (`:106,111,145,171`).
- Plantillas `_copias_items.html:9`, `_copias_estado.html:11-14`, `_restaurar_confirmar.html:5-6,16-18`,
  `_restaurar_resultado.html`.
- `scripts/restaurar_datos.sh` — estado (`:55-80`), verificación de copia (`:261-275,330-332`),
  base nueva (`:482-505`), health (`:409-421`), éxito (`:699-704`).
- `scripts/_comun.sh` — manifiesto (`:303-340`), `copias.json` (`:366-397`).
- `src/zascarr/config.py:275-279` (ficheros de estado), `:408` (`app_version`).
- `src/zascarr/api/health.py:459` (`version` en el payload).
- `docs/design/especificacion-BL-OPS1.md:191-193` (FR-16).
- `docs/design/especificacion-BL-OPS2.md:122` (FR-24), `:129` (FR-28), `:130` (FR-29), `:352`
  (R-7); §0 y FR-35(e) (solo catálogo; biblioteca intacta).
- `docs/adr/0021-auxiliar-del-host-para-operaciones.md`, `docs/adr/0023-restaurar-copia-desde-interfaz.md:3`
  (propuesto, no desplegado), `docs/adr/0025-aviso-de-version-observacional.md`.
- `docs/design/benchmark-referencias.md:74-80` (nivel 1).

**Pruebas leídas:** `tests/test_restauracion_estado.py:65-131`, `tests/test_copias_json.py:1,52-66`,
`tests/test_restauracion_ops2.py:31-...`, `tests/test_restaurar_produccion.py:49-278`,
`tests/test_restaurar_produccion_pg.py:227-...`, `tests/test_copias_ops.py:112`.

**Issues comprobadas con `gh` el 2026-11-21:** #1146 (abierto), #1145 (abierto, sin comentarios),
#1144 (abierto), #1141 (abierto, cita A6). Búsqueda de `A6/resultado.md` y
`A6/evidencia/resultado.txt` en el repo y en el árbol: no aparecen; en los issues solo se citan como
evidencia pendiente.

**Estado de esta entrega:** documento de readiness únicamente. **No** hay rama de código, **no** hay
PR de implementación, **no** se modifica ningún otro fichero y **no** se declara cumplida UATP-08.
