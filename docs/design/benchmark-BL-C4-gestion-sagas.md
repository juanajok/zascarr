# BL-C4 (#151) — benchmark y especificación: gestionar sagas a mano

> **Método:** lectura de documentación/código público de referencias; **NOT RUN** sobre las apps.
> El objetivo es una pantalla propia para crear, editar y ordenar sagas que cruzan series, no
> importar arcos desde una fuente.

## Referencias

| Referencia | Patrón observado | Veredicto |
|---|---|---|
| **Sonarr/Radarr** | Formulario de edición con guardado único, validación y confirmación de borrado | **Adoptar** el formulario propio y el guardado único |
| **Komga** | Listas de lectura propias: alta, edición, borrado y orden de elementos; no tocan los archivos | **Adaptar** a sagas con `reading_order` |
| **Kavita** | Colecciones/listas de lectura con gestión desde la UI | **Adaptar**; el coleccionista no debe tocar la BD |
| **Mylar3/Kapowarr** | Edición de metadatos de cómic/número y relaciones | **Construir sobre lo propio** (`story_arcs`/`story_arc_issues` ya existen) |
| Arrastrar y soltar / JS nuevo | Cómodo, pero añade dependencia y no es accesible sin JS | **Descartar**: subir/bajar con botones |
| Crear/editar arcos desde Comic Vine | Automatiza el alta, pero no existe hoy y mezcla dos responsabilidades | **Fuera** de esta historia |

## Contrato

- **Alta:** título obligatorio (≤500), descripción (≤10000), marca crossover.
- **Modificar:** los mismos campos; no cambia `reading_order` salvo que se use la gestión de números.
- **Baja:** se elimina la saga y sus vínculos; **no** se borran números, archivos ni series.
- **Añadir número:** serie por título exacto (o id), número dentro de esa serie y posición opcional;
  se inserta y se desplazan las posiciones. Duplicado → error claro.
- **Quitar número:** elimina solo el vínculo y renumera 1..N.
- **Reordenar:** subir/bajar un número intercambiando `reading_order` con su vecino.
- Sin migración; todas las escrituras son de esta app y no tocan la biblioteca.

## Criterios

- Un arco cruzado conserva el orden manual.
- Borrar una saga no borra `Issue` ni `File`.
- Errores de validación/dato se muestran en el formulario, sin 422 crudo y conservando lo escrito.
- Pruebas PG y web; mensajes en español.
