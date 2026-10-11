# Inventario: entradas heredadas que asignan, mueven o crean series, y uso del alias local

> **Estado: evidencia del estado actual, leída del código. No decide nada.** Las decisiones
> están en [ADR 0008](../adr/0008-catalogacion-explicita-y-propuestas-sin-ejecucion-silenciosa.md);
> este documento es lo que el ADR da por hecho y puede actualizarse sin tocarlo.
>
> **Ampliación (#112):** la sección [6](#6-ampliación-para-112-mit-m1-us01-inventario-completo-de-entradas-ui-api-tareas-cli-y-scripts) añade el inventario completo de UI, API, tareas, CLI y scripts con su propio SHA (`ef805ec9`). Las secciones 1–5 y su anclaje a `a53465ac` no cambian.

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

---

# 6. Ampliación para [#112](https://github.com/juanajok/zascarr/issues/112) (MIT-M1-US01): inventario completo de entradas (UI, API, tareas, CLI y scripts)

> **Estado: evidencia del estado actual, leída del código. No decide nada y no cambia comportamiento.** Esta sección **amplía**
> las secciones 1–5 (SHA `a53465ac`, #137), que **se conservan tal cual**, con sus conclusiones y su anclaje histórico: lo que
> allí se comprobó **no se ha repetido aquí** (ver «Qué se reutiliza»). Los criterios de #112 son tres; este documento aporta
> el primero y el tercero y **deja trazado el segundo**: **#112 no queda aceptada con este inventario.**

- **SHA de esta ampliación:** [`ef805ec9`](https://github.com/juanajok/zascarr/tree/ef805ec9f623507628de763ad464f9d19b67b650)
  (`main` tras la fusión de #147). Las rutas de archivo de esta sección se refieren a ese SHA.
- **Alcance del MVP aplicado** (decisión confirmada el 2026-10-10, comentario de #112): *tebeoteca ordenada y vinculada en la Pi* significa
  **vincular en sitio**; los archivos conservan nombre y ruta. «Organizar» (mover o renombrar) queda **fuera del MVP** como no objetivo
  explícito. **«Excluir del recorrido MVP» no significa borrar ni desactivar la función existente.**

## 6.0 Método y leyenda de evidencia

Las cinco clases de evidencia **no se mezclan**; cada fila de las tablas usa estas claves:

| Clave | Significado |
|---|---|
| **L** | **Comprobado por lectura de código** (archivo/función citados). No implica que se haya ejecutado. |
| **P** | **Cubierto por una prueba identificada** (archivo de `tests/`). **No ejecutada en esta ampliación**; su resultado en CI es el de cada PR, no el de esta revisión. |
| **I** | **Acreditado por un informe previo**, con referencia (PR, ADR o ficha). No repetido aquí. |
| **X** | **Ejecutado en esta revisión.** Aquí solo es: (a) un barrido estático de los decoradores de ruta de `src/zascarr/api/` y `src/zascarr/web/`, y (b) un cruce textual entre cada ruta y los archivos de `tests/` que la mencionan. **Nada más:** no se ha arrancado la aplicación, ni ejecutado pruebas, ni tocado archivos o fuentes reales. |
| **N** | **No verificado.** |

**Límites del método.** (1) Los *efectos* y las *garantías* salen de leer los manejadores y los servicios a los que delegan; los servicios muy
largos (`importer`, `enricher`, `orchestrator`, `tagger`) se leyeron por su documentación de módulo y por las funciones que escriben,
no línea a línea. (2) **No se han leído las plantillas ni el JavaScript** de HTMX: qué botón llama a qué ruta solo está acreditado
donde se dice (E1/E2 de §1). (3) Un «P» por *cruce textual* indica que **alguna prueba menciona la ruta**, no que cubra todos sus
casos; **«sin ruta localizada»** significa que la búsqueda textual no halló una prueba que la mencione (puede existir una prueba de
servicio, o una parametrizada por f-string que el cruce no ve). (4) Los scripts de operación se leyeron por su **cabecera y estructura**,
no completos, y **no se ejecutaron**.

## 6.1 Panorama

| | Cantidad | Detalle |
|---|---:|---|
| Endpoints HTTP (API + UI) | **72** | 31 `GET` y **41 de escritura** (37 `POST`, 2 `PATCH`, 2 `DELETE`); 21 en `api/` y 51 en `web/` (X). Además, `GET /` (redirección) y el montaje de `/static` (L, `main.py`). |
| Tareas de fondo del proceso | **5** (+ 1 bajo demanda) | Se lanzan en `lifespan` de `main.py`; **no hay worker `arq`** (L). El registro de la biblioteca corre en segundo plano solo al pulsar «adoptar». |
| Comandos de CLI | 2 | `python -m zascarr.cli.etiquetar` y `python -m zascarr.cli.seguridad` (L). |
| Scripts de operación | 13 en `scripts/` (+ `scripts/medicion/`) y 3 más | `scripts/*.sh` (12), `scripts/ci_postgres.py`, `scripts/medicion/*`, más `bootstrap.sh`, `docker-entrypoint.sh` y `Makefile` (L, por cabeceras). |

**Quién mueve o reescribe archivos** (búsqueda textual de `safe_move`, `shutil.move`, `os.replace`, `.rename(`, `unlink(` en `src/`; X):
`utils/fs.py`, `utils/cbz.py`, `services/tagger.py`, `services/importer.py`, `services/review.py`, `cli/etiquetar.py` y `services/asignacion.py`.
Ningún otro módulo, **y no aparecen en `services/vinculacion*.py`, `services/alta_serie.py`, `services/library_adopter.py` ni `services/library_audit.py`**.

### Clasificación por efecto (resumen; el detalle está en 6.2–6.6)

| Efecto | Entradas |
|---|---|
| **Vincula en sitio** (BD; sin tocar el disco) | `POST /api/revision/vinculacion` · `POST /ui/auditoria/adoptar` (registra archivos ya existentes con su ruta actual) |
| **Mueve y/o renombra** (→ «Organizar») | `POST /ui/pendientes/{id}/asignar` (E3) · tarea de importación (E6/E7) · reconciliación al arrancar · `ReviewService.assign_to_series` (sin llamadores) |
| **Reescribe el contenido** (no mueve) | `cli/etiquetar` con `--apply` (`scripts/etiquetar.sh`) |
| **Crea series** | `POST /api/revision/serie` (alta, C4) · `POST /ui/descubrir/crear` (C1) · `POST /api/series` (C3) |
| **Borra o desvincula catálogo** | `DELETE /api/series/{id}` · `POST /api/revision/serie/{id}/deshacer` |
| **Red hacia fuentes de metadatos** | descubrimiento (`/api/revision/descubrir`, `/ui/descubrir/buscar`), tarea de enriquecimiento, portadas |
| **Red hacia descargas** (Prowlarr, foro, Transmission, aMule) | tarea del orquestador, `buscar-ahora`, `enviar-candidato`, `/api/wishlist/*/search` |
| **Configuración** | `POST /ui/ajustes/guardar/*`, `cli/seguridad`, `bootstrap.sh`, `update.sh` |
| **Solo lectura** | el resto de los `GET` (31, con las salvedades de 6.3) |

## 6.2 API (`/api/*`): 21 endpoints

Columnas: **Entrada · Delegación · Efectos (BD / disco / externo) · Consentimiento · Garantías · Evidencia · Disposición propuesta.**

| Entrada | Delegación | Efectos | Consentimiento | Garantías | Evidencia | Disposición |
|---|---|---|---|---|---|---|
| `GET /api/health` | `api/health.py::health_check` (`_database_status`, `_check_transmission`, `_check_amule`, fichero de estado de la VPN) | BD: lectura · disco: lee un fichero de estado de VPN · externo: comprueba si Transmission/aMule responden (timeout corto, en paralelo) | n/a; **exenta de autenticación** (`_RUTAS_EXENTAS`) | Solo lectura; el estado es observacional, no bloqueante (CLAUDE.md §3.2) | L · P: `health`, `health_db_pg` | **Conservar** |
| `GET /api/legal/status`, `POST /api/legal/accept` | `services/legal.py` (`acknowledge`) | BD: registra la aceptación | Explícito (`acknowledged=true`; 400 si no) | Aceptación versionada (hash del texto legal) | L · P: `legal` | **Conservar** |
| `GET /api/revision/carpetas` | `RevisionCarpetas` | BD: lectura · disco: no · externo: no | n/a (lectura) | Solo lectura; claves de grupo sin depurar | I: #90 (rebanada 1b) · P: `web_carpetas_pg`, `test_vinculacion_limite_pg` | **Conservar** (MVP) |
| `POST /api/revision/descubrir` | `DescubrimientoDeGrupo` | BD: lectura · disco: no · **externo: consulta las fuentes de metadatos**, solo a petición | Explícito (llamada), con espaciado entre búsquedas (`429`) | No escribe; token firmado por candidata; cortesía compartida de Tebeosfera | I: #95, #96, #138 · P: `descubrimiento_grupo_pg`, `tokens_limites_pg` | **Conservar** (MVP) |
| `POST /api/revision/serie/previsualizar` | `AltaDeSerie.previsualizar` | Solo lectura (BD) | Explícito | Sin red ni escritura; token de alta firmado; ≤ 100 parecidas | I: #97, #138 · P: `alta_serie_pg`, `tokens_limites*` | **Conservar** (MVP) |
| `POST /api/revision/serie` | `AltaDeSerie.confirmar` | BD: crea o reutiliza una `Series` + comprobante `alta_operaciones` · disco: no · externo: no | Explícito (solo el token) | Candados, idempotencia, comprobante, procedencia; sin movimientos | I: #97 · P: `alta_serie_pg` | **Conservar** (MVP) |
| `POST /api/revision/serie/{id}/deshacer` | `AltaDeSerie.deshacer` | BD: borra la serie creada por esa operación si no tiene archivos, números, asignaciones ni deseados | Explícito | Exige el comprobante; 409 si no se puede | I: #97 · P: `alta_serie_pg` | **Conservar** (MVP) |
| `POST /api/revision/vinculacion/previsualizar` | `VistaPreviaDeVinculacion` | BD: lectura · **disco: solo `stat`** (no lee contenido) · externo: no | n/a (lectura) | Sin escrituras; estados por precedencia; ahora, fecha antigua y número largo del nombre se tratan como impedimentos (#141, #142) | I: #101, #144, #146 · P: `vinculacion_previa_pg`, `numero_largo_del_nombre_pg`, `fecha_anterior_a_1970_pg` | **Conservar** (MVP) |
| `POST /api/revision/vinculacion` | `VinculacionDeArchivos` | BD: `Issue` + `file.issue_id` + procedencia + informe inmutable · **disco: no mueve, no renombra** · externo: no · alias: no aprende | Explícito (solo el token firmado) | Una transacción, candados, reverificación contra el disco, repetición con el informe persistido, `resultado_incierto` | I: #103, #139 · P: `vinculacion_pg`, `vinculacion_limite_pg` | **Conservar** (MVP; es el camino de «vincular») |
| `GET /api/series`, `GET /api/series/{id}`, `GET …/{id}/missing` | `SeriesService`, consultas directas | BD: lectura | n/a | Solo lectura | P: `api_series` | **Conservar** |
| `POST /api/series` | `create_series` → `Series(**SeriesCreate)` | BD: crea una `Series` **sin** las garantías del alta (sin colisión por título, bloqueos ni comprobante) | Ninguno aparte de la autenticación (llamada programática) | Esquema Pydantic explícito (CLAUDE.md §3.1.3) | L (C3 de §2) · P: `api_series` | **Adaptar** al contrato del alta, o **excluir del recorrido MVP** (decisión pendiente; ADR 0008 no la toma) |
| `PATCH /api/series/{id}` | `update_series` | BD: cambia los campos del esquema `SeriesUpdate` | Ninguno (programática) | `exclude_unset`, esquema explícito | L · P: `api_series` | **Conservar** |
| `DELETE /api/series/{id}` | `delete_series` | BD: borra la serie; por las FK, **borra sus `Issue` (CASCADE) y deja los `File` con `issue_id` NULL** (SET NULL): **desvincula sin tocar el disco** · otras tablas con CASCADE sobre serie/issue (deseados, alias…) | Ninguno (programática); **no hay confirmación** | Rechaza con 409 si hay una asignación en curso | L (FK en `models/__init__.py`, `conflicto_por_operacion_viva`) · P: `api_series`, `asignacion_integracion_pg` | **Adaptar** (confirmación y efecto visible) o **excluir del recorrido MVP**; **no ejecutado** |
| `GET /api/wishlist` | `WishlistService` | BD: lectura | n/a | — | P: `api_wishlist` | **Excluir del recorrido MVP** |
| `POST /api/wishlist` | `WishlistService.add` | BD: crea un deseado · el orquestador lo buscará después | **Aviso legal** (`require_legal_acknowledgment`) | Esquema explícito; legal | P: `api_wishlist` | **Excluir del recorrido MVP** (descargas) |
| `PATCH /api/wishlist/{id}`, `DELETE /api/wishlist/{id}` | `update_wishlist_item`, `WishlistService.remove` | BD | Ninguno (programática) | Esquema explícito | P: `api_wishlist` | **Excluir del recorrido MVP** |
| `POST /api/wishlist/{id}/search` | `WishlistService.retry` | BD: vuelve a poner el deseado en cola; la búsqueda la hace el orquestador en su ciclo | Aviso legal | Salta el *cooldown* | L · **sin ruta localizada en pruebas** (N) | **Excluir del recorrido MVP** |

## 6.3 Interfaz web (`/ui/*`, `/login`, `/estado`, `/legal`): 51 endpoints

| Entrada | Delegación | Efectos | Consentimiento | Garantías | Evidencia | Disposición |
|---|---|---|---|---|---|---|
| `GET /ui/`, `/ui/biblioteca`, `/ui/biblioteca/resultados`, `/buscar-personaje`, `/buscar-saga`, `/ui/series/{id}`, `/ui/wishlist`, `/ui/wishlist/buscar-serie`, `/ui/_nav/estado`, `/ui/pendientes`, `/ui/pendientes/{id}/buscar-serie`, `/ui/auditoria`, `/ui/ajustes`, `/ui/descubrir`, `/ui/legal`, `/legal`, `/login` | `web/*` + consultas | BD: lectura · disco: no · externo: no | n/a | Solo lectura | P: `web_dashboard`, `web_library`, `web_series`, `web_wishlist`, `web_navegacion`, `pendientes`, `web_auditoria`, `web_ajustes`, `web_discovery`, `web_auth` | **Conservar** |
| `GET /ui/pendientes/carpetas` | `RevisionCarpetas` | BD: lectura | n/a | Solo lectura (la superficie de revisión de la rebanada 1) | I: #90 · P: `web_carpetas_pg` | **Conservar** (MVP) |
| `GET /estado` | `web/estado.py` | BD + comprobaciones de alcance de servicios (como `/api/health`) | n/a; accesible en modo diagnóstico | Observacional | L · P: `web_navegacion`, `web_dashboard` | **Conservar** |
| `GET /ui/pendientes/{file_id}/portada` | `web/pendientes.py::portada` (`extract_cover_thumbnail`) | BD: lectura · **disco: lee el CBZ (extrae la primera página) y NO escribe caché** · externo: no | n/a | `ETag` por fecha del archivo; trabajo bloqueante en hilo | L · P: `pendientes`, `web_navegacion` | **Conservar** |
| `GET /ui/series/{id}/portada` | `web/series.py::portada` | BD: lectura · **disco: puede leer un CBZ de la serie y escribe la caché local de portadas** (fuera de la biblioteca) · externo: puede descargar `cover_url` una vez | n/a | Caché local-first; política de portadas H1 (sin *hotlinking*); trabajo bloqueante en hilo | L · P: `web_series`, `cover_ssrf` | **Conservar** |
| `GET /ui/descubrir/buscar` | `DiscoveryService.search` | **externo: consulta las fuentes** a petición · BD: lectura | Explícito (búsqueda) | Cortesía por fuente | L · P: `web_discovery` | **Conservar** |
| `GET /ui/descubrir/portada` | `fetch_and_cache_cover` | **externo: descarga una portada** y la guarda en la caché local | n/a | Lista blanca de hosts y política H1 (SSRF) | I: H1 · P: `web_discovery`, `cover_ssrf` | **Conservar** |
| `POST /ui/descubrir/crear` | `DiscoveryService.get_or_create_series` (C1) | BD: crea una `Series` con datos que llegan del formulario, **sin** las garantías del alta | Explícito (botón «Crear serie»), pero sin vista previa ni token | H1 sobre `cover_url`; dedupe por identificador externo | L (§2) · P: `web_discovery`, `test_discovery_service` | **Adaptar** al contrato del alta (ADR 0008 §2) |
| `POST /ui/pendientes/{id}/asignar` | `AsignacionService.asignar` (E3/E4) | BD: `Issue`, `file.issue_id`, alias · **disco: copia, verifica, publica en una ruta canónica y retira el original (mueve y renombra)** | Explícito (botón «Sí, es esta» / «Confirmar»); **el texto no dice que mueve** | Recuperable (ADR 0006); colisión de edición; `ya_asignado` | I: ADR 0006, §1 · P: `pendientes_asignar_pg`, `asignacion_*_pg` | **Es «Organizar».** Excluir del recorrido MVP; **sustituir en el recorrido normal por «Vincular»** (#114) |
| `POST /ui/pendientes/{id}/ignorar` | `ReviewService.dismiss` | BD: `review_dismissed = true` · disco: no | Explícito (con confirmación del navegador) | — | P: `pendientes` | **Conservar** |
| `POST /ui/auditoria/analizar` | `LibraryAudit.run` | BD: escribe un `ImportRun` con el informe · **disco: lee** (`stat` y *hash* en *streaming* solo de los que comparten tamaño) · no mueve, no registra | Explícito (botón) | Solo lectura del disco; coste acotado | I: B16 · P: `test_library_audit`, `web_auditoria` · **ruta sin prueba localizada** | **Conservar** (MVP: informe antes de registrar) |
| `GET /ui/auditoria/registro` | `registro_biblioteca.estado_actual`, `LibraryAdopter` | BD: lectura | n/a | Solo lectura | P: `web_auditoria`, `registro_biblioteca_pg` | **Conservar** (MVP) |
| `POST /ui/auditoria/adoptar` | `registro_biblioteca.iniciar` → `LibraryAdopter.adopt` | BD: `File` con la **ruta actual**, emparejado con series existentes (no crea series, L); duplicados por *hash* **no se registran** · **disco: lee para el *hash*; no mueve ni renombra ni borra** (sin `safe_move`/`unlink`/`rename` en el módulo) | Explícito (botón); **no se reanuda sola** | Por lotes, idempotente por ruta, una ejecución a la vez, estado «interrumpido» sanitizado | I: B11, B16 · P: `registro_biblioteca_pg`, `test_library_adopter` | **Conservar** (MVP: «registrar una biblioteca existente») |
| `POST /ui/series/{id}/politica` | `cambiar_politica` + `politica.retirar_de_serie` | BD: `wishlist_policy`; **retira de inmediato** los deseados de esa serie · efecto **diferido**: el orquestador generará deseados y buscará | Explícito, pero el efecto de descargas llega después y **requiere el aviso legal** | Lista blanca de valores; retirada atómica | L · P: `web_series` | **Excluir del recorrido MVP** (descargas) |
| `POST /ui/wishlist/anadir`, `/{id}/reintentar` | `WishlistService.add`, `.retry` | BD | Explícito + **aviso legal** | Lista blanca | P: `web_wishlist` | **Excluir del recorrido MVP** |
| `POST /ui/wishlist/{id}/quitar`, `/{id}/cancelar-busqueda` | `WishlistService.remove`; (cerrar panel) | BD (quitar); sin efecto (cancelar) | Explícito | — | P: `web_wishlist` | **Excluir del recorrido MVP** |
| `POST /ui/wishlist/{id}/buscar-ahora` | `Orchestrator.preview_candidates` | **externo: Prowlarr/foro** · BD | Explícito + **aviso legal** | Se detiene **antes** de enviar nada; candidatos con token firmado | L · P: `web_wishlist` | **Excluir del recorrido MVP** |
| `POST /ui/wishlist/{id}/enviar-candidato` | `Orchestrator.send_manual_candidate` | **externo: envía la descarga a Transmission/aMule** · BD | Explícito, por candidato, + **aviso legal** | Token firmado; reclamo atómico del deseado; backend habilitado | L · P: `web_wishlist`, `test_orchestrator` | **Excluir del recorrido MVP** |
| `POST /ui/ajustes/guardar/{comic-vine, fuentes, prowlarr, transmission, amule, avisos}` (6) | `RuntimeSettingsService` | BD: `runtime_settings` + **muta el objeto `Settings` en memoria** (lista blanca `OVERRIDABLE_FIELDS`) | Explícito (formulario) | Lista blanca; secretos no se registran | P: `web_ajustes` (`prowlarr`, `avisos`); **`comic-vine`, `fuentes`, `transmission` y `amule` sin ruta localizada** | **Conservar** (configuración; las de descargas, fuera del recorrido MVP) |
| `POST /ui/ajustes/guardar/seguridad` | `services/seguridad.py` | BD: contraseña (PBKDF2), `auth_mode`, versión de sesión | Explícito | Mismo servicio que `cli/seguridad`; regla de longitud única | P: `web_ajustes` | **Conservar** (MVP: acceso) |
| `POST /ui/ajustes/probar/{comic-vine, prowlarr, transmission, amule, avisos}` (5) | clientes de cada servicio / `Notifier.enviar` | **externo: petición de prueba al servicio o al webhook** · sin escritura | Explícito (botón «Probar») | La causa sale del código HTTP o la clase de excepción, no de `str(exc)` | P: `web_ajustes` (`comic-vine`, `prowlarr`, `avisos`); **`transmission` y `amule` sin ruta localizada** | **Conservar** |
| `POST /login`, `POST /logout` (el `GET /login` está en la primera fila) | `services/auth.py` | Cookie de sesión firmada | Explícito | PBKDF2; sesión versionada | P: `web_auth` | **Conservar** (MVP) |
| `POST /ui/legal/accept` | `services/legal.py` | BD: aceptación | Explícito | Versionada | P: `legal` | **Conservar** |

## 6.4 Tareas de fondo del proceso (`main.py::lifespan`)

Se lanzan **solo si la base de datos está disponible**; en arranque degradado no se lanza ninguna (L, `lifespan`). **No hay interruptor individual** en `Settings` para apagarlas; solo los intervalos son ajustables (`import_interval_minutes` 15, `enrich_interval_minutes` 120, `scan_interval_minutes` 60). **No se ha comprobado si un intervalo de 0 las desactiva** (N).

| Tarea | Delegación | Efectos | Consentimiento | Garantías | Evidencia | Disposición |
|---|---|---|---|---|---|---|
| `reconciliar_al_arrancar` | `AsignacionService.reconciliar` | BD y **disco: continúa o cierra asignaciones que quedaron vivas** (publica la copia y retira el original) | La operación **ya** la confirmó la persona; al arrancar se completa **sin preguntar** | Solo consulta `asignacion_operaciones`; no propaga excepciones; ADR 0006 | I: ADR 0006 · P: `asignacion_servicio_pg`, `asignacion_integracion_pg` | **Conservar** (no actúa sobre vincular) |
| `_library_audit_task` | `LibraryAdopter.should_run` + `LibraryAudit.run` | BD: un `ImportRun` · disco: lectura/*hash* · no registra ni mueve | **Automático, una sola vez** (biblioteca con cómics, catálogo vacío y sin marcador de «hecho») | Solo lectura; marcador en `runtime_settings` | I: B16 · P: `test_library_audit`, `test_library_adopter` | **Conservar** (MVP) |
| `_import_loop` | `Importer.scan_and_import` | BD: `File` · **disco: lee `transmission_download_dir`, `amule_incoming_dir` y `downloads_path`; clasifica, deduplica y MUEVE a la ruta canónica de la serie o a `_Unsorted/`**; marca desaparecidos en la biblioteca (BD, sin tocar el disco, con guardarraíles) · externo: aviso por webhook (mejor esfuerzo) | **Automático**, cada `import_interval_minutes` | `safe_move` (copia verificada, no sobrescribe); dedupe por SHA-256; el instalador comprueba que biblioteca y descargas no se solapen (A9) | I: §1 E6/E7, A9 · P: `test_importer`, `test_importer_triage` | **Es «Organizar» de material entrante.** Excluir del recorrido MVP (no recorre la biblioteca adoptada); **no desactivar** |
| `_enrichment_loop` | `EnrichmentService.enrich_pending` | BD: completa huecos de metadatos (no pisa `manual` ni campos rellenos; reglas de identidad externa de #98) · **externo: Comic Vine, AniList, Tebeosfera** · disco: caché local de portadas | **Automático**, cada `enrich_interval_minutes`; Comic Vine requiere clave | Cortesía por fuente; reglas de convivencia; sin tocar la biblioteca | I: #98, #96 · P: `test_enricher`, `test_enricher_identidad_pg` | **Conservar**, fuera de la aceptación del MVP |
| `_orchestrator_loop` | `Orchestrator.sync_policy_items`, `process_wishlist`, `check_completions` | BD: deseados · **externo: Prowlarr, foro (apagado por defecto), Transmission, aMule** · disco: no (descargan los clientes; luego el importador mueve) | **Automático**, **solo con el aviso legal aceptado** (`is_acknowledged`); el foro está apagado por defecto y cada backend de descarga depende de su `*_enabled` | Cooldown de reintento; reclamo atómico; falla cerrado | I: D1, D8, D10 · P: `test_orchestrator` | **Excluir del recorrido MVP** |
| Registro de la biblioteca (bajo demanda) | `registro_biblioteca.iniciar` | ver `POST /ui/auditoria/adoptar` | Explícito | ver arriba | P: `registro_biblioteca_pg` | **Conservar** (MVP) |

## 6.5 CLI y scripts

| Entrada | Delegación | Efectos | Consentimiento | Garantías | Evidencia | Disposición |
|---|---|---|---|---|---|---|
| `python -m zascarr.cli.etiquetar` (`scripts/etiquetar.sh`) | `TaggerService` | **Por defecto no escribe** (imprime el plan). Con `--apply`: **reescribe `ComicInfo.xml` dentro del CBZ** (`os.replace`), recalcula `sha256_hash`/`file_size_bytes` en BD; no mueve ni renombra; CBR/CB7/PDF no se tocan | **Explícito** (`--apply`); **no hay endpoint ni tarea que lo llame** (búsqueda textual de `tagger`/`etiquetar` en `src/` y `scripts/`) | Plan que caduca si el archivo cambia, *advisory lock* por `File.id`, `locked_fields` respetados, un error no pierde el tebeo | I: B6 (`benchmark-B6-comicinfo.md`) · P: `test_b6_tagger_pg` | **Conservar fuera del recorrido MVP**; ver 6.6 |
| `python -m zascarr.cli.seguridad` (`estado`, `fijar-contrasena`, `efectiva`, `retirar-base-url`) | `services/seguridad.py` | BD: contraseña y `base_url` guardados; la contraseña entra por *stdin* | Explícito (lo invoca el instalador) | Mismo servicio que Ajustes; códigos de salida estables | I: A11 · P: `test_cli_seguridad` | **Conservar** (MVP: instalación) |
| `bootstrap.sh` | — | Host: instala git y Docker si faltan, clona, escribe `.env`, crea directorios, levanta PostgreSQL/Redis, **ejecuta `alembic upgrade head`**, arranca la app; elección guiada de exposición (A11) | Explícito (se ejecuta) + preguntas del instalador | Idempotente; fija la contraseña **antes** de abrir el puerto | I: A11, A9 · P: `test_exposicion*` · **cuerpo no leído completo** | **Conservar** (MVP: instalar) |
| `scripts/update.sh` | — | Copia de seguridad verificada → `git merge --ff-only` → reconstruye la imagen → **`alembic upgrade head` dentro del contenedor** | Explícito | Referencia de rescate `refs/zascarr/update/<TS>`; aborta con cambios locales | L (cabecera) · N (no ejecutado) | **Conservar** (MVP: actualizar). **Aplicará las migraciones 0018/0019 en la primera actualización** que incluya este código |
| `scripts/rollback.sh` | — | Revierte código y restaura el volcado previo | Explícito (`--dry-run` disponible) | Comprueba la revisión de Alembic | L (cabecera) · N | **Conservar** (MVP: restauración) |
| `scripts/backup.sh` | — | Volcado de PostgreSQL a otro disco, con retención | Programado (instalación en cron/systemd) | Verificado, retención automática | L (cabecera) · N | **Conservar** (MVP) |
| `scripts/uninstall.sh` (`make uninstall`, `uninstall-purge`) | — | Borra contenedores, red e imagen; **nunca** la biblioteca ni la configuración | Explícito | Lista de «nunca se borra» | I: A4 · P: `test_ensayo_aislamiento` | **Conservar** |
| `scripts/kavita.sh` (subcomandos `install`, `update`, `status`, `logs`, `restart` y `uninstall`) | — | Gestiona **Kavita** en baremetal. **No se ha localizado en el código una exportación a Kavita** (B20, #149; N) | Explícito | — | L (cabecera) · N | **Excluir del recorrido MVP** |
| `scripts/diagnostico-red.sh`, `medir-pbkdf2.sh` | — | **Solo leen**; imprimen lo que encuentran | Explícito | «SOLO LEE» | I: A10 · P: `test_diagnostico_red` | **Conservar** |
| `scripts/vpn-state.sh` | — | Publica el estado del túnel en un fichero del host | Programado (systemd) | — | L (cabecera) · N | **Excluir del recorrido MVP** |
| `scripts/medicion/*` (`medir_asignacion.*`, `medir_carpetas.py`, `censo*.py`…) | — | Herramientas de medición sobre BD y directorios de prueba; `medir_asignacion` **llama a `AsignacionService.asignar`** (E8) | Explícito (desarrollador) | BD de medición separada | I: V6a · P: `test_medir_asignacion_sh` | **Conservar** (no es una entrada de usuario) |
| `scripts/ci_postgres.py`, `scripts/_comun.sh`, `_exposicion.sh`, `_rutas.sh`, `docker-entrypoint.sh`, `Makefile` | — | Apoyo de CI / librerías de los scripts / ajuste de UID del contenedor / atajos (`make migrate`, `backup`, `uninstall`) | — | `_exposicion.sh` y `_rutas.sh` **no escriben nada** (lo dicen sus cabeceras) | L (cabeceras) · N | **Conservar** |

## 6.6 Etiquetado y huella: una operación distinta de vincular

**Lo que se acredita por lectura (L).** El etiquetado **puede conservar nombre y ruta y, aun así, reescribir el contenido**: son dos afirmaciones compatibles. Las garantías de cada operación son distintas:

| | Vincular (`POST /api/revision/vinculacion`) | Etiquetar (`cli/etiquetar --apply`) |
|---|---|---|
| Nombre y ruta | **No cambian** (garantía y pruebas) | **No cambian** (instala con `os.replace` en la misma ruta; B6) |
| Contenido, tamaño, fecha, *hash* | No se tocan | **Cambian** (reescribe el CBZ; recalcula `sha256_hash` y `file_size_bytes`) |
| Qué archivos alcanza | Los **sin vincular** que se marcan | Los que **ya tienen `issue_id`** y no están `is_missing` (`_consulta` hace `JOIN` con `Issue`) |
| Cómo se activa | Token firmado de la vista previa | Solo CLI con `--apply`; **ninguna ruta web ni tarea de fondo** lo invoca |
| Coordinación | Candados consultivos + `FOR UPDATE` sobre `files` | *Advisory lock* por `File.id` (`pg_advisory_xact_lock`) y plan que caduca |

**Hipótesis pendientes — no son defectos demostrados (N):**
1. **Mutua exclusión.** Vincular bloquea las filas de `files` con `FOR UPDATE` y el etiquetado toma un *advisory lock* por `File.id`: **mecanismos distintos que no se excluyen entre sí**. No se ha comprobado qué pasa si ambos coinciden sobre un mismo archivo.
2. **Huella.** La vista previa firma `(tamaño, mtime)` de los archivos **sin vincular** y la confirmación los reverifica; el etiquetado **solo toca archivos ya vinculados**, así que en el flujo normal no cruza esa huella. Un archivo que ya estuviera vinculado y se etiquetara después **cambia su tamaño y su fecha**: eso afecta a cualquier verificación posterior que dependa de ellos (p. ej. una nueva vista previa sobre ese archivo, o la medición de #122).
3. **Orden recomendado para el MVP** (propuesta, sin implementar): vincular primero, etiquetar después y solo a petición; documentarlo en la aceptación de M4.

No se ha ejecutado etiquetado ni ensayo alguno sobre archivos.

## 6.7 Pendiente trazado a otras tarjetas

- **Criterio 2 de #112** (*un camino que mueve archivos se denomina «Organizar»*): **pendiente y trazado a [#114](https://github.com/juanajok/zascarr/issues/114)**. Este inventario solo acredita **qué caminos mueven** (§6.1): `POST /ui/pendientes/{id}/asignar`, la tarea de importación, la reconciliación al arrancar y `ReviewService.assign_to_series` (sin llamadores). **No cambia ningún rótulo ni texto de la interfaz.**
- **Centralizar decisiones** (alta y creación de series por tres caminos distintos: C1, C3, C4) → [#113](https://github.com/juanajok/zascarr/issues/113).
- **Sin prueba localizada para la ruta** (por cruce textual; puede haber pruebas de servicio): `POST /api/wishlist/{id}/search`, `POST /ui/ajustes/guardar/{comic-vine, fuentes, transmission, amule}`, `POST /ui/ajustes/probar/{transmission, amule}` y `POST /ui/auditoria/analizar`. Cuatro de ellos son de configuración y descargas (fuera del recorrido MVP); **`/ui/auditoria/analizar` está en el recorrido MVP** y su servicio sí tiene pruebas (`test_library_audit`).

## 6.8 Qué se reutiliza y qué no se ha repetido

- **Reutilizado sin repetir:** E1–E8, C1–C4 y A1–A6 (§1–§3), con su SHA `a53465ac`: ninguna de esas filas se ha vuelto a leer línea a línea aquí, salvo las citas de esta sección. Los resultados de #138–#147 se citan como **I**; las cifras de pruebas y CI son las de cada PR.
- **No verificado (N):** el comportamiento en la Raspberry Pi; los efectos reales de los scripts (solo cabeceras); las plantillas y el JavaScript; si algún intervalo de 0 desactiva una tarea; la interacción entre etiquetado y vinculación; y si existen otras rutas montadas fuera de `api/` y `web/` (el barrido cubrió esos dos paquetes y `main.py`).

## 6.9 Disposición propuesta: resumen

| Disposición | Entradas |
|---|---|
| **Conservar (recorrido MVP: instalar, registrar, vincular)** | `bootstrap.sh`, `update.sh`, `rollback.sh`, `backup.sh`, `cli/seguridad`, login/Ajustes de seguridad, auditoría (`analizar`, `registro`, `adoptar`), `/api/revision/*` (7), `GET /ui/pendientes/carpetas`, `_library_audit_task`, `reconciliar_al_arrancar` |
| **Adaptar** | `POST /ui/descubrir/crear` y `POST /api/series` (al contrato del alta, #113); `DELETE /api/series/{id}` (confirmación y efecto visible); `POST /ui/pendientes/{id}/asignar` → **sustituir en el recorrido normal por «Vincular»** y rotular lo que mueve como **Organizar** (#114) |
| **Excluir del recorrido MVP** (**sin borrar ni desactivar**) | Todo lo de descargas (wishlist API y UI, orquestador, Prowlarr/foro/Transmission/aMule en Ajustes), `scripts/kavita.sh`, `vpn-state.sh`, el etiquetado (`--apply`), la tarea de importación (como «Organizar» de material entrante) |
| **Conservar fuera de la aceptación del MVP** | tarea de enriquecimiento, portadas, descubrimiento manual, métricas y diagnóstico |
