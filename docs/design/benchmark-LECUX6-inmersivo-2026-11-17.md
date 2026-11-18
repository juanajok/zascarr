# Benchmark previo — LECUX6 (lectura inmersiva)

- **Historia:** [#1073](https://github.com/juanajok/zascarr/issues/1073); épica #1067.
- **Fuente:** `docs/design/benchmark-BL-LEC-mercado-lectores-2026.md` (revisión 2026-11-17,
  13 aplicaciones verificadas; versiones y licencias en su §2.2/Anexo A). No se ha inventado
  comportamiento no comprobado: lo no medido se marca **NOT RUN**.
- **Alcance:** solo el cascarón del lector: inmersión, chrome, fullscreen, flechas y gesto.

## Matriz de referencia

| App | Papel | Qué se toma | Qué no se copia / límite |
|---|---|---|---|
| **Panels** | Lector iOS/iPad/Mac, propietario | Referencia de UX de lector y de filtros de escaneo; su interfaz está cuidada | No se copia la interfaz ni se asume su comportamiento de chrome: **NOT RUN** en esta ronda |
| **Chunky** | Lector iPad, propietario | Lector de tablet de referencia; ya adoptado como cliente OPDS de LEC5 | Sin medición de su fullscreen/chrome; no aplica a web |
| **Kavita** | Servidor + lector web, GPL-3.0 | Referencia de lector web y de biblioteca; ya medida en WK5 | No se integra; su chrome concreto no se ha medido aquí |
| **Komga** | Servidor + lector web, MIT | Referencia de contrato y de lector web | No se integra; su UX de chrome no se copia |
| **YACReader** | Lector de escritorio + WebUI básica, GPL-3.0 | Referencia de lectura de escritorio | Su WebUI es «muy básica»; no es modelo de inmersión web |
| **CDisplayEx** | Lector Android/Windows, propietario | Idea de lectura rápida y «siguiente álbum» | Nada de fullscreen/chrome medido; **descartar** como app |
| **OpenComic** | Lector de escritorio, GPL-3.0 | Filtros de imagen (LECUX1) y ambición de lector completo | IA local y coste incompatibles con la Pi; no se copia |
| **Perfect Viewer** | Lector Android | Ideas sueltas de filtros y caché | Versión/OPDS/PSE **NOT RUN**; no se copia |
| **TritonPanels** | Cliente iOS/Android de Komga/Kavita | Referencia de lector móvil | Suscripción y API propietaria; **descartar** |
| **Mihon** | Lector manga Android, Apache-2.0 | Nada para LECUX6 | Sin OPDS/PSE; ecosistema manga; **descartar** |
| **KOReader** | Lector multiplataforma libre | Cliente OPDS de LEC5 | No es web; su inmersión **NOT RUN** aquí |
| **KMReader / ComicScreen** | Clientes/lectores móviles | Nada | Fuera de alcance de este recorte; **descartar** |

## Conclusión para LECUX6

El mercado confirma la dirección («leer sin el marco de la app, con controles discretos y
flechas/grabación táctil»), pero **ninguna de las apps verificadas ofrece una medición
reproducible de este cascarón en navegador web**. Por eso LECUX6 es la **candidata 5 de §7.4**,
una petición explícita del PO, y se implementa sobre el lector propio, no copiando una app.

Decisiones aplicadas: D-LUX7 inmersivo por defecto; D-LUX8 flechas al pasar el ratón/enfocar
y nunca en táctil; D-LUX9 aviso legal en Opciones y ficha; D-LUX10 fondo neutro del tema.
No se añade zoom propio, panel a panel, modo webtoon ni recorte: descartados en el benchmark
(§4.2/§7.5) por coste en la Pi y por falta de evidencia.

## Verificación prevista

- Node/DOM para chrome, flechas, teclado, fullscreen y gesto.
- Navegador real 375/768/1280, claro/oscuro; fullscreen y fallback; teclado y `prefers-reduced-motion`.
- Medición en la Pi de que no hay peticiones nuevas de página ni cambios de URL.

**NOT RUN:** navegador real y lector de pantalla en esta primera implementación; se registrarán
como PASS/FAIL/NOT RUN separados en la PR, sin convertirlos en PASS.

## Lo observado en las apps (consulta de fuentes, 2026-11-17)

Esto es lo que **hacen**, no una propuesta de copiar su interfaz:

| App | Cómo resuelve el lector | Qué adopto / adapto | Qué descarto |
|---|---|---|---|
| **Kavita** | Menú de lector con barra de progreso, anterior/siguiente capítulo, ajustes de sentido, fullscreen y **auto-cierre del menú** configurable; tap/swipe. [Wiki](https://wiki.kavitareader.com/guides/readers/comic-manga/) | Chrome que se oculta y vuelve; menú de opciones explícito; fullscreen | Su lector tiene webtoon, split de imágenes y capítulos; no entran |
| **Komga** | Lector web con ajustes, fondo blanco/gris/negro, gestos, doble página, fit y ayuda de teclado contextual. [Webreader](https://komga.org/docs/guides/webreader-divina/) | Fondo neutro configurable en el tema; ayuda de teclado; sin marco | Fondos por página, webtoon y zoom propio |
| **Panels** | Botón «…» para configurar; presets; fondo negro/blanco/**inmersivo dinámico**; ajustes por lector. [Guías](https://guides.panels.app/read-content/reader-configurations) | Botón «Opciones» flotante y preferencia simple; fondo del tema | Presets, fondo dinámico por análisis de color y page curl: coste y alcance fuera |
| **YACReader** | `F` fullscreen, `H` mostrar/ocultar barra, `I` información, `Esc` salir, flechas y rueda; barra explícita. [Atajos](https://github.com/yacreader/yacreader/blob/328ea1a9d606034cd5da1e9c326eff235217d1c4/files/shortcuts.html) | **Añado `H` para ocultar/mostrar el chrome**, además de `F`; `Esc` sale | Su barra de herramientas de escritorio y la lupa/zoom propio |
| **Chunky / CDisplayEx / Perfect Viewer / TritonPanels** | Lectores móviles/escritorio con sus propios gestos y menús; la ficha ya los clasifica y varios detalles están **NOT RUN** | Solo la lección: gesto táctil + salida visible | No se copian menús ni funciones propietarias |
| **KOReader / OpenComic** | Lectores no web o de escritorio; OpenComic añade IA local | Nada para este cascarón | IA, filtros avanzados y zoom propio |

**Conclusión:** el patrón común es **página a pantalla completa + barra discreta que se oculta + menú de opciones + salida siempre disponible**; las variantes (fondo dinámico, presets, zoom) no compensan en la Pi. La implementación sigue ese patrón y añade `H` como en YACReader.
