# Benchmark — editar metadatos a mano (BL-INF5, #591)

> Ficha §13 para comportamiento nuevo P1. **Método:** lectura de documentación pública y de código
> de referencias; no se han ejecutado Sonarr/Radarr/Kavita/Komga/Mylar3/Kapowarr ni se ha tocado
> una biblioteca real. **NOT RUN** donde no hay evidencia ejecutada.

## 1. Problema local

Un coleccionista necesita corregir título, años, editorial, sinopsis, total de números y datos de
un número cuando las fuentes no los tienen o están mal. Hoy la ficha enseña lo que hay, pero no
hay formulario de edición; el enriquecimiento puede revertir cambios y la tabla de procedencia no
distingue «lo escribí yo» de «lo trajo una fuente». La historia pide **procedencia y bloqueo por
campo**, no cambiar `metadata_source` de toda la serie.

## 2. Referencias

| Referencia | Qué se ha mirado | Patrón útil | Límite |
|---|---|---|---|
| **Sonarr** | Edición de serie y de episodio; formulario propio, guardar único, validación; los metadatos automáticos no deben pisar una decisión manual sin avisar | Formulario de edición claro, guardado único, validación antes de persistir | Su modelo de «refresh» y perfiles no aplica a cómic |
| **Radarr** | Edición de película; campos de metadatos y guardado | Mismo patrón de formulario y aviso de guardado | No tiene identidad editorial por número |
| **Kavita** | Edición de metadatos de serie/volumen | Campos de serie y número en una pantalla; no hay que tocar archivos | No ofrece bloqueo por campo ni procedencia |
| **Komga** | Edición de metadatos de serie/libro | Formulario único; valores actuales precargados | Sin procedencia por campo |
| **Mylar3** | Edición de cómic/número | Editar datos del cómic y del número sin mover archivos | Sin bloqueo por campo; su modelo es otro |
| **Kapowarr** | Edición de volumen/número | Formulario de metadatos y guardado directo | Sin procedencia por campo |

**Decisiones del benchmark:**

| Idea | Veredicto |
|---|---|
| Formulario propio con un único **Guardar** y cancelar | **Adoptar** (Sonarr/Radarr/Komga/Kavita) |
| Precargar valores actuales y validar antes de guardar | **Adoptar** |
| No mover, renombrar ni escribir archivos al editar metadatos | **Adoptar** (todas) |
| Procedencia por campo y bloqueo individual | **Construir sobre lo propio** (#127 ya tiene procedencia; se amplía) |
| Cambiar `metadata_source` de toda la serie al editar | **Descartar**: falsearía la procedencia de los demás campos |
| Escribir `ComicInfo.xml` al guardar | **Descartar** en esta historia (#480/B6) |
| Crear números o series desde cero | **Descartar**: historia aparte |

## 3. Contrato propuesto

- `Series.metadata_["manual"][campo] = {"fecha": ISO-8601}` y `Series.locked_fields` incluye el
  campo. No se cambia `metadata_source`.
- `Issue.metadata_["manual"][campo] = {"fecha": ISO-8601}` y `Issue.locked_fields` incluye el campo.
- Desbloquear elimina la marca y el bloqueo, **sin borrar el valor actual**: el enriquecimiento
  vuelve a poder proponer.
- Series: `title`, `start_year`, `end_year`, `publisher`, `description`, `total_issues`.
- Número: `issue_number`, `title`, `release_date`, `format`, `synopsis`.
- La tabla de procedencia muestra «Editado a mano»/Manual y un enlace «Volver a la fuente» por
  campo.
- Validación: años numéricos y coherentes; total ≥ 0; longitudes; colisión de número
  `(serie, número, volumen)` explicada; al cambiar el número se recalcula `sort_order`.
- Sin migración.

## 4. PASS / FAIL / NOT RUN

- **PASS (lectura):** las referencias usan formulario propio, guardado único y no tocan archivos
  para editar metadatos; ZascArr ya tiene procedencia y `locked_fields` que se pueden reutilizar.
- **FAIL:** ninguna referencia cubre exactamente «bloqueo por campo con procedencia manual»; se
  construye sobre lo propio (§12 de CLAUDE.md).
- **NOT RUN:** ejecución de las referencias, navegador real, Pi y validación con personas.

## 5. Criterio de hecho

Formularios de serie y número, procedencia/bloqueo por campo, validaciones y colisión, aviso de
guardado, pruebas PG/web y documentación. Sin migración ni escritura de archivos.
