# Spike #343 / BL-WK5 — leer el progreso desde Kavita

**Estado:** investigación cerrada; **documento de decisión**. No implementa integración.
**Fecha:** 2026-11-11.
**Entorno:** Pi doméstica real (Kavita baremetal en la red local; ZascArr desplegado y sano,
Pi indicada por el Lead en `cbecad5`). **Solo lectura:** no se escribió en Kavita, en su BD ni
en la biblioteca; no se ejecutó ninguna llamada `POST` de lectura/progreso. Los títulos, rutas y
credenciales reales no se transcriben en este documento.

**Insumos:** #343, #149 (B20), #150 (C3), `docs/design/B20-exportacion-kavita.md`,
`docs/design/ui-BL-C3-lectura.md`, `docs/design/benchmark-whakoom.md` y
`docs/design/benchmark-BL-CNV-datos.md`.

---

## 1. Contrato real de Kavita

### 1.1 Versión y licencia

| Dato | Valor comprobado |
|---|---|
| Versión instalada | **Kavita 0.9.0.2** (`/opt/kavita/current` → `releases/v0.9.0.2`; `GET /api/server/check-update` devuelve `currentVersion: 0.9.0.2`) |
| Actualización disponible | 0.9.1.4 (dato del mismo endpoint; **no se actualizó**) |
| Licencia | **GPL-3.0** (LICENSE del repositorio y metadatos del Swagger de la propia aplicación; ver §1.3) |
| Despliegue | Baremetal ARM64, systemd `kavita.service`; escucha en la red local. **No** es un contenedor del compose de ZascArr |

La versión no se deduce de la UI: se comprobó contra el binario instalado y contra un endpoint
de la API. Es una versión antigua respecto a la última publicada; cualquier integración futura
debe fijar una versión mínima y **no** asumir la API de `develop`.

### 1.2 Autenticación

- Kavita usa **Auth Keys** (API keys) asociadas al usuario. La autenticación por API se hace con
  la cabecera **`x-api-key`** (también admite `?apiKey=` en query; la cabecera es la opción
  preferida y la que se usó).
- La aplicación documenta este esquema en su propio Swagger: «Auth Key passed in the
  `x-api-key` header». En la instancia real **el Swagger no está expuesto**
  (`/swagger/v1/swagger.json` → 404, también `/swagger/index.html`); el contrato se verificó
  contra la fuente del tag v0.9.0.2 (`Kavita.Server/Startup.cs`,
  `Middleware/AuthKeyAuthenticationHandler.cs`) y contra las respuestas HTTP reales.
- Hay una cuenta y varias Auth Keys; se usó una clave existente **sin imprimirla** y sin
  modificarla. El login por usuario/contraseña existe, pero no es necesario para este spike.
- **Coste de seguridad:** una integración real tendría que guardar una Auth Key de Kavita en la
  configuración de ZascArr. Es un secreto nuevo, con rotación/revocación y lectura de progreso de
  una persona; debe tratarse como credencial (no en logs, no en URLs, no en la exportación).

### 1.3 Endpoints comprobados (solo `GET`)

Todos contra `127.0.0.1:5000` en la Pi, con la cabecera `x-api-key`, y con respuesta 200:

| Endpoint | Qué devuelve | Uso para #343 |
|---|---|---|
| `GET /api/health` | `Ok` (texto) | Salud; **no** incluye versión |
| `GET /api/server/check-update` | `currentVersion`, `updateVersion` | Versión fiable |
| `GET /api/stats/server/stats` | recuentos de biblioteca (series, volúmenes, capítulos, ficheros, tamaño) | Cifras agregadas |
| `GET /api/series/{seriesId}` | `SeriesDto`: `pages`, `pagesRead`, `latestReadDate`, `totalReads`, `folderPath` | Progreso **por serie** |
| `GET /api/series/volumes?seriesId=` | `VolumeDto[]` con `pages`, `pagesRead` y `ChapterDto[]` | Progreso **por volumen/número** |
| `GET /api/series/chapter?chapterId=` | `ChapterDto`: `pages`, `pagesRead`, `totalReads`, `lastReadingProgressUtc`, `files` | Progreso **por capítulo/fichero** |
| `GET /api/reader/get-progress?chapterId=` | `ProgressDto`: `pageNum`, `chapterId`, `volumeId`, `seriesId`, `lastModifiedUtc` | Página actual |
| `GET /api/reader/has-progress?seriesId=` | booleano | Hay/no hay progreso |
| `GET /api/reader/continue-point?seriesId=` | siguiente capítulo a leer | «Continuar leyendo» |

