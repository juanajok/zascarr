# Ficha de benchmarking — Propuestas de serie desde el contexto de carpetas

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Antecedentes:
> `docs/design/auditoria-b14-carpetas.md` (la carpeta sugiere y agrupa, **no asigna sola**) y el primer registro real
> (BACKLOG, «Primer registro real»). **Esta ficha no implementa nada**: fija el problema, la evidencia, el contrato y las
> pruebas que deben existir antes de la primera rebanada. Lo aquí propuesto se prioriza en revisión.

## Historia

*Como coleccionista, quiero ver los archivos pendientes agrupados por contexto de carpeta, con propuestas de serie
explicadas y confirmables, para crear las series que faltan y asignar archivos sin que ZascArr confunda una coincidencia
textual con una edición distinta.*

No es un autoimportador desde carpetas: **ninguna acción es automática**.

## Problema observado (datos reales, primer registro en producción, 2026-10-05)

- 1.542 archivos registrados en su sitio; **1.322 en «Por revisar»** (1.308 sin identificar + 14 filas previas con la ruta
  obsoleta) y **0 filas con `Issue`**.
- **5 series locales** (`Absolute Batman`, `BATMAN` 2025, `BPRD`, `Far Sector`, `The DC Universe by Mike Mignola`), **ninguna** de
  las familias grandes de la colección (Superman, Patrulla-X, Nuevos Mutantes, The Boys, Carlos Giménez): «Por revisar» **no
  tiene destino local al que asignar**.
- **17 «reconocidos» que no están clasificados**: coincidencia de serie guardada en metadatos (`direct`, 1,0), sin `Issue`, y
  **fuera de «Por revisar»** (la bandeja filtra por `match_status = unsorted`; decisión de B11: «la resuelve el enriquecedor»).
  8 `Absolute Batman 0X` → `Absolute Batman` (razonable). **9 `Batman - Saga Scott Snyder 01…09` → `BATMAN (2025)` a 1,0: igualdad
  textual, edición distinta**; la carpeta (`Batman - Saga de Scott Snyder (2019)`) ya lo contradecía.
- Comportamiento actual: nadie mira la carpeta; el único camino para tener un destino es **Descubrir, serie a serie**; y un
  archivo con serie «sugerida» sin número queda sin superficie de revisión.
- Resultado deseado: que cada archivo pendiente tenga delante una **propuesta explicada** (o su ausencia), agrupada, y que
  crear una serie o asignar sea una **decisión humana con vista previa**.

### Medición de partida (biblioteca real, 1.542 nombres; `docs/design/auditoria-b14-carpetas.md`)
63 % nombre = carpeta; 16 % la carpeta **refina** el nombre (volumen, año, editorial, saga); 13 % distintos. **123 archivos (8 %)
están en una carpeta que no es su serie** (autor, contenedor, orden de lectura/crossover, arco); 5 de 16 carpetas «malas»
pasan por una regla de mayoría con cualquier umbral 50-80 %. Cifras con el parser anterior a #81 (evidencia histórica).

## Referencias consultadas

Licencias comprobadas en la API de GitHub: Kapowarr, Sonarr, Mylar3 y Aidoku **GPL-3.0**; Suwayomi-Server **MPL-2.0** (copyleft por
fichero, con componentes de terceros). **Solo como patrón; no se copia código** (CLAUDE.md §13, barrera legal: revisar el fichero
concreto antes de reutilizar nada). Lectura de código, **no ejecutadas**; «no lo encontré» no equivale a «no existe».

> **Corrección del borrador.** Una primera versión de esta ficha decía que Suwayomi «no aplica» y que «se buscó el equivalente y no lo
> hay». **Eso era falso: no se había buscado.** Suwayomi-Server tiene una *fuente local* que lee una biblioteca por carpetas, y es una
> referencia directa. Se añadió también **Aidoku**, a petición expresa.
>
> **Confirmado por el operador (2026-10-05):** «Aizoku» es **Aidoku** (`Aidoku/Aidoku`, lector de manga para iOS/iPadOS/macOS). La
> búsqueda literal «aizoku» en GitHub solo devuelve un asistente de IA sin relación.

