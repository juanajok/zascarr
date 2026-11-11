# Diseño de migración de identidad editorial (#184, MIT-M5)

> **Estado: DISEÑO PROPUESTO. NO APROBADO. MIGRACIÓN NO AUTORIZADA, NO EJECUTADA Y NO
> DESPLEGADA.** Este documento **no ejecuta** migraciones, no modifica producción, no toca la Pi,
> no crea tablas ni escribe datos. Es un diseño condicionado a disparadores medibles.
> **Base de código:** `origin/main` **`7508bca`** (2026-11-11; worktree `.squad/wt-184`). El censo
> de #181 se ejecutó en `alembic_version=0020`; desde entonces hay migraciones no relacionadas
> (0026-0029), pero la identidad editorial sigue sin `editions`, `edition_id` ni `number_key`.
> **Insumos:** #181 (`censo-identidad-real.md` + `censo-identidad-2026-11-04.txt`), #182
> (`discriminantes-publicacion.md`), #183 (`refinamiento-183.md`), ADR 0003, benchmark de identidad
> editorial y esquema actual (`models/__init__.py`, migraciones).
> **Decide el PO.** Diseñar no es aprobar; aprobar no es autorizar; autorizar no es ejecutar.

---

## 0. Resumen y recomendación

**Recomendación: NO AUTORIZAR la migración ahora.** El censo de #181 no observa hoy el problema que
la migración resolvería: **0 colisiones de clave, 0 recopilaciones, 0 `covered_issue_ids`, 0 archivos
con ComicInfo y 443/443 `Issue` con `format=single_issue`**. El modelo actual tiene una sola edición
implícita por serie; no hay evidencia de que haga falta separar ediciones ni de que existan
recopilaciones que cubran grapas.

El diseño se entrega **condicionado a disparadores medibles** (§6). Ningún disparador autoriza por sí
solo: abre una revisión de diseño y, si procede, una autorización separada (§7). El censo deja una
duda honesta —los **897 archivos sin Issue** no se han caracterizado—; esa duda se cierra con un censo
de contenido, no con esta migración ni con una suposición.