**Lo que no está disponible de forma sencilla:** `GET /api/series/all` y `/api/series/all-v2`
responden 404 por GET; la lista filtrada es un `POST` (`/api/series/all-v2` o `/api/series/v2`).
Para agregados de todo el catálogo se usó la **BD SQLite de Kavita en modo `ro`**, no una
colección de `GET` por serie. Un futuro sincronizador tendría que decidir entre ese `POST` de
solo lectura o el modo BD; **no se usó el `POST` en este spike**.

**OpenAPI/Swagger:** la instancia no lo sirve. La fuente del tag sí tiene Swagger configurado y
declara licencia GPL-3.0; si se necesita OpenAPI en una versión futura, habrá que comprobarlo en
esa versión, no darlo por hecho.

---

## 2. Qué progreso expone Kavita por serie y por número

Kavita modela **Serie → Volumen → Capítulo → Ficheros**. El «número» de ZascArr corresponde
razonablemente a un **Capítulo/Volumen** de Kavita, pero no hay una garantía de identidad: un
capítulo puede ser un especial, un volumen puede agrupar varios números y el fichero puede tener
nombre propio. El progreso es por **capítulo** (páginas leídas y página actual), con agregados
calculados en serie/volumen.

| Nivel | Campos reales | Interpretación |
|---|---|---|
| Serie | `pages`, `pagesRead`, `latestReadDate`, `totalReads` | Suma de páginas leídas de sus volúmenes; no hay un booleano «terminada» |
| Volumen | `pages`, `pagesRead`, `chapters[]` | Agregado; los capítulos llevan su propio progreso |
| Capítulo/número | `pages`, `pagesRead`, `totalReads`, `lastReadingProgressUtc` | Progreso de página y número de lecturas completas |
| Página actual | `pageNum` (`ProgressDto`) | Posición de reanudación |

**Conclusión de contrato:** hay datos suficientes para saber «hay progreso», «páginas leídas»,
«página actual» y «última lectura», pero **no hay un estado cerrado de terminado** equivalente al
`reading_progress.status` de ZascArr. Cualquier sincronización tendría que **derivar** el estado
(por ejemplo, `pagesRead >= pages` o `totalReads > 0`) y declarar esa derivación; no se puede
presentar como un dato exacto de Kavita.

### 2.1 Población real de progreso

En la BD real de Kavita (lectura `ro`):

- **1 fila** en `AppUserProgresses`; **1 serie**, **1 capítulo** y **1 fichero** con progreso.
- Del total de **1.109 series**, **4.690 capítulos** y **4.858 ficheros**, la cobertura es
  **0,09 % / 0,02 % / 0,02 %**. El único progreso tiene 20 páginas leídas de 132 y
  `totalReads = 0`.
- Ese fichero con progreso **no casa** con ninguno de los 1.493 ficheros de ZascArr que están
  enlazados a un número (0/1 por nombre de fichero).

Por tanto, con los datos actuales, un importador de progreso **no aportaría ninguna lectura** al
catálogo de ZascArr: la única lectura de Kavita no está en la parte catalogada de ZascArr. La
muestra es demasiado pequeña para validar una sincronización, incluso aunque la API funcione.

---

## 3. Casado ZascArr ↔ Kavita con datos reales

### 3.1 Universo medido

| Lado | Medida |
|---|---|
| ZascArr | 5.063 `files`; **1.493** enlazados a `issues` (46 series); 51 series en total |
| Kavita | **1.109** series, **4.690** capítulos, **4.858** ficheros |
| Raíces | **Distintas**; una biblioteca de Kavita apunta a una raíz propia distinta de la raíz canónica de ZascArr. No se transcriben las rutas |

### 3.2 Fracciones (solo agregados)

| Criterio | Resultado | Lectura |
|---|---:|---|
| Ruta absoluta exacta | **0 / 1.493** | Las raíces son distintas; sin B20 no hay ruta común |
| Nombre de fichero exacto (basename normalizado) | **1.413 / 1.493 = 94,6 %** de los enlazados; **4.836 / 5.063 = 95,5 %** del total | Alto, pero un basename **no es identidad**: puede haber homónimos y no dice de qué serie/número es |
| Serie por nombre normalizado | **30 / 46 = 65,2 %** de las series enlazadas de ZascArr | Hay series con título distinto entre catálogos |
| Estructura «serie normalizada + número de grapa» | **637 / 1.493 = 42,7 %** | Proxi de una estructura tipo B20; no es el formato B20 real |
| Formato B20 exacto (carpeta + `Serie NNN - Título.ext`) | **NOT RUN** | B20 está diseñado y **no implementado**; no hay exportación real que comparar. No se puede afirmar que Kavita lea esa estructura hoy |

