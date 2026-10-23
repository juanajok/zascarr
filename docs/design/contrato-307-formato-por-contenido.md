# Contrato de #307 — reconocer un ZIP por su contenido (un solo punto de decisión)

> **Estado: IMPLEMENTADO (rama `claude/307-formato-por-contenido`, pendiente de revisión). Sin migración y sin tocar ningún fichero del PO.** Se aplicaron las recomendaciones de §8 como valores por defecto (D1a, D2a, D3b, D4a, D5a); el PO no las había contestado, así que **siguen siendo revisables**. Desviaciones respecto a la propuesta, todas descubiertas al implementar y probar: ver §12. Cierra el contrato que la tarjeta pedía «antes de pasar a Lista para desarrollar» (`benchmark-formatos-contenedor.md` §6.1). Umbrales y topes se han **medido en la Pi** el 2026-10-23 con `scripts/medicion/censo_zip_por_contenido.py` (§9); los 20 ficheros que superan el tope de hoy también están medidos. Las decisiones que son del PO están en §8 con una recomendación.

## 1. Qué cambia respecto a la tarjeta (datos del censo de cabeceras, 2026-10-23)
La tarjeta partía de **2 ZIP sin extensión** (*Paul Pope*, *Barrio*). El censo de la Pi (1267 ficheros `.cbr`/`.rar`/sin extensión, solo 4 KiB de cada uno) dice otra cosa:

| Hallazgo | Cifra | Consecuencia |
|---|---|---|
| ZIP con extensión **`.cbr`** | **56** | **Ya están registrados** (el importador acepta `.cbr`), pero hoy solo se hashean: **sin portada ni `ComicInfo`**. Es el caso principal |
| ZIP **sin extensión** | 2 | El caso original. No se escanean hoy (la extensión decide) |
| 7z sin extensión | 1 | Solo auditoría |
| Tamaño de esos 58 ZIP | 26 < 50 MB; **15 entre 450 MB y 1,4 GB** | El tope actual (500 MiB descomprimidos **en total**) probablemente los deja sin portada aunque solo se lea una página → §6 |

**Reencuadre:** la mayor parte del valor de #307 es **leer mejor lo que ya está registrado** (56 ficheros), no registrar ficheros nuevos.

**Medido en la Pi (2026-10-23, solo directorio central):** 308 `.cbz` de control (298 tebeos + 10 sobre el tope de hoy), 56 `.cbr` que son ZIP (46 + 10 sobre el tope) y 2 sin extensión (2 tebeos). **`ComicInfo.xml`: 76 de 298 (25 %) en los `.cbz` de control, 0 de 46 en los `.cbr`-ZIP legibles y 0 de 2 sin extensión** → **ninguno de los 56 `.cbr`-ZIP (46 + los 10 grandes) trae `ComicInfo.xml`, y son la población completa, no una muestra**: para los ocultos el beneficio es la **portada** (y la anchura), no los metadatos. Tampoco lo traen los 10 `.cbz` grandes. **Uno de los 10 `.cbr`-ZIP grandes contiene un contenedor anidado: es un paquete**, escondido hoy bajo «límite».

## 2. Invariantes (no negociables)
1. **Nunca se renombra, mueve, convierte ni escribe el original.** Todo es lectura.
2. Lectura acotada: la firma son **≤ 512 bytes** (los 8 primeros bastan para ZIP/RAR/7z; el TAR lleva `ustar` en el byte 257); clasificar un ZIP lee **solo el directorio central** (nunca descomprime).
3. Sin dependencias nuevas (stdlib: `zipfile`).
4. Sin migración: el formato real se guarda en `files.metadata` (JSONB).
5. Causa y acción en español llano; nunca «formato no soportado» a secas (CLAUDE.md §6).
6. «Sin magic strings»: los enums nuevos viven en `models/__init__.py` (no son tipos de Postgres: sin migración).

## 3. El punto único de decisión
Módulo nuevo `src/zascarr/core/formato_contenedor.py` (puro, sin base de datos):

```python
firma_de(path) -> Firma                  # ≤ 512 bytes. ZIP | RAR | SIETE_Z | TAR | OTRO | ILEGIBLE
tratamiento(declarada: FileFormat | None, firma: Firma) -> Tratamiento   # PURA, sin E/S: la matriz de §4
clasificar_zip(path) -> ClaseZip         # solo directorio central, con topes (§5, §6)
```
`ClaseZip`: `TEBEO | PAQUETE | NO_TEBEO | CIFRADO | INVALIDO | VACIO | LIMITE`. `Tratamiento`: `LEER_COMO_ZIP | SOLO_HASH | AVISAR`.

**Quién lo usa** (hoy cada uno decide por su cuenta):

