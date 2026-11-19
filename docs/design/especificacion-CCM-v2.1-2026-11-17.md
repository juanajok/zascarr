# Especificación CCM v2.1 — correcciones sobre la propuesta v2

> **Estado:** especificación corregida, no implementada.
> **Sustituye a:** v2 pegada en el hilo (2026-11-17).
> **Base actualizada:** `origin/main` `11e53924` (la v2 citaba `cf2d7ba6`, ya anterior).
> **Objetivo de esta revisión:** dejar una especificación que se pueda implementar contra el modelo
> real sin inventar columnas, sin romper datos heredados y sin prometer fases que los clientes
> actuales no soportan.
> **No** se ha modificado código, datos ni biblioteca en esta revisión.

---

## 0. Resumen de cambios respecto a la v2

| # | Fallo de la v2 | Corrección v2.1 |
|---|---|---|
| 1 | Usaba `Series.country`, `Issue.gtin` y `Series.imprint` como si existieran | Se mapean a `Publisher.country`, `metadata_["identificadores"]["gtin"]` y `imprint_id`; no hay migración en Fase 1–3 |
| 2 | Usaba `edition_type` | El campo real es `Series.edition_kind` (`EditionKind`) |
| 3 | Decía «B6 intacto» y a la vez escribía `Web`/`GTIN`/`Count` | B6 no gestiona esos tags; Fase 5 los amplía explícitamente o los aplaza |
| 4 | Fase 1 prometía `fetch_issues_de_serie` en 8 fuentes | Fase 1 solo CV/Tebeosfera/GCD y **solo series**; issues en Fase 4 |
| 5 | `rol_vinculo` se infería por `language == "es"` | El rol es explícito y por defecto `obra_referencia`; la inferencia solo sugiere |
| 6 | El backfill convertía `metadata_source` en procedencia autoritativa | Los valores heredados quedan `legado: true`/no verificados; no alimentan `edition_scope` |
| 7 | «Retirar SCR7 en Fase 2» sin paridad | SCR7 y enricher conviven detrás de un flag hasta que la CCM demuestre paridad |
| 8 | Rutas `app/core/...` | Rutas reales `src/zascarr/core/...` y `src/zascarr/services/...` |
| 9 | Base `cf2d7ba6` | Base `11e53924`; verificar diferencias antes de abrir rama |
| 10 | «100 % de tests de adaptadores» | Se sustituye por matriz de casos cerrada y `MockTransport`, no una cifra de cobertura |

---

## 1. Decisiones que se mantienen de la v2

1. **No añadir fuentes nuevas.** La CCM usa las fuentes ya integradas.
2. **Identidad explícita, nunca por título.** La CCM no hace búsquedas de serie ni de issue por
   nombre.
3. **Reutilizar `entity_source_records` y `field_provenance`** de la migración `0032`. No se crean
   tablas nuevas en Fase 1–3.
4. **Separar `work_scope` y `edition_scope`** para no mezclar una edición española con la edición
   USA de la misma obra.
5. **Lo local manda:** manual/bloqueado > `ComicInfo` local propio o confirmado > fuente externa.
6. **Nada de escrituras en GET**; recolección en segundo plano y Cola de `ComicInfo` diferida.
7. **La colección local no se enriquece desde fuera.** `collections` sigue siendo una agrupación
   manual; la colección editorial es otra cosa (Fase 6 / ADR de edición).

---

## 2. Mapa de campos real (corregido)

### 2.1 Serie

