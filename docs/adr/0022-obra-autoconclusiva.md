# ADR 0022: obra autoconclusiva y publicaciones sin numeración editorial

- **Estado:** **Aceptado por el PO (2026-11-17)**. Autoriza la implementación según la
  especificación, con migración 0049 aditiva y sin backfill. Las decisiones abiertas de la
  propuesta quedaron resueltas (ver «Decisiones aceptadas»).
- **Relación:** [ADR 0003](0003-identidad-editorial.md) (vocabulario Serie/Edición/Publicación/Formato)
  y [ADR 0016](0016-publicacion-sin-numero.md) (publicación sin número). Benchmark y propuesta de
  producto revisados: matriz de cinco casos de «tomos y números únicos».
- **Base verificada:** `origin/main` `b26d5dad` (2026-11-17). Lo que se afirma del código está
  comprobado contra ese árbol; lo que no, se marca como NOT RUN.
- **No sustituye** al benchmark ni a la futura especificación: fija la decisión conceptual y deja
  los contratos de implementación a [`especificacion-obras-autoconclusivas.md`](../design/especificacion-obras-autoconclusivas.md).

## Contexto

El coleccionista tiene publicaciones que **no pertenecen a una serie numerada**: una novela
gráfica autoconclusiva, un álbum único, un manga de un solo tomo, un one-shot. La pregunta «¿a qué
serie pertenece?» es la fricción principal del alta.

La propuesta de producto que origina este ADR acierta en el diagnóstico —el cajón de sastre
«Tomos únicos» rompe el enriquecimiento y la interoperabilidad— y propone como solución crear
«1 serie = 1 número #1». Esa convención **no es neutra** en ZascArr: choca con el vocabulario del
ADR 0003, con la decisión del ADR 0016 y con el cálculo de huecos actual. Este ADR fija una
alternativa compatible con el modelo existente y separa lo que es una **decisión de catálogo**
(¿lleva número?) de lo que es **presentación** (formato, badge, ComicInfo).

### Lo que existe hoy (verificado)

- **No existe** una entidad «obra», ni `edition_type`, ni `es_obra_unica`. `Series` es la
  agrupación del coleccionista; `Issue` es la publicación; `IssueFormat` es la forma de
  presentación (`single_issue`, `trade_paperback`, `hardcover`, `omnibus`, `graphic_novel`,
  `album`, `manga_tankobon`, `digital`). **No hay `one_shot` en `IssueFormat`.**
- `Series.edition_kind` **no es** el tipo de edición: significa `oficial`, `tradumaqueta`,
  `escaneo_propio` u `otro`. No se debe reutilizar para esto.
- `Series.kind` es `regular | annual | special`; el anual es una **serie propia con
  `parent_series_id`** a la madre, no un `Issue.format` ni un `Issue.tipo`.
- `Series.parent_series_id` y `Collection` ya existen. `Collection` es una agrupación local de
  series para estanterías/política de auto-búsqueda; **no es identidad editorial**.
- El ADR 0016 ya decidió que un especial/tomo **sin número** se representa como `Issue` normal con
  `issue_number = NULL` (título + formato), no con un `#1` inventado. Hay código y UI:
  `services/especiales.py`, acción «Vincular como especial sin número» en Pendientes.
- `total_issues` lo copia el enricher de la fuente y **no siempre cuenta grapas**; la completitud
  solo se calcula cuando la fuente está en `UNIDAD_DE_GRAPA` (hoy Comic Vine). Los huecos cuentan
  únicamente `IssueFormat.SINGLE_ISSUE` con número entero (`numero_de_grapa`).
- **Consecuencia:** una serie con `total_issues = 1` y una publicación `graphic_novel` con número
  `NULL` o `#1` de formato no-grapa **no cuenta como poseída** y produciría un hueco falso del
  `#1`. El flag no basta; hay que cambiar la regla de completitud.
- B6 ya escribe ComicInfo, pero su mapa mínimo (**`CAMPOS_GESTIONADOS`**) incluye
  `Series`, `Number`, `Volume`, `Year`, `Publisher`, `Summary`, créditos, `Genre`, `PageCount` y
  `LanguageISO`; **no incluye `Count`, `Format` ni `SeriesGroup`**.

### Los cinco casos y su encaje

1. **Obra autoconclusiva/novela gráfica/álbum único**: una serie con una publicación; candidata a
   `SeriesKind.ONE_SHOT`.
2. **Integral/omnibus de una serie regular**: no es una obra única; es una **edición/recopilación**
   de publicaciones existentes. El ADR 0003 deja la entidad *Edición* abierta; no se debe marcar
   como one-shot para «cerrar» el hueco.
3. **Anual/especial ligado a una serie**: el anual ya es `Series.kind=annual` + parent; el especial
   sin número ya sigue el ADR 0016. No se inventa un tipo de `Issue` nuevo.
4. **Serie publicada directamente en tomos**: es una serie normal; cada tomo es un `Issue` con
   `format=manga_tankobon`/`trade_paperback` y numeración propia. No es un one-shot.
5. **Colección editorial numerada**: si se cataloga por el lomo, es una serie normal con su
   numeración; si se cataloga por obra suelta, cada obra es una serie one-shot. Decide el
   coleccionista, no el parser.

## Decisión (aceptada por el PO el 2026-11-17)

**D1 — Mantener `Series → Issue`; no crear Issues huérfanos ni una entidad «obra».** La obra se
representa por su serie, aunque tenga una sola publicación. No se reutiliza `edition_type`; se
amplía el vocabulario existente.

