# ADR 0003: Identidad editorial y cobertura — cierre de B22 (censo real + cuatro decisiones)

- Estado: **Propuesto** · 2026-09-27
- Relacionado: ADR-0002 (enricher), BACKLOG §B22, `docs/design/identidad-editorial-cobertura.md`

## Contexto

B22 pedía medir la biblioteca real y cerrar, en un solo ADR, las cuatro
decisiones del modelo de identidad editorial antes de tocar el esquema. No hay
entorno local de BD, pero el coleccionista aportó el **listado real del disco**
(`find` de `/media/WDElements/Tebeos`). Aportó además un **segundo listado**: la
carpeta de **descargas** (no la tebeoteca), que confirma y amplía los mismos
patrones con el caso Dreadstar (tres ediciones renumeradas) y ruido de descarga
(`(1)` de redescarga, `.part`, doble extensión). Ese listado es más revelador para esta
pregunta que el censo de columnas: las columnas de la BD que íbamos a medir
(`volume IS NULL`, `covered_issue_ids`) las conocemos por código — `covered_issue_ids`
se escribe siempre **vacío** en importación y adopción —, mientras que el
listado muestra la estructura editorial real que el censo de columnas no ve.

**Hallazgo central del censo real:** la evidencia de cobertura **sí existe y es
abundante, pero vive en el nombre de archivo, no en `covered_issue_ids`**. Un
censo basado solo en la columna habría dicho "cero cobertura contrastable →
posponer". El listado demuestra lo contrario: la cobertura se puede leer del
nombre en rangos explícitos. Por tanto **no se pospone**: la migración aditiva
está justificada, y la procedencia inicial de una cobertura será «rango en el
nombre (heurística)» → `proposed`, pendiente de confirmación humana.

## Decisión 1 — `number_key`: texto libre + clave canónica por edición; especiales y renumeraciones no se fuerzan

**Decisión.** `Issue.issue_number` se mantiene como texto libre (el literal del
nombre). `number_key` es una clave canónica **dentro de la edición**, usada para
ordenar y desambiguar, no para sustituir al texto:
- Número entero → el entero. Sufijos (`123a`, `123b`) → `123` + sufijo (no
  colapsan con `123`).
- Especiales/anuales (`Especial 1`, `Annual 01`) **no** entran en la numeración
  principal: subespacio propio (`especial-01`, `annual-01`) o edición propia.
- Un **rango** (`049-051a`) **no** es un número: es evidencia de cobertura
  (varias grapas en un archivo), va a la relación de cobertura, no a `number_key`.
- Una **renumeración** (`nº 03 (122)`) tiene su propia edición: `03` es la clave
  en la edición de reimpresión y `122` es la referencia a la edición de grapas
  original. `number_key` no mezcla las dos.

**Evidencia (biblioteca real).** `Superman Vol2 123a/123b/123c` y
`Animal Man (NuDC) 02a/02b/02c` (sufijos); `Superman Vol2 Especial 1–8` y
`Flash v2 Annual 01–13` (especiales); `Patrulla-X, nº 03 (122)` (renumeración);
`Superman Vol2 049-051a` y `Flash v2 164-169` (rangos). De la carpeta de
descargas se suman: **Dreadstar en tres ediciones renumeradas** (`Epic Comics
01–26 Ed.Forum`, `First Comics 27–64 USA`, `Malibu/Norma 01–06`);
`Transmetropolitan #01 … 1 de 4` («X de Y» = parte de un arco, no número de
grapa); `GunSmith Cats [P1N1]…[P3N9]` (codificación parte/número);
`M0N57R355 01 al 05` (rango en español); y ruido de descarga — sufijo `(1)` de
redescarga, `.part`, doble extensión `.cbr.zip`.

**Alternativa descartada.** Forzar todo a un `float` (el `sort_order` truncado ya
documentado: `123a` → `123` colisiona con `123`), o inventar un `0` para «sin
número» (NULL es el hueco honesto; lo dice la spec y lo confirma la regla de no
mentir).

## Decisión 2 — Edición ≠ Imprint: la edición es el espacio de numeración, el sello es atributo

**Decisión.** `editions` representa una **línea de numeración** dentro de una
serie (grapas originales, reimpresión Panini, Omnigold, Integral, tomos manga…).
Identidad: `series_id` + nombre/`kind` + `numbering_unit`, nunca el sello.
`Publisher`/`Imprint` (ya existen en `Series`) siguen siendo el sello editorial
(Panini, ECC, Zinco, Planeta, Norma, Glenat…) y **no** se duplican como clave en
`editions`; `editions.publisher_id`/`imprint_id` es opcional y solo para cuando
una edición la publica un sello distinto del de la serie.