**No se debe usar el 94,6 % de basename como «casa»**: el propio ZascArr ya trata los homónimos y
la identidad de serie/número como un problema, y Kavita puede tener el mismo nombre de fichero en
otra carpeta o serie. La única forma segura de casar es la que ya define B20: **ruta/manifiesto de
exportación + hash** (o una identidad explícita), no el nombre suelto.

---

## 4. Coste y privacidad

### 4.1 Coste medido en la Pi

Con la instancia real, desde `127.0.0.1` (sin red externa):

| Llamada | Tiempo | Respuesta |
|---|---:|---:|
| `GET /api/series/{id}` | 0,003 s | ~1 KB |
| `GET /api/series/volumes?seriesId=` | 0,014 s | ~2,5 KB |
| `GET /api/reader/get-progress?chapterId=` | 0,002 s | 140 B |
| `GET /api/stats/server/stats` | < 0,01 s | 171 B |

El proceso de Kavita ya está en **~579 MB RSS** (`MemoryCurrent` del servicio) con pico histórico
de **~1,8 GB**. Las consultas de este spike son despreciables frente a esa base; el coste real de
una integración sería la **lista completa** de series/progreso (1.109 series) y la lógica de
casado, no una llamada puntual. No se midió el `POST` de listado completo ni una sincronización
completa: **NOT RUN**.

### 4.2 Privacidad

- Todo ocurre en la **red local**; no hay telemetría, ni llamada a un servicio externo, ni
  escritura fuera de la Pi.
- El progreso es dato personal de lectura. La API exige Auth Key; no se usó usuario/contraseña.
- El documento no incluye títulos, rutas, IDs de usuario, claves ni tokens.
- Una integración futura debe ser **opt-in**, guardar la Auth Key como secreto, no loguear
  progreso/rutas y no enviar nada fuera. **No** se propone embeber el progreso en el CBZ ni
  escribirlo en Kavita.

---

## 5. Decisión: **descartar la integración automática por ahora**

Frente a la alternativa de #150 (marcar leído/puntuado **a mano** en ZascArr) y a la idea de
adoptar o adaptar una lectura automática de Kavita:

**DECISIÓN: DESCARTAR** (no construir la integración en esta historia). Mantener #150 manual como
vía soportada. No es un «no» definitivo a Kavita: es un **no ahora**, con condiciones de revisión.

Motivos, por orden de peso:

1. **No hay identidad segura hoy.** La ruta exacta casa 0/1.493; B20 no está implementado y no hay
   exportación real que comparar. El basename (94,6 %) es una coincidencia, no una identidad; el
   proxi estructural serie+número cae al 42,7 %. Una sincronización por nombre tendría falsos
   positivos y marcaría lecturas en el número equivocado.
2. **La muestra de progreso es irrelevante.** 1 fila en 1.109 series; 1 serie/capítulo/fichero; y
   ese fichero no está entre los 1.493 ficheros enlazados de ZascArr. No se puede validar el
   contrato con datos representativos, ni demostrar que el colectivo gane algo.
3. **Kavita no expone un «terminado» limpio.** Hay páginas/página actual/lecturas, pero ZascArr
   necesitaría derivar el estado y documentar la derivación; no es una copia directa de una
   verdad ajena.
4. **Coste/seguridad no nulos:** una Auth Key nueva que custodiar, una versión antigua
   (0.9.0.2) que puede cambiar, y endpoints de listado que no son GET. No compensa con 1 lectura.
5. **#150 ya resuelve el caso base** sin doble marcado para quien no use Kavita; y no bloquea al
   colectivo que sí lee en Kavita: simplemente hoy no se le promete sincronización.

### 5.1 Condiciones para revisar (no reabrir #150 por esto)

Volver a evaluar **solo** si se cumplen todas:

- **B20 implementado y usado**: existe una exportación real con manifiesto (`_zascarr_manifest.json`)
  y hashes; el casado se hace por **ruta/hash/ID de exportación**, nunca por basename.
- **Progreso representativo**: una muestra real con varias series/números leídos, no una fila
  aislada; se puede medir acierto y falsos positivos.
