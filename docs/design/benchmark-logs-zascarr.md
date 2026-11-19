# Benchmark — contenido y formato de los logs de ZascArr

> **Estado:** propuesta de mejora de observabilidad. **No** cambia datos, no toca la Pi ni
> producción, no modifica la política de privacidad de #369 y **no declara aprobado** ningún
> punto. Complementa —no repite— `benchmark-SEC-LOG-369.md`, que ya cubre el saneo de
> secretos/rutas y las referencias de Sonarr/Radarr/Kapowarr/Mylar3/ComicTagger/Calibre-Web.
>
> **Fecha:** 2026-11-17. **Base contrastada:** `origin/main` `d54ecb39` y el log real
> `zascarr-logs-20261117-092321.txt` (descarga de `/ui/logs`).

## 1. Muestra real: qué se estaba guardando

El fichero adjunto tiene **18 líneas** en 3 min 31 s:

| Grupo | Líneas | Lectura |
|---|---:|---|
| `importer.duplicate` por archivo | 9 (50 %) | Inodo y formato; no identifica la fila, el grupo ni el resultado del ciclo |
| `cache_http.hit` por URL | 4 (22 %) | `url_hash` y dominio; no hay latencia ni bytes |
| Arranque y resumen de ciclo | 5 | `zascarr.starting`, `db_connected`, schedulers, `cycle_done` |
| Errores | 0 | — |

Problemas concretos:

1. **`level=info` duplicado.** La línea ya pinta `INFO` y el formateador del búfer vuelve a
   añadir `level=info` porque `registro_reciente._linea` no excluye esa clave.
2. **72 % de ruido operativo en INFO.** Un hit de caché y un duplicado por archivo son
   diagnóstico (`DEBUG`); el resumen del ciclo ya está en `cycle_done`.
3. **No hay identificador de petición/ciclo.** Ante una incidencia no se puede cruzar una
   línea de aplicación con la petición HTTP que la originó.
4. **No hay duración/resultado agregado por operación.** `importer.duplicate` repite un inodo
   sin decir «9 duplicados en 1,2 s»; `cycle_done` lo resume, pero sin duración ni id de ciclo.
5. **Timestamp sin zona explícita** en la descarga (`2026-11-17 10:17:04`) y formato distinto
   del ISO-8601 que exige cualquier colector.
6. **No es JSON.** El ajuste `LOG_JSON=true` existe pero **no tenía efecto**; el stdout y el
   fichero descargado son texto no parseable por un colector.

## 2. Referencias consultadas

Se contrastaron las aplicaciones con las que ZascArr convive o compite en el mismo dominio.
Se usa el código/configuración publicado, no solo la documentación.

