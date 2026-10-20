# Marca

El estallido «¡ZAS!»: una Z rotulada (blanca, contorno y sombra de tinta) dentro de un
estallido de onomatopeya bermellón con puntas cóncavas, trama y líneas de impacto.
Elegido el 2026-10-20 tras cinco rondas de pruebas de iconos (los descartes y por qué
están en `CLAUDE.md` §6, «Marca»).

| Fichero | Uso | Notas |
|---|---|---|
| `zascarr-icono.svg` | Barra lateral y cabecera (fondo del `.brand::before` en `web.css`) | 80×80, fondo papel redondeado. Desde 28 px |
| `zascarr-favicon.svg` | Favicon y cabecera de móvil (18 px) | Versión de 16 px propia: Z grande, contorno fino, sin trama ni líneas |
| `zascarr-favicon-32.png` | Respaldo del favicon para navegadores sin SVG | Rasterizado del anterior |
| `apple-touch-icon.png` | Icono al añadir la app a la pantalla de inicio de iOS | 180×180 cuadrado: iOS redondea las esquinas |

Colores: bermellón `#F2542D`, trama `#C2391A`, tinta `#17171A`, papel `#F6F3EC`.

Reglas:

- **Nada de amarillo en la marca.** Es el color de Mylar3 y Kapowarr (gestores de cómic) y de
  Radarr; en la UI el amarillo sigue siendo el color de acción.
- **Por debajo de 24 px, siempre `zascarr-favicon.svg`**: la versión completa se empasta.
- La Z va **dentro** del estallido: si se sale, se parece a la K de Komga.
- El nombre lo dice el texto del enlace; la imagen es decorativa y no lleva texto alternativo.

Los PNG se regeneran rasterizando los SVG (cualquier navegador sin cabeza vale); no hay
herramienta en el repo a propósito, para no añadir dependencias.
