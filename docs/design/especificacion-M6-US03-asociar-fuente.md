# Especificación — MIT-M6-US03: Asociar otra fuente explícitamente (#129)

> **Estado:** propuesta de refinamiento para el PO. **No implementa código, no crea migración, no
> consulta fuentes reales y no ejecuta pruebas.**
> **Contraste:** `origin/main` en **`04ab6eea58e0deb98d1f12f6fb7d9d69e4f3f7ad`** (2026-11-09), worktree
> `.squad/wt-129`, rama `docs/129-refinamiento`. Toda cita `fichero:línea` se refiere a ese SHA.
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
