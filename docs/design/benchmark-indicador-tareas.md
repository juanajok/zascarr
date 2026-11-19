# Benchmark nivel 2 — «ZascArr está pensando»: tareas en curso, contador y progreso

> Ficha de **benchmark de referencias + diseño técnico**. No implementa, no toca
> `src/`, tests, plantillas, CSS ni tokens; **no declara aprobado** nada y no
> hace commit. La decisión es del PO.
>
> - **Fecha:** 2026-11-17
> - **Base del worktree:** `eb454fbe8ff3ed65980ea2cd08cb15fdf8c29f17`
>   (`.squad/wt-tareas`, rama `docs/indicador-tareas`). Al cerrar la ficha el
>   worktree está 5 commits por detrás de `origin/main` (`e9c07244`); no se
>   actualiza ni se mezcla en este trabajo.
> - **Rol:** SCOUT.bench.
> - **Objetivo:** que el coleccionista sepa que ZascArr sigue trabajando —
>   tareas, contador y progreso tipo Calibre— sin que la app parezca colgada.
> - **Insumo UX ya redactado en este worktree:** `docs/design/ui-indicador-tareas.md`
>   (chip en `.side` + panel «Ahora», umbral 400 ms, sin «0 tareas», sin
>   conversión global). Es **propuesta local sin seguimiento**, no aprobación;
>   este benchmark la usa como hipótesis y añade el registro, el contrato y los
>   adaptadores que le faltan.
> - **Caducidad:** 2027-01-15 (~60 días), o antes si cambia el pipeline de
>   tareas, el diseño global o el worker único.

---

## 1. Problema local: dónde espera hoy el coleccionista

### 1.1 Tareas que ya existen y qué se ve de ellas

| Tarea | Cómo se lanza | Estado que ya existe | Progreso real | Dónde se ve hoy | Qué falta |
|---|---|---|---|---|---|
| **Ciclo del importador** | Automático cada `import_interval_minutes`; manual `POST /ui/no-disponibles/comprobar` | `EstadoCicloDisco`: `inactivo/corriendo/terminado/error/ocupado`; `ImportRun` persiste el resultado (`services/comprobacion_disco.py:46-60,136-176`; `main.py:68-99,390-394`) | **No**: `scan_and_import` recorre `files` sin callback (`services/importer.py:528-545`); los contadores solo se conocen al terminar (`ImportReport`, `:1104-1126`) | Solo en el bloque «Comprobar el disco» de `/ui/no-disponibles`; sondeo cada 5 s mientras corre (`_comprobacion_disco.html:5,22-30`) | No hay contador global, no se ve desde Inicio/Biblioteca, no hay «N de M» durante el ciclo |
| **Rescan de la biblioteca** | Automático cada `rescan_interval_minutes`; manual `POST /ui/auditoria/rescanear` | `EstadoRescan`: `inactivo/corriendo/terminado/error/ocupado`; `RescanReport` en memoria; `ImportRun kind=rescan` (`services/rescan_biblioteca.py:35-60,108-170`) | **No, aunque el servicio lo permite**: `LibraryAdopter.rescanear(progreso=...)` acepta callback (`services/library_adopter.py:512-516,635-636`), pero `rescan_biblioteca._correr` no lo pasa (`:100-102`) | Solo en «Reescanear la biblioteca» de Auditoría; sondeo cada 5 s (`_rescan_biblioteca.html:5,26-34`) | No hay total ni «N de M»; no hay indicador global |
| **Registro de la biblioteca** | `POST /ui/auditoria/adoptar` (inicial o incremental) | `EstadoRegistro`: fase, `total`, `procesados`, `registrados`, errores… (`services/registro_biblioteca.py:38-55,107-116`); callback `progreso=_volcar` en `adopt` (`:165-174`) | **Sí**: total de archivos y procesados por archivo; `LibraryAdopter.adopt` llama a `progreso` tras cada archivo (`services/library_adopter.py:403-446,484-487`) | Bloque `#registro` de Auditoría, con `<progress>` real y sondeo cada 2 s (`_auditoria_registro.html:43-53`) | Es el único que ya tiene una barra real; **no** se ve fuera de Auditoría; no hay contador global; puede seguir si cierras la página |
| **Conversión CBR→CBZ** | Individual o lote `POST /ui/series/{id}/convertir` | **No hay estado de tarea**: la petición ejecuta el servicio y devuelve el resultado (`web/series.py:1890-1898`; `services/conversion.py:1139-1175`) | **No**: `convertir_lote` recorre `lote.vistas` sin callback de progreso | Texto «Convirtiendo la tanda… puede tardar unos minutos» y `htmx-indicator` en la propia página (`_conversion_lote.html:30-35`); individual, «Convirtiendo…» (`_conversion_previa.html:20`) | No hay «N de M», no hay tarea que sobreviva a navegar, no hay indicador global; si cierras, la petición se puede cancelar |
| **Paquetes RAR/ZIP** | `POST /ui/auditoria/paquetes/extraer` | **No hay estado de tarea**; operación durable en `paquete_operaciones`, pero la petición hace extraer + publicar + importar de forma síncrona (`web/auditoria.py:648-657`; `services/paquetes_extraccion.py:456`; `services/paquetes_publicacion.py:53`) | **No**; se conocen los ítems al listar, pero no hay callback por entrada ni fase visible | La vista previa no tiene `hx-indicator`; solo `hx-disable` y el `role=status` vacío de destino (`_paquete_previa.html:5-10`) | **Es el peor caso de «parece colgada»**: petición larga sin señal visible; el botón se deshabilita y no hay barra |
| **Copia de seguridad** | `POST /ui/copias/pedir`; una copia diaria auxiliar | `EstadoCopia`/`VistaCopias` (`en_marcha`, estado, mensaje) leído del fichero de estado del host (`web/copias.py:43-84`; `services/ops_host.py:228-255`) | **No**: el auxiliar no publica «N de M»; solo «Copia en marcha. Puede tardar unos minutos» (`ops_host.py:255`) | Bloque de `/estado`; sondeo cada 5 s mientras `en_marcha` (`_copias_estado.html:1-5`) | No es una tarea del proceso; no hay progreso ni contador global |
| **Descargas de Deseados** | Orquestador/política y cliente externo | `WishlistStatus`; el bloque calcula filas `downloading/downloaded` (`web/wishlist.py:152-207`) | **Parcial**: `%` de Transmission cuando está; aMule se declara sin progreso (`web/wishlist.py:181-198`) | Solo en Deseados; `_progreso_wishlist.html:1-17` con `<progress>`; sondeo cada 30 s (`wishlist.html:38`) | No hay contador global; el resto de la app no sabe que hay descargas |
| **Portadas / miniaturas** | Carga perezosa de cada `<img>` | Ninguno | No aplica | `ui.portada` con marcador de tinta debajo y `loading=lazy`/`decoding=async` (`_componentes.html:34-37`) | No hay skeleton ni spinner; no es una tarea global, pero una rejilla lenta no explica si está trabajando |
| **Enricher / orchestrator / upgrades** | Bucles de `main.py` | Solo logs y estado de fuentes en `Estado`; no hay objeto de tarea | No | No hay UI de progreso; `/estado` sondea salud cada 10 s (`estado.html:131,265-276`) | El trabajo periódico no se ve; no se sabe si está actualizando metadatos |
| **Contadores del menú** | `GET /ui/_nav/estado`, 30 s | `Contadores(pendientes, deseados)` + atención (`services/navegacion.py:25-29`; `_nav_contadores.html:1-8`) | No aplica | Badges del menú; ocultos a 0 | **No hay contador de tareas**; no hay señal global |
| **Resumen de operaciones** | `GET /api/operaciones` | `services/operaciones.py` agrega tablas e incluye fases en memoria de registro y comprobación (`:159-168`) | No hay listado vivo ni progreso | API de solo lectura; no se pinta en UI | Podría alimentar historial, pero no sustituye un registro de tareas |