| Campo canónico | Dónde vive de verdad | Ámbito | Nota |
|---|---|---|---|
| `title` | `Series.title` | `edition_scope` | Solo se rellena al crear; no se corrige automáticamente una serie existente |
| `sort_title` | `Series.sort_title` | `edition_scope` | Puede derivarse; no se inventa identidad |
| `volume` | `Series.volume` | `edition_scope` | Discriminador, no identidad |
| `start_year` / `end_year` | `Series.start_year` / `end_year` | `edition_scope` | Nunca desde una `obra_referencia` |
| `publisher` | `Series.publisher_id` → `Publisher` | `edition_scope` | Se resuelve a entidad; no se guarda el nombre crudo en la fila |
| `imprint` | `Series.imprint_id` → `Imprint` | `edition_scope` | La v2 decía «texto»; es FK |
| `country` | `Publisher.country` o `metadata_["pais"]` | `edition_scope` | **No hay `Series.country`**; no se crea migración en esta fase |
| `language` | `Series.language` | `edition_scope` | Existe, pero hoy está a 0/228 en la Pi; no sirve para inferir rol |
| `edition_type` | `Series.edition_kind` | `edition_scope` | Enum `EditionKind`; no `edition_type` |
| `total_issues` | `Series.total_issues` | `edition_scope` | El valor actual pudo venir de la edición USA; backfill conservador |
| `description` | `Series.description` | `work_scope` | Texto de fuente: se guarda en BD con atribución; no se copia a XML si es externa |
| `genres` | `series_genres` | `work_scope` | Unión normalizada con tope; no borra |
| `tags` | `series_tags` | `work_scope` | Política de fuente/tradición; no resucita `oculta` |
| `cover_url` | `Series.cover_url` | `edition_scope` | Una portada autorizada; nunca Fandom *fair use* en XML |
| `status` | `Series.status` | `edition_scope` | No entra en Fase 1; validar antes |

### 2.2 Issue

| Campo canónico | Dónde vive de verdad | Ámbito | Nota |
|---|---|---|---|
| `issue_number` | `Issue.issue_number` | `edition_scope` | Identidad local de la edición; no se renumera por fuente |
| `title` | `Issue.title` | `edition_scope` | Título localizado |
| `release_date` | `Issue.release_date` | `edition_scope` | Fecha de venta/publicación; distinguir `cover_date`/`store_date` |
| `format` | `Issue.format` | `edition_scope` | `IssueFormat` |
| `page_count` | `Issue.page_count` | `edition_scope` | Rango 1–10.000 |
| `isbn` | `Issue.isbn` | `edition_scope` | Columna existente |
| `gtin` | `metadata_["identificadores"]["gtin"]` | `edition_scope` | **No hay columna**; JSONB hasta que el PO decida migración |
| `synopsis` | `Issue.synopsis` | `work_scope` | Solo BD; `<Summary>` XML solo si es manual (LEGAL §7.1) |
| `cover_url` | `Issue.cover_url` | `edition_scope` | Igual que serie |
| `credits` | `issue_creators` | `work_scope` (creativos) / `edition_scope` (traductor/editor) | Sin procedencia por relación en Fase 1–3; solo «vacíos» |
| `characters` | `issue_characters` | `work_scope` | Solo si no hay relación previa |
| `story_arcs` | `story_arc_issues` | `work_scope` | Solo si no hay relación previa |

> **Regla de oro:** si un campo no tiene columna y no está en `metadata_`, no se escribe en la fila.
> La v2 no puede decir «cero migraciones» y a la vez asumir `country`/`gtin` como si existieran.

---

## 3. Rol del vínculo: explícito, no inferido

### 3.1 Regla corregida

Cada ID externo tiene un rol en `metadata_["vinculos_rol"]`:

```json
{"comic_vine": "obra_referencia", "tebeosfera": "edicion_propia"}
```

- **Sin entrada ⇒ `obra_referencia`.** Es el valor seguro: no puede corromper `edition_scope`.
- Solo una acción humana (o una importación explícita que el usuario confirme) escribe
  `edicion_propia`.
- La UI **sugiere** `edicion_propia` cuando la evidencia es fuerte (Tebeosfera/ISBN español,
  `language` ya confirmado, etc.), pero la persona confirma antes de aplicar campos de edición.
- La inferencia automática de la v2 queda limitada a `SugerenciaVinculo`; nunca a escritura.

### 3.2 Motivo

En la Pi, `Series.language` está vacío en 228/228 series y 173 no tienen ningún ID externo (55 tienen al menos uno).
La regla «si `language == es`, Tebeosfera es edición propia; si no, CV es edición propia» es
indeterminable para la mayoría del catálogo y puede clasificar CV (edición USA) como edición propia
de una serie española. Eso es exactamente el fallo que la v2 quería evitar.

