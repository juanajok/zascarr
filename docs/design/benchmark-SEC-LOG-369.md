# Benchmark nivel 2 — #369 SEC-LOG: registros sin rutas de biblioteca ni excepciones con datos

> Ficha de **diseño/seguridad**, insumo para la especificación. No implementa,
> no cambia el logging, no toca la Pi y **no declara aprobado** ningún punto.
> Nivel 2 ligero: es transversal a todo el código y toca una superficie de
> seguridad, aunque el cambio sea acotado.
>
> - **Fecha:** 2026-11-16
> - **`origin/main` contrastado:** `c7bf76d5` (worktree `.squad/wt-369`, rama
>   `docs/369-refinamiento`).
> - **Rol:** SCOUT.bench.
> - **Historia:** #369 `SEC-LOG`; nace del dictamen de SecOps sobre #361/PR
>   #365. #361 ya quitó la query del registro de acceso de uvicorn; esta
>   historia trata **structlog**, excepciones, trazas 5xx y el búfer
>   `/ui/logs`.
> - **Caducidad:** 2027-01-15 (~60 días), o antes si cambia el logging,
>   `registro_reciente`, el arranque o la política de #361.

---

## 1. Problema local fijado

### 1.1 Qué se escribe hoy y por dónde sale

| Salida | Qué escribe | Evidencia |
|---|---|---|
| **stdout del contenedor** | `structlog` con `PrintLoggerFactory` y la cadena por defecto de la versión instalada (contextvars, nivel, `exc_info`, timestamp, `ConsoleRenderer`). El proyecto **no define una configuración propia de formato**: `instalar_captura` reconfigura solo para insertar el capturador de `/ui/logs` | `main.py:20-25`; `utils/registro_reciente.py:107-128`; `pyproject.toml:18` (`structlog>=24.1.0`). En el entorno del worktree, `structlog.get_config()` devuelve `PrintLoggerFactory` + `ConsoleRenderer`; no es una medición de la Pi |
| **stderr de uvicorn** | Registro de acceso (`uvicorn.access`) y, en fallos, `uvicorn.error` con la traza «Exception in ASGI application» | `Dockerfile:95-98` (`--log-level info`); `main.py:423,560-561`; `utils/log_acceso.py:1-12` |
| **Docker** | Ambos flujos van al driver `json-file`, con rotación `10 MB × 3` por contenedor | `docker-compose.yml:19-24,75,110`; `SECURITY.md:196-200` |
| **Búfer `/ui/logs`** | Copia en memoria de los últimos 500 eventos / 256 KiB, descargable como texto; **también** incluye la traza de `exc_info` | `utils/registro_reciente.py:17-22,94-171`; `web/dashboard.py:33-45` |
| **Acceso HTTP** | #361 elimina la **query** de `uvicorn.access`; conserva método, ruta y estado | `utils/log_acceso.py:1-56`; `main.py:423`; `SECURITY.md:196-200` |

No hay `ProcessorFormatter`, ni filtro global de structlog, ni configuración
propia de `logging` en la app. El capturador de `/ui/logs` **no cambia el
evento para stdout**: copia, sanea secretos para el búfer y devuelve el evento
original (`registro_reciente.py:94-105`). Por tanto, cualquier ruta que llegue
al evento se escribe en stdout y, si no se sanea, también en el búfer.

### 1.2 Qué datos son «del PO» aunque no lo parezcan

- **`path.name`**: el nombre de un archivo puede contener el título de la
  serie, el número, el escaneador o el alias de una descarga; no es un simple
  «nombre técnico». El issue lo dice expresamente: el nombre de archivo es
  dato de la persona.
- **`str(exc)`**: `FileNotFoundError`, `OSError`, errores de `zipfile` o de
  `httpx` suelen incluir la ruta completa, la URL de la petición o el cuerpo.
  Un `str(exc)` no es un «tipo de error»: es texto libre del sistema/tercero.
- **Trazas `exc_info`**: el `traceback` incluye el mensaje de la excepción y
  puede incluir rutas de biblioteca; el búfer actual las formatea enteras
  (`registro_reciente._excepcion`, `:78-92`) y solo pasa `_sin_secretos`, que
  no conoce rutas.
