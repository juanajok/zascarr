# Especificación — BL-INF5 (#591): edición manual de metadatos

## Rutas

- `GET /ui/series/{id}/editar`: formulario de serie.
- `POST /ui/series/{id}/editar`: valida y guarda; error → mismo formulario con valores y mensajes.
- `POST /ui/series/{id}/editar/desbloquear/{campo}`: quita bloqueo y marca manual, conserva valor.
- `GET /ui/series/{id}/numero/{issue_id}/editar`: formulario de número.
- `POST /ui/series/{id}/numero/{issue_id}/editar`: valida y guarda.
- `POST /ui/series/{id}/numero/{issue_id}/editar/desbloquear/{campo}`: igual para número.

## Datos

Serie: `title` (obligatorio, ≤500), `start_year`/`end_year` (1000–9999, inicio ≤ fin si ambos),
`publisher` (≤255, se busca por nombre; si no existe se crea), `description` (≤10000),
`total_issues` (entero ≥0).
Número: `issue_number` (≤20, obligatorio), `title` (≤500), `release_date` (AAAA-MM-DD o vacío),
`format` (enum `IssueFormat`), `synopsis` (≤10000).

## Efectos

- Solo los campos que cambian se marcan manuales y se añaden a `locked_fields`.
- `metadata_` se reemplaza por un dict nuevo con `manual[campo] = {"fecha": ...}`; se preserva el
  resto de metadatos.
- `metadata_source` no cambia.
- No se tocan archivos, rutas, relaciones ni recuentos almacenados.
- Al cambiar `issue_number`, `sort_order` se recalcula a partir del primer número decimal/entero;
  si no es numérico, queda `None`. Los huecos se derivan de `Issue.issue_number` y `format`, así
  que no hay que recalcular una tabla.
- Colisión: `(series_id, issue_number, volume)` con otra fila → error en `issue_number`, sin guardar.
- Éxito → 303 a la ficha con `?guardado=serie` o `?guardado=numero`; aviso verde.
- Formulario propio, sin diálogos nativos; garantía «Solo cambia lo que ves en ZascArr; tus
  archivos no se tocan» junto al botón.

## Fuera

Crear números/series, escribir ComicInfo, cambiar identidad externa, editar autores/etiquetas,
borrar valores de la fuente. Sin migración.
