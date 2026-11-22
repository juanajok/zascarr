# Plantillas de página (propuesta, no adoptada)

> Estado: **propuesta para decidir** (2026-11-22). **P1 prototipada en el Inicio** (2026-11-22, a
> petición del PO; ver «Prototipo de P1»): P2 y P3 siguen sin tocar. Maquetas en el lienzo
> «Plantillas de página ZascArr» (artefacto privado del PO). Fuentes: sistema de diseño publicado
> (manda sobre la copia `sistema-de-diseno-zascarr.md`), §«Composición de página, no de rejilla» y
> `PropuestaInicio`; precedente en código: `.ajustes-pagina` (12 columnas, spans 8+4 · 4+4+4 · 6+6).
> Contraste con referencias: `benchmark-designsystems-surf.md` (GitLab Pajamas, dashboards: 12
> columnas que pasan a una en el punto medio; lo general arriba y el detalle abajo).

## Qué se toma y qué no

Se toma una **retícula modular**: 12 columnas, un medianil fijo y un vocabulario cerrado de spans.
Es la gramática de la escuela suiza (Müller-Brockmann) con la asimetría con función de la Bauhaus.
**No** se toma su estética: ni el amarillo como decoración, ni más giros que el del rótulo (−1,2°), ni
composiciones aleatorias, ni el desalineamiento de planchas fuera de la página de error.

## Medianil

- **`--space-3` (12 px)** entre viñetas que se tocan en una misma página. Ya lo fija el sistema de
  diseño publicado: no hace falta un token nuevo.
- **`--gutter`** (`clamp(14px, 2.2vw, 24px)`) sigue siendo la separación entre tarjetas de una lista.
- **Deuda que destapa:** la ficha de serie (#1217) separa sus viñetas con `--space-4` (16 px) y
  Ajustes con `--gutter`. Si se adopta, ambas pasan a `--space-3`.

## Spans cerrados

| Reparto | Uso |
|---|---|
| 12 | Contenido principal de una sola pieza (Números, Archivos, Buscar) |
| 8 + 4 | Resumen con un dato al lado (Estado: semáforo + versión) |
| 6 + 6 | Dos secciones cortas emparejadas |
| 4 + 4 + 4 | Bloques de control del mismo peso |
| Losa 8 × 2 filas + 2 + 2 / 2 + 2 | La tarea que manda con cuatro cifras al lado (Inicio) |

Otro reparto exige decidirlo antes (y añadirlo a esta tabla).

## Las cuatro plantillas

| Plantilla | Pantallas | Composición (≥ 1100 px) | Sombra y principal |
|---|---|---|---|
| **P1 Losa y satélites** | Inicio | Losa «Toca ahora» 8 × 2 filas + 4 cifras de 2; «Sigue leyendo» 6 + «Últimas actualizaciones» 6; «Buscar una serie» 12 | Solo la losa: única sombra y único botón principal |
| **P2 Ficha** | Ficha de serie y de número | Portada (140 px) + títulos y una fila de acciones; Números 12; Sagas 12; Sobre esta serie 12; parejas 6 + 6 (Etiquetas · Colecciones, Búsqueda · Seguimiento, Completitud · Notas); Archivos 12 | El principal de la cabecera (Leer o Añadir números del disco) |
| **P3 Panel** | Estado, Ajustes | 8 + 4 · 4 + 4 + 4 · 6 + 6 · 12, con la cinta de acto de Ajustes | Ninguna sombra: no hay una tarea que mande |
| **P4 Catálogo** | Biblioteca, Por revisar, Deseados, listas | **Sin retícula de 12**: `auto-fill` con mínimos de 130–230 px según la densidad que elige la persona; la composición solo toca el marco | Según la pantalla |

## Reglas

1. **Orden del DOM = orden de lectura** (izquierda a derecha, arriba abajo). Sin `order` ni áreas que
   lo contradigan (WCAG 2.4.3). La barra de secciones sigue ese orden.
2. **Reflujo:** ≥ 1100 px, 12 columnas; 860–1100, la losa a todo el ancho y lo demás en pares;
   ≤ 860, una viñeta por fila (las cifras siguen de dos en dos hasta 320 px). Sin desplazamiento
   horizontal a 320 px (WCAG 1.4.10). *Corregido con el prototipo:* la propuesta decía «dos carriles»
   por debajo de 860 px, pero a media fila las portadas de «Últimas actualizaciones» quedaban por
   debajo del mínimo de 130 px de P4.
3. **Las viñetas de una fila igualan su alto;** el contenido empuja las acciones al pie. Coste
   aceptado: una sección que crece deja hueco en su pareja; por eso solo se emparejan secciones cortas.
4. **Determinista:** una plantilla por tipo de pantalla; la misma pantalla siempre se compone igual.
5. **Accesibilidad que ya vigila la CI:** contraste, 14 px, `prefers-contrast` y `forced-colors` (las
   viñetas conservan el borde) y la prueba de estructura de pantallas. Lo que solo ve un navegador
   (reflujo, orden visual) queda pendiente de la decisión sobre el navegador en la CI.

## Cómo se adoptaría

1. Decidir este catálogo (PO).
2. Prototipo de **una** pantalla (Inicio, P1), sin JavaScript, en una PR con sus pruebas: spans del
   vocabulario, medianil y orden del DOM.
3. Si funciona, P2 y P3 en PR separadas; P4 no cambia.

## Prototipo de P1 (Inicio, 2026-11-22)

Decisiones del PO al encargarlo:

1. **Orden:** la losa «Toca ahora» va primero y «Sigue leyendo» baja a media fila junto a «Últimas
   actualizaciones» (antes la lectura en curso iba encima de los pasos; ninguna decisión ni prueba
   fijaba ese orden: CUR5 solo pide la tarjeta).
2. **Con lo básico hecho,** la losa muestra el paso recomendado con el único botón principal y los
   pasos hechos plegados dentro.
3. **«Últimas actualizaciones»** muestra 6 series (`services/resumen.py::ULTIMAS_SERIES`, antes 10):
   una fila de seis a todo el ancho; a media fila, dos de tres.

Cómo quedó: `dashboard.html` (clases `inicio-pagina`, `inicio-losa`, `inicio-cifras`, `inicio-par`,
`inicio-ancha`) y el bloque 15c de `web.css`. Sin cifras que enseñar (instalación nueva) la losa ocupa
las 12 columnas; sin lectura en curso, «Últimas actualizaciones» también. La sombra de «Continuar
leyendo» y las de los pasos dentro de la losa se quitaron: la losa es la única viñeta con sombra.

Coste visto en el navegador: con una lectura en curso, la fila 6 + 6 iguala su alto al de la rejilla de
portadas (2 × 3), y la tarjeta de lectura queda con hueco entre el progreso y sus botones, que bajan al
pie (regla 3). Si molesta, la alternativa es mostrar 3 portadas a media fila.

Pruebas: `tests/test_inicio_plantilla_p1.py` (orden del HTML, repartos del catálogo, botón principal
en la losa, sombra única y retícula sin reordenar; el estado «pasos a medias», solo en ellas).
Verificado en el navegador con datos de prueba: «leyendo» a 1280, 375 y 320 px en tema oscuro y a
1000 px en claro; «instalación nueva» y «con cifras» a 1280 px en claro. Sin desplazamiento
horizontal en ninguno.