### 1.2 Dónde puede esperar y por qué parece colgada

- **El importador y el rescan corren en segundo plano, pero solo se ven en su
  bloque.** El coleccionista que está en Inicio, Biblioteca o una ficha no ve
  nada; el texto «sigue en segundo plano» está solo en la pantalla de origen.
  Si el ciclo automático tarda minutos, la app parece quieta.
- **El registro ya tiene la barra correcta, pero está enterrada en Auditoría.**
  Es la mejor prueba de que el patrón funciona; no hay que inventarlo, hay que
  elevarlo a una señal global.
- **La conversión y los paquetes son peticiones HTTP síncronas.** El navegador
  muestra su propio spinner, el botón queda deshabilitado y el texto dice «no
  cierres esta página»; si el paquete tarda, no hay ni fase ni progreso. Es el
  caso que más se parece a «colgada».
- **La copia es un proceso externo.** La app solo sabe «en marcha» o no; no hay
  avance. Prometer un porcentaje sería inventarlo.
- **Las descargas solo existen en Deseados.** Si el PO está en otra pantalla,
  no hay señal de que Transmission/aMule estén trabajando.
- **El menú no tiene un contador de tareas.** Los tres badges existentes
  (pendientes, deseados, atención) no responden a «¿está haciendo algo?».
- **No hay estado `stale`.** Si una tarea se queda sin avanzar, el bloque sigue
  diciendo «en curso» indefinidamente; no hay «sin noticias» ni «tarda más».
- **No hay cancelación global.** No se ofrece porque no todas las tareas saben
  deshacer; pero tampoco se explica esa ausencia.
- **No hay una confirmación de fin global.** El bloque cambia si estás en la
  página; desde otra, el final pasa desapercibido.

### 1.3 Lo que NO hay hoy (confirmado en el árbol)

- **No hay registro de tareas** ni módulo `services/tareas.py`; cada servicio
  guarda su estado en su módulo (`comprobacion_disco`, `rescan_biblioteca`,
  `registro_biblioteca`, `ops_host` para la copia).
- **No hay endpoint global** `/ui/_tareas`, `/api/tareas` ni similar; no hay
  contrato JSON de tareas.
- **No hay SSE/WebSocket/SignalR** en `src/zascarr` (búsqueda de
  `EventSource`, `WebSocket`, `text/event-stream`, `socket.io` sin resultados).
- **No hay contador de tareas en el menú**; `_nav/estado` solo devuelve
  pendientes, deseados y atención.
- **No hay barra global** en `base.html`; el layout no tiene cabecera superior:
  `.side` + `main.content` (`base.html:14-33`).
- **No hay patrón de tarea con fases compartido**: las fases son enums de cada
  servicio y no se traducen a una etiqueta común.
- **No hay cancelación, límite de cola, historial de tareas ni notificación de
  fin** unificados.
- **No hay umbral global**; el único umbral existente es el `indicador-diferido`
  de Descubrir a 400 ms (`web.css:1540-1544`) y el `htmx-indicator` estándar
  (`web.css:575-576`).
- **No hay skeleton** en la biblioteca; `ui.portada` deja un marcador, no una
  forma de carga (`_componentes.html:34-37`).

### 1.4 Restricciones que mandan

- **Un solo proceso** (`uvicorn --workers 1`): el estado en memoria es válido,
  pero no hay coordinación entre réplicas; sin Redis (ADR-0011).
- **Pi compartida, 512 MB por contenedor**: no añadir un worker, una cola
  externa ni un SSE pesado sin medirlo.
- **HTMX + Jinja, sin SPA ni build**: la señal debe ser un fragmento, no un
  cliente nuevo.
- **Diseño:** `<progress>` nativo y progreso real, nunca temporizador que finja
  (`sistema-de-diseno-zascarr.md:379-386`); `aria-live` solo para cambios que
  importan; sin diálogos nativos (`CLAUDE.md` §6; sistema de diseño §Interacción).
