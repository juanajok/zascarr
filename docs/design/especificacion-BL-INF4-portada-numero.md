# Especificación — BL-INF4: portada por número y vista previa (fase 1)

> Historia #590 (continuación de BL-INF #446, cerrada). **Fase 1** del plan de metadatos y
> portadas: cimiento de BL-INF6 y BL-INF7. Sin migración, sin JS nuevo, sin red y sin escribir en
> la biblioteca.

## 1. Problema local

El coleccionista reconoce un número por su portada; hoy tiene que abrir la ficha del número para
verla. En la ficha de serie los números están como chips `#N` y no dan ninguna pista visual. Con
series de 30–100 números, abrir uno a uno para reconocerlos no escala.

Restricciones: Pi 4/5 compartida (512 MiB), htmx 4 vendorizado, sin SPA ni JS propio, la portada
de serie ya tiene cascada y caché (#418/BL-PORT1) y el lector de RAR es un recurso **serializado**
(`unar`, un turno) con topes y marcas de fallo.

## 2. Alcance

Dentro:

- **Miniatura por número**, cacheada **por archivo**, servida como JPEG de 240 px.
- **Vista previa** al pasar el ratón o al enfocar con teclado sobre los chips «En tu biblioteca»
  de la ficha. Sin precarga y sin peticiones sin interacción.
- Sin portada: no se pinta nada.

Fuera: elegir portada (BL-INF6), números en las tarjetas de Biblioteca (BL-INF7), escribir nada en
los archivos.

## 3. Contrato HTTP

### 3.1 Fragmento (lo que pide htmx)

```
GET /ui/series/{series_id}/numero/{issue_id}/previa
→ 200 text/html
   <img class="previa-numero-img" src="/ui/series/{series_id}/numero/{issue_id}/previa.jpg" ...>
   o vacío (200, cuerpo "") si el número no tiene portada.
Cache-Control: no-store
```

- `404` si el número no pertenece a la serie (mismo criterio que las rutas vecinas).
- El fragmento es diminuto y no se cachea: la caché de verdad está en la imagen y en el disco.

### 3.2 Imagen

```
GET /ui/series/{series_id}/numero/{issue_id}/previa.jpg
→ 200 image/jpeg (240 px de ancho máximo, sin ampliar)
   ETag: "<mtime de la caché>"
   Cache-Control: private, max-age=86400
→ 304 si If-None-Match coincide (cached_image_response, patrón ya usado en #418)
→ 404 + Cache-Control: no-store si no hay portada
```

### 3.3 Caché en disco

```
<settings.covers_cache_path>/v3/numero/<file_id>.jpg
```

- Una miniatura por **archivo**, no por número: la clave estable es `File.id`; varios números
  pueden compartir archivo y un reemplazo del archivo invalida la marca por `mtime`/tamaño.
- Escritura atómica (temporal en la misma carpeta + `os.replace`) y **una sola generación por
  archivo** con un lock `asyncio` por `file_id`.
- Marcas de fallo de RAR compartidas con la portada de serie (`<covers>/v3/fallos`), para no
  reintentar un CBR roto en cada hover.

## 4. Selección y generación

1. Archivos del número no ausentes, ordenados por ruta, como mucho `MAX_ARCHIVOS_NUMERO = 3`.
2. Se descartan los que no pueden dar portada sin abrirlos (`es_candidato_de_portada`,
   `es_rar_candidato`).
3. ZIP por contenido: `extract_cover_thumbnail(path, formato, ancho=240)` (misma regla que #418;
   no amplía, topes de píxeles y entradas).
4. RAR por firma: `portada_de_rar(path, covers, ancho=240)` con el turno único de `unar`. Si el
   lector está ocupado o no está, se salta sin marcar (la siguiente petición lo intenta). Un fallo
   del archivo deja marca.
5. Presupuesto de tiempo acotado (~6 s por petición) y como mucho 3 archivos: nunca un hover
   bloquea la ficha varios segundos por intentar media serie.

## 5. UX

> **Actualizado tras el benchmark** (`benchmark-BL-INF4-portada-numero.md`): tarjeta de 220 px
> con pie «Nº N · título» y «Pulsa para abrir la ficha», flecha al chip, retardo de 150 ms y
> fundido (anulado con `prefers-reduced-motion`). Va **debajo** del chip para no tapar el rótulo de
> la sección; sin flip automático (limitación declarada). **Solo se muestra la previa del chip con
> ratón o foco**; al salir se oculta (nada de previas acumuladas).

- Chips «En tu biblioteca» de la ficha: cada chip es un enlace al número; se le añade
  `hx-get="…/previa"`, `hx-trigger="mouseenter, focusin"`, `hx-target="#previa-<issue_id>"` y un
  contenedor `<span class="previa-numero" aria-hidden="true">` dentro de un envoltorio
  `position: relative`.
- El flotante va **encima** del chip, centrado, con `pointer-events: none` (no roba el hover ni el
  clic), borde de tinta y sombra dura corta (lenguaje de la app). Solo aparece cuando hay
  contenido (`:empty { display: none }`).
- Teclado: `focusin` dispara la misma petición; el flotante es decorativo y no entra en el árbol de
  accesibilidad. El texto del enlace sigue explicando a qué número va.
- Sin hover real (`pointer: coarse` o ≤860 px) el flotante no se muestra; tocar sigue abriendo el
  número. No hay cambio de comportamiento en móvil.
- Ni precarga ni `loading="eager"` de N imágenes: solo se pide lo que se mira.

## 6. Rendimiento (presupuesto)

| Caso | Coste objetivo |
|---|---|
| Fragmento con caché | 1 consulta a `files` + stat de la caché; < 20 ms |
| Primer hover, ZIP (CBZ) | 10–50 ms de extracción + escritura; < 150 ms |
| Primer hover, CBR (RAR) | 0,3–3 s según archivo (`unar`), acotado por presupuesto y 3 intentos |
| Hover repetido | Imagen desde caché HTTP (o disco); sin volver a extraer |
| Disco | ≈20 KB por archivo con miniatura; 5.000 ≈ 100 MB; limpieza, historia aparte si molesta |

## 7. Criterios de aceptación

- **AC-1**: el primer hover genera o sirve de caché la miniatura; el segundo no vuelve a extraer.
- **AC-2**: respeta topes/turno de #418; lector ocupado o archivo sin portada → sin imagen y sin
  error visible; no se rompe la ficha.
- **AC-3**: JPEG 240 px con ETag y caché privada 24 h; 304 si no cambió; 404 sin caché si no hay.
- **AC-4**: ratón y teclado funcionan igual; el flotante es decorativo y no atrapa el foco.
- **AC-5**: sin JS nuevo, sin precarga, sin peticiones sin interacción.
- **AC-6**: pruebas del servicio (ZIP real, caché, número sin archivo, archivo que falla) y de la
  ficha (marcado). Navegador real en la Pi: **NOT RUN** hasta desplegar.

## 8. Pruebas

- `tests/test_portada_numero.py`: servicio con ZIP sintético (Pillow), caché reutilizada
  (monkeypatch de la extracción que falla tras generar), sin archivos → `None`, ZIP roto → `None`,
  y no se toca ningún archivo de la biblioteca.
- `tests/test_web_portada_numero.py`: fragmento con `<img>` y ruta de imagen, 404 sin portada,
  cabeceras de caché y 304.
- `tests/test_web_ficha_447.py`: la ficha marca los chips con `hx-get`/`previa`.
- `ruff check src/` limpio.

## 9. Referencias (benchmark §13)

Benchmark de patrones: `docs/design/benchmark-BL-INF4-portada-numero.md`
(MediaWiki Page Previews, NN/g y htmx 4), además de la ficha de #418.

La extracción de portada ya está benchmarkeada y decidida en #418/BL-PORT1
(`docs/design/benchmark-BL-PORT3*`, ADR-0015 para `unar`): esta historia **no elige una fuente ni un
lector nuevos**, solo cachea por archivo y añade UI. La vista de números con portadas es común en
Kavita/Komga; no se copia código. No se requiere un benchmark nuevo; sí revisar que el flotante y
el teclado cumplan las reglas de UX de `CLAUDE.md` §6.