| Referencia | Versión leída | Ficheros |
|---|---|---|
| Kapowarr | `main` @ `c191dda` (última release V1.3.2) | `backend/features/library_import.py`, `backend/implementations/matching.py` (`select_best_volume_result_for_file`), `backend/implementations/comicvine.py` (`filenames_to_cvs`), `docs/src/general_info/matching.md` |
| Sonarr | `v5-develop` @ `da99063` (última release v4.0.20.3014; **se leyó develop**, no la release) | `frontend/src/AddSeries/ImportSeries/Import/{useImportSeries.ts, importSeriesEligibility.ts, SelectSeries/ImportSeriesSelectSeries.tsx}`, `src/NzbDrone.Core/RootFolders/RootFolderService.cs` (`GetUnmappedFolders`) |
| Mylar3 | `master` @ `cdc94a4` (v0.8.3) | `mylar/librarysync.py` (`libraryScan`) |
| Suwayomi-Server | `master` @ `cff9169` (última release v2.4.2366) | `server/src/main/kotlin/eu/kanade/tachiyomi/source/local/LocalSource.kt` (listado, detalles, capítulos), `…/local/io/LocalSourceFileSystem.kt` |
| Aidoku | `main` @ `3091ef2` (última release v0.9) | `Aidoku/Core/Sources/BuiltIn/Local/{LocalFileNameParser,LocalFileManager,LocalSource}.swift`, `Aidoku/Features/Source/LocalFileImportView.swift`, `AidokuTests/LocalFileNameParserTests.swift` |

## Cómo lo resuelve cada una

**Kapowarr — «Library Import»** (`propose_library_import` / `import_library`).
- Recorre las carpetas raíz, descarta lo ya importado **por ruta exacta** y los archivos sueltos en la raíz, y limita cuántas carpetas
  procesa por pasada (`limit`, 20) por los límites de la fuente.
- **Agrupa archivos** por título de serie + «anual» + versión especial + año (±1) + coherencia volumen/número
  (`create_groups`); la agrupación sale del **nombre de archivo**, y de la carpeta solo `prefer_folder_year`. Su documentación dice que
  extrae información «del nombre, la carpeta y la carpeta padre».
- Propone **un único volumen por grupo** (`filenames_to_cvs` → `select_best_volume_result_for_file`): **filtros duros** (el título debe
  coincidir; idioma; versión especial; el recuento de números del volumen no puede ser menor que el cubierto por los archivos) y
  **puntuación** (año exacto +1, año aproximado +1, **volumen +2**, recuento exacto +1, número mayor que el recuento −1).
  Regla de su documentación: para una serie normal «**el año o el número de volumen tiene que coincidir**»: **un título solo no basta**.
- `import_library` solo actúa sobre los emparejamientos que **el usuario envía**. Adopta la carpeta común como carpeta del volumen
  (`volume_folder=lcf`) **sin mover** salvo que se pida renombrar. Si el volumen ya estaba, **mueve** los archivos a su carpeta y deja un
  comentario que asume «la probabilidad de que el emparejamiento sea erróneo es bastante baja».

**Sonarr — «Import Existing Series»** (frontend + `RootFolderService`).
- «Carpetas sin mapear» = **subcarpetas de primer nivel** de la raíz (a una profundidad que sale del formato de nombres); **una carpeta = una
  serie**; se excluyen carpetas especiales.
- El nombre de la carpeta es el **término de búsqueda**; las búsquedas van por una **cola serie a serie**. Si el usuario no ha editado, **se
  preselecciona el primer resultado** (`data[0]`), **sin umbral ni corroboración**.
- Estado explícito por carpeta: **`ready | unmatched | existing | duplicate`**. Dos carpetas con la misma serie elegida → solo una es
  importable y las demás se **desmarcan** (no se fusionan). Importar envía el `path` de la carpeta (**en sitio**) y desactiva la búsqueda de
  faltantes (`searchForMissingEpisodes: false`): importar no dispara efectos.

**Mylar3 — «Import a directory»** (`libraryScan`).
- Escanea un directorio y lee, por este orden de interés, **metadatos embebidos del CBZ** (ComicInfo) y un fichero **`cvinfo` en la carpeta** que
  contiene el enlace al volumen: **evidencia explícita escrita por el usuario**, que se aplica a todo lo de esa carpeta.
