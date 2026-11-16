# Especificación — SEC-LOG (#369): registros sin rutas, nombres de archivo ni excepciones con datos

> **Estado: DISEÑO PROPUESTO. NO IMPLEMENTADO. SIN MIGRACIÓN.** Este documento no cambia código,
> no reescribe logs reales, no toca la Pi ni producción. La ficha de benchmark paralela
> `benchmark-SEC-LOG-369.md` **no existe en este SHA**; se cita cuando se incorpore y esta spec no
> duplica sus tablas.
> **Base:** `origin/main` `c7bf76d5` (2026-11-16), worktree `.squad/wt-369`, rama
> `docs/369-refinamiento`. Insumos: #369, #361/PR #365 (ya fusionada), `CLAUDE.md` §5.4,
> `utils/registro_reciente.py`, `main.py`, `utils/log_acceso.py` y el inventario de llamadas de §2.

---

## 0. Resumen

Hoy la app escribe con `structlog` a stdout y guarda una copia saneada **solo de credenciales y
queries** en `/ui/logs` (`registro_reciente.py:8-10,31-67,94-106`). Varias llamadas siguen
llevando **rutas, nombres de archivo o `str(exc)` con esos datos** (inventario §2), y las trazas
5xx de `uvicorn.error` pueden incluir una ruta en el mensaje de la excepción. #369 añade:

1. un **procesador structlog global** que sanea el evento antes del renderer (y antes del búfer);
2. un **filtro `logging.Filter`** para `uvicorn.error`/stdlib que sanea `msg`, `args` y
   `exc_text`;
3. una **política única** de campos permitidos/prohibidos y redacción `[ruta]`, `[archivo]`,
   `[url]`;
4. el inventario y los cambios de campo en cada llamada que no se puede resolver solo con el
   procesador.

