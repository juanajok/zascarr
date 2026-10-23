# Contrato de #307 — reconocer un ZIP por su contenido (un solo punto de decisión)

> **Estado: IMPLEMENTADO en la rama `claude/307-formato-por-contenido` (PR #325, EN BORRADOR: no fusionable hasta que el PO decida D1–D5). Sin migración y sin tocar ningún fichero del PO.** **D1–D5 (§8) son PROPUESTAS, no decisiones:** la rama aplica mis recomendaciones solo para que se puedan ver funcionando, y cada una dice qué pasa si el PO elige otra cosa. Desviaciones y hallazgos al implementar y probar: ver §12. **No forma parte de ningún candidato de despliegue.** Cierra el contrato que la tarjeta pedía «antes de pasar a Lista para desarrollar» (`benchmark-formatos-contenedor.md` §6.1). Umbrales y topes se han **medido en la Pi** el 2026-10-23 con `scripts/medicion/censo_zip_por_contenido.py` (§9); los 20 ficheros que superan el tope de hoy también están medidos. Las decisiones que son del PO están en §8 con una recomendación.

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
- **Propuesta (decisión D3), con su definición exacta:**

| Límite | Valor | A qué se aplica | Qué ocurre al superarlo |
|---|---|---|---|
| Entradas por ZIP | ≤ **2000** (máx. medido 941) | se mira en el **registro final del ZIP (EOCD, o ZIP64)** leyendo solo el final del fichero; si declara más, **ni se abre** (`ZipFile()` carga el directorio central entero en memoria antes de poder contar) | clase `LIMITE`; aviso; sin ComicInfo ni portada |
| Directorio central | ≤ **16 MiB** (2000 entradas ≈ 0,3 MiB) | igual: se lee del EOCD/ZIP64 | `LIMITE` |
| Entrada **que se lee** | ≤ **32 MiB** descomprimidos | el tamaño **declarado de esa entrada** (la primera página; `ComicInfo.xml` tiene su propio tope de 1 MiB) y, además, la lectura **no pasa de `tope + 1` bytes** aunque la cabecera mienta (`zf.open(...).read(tope + 1)`) | `EntradaNoLegible`; la página se ignora con aviso |
| Ratio de compresión | ≤ **100** | `tamaño descomprimido / tamaño comprimido` **de esa misma entrada** (la primera página observada: ≤ 1,77) | `EntradaNoLegible` (posible bomba) |
| Píxeles de la miniatura | ≤ **40 Mpx** | `ancho × alto` que declara la cabecera de la imagen (`Image.open` lee solo la cabecera); una página de tebeo de 3000×4500 son 13,5 Mpx | sin miniatura, **sin decodificar** |
| Total descomprimido | **ya no hay** | — | — (era el tope de 500 MiB que dejaba sin `ComicInfo`/anchura a 20 de 366 ZIP) |

**Qué NO acota esto:** el total de lo que contiene un ZIP (solo se lee **una página** y `ComicInfo.xml`); el tiempo de lectura de un disco lento; ni la decodificación de formatos que Pillow lea más despacio de lo que su tamaño sugiere (se acota por píxeles y por bytes, no por tiempo). Cambia el comportamiento de los `.cbz` existentes (los 10 grandes ganan `ComicInfo` y anchura): `tests/test_formatos_contenedor_hoy.py` se actualiza **a propósito**.

## 7. Qué se guarda y qué se avisa
**Persistencia (sin migración):** `files.metadata.formato_contenido = {"firma": "zip", "clase": "tebeo", "contrato": 1}`. `file_format` **no cambia** (sigue la extensión declarada). El importador rellena el campo al triar; para los **56 ya registrados** hace falta un **relleno idempotente** en el ciclo del importer (leer 4 bytes de los `.cbr` sin `formato_contenido`).

**Avisos.** Redacción revisada por UX el 2026-10-23 (≤ 2 frases, lo técnico entre paréntesis, sin jerga), **con un cambio posterior mío**: se quitaron todas las instrucciones del tipo «descomprímelo» o «cambia el final del nombre a .cbz» porque **el recorrido no está verificado y, comprobado, no existe** (§12.4): tras la adopción inicial, nada registra ficheros nuevos de la biblioteca. Una prueba (`test_todos_los_textos_siguen_las_reglas_de_ux`) impide reintroducirlas por fila.
La garantía y el **único camino verificado** van **una vez**, en la cabecera de la sección «Archivos que ZascArr no reconoce»: *«Archivos que ZascArr no puede usar como tebeo. ZascArr no cambia, mueve ni borra ninguno de esta lista. Si arreglas alguno (por ejemplo, lo descomprimes o le cambias el nombre), pon la copia arreglada en tu carpeta de descargas y ZascArr la importará como cualquier descarga.»* La frase habla de la **copia** para no contradecir «no mueve ninguno»: el importador sí **mueve** a la biblioteca lo que encuentra en descargas, pero eso es la copia, no el original de la lista. (La cabecera antigua decía que *ninguno* contaba en la biblioteca: ya no es cierto, p. ej. un `.cbz` que es RAR sí está registrado.)

| Situación | Texto |
|---|---|
| `.cbz` (o `.cbr`/`.cb7`/`.zip`) cuyo contenido no concuerda | «Se llama .cbz, pero por dentro es un .cbr (RAR). Sigue en tu biblioteca, aunque por ahora ZascArr no puede sacarle la portada.» |
| Sin final de tebeo, contenido ZIP / RAR / 7z | «Parece un tebeo, pero su nombre no acaba en .cbz (.cbr / .cb7), así que ZascArr no lo registra.» |
| Sin final de tebeo, contenido TAR | «Parece un tebeo, pero está guardado en un formato (TAR) que ZascArr no usa.» |
| ZIP «pack» | «Es un pack con varios tebeos dentro. ZascArr no lo trata como uno solo ni los separa.» |
| ZIP «no es un tebeo» | «Es un archivo comprimido, pero no parece un tebeo: tiene pocas imágenes o están mezcladas con otros archivos.» |
| Con contraseña | «Tiene contraseña, así que ZascArr no puede abrirlo.» |
| Dañado | «Está dañado o incompleto; quizá la descarga no terminó. Prueba a descargarlo de nuevo.» *(recorrido verificado: ver abajo)* |
| Vacío | «Está vacío: no tiene ninguna página. Prueba a descargarlo de nuevo.» *(ídem)* |
| Demasiados archivos | «Tiene demasiados archivos dentro (más de 2000) y ZascArr no lo abre, por precaución.» |
| `.rar` / `.7z` por el nombre | «Es un archivo .rar: ZascArr no lo registra como tebeo, aunque dentro haya uno.» |
| `.tar` / `.cbt` | «ZascArr no usa este formato (TAR), así que no lo registra como tebeo.» |

**Recorrido verificado** (`tests/test_importer_recorrido_de_descargas_pg.py`, importador real + Postgres real + ficheros sintéticos): (a) el importador recorre las carpetas de **descargas** (`transmission_download_dir`, `amule_incoming_dir`, `downloads_path`), de forma recursiva; (b) una copia buena **entra aunque el dañado siga en la biblioteca** (el dañado no tiene hash, así que la deduplicación por SHA-256 no los confunde) y el dañado **no se toca**; (c) va a **su serie y número** si casan y, si no, a `_Unsorted` («Por revisar»). Además: una copia con el nombre arreglado (`.cbz`) dejada en descargas **se importa y se mueve** a la biblioteca; un fichero sin extensión dejado en descargas **no** se importa; una copia idéntica a un fichero ya registrado se descarta como duplicado y **se queda en descargas**; un pack descomprimido en descargas se importa número a número. **Matices que el coleccionista debe poder entender:** el original no se toca ni se registra, así que quedan **dos copias en disco** (la auditoría las verá como «mismo contenido»); ZascArr **nunca sugiere borrar**.

**Abierto (no resuelto aquí):** el **aviso informativo** para un `.cbr` que se lee como ZIP («Se lee como un .cbz aunque se llame .cbr. Todo bien…»; UX pide chip neutro y solo en Auditoría). El texto está en `INFO_CBR_ES_ZIP` pero **no se muestra**: exige una categoría nueva en el informe y su plantilla (**no entregado**).

## 8. Decisiones del PO (PROPUESTAS PENDIENTES; la rama aplica la recomendada solo para poder verla)
| # | Decisión | Opciones y consecuencias | Recomendación (aplicada en la rama, **sin aprobar**) |
|---|---|---|---|
| **D1** | **Sin extensión y doble extensión** (2 ZIP + 1 7z hoy) | (a) solo **avisar**: el fichero no entra en la biblioteca de ZascArr; es un **recorte** respecto a «reconocer un ZIP sin extensión» (la tarjeta). (b) registrarlos: exige valor nuevo del enum `file_format` (**migración**) y, si se registran como CBZ, el tagger podría **escribir** en un fichero sin extensión | (a) |
| **D2** | **`.zip`** (hoy `triage`/portada lo leen pero el importador no lo recorre: la incoherencia que motivó el spike) | (a) no listarlo (el escaneo sigue sin recorrer `.zip`; `triage` y portada lo siguen leyendo si ya está en la base): **la incoherencia lector/importador se mantiene, ahora documentada**. (b) listarlo si es `TEBEO`: cambia el tamaño de la biblioteca y la deduplicación | (a) en esta tarjeta |
| **D3** | **Topes** (§6) | (a) conservar el total de 500 MiB y la portada sin tope: 20 de 366 ZIP sin ComicInfo/anchura y lectura de portada sin acotar. (b) topes por entrada leída + límites del registro final + píxeles | (b); **necesita revisión técnica del conjunto de límites** (§6, «Qué NO acota esto») |
| **D4** | `.pdf`/`.epub` dentro de un ZIP | (a) pack: se marca y no se registra. (b) ignorarlos. **Casos mixtos no definidos:** hoy cualquier contenedor anidado (aunque sean 11 imágenes y 1 PDF) vuelve `PAQUETE`; «paquete» y «contenido no admitido» no se distinguen | (a), conservador; pide definir los casos mixtos antes de fusionar |
| **D5** | **Relleno** automático de `formato_contenido` en los `.cbr`/`.cb7` ya registrados | (a) en el ciclo del importer: **escribe automáticamente en `files.metadata` de filas existentes**; (b) a demanda (sin escrituras automáticas). Alcance, conservación y concurrencia: §12.2 | (a), con las garantías de §12.2 |

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

## 12. Implementación, garantías y hallazgos
**Dónde está:** `core/formato_contenedor.py` (el único punto de decisión), enums `Firma`/`ClaseZip`/`Tratamiento` en `models/__init__.py`, `core/importer_triage.py::triage`, `utils/cover.py`, `services/importer.py` (`formato_contenido` al importar, al reenlazar y `rellenar_formato_contenido`), `services/library_adopter.py`, `services/library_audit.py`, `web/series.py` y `web/pendientes.py`.

### 12.1 Cifras y procedencia (denominadores)
Todas salen de `scripts/medicion/censo_zip_por_contenido.py` y del censo de cabeceras (`censo_cabeceras_rar.py`), ejecutados **en la Pi el 2026-10-23**, solo lectura.

| Cifra | Qué cuenta | Denominador y procedencia |
|---|---|---|
| **58** ZIP «ocultos» | ficheros `.cbr`/`.rar`/sin extensión cuya **firma** es ZIP | censo de cabeceras: 1267 ficheros (`.cbr`, `.rar` o sin extensión) |
| **56** | de esos 58, los que **llevan `.cbr`** (ya registrados, sin portada ni ComicInfo) | = 58 − 2 |
| **2** | de los 58, los **sin extensión** (el caso original de la tarjeta) | |
| **366** ZIP medidos | 308 `.cbz` de control + 56 `.cbr` ZIP + 2 sin extensión | censo de ZIP por contenido (no había ningún `.zip`) |
| **20** superan el tope **antiguo** (500 MiB totales) | **10 de los 308** `.cbz` + **10 de los 56** `.cbr` ZIP | mismo censo, estado `demasiado_grande`; 575 MiB–1,3 GiB |
| **«los 10 `.cbz` grandes»** | los 10 `.cbz` de esos 20 (**ya están registrados sin ComicInfo/anchura**; la portada sí sale) | |
| **«los 10 ZIP grandes» (portadas)** | los **10 `.cbr` ZIP** de esos 20 | son conjuntos **distintos**: 10 + 10 = 20 |

### 12.2 Garantías del relleno (D5)
Probadas con **Postgres real** en `tests/test_formato_contenido_relleno_pg.py` (27 pruebas con las de integración):
- **Conserva las demás claves de `files.metadata`, también frente a un escritor concurrente.** Una primera versión leía el diccionario, añadía la clave y lo reescribía entero: eso **pierde** cualquier clave escrita por otro proceso entre la lectura y la escritura (p. ej. el `vinculo` de BL-R1). Ahora es **una sola sentencia atómica por fila**: `metadata = coalesce(metadata,'{}') || {"formato_contenido": …}` y solo `WHERE` la clave aún no existe. Prueba: se lee la fila, otro proceso escribe `vinculo`, y después se aplica el relleno: **ambas claves sobreviven**.
- **Metadata `NULL`:** la prueba descubrió que `NOT (metadata ? 'clave')` vale `NULL` y la fila **nunca** se elegía. Corregido (`metadata IS NULL OR …`), con prueba.
- **Sin dobles ni reproceso:** dos rellenos solapados rellenan cada fila **exactamente una vez** (8 filas → 8 en total); una fila ya rellena no se lee otra vez; una clave existente no se sobrescribe.
- **Lote acotado y sin inanición:** como máximo **100** filas por ciclo (cada una lee ≤ 512 B y, si es ZIP, su directorio central), **elegidas al azar** entre las pendientes: con una selección fija, un grupo de ficheros ilegibles ocuparía el lote para siempre. Una biblioteca de ~1,2 k `.cbr` se rellena en ≥ 13 ciclos (15 min cada uno). **Coste de lectura NO medido**: el censo equivalente (4 KiB de 1267 ficheros + directorio central de 366 ZIP) «tarda un par de minutos» en el USB de la Pi (sin cronometrar con precisión); el lote de 100 es una cota prudente, **a medir tras desplegar**.
- Un fichero ilegible (disco desmontado) no se marca: se reintenta. Los ficheros **no se tocan** (hash y mtime iguales, probado).
- **Sigue siendo una escritura automática sobre filas existentes** (la decisión D5 es del PO): si se prefiere (b), basta quitar la llamada de `scan_and_import`.

### 12.3 «Sin escritura del original», en todos los consumidores
Quién puede escribir o mover un fichero de tebeo (revisado con `grep` sobre `src/`):
- `utils/cbz.py` (reescribe un CBZ con `os.replace`): solo lo alcanza el **tagger** y `cli/etiquetar`, y el tagger sale con `file.file_format is not FileFormat.CBZ` → **«formato no parcheable (solo CBZ)»**. `file_format` es la extensión **declarada**, así que un `.cbr` que es ZIP **nunca** entra. Probado (`TestElTaggerNoEscribeEnUnZipQueSeLlamaCbr`: hash y mtime iguales).
- `utils/fs.safe_move` y `services/asignacion.py` mueven ficheros por decisión del importer/del usuario, **sin depender del formato real**; #307 no los toca.
- `triage`, la portada, la auditoría y el relleno solo **leen**.

### 12.4 Hallazgos al implementar (algunos cambian el diseño)
1. **La clase no bloquea la lectura de un `.cbz`/`.zip` declarado.** `TEBEO` (≥ 10 imágenes, ≥ 80 %) solo es condición para un `.cbr`/`.cb7` que *resulta ser* un ZIP; un `.cbz` corto o un pack se lee **como siempre y sin aviso**. Lo detectó `test_naming_core`.
2. **Un `.cbz`/`.zip` cuyo contenido no es ningún contenedor conocido** (roto, descarga incompleta) sigue **sin hash** y con «zip ilegible». Hash solo para contenedores válidos con otro nombre (un RAR llamado `.cbz`).
3. **`formato_contenido` es una foto del momento del registro.** Si el usuario sustituye el fichero a mano, queda vieja. Por eso, para un `.cbz`/`.zip` declarado la portada solo mira la **firma**, no la clase.
4. **🚩 Tras la adopción inicial, nada registra ficheros nuevos de la biblioteca.** El importador solo recorre las carpetas de **descargas**; la adopción de la biblioteca solo se ofrece mientras el marcador `_library_adoption_done` no está puesto (`estado() == HECHA` → `puede_registrar()` es falso y `/ui/auditoria/adoptar` no hace nada). Probado (`TestNadaRecogeFicherosNuevosDeLaBiblioteca`). **Consecuencia:** «descomprímelo» (un pack) y «cambia el final del nombre a .cbz» (un ZIP sin extensión) **no llevan a que ZascArr incorpore nada** en una biblioteca ya adoptada. Los avisos por fila se reescribieron sin prometerlo; **el único camino que sí existe** (copiar el fichero arreglado a la carpeta de descargas) va una vez en la cabecera, verificado (§7). Es un **hueco de producto previo a #307** que merece su propia tarjeta (p. ej. «registrar los archivos nuevos de la biblioteca después de la adopción inicial»; referencias a mirar en la ficha §13: Sonarr/Radarr, refresco y escaneo de carpetas; Kapowarr/Mylar3, escaneo de biblioteca).
5. `extract_cover_thumbnail` leía `zf.read(pages[0])` sin ningún tope; `ZipFile()` cargaba el directorio central entero antes de poder contar entradas. Ambos acotados (§6).
6. `natural_key` e `IMAGE_EXTS` se movieron a `formato_contenedor` (se reexportan desde `importer_triage`). La auditoría avisa ahora de `.tar`/`.cbt`, de `.cbz`/`.cbr`/`.cb7` cuyo contenido no concuerda y de contenedores sin extensión.

### 12.5 Evidencia de pruebas
- `tests/test_formato_contenedor.py` (T1–T4, T8, límites del registro final, píxeles), `tests/test_formato_por_contenido_integracion.py` (T5, T6, T9 y regresiones), `tests/test_formato_contenido_relleno_pg.py` (T10, **Postgres real**), `tests/test_formatos_contenedor_hoy.py` y `tests/test_importer_triage.py` (T12 y T13, actualizadas **a propósito**). T7 y T11 están en la caracterización.
- La suite se ha ejecutado **sin** `tests/test_ensayo_f1bis_arnes.py` (5 pruebas del arnés de ensayo que **ya fallan en `main` en este equipo**; la CI las pasa): no es una suite completa sin exclusiones.

**NOT RUN:** los ficheros reales de la Pi (el relleno de los 56 y las portadas de los 10 `.cbr` ZIP grandes) hasta desplegar, **que no está autorizado**; el coste de lectura del relleno sobre el USB; el chip informativo (no entregado).
