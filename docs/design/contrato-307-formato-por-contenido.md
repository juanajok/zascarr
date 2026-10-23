# Contrato de #307 — reconocer un ZIP por su contenido (un solo punto de decisión)

> **Estado: IMPLEMENTADO en la rama `claude/307-formato-por-contenido` (PR #325, EN BORRADOR hasta completar la revisión técnica y la CI sobre el SHA final; esto NO autoriza fusión, despliegue ni ejecución del relleno en la Pi). Sin migración y sin tocar ningún fichero del PO.** **Procedencia de D1–D5:** llegaron como texto en un mensaje del usuario `juanajok` (2026-10-23); el revisor externo ha dicho que no las redactó ni las decidió. **`juanajok` las ha confirmado expresamente como suyas en el chat el mismo día** (junto con la aceptación de los recortes D1/D2 y la del 1 MiB condicionada a medir antes de fusionar): ver §8. Hallazgos y desviaciones: §12. **No forma parte de ningún candidato de despliegue.**

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
`ClaseZip`: `TEBEO | ANIDADOS | NO_TEBEO | CIFRADO | INVALIDO | VACIO | LIMITE`. `Tratamiento`: `LEER_COMO_ZIP | SOLO_HASH | AVISAR`.

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
| `ANIDADOS` | alguna entrada con extensión de contenedor (`.cbz .zip .cbr .rar .cb7 .7z .tar .epub .pdf`…) | **no se interpreta automáticamente como un tebeo** (ni se extrae su portada) y **no se afirma que contenga «varios tebeos»**: once imágenes y un PDF podrían ser un tebeo con un suplemento (D4) |
| `NO_TEBEO` | pocas imágenes o poca fracción | aviso |
| `CIFRADO` | alguna entrada cifrada | aviso: «necesita contraseña; ZascArr no la pide» |
| `INVALIDO` / `VACIO` | no se abre / sin entradas | aviso |
| `LIMITE` | supera los topes (§6) | aviso con el motivo |

**D4 (decidida):** un `.pdf` o `.epub` —o cualquier otro comprimido— dentro de un ZIP impide clasificarlo automáticamente como un tebeo individual para el reconocimiento de `.cbr`/`.cb7`; la clase se llama `ANIDADOS` precisamente para **no afirmar** «pack» ni «varios tebeos». Casos de prueba: imágenes + PDF, imágenes + EPUB y varios CBZ anidados. No se abren esos documentos. Un `.cbz` declarado con anidados se lee como siempre.
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
| Directorio central | ≤ **1 MiB** *(corrección técnica del 16 MiB aprobado: ver abajo)* | igual: se lee con **el mismo lector del registro final que usa `ZipFile`** (`zipfile._EndRecData`: última firma, comentario, localizador y registro ZIP64) | `LIMITE` (motivo «directorio»): «Su índice interno es demasiado grande y ZascArr no lo abre, por precaución.» |
| Entrada **que se lee** | ≤ **32 MiB** descomprimidos | el tamaño **declarado de esa entrada** (la primera página; `ComicInfo.xml` tiene su propio tope de 1 MiB) y, además, la lectura **no pasa de `tope + 1` bytes** aunque la cabecera mienta (`zf.open(...).read(tope + 1)`) | `EntradaNoLegible`; la página se ignora con aviso |
| Ratio de compresión | ≤ **100** | `tamaño descomprimido / tamaño comprimido` **de esa misma entrada** (la primera página observada: ≤ 1,77) | `EntradaNoLegible` (posible bomba) |
| Píxeles de la miniatura | ≤ **40 Mpx** | `ancho × alto` que declara la cabecera de la imagen (`Image.open` lee solo la cabecera); una página de tebeo de 3000×4500 son 13,5 Mpx | sin miniatura, **sin decodificar** |
| Total descomprimido | **ya no hay** | — | — (era el tope de 500 MiB que dejaba sin `ComicInfo`/anchura a 20 de 366 ZIP) |

**Por qué 1 MiB y no 16 MiB (corrección técnica, no cambio de producto).** `ZipFile()` recorre el directorio central por su **tamaño en bytes**, no por el nº de entradas que declara el registro, y reserva ~10 B de memoria por byte de índice. **Medido** (Python 3.14, x86): 2000 entradas = 109 KiB → 1,0 MiB de pico; 20 000 = 1,1 MiB → 10,8 MiB; 60 000 = 3,3 MiB → 33 MiB y 2,4 s. Con 16 MiB serían ~170 MiB y ~12 s (en la Pi, bastante más) dentro de un contenedor de 512 MiB: el tope de entradas **declaradas** no protege si el índice real es mayor. 1 MiB cubre de sobra 2000 entradas con nombres largos (~0,3 MiB) y acota el coste a ~11 MiB. La tabla aprobada decía 16 MiB; **se cambia por esta razón y se deja dicho**.

**Acreditación del valor (qué está medido y qué no).**
- *Medición:* Python **3.14.4**, x86_64, `tracemalloc`; ZIP sintéticos en memoria de entradas vacías (STORED) con nombres `pNNNNN.jpg`; se abre con `ZipFile(BytesIO)` y se anota el pico de memoria y el tiempo de pared. Resultados (esa máquina): 2000 entradas = 109 KiB de índice → 1,0 MiB de pico, 0,08 s; 20 000 = 1,1 MiB → 10,8 MiB, 0,76 s; 60 000 = 3,3 MiB → 33,4 MiB, 2,40 s (≈ 500–585 B por entrada). **Es el coste observado en ese entorno, no una ley universal de «10 B por byte de índice»**; con nombres más largos o ZipInfo más pesados cambiará. **NOT RUN en la Pi y en Python 3.11** (la versión del producto).
- *Cuántos ZIP legítimos quedan excluidos con 1 MiB:* **medido en la Pi (2026-10-23, solo lectura, `censo_zip_por_contenido.py`): 0 de 366** (0 de 308 `.cbz`, 0 de 56 `.cbr`-ZIP, 0 de 2 sin extensión). Tamaño del directorio central: mediana 2 KiB, p95 61 KiB, p99 82 KiB, **máximo 93 KiB** (941 entradas, 102 B por entrada) ⇒ **margen ×11** sobre el mayor existente. Densidad: mediana 82 B por entrada, máximo 320 B; **320 B × 2000 entradas = 0,6 MiB < 1 MiB**, así que el límite de índice y el de entradas son coherentes entre sí (con la densidad observada, un ZIP legítimo en el límite de 2000 entradas no superaría el índice). *Límite:* es la biblioteca de este PO (366 ZIP), no una población general; el script se ejecutó con el `python3` del host de la Pi (su versión no la registra el script) y **ejecutó `zipfile._EndRecData` sin error en esa versión** (un dato de compatibilidad, no la prueba de la CI en 3.11). El ordenador de desarrollo sí mide el coste de abrir (arriba, 3.14/x86).
- *El rechazo ocurre antes de construir el índice:* probado (`test_rechazar_cuesta_casi_nada_frente_a_abrir`: comprobar el límite en un ZIP de 30 000 entradas usa < 256 KiB; abrirlo cuesta más de 20 veces eso) y con `ZipFile` sustituido por una función que falla si se llama.
- *Un índice malformado no evita la comprobación ni acaba en lectura sin cota:* si el registro declara un índice **menor** que el real, `ZipFile` solo lee los bytes declarados (pico < 2 MiB, falla o abre lo declarado); si declara uno **mayor que el fichero** (~4 GiB), se rechaza sin abrir.
- *Los límites se complementan:* una prueba fabrica, por cada uno (entradas, índice, entrada leída > 32 MiB incomprimible, ratio > 100, píxeles > 40 Mpx), un ZIP que incumple **solo ese** y comprueba que los demás lo dejarían pasar y que ese lo para. **Ninguno sustituye a otro.**
- *El mensaje es de procesamiento, no de corrupción:* «…no lo abre, por precaución»; una prueba prohíbe «dañado», «corrupto», «incompleto» o «roto» en los textos de `LIMITE`.

**Coherencia entre el control previo y el lector que abre el ZIP** (condición del PO sobre D3): el control **no reimplementa** el registro final; llama al mismo `zipfile._EndRecData` que usa `ZipFile`. Una firma EOCD falsa dentro del comentario, un localizador ZIP64 que el EOCD normal no refleja o un registro truncado se interpretan igual en los dos. Pruebas: `TestCoherenciaConLoQueAbreZipFile` compara, para cada variante, lo que ve el control con lo que `ZipFile` realmente usa (espiando la función). Es una función privada de la biblioteca estándar: si una versión de Python la cambiara, el módulo **no se importa** (falla ruidoso, no deja pasar en silencio) y una prueba lo deja dicho. **Límite honesto:** se ha probado con Python 3.14 en local; la CI usa 3.11, que es la versión de la imagen.

**Causa dicha = causa que saltó** (condición del PO): `LIMITE` lleva un motivo, «entradas» o «directorio»; el aviso de «más de 2000 archivos» solo sale por entradas.

**Qué NO acota esto:** el total de lo que contiene un ZIP (solo se lee **una página** y `ComicInfo.xml`); el tiempo de lectura de un disco lento; ni la decodificación de formatos que Pillow lea más despacio de lo que su tamaño sugiere (se acota por píxeles y por bytes, no por tiempo). Cambia el comportamiento de los `.cbz` existentes (los 10 grandes ganan `ComicInfo` y anchura): `tests/test_formatos_contenedor_hoy.py` se actualiza **a propósito**.

## 7. Qué se guarda y qué se avisa
**Persistencia (sin migración):** `files.metadata.formato_contenido = {"firma": "zip", "clase": "tebeo", "contrato": 1}`. `file_format` **no cambia** (sigue la extensión declarada). El importador rellena el campo al triar; para los **56 ya registrados** hay un **relleno idempotente A DEMANDA** (D5: `python -m zascarr.cli.rellenar_formato --apply`; **no** lo lanza ningún ciclo). Mientras no se ejecute, esas filas no tienen `formato_contenido` y su portada se decide leyendo el contenido en el momento de pedirla (`extract_cover_thumbnail` sin formato guardado), y `puede_tener_portada` cae a la extensión (sin `<img>` para un `.cbr` aún sin rellenar).

**Avisos.** Redacción revisada por UX el 2026-10-23 (≤ 2 frases, lo técnico entre paréntesis, sin jerga), **con un cambio posterior mío**: se quitaron todas las instrucciones del tipo «descomprímelo» o «cambia el final del nombre a .cbz» porque **el recorrido no está verificado y, comprobado, no existe** (§12.4): tras la adopción inicial, nada registra ficheros nuevos de la biblioteca. Una prueba (`test_todos_los_textos_siguen_las_reglas_de_ux`) impide reintroducirlas por fila.
La garantía y el **único camino verificado** van **una vez**, en la cabecera de la sección «Archivos que ZascArr no reconoce»: *«Archivos que ZascArr no puede usar como tebeo. No cambia, mueve ni borra ninguno de esta lista. Si arreglas una copia (por ejemplo, la descomprimes o pones .cbz al final de su nombre) y la dejas en tu carpeta de descargas, ZascArr intentará importarla; el original seguirá aquí.»* (Redacción final de UX; el PO cambió «importará» por «intentará importarla» porque la propia prueba de duplicados muestra que una copia idéntica a algo ya registrado se descarta y se queda en descargas: la promesa no es absoluta.) La frase habla de la **copia** para no contradecir «no mueve ninguno»: el importador sí **mueve** a la biblioteca lo que encuentra en descargas, pero eso es la copia, no el original de la lista; «el original seguirá aquí» anticipa que la auditoría verá las dos. «Pones .cbz al final de su nombre» solo vale para una **copia cuyo contenido ya es un ZIP** (un ZIP sin extensión): no convierte ningún otro formato por cambiarle el nombre. Sin renombrar, un fichero sin extensión no se importa. (La cabecera antigua decía que *ninguno* contaba en la biblioteca: ya no es cierto, p. ej. un `.cbz` que es RAR sí está registrado.)

| Situación | Texto |
|---|---|
| `.cbz` (o `.cbr`/`.cb7`/`.zip`) cuyo contenido no concuerda | «Se llama .cbz, pero por dentro es un .cbr (RAR). Sigue en tu biblioteca, aunque por ahora ZascArr no puede sacarle la portada.» |
| Sin final de tebeo, contenido ZIP / RAR / 7z | «Parece un tebeo, pero su nombre no acaba en .cbz (.cbr / .cb7), así que ZascArr no lo registra.» |
| Sin final de tebeo, contenido TAR | «Parece un tebeo, pero está guardado en un formato (TAR) que ZascArr no usa.» |
| ZIP con otros comprimidos / PDF / EPUB dentro | «Contiene otros archivos comprimidos, PDF o EPUB. ZascArr no lo interpreta automáticamente como un solo tebeo ni separa su contenido.» |
| ZIP «no es un tebeo» | «Es un archivo comprimido, pero no parece un tebeo: tiene pocas imágenes o están mezcladas con otros archivos.» |
| Con contraseña | «Tiene contraseña, así que ZascArr no puede abrirlo.» |
| Dañado | «Está dañado o incompleto; quizá la descarga no terminó. Prueba a descargarlo de nuevo.» *(recorrido verificado: ver abajo)* |
| Vacío | «Está vacío: no tiene ninguna página. Prueba a descargarlo de nuevo.» *(ídem)* |
| Demasiados archivos | «Tiene demasiados archivos dentro (más de 2000) y ZascArr no lo abre, por precaución.» |
| Índice interno demasiado grande | «Su índice interno es demasiado grande y ZascArr no lo abre, por precaución.» |
| `.rar` / `.7z` por el nombre | «Es un archivo .rar: ZascArr no lo registra como tebeo, aunque dentro haya uno.» |
| `.tar` / `.cbt` | «ZascArr no usa este formato (TAR), así que no lo registra como tebeo.» |

**Alcance de la cabecera:** «intentará importarla» se refiere **solo a la carpeta de descargas**, el único recorrido que existe y está probado; **no promete** que ZascArr incorpore ficheros que el usuario deje dentro de la biblioteca (eso es justo el hueco que documenta #326).

**Recorrido verificado** (`tests/test_importer_recorrido_de_descargas_pg.py`, importador real + Postgres real + ficheros sintéticos): (a) el importador recorre las carpetas de **descargas** (`transmission_download_dir`, `amule_incoming_dir`, `downloads_path`), de forma recursiva; (b) una copia buena **entra aunque el dañado siga en la biblioteca** (el dañado no tiene hash, así que la deduplicación por SHA-256 no los confunde) y el dañado **no se toca**; (c) va a **su serie y número** si casan y, si no, a `_Unsorted` («Por revisar»). Además: una copia con el nombre arreglado (`.cbz`) dejada en descargas **se importa y se mueve** a la biblioteca; un fichero sin extensión dejado en descargas **no** se importa; una copia idéntica a un fichero ya registrado se descarta como duplicado y **se queda en descargas**; un pack descomprimido en descargas se importa número a número. **Matices que el coleccionista debe poder entender:** el original no se toca ni se registra, así que quedan **dos copias en disco** (la auditoría las verá como «mismo contenido»); ZascArr **nunca sugiere borrar**.

**Abierto (no resuelto aquí):** el **aviso informativo** para un `.cbr` que se lee como ZIP («Se lee como un .cbz aunque se llame .cbr. Todo bien…»; UX pide chip neutro y solo en Auditoría). El texto está en `INFO_CBR_ES_ZIP` pero **no se muestra**: exige una categoría nueva en el informe y su plantilla (**no entregado**).

## 8. D1–D5: decisiones recibidas del usuario (2026-10-23) y su procedencia
**Procedencia, por separado** (para no confundir quién propuso, quién recomendó y quién decidió):
- **Propuestas del implementador:** las opciones de cada decisión y las recomendaciones originales (D1a, D2a, D3b, D4a, D5a) de la versión anterior de este contrato.
- **Recomendaciones del revisor externo:** condiciones técnicas sobre D3 (causa dicha, coherencia con `ZipFile`), D4 (no afirmar «varios tebeos») y D5 (sin escrituras automáticas); y la revisión del límite y de la dependencia de `zipfile._EndRecData`.
- **Decisiones del usuario `juanajok`:** el texto de D1–D5 de la tabla, recibido en el chat el 2026-10-23, en primera persona («Elijo la opción (b)»…). **El revisor externo ha indicado que no las decidió él.** Preguntado expresamente el mismo día, `juanajok` respondió que **son suyas y que las toma como decisiones**.
- **Aceptación expresa de `juanajok` (2026-10-23, en el chat):** (1) **los recortes de alcance de D1 y D2** («Acepto los recortes D1 y D2»: reconocer el contenido no equivale a registrarlo; la incoherencia de `.zip` queda sin resolver y documentada); (2) **el valor de 1 MiB** del directorio central, que sustituye al 16 MiB de la tabla que se aprobó (§6), **«pero medir antes de fusionar»**: el censo (`censo_zip_por_contenido.py`, solo lectura) se ejecutó en la Pi el 2026-10-23 y **0 de 366 ZIP superan 1 MiB de índice** (máximo 93 KiB; §6). **La condición de medir está cumplida; fusionar sigue sin estar autorizado** (falta la revisión técnica y la CI sobre el SHA final).

| # | Decisión | Qué decidió el usuario | Consecuencias y reservas |
|---|---|---|---|
| **D1** | Sin extensión y doble extensión | **(a) avisar, sin registrar.** Detectar y explicar el contenido en Auditoría; sin nuevos formatos declarados, sin migraciones, sin renombrar originales ni hacerlos pasar por CBZ para permitir escrituras | **Recorte respecto al objetivo inicial de la tarjeta** (reconocer e incorporar ZIP sin extensión): queda registrado así. **Reconocer el contenido no equivale a registrarlo en el catálogo**; la tarjeta y su aceptación deben decirlo |
| **D2** | `.zip` | **(a) no ampliar el recorrido del importador** | **La incoherencia queda reconocida, no resuelta:** los lectores procesan un ZIP ya registrado, mientras el importador no descubre archivos nuevos por esa extensión. **No es «soporte completo de ZIP».** Su incorporación futura necesitará casos de tebeo individual, anidados, duplicado y contenido no utilizable |
| **D3** | Topes | **Aprobados como contrato objetivo, NO como garantía técnica ya acreditada.** Entradas 2000, entrada de imagen leída 32 MiB, `ComicInfo.xml` 1 MiB, ratio 100, miniatura 40 Mpx; directorio central: ver §6 | La aprobación de producto no sustituye la revisión técnica. **Dos puntos del diff debían resolverse antes de aprobar la PR: causa dicha = causa que saltó, y coherencia con `ZipFile` (§6) — resueltos con pruebas.** El valor del directorio central pasó de 16 a **1 MiB** por una razón técnica medida (§6), no de producto: queda para que el PO lo confirme. No acotan el tiempo de un disco lento ni toda la duración de la decodificación |
| **D4** | PDF/EPUB o comprimidos anidados | **Exclusión conservadora, sin afirmar «varios tebeos».** Impide clasificar automáticamente el ZIP como un tebeo individual para el reconocimiento de `.cbr`/`.cb7` | Clase `ANIDADOS`; texto neutro; fixtures imágenes + PDF, imágenes + EPUB y varios CBZ anidados (§5) |
| **D5** | Relleno de `formato_contenido` | **(b) a demanda en esta entrega; automático, diferido.** Se retira su invocación desde `scan_and_import` | Mecanismo operativo: `python -m zascarr.cli.rellenar_formato [--apply] [--limite N] [--json]` o `scripts/rellenar-formato.sh`. Por defecto **solo cuenta** (no lee ni escribe); con `--apply` ejecuta un lote acotado y devuelve un resultado identificable (leídas, rellenadas, ilegibles, pendientes antes y después); código de salida 1 si hubo ilegibles. Conserva la fusión atómica, no sobrescribe, los ilegibles quedan pendientes. **No se ejecuta sobre la Pi ni la biblioteca real por esta decisión.** Automatizarlo exige antes medir su coste de lectura en el USB y aprobar su presupuesto |

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
| T3 | `clasificar_zip`: tebeo, anidados, no-tebeo, cifrado, vacío, corrupto, límite; imágenes+PDF, imágenes+EPUB, varios CBZ anidados | clase de §5 (D4) |
| T4 | **Sin descomprimir** (se prohíbe `ZipFile.read/open` en la clasificación) | pasa |
| T5 | Un `.cbr` ZIP con imágenes + `ComicInfo.xml` | `triage` devuelve `ComicInfo` y `width_px`; la portada sale; **hash y mtime del original iguales** |
| T6 | El mismo fichero y el **tagger** | lo salta («solo CBZ declarado») |
| T7 | `.cbz` que es RAR | aviso con causa y acción; no «zip ilegible» a secas |
| T8 | ZIP bomba (entradas, tamaño, ratio), **tamaño declarado falso** (declara 10 KB, expande mucho) y corrupto, **también en la portada** | rechazados con aviso, sin extraer; la memoria no pasa del tope |
| T13 | Un ZIP > 500 MiB declarados con una sola página grande ≤ 32 MiB | `triage` devuelve `ComicInfo` y anchura (hoy: «ignorado»); la portada sale |
| T9 | `puede_tener_portada` con `formato_contenido` guardado y sin él | **cero E/S** en ambos casos |
| T10 | Relleno **a demanda** de los registrados: idempotente, conserva claves (también con un escritor concurrente), `metadata` NULL, ilegibles pendientes, resultado identificable, CLI que por defecto no escribe | pasa (Postgres real) |
| T14 | El ciclo **no** lanza el relleno | pasa |
| T15 | Causa dicha = causa que saltó; control previo coherente con `ZipFile` (firma falsa en el comentario, ZIP64 no reflejado, índice real enorme) | pasa |
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

### 12.1b Riesgo explícito: `zipfile._EndRecData` es una función privada
- **Qué es:** el control previo del límite llama a `zipfile._EndRecData` (y lee `_ECD_ENTRIES_TOTAL`/`_ECD_SIZE`) para interpretar el registro final **igual que `ZipFile`**. Está **encapsulado en un solo punto** (`core/formato_contenedor.py::leer_cabecera_zip`; el script de censo la usa solo para medir).
- **Qué pasa si cambia en una versión de Python:** el módulo **falla al importarse** (ruidoso) en vez de dejar pasar todo en silencio; `test_el_lector_privado_de_la_biblioteca_estandar_sigue_existiendo` y `TestCoherenciaConLoQueAbreZipFile` (que compara lo que ve el control con lo que `ZipFile` realmente usa, espiando la función) lo detectarían.
- **Evidencia que falta:** probado con Python **3.14** en local. La versión del producto es **3.11**: la CI debe **ejecutar** esas pruebas (no omitirlas) y quedar registrado cuáles; un check verde general no basta.
- **Alternativa si el riesgo no se acepta:** reimplementar el registro final (más código y más superficie de divergencia con `ZipFile`, que es justo lo que se quiere evitar) o aceptar el coste de abrir el ZIP antes de contar (no acotado).

### 12.2 Garantías del relleno (D5: a demanda)
Probadas con **Postgres real** en `tests/test_formato_contenido_relleno_pg.py` (27 pruebas con las de integración):
- **Conserva las demás claves de `files.metadata`, también frente a un escritor concurrente.** Una primera versión leía el diccionario, añadía la clave y lo reescribía entero: eso **pierde** cualquier clave escrita por otro proceso entre la lectura y la escritura (p. ej. el `vinculo` de BL-R1). Ahora es **una sola sentencia atómica por fila**: `metadata = coalesce(metadata,'{}') || {"formato_contenido": …}` y solo `WHERE` la clave aún no existe. Prueba: se lee la fila, otro proceso escribe `vinculo`, y después se aplica el relleno: **ambas claves sobreviven**.
- **Metadata `NULL`:** la prueba descubrió que `NOT (metadata ? 'clave')` vale `NULL` y la fila **nunca** se elegía. Corregido (`metadata IS NULL OR …`), con prueba.
- **Sin dobles ni reproceso:** dos rellenos solapados rellenan cada fila **exactamente una vez** (8 filas → 8 en total); una fila ya rellena no se lee otra vez; una clave existente no se sobrescribe.
- **Lote acotado:** como máximo **100** filas por ejecución (cada una lee ≤ 512 B y, si es ZIP, su directorio central), **elegidas al azar** entre las pendientes: con una selección fija, un grupo de ficheros ilegibles ocuparía el lote para siempre. **El azar reduce ese riesgo pero no garantiza un plazo de finalización.** Una biblioteca de ~1,2 k `.cbr` necesita ≥ 13 ejecuciones. **Coste de lectura NO medido**: el censo equivalente (4 KiB de 1267 ficheros + directorio central de 366 ZIP) «tarda un par de minutos» en el USB de la Pi (sin cronometrar con precisión); el lote de 100 es una cota prudente, **a medir tras desplegar**.
- Un fichero ilegible (disco desmontado) no se marca: se reintenta. Los ficheros **no se tocan** (hash y mtime iguales, probado).
- **Ya no es automática** (D5 decidida): ningún ciclo ni bucle la llama (prueba que lo comprueba). Ver §8 para el mecanismo.

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
