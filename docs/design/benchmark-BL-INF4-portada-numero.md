# Benchmark — BL-INF4: vista previa de la portada del número (fase 1)

> Historia #590. Benchmark ligero de **patrones UX**, no de fuentes de datos: la extracción y la
> caché de portadas ya están decididas y medidas en #418/BL-PORT1 (ADR-0015 para `unar`). Se revisa
> antes de rediseñar la previa porque la primera entrega se quedó en una miniatura de ~40 px (bug de
> CSS) y sin información de a qué número pertenece.

## 1. Qué se ha revisado

| Referencia | Qué se ha comprobado | Fuente |
|---|---|---|
| **MediaWiki — Page Previews** | Tarjeta con imagen principal + resumen al pasar el ratón; la imagen puede ir horizontal o vertical según dónde esté el enlace; inquietud explícita por los **hovers accidentales** y por no interferir con el resto de la página; control para desactivarlo. | [mediawiki.org/wiki/Page_Previews](https://www.mediawiki.org/wiki/Page_Previews) (consultado 2026-11-10) |
| **NN/g — Tooltip Guidelines** | 1) no meter información vital en un hover; 2) contenido breve; 3) soportar **ratón y teclado**; 4) **flecha** cuando hay elementos juntos; 5) uso consistente en todo el sitio. Los tooltips no existen en táctil. | [nngroup.com/articles/tooltip-guidelines](https://www.nngroup.com/articles/tooltip-guidelines/) (2019-01-27, consultado 2026-11-10) |
| **htmx 4 Guidance** | `hx-trigger` admite `delay:<tiempo>` (retardo/debounce); `hx-target` acepta selectores extendidos; en htmx 4 el atributo para deshabilitar durante la petición es **`hx-disable`** (ya no `hx-disabled-elt`); los errores HTTP se intercambian por defecto salvo 204/304. | [htmx 4.0.0, guidance](https://github.com/bigskysoftware/htmx/blob/v4.0.0/src/skills/htmx-guidance.md) |
| **Cómic (Kavita/Komga/Kapowarr)** | No consta en su documentación revisada una vista previa al hover de la portada de un número. **No se infiere ausencia** (§13): no se usa como argumento; la ficha del número sigue siendo el detalle completo. | Repos/documentación de los proyectos |

## 2. Comparación y decisiones

| Idea / patrón | Referencia | Decisión |
|---|---|---|
| Tarjeta flotante con **imagen + texto breve** | MediaWiki | **Adoptar**: portada + pie con «Nº N · título» y «Pulsa para abrir la ficha». |
| **Retardo** antes de mostrar (evitar hovers accidentales al barrer chips) | MediaWiki (FAQ: dwell ~250 ms) + NN/g (hover accesible) | **Adoptar** `delay:150ms` en la petición: menos peticiones y sin parpadeo. |
| **Teclado** (misma previa al enfocar) | NN/g #3 | **Adoptar** `focusin`, ya implementado. |
| **Flecha** que señale el chip (chips muy juntos) | NN/g #4 | **Adoptar** triángulo CSS de tinta sobre la tarjeta. |
| **No información vital** en el hover | NN/g #1 | **Adoptar**: la previa es decorativa (`aria-hidden`); el enlace al número y su ficha siguen siendo el camino. |
| **3:2 / ~320 px** (tarjeta grande tipo sidebar) | MediaWiki | **Adaptar**: 220 px de ancho (más grande que el chip, sin tapar media rejilla). |
| **Cambiar de posición según el espacio** (flip) | MediaWiki (con JS) | **Descartar por ahora**: sin JS nuevo; se coloca **debajo** del chip para no tapar el rótulo de la sección. Limitación aceptada: en la última fila puede solaparse con el encabezado siguiente; se revisará con *CSS anchor positioning* cuando el navegador objetivo lo soporte. |
| **Precargar** todas las portadas al pintar | — | **Descartar**: Pi y disco; solo se pide lo que se mira (una petición por hover, cacheada). |
| **Seguir el cursor / vídeo / carrusel** | — | **Descartar**: requiere JS nuevo; contradice ADR-0001. |
| Ajuste global para desactivar la previa | MediaWiki | **No en esta historia**: la previa es pasajera y no bloquea; si molesta, se valora en ajustes más adelante. |

## 3. Diseño resultante

- Tarjeta de **220 px** de ancho, borde de tinta, canto de panel y sombra dura corta; la portada arriba
  (JPEG 240 px del cimiento), pie en didascalia con **«Nº N · título»** y la pista «Pulsa para abrir
  la ficha».
- Aparece **debajo** del chip, centrada, con flecha; `pointer-events:none` para no robar hover ni clic;
  `aria-hidden` por ser decorativa.
- **Retardo de 150 ms** y fundido de 120 ms (anulado con `prefers-reduced-motion`).
- Sin cambios en la petición: una miniatura por archivo, cacheada (`covers/v3/numero/<file_id>.jpg`),
  ETag y 24 h de caché privada.
- Móvil y puntero grueso: no hay previa; tocar sigue abriendo el número.

## 4. Hallazgo colateral (corregido en la misma PR)

El proyecto usa **htmx 4.0.0** y 14 plantillas usaban `hx-disabled-elt` (atributo de htmx 2, ignorado
en 4): los botones no se deshabilitaban durante la petición. Se sustituye por **`hx-disable`** en
todas (19 usos), incluidos los formularios de conversión.

## 5. Criterios que se añaden a la historia

- AC-7: la previa se muestra como tarjeta con número y título, con flecha al chip, y no tapa el
  rótulo de la sección.
- AC-8: retardo de 150 ms (menos peticiones al barrer chips) y fundido respetando
  `prefers-reduced-motion`.
- AC-9: los botones de las peticiones htmx se deshabilitan con `hx-disable` (htmx 4).

**Limitación declarada**: sin flip automático; en la última fila la tarjeta puede solaparse con el
contenido siguiente. Se acepta como NOT RUN de UX hasta ver uso real.
