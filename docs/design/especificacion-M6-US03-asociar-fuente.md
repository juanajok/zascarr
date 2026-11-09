# Especificación — MIT-M6-US03: Asociar otra fuente explícitamente (#129)

> **Estado:** propuesta de refinamiento para el PO. **No implementa código, no crea migración, no
> consulta fuentes reales y no ejecuta pruebas.**
> **v1.1 (2026-11-09):** revisión de Seguridad H1-H17 sobre B y C; **el contrato vigente de B y C es
> §8** y sustituye §4.2-§4.6/§5.1 donde contradiga. A está fusionada (#542) pero **sin token**: el
> delta de §8.1 es obligatorio antes de B.
> **Contraste:** `origin/main` en **`04ab6eea58e0deb98d1f12f6fb7d9d69e4f3f7ad`** para la v1.0
> (2026-11-09; worktree `.squad/wt-129`, rama `docs/129-refinamiento`) y **`a87eabd`** para §8
> (2026-11-09; worktree `.squad/wt-129b-spec`). Las citas `fichero:línea` de §8 se refieren a
> `a87eabd`; las de §1-§7, a `04ab6ee`.
> **Insumos:** #129 (historia), #109 (contrato compartido), #124/#182 (identidad editorial), #133/#134
> (estados y cortesía), #128 (plan de enriquecimiento por campo), #127 (procedencia visible).
> **Método:** lectura de código y documentos en ese SHA; no se ejecutaron pruebas ni peticiones a
> fuentes. Lo no comprobado va marcado `[sin verificar]` o como NOT RUN.

---

## 0. Resumen para el PO

**Qué falta.** Hoy una serie solo puede tener identidad externa en **una** de las cuatro fuentes
(`comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`) y **el enricher no la empareja con otra
fuente a propósito** (`services/enricher.py:32-36`). Asociar una segunda fuente de forma explícita
**no existe**: no hay tabla, ni campo, ni pantalla, ni ruta (ver §1).

**Qué se propone.** Una operación en dos entregas: **A** consulta **una** fuente autorizada y
compara candidatas sin escribir nada; **B** guarda la correspondencia confirmada con procedencia y sin
fusionar, enriquecer ni tocar archivos. La corrección (retirar) es un corte propio y explícito.

**Decisión de modelo.** La entidad asociada es la **serie** (`Series`); no hay entidad de edición ni
de obra (#124/#182/ADR 0003) y `Issue` solo tiene identidad de Comic Vine. Una asociación como máximo
**por fuente y serie**, con las cuatro columnas únicas que ya existen: **no hace falta migración**.

**Persistencia.** No se toca `metadata_source` (es procedencia de *enriquecimiento*, univaluada) ni
`locked_fields`: la asociación se anota en `Series.metadata_["asociaciones"]` (versionado, con fecha y
`operacion_id`) y su comprobante de idempotencia reutiliza `vinculacion_operaciones` con un `tipo`
nuevo, igual que hizo la retirada de serie (`services/retirada_serie.py:340-390`).

**Corte.** A (M/5) → B + visibilidad de procedencia (M/5) → corrección/retirada (S/2). Ningún corte
necesita migración ni toca archivos. El antecedente 13/XL queda **repartido en tres cortes que no
pasan de M** (§5).

**Lo que este documento no decide.** Las seis decisiones bloqueantes se argumentan, pero **decide el
PO**; y el benchmark de referencias (Sonarr/Radarr/Kapowarr con varios identificadores por entidad)
está **NOT RUN** (§5.3).

---

## 1. Qué existe hoy (SHA `04ab6ee`)

### 1.1 Identificaciones por fuente

Se guardan en **columnas paralelas de `Series`**, una por fuente, cada una con `unique=True`:

| Fuente | Columna | Tipo | Línea |
|---|---|---|---|
| Comic Vine | `Series.comic_vine_id` | `BigInteger`, único | `src/zascarr/models/__init__.py:410` |
| AniList | `Series.anilist_id` | `BigInteger`, único | `src/zascarr/models/__init__.py:415` |
| Tebeosfera | `Series.tebeosfera_slug` | `String(255)`, único (slug de texto) | `src/zascarr/models/__init__.py:418` |
| GCD | `Series.gcd_id` | `BigInteger`, único | `src/zascarr/models/__init__.py:421` |

Evidencia de que el mapa fuente → columna es único en el código:
`src/zascarr/services/discovery.py:53-59` (`CAMPO_ID_EXTERNO`) y, para el enricher,
`src/zascarr/services/enricher.py:269-278` (`_source_for`, que elige **por tradición**).

Otras entidades con identidad externa, **fuera del alcance de #129**:

- `Issue.comic_vine_id` (`src/zascarr/models/__init__.py:489`), único. No hay id externo de número
  para AniList, Tebeosfera ni GCD.
- `Publisher.comic_vine_id` (`:281`), `Creator.comic_vine_id` (`:338`), `Character.comic_vine_id`
  (`:365`), `StoryArc.comic_vine_id` (`:461`).

**No existe una tabla de asociaciones** ni un campo «fuentes asociadas»: la asociación *es* el valor
de la columna. Consecuencia directa: el modelo admite hasta cuatro identificadores no nulos a la vez
(no hay `CHECK` que lo impida), pero **nada los lee en conjunto**; el enricher considera «identificada»
cualquier serie con uno y la excluye (`src/zascarr/services/enricher.py:190-202`).

### 1.2 `metadata_source` en cada modelo

| Modelo | Columna | Semántica que el código le da |
|---|---|---|
| `Series` | `metadata_source` `String(20)` (`:424`) | Fuente del **alta** o del **enriquecimiento**. Se escribe al crear (`services/alta_serie.py:456`) y al enriquecer **solo si es `NULL`** (`services/enricher.py:296-297`). `manual` bloquea el enriquecimiento entero (`services/enricher.py:202`; `services/enriquecimiento_plan.py:347-348`). |
| `Issue` | `metadata_source` (`:492`) | Comic Vine al aplicar campos del número (`services/enriquecimiento_plan.py:461-462`). |
| `File` | `metadata_source` (`:587`) | `comicinfo_xml` (importador/adoptador) o `manual` (vincular/asignar). |
| `Publisher`, `Creator`, `Character` | `metadata_source` (`:283`, `:341`, `:368`) | La fuente que rellenó la ficha. |

Es **univaluada y por entidad**, no por campo: `services/procedencia.py:146-163` solo atribuye los
campos que escribe el enriquecimiento y únicamente cuando tienen valor. No hay sitio donde quepa «esta
serie también está en GCD».

### 1.3 `locked_fields`

`ARRAY(String)` en `Series` (`:431`), `Issue` (`:495`), `Creator` (`:344`) y `Character` (`:369`).
Lista de **nombres de campo** que el enriquecimiento no sobrescribe. En `Series` solo lo escribe el
alta desde una fuente, con el campo del id externo (`services/alta_serie.py:457`); en `Issue` lo
escriben los caminos que crean un número, con `series_id`/`issue_number`
(`services/review.py:305`, `services/vinculacion.py:345`, `services/asignacion.py:574`). El enricher
solo lo lee (`services/enricher.py:287-297`), y `services/enriquecimiento_plan.py:184-206` muestra la
propuesta como `bloqueado` y **nunca sustituye la identidad** ya presente (`:201-206`).

No hay operación de «desbloquear» en la UI: `docs/design/procedencia-127.md` §3 lo declara estado de
solo lectura.

### 1.4 `File.source_tag` no es una fuente de metadatos

`File.source_tag` (`:582`) es una **heurística del nombre del archivo**: busca `digital`, `scan`,
`scan_hq` en el último bloque entre paréntesis (`src/zascarr/core/importer_triage.py:75-110`). Se
escribe en el importador (`services/importer.py:762`) y en el adoptador
(`services/library_adopter.py:934`). No acredita de dónde salen los metadatos y **no debe reutilizarse
como procedencia** de una asociación.

### 1.5 Confirmación, tokens, comprobantes e idempotencia existentes

| Mecanismo | Dónde | Qué garantiza |
|---|---|---|
| Token firmado (HMAC) con **propósito + contexto + caducidad** | `services/tokens_revision.py:90-125` (`crear_token` / `verificar_token`), reutiliza la firma de sesión | El formulario no reenvía datos sueltos: reenvía lo que el servidor vio. Propósitos ya en uso: `candidata`, `alta`, `vincular`, `desvincular`, `retirar_serie` (`:37-42`). |
| Plan firmado + **huella** de lo que se vio | `services/enriquecimiento_plan.py:138-158` (`_huella`), `:343-373` (previsualizar), `:388-420` (aplicar) | Si la ficha cambió entre vista y aplicación, se rechaza con «vuelve a revisarla»; no se vuelve a consultar la fuente. |
| Vista previa de retirada con huella | `services/retirada_serie.py:285-310` | Mismo patrón, con `huella_de_estado`. |
| Comprobante de alta (`alta_operaciones`) | `models:707-726`; `services/alta_serie.py:420-432` (repetir), `:476-478` (crear + comprobante) | Reenviar el mismo token devuelve lo mismo; sobrevive a un «deshacer». |
| Informe **inmutable** de vinculación/retirada (`vinculacion_operaciones`) | `models:729-748`; disparador `BEFORE UPDATE` en `alembic/versions/20261009_0019_vinculacion_operaciones.py:49-59`; retirada lo reutiliza con `tipo="retirada_serie"` (`services/retirada_serie.py:340-390`) | Idempotencia y resultado recuperable tras reiniciar, sin tabla nueva. Se purga a las 24 h y token caducado, **solo su tipo** (`:441-448`). |
| Candado consultivo por operación | `services/vinculacion.py:222-260`; `services/alta_serie.py:417` y `:481-483`; `services/retirada_serie.py:335-338` | Dos envíos simultáneos del mismo token se serializan. |
| Resultado incierto | `services/vinculacion.py:103-107`, `:188-201`; `services/retirada_serie.py:317-333` | Un fallo tras pedir `commit` no se anuncia como «no se ha cambiado nada»: se re-responde 503 y se relee. |
| Operación recuperable de archivos (ADR 0006) | `services/asignacion.py:1-31`, `:613-625` (`_resultado_desconocido`) | Un `commit` de resultado desconocido se comprueba con otra sesión; **nunca** se trata como `rollback`. Es el precedente de recuperación; B no lo reutiliza porque no mueve archivos. |
| Inventario de operaciones | `services/operaciones.py:126-128` | `/api/operaciones` cuenta solo las filas **sin** `tipo`; un `tipo` nuevo queda fuera del recuento (y se decide aparte, §5.3). |
| Historial de deshacer en JSONB | `services/desvinculacion.py:194-229` | Retirar un vínculo no borra: quita la clave y **añade** una entrada a `metadata.vinculo_historial` con `deshecho:{operacion_id,fecha}`. |
| Regla de fusión de `Series.metadata_` | `services/alta_serie.py:212-218` (`fusionar_metadata`) | Fusionar por clave de primer nivel, nunca sustituir el objeto y **no tocar `alta`**. |

### 1.6 ¿Hay pantalla o endpoint de «asociar fuente»? **No**

- Rutas de la ficha: `GET /ui/series/{id}`, `POST /ui/series/{id}/enriquecimiento/previsualizar` y
  `/aplicar`, etiquetas y política (`src/zascarr/web/series.py:341`, `:375`, `:395`, `:416-539`).
- Rutas de revisión: alta, vincular, desvincular y retirar (`src/zascarr/api/revision.py:237-476`;
  `src/zascarr/web/retirada_serie.py:111,129`).
- **No hay** ruta, plantilla ni servicio con «asociar fuente», «identidad» o equivalente
  (`grep -rn "asociar\|asociación" src/zascarr`: solo comentarios de Tebeosfera sobre cortesía).
- `services/edicion_serie.py:28` define identidad como **título, tradición y año**; los identificadores
  externos no se pueden editar desde ninguna superficie.

La ficha muestra la procedencia (`src/zascarr/web/templates/series_detail.html:49-81`), pero la
identidad va **agrupada en una sola fila** y **nunca pinta el id** (`services/procedencia.py:107-112`;
`docs/design/procedencia-127.md` §1-§2).

### 1.7 Unicidad por identificador externo

**Sí, por columna y por fuente**, no global:

- `unique=True` en las cuatro columnas de `Series` y en `Issue.comic_vine_id` (`models:410-421`,
  `:489`). Un `INSERT/UPDATE` con un id ya usado por otra fila falla con `IntegrityError` (índice
  único).
- No hay unicidad *cruzada* entre fuentes (correcto: el id 123 de GCD no es el 123 de Comic Vine) ni
  una tabla que relacione «serie ↔ fuente ↔ id» con su procedencia.
- El alta ya trata la carrera por el identificador: si al crear salta el único, busca la serie
  existente y la reutiliza (`services/alta_serie.py:461-473`). **Para asociar, ese mismo choque es un
  conflicto que hay que explicar, no una reutilización silenciosa** (criterio 8 de #129).

### 1.8 Lo que el código ya decidió: no asociar otra fuente

- El enricher excluye **cualquier** serie con uno de los cuatro ids (`services/enricher.py:190-202`) y
  lo razona en el docstring: «Asociarle otra fuente es una acción explícita y confirmada, que no
  existe todavía» (`:32-36`).
- #128, al preparar un plan, **conserva** la identidad existente y no propone sustituirla
  (`services/enriquecimiento_plan.py:201-206`).
- La vista de procedencia no atribuye identidad si no hay alta o enriquecimiento
  (`services/procedencia.py:146-163`).

Es decir: el producto ya tiene la **intención** de no inventar correspondencias; falta el camino
explícito. #129 no contradice esas reglas: las usa.

### 1.9 Huecos declarados de lo existente

| Hueco | Consecuencia para #129 |
|---|---|
| No hay tabla ni campo de asociación con procedencia | B necesita un sitio: se propone `metadata.asociaciones` (sin migración). |
| `metadata_source` es univaluada | No puede representar varias fuentes; no se toca (§3-D3). |
| La procedencia agrupa la identidad en una fila y no pinta ids | B necesita un delta pequeño en #127 para que la procedencia sea visible (§5.2). |
| #128 no clasifica los estados de #133: solo distingue «fuente apagada» y «sin coincidencia»; un `CortesiaEnEspera` de un cliente **no se captura** en `services/enriquecimiento_plan.py:254-272` y acabaría en el manejador global de error | A **no debe copiar ese camino**: reutiliza el clasificador de #133 que ya usa Descubrir (§4.1). |
| `DiscoveryResult` no expone `kind` de Tebeosfera (`collection`/`saga`), que el cliente sí trae (`services/tebeosfera.py:116-127`) | Delta mínimo para no asociar una serie a una **saga** (§4.1, D-A1). |
| La búsqueda de GCD filtra ediciones no españolas (`services/discovery.py:497-501`) y su ritmo es 2,0 s con un límite de 30 peticiones/hora del servidor | A consulta **una vez** y no pagina (§4.1). |

---

## 2. Reconciliación con las historias vecinas

| Historia | Qué se reutiliza tal cual | Qué **no** se duplica | Qué falta o se declara |
|---|---|---|---|
| **#109** (contrato compartido) | Los siete puntos: valor actual, origen conocido/desconocido, protección, propuesta, identidad del plan, resultado con motivos y **«asociar no fusiona, no enriquece, no toca archivos ni elimina protecciones»** (#109 §Contrato, punto 7). | No se crea un segundo modelo de procedencia: A/B usan el mismo patrón «lo que se vio, firmado» de #128. | El punto 4 («la aplicación consume el mismo plan, no una consulta nueva») es exactamente el contrato de A→B (§4). |
| **#124 / ADR 0003** | Vocabulario: **serie** es la unidad catalogada; **edición** y **obra** no existen; el id externo identifica *dentro de su fuente*. | No se crea entidad de edición ni de obra, ni `work_id`, ni migración (#181 pospuso #184). | La asociación se declara a nivel de **serie** y con `entidad: "serie"` en la procedencia. |
| **#182** (discriminantes) | Título y año **no** son identidad; una candidata única **sigue requiriendo elección explícita**; homónimas no se autoseleccionan; lo ausente se muestra «no consta»; ambigüedad → camino manual (§4-§6 del documento). | No se inventan idioma, país, edición ni identificador de obra. | A muestra **solo** los discriminantes que el cliente ya devuelve; los que no constan se dicen. |
| **#133** (estados por capacidad) | El conjunto cerrado de estados (`services/estados_fuentes.py:12-31`) y su clasificación por fuente **y capacidad**; `fuente_apagada` y `configuracion_incompleta` **sin tráfico**. | No se añade un estado nuevo ni se reinterpreta un fallo como ausencia. | A expone el estado de **su** consulta; no reutiliza el estado de otra capacidad. |
| **#134** (cortesía compartida) | Toda petición pasa por la cola compartida por fuente/host (`utils/cortesia.py`); Tebeosfera 2,5 s; CV 1,0 s; AniList 1,5 s; GCD 2,0 s (`config.py:44,72,82,90`; `utils/cortesia.py:117-123`). | No se añade cliente, reintento propio ni consulta masiva. | A hace **una** petición de búsqueda por acción; no pagina ni pide detalle. GCD: 30 peticiones/hora del servidor (medido en `docs/design/benchmark-modelo-cv-gcd.md` §0; no se ha vuelto a medir aquí). |
| **#111** (feature padre de #133/#134) | El marco: capacidad soportada/no soportada/desconocida y configuración completa/incompleta. | No se declara una capacidad nueva: #129 usa **búsqueda**, la única verificada por #133. | — |
| **#128** (plan por campo) | Token firmado, huella, caducidad, «no se vuelve a consultar la fuente al aplicar», identidad que no se sustituye, resultado por campo. | No se duplica el plan de enriquecimiento: A/B no aplican metadatos ni crean un segundo plan por campo. | **Asociar no cambia qué fuente enriquece**: el enricher y #128 siguen eligiendo por tradición (`services/enricher.py:269-278`). La asociación es identidad, no enriquecimiento; se declara como límite, no se promete lo contrario. |
| **#127** (procedencia visible) | El bloque «De dónde sale cada dato», sus reglas y sus pruebas (`docs/design/procedencia-127.md`). | No se crea otro panel de procedencia: se **extiende** el lector para la identidad (§5.2, D-B1). | Hoy la identidad es una fila agrupada; con varias fuentes hay que decir cuántas y desde cuándo sin pintar ids. |
| **#125 / #183** (elegir publicación) | Nada directamente: es otra entidad (`Issue`) y otra capacidad (detalle). | No se mezcla la elección de **publicación** con la asociación de **serie**. | Queda fuera; si se necesita, es otra historia con su propio contrato. |

---

## 3. Hoja de decisiones

Cada decisión lleva **lo que hay**, **opciones**, **recomendación**, **alternativa** y **coste**.
Recomendar no es decidir: la casilla la marca el PO.

### D1 · Tipo de entidad que se asocia

| | |
|---|---|
| **Pregunta** | ¿Qué entidad local se asocia a la fuente: serie, publicación/número, edición u obra? |
| **Lo que hay** | `Series` tiene las cuatro columnas de identidad; `Issue` solo `comic_vine_id`; **no existen** `editions`, `edition_id` ni entidad de obra (`docs/adr/0003-identidad-editorial.md`; `docs/design/discriminantes-publicacion.md` §3). |
| **Opciones** | (a) `Series`; (b) `Series` y, aparte, `Issue` para Comic Vine; (c) esperar a la edición de #184. |
| **Recomendación** | **(a) `Series`**, con `entidad: "serie"` firmado y guardado. Es la única entidad con identidad externa de varias fuentes y la única que el coleccionista cataloga (ADR 0003). |
| **Alternativa** | (b) admitir `Issue` solo con Comic Vine en un corte posterior: hoy no hay capacidad de número verificada (#133 solo acredita `busqueda`) ni id de número en AniList/Tebeosfera/GCD; haría falta otro contrato y otra UI. |
| **Coste** | Ninguno extra: B es un `UPDATE` de una columna de `Series`. |
| **Evidencia** | `models:410-421` y `:489`; `docs/design/discriminantes-publicacion.md` §3-§4.1; `docs/adr/0003-identidad-editorial.md` («Edición: no existe»). |

### D2 · Cardinalidad y ámbito

| | |
|---|---|
| **Pregunta** | ¿Cuántas asociaciones por fuente y por entidad se permiten? ¿Qué pasa ante conflicto? |
| **Lo que hay** | Una columna única por fuente: como máximo **un valor por fuente y serie**; varias columnas pueden estar llenas a la vez (no hay `CHECK`), pero hoy nada las usa en conjunto. `metadata_source` es univaluada. El único por columna impide que el mismo id esté en dos series. |
| **Opciones** | (a) máximo **una por (serie, fuente)**, varias fuentes por serie (hasta 4); (b) una sola fuente por serie (lo que hace el enricher); (c) varias asociaciones por fuente (varias colecciones Tebeosfera, por ejemplo). |
| **Recomendación** | **(a)**. Es lo que el modelo ya impone y lo que el coleccionista espera de «esta serie también está en GCD». Conflicto: si el id ya pertenece a **otra** serie, se **rechaza** con explicación y no se reasigna (criterio 8); si la serie ya tiene **otro** id de **esa misma** fuente, se rechaza como «sustituir» y se remite a retirar (D4). |
| **Alternativa** | (b) contradice el propósito de la historia; (c) exige tabla nueva + migración y no hay evidencia en el censo (#181: 0 colisiones, 0 ediciones paralelas). |
| **Coste** | (a) 0 migración. (c) migración + modelo + UI + pruebas. |
| **Evidencia** | `models:410-421`; `services/enricher.py:190-202`; `docs/design/censo-identidad-real.md` §«Métricas» (0 colisiones, 0 recopilaciones). |

### D3 · Procedencia conservada y semántica de «confirmada manualmente»

| | |
|---|---|
| **Pregunta** | ¿Dónde se guarda que la asociación la confirmó una persona, sin inventar usuarios ni auditoría? ¿Se pone `metadata_source = 'manual'`? |
| **Lo que hay** | `metadata_source` es **univaluada** y significa «fuente del alta o del enriquecimiento»; `manual` es un **bloqueo total** del enriquecimiento (`services/enricher.py:202`; `services/enriquecimiento_plan.py:347-348`). La procedencia del alta vive en `Series.metadata_["alta"]` con fuente, id, fecha y `operacion_id` (`services/alta_serie.py:500-509`). `metadata.vinculo` y `vinculo_historial` son el precedente de procedencia por operación en JSONB (`services/vinculacion.py:380-399`; `services/desvinculacion.py:194-229`). |
| **Opciones** | (a) no tocar `metadata_source` y anotar la asociación en `Series.metadata_["asociaciones"]`; (b) poner `metadata_source = 'manual'`; (c) poner `metadata_source = <fuente asociada>`. |
| **Recomendación** | **(a)**. Entrada versionada por fuente: `{version, fuente, id_externo, entidad:"serie", fecha, operacion_id, origen:"confirmada"}`. `metadata_source` se queda como está (puede ser `NULL` o de otra fuente) y **no se toca `locked_fields`**. Se fusiona con `fusionar_metadata` sin pisar `alta`. **Sin usuario, sin sesión, sin IP: no es auditoría, es procedencia y comprobante.** |
| **Alternativa** | (b) y (c) se descartan: `manual` convertiría la serie en «no enriquecible para siempre» por una asociación que no aporta metadatos, y (c) atribuiría sinopsis/portada/total a una fuente que no los escribió y solo cabe una. |
| **Coste** | (a) 0 migración; un delta en el lector de #127 para que la identidad muestre «Asociado con X el …» (D-B1). |
| **Evidencia** | `models:424`; `services/enricher.py:286-297`; `services/procedencia.py:146-163`; `services/alta_serie.py:212-218`. |

### D4 · Corrección de una asociación equivocada

| | |
|---|---|
| **Pregunta** | ¿Cómo se corrige: sustituir de golpe, retirar y volver a asociar, o no se corrige? |
| **Lo que hay** | Desvincular un archivo **no borra**: quita la clave y añade el comprobante a `metadata.vinculo_historial` (`services/desvinculacion.py:194-229`). Retirar una serie conserva números, archivos e historial (`services/retirada_serie.py:1-15`). **No hay** edición de identificadores externos (`services/edicion_serie.py:28`). |
| **Opciones** | (a) **retirar** explícito + historial, y «sustituir» = retirar + asociar (dos confirmaciones); (b) formulario que sobrescribe el id en un paso; (c) no corregir (solo SQL). |
| **Recomendación** | **(a)**. `retirar` vale para **cualquier** asociación, conste o no su procedencia (si no consta, se dice «procedencia desconocida», como D9 de BL-R1a). Quita solo el id de **esa** fuente, no toca las demás, no borra la serie, no toca archivos, no aplica metadatos y añade a `metadata_["asociaciones_historial"]` una entrada con `deshecho:{operacion_id, fecha}` y `previo`. |
| **Alternativa** | (b) es sustitución silenciosa y contradice #109 punto 3 y el criterio 10; (c) deja los errores sin arreglo y obliga a SQL. |
| **Coste** | Corte C, S/2. Sin él, B debería rechazar toda sustitución y los errores quedarían congelados: **B y C se entregan juntos** (§5). |
| **Evidencia** | `services/desvinculacion.py:194-229`; `docs/design/bl-r1-deshacer-vinculacion.md` §3 y D9; `services/retirada_serie.py:410-415`. |

### D5 · Vigencia de la propuesta, idempotencia y reintento

| | |
|---|---|
| **Pregunta** | ¿Qué invalida una propuesta? ¿Cómo se evita duplicar al repetir? ¿Sirve `updated_at`? ¿Qué se hace si se pierde la respuesta? |
| **Lo que hay** | Token HMAC con propósito, contexto y TTL de 15 min (`services/tokens_revision.py:90-125`, `:30`). Huella de lo que se vio en #128 (`services/enriquecimiento_plan.py:138-158`) y en retirada (`services/retirada_serie.py:285-310`). Comprobante inmutable con `operacion_id` y candado consultivo (`services/vinculacion.py:222-260`). `Series.updated_at` tiene `onupdate=func.now()` (`models:440-441`). |
| **Opciones** | (a) token `asociar_fuente` con huella explícita + `operacion_id` + comprobante en `vinculacion_operaciones`; (b) nueva tabla `asociacion_operaciones` con migración; (c) usar `updated_at` como testigo de vigencia. |
| **Recomendación** | **(a)**. La propuesta caduca a los 15 min y se invalida si cambia **la huella**: título, año, tradición, los cuatro ids, `metadata_source`, `locked_fields` y `metadata.asociaciones` de la serie, más la identidad firmada de la candidata. B revalida dentro de la transacción, con candado consultivo por `operacion_id` y `SELECT … FOR UPDATE` de la serie. Repetir el mismo token devuelve el mismo comprobante (`repetida: true`) sin escribir. `updated_at` **no** se usa: cambia con cualquier edición (y con la propia escritura de B) y no distingue qué cambió. |
| **Alternativa** | (b) es más explícita pero añade tabla, migración, purga y superficie; (c) se descarta por lo anterior. |
| **Coste** | (a) 0 migración: se reutiliza el almacén inmutable que ya usa la retirada (tipo nuevo, purgado solo por su tipo y excluido del recuento de vinculaciones en `/api/operaciones`). |
| **Evidencia** | `services/enriquecimiento_plan.py:406-410` (rechazo por huella); `services/retirada_serie.py:340-390`; `models:729-748`; `alembic/versions/20261009_0019_vinculacion_operaciones.py:49-59`. |

### D6 · Cómo se contrasta el SHA

| | |
|---|---|
| **Pregunta** | ¿Sobre qué código se afirman las cosas y cómo se puede reproducir? |
| **Recomendación** | Fijar **`04ab6eea58e0deb98d1f12f6fb7d9d69e4f3f7ad`** (`git rev-parse origin/main` el 2026-11-09). Cada afirmación de este documento lleva `fichero:línea` de ese árbol. El contraste es **lectura**: `git grep -n`, `git show`, lectura de ficheros y de las migraciones; **no** se ejecutaron pruebas, ni se consultaron fuentes, ni se arrancó la app. |
| **Alternativa** | Contrastar en el HEAD de la rama de trabajo o en `main` «de hoy»: se invalida en cuanto entra cualquier PR y las líneas dejan de cuadrar. |
| **Coste** | Nulo; si `main` avanza antes de implementar, **re-ejecutar las citas** (los números de línea cambian aunque el código sea el mismo). |
| **Evidencia** | §6 de este documento (comandos y salida). |

### Resumen de las seis decisiones

| # | Decisión | Recomendación en una línea |
|---|---|---|
| D1 | Tipo de entidad | **Serie** (`Series`), no número ni edición/obra. |
| D2 | Cardinalidad | **Una por (serie, fuente)**, varias fuentes por serie; conflicto = rechazo explícito. |
| D3 | Procedencia | **No** tocar `metadata_source` ni `locked_fields`; `metadata.asociaciones` versionado con fecha y `operacion_id`. |
| D4 | Corrección | **Retirar explícito con historial**; sustituir = retirar + asociar. |
| D5 | Vigencia e idempotencia | Token con **huella + `operacion_id` + comprobante** en `vinculacion_operaciones`; `updated_at` no decide. |
| D6 | Contraste | SHA completo **`04ab6ee…f7ad`** y citas `fichero:línea`; lectura, no ejecución. |

---

## 4. Contrato de las entregas A y B

### 4.0 Piezas nuevas (propuesta)

| Pieza | Tipo | Nota |
|---|---|---|
| `services/asociar_fuente.py` | nuevo | `PropuestaDeAsociacion` (A, solo lectura + token) y `AsociacionDeFuente` (B, persistencia). |
| `services/tokens_revision.py` | ampliación | `PROPOSITO_ASOCIAR = "asociar_fuente"`, `AsociacionFirmada`, `crear_token_asociacion`, `verificar_token_asociacion`, `MAX_TOKEN_ASOCIACION` (cota calculada como las demás). |
| `services/discovery.py` | ampliación mínima | `buscar_en(fuente, query, limit)`: **una** fuente, misma clasificación de #133 que `search_detallada`, sin duplicar la lógica (extraer el clasificador a un ayudante compartido). |
| `DiscoveryResult` | campo aditivo | `kind: str \| None`, relleno desde Tebeosfera (`collection`/`saga`); el resto, `None`. |
| `services/procedencia.py` | ampliación | Leer `metadata.asociaciones` para la fila de identidad (D-B1). |
| `web/asociar_fuente.py` + plantillas | nuevo | Rutas y UI; se registra en `main.py` como retirada (`main.py:369-414`). |
| `models.Series.metadata_` | sin cambio de esquema | JSONB ya existe; **cero migraciones**. |
| `services/vinculacion_operaciones` | reutilización | `resultado.tipo = "asociar_fuente"`; la purga filtra por tipo. |

### 4.1 Entrega A · Proponer y comparar correspondencias

**Qué es.** Dada una serie local, consultar **una** fuente autorizada y devolver candidatas con sus
discriminantes, más una **propuesta firmada** por candidata. No escribe en la base, no aplica
metadatos y no modifica archivos ni catálogo.

**Entradas**

| Entrada | Tipo | Regla |
|---|---|---|
| `series_id` | UUID (ruta) | Debe existir; si no, 404. |
| `fuente` | `comic_vine` \| `anilist` \| `tebeosfera` \| `gcd` | Obligatoria y explícita; **sin valor por defecto** (misma regla que la tradición del alta). |
| `q` | texto opcional | Por defecto, `Series.title`; no se inventa una consulta a partir de sinopsis ni de ids. |
| `limit` | fijo ≤ 10 | No se pagina ni se piden detalles (evita multiplicar cortesía). |

**Salidas (vista, no JSON de API)**

| Salida | Contenido |
|---|---|
| `estado` | `EstadoFuente` del conjunto cerrado de #133, con `fuente`, `capacidad="busqueda"`, `motivo` en español y `reintentar_en` solo si consta. |
| `candidatas[]` | `titulo`, `anio`, `id_externo`, `sitio_url`, `tradicion` + `procedencia_tradicion` (si consta), `kind` (Tebeosfera), y **solo** los discriminantes que el cliente devuelve. Lo ausente se marca «no consta». |
| `conflicto` | Si el `id_externo` ya pertenece a **otra** serie local: se muestra la candidata como **no asociable** y con el título de la serie que lo tiene. Se detecta con una consulta local, sin escribir. |
| `propuesta` | Un **token firmado por candidata** (`asociar_fuente`, contexto `series_id`, TTL 15 min) con: huella de la serie, fuente, id externo, título/año vistos, `sitio_url` y `operacion_id` (UUID). Sin token no hay confirmación posible. |
| `avisos` | Texto llano: fuente apagada, falta de clave, cortesía, «solo se han encontrado sagas, no colecciones», etc. |

**Efectos:** **ninguno** sobre la base. Una sola petición HTTP a la fuente elegida.

**Reglas de la consulta (criterio 1 y 4 de la historia)**

1. Si la fuente está **apagada** en Ajustes → `fuente_apagada`, **sin instanciar el cliente**.
2. Si es Comic Vine y no hay clave → `configuracion_incompleta`, **sin tráfico**.
3. `CortesiaEnEspera` → `limite_de_cortesia` (con espera solo si el contrato la da);
   `ReintentosAgotados` con 429 → `limite_de_cortesia`; otra excepción → `fallo_transitorio`;
   lista vacía → `sin_resultados`; lista con elementos → `ok`.
4. **Nunca** se consulta otra fuente «por si acaso»: la persona eligió una.
5. Tebeosfera: los resultados `saga` **no** son candidatas (una saga es nivel obra, no colección); si
   **todas** lo son, el estado es `sin_resultados` con el motivo «solo hay fichas de saga».
6. GCD: se mantiene el filtro de edición española que ya aplica Descubrir
   (`services/discovery.py:497-501`); la consulta no pagina.
7. No se muestran portadas de candidatas: exigirían proxy y otra fuente de tráfico; no hacen falta
   para comparar identidad y #129 no las pide.

**Segunda ruta de A (previsualizar la propuesta):** recibe el token de **una** candidata, lo verifica
(firma, propósito, contexto, caducidad) y vuelve a leer la serie. Si la huella no coincide →
`propuesta_desactualizada`, sin propuesta. Si hay conflicto local → se explica y no se ofrece
confirmar. **No escribe.**

### 4.2 Entrega B · Confirmar la asociación

> **v1.1:** este apartado queda como histórico; el contrato vigente de B está en §8.2-§8.5 y §8.12.
> Donde contradiga (token, idempotencia caducada, purga, columna/JSONB, enricher), manda §8.

**Qué es.** Consumir el **mismo token** que se vio y guardar la correspondencia con procedencia, sin
fusionar, sin enriquecer y sin tocar archivos ni `locked_fields`.

**Entrada:** `token` (único dato del formulario; `Form(..., min_length=1, max_length=MAX_TOKEN_ASOCIACION)`).
El `series_id` de la URL debe coincidir con el contexto firmado.

**Transacción (una sola, sin ficheros):**

1. Candado consultivo por `operacion_id`.
2. Comprobante previo en `vinculacion_operaciones` con
   `resultado.tipo == "asociar_fuente"` → devolver **lo mismo** con `repetida: true`
   (cero escrituras).
3. Si el comprobante ya se purgó, pero `metadata.asociaciones` tiene una entrada con **este**
   `operacion_id`, la operación se aplicó: devolver `asociada` con `repetida: true` (cero
   escrituras). La entrada es el testigo durable; el comprobante solo vive 24 h.
4. `SELECT … FOR UPDATE` de la serie; si no existe → `serie_inexistente` (sin escritura).
5. Recalcular la huella y comparar → si difiere, `propuesta_desactualizada` (sin escritura).
6. Comprobar el id: si ya está en **otra** serie → `conflicto_identificador` (sin escritura); si la
   serie ya tiene **otro** id en **esa misma** fuente → `ya_tiene_identidad_en_esa_fuente` (sin
   escritura, remite a retirar); si ya tiene **el mismo** id → `ya_asociada` **sin escribir** (no se
   inventa una procedencia nueva: ya constaba).
7. `UPDATE series` solo de: la columna de esa fuente, `metadata` (fusión con `asociaciones`) y, por
   `onupdate`, `updated_at`. **Nada más.** Si el índice único salta por una carrera, `IntegrityError`
   se traduce al **mismo** `conflicto_identificador` y se revierte: no hay asociación parcial.
8. `INSERT` del comprobante inmutable, en la misma transacción.
9. `commit` **al final**; si falla después de pedirlo → `resultado_incierto` (503), nunca «no se ha
   cambiado nada».

**Salidas**

| Salida | Valores |
|---|---|
| `resultado` | `asociada` \| `ya_asociada` \| `omitida` |
| `motivo` | `null` o el código del bloqueo (`conflicto_identificador`, `ya_tiene_identidad_en_esa_fuente`, `propuesta_desactualizada`, `serie_inexistente`) |
| `repetida` | `true` si se devolvió un comprobante ya guardado |
| `fuente`, `id_externo`, `fecha`, `operacion_id` | lo confirmado |
| `efectos` | `{campos_serie: 1, entradas_procedencia: 1, comprobantes: 1, numeros: 0, archivos: 0, metadatos_aplicados: 0}` |

**Efectos exactos (cuando escribe):** `series.<campo_id>` = id;
`series.metadata_["asociaciones"]` con la entrada; `vinculacion_operaciones` con el informe. **Cero**
en `issues`, `files`, `metadata_source`, `locked_fields`, `enrichment_attempted_at` y cualquier otra
tabla. Un `ya_asociada` por identidad ya presente **no escribe nada**.

**Formato de la procedencia (sin migración):**

```json
"asociaciones": [
  {
    "version": 1,
    "fuente": "gcd",
    "id_externo": "1234567",
    "entidad": "serie",
    "fecha": "2026-11-09T10:00:00+00:00",
    "operacion_id": "0f0c…",
    "origen": "confirmada"
  }
]
```

Una entrada por fuente como máximo. Al retirar, la entrada pasa a
`metadata_["asociaciones_historial"]` con `deshecho:{operacion_id, fecha}` y `previo` (el id), igual
que `vinculo_historial` (`services/desvinculacion.py:194-229`). La fusión usa `fusionar_metadata` y
**no toca `alta`**.

**Comprobante (mismo almacén que retirada):**

```json
{
  "version": 1, "tipo": "asociar_fuente", "accion": "asociar",
  "operacion_id": "0f0c…", "series_id": "…", "fuente": "gcd",
  "id_externo": "1234567", "resultado": "asociada", "motivo": null,
  "fecha": "2026-11-09T10:00:00+00:00"
}
```

Sin título, sin ruta, sin usuario, sin sesión, sin token. Se purga a las 24 h **y** con el token
caducado, solo las filas de este `tipo`; la entrada de `metadata.asociaciones` es **permanente** y
sirve para releer el resultado incluso después de la purga.

### 4.3 Ejemplos obligatorios de la entrega A

| Caso | Entrada | Salida A | Efecto |
|---|---|---|---|
| **Candidata única** | Serie con `comic_vine_id`; fuente `gcd`; la búsqueda devuelve **una** ficha | Una candidata con título, año, id y `sitio_url`; aviso «una sola candidata: compruébala antes de asociarla»; **token** de esa candidata | Ninguno. **No** se asocia sola: la elección es explícita (#182 §5). |
| **Homónimas** | Dos fichas GCD con el mismo título y año, sin editorial ni país que las distinga | Dos candidatas con **los mismos** discriminantes y aviso de ambigüedad; ninguna preseleccionada; sin recomendación | Ninguno. Si no se pueden distinguir, la persona no continúa o usa el camino manual; el sistema **no** elige. |
| **Conflicto de identificador** | La candidata tiene un id que **ya** está en otra serie local | La candidata se muestra **bloqueada** con «ya está asociada a “<título>”»; **no se emite token** para ella | Ninguno. No se reasigna ni se oculta la serie que lo tiene. |
| **Propuesta desactualizada** | Se busca, y antes de previsualizar se edita el título/año de la serie o se asocia otra fuente | `propuesta_desactualizada`: «la ficha cambió; vuelve a buscar»; sin propuesta ni token nuevo | Ninguno. La huella firmada es la que lo detecta. |
| **Repetición** | Se repite la búsqueda, o se previsualiza dos veces el mismo token | Misma lista (nueva consulta) y misma previsualización determinista; tokens nuevos con su propio `operacion_id` | Ninguno. A no escribe, así que repetir no duplica nada. |
| **Resultado desconocido** | La fuente no responde o se agota el tiempo | `fallo_transitorio` (o `limite_de_cortesia`); sin candidatas y **sin token**; mensaje que distingue el fallo de «no existe» | Ninguno. No hay escritura que reconciliar; se repite la búsqueda. |

### 4.4 Ejemplos obligatorios de la entrega B

| Caso | Entrada | Salida B | Efecto |
|---|---|---|---|
| **Candidata única** | Token válido de la única candidata | `asociada`, `repetida:false`, `efectos` con 1 campo + 1 entrada + 1 comprobante | `series.gcd_id` y `metadata.asociaciones`; nada más. |
| **Homónimas** | Token válido de **una** de las homónimas | `asociada` de **esa** candidata; el resultado no dice «equivalencia», dice «asociada a esta ficha» | Se guarda la elegida; la otra no se toca ni se fusiona. |
| **Conflicto de identificador** | Ese id ya está en otra serie (carrera o propuesta antigua) | `omitida` · `conflicto_identificador`: página de fallo (mismo patrón que retirada, sin éxito), con el título de la otra serie; **sin comprobante** | Ninguno. Nunca se reasigna en silencio. |
| **Propuesta desactualizada** | La serie cambió desde la vista (título, año, ids, `locked_fields` o `asociaciones`) | `omitida` · `propuesta_desactualizada`; «vuelve a revisarla»; **sin comprobante** | Ninguno. |
| **Repetición** | El **mismo** token, dos veces (o dos envíos simultáneos) | Segunda: `asociada`, `repetida:true`, mismo `operacion_id` y mismo informe; el candado serializa | Cero escrituras la segunda vez. |
| **Resultado desconocido** | Se pidió `commit` y se perdió la respuesta | 503 `resultado_incierto`; botón «Comprobar el resultado» que relee por `operacion_id` (comprobante o entrada de procedencia) | Si se aplicó, se muestra; si no, se puede repetir el mismo token sin duplicar. **Nunca se anuncia éxito sin leer.** |

### 4.5 Catálogo de resultados y mensajes (español llano, sin jerga)

| Código | Cuándo | Texto propuesto |
|---|---|---|
| `fuente_apagada` | Ajustes la tiene desactivada | «<Fuente> está desactivada en Ajustes. Enciéndela si quieres consultarla.» |
| `configuracion_incompleta` | CV sin clave | «Comic Vine no está configurada: falta su clave en Ajustes.» |
| `limite_de_cortesia` | 429 o espera que no cabe | «La fuente ha pedido esperar un poco. Vuelve a intentarlo en un momento.» (+ «en N s» si consta) |
| `fallo_transitorio` | red/HTTP/parseo | «No se ha podido consultar la fuente ahora mismo. No es que no exista: vuelve a intentarlo.» |
| `sin_resultados` | respondió y no hay | «La fuente no tiene ninguna ficha con ese título.» / «Solo hay fichas de saga, no colecciones.» |
| `propuesta_desactualizada` | huella distinta | «La ficha ha cambiado desde que viste la propuesta. Vuelve a revisarla antes de asociarla.» |
| `conflicto_identificador` | id en otra serie | «Esa ficha ya está asociada a “<serie>”. No se ha cambiado nada.» |
| `ya_tiene_identidad_en_esa_fuente` | misma fuente, otro id | «Esta serie ya tiene otra ficha de esa fuente. Retírala primero si quieres cambiarla.» |
| `token_caducado` | >15 min sin comprobante | «Esta propuesta ha caducado y no se conserva el resultado. Vuelve a revisarla.» |
| `resultado_incierto` | commit sin respuesta | «No sabemos si se ha guardado. Pulsa “Comprobar el resultado” antes de repetir.» |
| `conflicto_de_bloqueo` | interbloqueo | «Otra operación coincidió. No se ha cambiado nada: repite la confirmación.» |

Regla de superficie: no aparecen «token», «operación», «id externo» ni códigos internos
(`CLAUDE.md` §6, U20); el id se muestra solo si la persona lo necesita para comparar, y entonces como
dato de la fuente, no como identificador interno.

### 4.6 Qué **no** hace B (criterios 10 y límites de la historia)

- No fusiona series ni crea una «serie única» con dos fichas.
- No aplica sinopsis, portada, total, créditos ni ningún campo de metadatos.
- No modifica `metadata_source`, `locked_fields` ni `enrichment_attempted_at`.
- No crea, edita ni borra `Issue`, `File`, `Wishlist`, `ReadingProgress`, `StoryArcIssue` ni alias.
- No mueve, renombra, lee ni hashea archivos; no toca el disco.
- No activa el enriquecimiento ni cambia la fuente que enriquece (sigue mandando la tradición).
- No borra ni reasigna la asociación de otra fuente.
- No hace auditoría: no guarda usuario, sesión, IP ni historial de personas.

### 4.7 Criterios de aceptación de #129 → dónde se cumplen

| # | Criterio (resumen) | Dónde |
|---|---|---|
| 1 | Solo una capacidad disponible y autorizada; fuente apagada o mal configurada no se consulta | §4.1 reglas 1-4 (sin cliente y sin tráfico); estado de #133 |
| 2 | Un título parecido se presenta como candidata, no como equivalencia | §4.1 salidas + ejemplos «candidata única» y «homónimas» |
| 3 | Datos acreditados y desconocidos como tales; sin discriminantes inventados | §4.1: solo los campos que el cliente devuelve; «no consta» |
| 4 | Cero candidatas, error, configuración incompleta o fuente apagada se distinguen | §4.1 reglas 3-6 y catálogo §4.5 (`sin_resultados` ≠ `fallo_transitorio` ≠ `fuente_apagada`) |
| 5 | La comparación no guarda, no aplica metadatos, no modifica archivos ni catálogo | §4.1 «Efectos: ninguno»; A no abre transacción de escritura |
| 6 | La confirmación identifica entidad, fuente, id externo y tipo de entidad | Token y entrada de procedencia (`entidad: "serie"`, `fuente`, `id_externo`); no se asocia por título/año |
| 7 | Una asociación existente no se duplica al repetir | §4.2 pasos 2-3 (comprobante o entrada con el mismo `operacion_id`), ejemplo «repetición» |
| 8 | Un id ya asociado a otra entidad se informa y no se reasigna | §4.2 paso 6 (`conflicto_identificador`), ejemplo «conflicto» |
| 9 | Si cambia la entidad o la propuesta, se pide revisar de nuevo | §4.2 paso 5 (huella), ejemplo «propuesta desactualizada» |
| 10 | Conserva procedencia y alcance editorial; no fusiona, enriquece ni elimina protecciones | §4.2 efectos + §4.6 (lista de lo que no hace) |
| 11 | Resultado perdido o desconocido: no se anuncia éxito sin consultar; el reintento no duplica | §4.2 paso 9 (503 + releer por `operacion_id`), ejemplo «resultado desconocido» |

---

## 5. Cortes, estimación y DoR

### 5.1 Cortes propuestos

> **v1.1:** el corte vigente es el de §8.13 (PR-S1 delta de A, PR-B, PR-C); el de esta sección queda
> como histórico y se actualiza allí.

| Corte | Contenido | Estimación | ¿Migración? | ¿UI? | Por qué en este orden |
|---|---|---|---|---|---|
| **1 · A** | `services/asociar_fuente.py` (propuesta), `buscar_en` de una fuente con #133, campo `kind`, token `asociar_fuente`, rutas `/buscar` y `/previsualizar`, plantilla de comparación, pruebas con fuentes simuladas | **M (5)** | **No** | Sí | Es el valor visible y no escribe: se puede revisar sin riesgo. Sin A no hay token que B consuma. |
| **2 · B + visibilidad** | `AsociacionDeFuente.confirmar`, transacción, conflicto, idempotencia, comprobante reutilizado, delta de `procedencia.py` y de la ficha, pruebas con PostgreSQL real | **M (5)** | **No** | Sí (confirmar + resultado) | Consume el token de A. Incluye la procedencia visible para que el criterio 10 no sea invisible. |
| **3 · C (corrección)** | Retirar una asociación con historial, ruta y plantilla, pruebas | **S (2)** | **No** | Sí | Sin C, un error de B no se puede arreglar; **se entrega junto con B** (mismo release), no «algún día». |

**Total: 12 puntos propuestos** (el antecedente era 13/XL). Es la **suma de cortes de #129**, no del
árbol de #109. Ningún corte pasa de M. Estimación **sin calibrar** (no hay implementación todavía) y
sujeta a la revisión de quien implemente.

**Qué es migración:** nada. Se reutiliza `vinculacion_operaciones` (0019) con un `tipo` nuevo y
`Series.metadata_` (JSONB ya existente). **Si el PO prefiere una tabla propia** `asociacion_operaciones`,
eso sí sería migración (0023) y subiría B a L/8.

**Qué requiere UI:** A (lista de candidatas + comparación), B (confirmación + resultado/«comprobar»),
C (retirar). Presupuesto de texto de U21: una frase de entrada ≤20 palabras, ≤50 palabras antes de la
primera acción, garantía junto a la acción, sin diálogos nativos; la comparación va en tabla y lo
secundario en `<details>`.

### 5.2 Deltas pequeños sobre piezas existentes (no son corte aparte)

| Delta | Dónde | Por qué |
|---|---|---|
| **D-A1** `DiscoveryResult.kind` aditivo | `services/discovery.py:142-175`, `_search_tebeosfera` `:477-492` | Sin él, A no puede excluir «sagas» y asociaría una serie a una ficha de obra. |
| **D-A2** `buscar_en(fuente, …)` con el clasificador de #133 compartido | `services/discovery.py:351-430` | Reutilizar sin duplicar la lógica de estados; #128 no lo hace y un `CortesiaEnEspera` se le escapa. |
| **D-B1** `procedencia.py` lee `metadata.asociaciones` | `services/procedencia.py:107-112`, `:146-163` | Que «De dónde sale cada dato» no diga «origen no registrado» cuando la asociación sí consta. Se mantiene la fila única y **no se pintan ids**. |
| **D-B2** ajuste de la prueba de #127 | `tests/test_procedencia_serie.py` | La fila de identidad cambia de texto/origen; la prueba debe fijar el caso nuevo. |

### 5.3 Lo que falta para DoR

- [ ] **PO decide D1-D5** (D6 es el método de contraste; este documento recomienda, no decide).
- [ ] **Benchmark de referencia** (`CLAUDE.md` §13): cómo modelan Sonarr/Radarr/Kapowarr varios
      identificadores por entidad y qué hacen ante conflicto. **NOT RUN**; no se puede declarar Ready
      sin esa ficha, aunque la decisión de fondo (columnas paralelas) ya está en `CLAUDE.md` §12.
- [ ] **B y C en el mismo release**: sin corrección, la asociación equivocada es permanente.
- [ ] **Presupuesto de UI** aprobado (textos, tabla de comparación, sin portadas, sin diálogos
      nativos) y revisión de que no se muestran ids en la ficha (#127).
- [ ] **Re-revisión individual favorable** y estimación calibrada por quien implementará.
- [ ] **SHA congelado al empezar**: si `main` avanzó, re-ejecutar las citas de §6.
- [ ] **Decidir el delta D-A1** (campo `kind`) y si B incluye la visibilidad (D-B1/D-B2) o va después.
- [ ] **Decidir el destino en `/api/operaciones`**: hoy el inventario filtra las filas con `tipo`
      (`services/operaciones.py:126-128`) y **no** contará las asociaciones; si el PO las quiere ver,
      es un corte aparte.

---

## 6. Contraste en el SHA (método y evidencia)

**SHA completo:** `04ab6eea58e0deb98d1f12f6fb7d9d69e4f3f7ad` (`git rev-parse origin/main`,
2026-11-09; último commit `04ab6ee Merge pull request #533 from juanajok/docs/piloto-es007`).

Comandos de contraste (todos de lectura):

```bash
git -C /mnt/Datos/Documentos/Repos/zascarr rev-parse origin/main
git -C .squad/wt-129 grep -n "comic_vine_id\|anilist_id\|tebeosfera_slug\|gcd_id" src/zascarr/models
git -C .squad/wt-129 grep -n "metadata_source\|locked_fields" src/zascarr/services
git -C .squad/wt-129 grep -n "asociar\|asociación" src/zascarr
git -C .squad/wt-129 grep -n "@router\." src/zascarr/web src/zascarr/api
```

**Rutas inventariadas (ninguna es «asociar fuente»):** ficha y enriquecimiento
(`web/series.py:341,375,395`), descubrir/alta (`web/discovery.py:98-363`), vincular/desvincular
(`api/revision.py:331-476`), retirar (`web/retirada_serie.py:111,129`), operaciones
(`api/operaciones.py:13`).

**Pruebas reutilizables (leídas, no ejecutadas):**
`tests/test_enriquecimiento_plan.py` (plan, huella, token manipulado, plan desactualizado),
`tests/test_tokens_alta.py` y `tests/test_tokens_vinculacion.py` (cotas y propósitos),
`tests/test_vinculacion_pg.py` / `test_vinculacion_resultado_pg.py` (idempotencia y resultado
incierto), `tests/test_desvinculacion_pg.py` (historial), `tests/test_alta_serie_pg.py`
(identificador único y reutilización), `tests/test_procedencia_serie.py` (`#127`).

### PASS / FAIL / NOT RUN de este refinamiento

**PASS**
1. Inventario de persistencia, procedencia y protección con `fichero:línea` sobre el SHA completo.
2. Inventario de mecanismos de confirmación/idempotencia y de su reutilización por la retirada.
3. Confirmado que **no** existe pantalla, ruta, servicio ni tabla de «asociar fuente».
4. Confirmada la unicidad **por columna y por fuente** y la ausencia de unicidad cruzada.
5. Reconciliación explícita con #109, #124/#182, #133, #134, #128, #127 y #111.
6. Seis decisiones con recomendación, alternativa y coste; contratos A/B con los seis ejemplos
   obligatorios; cortes y estimación.

**FAIL**
- Ninguno de este documento. No se ejecutó nada que pudiera fallar.

**NOT RUN**
1. **Benchmark de referencias** para varios identificadores por entidad (Sonarr/Radarr/Kapowarr).
2. **Pruebas**: no se ejecutó la suite; las citas de pruebas son lectura.
3. **Fuentes reales**: no se consultó ninguna; cómo devuelve cada fuente una búsqueda real y si
   `kind`/editorial vienen siempre está `[sin verificar]`.
4. **Navegador, accesibilidad y Pi**: no se abrió la app ni se midió memoria/latencia.
5. **Datos reales**: no se comprobó cuántas series tienen más de un id (el censo de #181 no lo mide);
   la forma de la base se afirma por el esquema, no por un recuento nuevo.
6. **Decisión del PO** sobre D1-D5 y sobre B+C en el mismo release.

---

## 7. Trazabilidad

| Documento | Uso en esta spec |
|---|---|
| `docs/adr/0003-identidad-editorial.md` | Vocabulario y modelo mínimo; edición/obra no existen. |
| `docs/design/discriminantes-publicacion.md` | Discriminantes y «sin selección automática»; candidata única requiere elección. |
| `docs/design/procedencia-127.md` | Reglas de la procedencia visible y fila única de identidad. |
| `docs/design/enriquecimiento-preview-128.md` | Token, huella, «el mismo plan», no reconsultar. |
| `docs/design/estados-fuentes-133.md` | Conjunto cerrado de estados y capacidad `busqueda`. |
| `docs/design/cortesia-compartida.md` y `cortesia-tebeosfera.md` | Cola compartida y ritmos por fuente. |
| `docs/design/bl-r1-deshacer-vinculacion.md` | Retirar sin borrar; historial en JSONB; D9. |
| `docs/design/censo-identidad-real.md` | Evidencia disponible (0 colisiones; 61,4 % sin fuente). |
| `docs/adr/0006-asignacion-recuperable.md` | Resultado desconocido y reconciliación. |
| `docs/adr/0007-vincular-en-su-sitio.md` | Vincular no mueve nada; una operación con efecto se confirma aparte de revisarla. |
| `docs/adr/0009-contrato-comun-de-creacion-y-borrado-de-series.md` | Comprobantes que sobreviven a la entidad y orden de bloqueos (aceptado parcialmente). |

---

## 8. Revisión v1.1 — contrato de B y C con las condiciones de Seguridad (H1-H17)

> **Vigente desde 2026-11-09.** Esta sección **sustituye** §4.2, §4.3, §4.4, §4.5, §4.6 y §5.1
> donde contradigan. §4.1 (A) se conserva, pero **necesita el delta obligatorio de §8.1**.
> **Base de esta revisión:** `origin/main` **`a87eabd`** (2026-11-09; merge de A, PR #542). La v1.0
> se contrastó en `04ab6ee`; las citas de esta sección se han vuelto a comprobar en `a87eabd`.
> **Aviso de bloqueo:** A está fusionada, pero su implementación actual **no emite token**
> (`services/asociar_fuente.py:92-139`; `web/asociar_fuente.py:74-101`). Sin el delta de §8.1 no
> existe la propuesta firmada que B necesita y **B no puede implementarse**.
> **Decisiones del PO:** **D-A/H10** (restricción de A, §8.6) y **D-H16** (fuente apagada entre A
> y B, §8.8). Todo lo demás de esta sección es **implementación obligatoria**.
> **No implementa código, no ejecuta pruebas, no consulta fuentes y no crea migración.**

### 8.1 Delta obligatorio de A: token con `entidad` y `kind` (H1, H6, H7, H17)

La A actual es solo lectura y devuelve `Comparacion`/`CandidataComparada`
(`services/asociar_fuente.py:36-63`) sin token. La v1.0 ya exigía token; la implementación no lo
emitió. Para que B sea posible y seguro:

**H13-H15 no se reabren:** A ya implementa el coste/una acción de búsqueda (docstring
`services/asociar_fuente.py:1-15`), `_url_segura` (H14, `:77-90`) y `normalizar_consulta` acotada
(H15, `:69-75`); sus pruebas se conservan y B/C no las cambian.

1. **Añadir el propósito y la estructura firmada** en `services/tokens_revision.py`
   (`PROPOSITO_ASOCIAR = "asociar_fuente"`), junto a los propósitos existentes
   (`:37-42`). El token se firma con la clave del servidor y TTL de **15 min**
   (`TTL_SEGUNDOS`, `:30`; `crear_token`, `:90-102`).
2. **Firmar `entidad` y `kind`** (H1), además de lo que ya se veía:

```text
AsociacionFirmada
  version=1
  entidad="serie"            # obligatorio; B rechaza cualquier otro valor
  kind="collection" | null   # Tebeosfera; B rechaza "saga"
  fuente                     # comic_vine | anilist | tebeosfera | gcd
  id_externo                 # canónico y acotado (§8.9)
  titulo, anio               # lo visto; para la huella y el mensaje
  sitio_url | null           # http(s), sin credenciales y acotada (§8.9)
  huella                     # SHA-256 hex de §8.10
  operacion                  # UUID de la operación
  caduca                     # epoch; el contexto es el series_id
```

3. **Un token por candidata seleccionable**, emitido al comparar (no se confía en datos del
   formulario): `CandidataComparada` gana un campo opaco `token`; la vista B1 lo recibe como
   `<input type="hidden">`. Una candidata `kind == "saga"` o no seleccionable **no** lleva token
   (hoy se filtra en `services/asociar_fuente.py:108-118`). Repetir la búsqueda emite tokens nuevos
   con `operacion_id` nuevo; A no escribe.
4. **A no emite token si la identidad del candidato no es canónica**: `_valor_de_id` y las cotas de
   §8.9 se aplican **antes** de firmar. Un id inválido no produce candidata seleccionable ni token
   (mismo criterio que el alta, `services/alta_serie.py:230-236`).
5. **Huella canónica** de §8.10 calculada en A y recalculada en B; A incluye la identidad de la
   candidata y el estado de la serie. `entidad`/`kind` van **dentro de la huella y del token**.
6. **Cota del token** (§8.9): `MAX_TOKEN_ASOCIACION`, calculada con la serialización real como
   `MAX_TOKEN_RETIRADA` (`tokens_revision.py:700-755`); el campo del formulario usa exactamente esa
   cota. `sitio_url` se omite del token si supera la cota (no se trunca).
7. **H10 (decisión del PO, §8.6):** si se aprueba restringir A, `comparar` rechaza una serie sin
   ninguna de las cuatro identidades **antes** de consultar la fuente, sin tráfico.

**Pruebas de A (delta):** token ausente/inválido/caducado; `entidad`/`kind` firmados; saga sin token;
id no canónico sin token; `sitio_url` inválida o larga se omite; huella reproducible; repetición no
duplica; cero escrituras y cero peticiones extra (las de A ya están cubiertas por #542).

### 8.2 B · verificación previa e idempotencia con token caducado (H1, H2, H3)

**Entrada:** solo `token` (`Form(..., min_length=1, max_length=MAX_TOKEN_ASOCIACION)`); el
`series_id` de la URL coincide con el contexto firmado.

Orden obligatorio, **antes de cualquier escritura**:

1. **Verificar firma, propósito y contexto.** Si falla → `token_invalido` (sin escritura). Después,
   **leer el token aunque esté caducado** con `verificar_token_asociacion(..., ignorar_caducidad=True)`,
   igual que `retirada_serie.py:318` y `tokens_revision.py:126-143`; `vigente` se calcula aparte con
   la verificación normal. Un token manipulado no se lee ni con `ignorar_caducidad`.
2. **H1 antes de escribir:** si `entidad != "serie"` o `kind == "saga"`/un `kind` no admitido →
   `omitida` · `propuesta_no_asociable`. No se escribe, no se consulta nada. La regla se aplica
   también si el token está caducado.
3. **Candado consultivo por `operacion_id`** (`pg_advisory_xact_lock`, patrón
   `vinculacion.py:222-225`; `retirada_serie.py:335-338`): dos envíos simultáneos se serializan.
4. **Comprobante previo** en `vinculacion_operaciones` por `operacion_id` (`models:729-748`):
   - si existe con `resultado.tipo == "asociar_fuente"` y coincide `series_id`, fuente e id →
     devolver el mismo resultado con `repetida: true` (cero escrituras);
   - si existe con otro `tipo` u otra serie → `conflicto_operacion` (no se reutiliza un comprobante
     ajeno).
5. **Evidencia durable en `metadata_`** (H2/H3): si no hay comprobante, buscar `operacion_id` en
   `metadata.asociaciones` y en `metadata.asociaciones_historial` (validados, §8.5):
   - entrada activa con el mismo `operacion_id` y el id igual al token → `repetida: true`, sin
     escribir;
   - entrada en historial con `deshecho` para ese `operacion_id` → `ya_retirada`, sin escribir (la
     operación se aplicó y luego se retiró; no se vuelve a asociar);
   - entrada con el mismo `operacion_id` pero id distinto → `procedencia_invalida`, sin escribir.
6. **Token caducado sin evidencia:** `token_caducado`. Se distingue —como en retirada
   (`retirada_serie.py:347-352`)— si pudo haberse aplicado (`ahora >= firma + RETENCION_HORAS`) o no.
   El mensaje no anuncia «no se ha cambiado nada» cuando no puede probarlo.
7. **`SELECT … FOR UPDATE` de la serie** (H4/H8). Si no existe → `serie_inexistente`, sin escritura.
8. **Recalcular la huella** (§8.10) y comparar con la firmada. Si difiere →
   `propuesta_desactualizada`, sin escritura. `updated_at` **no** decide nada (v1 §D5).
9. Convertir/validar el id con `_valor_de_id` y las reglas de §8.9; si no coincide con el firmado →
   `token_invalido`/`identificador_invalido`, sin escritura.
10. Continuar en §8.3.

**H2/H3/H5 (idempotencia y purga):**

- La evidencia durable es **el comprobante (24 h) → la entrada activa de `metadata.asociaciones` →
  la entrada de `asociaciones_historial` por `operacion_id`**. Tres niveles, en ese orden; ninguno
  escribe si ya hay resultado.
- **Purga propia del tipo** (H5): B añade `_purgar("asociar_fuente")` con el patrón acotado de
  `retirada_serie.py:441-448`:
  ```sql
  DELETE FROM vinculacion_operaciones
  WHERE operacion_id IN (
    SELECT operacion_id FROM vinculacion_operaciones
    WHERE resultado ->> 'tipo' = :tipo
      AND creada < now() - make_interval(hours => :h)
      AND token_hasta < now()
    ORDER BY creada LIMIT :n FOR UPDATE SKIP LOCKED)
  ```
  `tipo = "asociar_fuente"`; **no** toca `retirada_serie` ni vinculaciones. La purga existente de
  `retirada_serie` solo purga su tipo (`retirada_serie.py:441-448`); la de `vinculacion.py:437-445`
  no filtra tipo y **no se usa** para B/C. C tiene su propia purga con `tipo="retirar_asociacion"`.
- Un `operacion_id` ocupado por otro tipo **nunca** se reutiliza ni se devuelve como asociación.

### 8.3 B · transacción, columnas y los tres desenlaces R2 (H4, H8, H9)

Con la serie bloqueada y la huella vigente:

1. **La columna es la autoridad de unicidad** (H8/H11). Pre-comprobar para el mensaje, pero la
   garantía final es el índice `UNIQUE` de `Series.comic_vine_id`/`anilist_id`/`tebeosfera_slug`/
   `gcd_id` (`models/__init__.py:410-421`). El JSONB **nunca** decide unicidad ni sustituye a la
   columna.
2. **R2, tres desenlaces** (con respuestas en §8.11):
   - **Mismo id y misma serie:** si ya está en la columna → `ya_asociada` (sin escribir); si es una
     repetición con el mismo `operacion_id`/comprobante → `asociada` con `repetida: true` (sin
     escribir).
   - **Mismo `(serie, fuente)` con otro id:** `omitida` ·
     `ya_tiene_identidad_en_esa_fuente`; no se sobrescribe; el mensaje remite a retirar primero.
   - **El id pertenece a otra serie:** `omitida` · `conflicto_identificador`; se informa del título
     de la otra serie y **no se reasigna**.
3. **Carrera de unicidad:** si el `UNIQUE` salta al hacer `flush`/`commit`, capturar `IntegrityError`
   y devolver **el mismo** `conflicto_identificador`; `rollback` completo, sin asociación parcial ni
   comprobante. Nunca un 500.
4. **Escritura exacta** (solo si procede):
   - `UPDATE series SET <columna_fuente> = :id, metadata_ = fusionar_metadata(...)`;
   - una entrada en `metadata_["asociaciones"]` y, si existía otra activa de esa fuente, no se
     duplica (R2 la rechaza antes);
   - `INSERT` del comprobante en `vinculacion_operaciones` con `tipo="asociar_fuente"`;
   - `updated_at` solo por `onupdate`.
   **No** se toca `metadata_source`, `locked_fields`, `enrichment_attempted_at`, `Issue`, `File` ni
   archivos. Un `ya_asociada` no escribe ni inventa procedencia.
5. **Purga acotada** de B (§8.2) en la misma transacción, antes del `commit`.
6. **`commit` al final**; preparar la respuesta antes de pedirlo. Si falla después de pedirlo →
   `resultado_incierto` (503), nunca «no se ha cambiado nada»; el reintento del mismo token relee
   comprobante/JSONB y no duplica.
7. **Carrera con el enricher (H9):** B bloquea la fila con `FOR UPDATE`; el enricher debe usar
   `UPDATE ... WHERE id = :serie AND <id_col> IS NULL` (o revalidar bajo bloqueo) y, si `rowcount=0`,
   **no** escribir identidad ni metadatos de esa serie. Ver §8.6.

**Efectos exactos cuando escribe:** `{campos_serie:1, asociaciones:1, comprobantes:1, numeros:0,
archivos:0, metadatos_aplicados:0}`. Un `ya_asociada`/`omitida` deja todos los contadores a 0.

### 8.4 C · retirar una asociación (H4)

**Qué es.** Retirar **solo** la identidad de una fuente de una serie, con historial, sin tocar la
serie, sus números, sus archivos, las demás fuentes, `metadata_source` ni `locked_fields`.

**Previsualización (GET, no escribe):**

- Desde la ficha, «Retirar» de la fuente; verifica que la serie y la columna de esa fuente existen;
  si no hay asociación, muestra `ya_retirada` (o 404 de asociación) sin token.
- Emite `RetirarAsociacionFirmada` con propósito `PROPOSITO_RETIRAR_ASOCIACION =
  "retirar_asociacion"`, contexto `series_id`, y payload:
  `version=1`, `entidad="serie"`, `fuente`, `id_externo` (el de la columna, canónico), `huella` de
  **la asociación** (§8.10), `operacion`, `caduca`. TTL 15 min; `MAX_TOKEN_RETIRAR_ASOCIACION`
  calculada igual que las demás (§8.9).
- La huella incluye la columna de esa fuente y su entrada activa (o `null`) **solo** de esa fuente;
  no incluye título/año ni las demás fuentes, para no bloquear una retirada por cambios ajenos.
- No se consulta la fuente; no se escribe.

**Confirmación (POST, solo token):**

1. Verificar firma/propósito/contexto; leer con `ignorar_caducidad=True` y calcular `vigente`.
   `entidad != "serie"` → `token_invalido`, sin escritura.
2. Candado consultivo por `operacion_id`.
3. Comprobante previo con `tipo="retirar_asociacion"`: mismo resultado `repetida: true`; otro tipo →
   conflicto.
4. Evidencia durable en `asociaciones_historial` por `operacion_id` (original o `deshecho`): si ya
   está retirada → `ya_retirada`, sin escribir. Token caducado sin evidencia → `token_caducado` con
   la distinción del paso 6 de §8.2.
5. `SELECT … FOR UPDATE` de la serie; si no existe → `serie_inexistente`.
6. Recalcular la huella de la asociación; si la columna cambió, se retiró o se sustituyó →
   `propuesta_desactualizada`, sin escritura. Si la columna es `NULL` → `ya_retirada`. Si la columna
   tiene **otro** id → `propuesta_desactualizada` (no se retira la nueva).
7. Escritura exacta:
   - quitar la entrada activa de esa fuente de `metadata_["asociaciones"]`;
   - añadir a `metadata_["asociaciones_historial"]` la entrada **íntegra** con
     `deshecho:{operacion_id, fecha, motivo:"retirada"}` y `previo` (fuente, id, entidad, kind,
     fecha, operación, origen, modo); si no había entrada activa, `previo` lleva lo que conste de la
     columna y `procedencia: "desconocida"` (se puede retirar igual, D9/BL-R1);
   - `UPDATE series SET <columna_fuente> = NULL, metadata_ = fusionar_metadata(...)`;
   - `INSERT` del comprobante con `tipo="retirar_asociacion"`.
   **No** se toca ninguna otra columna/fuente, ni `metadata_source`, ni `locked_fields`, ni
   `Issue`/`File`.
8. Purga propia `retirar_asociacion` (§8.2) y `commit` al final; fallo tras pedirlo →
   `resultado_incierto` (503 + comprobar resultado). Repetir el mismo token devuelve el mismo
   resultado sin duplicar historial ni comprobante.
9. **Resultados:** `retirada` (con `repetida:false`) / `ya_retirada` (`repetida:true` si se repite) /
   `omitida` con `propuesta_desactualizada`, `serie_inexistente`, `conflicto_operacion`,
   `conflicto_de_bloqueo`; `resultado_incierto` es un 503 aparte. Textos: los de
   `ui-M6-US03-asociar-fuente.md` §7-§8, sin jerga interna.
10. **C y B se entregan en el mismo release** (P8/D4): sin C, una asociación equivocada es permanente.

### 8.5 JSONB: esquema, validación al leer/escribir y reparación (H8, H11)

**La columna es la autoridad; `metadata_` es procedencia e historial.** No se escribe el JSONB antes
que la columna ni se usa para decidir unicidad.

**Esquema activo (`metadata_["asociaciones"]`, lista; una por fuente):**

```json
{
  "version": 1,
  "fuente": "gcd",
  "id_externo": "1234567",
  "entidad": "serie",
  "kind": "collection",
  "fecha": "2026-11-09T10:00:00+00:00",
  "operacion_id": "0f0c…",
  "origen": "confirmada",
  "modo": "busqueda"
}
```

**Historial (`metadata_["asociaciones_historial"]`, lista append-only):** la entrada anterior más
`deshecho: {operacion_id, fecha, motivo}` y `previo` (la entrada íntegra). La retirada nunca borra la
entrada: la mueve al historial.

**Validación (obligatoria al leer y al escribir):**

- `metadata_` debe ser un objeto; `asociaciones`/`asociaciones_historial`, listas (o ausentes).
- `version == 1`; `fuente` ∈ cuatro; `id_externo` canónico (§8.9); `entidad == "serie"`;
  `kind` ∈ `{null, "collection", "saga"}` (B solo escribe `null`/`"collection"`); `fecha` ISO 8601
  con zona; `operacion_id` UUID; `origen` ∈ `{confirmada, enriquecimiento}`; `modo` ∈
  `{busqueda, id_exacto}`; campos desconocidos → entrada inválida (no se interpreta).
- **Al escribir:** B/C validan el JSONB resultante **antes** del `UPDATE`; si el estado actual es
  inválido donde afecta (p. ej. una entrada activa de la misma fuente), B devuelve
  `procedencia_invalida` y no escribe. C puede retirar la columna aunque la entrada sea inválida,
  moviéndola al historial con `procedencia: "invalida"`.
- **Al leer:** una entrada inválida **no** se usa como identidad ni como evidencia de idempotencia;
  la ficha muestra «procedencia no registrada»; nunca se lanza una excepción de parseo por JSONB
  ajeno. La identidad vigente sigue siendo la columna.

**Entradas huérfanas (H11):**

| Caso | Definición | Tratamiento |
|---|---|---|
| **Activa huérfana** | entrada activa con id distinto de la columna, o columna `NULL` | no acredita identidad; se puede **reparar** moviéndola al historial |
| **Duplicada** | más de una entrada activa para la misma fuente | la columna manda; las demás al historial en la reparación |
| **Inválida** | no cumple el esquema | no se interpreta; reparación explícita |
| **Columna sin procedencia** | columna con id pero sin entrada activa (legacy) | **no** es huérfana: se muestra «origen no registrado» y se puede retirar; no se inventa procedencia |

- `auditar_asociaciones(series)` es **solo lectura** y devuelve las incidencias; no repara.
- `reparar_asociaciones(series_id, *, confirmar=True)` es **explícita, idempotente y sin red**:
  mueve las entradas huérfanas/duplicadas/inválidas al historial con
  `deshecho: {operacion_id: null, fecha, motivo: "reparacion"}` y `previo`; **no toca la columna**
  (no inventa ni borra identidad), no consulta la fuente y no se ejecuta automáticamente en B/C.
  Si el PO quiere superficie de UI para reparar, es otro corte; aquí se define el servicio/pruebas.
- **Pruebas:** lectura con JSONB corrupto no rompe la ficha; B rechaza JSONB inválido; C retira con
  entrada inválida; reparación mueve al historial y deja la columna intacta; columna sin procedencia
  no se «repara» inventando.

### 8.6 Carrera con el enricher (H9) y «asociar deja de enriquecer» (H10)

**H9 — obligatorio.** El enricher selecciona series con las cuatro columnas `NULL`
(`enricher.py:190-202`) y luego hace `setattr` del id (`:262-263`, `:281-299`). Si B asocia entre la
selección y la escritura, el enricher podría pisar la identidad. Contrato:

- El enricher escribe la identidad con un `UPDATE series SET <id_col> = :id ... WHERE id = :serie AND
  <id_col> IS NULL` (o `SELECT … FOR UPDATE` y revalidar) y comprueba `rowcount`.
- Si `rowcount == 0`, **no** escribe id, descripción, portada, total ni `metadata_source` de esa
  serie en ese ciclo: otra operación la identificó y no se pisa. No se lanza excepción; se registra
  sin datos del coleccionista.
- Prueba de dos sesiones (B asocia mientras el enricher intenta) → una sola identidad, sin pérdida.

**H10 — decisión del PO.** Asociar escribe una identidad; el enricher excluye **cualquier** serie con
una identidad (`enricher.py:190-202`). Por tanto, asociar una serie que **no tenía ninguna** la saca
del enriquecimiento automático. Dos opciones:

| Opción | Efecto | Recomendación |
|---|---|---|
| **D-A/H10 (recomendada): restringir A a series con ≥1 identidad** | «asociar otra fuente» exige una primera; no se apaga el enricher de una serie sin identidad; no hay efecto colateral nuevo | **Sí**; encaja con el título y con «otra fuente»; implementar en A antes de B |
| Alternativa: permitir series sin identidad | asociar deja de enriquecer; hay que **declararlo** en B1/B2 y probarlo | Solo si el PO lo decide; texto explícito y test de que el enricher no la toca después |

- Si se restringe: A devuelve `serie_sin_identidad` **sin tráfico**; la ficha no ofrece «Otras
  fuentes» o muestra «Primero identifica esta serie con una fuente». Es un cambio de A (hoy permite
  cualquier serie, `services/asociar_fuente.py:92-139`).
- Si se permite: B1/B2 advierte «Esta serie no tenía ninguna fuente; al asociarla dejará de
  enriquecerse automáticamente»; prueba de que tras B el enricher no la selecciona; se documenta.
- **Esto es decisión del PO**, no de la implementación.

### 8.7 Procedencia por fuente en la ficha (H12)

`services/procedencia.py:107-112` hoy elige **una** columna (`next(...)`) y pinta una fila agrupada;
con varias fuentes hay que mostrar **una línea por fuente**, sin ids internos:

- Para cada una de las cuatro columnas no nulas: nombre público de la fuente y, si hay entrada activa
  válida en `metadata.asociaciones`, fecha de asociación; si no, «origen no registrado».
- Varias fuentes → varias líneas, sin fusionar ni elegir una «principal»; no se pinta el id interno
  (la persona no lo necesita; si se muestra la ficha externa, es como dato de la fuente, no interno).
- JSONB inválido o entrada huérfana → «procedencia no registrada», sin romper la ficha; la identidad
  sigue saliendo de la columna.
- `procedencia.py` conserva su resumen y sus avisos; el cambio es aditivo. Pruebas: dos fuentes con
  procedencia, una legacy sin entrada, una inválida; el HTML no contiene ids internos ni jerga.

### 8.8 Fuente apagada entre A y B (H16) — decisión del PO

A comprueba la fuente antes de consultar. Entre A y B no hay red: B solo persiste lo ya firmado.
Opciones:

| Opción | Comportamiento | Recomendación |
|---|---|---|
| **D-H16 (recomendada): B guarda aunque la fuente esté apagada** | no se consulta la fuente; la propuesta se firmó cuando estaba encendida; B escribe igual y muestra un aviso neutro «La fuente está apagada en Ajustes; la asociación se guarda porque no se ha consultado» | **Sí**: apagar una fuente no revoca una identidad ya confirmada; B no hace red |
| Alternativa: B rechaza con `fuente_apagada` | exige volver a encender la fuente y repetir A; no escribe | Solo si el PO prefiere bloquear |

- En ambos casos la decisión se toma **antes** de escribir y se prueba explícitamente (token de A,
  apagar la fuente, B; con la opción recomendada: escritura y cero peticiones; con la alternativa:
  `omitida` y cero escrituras). No se consulta la fuente en B.

### 8.9 Cotas de token y URL (H6) e id canónico (H17)

**Token (H6, reutilizando `tokens_revision`):**

- `MAX_TOKEN_ASOCIACION` y `MAX_TOKEN_RETIRAR_ASOCIACION` se calculan con la **serialización real**
  del peor caso, como `MAX_TOKEN_RETIRADA` (`tokens_revision.py:700-755`), no con un número redondo.
- Cotas de campos: `MAX_ID_EXTERNO=255`, `MAX_TITULO=500`, `MAX_COVER_URL` (`LONGITUD_MAXIMA_URL`) y
  años `ANIO_MIN/MAX_FIRMABLE` (`tokens_revision.py:47-54`). `MAX_SITIO_URL = MAX_COVER_URL` (alias
  explícito para la ficha); si la supera o no es http(s) con host y sin credenciales, se firma `null`
  (no se trunca). El formulario usa exactamente `MAX_TOKEN_ASOCIACION`
  (`Form(..., max_length=...)`); un cuerpo mayor → 422, sin procesar.
- La huella es de 64 hex; UUIDs canónicos; `version=1`; `entidad`/`kind` dentro del token (H1).

**Id por fuente (H17):**

| Fuente | Campo | Tipo canónico | Regla |
|---|---|---|---|
| Comic Vine | `comic_vine_id` | entero positivo | ASCII `^[1-9][0-9]{0,18}$`, ≤ `2^63-1`; sin ceros a la izquierda, signos, espacios ni Unicode |
| AniList | `anilist_id` | entero positivo | ídem |
| GCD | `gcd_id` | entero positivo | ídem |
| Tebeosfera | `tebeosfera_slug` | texto | 1–255, `texto_firmable`, sin espacios/controles ni `/`, `?`, `#`; no es una URL |

- `_valor_de_id` (`alta_serie.py:230-236`) se reutiliza para la conversión, pero **envolviéndolo** en
  una validación estricta: `int("+1")`, espacios y dígitos Unicode no valen; el canónico se firma
  como `str(int)` para numéricos. A y B aplican la misma función; un id no canónico no produce token
  y B lo rechaza antes de escribir (`identificador_invalido`).
- `CAMPOS_ID_DE_TEXTO` (`discovery.py:50`) decide el tipo; no se duplica el mapa.

### 8.10 Huella canónica (H7)

`huella_de_asociacion(series, candidata)` (A/B) y `huella_de_asociacion_actual(series, fuente)` (C):

- Se construye un `dict` con claves explícitas y se serializa **siempre** con
  `json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` y SHA-256.
  `sort_keys` ya es el patrón de `enriquecimiento_plan._huella`
  (`enriquecimiento_plan.py:161`) y `retirada_serie.huella_de_estado` (`:205-207`).
- **Listas ordenadas**: `locked_fields` ordenado; `asociaciones` activas ordenadas por
  `(fuente, id_externo, operacion_id)`; ids de fuentes con valor fijo; sin `updated_at`.
- **Fechas ISO**: `fecha` y cualquier fecha del JSONB se convierten a `isoformat()` UTC antes de
  serializar; no se comparan objetos `datetime` con zona distinta.
- **A/B** incluyen: `version`, `serie_id`, `titulo`, `anio`, `tradicion`, los cuatro ids,
  `metadata_source`, `locked_fields`, `asociaciones` activas, y la identidad de la candidata
  (`fuente`, `id_externo`, `entidad`, `kind`, `titulo`, `anio`, `sitio_url` normalizada). **C**
  incluye solo: `version`, `serie_id`, `fuente`, `id_externo`, `entidad` y la entrada activa (o
  `null`) de esa fuente; no título/año ni otras fuentes.
- Misma entrada → misma huella en A y B; cualquier cambio relevante → distinta; cambio de
  `updated_at` o de una fuente ajena → no cambia (C). Pruebas de reproducibilidad y de orden de
  listas.

### 8.11 Respuestas de los tres desenlaces R2 y de C (códigos y textos)

| Caso | `resultado` | `motivo` | `repetida` | Escrituras | Superficie |
|---|---|---|---|---|---|
| Mismo id, misma serie, operación repetida | `asociada` | `null` | `true` | 0 | B2 «Ya estaba asociada» |
| Mismo id, misma serie, ya en columna sin comprobante | `ya_asociada` | `null` | `false` | 0 | B2 «Ya estaba asociada» |
| Otro id de la misma fuente | `omitida` | `ya_tiene_identidad_en_esa_fuente` | `false` | 0 | B2 «Ya tiene ficha» + enlace a C |
| Id en otra serie | `omitida` | `conflicto_identificador` | `false` | 0 | B2 «Ficha ocupada» + otra serie |
| Huella distinta | `omitida` | `propuesta_desactualizada` | `false` | 0 | B2 «Ficha desactualizada» |
| Token caducado sin evidencia | `omitida` | `token_caducado` | `false` | 0 | B2 «Propuesta caducada» |
| Entidad/kind no asociable | `omitida` | `propuesta_no_asociable` | `false` | 0 | B2 error |
| C: retirada | `retirada` | `null` | `false` | 1 columna + historial + comprobante | C2 «Asociación retirada» |
| C: repetida / ya no estaba | `ya_retirada` | `null` | `true`/`false` | 0 | C2 «Ya estaba retirada» |
| C: cambió la asociación | `omitida` | `propuesta_desactualizada` | `false` | 0 | C2 «Ficha desactualizada» |
| C: otra operación | `omitida` | `conflicto_operacion` | `false` | 0 | C2 «Ya no estaba»/reintentar |

Textos exactos en `ui-M6-US03-asociar-fuente.md` §6 y §8; no se introducen ids internos, «token» ni
códigos en superficie. `resultado_incierto` es siempre 503 con «Comprobar el resultado», nunca éxito
sin releer.

### 8.12 Pruebas obligatorias de esta revisión (H1-H17)

> H13-H15 ya están cubiertas por A (#542): coste/peticiones, `_url_segura` y `normalizar_consulta`;
> esta revisión las conserva y no las reabre. Las filas siguientes se centran en B/C y en el delta
> de A.

Sin red; PostgreSQL real para persistencia; fixtures simuladas para A. Se añaden a las de §7 del
documento UI y a las futuras de B/C:

| H | Prueba |
|---|---|
| H1 | token con `entidad="serie"`/`kind="collection"` pasa; `entidad="issue"`, `kind="saga"` o `kind` desconocido → `omitida`, sin escritura; token manipulado no se lee |
| H2 | mismo token tras 16 min con comprobante → mismo resultado; con comprobante purgado pero entrada activa → repetida; sin evidencia → `token_caducado` |
| H3 | evidencia en `asociaciones_historial` por `operacion_id` (activa retirada) → `ya_retirada`, sin escribir |
| H4 | C: token/huella, candado, `FOR UPDATE`, comprobante, `ya_retirada`, resultado incierto; C no toca otra fuente |
| H5 | purga de `asociar_fuente` y `retirar_asociacion` acotada; no purga `retirada_serie` ni vinculaciones |
| H6 | `MAX_TOKEN_ASOCIACION`/`MAX_TOKEN_RETIRAR_ASOCIACION` son el peor caso emitible; Form lo aplica; `sitio_url` larga se omite |
| H7 | huella reproducible con `sort_keys`/listas ordenadas/fechas ISO; cambia si cambia lo relevante; C no cambia por otras fuentes |
| H8 | columna única manda; `IntegrityError` → conflicto; JSONB inválido no se usa como identidad |
| H9 | dos sesiones: enricher no pisa el id asociado; `rowcount=0` no escribe metadatos |
| H10 | restricción A sin identidad: cero tráfico; o (si PO decide) efecto declarado y probado |
| H11 | auditoría de huérfanas; reparación explícita mueve al historial sin tocar columna; lectura no rompe |
| H12 | ficha con dos fuentes muestra dos líneas, sin ids internos; legacy dice «origen no registrado» |
| H16 | token de A, apagar fuente, B: opción recomendada escribe sin peticiones; alternativa `omitida` sin escritura |
| H17 | ids inválidos (`+1`, ` 1`, `001`, Unicode, 0, >2^63, slug con `/`) no emiten token y B los rechaza |
| R2 | los tres desenlaces con sus códigos, sin reasignar, sin duplicar, sin 500 |
| C | retirar solo esa columna; historial con `previo` y `deshecho`; repetir no duplica; resultado incierto releyendo |

### 8.13 Corte y PRs actualizado

A (#542) está fusionada, pero **sin token**: el primer paso es un delta de A. B y C no existen.

| PR | Contenido | Por qué |
|---|---|---|
| **PR-S1 · delta de A** | `PROPOSITO_ASOCIAR`, `AsociacionFirmada` con `entidad`/`kind`, emisión de token por candidata seleccionable, huella §8.10, id canónico §8.9, cota de token/URL; H10 si el PO lo aprueba | Sin token no hay B; es lo que H1/H6/H7/H17 exigen antes de escribir |
| **PR-B · confirmar** | Transacción B (§8.2-8.3), R2, idempotencia comprobante/JSONB/historial, purga propia, H8/H11 (validación/auditoría/reparación), H9 enricher, H12 procedencia, H16 según PO; pruebas PostgreSQL | Persistencia real; no migración |
| **PR-C · retirar** | Token/huella C, transacción C, historial, purga propia, estados y UI C1/C2; pruebas | **Mismo release que B** (P8/D4); sin C no hay corrección |
| **No entra** | Tabla nueva/migración, UI de reparación, automatismos de identidad, activar fuentes, #233 | Fuera de alcance / ADR |

**Orden:** PR-S1 → PR-B ∥ pruebas de C → PR-C en el mismo release. Si el PO elige la opción
alternativa de H10/H16, el PR correspondiente añade el aviso y la prueba, pero **no** cambia el
contrato de B/C más que en ese punto. **NOT RUN:** no se ha implementado nada de B/C; no se han
ejecutado pruebas ni tocado PostgreSQL; A no emite token todavía.

### 8.14 Criterios de aceptación de esta revisión (Given/When/Then)

**AC-S1 (H1/H6/H7/H17).** Given una comparación con candidata seleccionable, When se emite la
propuesta, Then el token firma `entidad="serie"` y `kind`, el id es canónico, la huella es
reproducible y el token cabe en su cota; una saga o un id inválido no producen token.

**AC-S2 (H1).** Given un token con `kind="saga"` o `entidad!="serie"`, When B lo recibe, Then
`omitida`/`propuesta_no_asociable` **antes de escribir**, sin peticiones y sin comprobante.

**AC-B1 (H2/H3).** Given un token caducado, When B lo repite, Then lee comprobante/JSONB/historial
con `ignorar_caducidad`; si hay evidencia devuelve el mismo resultado sin escribir; si no, distingue
`token_caducado` de «pudo aplicarse».

**AC-B2 (R2/H8).** Given los tres desenlaces, When se confirman, Then se devuelven `asociada`
repetida, `ya_tiene_identidad_en_esa_fuente` o `conflicto_identificador`, sin reasignar, sin
sobrescribir y sin 500; la columna manda y el JSONB no decide unicidad.

**AC-B3 (H4/H5).** Given una escritura de B, When termina, Then el comprobante es
`tipo="asociar_fuente"`, la purga es propia y acotada y no toca otros tipos; un fallo tras `commit`
es `resultado_incierto`.

**AC-B4 (H8/H11).** Given un JSONB inválido u huérfano, When se lee/escribe/repara, Then no se usa
como identidad, B no escribe si afecta, C puede retirar, la reparación explícita mueve al historial
sin tocar la columna y la lectura no rompe.

**AC-B5 (H9).** Given B y el enricher en paralelo, When ambos intentan escribir, Then el enricher no
pisa la identidad (`UPDATE ... WHERE id IS NULL`/`rowcount=0`) y no escribe metadatos de esa serie.

**AC-C1 (H4).** Given una asociación, When se retira, Then se quita solo esa columna, se conserva el
historial con `previo`/`deshecho`, no se tocan otras fuentes ni archivos y repetir no duplica;
resultado incierto se relee.

**AC-P1 (H12).** Given una serie con dos fuentes, When se abre la ficha, Then la procedencia muestra
una línea por fuente, sin ids internos; una fuente legacy dice «origen no registrado».

**AC-P2 (H10/H16).** Given la decisión del PO, When se ejecuta, Then la restricción de A o el aviso
de H16 se prueba con el caso elegido y no se cambia el contrato sin registro.

### 8.15 Decisiones del PO (explícitas)

| ID | Decisión | Recomendación | Consecuencia si se elige la alternativa |
|---|---|---|---|
| **D-A/H10** | ¿A solo para series con ≥1 identidad? | **Sí, restringir** | Si se permite, asociar una serie sin identidad la saca del enricher: hay que declararlo en B1/B2 y probarlo; no se puede presentar como efecto neutro |
| **D-H16** | ¿B guarda si la fuente se apaga entre A y B? | **Sí, guardar sin red** (aviso neutro) | Si se rechaza, B devuelve `fuente_apagada` y no escribe; hay que probarlo y explicarlo en B2 |

Todo lo demás (H1-H9, H11-H17, R2, C) es **implementación obligatoria**, no decisión de producto.
La restricción de A y la decisión H16 se registran en la spec/BACKLOG antes de implementar; sin
ellas, B no se declara Ready.

**Registro del PO (2026-11-09).** Se **eligen** las dos recomendaciones:

- **D-A/H10:** A solo se ofrece para series que **ya tienen al menos una identidad** (`comic_vine_id`,
  `anilist_id`, `tebeosfera_slug` o `gcd_id`). Sin identidad no se consulta, no se emite token y el
  enlace «Buscar en otra fuente» queda deshabilitado con el motivo en llano. Evita que asociar saque
  a la serie del enricher sin una explicación explícita.
- **D-H16:** si la fuente se apaga entre A y B, **B guardará sin red y avisará** («La fuente está
  apagada en Ajustes; la asociación se guarda porque no se ha consultado»). No se revalida la fuente
  ni se consulta red; se probará en B. A no se ve afectada porque comprueba la fuente antes.

### 8.16 NOT RUN de esta revisión

- **Código B/C:** no existe; no se ha implementado nada en esta entrega.
- **A token:** implementado en PR-S1 (token por candidata seleccionable, preview B1 sin escribir); B de persistencia sigue pendiente.
- **Pruebas:** no se ha ejecutado la suite ni PostgreSQL; las pruebas de §8.12 están definidas, no
  ejecutadas.
- **Fuentes reales:** ninguna; no se ha comprobado `kind`/editorial en vivo.
- **PO:** D-A/H10 y D-H16 **decididas el 2026-11-09** (restringir A y guardar H16 sin red); B las implementará.
- **SHA:** `a87eabd`; si `main` avanza antes de implementar, re-ejecutar las citas.
