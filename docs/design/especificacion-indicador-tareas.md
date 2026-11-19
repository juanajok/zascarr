# Especificación — #991 indicador global de tareas («ZascArr está pensando»)

> **Estado: DISEÑO PROPUESTO. NO IMPLEMENTADO. SIN MIGRACIÓN.** No se cambia código, plantillas,
> CSS, tests, BD ni producción; no se declara nada aprobado salvo las decisiones del PO ya
> registradas en `benchmark-indicador-tareas.md` §9 y `ui-indicador-tareas.md` §12.
> **Base:** `origin/main` **`a1802aee`** (2026-11-17), worktree `.squad/wt-tareas-impl`.
> Insumos: issue #991, `docs/design/benchmark-indicador-tareas.md` y
> `docs/design/ui-indicador-tareas.md` (base `eb454fbe`; se usan sus decisiones y copy, no sus
> números de línea de código, que se citan del SHA actual). **Sin mediciones reales** en Pi: lo no
> ejecutado va marcado **NOT RUN**.

---

## 0. Resumen y alcance

El coleccionista no tiene hoy una señal global de que ZascArr siga trabajando: el registro de la
biblioteca tiene una barra real **solo dentro de Auditoría** (`_auditoria_registro.html:43-53`),
el importador/rescan tienen estado pero no contador global (`services/comprobacion_disco.py:37-60`,
`services/rescan_biblioteca.py:44-60`) y la conversión/los paquetes son **peticiones síncronas**
(`services/conversion.py:1139-1164`, `web/series.py:1890-1899`;
`web/auditoria.py:648-657`), el peor caso de «parece colgada».

La solución se entrega **por fases**:

- **Fase 1 (visible):** registro en memoria `services/tareas.py`, `GET /api/tareas`, fragmento
  `GET /ui/_tareas` con OOB, chip en `.side` + panel «Ahora», y adaptadores para las tareas que ya
  existen: registro de biblioteca, comprobación de disco/import, rescan, descargas de Deseados y
  copia/verificación externa. Sin BD, sin Redis, sin migración, sin SSE.
- **Fase 2 (alcance ampliado por el PO):** conversión CBR→CBZ individual/lote y extracción/
  importación de paquetes **en segundo plano**, con el mismo registro y fases reales. La operación
  de paquete ya es durable (`paquete_operaciones`); la conversión no lo es como operación de lote:
  **si el PO exige que su resultado sobreviva a un reinicio, requiere una historia/migración
  aparte** (§5). Sin esa decisión, el resultado es de proceso y se puede repetir.

