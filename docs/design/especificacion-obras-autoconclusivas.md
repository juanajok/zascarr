# Especificación — obras autoconclusivas (one-shot) y publicaciones sin numeración

> **Estado:** v1.0 **aceptada por el PO** (2026-11-17). Acompaña al
> [ADR 0022](../adr/0022-obra-autoconclusiva.md) (**Aceptado**). Autoriza la implementación del
> primer corte (modelo/dominio/alta/UI); ComicInfo y backfill quedan fuera de este corte.
> Base: `origin/main` `b26d5dad`. Lo que no se ha medido va como **NOT RUN**.

## 1. Alcance

**Dentro:**

- Obra autoconclusiva/novela gráfica/álbum único/manga de un tomo/one-shot **sin serie numerada**:
  una `Series` con `kind=one_shot` y **una** publicación.
- Completitud y estado de colección de esa serie: completa con una publicación, sin huecos, sin
  wishlist de faltantes/futuros ni seguimiento de novedades.
- Alta/edición: crear la serie one-shot y su publicación sin inventar números; badge y ficha
  unificada; filtro del selector de series.
- ComicInfo de una obra one-shot (fase posterior a la decisión de modelo).

**Fuera:**

- Integrales/omnibus de una serie regular: son **edición/recopilación**, no one-shot; su modelo
  depende de la entidad *Edición* (ADR 0003, #125/#126).
- Anuales y especiales ligados a una serie: el anual sigue como `Series.kind=annual` +
  `parent_series_id`; el especial sin número sigue el ADR 0016.
- Series publicadas en tomos numerados: son series normales con `Issue.format` de tomo.
- Cajón de sastre, `edition_type` y `es_obra_unica`: descartados en el ADR.
- Backfill masivo de la biblioteca existente (decisión abierta; si se acepta, será otro corte).

## 2. Modelo propuesto (sin migración todavía)

### 2.1. Esquema

- **`Series.kind`**: nuevo valor `ONE_SHOT = "one_shot"` en `SeriesKind` (enum `series_kind`).
  No se añade columna nueva. `Series.edition_kind` **no se toca**: significa otra cosa
  (`oficial`/`tradumaqueta`/`escaneo_propio`/`otro`).
- **`Issue`**: sin columnas nuevas. `issue_number` ya es nullable; `format` ya existe. No se crea
  `Issue.tipo`.
- **`Collection`**: sin cambios; agrupa series para estanterías.
- **Migración 0049** (condicional): `ALTER TYPE series_kind ADD VALUE IF NOT EXISTS 'one_shot'`;
  sin DML, sin backfill y sin usar el valor en la misma transacción. `down_revision=0048`.
  `downgrade` documenta que el valor del enum no se puede retirar sin recrear el tipo; no borra
  filas.

### 2.2. Invariantes

1. `Series.kind=one_shot` ⇒ **una sola publicación** (`Issue`) en la práctica. La UI/servicio
   impide crear una segunda; no se añade una restricción SQL en v1 (los archivos múltiples de la
   misma publicación —variantes, calidad— siguen siendo `File` de ese `Issue`).
2. `Issue.issue_number`:
   - se copia el número de la fuente **solo si la fuente lo da**;
   - si no, `NULL` (ADR 0016), con `title` no vacío y `format` distinto de `single_issue`;
   - **nunca** se inventa `#1` por defecto.
3. `total_issues`:
   - puede guardarse `1` como dato de presentación, pero **no** es la base de la completitud;
   - la completitud de one-shot no llama a `compute_missing_issues`.
4. `Series.kind=one_shot`:
   - no se ofrece a «completar faltantes», «futuros» ni seguimiento de novedades;
   - puede pertenecer a N `Collection` (estanterías);
   - no se confunde con una serie abierta de un solo número: la marca es explícita.
5. Un one-shot **no** se convierte automáticamente por `total_issues == 1` ni por el nombre del
   archivo; la marca la decide el coleccionista.

## 3. Contratos y cambios por capa

### 3.1. Dominio — huecos, estado y política

- `services/series.py::numero_de_grapa` **no cambia** para series normales.
- `razon_de_no_calculable`/`huecos_de_serie`: si `series.kind == ONE_SHOT`, devolver un resultado
  «completo» sin huecos cuando hay una publicación con archivo disponible (o publicación
  vinculada, según el flujo); si no hay publicación, estado «sin publicación», no un hueco `#1`.
  No usar `total_issues` para one-shot.
- `services/coleccion.py` y `condicion_estado_coleccion`: tratar `ONE_SHOT` como completo/no
  computable por grapas, sin `1/1` ni «faltan N».
- `services/politica.py::querer_de_serie`: `ONE_SHOT` devuelve conjunto vacío y motivo «obra
  autoconclusiva»; nunca genera deseos. El flag de seguimiento de novedades se deshabilita en UI y
  servicio para one-shot.
- `services/inicio.py`/recuentos: no sumar one-shot en «series que completar» ni en faltantes.

### 3.2. Alta y UI

- **Alta desde Pendientes/archivo** (tres opciones explícitas):
  1. «Tomo único / novela gráfica / one-shot»: abre el formulario de serie one-shot (título limpio,
     tradición, formato de publicación) y crea la serie + su publicación; si no hay número de
     fuente, `issue_number=NULL`.
  2. «Pertenece a una serie numerada»: flujo actual.
  3. «Especial o anual de una serie»: flujo ADR 0016 o anual con `parent_series_id`.
- **No se reutiliza** el campo `edition_kind` para el tipo; no se pide «número» en la opción
  one-shot.
- **Ficha**: badge «Tomo único / Novela gráfica / Integral» según `Issue.format`; no anteponer
  `#1`; vista combinada serie+publicación.
- **Selector de series al importar**: one-shot ocultos por defecto; interruptor «Mostrar también
  tomos únicos» para casos de reemplazo. No se ocultan de la biblioteca ni de búsquedas.
- **`Collection`**: se puede añadir un one-shot como miembro; no se altera su identidad.
- **Accesibilidad**: labels, focus y 320 px según el sistema de diseño; el badge no sustituye al
  nombre de la serie.

### 3.3. ComicInfo (fase posterior; no en el primer corte)

- B6 actual (`core/comicinfo_write.py::CAMPOS_GESTIONADOS`) **no** escribe `Count`, `Format` ni
  `SeriesGroup`. Para one-shot se propone añadir al plan:
  - `<Series>`: título de la obra (el de la serie);
  - `<Count>`: `1`;
  - `<Format>`: mapa desde `Issue.format` (`Graphic Novel`, `One-Shot` si se decide, `TPB`, `HC`,
    `Omnibus`; `single_issue` no aplica);
  - `<Number>`: solo si `issue_number` no es NULL;
  - `<SeriesGroup>`: **fuera de v1** (ver ADR; una `Collection` puede tener varias franquicias).
- Requiere actualizar el contrato B6, la previsualización y las pruebas (ida/vuelta con Komga/
  Kavita) en una historia propia; no se promete en este corte.

## 4. Criterios de aceptación (semilla)

- **AC-1**: el alta permite marcar una serie como one-shot sin pedir número y sin crear un `#1`
  inventado.
- **AC-2**: una serie one-shot con una publicación con archivo se muestra completa, sin huecos,
  sin «faltan N» y sin entrar en wishlist de faltantes/futuros.
- **AC-3**: una serie one-shot sin publicación se muestra «sin publicación», no «falta el #1».
- **AC-4**: `querer_de_serie` no genera deseos y el seguimiento de novedades está deshabilitado
  para one-shot.
- **AC-5**: el selector de series oculta one-shot por defecto y los muestra con el interruptor;
  no se ocultan de la biblioteca.
- **AC-6**: badge/ficha sin `#1` artificial cuando el número es NULL; con número de fuente, se
  muestra sin convertirlo en una serie numerada.
- **AC-7**: un anual sigue como `Series.kind=annual` + parent; un especial sin número sigue ADR
  0016; no se convierten a one-shot.
- **AC-8**: un integral/omnibus no se marca one-shot por esta vía.
- **AC-9**: migración 0049 aditiva, sin backfill, con downgrade documentado; las instalaciones
  existentes no cambian.
- **AC-10**: pruebas unitarias, PG real de la migración y regresión de huecos/colección/política;
  NOT RUN del navegador hasta la fase UI.

## 5. Casos límite

- Serie abierta con un solo número: **no** es one-shot; el usuario puede marcarla, pero es una
  decisión explícita y reversible.
- Varias copias/calidades del mismo one-shot: `File` múltiples sobre el **mismo** `Issue`; no
  crean una segunda publicación.
- Obra one-shot que pertenece a una franquicia: `Collection` para agrupar; no `parent_series_id`
  (reservado a anuales/relación de presentación).
- Serie que después recibe más publicaciones: cambiar `kind` a `regular` y revisar huecos; no se
  hace automáticamente (evita romper completitud).
- `issue_number` con número de fuente no entero (`Annual`, `1.5`): one-shot solo si de verdad es
  una obra única; si es una línea, no es one-shot.
- Obras ya catalogadas con `total_issues=1`: no se convierten; decisión abierta de backfill.

## 6. Pruebas

- Puro: `razon_de_no_calculable`/`huecos_de_serie`/`compute_missing_issues` con `ONE_SHOT`.
- PG: migración 0049 subir/bajar; columna/enum; integridad de `Series.kind`.
- Servicios: `querer_de_serie`, `coleccion.py`, `condicion_estado_coleccion`, `inicio` con
  one-shot.
- UI: alta de las tres opciones, badge, selector/filtro, ficha y 320 px; foco/labels.
- ComicInfo: fase aparte; tests de plan y XML de ida/vuelta.
- Regresión: series normales, anuales, especiales ADR 0016 y huecos intactos.

## 7. Plan de entrega (una vez aceptado el ADR)

1. **Datos**: migración 0049 + modelo/enum; tests PG. Sin backfill.
2. **Dominio**: completitud/política/colección; tests puros y PG.
3. **Alta/UI**: tres opciones, badge, ficha, filtro; navegador real y 320 px.
4. **ComicInfo**: contrato B6 y pruebas de interoperabilidad (historia aparte).
5. **Backfill** (si el PO lo aprueba): dry-run, informe y confirmación; migración de datos
   separada; nunca automático.

## 8. Riesgos

- Convertir una serie abierta de un número en one-shot oculta un hueco real; por eso la marca es
  explícita y reversible.
- Una `Series` one-shot con `total_issues=1` y formato no-grapa seguiría produciendo hueco falso
  si algún camino no usa la nueva regla de completitud; hay que cubrir todos los consumidores
  (`huecos`, `coleccion`, SQL de estado, inicio, política).
- No hay entidad *Edición*; los integrales siguen sin modelo propio. No forzar one-shot para
  taparlo.
- El selector ocultando one-shot puede impedir reemplazos; el interruptor debe ser visible y
  probado.
- ComicInfo se retrasa: no se promete compatibilidad perfecta con Komga/Kavita hasta la fase 4.

## 9. Decisiones aceptadas (PO 2026-11-17)

1. **`SeriesKind.ONE_SHOT`** y número solo si la fuente lo da; si no, `NULL`.
2. Ficha **«Tomo único · completo» sin cifras de grapa**.
3. **Integrales/omnibus fuera** hasta la entidad *Edición*; no se marcan one-shot.
4. **`SeriesGroup`** en ComicInfo **pospuesto** a ETQ6/B6.
5. **Sin backfill** en v1; un dry-run separado si se decide.

**NOT RUN:** censo de series con `total_issues=1`; navegador real; migración; ComicInfo. Nada de
esto se implementa antes de la aceptación del ADR 0022.