| Aplicación / referencia | Versión / commit | Formato y nivel | Correlación | Rotación / retención | Saneo | Ruido / niveles por logger |
|---|---|---|---|---|---|---|
| **Sonarr** ([código](https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Common/Instrumentation/NzbDroneLogger.cs)) | `c018578e` (v4.0.20) | Texto de fichero `fecha\|nivel\|logger\|mensaje`; **CLEF/JSON opcional** en consola (`PROWLARR__LOG__CONSOLEFORMAT` en la familia) | `LoggingMiddleware` de acceso con ruta, método, estado y duración | Fichero rotado por NLog; consola | `CleanseLogMessage` global en todos los layouts | Niveles por logger y `LogLevel` configurable |
| **Radarr** ([código](https://github.com/Radarr/Radarr/tree/19edd437952373cd7bd39224c6235b61fad5672a)) | `19edd437` | Misma familia NLog/CLEF | Misma familia de middleware | NLog | Misma familia | Misma familia |
| **Prowlarr** ([código](https://github.com/Prowlarr/Prowlarr/blob/develop/src/NzbDrone.Common/Instrumentation/NzbDroneLogger.cs)) | `develop` | Texto `fecha\|nivel\|logger\|mensaje`; `ConsoleLogFormat.Clef` opcional | Logger/middleware común *arr | NLog | `Cleansing*LogLayout` | Niveles por logger |
| **Kavita** ([código](https://github.com/Kareadita/Kavita/blob/develop/Kavita.Server/Logging/LogLevelOptions.cs)) | `develop` | Serilog con plantilla `[Kavita] [timestamp correlationId threadId] [Level] SourceContext Message`; consola + fichero diario | **`CorrelationId` + `ThreadId` + `SourceContext`**; enriquece ruta/IP/user-agent | Rolling diario; fichero `config/logs/kavita.log` | No es su foco; **suprime** `/api/health`, `/hubs/messages`, `/api/image` del request log | Nivel global + overrides por logger (Microsoft/Hangfire/ASP.NET); `Debug/Information/Warning/Critical` |
| **Komga** ([config](https://github.com/gotson/komga/blob/master/komga/src/main/resources/application.yml), [docs](https://komga.org/docs/installation/configuration/)) | `master` | Logback/Spring; fichero `komga.log`; sin JSON por defecto | No se documenta correlation id en la configuración | `max-file-size: 10MB`, `max-history: 7`, `total-size-cap: 1GB`, limpieza al arrancar | No se documenta saneo propio | Niveles por paquete (`org.apache.activemq.audit`, fuentes, Spring Security) |
| **Suwayomi-Server** ([código](https://github.com/Suwayomi/Suwayomi-Server/blob/master/AndroidCompat/Config/src/main/java/xyz/nulldev/ts/config/Logging.kt)) | `master` | Logback, patrón `fecha [thread] nivel logger - mensaje`; consola + fichero | Thread, no request/correlation id | `SizeAndTimeBasedRollingPolicy` (por defecto 10 MB, 100 MB total, histórico configurable), `.gz` | No aplica | Niveles por logger (`Exposed` a ERROR) |
| **Kapowarr** | `c191ddaa` (v1.3.2) | `dictConfig`: consola + fichero rotado; `simple`/`detailed` | No | Rotación por fichero | **No**; hooks de excepción con traza completa | Nivel configurable |
| **Mylar3** | `cdc94a44` | `RotatingFileHandler`; formato clásico | No | Rotación | **No** | Nivel configurable |
| **ComicTagger** | `fa11a345` | `basicConfig`, fichero rotado | No | Rotación | **No** | Nivel por `--verbose` |
| **Calibre-Web** | `6e840acb` | Formatters de acceso/consola; `debug_no_auth` | No | Según despliegue | Solo credenciales AUTH, no rutas | Nivel DEBUG/INFO |

La tabla anterior **no dice que las aplicaciones de cómic sean el estándar**: Sonarr/Radarr y
Kavita son las que aportan piezas reutilizables; Kapowarr/Mylar3/ComicTagger/Calibre-Web son
útiles como contraste de que el logging clásico sin estructura ni saneo no basta.

## 3. Qué hacen bien las referencias

- **Kavita**: campos de correlación (`CorrelationId`, hilo, `SourceContext`), supresión de
  endpoints ruidosos y overrides por logger. Es la referencia más cercana a «poder seguir una
  petición concreta».
- **Sonarr/Radarr/Prowlarr**: un layout único y saneo en **todos** los destinos; CLEF/JSON
  opcional sin cambiar el resto del pipeline; middleware de acceso con duración.
- **Komga/Suwayomi**: rotación y límites explícitos; Suwayomi fija el ruido de una librería
  concreta a ERROR.
- **Todas**: el nivel es configurable y el fichero se rota por tamaño/tiempo. Ninguna
  recomienda escribir un log por cada archivo o cada hit de caché en INFO.

## 4. Decisión para ZascArr

| Práctica | Decisión | Motivo |
|---|---|---|
| JSON por defecto en stdout | **Adoptar** | Docker recoge stdout; un colector puede filtrar por `event`, `level`, `request_id`. `LOG_JSON=false` deja la consola legible. |
| `LOG_LEVEL` real | **Adoptar** | Hoy es un ajuste sin efecto; con `make_filtering_bound_logger` se filtra antes de renderizar. |
| `timestamp` ISO-8601 UTC | **Adoptar** | Sustituye el texto local sin zona; no cambia la hora de la máquina. |
| `event` estable + `level` una vez | **Adoptar** | Evita el `level=info` duplicado del búfer y permite agregaciones. |
| `request_id`/`method`/`path` | **Adoptar** | Middleware propio; cabecera `X-Request-ID` para cruzar con el acceso de uvicorn. |
| Duración/ciclo agregado | **Adoptar donde ya hay resumen** | `cycle_done`/`rescan.terminado` ya tienen contadores; añadir duración e id de ciclo es una mejora incremental. |
| Niveles semánticos | **Adoptar** | INFO = hitos y resumen; DEBUG = por archivo/hit; WARNING = degradación; ERROR = operación fallida. |
| Supresión de health/imágenes | **No copiar literalmente** | El acceso ya se filtra y la app no emite un log por request; no añadir un logger de acceso nuevo. |
| Rotación dentro de la app | **No añadir** | Docker ya rota `10MB × 3`; añadir fichero propio duplicaría estado y disco. |
| Saneo de secretos/rutas | **Mantener #369** | No se reimplementa; el JSON pasa por `sanear_evento` antes del renderer. |
| CLEF/JSON opcional | **Adoptar como `LOG_JSON`** | Menos dependencias que NLog; `structlog` ya está. |

### 4.1 Esquema de evento propuesto

```json
{
  "timestamp": "2026-11-17T09:17:04.123456Z",
  "level": "info",
  "event": "importer.cycle_done",
  "request_id": "a1b2c3d4e5f6",
  "method": "GET",
  "path": "/ui/auditoria",
  "escaneados": 9,
  "importados": 0,
  "duplicados": 9,
  "errores": 0,
  "duracion_ms": 1240
}
```

- `request_id`/`method`/`path` solo en peticiones HTTP.
- Los ids (`file_id`, `root_id`, `run_id`) son estables; nunca rutas/nombres.
- Las excepciones se renderizan como texto saneado; se conserva el tipo de error y la traza
  útil de la app, sin rutas de usuario.
- Un evento = una línea JSON; el búfer de `/ui/logs` sigue siendo texto legible, sin claves
  reservadas duplicadas.

## 5. Cambios de señal/ruido

| Evento | Antes | Después | Razón |
|---|---|---|---|
| `cache_http.hit` | INFO por URL | **DEBUG** | Frecuente y esperado; el resumen de ciclo ya existe |
| `cache_http.guardada`/`revalidada`/`negativa_guardada` | INFO | **DEBUG** | Telemetría de caché, no incidencia |
| `importer.duplicate` | INFO por archivo | **DEBUG** | El recuento está en `importer.cycle_done` |
| `importer.cycle_done` / `rescan.terminado` | INFO | INFO (con contadores) | Hito operativo útil |
| Errores/recuperaciones | WARNING/ERROR | Sin cambio | Deben seguir destacando |

No se elimina ningún evento: se baja el nivel de los que son diagnóstico por elemento y se
conserva el agregado.

## 6. Pruebas y límites

- **PASS (código):** JSON con `timestamp`/`level`/`event`/extras; `LOG_LEVEL` filtra;
  formato consola con `LOG_JSON=false`; `request_id` en cabecera y contexto; búfer sin
  `level=info` duplicado; #369 y `/ui/logs` siguen pasando.
- **NOT RUN:** medición de overhead del saneo/render en la Pi; rotación real de Docker;
  colector externo; lectura del fichero por una persona distinta del PO.
- **Compatibilidad:** el acceso de uvicorn no incorpora `request_id` en su línea (su
  formateador es de uvicorn); se cruza por la cabecera `X-Request-ID` y los logs de app.
- **No se toca** el nivel de `httpx`/`httpcore` (siguen WARNING) para no reabrir la fuga de
  URLs con credenciales.

## 7. Referencias y caducidad

- [`benchmark-SEC-LOG-369.md`](benchmark-SEC-LOG-369.md): saneo y política de privacidad.
- [`especificacion-SEC-LOG-369.md`](especificacion-SEC-LOG-369.md): contrato de saneo.
- [`especificacion-BL-E5-logs.md`](especificacion-BL-E5-logs.md): búfer `/ui/logs`.
- Sonarr, Radarr, Prowlarr, Kavita, Komga, Suwayomi, Kapowarr, Mylar3, ComicTagger y
  Calibre-Web, enlaces de la tabla.
- **Caducidad:** 2027-01-15, o antes si cambian `structlog`, el formato de `/ui/logs`, la
  política #369 o el pipeline de Docker.
