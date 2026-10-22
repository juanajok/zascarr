# U13c (#289) — Contraste de DoR: revisar una carpeta mixta antes de vincular

> **Estado: BORRADOR para re-revisión. No declara la historia Ready.**
> **SHA de contraste:** `245402e78a6357cfc79e726a4484662ba9ef8151` (`main`, merge de #285).
> **Fecha:** 2026-10-22.
> **Alcance:** documento de evidencia y decisiones; no implementa #289, no modifica contratos, no toca #289 en GitHub, no mide en la Pi, no despliega y no toca staging ni biblioteca real.

## 0. Veredicto corto

El recorrido que pide #289 **ya existe en gran parte** en `245402e`:

- la tarjeta de carpeta ya ofrece «Elegir la serie de esta carpeta»;
- el asistente ya abre el grupo sin consultar fuentes;
- la revisión ya permite marcar **archivo por archivo**, escribir números, paginar de 100 en 100 y confirmar solo una página;
- el marcado masivo de #207 ya existe;
- la confirmación, el resultado y la vuelta a la carpeta ya existen.

Lo que **no** está resuelto es la semántica fina que #289 necesita para una carpeta mixta:

1. **No hay una acción «Revisar archivos» separada de «Elegir serie»**: la revisión se abre después de elegir una serie local. La etiqueta existente es «Preparar los archivos de esta carpeta para esa serie», no «Revisar archivos».
2. **«Marcar todos» no distingue un archivo ajeno**: marca todo lo que el servicio da por `marcable`, aunque tenga un conflicto de título con la serie elegida. La protección de #289 es manual (marcar solo los dos correctos), no automática.
3. **«Elegir otra serie» no revoca el token anterior**: abre una revisión limpia, pero el token firmado de la preparación anterior sigue siendo válido hasta sus 15 minutos. La invalidación no está implementada y el propio test la declara pendiente de decisión.
4. **No hay prueba de aceptación específica de tres archivos con uno ajeno** en el repositorio. Se ha comprobado con dos pruebas temporales, pero no forman parte de la suite.
5. **No hay navegador real, lector de pantalla, 360 px ni cinco segundos para #289.** Todo eso sigue `NOT RUN`.

Por tanto: **DoR no cerrada**, y la estimación **5/M no está sostenida por el delta actual**. Si #289 se limita a verificar, probar y ajustar textos sobre lo existente, es una historia menor; si incluye invalidación de token o exclusión automática de archivos ajenos, cambia contratos y no cabe en 5/M sin trocear.

## 1. Alcance real: qué hay y qué falta

### 1.1. Lo que ya está en `245402e`

| Pieza | Evidencia vigente |
|---|---|
| Acción de tarjeta | `src/zascarr/web/templates/carpetas.html:46-49`: enlace GET a `/ui/pendientes/carpetas/asistente?clave=…`; el texto dice «No se crea ni se asigna nada hasta que confirmes». |
| Apertura sin fuentes ni escritura | `src/zascarr/web/asistente_carpetas.py:128-135`; `DescubrimientoDeGrupo.abrir()` en `src/zascarr/services/descubrimiento_grupo.py:169-174`. |
| Búsqueda local | `asistente_carpetas.py:318-334`; `ReviewService.search_series()` en `src/zascarr/services/review.py:237-249`; enlace a la revisión en `_asistente_locales.html:13`. |
| Búsqueda en fuentes solo a petición | `asistente_carpetas.py:138-166`; no se ejecuta al abrir. |
| Elección de candidata / alta | `asistente_carpetas.py:191-231`; vista previa en `src/zascarr/web/discovery.py:269-292`; alta en `discovery.py:300-349`; enlace posterior a la revisión en `_alta_resultado.html:22-27`. |
| Revisión por archivo | `src/zascarr/web/asistente_vinculacion.py:382-393`; `VistaPreviaDeVinculacion.previsualizar()` en `src/zascarr/services/vinculacion_previa.py:350-470`; plantilla `_vinculacion_revision.html`. |
| Selección, números y página | `asistente_vinculacion.py:312-379`; `vinculacion_previa.py:418-445`; límite de 100 en `vinculacion_previa.py:71`. |
| Marcado masivo de #207 | `asistente_vinculacion.py:337-360`; `_vinculacion_revision.html:52-56`; no marca bloqueados ni otras páginas. |
| Confirmación y resultado | `asistente_vinculacion.py:504-545`; única escritura del asistente; `_vinculacion_resultado.html`. |
| Vuelta y resultado guardado | `asistente_vinculacion.html:5-7`; `_vinculacion_resultado.html:33-34, 83-86`; `asistente_vinculacion.py:564-597`. |

### 1.2. Lo que no hay o no está cerrado

- **No existe una etiqueta/acción «Revisar archivos»** en la tarjeta. Sí existe la frase «Preparar los archivos de esta carpeta para esa serie» en `_asistente_locales.html:13`, y «Revisar los archivos de esta carpeta» en los resultados de alta (`_alta_resultado.html:26`, `asistente_alta_resultado.html:27`). La semántica propuesta en el borrador de DoR no es literal en la entrada.
- **No hay clasificación automática de «archivo ajeno»**. El servicio calcula señales (`con_conflicto_de_carpeta`, número repetido, etc.) y `marcable`, pero no una pertenencia a la serie elegida. La persona decide. La garantía existente es negativa: lo no marcado no entra en el token.
- **«Marcar todos» incluye un archivo con conflicto de título si es `marcable`**. No es un fallo de #207: su contrato es marcar todo lo marcable. Pero contradice una lectura fuerte del objetivo de #289.
- **No hay revocación de tokens**. El test `tests/test_vinculacion_previa_pg.py:655-664` documenta que emitir un token nuevo **no invalida** los anteriores; cada uno es una fotografía firmada de 15 minutos. La invalidación exigiría persistencia y está pendiente de decisión.
- **No hay prueba de tres archivos con uno ajeno** en la suite. Las pruebas existentes cubren subconjuntos, bloqueados, repetidos, conflictos y páginas, pero no el caso concreto de la CA3.
- **No hay presupuesto aprobado ni medición de #289**. La propuesta 2.000/1.000 ms no está medida y las cifras de #287/#288 no son evidencia de #289.
- **No hay evidencia de navegador real, teclado, 360 px, lector de pantalla ni cinco segundos para #289.** U19 tiene evidencia de Chrome headless para su recorrido, pero no cubre esta historia ni el lector.

## 2. Método y límites

- Lectura estática del código y de las pruebas en el SHA completo indicado, con líneas exactas.
- Ejecución local de pruebas existentes contra Postgres 15 en Docker, base de pruebas aislada y desechable. **No es CI de #289**: #289 no tiene aún implementación ni SHA de PR.
- Dos comprobaciones temporales, no incorporadas al repositorio, para el caso de tres archivos (una manual y otra con «Marcar todos»). Se describen en §9.
- No se ha ejecutado navegador real, no se ha usado la Pi, no se ha medido rendimiento, no se ha usado lector de pantalla y no se ha probado una biblioteca real.
- Los estados `PASS` de este documento se refieren solo a pruebas locales citadas. Lo no ejecutado se marca `NOT RUN`. No se usa `PASS` para rendimiento, accesibilidad ni navegador.

## 3. Mapa `ruta :: función :: plantilla :: SHA :: líneas`

| Paso | Ruta | Función | Plantilla | Líneas | Efecto |
|---|---|---|---|---|---|
| Tarjeta → asistente | `GET /ui/pendientes/carpetas` | `web/pendientes.py::carpetas` | `carpetas.html` | `216-229`; enlace `46-49` | Solo lectura; GET con `clave` URL-encoded. |
| Abrir grupo | `GET /ui/pendientes/carpetas/asistente?clave=` | `asistente_carpetas.py::abrir` → `_pagina` | `asistente_carpeta.html` | `128-135`, `111-125` | No consulta fuentes, no escribe. |
| Contexto del grupo | — | `DescubrimientoDeGrupo.abrir` → `RevisionCarpetas.archivos_del_grupo` | — | `descubrimiento_grupo.py:169-174`; `revision_carpetas.py:245-253` | Una lectura; sin red. |
| Buscar en biblioteca | `GET /ui/pendientes/carpetas/asistente/locales?clave=&q=` | `asistente_carpetas.py::locales` | `_asistente_locales.html` | `318-334`; enlace `13` | Solo base local; sin fuentes; sin preselección. |
| Buscar en fuentes | `POST /ui/pendientes/carpetas/asistente/buscar` | `asistente_carpetas.py::buscar` | `_asistente_resultados.html` | `138-166` | Red solo a petición; no crea ni vincula. |
| Elegir candidata | `POST /ui/pendientes/carpetas/asistente/elegir` | `asistente_carpetas.py::elegir` → `preparar_vista_previa` | `_asistente_eleccion.html` | `191-231`; `discovery.py:269-292` | No escribe; vista previa del alta. |
| Crear serie | `POST /ui/descubrir/crear` | `discovery.py::crear` | `_alta_resultado.html` | `300-349`; enlace `22-27` | Única escritura de serie; no vincula archivos. |
| Abrir revisión | `GET /ui/pendientes/carpetas/asistente/vinculacion?clave=&series_id=&cursor=` | `asistente_vinculacion.py::abrir` → `_revisar` | `asistente_vinculacion.html` + `_vinculacion_revision.html` | `382-393`, `312-379`; plantilla `1-170` | No escribe; estado inicial sin marcar. |
| Cambiar selección/página/números | `POST /ui/pendientes/carpetas/asistente/vinculacion/revisar` | `asistente_vinculacion.py::revisar` | `_vinculacion_revision.html` | `396-424`; plantilla `8-162` | Solo prepara; no escribe. |
| Marcar todos / desmarcar | incluido en el POST anterior | `asistente_vinculacion.py::_revisar` (bloque de acción masiva) | `_vinculacion_revision.html` | `337-360`; plantilla `52-56` | Solo página actual; no bloqueados ni otras páginas. |
| Confirmar | `POST /ui/pendientes/carpetas/asistente/vinculacion/confirmar` | `asistente_vinculacion.py::confirmar` → `ejecutar_vinculacion` | `_vinculacion_resultado.html` | `504-545` | **Única escritura de vinculación**; token de una página. |
| Leer resultado | `GET /ui/pendientes/carpetas/asistente/vinculacion/resultado?ref=` | `asistente_vinculacion.py::resultado_guardado` | `_vinculacion_resultado.html` | `564-597` | Solo lectura; referencia de 24 h; no reintenta. |
| Volver / otra serie | enlaces GET | `asistente_vinculacion.html` / `_vinculacion_resultado.html` | — | `asistente_vinculacion.html:5-7`; resultado `33-34, 83-86` | No escribe; «Otra serie» abre revisión limpia. No revoca token. |
| Volver antes del alta | `GET /ui/pendientes/carpetas/asistente/alta?clave=&candidata=&tradition=` | `asistente_carpetas.py::alta_previa` | `asistente_alta.html` | `240-286`; plantilla `9-16` | No consulta fuentes, no escribe. |
| Resultado del alta | `GET /ui/pendientes/carpetas/asistente/alta/resultado?clave=&series_id=` | `asistente_carpetas.py::alta_resultado` | `asistente_alta_resultado.html` | `296-315`; plantilla `22-27` | No repite el alta; enlaza a revisión. |

> Nota menor: el docstring de `web/pendientes.py:223-224` todavía dice que la vista «no ofrece ninguna acción», pero `carpetas.html:47` ya ofrece el enlace. Es una frase obsoleta, no un comportamiento distinto. #287 no la corrige en su diff actual.

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
- **No se revoca el token anterior.** Emitir un token nuevo no invalida los anteriores en el servidor; cada uno caduca a los 15 minutos. Prueba/documentación: `tests/test_vinculacion_previa_pg.py:655-664` («La invalidación del anterior exigiría persistencia y está pendiente de decisión para 2d»).
- Por tanto:
  - la **selección visible** no se reutiliza silenciosamente: la nueva página está limpia;
  - el **token anterior** sigue siendo verificable si se conserva la página o se reenvía su formulario;
  - no hay una invalidación explícita de la preparación previa.

Esto es seguro para no mezclar series distintas (el token está atado a `series_id`), pero **no es** la semántica de «invalidar» en sentido estricto. Es la decisión D1 de §8.

### 4.6. Volver, cancelar y resultado

- No hay un botón «Cancelar» explícito; hay enlaces de vuelta (`asistente_vinculacion.html:5-7`, `_vinculacion_resultado.html:33-34, 83-86`, `asistente_carpeta.html:7`, `asistente_alta.html:9-16`).
- Navegar no escribe: `tests/test_asistente_vinculacion_pg.py::TestCriterio10SinEfectos`; `tests/test_u19_recorrido_pg.py::TestT8VolverAntesDelAlta`, `TestT9VolverDespuesDelAlta`, `TestT10LecturaDelComprobante`.
- Tras una vinculación **no se ofrece deshacer**: el resultado informa y permite revisar de nuevo o volver a carpetas; no hay un botón de deshacer de vinculación. El alta sí tiene su propio «Deshacer» en el resultado inmediato (`_alta_resultado.html:32-37`), que es otra operación y no forma parte de la vinculación.
- Un resultado incierto no se declara éxito: se ofrece «Comprobar el resultado»/«Reintentar» según el fallo (`_vinculacion_resultado.html:25-31`); no se duplica la operación.

### 4.7. Payload, «Ignorar» y no descarte

- El formulario de revisión envía `clave` y `series_id` como campos ocultos (`_vinculacion_revision.html:13-14`). `series_id` es el id **local** de la serie elegida; la ruta rechaza un id vacío, no-UUID o una serie inexistente (`asistente_vinculacion.py:321-323`, `361-366`). No se usa un identificador externo como sustituto.
- **No hay «Ignorar» ni descarte en esta historia**: no existe botón, ruta ni campo de descarte en el asistente. Desmarcar un archivo solo lo saca del token; no cambia `issue_id`, no toca `review_dismissed` y el archivo sigue pendiente al recargar. La garantía es «no se incluye», no «se descarta».
- El contrato de solo lectura está cubierto por `TestSoloLectura` y `test_no_crea_issues_ni_aprende_alias_ni_toca_files` (`tests/test_vinculacion_previa_pg.py`), además de la comprobación de cero efectos de la revisión.

## 5. Siete ejemplos de carpeta mixta

Los ejemplos usan la misma clave `Comics/Flash (1987)` y una serie local `Flash (1987)`. «Ajeno» significa un archivo de otra serie dentro de la misma carpeta; el sistema no lo clasifica automáticamente, solo lo muestra con sus señales.

| # | Situación | Acción | Resultado vigente | Evidencia / estado |
|---|---|---|---|---|
| E1 | `Flash 01`, `Flash 02`, `Green Lantern 99` (3 archivos; el tercero ajeno y con conflicto de título). | Marcar solo los dos Flash. | Token con 2 archivos; `Green Lantern` queda sin marcar, fuera del token y pendiente. Sin escrituras por contrato de `previsualizar`. | Comprobación temporal PASS; servicio `incluido_en_token = marcado and marcable` (`vinculacion_previa.py:595`). **Falta prueba fija en el repo.** |
| E2 | 2 Flash válidos + `Sin numero.cbz`. | Marcar los tres. | Token con 2; el tercero queda «marcado, pero no se puede vincular» y no entra. | `tests/test_asistente_vinculacion_masivo_pg.py` (caso de bloqueado sin número); PASS local. |
| E3 | `Flash 03`, `Flash 03 (copia)`, `Flash 04`. | «Marcar todos». | Solo se marca `Flash 04`; los dos repetidos no se marcan y se explican; la persona puede elegir uno después. | `tests/test_asistente_vinculacion_masivo_pg.py:114-126`; PASS local. |
| E4 | `Flash 01`, `Flash 02`, un tercero ya vinculado. | Marcar los dos pendientes. | Token con 2; el ya vinculado se muestra, no es editable y no entra. | `tests/test_vinculacion_previa_pg.py:411-425`; PASS local. |
| E5 | 9 Flash coherentes + `Flash 10 (1999)` con conflicto. | Marcar el conflictivo. | Es `marcable`; se incluye si se marca, con el conflicto visible. No se excluye automáticamente. | `tests/test_vinculacion_previa_pg.py:573-590`; PASS local. |
| E6 | 155 archivos: página 1 (100) y página 2 (55). | Marcar en página 1 y pasar a la 2. | La página 2 empieza sin token; lo de la 1 no se presenta como evaluado ni entra en el token de la 2; los borradores se conservan solo dentro del formulario. | `tests/test_asistente_vinculacion_pg.py:245-263`; `tests/test_vinculacion_previa_pg.py:671-687`; PASS local. |
| E7 | Preparar Flash, marcar, y pulsar «Elegir otra serie» (Flash 1959). | Abrir la otra serie. | Revisión nueva limpia, sin marcas/token; no se escribe. El token anterior **no se revoca** y sigue válido hasta 15 min. | T12 `tests/test_u19_continuidad_pg.py:445-455`; tokens independientes `tests/test_vinculacion_previa_pg.py:655-664`; PASS local. **Decisión D1.** |

### 5.1. El riesgo del marcado masivo en E1

Con `Green Lantern 99` (número distinto, `marcable=True`), «Marcar todos los que se pueden vincular» marca **los tres**, incluido el ajeno con conflicto. Comprobación temporal PASS. No es un fallo de #207: su contrato es marcar todo lo marcable de la página. Pero deja claro que:

- la protección de #289 es **manual**;
- el masivo no implementa «no asignar archivos de una carpeta mixta» si la persona lo pulsa sin revisar;
- si #289 debe impedir ese caso, hay que decidir entre excluir conflictos del masivo, pedir una confirmación adicional o mantener el masivo como acción explícita y aceptar el riesgo.

Esta es la decisión D2 de §8. No se cambia #207 en este documento.

## 6. Reconciliación con #206 / #118–#120 / #207 / #287–#288

### 6.1. Estado administrativo verificado

| Issue | Estado | DoR / observación | Uso para #289 |
|---|---|---|---|
| #118 | `OPEN` | DoR sin marcar; código de entrada/búsqueda/elegir presente. | Contrato reutilizable; no reimplementar. |
| #119 | `CLOSED` (2026-10-22) | DoR sin marcar; código de revisión por archivo presente. | Contrato reutilizable; no reimplementar. |
| #120 | `OPEN` | DoR sin marcar; confirmación/resultado presentes. | Contrato reutilizable; no reimplementar. |
| #206 | `CLOSED` (2026-10-22, decisión del PO) | Solo la primera casilla de su DoR está marcada; el documento `docs/design/benchmark-U19-recorrido-vincular.md` y `docs/design/ui-u19/README.md` dicen que se cerraron ficha/matriz. | Contrato reutilizable; la inconsistencia es administrativa, no de código. |
| #207 | `CLOSED` (2026-10-22) | DoR con estimación/navegador/CI sin marcar; código U20 presente. | No reimplementar; su masivo tiene el límite descrito en E1. |
| #287 | `OPEN`, PR #293 | `8cdbb66`; CI obligatoria correcta; no fusionada. | Dependencia de coherencia de la vista, no de la existencia de la acción: el enlace ya está en `245402e`. |
| #288 | `OPEN`, PR #299 | `d54a6fa`; independiente; no bloquea. | Fuera de #289. |
| #289 | `OPEN` | En refinamiento; este documento no cambia su estado. | No Ready. |

### 6.2. Lo que no se debe reimplementar

| Historia | Contrato que #289 reutiliza | Evidencia |
|---|---|---|
| #118 | Abrir grupo, buscar local/fuentes, elegir candidata, alta con consentimiento separado. | `asistente_carpetas.py`; pruebas `test_asistente_carpetas_pg.py`, `test_u19_continuidad_pg.py`. |
| #119 | Revisión por archivo, números, bloqueos, página, token. | `vinculacion_previa.py`; `test_vinculacion_previa_pg.py`, `test_asistente_vinculacion_pg.py`. |
| #120 | Confirmar, idempotencia, resultado, fallos, caducidad. | `asistente_vinculacion.py:504-545`; `test_asistente_confirmar_pg.py`. |
| #206 | Búsqueda local, continuidad alta→revisión→resultado, vuelta. | `test_u19_recorrido_pg.py`; `docs/design/ui-u19/README.md`. |
| #207 | Marcar/desmarcar todos, lenguaje sin jerga, solo página. | `test_asistente_vinculacion_masivo_pg.py`. |
| #287 | Lista por carpetas, filtro `solo_utiles`, página 50. | PR #293; no fusionada. |

### 6.3. Delta candidato de #289

Si se mantiene el alcance estricto del cuerpo («acción de tarjeta → asistente existente → revisión selectiva → confirmación y resultado existentes»), el delta real es:

1. decidir y documentar la etiqueta de entrada («Elegir serie» vs «Revisar archivos»);
2. añadir la prueba fija E1/E7 y la prueba de no escritura asociada;
3. decidir qué hacer con el masivo en una carpeta mixta;
4. documentar que «Otra serie» limpia la revisión pero no revoca el token;
5. revisar textos y evidencia de accesibilidad/navegador.

Nada de eso exige, por sí solo, 5 puntos. Si se añade revocación de token o exclusión automática de ajenos, el delta cambia de naturaleza.

## 7. DoR: casillas y qué falta

> En la tarjeta de #289 la primera casilla ya está marcada. Este documento **no modifica** el issue ni marca ninguna casilla nueva.

| # | Casilla de la DoR (texto de #289) | Estado | Evidencia disponible | Qué falta para cerrarla |
|---|---|---|---|---|
| 1 | Slice de integración y reparto de responsabilidades delimitados. | Marcada en la tarjeta; alcance en revisión. | El título actual («Revisar una carpeta mixta…») y el cuerpo («Acción de carpeta y revisión selectiva») no coinciden; el delta real es menor de lo que sugiere 5/M. | Fijar el alcance y la estimación antes de Ready. |
| 2 | #287 disponible y contratos de #206/#118–#120/#207 contrastados en un SHA completo. | **Pendiente** | Mapa de §3; matriz de §6; 81 pruebas existentes PASS en local. | #287 no fusionada; #118/#120 abiertas; #206/#119/#207 cerradas con DoR incompleta. La decisión del PO debe registrarse, no deducirse. |
| 3 | Mapeo de acciones, selección, cancelación y resultado cerrado con ejemplos de carpeta mixta. | **Parcial** | §3 y §4; E1–E7; dos comprobaciones temporales. | Añadir prueba fija de tres archivos con uno ajeno; decidir etiqueta de entrada y semántica de «Otra serie»/cancelar. |
| 4 | Solapamientos reconciliados; sin cambios encubiertos del servicio. | **Parcial** | §6; no se propone tocar servicios existentes si se elige el alcance A. | Decidir el riesgo del masivo (D2) y si la invalidación de token entra o se difiere. |
| 5 | Entorno y presupuesto numérico aprobados; estimación calibrada y re-revisión favorable. | **Pendiente** | No hay medición de #289; 2.000/1.000 ms es propuesta; no hay navegador/lector/5 s. | Aprobar entorno y umbrales, medir con protocolo, calibrar 5/M y re-revisar. |

### 7.1. Bloqueos de Ready (no de implementación)

1. **#287 no fusionada** y #289 sigue detrás de ella por decisión de coherencia. La acción ya existe en `245402e`; el bloqueo es de secuencia/QA, no de código de entrada.
2. **Reconciliación administrativa**: #206/#119/#207 cerradas por el PO con casillas abiertas; #118/#120 abiertas con código presente. Hay que decidir si se acepta la evidencia de código/pruebas o se reabre/cierra formalmente.
3. **Semántica de invalidación**: «Otra serie» no revoca el token anterior. Si la CA6 exige invalidación, no está cubierta.
4. **Carpeta mixta y masivo**: el masivo puede incluir un ajeno marcable. Si la CA3/objetivo exige protección automática, no está cubierta.
5. **Evidencia de aceptación**: falta prueba fija, navegador real, 360 px, teclado, lector y cinco segundos. Todo `NOT RUN` para #289.
6. **Presupuesto/estimación**: 5/M sin calibración; no hay medición de #289.

## 8. Decisiones para el squad

### D1. ¿Se acepta que «Otra serie» no revoque el token anterior?

- **Opción A (mínima, recomendada para el alcance actual):** aceptar la semántica vigente. La revisión nueva está limpia; el token anterior caduca a los 15 min y está atado a su serie. Documentarlo como «no hay invalidación explícita».
- **Opción B (contrato nuevo):** persistir una revisión/preparación y revocar tokens anteriores al cambiar de serie. Requiere almacenamiento, invalidación y pruebas de idempotencia/seguridad; **no cabe en 5/M** sin trocear.
- **Opción C:** impedir volver a una preparación anterior desde la UI, sin cambiar el servidor. No revoca el token, solo reduce la exposición; no cumple «invalidar» en sentido estricto.

### D2. ¿Qué hace «Marcar todos» en una carpeta mixta?

- **A:** dejarlo como está (marca todo lo marcable) y confiar en la revisión humana. Es el contrato de #207.
- **B:** excluir del masivo los archivos con `con_conflicto_de_carpeta`; cambia #207 y puede dejar fuera archivos que la persona sí querría.
- **C:** mantener el masivo, pero añadir un aviso/confirmación cuando haya conflictos. Cambio de UI/contrato.
- **D:** no usar el masivo en #289; la historia solo garantiza la selección manual. Es la opción más pequeña y compatible con el código actual.

### D3. ¿Qué es «Revisar archivos»?

- **A:** la revisión existente tras elegir una serie local; no se añade una pantalla nueva. Solo se ajusta el texto si hace falta.
- **B:** una acción directa desde la tarjeta, antes de elegir serie; no tiene sentido sin una serie de destino y sería una pantalla nueva.
- **C:** una etiqueta de la acción de la tarjeta que sustituya «Elegir la serie…»; cambio de copy, no de flujo.

### D4. Estimación

- **A (verificación + pruebas + copy):** 2–3 puntos; no 5/M.
- **B (A + invalidación de token):** contrato nuevo; trocear y estimar aparte.
- **C (A + exclusión automática de ajenos/masivo):** cambio de #207/UI; trocear y estimar aparte.

> Recomendación: no declarar Ready con 5/M hasta que el squad elija A/B/C y se vea qué trabajo nuevo llena la estimación. La historia puede ser valiosa como aceptación, pero no debe ocultar un cambio de contrato bajo la etiqueta «reutiliza».

## 9. Pruebas y evidencia local

### 9.1. Pruebas existentes ejecutadas

Comando (entorno local, Postgres 15 en Docker, base de pruebas aislada; no es CI):

```bash
TEST_DATABASE_URL=postgresql://…/zascarr_289_test \
PYTHONPATH=src /tmp/opencode/zascarr-test-venv/bin/python -m pytest -q \
  tests/test_vinculacion_previa_pg.py::TestSeleccionYToken \
  tests/test_vinculacion_previa_pg.py::TestCambiosReflejados \
  tests/test_vinculacion_previa_pg.py::TestPaginas::test_el_token_y_la_seleccion_valen_solo_para_la_pagina \
  tests/test_vinculacion_previa_pg.py::TestLimite::test_a_lo_sumo_100_archivos_y_el_resto_explicado \
  tests/test_asistente_vinculacion_pg.py::TestCriterio1y12Entrada \
  tests/test_asistente_vinculacion_pg.py::TestCriterio7y8Seleccion \
  tests/test_asistente_vinculacion_pg.py::TestCriterio10SinEfectos \
  tests/test_asistente_vinculacion_masivo_pg.py::TestMarcarTodos \
  tests/test_asistente_confirmar_pg.py::TestCriterio2Consentimiento \
  tests/test_u19_continuidad_pg.py::TestLimites
```

Resultado: **39 passed**.

```bash
… pytest -q \
  tests/test_u19_recorrido_pg.py::TestT8VolverAntesDelAlta \
  tests/test_u19_recorrido_pg.py::TestT9VolverDespuesDelAlta \
  tests/test_u19_recorrido_pg.py::TestT10LecturaDelComprobante
```

Resultado: **36 passed**.

```bash
… pytest -q \
  tests/test_vinculacion_previa_pg.py::TestEstados::test_registro_ya_vinculado_se_muestra_y_no_se_puede_marcar \
  tests/test_vinculacion_previa_pg.py::TestConflictos \
  tests/test_vinculacion_previa_pg.py::TestPaginas::test_con_los_cien_primeros_bloqueados_se_llega_a_los_siguientes_y_se_previsualiza_uno
```

Resultado: **6 passed**.

Total: **81 pruebas existentes PASS en local**. No es CI de #289 y no sustituye la CI sobre el SHA de la futura PR.

### 9.2. Comprobaciones temporales (no incorporadas)

Se ejecutaron dos pruebas temporales, no incluidas en el repositorio, con la misma base:

1. `test_dos_de_tres_entran_en_el_token_y_el_ajeno_no`: tres archivos (`Flash 01`, `Flash 02`, `Green Lantern 99`), marcar solo los dos Flash. Resultado: **PASS**. Token con 2; el ajeno sin marcar y fuera del token.
2. `test_marcar_todos_si_incluye_al_ajeno_si_es_marcable`: los mismos tres, pulsar «Marcar todos». Resultado: **PASS** (confirma el riesgo): el ajeno con conflicto y número distinto también se marca y entra en el token.

Estas pruebas deben convertirse en pruebas fijas de #289, con nombres y fixtures del repo, antes de aceptar la CA3.

### 9.3. Lo que sigue `NOT RUN`

| Comprobación | Estado |
|---|---|
| Navegador real de #289 (Chrome/Firefox, escritorio/móvil) | `NOT RUN` |
| 360 px y teclado en la pantalla de revisión mixta | `NOT RUN` |
| Lector de pantalla (Orca/NVDA/VoiceOver/TalkBack) | `NOT RUN` |
| Prueba de cinco segundos con una persona | `NOT RUN` |
| Rendimiento de #289 (p95 de primera revisión y cambio de página) | `NOT RUN` |
| Pi, staging, biblioteca real, despliegue | `NOT RUN` |

U19 tiene evidencia propia de Chrome headless y teclado para su recorrido (`docs/design/ui-u19/README.md`), pero **no** acredita #289, la carpeta mixta con un tercero ajeno, el lector de pantalla ni los cinco segundos. No se hereda como PASS de #289.

## 10. Anexo: prueba fija propuesta para E1/E7

La prueba debe vivir en `tests/test_asistente_vinculacion_pg.py` o en un módulo de aceptación de #289, usar la clave `Comics/Flash (1987)` y una serie local `Flash (1987)`, y comprobar:

- tres archivos: dos Flash y `Green Lantern 99`;
- marcar solo los dos Flash;
- token con exactamente dos archivos;
- el tercero con `marcado=False`, `incluido_en_token=False`;
- cero escrituras en base y disco (reutilizar `instantanea`/`huella_disco`);
- después, pulsar «Elegir otra serie» y comprobar que la nueva página no tiene marcas ni token;
- si se decide D1-B, comprobar además que el token anterior ya no verifica; si se decide D1-A, documentar que sigue verificando hasta su caducidad y **no** presentarlo como invalidado.

Para el masivo, la prueba debe fijar la decisión D2: o el ajeno conflictivo no se marca, o se marca y el test lo declara explícitamente como riesgo aceptado.

## 11. Referencias

- Código: `src/zascarr/web/asistente_carpetas.py`, `asistente_vinculacion.py`, `discovery.py`, `pendientes.py`.
- Plantillas: `carpetas.html`, `asistente_carpeta.html`, `_asistente_locales.html`, `_vinculacion_revision.html`, `_vinculacion_resultado.html`, `_alta_resultado.html`, `asistente_alta_resultado.html`.
- Servicios: `descubrimiento_grupo.py`, `revision_carpetas.py`, `vinculacion_previa.py`, `vinculacion.py`, `tokens_revision.py`.
- Pruebas: `test_vinculacion_previa_pg.py`, `test_asistente_vinculacion_pg.py`, `test_asistente_vinculacion_masivo_pg.py`, `test_asistente_confirmar_pg.py`, `test_u19_continuidad_pg.py`, `test_u19_recorrido_pg.py`, `test_asistente_carpetas_pg.py`.
- Documentos: `docs/design/benchmark-U19-recorrido-vincular.md`, `docs/design/ui-u19/README.md`, `docs/design/rebanada-2-elegir-serie-y-vincular.md`, `docs/design/ficha-propuestas-desde-carpetas.md`.
- PRs: #293 (#287), #299 (#288). Ninguna fusionada en el momento de este contraste.