- **URLs**: la URL del foro puede llevar `s=<sesión>`; la de una API, query o
  credenciales; la de una portada, token firmado. La query de uvicorn ya se
  elimina, pero **no** las URLs que los servicios escriben en structlog.
- **Rutas de raíz/nombre de raíz**: un nombre de raíz puede ser una ruta del
  host o un alias del disco; la ruta completa revela la estructura del PO.
- **Credenciales**: el búfer ya tiene reglas para `token`, `password`,
  `api_key`, `Authorization`, `Cookie`, userinfo y query (`registro_reciente.py:
  28-74`), pero el stdout no pasa por esas reglas y una traza puede incluir el
  texto de un error con credenciales.

### 1.3 Qué NO cubre #361 y qué NO cubre #369

**#361/PR #365** (ya en `main`) cubre **solo**:

- `uvicorn.access` y **solo la query**; no `uvicorn.error`, ni structlog, ni
  excepciones, ni el proxy.
- Instala un filtro de `logging` que falla cerrado si el formato de uvicorn
  cambia (`utils/log_acceso.py:22-56`).
- Rotación nominal de logs en Compose (`10 MB × 3`), que es disco, no RAM.
- Pruebas con uvicorn real y query centinela (`tests/test_log_acceso.py`).
- `SECURITY.md:198-200` declara expresamente fuera de alcance «los registros
  estructurados de la aplicación (`structlog`) que escriben rutas de la
  biblioteca o mensajes de excepción, y las trazas de error 5xx».

**#369** debe cubrir:

- structlog de la app (stdout y búfer `/ui/logs`);
- mensajes de excepción y `exc_info` de structlog;
- trazas 5xx de `uvicorn.error` (filtro de stdlib), si se decide;
- tests de cada punto inventariado y control negativo.

**#369 no cubre y debe decirlo:** el registro de acceso (ya #361), los logs de
PostgreSQL, Transmission, aMule o un proxy inverso, ni la rotación/limpieza de
logs ya escritos. Tampoco cambia la UI ni los contratos de datos.

### 1.4 Lo que ya está bien y no se tira

`registro_reciente._sin_secretos` ya redacta:

- credenciales en userinfo (`://usuario:clave@`), query sensibles y
  `password=`, `token=`, `Authorization`, `Bearer`, `Cookie`
  (`registro_reciente.py:28-74`);
- campos con nombre sensible (`_CLAVE_SENSIBLE`, `:32-34`) y recursión en
  dict/listas (`_sanear_campo`, `:76-88`).

El búfer ya es acotado y falla de forma segura si el `repr` de un valor revienta
(`:49-58,94-105`). La política nueva debe **conservar** esa parte y añadir
rutas, nombres, URLs y excepciones; no se reescribe el búfer desde cero.

---

## 2. Referencias consultadas

| Referencia | Versión / commit | Qué se leyó |
|---|---|---|
| **Sonarr** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` (v4.0.20.3014) | `CleanseLogMessage`, `CleansingFileTarget`, `CleansingClefLogLayout`, `CleansingConsoleLogLayout`, `NzbDroneLogger`, `LoggingMiddleware` |
| **Radarr** | `19edd437952373cd7bd39224c6235b61fad5672a` (develop; release v6.4.4.10685) | La misma familia `CleanseLogMessage`/layouts y middleware de acceso |
| **Kapowarr** | `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2) | `backend/base/logging.py`: `dictConfig`, consola+fichero rotado, hooks de excepción |
| **Mylar3** | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (v0.8.3) | `mylar/logger.py`: `RotatingFileHandler`, hooks de excepción |
| **ComicTagger** | `fa11a3456cbe5aa9f54f47bdc374ba26b2b946f3` (develop, Apache-2.0) | `comictaggerlib/log.py`: `basicConfig`, fichero rotado, sin saneo |
| **Calibre-Web** | `6e840acbda8d62fdd159bf3855c01872d629a914` (GPL-3.0) | `cps/logger.py`: formatters, `debug_no_auth`, sin saneo de rutas |
| **Propio #361/PR #365** | `docs/design/...`/PR | Filtro de acceso, rotación, límites y pruebas con uvicorn real |
| **Propio `/ui/logs`** | `utils/registro_reciente.py` | Saneo de secretos y búfer; **no** de rutas |

