# B20: Exportación de colección → carpeta compatible con Kavita

**Estado:** fases 1 y 2 implementadas (núcleo + parche ComicInfo opcional)
**Origen:** análisis de la biblioteca real de TV del coleccionista (Sonarr, 2026-09-26) — la carpeta de serie es la unidad portable
**Relación:** el **formato de exportación** es el contrato de lectura de los futuros consumidores de la exportación. Con B14 la relación es **conceptual, no de dependencia**: B20 crea carpetas de DESTINO para Kavita, mientras B14 analiza carpetas de ORIGEN durante la adopción — la exportación no aporta contexto a los ficheros planos originales.

## 0. Corte de la primera entrega (#149, 2026-11-13)

Esta entrega implementa el **núcleo sin parche** y usa las colecciones de
#155. Decisiones fijadas:

- **Raíz única**: `export_path` (config, default `/media/export`). El host la
  monta con `HOST_EXPORT_DIR` (`${HOST_EXPORT_DIR:-/media/data/export}:/media/export`).
  No se acepta una raíz por petición.
- Se rechaza una raíz que sea symlink, que contenga `..` o que esté dentro de
  biblioteca, descargas, incoming o una carpeta compartida.
- `patch_comicinfo=true` se rechaza con error claro (422 en API; mensaje en
  UI): **fase 2**, no se toca ningún archivo.
- Materialización automática: `os.link` y `copy` si `EXDEV`; nunca `move`.
  Una fila por issue con archivo disponible; los desaparecidos se omiten.
- Manifiesto `_zascarr_manifest.json` atómico (versión 1) y `ImportRun` con
  `details.kind="export"` y contadores; sin migración.
- Sin fuentes, calidad ni scheduler en esta entrega.
- **Revisión SecOps/QA (task-190):** todo el I/O de materialización y
  manifiesto va en `asyncio.to_thread`; la copia usa un temporal único y se
  publica en exclusiva (nunca `os.replace` sobre un destino de usuario); los
  archivos de origen symlink o desaparecidos se omiten y reportan; las
  carpetas de serie con el mismo nombre se desambiguan (`[2]`) y se reportan;
  el manifiesto conserva las entradas `skip` (hash igual) para ser idempotente
  y completo, y el modo global es `hardlink`, `copy` o `mixed`.

## 1. Objetivo

### Fase 2 (task-201)

`patch_comicinfo=true` está disponible: cada CBZ se materializa **siempre como
copia privada** (nunca hardlink), se parchea el `ComicInfo.xml` de esa copia
con el plan/fusión de B6 y se publica con `os.link` sin pisar. El original
conserva bytes, tamaño y mtime. CBR/CB7/PDF/EPUB viajan sin parche y se
registran con `patch_status="no_escribible"`. El manifiesto y el run llevan
`patched`/`patch_status` por archivo y `patch_comicinfo` global. La UI ofrece
la casilla y avisa de que se copia; la API acepta `patch_comicinfo: true`.

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
| `copy` | raíz en otro filesystem, **o el archivo se va a parchear** (§4) | Copia byte a byte. |
| `move` | **prohibido** | La exportación nunca vacía la canónica. |

`hardlink` y `copy` se detectan automáticamente: intentar `os.link()`, caer a copia si falla por `EXDEV`. El modo elegido se registra por archivo en el run.

**Excepción que manda sobre la detección automática:** con `patch_comicinfo=true`, **un CBZ se materializa siempre como copia privada, nunca como hardlink**. Un CBZ parcheado se reescribe por dentro y, con un hardlink, la exportación y la canónica son el MISMO inodo — el parche alcanzaría al original y rompería la garantía de §1. La excepción es por archivo: el resto del run puede seguir en `hardlink`.

## 4. Metadatos: parche ComicInfo opcional

Flag `patch_comicinfo` (por defecto **off**):

- **CBZ**: se actualiza/añade `ComicInfo.xml` dentro del zip con los metadatos canónicos de la DB (Series, Number, Title, Writer, Penciller, Publisher, Summary, Tags de género). ZascArr ya lee este formato en capa 0; escribirlo es simétrico. **Requiere copia privada**: parchear es reescribir el zip por dentro, así que con `hardlink` el parche modificaría el archivo canónico — el mismo inodo. Estos CBZ se exportan con `copy` aunque el destino esté en el mismo filesystem (§3); el resto del run no cambia de modo.
- **CBR**: **no se parchea** — escribir en RAR exige `rar`/libarchive de escritura, dependencia que ya se descartó con datos (sonda 0,5%). Los CBR viajan tal cual; Kavita los clasifica por nombre de archivo.
- **CB7/PDF/EPUB**: no se parchean en v1.

