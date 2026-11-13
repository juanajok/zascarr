# Referencia normalizada de series e issues — investigación y benchmark

> **Estado:** propuesta de diseño, no implementada.
> **Alcance:** nombre/referencia normalizada en la BD. **No se renombran archivos.**
> **Medición:** BD real de producción, 2026-11-12, 90 series / 2.735 issues / 5.063 archivos.
> **JSON reproducible:** [`referencia-normalizada-2026-11-12.json`](referencia-normalizada-2026-11-12.json).

## 1. La pregunta

¿Conviene tener un **nombre normalizado de cada serie y cada issue** en la BD, sin cambiar
el nombre real de los archivos, y con toda la información posible por fuente?

La respuesta corta es **sí, pero como capa de referencia derivada, no como identidad**.
La identidad sigue siendo `UUID` + IDs de fuente. El nombre normalizado sirve para buscar,
mostrar, ordenar, exportar y comparar; no para decidir que dos publicaciones son la misma.

## 2. Resumen ejecutivo

- `Series.title_norm` ya existe y cubre **90/90 series**. Es una columna generada por
  Postgres, espejo de `core.matcher.normalize_title`.
- Solo hay **una colisión** de `title_norm` en todo el catálogo: `ANIMAL MAN` (1989) y
  `Animal Man` (2011). El año las distingue.
- La normalización que **quita el volumen** (`_base_title`, usada para el matching) sí
  colapsa `Catwoman Vol. 4` y `Catwoman Vol. 5`. Por eso una referencia debe conservar el
  **título completo + volumen/edición**, no la forma sin volumen.
- Los números de issue están en formas heterogéneas: 2.648 enteros, 30 con sufijo
  (`12a`), 33 decimales (`23.1`), 21 especiales/A-E. Canonizarlos no produce colisiones
  dentro de una serie, pero **no se puede reducir todo a un entero**.
- La cobertura de identificadores externos es baja: series **40/90 con Comic Vine**, 3 GCD,
  10 Tebeosfera; issues **574/2.735 con Comic Vine** (21 %). No hay IDs GCD/Metron en
  `Issue`, y los campos bibliográficos están casi vacíos: **3 títulos de issue**,
  **0 fechas de publicación**, **0 ISBN**.
- La etiqueta textual sola no basta: sobre las 200 etiquetas humanas, un resolver
  puramente textual encuentra 125 issues exactos, pero deja **61 series ausentes** y
  **5 ambiguas**. El matcher actual, con parser + contexto + fuzzy, está en 118/118.
  El nombre referencia **no sustituye al matcher**.

## 3. Medición actual

### 3.1 Cobertura de campos

| Dato | Cobertura | Lectura |
|---|---:|---|
| Series | 90 | — |
| `Series.title_norm` | 90/90 | base de búsqueda ya existente |
| `Series.start_year` | 31/90 (34 %) | insuficiente para desambiguar volúmenes |
| `Series.sort_title` | 0/90 | sin orden bibliográfico |
| `Series.comic_vine_id` | 40/90 (44 %) | mejor fuente actual |
| `Series.gcd_id` | 3/90 | casi sin uso |
| `Series.tebeosfera_slug` | 10/90 | — |
| `Series.anilist_id` / `metron_id` / `open_library_id` | 0/90 | no hay datos |
| Issues | 2.735 | — |
| `Issue.comic_vine_id` | 574/2.735 (21 %) | cobertura baja |
| `Issue.title` | 3/2.735 | prácticamente vacío |
| `Issue.release_date` | 0/2.735 | vacío |
| `Issue.isbn` | 0/2.735 | columna sin uso |
| `Issue.metadata` | 2.735/2.735 | JSON **procedimental**, no payload de fuente |

`metadata` contiene claves de proceso (`origen`, `serie`, `fecha`, `lote`, `archivo_origen`,
`comicinfo_aplicado`), no una copia estructurada de la ficha de Comic Vine/GCD/Metron.

