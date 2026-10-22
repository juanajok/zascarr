# Benchmark y compatibilidad de formatos de contenedor (`.rar`, `.tar`, sin extensión, paquetes) — spike #305

> **Estado: spike de MEDICIÓN y BENCHMARK, sin código de producto.** Las recomendaciones son PROPUESTAS del spike; decide el PO. Entorno de las mediciones: un PC (8 hilos, 31 GB), **no la Pi**; todo con ficheros **sintéticos** en un directorio temporal (ninguna biblioteca real). Ficha según `docs/design/benchmark-referencias.md` (§13 de CLAUDE.md). **NOT RUN** al final: lectura de un RAR real (v4/v5) y mediciones en la Pi.

## 1. Problema observado y datos reales de partida
Censo de la Pi del PO (#297, `docs/design/censo-disco-vs-base-2026-10-22.md`): de los 252 ficheros del disco sin fila en la base, **29 ficheros tienen contenido que ZascArr no conoce**: 21 `.rar` de *One Piece* (uno `.cbz.rar`), 7 novelas gráficas **sin extensión** y 1 `.tar` (*Paracuellos* completo). Con `file(1)`, los 12 sin extensión son 9 RAR (v4 ×7, v2.0 ×1 y v5 ×1), 2 ZIP y 1 7-zip. Son **ficheros**, no 29 tebeos (no se abrió ningún contenedor). Además el disco tiene 1234 `.cbr` (80 % de los 1542 tebeos `.cbr`/`.cbz`): hoy **ningún `.cbr` se abre**.

**Preguntas del spike:** (1) extensión del nombre frente a formato real; (2) un tebeo frente a un paquete con varios; (3) capacidades del lector actual y lo que haría falta; (4) coste y seguridad en la Pi; (5) cómo lo resuelven las referencias.

## 2. Qué hace ZascArr hoy (medido con las funciones reales)
Banco: `scripts/medicion/banco_formatos_comportamiento.py` (sintético; pruebas de caracterización en `tests/test_formatos_contenedor_hoy.py`). Mini-biblioteca con el **mismo contenido** en distintos envoltorios:

| Fichero (qué es de verdad) | ¿Lo recorre el importador? | Hash | ComicInfo | Portada | Auditoría B16 |
|---|---|---|---|---|---|
| `a.cbz` (ZIP con ComicInfo) | sí | sí | **sí** | **sí** | — |
| `b.zip` (ZIP) | **no** | sí | sí | sí | — |
| `c_sin_ext` (ZIP sin extensión) | **no** | sí | no | no | — |
| `d.cbz.rar` (ZIP con doble extensión) | no | sí | no | no | «doble extensión (.cbz.rar)» |
| `e.7z` (7z real) | no | sí | no | no | «formato no soportado (7Z)» |
| `f_7z_sin_ext` (7z sin extensión) | no | sí | no | no | **— (no avisa)** |
| `g.tar` (TAR real) | no | sí | no | no | **— (no avisa)** |
| `h_tar_sin_ext`, `i.cbt` (TAR) | no | sí | no | no | **— (no avisa)** |
| `j.rar` (firma RAR sintética, no legible) | no | sí | no | no | «formato no soportado (RAR)» |
| `k.cbr` (firma RAR sintética como `.cbr`) | **sí** | sí | no | no | — |

Hechos (todos verificados en el código `245402e`):
- **La decisión es por la extensión, no por el contenido.** El importador recorre `COMIC_EXTS = {.cbz, .cbr, .cb7, .pdf, .epub}` (`services/importer.py`). Un ZIP legible sin extensión es invisible aunque su contenido sea un tebeo.
- **Solo se abren ZIP/CBZ.** `triage` (`core/importer_triage.py`) lee ComicInfo y `extract_cover_thumbnail` (`utils/cover.py`, `EXTENSIONES_CON_PORTADA = {.cbz, .zip}`) saca la portada solo de un ZIP. Un `.cbr` se registra pero **solo se hashea** («triaje solo por filename»); no hay lector de RAR (decisión documentada: «NO instalar unrar solo por ComicInfo»).
- Incongruencia: `triage` y la portada aceptan `.zip`, pero el importador **no lo recorre** (`.zip` no está en `COMIC_EXTS`).
- La auditoría (B16, RF-02) ya avisa de `.rar`/`.7z` y de la doble extensión, pero **no** del `.tar`, de los `.cbt` ni de los archivos **sin extensión**.
- La imagen de producción (`Dockerfile`, `python:3.11-slim-bookworm`) solo instala `libpq5 libxml2 libxslt1.1 tini`: **no hay `unrar`, `7z`, `bsdtar` ni `unar`**. Leer RAR o 7z es una dependencia de sistema nueva.
- Protecciones contra bombas ZIP: solo para ZIP (`MAX_ZIP_ENTRIES = 1000`, `MAX_ZIP_UNCOMPRESSED = 500 MiB`). Cualquier otro formato necesitaría las suyas.

## 3. Coste (PC, sintético; la Pi es NOT RUN)
Banco: `scripts/medicion/banco_formatos_coste.py` (400 páginas de ~1 MB de bytes aleatorios ≈ 400 MB por empaquetado; 100 páginas dan los mismos órdenes de magnitud). Pico de memoria (MiB) / tiempo:

| Operación | ZIP (`zipfile`) | TAR (`tarfile`) | 7z no sólido (`7z`) | 7z **sólido** (`7z`) |
|---|---|---|---|---|
| Listar entradas | 13,6 / 0,10 s | 13,4 / 0,25 s | 6,4 / 0,02 s | 6,2 / 0,02 s |
| Primera página (portada) | 14,6 / 0,21 s | 14,2 / 0,28 s | 8,2 / 0,02 s | 8,2 / 0,02 s |
| Última página | 14,6 / 0,21 s | 14,2 / 0,28 s | 8,1 / 0,02 s | **770 / 0,77 s** (400 págs.); **197 / 0,22 s** (100 págs.) |
| SHA-256 en streaming (ya existente) | 7,4 MiB / 4,4 s (400 MB) | | | |

Lectura: ZIP y TAR cuestan unos 14 MiB sin importar el tamaño. En un 7z **sólido** sacar una página tardía **escala con el tamaño del archivo** (≈ 2× el tamaño con dos puntos medidos: 100 → 197 MiB, 400 → 770 MiB), lo que **rebasa el presupuesto de 512 MiB del contenedor** (`docker-compose.yml`) con volúmenes sólidos de unos 250 MB o más. Un RAR sólido puede comportarse igual: **no medido** (no hay herramienta para crear un RAR aquí). Esos 512 MiB son el presupuesto del contenedor, no la memoria física de la Pi.

## 4. Referencias (versión/commit; inspeccionado el código)
| Referencia | Qué hace con estos formatos | Evidencia |
|---|---|---|
| **Kapowarr** V1.3.2 (`main` `c191dda661`, 2026-09-14), **GPL-3.0** | Reconoce como contenedor `.cbz .zip .cbr .rar .cb7 .7zip .7z .cbt .tar.gz .epub .pdf .cba .mobi` (`backend/base/definitions.py`). **Convierte** entre formatos (zip→cbz y rar→cbr por renombrado; zip/cbz→rar/cbr con un ejecutable `rar`) y **extrae paquetes** (`backend/implementations/converters.py`). `archive_contains_issues` **lista** el ZIP/RAR y lo considera paquete de varios números si dentro hay ficheros con extensión de contenedor (`backend/base/files.py`). Lleva en el repositorio los binarios `rar` (`backend/lib/rar_linux_64`, `rar_bsd_64`, `rar_windows_64.exe`); algunos convertidores `supports_32bit=False`. | URLs abajo |
| **Mylar3** v0.8.3 (`master` `cdc94a4442`, 2025-08-17), **GPL-3.0** | Extensiones `.cbr .cbz .cb7` (+ `.pdf`). Lee CBR con la librería Python `rarfile` incluida (`lib/rarfile`), que **depende de `unrar`** (o `unar`; `bsdtar` «tiene un soporte muy limitado de RAR»). `open_archive` usa ZIP si acaba en `.cbz`; si no, `rarfile`, y si falla con `BadRarFile` **prueba a abrirlo como un ZIP «renombrado como rar»** (`mylar/getimage.py`). | URLs abajo |
| **Suwayomi-Server** v2.4.2366 (`master` `6b481e8b62`, 2026-10-21), **MPL-2.0** | Fuente local: carpetas, ZIP/CBZ, RAR/CBR y EPUB (`Archive.kt`: `zip, cbz, rar, cbr, epub`); no 7z ni tar. RAR con `junrar` 8.1.2 (JVM). Su documentación: «se espera mejor rendimiento con directorios y ZIP/CBZ», **RAR5 no soportado todavía** y, si un CBR/RAR falla, «extráelo y vuelve a comprimirlo». | URLs abajo |
| Debian bookworm | `unar` 1.10.7+ds1+really1.10.1-2 (**main**): «zip, RAR, 7z, tar…». `libarchive-tools` 3.6.2-1+deb12u5 (**main**): `bsdtar`. `unrar` 1:6.2.6 es **non-free**. Soporte de RAR5 en `unar` 1.10.1: **no verificado**. | packages.debian.org |

URLs: Kapowarr `https://github.com/Casvt/Kapowarr/blob/c191dda661/backend/base/definitions.py`, `…/backend/implementations/converters.py`, `…/backend/base/files.py`; Mylar3 `https://github.com/mylar3/mylar3/blob/cdc94a4442/mylar/getimage.py`, `…/lib/rarfile/doc/faq.rst`; Suwayomi `https://github.com/Suwayomi/Suwayomi-Server/blob/6b481e8b62/docs/Local-Source.md`, `…/server/src/main/kotlin/eu/kanade/tachiyomi/source/local/io/Archive.kt`.

**Barrera legal (§13):** se ha leído el código para entender el diseño; no se copia ni adapta ninguna implementación. Kapowarr y Mylar3 son GPL-3.0 y Suwayomi MPL-2.0; los binarios `rar`/`unrar` son propietarios (y `unrar` va en `non-free` de Debian): cualquier dependencia nueva debe pasar su revisión de licencia aparte.

## 5. Traducción a ZascArr
| Idea | Referencia | Decisión | Motivo |
|---|---|---|---|
| Listar un contenedor **antes** de decidir si es un tebeo o un paquete (si contiene ficheros con extensión de contenedor) | Kapowarr | **Adaptar** | Resuelve «un tebeo frente a un paquete» sin extraer; en ZascArr solo **lectura** y con topes de entradas/tamaño |
| Probar el formato real cuando el nombre engaña (ZIP «renombrado como rar») | Mylar3 | **Adaptar** y ampliar: mirar la **firma** (bytes mágicos) también para ficheros **sin extensión** | Cubre el caso real del censo (un ZIP sin extensión es legible con la biblioteca estándar, sin dependencias) |
| ZIP/CBZ como formato de primera clase y RAR como «lo mejor que se pueda» con límite RAR5 documentado | Suwayomi | **Adoptar** | Coincide con el coste medido (ZIP barato; RAR/7z con dependencia y riesgo de memoria) |
| Convertir los ficheros del usuario entre formatos (con `rar` propietario) | Kapowarr | **Descartar** | ZascArr no modifica originales sin confirmación y la licencia de `rar` no permite empaquetarlo; la conversión la hace el PO fuera |
| Aceptar `.7z`, `.tar`, `.cbt`, `.cba`, `.mobi`… como contenedores | Kapowarr | **Descartar por ahora** | Sin un caso real mayor que 1 fichero (`.tar`); los `.7z` y `.tar` sin extensión se **avisarían** (no se leerían) |

## 6. Opciones y recomendación (PROPUESTA; decide el PO)
- **A — Sin código.** El PO convierte o renombra **fuera** de ZascArr (ZIP → `.cbz`, RAR → `.cbr`, TAR → ZIP). Un `.cbr` renombrado se registra pero, como todos los `.cbr`, **sin portada ni ComicInfo**. Modifica ficheros del PO: es decisión suya.
- **B — Código pequeño, sin dependencias nuevas (recomendada como primer paso).** (1) Detectar por **firma** los ZIP sin extensión o con doble extensión y tratarlos como CBZ de solo lectura con `zipfile` (cubre *Paul Pope* y *Barrio*, los 2 ZIP sin extensión); (2) ampliar la auditoría (B16) para **avisar** de `.tar`, `.cbt`, `.7z` y archivos sin extensión que son contenedores («parece un tebeo, pero ZascArr no lo trata como tal»); (3) decidir qué hacer con `.zip` (hoy leído por `triage` pero no recorrido). Riesgo bajo; no cambia el esquema ni las dependencias.
- **C — Leer RAR/7z (dependencia nueva).** Daría portada y ComicInfo a los 1234 `.cbr` de la biblioteca (80 % de los tebeos), mucho más que los 29 ficheros del censo. Exige `unar` o `bsdtar` (ambos en `main` de Debian; `unrar` es `non-free`), **topes propios** de entradas/tamaño/memoria, tratamiento de RAR5 y de archivos sólidos (7z sólido medido: ≈ 2× el tamaño en memoria). Solo tras B y con una prueba de RAR real en la Pi.

**Invariantes de ZascArr** (no mentir, no borrar, confirmación, coste Pi): sin modificar ni mover originales; todo contenedor desconocido se **lista y mide antes** de extraer; nada de red; presupuesto de 512 MiB del contenedor; sin dependencia nueva sin justificación (CLAUDE.md §2); en pantalla, causa y acción, nunca «formato no soportado» a secas.

## 7. Casos de prueba antes de implementar
1. (ya, `tests/test_formatos_contenedor_hoy.py`) La tabla de §2 como punto de partida; cada cambio de comportamiento la actualiza a propósito.
2. Un ZIP sin extensión y un ZIP con doble extensión: se detectan por firma y se leen como CBZ (portada, ComicInfo) **sin modificar el fichero**.
3. Un `.tar`, un `.7z` y un fichero sin extensión que **no** es ZIP: la auditoría los avisa con su causa; el importador no los registra.
4. Un ZIP «bomba» (muchas entradas / mucho descomprimido) y un ZIP falsificado (firma ZIP, contenido corrupto): rechazados con aviso, sin extraer.
5. (opción C) RAR v4 y RAR5, sólido y no sólido, con memoria acotada por debajo de 512 MiB medida **en la Pi**; con RAR5 sin soporte: mensaje claro, no un error.
6. Un paquete con varios números (contenedores dentro): se lista y se marca como paquete; no se registra como un solo tebeo.

## 8. NOT RUN y datos que faltan
- **Lectura de un RAR real** (v4, v5, sólido) con `unar`/`bsdtar`/`unrar`: no hay herramienta para crear RAR aquí. Propuesta: probar con **copias** de tres ficheros del PO (uno v4, el v5 y el 7z) en un contenedor desechable con `unar` y `libarchive-tools`, solo lectura (`lsar`, `bsdtar -tf`), sin tocar la biblioteca.
- **Mediciones en la Pi** (`banco_formatos_coste.py` con `PAGINAS=100`): pendientes.
- **`file(1)` de los 21 `.rar` de *One Piece* y del `.tar`**: no se han inspeccionado (versión de RAR, sólidos, contenido).
- **RAR sólido y su memoria**, y el soporte de RAR5 de `unar` 1.10.1: no medidos ni verificados.
- Si los 29 ficheros contienen **imágenes** legibles: no se abrieron.
