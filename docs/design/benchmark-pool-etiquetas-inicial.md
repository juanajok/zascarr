# Benchmark y especificación — pool inicial de etiquetas (2026-11-13)

> **Estado:** propuesta de vocabulario inicial para BL-ETQ (sistema de etiquetas ya implementado).
> **Método:** lectura del código de ZascArr, benchmark previo de etiquetas y consulta en vivo a la
> API pública de AniList. **NOT RUN:** uso con coleccionistas reales, Kavita/Komga en ejecución y
> datos de una biblioteca real. No se copia código de las referencias.

## 1. Problema local

El sistema de etiquetas (`tags` + `series_tags`, namespace `etiqueta`) ya permite añadir, quitar,
crear, filtrar y recibir tags de AniList/ComicInfo. Pero una instalación nueva abre la ficha de una
serie con **cero etiquetas y cero ideas**: el campo pide escribir, y hasta que el coleccionista no
inventa palabras no hay nada que elegir. Eso castiga justo al público no técnico y hace que el
vocabulario crezca de forma arbitraria («space-opera», «Space Opera», «espacial»).

**Resultado deseado:** un vocabulario inicial **curado, corto y en español**, visible como ideas en
la ficha y disponible en el autocompletado desde el primer día, sin asignar nada automáticamente.
Las fuentes y los metadatos siguen aportando sus tags con su procedencia; el pool es una base
común, no una segunda taxonomía.

## 2. Evidencia de las fuentes

### AniList (consulta en vivo, 2026-11-13)

- `GenreCollection`: **19 géneros** (`Action`, `Adventure`, `Comedy`, `Drama`, `Ecchi`, `Fantasy`,
  `Hentai`, `Horror`, `Mahou Shoujo`, `Mecha`, `Music`, `Mystery`, `Psychological`, `Romance`,
  `Sci-Fi`, `Slice of Life`, `Sports`, `Supernatural`, `Thriller`).
- `MediaTagCollection`: **430 tags** en categorías: Cast-Traits (73), Sexual Content (66),
  Theme-Other (60), Theme-Game-Sport (31), Setting-Scene (24), Technical (21), Theme-Fantasy (19),
  Theme-Romance (17), Theme-Arts (15), Cast-Main Cast (12), Theme-Drama (11),
  Theme-Other-Organisations (10), Setting-Universe (8), Theme-Slice of Life (8), Theme-Action (8),
  Theme-Arts-Music (8), Setting-Time (7), Theme-Other-Vehicle (7), Theme-Game-Card & Board Game (6),
  Demographic (5), Theme-Sci-Fi (5), Theme-Comedy (4), Theme-Game (3), Theme-Sci-Fi-Mecha (2).
- `rank` es la relevancia por obra (0–100), no una nota global del catálogo; la colección de tags
  no trae un ranking único. **No se importan los 430**: incluyen spoilers, rasgos de reparto,
  contenido sexual, términos técnicos y anglicismos que no son un buen punto de partida.
- El cliente de ZascArr ya pide `genres` y `tags { name rank }`; ETQ4 los aplica a `series_tags`
  con `source='anilist'` y `weight=rank` (AniList en su idioma, D-2).

### ComicInfo / Kavita / Komga

- ComicInfo (Anansi): `<Tags>` y `<Genre>` son **listas de texto separadas por comas**, sin
  vocabulario cerrado. ZascArr ya lee ambos (ETQ2) y los guarda con `source='comicinfo_xml'`.
- Kavita y Komga tratan tags/géneros como **texto libre** y leen ComicInfo; no ofrecen un pool
  inicial en español. Kavita tiene filtros AND/`must not contain` y un mapper genres↔tags en
  Kavita+ (de pago), no en el escáner base.
- Mylar3 y Kapowarr **no tienen taxonomía de tags** propia; Mylar delega en ComicTagger y no
  escribe `<Tags>`.

### Conclusión

No existe un vocabulario canónico que se pueda importar tal cual. La fuente más rica (AniList) es
en inglés, ruidosa y con categorías que no queremos ofrecer como primer contacto. La decisión es
**construir sobre lo propio**: un pool pequeño en español, revisable, que convive con los tags de
fuente ya existentes y no los sustituye.

## 3. Decisiones

