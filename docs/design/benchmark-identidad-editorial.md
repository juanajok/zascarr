# Ficha de benchmarking — identidad editorial y cobertura (B22)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Solo identidad por
> edición, archivo↔issues y recopilaciones. **Sin migración**: esto precede al contrato.

**Historia / problema observado:**
B22 — separar la identidad de edición del número (grapa #12 vs Omnigold 12) y modelar qué
grapas cubre cada recopilación, para que los huecos no mientan ni C6 pida lo que ya es
legible. El modelo actual identifica por `(series_id, issue_number, volume)` sin `format`;
`File.covered_issue_ids` está vacío y sin procedencia.

**Datos reales y medición de partida:**
Pendiente del censo (requiere la BD real o un dump). Se medirá: issues por `format`,
colisiones de `UNIQUE(series_id, issue_number, volume)`, `volume=NULL`, `covered_issue_ids`
no vacíos, y casos reales de Omnigold/integral/tomo manga/pack entre series.

**Referencias consultadas (URL, versión/commit):**
- Kapowarr (Python, GPL-3.0) — **commit `c191dda` (v1.3.2, 2026-09-14, `main`)**.
  Código leído en local a ese commit; la documentación se leyó en `docs/src/` del
  **mismo commit** y se contrastó con la web en vivo (idéntica en lo comparado,
  pero el pie de la web dice 2026-03-02, **anterior** al commit: manda el repo).
- Mylar3 (Python, GPL-3.0) — **tag `v0.8.3`, commit `cdc94a4` (2025-08-17, `master`)**.
  Solo código + README; su web **no** se consultó. La afirmación del benchmarking
  ronda 2 (2026-09-22) de que usa el ID de Comic Vine como clave queda
  **confirmada en el esquema**: `comics.ComicID` es el volumen de CV.
- Suwayomi: fuera del alcance de esta ficha (lectura/fuentes, no identidad de edición).

**Cómo lo resuelve cada una:**
- Kapowarr: la unidad de catálogo es el **volumen de Comic Vine** (una colección de grapas y
  un ómnibus pueden ser volúmenes distintos, cada uno con sus números); clasifica cada volumen
  (normal, TPB, ómnibus, one-shot, «volume as issue») y permite corregirla. Para «un CBZ con
  varios issues» usa una asociación manual **archivo ↔ uno o varios issues** (`issues_files`,
  N:M con PK `(file_id, issue_id)` y flag `forced`), y el auto-match **expande el rango**: un
  `01-07` se ata a los siete. Además `volume_files` guarda los ficheros «generales» del
  volumen (portada, `comicinfo.xml`) con un `file_type`, que es un vínculo **exclusivo** y
  distinto del N:M. **No se ha encontrado** ninguna relación bibliográfica confirmada entre el
  issue de un ómnibus y los issues de otro volumen — ni SQL que una `issues` con `issues`, ni
  un campo de «reproduce»: un TPB/ómnibus es **otro volumen con un único issue**.
- **Mylar3 (verificado en el esquema, `v0.8.3`):**
  - **Archivo ↔ issues: NO hay N:M.** Es **1 fichero ↔ 1 fila** por `issues.Location TEXT`
    (`UPDATE issues SET Status=?, ComicSize=?, Location=? WHERE IssueID=?`, y el bucle de
    escaneo **rompe** al encontrar match). Los «packs» se modelan **en la descarga**
    (`ddl_info.pack`, `manualresults.pack_issuelist`), no en el fichero: al agarrar un pack
    lanza una búsqueda por cada número y cada issue acaba con su propio `Location`.
  - **Cobertura editorial: SÍ existe un campo, y no se usa para nada funcional.**
    `comics.Collects CLOB` guarda `[{series, comicid, issueid, issues}]`, **raspado del HTML**
    de la descripción de Comic Vine (`data-ref-id` `4000…` = issue, `4050…` = volumen + el
    texto del run) y **solo si** la descripción cumple una condición estrecha (empieza por
    «trade paperback» y contiene «collecting»). Sus **únicos** consumidores son pintar
    `( Collects: … )` en la ficha de serie y escribirlo en `series.json`. **No alimenta
    huecos, estados, `Have`/`Total` ni búsquedas**, y en la API no aparece.
  - **Identidad: tampoco hay entidad «edición».** La clave es `comics.ComicID` (volumen de
    CV) y una **colisión del mismo `Int_IssueNumber` se desambigua por AÑO**
    (`Int_IssueNumber` + `IssueDate[:4]`), no por edición. `ComicVersion` es el «Volume N» del
    título, sacado heurísticamente de la descripción y usado solo para validar nombres de
    release: **no** segmenta la tabla de issues.
  - **Anuales: tabla propia** (`annuals`), con `ComicID` = serie padre y `ReleaseComicID` =
    volumen de CV del anual, y numeración separada de la principal.

**Supuestos de su modelo que NO valen en ZascArr:**
- Una sola fuente (Comic Vine) como identidad: ZascArr combina Comic Vine + Tebeosfera +
  AniList, que **no comparten** noción de volumen/tomo/capítulo — de ahí `numbering_unit`.
- «El archivo corresponde a issues» no implica «el ómnibus reproduce grapas de otra edición»:
  son dos afirmaciones distintas, y solo la segunda es cobertura editorial.
- **Ni una sola de las dos referencias tiene cobertura editorial de verdad.** Kapowarr **no**
  la modela; Mylar3 tiene un campo raspado, condicionado a una frase en inglés y sin ningún
  uso funcional. Es el hallazgo más importante de esta ronda: **no hay implementación de
  referencia que adoptar** para el tomo→grapas, solo un precedente que nadie usa.

**Adoptar / adaptar / descartar, con motivo:**
- **Adoptar:** espacio de numeración por edición (≈ volúmenes de Kapowarr) → `editions`.
- **Adaptar:** asociación **archivo ↔ issues N:M** para packs/«un CBZ con varios números»
  (patrón de Kapowarr, con `forced` para distinguir match manual de automático) → relación
  física separada de la cobertura editorial (esquema aún sin decidir).
- **Adaptar (con la lección de Mylar3):** si algún día hay cobertura, la **procedencia** y la
  **confirmación humana** son obligatorias. El campo de Mylar3 demuestra lo contrario: dato
  raspado, frágil (una frase en inglés decide si existe) y que **nadie lee** — por eso no
  sirve ni como precedente de diseño.
- **Adaptar:** corrección manual antes de aceptar el match → refuerza Pendientes + confirmación.
- **Descartar:** identidad acoplada al ID de una sola fuente (Mylar3) — ZascArr ya usa columnas
  paralelas por proveedor. **Confirmado** en el esquema, no solo en las notas.
- **Descartar:** codificar sufijos y especiales en un `float` (Kapowarr: `2b`→2.02, `3 ½`→3.5,
  `∞`→9999999999999). ZascArr ya decidió texto libre + `number_key` por edición, y esto lo
  refuerza: el `float` obliga a un alfabeto artificial y hace ilegible el dato.
- **Descartar:** desambiguar dos números por **año** (Mylar3) — ZascArr desambigua por edición,
  que es la dimensión correcta cuando el mismo número convive en una grapa y en un tomo.
- **Descartar (por ahora):** dar por resuelto tomo→grapas copiando `issues_files` — no aporta
  procedencia ni confirmación; es justo lo que `IssueCoverage` debe cubrir.

**Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi):**
- No mentir: una propuesta no rellena huecos; una cobertura confirmada no convierte el tomo en
  grapas sueltas.