- Deja todo en una **tabla de preparación** (`importresults`) con estado **`Not Imported`**, agrupada por nombre dinámico + año; nada entra
  en la biblioteca hasta que el usuario lo gestiona en «Import Results Management».

**Suwayomi-Server — fuente local** (`LocalSource`, `LocalSourceFileSystem`).
- La biblioteca es un directorio raíz (`localMangaRoot`); **cada subcarpeta de primer nivel** (que no empiece por `.`) **es una serie** y su
  **título es el nombre de la carpeta** (`title = mangaDir.name`). Los capítulos son los archivos soportados (o subcarpetas) de dentro.
- **No hay proposición ni confirmación**: la identidad de la serie es la convención «carpeta = serie», que la persona debe respetar.
- Los **metadatos de serie** se leen de un `ComicInfo.xml` **en la carpeta de la serie** (o del heredado `details.json`) y, si falta, se copia el
  `ComicInfo.xml` del primer capítulo al nivel de la serie: evidencia **declarada por la persona**, a nivel de carpeta.
- Para el número de capítulo llama a `ChapterRecognition.parseChapterNumber(manga.title, nombre_de_archivo, …)`: **se le pasa el título de la
  serie (el de la carpeta) para descontarlo del nombre antes de buscar el número**, de modo que las cifras del título no se lean como número.

**Aidoku — archivos locales** (`LocalFileManager`, `LocalFileNameParser`, `LocalFileImportView`).
- Misma convención: dentro de su carpeta «Local», **cada carpeta es una serie** y la BD se **sincroniza desde el sistema de ficheros**
  (`scanLocalFiles`), con un escuchador de cambios. La BD es derivada: recalcularla es idempotente.
- **Importar un archivo es un formulario explícito**: la serie se **prefija** con `comicInfo.series` y, si no hay, con
  `LocalFileNameParser.parseMangaSeries` (un port del parser de Kavita, **con pruebas unitarias propias**); si la serie ya existe
  (`hasSeries`) se **preselecciona**, si no aparece «serie nueva»; la persona puede cambiarla.
- **Valida antes de dejar importar**: el nombre de una serie nueva no puede repetir una existente ni estar vacío, y el volumen/capítulo no puede
  coincidir con uno ya presente en la serie; **sugiere el siguiente número** libre. La importación **copia** el archivo a su almacenamiento.

## Supuestos de su modelo que NO valen en ZascArr

| Supuesto | Por qué no vale aquí |
|---|---|
| **Una carpeta = una serie, por convención que la persona respeta** (Sonarr, Suwayomi, Aidoku; Kapowarr con carpeta de volumen) | En la biblioteca real hay carpetas de **autor** (`Carlos Giménez`: 52 archivos, 26 obras), **contenedores** (`_Omnibus`, `_Specials`, `spin offs`), **orden de lectura / crossover** (`Flash (1987)` con `Green Lantern` dentro), **arcos** (`Locas - La muerte de Speedy`) y **franquicias** (`Marvel-Inhumanos`). |
| **Hay una fuente remota que propone el candidato** (CV/TVDB) | En ZascArr las fuentes son opcionales y están desactivadas por defecto; las propuestas deben funcionar **con evidencia local** y usar fuentes solo si el usuario las pide. |
| **El mejor resultado se preselecciona** (Sonarr) | Un título genérico con coincidencia exacta es justo lo que falló con `BATMAN`. |
| **Mover es aceptable si el emparejamiento «casi seguro» acierta** (Kapowarr) | ZascArr no mueve sin confirmación y con copia verificada (ADR 0006). |
| Un único recorrido, estado en memoria/cliente | Pi con 512 MB, posibles reinicios: la propuesta debe poder recalcularse de la BD sin releer discos. |
| La app es dueña del almacenamiento (Aidoku copia a su carpeta; Suwayomi lee un único `localMangaRoot` con la forma impuesta) | La biblioteca de ZascArr es **del coleccionista**, con varias raíces y estructuras (por tradición, por autor, por franquicia); se registra **en su sitio**. |
| Series ≡ volúmenes con `issue_count` conocido | Sin fuente remota no hay recuento: el filtro «el recuento cubre los números» no se puede aplicar. |