- **Privacidad:** los títulos de tarea y fases no llevan rutas, nombres de
  archivo ni mensajes de excepción (`CLAUDE.md` §5.4; benchmark SEC-LOG #369).

---

## 2. Referencias: código real, versión y qué aporta cada una

> No se ha ejecutado ninguna de estas aplicaciones; se ha leído su código en el
> commit indicado. **No se infiere una función por su UI ni su ausencia por no
> encontrarla.**

| Referencia | Versión / commit | Enlaces al código leído |
|---|---|---|
| **Sonarr v4** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` | [Queue.tsx](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Activity/Queue/Queue.tsx#L85-L85), [QueueStatus.tsx](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Activity/Queue/QueueStatus.tsx#L1-L25), [PageSidebarStatus.tsx](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Components/Page/Sidebar/PageSidebarStatus.tsx#L17-L31), [TimeleftCell.tsx](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Activity/Queue/TimeleftCell.tsx#L29-L84), [QueueStatusResource.cs](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/Sonarr.Api.V5/Queue/QueueStatusResource.cs#L5-L15), [QueueStatus.cs](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Core/Queue/QueueStatus.cs#L3-L14), [QueueStatusController.cs](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/Sonarr.Api.V5/Queue/QueueStatusController.cs#L33-L70) |
| **Radarr v5** | `v5.28.0.10274`, commit `54cbbe05d976ac053744012f8b48d44e384e2d41` | [Queue.tsx vacío](https://github.com/Radarr/Radarr/blob/54cbbe05d976ac053744012f8b48d44e384e2d41/frontend/src/Activity/Queue/Queue.tsx#L240-L255), [QueueStatusResource.cs](https://github.com/Radarr/Radarr/blob/54cbbe05d976ac053744012f8b48d44e384e2d41/src/Radarr.Api.V3/Queue/QueueStatusResource.cs#L5-L15), [QueueStatusController.cs](https://github.com/Radarr/Radarr/blob/54cbbe05d976ac053744012f8b48d44e384e2d41/src/Radarr.Api.V3/Queue/QueueStatusController.cs#L33-L75), [PageSidebarStatus.tsx](https://github.com/Radarr/Radarr/blob/54cbbe05d976ac053744012f8b48d44e384e2d41/frontend/src/Components/Page/Sidebar/PageSidebarStatus.tsx#L17-L31) |
| **Kapowarr** | `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2) | [tasks.py](https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/backend/features/tasks.py#L45-L60), [cola](https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/backend/features/tasks.py#L288-L306), [general.js](https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/frontend/static/js/general.js#L196-L233), [socket](https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/frontend/static/js/general.js#L257-L272) |
| **Mylar3** | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (v0.8.3) | [queue_management.html](https://github.com/mylar3/mylar3/blob/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316/data/interfaces/default/queue_management.html#L32-L66), [tabla y sondeo](https://github.com/mylar3/mylar3/blob/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316/data/interfaces/default/queue_management.html#L97-L160) |
| **Calibre** | master `8d119ee9e310918c3693200a9b357bdc98b5884d` (2026-11-16) | [JobsButton](https://github.com/kovidgoyal/calibre/blob/8d119ee9e310918c3693200a9b357bdc98b5884d/src/calibre/gui2/jobs.py#L507-L625), [JobsDialog](https://github.com/kovidgoyal/calibre/blob/8d119ee9e310918c3693200a9b357bdc98b5884d/src/calibre/gui2/jobs.py#L647-L679), [integración en UI](https://github.com/kovidgoyal/calibre/blob/8d119ee9e310918c3693200a9b357bdc98b5884d/src/calibre/gui2/ui.py#L277-L279), [jobs.ui](https://github.com/kovidgoyal/calibre/blob/8d119ee9e310918c3693200a9b357bdc98b5884d/src/calibre/gui2/dialogs/jobs.ui#L1-L90) |
| **Komga** | `25c67d14eb748dd3fb9f6612c099959a077fc850` | [SseController.kt](https://github.com/gotson/komga/blob/25c67d14eb748dd3fb9f6612c099959a077fc850/komga/src/main/kotlin/org/gotson/komga/interfaces/sse/SseController.kt#L56-L90), [TaskQueueSseDto.kt](https://github.com/gotson/komga/blob/25c67d14eb748dd3fb9f6612c099959a077fc850/komga/src/main/kotlin/org/gotson/komga/interfaces/sse/dto/TaskQueueSseDto.kt#L1-L5), [HomeView.vue](https://github.com/gotson/komga/blob/25c67d14eb748dd3fb9f6612c099959a077fc850/komga-webui/src/views/HomeView.vue#L25-L50), [Task.kt](https://github.com/gotson/komga/blob/25c67d14eb748dd3fb9f6612c099959a077fc850/komga/src/main/kotlin/org/gotson/komga/application/tasks/Task.kt#L7-L30) |
| **Kavita** | `e844b64f2d64867afd089adf8af4376bdc85eecc` (0.9.1.23) | [ActivityTracker.cs](https://github.com/Kareadita/Kavita/blob/e844b64f2d64867afd089adf8af4376bdc85eecc/Kavita.Services/SignalR/ActivityTracker.cs#L15-L95), [ActivitySnapshotDto.cs](https://github.com/Kareadita/Kavita/blob/e844b64f2d64867afd089adf8af4376bdc85eecc/Kavita.Models/DTOs/SignalR/ActivitySnapshotDto.cs#L1-L20), [activity-job-row](https://github.com/Kareadita/Kavita/blob/e844b64f2d64867afd089adf8af4376bdc85eecc/UI/Web/src/app/nav/_components/activity-job-row/activity-job-row.component.html#L1-L75) |
| **Suwayomi WebUI** | `7168804c7438d922d5ae17f974c5339ff06544d5` | [NavigationBar.constants.ts](https://github.com/Suwayomi/Suwayomi-WebUI/blob/7168804c7438d922d5ae17f974c5339ff06544d5/src/features/navigation-bar/NavigationBar.constants.ts#L90-L123), [DownloadQueue.tsx](https://github.com/Suwayomi/Suwayomi-WebUI/blob/7168804c7438d922d5ae17f974c5339ff06544d5/src/features/downloads/screens/DownloadQueue.tsx#L1-L180), [DownloaderSubscription.ts](https://github.com/Suwayomi/Suwayomi-WebUI/blob/7168804c7438d922d5ae17f974c5339ff06544d5/src/lib/graphql/download/DownloaderSubscription.ts#L1-L80) |

### 2.1 Sonarr v4 y Radarr v5

**Qué hacen**

- **Contador en el menú:** `QueueStatus` usa `useQueueStatus()` y
  `PageSidebarStatus`; a 0 devuelve `null`, así que no se pinta «0»
  ([Sonarr QueueStatus](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Activity/Queue/QueueStatus.tsx#L1-L25);
  [PageSidebarStatus](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Components/Page/Sidebar/PageSidebarStatus.tsx#L17-L31)).
- **Cola con datos:** `Queue.tsx` pide la cola, muestra `count`, estado, tamaño,
  progreso y tiempo restante; `TimeleftCell` usa `timeleft` y
  `estimatedCompletionTime` y, si no hay dato, pinta `-`
  ([TimeleftCell](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/frontend/src/Activity/Queue/TimeleftCell.tsx#L29-L84)).
- **Estados:** `QueueStatus` enum: `Queued`, `Paused`, `Downloading`,
  `Completed`, `Failed`, `Warning`, `Delay`,
  `DownloadClientUnavailable`, `Fallback`
  ([QueueStatus.cs](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Core/Queue/QueueStatus.cs#L3-L14)).
- **API + SignalR:** `/api/v3/queue/status` devuelve conteos, errores y avisos;
  el controlador emite cambios con debounce de 5 s por SignalR
  ([QueueStatusController](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/Sonarr.Api.V5/Queue/QueueStatusController.cs#L33-L70);
  [QueueStatusResource](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/Sonarr.Api.V5/Queue/QueueStatusResource.cs#L5-L15)).
- **Vacío:** la cola vacía no es una barra a 0; es un mensaje
  `QueueIsEmpty` (`Queue.tsx:362-367`). Radarr v5 hace lo mismo con un
  `Alert kind=INFO` (`Queue.tsx:240-255`).
- **Radarr v5:** misma familia de contador, estados y `TimeleftCell`; se usa el
  commit v5.28 pedido, no el `develop` actual.

**Qué no cubre**

- Es una cola de **descargas/importación**, no un registro genérico de tareas
  de aplicación. No hay un «job» de rescan de biblioteca con barra global.
- El contador cuenta elementos de cola, no trabajos en curso con fases.
- SignalR no es trasladable a HTMX sin una capa nueva; su coste/estado no se
  copia.
- Su `CleanseLogMessage` no tiene que ver con esta historia.

**Lección:** contador oculto a 0, mensaje explícito de vacío, estado + progreso
por elemento y ETA **solo si el cliente la da**. La ETA de una operación de
disco local no es comparable.

### 2.2 Kapowarr

- **TaskHandler** mantiene una cola de tareas, las ejecuta y guarda historial
  (`backend/features/tasks.py:45-60,95-133`). `get_all` devuelve `id`, `action`,
  `display_title`, `running`, `message`, `volume_id`, `issue_id`
  (`:288-306`); no hay porcentaje salvo el mensaje de la tarea.
- **Frontend:** pide `/api/system/tasks`, pinta un mensaje de la tarea en
  `#task-queue`, y gira el icono del botón que la lanzó
  (`frontend/static/js/general.js:196-233`; `base.html:160`). Se actualiza por
  Socket.IO: `task_added`, `task_ended`, `task_status`
  (`general.js:257-272`).
- **Descargas:** la cola de descargas sí tiene progreso, velocidad y estado
  (`frontend/static/js/queue.js:1-75`), pero es otra pantalla, no un indicador
  global.
- **Vacío:** no hay contador global; si no hay tareas, no hay mensaje; el
  `#task-queue` queda vacío.
- **Qué no cubre:** no hay barra determinada por tarea ni contador de tareas
  global; el mensaje es una sola línea y la cancelación es limitada
  (`TaskNotDeletable`). El Socket.IO es una dependencia que ZascArr no tiene.

**Lección:** fase/mensaje corto + historial; no confundir cola de descargas con
tarea de biblioteca.

### 2.3 Mylar3

- `queue_management.html` muestra una sección **ACTIVE** con una barra de
  progreso y estado de la descarga activa (`:32-55`), y una tabla de historial
  con `%`, estado, y acciones `restart/abort` (`:59-66,97-160`). Se refresca por
  DataTables/AJAX.
- **No hay indicador global**: el bloque solo existe en la página de cola. No
  hay contador en el menú ni banner persistente.
- **Qué no cubre:** tareas de biblioteca, fases, ETA, cancelación general; no es
  un patrón global.

**Lección:** una barra real por descarga y estados de reintento; no basta como
solución global.

### 2.4 Calibre: el ejemplo que pide el PO

- **`JobsButton`** vive en la UI (barra inferior), actualiza `Jobs: N`, arranca
  un `ProgressIndicator` con trabajos y lo para a 0
  (`src/calibre/gui2/jobs.py:507-625`; `ui.py:277-279`). El texto exacto es
  «Jobs: N» y el tooltip «Click to see list of jobs».
- **`JobManager`** es un `QAbstractTableModel` con columnas **Job, Status,
  Progress, Running time, Start time**; un timer de 1 s actualiza
  (`jobs.py:59-88,109-130`). Distingue running/waiting; `job_added`/`job_done`
  emiten el número de no terminados (`:611-625`).
- **`JobsDialog`** es **no modal**, con tabla, `Stop selected jobs`, `Hide`,
  `Show details`, `Stop all non device jobs`; el progreso es una barra por fila
  (`jobs.py:647-679`; `jobs.ui:1-90`).
- **Vacío:** `Jobs: 0` y sin spinner; el diálogo se puede abrir y no hay trabajos.
- **Qué no cubre:** es una app de escritorio Qt; el `ThreadedJobServer`, IPC y
  el diálogo no se copian. Tampoco tiene SSE ni un contrato web.

**Lección:** el patrón «contador permanente en una esquina + panel no modal con
lista y detalle + progreso real + cola» es exactamente el que hay que adaptar,
no el código.

### 2.5 Komga

- **SSE de conteo:** `SseController` envía `TaskQueueStatus` cada 10 s a los
  emisores, con `TaskQueueSseDto(count, countByType)`
  (`SseController.kt:56-90`; `TaskQueueSseDto.kt:1-5`). Hay heartbeat cada 15 s.
- **UI global:** en la barra lateral, `v-progress-linear` **indeterminado**
  activo si `taskCount > 0`; tooltip con «pending tasks» y desglose por tipo
  (`HomeView.vue:25-50,446-450`). No hay porcentaje por tarea.
- **Cola/prioridad:** `Task` tiene prioridad y `uniqueId`; `TaskController` solo
  permite **cancelar toda la cola** (`DELETE /api/v1/tasks`), no una tarea
  individual.
- **Vacío:** barra inactiva/oculta a 0; no hay «0».
- **Qué no cubre:** no hay progreso real por tarea, ni ETA, ni historial visible,
  ni detalle. SSE es una conexión persistente que ZascArr no tiene.

**Lección:** un contador global indeterminado ya resuelve «está pensando»; para
progreso real hay que añadir algo más (Calibre/Kavita). No copiar SSE para un
puñado de tareas.

### 2.6 Kavita

- **`ActivityTracker`** es un singleton con `MaxRows=50`, `MaxRecentJobs=100`,
  `NoJobStaleAfter=10 min`, `RecentWindow=24 h`; mantiene filas vivas y
  historial; `GetRunning` descarta las que ya no están vivas o están stale
  (`ActivityTracker.cs:15-95`).
- **Snapshot:** `ActivitySnapshotDto` incluye `Running`, `Scheduled`,
  `RecentJobs`, `RecentEntries`; la UI recibe por SignalR y muestra filas de
  actividad con pasos, contador (`current/total`, `leftToProcess`), edad y
  acciones de descarte (`activity-store.service.ts`; `activity-job-row`).
- **Vacío:** el componente `server-activity` usa un `EmptyState` si no hay
  sesiones; el widget de actividad no pinta filas vacías.
- **Qué no cubre:** es una UI Angular con SignalR; el modelo (running + recent +
  stale + dismiss) es valioso, la tecnología no.
- **Ojo:** su «stale» no mata el job, solo deja de mostrarlo como vivo; es
  exactamente la política que necesita ZascArr.

**Lección:** estados vivo/reciente/stale, pasos con contador y descarte; no
enseñar para siempre un job muerto.

### 2.7 Suwayomi WebUI

- **Badge de descargas en la navegación:** cuenta `downloadStatus.queue.length`;
  si está pausado, el título es «Paused — N remaining»
  (`NavigationBar.constants.ts:90-123`).
- **Cola:** `DownloadQueue.tsx` lista las descargas con estado y progreso;
  `DownloaderSubscription` mantiene la cola actualizada por GraphQL.
- **Vacío:** el badge no se pinta con 0.
- **Qué no cubre:** solo descargas de capítulos; no hay tareas de escaneo ni un
  registro general.

**Lección:** contador en navegación con estado «pausado» y progreso por ítem;
útil para descargas, no para el importador.

### 2.8 Patrones de «app lenta» que sí aplican

- **Umbral:** el proyecto ya usa 400 ms para el indicador diferido de Descubrir
  (`web.css:1540-1544`); es el patrón correcto para que una respuesta rápida no
  parpadee.
- **No fingir:** el sistema de diseño prohíbe simular progreso con temporizador
  y exige `<progress>` nativo (`sistema-de-diseno-zascarr.md:379-386`).
- **Indeterminado:** una barra sin `value`/giro es legítima cuando no hay total
  (Komga; Calibre cuando el job no reporta `%`).
- **Skeleton:** no hay una librería de skeleton en el proyecto; `ui.portada`
  usa un marcador de tinta. Para tareas largas, un texto de fase + barra/
  indeterminado comunica más que un skeleton.
- **No bloquear:** las tareas de disco ya usan `asyncio.to_thread` para E/S
  (`CLAUDE.md` §4; `importer.py:535`; `library_adopter.py:569`); la
  conversión/paquete síncronos de la petición son el punto a revisar.
- **Cancelación/reintento:** solo donde el dominio sabe deshacer; no prometer
  cancelar un `safe_move` o una conversión a medias (Calibre mata, Mylar aborta,
  Komga cancela toda la cola; son contextos distintos).
- **Historial:** útil, pero en ZascArr ya hay `ImportRun` y `operaciones`; no
  crear otra tabla para lo mismo.

### 2.9 Matriz de referencias (adoptar / adaptar / mejorar / construir / descartar)

| Idea | Referencia | Resultado | Motivo |
|---|---|---|---|
| Contador global oculto a 0 | Sonarr, Radarr, Suwayomi | **Adoptar** | El número responde «¿está haciendo algo?»; 0 no se pinta |
| Mensaje explícito de vacío | Sonarr/Radarr `QueueIsEmpty` | **Adoptar** | El panel debe decir «No hay tareas en curso», no quedarse en blanco |
| Panel no modal con lista y detalle | Calibre `JobsDialog`, Kavita activity | **Adaptar** | Se adapta a un panel HTMX; no se copia Qt ni SignalR |
| Barra de progreso real por tarea | Calibre, Sonarr/Radarr, Mylar | **Adoptar** | Es la señal que evita «colgada»; solo con total real |
| Indeterminado cuando no hay total | Komga, Calibre | **Adoptar** | La copia externa no tiene total; no se inventa |
| Fases/pasos con contador | Kavita, Kapowarr, Sonarr | **Adaptar** | En ZascArr las fases son cortas; se traducen a 2–4 pasos de superficie |
| ETA / tiempo restante | Sonarr/Radarr `TimeleftCell` | **Descartar en v1** | En disco local la velocidad es irregular; se puede añadir después con datos |
| SSE/SignalR/WebSocket | Komga, Kavita, Sonarr, Kapowarr | **Descartar en v1** | Un sondeo pequeño con HTMX basta; SSE añade conexión/proxy/estado |
| Polling | Propio `registro` (2 s), `rescan` (5 s), `wishlist` (30 s) | **Construir/mejorar** | Unificar en un fragmento con 2 s activo y 10 s en reposo |
| Historial | Calibre, Kavita | **Construir sobre lo propio** | Ya hay `ImportRun` y `operaciones`; no duplicar tabla |
| Notificación al terminar | Calibre `no_more_jobs`/alert | **Adaptar** | `aria-live`/`region_viva` y «Listo» 8 s; sin alert nativo ni toast ruidoso |
| Cancelar | Calibre, Mylar, Komga | **Descartar en v1** | No todas las tareas saben deshacer; se explica y se enlaza a su pantalla |
| Límite/cola de tareas | Calibre `JobManager`, Komga prioridad | **Construir** | Ya hay cerrojos para una operación de disco; no hace falta un scheduler |
| Stale / sin noticias | Kavita `NoJobStaleAfter=10 min` | **Adoptar** | Evita un «en curso» eterno sin mentir sobre el fallo |
| Estado de error separado | Sonarr/Radarr `Errors/Warnings`; Kavita | **Adoptar** | Error no es «tarda»; se muestra una vez y se puede revisar |
| Dismiss/hide | Calibre, Kavita, Sonarr | **Adaptar** | Solo lo terminado/leído; nunca ocultar una tarea activa |
| Accesibilidad (una `aria-live`, progreso nativo) | Diseño propio + Calibre | **Mejorar** | La app ya tiene `region_viva` y `<progress>`; se usan, no se reinventan |
| Skeleton genérico | — | **Descartar** | No aporta al problema; el marcador de portada ya existe |

---

## 3. Matriz ponderada de decisión

**Pesos** (acordados para esta ficha, no una medición):
**evitar que parezca colgada 35 %**, **frecuencia/utilidad 20 %**,
**coste en la Pi 20 %**, **encaje HTMX/sin Redis 15 %**, **accesibilidad 10 %**.
`P` (1–5) es la prioridad resultante, no un porcentaje.

| Idea | P | Decisión | Evidencia / coste | Límite |
|---|---:|---|---|---|
| Indicador global con contador, oculto a 0 | **5** | **Adoptar** | Calibre `Jobs: N`, Komga, Sonarr/Radarr, Suwayomi | No debe tapar acciones; en móvil, sobre la barra inferior |
| Progreso real por tarea (`X de Y`) | **5** | **Adoptar** | Registro ya lo hace; Calibre/Sonarr/Mylar | Solo si el total es real; sin barra inventada |
| Indeterminado cuando no hay total | **4** | **Adoptar** | Komga; Calibre con `%` desconocido | No usar temporizador |
| Lista/panel de tareas activas | **4** | **Adaptar** | Calibre `JobsDialog`; Kavita activity | Panel no modal; no copiar Qt/SignalR |
| Fases / paso actual | **4** | **Adaptar** | Kavita steps; Kapowarr `message`; Sonarr status | Solo 2–4 fases útiles, no jerga |
| Polling 2 s activo / 10 s reposo | **5** | **Construir/mejorar** | Ya hay sondeos 2/5/30 s; HTMX | Sin DB en el sondeo; parar el detalle si no hay tareas |
| SSE/SignalR | **2** | **Descartar v1** | Komga/Kavita/Sonarr | Conexión persistente, proxy, más estado; no necesario |
| ETA / tiempo restante | **2** | **Descartar v1** | Sonarr/Radarr `TimeleftCell` | Disco/CPU irregular; se puede estudiar luego |
| Historial de tareas | **3** | **Construir sobre lo propio** | `ImportRun`, `operaciones` | Sin tabla nueva; cargar solo al abrir, no en el sondeo |
| Aviso de fin | **3** | **Adaptar** | Calibre alert; `region_viva` | `aria-live` y «Listo» 8 s; sin modal |
| Cancelar | **2** | **Descartar v1** | Calibre/Komga/Mylar | No todas las tareas son reversibles; enlace a su pantalla |
| Límite/cola de tareas | **4** | **Construir** | Cerrojos de disco; Calibre JobManager | Una operación de disco; no un scheduler genérico |
| Stale / sin noticias | **5** | **Adoptar** | Kavita 10 min; Calibre timeout | No matar ni marcar error sin evidencia |
| Error visible y con qué hacer | **5** | **Adoptar** | Sonarr/Radarr warnings/errors; Kavita | Tipo de error, sin `str(exc)` ni ruta |
| Accesibilidad (una sola `aria-live`) | **5** | **Mejorar** | Diseño propio; Calibre | No anunciar cada tick; `progress` nativo |
| Dismiss/hide | **2** | **Adaptar** | Calibre, Kavita | Solo tareas terminadas/leídas; nunca activas |
| Contador en navegación | **3** | **Adaptar** | Sonarr/Radarr badge; Suwayomi | El chip global ya cuenta; un badge extra solo si el PO lo pide |
| Coste/memoria en Pi | **4** | **Construir** | Sin Redis; 512 MB; un worker | Registro acotado; sin SSE; sin DB por sondeo |

**Conclusión de la matriz:** adoptar el **contador + panel + progreso real +
stale**, construir un **registro en memoria + fragmento HTMX con sondeo**, y
descartar **ETA, SSE, cancelación y scheduler** en la primera versión.

---

## 4. Diseño propuesto para ZascArr

> Propuesta técnica; el PO decide. La pieza UX ya está descrita en
> `docs/design/ui-indicador-tareas.md` (worktree, **sin aprobar**): chip en
> `.side`, panel «Ahora», umbral 400 ms, sin «0 tareas», fuera de
> `main[hx-history-elt]`. Este apartado fija el **registro y el contrato** que
> esa pieza necesita.

### 4.1 Principios

1. **Una sola fuente de verdad en memoria**, en el proceso único; sin Redis y sin
   tabla nueva.
2. **El servicio escribe, la web solo lee.** Los routers no inventan tareas ni
   calculan progreso.
3. **Progreso real o indeterminado.** Nunca un porcentaje por temporizador.
4. **Tareas de fondo, no cada petición.** Una búsqueda de 400 ms o una portada
   no son tareas globales; tienen su indicador local. El criterio operativo es:
   dura previsiblemente >1 s, tiene estado de inicio/fin y el coleccionista puede
   cambiar de pantalla mientras sigue.
5. **El silencio es un estado.** Sin tareas no hay chip, ni «0», ni «Todo al día»
   permanente.
6. **El estado sobrevive a la navegación HTMX**, pero no al reinicio del proceso:
   al arrancar no hay tareas y el chip no miente.
7. **Nada de rutas, nombres de archivo, `str(exc)` ni credenciales** en títulos,
   fases ni mensajes (SEC-LOG #369).
8. **Un solo worker** es una invariante; si algún día hay más, este registro no
   se comparte y habrá que replantearlo.

### 4.2 Registro en memoria

Módulo nuevo propuesto: `services/tareas.py` (sin dependencias nuevas).

```text
Tarea
  id: str                  # opaco, 8 hex; nunca un id de fila ni una ruta
  tipo: str                # importar | rescanear | registrar | convertir |
                           # paquete | copia | descargas | metadatos
  titulo: str              # copy de superficie, estático por tipo
  estado: str              # en_cola | corriendo | terminada | error |
                           # interrumpida | estancada
  fase: str | None         # «Importando», «Comprobando el disco»…
  hecho: int | None        # None si no se sabe
  total: int | None        # None si no se sabe
  unidad: str | None       # archivos | tebeos | CBR | paquetes…
  iniciada: datetime
  actualizada: datetime    # heartbeat; no se actualiza en cada tick de UI
  detalle: str | None      # solo superficie; sin datos personales
  run_id: str | None       # enlace al ImportRun / operación durable
  puede_cancelar: bool     # False en v1
  origen: str              # manual | automatico
  mostrar_desde: datetime  # umbral de 400 ms
```

**Operaciones del registro**

- `registrar(tipo, titulo, total=None, unidad=None, fase=None, run_id=None,
  origen=...) -> Tarea`
- `avanzar(id, hecho=None, total=None, fase=None, detalle=None)`
- `terminar(id, resumen=None)` / `fallar(id, tipo_error)` /
  `interrumpir(id, tipo_error)`
- `snapshot(incluir_recientes=False) -> dict`
- `limpiar_al_arrancar()`: el proceso nuevo no hereda tareas.

**Reglas**

- **Cota:** máximo 20 tareas activas + 5 recientes; una tarea terminada se
  conserva 8 s para el anuncio de «Listo» y luego se retira. Sin fuga de memoria.
- **Actualización:** una vez por archivo/ítem, no por byte; como máximo un
  `avanzar` cada 250 ms si el bucle es muy rápido (coalescer). El DOM no se
  actualiza a 60 Hz.
- **Hilo:** todo ocurre en el bucle de eventos. Si un callback viene de un hilo
  (p. ej. `asyncio.to_thread`), se publica con `loop.call_soon_threadsafe`; no
  se toca el registro desde dos hilos.
- **Errores:** solo `tipo_error` (nombre de clase); la UI dice «No se pudo
  terminar» y enlaza a la pantalla. Nunca el mensaje ni la traza.
- **Stale:** si `actualizada` supera 60 s, la fila se marca «sin noticias»; si
  supera 10 min, «puede estar atascada» (ámbar). No se cambia a error ni se
  cancela automáticamente.
- **Reinicio:** `limpiar_al_arrancar()` en `create_app`; no hay reanudación
  automática (el registro ya no se reanuda solo, `registro_biblioteca.py:1-11`).

### 4.3 Contrato JSON

`GET /api/tareas` (solo lectura, autenticado, `Cache-Control: no-store`):

```json
{
  "version": 1,
  "generado": "2026-11-17T10:33:57Z",
  "resumen": {
    "total": 2,
    "corriendo": 1,
    "en_cola": 1,
    "con_error": 0,
    "hay_tareas": true
  },
  "tareas": [
    {
      "id": "a1b2c3d4",
      "tipo": "registrar",
      "titulo": "Registrando tu biblioteca",
      "estado": "corriendo",
      "fase": "Mirando los tebeos",
      "hecho": 3,
      "total": 12,
      "unidad": "tebeos",
      "pct": 25,
      "eta_segundos": null,
      "iniciada": "2026-11-17T10:30:00Z",
      "actualizada": "2026-11-17T10:33:55Z",
      "estancada": false,
      "puede_cancelar": false,
      "run_id": "uuid-o-null",
      "detalle": "3 de 12 mirados; 2 ya guardados"
    }
  ]
}
```

**Reglas del contrato**

- `pct` se calcula **solo** si `total > 0`; si no, `pct: null` y la UI usa
  indeterminado. No se envía un `pct` de relleno.
- `eta_segundos` es `null` en v1. Si algún día se calcula, solo con una ventana
  de al menos 3 ítems y se etiqueta como estimación; nunca con el primer ítem.
- `detalle` no lleva rutas, nombres, URLs ni `str(exc)`; es copy de superficie.
- `run_id` enlaza al `ImportRun`/operación durable para el detalle y el
  historial; no sustituye al id de tarea.
- El endpoint no consulta la BD: lee el registro en memoria. Es barato y no
  puede bloquearse por una BD lenta.
- El snapshot es una copia; no se expone el objeto mutable.

### 4.4 Fragmento HTMX

`GET /ui/_tareas` devuelve **fragmentos OOB**, no una página:

- `#tareas-lista`: filas de tareas activas.
- contador visible del chip y `#tareas-nombre` (nombre accesible); no se
  reemplaza el `<details>` ni el `<summary>`.
- `#tareas-anuncio`: **solo** cuando cambia el estado (empezó, terminó, falló,
  pasó a «tarda más»), nunca en cada tick.
- Si no hay tareas: lista vacía, contador oculto y `#tareas-anuncio` vacío; el
  `<details>` abierto se queda con «No hay tareas en curso.».
- `Cache-Control: no-store`.
- **Autenticación:** añadir `/ui/_tareas` a
  `services/auth.py::RUTAS_FRAGMENTO_SILENCIOSO` (`:130-136,645-704`). Si la
  sesión caduca, el fragmento responde 204/ vacío y no intercambia el login en
  el chip. Sin esto, el sondeo global sería un redirect disfrazado.
- En el HTML, ningún campo se interpola sin escapar; los títulos son estáticos
  y no incluyen datos del usuario.

### 4.5 Dónde y cómo se pinta

Se alinea con `docs/design/ui-indicador-tareas.md`:

- **Chip en `.side`**, fuera de `main[hx-history-elt]`, para que no lo sustituya
  una navegación HTMX.
- **Panel «Ahora»** no modal, abierto con `<details>`; lista, fase, tiempo,
  barra real o giro, enlace «Ver la tarea».
- **Sin tareas:** oculto; el panel abierto no se cierra de golpe, muestra «No
  hay tareas en curso» hasta que se cierre.
- **Estados:** «En curso» (info), «Hecho» (ok, 8 s), «Error» (warn, se queda
  hasta abrir), «Tarda más» (amber, 10 min sin noticias). No se usa rojo por
  tardar.
- **Accesibilidad:** un solo `aria-live="polite"` para cambios de estado; el
  `<progress>` nativo con etiqueta; el panel no está dentro de la región viva;
  no se anuncia cada `X de Y`; foco estable; 44 px; 14 px; `prefers-reduced-motion`
  apaga pulso/giro.
- **Sin colores, iconos ni JS nuevos:** se usan `ui.chip`, `ui.progreso`,
  `region_viva`, el icono `activity` existente y CSS de la hoja.

**Alternativa descartada:** una banda que empuje el contenido al aparecer
provoca salto de layout; una píldora fija puede tapar. La propuesta UX del
worktree ya resolvió el sitio en `.side`; este benchmark no la reabre salvo
decisión del PO.

### 4.6 Sondeo, no SSE

| Opción | Coste | Latencia | Riesgo | Veredicto |
|---|---|---|---|---|
| **Sondeo HTMX** | 1 petición pequeña cada 2 s activo / 10 s reposo; sin BD | ≤2 s | Ninguno nuevo; ya se usa en 4 bloques | **v1** |
| **SSE** | Conexión persistente, heartbeat, reconexión, proxy/TLS; más estado en uvicorn | Inmediata | Complejidad y RAM; no hay infraestructura SSE | **Descartar v1** |
| **WebSocket/SignalR** | Dependencia/servidor nuevo | Inmediata | Contradice el stack y el presupuesto | **Descartar** |
| **Sondeo cada 30 s** | Más barato | Hasta 30 s | Una tarea de 20 s puede no verse | **Solo reposo si el PO prefiere menos ruido** |

**Propuesta:** `load, every 10s` en reposo; si `hay_tareas`, el fragmento
devuelve `every 2s`; al quedar vacío, vuelve a 10 s. En v1 no hay SSE.

**Cómo aparece una tarea nacida en segundo plano:** con 10 s de reposo, en
≤10 s; una tarea lanzada por una acción de la página ya tiene su indicador local
y el chip aparece en el siguiente sondeo. Si el PO exige inmediatez absoluta,
la respuesta de la acción puede disparar un `HX-Trigger`/OOB, pero no es
necesario para v1.

**No bloquear:** el endpoint no consulta la BD, no abre sesión y no hace E/S.
El registro ya tiene el estado; responde en microsegundos.

### 4.7 Cómo medir avance real sin fingir

| Tarea | Total real | Fase | Actualización |
|---|---|---|---|
| **Importar** | `len(files)` tras listar Descargas (`importer.py:534-536`) | «Buscando en Descargas» → «Importando» → «Comprobando la biblioteca» | Callback `progreso` por archivo en `scan_and_import`; `hecho`++; al terminar, resumen |
| **Rescan** | Desconocido hasta `_recorrer`; después `report.files_scanned` | «Recorriendo la biblioteca» → «Revisando cambios» | Pasar `progreso` a `LibraryAdopter.rescanear` (`library_adopter.py:512-516`); antes de saber el total, indeterminado |
| **Registrar** | `report.to_process` (ya existe) | «Mirando los tebeos» | Ya lo hace `_volcar` (`registro_biblioteca.py:107-116`); solo se eleva a global |
| **Convertir lote** | `len(lote.vistas)` | «Convirtiendo 3 de 8» | Añadir callback en `convertir_lote` (`conversion.py:1139-1175`); si sigue siendo petición, no prometer que sobrevive a navegar |
| **Paquete** | `len(op.items)` tras listar | «Extrayendo» → «Verificando» → «Importando» | Callback por entrada/fase en `paquetes_extraccion`/`publicacion`; no hay progreso por byte |
| **Copia** | Desconocido (proceso externo) | «Copia en marcha» | Indeterminado; se lee el estado existente, no se inventa |
| **Descargas** | Cola externa; `%` de Transmission | «Descargando 2 de 3» | Se reutiliza `_progreso_wishlist`; no se consulta por fila en el sondeo global |

**Regla:** si el total no existe antes de empezar, se muestra indeterminado
hasta conocerlo; no se muestra «0 %» ni «99 %» fijo. Si el total cambia (rescan
que descubre más archivos), se actualiza y el porcentaje puede bajar; es real.

### 4.8 Integración con los trabajos existentes

| Servicio actual | Cambio propuesto | No cambiar |
|---|---|---|
| `comprobacion_disco` | Registrar tarea al iniciar manual/automático; `Importer` acepta callback; fases; terminar/error | Cerrojo, estado, persistencia de `ImportRun`, notifier |
| `rescan_biblioteca` | Pasar `progreso` que ya acepta `LibraryAdopter`; registrar; fase antes/después del recorrido | Cerrojo compartido, `RescanReport`, lectura de `ImportRun` |
| `registro_biblioteca` | Registrar alrededor de `_ejecutar`; reutilizar `_volcar`; cerrar en `finally` | Su callback, cerrojos, contrato de lotes |
| `conversion` | Registrar tarea de petición; total de `lote.vistas`; callback; **si se quiere global**, mover a tarea de fondo (decisión PO) | Tokens, verificación, diario, deshacer |
| `paquetes` | Registrar y emitir fases; **no es global mientras siga síncrono**; si se mueve a fondo, usar el mismo registro | Tokens de un solo uso, verificación, publicación durable |
| `copias` | Mantener su bloque; añadir al registro como tarea externa indeterminada si el PO lo pide | Estado del host, sondeo 5 s |
| `wishlist` | Mantener su widget; opcionalmente exponer el conteo de descargas al registro desde el orquestador | Polling 30 s, Transmission, estados |
| `enricher/orchestrator/upgrades` | No registrar en v1 salvo que el PO quiera ver el ciclo; si se registra, solo si dura >1 s y con fase | Bucles, intervalos, no bloquear |
| `api/operaciones` | No cambia; sirve para historial, no para el sondeo en vivo | Contrato existente |
| `_nav/estado` | Opcional: incluir `tareas` en el mismo fragmento OOB; no añadir otra petición | Contadores, degradación a 204 |

**Qué NO se envuelve:** cada búsqueda, cada portada, cada validación de
contraseña, la carga de una página, el healthcheck ni una petición breve. Esas
tienen `htmx-indicator` local con el umbral existente.

### 4.9 Estados, stale, error y límites

- **En cola:** hoy no hay una cola genérica; si una tarea de disco encuentra el
  cerrojo ocupado, el servicio responde `ocupado`. El registro puede mostrar
  «Otra tarea de disco está en curso» como mensaje, no como tarea falsa.
- **Corriendo:** fase + `hecho/total` o indeterminado; `actualizada` avanza.
- **Terminada:** «Hecho» 8 s y resumen; el panel abierto lo conserva hasta
  cerrarlo.
- **Error:** tipo de error; «No se pudo terminar. Vuelve a intentarlo desde la
  tarea»; enlace a la pantalla. No se autodescarta sin abrir.
- **Interrumpida:** por apagado/cancelación; se marca y se retira; no se
  reanuda.
- **Estancada:** 10 min sin heartbeat; «Tarda más»; no se mata y no se pinta
  en rojo.
- **Límite:** una operación de disco a la vez la garantizan los cerrojos
  existentes; el registro no crea un scheduler. Máximo 20 activas en memoria.
- **Cancelar:** `puede_cancelar=false` en v1. La cancelación de una tarea de
  disco/paquete no está soportada hoy; no se ofrece un botón que no cumple.
- **Historial:** se lee de `ImportRun` (`kind=adopt/rescan/audit`), de
  `operaciones` y de los bloques existentes, **solo al abrir el panel/página**;
  no en cada sondeo. Sin migración.

### 4.10 Pruebas que deberá exigir la especificación

1. **Registro unitario:** crear, actualizar, terminar, error, reinicio; cota y
   limpieza de recientes; snapshot inmutable; ningún `str` con `/` de ruta.
2. **Contrato JSON:** claves y tipos; `pct` nulo sin total; `pct` calculado con
   total; `version`; 0 tareas devuelve `hay_tareas=false`; sin rutas/nombres.
3. **Fragmento HTMX:** vacío no pinta contador; con tareas pinta lista y
   `every 2s`; en reposo `every 10s`; no reemplaza `<details>`/`<summary>`;
   `Cache-Control: no-store`.
4. **Autenticación:** `/ui/_tareas` está en `RUTAS_FRAGMENTO_SILENCIOSO`; sin
   sesión no redirige ni rompe el chip.
5. **Importador:** callback produce `hecho` por archivo; total conocido; fases;
   no actualiza por byte; no bloquea el bucle.
6. **Rescan:** se pasa `progreso` y se ve el avance; antes de `_recorrer` es
   indeterminado; no se inventa un porcentaje.
7. **Registro:** se reutiliza el progreso existente; `total` y `procesados`
   coinciden; al terminar con errores, no anuncia éxito.
8. **Conversión/paquete:** tarea se cierra en éxito y en error; no se queda
   «corriendo»; si la petición se cancela, se marca interrumpida; no filtra
   nombre de archivo.
9. **Copia externa:** indeterminada; no muestra `%`; stale si no hay noticias.
10. **Accesibilidad:** una sola `aria-live`, anuncio solo en cambio de estado;
    `<progress>` con etiqueta; foco estable al refrescar; 44 px; sin movimiento
    con `prefers-reduced-motion`.
11. **Control negativo:** sin registro no aparece chip global; las tareas
    siguen viéndose en sus bloques actuales; no se crean tareas por peticiones
    cortas.
12. **Rendimiento:** 0/1/10 tareas, 10 000 snapshots en el banco; **NOT RUN**
    en la Pi hasta medir.

---

## 5. Riesgos y coste en la Pi

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Sondeo de más (varias pestañas) | Media | Bajo | 2 s activo, 10 s reposo; sin BD; respuesta pequeña; opcional pausa con pestaña oculta |
| Estado viejo tras reinicio | Alta | Bajo | `limpiar_al_arrancar`; sin reanudar; historial en BD |
| Tarea síncrona no avanza | Media | Alto | Convertir/paquete: fases + `to_thread`; si no, no prometer progreso |
| Falsa ETA / % inventado | Alta si se copia Sonarr | Alto | Sin ETA v1; `pct` solo real |
| Barra que tapa acciones | Media | Medio | Chip en `.side`; panel no modal; sin overlay permanente |
| Anuncio por cada tick | Media | Medio (a11y) | Una sola `aria-live`; solo cambios de estado |
| Tarea atascada sin señal | Media | Medio | Stale a 10 min; «Tarda más»; enlace a su pantalla |
| Duplicar estado/sondeos | Alta | Medio | Un solo registro; los bloques actuales se mantienen, pero el chip lee del registro |
| Multiusuario/multiworker | Baja hoy | Alto | Invariante `--workers 1`; si cambia, registro no compartido; replantear |
| Fuga de memoria | Baja | Medio | Cota 20 activas + 5 recientes; 8 s de gracia |
| Rutas/nombres en copy | Baja | Alto (privacidad) | Títulos estáticos; `detalle` sin datos; test negativo |
| Sobrecarga de callbacks | Baja | Bajo | Un `avanzar` por archivo, coalescer 250 ms; no por byte |
| Confusión «tarea» vs «espera local» | Media | Medio | Criterio explícito: >1 s, fondo, estado propio; búsquedas/portadas no |

**Coste estimado, sin medir:**

- **Sondeo:** 6 req/min en reposo, 30 req/min con una tarea; respuesta <2 KB;
  ~12 KB/min por pestaña. Tres pestañas: ~36 KB/min. Sin consultas SQL.
- **Memoria:** 20 tareas × cadenas cortas ≈ <20 KB; sin Redis, sin worker.
- **CPU:** serializar un dict pequeño y renderizar un fragmento; el coste
  real está en el trabajo de disco, no en el indicador.
- **DOM:** una píldora y un panel; el panel no se reemplaza entero en cada
  sondeo (OOB de filas), así que no pierde foco ni estado abierto.
- **No se añade** una dependencia, un servidor SSE, un proceso, una tabla ni una
  migración.

**Medición pendiente (NOT RUN):** latencia/CPU con 1, 5 y 20 tareas en la Pi 4,
tres pestañas, 2 s/10 s, y prueba con el panel abierto durante una tarea larga.

---

## 6. Decisiones abiertas para el PO

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 1 | ¿Dónde vive el contador? | chip en `.side` (UX ya redactada); badge en menú; ambos | **Chip en `.side`**; badge solo si el PO lo pide |
| 2 | ¿Qué tareas son globales? | solo fondo; incluir conversión/paquete; incluir descargas | **Solo fondo y descargas**; conversión/paquete siguen locales mientras sean peticiones |
| 3 | ¿Se mueve conversión/paquete a segundo plano? | no; sí | **No en esta historia**; si se mueve, usar el mismo registro y no prometer «sobrevive» antes |
| 4 | ¿ETA? | sí; no | **No v1**; reevaluar con datos reales |
| 5 | ¿Cancelar? | global; por tarea; no | **No v1**; enlace a la pantalla y confirmación existente |
| 6 | ¿Historial? | panel; página; solo enlaces a lo actual | **Sin página nueva**: enlaces a Auditoría/No disponibles y `ImportRun` |
| 7 | ¿Copia externa en el chip? | sí, indeterminada; no | **Sí si no cuesta un sondeo extra**; si no, mantener su bloque |
| 8 | ¿Descargas en el chip? | sí, con conteo; no | **Sí como conteo sin `%`** si el orquestador ya lo tiene; no consultar Transmission cada 2 s |
| 9 | ¿Frecuencia en reposo? | 10 s; 30 s; solo 3 s siempre | **10 s**; 3 s activo si el PO prefiere la UX redactada; nunca sondeo sin parar |
| 10 | ¿Umbral? | 400 ms; 300 ms; inmediato | **400 ms**, ya usado en la app |
| 11 | ¿Se retiran las tareas viejas? | 8 s; 30 s; hasta cerrar | **8 s para «Hecho»**, errores hasta abrir |
| 12 | ¿«Tareas» o «Trabajos»? | tareas; trabajos | **«Tareas»** (español llano; «job» no) |
| 13 | ¿Registro compartido si hay más de un worker? | no; Redis; DB | **Fuera de alcance**; mantener `--workers 1` y documentar |
| 14 | ¿Se anuncia cada fase? | sí; no | **No**; solo cambio de estado |

---

## 7. NOT RUN y estado de la ficha

| Comprobación | Estado | Motivo |
|---|---|---|
| Lectura del código actual y de las 8 referencias | **PASS de lectura** | Commits y enlaces de §2; no se ejecutaron las apps |
| Inventario de tareas y feedback del árbol | **PASS de lectura** | `eb454fbe`; ver §1 |
| Ejecutar Sonarr/Radarr/Kapowarr/Mylar/Calibre/Komga/Kavita/Suwayomi | **NOT RUN** | Solo se leyó código; no se tomaron capturas |
| Medir rendimiento en la Pi (1/5/20 tareas, 3 pestañas) | **NOT RUN** | Esta ficha no arranca la app |
| Probar navegador real, 320/1280, lector de pantalla | **NOT RUN** | Sin implementación; la UX lo declara NOT RUN |
| Probar tareas reales de import/rescan/registro/conversión/paquete | **NOT RUN** | No se ejecutó la app |
| Implementar registro, endpoint, chip o CSS | **NOT RUN** | Solo diseño |
| Medir coste de `to_thread`/callbacks en una biblioteca grande | **NOT RUN** | Requiere banco |
| **FAIL** | — | Ninguno de la ficha; no hay implementación que probar |

**No se declara aprobado** nada de §4 ni de la UX local. La ficha caduca el
**2027-01-15** o antes si cambia el pipeline de tareas, el worker único o el
sistema de diseño.

---

## 8. Resumen para el PO — 10 líneas

1. Hoy el registro ya tiene barra real en Auditoría, pero importar, rescan, convertir, paquetes, copia y descargas viven en señales dispersas.
2. Fuera de su pantalla no hay ninguna prueba de que ZascArr esté trabajando; el menú no cuenta tareas y no hay estado global.
3. La conversión y la extracción de paquetes son peticiones síncronas: el caso que más se parece a una app colgada.
4. Calibre es el patrón correcto (Jobs: N, panel no modal); Sonarr/Radarr aportan contador oculto a 0 y vacío explícito; Komga/Suwayomi, el contador global.
5. Kapowarr/Kavita/Mylar aportan fases, historial y stale; su tecnología (SignalR, Socket.IO, Qt) no se copia.
6. Recomiendo un registro en memoria (sin Redis ni tabla), un contrato JSON mínimo y un fragmento HTMX con 2 s activo / 10 s en reposo.
7. Solo tareas de fondo: progreso real o indeterminado, sin ETA inventada, sin SSE, sin cancelación global y sin «0 tareas».
8. La UX ya redactada (chip en `.side`, panel «Ahora», 400 ms, `aria-live` único) encaja; el benchmark añade el registro y los adaptadores que le faltan.
9. El coste es pequeño (sin BD en el sondeo, <20 KB de estado), pero requiere convertir/paquete a segundo plano o aceptar que sigan siendo locales.
10. Quedan decisiones de PO (ubicación, tareas globales, copia/descargas, historial, cancelación); **NOT RUN** mediciones, apps reales, navegador y capturas.

---

## 9. Decisión del PO (2026-11-17)

El PO aprueba:

- **Ubicación A**: chip global en `.side` + panel «Ahora».
- **Alcance ampliado**: además de las tareas de fondo (registro, disco, descargas), el indicador incluye **conversión CBR→CBZ** y **extracción de paquetes**.

Esto **modifica** la recomendación de §6.3 y §6.8: para que conversión y paquetes aparezcan en el chip y sobrevivan a navegar, hay que convertirlas en **tareas de fondo** (no peticiones síncronas) con el mismo registro, fases y progreso. Implica:

1. Registro de tareas con id, tipo, fase, `hechos`/`total`, estado y enlace.
2. Adaptadores para conversión individual/lote y paquete (la operación durable ya existe; falta exponerla y ejecutarla en segundo plano).
3. Fases reales: «Leyendo», «Extrayendo N de M», «Comprobando», «Importando», «Convirtiendo N de M».
4. Mantener la UI local existente mientras la tarea es de página; migrarla al registro cuando pase a segundo plano.

El coste sube respecto a la estimación inicial; requiere especificación propia antes de implementar. Los NOT RUN de esta ficha siguen vigentes.