**Lo que sí se puede hacer sin migrar:** seguir con el camino actual (discriminantes de #182,
elección explícita de #183 en JSONB, ambigüedad a revisión manual); #183 ya demuestra que se puede
elegir una publicación local sin cambiar el esquema (`File.metadata_["publicacion_identificada"]`).

**Si se autorizara en el futuro**, el orden propuesto es aditivo y conservador: tablas/columnas
nuevas → backfill de ediciones y vínculos → validación → solo después, y en un corte separado, retirar
la clave antigua. Nunca se borran ni se reescriben rutas, hashes, IDs, vínculos, procedencia ni
recuentos; las columnas heredadas se conservan hasta que una validación lo autorice (§3-§4).

---

## 1. Evidencia: lo que el censo mide y lo que no

### 1.1 Tabla del censo (#181)

Censo ejecutado **2026-11-04** en la Pi del PO, `alembic_version=0020`, checkout `8fc761f`,
transacción `READ ONLY` (`censo-identidad-real.md:6-17`; salida íntegra
`censo-identidad-2026-11-04.txt`).

| Métrica | Valor | Lectura |
|---|---:|---|
| Issues | **443** | Catálogo medido |
| `format` | **`single_issue` 443**; resto 0 | Ningún formato de recopilación en la BD (`censo-identidad-real.md:33`) |
| Series | **20** (american 13, tebeo 4, franco-belga 2, manga 1) | Contexto del catálogo (`:42`) |
| `grupos_con_multiples` | **0** | Ningún grupo serie+número con más de un issue (`:34`) |
| `colisiones_null` | **0** | Ningún duplicado con `volume` NULL (`:34`) |
| `otras_ediciones_posibles` | **0** | Ningún número en dos volúmenes distintos (`:35`) |
| `issues_sin_numero` | **0** | Ningún issue sin número (`:34`) |
| Recopilaciones con archivo | **0** | Ningún tomo/ómnibus/álbum con archivo (`:36`) |
| `covered_issue_ids` no vacío | **0** | Ninguna evidencia **almacenada** de cobertura (`:37`) |
| `files_con_comicinfo` | **0** | Ningún archivo con `metadata_source='comicinfo_xml'` (`:37`) |
| `issues_volume_null` | **0** | Ningún `volume` nulo (`censo-identidad-2026-11-04.txt`) |
| Archivos sin Issue | **897** | `files.issue_id IS NULL`; **no** se ha abierto ninguno (`censo-identidad-real.md:43`) |
| Sin fuente de metadatos | **272/443 (61,4 %)** | Calidad de datos, no identidad (`:38`) |
| Con fuente | **171 `comic_vine` (38,6 %)** | Ídem |

**Lectura literal:** en lo que el censo mide, **no aparece el problema** que la migración resolvería.
No hay una segunda edición, ni una recopilación, ni una colisión de `number_key` (de hecho
`number_key` no existe). El `UNIQUE(series_id, issue_number, volume)` no tiene nada que desambiguar.
El ADR 0003 ya lo advirtió: el censo de nombres no sustituye al de filas/colisiones; ahora el de filas
tampoco muestra diversidad editorial (`docs/adr/0003-identidad-editorial.md:129-137,326-354`).

### 1.2 Discriminantes acordados (#182)

`docs/design/discriminantes-publicacion.md:28-45` fija qué identifica y qué no:

- **Identidad:** UUID local de `Series`/`Issue`; identificador externo **de su fuente**
  (`comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`…), único dentro de esa fuente. No hay
  identidad editorial universal.
- **Discriminantes para mostrar/comparar, nunca para decidir solos:** título y año de la serie,
  tradición, editorial/sello (`Publisher`/`Imprint`), número (`issue_number`), formato de publicación
  (`Issue.format`), fuente/procedencia, id externo y URL de ficha si consta. `Issue.volume` es dato
  heredado, no identidad.
- **No disponibles / no inventar:** idioma y país de edición, identidad de obra, edición/reimpresión,
  ISBN, cobertura. `Issue.isbn` existe como columna, pero **nada la escribe ni la lee** (`:38`).
- **Ambigüedad persistente:** no se elige automáticamente; se explica y se usa el camino manual
  (`:67-77`).
- La migración sigue **no autorizada**; los disparadores de #182 coinciden con los de §6
  (`:129-141`).

### 1.3 Lo que el censo **no** mide (no convertirlo en certeza)

- **Los 897 archivos sin Issue.** El script no abre archivos; no puede decir si son packs, tomos o
  vinculaciones incompletas (`censo-identidad-real.md:43,59-67`). El `.txt` marca 9 de 20 candidatos
  con nombre que «parece rango», pero es **heurístico, no cobertura**.
- **ComicInfo dentro del archivo.** `files_con_comicinfo=0` solo mide `metadata_source`; no se
  inspeccionó el contenido (`:59`).
- **Catálogos editoriales y revisión manual** (`:59`).
- **Segunda instalación**; el censo describe una biblioteca, no el parque (`:61`).
- **`Issue.isbn`:** columna presente, sin escritura/lectura; no hay datos que permitan usarla.
- **`Series.kind=annual|special`:** el modelo actual ya tiene líneas de numeración propias
  representadas como **Series** (migración 0027; `models/__init__.py:46-60,501-511`), pero el censo no
  las midió. No se convierten en «ediciones» por suposición.

**Conclusión de evidencia:** el diseño se hace **para el futuro**, no para un problema presente. No
se autoriza nada; cualquier migración futura debe empezar por un **re-censo** en el SHA/alembic vigente
(§6).

---

## 2. Modelo objetivo explícito

### 2.1 Entidades y relaciones

Según ADR 0003 (`docs/adr/0003-identidad-editorial.md:33-40,60-68,85-98`):

```
Series 1 ─── N Edition 1 ─── N Publication (Issue)
                                   │
File N ─── M Publication           │
   │                               │
   └── N ─── M Publication (file_publications)
```

| Entidad | Hoy | Objetivo | Identidad |
|---|---|---|---|
| **Serie** | Sí (`Series`, `models/__init__.py:467-535`) | Se conserva | `Series.id` UUID; IDs externos de su fuente, únicos y paralelos (`:517-533`) |
| **Edición** | **No existe** (`grep` de `editions`/`edition_id` en `src/` y `alembic/`: sin resultados) | Tabla nueva `editions` | `edition.id` UUID; lógica `(series_id, edition_key)`; nunca el sello |
| **Publicación** | Sí (`Issue`, `models:582-620`) | Se conserva la tabla `issues`, con `edition_id` y `number_key` | `Issue.id` UUID; `(edition_id, number_key)` cuando hay número; id externo si consta |
| **Archivo** | Sí (`File`, `models:668-715`) | Se conserva; enlace N:M a publicaciones | `File.id`; `file_path` único; `sha256` identifica contenido, no publicación |
| **Cobertura** | No existe; `covered_issue_ids` vacío y sin procedencia (`models:696`) | **Fuera de esta migración** (D4.2); no se crea aquí | `(collection_issue_id, target_issue_id)` si algún día se autoriza |

**Relaciones objetivo:**

- `Edition.series_id → Series.id` (N:1).
- `Publication.edition_id → Edition.id` (N:1). `Issue.series_id` se conserva por compatibilidad y debe
  ser coherente con `Edition.series_id`.
- `file_publications`: N:M entre `File` y `Issue` (una fila por par). Sustituye conceptualmente a
  `File.issue_id` 0..1, pero **no lo retira** en la primera migración.
- `issue_coverages` (si se autoriza) N:M entre publicaciones, **no** es lo mismo que
  `file_publications`: una es relación física archivo↔publicación; la otra, bibliográfica
  tomo→grapas (ADR 0003, D4; benchmark §«Dos relaciones»). No se mezclan.

### 2.2 Tablas y columnas objetivo

#### `editions` (nueva)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `UUID PK` | Identidad local |
| `series_id` | `UUID NOT NULL FK series(id) ON DELETE CASCADE` | La serie de la que es línea de numeración |
| `edition_key` | `text NOT NULL` | Clave estable dentro de la serie: `regular`, `annual`, `special`; futuras `reprint:<...>`, `collection:<...>` |
| `kind` | enum `EditionKind` | `regular`, `annual`, `special`, `reprint`, `collection` |
| `numbering_unit` | enum `NumberingUnit` | `issue`, `chapter`, `volume`, `unknown`; no se infiere del nombre |
| `name` | `text NULL` | Nombre visible/editorial si consta; no es identidad |
| `source_ref` | `text NULL` | Referencia de la fuente si consta; no URL de portada |
| `origen` | enum `OrigenEdition` | `migracion`, `humano`, `fuente` |
| `creado_en` | `timestamptz NOT NULL` | — |

`UNIQUE(series_id, edition_key)`. Índice por `series_id`.

- **Migración inicial:** una edición por `Series` existente; `edition_key` = valor de
  `Series.kind` (`regular|annual|special`); `numbering_unit='unknown'` salvo que una fuente/PO lo
  acredite; `origen='migracion'`. No se inventan nombres editoriales.
- **Sello:** `Publisher`/`Imprint` siguen en `Series`. No se añaden a `editions` en esta migración
  (evitar doble verdad; `editions.publisher_id` es decisión abierta del ADR).
- **Año:** no se añade a `editions`; el año de serie está en `Series.start_year`; el año de edición no
  está acreditado y no se inventa.

#### `issues` (ampliada, no renombrada)

| Columna | Tipo | Regla |
|---|---|---|
| `edition_id` | `UUID NULL FK editions(id) ON DELETE RESTRICT` | Se rellena con la edición de su `Series`; el objetivo final es `NOT NULL` |
| `number_key` | `text NULL` | Clave canónica **dentro de la edición**; solo si el número tiene forma canónica y #125 la aprueba; si no, `NULL` |
| `issue_number` | `text` | Se conserva tal cual; no se reescribe |
| `volume` | `integer` | **Se conserva como legado**; deja de ser identidad; no se borra |
| `format` | `IssueFormat` | Se conserva; no identifica edición por sí solo |
| `comic_vine_id` | bigint unique | Se conserva; id de su fuente |
| `isbn` | text | Se conserva; hoy no se escribe/lee; no se usa como identidad |
| `series_id` | UUID | Se conserva por compatibilidad; `edition.series_id` debe coincidir |

Índices/unique nuevos:

```sql
UNIQUE (edition_id, number_key) WHERE number_key IS NOT NULL
INDEX (edition_id)
INDEX (number_key)
```

`number_key NULL` (sin número) **no** colisiona con otro `NULL`; la unicidad solo aplica a números
canónicos. La clave antigua `UNIQUE(series_id, issue_number, volume)` se mantiene hasta el corte
(§4); no se elimina en la primera migración.

#### `file_publications` (nueva)

| Columna | Tipo | Regla |
|---|---|---|
| `file_id` | `UUID NOT NULL FK files(id) ON DELETE CASCADE` | Archivo |
| `publication_id` | `UUID NOT NULL FK issues(id) ON DELETE CASCADE` | Publicación |
| `estado` | enum `EstadoVinculoArchivo` | `heredado`, `propuesto`, `confirmado`, `rechazado` |
| `procedencia` | `jsonb NOT NULL DEFAULT '{}'` | `origen` (`issue_id_legacy`, `manual`, `evidencia`), `fecha`, `operacion_id`; sin datos personales |
| `creado_en` | `timestamptz NOT NULL` | — |

`PRIMARY KEY(file_id, publication_id)`, índices por `publication_id` y `estado`.

- **Backfill:** una fila por cada `File.issue_id` no nulo, con `estado='heredado'` y
  `procedencia.origen='issue_id_legacy'`. **No se marca `confirmado` automáticamente:** el censo no
  distingue vínculos humanos de automáticos. `heredado` es un estado de migración explícito; un
  humano puede promoverlo a `confirmado` o rechazarlo.
- **`File.issue_id` se conserva** y sigue siendo la referencia mientras dure la compatibilidad; no se
  pone a `NULL`, no se mueve el archivo y no se altera su ruta.
- `file_publications` permite N:M; no se rellena con los 897 archivos sin `issue_id` (no se infiere
  que sean packs).

#### `issue_coverages` (fuera de esta migración)

No se crea en el primer diseño autorizable. `File.covered_issue_ids` (hoy vacío) se conserva como
legado; la cobertura editorial (D4.2) es una relación distinta y no se deduce de `file_publications`.
Si se autoriza, tendrá su propio diseño, estados `propuesto/confirmado/rechazado` y procedencia.

### 2.3 Identificadores y claves únicas

| Elemento | Identidad | Clave única | No es identidad |
|---|---|---|---|
| Serie | `Series.id`; IDs externos de su fuente | `UNIQUE` de cada columna externa (ya existe) | título, `title_norm`, año, editorial |
| Edición | `Edition.id` | `(series_id, edition_key)` | sello, formato, `volume`, nombre solo |
| Publicación | `Issue.id`; `comic_vine_id` si consta | `(edition_id, number_key)`; `UNIQUE(issue.comic_vine_id)`; UUID | número solo, `(serie, número)`, `volume`, formato |
| Archivo | `File.id`; `file_path` único | `file_path`; `sha256` no único (contenido) | nombre, hash como publicación |
| Archivo↔publicación | Par | `(file_id, publication_id)` | `File.issue_id` como única relación |

**No hay identidad universal de obra ni de edición.** El UUID local y el id de la fuente son las
identidades; la edición se identifica por su UUID y su clave lógica, nunca por el sello.

### 2.4 `Series.kind` anual/especial: excepción explícita

El código actual ya tiene `Series.kind` (`regular|annual|special`) y `parent_series_id`
(`models/__init__.py:46-60,501-511`; migración `0027`). Un anual es hoy una **Serie propia** con sus
Issues, no una `Edition`.

**Decisión propuesta (PO):**

- **A (recomendada, transicional):** cada `Series` —incluidas anual y especial— recibe **su propia
  edición**; `Edition.kind` copia `Series.kind`; `Series.parent_series_id` se conserva como relación
  de presentación. No se fusionan filas ni se cambian IDs. El modelo no queda totalmente normalizado
  (un anual es Serie y Edición a la vez), pero la migración es aditiva y no rompe la UI.
- **B:** convertir las Series anuales en Editions de la serie madre y mover sus Issues. Cambia IDs y
  APIs, y no hay censo que lo justifique; **no se propone ahora**.

Sin esta decisión no se implementa `editions`; la opción A permite avanzar sin tocar anuales y deja B
para una migración posterior.

### 2.5 Transiciones de estado

| Objeto | Estado inicial | Transiciones | Regla |
|---|---|---|---|
| Migración (proceso) | `DISEÑADO` | `APROBADO` → `AUTORIZADO` → `EJECUTADO` → `DESPLEGADO` | Ninguna implica la siguiente (§7) |
| `Edition` | `migracion` | sin ciclo de vida propio en esta entrega | No se borra; identidad por UUID/clave |
| `Issue.edition_id` | `NULL` | `NULL → asignada` | Backfill; validación exige asignada salvo excepción documentada |
| `Issue.number_key` | `NULL` | `NULL → calculada` solo si #125 aprueba la función; `NULL` para sin número | No se inventa una forma canónica |
| `file_publications.estado` | — | `heredado → confirmado|rechazado`; `propuesto → confirmado|rechazado` | Solo humano; `heredado` no se presenta como confirmado |
| `issue_coverages.estado` (futuro) | — | `propuesto → confirmado|rechazado` | Fuera de esta migración |
| `File.issue_id` | valor actual | se conserva; no se pone a `NULL` | Compatibilidad; no es la relación final |

**No se crea una `Edition` ni una `Publication` como efecto de una elección de #183.** La elección de
#183 vive en `File.metadata_["publicacion_identificada"]` (JSONB) y apunta a un `Issue` existente
(`refinamiento-183.md:270-330`); la migración la **conserva sin interpretarla**. No se convierte en
`file_publications` automáticamente ni se usa para inventar ediciones.

---

## 3. Compatibilidad: qué se conserva, qué se deriva y qué queda obsoleto

### 3.1 Se conserva sin cambios

| Dato | Por qué |
|---|---|
| `File.file_path` (unique), `file_name`, `file_format`, `file_size_bytes`, `file_mtime_ns` | Ninguna migración mueve ni renombra archivos; la ruta es la referencia del archivo |
| `File.sha256_hash`, `original_sha256`, `is_verified` | El hash identifica contenido, no publicación; no se recalcula |
| `File.issue_id` | Vínculo existente 0..1; se copia a `file_publications` y se mantiene hasta cutover |
| `File.metadata_` JSONB, `metadata_source`, `locked_fields`, `source_tag`, `review_dismissed`, `is_missing` | Procedencia, protección y estado; #183 guarda `publicacion_identificada` aquí y debe conservarse |
| `Issue.id`, `Issue.comic_vine_id`, `issue_number`, `format`, `release_date`, `page_count`, `isbn`, `synopsis`, `cover_url`, `sort_order`, `metadata_`, `metadata_source`, `locked_fields`, `enrichment_attempted_at` | Identidad, metadatos y protecciones existentes |
| `Issue` créditos, personajes, tags, sagas, progreso de lectura, deseados, notas | Relaciones con FK; no se recrean ni se pierden |
| `Series.id`, IDs externos (CV/AniList/Tebeosfera/GCD/Metron/OpenLibrary), `publisher_id`, `imprint_id`, `universe_id`, `kind`, `parent_series_id`, `total_issues`, `wishlist_policy`, `metadata_`, `locked_fields` | Identidad, sellos, clasificación y recuentos |
| `File.metadata_["publicacion_identificada"]` (#183) | Elección local reversible; no se borra ni se convierte |
| `covered_issue_ids` | Aunque vacío, es columna heredada; no se borra ni se reinterpreta |
| `alembic_version` | Se avanza solo con migraciones aprobadas; nunca se salta |

### 3.2 Se deriva (valores nuevos, sin sustituir los antiguos)

| Dato nuevo | Origen | Regla |
|---|---|---|
| `Edition` por Serie | `Series` existente | Una por `Series` (A de §2.4); `origen='migracion'`; sin nombre inventado |
| `Issue.edition_id` | `Edition` de su `Series` | Backfill; la relación `Issue.series_id` se conserva |
| `Issue.number_key` | `issue_number` + función #125 | Solo con función aprobada; si no, `NULL`; no se inventa |
| `file_publications` | `File.issue_id` | Una fila por vínculo existente, `estado='heredado'`; no se confirma automáticamente |
| `Issue.isbn` | — | **No se deriva**; sigue sin uso |
| `File.covered_issue_ids` → cobertura | — | **No se deriva**; la cobertura es otra relación y está fuera |

### 3.3 Queda obsoleto (como identidad, no como dato)

| Elemento | Qué pasa | Qué **no** se hace |
|---|---|---|
| `UNIQUE(series_id, issue_number, volume)` | Se sustituye por `(edition_id, number_key)` en el corte | No se elimina antes de validar; se puede recrear en rollback |
| `Issue.volume` | Dato heredado/advertencia; no identidad | No se borra ni se reescribe; se conserva |
| `File.issue_id` | Relación 0..1 heredada; deja de ser la única | No se pone a `NULL`; se mantiene hasta cutover |
| `File.covered_issue_ids` | Columna heredada vacía; no es cobertura confirmada | No se borra ni se migra a `issue_coverages` sin diseño |
| `Series.total_issues` | Recuento externo informativo; no universo de edición | No se recalcula ni se usa para inventar huecos |
| `Issue.isbn` | Columna dormida; no identidad | No se rellena por inferencia |
| Identidad por título/año/formato/volumen | No era identidad | No se usa para fusionar ni separar |

**Compatibilidad de la clave antigua:** mientras exista
`UNIQUE(series_id, issue_number, volume)`, dos ediciones con el mismo número en la misma serie **no
pueden coexistir**. La migración no crea esas filas durante el backfill (solo asigna la edición
existente). El corte que permita dos ediciones exige retirar la clave antigua; es un paso separado,
tras validación y backup (§4). Sin ese corte, el modelo nuevo es compatible y suficiente para
verificar, pero no habilita la coexistencia editorial.

### 3.4 Cómo se evita perder nada

1. **Aditivo primero:** no se borra ni se actualiza ningún valor existente; solo se añaden tablas y
   columnas.
2. **Backfill desde lo existente:** `Edition` desde `Series`; `Issue.edition_id` desde su serie;
   `file_publications` desde `File.issue_id`. No se infiere de nombres ni de los 897 archivos sin
   Issue.
3. **Doble lectura/escritura:** durante la transición, las rutas actuales siguen leyendo
   `File.issue_id`/`Issue.series_id`; las nuevas escriben también en las tablas nuevas. Ninguna
   lectura antigua se rompe.
4. **Nada se elimina hasta después:** columnas y constraints viejos se conservan; la retirada es una
   migración posterior con su propia autorización.
5. **Backup y ensayo:** copia de la BD, ensayo en base desechable, y comparación de snapshots antes de
   cualquier paso en producción.

---

## 4. Orden de migración, puntos de comprobación y reversión

### 4.1 Precondiciones (sin escritura)

- Decisión del PO: diseño **aprobado** y migración **autorizada** por separado (§7), con ventana y
  responsable.
- Re-censo en el SHA/alembic vigente; ningún disparador de §6 sin resolver.
- Backup completo de la BD; verificación de restauración en base desechable.
- Inventario pre: recuentos, rutas, hashes, IDs, IDs externos, `alembic_version` (§8).
- Tests de la app sobre el snapshot; plan de rollback probado en la copia.

### 4.2 Fases propuestas

| Fase | Contenido | Escritura | Checkpoint |
|---|---|---|---|
| **0 · Preflight** | Copia, re-censo, snapshots, ensayo de restauración | Ninguna en producción | Backup restaurable; conteos pre; disparadores revisados |
| **1 · Esquema aditivo** | `editions`, `edition_id`, `number_key`, `file_publications`; sin tocar constraints antiguos | Solo DDL aditivo | Tablas/columnas existen; app antigua sigue funcionando; `alembic_version` nueva |
| **2 · Ediciones** | Una `Edition` por `Series` (A de §2.4), `origen='migracion'` | Solo tablas nuevas | `count(editions)=count(series)`; una por serie; sin duplicados `(series_id, edition_key)` |
| **3 · Asignación** | `Issue.edition_id` desde su serie | Solo columna nueva | Todos los `Issue` con edición; 0 huérfanos; `Issue`/`Series` intactos |
| **4 · Vínculos heredados** | `file_publications` desde `File.issue_id`, `estado='heredado'` | Solo tabla nueva | Filas = `File.issue_id` no nulo; ninguna fila nueva para los 897 sin Issue; `File` intacto |
| **5 · Validación** | Checks de §8 en la copia | Read-only | PASS de integridad; sin pérdidas; rollback probado |
| **6 · Canonización `number_key`** | Función #125 aprobada; backfill; validar colisiones | Columna nueva | 0 colisiones; si >0, **parar** y revisión humana |
| **7 · Doble escritura/lectura** | Flag de aplicación; escribir ambas representaciones; leer la antigua por defecto | App + nuevas tablas | Consistencia; ninguna ruta/hash cambia |
| **8 · Corte de unicidad** | Retirar `UNIQUE(series_id, issue_number, volume)` solo con backup y datos validados; nuevo unique activo | DDL + posible DML | Reversible si no hay filas que violen la clave antigua; si las hay, no se baja sin resolución |
| **9 · Retirada legacy** | Separada, posterior, no en esta autorización: `File.issue_id`/`Issue.volume`/`covered_issue_ids` como solo lectura | DDL destructivo | Requiere otra autorización y backup; **no ahora** |

- **`number_key` depende de #125**, cuya función exacta sigue abierta (ADR 0003, decisiones abiertas
  `:114-124`). Sin esa aprobación, la migración **se detiene en la fase 5**; no se inventa una clave
  canónica.
- **Fase 8 no se ejecuta ahora:** no hay datos que la necesiten; si un disparador la justifica, es
  una autorización aparte con su propio ensayo. Mientras no se ejecute, la clave antigua sigue
  vigente y el modelo nuevo es compatible.
- **La cobertura editorial** (`issue_coverages`) no es una fase de esta migración; su tabla, si se
  autoriza, va en un diseño separado y no se deduce de `file_publications`.

### 4.3 Puntos de comprobación y aborto

Después de cada fase, en la base desechable y luego en producción solo si se autorizó:

1. Recuentos: `series`, `issues`, `files`, `file_publications`, `editions`; sin diferencias no
   explicadas.
2. Integridad: 0 `Issue` sin `edition_id` (salvo lista de excepción vacía); 0 `Edition` sin serie; 0
   `file_publications` con `file_id`/`publication_id` inexistente; 0 filas duplicadas.
3. Vínculos: cada `File.issue_id` no nulo tiene su fila `heredado`; cada fila nueva apunta a un
   `Issue` real; no se ha creado ninguna para los 897 sin Issue.
4. Rutas/hashes: `File.file_path` y `sha256_hash` idénticos al snapshot pre; ninguna ruta nueva o
   desaparecida.
5. IDs externos: recuentos por `comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`, `metron_id`,
   `open_library_id` iguales; `Issue.comic_vine_id` igual.
6. Recuentos: `Series.total_issues` igual; `Wishlist`, `ReadingProgress`, `Notes`, `Tag`/`StoryArc`
   cuentan igual; `covered_issue_ids` igual (0).
7. App: tests y smoke de lectura/escritura en la copia; no se despliega.
8. `alembic_version` exacto al esperado.

**Abortar** si cualquier checkpoint difiere, si hay una colisión de `number_key` sin resolver, si una
fila no tiene edición por causa no documentada, o si una restauración de backup no es verificable. No
se «arregla» un descuadre con `UPDATE`/`DELETE` manual en producción.

### 4.4 Reversión y recuperación

| Punto | Reversión |
|---|---|
| Antes de fase 1 | Nada que revertir; backup |
| Fases 1-5 | `downgrade` de la migración aditiva (drop de tablas/columnas nuevas); los datos viejos nunca se tocaron; app antigua sigue válida |
| Fase 6 (`number_key`) | Drop de la columna/índice nuevo; los `Issue` y números originales siguen; no se pierde nada |
| Fase 7 (doble escritura) | Apagar el flag; las tablas nuevas se ignoran; la app vuelve a leer `issue_id`; no se borran filas nuevas (se pueden quedar como histórico) |
| Fase 8 (corte de unicidad) | Recrear `UNIQUE(series_id, issue_number, volume)` **solo si** los datos no violan la clave antigua; si la nueva coexistencia creó duplicados, la vuelta exige resolverlos (humano/backup); es un **punto de no retorno lógico** |
| Fase 9 (retirada legacy) | Fuera de esta autorización; requeriría backup/restauración completa, no un `downgrade` trivial |

**Regla:** todas las fases 1-7 son aditivas y reversibles con `downgrade`; la fase 8 es la única que
puede no ser reversible sin intervención porque cambia una garantía de unicidad. Por eso no se
autoriza ahora.

---

## 5. Ambigüedades del censo

| Caso | Estado en el censo | Resolución propuesta |
|---|---|---|
| Colisiones de `number_key` (`grupos_con_multiples`, `colisiones_null`) | **0** | No hay nada que resolver hoy. Si aparecen, **no se migra en automático**: se revisan con discriminantes de #182 y decisión humana; la migración se bloquea hasta resolverlas |
| Mismo número en volúmenes/ediciones distintas (`otras_ediciones_posibles`) | **0** | Idem; si aparece, es el disparador de edición y de la fase 8; humano |
| Recopilaciones / `format != single_issue` | **0** | No se crean ediciones de recopilación; si aparece, revisión de discriminantes y cobertura |
| `Issue` sin número (`issues_sin_numero`) | **0** | Si aparece: `number_key=NULL`, no se inventa «0»; la unicidad no aplica; revisión |
| `Issue.volume=NULL` | **0** | Si aparece, no se usa como identidad; el `NULL` no colisiona; revisión |
| `covered_issue_ids` no vacío | **0** | No se migra cobertura; se conserva como legado; si aparece, diseño separado |
| ComicInfo dentro de archivos | **0 medido; no inspeccionado** | Fuera de esta migración; censo de contenido aparte; no se usa como evidencia automática |
| 897 archivos sin Issue | **No caracterizados** | **Fuera de alcance**: no se asume que sean packs; no se crean filas ni publicaciones; censo de contenido (§6) |
| `Issue.isbn` | **Sin escritura/lectura** | No es identidad; no se rellena; si algún día se usa, decisión aparte |
| Series anuales/especiales (`Series.kind`) | No medido; existe en el modelo | Decisión A/B de §2.4; recomendación A (transicional), sin fusionar Series |
| Dos `Series` con mismo título/año | No es una colisión de `number_key`; no medido | No se funden; se identifican por UUID/id de fuente; #182; humano |
| Sello/editorial distinto para el mismo número | **0** hoy | No se usa como identidad; atributo; si aparece, discriminante + humano |
| 443 `Issue` con `single_issue` | **443/443** | No se inventa una edición distinta por formato; el formato no identifica |

**Regla:** una ambigüedad no se resuelve por el script, ni por título/año, ni por «la primera». Se
resuelve con discriminantes acreditados y, si persiste, con intervención humana; si no, se deja fuera.

---

## 6. Disparadores de necesidad medibles

Ningún disparador autoriza la migración. Cada uno **abre una revisión** y exige re-censo en el
SHA/alembic vigente; la autorización es una decisión posterior (§7).

| # | Disparador | Cómo se mide | Quién evalúa |
|---|---|---|---|
| **D1** | Aparece `format != single_issue` en el catálogo | Re-censo `#181` por `Issue.format`; `>0` con archivo | PO + responsable de datos |
| **D2** | Colisiones de la clave actual | `grupos_con_multiples >0` o `colisiones_null >0` | PO + datos |
| **D3** | Mismo número en dos volúmenes/ediciones | `otras_ediciones_posibles >0` | PO + datos |
| **D4** | Recopilaciones con archivo o cobertura almacenada | `format != single_issue` con archivo, o `covered_issue_ids` no vacío | PO + datos |
| **D5** | Evidencia externa de cobertura | Censo de contenido: ComicInfo dentro de los archivos >0, o catálogo/revisión humana que la acredite | PO + datos + revisión manual |
| **D6** | Los 897 archivos sin Issue resultan packs/tomos | Censo de contenido sobre los 897 (nombres + ComicInfo + revisión), no una suposición | PO + datos |
| **D7** | `Issue.isbn` con datos | Consulta de solo lectura: `isbn IS NOT NULL` en `issues`; hoy 0 por ausencia de escritura | PO + datos |
| **D8** | Una fuente real exige identidad de edición/publicación que el modelo no puede representar | Evidencia de una operación soportada que falla por falta de `edition_id`/N:M; no «la web lo muestra» | PO + quien implementa la fuente |
| **D9** | Un archivo debe apuntar a varias publicaciones de forma confirmada | Caso real de pack/omnibus con archivo y varias publicaciones; no rango heurístico | PO + revisión manual |
| **D10** | Se decide normalizar las Series anuales/especiales como Editions | Decisión de producto explícita, no un dato del censo | PO |

- **Evaluador:** el PO (o quien delegue) ejecuta/encarga el re-censo **read-only** y registra
  `alembic_version`, SHA, fecha, parámetros y salida; no se acepta «hay bastantes» sin cifra.
- **Re-censo obligatorio** antes de cualquier autorización: el censo de #181 es de `0020`; el código
  actual está en `0029` y el catálogo puede haber cambiado. La cifra vieja no autoriza nada.
- **Un disparador no equivale a autorización:** D1-D10 abren diseño/revisión; la migración sigue
  necesitando aprobación y autorización separadas (§7).

---

## 7. Separación de estados y autorizaciones

Ninguno de estos estados implica el siguiente; cada uno exige una decisión explícita y evidencia
propia.

| Estado | Qué significa | Quién | Evidencia |
|---|---|---|---|
| **Diseño propuesto** | Este documento: modelo, compatibilidad, orden, validación | SPEC/autor | Este fichero; **estado actual** |
| **Diseño aprobado** | El PO acepta el modelo y los disparadores, sin autorizar ejecución | PO | Registro de aprobación; no toca datos |
| **Migración autorizada** | Permiso explícito para ejecutar un plan concreto, ventana, backup y responsable | PO (decisión separada) | Autorización firmada/registrada; plan y presupuesto |
| **Migración ejecutada** | Las migraciones se aplicaron a una base concreta (ensayo o producción) | Responsable autorizado | Log de migración, `alembic_version`, checkpoints y snapshots |
| **Desplegado** | La aplicación usa el modelo nuevo en producción | PO/operación | Versión desplegada y smoke; no se deduce de «ejecutada» |

**Estado actual:** diseño **propuesto**, no aprobado; migración **no autorizada**, **no ejecutada**,
**no desplegada**. Cualquier afirmación distinta es falsa.

**Secuencia mínima para autorizar (futuro):** disparador medido → re-censo → diseño revisado →
aprobación del PO → plan de ejecución + backup + ventana → autorización separada → ensayo en base
desechable → ejecución → validación post → despliegue separado.

---

## 8. Plan de validación pre/post

### 8.1 Snapshots y comprobaciones

Se comparan **antes** (base actual), **en la copia ensayada** y **después** (si se autoriza ejecutar);
los valores deben ser idénticos salvo las columnas/tablas nuevas previstas.

| Grupo | Qué se comprueba | Criterio |
|---|---|---|
| **Recuentos** | `series`, `issues`, `files`; `file_publications`; `editions`; `wishlist`, `reading_progress`, `notes`, `tags`, `story_arc_issues` | Iguales a pre; nuevas tablas con el conteo derivado esperado |
| **Vínculos** | `File.issue_id` no nulo; filas `file_publications` por vínculo; 0 huérfanos; 0 duplicados | Cada vínculo existente conservado; ninguna creación para los 897 sin Issue |
| **Rutas/hashes** | `File.file_path`, `file_name`, `file_size_bytes`, `sha256_hash`, `original_sha256`, `file_mtime_ns` | Idénticos; ninguna ruta movida/renombrada/borrada |
| **IDs** | `Series.id`, `Issue.id`, `File.id`; `Issue.comic_vine_id`; IDs externos de Serie | Idénticos; sin reasignaciones |
| **Procedencia y protección** | `metadata_source`, `locked_fields`, `metadata_` JSONB, `File.metadata_["publicacion_identificada"]` | Idénticos; la elección de #183 se conserva |
| **Recuentos por fuente** | `comic_vine`, `anilist`, `tebeosfera`, `gcd`, `metron`, `open_library`; `metadata_source` de Issues | Iguales; no se reclasifica |
| **Recuentos editoriales** | `Series.total_issues`, `Issue` count, `covered_issue_ids` | Iguales; no se recalcula ni se inventa |
| **Esquema** | `alembic_version`, constraints, FKs, índices | `alembic_version` avanza solo con migración autorizada; constraints nuevas presentes; viejas conservadas hasta corte |
| **Integridad** | `Issue.edition_id` no nulo (salvo lista de excepción vacía); `Edition.series_id` existe; `file_publications` FKs; `number_key` sin colisiones | 0 violaciones |

### 8.2 Ensayo en base desechable

1. Restaurar el backup en una base con nombre `*_test_*`/desechable, nunca producción.
2. Aplicar las migraciones en el orden de §4; ejecutar los checkpoints de §4.3.
3. Ejecutar la suite de la app y un smoke de lectura/escritura sobre la copia.
4. Probar el `downgrade` de las fases aditivas y, si se llega, la recreación de la clave antigua.
5. Comparar snapshots pre/post y registrar PASS/FAIL/NOT RUN.
6. Solo si todo PASS, proponer la ejecución autorizada en producción (decisión aparte).

### 8.3 PASS / FAIL / NOT RUN de este diseño

- **PASS de lectura:** censo, discriminantes, ADR 0003 y esquema actual contrastados; modelo,
  compatibilidad, orden, disparadores y validación definidos; sin ejecución.
- **FAIL:** ninguno del diseño.
- **NOT RUN:** migraciones (no existen), pruebas, ensayo en base, producción, Pi, navegador y
  despliegue. **No se ha autorizado nada.**

---

## 9. Mapa AC de #184 → secciones y NOT RUN

| AC #184 | Qué exige | Dónde se cumple |
|---|---|---|
| 1. Diseño basado en evidencia | Citar censo y discriminantes; no suposiciones | §1.1-§1.3; §5 |
| 2. Modelo explícito | Entidades, relaciones, identificadores, claves únicas, transiciones | §2.1-§2.5 |
| 3. Compatibilidad definida | Qué se conserva, deriva, queda obsoleto; evitar pérdida | §3.1-§3.4 |
| 4. Orden y reversibilidad | Pasos, checkpoints, reversión/recuperación | §4.2-§4.4 |
| 5. Ambigüedades resueltas o marcadas | Discriminantes, humano o fuera de alcance | §5 |
| 6. Separación de autorizaciones | Propuesto/aprobado/autorizado/ejecutado/desplegado, sin implicación | §7 |
| 7. Plan de validación | Conservación, integridad, recuentos, ensayo | §8 |
| 8. Sin ejecución | No migra, no toca producción, no despliega | §0, §7, §8.3, este apartado |

**NOT RUN explícito:** esta entrega **no** ejecuta migración, no modifica la base, no toca la Pi, no
cambia el esquema, no crea tablas, no borra ni actualiza datos, no ejecuta pruebas y no despliega. El
documento es el diseño; la migración queda condicionada a disparadores y a una autorización separada.

**Recomendación final:** **no autorizar ahora.** Reabrir con un re-censo que cumpla uno o más
disparadores de §6; si se cumple, actualizar este diseño con la evidencia nueva y decidir. La
alternativa a corto plazo es el camino actual: discriminantes de #182, elección de #183 en JSONB y
revisión manual; no se pierde nada y no se inventa una identidad que los datos no sostienen.