| Consumidor | Hoy | Con el contrato |
|---|---|---|
| `core/importer_triage.py::triage` | `ext in {.cbz,.zip}` → abre; si no, solo hash | `firma_de` → `tratamiento`; abre como ZIP si `LEER_COMO_ZIP` |
| `utils/cover.py::puede_tener_portada` / `extract_cover_thumbnail` | solo extensión, sin abrir (a propósito: se llama en listados). **`extract_cover_thumbnail` no tiene ningún tope**: `zf.read(pages[0])` | `puede_tener_portada`: **sin E/S**, lee `metadata.formato_contenido` ya guardado; si no hay, cae a la extensión (como hoy). `extract_cover_thumbnail`: **tope por entrada leída** (§6) |
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
**Umbrales, con datos reales de esta biblioteca:** imágenes por fichero **mín 21** (control), **22** (`.cbr`-ZIP) y **62** (sin extensión); fracción de imágenes sobre las entradas **mín 0,95** (control) y **1,00** (ocultos). Cualquier N ≤ 20 y F ≤ 0,9 da **0 falsos negativos**. **Se propone N = 10 y F = 0,8** (margen ×2 sobre el mínimo observado). Límite honesto: **en esta biblioteca no hay ningún ZIP que no sea un tebeo** (298/298 y 46/46 salen `TEBEO`), así que los umbrales **no se han contrastado contra falsos positivos con datos reales**; eso lo cubren solo las pruebas sintéticas (T3). Son parámetros revisables.

## 6. Topes
- **Hoy:** `MAX_ZIP_ENTRIES = 1000` y `MAX_ZIP_UNCOMPRESSED = 500 MiB` **en total**, solo en `triage` (afecta a `ComicInfo.xml` y `width_px`). **La portada no tiene ningún tope.**
- **Medido:** **20 de 366 ZIP** superan el tope total: **10 de 308 `.cbz` de control y 10 de 56 `.cbr`-ZIP** (575 MiB – 1,3 GiB descomprimidos, 138–941 entradas). Los 10 `.cbz` grandes **ya están registrados sin `ComicInfo` ni anchura** por ese tope (la portada sí sale, porque no hay tope); a los 10 `.cbr`-ZIP grandes les pasaría igual.
- **Lo que de verdad se lee es poco:** una página y `ComicInfo.xml`. Sobre los 366 ZIP: primera página **≤ 7,1 MiB** con **ratio de compresión ≤ 1,77** (JPEG/PNG ya comprimidos); la entrada mayor de todas llega a 20 MiB pero **no es la que se lee**. Hay entradas con ratio > 20 (en 6 ficheros) y hasta 82 en un `.cbz` y 293 en un `.cbr`-ZIP, **nunca la primera página**.
- **Entradas:** el máximo observado es **941** de 1000 (en los que superan el tope): **margen del 6 %**, escaso para un integral mayor.
- **Propuesta (decisión D3):** (1) **topes por entrada leída**, en `triage` **y en la portada**: tamaño descomprimido declarado de la entrada **leída** ≤ **32 MiB** (×4,5 sobre la primera página mayor, 7,1 MiB) y ratio ≤ **100** (primera página observada: ≤ 1,77); (2) la lectura se acota con `zf.open(entrada).read(tope + 1)`, de modo que un tamaño declarado falso tampoco ocupa memoria (probado en T8); (3) entradas ≤ **2000**; (4) el total de 500 MiB deja de ser un tope de lectura. Cambia el comportamiento de los `.cbz` existentes (los 10 grandes ganan `ComicInfo` y anchura): `tests/test_formatos_contenedor_hoy.py` se actualiza **a propósito**.

## 7. Qué se guarda y qué se avisa
**Persistencia (sin migración):** `files.metadata.formato_contenido = {"firma": "zip", "clase": "tebeo", "contrato": 1}`. `file_format` **no cambia** (sigue la extensión declarada). El importador rellena el campo al triar; para los **56 ya registrados** hace falta un **relleno idempotente** en el ciclo del importer (leer 4 bytes de los `.cbr` sin `formato_contenido`).

**Avisos (redacción revisada por UX el 2026-10-23; ≤ 2 frases: qué es + qué hacer; lo técnico entre paréntesis; «desde tu ordenador»; sin jerga):**
La garantía va **una vez**, en la cabecera de la sección «Archivos que ZascArr no reconoce» de la auditoría: *«Archivos que ZascArr no puede usar como tebeo. No cambia, mueve ni borra ninguno: si quieres arreglar alguno, hazlo desde tu ordenador.»* (Sustituye a la antigua, que decía que *ninguno* contaba en la biblioteca: ya no es cierto, p. ej. un `.cbz` que es RAR sí está registrado.)