## Adoptar / adaptar / descartar

**Adoptar**
- Estado **explícito y visible** por propuesta, sin efectos hasta confirmar (Sonarr `eligibility`; Mylar `Not Imported`; Kapowarr solo importa lo enviado).
- **Importar en sitio** y **sin efectos colaterales** (Sonarr; Kapowarr `volume_folder`).
- **Duplicados entre carpetas**: detectar que dos grupos apuntan a la misma serie y **no fusionarlos** (Sonarr `duplicate`) → nuestras carpetas gemelas.
- **Límite por pasada y cola serie a serie** para las fuentes externas (Kapowarr `limit`; Sonarr `lookupQueue`) → respeta los 1,0-2,5 s por petición del proyecto.

**Adaptar**
- **ComicInfo primero, nombre después, y mostrarlo** (Aidoku: `comicInfo.series ?? parseMangaSeries`) → la propuesta usa la señal **más fuerte disponible** y dice cuál usó.
- **Validar colisiones *antes* de permitir confirmar** (Aidoku: nombre de serie único, número no repetido en la serie) → en la vista previa: serie que ya existe (reutilizar), número ya ocupado, destino ocupado (B15).
- **Descontar el título de la serie antes de leer el número** (Suwayomi `ChapterRecognition`) → una vez confirmada la serie de un grupo, el parser del número puede recibir el título como pista (resuelve casos tipo `Top 10 07`, `Delta 99 - 04`). *Mejora posterior, no de la primera rebanada.*
- **Evidencia declarada a nivel de carpeta** (Suwayomi: `ComicInfo.xml` de serie; Mylar: `cvinfo`) → dos referencias independientes llegan a la misma idea: una **señal explícita de la persona que prevalece sobre lo inferido**. No se implementa en la primera rebanada, pero el modelo de señales deja sitio a una señal «declarada».
- **Un perfil por carpeta raíz, declarado una vez** (Sonarr deriva la profundidad del formato de nombres; Suwayomi fija la forma) → que la persona pueda decir «`Comics/` = una carpeta por serie» y «`Graphic Novels/` = una carpeta por autor» una sola vez. *Decisión abierta (ver abajo): no se asume por defecto.*
- **«El título solo no basta»** (Kapowarr: año **o** volumen tiene que coincidir; tolerancia ±1 año) → *corroboración obligatoria* para llegar a «lista»; el título solo, aunque sea exacto, es «requiere confirmación».
- **Agrupar por contexto** (Kapowarr `create_groups`, Mylar por nombre dinámico + año) → agrupar por **(carpeta inmediata + título normalizado)**, mirando **varias carpetas ascendentes**, y medir **por archivo** el acuerdo con la carpeta (no por carpeta: ver la auditoría).
- **Evidencia explícita del usuario en la carpeta** (Mylar `cvinfo`) → *no se implementa en la primera rebanada*, pero el diseño deja sitio a una señal «declarada» que prevalezca sobre las inferidas.
- **Metadatos embebidos primero** (Mylar, ComicInfo) → ya es la capa 0 del triaje: se reutiliza como señal más fuerte cuando existe.

**Descartar**
- Preselección del primer resultado sin umbral (Sonarr) y el supuesto «una carpeta = una serie».
- Mover automáticamente a la carpeta del volumen asumiendo baja probabilidad de error (Kapowarr, `VolumeAlreadyAdded`).
- Depender de una clave de API para poder proponer.
- **Copiar los archivos al almacenamiento de la app** al importar (Aidoku) y el **escuchador de cambios del sistema de ficheros** que resincroniza solo: ZascArr registra en su sitio y solo escribe tras una confirmación.
- **Identidad por convención sin comprobación** (Suwayomi: «carpeta = serie» sin contraste con nada): es lo que la auditoría de la biblioteca real desmiente en un 8 % de los archivos.

### Qué se toma de cada referencia (resumen)