### 3.3 Consecuencia aceptada

Al principio, casi todo será `obra_referencia` y la CCM **no rellenará** años/editorial/total de
edición hasta que haya una confirmación. Es más lento, pero no rompe huecos ni `total_issues`.
La UI de roles es parte de Fase 2, no un extra.

---

## 4. Backfill conservador

La v2 decía que `metadata_source` se convertía en procedencia. Corregido:

| Fuente de evidencia existente | Qué se escribe en `field_provenance` |
|---|---|
| `metadata_["manual"]` | `source = "manual"`, `confianza = "manual"`, `locked = true` si consta |
| `metadata_["comicinfo_aplicado"].aplicado` | `source = "comicinfo_local"`, `confianza = "local"` |
| `metadata_["relleno"][fuente].campos` | `source = fuente`, `confianza = "secundaria"`, solo las claves listadas |
| `locked_fields` sin otra evidencia | `source = "desconocido"`, `locked = true`; **no** se etiqueta como manual |
| `metadata_source` de la fila | `source = metadata_source`, `confianza = "legado"`, `verificado = false` |

Reglas:

1. Un campo `legado` **no alimenta `edition_scope`** en modo automático. Se muestra como
   «origen no verificado» y solo se usa para `work_scope` si el campo es de obra y no hay conflicto.
2. `total_issues` y `end_year` actuales se revisan antes de confiar en ellos: pudieron rellenarse
   desde una edición USA.
3. El backfill es idempotente y no modifica `Series`/`Issue`; solo puebla procedencia.

---

## 5. Fases corregidas

### Fase 0 — Diagnóstico (S)

Sin cambios: comando read-only que informe de IDs, campos, roles, filas de `0032` y posibles
conflictos. No escribe.

### Fase 1 — Recolector mínimo (M)

**Alcance corregido:**

- Solo fuentes con lectura por ID ya probada para **series**: CV (`get_volume`), Tebeosfera
  (`get_collection`), GCD (`get_series`).
- Campos escalares de serie: año inicio/fin, editorial/sello, país (como metadato de payload),
  idioma, total, descripción, portada URL.
- Escribe `entity_source_records`; **no toca** `Series`/`Issue`.
- `fetch_issue`/`fetch_issues_de_serie` no forman parte de la Fase 1; se implementan por fuente en
  Fase 4.

**DoD:**

- Una fila por `(entity_type, entity_id, source, external_id)`; UPSERT idempotente por `payload_hash`.
- Un 404/429/500 o un parseo roto **no** borra el payload anterior.
- `httpx.MockTransport` cubre 200, 304, 404, 429 y HTML roto para los tres adaptadores.
- Cero escrituras en `Series`/`Issue`.

### Fase 2 — Motor, roles y backfill (M)

- `work_scope`/`edition_scope`, `rol_vinculo` explícito, `field_provenance`, `aplicador`.
- Backfill conservador de §4.
- `enricher` y SCR7 siguen funcionando; se les puede redirigir detrás de un flag cuando la CCM
  demuestre paridad. **No se retiran en esta fase.**
- La UI de roles es necesaria aquí, aunque sea mínima.

**DoD anti-Frankenstein:** una serie española con Tebeosfera `edicion_propia` y CV
`obra_referencia` no copia `end_year`/`total_issues` de CV; sí puede usar `description`/géneros de
obra si la política lo permite y no hay conflicto.

### Fase 3 — UI «Completar datos» (M)

- Vista previa, conflictos, «usar este», «mantener el mío», locks.
- `procedencia.py` lee `field_provenance`.
- Lote de solo lectura; la acción de rellenar huecos se ejecuta en segundo plano.
- GET sin red ni escrituras.

### Fase 4 — Issues (L)

- Añadir métodos por fuente: CV (`get_issue`/`find_issue`), Tebeosfera (`get_numero`), Fandom
  (`get_issue`); GCD/Metron requieren endpoint de issue nuevo; AniList y Open Library no tienen
  issue.