Enlaces: [Sonarr](https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837),
[Radarr](https://github.com/Radarr/Radarr/tree/19edd437952373cd7bd39224c6235b61fad5672a),
[Kapowarr](https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2),
[Mylar3](https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316),
[ComicTagger](https://github.com/comictagger/comictagger/tree/fa11a3456cbe5aa9f54f47bdc374ba26b2b946f3),
[Calibre-Web](https://github.com/janeczku/calibre-web/tree/6e840acbda8d62fdd159bf3855c01872d629a914).

### 2.1 Sonarr / Radarr: saneo global en el render/target, no en cada llamada

- `CleanseLogMessage` aplica una **lista de regex** al mensaje renderizado
  completo: credenciales/URLs, tokens de trackers, `/home/Users`, correos,
  IPs remotas, claves de clientes, etc.
  `src/NzbDrone.Common/Instrumentation/CleanseLogMessage.cs:16-74`.
- El saneo se instala en **todos los targets**: fichero
  (`CleansingFileTarget.cs:8-14`), consola
  (`CleansingConsoleLogLayout.cs`), CLEF/JSON
  (`CleansingClefLogLayout.cs:8-20`) y NLog (`NzbDroneLogger.cs:13-20`, layouts
  de fichero/consola con excepción incluida).
- `LoggingMiddleware` escribe método, ruta, estado y duración; el saneo global
  actúa sobre el mensaje final, incluidas las excepciones renderizadas.
- **Qué no cubre:** su regex de «Path» solo contempla `C:\Users\…` y
  `/home|Users/…` (`CleanseLogMessage.cs:~49-52`), **no** `/media/library`,
  `/mnt/...` ni un nombre de archivo cualquiera. Tampoco conoce `file_id`: si
  una ruta no cae en esos prefijos, se escribe. La idea (saneo central antes
  del render) sirve; la lista de rutas **no** se copia.
- **Radarr** replica el mismo contrato (misma familia, commit propio); no se
  encontró una diferencia de política relevante.

### 2.2 Kapowarr / Mylar3: logging estándar, sin redacción

- **Kapowarr** configura `logging.config.dictConfig` con consola y fichero
  rotado, formatters `simple`/`detailed`; no hay filtro de saneo. Los hooks
  `sys.excepthook`/`threading.excepthook` registran la excepción completa con
  `traceback.format_exception` (`backend/base/logging.py:43-115,185-210`).
  No es un contrato de redacción: la traza y el mensaje salen enteros.
- **Mylar3** usa `RotatingFileHandler` y `logger.exception` con
  `traceback.format_exception` y `logger.exception` en sus hooks; no hay
  filtro de rutas ni de credenciales (`mylar/logger.py:60-130,300-325`). Es un logging clásico, no
  una política de privacidad.
- **ComicTagger** hace `logging.basicConfig` con fichero rotado y formato de
  mensaje; no hay saneo (`comictaggerlib/log.py:5-75`).
- **Calibre-Web** define formatters de acceso y consola, y `debug_no_auth`
  recorta `send: AUTH`; no hay saneo general de rutas ni de excepciones
  (`cps/logger.py:20-80`). Su `ACCESS_FORMATTER` no sustituye a #369.
- **Conclusión:** las referencias de cómic/ebook **no** ofrecen un contrato
  reutilizable; Sonarr/Radarr sí ofrecen el patrón de saneo global, pero con
  reglas que no cubren las rutas de ZascArr.

### 2.3 Matriz de referencias (adoptar / adaptar / descartar)

| Idea de la referencia | Resultado | Motivo |
|---|---|---|
| Saneo **global** en el render/target, no en cada `logger.info` | **Adoptar/adaptar** de Sonarr/Radarr | Centraliza la política y evita que una llamada nueva se olvide; hay que adaptar las reglas a rutas de biblioteca y a `file_id` |
| Regex de `/home` y `/Users` (Sonarr) | **Descartar** como suficiente | No cubre `/media/library`, `/mnt`, `/config` ni nombres de archivo; es una lista blanca de prefijos, no una política |
| Saneo de **trazas** al renderizar excepción | **Adaptar** de Sonarr/Radarr | El layout incluye la excepción; aquí hay que conservar el tipo y quitar el mensaje/la ruta, no solo el mensaje de la línea |
| `CleansingFileTarget`/`CleansingClefLogLayout` para múltiples salidas | **Adaptar** | ZascArr tiene stdout y búfer; se puede usar un procesador structlog + filtro stdlib, sin NLog |
| Logging estándar con fichero rotado (Kapowarr/Mylar3) | **Descartar** | No redacta nada; añadiría dependencia/estado y no resuelve el problema |
| Hooks `excepthook` que vuelcan la traza completa (Kapowarr/Mylar3) | **Descartar** | Justo el anti-patrón: más superficie de fuga |
| `basicConfig` de ComicTagger/Calibre-Web | **Descartar** | Sin política de datos; `debug_no_auth` solo cubre la línea `AUTH` |
| Filtro de `uvicorn.access` de #361 | **Adoptar** como patrón | Falla cerrado, es idempotente y ya está probado con uvicorn real; se adapta a 5xx |
| Búfer `/ui/logs` con saneo de secretos | **Construir sobre lo propio** | Ya acredita secretos; solo falta rutas/nombres/URLs/excepciones; no se tira |

---

## 3. Inventario medido (no solo el issue)

**Método:** `git grep` + análisis AST sobre `src/zascarr` en `c7bf76d5`;
se contaron las llamadas `logger.<nivel>` (no comentarios ni strings). El AST
encuentra campos por nombre y valores `str(exc)`/`str(outcome)`, y separa
`logger.exception`. El `git grep` simple **no** ve llamadas multilínea; el AST
sí. Los números son de este árbol y esta fecha, no de `6f48797` (el SHA del
dictamen original).

### 3.1 Totales

| Métrica | Valor |
|---|---:|
| Llamadas a `logger` en `src/zascarr` | **297** en 64 ficheros |
| `logger.exception(...)` (traza completa) | **36** en 14 ficheros |
| Ficheros con campos `path/ruta/file/archivo/destino/origen/dir/raiz/url` | **8** |
| Ficheros con `str(exc)`/`str(outcome)` en un campo | **3**; **5** llamadas |
| Ficheros con `logger.exception` (algunos además con campos de ruta) | 14 (la traza sigue siendo el riesgo) |

### 3.2 Por servicio y riesgo

**Riesgo alto:** ruta completa, nombre de archivo visible o `str(exc)` textual.
**Riesgo medio:** traza de excepción (puede llevar mensaje con ruta),
`path.name` (nombre), URL parcial. **Bajo:** id, hash, host, código, contadores.

| Fichero | Llamadas | Hallazgos medidos | Riesgo |
|---|---:|---|---|
| `services/importer.py` | 22 | `file=path.name` (`554,783,955,1042`), `archivo=path.name` (`843,858,1016`), `destino=str(ruta)` (`1156`), `logger.exception` (`1159`) | **Alto** |
| `services/library_adopter.py` | 9 | `path=str(path)` (`1000,1057`); `logger.exception` (`619,630`) | **Alto** |
| `services/library_audit.py` | 1 | `path=str(ruta), error=str(exc)` (`238`) | **Alto** |
| `services/tagger.py` | 5 | `path=str(path)` (`496`); `logger.exception` (`843`) | **Alto/medio** |
| `utils/cbz.py` | 3 | `dir=str(path.parent)` (`99,204`); `path=str(temporal)` (`236`) | **Alto** |
| `services/blog_feed.py` | 3 | `url=url` (`180`); `raiz=nombre` (`100`) | **Alto** (URL) |
| `utils/robots.py` | 2 | `origen=origen` (`198,255`) | **Alto** (URL con path) |
| `services/exportacion_kavita.py` | 1 | `destino=str(destino)` (`406`), además `exception` | **Alto** |
| `services/discovery.py` | 3 | `error=str(outcome)` (`241`) | **Alto** |
| `web/ajustes.py` | 10 | `error=str(exc)` (`951,979,996`) | **Medio/alto** (HTTPX puede incluir URL) |
| `services/forum_scraper.py` | 8 | `motivo=str(exc)` (`591,619`); `host` y `type` en el resto; **no se reproduce la URL completa de la línea ~188 del dictamen** | **Bajo/medio** (revisar el texto del error; la URL completa no está en las llamadas actuales) |
| `main.py` | 28 | 9 `logger.exception` en ciclos (no campos de ruta); traza completa | **Medio** |
| `services/orchestrator.py`, `enricher.py`, `amule.py`, `web/errores.py`, `web/arcos.py`, `web/retirada_serie.py` | varios | `logger.exception` sin campos de ruta; la traza puede llevar datos | **Medio** |
| `utils/cache_http.py` | 9 | `url_hash` corto y `domain`; **no** URL completa | **Bajo** |
| `utils/registro_reciente.py` | — | Sanea secretos, **no** rutas; el test `test_logs_recientes.py:55` **afirma que `/media/x.cbz` aparece** en el texto | **Alto por diseño**; hay que actualizarlo |

**Nota de inventario:** el issue cita `forum_scraper` línea ≈188 con la URL
completa; en `c7bf76d5` las llamadas actuales usan `host` + `type` y
`motivo=str(exc)` de `OrigenNoPermitidoError` (un código de dominio, no la URL).
No se declara «resuelto»: hay que comprobar el texto real de cada excepción y
el test de control. Es un ejemplo de por qué el inventario se mide, no se copia.

**Inventario de `logger.exception` (36):** `main.py` (10), `enricher.py` (8),
`orchestrator.py` (5), `tagger.py`/`library_adopter.py`/`arcos.py` (2 cada uno),
`api/health.py`, `api/series.py`, `amule.py`, `exportacion_kavita.py`,
`importer.py`, `cache_http.py`, `web/errores.py`, `web/retirada_serie.py`.
La traza incluye el mensaje de la excepción; si ese mensaje lleva una ruta, se
filtra aunque no haya un campo `path` explícito.

---

## 4. Opciones de mecanismo

| Opción | Ventajas | Límites | Veredicto |
|---|---|---|---|
| **A. Sanear en cada llamada** | Local, sin magia; se ve qué se redacta | 297 llamadas y las futuras; `logger.exception` y bibliotecas externas se escapan; fácil olvidar; tests frágiles | **Descartar como único mecanismo**; útil para campos que requieren decisión local (p. ej. conservar un id) |
| **B. Procesador global de `structlog` antes del renderer** | Un solo punto para stdout y búfer; cubre eventos nuevos; puede sanear `exc_info`; bajo coste | No cubre `uvicorn.error`/stdlib; hay que ordenar procesadores (antes del capturador y del renderer); `exc_info` no es un string; `ProcessorFormatter` si se mezcla stdlib | **Adoptar/adaptar** (núcleo) |
| **C. Filtro de `logging` para `uvicorn.error`/5xx** | Cubre la traza ASGI y logs stdlib; se instala como el de #361; falla cerrado | No ve structlog; `record.msg/args/exc_info` y handlers múltiples; hay que probar la salida real | **Adoptar/adaptar** (complemento) |
| **D. `ProcessorFormatter` de structlog para todo** | Unifica stdlib y structlog en un solo renderer | Cambia el pipeline de logging de uvicorn y terceros; más complejo; riesgo de doble formato; no necesario para el alcance | **Descartar en v1** |
| **E. Solo quitar campos de ruta de las llamadas** | Simple y visible | Pierde contexto sin sustituirlo; no cubre `str(exc)`/traza; no cumple AC1 | **Descartar** |
| **F. Saneo en el búfer solamente** | Ya existe y es fácil | No cubre stdout/Docker, que es justo lo que se comparte; no cubre uvicorn | **Descartar** |
| **G. Híbrido B+C con una función común** | Cubre app y stdlib; una sola política; testeable por separado | Dos puntos de instalación; hay que probar doble saneo y orden | **Recomendado** |

**Orden de procesadores propuesto:** `merge_contextvars → … → redactar →
capturar (búfer) → ConsoleRenderer/PrintLogger`. Si `redactar` va antes de
`capturar`, el búfer ya recibe el evento saneado; si el capturador se instala
antes por compatibilidad, `capturar` debe llamar a la misma función de forma
defensiva (idempotente). El actual `instalar_captura` inserta antes del último
procesador (`registro_reciente.py:107-128`); la spec debe fijar el orden, no
dejarlo a la suerte.

**Excepciones:** un procesador de structlog recibe `exc_info` como tupla
`(tipo, valor, tb)`. Opciones: formatear y sanear el texto; conservar
`excepcion_tipo` y `excepcion_mensaje` saneado; eliminar `exc_info` crudo y
añadir una traza saneada (con función/línea de la app, sin rutas de usuario).
No basta con sanear `event` si `ConsoleRenderer` vuelve a formatear la
excepción original. La decisión de cuánto stack conservar es del PO (§7).

**5xx:** el handler de `main.py:560-561` no registra la excepción; la registra
Starlette/uvicorn en `uvicorn.error`. Un filtro en ese logger debe sanear
`record.msg`, `record.args` y `record.exc_info` **antes** de los handlers;
como uvicorn puede tener varios handlers (stderr/color), el filtro va en el
logger, no en un handler concreto. Si se instala también en el root, hay que
evitar doble saneo; la función debe ser idempotente.

**Rendimiento:** la política es regex + recorrido de un evento acotado; el
búfer ya está limitado a 500 eventos/256 KiB. No se ha medido en la Pi; un
saneo de cada evento de 297 llamadas no debería ser el cuello, pero **NOT RUN**
hasta medir. No se propone `ProcessorFormatter` ni un handler nuevo.

---

## 5. Política propuesta

> **Propuesta, no aprobada.** El criterio es: conservar lo que sirve para
> diagnosticar y no conservar lo que identifica la biblioteca o al PO.

### 5.1 Qué se conserva

- `event` (nombre estable del evento), nivel, timestamp.
- **Tipo** de excepción (`FileNotFoundError`, `PermissionError`,
  `BadZipFile`, `HTTPStatusError`), `errno`, código HTTP, `motivo` de dominio.
- **Identificadores**: `file_id`, `run_id`, `root_id`, `operacion_id`, `job_id`;
  no la ruta ni el nombre.
- **Fuente/host** (solo host, sin path/query): `source`, `host`, `dominio`,
  `url_hash` corto.
- **Contexto funcional**: `escaneados`, `importados`, `duplicados`,
  `bytes`, `segundos`, `intento`, `limite`, `estado`, `resultado`,
  `causa` de dominio. Los contadores no son datos personales.
- **Traza sanitizada**: tipo de excepción + mensaje redactado + frames de la
  app con módulo/función/línea (sin rutas de usuario). Si el PO prefiere
  menos detalle, solo tipo + mensaje.

### 5.2 Qué se redacta

| Dato | Regla propuesta |
|---|---|
| Ruta absoluta o relativa de biblioteca/descargas/config (`/media/...`, `/mnt/...`, `C:\...`) | `[ruta omitida]`; no conservar prefijo ni basename |
| `path.name` / nombre de archivo | `[archivo omitido]`; usar `file_id` si existe; si no, `[archivo sin id]` + extensión genérica |
| Nombre/ruta de raíz | `[raíz omitida]`; usar `root_id` |
| URL con path/query/fragment/userinfo | `esquema://host[/... omitido]` o solo `host`; quitar query entera (tokens, `clave`, `cursor`, `ref`, `s`, `q`) |
| Credenciales en texto | `[redactado]` (ya lo hace `_sin_secretos`; se reutiliza) |
| `str(exc)` textual | `error_tipo` + mensaje saneado; nunca el `repr` crudo |
| `exc_info`/traceback | Tipo + frames de la app sin rutas de usuario; nunca el mensaje crudo |
| IP remota / correo / datos de terceros | Mantener solo si ya son públicos y necesarios; si no, redactar; Sonarr enmascara IPs remotas |
| Contenido de un error de API/HTTP | Código/estado y tipo; no cuerpo ni URL completa |

### 5.3 Diagnóstico suficiente sin datos

El operador debe poder responder «qué falló y dónde» con:

1. nombre del evento y timestamp;
2. `file_id`/`run_id`/`operacion_id` para abrir la ficha/registro local;
3. tipo de excepción + `errno`/código HTTP;
4. `source`/host y `root_id`;
5. contadores y `motivo` de dominio.

La ruta y el nombre siguen en la base/UI local (el PO los ve ahí); **no** hacen
falta en el texto que se descarga o se comparte. Para un archivo que aún no
tiene fila, se conserva un identificador de operación / hash corto, no el
nombre.

### 5.4 Fronteras explícitas

- No se toca `uvicorn.access` (ya #361).
- No se toca el formato de la UI de error ni el detalle que ve la persona.
- No se promete limpiar logs **ya escritos** en Docker; la política aplica a
  eventos nuevos. El histórico anterior sigue donde esté.
- No se cubren Postgres, Transmission, aMule, proxy ni logs del host.
- El saneo no sustituye el control de acceso a `/ui/logs`: el búfer sigue
  siendo local y autenticado por la app, pero ahora sin rutas.

---

## 6. Diseño y pruebas (sin código)

### 6.1 Diseño propuesto

1. **Función pura `redactar_evento`** (nombre a decidir): recibe un evento
   structlog y devuelve una copia saneada. No escribe, no lanza, es
   idempotente y no depende de la BD.
2. **Procesador structlog** que la aplica antes de `capturar` y del renderer
   final. Se instala en `create_app()` o junto a `instalar_captura`, una sola
   vez; no duplica si ya está.
3. **Capturador `/ui/logs`** usa la misma función (o recibe el evento ya
   saneado); su test actual que acepta `/media/x.cbz` se cambia por el
   contrario.
4. **Filtro stdlib** para `uvicorn.error`/5xx con la misma función de
   redacción aplicada a `record.msg`, `record.args` y `record.exc_info`; falla
   cerrado como el de #361 si el formato no se reconoce. Conserva tipo y
   estado; no bloquea la respuesta.
5. **Sin `ProcessorFormatter`** en v1: no hace falta y añade riesgo de doble
   formato; si en el futuro se unifica stdlib+structlog, se evalúa aparte.
6. **`SECURITY.md`** actualiza la frase de fuera de alcance cuando la
   historia esté implementada y verificada; no antes.
7. **UI:** `/ui/logs` sigue existiendo; el texto descargado ya no lleva rutas.
   La pantalla puede avisar «registros saneados»; no se cambia el contrato de
   descarga (nombre, `text/plain`, `no-store`).

### 6.2 Pruebas exigidas

| Prueba | Qué demuestra |
|---|---|
| Procesador: evento con `path=/media/.../Serie 1.cbz`, `file=Serie 1.cbz`, `url=https://foro/x?s=SECRETO`, `error=str(FileNotFoundError("/media/..."))` | No aparece ruta, nombre, query ni `str(exc)`; sí `file_id`, tipo y evento |
| **Control negativo**: el mismo evento sin el procesador | La ruta/nombre/URL **sí** aparecen; la prueba sabe detectar la fuga |
| `exc_info` real (`FileNotFoundError("/media/.../x.cbz")`) | La traza no lleva `/media`, `x.cbz` ni mensaje crudo; sí `FileNotFoundError` y frames de app |
| Filtro `uvicorn.error` con `LogRecord`/traza ASGI 5xx | No hay ruta en `record.getMessage()` ni en `exc_text`; tipo/estado conservados; control negativo sin filtro |
| `/ui/logs` tras un evento con ruta y secreto | Ni ruta ni nombre; secreto sigue redactado; el test antiguo de `path` se actualiza a la política nueva |
| Cada uno de los puntos del inventario (§3) parametrizado | AC2: prueba por punto, no solo por servicio |
| Doble saneo | Dos pasadas no convierten `[ruta omitida]` en basura ni duplican placeholders |
| Structlog capturado + stdout (`capsys`) + handler stdlib | El pipeline no se rompe, no hay doble formato y el evento llega saneado a ambas salidas |
| Rendimiento (opcional, Pi) | 1 000/10 000 eventos no degradan el ciclo; **NOT RUN** hasta medir |

### 6.3 Riesgos del diseño

- **Doble saneo**: procesador + búfer + filtro; usar función idempotente y
  probar que el texto no se corrompe.
- **Pérdida de contexto**: si se borra la ruta sin conservar `file_id`, el
  operador no puede localizar el archivo; la política exige conservar un
  identificador.
- **`exc_info` no es string**: sanear el evento no basta; hay que sanear la
  representación de la traza y evitar que `ConsoleRenderer` reimprima la
  original.
- **Múltiples handlers**: el filtro debe ir en el logger/registro, no en un
  handler; probar `uvicorn.error` con sus handlers reales.
- **Rendimiento**: regex y formateo de trazas por evento; no medido; el
  búfer está acotado.
- **Falsa sensación de seguridad**: no cubre logs ya escritos, proxies,
  Postgres ni Transmission; debe decirlo `SECURITY.md`.
- **Compatibilidad de tests**: el test actual de `/ui/logs` afirma que la
  ruta aparece; cambiarlo es parte de la historia, no un fallo.

---

## 7. Decisiones abiertas para el PO y NOT RUN

| # | Decisión | Opciones | Recomendación provisional |
|---|---|---|---|
| 1 | ¿Qué contexto se conserva? | solo tipo/estado; tipo + `file_id`/`run_id` + host | **Tipo + id + host + contadores**; sin id no hay diagnóstico útil |
| 2 | ¿Se conserva el **nombre** de archivo? | sí; no; solo extensión | **No**; el issue lo trata como dato del PO. Usar `file_id`/hash |
| 3 | ¿Se conservan nombres de raíz? | sí; solo `root_id` | **`root_id`**, no el nombre/ruta |
| 4 | ¿Cuánta traza se conserva? | tipo + mensaje saneado; frames app; nada | **Tipo + mensaje saneado + frames de app sin rutas de usuario**; si el PO prioriza mínimo, solo tipo + mensaje |
| 5 | ¿Filtro 5xx en `uvicorn.error` o también root? | solo uvicorn; uvicorn+root; middleware | **`uvicorn.error`** y, si se comprueba que el root recibe copia, filtro en ambos con función idempotente |
| 6 | ¿`/ui/logs` siempre saneado o modo detallado local? | siempre saneado; dos botones | **Siempre saneado**; el detalle con ruta se ve en la ficha/registro de la app, no en el fichero que se comparte |
| 7 | ¿Se limpian logs viejos? | no; rotación/limpieza aparte | **No en #369**; la rotación ya existe y no borra lo ya escrito |
| 8 | ¿Proxy/Postgres/Transmission? | dentro; fuera | **Fuera**; cada uno tiene su configuración y no se controla desde la app |

### NOT RUN

| Comprobación | Estado | Motivo |
|---|---|---|
| Inventario completo con `git grep`/AST | **PASS de lectura** | 297 llamadas, 36 excepciones, 8 ficheros con campos de ruta/URL, 3 con `str(exc)`; medido en `c7bf76d5` |
| Ejecutar la app y capturar stdout/Docker reales | **NOT RUN** | Esta ficha no arranca ni despliega |
| Medir el coste de saneo en la Pi | **NOT RUN** | No hay banco de logging en esta ficha |
| Probar 5xx reales de uvicorn/Starlette | **NOT RUN** | Requiere servidor real; solo se leyó el código |
| Probar el proxy inverso, Postgres, Transmission | **NOT RUN** | Fuera de alcance declarado |
| Probar logs ya escritos en Docker | **NOT RUN** | La política no es retroactiva |
| Implementar/tests de esta historia | **NOT RUN** | Solo diseño |
| **FAIL** | — | Ninguno en la ficha; los huecos son el objeto de #369 |

**No se declara aprobado nada de §5/§6.** La ficha caduca el **2027-01-15** o
antes si cambia el pipeline de logging, `registro_reciente`, #361 o la
política de seguridad.