- No borrar: migración aditiva; `covered_issue_ids` se mantiene como dato heredado hasta auditar.
- Confirmación: solo la persona promueve `proposed` → `confirmed`.
- Coste Pi: sin servicios nuevos; tablas pequeñas e índices mínimos.

**Casos de prueba antes de implementar:**
- (Censo) contar formatos/colisiones/NULL/`covered_issue_ids` contra Postgres real.
- Dos #12 de distinta edición coexisten; de la misma edición no.
- Una propuesta no cuenta como contenido; una confirmada solo con `File` disponible.
- Perder el único archivo del tomo quita «contenido legible» pero no borra la relación.

**Decisión final / ADR si cambia arquitectura:**
El **benchmark está cerrado** (2026-10-01): versiones fijadas y el hueco que quedaba
—el archivo↔issues y la cobertura de Mylar3— **verificado en su esquema**. Lo que
falta para cerrar B22 **no es investigación**: es el **censo de BD**
(`scripts/medicion/censo_identidad.py`), que necesita la instalación real. Si los
datos no sostienen coberturas contrastables, la ficha recomienda **posponer**
(resultado válido, no fracaso). Las cuatro decisiones
(`number_key`/especiales, edición vs `Imprint`, universo de grapas,
archivo↔publicaciones) están redactadas en **ADR-0003** (Propuesto), con la tabla
de qué decide cada resultado del censo.

**Lo que NO se ha verificado en esta ronda** (para que nadie lo dé por supuesto):
- Kapowarr: «cobertura entre volúmenes = no existe» se apoya en el esquema completo
  y en la ausencia de SQL que una `issues`/`volumes` entre sí. **No** se leyó su
  `db_migration.py` completo (~1200 líneas) ni sus PRs/issues: no se descarta algo
  planificado o retirado.
- Kapowarr: `PUT /volumes/{id}/manualmatch` **no valida** que los `issue_ids`
  pertenezcan al volumen (la FK de `issues_files` apunta a `issues.id`, no a la
  pareja) — es un agujero del esquema, no una función. No se abrió su UI, así que
  **no se afirma** qué ofrece el diálogo de match manual.
- Ninguna de las dos se ejecutó: todo es lectura estática, sin comportamiento en
  runtime con ficheros reales.
- Mylar3: «no hay N:M» se apoya en su DDL completo (24 tablas) y en el patrón
  `Location` único. **No** se revisaron PRs abiertas ni otras ramas: si existió y se
  retiró, no se vería.
- Mylar3: de `Collects` se verificaron sus consumidores con un grep exhaustivo del
  árbol de código; **no** se auditaron plugins ni el JS del frontend.
- Mylar3: **no** se consultó su web de documentación (mylarcomics.com): todo sale de
  código y README.
- No se ha comprobado si el metatagging (ComicTagger embebido en `lib/`) escribiría
  un campo tipo «collects» en `ComicInfo.xml`.