- Emparejamiento exacto por ID; nunca por título de número.
- `fetch_issues_de_serie` solo donde exista paginación real.
- Créditos/personajes/arcos: solo si la relación está vacía; sin procedencia de relación todavía.

### Fase 5 — ComicInfo (M)

Corregido:

- B6 **no** gestiona `Web`, `GTIN` ni `Count`. La fase incluye una ampliación explícita de
  `CAMPOS_GESTIONADOS` y sus pruebas, o el aplazamiento de esos campos.
- `Summary` solo se escribe si la procedencia es `manual` (o `comicinfo_propio`, según la regla
  vigente); una sinopsis de fuente externa no se escribe en el XML.
- La atribución de fuentes va en la UI; escribir URLs en `<Web>` es una decisión aparte con
  revisión legal.
- Cola diferida con un solo worker, advisory lock y pausa configurable; nunca dentro del POST.
- Si el archivo está compartido, ausente o cambia, se aplaza y se conserva la BD.

### Fase 6 — Edición/colecciones editoriales (decisión tomada)

El ADR [0020](../adr/0020-edicion-y-colecciones-ccm.md) decide **no crear `Edition` en este ciclo**
y **no añadir identidad externa a `collections`**. `Series` sigue siendo la unidad de catálogo; si
aparece otra edición, se crea otra `Series` y se usan los roles ya implementados. Se revisa solo si
se alcanzan los umbrales de uso del ADR.

---

## 6. Fuentes: alcance real por fase

| Fuente | Fase 1 serie | Fase 4 issue | Limitación |
|---|---|---|---|
| Comic Vine | `get_volume` | `get_issue`/`find_issue` | No edición ES; no comercial; 200/recurso/h |
| Tebeosfera | `get_collection` | `get_numero` | HTML; sin licencia abierta de fichas; cortesía |
| GCD | `get_series` | nuevo endpoint de issue | Registro/anónimo; CC BY-SA; portadas 403 |
| Metron | Fase 4 (serie + issue) | nuevo endpoint | Solo EN/IT; 20/min; CC BY-SA |
| AniList | Fase 4 (serie) | — | No hay issue |
| Open Library | Fase 4 (obra/tomo) | — | No hay issue |
| Fandom DC/Marvel | Fase 4 (serie/issue) | `get_issue` | Sin IDs formales; CC BY-SA; portadas *fair use* |

La v2 decía «8 adaptadores en Fase 1»; eso no es realista ni necesario para validar la arquitectura.
La Fase 1 se limita a tres fuentes con series y campos escalares.

---

## 7. Persistencia: qué se mantiene y qué se corrige

### 7.1 `entity_source_records`

Se mantiene la estructura de la v2, con estas precisiones:

- `payload` guarda `schema_version`, `normalizer_version`, `raw_acotado` y `normalizado`.
- `raw_acotado` tiene tope de 32 KB y se sanea antes de guardar.
- Un error de red/parseo **no** actualiza el payload; solo un `200`/`304` válido.
- `payload_hash` se calcula sobre JSON canónico, no sobre el orden de claves.
- `sugerencias_id` solo se guarda si la fuente declara un ID cruzado; no se inventa por título.

### 7.2 `field_provenance`

- `value` mantiene el formato de la v2 (`valor`, `ambito`, `external_id`, `url`, `licencia`,
  `acuerdos`, `descartados`), pero `ambito` debe ser uno de los dos valores del mapa real.
- `locked` es informativo; **la decisión se lee de `Series.locked_fields`/`Issue.locked_fields`**.
- `field` usa nombres canónicos del mapa de §2; para `gtin`, el nombre es
  `identificadores.gtin` y su valor vive en `metadata_` hasta que haya columna.

### 7.3 `metadata_`

- `vinculos_rol` (rol explícito).
- `identificadores.gtin` (solo si hay dato).
- `pais` (solo si `Publisher.country` no puede representarlo).
- `comicinfo_sync_pendiente` (marca de cola).
- `manual` y `relleno` se conservan por compatibilidad.