Si el parche está off, el CBR/CBZ viaja sin tocar y la clasificación en Kavita depende del nombre (que ya es canónico). En ningún caso se escribe sobre un archivo de la biblioteca canónica: **si hay que parchear, se parchea la copia**.

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
- **Espacio insuficiente**: comprobación previa agregada sobre todo lo que se vaya a materializar como copia — **no solo** las copias forzadas por `EXDEV`, también las **copias privadas de CBZ en el mismo filesystem** cuando el parche está activo (§4), que no son gratis en disco. Si no cabe, el run no empieza.

## 7. Superficie

- **API**: `POST /api/export/collections/{id}` con body explícito `{patch_comicinfo: false}`. La raíz es siempre `export_path` (`/media/export`); en fase 1 `patch_comicinfo=true` devuelve 422. Respuesta: `run_id` y resumen.
- **Run auditable**: cada exportación crea un `import_runs` con `run_type='export'` y detalle por archivo — visible en Historial como cualquier otra operación, con su "Registro de auditoría".
- **UI**: botón "Exportar a Kavita" en el menú ⋮ de la tarjeta de colección (misma familia que "Exportar CSV", que ya existe). Sin scheduler: acción manual, sin tarea nocturna en la Pi.

## 8. Criterios de aceptación

1. Exportar una colección con hardlink no consume espacio medible (`df` estable) y el árbol resultante es abrible por Kavita sin configuración extra.
2. Re-ejecutar la misma exportación no rehace archivos (solo manifiesto actualizado).
3. Un CBR con parche activado exporta sin error y sin parche (registrado como "skip, formato no escribible").
4. Un destino pre-editado manualmente se detecta como deriva y no se pisa.
5. Tests: función pura de planificación (`plan_export(collection_files, root) → acciones`) sin disco; integración sobre tmpfs con hardlink real.
6. Con `patch_comicinfo=true` sobre un destino en el **mismo** filesystem, el modo registrado para cada CBZ es `copy` (no `hardlink`) y el `sha256` del archivo canónico es **idéntico antes y después** de la exportación. Es la prueba de que el parche no ha alcanzado al original.

## 9. Lo que NO hace

- No lee de vuelta desde Kavita (la canónica manda; la lectura inversa es de los futuros consumidores de la exportación).
- No genera `poster.jpg`/`tvshow.nfo` estilo Kodi — Kavita extrae portada de la primera página del archivo (capa 0 que ya tenemos); los sidecars Kodi quedan para cuando alguien lo pida.
- No parchea CBR (decisión con datos, sonda del 2026-09-25).
- **ZascArr no escribe nunca sobre la biblioteca canónica durante la exportación.** El parche de ComicInfo se aplica a una copia privada; con `hardlink` la exportación y el original comparten inodo, así que parchear "la exportación" sería parchear el original.

  **Matiz que acota esa garantía — el hardlink NO aísla el origen de terceros.** Que ZascArr no escriba no significa que el árbol exportado esté protegido: con `hardlink` el archivo exportado y el canónico son el **mismo inodo**, así que **cualquier herramienta que edite el destino en sitio** (Kavita, ComicTagger, un renombrador de metadatos) modifica también la biblioteca canónica. El manifiesto detecta la deriva *después* (§5), pero **no la previene**. Quien necesite aislamiento frente a lectores o etiquetadores que escriben debe elegir **`copy` para toda esa exportación**, no solo para los CBZ parcheados.

## 10. Posible mejora futura: metadatos de catálogo junto a la exportación

No forma parte de v1 y **no se escribe en la biblioteca canónica**. Si otra
herramienta necesita leer el estado de una serie sin hablar con la API de
ZascArr, el sitio correcto es el árbol de exportación (`export_path`), no la
carpeta de la serie: un `series.json`/`metadata.json` junto a los archivos
exportados, generado en el mismo run y cubierto por el manifiesto.

Descarta el planteamiento de la antigua BL-C7 (#161) de regenerar un
`series.json` dentro de cada carpeta de serie: no hay un estándar que lo
consuma (Mylar3 usa el suyo; Kapowarr lo trata como metadato genérico;
Kavita y ComicTagger no lo leen), duplicaría la verdad de `ComicInfo.xml` y
obligaría a escribir en la biblioteca canónica tras cada cambio. Si se
retoma, debe nacer como una extensión pequeña de B20 y con un consumidor
externo concreto identificado.