| Situación | Texto |
|---|---|
| `.cbz` (o `.cbr`/`.cb7`/`.zip`) cuyo contenido no concuerda | «Se llama .cbz, pero por dentro es un .cbr (RAR). Sigue en tu biblioteca, aunque por ahora ZascArr no puede sacarle la portada.» |
| Sin final de tebeo, contenido ZIP / RAR / 7z | «Parece un tebeo, pero su nombre no acaba en .cbz (.cbr / .cb7). Para que ZascArr lo tenga en cuenta, cambia el final del nombre a .cbz (.cbr / .cb7) desde tu ordenador.» |
| Sin final de tebeo, contenido TAR | «Parece un tebeo, pero está guardado en un formato (TAR) que ZascArr no usa. Para conservarlo, conviértelo a .cbz con otro programa.» |
| ZIP «pack» | «Es un pack con varios tebeos dentro. ZascArr no lo trata como uno solo: descomprímelo si quieres cada número por separado.» |
| ZIP «no es un tebeo» | «Es un archivo comprimido, pero no parece un tebeo: tiene pocas imágenes o están mezcladas con otros archivos.» |
| Con contraseña | «Tiene contraseña, así que ZascArr no puede abrirlo. Si la conoces, guárdalo de nuevo sin contraseña desde tu ordenador.» |
| Dañado | «Está dañado o incompleto; quizá la descarga no terminó. Prueba a descargarlo de nuevo.» |
| Vacío | «Está vacío: no tiene ninguna página. Prueba a descargarlo de nuevo.» |
| Demasiados archivos | «Tiene demasiados archivos dentro (más de 2000) y ZascArr no lo abre, por precaución. Si es un pack, descomprímelo.» |
| `.rar` / `.7z` por el nombre | «Es un archivo .rar. Si dentro hay un tebeo, cambia el final del nombre a .cbr; si hay varios, descomprímelo.» (`.7z` → `.cb7`) |
| `.tar` / `.cbt` | «ZascArr no usa este formato (TAR). Para conservarlo como tebeo, conviértelo a .cbz con otro programa.» |

**Dos cuestiones que la revisión dejó abiertas (no resueltas aquí):**
1. **Aviso positivo** para un `.cbr` que se lee como ZIP («Se lee como un .cbz aunque se llame .cbr. Todo bien: no hace falta hacer nada.»): UX pide un chip **informativo, neutro (nunca ámbar), solo en Auditoría** y no en los avisos del importador. El texto está en `INFO_CBR_ES_ZIP`, pero **la pantalla no lo muestra todavía**: exige una categoría nueva en el informe de auditoría y en su plantilla (tarjeta aparte).
2. **«Descomprímelo»** para un pack: hay que **verificar** que, tras descomprimirlo en la misma carpeta de la biblioteca, algo recoge los números sueltos (el importador recorre las carpetas de descargas, no la biblioteca; la adopción de la biblioteca es otra ruta). Si hace falta dejarlo en la carpeta de descargas, el texto debe decirlo.

## 8. Decisiones del PO (con recomendación)
| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D1** | **Sin extensión y doble extensión** (2 ZIP + 1 7z hoy) | (a) solo **avisar** en la auditoría; (b) registrarlos | **(a)**: registrarlos exige un valor nuevo del enum `file_format` (**migración**) y, si se registran como CBZ, el tagger podría **escribir** en un fichero sin extensión |
| **D2** | **`.zip`** (hoy se lee pero no se recorre) | (a) no listarlo y avisar; (b) listarlo si `TEBEO` | **(a)** en esta tarjeta (cambia el tamaño de la biblioteca y la deduplicación) |
| **D3** | **Topes** (§6) | (a) dejar el total de 500 MiB y portada sin tope; (b) topes por entrada leída en `triage` y portada, entradas ≤ 2000 | **(b)**: con los datos, los 20 ficheros grandes ganan `ComicInfo`/anchura sin abrir la puerta a bombas, y se cierra la lectura sin tope de la portada |
| **D4** | `.pdf`/`.epub` dentro de un ZIP | (a) paquete; (b) ignorarlos | **(a)**, conservador |
| **D5** | Relleno de `formato_contenido` en los 56 ya registrados | (a) en el ciclo del importer; (b) a demanda | **(a)** |

## 9. Medición
`scripts/medicion/censo_zip_por_contenido.py` (solo lectura; directorio central; **no imprime nombres**, solo recuentos; los nombres van a un TSV que es tuyo). Cuatro grupos (**`cbz_control`**, **`cbr_zip`**, **`sin_extension`**, **`zip`**) y, por fichero: entradas, imágenes, anidados, `ComicInfo`, descomprimido, ratio máximo, cifrado, entrada mayor y primera página (tamaño y ratio).

