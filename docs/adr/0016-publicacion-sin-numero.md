# ADR 0016: Publicación sin número para especiales y tomos sueltos

## Estado

**Propuesto** — 2026-11-11. Prototipo backend en `services/especiales.py`
(3 tests PG) y acción HTMX en Pendientes; **sin migración y sin cambios en
producción**. La acción solo aparece en los resultados de búsqueda de serie.

## Contexto

La biblioteca tiene archivos que son una publicación real pero **no tienen un
número editorial deducible del nombre**:

- `Bad Weekend - Criminal` (especial/spin-off).
- `Lobo - Año 1`.
- `Lazarus - X+66` (tomo).
- `22.1 Catwoman Vol 02 Year One (1995)` (archivo mal nombrado; la etiqueta
  humana dice `Catwoman Annual #2`).

Hoy `File.issue_id` es la única relación con el catálogo. `Issue.issue_number`
**ya es nullable** (`models/__init__.py`), pero:

- `ReviewService.assign_to_series` rechaza un número vacío;
- no hay flujo de UI para crear un especial sin número;
- el matcher no debe crear este Issue automáticamente.

La alternativa `files.series_id` para archivos sin Issue se propuso antes, pero
duplicaría la relación publicación↔archivo y obligaría a otra migración.

## Decisión

1. **Un especial/tomo sin número se representa con un `Issue` normal cuyo
   `issue_number` es `NULL`.** Es una publicación identificable por su título
   y formato, no un número inventado.
2. El Issue exige en la práctica:
   - `title` no vacío (p. ej. `Bad Weekend`, `Año 1`, `X+66`);
   - `format` distinto de `single_issue` cuando la persona lo declare
     (`graphic_novel`, `trade_paperback`, `hardcover`, `omnibus`);
   - `metadata_ = {"sin_numero": true, "origen": "manual"}`;
   - `locked_fields` protege la identidad creada a mano.
3. El enlace es **manual** desde Pendientes. El matcher nunca crea ni enlaza
   automáticamente un Issue sin número.
4. No se añade `files.series_id` en esta entrega. Un archivo sin publicación
   sigue en Pendientes; si en el futuro se quiere enlazar a nivel de serie para
   packs/desconocidos, será otra decisión con su propia migración.
5. La unicidad existente `(series_id, issue_number, volume)` permite varios
   `issue_number IS NULL` en Postgres; no hace falta cambiar el esquema.

## Consecuencias

- **Sin migración**: `issue_number` ya admite NULL.
- Hay que añadir un camino de servicio (p. ej. `AsignacionService` o un método
  específico de revisión) que cree el Issue sin número y enlace el archivo.
- La UI de Pendientes necesita una acción explícita: título + formato, nunca un
  número inventado.
- Los cálculos de huecos deben ignorar Issues con `issue_number IS NULL` (ya
  hay `numero_de_grapa`/filtros que lo hacen; verificar todos).
- La ficha muestra `(sin número)` en los sitios que ya contemplan NULL.
- Los Issues sin número no cuentan como grapa ni como hueco.

## Alternativas descartadas

- **`files.series_id`**: útil para archivos sin publicación, pero no para este
  caso: aquí sí hay una publicación (un especial/tomo). Añade otra relación y
  otra migración.
- **Inventar `#1`**: rompe identidad, huecos y orden; es exactamente lo que se
  evitó en el alta manual.
- **Dejarlo todo en Pendientes**: no permite ni siquiera decir «esta serie ya
  tiene este especial».

## Plan de implementación

1. Servicio de alta/asignación de especial sin número, con transacción y tests.
2. Acción HTMX en Pendientes: «vincular como especial», título y formato.
3. Tests de: dos especiales null en la misma serie, huecos, ficha y matcher que
   no lo crea solo.
4. Documentar la excepción `Catwoman 22.1` (archivo mal nombrado).
5. No tocar los datos de la Pi hasta revisar el flujo en local.
