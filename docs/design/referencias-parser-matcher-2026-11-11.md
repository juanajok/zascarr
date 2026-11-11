# Parser y matcher: qué adoptar de otros proyectos (2026-11-11)

> Revisión estática de código y documentación. **No se ha ejecutado** ningún
> proyecto externo en este análisis: sus dependencias no están instaladas y no
> se han levantado sus servidores. No se copia código; se comparan decisiones.
> Zascarr es GPL-3.0, así que la licencia no impide reutilizar, pero el criterio
> es no arrastrar modelos ajenos.

## 1. Proyectos y versiones

| Proyecto | Rol | GitHub | Stars | Último push | Licencia | Commit revisado |
|---|---|---|---:|---|---|---|
| **Kavita** | servidor de lectura de cómic/manga | <https://github.com/Kareadita/Kavita> | 12.102 | 2026-11-11 | GPL-3.0 | `a9cdf1c` (`develop`) |
| **Suwayomi** | servidor de manga | <https://github.com/Suwayomi/Suwayomi-Server> | 8.041 | 2026-11-10 | MPL-2.0 | `d521528` (`master`) |
| **Komga** | servidor de cómic/manga | <https://github.com/gotson/komga> | 6.840 | 2026-11-11 | MIT | `db2ad64` (`master`) |
| **Mylar3** | gestor/descargador de cómic | <https://github.com/mylar3/mylar3> | 1.469 | 2026-03-25 | GPL-3.0 | `cdc94a4` (`master`) |
| **Kapowarr** | gestor/descargador de cómic | <https://github.com/Casvt/Kapowarr> | 1.112 | 2026-11-10 | GPL-3.0 | `c191dda` (`main`, v1.3.2) |
| **ComicTagger** | etiquetador y parser de referencia | <https://github.com/comictagger/comictagger> | 844 | 2026-11-02 | Apache-2.0 | `fa11a34` (`develop`) |
| **ComiXed** | servidor/biblioteca de cómic | <https://github.com/comixed/comixed> | 297 | 2026-11-10 | GPL-3.0 | `dd2fef9` (`main`) |

Mylar3 es el menos activo (último commit en `master` de 2025-08; el push más
reciente es de 2026-03), pero se mantiene por estrellas/uso y su parser es la
referencia histórica que heredó ComicTagger.

## 2. Qué hace cada uno

### Kavita
`Kavita.Services/Scanner/Parser.cs`, `BasicParser.cs`, `ComicVineParser.cs`.

- Separa el parser por **tipo de biblioteca** (Comic, Manga, ComicVine, Book,
  Image).
- Extrae serie/volumen/capítulo del nombre; si la serie queda vacía, **baja a
  las carpetas** (`ParseFromFallbackFolders`), y en ComicVine usa la carpeta
  `Serie (Año)`.
- Detecta especiales con una lista amplia (`Annual`, `TPB`, `Omnibus`,
  `One Shot`, `Director's Cut`, `FCBD`, etc.) y los mueve a un volumen especial.
- `ComicInfo` pisa los valores del nombre.
- Usa expresiones de volumen/capítulo equivalentes para manga, con rangos.

**Lección:** el contexto de carpeta y la lista de formatos especiales son
prácticos; su modelo volumen/capítulo no es el de Zascarr (Issue + anual).

### Kapowarr
`backend/base/file_extraction.py`.

- Trabaja con **filepath completo**: serie, año y volumen pueden venir de la
  carpeta; el número de issue se busca por **posición relativa** a volumen,
  año y especiales.
- Si no hay volumen en ningún sitio, **asume volumen 1** (`assume_volume_number`).
- Detecta `TPB`, `one-shot`, `HC`, `omnibus` antes de buscar número.
- Reconoce rangos `11-25` como **tupla** y los enlaza a todos los Issues del
  rango; un archivo puede corresponder a varios Issues.
- Tiene un matcher de archivos por volumen con `forced_match` manual y
  reescaneo; reintenta con el siguiente candidato si falla (idea ya usada en
  `orchestrator.py`).