**D2 — `Series.kind = ONE_SHOT`** (nuevo valor del enum `SeriesKind`, no un campo
`es_obra_unica`): una serie que contiene **una sola publicación autónoma** y no una línea de
numeración. `Collection` sigue agrupando estanterías; `parent_series_id` se reserva para anuales y
relaciones de presentación, no para «obra única».

**D3 — Número: no inventar.** El `Issue` de una obra one-shot lleva el número **solo si la fuente
lo da** (p. ej. Comic Vine Volume count 1 → `#1`); si no, `issue_number = NULL`, título y formato,
como el ADR 0016. La UI no muestra `#1` cuando no existe. La convención «siempre #1» se descarta
como regla general y queda como decisión de datos por fuente.

**D4 — Completitud propia de one-shot.** Una serie `ONE_SHOT` está completa cuando tiene **al
menos una publicación con archivo disponible** (o su publicación vinculada, según el caso); no se
calculan huecos, no entra en «faltantes», no se ofrece a seguimiento de novedades ni a wishlist de
futuros. `total_issues` puede ser `1` solo como dato de presentación; **no** es la base del
cálculo. Esto exige tocar `huecos_de_serie`, `razon_de_no_calculable`, `coleccion.py` y la
condición SQL de estado, además de `querer_de_serie`.

**D5 — Anuales y especiales no cambian.** Anual: `SeriesKind.ANNUAL` + `parent_series_id`; especial
sin número: ADR 0016 (`Issue` NULL + formato). No se añade `Issue.tipo`.

**D6 — Integrales/omnibus quedan fuera de esta decisión.** Se reconocen como **edición o
recopilación**, no como one-shot. Mientras no exista *Edición* (ADR 0003), no se convierten
automáticamente ni se les pone `kind=one_shot`; su modelado es una historia aparte (#125/#126 y la
decisión de Edición).

**D7 — ComicInfo se amplía después, con contrato propio.** Para un one-shot: `<Series>` = título de
la obra, `<Count>` = 1, `<Format>` = `Graphic Novel`/`One-Shot`/`TPB`/`HC`/`Omnibus` según
`Issue.format`; `<Number>` solo si hay número real. `SeriesGroup` **no entra en v1**: una
`Collection` local puede agrupar varias franquicias y no hay una regla unívoca; se decide en una
historia de ComicInfo/ETQ6 con pruebas. B6 actual **no** escribe `Count`/`Format`; no se finge que
ya está hecho.

**D8 — UX de alta con tres opciones**, no una pregunta única:
`¿Qué es?` → «Tomo único / novela gráfica / one-shot» / «Pertenece a una serie numerada» /
«Especial o anual de una serie». La primera crea una serie `ONE_SHOT` con su publicación (número
si la fuente lo da; si no, NULL); la segunda sigue el flujo actual; la tercera ofrece el flujo del
ADR 0016 o el anual con `parent_series_id`. Los one-shot se ocultan del selector de series por
defecto, con un interruptor «mostrar también tomos únicos» para reemplazos.

## Alternativas descartadas

- **`Issue.series_id` nulo / libros sin serie**: pierde los IDs de volumen y todo el enriquecimiento;
  ya descartado en ADR 0003/0016.
- **`edition_type` o `es_obra_unica`**: duplica vocabulario, choca con `Series.edition_kind` y no
  resuelve huecos por sí solo. Se prefiere `SeriesKind`.
- **«1 serie = 1 `#1`» como regla universal**: convierte una convención de catálogo en identidad y
  contradice el ADR 0016; solo se admite cuando la fuente da el número.
- **Cajón de sastre** («Tomos únicos» con `#1..#N`): rompe enriquecimiento, autores, años,
  ComicInfo y lectores externos. Descartado sin matices.
- **Usar `Collection` como identidad**: agrupa series para estanterías; no identifica una obra ni
  sustituye a la serie.
- **Marcar integrales como one-shot**: falsea la relación con las publicaciones que recopilan y
  bloquea la futura Edición.

## Consecuencias

- **Migración 0049** (si se aprueba): añadir `one_shot` al enum `series_kind`, sin DML ni backfill;
  las series existentes siguen `regular`. El valor no se usa dentro de la misma migración que lo
  añade.
- **Sin cambios** en `Issue.issue_number` (ya nullable), `Issue.format` ni `Collection`.
- Cambios en servicios de huecos/colección/política, UI de alta/ficha, filtro de selector y B6
  (fase posterior). Detalle y pruebas en la especificación.
- **Compatibilidad**: una instalación existente no cambia; marcar una serie como one-shot es una
  acción explícita del coleccionista. No se convierten automáticamente series de `total_issues=1`.
- **Riesgo aceptado**: una serie abierta con un solo número **no** es one-shot; la marca es una
  decisión humana, no una inferencia por `total_issues == 1`.

## Decisiones aceptadas por el PO (2026-11-17)

1. **Sí** a `SeriesKind.ONE_SHOT`; el número se copia **solo si la fuente lo da**; si no, `NULL`.
2. La ficha muestra **«Tomo único · completo» sin cifras de grapa**, no «1/1».
3. **Integrales/omnibus fuera** de esta decisión hasta que exista la entidad *Edición*; no se
   marcan como one-shot.
4. **`SeriesGroup` en ComicInfo se pospone** a ETQ6/B6; no entra en el primer corte.
5. **Sin backfill** de obras existentes en v1; si se quiere, será un dry-run separado con
   confirmación.

## No verificado / NOT RUN

- No se ha hecho censo de cuántas series reales tienen `total_issues=1` con formatos no-grapa.
- No se ha medido en navegador la propuesta de alta ni el filtro del selector.
- No se ha modificado el ADR 0003/0016 ni el esquema; este ADR no autoriza migración.
