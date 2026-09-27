# Identidad editorial y cobertura tomo → grapa (especificación)

**Estado:** especificación, pendiente de implementación (migración y código van aparte).
**Origen:** cierre de la cadena A4 → A6 → B15 → huecos fiables (2026-09-27). La vista de
huecos de grapas ya es fiable y acotada (PR #13); esto es el rediseño de catálogo que la
precede. **No es C6.**

## 1. El problema en una frase

Una recopilación (tomo, ómnibus, integral) contiene **varias** grapas originales. Hoy el
catálogo la guarda como un `Issue` con otro `format` y un único `issue_number`; nada dice
«este tomo cubre las grapas 7..12». Hasta que eso exista, **un tomo no rellena huecos de
grapa por inferencia** — regla que ya se aplica en la vista de huecos.

La raíz del problema es más honda: la identidad de una publicación está atada al **número**
en un espacio común (`series_id`), de modo que «el tomo contiene la grapa» se confunde con
«son el mismo `Issue`». `La Patrulla-X #12` y `La Patrulla-X Omnigold 12` son dos
publicaciones distintas, y deben poder serlo sin trucos.

## 2. Realidad del esquema (verificado contra `models` y `0001_initial_schema`)

- `Issue` tiene `UNIQUE(series_id, issue_number, volume)`, **sin `format`**.
- `volume` es `sa.Integer server_default="1"` **sin `NOT NULL`**: aunque el ORM lo tipa
  `Mapped[int]`, en PostgreSQL la columna admite `NULL`. Con `volume=1` grapa y ómnibus del
  mismo número **chocan**; con volúmenes distintos coexisten; y los `NULL` son distintos
  entre sí en una restricción única ordinaria, así que puede haber duplicados ambiguos.
- `issue_number` es `sa.String(20)` **nullable**: «sin número» ya se representa como `NULL`,
  no hace falta inventar un `0`.
- `File.covered_issue_ids` es `ARRAY(UUID) server_default "{}"`: solo se escribe **vacío**
  (`importer.py:384`, `library_adopter.py:180`) y **nadie lo lee** para semántica. Es una
  pista ligada a una copia física, sin procedencia ni confirmación; hoy, en la práctica, una
  columna muerta. No es la verdad editorial por sí sola.
- Ya existen `Publisher`, `Imprint` (`UNIQUE(publisher_id, name)`) y
  `Series.publisher_id`/`imprint_id`. Un `Imprint` es un **sello**; una *edición* (línea
  editorial con numeración propia: grapas originales, Omnigold, Integral, reedición…) es un
  concepto distinto y adyacente — hay que fijar la frontera para no doblar el modelo.
- Ya existe `MetadataSource` (`comic_vine | gcd | anilist | tebeosfera | comicinfo_xml |
  manual`) y `IssueFormat` + `EDITION_KIND_A_FORMAT`. `edition_kind` (omnigold/integral/
  tomo/volumen) solo vive durante el parseo; hoy lo único que se persiste es `Issue.format`.

## 3. Modelo propuesto

Separar **identidad de edición** del **número**, y la cobertura como **relación**:

| Entidad | Qué representa | Identidad |
|---|---|---|
| `editions` | Una línea editorial con numeración propia: grapas originales, Omnigold, Integral, reedición, etc. | UUID; pertenece a una `Series` |
| `issues.edition_id` | La edición a la que pertenece esa publicación | FK a `editions` |
| `issue_coverages` | Afirmación «esta publicación recopilatoria contiene esta publicación objetivo» | Par único `(collection_issue_id, target_issue_id)` |

### 3.1 `editions` — el espacio de numeración

Campos mínimos: `id`, `series_id`, `name`, `kind`, `publisher_id` opcional, año opcional,
identificador externo opcional y `numbering_unit` (`single_issue | volume | chapter |
unknown`).

**La edición es el espacio de numeración**: la grapa #12 y el Omnigold 12 tienen
`edition_id` distintos. `kind=omnigold` no basta como clave, porque pueden existir dos
líneas editoriales del mismo tipo.

Se separa una edición cuando una línea **reinicia su numeración** (reedición 2010 que vuelve
al #1, por ejemplo). No se usa `volume=NULL` como truco de identidad.

### 3.2 `issues.edition_id` + `number_key`

En `issues` se conservan `series_id` y `format` por compatibilidad, y se añade:

- `edition_id` (FK a `editions`, inicialmente nullable durante la migración).
- `number_key` normalizada **dentro de esa edición**.

Para números conocidos, la unicidad es `UNIQUE(edition_id, number_key)`. Una publicación
**sin número** no recibe un `0` inventado para satisfacer el índice: se identifica por su
UUID/ID externo y pasa a revisión si hay ambigüedad. La normalización exacta de `number_key`
(qué hacer con `Annual 1`, `1.5`, `0`, `12 B`, `1/2`) es decisión abierta — ver §8.

### 3.3 `issue_coverages`

```text
collection_issue_id  FK issues.id
target_issue_id      FK issues.id
status               proposed | confirmed | rejected
source               (procedencia, ver §4)
source_ref           identificador o enlace de la evidencia, opcional
evidence_note        texto breve, opcional
confirmed_at         fecha, solo si confirmed
created_at / updated_at
UNIQUE(collection_issue_id, target_issue_id)
CHECK(collection_issue_id <> target_issue_id)
```

Un índice por `target_issue_id, status` permite consultar rápido qué tomos contienen una
grapa.

La cobertura guarda **IDs de grapas concretas**, no «5–7». Un rango solo sirve para
*proponer* varios enlaces, y el sistema comprueba que existen y corresponden a la edición
correcta antes de confirmarlos. Un pack que contiene `Serie A #12` y `Serie B #3` son **dos
enlaces explícitos**, no un rango ni una suposición de serie compartida.

### 3.4 Los tres ejemplos sobre el modelo

- **A. Tomo que cubre grapas de una misma serie** — `Berserk Deluxe 1` (tomo, edición
  «Deluxe», `numbering_unit=volume`, `number_key=1`) con coberturas hacia las grapas #1..#3
  (edición «grapas», `numbering_unit=single_issue`). Origen + confirmación, no inferencia.
- **B. Dos ediciones del mismo #12** — grapa #12 (edición «grapas», `number_key=12`) y
  ómnibus #12 (edición «Omnigold», `number_key=12`) coexisten porque `edition_id` difiere;
  el ómnibus declara qué grapas cubre (p. ej. #7..#12) sin confundirse con la grapa #12.
- **C. Pack que cruza series** — un archivo con material de `Serie A #12` y `Serie B #3`
  produce dos filas de `issue_coverages` (o su representación equivalente), y por cruzar
  series exige **confirmación humana explícita** conservando el motivo (§4).

## 4. Procedencia y confirmación

- Toda cobertura tiene un **origen**. Reutilizar `MetadataSource` para no perder
  granularidad (comic_vine ≠ tebeosfera), salvo que se decida el valor grueso
  `manual | catalog | comicinfo | other` de la tabla §3.3 — decisión abierta (§8).
- Si el origen no es fiable, la cobertura queda **`proposed`**: se puede mostrar, pero
  **no** cuenta como «lo tengo» ni rellena huecos. Una fuente externa puede crear una
  propuesta; **no puede** convertirla silenciosamente en `confirmed`.
- La **confirmación humana** es lo que la promueve a `confirmed`.
- `rejected` persiste el rechazo para que el siguiente enriquecimiento **no** vuelva a
  proponer lo mismo por su cuenta.
- Si varias fuentes aportan evidencia del mismo par, se amplía con una tabla
  `coverage_evidence` en vez de sobrescribir la procedencia de la primera.

## 5. Qué cuenta como posesión

La relación editorial y el archivo físico responden preguntas distintas:

| Pregunta | Regla |
|---|---|
| «¿Tengo la grapa #12 suelta?» | Existe un `File` disponible (`is_missing=false`) asociado a esa grapa. Un tomo no la convierte en grapa suelta. |
| «¿Puedo leer el contenido de la grapa #12?» | La tengo suelta **o** existe una cobertura `confirmed` desde un tomo con al menos un `File` disponible. |
| «¿Debo pedirla con C6?» | Depende de una política futura elegida por el coleccionista: *quiero la grapa suelta* frente a *me basta poder leerla*. Nunca se deduce de que ambos lleven «12». |

Ejemplo: un Omnigold 2 tiene confirmada la cobertura de las grapas #5, #6 y #7. Si su CBZ
está disponible, siguen faltando esas **grapas sueltas**, pero sus **contenidos** están
disponibles. Si desaparece el único archivo del tomo, dejan de estar disponibles por esa
vía; si reaparece, vuelven. Una propuesta sin confirmar no modifica ninguno de los dos
recuentos.

## 6. Migración sin adivinar

1. **Auditar primero** las colisiones actuales de `UNIQUE(series_id, issue_number, volume)`
   y cualquier valor no vacío de `File.covered_issue_ids`. Ese array es información
   potencial del archivo/pack, no una relación editorial confirmada: no se descarta ni se
   convierte automáticamente en verdad.
2. Crear `editions` e introducir `issues.edition_id` inicialmente nullable. Asignar una
   edición de grapas a los `SINGLE_ISSUE` inequívocos; para tomos o reediciones ambiguas,
   crear agrupaciones «edición por verificar» o dejar pendiente, **no** generar una
   identidad por regex.
3. Añadir `issue_coverages` **sin ninguna cobertura confirmada** por migración. Las fuentes
   conocidas podrán generar `proposed`; un acto explícito de revisión las pasa a `confirmed`.
4. Adaptar matcher e importador para resolver primero **edición**, después número. Si una
   edición no está identificada con confianza, Pendientes; nunca volver al primer `Issue`
   con ese número.
5. Solo tras auditar datos y adaptar consultas, sustituir la restricción antigua por la
   unicidad acotada a edición. El cambio de restricciones y el backfill van con copia de
   seguridad y prueba de rollback; no se suelta la restricción antigua antes de saber qué
   filas colisionan.

## 7. Aceptación antes de C6 (contra PostgreSQL real)

- Dos #12 de **distinta** edición coexisten.
- Dos #12 de la **misma** edición no.
- Una cobertura `proposed` no cuenta como posesión ni como contenido.
- Una cobertura `confirmed` solo cuenta como contenido legible si el tomo tiene un `File`
  disponible.
- Dos copias del tomo con una presente siguen contando.
- Un pack entre series exige confirmación humana.
- Borrar/restaurar el archivo cambia la disponibilidad **sin** borrar la relación.
- Una propuesta `rejected` no se vuelve a confirmar sola en el siguiente enriquecimiento.

## 8. Qué NO decide este documento / decisiones abiertas

- **No define migración ni código** (van aparte, tras revisar esta spec).
- **No cambia `GET /missing` ni empieza C6.** Antes faltará que su API exponga
  `computable`/`motivo`, que el universo de grapas esperadas esté acreditado y que el
  usuario elija si «Completar» significa conseguir grapas sueltas o contenido legible — la
  distinción entre esos dos objetivos es el valor de introducir cobertura explícita.
- **Normalización de `number_key`:** qué forma canónica toman `Annual 1`, `1.5`, `0`,
  `12 B`, `1/2`, y si los anuales/especiales viven en el mismo espacio de numeración que la
  serie principal o en un subespacio. El `numbering_unit` propuesto no los cubre.
- **`source` de cobertura:** reutilizar `MetadataSource` (granular) o el valor grueso
  `manual | catalog | comicinfo | other`. Se recomienda `MetadataSource` por la regla de «sin
  magic strings» y para no perder procedencia.
- **Frontera `editions` ↔ `Imprint`/`Series.publisher_id`:** decidir si
  `editions.publisher_id` aporta algo que `Series.publisher_id`/`imprint_id` no cubren ya,
  para no doblar la verdad del sello editorial.
- **Destino de `File.covered_issue_ids`:** abandonarlo, mantenerlo para packs/archivos
  físicos, o migrarlo hacia la tabla de cobertura. Hoy está vacío en la práctica.
- **El universo de grapas** (`Series.total_issues` + `metadata_source=comic_vine`, usado por
  la vista de huecos): al introducir ediciones, su sitio natural es la edición de grapas
  (`editions.numbering_unit='single_issue'`), no la serie. Es una consecuencia a decidir en
  la migración, no un cambio de esta spec.