| Decisión | Suwayomi-Server | Aidoku | ZascArr (propuesto) |
|---|---|---|---|
| Carpeta como señal | La carpeta de primer nivel **define** la serie | Carpeta por serie en su almacenamiento | **Evidencia, nunca autoridad ciega** |
| Metadatos declarados | `ComicInfo.xml` de la carpeta de serie | `ComicInfo` embebido, luego parser | **Mayor prioridad como señal**, con el conflicto visible |
| Nombre de archivo | Descuenta el título de la serie antes de leer el número | Parser local (port del de Kavita, con pruebas) | Parser existente, **enriquecido por el contexto** una vez confirmada la serie |
| Creación de serie | Implícita por estructura | Serie **prefijada y validada** antes de importar | **Propuesta explicada; confirmación obligatoria** |
| Archivos | Fuente local, en su sitio | **Copia** al almacenamiento de la app | **Mantener las rutas originales**; solo mover tras confirmar y por el servicio recuperable |

## Contrato de la historia

### Política de conflicto (invariante de la historia)

> **Si el nombre de archivo coincide exactamente con una serie, pero la carpeta, el año o la edición discrepan, el resultado es siempre
> `requiere_confirmacion` («por confirmar»): nunca una asignación directa, nunca un enlace a `Issue`, nunca una serie «preseleccionada».**
>
> Un título exacto sin corroboración por año o volumen tampoco llega a `lista`. Es el caso real `Batman - Saga Scott Snyder` ↔ `BATMAN (2025)`;
> es la prueba nº 1 de esta ficha y el criterio de aceptación de la medición (falsos `lista` = 0).

### Entrada
- Archivos de `files` con `issue_id IS NULL`, no descartados, y **de dos tipos**: (a) `match_status = unsorted` (hoy en «Por revisar») y (b) **«serie sugerida pero sin `Issue`»** (hoy invisibles: los 17). Se trabaja **sobre la BD** (`file_path`, `file_name`, `metadata`), sin releer discos ni hashear.
- **Contexto de carpetas ascendentes** (no solo `parent.name`), descartando el primer nivel (tradición) y los contenedores conocidos (`_Omnibus`, `_Specials`, `varios`, `revisar`…).
- Series locales existentes (para *reutilizar* en vez de crear).

### Unidades y señales
Un **grupo** es *(carpeta inmediata limpia, título normalizado del nombre)*. Señales por archivo y por grupo:

| Señal | Qué es |
|---|---|
| S1 título del nombre | tras quitar ruido y prefijos de orden de lectura (cohorte) |
| S2 carpeta limpia | título, **año**, **volumen** (`Vol2`), **editorial/edición** (`(Ed.Zinco)`, `Omnigold`) y «Saga de…» separados del título |
| S3 acuerdo archivo↔carpeta | proporción **de archivos del grupo** cuyo título coincide con la carpeta (por archivo) |
| S4 diversidad | cuántos títulos distintos hay en la carpeta (autor/contenedor ⇒ muchos) |
| S5 año | año de carpeta/nombre frente a `Series.start_year` de un candidato (±1) |
| S6 volumen/edición | volumen o marcador de edición frente al candidato |
| S7 embebida | ComicInfo (serie, volumen, año) si existe |
| **S8 conflicto** | año, volumen, edición o título de carpeta que **contradice** al candidato |

### Estados de una propuesta (explícitos, como Sonarr `eligibility`)
`lista` · `requiere_confirmacion` (hay conflicto o solo coincide el título) · `ambigua` (varias series locales posibles) ·
`existente` (se reutilizaría una serie local, corroborada) · `sin_propuesta`. **Ninguno se aplica solo**; ninguno viene preseleccionado.

### Umbrales (HIPÓTESIS a medir, no a fijar)
- «lista» exige: acuerdo S3 alto **por archivo**, **corroboración por año o volumen** (S5/S6) y **cero conflictos S8**.
- **Título exacto sin corroboración** ⇒ `requiere_confirmacion` (es el caso `BATMAN`).
- Cualquier conflicto S8 ⇒ `requiere_confirmacion` con la explicación, aunque el título sea exacto.
- Diversidad S4 alta ⇒ no se propone la carpeta como serie del grupo (autor/contenedor).
- **Criterio de aceptación de la medición (antes de implementar):** sobre los 1.542 nombres reales con las etiquetas de la auditoría,
  **ningún grupo de una carpeta etiquetada «incorrecta» sale como `lista`** (falsos «lista» = 0); se acepta a cambio un volumen alto de
  `requiere_confirmacion`. Se reutiliza `scripts/medicion/medir_carpetas.py`.

