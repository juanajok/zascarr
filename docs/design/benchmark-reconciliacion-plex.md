# Ficha de benchmarking — reconciliación de la biblioteca (BL-R0, #229)

> Ficha §13 (`docs/design/benchmark-referencias.md`, CLAUDE.md §13). **Spike documental: sin código, sin migraciones, sin tocar el backlog,
> sin ejecutar Plex ni fuentes reales.** Es la puerta de BL-R1 a BL-R7 (#230–#236).
> Lectura: **2026-10-20** · `main` de ZascArr: `4270c62`. Propuesta de historias que se contrasta: `docs/design/historias-reconciliacion-plex-2026-10-18.md` (PR #227).

## 0. Lo esencial (léelo primero)

1. **Lo que se dice de Plex NO ha podido leerse en su fuente.** `support.plex.tv` responde **HTTP 403** tanto a la herramienta de descarga como al
   navegador integrado (2026-10-20). Todo lo de Plex marcado `[DOC-RESUMEN]` procede de **resúmenes de búsqueda web de ese día**, no del texto
   de la página. Es evidencia **débil**: sirve para orientar el diseño, no para afirmar que Plex «hace X». Quien decida debe leer los artículos (URLs en §2).
2. **Lo único de Plex demostrado por código es el ejemplo oficial** (`plexinc/tmdb-example-provider` @ `3348a89`): un *proveedor de metadatos*.
   Demuestra el contrato de **emparejar** (por id externo primero, por título después; una candidata, o hasta cinco si `manual=1`) y de **paginar**.
   **No** demuestra *Fix Match*, *Unmatch*, papelera, bloqueo de campos ni versiones: eso es del servidor de Plex, que no se usa ni se lee.
3. **El ejemplo oficial no trae fichero `LICENSE`** en ese commit: «ISC» sale solo del campo `license` de `package.json`/`package-lock.json`, y GitHub
   informa `license: null`. La propuesta decía «declara ISC»; es cierto **solo así**. Conclusión de §6: **no se reutiliza código**, solo el contrato de API.
4. **Kapowarr (GPL-3.0, `c191dda`) sí aporta un patrón verificado en código** para vínculos manuales (`forced` en `issues_files`/`volume_files`),
   pero **borra vínculos de archivos ausentes aunque sean manuales** (§4, escenario 3): justo lo contrario de lo que ZascArr quiere.
5. **Hallazgo local nuevo que condiciona BL-R1:** el informe de vinculación es **inmutable** (disparador `BEFORE UPDATE` en la migración 0019,
   `vinculacion_operaciones`). Deshacer no puede reescribir ese informe; necesita **su propio registro** (probablemente tabla nueva + ADR → D2).
6. **Casos reales:** hay casos registrados para E4, E5 y E6. **E1, E2 y E3 no tienen caso real** (§4). Por decisión del PO (2026-10-20, opción «mixta») cada uno lleva
   un **caso DERIVADO, claramente etiquetado como NO real** (ilustrativo, construido a partir de la arquitectura y de formas reales ya documentadas), y su
   **hueco sigue abierto**: el criterio 1 de #229 **no queda cumplido para esos tres** hasta que el PO aporte un caso real anonimizado (qué pasó, qué
   esperaba, qué resultado tuvo). Un caso derivado **no sustituye** a uno real: sirve para fijar el escenario de prueba, no para medir un problema vivido.
7. **Ninguna prueba de benchmark se ha ejecutado** (§7): están definidas con dataset y umbral *propuesto*; los umbrales son hipótesis, no mediciones.

## 1. Etiquetas de evidencia

| Etiqueta | Significa |
|---|---|
| `[COD@sha]` | **Demostrado por código** leído en ese commit (se cita fichero/función) |
| `[DOC-REPO]` | Documentado **en el propio repositorio de la referencia** (p. ej. `docs/API Endpoints.md` del ejemplo), leído en el commit fijado |
| `[DOC-RESUMEN]` | Resumen de búsqueda web de 2026-10-20; **la página no se ha leído** (403). Evidencia débil |
| `[ZASC]` | Verificado en el código de `main` `4270c62` (fichero/función) |
| `[NV]` | **No verificado.** «No lo encontré» **no** se escribe «no existe» |

## 2. Referencias fijadas

| Referencia | Versión / commit | Fecha de lectura | Cómo se leyó | Alcance |
|---|---|---|---|---|
| `plexinc/tmdb-example-provider` | `3348a89009bb418e083646fbe1360f544774bf71` («First commit», 2025-10-07; es además la cabeza de `main` a 2026-10-20) | 2026-10-20 | `gh api` (contenidos al commit) | Código + `docs/API Endpoints.md`; README: «demo para desarrolladores, uso permanente no recomendado», escrito con ayuda de Claude Code |
| Plex — [Scanning vs Refreshing a Library](https://support.plex.tv/articles/200289306-scanning-vs-refreshing-a-library/) | sin versión | 2026-10-20 | **403**; solo `[DOC-RESUMEN]` | Escanear ≠ refrescar |
| Plex — [Fix Match / Match](https://support.plex.tv/articles/201018497-fix-match-match/) | sin versión | 2026-10-20 | **403**; solo `[DOC-RESUMEN]` | Corregir identificación |
| Plex — [Unmatch an Item](https://support.plex.tv/articles/201101586-unmatch-an-item/) | sin versión | 2026-10-20 | **403**; solo `[DOC-RESUMEN]` | Desvincular |
| Plex — [Emptying Library Trash](https://support.plex.tv/articles/200289326-emptying-library-trash/) | sin versión | 2026-10-20 | **403**; solo `[DOC-RESUMEN]` | Papelera y vaciado automático |
| Plex — [Edit Details](https://support.plex.tv/articles/201272763-edit-details/) | sin versión | 2026-10-20 | **403**; solo `[DOC-RESUMEN]` | Campos bloqueados |
| Plex — [Multi-Version Movies](https://support.plex.tv/articles/200381043-multi-version-movies/) y [Multiple Editions](https://support.plex.tv/articles/multiple-editions/) | sin versión | 2026-10-20 | **403**; solo `[DOC-RESUMEN]` | Versiones/ediciones (audiovisual) |
| Plex — [Why does content I deleted on my drive still show up?](https://support.plex.tv/articles/201447966-why-does-content-i-deleted-on-my-drive-still-show-up/) | sin versión | 2026-10-20 | **localizado, ni leído ni resumido** | Pendiente: relevante para el escenario 3 |
| Kapowarr (Casvt) | `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2, 2026-09-14), GPL-3.0 | 2026-10-20 | `gh api` (código al commit) | `backend/implementations/file_matching.py` (`scan_files`, `get/set_file_matching`) |
| Mylar3 | `cdc94a4` (v0.8.3, 2025-08-17), GPL-3.0 (fijado en `benchmark-identidad-editorial.md`) | — | **No inspeccionado en este spike** | No se afirma nada sobre su reconciliación |
| Suwayomi | — | — | **No inspeccionado** | Distinguiría «actualizar biblioteca» de «refrescar» pero `[NV]` |
| Sonarr/Radarr | — | 2026-10-20 | Un intento sobre la FAQ de Servarr devolvió solo el título; **sin contenido** | `[NV]` (candidatas naturales para «rescan» vs «refresh» y raíz ausente; leer antes de BL-R3) |

## 3. Qué demuestra el ejemplo oficial de Plex (y qué no)

`[COD@3348a89]` `src/services/MatchService.ts` (`matchShow`) y `docs/API Endpoints.md`:

- **Identificador externo primero:** si la petición trae `guid` (`imdb://` o `tvdb://`, **solo esos dos**), se busca por él; si falla o no hay resultado, **cae a la búsqueda por título** (con `year`).
- **Una o varias candidatas:** sin `manual`, **una** candidata (la primera); con `manual=1`, **hasta cinco** («ordenadas de mayor a menor confianza», `[DOC-REPO]`). La ordenación es la del buscador de TMDB; el ejemplo **no calcula confianza propia**.
- **Paginado:** `X-Plex-Container-Size`/`Start`, `totalSize` frente a `size`, por defecto 20; **obligatorio solo** en `/children` y `/grandchildren` `[DOC-REPO]`.
- **Lo que NO está:** ni desvinculación, ni papelera, ni bloqueo de campos, ni escaneo, ni versiones. Es un proveedor, no el servidor. Tampoco es «el algoritmo interno de Plex».

## 4. Los seis escenarios

Formato: historia → caso real (anonimizado) → comportamiento actual → resultado deseado → qué dicen las referencias.

### E1 · Corregir una identificación equivocada — BL-R1 (#230)
- **Caso real:** **NO DISPONIBLE** (hueco abierto; lo aporta el PO). No hay registrado un caso de «vinculé mal y quiero corregir».
- **Caso DERIVADO — NO REAL, ilustrativo:** un archivo de **año minoritario** (en la forma de `Serie X 03 (2011).cbz`, que la rebanada 1 documenta con la forma de la biblioteca real) queda vinculado al número equivocado de la serie del año mayoritario; la persona lo ve en la ficha de la serie y quiere devolverlo a Pendientes y vincularlo bien sin tocar el fichero. Fija el escenario de prueba de E1; no mide un problema vivido.
- **Hoy `[ZASC]`:** `services/vinculacion.py` declara que **no desvincula ni reasigna jamás** un archivo ya vinculado (cabecera; `ya_vinculado_a_otro` → omitido). El vínculo guarda `metadata.vinculo` con `previo.match_status`/`review_motivo`; `File.issue_id` es `ON DELETE SET NULL`. El informe vive en `vinculacion_operaciones`, **inmutable** (disparador, migración 0019).
- **Deseado:** deshacer y volver a vincular como **dos operaciones**, sin tocar el fichero, con vista previa y comprobante (BL-R1).
- **Referencias:** Plex *Fix Match* (elegir otra entre candidatas) y *Unmatch* (volver a «sin emparejar») `[DOC-RESUMEN]`; Kapowarr permite **forzar o liberar** un vínculo (`set_file_matching`, `forced_match`) `[COD@c191dda]`. Ninguna prueba que lo hagan sin perder datos asociados: `[NV]`.

### E2 · Actualizar tras una edición manual — BL-R4 (#233)
- **Caso real:** **NO DISPONIBLE** (hueco abierto; lo aporta el PO). No hay incidente registrado de una fuente pisando una edición manual.
- **Caso DERIVADO — NO REAL, ilustrativo:** una serie creada a mano (`metadata_source='manual'`) con la descripción bloqueada (`locked_fields=['description']`) cuya fuente publica después otra descripción y otro número de números totales; la persona quiere ver qué propone la fuente sin que se aplique y conservar lo suyo. Fija el escenario de prueba de E2.
- **Hoy `[ZASC]`:** el enricher **nunca** toca una fila con `metadata_source='manual'` y respeta `locked_fields` por campo (`services/enricher.py`, cabecera y bloque «H3»); la vinculación escribe `metadata_source='manual'` (`vinculacion.py`, UPDATE de `files`). **No hay** registro de «lo que dijo la fuente frente a lo que confirmó la persona»: la discrepancia se pierde en silencio.
- **Deseado:** proteger la **relación** confirmada y poder ver la propuesta de la fuente sin aplicarla (D3/D4).
- **Referencias:** Plex bloquea campos al editarlos a mano y no los actualiza en el refresco `[DOC-RESUMEN]`; Kapowarr marca vínculos como `forced` para que el reescaneo no los reemplace `[COD@c191dda]` (bandera booleana **sin procedencia**).

### E3 · Desconectar y reconectar una raíz — BL-R2 (#231)
- **Caso real:** **sin incidente fechado registrado** (hueco abierto; lo aporta el PO si lo recuerda). Lo que sí existe: el diseño de B7 parte de «disco de red que estuvo desmontado / punto de montaje sin desmontar de verdad» (`docs/BACKLOG.md`, B7, 2026-09-26), y el despliegue en la Pi usa un disco USB externo, es decir, el riesgo es real aunque no haya un episodio documentado.
- **Caso DERIVADO — NO REAL, ilustrativo:** el disco externo se desconecta durante un ciclo del importador (raíz de la biblioteca inexistente) y se vuelve a conectar horas después; la persona entra en la aplicación mientras tanto y quiere saber que sus tebeos **siguen ahí** y por qué no se pueden abrir. **Compensación mientras no haya caso real:** el escenario de prueba E3 de §7 reproduce las tres situaciones (inexistente, vacía y ausencia masiva) con un dataset sintético, que sí está definido.
- **Hoy `[ZASC]`:** `Importer._detectar_desaparecidos`: raíz inexistente → *warning* y **no marca nada**; raíz vacía → *warning*; desaparición ≥ 50 % y ≥ 10 archivos → *error* y **no marca nada**; si no, marca `is_missing`/`missing_since` y **revierte solo** si el fichero reaparece. **Los tres guardarraíles solo escriben en el log**; `ImportRun` guarda `disappeared_count` y `details`, no la causa de una omisión.
- **Deseado:** hacerlo **visible** (dos niveles: estado del archivo y última comprobación de su raíz), sin borrar nada (BL-R2).
- **Referencias:** Plex manda a la papelera lo que desaparece y **no la vacía por defecto**; vaciar automáticamente tras cada escaneo es opcional y advierte de que no hay vuelta atrás `[DOC-RESUMEN]` → **descartar** el vaciado automático. **Kapowarr, por el contrario, elimina vínculos de archivos ausentes aunque fueran manuales** (`delete_bindings` incluye `file_id in manually_matched_files_missing`) y su `scan_files` tiene `del_unmatched_files=True` por defecto `[COD@c191dda]`; solo se queda quieto si la carpeta del volumen no existe (`return` temprano si `not isdir(...)`). **No es el patrón a seguir.**

### E4 · Escanear sin cambios — BL-R3 (#232)
- **Caso real registrado:** la Pi de referencia a 2026-10-20 tiene **1.339 ficheros** en base y **2.478 ciclos** del importador (consulta de solo lectura del plan de despliegue de #243); es el tamaño de partida para medir el coste de un ciclo sin cambios.
- **Hoy `[ZASC]`:** el importador **solo recorre las carpetas de descargas** (`Importer._scan_dirs`: descargas de Transmission, entrantes de aMule y `downloads_path`), no la biblioteca; sobre la biblioteca hace **un `select(File)` completo y un `Path.exists()` por fila** en un solo salto a un hilo (`_detectar_desaparecidos`). La auditoría de biblioteca (`library_audit.py`) **solo hashea archivos que comparten tamaño con otro**. El **enriquecimiento** es un ciclo **separado** (`enrich_interval_minutes`=120) y las consultas a fuentes dependen de los flags de fuentes.
- **Deseado:** comprobar el disco **sin consultar fuentes** y ver cuándo fue la última vez (BL-R3); medir objetos procesados, no filas devueltas.
- **Referencias:** Plex distingue *escanear* (buscar altas/bajas) de *refrescar metadatos* (rehacerlos aunque existan); el primero se automatiza, el segundo es manual `[DOC-RESUMEN]`. Sonarr/Radarr: `[NV]` (leer antes de BL-R3).

### E5 · Dos digitalizaciones y dos ediciones — BL-R6 (#235)
- **Caso real registrado:** biblioteca real del 2026-09-25 con **carpetas duplicadas enteras (la misma colección en dos rutas, ~140 archivos)**, que llevó a decidir «el sistema informa, la persona decide» (`main.py::_library_audit_task`). Y la serie de referencia con 155 archivos (`benchmark-U20-marcar-todos.md`). Sin datos personales.
- **Hoy `[ZASC]`:** varios `File` pueden colgar de un mismo `Issue` (no hay restricción de unicidad por archivo); el duplicado **exacto** se detecta por SHA-256 y el informe de auditoría lo cuenta (`mismo_contenido`). **No hay vocabulario** para distinguir *copia* (mismo contenido), *variante* (otra digitalización) y *edición* (otra publicación); la identidad por edición depende de M5 (`benchmark-identidad-editorial.md`).
- **Deseado:** presentar copia/variante/edición sin confundirlas (BL-R6, P2, tras M5).
- **Referencias:** Plex agrupa versiones de un mismo título y trata **ediciones** aparte, con seguimiento propio `[DOC-RESUMEN]` (modelo **audiovisual**: resolución/códec/corte). Su jerarquía audiovisual **no se traslada**.

### E6 · Pedir una página de una colección grande — #122 / BL-R2
- **Caso real registrado:** **1.322 pendientes en 108 carpetas** (auditoría en la Pi, 2026-10-15, `a5369ef`, `benchmark-U12-pendientes-escala.md`).
- **Hoy `[ZASC]`:** `GET /api/series` pagina con `page_size` ≤ 100 y devuelve `total`/`pages`; la revisión de vinculación pagina **a 100** y evalúa **solo la página**; el cursor de Pendientes es binario con `LIMITE_CURSOR = 2000` (`services/vinculacion_previa.py`). **No existe medición en la Pi** del coste de esas consultas (lo dice la ficha U12).
- **Deseado:** medir **objetos procesados**, no filas devueltas, y fijar un tope por página.
- **Referencias:** el contrato del ejemplo de Plex pagina por `Container-Start/Size` con `totalSize` y **mide el tamaño total aparte del de la página** `[DOC-REPO]`: coincide con lo que ZascArr ya hace; **no aporta nada nuevo**.

## 5. Adoptar / adaptar / descartar (por patrón)

| Patrón | Decisión | Motivo | Evidencia | Historia |
|---|---|---|---|---|
| Resolver por **id externo antes que por título**, con caída a título | **Adaptar** | ZascArr tiene columnas por proveedor (`comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`); hoy solo `enricher.py` resuelve por título. El ejemplo lo hace con 2 ids (`imdb`, `tvdb`) | `[COD@3348a89]` | BL-R5 |
| Devolver **varias candidatas** solo cuando la persona lo pide (`manual=1`, hasta 5) | **Adaptar** | Encaja con «el sistema informa, la persona decide»; el tope y la ordenación por confianza son decisiones propias (el ejemplo no calcula confianza) | `[COD@3348a89]` | BL-R1/BL-R5 |
| **Desvincular** devolviendo el elemento a «sin emparejar», sin tocar el fichero | **Adoptar el patrón** (implementación propia) | Coincide con el contrato local: vuelve a Pendientes; el estado previo se conserva como evidencia | `[DOC-RESUMEN]` + `[ZASC]` | BL-R1 |
| **Bloquear campos** editados a mano | **Ya adoptado** (`locked_fields`) → **ampliar** a la *relación* confirmada | Falta la relación y la procedencia (D3) | `[ZASC]` + `[DOC-RESUMEN]` | BL-R4 |
| Bandera **`forced`** de Kapowarr en el vínculo | **Descartar tal cual / adaptar con procedencia** | Es un booleano sin quién/cuándo/qué; ZascArr ya guarda `metadata.vinculo` con `operacion_id` | `[COD@c191dda]` | BL-R4 |
| **Papelera**: conservar lo no disponible | **Adoptar** (ya hecho en B7: `is_missing`) y **hacer visible** | Falta el *porqué* | `[DOC-RESUMEN]` + `[ZASC]` | BL-R2 |
| **Vaciado automático** de la papelera | **Descartar** | Sin vuelta atrás; contradice «no borrar». Kapowarr, además, borra vínculos de ausentes | `[DOC-RESUMEN]` + `[COD@c191dda]` | — |
| **Escanear ≠ refrescar** como acciones separadas | **Adaptar** | Ya son ciclos separados; falta poder lanzar uno sin el otro y ver el último | `[DOC-RESUMEN]` + `[ZASC]` | BL-R3 |
| **Versiones/ediciones** de Plex | **Descartar la jerarquía audiovisual**; **adaptar** solo la idea de agrupar | Unidades distintas (grapa/tomo/capítulo); depende de M5 | `[DOC-RESUMEN]` | BL-R6 |
| **Colecciones inteligentes** | **Aplazar** (BL-R7, P2) | Sin lectura de la fuente; se decidirá con su ficha | `[NV]` | BL-R7 |
| **Paginado** con total aparte | **Ya adoptado** | Coincide con lo existente | `[DOC-REPO]` + `[ZASC]` | #122 |

## 6. Barrera legal

- **Plex servidor:** no se usa, no se copia, no se ejecuta. Solo se toman **patrones de comportamiento** descritos públicamente.
- **`tmdb-example-provider`:** `package.json` y `package-lock.json` declaran `"license": "ISC"`, **no hay fichero `LICENSE`** en el árbol del commit fijado y GitHub devuelve `license: null`. ISC exige conservar el aviso de copyright y el de permiso; **sin ese texto no hay cómo cumplirlo**. Además es un ejemplo en TypeScript, para TMDB, escrito con ayuda de IA. **Decisión: no se reutiliza ni una línea.** El contrato (campos de `/matches`, paginado) es público y se reimplementa.
- **Kapowarr (GPL-3.0) y Mylar3 (GPL-3.0):** solo se estudió el *patrón*; la licencia del repositorio de ZascArr está en `LICENSE`. Antes de reutilizar cualquier fichero concreto habría que revisar su aviso (CLAUDE.md §13).
- **Contenido de terceros:** este documento resume y enlaza; no reproduce artículos de soporte.

## 7. Pruebas de benchmark — definidas, **NO ejecutadas**

Tres métricas comunes: **llamadas externas**, **memoria máxima** (cgroup del contenedor, límite 512 M) y **lecturas/escrituras** (consultas SQL y bytes leídos del disco). Dataset sintético reproducible, nunca la biblioteca real. Los **umbrales son hipótesis a validar**, no mediciones.

| # | Escenario | Qué medir | Dataset | Umbral propuesto (Pi) |
|---|---|---|---|---|
| E1 | Deshacer + volver a vincular | Consultas por vista previa y por confirmación; filas tocadas; bytes de fichero leídos (esperado **0**) | 1 serie con 200 números y 1 archivo vinculado | Vista previa ≤ 5 consultas; **0** ficheros leídos/movidos; confirmar es idempotente |
| E2 | Refresco tras edición manual | Llamadas a fuentes; campos escritos; relaciones protegidas respetadas | 100 series, 20 con relación confirmada y 10 con `locked_fields` | **0** escrituras sobre protegidas; llamadas ≤ 1 por serie no protegida |
| E3 | Raíz desconectada y reconectada | Estado de cada archivo tras 3 ciclos (desconectada, parcial, reconectada); líneas de causa guardadas | 1.500 archivos; raíz inexistente / vacía / 60 % ausente | **0** archivos marcados y **0** borrados con raíz no comprobable; reaparición automática en el 1.er ciclo |
| E4 | Escaneo sin cambios | Tiempo y memoria de un ciclo; `Path.exists()` por ciclo; llamadas a fuentes (esperado **0**) | 1.339 archivos (como la Pi) y 5.000 (margen) | Ciclo ≤ 5 s y memoria extra ≤ 64 MiB con 1.339; 0 llamadas externas |
| E5 | Copias/variantes/ediciones | Archivos hasheados frente a archivos con tamaño repetido; tiempo de auditoría | 2.000 archivos con 140 duplicados exactos y 30 variantes de otro tamaño | Solo se hashean los de tamaño repetido; ≤ 300 GB leídos evitados (cota del propio `library_audit.py`) |
| E6 | Página de colección grande | **Objetos procesados** frente a filas devueltas; tiempo por página; plan de consulta | 5.000 pendientes; páginas de 50/100 | ≤ 1 s por página y objetos procesados ≤ 2 × tamaño de página |

## 8. Decisiones abiertas (§6 de las historias): respuesta o aplazamiento

| # | Decisión | Respuesta de este spike | Estado |
|---|---|---|---|
| D1 | Número creado por la vinculación al deshacer | **Conservarlo siempre**: coherente con *Unmatch* (vuelve a «sin emparejar» sin borrar el elemento) `[DOC-RESUMEN]` y con que Kapowarr no borra el issue al soltar un vínculo `[COD@c191dda]` | **Respondida** (propuesta) |
| D2 | Comprobante de la corrección | Debe ser **duradero e idempotente**. **Hallazgo:** `vinculacion_operaciones` es inmutable por disparador, así que el deshacer **no puede reutilizarla**; lo probable es una tabla propia con ADR | **Diferida** al contrato técnico de BL-R1 |
| D3 | Qué es una relación «confirmada» | **Aceptación explícita con procedencia** (no un booleano, no solo `metadata_source='manual'`). Se descarta copiar el `forced` de Kapowarr | **Respondida** (propuesta) |
| D4 | Dónde se guarda una discrepancia | Identidad, procedencia y ciclo de vida primero; almacenamiento después | **Diferida** a BL-R4 |
| D5 | ¿BL-R1 con etiqueta MVP? | **Decidida por el PO el 2026-10-20: SÍ, con alcance estrictamente limitado a «deshacer una vinculación equivocada y volver a vincular»**, sin ampliar a correcciones de M5 (edición/publicación), lotes ni mover archivos. Es el hueco más doloroso del recorrido «vincular en sitio» y no depende de ninguna fuente externa. Esta ficha lo **registra**; **no cambia la etiqueta en el tablero** (se hace aparte) | **Decidida** (PO) |
| D6 | Kanban | Superada por la orden del PO (#228–#236 existen) | Cerrada |
| D7 | ISBN | El ejemplo de Plex solo usa `imdb`/`tvdb`; **no** hay evidencia a favor del ISBN como id de serie. Estudiarlo en #182 | **Diferida** a #182 |

## 9. Límites y NOT RUN

- **NOT RUN:** todas las pruebas de §7. **No leído:** los artículos de Plex (403), Mylar3, Suwayomi y Sonarr/Radarr para esta ficha.
- **Casos reales pendientes del PO:** E1 y E2, y un incidente fechado para E3. Están cubiertos **solo con casos derivados etiquetados como no reales** (decisión «mixta» del PO, 2026-10-20). **El criterio de aceptación 1 de #229 no se da por cumplido para esos tres escenarios** hasta que haya un caso real anonimizado.
- **Este documento no cambia el backlog ni la estimación** de BL-R1–BL-R7: la refinará quien las implemente, con esta ficha ya disponible.
- **Definition of Ready de BL-R1–BL-R7:** esta ficha cubre el punto «benchmark pertinente (BL-R0)». Siguen pendientes los demás (casos reales, decisiones D2/D4/D5, estimación).
