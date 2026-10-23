# Contrato de #307 — reconocer un ZIP por su contenido (un solo punto de decisión)

> **Estado: PROPUESTA PARA REVISIÓN. No se ha implementado nada**, no hay migración y no se toca ningún fichero del PO. Cierra el contrato que la tarjeta pedía «antes de pasar a Lista para desarrollar» (`benchmark-formatos-contenedor.md` §6.1). Lo que **no** se puede fijar sin datos (umbrales, topes) queda marcado **PENDIENTE de medir** y se mide con `scripts/medicion/censo_zip_por_contenido.py` (§9). Las decisiones que son del PO están en §8 con una recomendación.

## 1. Qué cambia respecto a la tarjeta (datos del censo de cabeceras, 2026-10-23)
La tarjeta partía de **2 ZIP sin extensión** (*Paul Pope*, *Barrio*). El censo de la Pi (1267 ficheros `.cbr`/`.rar`/sin extensión, solo 4 KiB de cada uno) dice otra cosa:

| Hallazgo | Cifra | Consecuencia |
|---|---|---|
| ZIP con extensión **`.cbr`** | **56** | **Ya están registrados** (el importador acepta `.cbr`), pero hoy solo se hashean: **sin portada ni `ComicInfo`**. Es el caso principal |
| ZIP **sin extensión** | 2 | El caso original. No se escanean hoy (la extensión decide) |
| 7z sin extensión | 1 | Solo auditoría |
| Tamaño de esos 58 ZIP | 26 < 50 MB; **15 entre 450 MB y 1,4 GB** | El tope actual (500 MiB descomprimidos **en total**) probablemente los deja sin portada aunque solo se lea una página → §6 |

**Reencuadre:** la mayor parte del valor de #307 es **leer mejor lo que ya está registrado** (56 ficheros), no registrar ficheros nuevos.

## 2. Invariantes (no negociables)
1. **Nunca se renombra, mueve, convierte ni escribe el original.** Todo es lectura.
2. Lectura acotada: la firma son **≤ 8 bytes**; clasificar un ZIP lee **solo el directorio central** (nunca descomprime).
3. Sin dependencias nuevas (stdlib: `zipfile`).
4. Sin migración: el formato real se guarda en `files.metadata` (JSONB).
5. Causa y acción en español llano; nunca «formato no soportado» a secas (CLAUDE.md §6).
6. «Sin magic strings»: los enums nuevos viven en `models/__init__.py` (no son tipos de Postgres: sin migración).

## 3. El punto único de decisión
Módulo nuevo `src/zascarr/core/formato_contenedor.py` (puro, sin base de datos):

```python
firma_de(path) -> Firma                  # ≤ 8 bytes. ZIP | RAR | SIETE_Z | TAR | OTRO | ILEGIBLE
tratamiento(declarada: FileFormat | None, firma: Firma) -> Tratamiento   # PURA, sin E/S: la matriz de §4
clasificar_zip(path) -> ClaseZip         # solo directorio central, con topes (§5, §6)
```
`ClaseZip`: `TEBEO | PAQUETE | NO_TEBEO | CIFRADO | INVALIDO | VACIO | LIMITE`. `Tratamiento`: `LEER_COMO_ZIP | SOLO_HASH | AVISAR`.

**Quién lo usa** (hoy cada uno decide por su cuenta):

| Consumidor | Hoy | Con el contrato |
|---|---|---|
| `core/importer_triage.py::triage` | `ext in {.cbz,.zip}` → abre; si no, solo hash | `firma_de` → `tratamiento`; abre como ZIP si `LEER_COMO_ZIP` |
| `utils/cover.py::puede_tener_portada` / `extract_cover_thumbnail` | solo extensión, sin abrir (a propósito: se llama en listados) | **sin E/S**: lee `metadata.formato_contenido` ya guardado; si no hay, cae a la extensión (como hoy) |
| `services/library_audit.py` (B16) | avisa `.rar`/`.7z`/doble extensión | usa `tratamiento` y añade avisos de §7 |
| `services/importer.py` / `utils/fs.py::listar_comics` | `rglob("*{ext}")` por extensión | **sin cambios** (los 56 ya se listan). Ver D1 para sin extensión |
| `services/tagger.py` | solo escribe si `file_format is CBZ` | **sin cambios** y deliberadamente: `file_format` sigue siendo la extensión **declarada**, así el tagger nunca escribe en un ZIP que se llama `.cbr` |