### Salida (por grupo)
Propuesta **explicada**, por ejemplo: «`Batman - Saga de Scott Snyder (2019)` **contradice** `BATMAN (2025)` (año y edición): requiere confirmación». Con: archivos afectados, serie propuesta (nueva o existente), señales a favor y en contra, y qué pasaría con cada archivo.

### Acciones (todas manuales)
- **Crear serie** (con título, año y **tradición** que elige la persona; la sugerencia sale de la carpeta pero **no se preselecciona**) — opcionalmente buscando en Descubrir si hay fuentes activas.
- **Usar una serie existente** (lista acotada a candidatas).
- **Dejar pendiente** / **ignorar**.
- «Aplicar a varios grupos» solo para los marcados **a mano** y en estado `lista`; nunca por defecto.

### Vista previa (antes de cualquier escritura)
Archivos afectados (nº, tamaño, primeros nombres); **series que se crearían o reutilizarían**; **conflictos**; **archivos excluidos** (repetidos, en conflicto, formatos no soportados); y, si la acción incluye asignar, **la ruta de destino de cada archivo** y las colisiones (`destino ocupado`, ediciones B15), porque **asignar mueve y renombra** (ADR 0006).

### Confirmación
Una acción explícita **por grupo** («Crear «X (2019)» y asignar 24 archivos»). Se separan **crear la serie** (catálogo, reversible) y **asignar** (mueve ficheros, por el servicio recuperable, con límites por bytes/cantidad/simultaneidad).

### Reversibilidad y auditoría
No se borra ni se mueve nada en la primera rebanada. Crear una serie queda **registrado** (qué evidencia, qué archivos, quién/cuándo) y es **deshacible mientras no tenga asignaciones vivas** (ya existe el 409 de `DELETE /api/series/{id}`). Dónde persistir el registro es una **decisión abierta** (ver abajo).

### Invariantes de ZascArr
No mentir (nunca llamar «clasificado» a lo que no lo está; «serie sugerida, pendiente de confirmar número/edición»), no borrar, confirmación explícita, sin autoasignación, sin hotlinking, coste Pi (propuestas calculables desde la BD; fuentes externas por cola y a petición), y el servicio de asignación recuperable para cualquier movimiento.

## Pruebas que deben existir antes de implementar

Con Postgres y ficheros reales (nombres reales de la biblioteca como casos; ningún dato personal en el repo):

1. **`Batman - Saga Scott Snyder` (carpeta `Batman - Saga de Scott Snyder (2019)`) frente a `BATMAN (2025)`** → `requiere_confirmacion`, con la contradicción explicada; **no** `lista`; **no** `existente`.
2. **`Absolute Batman`** frente a `Absolute Batman` (2024) → caso **correcto**: título exacto + año/volumen corroborado ⇒ puede ser `existente`/`lista` (sigue sin aplicarse solo).
3. **Carpeta de autor** (`Carlos Giménez`: muchos títulos distintos) → **no se propone como serie**; los archivos se agrupan por título del nombre.
4. **Franquicia / contenedor** (`Marvel-Inhumanos`, `_Omnibus`, `_Specials`, `spin offs`) → señal ignorada o degradada; **nunca** `lista`.
5. **Carpeta que miente en parte** (`Flash (1987)` con `Green Lantern` / `Impulse` dentro) → la carpeta es serie «casi entera»: los archivos discrepantes **salen del grupo**, no se arrastran.
6. **Arco dentro de una serie** (`Locas - La muerte de Speedy` sobre archivos `Locas`) → conflicto, no `lista`.
7. **Refinamiento** (`Superman Vol2 (Ed.Zinco)(1987-96)` frente al nombre `Superman`) → la carpeta aporta **volumen y año** (S5/S6) y corrobora.
8. **Carpetas gemelas** (`Superman (1987)` / `Superman Vol2…`, mismo contenido) → dos grupos hacia la misma serie: se muestran como **duplicado**, sin fusionar (Sonarr `duplicate`).
9. **Los 17 «serie sugerida sin `Issue`»** aparecen en la superficie de revisión y **no** cuentan como clasificados.
10. **Límite que ninguna referencia cubre:** propuesta **sin fuentes externas** (todas desactivadas) sigue funcionando y no hace ninguna petición de red.
11. **Idempotencia y concurrencia:** pedir la misma propuesta dos veces no crea nada; dos confirmaciones solapadas sobre el mismo grupo no duplican series (restricción de unicidad / servicio recuperable).
12. **Medición previa:** falsos `lista` = 0 sobre las carpetas etiquetadas incorrectas de la auditoría.
13. **Colisiones antes de confirmar** (Aidoku): una serie nueva que repite el título de una existente se propone como *reutilizar*, no como crear; un número ya presente en la serie y un destino ocupado aparecen en la vista previa y **bloquean** la confirmación de ese archivo, no la del resto.
14. **Perfil de carpeta raíz** (si se admite): con `Graphic Novels/` declarada «una carpeta por autor», la carpeta de autor **no** se propone como serie; con `Comics/` declarada «una carpeta por serie», sigue sin bastar el título si el año o el volumen la contradicen.

