# SPEC: «Portada de los CBR, leída del propio archivo» (BL-PORT3, issue #418) — v1.0

> **Estado:** **v1.0** (2026-11-06). **Sin decisiones abiertas del PO:** las seis decisiones (D-1 a D-6) se
> aceptaron con mi recomendación y las cinco menores (Q-7 a Q-11) con su valor por defecto, el 2026-11-06 («sí a todo»);
> el registro, con las alternativas descartadas, está en §11. Siguen vigentes los supuestos (§13), los NOT RUN (§12) y las
> **puertas de despliegue** de §10.1 (revisión de SecOps de `unar`/GNUstep, bomba de descompresión, RAR cifrado, lectura en
> frío del USB, imagen ARM): **la spec no está cerrada como entrega, y no autoriza implementación ni despliegue.** Solo
> especificación: sin código, sin dependencias, sin PR, issue ni tablero. Destino propuesto en el repo:
> `docs/design/especificacion-BL-PORT3.md` (lo lleva el Brain).
> **Base contrastada:** `origin/main` = `721345a983b8042ef82153ac315f9034951a9437` (2026-11-06). La v0.1 se contrastó en
> `488cb037ed7592196fb46e0a3c69aa44ecb78f7e` (el SHA que corre la Pi); entre ambos solo cambian la plantilla
> `_politica_serie.html` y pruebas/documentos (`git diff --name-only 488cb03 721345a -- src Dockerfile .github pyproject.toml`
> da solo esa plantilla): **ningún fichero de portada, de formato de contenedor, del `Dockerfile` ni de CI**. Lo de «Hecho
> verificado» (§1.1) sigue valiendo. Nada ejecutado.
> **Semilla:** issue #418 (cuerpo y 4 comentarios), ficha de nivel 2 de SCOUT (`ficha-418-portada-cbr.md`, contrastada en
> `3562f3a`), evaluación de `unar` (`docs/design/evaluacion-lector-rar-tanda2-2026-10-23.md` y `-datos.md`), estilo de
> `docs/design/especificacion-BL-PORT1.md`.
> **Notación:** EARS con palabras clave en español (CUANDO, MIENTRAS, SI/ENTONCES, DONDE); criterios Given/When/Then;
> identificadores en inglés; textos de cara a la persona, en español llano (CLAUDE.md §6). Esta historia **no añade
> texto visible**.

---

## 0. Resumen ejecutivo

**Qué cambia.** Si el primer archivo utilizable de una serie es un `.cbr` que de verdad es RAR, su portada sale de **su
primera página**, leída con `unar` (una sola página, con topes y verificada), a 600 px, sin red, por el mismo camino que
un CBZ: generación perezosa y caché en disco. Si la portada de un archivo falla, **se recuerda por archivo, con el motivo
y sin ruta, y no se reabre hasta que el archivo cambie**.

**Lo que ya no hace falta construir (hallazgo).** La ficha de SCOUT propone «recorrer los archivos hasta el primero que
dé portada» (S2) como mejora: **ya está en `main`** (#419: `MAX_INTENTOS_PORTADA = 3`, `MAX_EVALUADOS_PORTADA = 50`,
`es_candidato_de_portada`). Esta historia solo tiene que **enseñar al recorrido a abrir un RAR** y a **no reabrir los
que fallaron**.

**Qué no cambia.** CBZ y ZIP (misma portada, mismos topes, mismo código); `tratamiento()` de un RAR (solo hash: leer una
portada no es indexar); «Por revisar» (salvo que el PO decida lo contrario en D-6); ninguna escritura en el archivo ni
junto a él; sin red.

