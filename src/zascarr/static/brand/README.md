# Marca

El estallido «¡ZAS!»: una Z rotulada, gruesa (blanca, contorno y sombra de tinta), que
sobresale un poco de un estallido de onomatopeya bermellón con puntas cóncavas.
Elegido el 2026-10-20 tras cinco rondas de pruebas de iconos (los descartes y por qué
están en `CLAUDE.md` §6, «Marca»).

**Cada tamaño tiene su dibujo** (2026-10-21). El dibujo completo (trama y líneas de impacto)
solo se lee grande: en la barra lateral, a 32 px, la Z medía unos 10 px y el contorno se comía
el blanco, así que se veía gris y empastada. Por eso hay tres dibujos de la misma marca:

- **Completo**, a 180 px: `zascarr-completo.svg`, rasterizado en `apple-touch-icon.png`. Añade la
  trama y las líneas de impacto.
- **De interfaz**, de 24 a 48 px: `zascarr-icono.svg`. Sin trama ni líneas, con el estallido
  más grande y el contorno más grueso.
- **De favicon**, por debajo de 24 px: `zascarr-favicon.svg`. Sin el cuadrado de papel: en una
  pestaña clara se perdía y la Z blanca se fundía con él. El estallido es la silueta, con
  contorno de tinta para las pestañas claras.

En los tres, **la Z es grande y gruesa, y sobresale un poco del estallido**
(decisión del PO, 2026-10-21): en pequeño lo primero es que la Z se lea, y una Z que se sale
nos aleja de Komga (ver Reglas). Tiene trazos más anchos que la primera Z de la marca, relleno
blanco y contorno y sombra de tinta.

| Fichero | Uso | Notas |
|---|---|---|
| `zascarr-icono.svg` | Barra lateral y cabecera (fondo del `.brand::before` en `web.css`) | 80×80, fondo papel redondeado. Dibujo de interfaz: de 24 a 48 px |
| `zascarr-favicon.svg` | Favicon y cabecera de móvil (18 px) | Versión de 16 px propia: sin fondo, el estallido es la silueta; Z gruesa blanca con contorno y sombra de tinta, sin trama ni líneas |
| `zascarr-favicon-32.png` | Respaldo del favicon para navegadores sin SVG | Rasterizado del anterior |
| `zascarr-completo.svg` | Fuente del icono de iOS (no se sirve en ninguna página) | 80×80 cuadrado, dibujo completo |
| `apple-touch-icon.png` | Icono al añadir la app a la pantalla de inicio de iOS | 180×180 cuadrado: iOS redondea las esquinas. Rasterizado de `zascarr-completo.svg` |

Colores: bermellón `#F2542D`, tinta `#17171A` y blanco `#FFFFFF`; son las tres tintas de la
marca. El papel `#F6F3EC` es el fondo del cuadrado y la trama `#C2391A` es un tono del
bermellón, no una tinta más. Solo se usan en pantalla, así que no hay valores CMYK.

Uso:

- **Tamaño mínimo: 16 px**, con `zascarr-favicon.svg`.
- **Espacio libre**: alrededor del icono, al menos ¼ de su lado (8 px a 32 px; la barra lateral
  deja 10). Nada lo toca: ni el texto ni otro control.
- **En blanco y negro funciona**: sobre fondo claro queda un estallido negro con la Z blanca,
  y se reconoce a 96, 32 y 16 px (probado el 2026-10-21 en escala de grises con umbral). Sobre
  fondo oscuro hace falta la versión invertida, con el estallido claro y la Z oscura. Ningún
  sitio la usa hoy, así que no hay fichero; el icono de interfaz ya lleva su propio fondo de papel.
- **Contextos probados**: la barra lateral en tema claro y oscuro, y la pestaña del navegador
  clara y oscura, a 1× y 2×.

Reglas:

- **Nada de amarillo en la marca.** Es el color de Mylar3 y Kapowarr (gestores de cómic) y de
  Radarr; en la UI el amarillo sigue siendo el color de acción.
- **Por debajo de 24 px, siempre `zascarr-favicon.svg`**: la versión completa se empasta.
- **La trama y las líneas de impacto, solo a partir de unos 96 px.** Más pequeñas, ensucian.
- La Z **sobresale un poco** del estallido, y el estallido tiene que seguir viéndose alrededor:
  si la Z lo tapa, se pierde la marca y queda una Z suelta. Sacarla un poco además nos
  distingue de Komga, cuyo logo lleva la letra dentro de un estallido (observación del PO,
  2026-10-21; la regla anterior, «la Z dentro», partía de la idea contraria).
- El nombre lo dice el texto del enlace; la imagen es decorativa y no lleva texto alternativo.

Los PNG se regeneran rasterizando los SVG (cualquier navegador sin cabeza vale); no hay
herramienta en el repo a propósito, para no añadir dependencias.