**Lección:** la posición y el contexto de carpeta son mejores que buscar “el
último número”; el rango como múltiples Issues es correcto para *su* modelo
muchos-a-muchos, no para el `files.issue_id` 1:1 actual de Zascarr.

### Mylar3
`mylar/filechecker.py::parseit` (parser histórico, ≈1.500 líneas con
excepciones, anuales, variantes alfanuméricas, tags, rangos y subcarpetas).

- Toma `path`, `filename` y `subpath`; las subcarpetas aportan contexto.
- Separa número, año, volumen, anual, especial y tags con muchas reglas y
  listas de excepciones (`ISSUE_EXCEPTIONS`).
- Reconoce variantes (`15A`, `Director's Cut`), `N of M`, anuales y números
  alfanuméricos.
- Es el ejemplo de **no volver a inventar un parser monolítico de 1.500
  líneas**: gran cobertura, alto coste de mantenimiento.

**Lección:** adoptar su catálogo de *casos* (anual, variante, `of M`, contexto),
no su estructura.

### Suwayomi
`eu.kanade.tachiyomi.util.chapter.ChapterRecognition`.

- Modelo de **manga**: capítulo/volumen, no serie/Issue de cómic USA.
- Normaliza `ch.`, `chapter`, `vol`, `volume`, `season`, tags no deseados.
- Resuelve decimales y sufijos alfanuméricos (`12.5`, `12a`), y da
  `extra/omake/special` un valor decimal para ordenar.
- Si hay varios números, elimina primero los tags de volumen y se queda con el
  primer número restante.

**Lección:** es buena referencia para **normalizar el número para ordenar**;
no para decidir a qué serie/Issue pertenece un cómic occidental.

### Komga
`FileSystemScanner.kt`.

- Su unidad es **carpeta = serie** y **archivo = libro**. No intenta adivinar
  una serie a partir del nombre del archivo.
- Los oneshots se configuran por carpeta; los sidecars (ComicInfo/metadata) y
  las fuentes externas aportan identidad.
- No tiene un fuzzy matcher de títulos de serie en el escáner.

**Lección:** la carpeta es una señal fuerte de colección, pero no puede ser la
identidad en Zascarr: la biblioteca real mezcla carpetas, ediciones y series
del catálogo.

### ComicTagger
`comicapi/filenameparser.py`.

- Parser de nombre mucho más pequeño que Mylar.
- Busca el número por posición: normalmente la última palabra numérica; `#N`
  tiene prioridad; acepta `N of M`, cuenta de issues, volumen `vN`, año y
  one-shots (`TPB/OS/OGN`).
- Extrae serie a la izquierda del número; el volumen/año se separa aparte.
- No usa la carpeta para la serie (a diferencia de Kavita).

**Lección:** el enfoque “posición + marcadores” es más fácil de testear que
una lista interminable de regex; `N of M` es información útil de contexto, no
identidad.

### ComiXed
`FilenameScraperAdaptor.java`.

- El usuario define **reglas regex** con posiciones de serie, volumen, issue y
  fecha; la regla se aplica y extrae grupos.
- Es configurable y potente, pero traslada la complejidad al usuario y puede
  romper la biblioteca si una regla es incorrecta.

**Lección:** no meter un motor de reglas arbitrarias en el camino automático;
sí mantener alias locales aprendidos y, quizá, una regla manual por serie.

## 3. Matriz de decisión

