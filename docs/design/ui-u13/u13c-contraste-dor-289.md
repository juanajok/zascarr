# U13c (#289) — Contraste de DoR: revisar una carpeta mixta antes de vincular

> **Estado: CONTRASTE ACTUALIZADO PARA RE-REVISIÓN. No declara la historia Ready.**
> **PR de contraste:** #310 (documento + pruebas fijas; CI funcional en verde).
> **SHA de contraste:** `b59b00c436fc5067f3d752f3ddd76c201335fab4` (`main`, merge de #306; incluye #293 y #299).
> **Fecha:** 2026-10-22.
> **Decisiones de producto:** D1, D2 y D3 cerradas (ver §8).
> **Estimación:** 3 puntos / S (reestimada; 5/M queda como antecedente).
> **Pruebas fijas:** `tests/test_u13c_carpeta_mixta_pg.py`, 3 pruebas PASS en local sobre Postgres real.
> **Presupuesto:** propuesto en §6.4; **no aprobado** y **no medido** en la Pi. La medición sigue siendo DoD.
> **Alcance:** documento de evidencia y decisiones; no implementa #289, no modifica contratos, no mide en la Pi, no despliega y no toca staging ni biblioteca real.

## 0. Veredicto corto

El recorrido que pide #289 **ya existe en gran parte** en `b59b00c`:

- la tarjeta de carpeta ya ofrece «Elegir la serie de esta carpeta»;
- el asistente ya abre el grupo sin consultar fuentes;
- la revisión ya permite marcar **archivo por archivo**, escribir números, paginar de 100 en 100 y confirmar solo una página;
- el marcado masivo de #207 ya existe;
- la confirmación, el resultado y la vuelta a la carpeta ya existen.

Lo que hay que **fijar, probar o documentar** para una carpeta mixta:

1. **No hay una acción «Revisar archivos» separada de «Elegir serie»**: la revisión se abre después de elegir una serie local. D3 mantiene la revisión existente; si se ajusta el copy, entra en los 3/S y no cambia el flujo.
2. **«Marcar todos» no distingue un archivo ajeno**: marca todo lo que el servicio da por `marcable`, aunque tenga un conflicto de título. D2 acepta ese comportamiento, con la condición de que el conflicto siga visible dentro de la revisión. La protección es manual, no automática.
3. **«Elegir otra serie» no revoca el token anterior**: abre una revisión limpia, pero el token firmado de la preparación anterior sigue siendo válido hasta sus 15 minutos. D1 acepta esa semántica, con la condición de que la confirmación muestre siempre la serie destino.
4. **La prueba fija de tres archivos con uno ajeno ya está en el repositorio** (`tests/test_u13c_carpeta_mixta_pg.py`): token con dos, ajeno fuera; «Marcar todos» incluye al ajeno marcable con el conflicto visible; y el token antiguo confirma mostrando su serie de origen. PASS local.
5. **No hay navegador real, lector de pantalla, 360 px, cinco segundos ni medición de rendimiento para #289.** Todo eso sigue `NOT RUN`. La verificación de navegador de U13a/U13b no se hereda como PASS de U13c.

Por tanto: **DoR 1–4 con evidencia sobre el SHA vigente; la casilla 5 sigue pendiente de re-revisión y de aprobación del presupuesto**. La estimación se mantiene en **3/S** y el 5/M queda como antecedente. D1, D2 y D3 están cerradas por producto: no se introduce invalidación activa de tokens ni exclusión automática de ajenos. El trabajo de #289 es verificar, probar y ajustar textos, con dos condiciones: la serie destino siempre visible en la confirmación (D1) y el conflicto visible dentro de la revisión (D2).

## 1. Alcance real: qué hay y qué falta

### 1.1. Lo que ya está en `b59b00c`

| Pieza | Evidencia vigente |
|---|---|
| Acción de tarjeta | `src/zascarr/web/templates/carpetas.html:69-70`: enlace GET a `/ui/pendientes/carpetas/asistente?clave=…`; el texto dice «No se crea ni se asigna nada hasta que confirmes». |
| Apertura sin fuentes ni escritura | `src/zascarr/web/asistente_carpetas.py:129-136`; `DescubrimientoDeGrupo.abrir()` en `src/zascarr/services/descubrimiento_grupo.py:169-174`. |
| Búsqueda local | `asistente_carpetas.py:319-337`; `ReviewService.search_series()` en `src/zascarr/services/review.py:237-249`; enlace a la revisión en `_asistente_locales.html:13`. |
| Búsqueda en fuentes solo a petición | `asistente_carpetas.py:139-179`; no se ejecuta al abrir. |
| Elección de candidata / alta | `asistente_carpetas.py:192-232`; vista previa en `src/zascarr/web/discovery.py:216-298`; alta en `discovery.py:301-349`; enlace posterior a la revisión en `_alta_resultado.html:22-27`. |
| Revisión por archivo | `src/zascarr/web/asistente_vinculacion.py:383-393`; `VistaPreviaDeVinculacion.previsualizar()` en `src/zascarr/services/vinculacion_previa.py:350-470`; plantilla `_vinculacion_revision.html`. |
| Selección, números y página | `asistente_vinculacion.py:312-379`; `vinculacion_previa.py:418-445`; límite de 100 en `vinculacion_previa.py:71`. |
| Marcado masivo de #207 | `asistente_vinculacion.py:337-360`; `_vinculacion_revision.html:52-56`; no marca bloqueados ni otras páginas. |
| Confirmación y resultado | `asistente_vinculacion.py:505-545`; única escritura del asistente; `_vinculacion_resultado.html`. |
| Vuelta y resultado guardado | `asistente_vinculacion.html:5-7`; `_vinculacion_resultado.html:33-34, 83-86`; `asistente_vinculacion.py:565-597`. |

### 1.2. Lo que no hay o no está cerrado

- **No existe una etiqueta/acción «Revisar archivos»** en la tarjeta. Sí existe la frase «Preparar los archivos de esta carpeta para esa serie» en `_asistente_locales.html:13`, y «Revisar los archivos de esta carpeta» en los resultados de alta (`_alta_resultado.html:26`, `asistente_alta_resultado.html:27`). La semántica propuesta en el borrador de DoR no es literal en la entrada.
- **No hay clasificación automática de «archivo ajeno»**. El servicio calcula señales (`con_conflicto_de_carpeta`, número repetido, etc.) y `marcable`, pero no una pertenencia a la serie elegida. La persona decide. La garantía existente es negativa: lo no marcado no entra en el token.
- **«Marcar todos» incluye un archivo con conflicto de título si es `marcable`; D2 lo acepta**. No es un fallo de #207: su contrato es marcar todo lo marcable. La condición de D2 es que el conflicto siga visible dentro de la revisión y no se convierta en invisible al marcar; la exclusión automática queda como hipótesis futura.
- **No hay revocación de tokens; D1 la acepta**. El test `tests/test_vinculacion_previa_pg.py:655-664` documenta que emitir un token nuevo **no invalida** los anteriores; cada uno es una fotografía firmada de 15 minutos. La condición de D1 es que la confirmación muestre siempre la serie destino de la preparación que se confirma.
- **La prueba fija de tres archivos con uno ajeno ya existe**: `tests/test_u13c_carpeta_mixta_pg.py` cubre E1, D2 y E7/D1 con Postgres real. No queda como comprobación temporal.
- **No hay presupuesto aprobado ni medición de #289**. La propuesta propia de §6.4 (1.500/900 ms) no está medida; las cifras de #287/#288 no son evidencia de #289 y no se heredan.
- **No hay evidencia de navegador real, teclado, 360 px, lector de pantalla ni cinco segundos para #289.** La evidencia de navegador de U13a/U13b está registrada para esas historias, pero no cubre esta pantalla ni el lector.

## 2. Método y límites

- Lectura estática del código y de las pruebas en el SHA completo indicado, con líneas exactas revalidadas en `b59b00c`.
- Ejecución local de pruebas contra Postgres 15 real en Docker, base aislada y desechable. **No es CI de #289**: #289 no tiene aún implementación propia.
- **Pruebas fijas incorporadas al repositorio** en `tests/test_u13c_carpeta_mixta_pg.py`: E1 (tres archivos con uno ajeno), D2 (masivo con conflicto visible) y E7/D1 (token antiguo con serie de origen visible). PASS local.
- Medición orientativa local del servicio (ASGI, no navegador ni Pi) para fundamentar los umbrales de §6.4. **No es la medición DoD** ni se registra como PASS de rendimiento.
- No se ha ejecutado navegador real, no se ha usado la Pi, no se ha medido en el entorno de referencia, no se ha usado lector de pantalla y no se ha probado una biblioteca real.
- Los estados `PASS` de este documento se refieren solo a pruebas locales citadas. Lo no ejecutado se marca `NOT RUN`. No se usa `PASS` para rendimiento, accesibilidad ni navegador.

## 3. Mapa `ruta :: función :: plantilla :: SHA :: líneas`

| Paso | Ruta | Función | Plantilla | Líneas | Efecto |
|---|---|---|---|---|---|
| Tarjeta → asistente | `GET /ui/pendientes/carpetas` | `web/pendientes.py::carpetas` | `carpetas.html` | `247-267`; enlace `69-70` | Solo lectura; GET con `clave` URL-encoded. |
| Abrir grupo | `GET /ui/pendientes/carpetas/asistente?clave=` | `asistente_carpetas.py::abrir` → `_pagina` | `asistente_carpeta.html` | `129-136`, `111-127` | No consulta fuentes, no escribe. |
| Contexto del grupo | — | `DescubrimientoDeGrupo.abrir` → `RevisionCarpetas.archivos_del_grupo` | — | `descubrimiento_grupo.py:169-174`; `revision_carpetas.py:394-399` | Una lectura; sin red. |
| Buscar en biblioteca | `GET /ui/pendientes/carpetas/asistente/locales?clave=&q=` | `asistente_carpetas.py::locales` | `_asistente_locales.html` | `319-337`; enlace `13` | Solo base local; sin fuentes; sin preselección. |
| Buscar en fuentes | `POST /ui/pendientes/carpetas/asistente/buscar` | `asistente_carpetas.py::buscar` | `_asistente_resultados.html` | `139-179` | Red solo a petición; no crea ni vincula. |
| Elegir candidata | `POST /ui/pendientes/carpetas/asistente/elegir` | `asistente_carpetas.py::elegir` → `preparar_vista_previa` | `_asistente_eleccion.html` | `192-232`; `discovery.py:216-298` | No escribe; vista previa del alta. |
| Crear serie | `POST /ui/descubrir/crear` | `discovery.py::crear` | `_alta_resultado.html` | `301-349`; enlace `22-27` | Única escritura de serie; no vincula archivos. |
| Abrir revisión | `GET /ui/pendientes/carpetas/asistente/vinculacion?clave=&series_id=&cursor=` | `asistente_vinculacion.py::abrir` → `_revisar` | `asistente_vinculacion.html` + `_vinculacion_revision.html` | `383-393`, `312-379`; plantilla `1-170` | No escribe; estado inicial sin marcar. |
| Cambiar selección/página/números | `POST /ui/pendientes/carpetas/asistente/vinculacion/revisar` | `asistente_vinculacion.py::revisar` | `_vinculacion_revision.html` | `397-423`; plantilla `8-162` | Solo prepara; no escribe. |
| Marcar todos / desmarcar | incluido en el POST anterior | `asistente_vinculacion.py::_revisar` (bloque de acción masiva) | `_vinculacion_revision.html` | `337-360`; plantilla `52-56` | Solo página actual; no bloqueados ni otras páginas. |
| Confirmar | `POST /ui/pendientes/carpetas/asistente/vinculacion/confirmar` | `asistente_vinculacion.py::confirmar` → `ejecutar_vinculacion` | `_vinculacion_resultado.html` | `505-545` | **Única escritura de vinculación**; token de una página. |
| Leer resultado | `GET /ui/pendientes/carpetas/asistente/vinculacion/resultado?ref=` | `asistente_vinculacion.py::resultado_guardado` | `_vinculacion_resultado.html` | `565-597` | Solo lectura; referencia de 24 h; no reintenta. |
| Volver / otra serie | enlaces GET | `asistente_vinculacion.html` / `_vinculacion_resultado.html` | — | `asistente_vinculacion.html:5-7`; resultado `33-34, 83-86` | No escribe; «Otra serie» abre revisión limpia. No revoca token. |
| Volver antes del alta | `GET /ui/pendientes/carpetas/asistente/alta?clave=&candidata=&tradition=` | `asistente_carpetas.py::alta_previa` | `asistente_alta.html` | `241-286`; plantilla `9-16` | No consulta fuentes, no escribe. |
| Resultado del alta | `GET /ui/pendientes/carpetas/asistente/alta/resultado?clave=&series_id=` | `asistente_carpetas.py::alta_resultado` | `asistente_alta_resultado.html` | `297-315`; plantilla `22-27` | No repite el alta; enlaza a revisión. |

> Nota menor: el docstring de `web/pendientes.py:254-256` todavía dice que la vista «no ofrece ninguna acción», pero `carpetas.html:69` ya ofrece el enlace. Es una frase obsoleta, no un comportamiento distinto. #287 no la corrigió en su diff.

## 4. Semántica vigente de selección, token y resultado

### 4.1. Estado inicial

- Todo empieza **sin marcar** y sin token: `tests/test_asistente_vinculacion_pg.py:177-185`.
- Con cero seleccionados, el servicio devuelve `token=None` y el motivo «No has marcado ningún archivo»: `vinculacion_previa.py:441-445`; prueba citada.
- No hay preselección por sugerencia ni por candidata: la elección de serie no marca archivos.

### 4.2. Tres conceptos distintos

| Concepto | Significado | Dónde |
|---|---|---|
| `marcable` | El archivo no tiene un impedimento; se puede marcar. | `vinculacion_previa.py:591` |
| `marcado` | La persona lo marcó, aunque luego resulte bloqueado. | `vinculacion_previa.py:592-596` |
| `incluido_en_token` | `marcado and marcable`; solo esto se firmará y se vinculará. | `vinculacion_previa.py:595` |

Consecuencia: un archivo marcado pero bloqueado se muestra como «Marcado, pero no se puede vincular» y **no** entra en el token (`_vinculacion_revision.html:74-77`). Lo no marcado nunca entra, aunque sea `marcable`.

### 4.3. Bloqueos y conflicto

- Impedimentos: `ya_vinculado`, `en_curso`, `origen_no_encontrado`, `origen_no_verificable`, `requiere_numero`, `numero_repetido_en_el_grupo`, `colision_de_edicion`, `numero_ambiguo`, `numero_ya_existe` (`vinculacion_previa.py:77-83`).
- Un archivo con `con_conflicto_de_carpeta` **sí es marcable**; el conflicto es información para la persona, no un bloqueo. Prueba: `tests/test_vinculacion_previa_pg.py:573-590` (un conflicto minoritario se muestra; marcarlo es decisión de la persona y consta).
- `ya_vinculado` se muestra, no es editable y no entra en el token: prueba `tests/test_vinculacion_previa_pg.py:411-425`.
- Dos archivos **marcados** con el mismo número se bloquean ambos; el masivo evita marcar dos del mismo número y solo marca uno: `tests/test_asistente_vinculacion_masivo_pg.py:114-126`.

### 4.4. Página, borradores y token

- Límite de 100 archivos por página: `vinculacion_previa.py:71`; prueba `tests/test_vinculacion_previa_pg.py:671-679`.
- La selección, los números y el token valen **solo para la página evaluada**: `_vinculacion_revision.html:8-18` y `:140-160`; prueba `tests/test_asistente_vinculacion_pg.py:245-263`.
- Los borradores de otras páginas viajan en el formulario (`borradores`), pero no son una selección global persistida. Recargar o cambiar de serie los pierde.
- El token es una fotografía firmada de los archivos incluidos, con caducidad de 15 minutos: `tokens_revision.py:30`, `:89-121`; `vinculacion_previa.py:441-457`.
- El token de una página no incluye lo marcado en otra: prueba `tests/test_vinculacion_previa_pg.py:681-687`.
- El resultado guardado se conserva 24 h y se lee por referencia; no se reintenta ni se deshace: `vinculacion.py:56-57`; prueba de resultado incierto/caducidad en `tests/test_asistente_confirmar_pg.py`.

### 4.5. «Elegir otra serie»: lo que realmente pasa

- El enlace está en `asistente_vinculacion.html:6`: vuelve a `/asistente?clave=…`, sin `series_id`.
- La nueva revisión empieza limpia: sin marcas y sin token. Prueba: `tests/test_u19_continuidad_pg.py:445-455` (T12: cambiar de serie descarta los números borrador de la anterior).
- **No se revoca el token anterior.** Emitir un token nuevo no invalida los anteriores en el servidor; cada uno caduca a los 15 minutos. Prueba/documentación: `tests/test_vinculacion_previa_pg.py:655-664`; D1 acepta esta semántica y no introduce invalidación activa.
- Por tanto:
  - la **selección visible** no se reutiliza silenciosamente: la nueva página está limpia;
  - el **token anterior** sigue siendo verificable si se conserva la página o se reenvía su formulario;
  - no hay una invalidación explícita de la preparación previa.

Esto es seguro para no mezclar series distintas (el token está atado a `series_id`), pero **no es** la semántica de «invalidar» en sentido estricto. D1 acepta esa semántica; la condición es que la confirmación muestre la serie de origen (§4.8).

### 4.6. Volver, cancelar y resultado

- No hay un botón «Cancelar» explícito; hay enlaces de vuelta (`asistente_vinculacion.html:5-7`, `_vinculacion_resultado.html:33-34, 83-86`, `asistente_carpeta.html:7`, `asistente_alta.html:9-16`).
- Navegar no escribe: `tests/test_asistente_vinculacion_pg.py::TestCriterio10SinEfectos`; `tests/test_u19_recorrido_pg.py::TestT8VolverAntesDelAlta`, `TestT9VolverDespuesDelAlta`, `TestT10LecturaDelComprobante`.
- Tras una vinculación **no se ofrece deshacer**: el resultado informa y permite revisar de nuevo o volver a carpetas; no hay un botón de deshacer de vinculación. El alta sí tiene su propio «Deshacer» en el resultado inmediato (`_alta_resultado.html:32-37`), que es otra operación y no forma parte de la vinculación.
- Un resultado incierto no se declara éxito: se ofrece «Comprobar el resultado»/«Reintentar» según el fallo (`_vinculacion_resultado.html:25-31`); no se duplica la operación.

### 4.7. Payload, «Ignorar» y no descarte

- El formulario de revisión envía `clave` y `series_id` como campos ocultos (`_vinculacion_revision.html:13-14`). `series_id` es el id **local** de la serie elegida; la ruta rechaza un id vacío, no-UUID o una serie inexistente (`asistente_vinculacion.py:321-323`, `361-366`). No se usa un identificador externo como sustituto.
- **No hay «Ignorar» ni descarte en esta historia**: no existe botón, ruta ni campo de descarte en el asistente. Desmarcar un archivo solo lo saca del token; no cambia `issue_id`, no toca `review_dismissed` y el archivo sigue pendiente al recargar. La garantía es «no se incluye», no «se descarta».
- El contrato de solo lectura está cubierto por `TestSoloLectura` y `test_no_crea_issues_ni_aprende_alias_ni_toca_files` (`tests/test_vinculacion_previa_pg.py`), además de la comprobación de cero efectos de la revisión.

### 4.8. Condiciones de copy de D1 y D2

**D1 — serie destino visible al confirmar.** La condición se cumple en el código vigente y debe conservarse:

- la revisión muestra «Serie elegida» con título y año antes de confirmar (`_vinculacion_revision.html:20-27`);
- el bloque «Listo para vincular» repite la serie en el texto de la acción: «quedarán vinculados a «{{ s.titulo }}»» (`_vinculacion_revision.html:157-159`);
- el resultado vuelve a mostrar «Serie» con el título (`_vinculacion_resultado.html:11`);
- al confirmar, `confirmar()` deriva `titulo_serie` del token (`asistente_vinculacion.py:519`), no de la elección que hubiera en otra pestaña o del estado de la página.

No hace falta cambiar el contrato: la prueba fija `test_e7_serie_destino_visible_al_confirmar_un_token_antiguo` reenvía un token antiguo desde una página anterior y comprueba que sigue verificando y que la confirmación y el resultado muestran su serie de origen, no la elección nueva.

**D2 — conflicto visible en la revisión.** La condición también se cumple y debe conservarse:

- cada fila lleva `data-estado` (incluido `con_conflicto_de_carpeta`) en `_vinculacion_revision.html:62`;
- el texto legible del conflicto se muestra en la fila (`_vinculacion_revision.html:95`) y el detalle «Qué dice la carpeta frente a esta serie» en `:107-112`;
- el conflicto no impide marcar, pero no desaparece al pulsar «Marcar todos»: la fila se vuelve a evaluar y se pinta con su estado.

La prueba fija `test_d2_marcar_todos_incluye_al_ajeno_marcable_y_conserva_su_conflicto` comprueba que, después de «Marcar todos», el archivo conflictivo sigue mostrando su conflicto y que el token lo incluye solo porque la persona lo marcó. No se añade exclusión automática.

## 5. Siete ejemplos de carpeta mixta

Los ejemplos usan la misma clave `Comics/Flash (1987)` y una serie local `Flash (1987)`. «Ajeno» significa un archivo de otra serie dentro de la misma carpeta; el sistema no lo clasifica automáticamente, solo lo muestra con sus señales.

| # | Situación | Acción | Resultado vigente | Evidencia / estado |
|---|---|---|---|---|
| E1 | `Flash 01`, `Flash 02`, `Green Lantern 99` (3 archivos; el tercero ajeno y con conflicto de título). | Marcar solo los dos Flash. | Token con 2 archivos; `Green Lantern` queda sin marcar, fuera del token y pendiente. Sin escrituras por contrato de `previsualizar`. | **Prueba fija PASS:** `tests/test_u13c_carpeta_mixta_pg.py::test_e1_tres_archivos_uno_ajeno_solo_dos_entran_en_el_token`; servicio `incluido_en_token = marcado and marcable` (`vinculacion_previa.py:595`). |
| E2 | 2 Flash válidos + `Sin numero.cbz`. | Marcar los tres. | Token con 2; el tercero queda «marcado, pero no se puede vincular» y no entra. | `tests/test_asistente_vinculacion_masivo_pg.py` (caso de bloqueado sin número); PASS local. |
| E3 | `Flash 03`, `Flash 03 (copia)`, `Flash 04`. | «Marcar todos». | Solo se marca `Flash 04`; los dos repetidos no se marcan y se explican; la persona puede elegir uno después. | `tests/test_asistente_vinculacion_masivo_pg.py:114-126`; PASS local. |
| E4 | `Flash 01`, `Flash 02`, un tercero ya vinculado. | Marcar los dos pendientes. | Token con 2; el ya vinculado se muestra, no es editable y no entra. | `tests/test_vinculacion_previa_pg.py:411-425`; PASS local. |
| E5 | 9 Flash coherentes + `Flash 10 (1999)` con conflicto. | Marcar el conflictivo. | Es `marcable`; se incluye si se marca, con el conflicto visible. No se excluye automáticamente. | `tests/test_vinculacion_previa_pg.py:573-590`; PASS local. |
| E6 | 155 archivos: página 1 (100) y página 2 (55). | Marcar en página 1 y pasar a la 2. | La página 2 empieza sin token; lo de la 1 no se presenta como evaluado ni entra en el token de la 2; los borradores se conservan solo dentro del formulario. | `tests/test_asistente_vinculacion_pg.py:245-263`; `tests/test_vinculacion_previa_pg.py:671-687`; PASS local. |
| E7 | Preparar Flash, marcar, y pulsar «Elegir otra serie» (Batman 1940). | Abrir la otra serie. | Revisión nueva limpia, sin marcas/token; no se escribe. El token anterior **no se revoca** y sigue válido hasta 15 min. | **Prueba fija PASS:** `tests/test_u13c_carpeta_mixta_pg.py::test_e7_serie_destino_visible_al_confirmar_un_token_antiguo`; T12 `tests/test_u19_continuidad_pg.py:445-455`; tokens independientes `tests/test_vinculacion_previa_pg.py:655-664`. **D1 aceptada.** |

### 5.1. D2 aceptada: el masivo incluye al ajeno, pero el conflicto debe seguir visible

Con `Green Lantern 99` (número distinto, `marcable=True`), «Marcar todos los que se pueden vincular» marca **los tres**, incluido el ajeno con conflicto. **Prueba fija PASS** (`test_d2_marcar_todos...`).

D2 acepta ese comportamiento: la protección de H6 es la **revisión selectiva**. La persona ve la selección, excluye el ajeno y confirma. No se añade exclusión automática en U13c. La condición es que el conflicto sea visible dentro de la revisión —no solo en la tarjeta— y que «Marcar todos» no lo convierta en invisible. El código actual lo muestra en `_vinculacion_revision.html:95,109-113`; la prueba fija lo conserva.

La exclusión automática de ajenos queda como **hipótesis para una historia futura** si la evidencia de uso la justifica; no se decide en #289. No se cambia #207 en este documento.

## 6. Reconciliación con #206 / #118–#120 / #207 / #287–#288

### 6.1. Estado administrativo verificado

| Issue | Estado | DoR / observación | Uso para #289 |
|---|---|---|---|
| #118 | `OPEN` | DoR sin marcar; código de entrada/búsqueda/elegir presente. | Contrato reutilizable; no reimplementar. |
| #119 | `CLOSED` (2026-10-22) | DoR sin marcar; código de revisión por archivo presente. | Contrato reutilizable; no reimplementar. |
| #120 | `OPEN` | DoR sin marcar; confirmación/resultado presentes. | Contrato reutilizable; no reimplementar. |
| #206 | `CLOSED` (2026-10-22, decisión del PO) | Solo la primera casilla de su DoR está marcada; el documento `docs/design/benchmark-U19-recorrido-vincular.md` y `docs/design/ui-u19/README.md` dicen que se cerraron ficha/matriz. | Contrato reutilizable; la inconsistencia es administrativa, no de código. |
| #207 | `CLOSED` (2026-10-22) | DoR con estimación/navegador/CI sin marcar; código U20 presente. | No reimplementar; su masivo tiene el límite descrito en E1. |
| #287 | `OPEN`; PR #293 **fusionada** (`704844c`) | La entrada por carpetas ya está en `main`; la tarjeta sigue abierta hasta registrar la evidencia de navegador (`docs/design/ui-u13/verificacion-navegador-u13a-u13b-2026-10-22.md`, PR #309) y cerrarla con el patrón de #276. | Dependencia **disponible** en el SHA de contraste. |
| #288 | `OPEN`; PR #299 **fusionada** (`17f0da9`) | Independiente; no bloquea #289. Su cierre sigue el mismo patrón que #287. | Fuera de #289. |
| #289 | `OPEN` | En refinamiento; DoR 1–4 con evidencia, casilla 5 pendiente de re-revisión y presupuesto. | No Ready. |

### 6.2. Lo que no se debe reimplementar

| Historia | Contrato que #289 reutiliza | Evidencia |
|---|---|---|
| #118 | Abrir grupo, buscar local/fuentes, elegir candidata, alta con consentimiento separado. | `asistente_carpetas.py`; pruebas `test_asistente_carpetas_pg.py`, `test_u19_continuidad_pg.py`. |
| #119 | Revisión por archivo, números, bloqueos, página, token. | `vinculacion_previa.py`; `test_vinculacion_previa_pg.py`, `test_asistente_vinculacion_pg.py`. |
| #120 | Confirmar, idempotencia, resultado, fallos, caducidad. | `asistente_vinculacion.py:504-545`; `test_asistente_confirmar_pg.py`. |
| #206 | Búsqueda local, continuidad alta→revisión→resultado, vuelta. | `test_u19_recorrido_pg.py`; `docs/design/ui-u19/README.md`. |
| #207 | Marcar/desmarcar todos, lenguaje sin jerga, solo página. | `test_asistente_vinculacion_masivo_pg.py`. |
| #287 | Lista por carpetas, filtro `solo_utiles`, página 50. | PR #293 **fusionada** (`704844c`); el código está en `b59b00c`. |

### 6.3. Delta candidato de #289

Si se mantiene el alcance estricto del cuerpo («acción de tarjeta → asistente existente → revisión selectiva → confirmación y resultado existentes»), el delta real es:

1. **Etiqueta de entrada (D3):** se mantiene el flujo actual «Elegir la serie de esta carpeta» → revisión. No se añade una acción separada «Revisar archivos» ni una pantalla nueva; si la re-revisión pide un ajuste de copy, entra en los 3/S y no cambia el flujo.
2. **Pruebas fijas E1/E7/D2:** hechas en `tests/test_u13c_carpeta_mixta_pg.py`; PASS local y pendientes de CI en la PR de contraste.
3. **Masivo en carpeta mixta (D2):** decidido; incluye al ajeno marcable y conserva el conflicto visible. No se añade exclusión automática.
4. **«Otra serie» y token (D1):** documentado y fijado con prueba; no se invalida el token anterior y la confirmación muestra la serie de origen.
5. **Evidencia de accesibilidad/navegador:** navegador real, 360 px, teclado, lector de pantalla y cinco segundos siguen `NOT RUN` para #289. La evidencia de U13a/U13b no se hereda.
6. **Presupuesto propio:** propuesto en §6.4; la medición es DoD y sigue `NOT RUN`.

Con D1, D2 y D3 cerradas, el delta se reestima en **3 puntos / S**. No incluye revocación de tokens ni exclusión automática de ajenos; si alguna de esas dos cosas entrara, el delta cambiaría de naturaleza y habría que trocear. El 5/M queda como antecedente en la issue.

### 6.4. Presupuesto de rendimiento propio de #289 (propuesta)

No se heredan los umbrales de U13a/U13b (2.000/1.000 ms). El objeto medido aquí es la **primera revisión de una carpeta de 155 archivos** (página 1 = 100; página 2 = 55) y el **cambio a la página 2**, con la serie local ya elegida.

| ID | Métrica | Umbral propuesto (p95) | Conjunto | Entorno | Caché / repeticiones |
|---|---|---|---|---|---|
| P1 | Primera revisión: `GET /ui/pendientes/carpetas/asistente/vinculacion?clave=…&series_id=…` | **≤ 1.500 ms** | 155 archivos (100 + 55); carpeta sintética `Comics/Flash (1987)` | Pi 4/5 de referencia; Postgres real; LAN; sin CDN; sin fuentes externas | `no-store`; SO caliente; 2 calentamientos + 20 medidas; frío aparte |
| P2 | Cambio de página: `POST /ui/pendientes/carpetas/asistente/vinculacion/revisar` con `ir_a` a la página 2 | **≤ 900 ms** | Igual | Igual | Igual; 20 medidas |

Justificación y límites:

- La medición orientativa local en ASGI (Postgres real, 20 medidas, 2 calentamientos) dio **p95 76,0 ms** en la primera revisión y **p95 123,2 ms** en el cambio de página. **No es la medición DoD**: no es navegador, no es la Pi y no incluye la latencia de LAN.
- Los umbrales dejan margen sobre esa base local para el hardware de referencia y la red, pero son una **propuesta para aprobar**, no un resultado.
- El fixture de referencia de #289 no incluye las 1.322 de U13a ni las 17 B de U13b: es una carpeta de 155 archivos. No se comparan cifras de otras historias.
- La medición DoD debe registrar p50/p95, tamaños de página, versión de Postgres, si el SO estaba caliente y si hubo ejecuciones en frío. **Medir es DoD; no se marca `PASS` hasta hacerlo.**

## 7. DoR: casillas y qué falta

> Las casillas **1–4 tienen evidencia sobre `b59b00c` y pruebas locales**. La casilla **5 no se marca**: el presupuesto es una propuesta y falta la re-revisión favorable. Este documento no declara la historia Ready.

| # | Casilla de la DoR (texto de #289) | Estado | Evidencia disponible | Qué falta para cerrarla |
|---|---|---|---|---|
| 1 | Slice de integración y reparto de responsabilidades delimitados. | **Cumplida con evidencia** | §1, §3 y §6.3; D3 mantiene la entrada actual y no añade pantalla/acción; estimación 3/S. | Nada técnico; la re-revisión debe aceptar el alcance. |
| 2 | #287 disponible y contratos de #206/#118–#120/#207 contrastados en un SHA completo. | **Cumplida con evidencia** | `b59b00c`; #287 fusionada (`704844c`) y #288 fusionada (`17f0da9`); mapa §3 y matriz §6 sobre el SHA completo; 182 pruebas PASS en local. #118/#120 siguen abiertas, pero sus contratos están presentes y se reutilizan sin cambios. | Registrar la reconciliación administrativa de #118/#120 en #196; no bloquea el código. |
| 3 | Mapeo de acciones, selección, cancelación y resultado cerrado con ejemplos de carpeta mixta. | **Cumplida con evidencia** | §3, §4, E1–E7; D1/D2/D3 cerradas; `tests/test_u13c_carpeta_mixta_pg.py` cubre E1, D2 y E7/D1. | Nada técnico; CI de la PR de contraste. |
| 4 | Solapamientos reconciliados; sin cambios encubiertos del servicio. | **Cumplida con evidencia** | §6; D1/D2/D3 no tocan el servicio; el delta no incluye invalidación ni exclusión automática; 3/S. | Confirmar en la re-revisión que no se añade alcance encubierto. |
| 5 | Entorno y presupuesto numérico aprobados; estimación calibrada y re-revisión favorable. | **Pendiente** | Presupuesto propio propuesto en §6.4 (1.500/900 ms p95; 155 archivos); medición orientativa local, no DoD; 3/S aprobada como reestimación. | Aprobar entorno y umbrales, medir con el protocolo y dar la re-revisión favorable. No marcar hasta entonces. |

### 7.1. Pendientes para Ready (no de implementación)

1. **#287 ya está fusionada** (`704844c`) y #288 también (`17f0da9`). La evidencia de navegador de ambas está registrada en `docs/design/ui-u13/verificacion-navegador-u13a-u13b-2026-10-22.md` (PR #309). #289 ya no está detrás de #287.
2. **Reconciliación administrativa**: #206/#119/#207 cerradas por el PO con casillas abiertas; #118/#120 abiertas con código presente. No bloquea #289; se tratará en la próxima pasada de cierre de #196.
3. **D1 fijada**: no se invalida el token; `test_e7_serie_destino_visible_al_confirmar_un_token_antiguo` comprueba que la confirmación y el resultado muestran la serie de origen.
4. **D2 fijada**: el masivo incluye al ajeno marcable; `test_d2_marcar_todos...` comprueba que el conflicto sigue visible y no se añade exclusión automática.
5. **Evidencia de aceptación**: pruebas fijas PASS y CI funcional de #310 en verde; navegador real, 360 px, teclado, lector y cinco segundos siguen `NOT RUN` para #289. No se hereda la evidencia de U13a/U13b.
6. **Presupuesto**: propuesta 1.500/900 ms p95; **no medida**. La medición es DoD. El 5/M queda como antecedente.

## 8. Decisiones de producto (cerradas)

### D1 — Token de preparación: comportamiento vigente aceptado

**Decisión:** «Elegir otra serie» abre una revisión limpia sin revocar el token anterior, que caduca a los 15 minutos. Se acepta como comportamiento vigente.

**Condición de copy:** la vista previa de confirmación debe mostrar siempre la serie destino de la preparación que se está confirmando, de forma que confirmar un token antiguo nunca pueda confundirse con la elección nueva.

**Verificación:** la revisión muestra «Serie elegida» (`_vinculacion_revision.html:20-27`) y el bloque de confirmación repite «quedarán vinculados a «{{ s.titulo }}»» (`:157-159`); el resultado muestra «Serie» (`_vinculacion_resultado.html:11`) y `confirmar()` toma `titulo_serie` del token (`asistente_vinculacion.py:519`). No hace falta cambiar el contrato: `test_e7_serie_destino_visible_al_confirmar_un_token_antiguo` lo fija con un token antiguo.

**No entra:** invalidación activa de tokens. Es un cambio de contrato del asistente no justificado por un incidente; la ventana de riesgo queda cubierta por la confirmación explícita y por la visibilidad de la serie.

### D2 — «Marcar todos»: exclusión manual y conflicto visible

**Decisión:** el masivo marca todo lo marcable, incluido el archivo con conflicto de título. La protección de H6 es la revisión selectiva: la persona ve la selección, excluye el ajeno y confirma.

**Condición:** el archivo con conflicto debe ser visible como tal **dentro de la revisión**, no solo en la tarjeta, de modo que «Marcar todos» no convierta el conflicto en invisible.

**Verificación:** la fila lleva `data-estado` (`_vinculacion_revision.html:62`), el texto del conflicto se pinta en `:95` y el detalle «Qué dice la carpeta frente a esta serie» en `:109-113`. La prueba fija `test_d2_marcar_todos_incluye_al_ajeno_marcable_y_conserva_su_conflicto` comprueba que sigue visible después de «Marcar todos».

**No entra:** exclusión automática de ajenos. Queda como hipótesis para una historia futura si la evidencia de uso la justifica; no se decide en U13c.

### D3 — «Revisar archivos» y alcance de copy

No se añade una pantalla nueva ni una acción directa antes de elegir serie. La revisión existente tras elegir una serie local es la revisión selectiva; si se ajusta el copy de entrada, entra dentro de los 3/S y no cambia el flujo. La condición de D1 (serie visible) y la de D2 (conflicto visible) son las únicas correcciones de lectura exigidas.

### D4 — Estimación

**3 puntos / S**, con el desglose de verificación, pruebas, copy y evidencia de aceptación. El 5/M queda como antecedente en la issue. El contraste ya está actualizado a `b59b00c` y las pruebas fijas están incorporadas; no se declara Ready hasta la re-revisión favorable y la aprobación del presupuesto (§6.4).

## 9. Pruebas y evidencia local

### 9.1. Pruebas existentes y fijas ejecutadas

Comando (entorno local, Postgres 15 real en Docker, base de pruebas aislada; no es CI):

```bash
TEST_DATABASE_URL=postgresql://…/zascarr_289_test \
PYTHONPATH=src /tmp/opencode/zascarr-venv/bin/python -m pytest -q \
  tests/test_u13c_carpeta_mixta_pg.py \
  tests/test_vinculacion_previa_pg.py \
  tests/test_asistente_vinculacion_pg.py \
  tests/test_asistente_vinculacion_masivo_pg.py \
  tests/test_asistente_confirmar_pg.py
```

Resultado: **182 passed** en 59,71 s. Incluye las **3 pruebas fijas nuevas** y las pruebas existentes de revisión, selección, token, páginas, masivo, confirmación y resultado.

```bash
/tmp/opencode/zascarr-venv/bin/ruff check tests/test_u13c_carpeta_mixta_pg.py
```

Resultado: **All checks passed**.

No es CI de #289 y no sustituye la CI sobre el SHA de la PR de contraste.

### 9.2. Pruebas fijas incorporadas (E1/E7/D2)

Archivo: `tests/test_u13c_carpeta_mixta_pg.py`. Usa la clave `Comics/Flash (1987)`, una serie local `Flash (1987)` y una segunda serie `Batman (1940)`.

1. **E1 — `test_e1_tres_archivos_uno_ajeno_solo_dos_entran_en_el_token`:**
   - tres archivos: `Flash 01`, `Flash 02` y `Green Lantern 99`;
   - el ajeno tiene `con_conflicto_de_carpeta` y es `marcable`;
   - se marcan solo los dos Flash;
   - el token contiene **exactamente dos** ids;
   - el ajeno queda `marcado=False` e `incluido_en_token=False`;
   - cero escrituras en base y disco.

2. **D2 — `test_d2_marcar_todos_incluye_al_ajeno_marcable_y_conserva_su_conflicto`:**
   - «Marcar todos» marca los tres, incluido el ajeno;
   - el token contiene los tres ids;
   - el ajeno conserva `con_conflicto_de_carpeta`;
   - la fila sigue mostrando «Se puede vincular, pero hay señales que lo contradicen» y el detalle «Qué dice la carpeta frente a esta serie»;
   - no se introduce exclusión automática.

3. **E7/D1 — `test_e7_serie_destino_visible_al_confirmar_un_token_antiguo`:**
   - se prepara Flash y se marca un archivo;
   - se abre Batman: revisión limpia, sin token, sin escrituras;
   - el token de Flash **sigue verificando**;
   - la revisión muestra «Serie elegida Flash (1987)» y «quedarán vinculados a «Flash»»;
   - al confirmar el token antiguo, el resultado muestra «Flash (1987)» y no Batman.

Estas pruebas fijan D1/D2 y E1/E7 tal como quedaron aprobadas; no presentan la no-invalidación como fallo ni la inclusión del conflictivo como éxito silencioso.

### 9.3. Lo que sigue `NOT RUN`

| Comprobación | Estado |
|---|---|
| Navegador real de #289 (Chrome/Firefox, escritorio/móvil) | `NOT RUN` |
| 360 px y teclado en la pantalla de revisión mixta | `NOT RUN` |
| Lector de pantalla (Orca/NVDA/VoiceOver/TalkBack) | `NOT RUN` |
| Prueba de cinco segundos con una persona | `NOT RUN` |
| Rendimiento de #289 (p95 de primera revisión y cambio de página) | `NOT RUN`; solo hay medición orientativa local en ASGI (§6.4) |
| Pi, staging, biblioteca real, despliegue | `NOT RUN` |

La verificación de navegador de U13a/U13b está registrada en `docs/design/ui-u13/verificacion-navegador-u13a-u13b-2026-10-22.md`, pero **no** acredita #289, la carpeta mixta con un tercero ajeno, el lector de pantalla ni los cinco segundos. No se hereda como PASS de #289.

## 10. Anexo: pruebas fijas E1/E7/D2 ya incorporadas

Las pruebas viven en `tests/test_u13c_carpeta_mixta_pg.py`, usan la clave `Comics/Flash (1987)` y una serie local `Flash (1987)`, y comprueban:

- tres archivos: dos Flash y `Green Lantern 99`;
- marcar solo los dos Flash;
- token con exactamente dos archivos;
- el tercero con `marcado=False`, `incluido_en_token=False`;
- cero escrituras en base y disco;
- «Marcar todos» incluye al ajeno conflictivo, pero su conflicto sigue visible en la fila y en el detalle;
- el token antiguo sigue verificando hasta su caducidad (D1), y la confirmación y el resultado muestran la serie de origen, no la serie nueva;
- ninguna exclusión automática ni descarte.

Las pruebas fijan D1 y D2 tal como quedaron aprobadas; no presentan la no-invalidación como un fallo ni la inclusión del conflictivo como un éxito silencioso. Quedan pendientes de la CI de la PR de contraste y de la re-revisión.

## 11. Referencias

- Código: `src/zascarr/web/asistente_carpetas.py`, `asistente_vinculacion.py`, `discovery.py`, `pendientes.py`.
- Plantillas: `carpetas.html`, `asistente_carpeta.html`, `_asistente_locales.html`, `_vinculacion_revision.html`, `_vinculacion_resultado.html`, `_alta_resultado.html`, `asistente_alta_resultado.html`.
- Servicios: `descubrimiento_grupo.py`, `revision_carpetas.py`, `vinculacion_previa.py`, `vinculacion.py`, `tokens_revision.py`.
- Pruebas: `test_u13c_carpeta_mixta_pg.py` (nueva), `test_vinculacion_previa_pg.py`, `test_asistente_vinculacion_pg.py`, `test_asistente_vinculacion_masivo_pg.py`, `test_asistente_confirmar_pg.py`, `test_u19_continuidad_pg.py`, `test_u19_recorrido_pg.py`, `test_asistente_carpetas_pg.py`.
- Documentos: `docs/design/ui-u13/verificacion-navegador-u13a-u13b-2026-10-22.md`, `docs/design/benchmark-U19-recorrido-vincular.md`, `docs/design/ui-u19/README.md`, `docs/design/rebanada-2-elegir-serie-y-vincular.md`, `docs/design/ficha-propuestas-desde-carpetas.md`.
- PRs: #293 (#287) fusionada en `704844c`; #299 (#288) fusionada en `17f0da9`; #309 registra la evidencia de navegador de ambas; **#310** es la PR de contraste de #289 sobre `b59b00c`, con CI funcional en verde y `ruff` informativo preexistente en rojo.
