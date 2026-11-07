# Ficha de benchmarking — convertir CBR a CBZ y mejorar `ComicInfo.xml` (BL-CNV)

> Ficha de **nivel 2** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13): toca
> ficheros (reescribe el archivo del coleccionista), modelo (`File`) y fuentes externas.
> Fecha: 2026-11-07. Contrastada con `origin/main` `56c782a`. **Insumo, no aprobación:**
> decide el PO.

## 1. Historia y problema observado

Como coleccionista, quiero que ZascArr convierta mis `.cbr` en `.cbz` y mejore (o cree) su
`ComicInfo.xml` con datos de varias fuentes, para que mi tebeoteca sea legible por cualquier
lector (Kavita, Komga, ComicTagger…) sin depender de ZascArr.

**Por qué van juntas y en este orden:** ZascArr solo escribe `ComicInfo.xml` dentro de un
CBZ (B6: «CBR nunca se parchea»; escribir RAR exige el `rar` propietario). Mientras la mayoría
de la colección sea CBR, mejorar metadatos no llega a la mayoría de los tebeos.

## 2. Datos reales y medición de partida

| Dato | Valor | Origen |
|---|---|---|
| CBR en el disco de la biblioteca | **4.891 archivos, 202,1 GiB** | `find` de solo lectura sobre `/mnt/WDElements/Tebeos`, 2026-11-07 (todo el disco, no solo lo registrado) |
| CBZ en el mismo disco | 746 archivos, 26,8 GiB | ídem |
| Espacio libre en ese disco | 1,1 TiB de 3,6 TiB (72 % usado) | `df`, ídem |
| CBR registrados en la instalación | 1.234 de 1.542 (80 %) | primer registro real, 2026-10-05 (`BACKLOG.md`) |
| CBR con `ComicInfo.xml` | **0 de 36** muestras; 0,5 % en la sonda de B6 | #308 tanda 2; ficha B6 |
| `.cbr` que en realidad son ZIP | 58 (cifra de #308, a revisar) | #307/#328 |
| Lector de RAR | `unar` 1.10.7 adoptado con condiciones (#308): pico ≤ 25,8 MiB, +22,5 MiB de imagen, LGPL-2.1+, **revisión de vulnerabilidades pendiente**; **aún no está en la imagen** (llega con BL-PORT3 #418, `utils/lector_rar.py`) | `evaluacion-lector-rar-tanda2-2026-10-23.md` |

**Comportamiento actual en el código vigente:**
- `services/tagger.py` + `utils/cbz.py` + `core/comicinfo_write.py` (B6): plan por campo
  (`cambia`/`conserva`/`ya_coincide`/`sin_dato`/`bloqueado`), simulación con el mismo plan,
  procedencia (`File.metadata_["comicinfo_propio"]`), `locked_fields`, manifiesto SHA256 de
  las entradas no-XML, temporal hermano, `testzip`, `fsync` y `os.replace`, bloqueo
  `pg_advisory_xact_lock` por `File.id`, recálculo de hash y tamaño. **Solo CLI**
  (`scripts/etiquetar.sh`), mapa mínimo (sin créditos, género ni páginas), CBR se salta.
- Ninguna conversión de formato. #159 (B10, P2) la pedía como opción, sin contrato.

## 3. Referencias consultadas (código leído, no solo documentación)

| Referencia | Versión / commit | Licencia | Ficheros leídos |
|---|---|---|---|
| ComicTagger | `fa11a34` (2026-09-06) | Apache-2.0 | `comictaggerlib/cli.py::export`, `comicapi/comicarchive.py::export_as_zip`, `comicapi/archivers/zip.py::copy_from_archive`, `ctsettings/commandline.py`, `ctsettings/file.py`, `comicapi/merge.py`, `comictalker/` |
| Kapowarr | `c191dda` (2026-09-14) | GPL-3.0 | `backend/implementations/converters.py`, `conversion.py`, `base/files.py::create_zip_archive`, `base/definitions.py::RAR_EXECUTABLES`, `backend/lib/` |
| Mylar3 | `cdc94a4` (2025-08-17) | GPL-3.0 | `mylar/cmtagmylar.py`, `mylar/config.py` (`CBR2CBZ_ONLY`) |
| Komf (complemento de Komga) | `d8a34e9` (2026-09-27) | MIT | `komf-core/.../comicinfo/ComicInfoWriter.kt`, `komf-mediaserver/.../MetadataService.kt`, `MediaServerConfig.kt`, `MetadataProvidersConfig.kt` |
| metron-tagger | 4.9.2 (PyPI, solo documentación) | — | ayuda de `-z/--export-to-cbz` y `--delete-original` |
| Calibre, complemento Embed Comic Metadata | hilo de MobileRead (solo documentación) | — | opciones «Auto convert cbr to cbz» (por defecto sí) y borrar el CBR (por defecto no) |
| Kapowarr, documentación | `casvt.github.io/Kapowarr/settings/mediamanagement` | — | «Format Preference», «No Conversion» |

## 4. Cómo lo resuelve cada una

### 4.1 Conversión

- **ComicTagger** (`cli.py::export`): crea `<nombre>.cbz` **al lado** del original; si ya
  existe, nombre único (o aborta con `--abort-on-conflict`). Copia entrada a entrada leyendo
  cada una entera en memoria (`zip.py::copy_from_archive`, `ZipFile(..., "w")` sin
  compresión, es decir, `ZIP_STORED`: **no recomprime**) y conserva el comentario. Si la
  copia falla, borra el ZIP a medias. `--delete-original` hace `unlink` **definitivo** tras
  el éxito. **No verifica** el contenido de la copia contra el original: el éxito es «no
  hubo excepción». Tiene `--dryrun`.
- **Kapowarr** (`converters.py::rar_to_zip`): extrae **todo** el RAR a una carpeta, lo
  recomprime con `ZIP_DEFLATED` (`files.py::create_zip_archive`), **borra el original** y la
  carpeta, sin verificación del resultado. Usa un `rar` **propietario empaquetado** y solo
  para x86-64 (`backend/lib/rar_linux_64`: ELF x86-64; `supports_32bit=False`): **en una
  Raspberry Pi no hay conversión de RAR**. Elige el formato con una lista de preferencia cuyo
  último puesto es siempre «No Conversion»; puede convertir al descargar y tiene una
  previsualización por volumen (`conversion.py::preview_mass_convert`: ruta antes → después).
- **Mylar3**: delega en ComicTagger. Conserva o borra el RAR según el modo de
  postprocesado: «move» añade `--delete-rar` (`cmtagmylar.py`), «copy» lo conserva. Opción
  `CBR2CBZ_ONLY` para convertir sin etiquetar.
- **metron-tagger**: `-z` convierte; `--delete-original` es un paso aparte, **apagado por
  defecto**, solo tras exportar con éxito.
- **Calibre (Embed Comic Metadata)**: convierte para poder guardar metadatos; borrar el CBR
  viene **apagado** por defecto.

### 4.2 Metadatos de varias fuentes

- **ComicTagger**: dos modos de fusión (`comicapi/merge.py::Mode`): `OVERLAY` (lo nuevo
  pisa) y `ADD_MISSING` (solo rellena), por separado para leer etiquetas (`--tag-merge`) y
  para lo descargado (`--metadata-merge`); fuentes como *talkers* enchufables (Comic Vine
  incluido; Metron, GCD… como complementos). Una fuente por pasada.
- **Komf**: proveedores con **prioridad** numérica; se toma la primera coincidencia y, con
  `aggregate=true` (por defecto **no**), completa los huecos con las demás
  (`MetadataService.kt::aggregateMetadataFromProviders`). Escribe en CBZ/ZIP solo
  (`supportedExtensions = cbz, zip`), por temporal en la misma carpeta y `moveTo` con
  sustitución; `overrideComicInfo` (por defecto **no**) decide si sustituye el
  `ComicInfo.xml` o solo añade.
- **Kapowarr**: no escribe metadatos en los archivos; existe la petición #50 («exporting
  metadata»). Estado no comprobado.

## 5. Supuestos de su modelo que NO valen en ZascArr

1. **Borrar el original es aceptable** (Kapowarr siempre; ComicTagger, Mylar3 en «move»).
   Aquí no: no se borra nada sin confirmación (CLAUDE.md, ADR 0006/0014) y un fallo no
   puede costar un tebeo.
2. **«Sin excepción» = copia buena** (ComicTagger, Kapowarr). Aquí ya existe un listón más
   alto (manifiesto + `testzip` de B6) y se aplica igual.
3. **Hay un `rar` para la plataforma** (Kapowarr). En la Pi, no: `unar` (#308).
4. **La aplicación es dueña de la carpeta** (Kapowarr, Mylar3 mueven y renombran). ZascArr
   vincula en su sitio (ADR 0007) y la interfaz promete «no se mueve ni se renombra nada».
5. **La fuente principal es Comic Vine** (todas). Aquí la fuente depende de la tradición
   (ADR 0002: Tebeosfera para lo español, AniList para manga) y todas vienen apagadas
   (ADR 0013).
6. **Una persona delante, archivo a archivo** (ComicTagger). ZascArr además trabaja por
   lotes y en una Pi compartida: topes, espacio y no bloquear el bucle de eventos.

## 6. Resultado por idea

| # | Idea | Resultado | Motivo |
|---|---|---|---|
| I1 | Copiar entrada a entrada **sin recomprimir** (`ZIP_STORED`) | **Adoptar** (ComicTagger) | Las imágenes ya van comprimidas; recomprimir gasta CPU en la Pi sin ganar espacio. Sin pérdida de calidad. Hay que medir la diferencia de tamaño (NOT RUN). |
| I2 | Extraer todo a una carpeta y recomprimir con `DEFLATED` | **Descartar** (Kapowarr) | Doble escritura en disco USB, CPU y espacio temporal de un tebeo entero; ningún beneficio sobre I1. |
| I3 | Verificar la copia antes de publicarla | **Construir sobre lo propio** (B6) | Manifiesto: mismo número de entradas, mismos nombres y mismo CRC/tamaño que el listado de `unar`, y `testzip`. Ninguna referencia verifica. |
| I4 | Borrar el original tras el éxito | **Descartar** como acción del mismo paso; **adaptar** el «borrar aparte, apagado por defecto» de metron-tagger y Calibre | El original se **aparta** (carpeta de ZascArr, fuera de la biblioteca); vaciarla es una acción separada con confirmación. Ver decisión D2. |
| I5 | Nombre único si ya existe `<nombre>.cbz` | **Adaptar** (ComicTagger) | Aquí mejor **no convertir** y avisar (`--abort-on-conflict`): un `.cbz` homónimo suele ser otra copia del mismo tebeo, terreno de BL-DUP. |
| I6 | Lista de preferencia con «No convertir» siempre al final | **Adaptar** (Kapowarr) | En la primera versión el único destino es CBZ; la salida segura («si no se puede, se queda como está») sí se adopta. |
| I7 | Convertir automáticamente al descargar | **Descartar por ahora** (Kapowarr, Mylar3) | ADR 0008 (nada se ejecuta en silencio) y «medir antes de automatizar». Revisable con datos de BL-CNV2. |
| I8 | Previsualización de la conversión (antes → después) | **Adoptar** (Kapowarr) | Encaja con el patrón de vista previa + confirmación de ZascArr. |
| I9 | Mantener la **misma fila `File`** y actualizar ruta, extensión, hash y tamaño | **Construir sobre lo propio** | Conserva vínculo, historial y deshacer. Las referencias borran y crean (Kapowarr: `FilesDB.delete_filepath`). |
| I10 | Fusión `OVERLAY` / `ADD_MISSING` | **Ya adoptado** en B6 (precedencia + `--no-overwrite`) | Sin cambio. |
| I11 | Varias fuentes con prioridad y agregación | **Mejorar** (Komf) | Komf combina a ciegas. Aquí: propuesta **campo a campo** con la procedencia visible y la persona elige; ruta por tradición (ADR 0002). Evidencia de la debilidad: `aggregate` rellena huecos sin enseñar de dónde sale cada valor. |
| I12 | Sustituir o solo añadir al `ComicInfo.xml` | **Ya adoptado** en B6 (`fusionar_xml` conserva lo desconocido) | Sin cambio. |
| I13 | `MetronInfo.xml` | **Descartar por ahora** | Ningún lector de la casa (Kavita) lo necesita; ComicInfo basta. |
| I14 | `rar` propietario empaquetado | **Descartar** | Licencia no libre, sin ARM. `unar` (#308). |

## 7. Invariantes de ZascArr

1. **No se pierde ningún tebeo:** el original no se borra en la conversión; se aparta y se
   puede deshacer.
2. **No se publica una copia sin verificar** (I3); cualquier fallo deja el original intacto
   y limpia el temporal.
3. **No se mezcla el ORM con el disco** (CLAUDE.md §3.1): se convierte y verifica primero y
   el `commit` es corto después; reconciliación si falla el `commit` (patrón B6).
4. **Espacio libre comprobado** antes de cada conversión (tamaño del original + margen).
5. **Topes del lector** (#308 §6): listar antes, `RLIMIT_FSIZE`, tiempo con muerte del
   grupo de procesos, memoria del contenedor; I/O fuera del bucle de eventos.
6. **Sin red** para convertir. Para metadatos, solo las fuentes encendidas y con la cola de
   cortesía compartida (`utils/cortesia.py`).
7. **Lo manual no se pisa** (procedencia de B6 y `locked_fields`).
8. **A demanda y con vista previa**; nada automático.

## 8. Casos de prueba antes de implementar

- RAR4, RAR5 y RAR5 sólido mínimos (los de BL-PORT3, D-4) → CBZ con el mismo manifiesto.
- RAR cortado / CRC malo → no se publica nada, original intacto, temporal limpio.
- `.cbr` que es un ZIP → **no se recomprime**: solo cambia la extensión (decisión D5).
- Ya existe `<nombre>.cbz` → no se convierte y se explica.
- Espacio insuficiente → no empieza.
- Fallo del `commit` tras el `os.replace` → la pasada siguiente reconcilia sin reconvertir.
- Deshacer → vuelve el `.cbr` a su ruta, la fila recupera ruta, hash y tamaño.
- Cifrado, multivolumen (`.part1.rar`), `ANIDADOS` → no se convierten, con motivo.
- El caso que las referencias no cubren: copia «sin excepción» pero con una entrada que
  difiere → la verificación la rechaza.

## 9. Matriz (criterios y pesos por defecto, sin mover)

Puntuación 1–5 por enfoque de **conversión** (la parte que toca ficheros):

| Criterio (peso) | A. Kapowarr | B. ComicTagger | C. Propio sobre B6 (I1+I3+I4+I9) |
|---|---|---|---|
| Encaje con el flujo del Coleccionista (25) | 2 (borra, sin vista previa por archivo) | 3 (CLI, borra si se pide) | 5 |
| Coste en Pi (20) | 1 (no funciona en ARM; recomprime) | 4 (sin recomprimir; memoria por entrada) | 4 (ídem + verificación) |
| Seguridad, legalidad y licencia (20) | 1 (`rar` no libre; borrado sin verificar) | 3 (Apache-2.0; sin verificación) | 5 |
| Cobertura del requisito core (15) | 3 | 4 | 4 (solo CBZ como destino) |
| Adaptabilidad al stack y al modelo (10) | 2 | 3 | 5 |
| Mantenimiento de la referencia (5) | 4 | 4 | 3 (código propio) |
| Lock-in y coste de salida (5) | 3 | 4 | 5 |
| **Total ponderado (sobre 5)** | **1,90** | **3,45** | **4,55** |

## 10. IGUALAR / MEJORAR

**IGUALAR (mínimo competitivo):** convertir sin recomprimir (ComicTagger), previsualizar
(Kapowarr), simular sin escribir (ComicTagger), salida segura «se queda como está»
(Kapowarr), conservar el original por defecto (metron-tagger, Calibre).

**MEJORAR (con evidencia):**
- Verificar la copia contra el original antes de publicarla (ninguna lo hace: §4.1).
- Deshacer la conversión (todas borran o dejan el original suelto, sin vínculo).
- Funcionar en la Pi sin `rar` propietario (Kapowarr no puede: §4.1).
- Proponer metadatos campo a campo con su procedencia (Komf agrega a ciegas: §4.2).

## 11. Decisiones para el PO

- **D1. Garantía «no se mueve ni se renombra nada».** Convertir cambia la extensión y el
  hash. Propuesta: la conversión es una acción explícita con su propia garantía («tu
  original queda apartado y puedes deshacerlo») y la promesa actual sigue para todo lo
  demás.
- **D2. Qué pasa con el original.** Propuesta: apartarlo en una carpeta de ZascArr en el
  mismo disco (sin copiar: `os.replace`), con «Vaciar» separado y confirmado. Coste: hasta
  ~202 GiB más mientras no se vacíe; caben (1,1 TiB libres), pero conviene por tandas.
- **D3. Archivos que comparte un cliente P2P.** Si Transmission o aMule sirven archivos de
  la biblioteca, convertirlos rompe el compartido. ¿Se excluyen? ¿Cómo se detecta (carpeta
  configurada, cliente de descargas)?
- **D4. Conversión automática al descargar.** Propuesta: no, por ahora (I7).
- **D5. `.cbr` que ya es un ZIP.** Propuesta: «convertir» = renombrar a `.cbz` sin tocar el
  contenido, por el mismo flujo (vista previa, deshacer).

## 12. NOT RUN

- Tiempo y memoria de convertir un CBR completo en la Pi (solo se midió listar y leer una
  página en #308), en especial los RAR sólidos grandes.
- Diferencia de tamaño CBR → CBZ con `ZIP_STORED`.
- Qué parte de los 4.891 CBR es convertible (cifrados, multivolumen, anidados, dañados).
- Efecto en Kavita de que un archivo cambie de extensión (¿conserva el progreso de lectura?).
- Revisión de vulnerabilidades de `unar`/GNUstep (pendiente desde #308).
- Sonarr/Radarr y Kavita/Komga: no se ha leído su código en esta ronda (no reescriben el
  archivo de medios según la ficha B6, sin revalidar).
- Estado de la petición #50 de Kapowarr.

## 13. Caducidad

~60 días (2027-01-06), o antes si cambia BL-PORT3 (#418), el contrato de B6 o la decisión
sobre `unar`.

**Barrera legal:** esta ficha toma ideas, no código. Kapowarr y Mylar3 son GPL-3.0,
ComicTagger Apache-2.0 y Komf MIT; antes de reutilizar cualquier implementación, revisar el
fichero concreto y sus avisos.