**Evidencia (biblioteca real).** El caso que lo decide: `Superman (1987)` y
`Superman Vol2 (Ed.Zinco)(1987-96)` son **dos carpetas con el mismo contenido**
(`Superman Vol2 NNN`) — un duplicado, no dos ediciones. El sello «Zinco» es
atributo; la identidad editorial es «Superman Vol2». Frente a eso,
`Patrulla-X (Panini)` (reimpresión `nº 03 (122)`), `La Patrulla X Omnigold` y
`La Imposible Patrulla X` son **tres ediciones reales** de la misma serie. El
caso más limpio lo da **Dreadstar** en la carpeta de descargas: `Dreadstar
(Epic Comics)(01 Ed.Forum)…(26)`, `Dreadstar (First Comics) 27 USA…64 USA` y
`Jim Starlin's Dreadstar (Malibu Comics)(01 Ed.Norma)…(06)` — **tres ediciones
de la misma serie**, cada una con su numeración y su sello en el nombre; el
sello es dato, la edición es el espacio de numeración.

**Alternativa descartada.** Modelar cada sello como una edición (dobla filas
para el mismo contenido) o usar `kind` solo como identidad (falla cuando hay dos
líneas del mismo tipo: The Boys tiene *Omnibus* y *Edición Integral* a la vez).

## Decisión 3 — El universo esperado vive en la edición, no en la serie

**Decisión.** El «total de números esperados» se calcula contra la **edición**,
no contra `Series.total_issues` (que se conserva por compatibilidad). La unidad
se acredita por `numbering_unit` + fuente: solo `single_issue` con fuente que
cuente grapas (Comic Vine) define un universo de grapas `1..N`. El manga cuenta
**capítulos** (AniList) y sus ficheros son tomos; una reimpresión renumerada
tiene su **propio** universo, independiente del de las grapas originales.

**Evidencia (biblioteca real).** `One Piece Manga Volumen 93 (932-942)` — el
tomo declara el rango de **capítulos** en el nombre, no grapas. La separación
física del disco (carpetas `Comics/` de grapas americanas frente a `Manga/` de
tomos) refuerza que no comparten unidad.

**Alternativa descartada.** Seguir usando `Series.total_issues` como universo
único — es exactamente lo que produjo los 143 huecos falsos del manga de 120
capítulos (documentado en #13).

## Decisión 4 — Archivo ↔ publicaciones es una relación distinta de la cobertura editorial

**Decisión.** Se distinguen dos relaciones:
1. **Archivo ↔ publicaciones** (N:M, al estilo de Kapowarr `issues_files`): «este
   CBZ contiene estas publicaciones». Su evidencia inicial es el **rango en el
   nombre**.
2. **Cobertura editorial** (`issue_coverages`): «este tomo publicado reproduce
   estas grapas», con procedencia y confirmación.

En esta biblioteca ambas se alimentan de la misma señal porque el archivo **es**
la publicación recopilatoria (un tomo = un CBZ con N grapas dentro). No hay packs
«sin Issue» que obliguen a inventar una publicación: los rangos aparecen ligados
a una publicación identificable (el tomo/volumen). Si apareciera un pack sin
publicación identificable, va a Pendientes sin `Issue` y no se le inventa uno.

**Evidencia (biblioteca real).** `Tom Strong - Volumen 1 (01-07)`,
`One Piece Manga Volumen 93 (932-942)`, `Superman Vol2 049-051a`,
`Batman · El Tribunal De Los Búhos … {BMv2 #1-12 USA}`,
`La Patrulla X (122-143 usa) Omnigold nº 2`.

**Alternativa descartada.** `File.covered_issue_ids` como única verdad (está
vacío y sin procedencia) y «dar por resuelto» tomo→grapas copiando `issues_files`
sin confirmación (Kapowarr no resuelve esa afirmación bibliográfica, §9 de la
spec).

## Consecuencias

- **No se pospone la cobertura**: hay material real que la llena. La migración
  aditiva (`editions`, `issues.edition_id`, `issue_coverages`) queda justificada
  como siguiente entrega, en otra PR y con backup/rollback probados.
- **La procedencia inicial es el nombre de archivo** (rango), etiquetada
  `proposed`; una persona confirma o rechaza. Nunca `confirmed` automático.
- **C6 sigue bloqueado** hasta que la API distinga «completa» de «no computable»
  y el coleccionista elija entre «quiero la grapa suelta» y «me basta poder
  leerla». Este ADR no lo desbloquea; solo cierra el modelo previo.
- **B20 sigue aparcado**: también mueve conceptos de edición y nombre, y
  aumentaría los contratos cambiando en paralelo.

## Decisión fuera de este ADR (registrada, no resuelta aquí)

El censo por columnas (censo_identidad.py) queda como herramienta complementaria
para cuando exista una BD real: medirá lo que el listado no puede (colisiones por
`volume NULL`, `covered_issue_ids` no vacíos, formatos). Este ADR se apoya en el
listado, que es la fuente disponible hoy y la más rica para identidad editorial.