**Entrega.** Una historia = **una PR** (regla del PO), con cuatro commits (§10). Cuatro puertas antes de fusionar: la
revisión de SecOps de `unar`/GNUstep (DoR pendiente de #418), la medición en la Pi (AC-22..24), el fixture RAR creado a
mano con permiso del PO (D-4) y la decisión de D-1..D-6.

**Las seis decisiones, en una línea cada una** (detalle en §11):
| # | Decisión | Recomendación |
|---|---|---|
| D-1 | Dónde se guarda el fallo recordado | **Fichero de marca en la caché de portadas** (`covers/v3/fallos/<file_id>.json`), no en la base de datos ni en memoria |
| D-2 | Cómo sustituir lo que ya está en `covers/v2` | **Subir a `v3`** y que **solo las portadas sacadas de un archivo** vivan en `v3`; la externa va aparte |
| D-3 | Un envoltorio de `unar` para #418 y #344 | **Sí:** `utils/lector_rar.py`, con listar + leer una entrada verificada |
| D-4 | Cómo se prueba en CI sin RAR | **Pruebas con `unar` falso para la lógica + 3 fixtures RAR mínimos + `unar` instalado en el job + prueba que falla si se salta** |
| D-5 | Peso y arranque | **`unar` solo en la etapa `runtime`** del `Dockerfile`; aviso (no bloqueante) en `/api/health` si falta |
| D-6 | Miniatura de RAR en «Por revisar» | **No en esta historia** (cada tarjeta lanzaría un `unar` y no hay caché de disco); historia aparte |

---

## 1. Problema y resultado deseado

### 1.1 Hecho verificado en `main` `488cb03`

| # | Hecho | Evidencia |
|---|---|---|
| V1 | Solo `.cbz` y `.zip` tienen extractor de portada; un `.cbr`/`.cb7` cuyo contenido es ZIP se lee (#307). Un RAR real devuelve `None` | `utils/cover.py:72` (`EXTENSIONES_CON_PORTADA`), `:111-172` (`extract_cover_thumbnail`) |
| V2 | **#419 ya está:** la portada de serie recorre los archivos no ausentes por `sort_order` (nulos al final, `File.id` de desempate), con `MAX_EVALUADOS_PORTADA = 50` filas y `MAX_INTENTOS_PORTADA = 3` aperturas; `es_candidato_de_portada` descarta sin abrir la ausencia conocida y decide por **firma de 512 bytes** lo desconocido. **La ficha de SCOUT (contrastada en `3562f3a`) describía el `.limit(1)` anterior** | `web/series.py:62-72`, `:112-141` (`_stmt_archivos_de_portada`, `_primera_portada`); `utils/cover.py:95-108` |
| V3 | Cascada de `portada`: (1) `covers/v2/<serie>.jpg` si existe → se sirve sin consultar archivos; (2) archivos → `write_cover_cache` a `v2`; (3) `covers/<serie>.jpg` legada, solo lectura; (4) `cover_url` externa → **se escribe también en `v2`**; (5) 404. «Nunca se cachea una ausencia» | `web/series.py:290-` (docstring y cuerpo) |
| V4 | Consecuencia de V3(4): una serie cuyo primer archivo era ilegible y que tenía `cover_url` **guarda su portada externa en `v2`**, y `v2` no se regenera si existe. Es el mismo bloqueo que menciona el encargo para «la portada de un número posterior» | `web/series.py` (rama 4), `utils/cover.py:190` |
| V5 | Topes ya existentes que un RAR debe igualar: `MAX_PIXELES_PORTADA = 40 000 000`, `MAX_ENTRADA_LEIDA = 32 MiB`, `MAX_RATIO_LEIDA = 100`, `MIN_IMAGENES = 10`, `FRACCION_IMAGENES = 0,8` | `core/formato_contenedor.py:55-72` |
| V6 | Un RAR se reconoce por firma (`Firma.RAR`) y `tratamiento()` lo deja en **solo hash**; `puede_dar_portada(ext, fc)` devuelve `False` para cualquier firma que no sea ZIP | `core/formato_contenedor.py:92-93, 161-180, 294-312` |
| V7 | «Por revisar» llama a `puede_tener_portada` para decidir si pinta `<img>` y a `extract_cover_thumbnail(path, formato_contenido)` a 240 px, **sin caché en disco** (ETag por `mtime` del archivo) | `web/pendientes.py:92`, `:502-515` |
| V8 | `unar` **no está** en `src`, `pyproject.toml`, `Dockerfile` ni CI; solo en `scripts/medicion/evaluacion_rar/`. El `Dockerfile` tiene dos etapas (`builder` con compilador y `runtime` con `libpq5 libxml2 libxslt1.1 tini`); CI usa `apt` solo para `postgresql-client-15` en el job de Postgres | `Dockerfile`; `.github/workflows/ci.yml` |
| V9 | `File` guarda `file_size_bytes` y `sha256_hash` pero **no `mtime`**; `files.metadata` es JSONB (ahí vive `formato_contenido`) | `models/__init__.py` (clase `File`) |
| V10 | Forma medida de invocar `unar`: `unar -q -D -f -i -o <dir> <fichero> <índice>` (**por índice**, no por nombre, porque los nombres llevan corchetes). **`-q` ocultó mensajes en la primera prueba corta** y se rehízo: la integración debe leer `stdout` y `stderr` y no asumir que `-q` los conserva | `scripts/medicion/evaluacion_rar/banco_rar.py:103`; evaluación §7 |
| V11 | Medido en la Pi (#308, 35 muestras RAR): primera página ≤ 0,09 s en caliente y ≈ 0,33 s en frío (disco del sistema); pico ≤ 25,8 MiB; `lsar -j` en un RAR sólido tarda 2,5–4,7 s; `lsar` lista un fichero truncado con código 0 y `unar` devuelve 0 sin escribir si el índice no existe; `RLIMIT_AS` mata a `unar` (SIGSEGV con 96 MiB); `RLIMIT_FSIZE` y matar el grupo de procesos funcionan | evaluación §4.2–§4.4 |
| V12 | Datos de la Pi (encargo, 2026-11-05/06, una instalación): 1094 `.cbr` = 1041 RAR + 53 ZIP; 7 series con 100×100 de Tebeosfera y 2 con Comic Vine a 320 px empiezan por un RAR | encargo |

### 1.2 Resultado deseado, medible

| Objetivo | Métrica | Umbral |
|---|---|---|
| O-1 Portada de archivo para RAR | una serie cuyo primer archivo utilizable es un RAR real obtiene `covers/v3/<id>.jpg` del archivo | 100 % de los RAR sanos del fixture |
| O-2 Nitidez y honestidad | ancho del JPEG; nunca ampliar | 600 px, ≤ ancho del original |
| O-3 Sin red ni escritura junto al original | peticiones externas nuevas / ficheros nuevos fuera de `covers/` | 0 / 0 |
| O-4 Fallos sin 500 | respuestas 5xx por RAR cifrado, roto, sin imágenes, bomba o `unar` ausente | 0 |
| O-5 Fallo recordado | veces que se abre un archivo cuya portada ya falló y no ha cambiado | 0 |
| O-6 Coste en Pi | portada RAR en frío | p95 ≤ 1,0 s (no sólido) y ≤ 6 s (sólido); ΔRSS pico del proceso ≤ 100 MB; imagen ≤ +30 MiB. **Umbrales propuestos desde #308 y BL-PORT1; los ratifica el PO tras medir** |
| O-7 CBZ/ZIP intactos | misma portada y mismo código para todo ZIP | comparación literal |

## 2. Alcance

### 2.1 En alcance
Lector RAR por subproceso (`unar`/`lsar`) acotado y verificado; elegir página y archivo; integrarlo en el recorrido de
#419; fallo recordado por archivo; sustitución de lo ya cacheado (D-2); `Dockerfile` y CI; registro sin rutas; aviso de
salud si falta la herramienta.

### 2.2 Fuera de alcance (no-goals)
1. **Mostrar pequeña y centrada una portada pequeña** (decisión relacionada del PO: historia propia o aquí; **aquí no**,
   hipótesis Q-10).
2. **#435**, conservar una portada buena frente a una peor.
3. **#159**, convertir CBR a CBZ, y cualquier modificación de originales.
4. **#344**, importar paquetes: solo comparte el envoltorio (D-3); su especificación es otra.
5. Biblioteca RAR embebida en el proceso, `unrar` y `rarfile` (descartadas por el PO).
6. Elegir la portada a mano, generar y guardar por archivo al escanear (S3, S4: descartadas «por ahora»).
7. 7z, TAR y formatos sin extensión.
8. Miniatura de RAR en «Por revisar» (D-6, recomendación: no).
9. Reabrir las decisiones del PO del 2026-11-05/06 (tabla §3).

## 3. Decisiones del PO ya tomadas (no se reabren)

| Decisión | Fecha | Dónde queda |
|---|---|---|
| Herramienta: **`unar`**, con las condiciones del §6 de la evaluación: firma, listar antes, una sola página con topes, verificar tamaño + CRC32 + `Image.load()`, leer `stdout` y `stderr`, cachear el listado de los sólidos, sin tocar originales; subproceso con límites (salida, tiempo, muerte del grupo) | 2026-10-28 | FR-01..FR-09 |
| Benchmark: adoptar una sola página como flujo; adaptar nombre de portada y descarte de `__MACOSX` (opcional); sin 500 ante cifrado/multivolumen y con motivo sin rutas; descartar librería RAR embebida y leer entradas enteras en memoria | 2026-11-05 | FR-04, FR-05, FR-14 |
| **Recordar el fallo por archivo** (motivo, sin ruta; no se reabre hasta que cambie). Sustituye, para este caso, al «nunca se cachea una ausencia» de `portada`; criterio 7 del cuerpo | 2026-11-05/06 | FR-10..FR-13 |
| Pendientes de #308 antes de desplegar: revisión de vulnerabilidades de `unar`/GNUstep (SecOps), bomba real, RAR cifrado, lectura en frío desde el USB | 2026-10-28 | §12 (NOT RUN) y puerta de despliegue |

## 4. Requisitos funcionales (EARS)

Origen: I = issue #418, B = benchmark aceptado, E = evaluación de `unar` (§6), V# = verificación, D-n = decisión de §11.

**Reglas de negocio**
- BR-01 La portada de una serie es la de **un archivo** suyo; el RAR entra en el mismo orden y el mismo tope de intentos que el ZIP (#419). *(I, V2)*
- BR-02 **Un RAR se decide por su firma**, nunca por la extensión (53 ZIP disfrazados de `.cbr`; 12 archivos sin extensión). *(E, V6)*
- BR-03 Leer una portada **no** es indexar el contenido: `tratamiento()` no cambia y no se escribe nada de lo leído en `files.metadata`, salvo la marca de fallo de D-1 si el PO la elige allí. *(invariante)*
- BR-04 Lo que no se puede leer **se dice en el registro, sin ruta ni nombre de archivo** (CLAUDE.md §5.4) y la cascada sigue; jamás un 500. *(I, B)*

**Lector RAR (envoltorio compartido, D-3)**
- FR-01 (ubicuo) El sistema deberá tratar como candidato a portada un archivo cuya **firma sea RAR** y cuya extensión sea `.cbr`; con otra extensión (`.rar` o ninguna) solo si el listado lo clasifica como tebeo (FR-04). Un `.cbr` cuya firma sea ZIP sigue el camino ZIP de hoy. *(BR-02, V1, V6; extensiones: Q-8)*
- FR-02 (evento) CUANDO se vaya a leer un RAR, el sistema deberá **listarlo antes** con `lsar -j` y aplicar los topes: nº de entradas ≤ 1000, tamaño declarado total ≤ 500 MiB, tamaño de la salida del listado ≤ 4 MiB, entrada elegida ≤ `MAX_ENTRADA_LEIDA`. SI se superan, ENTONCES no se extrae nada y el motivo es `demasiado_grande`. *(E §6.2; los valores salen de la evaluación: máximo observado 324 entradas y 221 MiB; los fijo yo, ratifica el PO)*
- FR-03 (ubicuo) El listado deberá **verificarse como entrada, no como verdad**: un listado vacío o con menos entradas que las esperadas por un truncado no es «sin imágenes» sino sospechoso. SI el listado termina con código 0 pero la lista está vacía y el archivo pesa más de 1 MiB, ENTONCES el motivo es `ilegible`. *(V11: `lsar` lista un truncado con código 0)*
- FR-04 (evento) CUANDO el listado es válido, el sistema deberá elegir como portada **la primera imagen en orden natural** (`natural_key`, la misma regla que el ZIP) entre las entradas que no sean directorios y tengan extensión de imagen, **descartando** `__MACOSX/` y los nombres que empiezan por `._`. SI no hay ninguna, ENTONCES el motivo es `sin_imagenes`. SI el archivo no es `.cbr` y no cumple `MIN_IMAGENES` ni `FRACCION_IMAGENES`, o contiene entradas con extensión de contenedor (`.cbz`, `.cbr`, `.zip`, `.rar`, `.7z`, `.pdf`, `.epub`), ENTONCES es un paquete y el motivo es `paquete`. *(B adaptar; E §6.2; la preferencia por un nombre de portada queda fuera de v1: Q-9)*
- FR-05 (evento) CUANDO hay una entrada elegida, el sistema deberá **extraerla sola**, por **índice** (nunca por nombre), a un directorio temporal propio y vacío, y **verificar** antes de usarla: que existe un único fichero regular dentro del directorio (sin enlaces simbólicos ni rutas que escapen), que su **tamaño** y su **CRC32** coinciden con el listado, que sus píxeles no superan `MAX_PIXELES_PORTADA` (comprobado con la cabecera, sin decodificar) y que `Image.load()` decodifica. Cualquier discrepancia es un fallo con motivo `ilegible`. Un código de salida 0 **no** es prueba de nada. *(E §6.3-6.4; V10, V11)*
- FR-06 (ubicuo) El subproceso deberá lanzarse **sin shell**, con argumentos en lista, ruta absoluta, entorno mínimo (incluido un `HOME` dentro del directorio temporal), en un **grupo de procesos propio**, con **tiempo máximo** tras el cual se **mata el grupo entero**, **tope de tamaño de fichero escrito** (`RLIMIT_FSIZE` o una vigilancia equivalente) y **tope de salida** de `stdout`/`stderr`. **No** se usará `RLIMIT_AS`. Se leerán `stdout` y `stderr`; no se asumirá que `-q` conserva los mensajes. *(E §4.4, §6.3, §6.5; V10; la mecánica de `RLIMIT_FSIZE` en un proceso con hilos la decide quien implemente, ver R-6)*
- FR-07 (ubicuo) El directorio temporal deberá estar **dentro de la caché de portadas** (nunca junto al original), crearse con permisos privados y **borrarse siempre**, también ante excepción, tiempo agotado o muerte del grupo. El archivo original no se abre para escritura, no se renombra y no se mueve. *(I criterio 2, E §6.7)*
- FR-08 (ubicuo) El sistema no deberá ejecutar a la vez más de **N procesos del lector RAR** en todo el proceso de ZascArr (recomendado N = 1). *(RAM: 25,8 MiB por proceso en una Pi de 512 MB; D-5)*
- FR-09 (ubicuo) El envoltorio deberá exponer una interfaz que **no conozca portadas**: `disponible()`, `listar(ruta)` y `leer_entrada(ruta, entrada, tope)` con errores tipados y motivos en un enum de dominio (`models`/`core`, sin magic strings). #344 la reutilizará. *(D-3)*

**Portada**
- FR-10 (evento) CUANDO la extracción de un archivo RAR falla por una causa **del archivo** (`cifrado`, `multivolumen`, `ilegible`, `sin_imagenes`, `paquete`, `demasiado_grande`, `tiempo`), el sistema deberá **recordar el fallo por archivo**: motivo + huella del archivo (tamaño y `mtime_ns`) + versión del contrato, **sin ruta ni nombre**, en el lugar que decida D-1. *(Decisión del PO; I criterio 7)*
- FR-11 (estado) MIENTRAS exista una marca de fallo vigente para un archivo, el sistema **no deberá abrirlo** ni lanzar `lsar`/`unar`: lo saltará **sin gastar intento** de `MAX_INTENTOS_PORTADA` y seguirá con el siguiente candidato. *(O-5)*
- FR-12 (evento) CUANDO la huella del archivo (tamaño o `mtime_ns`) cambie, o cambie la versión del contrato, la marca deja de ser vigente y el archivo vuelve a intentarse. *(I criterio 7)*
- FR-13 (no deseado) SI la causa del fallo es **del entorno** —herramienta ausente, el proceso muerto por el cgroup, error inesperado— ENTONCES no se recordará como fallo del archivo (se reintentará en la petición siguiente). `herramienta_ausente` se detecta antes de abrir ningún archivo y no gasta intento. *(propuesta mía; Q-7)*
- FR-14 (no deseado) SI falla escribir la marca (disco lleno, permisos), ENTONCES se registra el tipo de error y la petición sigue: ni 500 ni portada perdida. *(patrón de FR-11 de BL-PORT1)*
- FR-15 (ubicuo) La portada obtenida deberá pasar por el **mismo tratamiento que la de un ZIP**: `Image.thumbnail` a `SERIES_COVER_MAX_WIDTH` (600) **sin ampliar**, JPEG calidad 80, escritura atómica en la caché y las mismas cabeceras (`ETag` por `mtime`, `Cache-Control: private, max-age=86400`, 304). *(O-2; BL-PORT1)*
- FR-16 (ubicuo) Un fallo de un candidato RAR deberá seguir la cascada actual (siguiente candidato → caché antigua → portada externa → 404) y **dejar un evento de registro** con `motivo` y `intento`, **sin ruta, nombre de archivo ni nombre de serie**. *(BR-04, B)*
- FR-17 (ubicuo) El sistema deberá presupuestar el tiempo total de generar la portada de una serie (propuesta: 20 s); agotado, no abrirá más candidatos en esa petición (los restantes se intentarán en las siguientes, porque los fallidos quedan marcados). *(R-2)*
- FR-18 (estado) MIENTRAS dos peticiones pidan a la vez la portada de la misma serie, el sistema deberá hacer **una sola** generación y servir el resultado a ambas. *(evita doble coste cuando la ficha y la rejilla se solapan; Q-11)*

**Sustituir lo ya guardado (D-2)**
- FR-19 (ubicuo) `[D-2]` La caché de portadas **de serie sacadas de un archivo** pasará a `covers/v3/<serie>.jpg`; lo que haya en `covers/v2` **no se sirve** ni se borra automáticamente. *(CACHE_VERSION, BL-PORT1 FR-03)*
- FR-20 (ubicuo) `[D-2]` La portada **externa** (`cover_url`) se guardará **fuera de `v3`** (`covers/externa/<serie>.jpg`), de modo que una petición sin portada de archivo siga evaluando los candidatos (barato gracias a FR-11) y una serie cuyo primer archivo pase a ser legible **cambie sola** a la portada de archivo. Si el PO elige la opción A de D-2, este FR se sustituye por «la externa se guarda en `v3` como hoy» y se acepta que no cambia sola.
- FR-21 (ubicuo) La caché antigua `covers/<serie>.jpg` sigue siendo un respaldo de solo lectura que no se copia. *(BL-PORT1 Q-1, sin cambios)*

**CBZ, ZIP y «Por revisar»**
- FR-22 (ubicuo) Para todo ZIP (`.cbz`, `.zip`, `.cbr`/`.cb7` con firma ZIP) el sistema deberá producir **la misma portada, con los mismos topes y el mismo comportamiento ante fallos que hoy**, incluido **reintentar siempre** (la marca de fallo es solo para RAR). *(I criterio 6; Q-7)*
- FR-23 (ubicuo) `[D-6]` `puede_tener_portada` y la ruta de miniatura de «Por revisar» **no cambian**: un RAR sigue sin `<img>` ni petición allí.

**Entorno**
- FR-24 (ubicuo) La imagen del `Dockerfile` deberá incluir `unar` **solo en la etapa `runtime`** y la imagen resultante deberá poder listar y extraer un RAR de prueba como el usuario `zascarr`. *(D-5)*
- FR-25 (estado) MIENTRAS `lsar`/`unar` no estén disponibles, `/api/health` deberá dar un **aviso** (no un error) en `warnings` y el arranque no se bloqueará; el registro lo dirá una vez al arrancar. *(CLAUDE.md §3.2 y §6: observacional, no bloqueante; D-5)*

## 5. Contratos y datos

### 5.1 Ruta `GET /ui/series/{series_id}/portada` (existente)
Mismo contrato. Cascada resultante:
1. `covers/v3/<id>.jpg` → servir (`ETag` por `mtime`, 304). *(sin consultar archivos)*
2. Candidatos (`_stmt_archivos_de_portada`, tope 50) → para cada uno, en orden: omitir ausencia conocida o firma ajena; **omitir si tiene marca vigente (sin gastar intento)**; abrir (ZIP como hoy; RAR con el lector) hasta `MAX_INTENTOS_PORTADA`; el primero que dé portada → `write_cover_cache(v3)` → servir.
3. `covers/<id>.jpg` legada → servir sin copiar.
4. `covers/externa/<id>.jpg` si existe → servir; si no, `cover_url` → descargar → `covers/externa/` → servir.
5. 404.

### 5.2 Marca de fallo (si D-1 = fichero)
`covers/v3/fallos/<file_id>.json`, escrita atómicamente (`_publicar_atomico`), permisos del proceso:
```json
{"v": 1, "motivo": "cifrado", "tamano": 73400320, "mtime_ns": 1730851200123456789}
```
Sin ruta, nombre de archivo ni de serie. `file_id` es el UUID de `File`. Vigente si `tamano` y `mtime_ns` coinciden con `stat()` y `v` es la versión del contrato vigente.

### 5.3 Constantes (orientativas; las fija quien implemente, ratifica el PO tras medir)
| Constante | Valor propuesto | Origen |
|---|---|---|
| `CACHE_VERSION` | `v3` | D-2 |
| `MAX_INTENTOS_PORTADA`, `MAX_EVALUADOS_PORTADA` | 3, 50 (sin cambio) | V2 |
| `RAR_MAX_ENTRADAS` | 1000 | E §4.4 (máx. observado 324) |
| `RAR_MAX_BYTES_DECLARADOS` | 500 MiB | E §4.4 (máx. observado 221 MiB) |
| `RAR_MAX_SALIDA_LISTADO` | 4 MiB | propuesta |
| `RAR_TIMEOUT_LISTAR_S` / `RAR_TIMEOUT_EXTRAER_S` | 15 s / 10 s | E: sólido 4,7 s listar, 3,97 s última página (≈ 3× de margen) |
| `PRESUPUESTO_PORTADA_S` | 20 s | propuesta (FR-17) |
| `RAR_SIMULTANEOS` | 1 | D-5 |
| `CONTRATO_PORTADA_RAR` | 1 | FR-12 |

### 5.4 Datos que se leen
`File.file_path`, `File.id`, `files.metadata["formato_contenido"]`, `stat()` del archivo. **Sin cambios de modelo ni migración** (si D-1 = fichero). Ningún dato nuevo en `files.metadata`.

### 5.5 Decisiones de diseño ya tomadas (no se reabren)
Subproceso, no biblioteca; una página, no el archivo entero; por índice; sin ampliar; sin red; sin escribir junto al original; `tratamiento()` intacto.

## 6. Qué ve la persona
Nada nuevo: el `<img>` de Biblioteca/Inicio/ficha muestra la portada de su archivo en vez de la miniatura de internet, y si no hay ninguna sigue el marcador CSS. El registro (no la pantalla) lleva los motivos. «Mostrar pequeña y centrada» queda fuera (§2.2).

## 7. Requisitos no funcionales
| Id | Requisito | Método |
|---|---|---|
| NFR-01 | Portada RAR en frío: p95 ≤ 1,0 s (no sólido), ≤ 6 s (sólido) | Medición en la Pi (AC-22) |
| NFR-02 | ΔRSS pico del proceso de ZascArr ≤ 100 MB durante una generación (BL-PORT1 midió 65,5 MB a 600; `unar` aporta ≤ 25,8 MiB) | Medición (AC-23) |
| NFR-03 | Imagen ≤ +30 MiB (medido +22,5 MiB) | `docker image ls` (AC-24) |
| NFR-04 | Cero procesos huérfanos tras un tiempo agotado | Prueba con `unar` falso que se cuelga (AC-09) |
| NFR-05 | Registro sin rutas, nombres de archivo ni de serie | `capture_logs` (AC-18) |
| NFR-06 | Sin dependencias Python nuevas | revisión de `pyproject.toml` (AC-26) |

## 8. Criterios de aceptación (Given/When/Then)

**Lector RAR** (`utils/lector_rar.py`; con `unar` falso salvo donde se indica «real»)
- AC-01 *(FR-01)* Dado un archivo con firma RAR y extensión `.cbr`, cuando se evalúa, entonces es candidato; con firma ZIP y extensión `.cbr`, sigue el camino ZIP; con firma RAR y extensión `.txt`, no es candidato.
- AC-02 *(FR-02)* Dado un listado de 1001 entradas, o 501 MiB declarados, o una salida de listado mayor que el tope, cuando se lee, entonces no se extrae nada y el motivo es `demasiado_grande`.
- AC-03 *(FR-03)* Dado `lsar` con código 0 y lista vacía sobre un archivo de 5 MiB, cuando se lee, entonces el motivo es `ilegible`, no `sin_imagenes`.
- AC-04 *(FR-04)* Dado un listado `["10.jpg","2.jpg","__MACOSX/1.jpg","._1.jpg"]`, cuando se elige página, entonces es `2.jpg`; dado un listado sin imágenes, el motivo es `sin_imagenes`; dado un `.rar` con extensiones de contenedor, el motivo es `paquete`.
- AC-05 *(FR-05)* Dado `unar` que sale con 0 pero no escribe nada, o escribe un fichero de otro tamaño, o con CRC distinto, o un enlace simbólico, o dos ficheros, cuando se verifica, entonces es un fallo `ilegible` y no se usa nada.
- AC-06 *(FR-05)* Dada una imagen con más de `MAX_PIXELES_PORTADA` píxeles en su cabecera, cuando se verifica, entonces falla `demasiado_grande` **sin decodificar**.
- AC-07 *(FR-05, real)* Dado un RAR4, un RAR5 y un RAR5 sólido del fixture, cuando se genera la portada, entonces el JPEG decodifica, mide ≤ 600 de ancho y es la primera página.
- AC-08 *(FR-06)* Dados `lsar`/`unar` invocados, entonces el argv es una lista (sin shell), la entrada se pasa por índice, el entorno no hereda `HOME`, y se capturan `stdout` y `stderr`.
- AC-09 *(FR-06, NFR-04)* Dado un `unar` falso que no termina, cuando vence el tiempo, entonces se mata el **grupo** de procesos, no queda ningún hijo vivo y el motivo es `tiempo`.
- AC-10 *(FR-06)* Dado un `unar` falso que escribe más del tope de fichero, cuando se ejecuta, entonces se interrumpe y el motivo es `demasiado_grande`.
- AC-11 *(FR-07)* Dada cualquier salida (éxito, fallo, tiempo agotado, excepción), entonces el directorio temporal ya no existe y no hay ficheros nuevos fuera de `covers/`; el original conserva hash, tamaño y `mtime`.
- AC-12 *(FR-08)* Dadas 5 generaciones simultáneas con N = 1, entonces nunca hay más de 1 `unar` vivo.
- AC-13 *(FR-09)* Dado el módulo, entonces no importa nada de `web/` ni `models` salvo el enum de motivos, y `listar`/`leer_entrada` no mencionan «portada».

**Portada y recuerdo del fallo**
- AC-14 *(FR-10, FR-11)* Dado un RAR cifrado (simulado), cuando se pide la portada dos veces, entonces la 1.ª lanza `lsar`, deja una marca con motivo `cifrado`, y la 2.ª **no** lanza ningún proceso.
- AC-15 *(FR-12)* Dada una marca vigente, cuando cambia el tamaño o el `mtime_ns` del archivo, o `CONTRATO_PORTADA_RAR`, entonces el archivo vuelve a intentarse; si no cambian, no.
- AC-16 *(FR-13)* Dada la herramienta ausente, entonces la petición responde sin 500, no se escribe ninguna marca, y la siguiente petición vuelve a comprobar.
- AC-17 *(FR-14)* Dado un fallo al escribir la marca (`OSError`), entonces hay un registro con el tipo de error y la petición sigue su cascada.
- AC-18 *(FR-16, NFR-05)* Dado cualquier fallo, entonces `capture_logs` (structlog y `logging`) no contiene ruta, nombre de archivo ni de serie, y sí `motivo` e `intento`.
- AC-19 *(FR-11, #419)* Dada una serie con 5 RAR ilegibles seguidos de un CBZ, cuando se piden portadas sucesivas, entonces la 1.ª abre 3 RAR y marca 3, la 2.ª salta los 3 marcados sin gastar intento, abre 2 y llega al CBZ, y sirve la portada del CBZ.
- AC-20 *(FR-15)* Dado un RAR cuya primera página mide 300 px de ancho, entonces el JPEG de `v3` mide 300, no 600; dado uno de 1800, mide 600.
- AC-21 *(FR-16, FR-17)* Dado un candidato que agota `PRESUPUESTO_PORTADA_S`, entonces no se abren más en esa petición y la respuesta usa la cascada (caché antigua / externa / 404), sin 500.

**Coste en la Pi** (NOT RUN hasta medir)
- AC-22 *(NFR-01)* En la Pi, sobre los 34 RAR de #308 y las 9 series reales sin tocar los originales: p95 en frío ≤ 1,0 s (no sólido) y ≤ 6 s (sólido).
- AC-23 *(NFR-02)* ΔRSS pico del proceso durante una generación ≤ 100 MB.
- AC-24 *(NFR-03)* La imagen ARM construida pesa ≤ +30 MiB sobre la actual (594 261 630 B).

**Efectos colaterales y regresión**
- AC-25 *(FR-22, O-7)* Dados los CBZ, ZIP y `.cbr`-ZIP existentes en las pruebas, entonces la portada es byte a byte la de `main` y un ZIP que falla se **reintenta** en la petición siguiente (sin marca).
- AC-26 *(NFR-06)* El diff no cambia `pyproject.toml` y no añade ninguna biblioteca RAR de Python.
- AC-27 *(FR-23, D-6)* Dado un RAR en «Por revisar», entonces `con_portada` sigue siendo `False`, no hay `<img>` y `web/pendientes.py` no lanza ningún subproceso.
- AC-28 *(BR-03)* `tratamiento()` de un RAR sigue siendo «solo hash» y ningún campo de `files.metadata` nuevo aparece tras generar una portada.

**Sustitución (D-2)**
- AC-29 *(FR-19)* Dada una serie con `covers/v2/<id>.jpg` (cualquiera), cuando se pide la portada, entonces `v2` no se sirve y se genera `v3`; `v2` no se borra.
- AC-30 *(FR-20)* Dada una serie sin portada de archivo y con `cover_url`, cuando se pide, entonces la externa se guarda en `covers/externa/` y **no** en `v3`; cuando después su primer archivo pasa a ser legible, entonces la petición siguiente genera `v3` del archivo y lo sirve.
- AC-31 *(FR-21)* La caché antigua se sirve solo si no hay `v3` ni candidato utilizable, y no se copia.

**Entorno**
- AC-32 *(FR-24)* Dada la imagen construida, entonces `docker run … lsar --version` funciona como `zascarr` y el estrato `builder` **no** contiene `unar`.
- AC-34 *(FR-18)* Dadas dos peticiones simultáneas de la portada de la misma serie, entonces el lector se invoca **una sola vez** y ambas reciben la misma imagen; con dos series distintas, una generación por serie.
- AC-33 *(FR-25)* Con `unar` ausente, `/api/health` responde 200 con un aviso `lector_rar`, y el arranque no falla.

## 9. Plan de pruebas

### 9.1 Pruebas automáticas
| Capa | Qué | Cómo |
|---|---|---|
| Lógica del lector (AC-01..06, 08..13) | listado, topes, elección de página, verificación, argv, procesos, limpieza | **`lsar`/`unar` falsos** (scripts en un `PATH` de prueba) que simulan cada trampa de la evaluación: código 0 sin salida, lista truncada, tamaño/CRC distinto, cuelgue, salida enorme, enlace simbólico. **No necesitan RAR ni la herramienta real** |
| Integración real (AC-07, AC-05 real) | un RAR4, un RAR5 y un RAR5 sólido pequeños | `unar` real; `@pytest.mark.skipif(shutil.which("unar") is None)` **más** la prueba de «no se saltaron» (D-4) |
| Portada y marca (AC-14..21, 25, 29..31) | cascada, marcas, recorrido de #419, `v3`/`externa` | `FakeSession` + lector falso + `tmp_path` para la caché |
| Estructura (AC-26, 27, 32, 33) | diff, «Por revisar», imagen, salud | pytest + un paso de CI de `docker build` y `run` |
| Mutaciones (una prueba por mutación) | no contar el intento de un marcado; reabrir un marcado; marca sin huella; matar solo el proceso y no el grupo; no borrar el temporal; aceptar `rc 0` sin verificar; extraer por nombre; ampliar una imagen pequeña; que «Por revisar» llame al lector; servir `v2` | cada una rompe al menos un AC |

### 9.2 Fixtures y CI (D-4)
- **Fixtures** (`tests/fixtures/rar/`), **creados a mano con permiso del PO** (no puedo generarlos aquí: crear RAR exige `rar`, que no es libre): `minimo_rar4.cbr` (RAR4, 2 JPEG de 8×8), `minimo_rar5.cbr` (RAR5, 2 JPEG) y `solido_rar5.cbr` (RAR5 sólido, 3 JPEG). Imágenes **sintéticas** (sin contenido de la biblioteca real); cada uno < 5 KB; se registran su SHA-256 y el comando que los creó. Faltan por poder fabricarse: **RAR cifrado** y **multivolumen** (quedan NOT RUN reales y se prueban solo con el falso).
- **CI:** el job «Suite unitaria» instala `unar` (`apt-get install -y --no-install-recommends unar`) para que las pruebas reales **no se salten** (el propio `ci.yml` ya recuerda que «una prueba saltada no es una pasada»); un paso final falla si alguna prueba marcada `rar_real` figura como saltada (mismo patrón que `scripts/ci_postgres.py`). El job de Docker construye la imagen y ejecuta `lsar --version` dentro. **No hay construcción ARM en CI**: la imagen ARM solo se verifica en la Pi (AC-24, NOT RUN).

### 9.3 Mediciones en la Pi (puertas)
AC-22..24 más lo pendiente de #308 (§12). Se hacen con el banco existente (`scripts/medicion/evaluacion_rar/`), sobre copias o con la biblioteca montada solo lectura, **con autorización por tanda** (memoria `reference_acceso_a_la_pi`).

## 10. División en PR

Una historia = **una PR** (regla del PO). Cuatro commits, en este orden:
1. **Lector RAR** (`utils/lector_rar.py` + motivos + pruebas con `unar` falso). Sin tocar `web/`.
2. **Fixtures + CI** (RAR mínimos, `apt` en el job, prueba anti-salto).
3. **Portada de serie** (`web/series.py`, `utils/cover.py`: candidato RAR, marca de fallo, `v3`/`externa`). Con `unar` falso y real.
4. **Imagen y salud** (`Dockerfile` runtime, aviso en `/api/health`, `docs/design/ui-migracion.md` si procede, `docs/design/especificacion-BL-PORT3.md`).

**Puertas de fusión:** pruebas verdes en CI sin saltos; los tres fixtures RAR creados a mano (D-4, aceptados por el PO); la revisión de SecOps del diff. Las decisiones D-1..D-6 y Q-7..Q-11 **ya están tomadas** (§11).

### 10.1 Qué queda ANTES DE DESPLEGAR (no impide fusionar; impide poner `unar` en la Pi)
| # | Puerta | Quién / cómo | Estado |
|---|---|---|---|
| P-1 | **Revisión de SecOps de vulnerabilidades de `unar` y del runtime de GNUstep** (12 paquetes; superficie nueva: un parser de archivos de terceros), incluida la comprobación de que no escribe en `$HOME` | SecOps; DoR pendiente de #418 | **NOT RUN** |
| P-2 | **Bomba de descompresión real** | No hay forma de crear una con las herramientas libres; se cubre con topes (FR-02, FR-05, FR-06) y se prueba solo con el `unar` falso. Decisión de despliegue: aceptar el riesgo residual con los topes, o conseguir una muestra | **NOT RUN** |
| P-3 | **RAR cifrado** (y multivolumen) | 0 de 1208 en el censo y no se puede fabricar uno sin `rar`; solo prueba con el falso. Cómo informa `lsar -j` del cifrado: sin probar | **NOT RUN** |
| P-4 | **Lectura en frío desde el disco USB de la biblioteca** (todo lo medido fue desde el disco del sistema) | Medición en la Pi con autorización por tanda | **NOT RUN** |
| P-5 | **Imagen ARM**: construcción, tamaño (≤ +30 MiB) y `lsar` dentro como `zascarr`; la CI solo construye la del ejecutor | Construcción en la Pi (AC-24, AC-32) | **NOT RUN** |
| P-6 | Medición del coste integrado (AC-22, AC-23) sobre las series reales sin tocar originales | Pi, autorización por tanda | **NOT RUN** |
| P-7 | Orden de despliegue con #435 (§16) | PO | Recomendación en §16 |

## 11. Registro de decisiones (resueltas por el PO el 2026-11-06, «sí a todo»)

| Decisión | **Aceptada** | Alternativas descartadas |
|---|---|---|
| D-1 dónde se guarda el fallo | **C** fichero de marca `covers/v3/fallos/<file_id>.json` (motivo + tamaño + `mtime_ns` + versión) | A `files.metadata` (escribe en la base desde un `GET`; carrera con importer y `rellenar-formato.sh`; `File` no guarda `mtime`); B memoria del proceso (se pierde al reiniciar) |
| D-2 sustituir lo guardado | **B** `CACHE_VERSION = v3` solo para portadas de archivo; externa en `covers/externa/` | A solo subir a `v3` (el bloqueo se aplaza: la externa en `v3` no cambia sola); C sidecar con revalidación en cada petición (consulta archivos en caliente) |
| D-3 envoltorio | **Sí**, `utils/lector_rar.py`, interfaz sin portadas | Un lector por historia (#418 y #344 duplicarían procesos, limpieza y trampas) |
| D-4 CI sin RAR | `unar` falso + **3 RAR mínimos a mano** + `unar` en el job + prueba anti-salto | Solo `skipif` (la parte real quedaría sin ejecutar sin que nadie lo vea); CI sin herramienta |
| D-5 peso y arranque | `unar` solo en la etapa `runtime`; `RAR_SIMULTANEOS = 1`; aviso no bloqueante en `/api/health` | Instalarlo también en `builder` (no lo necesita); N = 2 (+26 MiB en una Pi compartida); fallar al arrancar si falta (contra CLAUDE.md §3.2) |
| D-6 «Por revisar» | **No en esta historia** (camino nuevo; `extract_cover_thumbnail` y `puede_tener_portada` no cambian) | Que el RAR gane miniatura allí: un `unar` por tarjeta y sin caché de disco |
| Q-7..Q-11 | Valores por defecto de §11.2 | Memoria también para ZIP; nombre de portada en v1; «pequeña y centrada» aquí |

A partir de aquí se conserva el razonamiento original de cada decisión (con sus opciones) como registro.

### 11.1 Las seis del encargo (propuse y justifiqué; aceptadas)

**D-1 — Dónde se guarda el fallo recordado y cómo se detecta que el archivo cambió**
| Opción | Cómo | Pros | Contras |
|---|---|---|---|
| **A** `files.metadata["portada_fallida"]` | clave JSONB con motivo + `file_size_bytes`/`mtime` | Una sola fuente; sobrevive a vaciar la caché | **Escribe en la base desde un `GET`** (el commit de `get_db` llega tras la respuesta); `files.metadata` lo escriben también el importer y `rellenar-formato.sh`: un `UPDATE` que reescriba el objeto entero puede pisar la clave, o ella otra (hay que usar un `||` atómico); y `File` no guarda `mtime` |
| **B** memoria del proceso | diccionario `file_id → huella+motivo` | Cero escrituras, cero esquema | Se pierde en cada reinicio (tras `update.sh` se reabrirían los RAR sólidos, segundos cada uno); un solo worker lo permite, pero no sobrevive |
| **C (recomendada)** fichero de marca en la caché | `covers/v3/fallos/<file_id>.json` con motivo + tamaño + `mtime_ns` + versión | Mismo patrón y misma carpeta que la portada (ya se escribe desde un `GET` con `write_cover_cache`); atómico; sobrevive a reinicios; sin migración; si se vacía la caché se reintenta (correcto) | Un fichero pequeño por archivo fallido; hay que decidir la limpieza de huérfanos (fuera de v1, inofensivo) |
| **Recomiendo C.** Detecta el cambio con `stat()` (tamaño + `mtime_ns`) más una **versión del contrato** para reintentar si cambian los topes o la herramienta. Las causas del **entorno** (herramienta ausente, proceso muerto) no se recuerdan (FR-13). Coste de decisión: nada de esquema. Efecto: AC-14, AC-15, AC-17. |

**D-2 — Sustituir lo ya guardado en `covers/v2`**
Hecho nuevo (V4): `v2` guarda también las portadas **externas**, así que no solo una portada de «un número posterior» bloquea el cambio: **también la externa**.
| Opción | Cómo | Resultado |
|---|---|---|
| **A** subir a `v3` y dejarlo | `CACHE_VERSION = "v3"` | Todas las series se regeneran una vez con el algoritmo nuevo (RAR incluido). **Pero** una serie sin portada de archivo guardaría su externa en `v3` y **no cambiaría sola** si su primer archivo pasa a ser legible (el mismo bloqueo, aplazado) |
| **B (recomendada)** `v3` solo para portadas de archivo; la externa en `covers/externa/` | además de A, separa el origen | Mientras no haya portada de archivo, cada petición reevalúa los candidatos (barato: 1 consulta + `stat()` de ≤ 50 marcas, sin abrir los fallidos) y la serie **cambia sola** cuando un archivo se hace legible; converge aunque haya más de 3 RAR ilegibles (AC-19, AC-30) |
| **C** sidecar con el archivo de origen y revalidación en cada petición | JSON junto a `v3` | Detecta cambios en cualquier serie, pero consulta archivos en **cada** petición caliente y complica el contrato |
| **Recomiendo B.** Coste: toca el contrato de BL-PORT1 (la externa ya no vive en `v2`/`v3`) y añade una carpeta. Límite que se acepta en ambas: una serie con portada de archivo en `v3` no cambia sola si un archivo anterior al elegido se hace legible después; se arregla borrando su `v3` (fuera de alcance: botón de «volver a leer la portada»). `v2` queda huérfano (no se borra solo). |

**D-3 — Un único envoltorio de `unar` compartido con #344**
**Sí.** `src/zascarr/utils/lector_rar.py` (utilidades con E/S, no `core/`, que es puro; no `services/`, que lleva base de datos). Interfaz **sin portadas**: `disponible()`, `listar(ruta) → Listado` (entradas con índice, nombre, tamaño, CRC32, si es directorio, si está cifrada), `leer_entrada(ruta, entrada, tope) → bytes` ya verificada (tamaño + CRC32), y un `MotivoRar` en `models/__init__.py` (CLAUDE.md §2). #344 añadiría, si lo necesita, `leer_entradas(...)` sin cambiar lo existente. Los topes y tiempos son parámetros con los valores de §5.3. **Coste de no hacerlo:** dos copias del manejo de procesos, de la limpieza y de las trampas de `unar`. Efecto: FR-09, AC-13.

**D-4 — Cómo se prueba en CI sin RAR**
**Recomiendo** combinar: (1) la lógica con `lsar`/`unar` **falsos** (la mayoría de los AC, sin RAR); (2) **tres RAR mínimos creados a mano** (permiso del PO), con SHA-256 documentado; (3) **`unar` instalado en el job** de la suite unitaria; (4) un paso que **falla si una prueba `rar_real` se salta**. Alternativa «solo saltar si falta»: deja la parte real sin ejecutar en CI sin que nadie lo vea (el propio repo lo evita). **Imagen Docker en CI:** el job de Docker ya construye la imagen; se añade `docker run … lsar --version` y se acepta que **ARM no se construye en CI** (NOT RUN; se mide en la Pi). Coste: ~12 paquetes más en un job y ~15 KB de binarios en el repo. Efecto: AC-07, AC-32.

**D-5 — Peso y arranque**
- **Imagen:** `unar` **solo en la etapa `runtime`** del `Dockerfile` (`apt-get install -y --no-install-recommends unar` junto a `libpq5 libxml2 libxslt1.1 tini`); la etapa `builder` no lo necesita. +22,5 MiB y 12 paquetes (GNUstep) ya aceptados por el PO. Los paquetes de Debian bookworm existen para arm64 (medido en la Pi); verificar con una construcción en la Pi (AC-24).
- **Arranque:** `unar` se arranca **a demanda** por subproceso; el arranque de la aplicación no cambia (coste ≈ 0,2–0,3 s solo en la primera lectura en frío). Se propone un **aviso (no un error)** en `/api/health` si falta la herramienta y un registro único al arrancar (FR-25).
- **RAM:** `RAR_SIMULTANEOS = 1` (25,8 MiB por proceso; una rejilla fría de 11 series RAR tardaría ~4 s en serie, aceptable porque es perezosa y se cachea). **Coste de decisión:** Con N = 2 se gana latencia a cambio de otros 26 MiB en una Pi que comparte con Transmission, aMule, Prowlarr y Kavita.
- **`HOME`:** GNUstep puede escribir ajustes en `$HOME`; el entorno del subproceso lleva un `HOME` temporal (FR-06). **NOT RUN:** que no escriba nada.

**D-6 — Efecto colateral en «Por revisar»**
Si `extract_cover_thumbnail` aprendiera RAR, `web/pendientes.py` (que llama a `puede_tener_portada` y a esa función) pintaría una miniatura de cada RAR. Cuesta un `unar` por tarjeta (50 por página) y esa ruta **no tiene caché de disco** ni marca de fallo. **Recomiendo no hacerlo aquí:** el RAR vive en un camino nuevo (`utils/lector_rar` + `_primera_portada`), `extract_cover_thumbnail` y `puede_tener_portada` no cambian (FR-23, AC-27), y «Por revisar» con RAR queda como historia propia con su caché. **Alternativa:** incluirlo ahora con el semáforo de FR-08 y la marca de FR-10 compartidos; sube el alcance (UI y consultas) y la medición de AC-22. Efecto: ninguno visible hoy.

### 11.2 Decisiones menores (aceptadas con su valor por defecto)
| Id | Pregunta | Valor aceptado |
|---|---|---|
| Q-7 | ¿La memoria del fallo es solo para RAR o también para ZIP? (FR-22 «CBZ y ZIP no cambian») ¿Y se recuerdan `tiempo`, que depende del disco, y no los motivos del entorno? | **Solo RAR**; se recuerda `tiempo` (la versión del contrato permite reintentar si se suben los topes); no se recuerdan herramienta ausente ni error inesperado |
| Q-8 | ¿Qué extensiones con firma RAR se intentan? | `.cbr` siempre; `.rar` y sin extensión solo si el listado cumple `MIN_IMAGENES`/`FRACCION_IMAGENES` y no es un paquete (igual que el ZIP con extensión que no es de tebeo) |
| Q-9 | La ficha acepta «preferir una imagen con nombre de portada» (**adaptar**) y descartar `__MACOSX` (opcional). Preferir un nombre de portada en RAR pero no en ZIP daría una portada distinta al convertir un CBR a CBZ (#159) | **No en v1** para ninguno; sí descartar `__MACOSX` y `._*` en RAR. El nombre de portada se reabre para ZIP y RAR a la vez |
| Q-10 | ¿«Pequeña y centrada» va aquí? | **No**, historia propia |
| Q-11 | ¿Una sola generación por serie concurrente (FR-18) entra en esta historia? | **Sí** (evita doble coste con ficha + rejilla), prueba AC-34 |

## 12. NOT RUN / no verificado
1. Nada ejecutado: ni la suite, ni `unar`, ni ZascArr, ni la Pi. Todo lo de §1.1 es lectura en `488cb03`.
2. **Pendiente de #308 / DoR de #418:** revisión de vulnerabilidades de `unar`/GNUstep (SecOps); bomba de descompresión real; **RAR cifrado** (0 de 1208 en el censo; el fixture no se puede fabricar); **multivolumen**; lectura en frío desde el USB.
3. Cómo informa `lsar -j` de un archivo cifrado o multivolumen: no probado; mientras tanto el motivo puede salir como `ilegible`.
4. Que `unar`/GNUstep **no escriba en `$HOME`** ni en ningún otro sitio fuera del directorio dado.
5. La mecánica exacta de `RLIMIT_FSIZE` desde Python en un proceso con hilos (R-6).
6. Imagen ARM: construcción y tamaño; la CI solo construye la imagen del ejecutor.
7. Calidad real de la primera página de los CBR de la Pi; los umbrales de NFR-01..03 son propuestos.
8. Los valores de `RAR_*` de §5.3 los fijo yo a partir de #308; no hay medición de bombas ni de discos USB.
9. Convergencia en la Pi con varias series de más de 3 RAR ilegibles seguidos.
10. Que las pruebas «existentes» citadas se ejecuten en la CI de `main` (no re-verificado).

## 13. Supuestos y riesgo si son erróneos
| Id | Supuesto | Riesgo |
|---|---|---|
| S-1 | `lsar -j` devuelve índice, nombre, tamaño y CRC32 por entrada (la evaluación lo usó así) | Si falta el CRC, FR-05 pierde la verificación de contenido y solo queda `Image.load()` |
| S-2 | `unar` admite el patrón `-D -f -i -o <dir> <fichero> <índice>` (banco_rar.py:103) sin `-q` | Las opciones exactas se fijan al implementar con la medición de #308 |
| S-3 | El cgroup del contenedor mata al proceso si se excede la memoria (no se usa `RLIMIT_AS`) | Un pico no previsto afectaría a todo el contenedor |
| S-4 | `v3` regenerado una vez no sobrecarga la Pi (200 series × ≤ 0,33 s + Pillow) | La primera carga tras el despliegue sería lenta (lazy; la rejilla pide imágenes en paralelo) |
| S-5 | El PO mantiene `MAX_INTENTOS_PORTADA = 3` para RAR y ZIP juntos | Con RAR sólidos de 4 s, 3 intentos son hasta 12 s; FR-17 lo acota |
| S-6 | Una sola instalación de la Pi es representativa | Los umbrales pueden requerir ajuste |

## 14. Riesgos
| Id | Riesgo | Mitigación |
|---|---|---|
| R-1 | Vulnerabilidad en `unar`/GNUstep (superficie nueva: un parser de archivos de terceros) | Revisión de SecOps antes de desplegar; subproceso sin shell, sin red, grupo propio, `HOME` temporal, tope de salida, de tiempo y de tamaño; originales de solo lectura; sin `RLIMIT_AS` |
| R-2 | Latencia en frío: sólidos de 4 s × 3 intentos en una sola petición | FR-17, FR-11 (los fallidos no se reabren), perezosa y cacheada |
| R-3 | La rejilla fría lanza decenas de generaciones | FR-08 (N = 1), FR-18 (una por serie) |
| R-4 | Marca de fallo que oculta una portada que sí se podría leer | Huella (tamaño + `mtime_ns`) + versión del contrato; las causas del entorno no se recuerdan |
| R-5 | `lsar` truncado con código 0 / `unar` 0 sin escribir | FR-03, FR-05, AC-03, AC-05 |
| R-6 | Aplicar `RLIMIT_FSIZE` con `preexec_fn` en un proceso con hilos es frágil en Python | Decidir al implementar (`prlimit`, o vigilar el directorio temporal y matar el grupo); AC-10 lo prueba con cualquiera |
| R-7 | Cambiar el contrato de caché (D-2 B) rompe supuestos de BL-PORT1 | AC-29..31; actualizar `especificacion-BL-PORT1.md` (nota) |
| R-8 | Desajuste entre `es_candidato_de_portada` (decide) y el lector (abre) | Una sola función de decisión para ambos (BR-02) |
| R-9 | Rutas o nombres en el registro (CLAUDE.md §5.4) | FR-16, AC-18 |

## 15. Registro de decisiones y trazabilidad
| Objetivo | FR | AC | Commit |
|---|---|---|---|
| O-1 portada de archivo para RAR | 01–05, 15, 19–20 | 01–07, 20, 29–31 | 1, 3 |
| O-3/O-4 sin red, sin escritura, sin 500 | 06–07, 13–14, 16–17 | 08–11, 16–18, 21 | 1, 3 |
| O-5 fallo recordado | 10–13 | 14–19 | 3 |
| O-6 coste en Pi | 08, 17–18, 24–25 | 12, 22–24, 32–34 | 1, 4 |
| O-7 CBZ/ZIP intactos | 22–23 | 25–28 | 3 |
| Reutilización con #344 | 09 | 13 | 1 |

**Autorrevisión.** *Vaguedad:* los umbrales de NFR y de topes son números propuestos con su origen, no adjetivos. *Compuestos:* FR-10..FR-13 separan guardar, saltar, reintentar y no recordar. *Contradicciones a la superficie:* (a) la ficha daba por pendiente S2 y **ya está en `main`** (#419); (b) `v2` también contiene portadas externas, no solo de «un número posterior» (V4), lo que cambia D-2; (c) «Por revisar» ganaría RAR solo si `extract_cover_thumbnail` lo aprende (D-6); (d) el encargo habla de `Dockerfile` multietapa: solo la etapa `runtime` necesita `unar`. *FR sin AC:* ninguno (FR-18 → AC-34, por hipótesis Q-11). *Estado:* v1.0: ninguna decisión abierta del PO; con 10 NOT RUN, supuestos y las puertas de despliegue de §10.1; no cierra el despliegue.

## 16. Cruce con #435 (BL-PORT5): conservar la portada que ya tiene buena resolución

> **No se especifica aquí: es otra historia** (#435, en Backlog, talla S, DoR sin completar: umbral propuesto de 300 px y qué hacer con las `v2` ya escritas). Esta sección solo dice cómo conviven con D-2, para fijar el orden.

### 16.1 Qué pide #435 (leído en el cuerpo de la issue, 2026-11-06)
Si hay una portada previa con ancho ≥ umbral, **se conserva** y no se extrae nada del archivo; si es menor (los 100×100 de Tebeosfera) o falta, sigue la cascada (se extrae del archivo). La caché antigua no se copia ni se modifica (Q-1 de #300). Origen: tras desplegar #419, **5 series pasaron de una portada de Comic Vine de 240–320 px a la primera página de su CBZ**; el PO prefiere no cambiarlas si la previa ya es buena. La issue pide que la regla se aplique también a las series cuyo primer archivo es RAR cuando llegue #418.

### 16.2 Dónde chocan con D-2
| Pieza | Con #418 (D-2 B) solo | Con #435 | Efecto de combinarlas |
|---|---|---|---|
| **Qué se mira antes de los archivos** | `v3` y nada más | `v3`, y **después** «portada previa suficiente» (la antigua `covers/<id>.jpg`; y `covers/externa/<id>.jpg`, si tiene ancho ≥ umbral) | La regla de #435 se inserta entre `v3` y los candidatos; **la misma cabecera de imagen que lee la caché** (sin tocar archivos ni red) |
| **`covers/v3`** | Solo portadas sacadas de un archivo | No cambia: `v3` sigue siendo solo de archivo. **Una portada previa suficiente no se copia a `v3`** | Una serie con previa suficiente nunca escribe `v3` ni abre archivos (ni marca fallos) |
| **`covers/externa`** | Cualquier externa descargada; no bloquea al archivo | Una externa **suficiente** sí lo bloquea, a propósito; una pequeña no | Se conserva la propiedad de D-2 (una externa pequeña cede ante un archivo que se hace legible) y se añade la preferencia del PO para las buenas |
| **`v2` ya escrita** (las 5 series) | D-2 las **ignora** (v3 ≠ v2): se reevalúan una vez | Es justo el problema abierto de #435 («habría que borrar esas `v2`») | **El salto a `v3` resuelve las `v2` ya escritas sin borrar nada**, si la regla de #435 ya está activa en ese despliegue; la antigua sigue ahí porque `v2` nunca la borró |
| **RAR (#418)** | Las 2 series de Comic Vine a 320 px cuyo primer archivo es RAR **pasarían a la primera página del RAR** | Se quedan con la de Comic Vine | Sin #435, #418 repite el efecto que el PO no quiso (2 series de la medición del 2026-11-05/06) |

### 16.3 Recomendación de orden
1. **Fusionar #435 antes que #418** (S, sin dependencias, regla de cascada propia), **y desplegarlas juntas, en la misma ventana**: el salto a `v3` de #418 hace de invalidación de las `v2` ya escritas (nada que borrar a mano, que el PO no ha ordenado) y las 2 series de Comic Vine con RAR no cambian de portada.
2. **Si #435 sale sola antes** (porque #418 espera a SecOps y a la medición, P-1..P-6), las 5 series seguirán con su `v2` local hasta que haya una orden expresa del PO de borrar esas 5 `v2` (con la lista a la vista) o hasta el despliegue de #418. No hay pérdida de datos.
3. **Si #418 saliera sola antes**, las 2 series de Comic Vine con RAR cambiarían a la primera página del RAR y revertirlo exigiría borrar sus `v3` por orden expresa. **No lo recomiendo.**

### 16.4 Qué hay que decidir al implementar (sin cambiar #418 ni #435)
- Una sola función de «portada previa suficiente» que lean las dos historias (no dos reglas).
- El umbral lo decide #435 (300 px propuesto); #418 no lo fija.
- Hallazgo menor de D-2: el salto a `v3` deja `covers/v2` huérfano; las portadas externas que estaban en `v2` se **volverían a descargar** una vez (hay cortesía y semáforo de 2). Si se quiere evitarlo, `v2` puede quedar como respaldo de solo lectura **detrás** de los candidatos y de la antigua (no se puede tratar como «previa suficiente» porque no se sabe si es local o externa). **No cambia la spec aceptada**; lo anoto para el Brain.

## 17. Implementación (PR #455 de #418) — qué se hizo y qué NO se ejecutó

> Nota del implementador (builder). Esta sección no cambia la spec: registra cómo se cumplió, las desviaciones y lo que
> sigue sin comprobarse. Las decisiones D-1..D-6 y Q-7..Q-11 se implementaron tal como se aceptaron.

**Piezas.** `utils/lector_rar.py` (FR-02..09, sin portadas; `MotivoRar` en `models`), `utils/portada_rar.py` (elegir página,
recorte, marca de fallo `covers/v3/fallos/<file_id>.json`, barrido de temporales), `web/series.py` (candidato RAR en
`_primera_portada`, presupuesto de 20 s, una generación por serie, `v3`/`externa`), `utils/cover.py` (`CACHE_VERSION = "v3"`,
`covers/externa` en la **única** lista de previas de #435, `es_candidato_de_portada` acepta el RAR por firma), `api/health.py` +
`main.py` (aviso `lector_rar`, registro único, barrido), `Dockerfile` (`unar` solo en `runtime`), `ci.yml` (`unar` en el job, prueba
anti-salto, `lsar` en la imagen).

**Decisiones de implementación que la spec dejaba abiertas.**
- *R-6 (`RLIMIT_FSIZE`):* sin `preexec_fn` en un proceso con hilos; lo escrito se **vigila** (sondeo del temporal cada 20 ms) y
  se mata el grupo al pasar el tope (AC-10).
- *Memoria (dictamen SecOps M-1):* el mismo bucle lee la memoria residente del proceso y sus descendientes (`/proc`) y mata el
  grupo por encima de 128 MiB (máximo medido en #308: 25,8 MiB). Sigue sin `RLIMIT_AS`.
- *Espera del turno (SecOps M-2 / QA F-1):* el semáforo de un lector se espera como mucho 2,5 s; si no, `OCUPADO`: no gasta
  intento, no deja marca, no se cachea la ausencia (404 `no-store`) y no se abren más RAR en esa petición.
- *Valores de `lsar` (SecOps B-1/B-2):* índice dentro de rango, tamaño ≥ 0 y ruta absoluta, o `ilegible`.
- *Marca de `tiempo` (SecOps B-3):* caduca a las 24 h (guarda su fecha); los demás motivos duran hasta que cambie el archivo.
- *Temporales huérfanos (SecOps B-4):* se barren al arrancar.
- *Una sola función de decisión (R-8):* `es_candidato_de_portada` y `_primera_portada` usan `es_rar_candidato`.
- *CRC32:* la primera clave de la entrada de `lsar -j` que lleve «CRC» (confirmada con `unar`/`lsar` reales: `RAR5CRC32`/`CRC32`).

**Desviación de AC-07 (RAR 5 sólido).** `unar` **no extrae** un RAR 5 sólido (probado con `solido_rar5.cbr`, rar 7.11): «Attempted to
read more data than was available», con `unar`/`lsar` **v1.10.1** (Debian bookworm, imagen de producción; Debian empaqueta la 1.10.1
bajo el número 1.10.7) y con **v1.10.8** (CI). Efecto: `ilegible` → marca → cascada, sin 500. Los fixtures reales son cuatro:
`minimo_rar4`, `minimo_rar5`, `solido_rar4` y `solido_rar5` (este último, con `xfail(strict)` que documenta la limitación). Cuántos
RAR 5 sólidos hay en la biblioteca real: no medido.

**Cruce con #435 (QA F-3).** Una portada externa de **≥ 300 px** cuenta como previa suficiente y gana a `v3` y a los archivos: esa
serie no cambia sola a la portada del RAR (lo prevé §16 y lo prueba `test_una_externa_suficiente_se_conserva_sin_abrir_archivos`).
**Coste de desplegar (QA F-2):** `v2` se ignora, así que las series cuya portada vino de `cover_url` y vivía en `v2` se vuelven a
descargar una vez a `covers/externa/`.

**NOT RUN (se suma a §12).**
1. Imagen en ARM y P-1..P-6 de §10.1 (SecOps de `unar`/GNUstep, bomba de descompresión real, RAR cifrado y multivolumen reales,
   lectura en frío desde el USB, medición en la Pi). La imagen x86 la construyó QA (+21,1 MiB).
2. Los seis RAR hostiles de SecOps (traversal, ruta absoluta, enlace, comodines, salto de línea, tamaño falso) con `unar` real:
   se ejecutan por primera vez en la CI.
3. El hash del paquete `rar` 6.24 de RARLAB (usado para los RAR 4) no es verificable contra un valor publicado (`LEEME.md` de los fixtures).
