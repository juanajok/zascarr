# B20 (prerequisito): Exportación de colección → carpeta compatible con Kavita

**Estado:** diseño fijado, pendiente de implementación
**Origen:** análisis de la biblioteca real de TV del coleccionista (Sonarr, 2026-09-26) — la carpeta de serie es la unidad portable
**Relación:** habilita B14 (la carpeta exportada es un árbol limpio donde el contexto de carpeta existe) y B22/B23 (el formato de exportación es el contrato de lectura)

## 1. Objetivo

Volcar una colección de la biblioteca canónica de ZascArr a un árbol nuevo, legible por Kavita, **sin modificar el origen**. La biblioteca canónica sigue siendo la única fuente de verdad; la exportación es una vista derivada.

## 2. Estructura de destino

```
<raiz_exportacion>/                          # elegida por el usuario (p. ej. /media/Kavita/)
└── Dinastía Vázquez [Brekte Boom y Don Bowich]/    # series_name, sanitizado para FS
    ├── Dinastía Vázquez 01 - Brekte Boom y Don Bowich.cbz
    ├── Dinastía Vázquez 02 - Brekte Boom y Don Bowich.cbz
    └── Dinastía Vázquez 03 - Picos de Virub.cbz
```

Reglas:

- La taxonomía canónica (`Género/Colección/`) se **aplana**: en la exportación, la carpeta de colección va directamente bajo la raíz. Kavita trata cada carpeta con cómics como una serie; los géneros no le aportan.
- El nombre de la carpeta de serie es el `series_name` ya normalizado (incluye corchetes de volumen si los hay: `Batman White Knight [Tomos]`).
- El nombre de archivo usa la **plantilla de naming de biblioteca existente** (`library.naming.filename_template`), ya probada: `Serie NNN - Título.ext`. No se inventa un formato nuevo.
- Los volúmenes **sin número** van como `Serie - Título.ext`. La clave de orden en Kavita será el propio nombre; es suficiente para obras únicas.

## 3. Modos de materialización

| Modo | Cuándo | Detalle |
|---|---|---|
| `hardlink` | **por defecto** — mismo filesystem | Cero espacio adicional; ideal en la Pi con un único disco externo. El archivo existe en ambos árboles. |
| `copy` | raíz en otro filesystem | Copia byte a byte. |
| `move` | **prohibido** | La exportación nunca vacía la canónica. |

`hardlink` y `copy` se detectan automáticamente: intentar `os.link()`, caer a copia si falla por `EXDEV`. El modo elegido se registra por archivo en el run.

## 4. Metadatos: parche ComicInfo opcional

Flag `patch_comicinfo` (por defecto **off**):

- **CBZ**: se actualiza/añade `ComicInfo.xml` dentro del zip con los metadatos canónicos de la DB (Series, Number, Title, Writer, Penciller, Publisher, Summary, Tags de género). ZascArr ya lee este formato en capa 0; escribirlo es simétrico.
- **CBR**: **no se parchea** — escribir en RAR exige `rar`/libarchive de escritura, dependencia que ya se descartó con datos (sonda 0,5%). Los CBR viajan tal cual; Kavita los clasifica por nombre de archivo.
- **CB7/PDF/EPUB**: no se parchean en v1.

Si el parche está off, el CBR/CBZ viaja sin tocar y la clasificación en Kavita depende del nombre (que ya es canónico).

## 5. Manifiesto e idempotencia

Cada colección exportada escribe `_zascarr_manifest.json` junto a los archivos:

```json
{
  "zascarr_version": "1.6.0",
  "collection_id": 7,
  "series_name": "Dinastía Vázquez [Brekte Boom y Don Bowich]",
  "exported_at": "2026-09-26T11:00:00Z",
  "mode": "hardlink",
  "files": [
    {"dest": "Dinastía Vázquez 01 - Brekte Boom y Don Bowich.cbz", "sha256": "...", "issue_id": 101, "mode": "hardlink"}
  ]
}
```

Consecuencias:

- **Re-exportar es seguro**: los archivos con hash idéntico se saltan; solo viajan novedades o cambios. No hay borrados masivos.
- **Detección de deriva**: si el hash del destino ya no coincide (alguien editó en Kavita), el manifiesto lo delata en la siguiente exportación y se registra — no se sobreescribe en silencio (principio del coleccionista).
- El manifiesto es la semilla futura de "detectar cambios en biblioteca" (RF-02b ya añadido en 1.4.0).

## 6. Casos especiales

- **Duplicados (B6)**: se exporta solo la variante canónica; las marcadas duplicadas se omiten y se listan en el reporte del run.
- **Piezas sueltas sin colección**: no exportables por este camino; ya tienen su pestaña.
- **Colisión de nombre en destino** (ya existe un archivo distinto con ese nombre): se aborta ese archivo, se registra en el run, nunca se pisa.
- **Espacio insuficiente** (solo modo `copy`): comprobación previa agregada; si no cabe, el run no empieza.

## 7. Superficie

- **API**: `POST /api/v1/collections/{id}/export` con body `{root, patch_comicinfo}`. Respuesta: `run_id`.
- **Run auditable**: cada exportación crea un `import_runs` con `run_type='export'` y detalle por archivo — visible en Historial como cualquier otra operación, con su "Registro de auditoría".
- **UI**: botón "Exportar a Kavita" en el menú ⋮ de la tarjeta de colección (misma familia que "Exportar CSV", que ya existe). Sin scheduler: acción manual, sin tarea nocturna en la Pi.

## 8. Criterios de aceptación

1. Exportar una colección con hardlink no consume espacio medible (`df` estable) y el árbol resultante es abrible por Kavita sin configuración extra.
2. Re-ejecutar la misma exportación no rehace archivos (solo manifiesto actualizado).
3. Un CBR con parche activado exporta sin error y sin parche (registrado como "skip, formato no escribible").
4. Un destino pre-editado manualmente se detecta como deriva y no se pisa.
5. Tests: función pura de planificación (`plan_export(collection_files, root) → acciones`) sin disco; integración sobre tmpfs con hardlink real.

## 9. Lo que NO hace

- No lee de vuelta desde Kavita (la canónica manda; la lectura inversa es B22/B23).
- No genera `poster.jpg`/`tvshow.nfo` estilo Kodi — Kavita extrae portada de la primera página del archivo (capa 0 que ya tenemos); los sidecars Kodi quedan para cuando alguien lo pida.
- No parchea CBR (decisión con datos, sonda del 2026-09-25).
