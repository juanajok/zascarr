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
- Kapowarr (Python, GPL-3.0) — [implementation details](https://casvt.github.io/Kapowarr/general_info/implementation_details/),
  [how to use](https://casvt.github.io/Kapowarr/general_info/how_to_use/); estudio 2026-09-27
  (spec `docs/design/identidad-editorial-cobertura.md` §9). **Versión/commit: no fijado** — se
  estudió la documentación en vivo, no un release concreto; pendiente de pinchar al cerrar.
- Mylar3 (Python, GPL-3.0) — [repo](https://github.com/mylar3/mylar3); notas de
  benchmarking ronda 2 del backlog (2026-09-22). **Versión/commit: no fijado** — pendiente.
- Suwayomi: fuera del alcance de esta ficha (lectura/fuentes, no identidad de edición).

**Cómo lo resuelve cada una:**
- Kapowarr: la unidad de catálogo es el **volumen de Comic Vine** (una colección de grapas y
  un ómnibus pueden ser volúmenes distintos, cada uno con sus números); clasifica cada volumen
  (normal, TPB, ómnibus, one-shot, «volume as issue») y permite corregirla. Para «un CBZ con
  varios issues» usa una asociación manual **archivo ↔ uno o varios issues** (`issues_files`,
  N:M). **No se ha encontrado** una relación bibliográfica confirmada entre el issue de un
  ómnibus y los issues de otro volumen (no se afirma que las marque poseídas).
- Mylar3: usa el **ID de Comic Vine como clave** (afirmación del benchmarking ronda 2 del
  backlog, 2026-09-22: «a diferencia de Mylar3, que usa el ID de Comic Vine como clave y se
  queda cojo sin él»). Anuncia pull-list, TPB/arcos y escritura de ComicInfo. **No se ha
  inspeccionado a fondo** su esquema de archivo↔issues ni de cobertura entre volúmenes en esta
  ronda — esa parte queda **pendiente de verificar**, no se da por sustentada.

**Supuestos de su modelo que NO valen en ZascArr:**
- Una sola fuente (Comic Vine) como identidad: ZascArr combina Comic Vine + Tebeosfera +
  AniList, que **no comparten** noción de volumen/tomo/capítulo — de ahí `numbering_unit`.
- «El archivo corresponde a issues» no implica «el ómnibus reproduce grapas de otra edición»:
  son dos afirmaciones distintas, y solo la segunda es cobertura editorial.

**Adoptar / adaptar / descartar, con motivo:**
- **Adoptar:** espacio de numeración por edición (≈ volúmenes de Kapowarr) → `editions`.
- **Adaptar:** asociación **archivo ↔ issues N:M** para packs/«un CBZ con varios números» →
  relación física separada de la cobertura editorial (esquema aún sin decidir).
- **Adaptar:** corrección manual antes de aceptar el match → refuerza Pendientes + confirmación.
- **Descartar:** identidad acoplada al ID de una sola fuente (Mylar3, según el benchmarking
  ronda 2 del backlog 2026-09-22) — ZascArr ya usa columnas paralelas por proveedor (misma
  ronda). La cobertura entre volúmenes no se descarta: queda **pendiente de verificar**.
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
Pendiente del censo. Si los datos no sostienen coberturas contrastables o ninguna fuente da
evidencia, la ficha recomienda **posponer** (resultado válido, no fracaso). El ADR que cierre
las cuatro decisiones (`number_key`/especiales, edición vs `Imprint`, universo de grapas,
archivo↔publicaciones) se escribe tras medir.