| Idea | Decisión | Por qué |
|---|---|---|
| Contexto de carpeta para desambiguar serie/volumen | **Adoptar como pista, no como identidad** | Kavita/Kapowarr/Mylar lo usan; Zascarr tiene catálogo y carpetas mixtas. Solo debe desempatar candidatos, nunca crear una serie. |
| `ComicInfo` manda sobre el nombre | **Adoptar (ya existe)** | Coinciden todos; es capa 0 y evita adivinar. |
| Lista de formatos especiales (`TPB`, `Omnibus`, `Annual`, `One Shot`, `FCBD`) | **Adaptar** | Zascarr ya tiene `edition_kind`/`Issue.format`; falta mapear más formatos y usar el formato en el matcher. |
| Búsqueda de número por posición (evitar año/volumen) | **Adaptar** | Kapowarr/ComicTagger lo demuestran; nuestra prioridad de patrones ya lo hace en parte. Añadir pruebas de solapamiento, no reescribir todo. |
| `N of M` / cuenta de la miniserie | **Adoptar como contexto/confianza** | ComicTagger y Mylar lo extraen; no identifica el Issue, pero ayuda a validar rango y detectar números falsos. |
| Normalizar número para ordenar (`12a`, `12.5`, `½`, `∞`) | **Adoptar en una función de cálculo** | Kapowarr/Suwayomi/ComicTagger; mantener `issue_number` como string canónico, no cambiar el esquema. |
| Pack que cubre varios Issues | **Rechazar por ahora; revisión** | Kapowarr lo enlaza a varios Issues, pero Zascarr tiene `files.issue_id` 1:1. Hace falta tabla puente; no forzar un Issue falso. |
| Asumir volumen 1 si no aparece | **Rechazar** | Kapowarr puede permitírselo en su modelo; en Zascarr produciría enlaces falsos entre ediciones. La ausencia de volumen debe ser ambigua. |
| Carpeta = serie | **Rechazar como regla general** | Komga se apoya en una estructura ordenada; la biblioteca real de Zascarr no la garantiza. Usar solo como pista. |
| Reglas regex configurables por el usuario | **Rechazar en el camino automático** | ComiXed lo ofrece, pero es superficie de error y seguridad; mejor alias locales aprendidos + tests. |
| Parser monolítico de miles de líneas | **Rechazar** | Mylar demuestra cobertura, pero también coste de mantenimiento; Zascarr debe crecer con reglas medidas y tests. |
| Modelo capítulo/volumen de manga | **Rechazar para la identidad** | Suwayomi no distingue serie/Issue/anual; solo reutilizar normalización numérica. |
| Reintento con siguiente candidato | **Adoptar (ya existe)** | Kapowarr/Mylar; ya está en `orchestrator.py`. |
| Match manual forzado y reescaneo | **Adoptar (ya existe)** | Kapowarr; Zascarr ya tiene asignación manual/alias. |
| Copiar código GPL/Apache | **Rechazar** | Se adoptan ideas y se implementan con tests propios; no se arrastran modelos ni texto. |

## 4. Qué hacer después, en orden

1. **Contexto de carpeta como desempate** en el matcher: si el parser no cambia
   de candidato pero hay empate, la carpeta puede preferir uno; si no hay
   evidencia, sigue `unsorted`. **Implementado en esta rama**: 0 cambios en la
   foto actual de 3.556 pendientes porque no hay empates con evidencia, pero
   cubierto con tests de volumen, año y contradicción.
2. **Tabla de formatos** (`annual`, `special`, `TPB`, `omnibus`, `one_shot`)
   para que el matcher no confunda una recopilación con una grapa; el modelo ya
   tiene el campo. **Implementado para Omnibus/TPB/Hardcover/Graphic Novel**.
3. **`N of M` y cuenta de issues** como confianza, nunca identidad.
   **Capturado en el parser** (`issue_count`); falta usarlo en el matcher.
4. **Normalizador de número para ordenar** sin tocar `issue_number`.
5. **Benchmark etiquetado de 200 archivos** de la biblioteca (ver
   [`benchmark-parser-biblioteca-2026-11-11.md`](benchmark-parser-biblioteca-2026-11-11.md)).
6. Solo después, evaluar packs con tabla puente; no mezclarlo con el parser.

## 5. Límites de esta revisión

- No se ejecutaron Kavita, Komga, Mylar3, Kapowarr, ComicTagger, ComiXed ni
  Suwayomi: solo lectura de código/documentación. Las afirmaciones de
  comportamiento son estáticas y se limitan a los archivos citados.
- No se copió código. Las licencias se respetan.
- Las estrellas y fechas son una foto de GitHub el 2026-11-11; no miden calidad.