**No cambia** el registro de acceso de uvicorn (#361), ni las URLs/contratos HTMX, ni los bloques
locales de las pantallas de origen; no se añaden tokens, colores, iconos, JS ni dependencias.

---

## 1. Registro en memoria `services/tareas.py`

### 1.1 Modelo

Módulo nuevo, sin dependencias (stdlib), **un solo proceso** (`Dockerfile:91-99`:
`--workers 1`); no hay coordinación entre réplicas. `threading.RLock` protege el diccionario
porque algunos adaptadores actualizan desde callbacks de `asyncio.to_thread`; el registro **no
hace I/O, no consulta BD y no usa Redis**.

```text
Tarea
  id: str                  # opaco, 8 hex; nunca id de fila, ruta ni nombre
  tipo: TipoTarea          # importar | rescanear | registrar | convertir | paquete | descarga | copia
  titulo: str              # copy estática del mapa TITULOS[tipo]; nunca datos del usuario
  fase: str | None         # copy estática de fase (p. ej. «Importando», «Comprobando»)
  hechos: int | None       # None = no se sabe
  total: int | None        # None = no se sabe; si total>0, % real
  estado: EstadoTarea      # EN_CURSO | TERMINADA | ERROR | ATASCADA (ATASCADA derivada)
  iniciada: datetime
  actualizada: datetime    # heartbeat; no se toca en cada tick de UI
  enlace: str | None       # ruta interna allowlist; sin query de datos
  detalle: str | None      # copy de superficie, sin ruta/nombre/URL/str(exc)
  run_id: str | None       # id interno de ImportRun/operación durable, opcional
  visto: bool              # solo para error: se marca al abrir el panel
```

- `TipoTarea` y `EstadoTarea` son enums del dominio en `models/__init__.py` o en el propio
  `services/tareas.py` (sin tipo Postgres, sin migración). `ATASCADA` **no se escribe**: se
  deriva en `snapshot` si `estado=EN_CURSO` y `ahora - actualizada >= 10 min`; el estado interno
  sigue `EN_CURSO` y una actualización posterior vuelve a `EN_CURSO`.
- `total` solo se publica si es un total **real** conocido; nunca se calcula por tiempo ni por
  bytes. `hechos` no supera `total` cuando ambos existen.
- `titulo`, `fase`, `detalle`, `enlace` se construyen con **copy estática** y contadores; no se
  interpolan nombres de archivo, rutas, URLs, títulos de series ni mensajes de excepción
  (`CLAUDE.md` §5.4; #369). `enlace` debe empezar por una ruta interna permitida
  (`/ui/...` o `/estado`) y no llevar parámetros con datos; el registro lo valida y descarta el
  enlace si no cumple.
- `id` se genera con `secrets.token_hex(4)`; no se reutiliza ni se deriva de un id de BD.
- `run_id` es solo para que la UI enlace con el detalle durable; no sustituye al `id` de tarea y
  no se usa como ruta.

### 1.2 API del registro

```text
iniciar(tipo, *, total=None, fase=None, enlace=None, run_id=None,
        origen="manual") -> Tarea | None
actualizar(id, *, fase=None, hechos=None, total=None, detalle=None) -> None
terminar(id, *, resumen=None) -> None
error(id, *, tipo_error, fase=None) -> None
marcar_visto(id) -> None
snapshot(*, ahora=None, incluir_recientes=False) -> dict
limpiar_al_arrancar() -> None
```

- `iniciar` es el único punto de creación; si ya hay 20 activas, **no lanza** la operación de
  dominio: devuelve `None` y el adaptador sigue sin tarea (el registro nunca tumba la tarea real).
  Si el mismo adaptador ya tiene una tarea activa, reutiliza el id (no duplica).
- `actualizar` solo actúa sobre tareas `EN_CURSO`; actualiza `actualizada` y hace *coalescing*
  (máximo un cambio de estado de superficie cada 250 ms si el bucle es muy rápido; la marca de
  heartbeat puede actualizarse siempre). No hay actualización por byte.
- `terminar` fija `TERMINADA`, `actualizada` y una hora de fin; `error` fija `ERROR`,
  `tipo_error` (solo nombre de clase) y **nunca** el mensaje/traza. `marcar_visto` pone
  `visto=True` para los errores; un error visto se retira tras 8 s (o al abrir el panel y
  refrescar), nunca antes de ser visto.
- `snapshot` devuelve una **copia inmutable** de las tareas visibles y un resumen; no expone el
  objeto mutable. Las tareas que empezaron hace menos de 400 ms no se publican; si terminan antes
  del umbral, **no parpadean**. El snapshot no incluye `detalle` de usuario, solo copy estática y
  contadores.
- `limpiar_al_arrancar` se llama en `create_app()` y deja el registro vacío: **no hay
  reanudación automática**; al reiniciar el chip no miente. El estado duradero de las operaciones
  (ImportRun, paquete) se consulta en su pantalla, no en el registro.

### 1.3 Retención, límites y limpieza

| Regla | Valor | Comportamiento |
|---|---:|---|
| Tareas activas | **20** | `iniciar` devuelve `None` si se supera; la operación real sigue |
| Tareas recientes | **5** | terminadas/error vistas se conservan 8 s y luego se retiran |
| Terminada visible | **8 s** | «Listo»/«Hecho»; luego se oculta y se libera |
| Error | **hasta visto** | chip «Revisar»; al abrir el panel se marca visto y se retira tras 8 s. Tope de 5 errores no vistos; el más antiguo se descarta al superarlo (el evento sigue en logs/ImportRun) |
| Umbral de aparición | **400 ms** | tarea corta no se pinta |
| Atascada | **10 min** sin `actualizada` | `estado` derivado `ATASCADA`; chip no rojo; no se mata ni se marca error |
| Actualización | **250 ms** | coalescing de `actualizar`; no por byte ni por tick de UI |
| Proceso | **reinicio** | desaparecen todas; no hay reanudación; no hay tarea falsa |

La limpieza se hace **en `snapshot`/mutaciones** (no hay hilo de limpieza): recorre como máximo
20+5 entradas, descarta expiradas y devuelve una lista nueva. No hay fuga si nadie mira: las
mutaciones también podan.

### 1.4 Concurrencia y worker único

- Todas las operaciones (`iniciar`/`actualizar`/`terminar`/`error`/`snapshot`) toman
  `RLock`; los callbacks de `asyncio.to_thread` pueden llamar sin tocar el bucle de eventos.
- No se espera a la UI ni se hace I/O dentro del lock; el snapshot copia y sale.
- `Dockerfile:91-99` fija `--workers 1`; si algún día hay más de un worker, este registro **no se
  comparte** (no hay Redis ni tabla): habrá que replantearlo, no se promete.
- El registro no crea un scheduler: los cerrojos existentes de disco/registro/paquete siguen
  mandando. Una tarea `ocupada` se representa con un mensaje de estado, no con una tarea falsa.

---

## 2. Adaptadores de fase 1 (tareas que ya existen)

### 2.1 Criterio de qué es tarea global

**Es tarea global** si dura previsiblemente **>1 s**, tiene un estado de inicio/fin y puede
seguir viva mientras el coleccionista cambia de pantalla. **No es tarea global** una búsqueda,
una portada, una carga de página, el healthcheck, una validación de contraseña o una petición
breve: se quedan con su `htmx-indicator` local y su umbral de 400 ms
(`web.css:1540-1546`).

| Tarea | Adaptador | Total/progreso real | Enlace |
|---|---|---|---|
| Registro de biblioteca | `registro_biblioteca` alrededor de `iniciar`/`_volcar`/`_ejecutar` | `to_process` y `processed` ya existen (`registro_biblioteca.py:107-116,152-184`) | `/ui/auditoria#registro` |
| Comprobación de disco + import | `comprobacion_disco`/`Importer.scan_and_import` con callback `progreso` | `len(files)` tras listar; `hechos` por archivo (`importer.py:528-548`); fase antes/después | `/ui/no-disponibles#comprobar-disco` |
| Rescan | `rescan_biblioteca`; pasar `progreso` que ya acepta `LibraryAdopter.rescanear` | total desconocido al empezar; después `files_scanned`; nunca fingir % (`rescan_biblioteca.py:44-60,103-145`) | `/ui/auditoria#rescan-biblioteca` |
| Descargas de Deseados | adaptador desde el ciclo del orquestador/estado de `Wishlist` | `total` = deseos en `DOWNLOADING`/`DOWNLOADED`; `hechos` = completados; **sin % global**; el `%` de Transmission sigue en su bloque local (`wishlist.py:151-207`) | `/ui/wishlist#wishlist-progreso` |
| Copia/verificación externa | adaptador de `web/copias`/`ops_host` | **indeterminado** (proceso externo); sin `%`; estado leído de `ops_host` (`ops_host.py:228-290`; `web/copias.py:40-84`) | `/estado#copias` |

**Reglas de adaptador:**

- `iniciar` **antes** de crear la tarea de fondo; si `iniciar` devuelve `None` por límite, la tarea
  de dominio sigue sin indicador (no se falla la operación por el registro).
- `actualizar` en el callback de progreso con `hechos`/`total` reales; el callback no hace E/S ni
  consulta BD. Los callbacks que vienen de hilo son seguros por el lock.
- `terminar` en el `finally`/después del cierre; si el servicio distingue terminado con errores,
  la tarea global no anuncia éxito sin mirar `errores`; se usa `error` solo para fallo global.
- Una tarea `error` enlaza a la pantalla donde se puede reintentar; no se reintenta sola.
- El adaptador **no cambia** la semántica de la tarea de origen (`ImportRun`, estado de rescan,
  cerrojos, `registro_biblioteca._volcar`, bloques locales).
- Si el proceso muere, no se reanuda nada; el registro se vacía y el estado durable de la tarea
  (si existe) se consulta en su pantalla.

### 2.2 Registro de biblioteca (detalle)

`registro_biblioteca.iniciar` crea la tarea global antes de `asyncio.create_task`; `_volcar`
actualiza `total/procesados` y fase; `_ejecutar` llama `terminar` al final, `error` si el estado
es `INTERRUMPIDO`, y **no anuncia éxito** si hay `errores` (la tarea puede terminar con resumen
«con errores» y la UI muestra «Revisar»). El bloque `#registro` existente
(`_auditoria_registro.html:43-53`) se conserva; el chip es una segunda vista del mismo estado.

### 2.3 Comprobación de disco/import

`comprobacion_disco` ya tiene fases `inactivo/corriendo/terminado/error/ocupado`
(`comprobacion_disco.py:37-60,138-181`). Se añade:
- tarea global al empezar manual/automático;
- `Importer.scan_and_import(..., progreso=callback)` (nuevo parámetro opcional) que informa
  `hechos` por archivo y total tras `listar_comics` (`importer.py:528-548`);
- fase «Buscando en Descargas» antes de listar (indeterminada) y «Comprobando la biblioteca» para
  B7; al terminar, resumen de importados/errores.
- No se convierte la comprobación en una tarea de la UI local: el bloque
  `_comprobacion_disco.html:4-6` sigue igual; el chip es adicional.

### 2.4 Rescan

`LibraryAdopter.rescanear(progreso=...)` ya admite callback; `rescan_biblioteca._correr` debe
pasarlo (hoy no lo hace). Antes de `_recorrer` no hay total: la tarea es indeterminada; después
de `files_scanned` se fija el total y se actualiza por archivo. En el cierre se respeta
`no_revisado`/errores; el chip no anuncia «Listo» si el rescan quedó incompleto.

### 2.5 Descargas de Deseados

Una sola tarea por ciclo de descargas activas, no una por deseo:
`total = número de deseos en DOWNLOADING/DOWNLOADED`, `hechos = completados`, fase
«Descargando»; `detalle` solo contadores. No se consulta Transmission desde el sondeo global; el
adaptador usa el estado que el ciclo ya consulta. `%` por deseo no se replica en el chip (el
bloque local `_progreso_wishlist.html` sigue igual); aMule no aporta progreso y no se inventa.
Si no hay deseos en curso, no hay tarea (ni «0 descargas»).

### 2.6 Copia/verificación externa

`web/copias.py` registra la tarea al pedir copia; `ops_host.resolver_estado` (`ops_host.py:260-290`)
da «en marcha/sin noticias/hecha/fallo»; la tarea es **indeterminada** (sin total), se actualiza
cuando el bloque de copia consulta el estado y se termina/falla en la siguiente observación. Si
no hay noticias, se muestra «Tarda más» a los 10 min, no un `%`. No se añade un sondeo nuevo
desde el registro; el bloque de copia conserva su refresco.

### 2.7 Lo que **no** se envuelve en fase 1

Búsquedas, portadas/miniaturas, carga de página, healthcheck, validaciones, tareas de enricher/
orchestrator/upgrades (solo logs), cancelación global, ETA, historial nuevo y cada descarga
individual. **Conversión y paquetes no entran como peticiones globales**: pasan a fase 2 y solo
cuando se ejecuten en segundo plano.

---

## 3. Contrato HTTP/HTMX

### 3.1 `GET /api/tareas` (JSON versionado)

- Autenticación: la existente (cookie/Basic); no se crea auth nueva. `Cache-Control: no-store`.
- **No consulta BD, no abre sesión, no hace E/S**: solo lee el snapshot en memoria.
- Respuesta:

```json
{
  "version": 1,
  "generado": "2026-11-17T10:33:57Z",
  "resumen": {"total": 2, "en_curso": 1, "con_error": 0, "hay_tareas": true},
  "tareas": [{
    "id": "a1b2c3d4", "tipo": "registrar", "titulo": "Registrando tu biblioteca",
    "estado": "en_curso", "fase": "Mirando los tebeos",
    "hechos": 3, "total": 12, "pct": 25, "unidad": "tebeos",
    "atascada": false, "iniciada": "…", "actualizada": "…",
    "enlace": "/ui/auditoria#registro", "run_id": null,
    "detalle": "3 de 12 mirados"
  }]
}
```

- `pct` solo si `total>0`; si no, `null` (indeterminado). No hay `eta_segundos` en v1.
- `estado` ∈ `en_curso|terminada|error|atascada`; `atascada` derivada; `terminada` 8 s, `error`
  hasta visto. `detalle` sin ruta/nombre/URL/`str(exc)`.
- `version` permite detectar contrato; `generado` es informativo. `enlace` es una ruta interna
  validada; no se acepta una URL externa.
- Si no hay tareas: `hay_tareas=false`, `total=0`, `tareas=[]`; **no** se inventa «0 tareas» en UI.

### 3.2 `GET /ui/_tareas` (fragmento OOB)

- Devuelve **solo fragmentos con `hx-swap-oob`**, no una página:
  - `#tareas-lista` (filas),
  - `#tareas-contador`/`#tareas-nombre` (texto visible y nombre accesible),
  - `#tareas-anuncio` **solo** cuando cambia un estado global (empezó/terminó/error/atascada),
  - `#tareas-cadencia` (elemento oculto que reprograma el sondeo, §3.3).
- **Nunca** sustituye `<details id="tareas">` ni su `<summary>`: el panel abierto y el foco se
  conservan. No incluye `<details>` nuevo.
- Si no hay tareas, la lista va vacía y el wrapper se oculta por CSS; el panel abierto se queda
  con «No hay tareas en curso.» hasta que se cierre.
- `Cache-Control: no-store`; `Vary: Cookie` si la auth existente lo requiere.
- Añadir `/ui/_tareas` a `RUTAS_FRAGMENTO_SILENCIOSO` (`services/auth.py:136`): si la sesión
  caduca, el middleware responde **204 vacío** y no pinta el login dentro del chip
  (`auth.py:645-646`). Sin esto, el sondeo global sería un redirect disfrazado.
- `POST /ui/_tareas/visto` (mutable, auth/CSRF existentes) marca vistos los errores; lo dispara
  el `summary` con `hx-post`/`hx-trigger="click"`, sin JS. Responde 204; no toca el panel.
- Escape: los textos son copy estática; no se interpola ningún dato de usuario.

### 3.3 Sondeo 2 s activo / 10 s reposo sin JS nuevo

- Elemento oculto `#tareas-cadencia` con
  `hx-get="/ui/_tareas" hx-trigger="load, tareas from:body, every 2s" hx-swap="none"`.
- La respuesta OOB reemplaza **solo ese elemento** con `every 10s` si el snapshot está vacío, o
  con `every 2s` si hay tareas; al cambiar la cadencia no se tocan panel/summary/foco.
- Una acción de página que crea una tarea puede devolver `HX-Trigger: tareas` para que el chip
  se actualice ya, sin esperar al sondeo. Una tarea de fondo nacida sin acción se ve en **≤10 s**
  en reposo; una tarea ya activa se ve en **≤2 s**. No se promete 2 s absolutos para el nacimiento
  silencioso; el PO puede ajustar la cadencia (decisión §7).
- No SSE, WebSocket, SignalR ni worker nuevo. El sondeo no consulta BD ni ejecuta servicios.
- Varias pestañas: cada una sondea; el coste es pequeño (§6), sin estado compartido más allá del
  registro del proceso.

### 3.4 OOB y `aria-live`

- Una sola región viva en el fragmento: `<p id="tareas-anuncio" class="sr" role="status"
  aria-live="polite" aria-atomic="true">`.
- Se actualiza **solo** con cambios de estado (empezó, terminó, falló, pasó a atascada); no con
  cada `X de Y`, no con cada tick del contador, no con cada respuesta idéntica.
- El `<progress>` nativo no es una región viva; no se anuncia cada avance.
- El panel no está dentro de `aria-live`: las filas se actualizan sin anunciarse.
- El chip no es una región viva; el `summary` mantiene su nombre accesible completo.

---

## 4. UI: chip y panel «Ahora»

### 4.1 Dónde

- `base.html:16-27`: el chip va en `.side`, **fuera de** `main#main[hx-history-elt]`; añadir una
  fila `.side-cabecera` que envuelva la marca y el chip. No se añade una fila nueva si está
  oculto.
- Escritorio: chip a la derecha de la marca. Móvil ≤860 px: la `.side` ya es una fila
  (`web.css:367-373`); el chip queda junto a la marca y «Cerrar sesión»; en ≤480 px muestra solo
  el número y conserva el nombre accesible completo.
- Panel `<details>` no modal, absoluto bajo el chip en escritorio (360 px) y hoja fija por encima
  de la barra inferior en móvil (`bottom:64px`), con scroll interno. Sin backdrop ni trampa de
  foco; `Escape` no cierra `<details>` sin JS: límite aceptado y documentado.

### 4.2 Estados y copy exacto

| Estado | Chip | Panel | Anuncio |
|---|---|---|---|
| Sin tareas | **Oculto**; nunca «0 tareas» | «No hay tareas en curso.» si estaba abierto | Ninguno |
| 1 tarea | `i` «1 tarea» | Una fila, «En curso» | «ZascArr está trabajando en 1 tarea.» al empezar |
| Varias | `i` «2 tareas» | Lista; primera arriba | «…en 2 tareas.» solo al cambiar el número |
| Progreso real | Igual | `<progress>` nativo + «3 de 12» + etiqueta accesible | No se anuncia cada `X` |
| Sin total | Igual | Giro indeterminado + «Trabajando…»; **sin barra inventada** | Solo al empezar |
| Terminada | `ok` «Listo» **8 s** | «Hecho» + resumen; permanece con panel abierto | «Terminó: Registrando tu biblioteca.» una vez |
| Error | `warn` «Revisar» hasta visto | «Error» + qué hacer + «Revisar» | «No se pudo terminar: …» una vez |
| Atascada | `info`/`amber` «1 tarea»/«2 tareas»; chip no rojo | Fila `amber` «Tarda más» + «Está tardando más de lo normal. Puedes seguir usando ZascArr.» | Una vez al pasar a «Tarda más» |
| Varias, una con error | `warn` «2 tareas»; `aria-label` «2 tareas, una con error» | Error primero | «Una tarea ha fallado.» una vez |

Copy del chip: `1 tarea`, `2 tareas`, `10 tareas`, `Listo`, `Revisar`.
Panel: título **«Ahora»**, ayuda **«ZascArr sigue trabajando aunque cambies de pantalla.»**,
estados **«En curso»/«Hecho»/«Error»/«Tarda más»**, fases
**«Importando 3 de 12»/«Registrando tu biblioteca»/«Comprobando el disco»/«Descargando 2 de 3»**,
progreso **«3 de 12»** con etiquetas **«Archivos importados»/«Tebeos mirados»/«Descargas»**,
tiempo **«Empezó hace 2 min»** (o «Empezó a las 10:32»), enlaces **«Ver la tarea»/«Revisar»/
«Ver el resultado»**, terminada **«Terminó: 12 tebeos importados.»**, error **«No se pudo
terminar. Vuelve a intentarlo desde la tarea.»**, vacío **«No hay tareas en curso.»**.

Sin «job», «worker», «SSE», «polling», «proceso», «cola» ni porcentajes inventados.

### 4.3 Componente y tokens

- Reutilizar `ui.chip` (`_componentes.html:12-15`), `ui.progreso` (`:63-65`), el icono existente
  **`estado`** (activity, `web/iconos.py:78-81`; el doc UX lo llama `activity`, pero la clave real
  es `estado`), `chevron_down`, `paper-2`, `ink`, `ink-faint`, `radius-panel`, `radius-pill`,
  `shadow-ink`, `border-panel`, `border-chip`, `text-chip`, `yellow` para progreso. **No se añaden
  tokens, colores, iconos ni fuentes.**
- Chip: 44 px de alto, píldora, borde 2 px, texto `.875rem`; estado `info` en curso, `ok` Listo,
  `warn` Revisar, `amber` Tarda más. Progreso: `<progress class="progress">` nativo, 14 px,
  borde 3 px, relleno amarillo (`web.css:1408-1417`). Indeterminado: giro CSS reutilizado (patrón
  `conversion-espera`, `web.css:1979-1986`) con `prefers-reduced-motion`.
- Panel: `paper-2`, borde 3 px, `radius-panel`, `shadow-ink`, 360 px/100% móvil, scroll interno.
  Filas con enlaces de 44 px, texto ≥14 px, `overflow-wrap:anywhere`.
- Aparición 400 ms (no CSS que finja progreso); pulso suave solo con tarea en curso; sin
  animación de progreso simulada; `@media (prefers-reduced-motion: reduce)` apaga pulso/giro.

### 4.4 Accesibilidad y comportamiento

- `details`/`summary` nativos; foco en summary al abrir/cerrar; Tab entra en el panel; sin
  trampa de foco; sin JS de toggle.
- Un solo `aria-live`; el panel no es live; el `<progress>` lleva `aria-label` y no se anuncia
  por tick.
- El resumen del chip tiene `aria-labelledby` a `#tareas-nombre`; en 320 el texto visible puede
  ser `2`, pero el nombre accesible completo no se recorta.
- Al refrescar por OOB no se sustituyen summary/panel/foco; las filas terminadas permanecen con
  el panel abierto para no perder el foco.
- Error: al abrir el panel se marca visto (POST `visto`); el chip deja de reclamar atención pero
  la fila sigue visible mientras el panel esté abierto. No se autodescarta sin ver.
- 320/1280 sin scroll horizontal; 44 px; contraste de pares existentes; `forced-colors` y
  `prefers-reduced-motion` probados.

---

## 5. Fase 2: conversión y paquetes en segundo plano (decisión PO)

### 5.1 Conversión CBR→CBZ

- **Hoy:** `POST /ui/series/{id}/convertir` ejecuta `convertir_lote` en la petición
  (`web/series.py:1890-1899`; `conversion.py:1139-1164`); la página dice «No cierres esta
  página» (`_conversion_lote.html:30-35`). No hay estado de tarea ni resultado tras navegar.
- **Contrato fase 2:** la ruta valida/inicia y **devuelve sin esperar**: crea tarea global
  `convertir` (`iniciar`), lanza `asyncio.create_task` con la sesión propia y el servicio
  existente, y responde 202/fragmento con el id de tarea y enlace a la serie. La tarea actualiza
  por archivo (`hechos`/`total = len(lote.vistas)`), fases «Preparando», «Convirtiendo N de M»,
  «Comprobando»; termina con resumen; error solo con `tipo_error`.
- **Garantías conservadas:** tokens, vista previa, verificación, diario, cuarentena, original y
  deshacer no cambian (`conversion.py:1-35,407-477,700-790`). La ejecución en fondo no escribe
  nada nuevo del catálogo: usa el servicio existente. No se cancela una conversión a medias; si
  el proceso muere, el diario de conversión se reconcilia al arrancar (ya existe), pero **la
  tarea del registro se pierde**.
- **Resultado/restart:** el `ResultadoLote` es de proceso; la pantalla de la serie consulta el
  resultado/tokens existentes. Si el PO exige que el resultado del lote sobreviva a reiniciar,
  hace falta una **historia/migración de operación durable/historial**; no se inventa aquí. Con
  lo mínimo, la tarea se pierde y el usuario puede volver a convertir (idempotente por archivo).
- **Concurrencia:** una tarea de conversión por serie/lote; los tokens y locks existentes
  serializan por archivo; no se lanzan dos lotes iguales; si ya hay una tarea activa, se
  devuelve la misma/409 visible, no se duplica.

### 5.2 Paquetes RAR/ZIP

- **Hoy:** `POST /ui/auditoria/paquetes/extraer` hace `crear_operacion`, `extraer_y_verificar` y
  `publicar_e_importar` de forma síncrona (`web/auditoria.py:648-657`;
  `paquetes_extraccion.py:456`; `paquetes_publicacion.py:53`). La operación ya es durable
  (`PaqueteOperacion`, `PaqueteEstado`, `models/__init__.py:999-1008,1623-1666`).
- **Contrato fase 2:** la ruta crea/reutiliza la operación durable y lanza el trabajo en
  `asyncio.create_task` (con sesión propia); responde 202/fragmento con tarea y enlace; no
  bloquea. La tarea usa los estados reales `listando/extrayendo/verificando/publicando/
  importando` y `items` de la operación para `hechos`/`total`; fases «Leyendo», «Extrayendo N de
  M», «Comprobando», «Importando». La UI de resultado lee la **operación durable**, no el
  registro efímero.
- **Original/undo:** no se borra/mueve el paquete; no se altera la cuarentena; el paquete ya
  tiene su contrato #344. Si el proceso muere, `limpiar_huerfanos` deja la operación recuperable
  y la tarea desaparece; al volver, la pantalla puede mostrar el estado durable y reintentar. No
  se duplica la extracción (clave/estado durable).
- **Concurrencia:** una operación por paquete; el estado durable y los locks existentes evitan
  dos extracciones; el registro no crea scheduler.

### 5.3 Requisitos de otra historia/migración

- **No** se requiere migración para el registro en memoria ni para la operación de paquete.
- **Sí** se requiere historia/migración si el PO quiere **resultado durable de la conversión**
  (más allá del proceso) o un **historial de tareas**; la conversión actual no tiene una tabla de
  operación de lote, y el registro en memoria no sobrevive a un reinicio. Se marca como
  **fuera de esta entrega** hasta decisión.
- Las fases 2A/2B pueden entregarse por separado; paquete antes que conversión porque su estado
  durable ya existe.

---

## 6. Seguridad, privacidad y rendimiento

### 6.1 Privacidad

- Títulos/fases/detalles son copy estática y contadores; **nunca** rutas, nombres de archivo,
  títulos de series, URLs, `str(exc)` ni credenciales (`CLAUDE.md:139-140`; #369).
- `error` solo `tipo_error` (nombre de clase); enlace interno allowlist; `id` opaco; `run_id`
  interno no se usa como dato de superficie.
- El snapshot no expone objetos mutables; los adaptadores no vuelcan el estado completo de un
  servicio con datos.
- No se toca `uvicorn.access` (#361); no se añaden logs con datos de tarea; no se modifica el
  búfer de logs.
- No se añade auth nueva; el JSON y el fragmento usan la auth existente; el fragmento se une a
  `RUTAS_FRAGMENTO_SILENCIOSO`.

### 6.2 No bloquear

- `snapshot` y render del fragmento son puros, en memoria, sin BD/FS/red.
- Los adaptadores actualizan en callbacks baratos; `Importer`/`LibraryAdopter` siguen usando
  `asyncio.to_thread` para E/S (`CLAUDE.md` §4).
- Conversión/paquete en fase 2 usan tareas de fondo con sesión propia; la petición no espera;
  ninguna tarea bloquea el bucle con zipfile/unar/shutil síncronos: los servicios existentes
  usan `to_thread`/subproceso.
- Un fallo del registro nunca tumba la operación de dominio (se captura y se sigue).

### 6.3 Presupuesto en la Pi (propuesto; **NOT RUN**)

- Estado: <20 KB para 20 tareas; respuesta JSON <2 KB; fragmento <4 KB.
- Peticiones: 6/min en reposo (10 s), 30/min con tareas (2 s), <12 KB/min por pestaña; 3
  pestañas <36 KB/min; sin consultas SQL.
- Objetivos de aceptación: `GET /api/tareas` p95 <20 ms y `GET /ui/_tareas` p95 <10 ms en el
  equipo de desarrollo, con 0/1/10 tareas; RSS adicional <1 MB; **medición en Pi NOT RUN**.
- Nada de SSE/WebSocket/worker/Redis/tabla; una tarea de fondo no crea un segundo proceso.

---

## 7. Pruebas

### 7.1 Registro (unitarias)

- Crear/actualizar/terminar/error; snapshot inmutable; `pct` solo con total; `atascada` a 10 min
  con reloj falso y vuelta a `en_curso` al actualizar.
- Retención 8 s; 400 ms; error hasta visto; tope 20 activas/5 recientes; error no visto se
  conserva; limpieza sin hilo; no crece.
- Concurrencia: N hilos/`asyncio.to_thread` actualizan mientras se toma snapshot; no corrupción,
  no deadlock; lock corto.
- Copy: no acepta ruta/nombre/URL/`str(exc)` en `detalle`; enlace inválido se descarta; ids
  opacos; no se expone el objeto mutable.
- Reinicio: `limpiar_al_arrancar` deja 0 tareas; no reanuda.
- Límite: 21.ª tarea devuelve `None` sin tumbar el servicio.

### 7.2 Adaptadores y contrato

- Registro: total/procesados reales, termina en éxito/error; no anuncia éxito con errores.
- Import/comprobación: `progreso` por archivo, total tras listar; fases; no actualiza por byte;
  no bloquea; la UI local no cambia.
- Rescan: callback pasado, indeterminado antes del total, avance después; incompleto no es
  «Listo».
- Descargas: total de DOWNLOADING/DOWNLOADED, sin `%` global, sin consultar Transmission en el
  sondeo; 0 deseos no crea tarea.
- Copia: indeterminada, stale a 10 min, fallo con tipo, sin `%`.
- Control negativo: una búsqueda/portada/petición breve no crea tarea; sin registro el chip no
  aparece.
- JSON: `version=1`, claves/tipos, `pct` nulo/real, `hay_tareas=false`, `no-store`, auth.
- Fragmento: OOB no incluye `<details>`/`<summary>`, panel abierto/foco conservado, cadencia
  2/10, lista vacía, un solo `aria-live`, error visto por POST.
- Auth: `/ui/_tareas` en `RUTAS_FRAGMENTO_SILENCIOSO`; sesión caducada → 204; no redirect.
- UI: 0/1/N, 400 ms, 8 s, error, atascada, 320/1280, claro/oscuro, `prefers-reduced-motion`;
  contraste/`test_web_css_contraste`; navegador real (Playwright/arnés), no solo HTML.
- No regresión: bloques de Auditoría/No disponibles/Deseados/Copias, `/ui/_nav/estado`,
  `test_logs_recientes`, contratos HTMX y tests existentes.

### 7.3 Fase 2

- Conversión: la ruta responde sin esperar; tarea avanza por lote; navegar no la cancela; error
  deja tarea en `error`; resultado en la pantalla de serie; reinicio pierde tarea y no deja
  conversión a medias (diario reconcilia); no duplica lote; original/undo intactos.
- Paquete: ruta responde 202; tarea sigue estados durables; resultado lee `PaqueteOperacion`;
  reinicio no duplica y `limpiar_huerfanos` deja la operación recuperable; original intacto.
- Sin migración en fase 2 si se mantiene el resultado de conversión en proceso; si el PO exige
  durabilidad, se marca como bloqueo/historia aparte.

### 7.4 PASS / FAIL / NOT RUN

- **PASS:** lectura del issue, benchmark, UI, docs y código de `a1802aee`; contrato, fases,
  pruebas y presupuesto definidos.
- **FAIL:** ninguno de la especificación; un fallo real solo aparece al implementar/probar.
- **NOT RUN:** implementación; Pi; navegador real 320/1280; lector de pantalla; tareas reales;
  conversión/paquete en fondo; reinicio; p95/RSS; SSE descartado. Las cifras de rendimiento son
  un presupuesto, no una medición.

---

## 8. EARS y criterios de aceptación

### 8.1 EARS

- **Cuando** una tarea de fondo lleva >400 ms, **el sistema** la publica en el chip con su tipo,
  estado, fase y progreso real si lo hay; si termina antes, no aparece ni parpadea.
- **Cuando** hay 0/1/N tareas, **el sistema** oculta el chip a 0, muestra «1 tarea»/«N tareas» y
  nunca «0 tareas»; el panel dice «No hay tareas en curso» si está abierto.
- **Cuando** `total>0`, **el sistema** muestra `<progress>` con `hechos/total`; cuando no hay
  total, **el sistema** muestra giro indeterminado y «Trabajando…», nunca un porcentaje inventado.
- **Cuando** una tarea termina, **el sistema** muestra «Listo»/«Hecho» 8 s; **cuando** falla,
  **el sistema** muestra «Revisar»/«Error» hasta que el panel se abre y se marca visto; **cuando**
  no avanza 10 min, **el sistema** muestra «Tarda más» sin matar ni marcar error.
- **Cuando** se navega con HTMX, **el sistema** conserva chip/panel/foco porque el fragmento solo
  actualiza OOB y nunca sustituye `<details>`/`<summary>`.
- **Cuando** la sesión caduca, **el sistema** responde 204 al fragmento y no pinta login; **cuando**
  no hay tareas, no se pinta «0».
- **Cuando** una tarea real (registro, disco/import, rescan, descargas, copia) avanza, **el
  sistema** actualiza el registro con el total real o indeterminado, sin fingir; la UI local no se
  degrada.
- **Cuando** se ejecuta una conversión/lote o un paquete en fase 2, **el sistema** responde sin
  bloquear, registra fases reales y mantiene las garantías de original/undo/operación durable.
- **Cuando** el registro no está disponible/lleno/falla, **el sistema** no tumba la operación de
  dominio; no hay tarea falsa.
- **Cuando** el operador descarga `/ui/logs` o consulta stdout, no ve rutas/nombres/URLs nuevas
  por estas tareas; no se toca `uvicorn.access`.

### 8.2 AC

- AC1 chip/panel visible en cualquier pantalla; no parpadeo <400 ms; 0/1/N.
- AC2 progreso real/indeterminado; fase y tiempo.
- AC3 «Listo» 8 s, «Revisar» error, «Tarda más» 10 min; no se autodescarta error sin ver.
- AC4 navegación HTMX y panel/foco conservados; OOB; un solo `aria-live`.
- AC5 fase 1 adapta registro/disco/rescan/descargas/copia con datos reales; no búsquedas.
- AC6 fase 2 conversión/paquete en fondo, sin bloquear; resultado/garantías.
- AC7 privacidad: copy sin datos; ids/tipos; enlace interno; no errors crudos.
- AC8 accesibilidad/320/1280/contraste/reduced motion; tokens existentes.
- AC9 rendimiento sin BD/Redis/tabla; p95/RSS/req/min presupuestados; Pi NOT RUN.
- AC10 sin regresión en tareas existentes, UI local, `/ui/_nav/estado`, #361.

---

## 9. Cortes, estimación y decisiones abiertas

### 9.1 Cortes

| Corte | Contenido | Cierra | Esfuerzo |
|---|---|---|---|
| **C1 · Registro + chip/panel + contrato** | `services/tareas.py`, `GET /api/tareas`, `/ui/_tareas`, auth silencioso, chip/panel, OOB, 400 ms/8 s/10 min, copy, tests unitarios/a11y; adaptador de registro de biblioteca | Fase 1 visible (con una tarea real) | **M** |
| **C2 · Adaptadores de fondo** | Disco/import, rescan, descargas, copia; callbacks reales; UI local intacta; tests de no regresión | Fase 1 completa | **M/L** |
| **C3 · Conversión y paquete en fondo** | Rutas 202/resultado, tareas, fases, paquete durable, conversión en proceso, reinicio/garantías; pruebas | Fase 2 | **L** |

- Dependencias: C1 → C2/C3; C3 puede separarse en paquete (sin migración) y conversión (resultado
  durable requiere historia/migración aparte).
- **Estimación total: L no calibrada**; no hay migración en C1/C2/C3 mínimo. No se promete fecha.

### 9.2 Decisiones abiertas para el PO

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 1 | **Reinicio** | perder chip; reanudar; recuperar estado | **Perder tareas** (no hay persistencia); el paquete conserva su operación durable; la conversión se puede repetir. Resultado de conversión durable = historia/migración aparte |
| 2 | **Sondeo** | 2 s/10 s; 3 s; solo 10 s | **2 s activo/10 s reposo** (issue); una tarea de fondo nueva se ve ≤10 s, una activa ≤2 s; acción de página puede forzar OOB |
| 3 | **Cancelación** | global; por tarea; no | **No v1**: no todas las tareas saben deshacer; enlace a su pantalla |
| 4 | **Historial** | panel; página; enlaces | **Sin página nueva**: `ImportRun`/operaciones y enlaces a las pantallas; no duplicar tabla |
| 5 | **Error visto** | auto; al abrir panel; nunca | **Al abrir el panel** (POST `visto`); no autodescartar |
| 6 | **Tareas globales** | solo fondo; + conversión/paquete; + enricher | **Fase 1: fondo; Fase 2: conversión/paquete** (decisión ya ampliada); enricher fuera |
| 7 | **Conversión durable** | proceso; tabla/historial | **Proceso en esta entrega**; si el resultado debe sobrevivir, historia/migración aparte |
| 8 | **Frecuencia en reposo** | 10; 30 | **10 s**; 30 s solo si el PO prioriza menos ruido y acepta latencia |

---

## 10. Referencias y trazabilidad

- Issue #991; decisión PO en `benchmark-indicador-tareas.md:732-746` y
  `ui-indicador-tareas.md:668-673`; copy/estados en `ui-indicador-tareas.md:123-186,597-622`.
- Código actual `a1802aee`: `base.html:16-27`; `_componentes.html:12-15,63-65`;
  `web.css:287,367-373,575,1358-1372,1408-1417,1540-1546,1979-1986`;
  `services/auth.py:136,645-646`; `Dockerfile:91-99`;
  `services/registro_biblioteca.py:107-116,152-184`;
  `services/comprobacion_disco.py:37-60,138-181`;
  `services/rescan_biblioteca.py:44-60,103-145`; `services/importer.py:528-548`;
  `web/wishlist.py:151-207`; `_progreso_wishlist.html:1-17`;
  `services/ops_host.py:228-290`; `web/copias.py:40-84`;
  `services/conversion.py:1139-1164`; `web/series.py:1890-1899`;
  `_conversion_lote.html:30-35`; `web/auditoria.py:648-657`;
  `services/paquetes_extraccion.py:456`; `services/paquetes_publicacion.py:53`;
  `models/__init__.py:999-1008,1623-1666`.
- Bloques locales existentes: `_auditoria_registro.html:43-53`,
  `_comprobacion_disco.html:4-6`, `_rescan_biblioteca.html:4-6`,
  `wishlist.html:37-39`.
- **No se ha implementado nada**; el registro, endpoints, fragmento, chip y adaptadores son
  propuesta. **NOT RUN** mediciones en Pi, navegador real, lector de pantalla, tareas reales y
  fase 2.

*Fin. Diseño propuesto; sin código, sin migración, sin despliegue.*