## 4. Matriz: extensión declarada × firma → tratamiento
| Declarada | Firma | Tratamiento | Nota |
|---|---|---|---|
| `.cbz` | ZIP | `LEER_COMO_ZIP` | como hoy |
| `.cbz` | RAR / 7z / otro | `SOLO_HASH` + `AVISAR` | hoy sale «zip ilegible»; pasa a decir qué es y qué hacer |
| **`.cbr`** | **ZIP** | **`LEER_COMO_ZIP`** (solo si `ClaseZip.TEBEO`) | **los 56**; portada y `ComicInfo`, sin tocar el fichero |
| `.cbr` | RAR | `SOLO_HASH` | como hoy hasta decidir #308 |
| `.cbr` | otra cosa | `SOLO_HASH` + `AVISAR` | |
| `.cb7` | ZIP | `LEER_COMO_ZIP` (si `TEBEO`) | |
| `.cb7` | 7z | `SOLO_HASH` | |
| `.zip` | ZIP | **no se escanea** (ver D2); si ya está en la base, `triage`/portada como hoy | |
| sin extensión / doble extensión | cualquiera | **no se registra**; la auditoría avisa (ver D1) | |
| `.pdf`, `.epub` | — | sin cambios | |

Una carrera (el fichero cambia entre la firma y la apertura) acaba en `BadZipFile`, que `triage` ya captura.

## 5. Clasificar un ZIP (solo directorio central)
| Clase | Regla | Efecto |
|---|---|---|
| `TEBEO` | ≥ **N** imágenes, esas imágenes ≥ **F** del contenido (sin `Thumbs.db`, `.DS_Store`, `ComicInfo.xml`), sin contenedores anidados | portada + `ComicInfo` |
| `PAQUETE` | alguna entrada con extensión de contenedor (`.cbz .zip .cbr .rar .cb7 .7z .tar .epub .pdf`…) | **se marca**, no se extrae portada ni se trata como un tebeo (idea de Kapowarr) |
| `NO_TEBEO` | pocas imágenes o poca fracción | aviso |
| `CIFRADO` | alguna entrada cifrada | aviso: «necesita contraseña; ZascArr no la pide» |
| `INVALIDO` / `VACIO` | no se abre / sin entradas | aviso |
| `LIMITE` | supera los topes (§6) | aviso con el motivo |

**Decisión que se hereda del ensayo:** un `.pdf` o `.epub` dentro de un ZIP cuenta como contenedor y lo hace `PAQUETE` (conservador: se marca, no se registra).
**PENDIENTE de medir:** **N** (propuesto 5) y **F** (propuesto 0,8). Se fijan viendo la distribución de los `.cbz` que ya sabemos que son tebeos (control: 0 falsos negativos) y de los 58 ocultos.

## 6. Topes
- **Hoy:** `MAX_ZIP_ENTRIES = 1000` y `MAX_ZIP_UNCOMPRESSED = 500 MiB` **en total** (`importer_triage.py`).
- **Problema:** 15 de los 58 ZIP ocultos pesan 450 MB–1,4 GB; en un tebeo de imágenes comprimidas lo descomprimido ≈ lo comprimido, así que el tope total los deja sin portada aunque solo se lea **una** página y `ComicInfo.xml`. (El mismo efecto puede estar afectando ya a los `.cbz` grandes: el script lo cuenta en el grupo de control.)
- **Propuesta (PENDIENTE de medir y decisión D3):** mantener las entradas (≤ 1000) y sustituir el total por topes **de lo que de verdad se lee**: la primera página y `ComicInfo.xml` (tamaño descomprimido máximo por entrada y **ratio** de compresión máximo para detectar bombas). Los datos que faltan —entrada mayor, tamaño y ratio de la primera página, y cuántos superan los topes de hoy— los da el script de §9.
- Cualquier cambio de tope de los `.cbz` existentes **actualiza a propósito** `tests/test_formatos_contenedor_hoy.py`.

## 7. Qué se guarda y qué se avisa
**Persistencia (sin migración):** `files.metadata.formato_contenido = {"firma": "zip", "clase": "tebeo", "contrato": 1}`. `file_format` **no cambia** (sigue la extensión declarada). El importador rellena el campo al triar; para los **56 ya registrados** hace falta un **relleno idempotente** en el ciclo del importer (leer 4 bytes de los `.cbr` sin `formato_contenido`).

**Avisos (causa y acción; redacción final con el experto de UX):**
| Situación | Mensaje |
|---|---|
| `.cbr` que es ZIP y `TEBEO` | *(sin aviso; informativo en auditoría)* «Se lee igual que un .cbz aunque se llame .cbr. No se ha cambiado el nombre.» |
| `.cbz` que es RAR | «Se llama .cbz pero por dentro es un RAR. ZascArr todavía no lo abre; sigue en tu biblioteca, solo sin portada.» |
| ZIP `PAQUETE` | «Contiene varios archivos comprimidos (parece un pack de varios números). No se trata como un solo tebeo.» |
| ZIP `NO_TEBEO` / `CIFRADO` / `INVALIDO` / `LIMITE` | una frase de causa + qué hacer, por clase |
| `.tar`, `.cbt`, `.7z` o sin extensión que son contenedores | «Parece un tebeo guardado en otro formato. ZascArr no lo trata como tal y no lo modifica.» |