---

## 8. Motor de consolidación (correcciones)

Las reglas de la v2 se mantienen, con estos añadidos:

1. **Rol primero.** Si el campo es `edition_scope` y el vínculo no es `edicion_propia`, el
   candidato se descarta antes de evaluar prioridad.
2. **Legado no es fuente.** Los campos con `confianza = "legado"` no se actualizan en automático
   ni se usan para rellenar `edition_scope`.
3. **Valores actuales no verificados:** si un campo está poblado pero su procedencia es
   desconocida, se trata como «conservar»; no se pisa por una fuente externa.
4. **Fechas:** la comparación por granularidad de la v2 se acepta; no es conflicto un año frente a
   una fecha completa si son compatibles.
5. **Relaciones:** solo «vacíos» en Fase 4; no unión de créditos hasta que exista procedencia de
   relación.
6. **Descartes:** `descartados` se registra por campo/fuente/valor; si la fuente cambia el valor,
   el descarte caduca.
7. **Huella:** incluye `updated_at`, `locked_fields`, hashes de payloads y `politica_version`.
8. **Aplicación:** transacción con `FOR UPDATE`, recalcular huella y `409` si cambió.

---

## 9. Interfaz (correcciones)

- Se mantiene la sección «Completar datos» y la vista de procedencia.
- Se añade **«Rol de las fuentes»**: una lista de IDs asociados con `edicion_propia`/`obra_referencia`.
  Sin esta pantalla, la CCM no puede saber qué campos de edición puede usar.
- «Mantener el mío» escribe un descarte, no un lock; «Bloquear campo» es una acción separada.
- El lote solo rellena huecos seguros; nunca resuelve conflictos.
- No se muestra jerga `work_scope`/`edition_scope`; se usa «datos de la edición» y «datos de la obra».

---

## 10. Pruebas y aceptación corregidas

1. **Puros:** matriz de estados, mapa de ámbitos, prioridades, vocabulario y fechas.
2. **Anti-Frankenstein:** serie ES con Tebeosfera `edicion_propia` y CV `obra_referencia`; no copia
   `end_year`, `total_issues`, `publisher_id` ni `language` de CV.
3. **Rol:** sin rol explícito, todo es `obra_referencia`; un campo de edición no se rellena.
4. **Legado:** un campo `metadata_source` antiguo no se trata como verificado; no se escribe en
   `edition_scope`.
5. **Manual/lock:** ninguna combinación pisa un campo manual o bloqueado.
6. **Idempotencia:** dos recolecciones iguales no duplican filas; dos aplicaciones iguales no
   cambian nada.
7. **Errores:** 404/429/500/parseo conservan el payload anterior; no hay caché negativa falsa.
8. **GET:** cero red y cero escrituras.
9. **B6:** `Summary` externo no llega al XML; `Summary` manual sí; archivo compartido se aplaza.

No se exige «100 % de cobertura» como criterio; se exige que la matriz de casos esté cubierta.

---

## 11. Decisiones pendientes del PO

1. **`country`**: ¿`Publisher.country` es suficiente o hace falta `Series.country` (migración)?
2. **`gtin`**: ¿se queda en `metadata_` o se añade columna en una migración posterior?
3. **Roles heredados:** ¿se revisan a mano las 55 series con ID actual, o se acepta que todas
   empiecen como `obra_referencia` hasta confirmación?
4. **B6 Web/GTIN/Count:** ¿se amplía en Fase 5 o se aplaza?
5. **SCR7/enricher:** ¿se mantienen indefinidamente como fallback o se retiran tras paridad?

---

## 12. Límites de esta revisión

- No se ha implementado nada; no hay cambios de código ni de esquema.
- No se han consultado fuentes externas para esta corrección; se apoya en el código actual y en la
  medición read-only de la Pi del 2026-11-17.
- La v2 sigue siendo válida en su dirección; esta v2.1 corrige los puntos que habrían producido
  datos incorrectos o fases no ejecutables.