| Decisión | Veredicto |
|---|---|
| Sembrar un pool curado en `tags` (namespace `etiqueta`) | **Adoptar** |
| Ofrecer 12 ideas visibles en la ficha, sin asignarlas | **Adoptar** |
| Mantener el resto en el autocompletado (ya consulta `tags`) | **Adoptar** |
| Importar los 430 tags de AniList como pool | **Descartar**: inglés, spoilers, contenido adulto, ruido |
| Duplicar personajes, formato, universo o edad en tags | **Descartar**: ya son campos estructurados |
| Asignar automáticamente el pool a series | **Descartar**: una idea no es un dato |
| Traducir tags de fuente a español en esta historia | **Fuera**: ETQ5 (alias) |
| Crear categorías/namespace nuevos | **Descartar**: D-1, un solo espacio visible |

## 4. Pool propuesto (60 etiquetas)

Se agrupan por intención; todos caben en 64 caracteres y son únicos tras `f_tag_norm`.

### Género y tono (16)

superhéroes · noir · ciencia ficción · fantasía · terror · misterio · policíaco · bélico ·
western · romance · comedia · drama · aventura · histórico · cyberpunk · distopía

### Tema (28)

viajes en el tiempo · multiverso · magia · escuela · instituto · vigilantes · crimen organizado ·
mafia · piratas · vampiros · zombis · robots · inteligencia artificial · alienígenas · mitología ·
artes marciales · deportes · música · cocina · política · investigación · supervivencia · amistad ·
familia · duelo · identidad · poderes · corrupción

### Ambientación (10)

ciudad · espacio · futuro · medieval · victoriano · años 20 · años 80 · japón · estados unidos ·
europa

### Tono y estructura (6)

thriller psicológico · comedia negra · coming of age · road trip · post-apocalíptico · space opera

**Ideas visibles al inicio (12):** superhéroes, noir, ciencia ficción, fantasía, terror, misterio,
aventura, romance, comedia, viajes en el tiempo, magia, crimen organizado.

Criterios de inclusión: alta frecuencia en cómic/manga, comprensibles sin explicación, no
duplican un campo estructurado, no dependen de una editorial ni de una fuente, y dejan espacio
para que el coleccionista añada las suyas. Se excluyen términos adultos, spoilers, personajes,
formatos y etiquetas de estado.

## 5. Cómo se integra con fuentes y metadatos

- El pool se siembra una vez en `tags`; **no se asigna** a ninguna serie.
- En la ficha, «Ideas para empezar» muestra hasta 12 tags del pool que la serie aún no tiene.
- Al pulsar una idea se usa el mismo `POST /ui/series/{id}/etiquetas` (`source='manual'`).
- El autocompletado ya busca en todas las `tags`, así que el pool completo está disponible sin
  crear una pantalla nueva.
- AniList y ComicInfo siguen añadiendo sus tags con `source` y `weight`; si coinciden en nombre
  normalizado, reutilizan la misma fila (no se duplica). La traducción/alias de los tags de fuente
  queda para ETQ5, como ya decidió D-2.

## 6. Criterios de aceptación

- Una base recién migrada tiene **60 tags** del pool en `etiqueta` (idempotente al repetir la
  migración no aplica; el `ON CONFLICT` evita duplicados si ya existen).
- La ficha de una serie sin etiquetas muestra **hasta 12 ideas**, sin asignarlas.
- Añadir una idea crea una asignación **manual** y la idea desaparece de la lista.
- Una serie con etiquetas no ve ideas que ya tiene.
- El pool no crea asignaciones, no toca `issue_tags`, no toca archivos.
- El autocompletado encuentra el pool al escribir (p. ej. «noi» → noir).
- Pruebas: migración/seed, servicio de ideas, ruta de ficha y suite completa.

## 7. PASS / FAIL / NOT RUN

- **PASS (lectura/API):** AniList devuelve los 19 géneros y 430 tags; ComicInfo/Kavita/Komga
  confirman texto libre; el código de ZascArr ya integra ETQ2/ETQ4.
- **FAIL:** ninguna referencia ofrece un vocabulario inicial en español; se construye sobre lo
  propio.
- **NOT RUN:** uso real con coleccionistas, navegador/Pi, rendimiento con una biblioteca real,
  traducción automática de tags de fuente (fuera de alcance).
