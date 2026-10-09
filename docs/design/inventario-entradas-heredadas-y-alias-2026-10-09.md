# Inventario: entradas heredadas que asignan, mueven o crean series, y uso del alias local

> **Estado: evidencia del estado actual, leída del código. No decide nada.** Las decisiones
> están en [ADR 0008](../adr/0008-catalogacion-explicita-y-propuestas-sin-ejecucion-silenciosa.md);
> este documento es lo que el ADR da por hecho y puede actualizarse sin tocarlo.

- **SHA revisado:** [`a53465ac`](https://github.com/juanajok/zascarr/tree/a53465ac39e54ea70a978e729660fc5299fa1036)
  (`main` tras la fusión de #136). Todos los enlaces de abajo están anclados a ese SHA.
- **Método:** lectura de código, plantillas, pruebas, `scripts/` y `docs/`, y búsquedas textuales
  (`grep`) sobre `src/`, `scripts/`, `docs/` y `tests/`. **No se ha ejecutado nada**: ni la
  aplicación, ni las pruebas, ni consultas a fuentes reales.
- **Estado de verificación** (columna final):
  - **Verificado:** el comportamiento descrito se ha leído de extremo a extremo en el código.
  - **Parcial:** se ha leído una parte; lo que falta se indica.
  - **Pendiente:** no se ha comprobado.

## 1. Entradas que asignan o mueven archivos

| Id | Ubicación | Disparador | Efectos actuales | Garantías existentes | Diferencia respecto al objetivo | Verificación |
|---|---|---|---|---|---|---|
| E1 | [`_tarjeta_pendiente.html:20`](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/web/templates/_tarjeta_pendiente.html#L20) | Botón «Sí, es esta» de «Por revisar» (sugerencia del matcher) | `POST /ui/pendientes/{id}/asignar` con `series_id` e `issue_number` (E3) | El número es obligatorio en el formulario | El texto del botón no dice que el archivo se moverá y se renombrará | Verificado |
| E2 | [`_resultados_serie.html:8`](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/web/templates/_resultados_serie.html#L8) | Botón «Confirmar» tras «Buscar serie…» en «Por revisar» | Mismo endpoint (E3) | Idem | Idem | Verificado |
| E3 | [`web/pendientes.py::asignar` L248](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/web/pendientes.py#L248) | Cualquiera de E1/E2; también un cliente no HTMX (devuelve 409 JSON) | Llama a `servicio_por_defecto().asignar(file_id, series_id, issue_number)` (L259) **sin** pasar `aprender_alias`, es decir, `True` | Número vacío se rechaza antes de tocar la BD; los estados del servicio tienen respuesta explícita; el resultado sobrevive al cierre de la petición | Es el **único llamador** de `AsignacionService.asignar` en `src/` (búsqueda textual de `.asignar(` y `servicio_por_defecto`). No pasa por vinculación en sitio | Verificado |
| E4 | [`AsignacionService.asignar` L278](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/asignacion.py#L278), [`_preparar` L308](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/asignacion.py#L308) | E3 y `scripts/medicion/medir_asignacion.py` | Calcula el destino con `build_library_path`, **copia, verifica, publica y retira el origen**; escribe `Issue` si falta, `file.issue_id`, `file.file_path`, `file.file_name`, `metadata_source='manual'` y, si `aprender_alias`, el alias (L565). Operación recuperable (`asignacion_operaciones`, ADR 0006) | ADR 0006: recuperable tras caída, un fallo no deja fichero movido con la BD revertida; colisión de edición (B15); `ya_asignado` idempotente. Pruebas: `test_asignacion_*_pg.py`, `test_pendientes_asignar_pg.py` | Mueve **cualquier** archivo, también uno registrado en su sitio. [ADR 0007](../adr/0007-vincular-en-su-sitio.md) decide no modificarlo: sigue siendo «Organizar» | Verificado |
| E5 | [`ReviewService.assign_to_series` L131](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/review.py#L131) | Ninguno en `src/` | Mueve con la sesión de la petición (`safe_move_async`, L197) y aprende el alias de forma incondicional | Su docstring lo declara camino heredado: «Ya no lo usa ninguna ruta». Se conserva con sus pruebas de B13/B15 (`tests/test_review.py`) | Sin llamadores. La búsqueda se limita a `src/`; su retirada **no** se decide aquí | Verificado (sin llamadores en `src/`); pendiente: scripts externos al repositorio |
| E6 | [`Importer` L319](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/importer.py#L319), [`decide` L291](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/importer.py#L291), [`safe_move_async` L454](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/importer.py#L454) | Ciclo del importador sobre `_scan_dirs` = Transmission, aMule y `downloads_path` | Cada fichero **entrante** se clasifica con `SeriesMatcher.decide` (que consulta el alias, A3) y se **mueve** a la biblioteca: a la ruta de su serie, o a `_Unsorted/` si no hay coincidencia | Dedupe por hash, copia verificada (`safe_move`), colisión de edición (B15) | No recorre la biblioteca ya adoptada (`_scan_dirs` no la incluye). Es el uso legítimo de «mover» para material en tránsito (ADR 0007, decisión 3) | Verificado |
| E7 | [`Importer._reenlazar` L529](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/importer.py#L529) | Un fichero entrante con el mismo contenido que una fila `is_missing` | Mueve a la ruta de la fila existente o a `_Unsorted/` y la reenlaza | Igual que E6 | Ninguna para el objetivo | Parcial: leído el movimiento, no el reenlace completo |
| E8 | [`medir_asignacion.py` L218](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/scripts/medicion/medir_asignacion.py#L218) | Ejecución manual por un desarrollador | Llama a `AsignacionService.asignar` sobre una BD de medición | Es herramienta de medición, no entrada de usuario | Hay que tenerla en cuenta si cambia la firma de `asignar` | Verificado |

**Referencias en documentación** (no son entradas): `docs/design/ui-migracion.md` (inventario de
rutas y plantillas), `docs/design/auditoria-mover-y-sesion.md`, `docs/design/benchmark-V6a-asignacion.md`,
`docs/adr/0006-asignacion-recuperable.md`. Sin referencias en `scripts/` salvo E8.

## 2. Entradas que crean series

| Id | Ubicación | Disparador | Efectos actuales | Garantías existentes | Diferencia respecto al objetivo | Verificación |
|---|---|---|---|---|---|---|
| C1 | [`web/discovery.py::crear` L102](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/web/discovery.py#L102), formulario en [`_resultados_descubrir.html:28`](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/web/templates/_resultados_descubrir.html#L28) | Botón «Crear serie» de Descubrir | Llama a `get_or_create_series` (L118) con `source`, `external_id`, `title`, `tradition`, `start_year`, `description`, `cover_url` **tal como llegan de campos ocultos del formulario** | La URL de portada pasa por la política de H1 (`es_url_de_portada_permitida`); si el identificador externo ya existe se reutiliza la fila | No hay token firmado: los datos de la candidata los aporta el cliente. Sin vista previa ni confirmación, sin colisión por título, sin bloqueo (H4), sin comprobante ni «deshacer», sin procedencia `metadata_["alta"]`. Pruebas: `test_web_discovery.py` | Verificado |
| C2 | [`DiscoveryService.get_or_create_series` L208](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/discovery.py#L208) | C1 (único llamador en `src/`) | Busca por el campo de identificador externo de la fuente; si no existe, inserta una `Series` con `metadata_source` de la fuente y hace `flush` + `refresh` | «Nunca duplica» **por identificador externo**; `ValueError` para una fuente desconocida. Pruebas: `test_discovery_service.py` | No comprueba el título normalizado: dos identificadores distintos con el mismo título crean dos series. Dos peticiones concurrentes con el mismo identificador dependen del `UNIQUE` de la BD (no se ha leído la reacción al choque) | Parcial |
| C3 | [`api/series.py::create_series` L148](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/api/series.py#L148) | `POST /api/series` | `Series(**data.model_dump())` con el esquema Pydantic `SeriesCreate` | Esquema explícito (CLAUDE.md §3.1.3); pruebas en `test_api_series.py` | **Tercer camino de creación**, no incluido en el cruce inicial. No usa el contrato del alta (colisión por título, bloqueos, comprobante). **Su tratamiento no está decidido** en el ADR 0008 | Parcial: no se ha leído el esquema campo a campo |
| C4 | [`alta_serie.py` L384](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/alta_serie.py#L384), `POST /api/revision/serie` | Referencia, no heredado (#97) | El contrato objetivo: alta con vista previa y confirmación, bloqueos, comprobante `alta_operaciones`, procedencia y deshacer | Pruebas: `test_alta_serie_pg.py` | Sin interfaz (2e) | Verificado (como contrato; no como interfaz) |

## 3. El alias local (`local_aliases`, B13)

Modelo: [`LocalAlias` L656](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/models/__init__.py#L656): `pattern_norm` **único** en toda
la instalación → `series_id` (FK con `ON DELETE CASCADE`). No tiene ámbito (carpeta, fuente) ni
estado (activo/inactivo) ni fecha de uso. Una nueva corrección sobre el mismo patrón **sustituye**
a la anterior ([`_learn_alias` L207](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/review.py#L207); prueba
`test_alias_existente_se_actualiza_en_vez_de_duplicarse`).

| Id | Rol | Ubicación | Disparador y efecto | Garantías existentes | Diferencia respecto al objetivo | Verificación |
|---|---|---|---|---|---|---|
| A1 | **Productor** | [`asignacion.py` L565](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/asignacion.py#L565) → `ReviewService._learn_alias` | Al confirmar una asignación (E3/E4) con `aprender_alias=True` (valor por defecto, y E3 no lo cambia). Escribe o sobrescribe el alias del patrón del **nombre original** del archivo | `aprender_alias` se persiste en la operación y sobrevive a la reconciliación (`test_asignacion_integracion_pg.py`, `test_el_alias_solo_se_aprende_si_se_pide`) | Hoy el único camino de usuario que aprende alias es E3, y aprende **siempre** | Verificado |
| A2 | Productor heredado | [`assign_to_series`](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/review.py#L131) | Sin llamadores (E5) | `test_crea_alias_nuevo` | — | Verificado |
| A3 | **Lector (importador)** | [`SeriesMatcher.find_alias` L216](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/core/matcher.py#L216), usado en [`decide` L315](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/core/matcher.py#L315) | Si el título extraído de un fichero **entrante** coincide con un alias, el alias «manda» sobre el fuzzy: resultado `DIRECT`, `score 1.0`, nota «alias local aprendido». El importador (E6) lo clasifica **sin preguntar** y lo mueve a la biblioteca | Solo se aplica a ficheros de `_scan_dirs`, no a la biblioteca adoptada. B15 sigue impidiendo enlazar si el número está compartido entre ediciones. Prueba con dobles en `test_naming_core.py` (L668) | Es el automatismo que M7-US02 pide convertir en propuesta. **No se modifica en esta entrega** (ADR 0008). Falta una prueba contra Postgres real de este camino (`test_matcher_sql_pg.py` no menciona el alias) | Verificado (lectura); prueba SQL real pendiente |
| A4 | **Lector (orquestador)** | [`orchestrator.py` L263](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/orchestrator.py#L263) y [`_candidato_es_del_numero` L488](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/orchestrator.py#L488) | Al buscar una descarga para un elemento de la lista de deseos, los alias de **esa serie** amplían el filtro de candidatos: un nombre distinto del título catalogado (p. ej. «La Patrulla-X» para «X-Men») se acepta si su patrón está en `local_aliases`. Los candidatos supervivientes pasan al ranking y, **en el ciclo automático** (`_process_item`, L171), el primero que se pueda enviar se manda a Transmission o aMule | El número debe coincidir exactamente; las ediciones tipo ómnibus/tomo se rechazan; el filtro falla cerrado (sin serie y sin alias, no acepta); backends P2P desactivados por defecto. Pruebas: `test_orchestrator.py` L854-871 | El alias afecta aquí a **qué se descarga**, no a cómo se cataloga. No se modifica en esta entrega | Verificado de la lectura del alias a la decisión del filtro y de ahí a `_process_item`; **pendiente** el efecto final de `_send` con cada backend |
| A5 | **No productor** | [`vinculacion.py` (cabecera)](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/vinculacion.py#L10) | La vinculación «no aprende alias». La vista previa tampoco escribe alias | **Hay prueba de regresión:** `test_no_aprende_alias_ni_toca_nada_ajeno` ([`test_vinculacion_pg.py` L214](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/tests/test_vinculacion_pg.py#L214)) comprueba que `local_aliases` queda igual tras vincular, y [`test_no_crea_issues_ni_aprende_alias_ni_toca_files` L180](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/tests/test_vinculacion_previa_pg.py#L180) lo comprueba para la vista previa | Ninguna para la garantía «confirmar una vinculación no crea un alias». *Corrige una afirmación mía anterior ("falta una regresión"): existen las dos pruebas.* El alta (#97) no se ha revisado con la misma pregunta | Verificado (vinculación y vista previa); **pendiente** el alta |
| A6 | Gestión | — | Búsqueda textual de `LocalAlias`/`local_aliases` en `src/`: solo los puntos A1–A4 y el modelo. **No hay pantalla, endpoint ni servicio que liste, delimite, desactive o borre alias** | — | Lo cubre M7-US03, aún sin implementar | Verificado por búsqueda textual |

## 4. Observaciones que se derivan del inventario

1. **Un solo camino de usuario produce alias** (A1 vía E3). Si «Por revisar» deja de asignar con
   `AsignacionService` y pasa a vincular en sitio, **nada nuevo aprenderá alias**: los existentes
   seguirán funcionando (A3, A4), pero el mecanismo de «arranque en frío» que describe el propio
   orquestador (un alias se aprende cuando ya hay un fichero asignado a mano desde Pendientes,
   [`orchestrator.py` L518](https://github.com/juanajok/zascarr/blob/a53465ac39e54ea70a978e729660fc5299fa1036/src/zascarr/services/orchestrator.py#L518)) quedaría sin productor hasta que M7-US02
   declare uno explícito. Es una consecuencia de la decisión, anotada en el ADR 0008.
2. **Hay tres caminos de creación de series** (C1, C3, y el alta nueva C4), no dos.
3. **El alias es global a la instalación y se sobrescribe sin aviso**: dos carpetas con el mismo
   título pero series distintas comparten un único alias (el último gana).
4. **Fuera de este inventario** (no mueven ni crean series, pero escriben en archivos o BD y no se
   han revisado aquí): el etiquetado ComicInfo (`services/tagger.py`, `cli/etiquetar.py`) que
   reescribe el CBZ con `os.replace` sin cambiar su ruta, y el enriquecimiento (`services/enricher.py`).

## 5. Verificación pendiente

- Scripts o tareas **externas al repositorio** que llamen a `AsignacionService` o `assign_to_series`.
- Esquema `SeriesCreate` campo a campo (C3) y reacción de C2 ante un choque de `UNIQUE`.
- Efecto final de `_send` por backend (A4).
- Prueba contra Postgres real del alias en el matcher (A3).
- Si el alta (#97) debe tener su propia prueba «no aprende alias» (A5).