**No cambia** la UI de diagnóstico (`report.errors` puede seguir mostrando la ruta al
coleccionista), las URLs, los contratos HTMX ni el registro de acceso (#361). El texto visible de
aviso de `/ui/logs` debe dejar de decir que puede contener rutas (es falso tras #369); es el único
cambio de texto, no de contrato.

**Estimación propuesta: M** (dos cortes, §7), no calibrada.

---

## 1. Alcance exacto

### 1.1 Entra

- **structlog de la aplicación:** eventos emitidos por `zascarr.*` (`structlog.get_logger()`),
  incluido `logger.exception`/`exc_info`, mensajes `event`, campos, listas/dicts anidados y
  traceback formateado.
- **Trazas 5xx de uvicorn:** el registro de `uvicorn.error` («Exception in ASGI application»),
  con `msg`, `args`, `exc_info`/`exc_text`.
- **Registros stdlib** que puedan contener datos (hoy solo `utils/cortesia.py:86,559` es stdlib;
  además del filtro de uvicorn, se cubre el caso general sin reemplazar handlers).
- **Inventario y decisiones por punto** (§2).
- **Búfer `/ui/logs`:** debe recibir el evento ya saneado, incluido el traceback; no puede quedar
  una segunda copia sin sanear.
- **Pruebas** por punto con captura de structlog, control negativo, filtro 5xx y no regresión de
  UI.

### 1.2 No entra

| Fuera | Por qué |
|---|---|
| **Registro de acceso de uvicorn (`uvicorn.access`)** | Es #361/PR #365, ya fusionado: quita la query con `SinQueryEnAcceso` (`utils/log_acceso.py:32-56`). #369 no lo modifica ni lo acredita |
| **Logs de PostgreSQL, Transmission, aMule, proxy inverso, Docker** | No son de la app; #369 declara NOT RUN y no promete sanearlos |
| **Cambiar URLs, enlaces guardados, contratos HTMX o respuestas** | Sin efecto en la petición; solo se cambia lo que se escribe al registro |
| **Cambiar los mensajes de pantalla** | `report.errors`/UI pueden seguir mostrando ruta y nombre para diagnóstico; no se degradan (AC4) |
| **Rediseñar `/ui/logs` o su descarga** | Se conserva el contrato; solo se sanea el contenido y se corrige el aviso de privacidad |
| **Migración/tabla** | No hay datos nuevos; es código de logging |
| **Rotación de logs** | Ya hecha en #361 (`docker-compose.yml`); no se toca |
| **Onboarding de nuevos logs** | La política permite añadir eventos con campos permitidos; no se inventan campos |

**Frontera con #361:** #361 se limita a `uvicorn.access`; su PR declara fuera de alcance
structlog, excepciones y 5xx (`PR #365`, cuerpo). #369 empieza exactamente ahí.

---

## 2. Inventario medido y decisión por punto

### 2.1 Método

- `git grep` sobre `src/zascarr` en `c7bf76d5`: **297** líneas con `logger.` (structlog y stdlib).
- Candidatos por valor sensible: **25** llamadas con `path=`, `ruta=`, `file=`, `archivo=`,
  `dir=`, `destino=`, `url=`, `origen=`, `error=str(...)`, `motivo=str(...)` o `nombre=`;
  más `tagger.lote_abortado` (`motivo=r.motivo`) y los campos multilínea de `forum`, que la
  búsqueda simple no ve. **36** llamadas con `logger.exception` (traza automática).
- Se leyó el contexto de cada candidato; el resto son `error=type(exc).__name__`, IDs, hosts,
  códigos o contadores y **no cambian** (lista de «ya seguros» al final).

### 2.2 Puntos que requieren cambio directo (campo → id/tipo/eliminar)

| # | Ubicación actual | Qué se escribe hoy | Decisión |
|---|---|---|---|
| 1 | `services/importer.py:554` | `importer.file_failed`, `file=path.name`, `error=type` | **Eliminar `file`**; conservar `error_tipo`; añadir `formato=path.suffix.lstrip(".") or "sin_extension"` (tipo, no nombre) |
| 2 | `services/importer.py:843` | `archivo=path.name`, `causa=causa` (el mensaje ya lleva `path.name`), `raiz=exc.raiz` | **Eliminar `archivo` y `causa`**; conservar `raiz` (nombre de raíz) y añadir `motivo=type(exc).__name__`/`formato` |
| 3 | `services/importer.py:858` | `archivo=path.name`, `raiz=raiz.name` | **Eliminar `archivo`**; conservar `raiz` y añadir `formato` |
| 4 | `services/importer.py:955` | `file=path.name`, `root=raiz.name`, `relative=str(final_dest.relative_to(...))` | **Eliminar `file` y `relative`**; usar `file_id` de la fila ya creada, `root`, `status`, `formato` |
| 5 | `services/importer.py:1016` | `archivo=path.name`, `causa=causa`, `raiz` | Igual que #2: eliminar `archivo`/`causa`; `raiz`, `motivo`/`formato` |
| 6 | `services/importer.py:1042` | `file=path.name`, `root=raiz.name`, `relative=...` | **Eliminar `file`/`relative`**; `file_id` (la fila existe), `root`, `formato` |
| 7 | `services/importer.py:1156` | `destino=str(ruta)` | **Eliminar `destino`**; conservar `file_id` y `resultado` |
| 8 | `services/library_adopter.py:1000` | `path=str(path)` | **Cambiar a `file_id=outcome.recuperar.id`** (la fila existe); sin ruta |
| 9 | `services/library_adopter.py:1057` | `path=str(path)` | **Cambiar a `file_id=file_rec.id`**; `status` |
| 10 | `services/library_audit.py:238` | `path=str(ruta)`, `error=str(exc)` | **Eliminar `path`; `error_tipo=type(exc).__name__`**; añadir `formato` (extensión) |
| 11 | `services/tagger.py:496` | `path=str(path)` | **Eliminar `path`** (ya hay `file_id`); conservar `file_id` |
| 12 | `services/tagger.py:875` | `motivo=r.motivo` (viene de `str(exc)` en `:845`) | **Cambiar a `motivo_tipo=type(exc).__name__`** o eliminar; el informe de UI conserva el mensaje |
| 13 | `utils/cbz.py:99` | `dir=str(path.parent)` | **Eliminar `dir`**; dejar el evento `cbz.limpieza_temporales_fallida` y, si hace falta, `fase`/`operacion` |
| 14 | `utils/cbz.py:204` | `dir=str(path.parent)` | **Eliminar `dir`**; `cbz.fsync_dir_fallido` + código |
| 15 | `utils/cbz.py:236` | `path=str(temporal)` | **Eliminar `path`**; `cbz.temporal_no_borrado` + `fase` |
| 16 | `services/blog_feed.py:180` | `url=url` | **Cambiar a `host=host_para_log(url)`**; no URL completa |
| 17 | `services/discovery.py:241` | `error=str(outcome)` | **Cambiar a `error_tipo=type(outcome).__name__`**; `source` se queda |
| 18 | `services/exportacion_kavita.py:406` | `destino=str(destino)` + `logger.exception` | **Eliminar `destino`**; conservar `file_id`/`modo`; el traceback lo sanea el procesador |
| 19 | `web/ajustes.py:951` | `error=str(exc)` | **Cambiar a `error_tipo=type(exc).__name__`**; el mensaje de pantalla no cambia |
| 20 | `web/ajustes.py:979` | `error=str(exc)` | Ídem |
| 21 | `web/ajustes.py:996` | `error=str(exc)` | Ídem |
| 22 | `utils/robots.py:198` | `origen=origen` (URL de origen con esquema/host) | **Cambiar a `host=...`** (solo host); no URL |
| 23 | `utils/robots.py:255` | `origen=origen` | **Cambiar a `host=...`** |
| 24 | `services/forum_scraper.py:609` | `motivo=str(exc)` (`OrigenNoPermitidoError` ya es un **código**, sin URL) | **Sin cambio de valor**; conservar el código; añadir prueba que demuestre que no lleva URL |
| 25 | `services/forum_scraper.py:591` | `motivo=str(exc)` (código) | **Sin cambio**; ya es código |
| 26 | `services/forum_scraper.py:619` | `motivo=str(exc)` (código) | **Sin cambio**; ya es código |
| 27 | `utils/cover.py:344` | `motivo=str(exc)` (`UrlNoPermitidaError` es **código**) | **Sin cambio**; ya es código; `host` se queda |
| 28 | `utils/registro_reciente.py:94-106` | Copia el evento y solo redacta credenciales/queries | **Aplicar el saneador compartido** antes de guardar; también al formatear `_linea`/`_excepcion` para que un buffer antiguo o una llamada directa no deje ruta |
| 29 | `web/templates/dashboard.html:44` | Aviso «Pueden incluir rutas de tu biblioteca» | **Actualizar el texto** a «Las rutas y nombres de tus archivos se ocultan; contraseñas y tokens también» (no cambia la descarga) |

> Los puntos 24-27 se incluyen porque el issue los citaba como hallazgos o candidatos: en el
> código actual su excepción ya es un **código corto** (`OrigenNoPermitidoError`/`UrlNoPermitidaError`
> documentan «el mensaje es un CÓDIGO, sin la URL», `forum_scraper.py:166-167`,
> `url_portada.py:86-87`); se acredita con prueba y **no se cambia** el valor. No se declara
> cerrado el hallazgo original sin leer el código actual.

### 2.3 Trazas de excepción (36 llamadas)

Estas llamadas **no necesitan cambiar sus campos** (ya usan IDs, tipos o eventos genéricos), pero
su `exc_info` puede contener una ruta en el mensaje de la excepción. Las cubre el procesador global
(§3.1) y, para uvicorn, el filtro (§3.2). Inventario de `logger.exception` en `c7bf76d5`:

- `main.py:88,125,166,198,233,276,335,348,361`;
- `api/health.py:292`, `api/series.py:308`;
- `services/tagger.py:843`, `services/amule.py:110`;
- `services/enricher.py:579,609,639,749,996,1088,1185,1208`;
- `services/exportacion_kavita.py:406` (además corrige `destino`, #18);
- `services/importer.py:1159` (ya tiene `file_id`);
- `services/library_adopter.py:619,630`;
- `services/orchestrator.py:274,427,456,741,781`;
- `utils/cache_http.py:556`, `web/errores.py:75`, `web/retirada_serie.py:170`,
  `web/arcos.py:343,372,410`.

**Decisión:** no se toca cada llamada; se sanea la traza en el procesador. Si alguna excepción
tiene un mensaje con ruta de la biblioteca, el resultado conserva **tipo de excepción, código de
evento y traza de código de la app**, y sustituye las rutas de datos por `[ruta]`/`[archivo]`.

### 2.4 Llamadas ya seguras (no cambian)

- `importer.py:565` (`error=type`), `:719` (`error=type`), `:441` (`fila`/id);
- `library_adopter.py:433,444,596,804,872` (`error=type`), `:619,630` (excepción, §2.3);
- `tagger.py:523` (`file_id`, estado), `:843` (excepción, §2.3);
- `forum_scraper.py:285` (`host`), `:478` (`host`), `:598` (`error=type`), `:608` (`host`),
  `:624` (`host` + tipo);
- `tebeosfera.py:360` (`host` + `motivo` enum), `:364` contador;
- `cover.py:347,354` (`host`), `:113` (`motivo=type`); `series.py:340` (`motivo` enum);
- `cortesia.py:559` (fuente + tope; stdlib, sin ruta);
- `cache_http.py` (`url_hash`/`domain`/código), `asignacion.py:699` (`operacion`, `error=type`),
  `paquetes_extraccion.py:140` (`error="limpieza"`);
- `discovery`/`fandom`/`tebeosfera` con títulos/slugs externos: **no son rutas ni nombres de
  archivo de la persona**; quedan fuera de la política de #369 (no se afirma que no sean datos
  de terceros; no se amplía el alcance).

---

## 3. Política única y mecanismo

### 3.1 Política de campos y redacción

**Campos permitidos** (sin sanear salvo que su valor contenga un patrón sensible):

| Campo | Ejemplo | Regla |
|---|---|---|
| `event` / `log_level` / `timestamp` | `importer.imported`, `error` | Código estable; no mensajes con datos |
| `file_id`, `issue_id`, `series_id`, `operacion`, `op_id`, `id` | UUID/texto | Identificador; nunca ruta ni nombre |
| `root`/`raiz` | `Manga` | **Nombre** de raíz, no `path` |
| `host` | `example.com` | Sin esquema, path ni query |
| `codigo`, `status`, `estado`, `motivo` | `404`, `sin_espacio`, enum | Código de dominio, no texto libre |
| `error_tipo`/`tipo_excepcion` | `FileNotFoundError` | Solo el tipo |
| `formato`, `extension` | `cbz` | Tipo, no nombre |
| contadores, duración, bytes, `modo` | `3`, `1.2`, `cbz` | Sin datos personales |

**Prohibido en valores** (se redacta siempre):

- ruta completa de la biblioteca, descargas, raíces, temporales, cuarentena, exportación,
  `.zascarr`, o una ruta absoluta con extensión de cómic (`.cbz/.cbr/.cb7/.pdf/.epub`) aunque
  quede fuera de una raíz conocida;
- nombre de archivo suelto (`foo.cbz`, `foo.cbr`) o ruta relativa que lo contenga;
- URL con path/query/fragmento (`https://host/ruta?token=…`), URL con credenciales
  (`https://user:pass@host/…`);
- credenciales/secretos: `password`, `passwd`, `contraseña`, `secret`, `token`, `api_key`,
  `authorization`, `cookie`, `bearer`, `session`, `s=`.

**Formato de redacción** (idempotente, sin datos alrededor):

| Patrón | Resultado |
|---|---|
| ruta absoluta/relativa de biblioteca/descargas/raíz/temporal | `[ruta]` |
| nombre de archivo o ruta relativa con extensión de cómic | `[archivo]` |
| URL | `https://host/[url]` (se conserva **solo esquema + host**; sin puerto si no es necesario para diagnosticar, sin path/query) |
| credencial/query secreta | `[credencial]` |
| traceback con ruta de datos | se conserva `File "<código de la app>"` si es código de la app; ruta de datos → `[ruta]`/`[archivo]` |

- Las **rutas del código de la app** (`/app/src/zascarr/...`) en el traceback son diagnóstico y
  no datos del coleccionista; se conservan. Las rutas de la biblioteca/descargas/raíces y las
  absolutas con extensión de cómic se redactan.
- La redacción **no cambia el tipo ni el código del evento**; el operador sigue viendo
  `error_tipo=FileNotFoundError`, `file_id`, `root`, `host`, `estado`.
- Si el saneador no puede procesar un valor (objeto raro, excepción de formato), **falla
  cerrado**: sustituye ese valor por `[no_saneado]` (nunca lo emite crudo), conserva el evento y
  deja un aviso de tipo `log.saneo_fallido` sin el valor original.

### 3.2 Procesador structlog global

- Nuevo módulo de saneo compartido (propuesta `utils/saneo_logs.py`):
  `sanear_texto`, `sanear_valor`, `sanear_evento`, `SaneadorStructlog`,
  `instalar_saneo_structlog`, `refrescar_raices`.
- `SaneadorStructlog` firma `(logger, method_name, event_dict) -> event_dict`:
  - copia el dict; sanea **claves y valores** (strings, listas, tuplas, dicts anidados);
  - sanea `event` y `exception`/traceback; conserva `exc_info` si aún no se formateó? Se instala
    **después de `format_exc_info`** (se añade si falta), así que el traceback llega como texto
    en `exception`; se sanea.
  - no hace I/O, no consulta BD, no resuelve symlinks en cada evento: usa raíces precalculadas
    (§3.4) y regex precompiladas.
- **Instalación idempotente:** `instalar_saneo_structlog()` lee `structlog.get_config()`,
  conserva logger factory/wrapper/contexto, añade `format_exc_info` si no está, inserta el
  saneador **antes del renderer** (último procesador) y **antes de `capturar`** del búfer; no
  duplica si ya está por `__name__`/marca. Si se llama dos veces, no cambia el orden.
- **Búfer:** `registro_reciente.instalar_captura()` debe insertar `capturar` **después** del
  saneador (o `capturar` aplica el mismo `sanear_evento`), para que lo que se guarde y lo que se
  descarga esté saneado. `_linea`/`_excepcion` también aplican `sanear_texto` al formatear
  (defensa para eventos capturados antes de instalar o por una llamada directa).
- **Arranque:** `main.py:18-20` instala captura al importar; `create_app()` (`main.py:420-423`)
  instala el filtro de acceso. La secuencia propuesta:
  1. `instalar_saneo_structlog()` **antes** de `instalar_captura()`;
  2. `instalar_captura()`;
  3. `instalar_filtro_de_acceso()` (#361, ya existe);
  4. `instalar_filtro_de_registros()` (nuevo).
  Si el orden se invierte, el búfer podría guardar un evento sin sanear; la prueba de orden lo
  detecta. Cualquier llamada a `instalar_saneo_structlog()` posterior a `instalar_captura()` debe
  recolocar el saneador antes del capturador (idempotente).

### 3.3 Filtro `logging.Filter` para stdlib/uvicorn

- Nuevo `SaneadorDeRegistro(logging.Filter)`:
  - sanea `record.msg` (string; no reinterpreta formato), `record.args` (tupla/dict/valores
    anidados) y `record.exc_text`;
  - si hay `exc_info` y no `exc_text`, formatea la excepción con `traceback.format_exception`,
    la sanea y la asigna a `record.exc_text`; deja `exc_info` para que el formatter use el texto
    saneado (el `Formatter` de stdlib usa `exc_text` si existe);
  - **nunca** deja el mensaje original si el saneo falla: `record.msg = "(registro omitido: saneo
    fallido)"`, `record.args = ()`, `exc_text` saneado/`"..."`; devuelve `True` (no silencia el
    evento, pero no filtra datos);
  - no modifica handlers, niveles ni propagación.
- **Instalación segura:** `instalar_filtro_de_registros()`:
  - añade el filtro a `logging.getLogger("uvicorn.error")` (donde uvicorn escribe «Exception in
    ASGI application»; `uvicorn.access` es de #361 y no se toca);
  - para stdlib de la app, añade el filtro a los **handlers existentes del logger raíz** si los
    hay, sin reemplazarlos; si no hay handlers, no inventa uno; el filtro de `uvicorn.error` es
    el que cubre 5xx. No se añade a `uvicorn.access`.
  - idempotente: comprueba `isinstance` en `logger.filters` y `handler.filters`; una marca evita
    duplicar; llamar dos veces no cambia nada;
  - si un handler no admite filtros o falla, no tumba el arranque: se registra un evento propio
    sin datos y se sigue (el procesador structlog sigue protegiendo la app).
- **5xx:** uvicorn con `--log-level info` (`Dockerfile:91-99`) escribe la traza en
  `uvicorn.error`; el filtro la sanea antes del handler. No se necesita cambiar el `CMD` ni el
  log config.
- **Stdlib conocida:** `utils/cortesia.py:86,559` usa `logging` y escribe fuente + tope (sin
  ruta); el filtro no la altera. No hay otro logger stdlib de la app en `src/zascarr` (comprobado
  con `grep -RIn 'logging.getLogger'`).

### 3.4 Raíces sensibles

- Al instalar/refrescar, construir un conjunto de raíces:
  `library_path`, `downloads_path`, `transmission_download_dir`, `amule_incoming_dir`,
  `covers_cache_path`, `export_path`, `library_roots` (`config.py:196-216`), y las raíces de BD
  que el servicio de raíces registre al cargar; resolver con `Path.resolve(strict=False)` y
  guardar también la forma sin resolver y sus `host_path` si aplica.
- `refrescar_raices()` se llama al arrancar y cuando Ajustes/raíces cambian; **nunca dentro del
  procesador** (sin I/O ni BD en el camino de log).
- Si una ruta no cuelga de una raíz conocida pero es absoluta y termina en extensión de cómic,
  se redacta igual (`[archivo]`/`[ruta]`) por la regex de extensión; no se espera a tener la raíz.
- Los **nombres de raíz** (`raiz.name`) sí se permiten; no se permiten sus `path`.

### 3.5 Diagnóstico que se conserva

- stdout: evento, nivel, timestamp, `file_id`, `root`, `host`, `error_tipo`, `estado`, `code`,
  contadores, traza de código de la app.
- `/ui/logs`: mismo contenido saneado; el búfer no guarda rutas/nombres/URLs con path/query.
- UI de la app: **sin cambios**; `report.errors` y los mensajes de pantalla pueden seguir
  mostrando la ruta/nombre al coleccionista (no son logs). `dashboard.html:44` solo cambia su
  aviso de privacidad para no prometer lo que ya no ocurre.
- No se introduce jerga nueva (`hash`, `token`, `structlog`) en superficie; los textos de error
  de pantalla siguen con causa/acción.

---

## 4. EARS de comportamiento

- **Cuando** cualquier evento structlog incluye una ruta de la biblioteca/descargas/raíz/temporal
  o un nombre de archivo con extensión de cómic, **el sistema** lo sustituye por `[ruta]`/
  `[archivo]` antes del renderer y antes de guardarlo en el búfer; el evento, su nivel y sus
  campos permitidos se conservan.
- **Cuando** un valor es una URL, **el sistema** conserva solo esquema + host y sustituye
  path/query/fragmento por `[url]`; si lleva credenciales o query sensible, aplica
  `[credencial]`; no emite la URL original.
- **Cuando** el valor es un dict/lista/tupla anidada, **el sistema** sanea recursivamente claves
  y valores; no deja una rama sin revisar.
- **Cuando** se emite `logger.exception`/`exc_info`, **el sistema** formatea la excepción (si
  hace falta), sanea el traceback y conserva el tipo de excepción; no deja rutas de datos en el
  mensaje.
- **Cuando** uvicorn registra una traza 5xx en `uvicorn.error`, **el sistema** sanea `msg`,
  `args` y `exc_text`; el estado HTTP y la traza de código siguen siendo diagnosticables.
- **Cuando** el saneador no puede procesar un valor, **el sistema** falla cerrado
  (`[no_saneado]`/aviso), no emite el valor crudo y no tumba la petición.
- **Cuando** se instala dos veces, **el sistema** no duplica procesadores/filtros ni cambia el
  orden; **cuando** el orden es incorrecto (captura antes del saneador), la prueba de integración
  falla.
- **Cuando** no hay nada sensible, **el sistema** no altera el evento (prueba de no regresión).
- **Cuando** se cambian las raíces en Ajustes/BD, **el sistema** refresca las raíces fuera del
  procesador; los eventos nuevos usan la lista nueva, sin I/O en el log.
- **Cuando** el coleccionista descarga `/ui/logs`, **el sistema** entrega el mismo contenido
  saneado, con `no-store`/`nosniff` y el aviso corregido; la UI de diagnóstico no cambia.
- **Cuando** se ejecuta el control negativo (sin saneador/filtro), **el sistema** deja ver la
  ruta/URL de prueba en stdout/captura; con ellos, no aparece. Cada punto del inventario tiene
  su par positivo/negativo.

---

## 5. Pruebas

### 5.1 Por punto y control negativo

| Grupo | Casos | Criterio |
|---|---|---|
| Inventario directo | Cada fila de §2.2 con una ruta/nombre/URL de prueba (p. ej. `/media/library/Serie/foo.cbz`) capturada con `structlog.testing.capture_logs` o un handler de prueba | La ruta/nombre no aparece; `file_id`/`formato`/`raiz`/`error_tipo` sí; control negativo **sin** saneador la muestra |
| Búfer | `registro_reciente.capturar` con evento sensible, `texto_reciente()` y descarga `/ui/logs` | Ruta/nombre/URL no aparecen; evento/ID sí; actualizar `tests/test_logs_recientes.py:51-57`, que hoy **afirma que `/media/x.cbz` aparece** (contrato obsoleto de BL-E5) |
| Anidados | dict/list/tuple con claves `path`, `ruta`, `file_path`, `url`, `password` | Saneo recursivo; no se muta el original; idempotente |
| URLs | `https://host/path?token=x`, `https://user:pass@host/x`, `ftp://host/a`, URL con `%2F` | Solo `https://host/[url]`/`ftp://host/[url]`; sin query/credenciales |
| Exception | `logger.exception` con `FileNotFoundError("/media/.../foo.cbz")`; `format_exc_info` | Tipo y evento se conservan; `[ruta]` en el mensaje; no se duplica la traza |
| Filtro stdlib | `LogRecord` con `msg`, `args`, `exc_text` y `exc_info`; `uvicorn.error` con `caplog`/handler de prueba; 5xx real si es posible | Saneado; estado/tipo conservados; no se alteran handlers ni niveles |
| Instalación | Llamar dos veces; orden captura/saneador; `structlog.get_config` antes/después | Sin duplicados; orden correcto; resto de procesadores intactos |
| No regresión | Evento sin datos; UI `report.errors`/mensajes de pantalla; `uvicorn.access` #361; tests de `/ui/logs` | Sin cambios; no se filtra el acceso; la UI conserva causa/acción |
| Seguridad | Raíz symlink resuelta, ruta fuera de raíz con `.cbz`, nombre que parece app (`/app/src/...`) | Datos de usuario redactados; código de la app conservado |
| Rendimiento | 10.000 eventos/strings de 1 KiB, sin I/O; medir tiempo/ memoria local | Regex precompiladas; coste lineal y bajo; sin llamadas a BD/FS; presupuesto propuesto <1 ms/evento en el equipo de desarrollo; **Pi NOT RUN** |

### 5.2 Casos concretos de inventario

- `importer.file_failed` con `path.name` → no nombre; `formato=cbz`; control negativo.
- `importer.imported`/`recuperado` con `relative` → no ruta relativa; `file_id`/`root`.
- `library_audit.hash_failed` con `path`/`str(exc)` → no ruta; `error_tipo=OSError`.
- `cbz.*` con `dir`/`path` → no ruta; evento/fase.
- `discovery.source_failed`/`ajustes.test_failed` con `str(exc)` → tipo; UI sigue mostrando el
  mensaje de conexión.
- `exportacion_kavita.materializar_falló` con `destino` → no destino; `file_id`/`modo`.
- `tagger.lote_abortado` con `motivo` de excepción → tipo, no mensaje.
- `forum`/`cover` con códigos → prueba de que el código no contiene URL (no cambio de valor).
- `blog_feed`/`robots` con URL → host.
- `uvicorn.error` 5xx con `FileNotFoundError("/media/...")` → no ruta; traza de app conservada.

### 5.3 PASS / FAIL / NOT RUN

- **PASS:** este diseño, el inventario y las pruebas definidas; lectura del código/docs.
- **FAIL:** ninguno de la especificación. Un fallo real solo aparece al implementar/probar.
- **NOT RUN:** implementación, pruebas ejecutadas, Pi, stdout real de Docker, `/ui/logs` real,
  logs de terceros (Postgres/Transmission/aMule/proxy), 5xx reales bajo uvicorn, rendimiento en
  Pi, y la ficha `benchmark-SEC-LOG-369.md` (no existe en `c7bf76d5`; se cita cuando se
  incorpore, sin duplicar).

---

## 6. Riesgos y límites

| Riesgo | Mitigación |
|---|---|
| Saneador demasiado agresivo y diagnóstico pobre | Conserva tipo/id/root/host/código/traza de app; solo redacta datos de usuario; tests de no regresión |
| Falso negativo (ruta no reconocida) | Raíces resueltas + regex de extensión de cómic + URLs + credenciales; prueba adversarial |
| Falso positivo (ruta de código) | Se conservan `/app/src/zascarr/...`; solo se redactan datos/absolutas de cómic |
| Saneador rompe el log | Falla cerrado (`[no_saneado]`/`[credencial]`), evento conservado, nunca crudo; envuelto en `try` |
| Orden de procesadores/captura | Instalación idempotente y prueba de orden; `capturar` aplica saneo por defensa |
| Filtro no cubre 5xx por handler/versión | Filtro en `uvicorn.error` + prueba con uvicorn real; no se sustituyen handlers; si no se puede, se registra y se declara |
| Coste en Pi | Regex precompiladas, sin I/O/BD/FS; 10k eventos microbenchmark; **Pi NOT RUN** |
| Pérdida de la ruta en `/ui/logs` que el operador necesitaba | La UI de la app sigue mostrando causa/acción; el ID permite localizar; se documenta el cambio de privacidad |
| Logs antiguos del búfer | `_linea`/`_excepcion` sanean al formatear; reinicio vacía el búfer; no se reescriben logs de Docker |
| Terceros | Fuera de alcance declarado; no se afirma que Postgres/Transmission/proxy estén saneados |

---

## 7. Plan por cortes y estimación

| Corte | Contenido | Esfuerzo | AC |
|---|---|---|---|
| **1 · Procesador + inventario** | `utils/saneo_logs.py` (texto/valores/eventos/raíces), `SaneadorStructlog`, instalación idempotente, orden con captura, cambios de campo §2.2, búfer, pruebas por punto + control negativo + nested/URL/exception | **M** | AC1, AC2, AC3 (structlog), AC4 |
| **2 · Filtro stdlib/uvicorn + UI copy** | `SaneadorDeRegistro`, instalación en `uvicorn.error`/handlers existentes, 5xx, idempotencia, `/ui/logs` y aviso, pruebas 5xx/no regresión/rendimiento | **S/M** | AC1, AC2 (5xx), AC3, AC4 |

- **Dependencia:** 1 → 2. Sin el procesador no se declara AC3; sin el filtro no se cubre 5xx.
- **Estimación:** **M no calibrada**; no hay migración ni cambio de modelo. El corte 1 es la mayor
  parte; el 2 es acotado.
- No se necesita ADR: es una política de logging dentro de la app; `CLAUDE.md` §5.4 ya la manda.
  Si el PO quiere fijar la política como decisión duradera, puede añadirse a SECURITY.md, pero
  no se crea ADR en este encargo.
- **NOT RUN:** Pi/volumen real, stdout real de Docker, logs de terceros, proxy, 5xx reales y
  rendimiento en hardware; no se declara nada implementado.

---

## 8. Trazabilidad AC #369 → contrato y pruebas

| AC #369 | Dónde | Pruebas |
|---|---|---|
| 1. Sin ruta/nombre; tipo + id suficiente | §2.2, §3.1, §3.5 | tabla §5.1; control negativo por punto |
| 2. Prueba por punto + control negativo | §5.1-§5.2 | captura structlog y handler stdlib |
| 3. Trazas sin rutas (o se declara) | §2.3, §3.2-§3.3 | excepción/traceback, 5xx |
| 4. Sin cambio de UI/contratos; diagnóstico no degrada | §3.5, §5.1 | report.errors/UI; `uvicorn.access` #361; `/ui/logs` |

---

## 9. Referencias

- #369 (encargo); #361 y PR #365 (access log, fuera de alcance); `CLAUDE.md:139-140` (§5.4).
- `src/zascarr/utils/registro_reciente.py:8-10,31-67,94-128` (búfer y redacción actual).
- `src/zascarr/main.py:18-20,32-33,420-423` (instalación de captura/filtro; sin configuración
  structlog propia; `structlog>=24.1.0`, `pyproject.toml:18`).
- `src/zascarr/utils/log_acceso.py:32-56` (filtro de acceso #361; no se toca).
- `src/zascarr/web/dashboard.py:34-42` y `dashboard.html:42-44` (`/ui/logs` y aviso).
- `tests/test_logs_recientes.py:51-57` (hoy afirma que la ruta aparece; debe cambiar).
- `docs/design/especificacion-BL-E5-logs.md` (privacidad del búfer; su afirmación de que puede
  contener rutas queda superada por #369).
- Inventario: §2 (25 candidatos directos + 36 `logger.exception`; `git grep` 297 líneas
  `logger.`).
- `benchmark-SEC-LOG-369.md`: **no existe en `c7bf76d5`**; se cita cuando se incorpore, sin
  duplicar sus tablas.

*Fin. Diseño propuesto; no implementado; sin cambios de código, UI real, producción ni Pi.*