### 3.2 Colisiones de nombre

| Clave | Grupos en colisión | Series afectadas | Ejemplo |
|---|---:|---:|---|
| `title_norm` completa | 1 | 2 | `ANIMAL MAN` (1989) / `Animal Man` (2011) |
| `_base_title` (sin volumen) | 2 | 4 | Animal Man + `Catwoman Vol. 4` / `Vol. 5` |
| `title_norm` + `start_year` | 0 | 0 | — |
| `(series_id, número canonizado)` | 0 | 0 | — |

Conclusión: **no hace falta un nombre único global**. Hace falta conservar los
discriminadores que ya existen (año, volumen/edición) y usarlos en la referencia.
El título sin volumen es una buena clave de *matching*, pero una mala referencia de
*display*: Catwoman Vol. 4 y Vol. 5 deben verse distintas.

### 3.3 Formas del número

| Forma | Nº issues | Ejemplos |
|---|---:|---|
| Entero | 2.648 | `1`, `12`, `259` |
| Entero + letra | 30 | `12a`, `123b` |
| Decimal | 33 | `23.1`, `40.5` |
| Especial/A-E | 21 | `E1`, `A11`, `2A3` |
| Sin número | 3 | `NULL` |

Una `number_key` útil debe conservar sufijo/forma especial; el `sort_order` numérico
no puede ser la clave canónica. Esto coincide con el ADR 0003 (`number_key` texto
libre + clave canónica dentro de la edición).

### 3.4 Benchmark sobre la muestra de 200

Resolver **solo por nombre normalizado + número**:

| Resultado | Nº |
|---|---:|
| Serie única encontrada | 134/200 |
| Issue exacto encontrado | **125/200** |
| Serie ausente del catálogo | 61 |
| Serie ambigua | 5 |
| Número no existente en la serie | 9 |

El matcher actual está en **118/118** de identidad y **59,0 %** de cobertura. El
resolver textual no es un sustituto: encuentra algunos casos más porque busca sobre la
etiqueta humana, pero deja fuera 61 series que no están en catálogo. La diferencia de
125 vs. 118 mide sobre todo **presencia de catálogo y volumen**, no superioridad del
nombre normalizado.

## 4. Qué dicen los estándares y las fuentes

### 4.1 ComicInfo.xml