## 8. Decisiones del PO (con recomendación)
| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D1** | **Sin extensión y doble extensión** (2 ZIP + 1 7z hoy) | (a) solo **avisar** en la auditoría; (b) registrarlos | **(a)**: registrarlos exige un valor nuevo del enum `file_format` (**migración**) y, si se registran como CBZ, el tagger podría **escribir** en un fichero sin extensión |
| **D2** | **`.zip`** (hoy se lee pero no se recorre) | (a) no listarlo y avisar; (b) listarlo si `TEBEO` | **(a)** en esta tarjeta (cambia el tamaño de la biblioteca y la deduplicación) |
| **D3** | **Topes** | (a) dejar el total de 500 MiB; (b) topes por entrada leída | decidir **tras medir** (§9); (b) probablemente |
| **D4** | `.pdf`/`.epub` dentro de un ZIP | (a) paquete; (b) ignorarlos | **(a)**, conservador |
| **D5** | Relleno de `formato_contenido` en los 56 ya registrados | (a) en el ciclo del importer; (b) a demanda | **(a)** |

## 9. Medir antes de fijar nada
`scripts/medicion/censo_zip_por_contenido.py` (solo lectura; directorio central; **no imprime nombres**, solo recuentos; los nombres van a un TSV que es tuyo). Mide cuatro grupos (**`cbz_control`**, **`cbr_zip`**, **`sin_extension`**, **`zip`**) y para cada fichero: entradas, imágenes, anidados, `ComicInfo`, descomprimido, ratio máximo, cifrado, entrada mayor y primera página (tamaño y ratio).

```bash
python3 scripts/medicion/censo_zip_por_contenido.py /media/WDElements/Tebeos --tsv ~/eval-rar/salida/zip-por-contenido.tsv
```
**Qué se decide con el resultado:** (1) N y F: sin falsos negativos en `cbz_control` y una lista revisable en `cbr_zip`; (2) cuántos ficheros superan los topes de hoy y qué topes por entrada los absorben sin abrir la puerta a bombas; (3) cuántos de los 56 traen `ComicInfo.xml` (el beneficio real de leerlos).

## 10. Pruebas (se escriben con la implementación; PASS/FAIL/NOT RUN separados)
| # | Caso | Esperado |
|---|---|---|
| T1 | `firma_de` con ZIP, ZIP vacío, ZIP partido, RAR4, RAR5, 7z, TAR, texto, fichero vacío, ilegible | enum correcto, ≤ 8 bytes leídos |
| T2 | `tratamiento` para todas las celdas de §4 | tabla exacta (función pura) |
| T3 | `clasificar_zip`: tebeo, paquete, no-tebeo, cifrado, vacío, corrupto, límite, `.pdf` dentro | clase de §5 |
| T4 | **Sin descomprimir** (se prohíbe `ZipFile.read/open` en la clasificación) | pasa |
| T5 | Un `.cbr` ZIP con imágenes + `ComicInfo.xml` | `triage` devuelve `ComicInfo` y `width_px`; la portada sale; **hash y mtime del original iguales** |
| T6 | El mismo fichero y el **tagger** | lo salta («solo CBZ declarado») |
| T7 | `.cbz` que es RAR | aviso con causa y acción; no «zip ilegible» a secas |
| T8 | ZIP bomba (entradas, tamaño, ratio) y corrupto | rechazados con aviso, sin extraer |
| T9 | `puede_tener_portada` con `formato_contenido` guardado y sin él | **cero E/S** en ambos casos |
| T10 | Relleno de los registrados: idempotente (segunda pasada no escribe) | pasa |
| T11 | Auditoría: `.tar`, `.cbt`, `.7z` y sin extensión que son contenedores | aviso en lenguaje llano; no registra |
| T12 | Regresión: `tests/test_formatos_contenedor_hoy.py` | se actualiza **a propósito** |
| NOT RUN | Los 58 reales | hasta ejecutar el script en la Pi; **no** se presenta ningún resultado de PC como de la Pi |

## 11. Fuera de alcance
Leer RAR/7z/TAR (#308: `unar` queda como candidato con decisión pendiente; el mismo `firma_de` y `tratamiento` servirán, añadiendo `LEER_COMO_RAR`); renombrar, mover o convertir ficheros; registrar ficheros sin extensión (D1); cambiar el esquema.