## Rebanadas propuestas (cada una es una PR; ninguna es la interfaz completa)

1. **Superficie de revisión de solo lectura**: grupos y estados con explicación (sin acciones de escritura) + hacer visibles los 17 como «serie sugerida, falta confirmar». Mide con el corpus real (criterio de aceptación de arriba). **Ficha técnica: `docs/design/rebanada-1-superficie-de-revision.md`** (contratos de entrada y salida, 16 pruebas de aceptación, entrega en dos PR).
2. **Crear serie** desde un grupo (formulario con tradición elegida a mano, sin fuentes externas), con vista previa y confirmación; registro auditable.
3. **Asignar un grupo** por el servicio recuperable (con la vista previa de rutas de destino).
4. **Descubrir** como fuente opcional de candidatas, por cola, a petición.

## Decisiones abiertas para la revisión (D1-D5)

- **D1 — Dónde persistir el registro de altas de serie.** `import_runs.details` (`kind = "series_from_folders"`, sin migración) frente a una tabla propia (migración). *Recomendación:* lo primero en la rebanada 2.
- **D2 — Los 17 «serie sugerida sin `Issue`» y la bandeja.** ¿Se unen a «Por revisar» con un estado propio, o una pestaña aparte? *Recomendación:* mismo lugar, estado propio. Implica revisar la decisión de B11 («se resuelve sola con el enriquecedor»).
- **D3 — Tradición de una serie nueva.** La carpeta de primer nivel (`Comics`, `BD`, `Tebeos`, `Manga`) sugiere, no decide; ¿se admite que la persona la fije por carpeta una sola vez? *Recomendación:* sugerir y exigir elección explícita; sin valor por defecto.
- **D4 — Perfil por carpeta raíz.** Sonarr y Suwayomi lo imponen por convención; Kapowarr y Mylar lo evitan agrupando por nombre. ¿La persona declara una vez cómo está organizada cada carpeta de primer nivel («una carpeta por serie», «por autor»…) o se infiere siempre? *Recomendación:* **inferir y mostrar**; la declaración queda como mejora posterior si la medición lo justifica.
- **D5 — Política de duplicados (~200 grupos de copias idénticas) y de referencias obsoletas (14).** Fuera de esta historia, pero la rebanada 1 las deja a la vista. *Recomendación:* decidir después de la rebanada 1, con las propuestas delante.

## Límites de esta ficha
Lectura de código de cinco referencias (Kapowarr, Sonarr, Mylar3, Suwayomi-Server y Aidoku) en versiones concretas, sin ejecutarlas; «Aizoku» = Aidoku (confirmado por el operador); Sonarr se leyó en `develop`, no en la release; las etiquetas de «carpeta incorrecta» son un juicio mío sobre nombres (auditoría), una biblioteca y un coleccionista; los umbrales son hipótesis hasta medirlos.