El esquema separa explícitamente `Series`, `Number`, `Count`, `Volume`,
`AlternateSeries`/`AlternateNumber`/`AlternateCount`, `Title`, `StoryArc`/`StoryArcNumber`,
`Publisher`, `Imprint`, `Year`/`Month`/`Day`, `LanguageISO`, `Format`, `GTIN` y los
campos de creadores, personajes, equipos, localizaciones y páginas.
Fuente: [Anansi Project / ComicInfo — Schema documentation](https://github.com/anansi-project/comicinfo/blob/99e1453a163c777b4b5320a68732f6f133ac7918/DOCUMENTATION.md).

ZascArr ya lee un subconjunto (`series`, `number`, `volume`, `year`, `publisher`,
`summary`, `tags`, `genres`, `language_iso`, `page_count`, credits). **No persiste**
`AlternateSeries`, `StoryArc`, `SeriesGroup`, `GTIN`, `Web`, `ScanInformation` ni la
procedencia por campo. Ese es el hueco más claro para una referencia completa.

### 4.2 Comic Vine

Comic Vine separa **volume** e **issue** con IDs propios, y expone `aliases`,
`site_detail_url`, `cover_date`, `store_date`, `person_credits`, `story_arc_credits`,
`image`, etc. En el esquema actual solo guardamos `series.comic_vine_id` e
`issue.comic_vine_id`; no guardamos URL, alias, fechas de fuente ni payload.
Fuente: [Comic Vine API documentation](https://comicvine.gamespot.com/api/documentation).

### 4.3 GCD, Metron y Tebeosfera

Son fuentes con identificadores propios y metadatos complementarios. GCD ya tiene
columna en `Series` pero solo 3/90; Tebeosfera 10/90. `Issue` no tiene `gcd_id` ni
`metron_id`. Metron se documenta en
[Metron API](https://metron.cloud/wiki/api/api-documentation/) y en el código se usa
como fuente CC BY-SA 4.0; GCD en [Grand Comics Database](https://www.comics.org/).
No conviene inventar una clave global de identidad: se mantienen columnas paralelas por fuente, como en `Series`.

### 4.4 Kavita / Komga

Kavita y Komga usan nombre/ComicInfo para escanear y mostrar, pero su identidad es
local; no son una autoridad bibliográfica global. Sirven como consumidores de una
referencia normalizada, no como fuente de identidad.
Fuente: [Kavita — Comic and Manga Metadata](https://wiki.kavitareader.com/guides/metadata/comics/).

### 4.5 Modelo bibliográfico

FRBR/WEMI (obra → expresión → manifestación → ítem) recuerda la separación:
la **obra** no es la **manifestación** ni el **archivo**. ZascArr ya modela algo
parecido con `Series` → `Issue` → `File`; una referencia normalizada debe nombrar
la manifestación/publicación, no el archivo.
Fuente: [IFLA — Resource and Work, Expression, Manifestation, Item](https://cdn.ifla.org/wp-content/uploads/2019/05/assets/cataloguing/isbd/OtherDocumentation/resource-wemi.pdf).

### 4.6 Referencias comparadas

Procedimiento de `docs/design/benchmark-referencias.md`: se compara el patrón, no se
copia código. Fecha de consulta: 2026-11-12.

| Referencia | Qué hace | Decisión para ZascArr |
|---|---|---|
| **ComicInfo.xml** | Separa `Series`/`Number`/`Volume`/`AlternateSeries`/`StoryArc`/`GTIN` | **Adoptar** el vocabulario y persistir más campos; no usarlo como identidad |
| **Comic Vine** | IDs separados de volume e issue, aliases, `cover_date`/`store_date` | **Adoptar** IDs y URL/procedencia; **adaptar** a columnas paralelas por fuente |
| **GCD / Metron / Tebeosfera** | Fichas e IDs propios por serie/issue | **Adoptar** IDs como evidencia; **descartar** un ID global inventado |
| **Kavita / Komga** | Escanean y muestran con nombre/ComicInfo; identidad local | **Adoptar** referencia para UI/export; **descartar** su nombre como identidad global |
| **Sonarr/Radarr** | Título normalizado como criterio de búsqueda, no de identidad | **Adoptar** la separación búsqueda/identidad; **descartar** igualar por nombre |
| **Kapowarr / Mylar3** | Gestión de metadatos de cómic y ComicInfo | **Adoptar** el patrón de campos y procedencia; no copiar implementación (GPL) |

La conclusión común: **el nombre es una etiqueta de búsqueda/referencia; la
identidad es UUID + ID de fuente**. Esto ya coincide con el ADR 0003.

## 5. Diseño propuesto

### 5.1 Principios

1. **La identidad no se toca:** `Series.id`/`Issue.id` + IDs externos únicos.
2. **El nombre nunca es único:** no se añade `UNIQUE(title_norm)` ni se usa una
   referencia textual para decidir identidad.
3. **La referencia es derivada:** se puede regenerar; no sustituye a los campos
   fuente ni a `title`.
4. **Conservar volumen/edición:** la referencia usa el título completo, no
   `_base_title`.
5. **No renombrar archivos:** `File.file_path` no cambia; la referencia es para
   UI, búsqueda, exportación y parcheo de `ComicInfo.xml` sobre copias.

### 5.2 Series

Campos/campos derivados propuestos:

| Campo | Tipo | Uso |
|---|---|---|
| `title` | texto actual | título editorial fuente |
| `title_norm` | ya existe, generado | búsqueda; **no único** |
| `sort_title` | texto | orden bibliográfico; rellenar |
| `start_year` / `end_year` | entero | discriminador de volumen; rellenar |
| `volume` o `edition_id` | entero/UUID | volumen/edición real (ADR 0003); no confundir con `Issue.volume` |
| `reference_name` | generado/materializado | `Batman (1940) Vol. 1`; no único |

Formato humano sugerido:

```
Batman (1940) Vol. 1
Catwoman Vol. 4 (2011)
Flash Especial 50 Aniversario (1987)
```

La clave de máquina (`series_key`) puede ser `normalize_title(title) + año + volumen`,
pero **solo para índices/búsqueda**, nunca para identidad.

### 5.3 Issues

| Campo | Tipo | Uso |
|---|---|---|
| `issue_number` | texto actual | literal |
| `number_key` | texto generado | entero/sufijo/decimal/especial, dentro de la edición |
| `title` | texto | título del número (hoy 3/2.735) |
| `release_date` | fecha | fecha de portada/publicación (hoy 0) |
| `isbn` / `gtin` | texto | ISBN/GTIN cuando exista; hoy 0 |
| `reference_name` | generado/materializado | `Batman (1940) Vol. 1 #25` |

La `reference_name` de un issue sin número (especial, tomo, pack) **no inventa un
número**: usa el título editorial o queda como referencia de archivo.

### 5.4 IDs externos y procedencia

**Decisión: mantener el principio del proyecto de IDs en columnas paralelas**, no
sustituirlo por una clave global acoplada a una fuente (CLAUDE.md §12). Ya existen en
`Series`: `comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`, `metron_id`,
`open_library_id`. `Issue` solo tiene `comic_vine_id`; el hueco se cubre **añadiendo
columnas paralelas** para las fuentes que realmente se usen:

```text
issues.comic_vine_id  (ya existe)
issues.gcd_id         (nuevo, único)
issues.metron_id      (nuevo, único)
issues.anilist_id     (nuevo, único, si aplica a manga)
issues.tebeosfera_slug(nuevo, único, si aplica)
```

Cada columna es opcional y única por fuente, igual que en `Series`. No hay una
tabla genérica de identidad ni una «clave global». Si en el futuro una misma entidad
necesita **varios IDs de la misma fuente** (por ejemplo, reediciones), se estudiaría
una tabla de IDs como extensión, no como sustituto; hoy no hace falta.

Para guardar la ficha completa y su procedencia se propone una tabla de **payloads**,
que no es identidad:

```text
entity_source_records:
  id UUID PK
  entity_type   enum('series','issue')
  entity_id     UUID
  source        varchar
  external_id   text          -- copia del ID de la columna paralela, para consulta
  source_url    text
  payload       JSONB         -- ficha normalizada de la fuente
  payload_hash  text
  fetched_at    timestamptz
  license       text
  INDEX(entity_type, entity_id, source)
```

No sustituye a `metadata` (procedimental); guarda el **payload de fuente** y su
procedencia. Es la base para “toda la info posible por fuente”. Los datos de CV/GCD/
Metron/Tebeosfera conservan su atribución y no se presentan como datos propios.

### 5.5 Procedencia por campo

`Series.metadata_source`/`Issue.metadata_source` son un único valor por fila. Para
“toda la info posible” hace falta saber **de dónde salió cada campo**. Opciones, de
menor a mayor coste:

1. `metadata["procedencia"]` JSONB por campo (sin migración; suficiente para el piloto).
2. Tabla `field_provenance(entity_type, entity_id, field, source, value, retrieved_at,
   locked)` para consultas y auditoría.

Se puede empezar por la opción 1 y promover a tabla si el benchmark de fuentes lo
justifica. `locked_fields` sigue mandando: una fuente nunca pisa un campo bloqueado.

### 5.6 Alias

- Mantener `local_aliases` como alias local aprendido.
- Añadir alias canónicos/importados con `scope_path`, estado y procedencia
  (ya existe `AliasImportado` para el inventario).
- La referencia normalizada no debe convertir un alias en identidad.

### 5.7 Archivos

- `File.file_path` se conserva.
- `File` puede tener `reference_label`/`comicinfo_proposed` para UI y exportación.
- El export a Kavita/ComicInfo usa la referencia y el payload fuente, pero escribe
  **solo sobre copia**, nunca sobre el archivo canónico.

## 6. Benchmark propuesto

### Fase 0 — Línea base (hecha)

- 90 series, 2.735 issues.
- Muestra 200: parser 192/197/192; matcher 118/118; cobertura 59,0 %.
- Cobertura externa y colisiones de §3.

### Fase 1 — Referencia derivada

- Añadir `number_key`, `reference_name` y `Series.start_year/sort_title`.
- Backfill de referencia; **sin cambiar matcher ni identidad**.
- Medir:
  - cobertura de `reference_name`;
  - colisiones de referencia con año/volumen/edición;
  - latencia de generación y tamaño;
  - regresión de tests actuales.
- Criterio de éxito: 0 colisiones en el catálogo actual; 100 % de references
  no vacías; matcher sin cambios.

### Fase 2 — Resolver offline

- Sobre las 200 etiquetas, resolver solo con `reference_name` + número.
- Comparar contra matcher actual:
  - precisión/recall de identidad;
  - series ausentes/ambiguas;
  - falsos positivos.
- La referencia solo puede **proponer candidato**; nunca confirmar sin revisión.
- Criterio: no aumentar falsos positivos; medir el hueco real de catálogo.

### Fase 3 — IDs y payloads de fuente

- Backfill CV/GCD/Metron/Tebeosfera por prioridad y tradición.
- Medir cobertura por fuente y por tradición; coste/rate limits.
- Medir si un ID externo reduce ambigüedad sin fuzzy.
- Criterio: cada issue enlazado tiene al menos una evidencia de identidad
  (UUID/ID fuente), no solo un nombre.

Métricas a registrar:

```
reference_coverage_series, reference_coverage_issues
reference_collision_groups
external_id_coverage_series, external_id_coverage_issues
resolver_precision, resolver_recall, resolver_ambiguous, resolver_false_positive
catalog_absent_series, catalog_absent_issues
enrichment_requests, enrichment_failures, enrichment_latency
```

## 7. Riesgos

- **Nombre como identidad falsa:** dos tomos/volúmenes con el mismo título. Mitigación:
  UUID + IDs + volumen/año; nombre solo referencia.
- **Pérdida de volumen:** usar `title_norm` completa y edición; no `_base_title` para
  display.
- **Año ausente:** 59/90 series sin `start_year`; la referencia puede quedar ambigua.
  Rellenar desde carpeta/fuente.
- **Datos de fuente incompletos:** CV 21 % de issues; GCD/Metron casi cero. No prometer
  cobertura que no existe.
- **Licencias/rate limits:** Comic Vine, GCD, Metron, Tebeosfera; guardar URL/atribución
  y respetar condiciones.
- **Migración:** columnas de IDs paralelas, tabla de payloads y columnas derivadas; hacerlo aditivo y reversible.
- **Sobreingeniería:** no crear una entidad “obra” ni un identificador inventado.

## 8. Recomendación

**Sí a la vía**, en tres pasos:

1. **Ahora:** `number_key` + `reference_name` derivados + completar
   `start_year`/`sort_title`/volumen. Sin tocar identidad ni archivos.
2. **Después:** columnas paralelas de IDs en `Issue` + `entity_source_records` + procedencia
   por campo; backfill CV/GCD/Metron/Tebeosfera.
3. **Solo entonces:** resolver/benchmark con referencias como candidatas; el matcher
   sigue siendo la autoridad de identidad.

El benchmark actual no justifica reemplazar el matching por nombres. Justifica
**enriquecer y normalizar la referencia** para que la ficha, la búsqueda, el export y
la comparación entre fuentes sean coherentes, y para que la identidad tenga más
evidencia que un título.

## 9. Evidencia

- JSON del benchmark: [`referencia-normalizada-2026-11-12.json`](referencia-normalizada-2026-11-12.json).
- ADR relacionado: [`0003-identidad-editorial.md`](../adr/0003-identidad-editorial.md).
- Alias de catálogo: [`alias-catalogo-2026-11-11.md`](alias-catalogo-2026-11-11.md).
- Fuentes citadas:
  - [ComicInfo schema](https://github.com/anansi-project/comicinfo/blob/99e1453a163c777b4b5320a68732f6f133ac7918/DOCUMENTATION.md)
  - [Comic Vine API](https://comicvine.gamespot.com/api/documentation)
  - [Kavita metadata](https://wiki.kavitareader.com/guides/metadata/comics/)
  - [Metron API](https://metron.cloud/wiki/api/api-documentation/)
  - [GCD](https://www.comics.org/)
  - [IFLA FRBR/WEMI](https://cdn.ifla.org/wp-content/uploads/2019/05/assets/cataloguing/isbd/OtherDocumentation/resource-wemi.pdf)
  - [Diamond UPC guide](https://www.diamondcomics.com/SiteData/Downloads/UPCGuide%20forComics10-15.pdf)

## 10. Implementación fase 1 (2026-11-12)

Ya implementado en la migración **0030**:

- `series.volume` (smallint, aditivo).
- `series.reference_name`: generado con `f_series_reference(title, start_year, volume)`.
- `issues.number_key`: generado con `f_number_key(issue_number)`; conserva sufijos,
  decimales y especiales, y elimina ceros a la izquierda.
- Vista `v_issue_reference`: referencia de issue (`serie #número`), usando la
  referencia de serie y `number_key`.
- Índice `ix_issues_series_number_key` (no único).
- Relleno de `sort_title` y de `volume` cuando el título lo declara.

No cambia el matcher, la identidad ni el nombre de los archivos. Los tests de
Postgres cubren `001`, `000`, `012a`, `023.1`, `023.1a`, `E1`, `2A3`, espacios,
vacío/NULL, año/volumen y la vista de issue.

Pendiente de fase 1:

- `start_year` se rellena desde fuente/carpeta, no se deduce en la migración.
- La UI/consumidores aún no pintan `reference_name`; el dato ya está disponible
  en la BD para la siguiente entrega.

## 11. Implementación fase 2 y UI (2026-11-12)

### IDs externos por issue

Migración **0032** (aditiva, después de `0031_colecciones`):

- `issues.gcd_id`, `issues.metron_id`, `issues.anilist_id`, `issues.tebeosfera_slug`:
  columnas paralelas por fuente, opcionales y únicas. Se mantiene el principio
  del proyecto de no crear una clave global de identidad.

### Payloads y procedencia

- `entity_source_records`: payload normalizado de una fuente con `source_url`,
  `payload_hash`, `license` y `fetched_at`; no es identidad.
- `field_provenance`: origen del último valor de un campo, con `locked`.
- Sin FK polimórfica: `entity_type` limitado por CHECK a `series`/`issue`.
- Sin backfill automático: las fuentes rellenan estas tablas cuando enriquecen.

### UI

- La ficha de serie muestra `series.reference_name`.
- La ficha de número muestra `series.reference_name #issue.number_key`
  (o el título si no hay número). Ambas son derivadas: si faltan, se muestra
  el título de la serie.

### Tests

- `tests/test_referencia_fase2_pg.py`: columnas, unicidad, CHECK, payloads y
  procedencia.
- Tests de fase 1 y suite de fichas en verde.