- **Opt-in explícito y Auth Key** gestionada como secreto, con rotación y sin logs.
- **Solo lectura** en Kavita y **sin escribir** en la biblioteca/CBZ; ZascArr sigue siendo la
  fuente de verdad del catálogo.
- **Derivación de estado documentada** (p. ej. `pagesRead >= pages` → terminado), con tests de
  frontera y una decisión de producto sobre «páginas parciales».
- **Versión mínima** de Kavita fijada y verificada; el endpoint de listado completo y el contrato
  de progreso comprobados en esa versión.
- **Sin telemetría** y con privacidad revisada; el sync, si existe, es una acción manual/opt-in,
  no un scheduler silencioso.

### 5.2 Qué significa para #150

- **#150 (C3) sigue siendo la vía manual**: marcar leído/leyendo/pendiente y puntuar en ZascArr,
  sin depender de Kavita ni de una API key.
- **No se bloquea #150 con este spike**; el comentario de decisión se deja en #150 sin reabrirlo.
- Si en el futuro se implementa B20 y hay datos, la sincronización sería una **historia nueva** de
  solo lectura, **no** una ampliación silenciosa de #150.

---

## 6. PASS / FAIL / NOT RUN

### PASS

- **Contrato real:** versión **0.9.0.2**, licencia **GPL-3.0**, autenticación por **`x-api-key`**,
  y endpoints reales de salud, versión, estadísticas, serie, volúmenes, capítulo y progreso
  verificados con 200 en la Pi.
- **Progreso:** se confirmó que Kavita expone progreso por **serie/volumen/capítulo** (páginas
  leídas, página actual, última lectura, lecturas completas) y que **no** hay un booleano de
  terminado equivalente a ZascArr.
- **Casado medido:** ruta exacta 0/1.493; basename 1.413/1.493 (94,6 %); serie normalizada
  30/46 (65,2 %); proxi estructural serie+número 637/1.493 (42,7 %), con datos reales agregados.
- **Población de progreso medida:** 1/1.109 series, 1/4.690 capítulos, 1/4.858 ficheros, y 0/1.493
  ficheros enlazados de ZascArr con coincidencia de progreso.
- **Coste/privacidad:** consultas locales de milisegundos y kilobytes; proceso Kavita ~579 MB RSS;
  todo en red local; sin telemetría; solo `GET` y BD SQLite en `ro`. No se escribió nada.
- **Decisión razonada** con condiciones de revisión y recomendación para #150.

### FAIL

- Ninguno de ZascArr. El único «fail» es de encaje para una integración: **no existe hoy una
  identidad segura ZascArr↔Kavita** (ruta 0; B20 no implementado; basename no es identidad) y la
  muestra de progreso no permite validar el valor. Es la base de la decisión de descartar, no un
  defecto del PR.

### NOT RUN

- **Formato B20 exacto**: B20 está diseñado y **no implementado**; no hay exportación real que
  comparar. El 42,7 % es un proxi estructural, no una prueba de B20.
- **Sincronización completa** / listado de las 1.109 series vía API: no se ejecutó el `POST` de
  filtrado ni se midió una ronda completa; los agregados salen de la BD SQLite en `ro`.
- **Escritura** en Kavita, en su BD o en la biblioteca: fuera de alcance y **no ejecutada**.
- **UI/navegador real** y **matriz de versiones** de Kavita: no se abrió el navegador; solo se
  probó la versión instalada.
- **Auth Key rotación/revocación, permisos de usuario y multiusuario**: no se probaron.
- **Progreso representativo** de una persona que lea habitualmente en Kavita: la instancia tiene
  una sola fila de progreso.

---

## 7. Reproducción y límites

- Las lecturas se hicieron en la Pi, contra `127.0.0.1:5000`, con una Auth Key existente en la
  cabecera `x-api-key`; **no se imprime ninguna clave**.
- Los recuentos y el casado se calcularon leyendo la BD de Kavita en modo SQLite `ro` y la BD de
  ZascArr con `psql` de solo lectura (`docker exec`, sin escrituras), agregando por SQL y
  normalizando nombres en memoria. No se copiaron ficheros ni se tocó la biblioteca.
- La normalización de títulos es deliberadamente simple (acentos/casefold/puntuación); no sustituye
  al matcher de ZascArr ni demuestra identidad.
- **No se ejecutó ningún `POST`** ni se modificó configuración de Kavita/Pi.
- Este documento es el entregable del spike; **no autoriza** implementar la integración ni cambiar
  el esquema. Cualquier implementación futura iría en su propia historia, con migración si hace
  falta y con la decisión de producto correspondiente.