- **Ejecutado en la Pi (2026-10-23):** 366 ZIP (308 + 56 + 2); no había ningún `.zip`. Resultados citados en §1, §5 y §6.
- **Repetición hecha** (2026-10-23): ya mide también los 20 ficheros que superan el tope de hoy. Resultado en §1 y §6: ninguno trae `ComicInfo.xml`, primera página ≤ 7,1 MiB, un paquete entre los grandes.

Comando (solo lectura, ~2 min en el disco USB):

```bash
python3 censo_zip_por_contenido.py /media/WDElements/Tebeos --tsv ~/eval-rar/salida/zip-por-contenido.tsv
```

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
| T8 | ZIP bomba (entradas, tamaño, ratio), **tamaño declarado falso** (declara 10 KB, expande mucho) y corrupto, **también en la portada** | rechazados con aviso, sin extraer; la memoria no pasa del tope |
| T13 | Un ZIP > 500 MiB declarados con una sola página grande ≤ 32 MiB | `triage` devuelve `ComicInfo` y anchura (hoy: «ignorado»); la portada sale |
| T9 | `puede_tener_portada` con `formato_contenido` guardado y sin él | **cero E/S** en ambos casos |
| T10 | Relleno de los registrados: idempotente (segunda pasada no escribe) | pasa |
| T11 | Auditoría: `.tar`, `.cbt`, `.7z` y sin extensión que son contenedores | aviso en lenguaje llano; no registra |
| T12 | Regresión: `tests/test_formatos_contenedor_hoy.py` | se actualiza **a propósito** |
| NOT RUN | Los 58 reales | hasta ejecutar el script en la Pi; **no** se presenta ningún resultado de PC como de la Pi |

## 11. Fuera de alcance
Leer RAR/7z/TAR (#308: `unar` queda como candidato con decisión pendiente; el mismo `firma_de` y `tratamiento` servirán, añadiendo `LEER_COMO_RAR`); renombrar, mover o convertir ficheros; registrar ficheros sin extensión (D1); cambiar el esquema.

## 12. Implementación y desviaciones (descubiertas al implementar)
**Dónde está:** `core/formato_contenedor.py` (el único punto de decisión), enums `Firma`/`ClaseZip`/`Tratamiento` en `models/__init__.py`, `core/importer_triage.py::triage`, `utils/cover.py`, `services/importer.py` (`formato_contenido` al importar, al reenlazar y `rellenar_formato_contenido`), `services/library_adopter.py`, `services/library_audit.py`, `web/series.py` y `web/pendientes.py`.

**Desviaciones respecto a lo propuesto (con su motivo):**
1. **La clase no bloquea la lectura de un `.cbz`/`.zip` declarado.** La clase `TEBEO` (≥ 10 imágenes, ≥ 80 %) solo es condición para un `.cbr`/`.cb7` que *resulta ser* un ZIP. Un `.cbz` declarado con pocas páginas (un especial de 8) o un pack se lee **como siempre y sin aviso**; su clase queda guardada. Lo detectó `test_naming_core` (el aviso era una regresión).
2. **Un `.cbz`/`.zip` cuyo contenido no es ningún contenedor conocido** (basura, descarga incompleta) sigue **sin hash** y con «zip ilegible», como siempre. El hash es solo para contenedores válidos con otro nombre (un RAR llamado `.cbz`). Lo detectó `test_naming_core`.
3. **`puede_tener_portada` ya conoce la extensión declarada**: un `.cbz` guardado como `no_tebeo`/`paquete` sigue dando portada (como hoy); un `.cbr` ZIP solo si es `tebeo`.
4. **`extract_cover_thumbnail` también acota la lectura** (antes: `zf.read(pages[0])` sin tope): topes de §6 en la portada y en `triage`.
5. **La auditoría** avisa ahora de `.tar`/`.cbt`, de `.cbz`/`.cbr`/`.cb7` cuyo contenido no concuerda y de contenedores sin extensión (el filtro de tamaño mínimo se descartó: se leen ≤ 512 B de todos modos).
6. `natural_key` e `IMAGE_EXTS` se movieron a `formato_contenedor` (se reexportan desde `importer_triage`).

**Pruebas:** `tests/test_formato_contenedor.py` (T1–T4, T8), `tests/test_formato_por_contenido_integracion.py` (T5, T6, T9, T10 y regresiones), `tests/test_formatos_contenedor_hoy.py` y `tests/test_importer_triage.py` (T12 y T13, actualizadas **a propósito**). T7 y T11 están en la caracterización (`.cbz` que es RAR; `.tar`/`.cbt`/sin extensión).

**NOT RUN:** los ficheros reales de la Pi (el relleno de los 56 y las portadas de los 10 ZIP grandes se comprobarán tras el despliegue, que **no** está autorizado aquí); una medición de coste del relleno sobre el USB.
