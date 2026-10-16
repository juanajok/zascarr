# Ficha de benchmarking — U14: Descubrir, ver que la búsqueda avanza y leer resultados limpios

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Historia: Kanban #201 (BL-U14, P1, 5 pts).
> **Estado: escrita antes de implementar, el 2026-10-16.** Las decisiones marcadas «para el revisor» son
> propuestas mías y se pueden devolver; el código se escribe después y las cita.

## Historia / problema observado

Como coleccionista que busca una serie en Descubrir, quiero ver que la búsqueda avanza y leer resultados limpios, para
no pensar que se ha colgado ni descifrar texto técnico. Auditoría del 2026-10-15 sobre `a5369ef`
(`docs/design/auditoria-ui-2026-10-15.md`, M3): «Mortadelo» tardó 15–20 s **sin indicador**; las descripciones salían con
etiquetas HTML visibles; la procedencia se leía `COMIC_VINE`; el selector de tradición era el `select` nativo gris claro
en tema oscuro; el enlace `↗` no decía adónde lleva.

## Datos reales y medición de partida

| Dato | Valor | Cómo se sabe |
|---|---|---|
| Espera sin indicador | 15–20 s con «Mortadelo» | Auditoría en la Pi. **No lo he vuelto a medir** (necesita las fuentes reales) |
| Fuentes consultadas | hasta 4, **en paralelo** (`asyncio.gather`), cada una con su cliente | `services/discovery.py:134` |
| «Tarda demasiado» | **No hay plazo global, y 30 s NO es el máximo de una búsqueda.** Cada cliente HTTP tiene `timeout=30.0` **por petición**; además Comic Vine y AniList **reintentan hasta 3 veces** (`_MAX_RETRIES = 3`) durmiendo `Retry-After` (valor del servidor) o 2·2ⁿ s, y Tebeosfera encadena hasta **4 peticiones** (`MAX_SALTOS = 3`) con espaciado de 2,5 s | `comic_vine.py:18,69,84-96`, `anilist.py:39,82,92-103`, `tebeosfera.py:68,126,151`, `gcd.py:82`. **La cota total por fuente no está calculada ni medida**; no se afirma ninguna |
| Estado por fuente | ya existe: `Busqueda.fuentes` = `ok` / `apagada` / `sin_clave` / `error` | `services/discovery.py:55,101` (`search_detallada`). La web usa `search()`, que lo descarta |
| Aviso de fallo | «{Fuente}: no se pudo consultar ahora mismo.» | `discovery.py:140`; **no dice que las demás sí respondieron** |
| Aviso de «sin clave» | «…añade COMICVINE_API_KEY en tu .env…» | `discovery.py:114`: nombre de variable de entorno y fichero, jerga de administrador |
| Etiqueta de la fuente | `{{ r.fuente }}` = el **valor interno** `comic_vine` (la hoja lo pone en mayúsculas: `COMIC_VINE`) | `descubrimiento_grupo.py:279`, `_resultados_descubrir.html` |
| Descripción | `{{ r.descripcion }}` tal cual la entrega la fuente (Comic Vine: HTML) | `_resultados_descubrir.html`; Jinja la escapa, así que **se ve el HTML** |
| Estado de carga | **ninguno**: `descubrir.html` no tiene `hx-indicator` | auditoría + plantilla |
| Anuncio del resultado | **ninguno**: no hay región `aria-live` | plantilla |
| `select` de tradición | sin estilo propio (el control nativo); hay un patrón ya estilado: `.politica-form select` | `web.css:726` |

## Referencias consultadas (código leído)

| Referencia | Commit | Licencia | Qué se leyó |
|---|---|---|---|
| Sonarr, `v5-develop` | `d137dc5a19f46a8aa6d41e706143cad1f0af27af` | GPL-3.0 | `frontend/src/AddSeries/AddNewSeries/AddNewSeries.tsx`, `Components/Loading/LoadingIndicator.tsx`, `Localization/Core/en.json` |
| Prowlarr, `develop` | `b8d04898207b16070c010c8d74b4cc218ff84b8f` | GPL-3.0 | `frontend/src/Search/SearchIndex.js` |
| Kapowarr, `development` | `5b225cfed49d9eccf13e14cb2a947143477606ef` | GPL-3.0 | `frontend/static/js/library_import.js` (ya leído para U20: vistas de carga y banner de límite de peticiones) |

**Solo como patrón: no se copia código.** **No consultadas:** Radarr, Mylar3, Suwayomi y el resto de ficheros de Prowlarr
(solo `SearchIndex.js`): **no se afirma nada sobre lo que no se leyó**.

## Cómo lo resuelve cada una

**Sonarr (añadir serie).**
- La búsqueda se lanza con un **debounce de 300 ms** sobre lo escrito; el estado «cargando» se activa **al escribir**
  (`setIsFetching(!!value.trim())`) y pinta un `LoadingIndicator` **de inmediato**, sin umbral.
- Hay **tres estados mutuamente excluyentes**: cargando, **error de la búsqueda** («No se pudieron cargar los
  resultados, inténtalo de nuevo», `AddNewSeriesError`) y resultados con **recuento** («N resultados»,
  `CountResult(s)`); sin resultados, «No se encontró nada para '{term}'».
- Es **una sola fuente**: el error es de todo o de nada. En los dos ficheros que leí **no hay `aria-live`** ni `role` en el
  indicador (`grep` sin resultados): el recuento y el spinner no se anuncian a un lector de pantalla. *Solo afirmo lo que leí
  en esos dos ficheros.*

**Prowlarr (búsqueda en varios indexadores).**
- `SearchIndex.js` muestra `LoadingIndicator` mientras carga (`isFetching && !isPopulated`) y, si falla, **una alerta
  roja con el error de la API**; sin resultados, un componente propio. En ese fichero **no vi** un aviso por indexador
  fallido mientras los demás responden; **no puedo afirmar que Prowlarr no lo haga en otra parte**.

**Kapowarr.**
- Vistas separadas para cargando, sin resultados, **sin clave de ComicVine** (`noCv`) y un **banner** de «límite de
  peticiones», ya con texto propio y específico de **una fuente**.

## Supuestos de su modelo que NO valen en ZascArr

- **Varias fuentes en paralelo con fallos independientes.** Sonarr y Kapowarr hablan con una; aquí hay hasta cuatro y lo
  honesto es «no respondió X; las demás sí». Es el caso que las referencias leídas no resuelven.
- **Spinner inmediato.** Con respuestas rápidas parpadea. La tarjeta propone un umbral (400 ms): se adapta.
- **Lector de pantalla.** Ninguna de las dos referencias leídas anuncia el estado; el criterio 2 va **más allá** de ellas.
- **Descripciones.** Sonarr/Prowlarr muestran metadatos propios; aquí vienen HTML de Comic Vine y hay que limpiarlo.
- **Quién configura.** La persona no edita `.env`; Ajustes (D11) ya deja poner la clave de Comic Vine.

## Adoptar / adaptar / descartar

| Idea | Decisión | Motivo |
|---|---|---|
| Estados cargando / error / recuento mutuamente excluyentes (Sonarr) | **Adoptar** | Lo que ya pide la tarjeta; hoy solo hay «resultados» |
| Debounce (300 ms en Sonarr) | **Ya existe** (`keyup changed delay:400ms`) | Sin cambio |
| Indicador inmediato | **Adaptar** | Umbral de **400 ms** de petición en vuelo, solo con CSS (`transition-delay`): una respuesta rápida no lo hace parpadear |
| Error de TODA la búsqueda (Sonarr, Prowlarr) | **Adaptar** | Aquí el error es **por fuente** y debe decir cuáles sí respondieron |
| Banner específico de una fuente (Kapowarr) | **Adaptar** | Mismo patrón por cada fuente de las cuatro |
| Recuento «N resultados» (Sonarr) | **Adoptar** y **anunciarlo** en una región `aria-live="polite"` | Criterio 2; supera a las referencias |
| Sin `aria-live` (lo observado en los dos ficheros de Sonarr) | **Descartar** | Un indicador mudo es justo el fallo que la tarjeta quiere evitar |

## Decisiones técnicas propuestas (para el revisor)

1. **Indicador sin JS propio.** `hx-indicator` sobre el campo; el elemento recibe `.htmx-request` y la hoja lo muestra con
   `transition-delay: 400ms` (la propia hoja de htmx ya usa `visibility`/`opacity`). Texto: «Buscando en {fuentes
   activas}…» con **solo las fuentes encendidas** (si GCD está apagada no se nombra). Un `<span>` visible; **no** se anuncia
   al aparecer (lo anuncia la región viva solo al terminar), para no duplicar.
2. **Región viva única y persistente** (`aria-live="polite"`, `aria-atomic="true"`, la convención de `ui.region_viva`)
   **fuera** del destino del intercambio, que la respuesta actualiza con `hx-swap-oob`. *Corrección al implementar:* se
   **oculta a la vista** (`sr`) y el recuento visible va aparte (`aria-hidden`); de lo contrario el mismo texto sale dos
   veces en pantalla (región y avisos). Un solo anuncio por búsqueda: «3 resultados» / «Ningún resultado» /
   «No respondió Comic Vine; …». El contenido nuevo del destino **no** lleva `role="status"` para no anunciar dos veces.
3. **Texto plano en el servidor** con `html.parser` de la biblioteca estándar (sin dependencia nueva): quita etiquetas,
   descarta el contenido de `script`/`style`, decodifica entidades y colapsa espacios. Se aplica a la **presentación**
   (no cambia lo que se firma en el token).
4. **Etiqueta de fuente** por una tabla `MetadataSource → nombre` («Comic Vine», «AniList», «Tebeosfera», «GCD»), con
   la misma lista que ya usa el aviso del servicio, y **un valor desconocido se muestra como «otra fuente»**, nunca el id.
5. **Errores por fuente** a partir de `search_detallada` (`Busqueda.fuentes`): «**No respondió Comic Vine.** Los resultados
   de AniList, Tebeosfera y GCD sí se han consultado.» Con varias caídas, las enumera; con todas caídas, dice que
   ninguna respondió y no «sin resultados». El aviso de «sin clave» pasa de «`COMICVINE_API_KEY` en tu `.env`» a «Comic
   Vine no está configurado: añade su clave en Ajustes». *Corrección al implementar:* **se hace en la capa web**
   (`web/descubrir_texto.py::resumir`), no en el servicio: `discovery.py` y sus pruebas no cambian, y la web deja de pintar
   los avisos de texto del servicio.
5b. **«Tarda demasiado»: no se añade un plazo global, y no se afirma ninguna duración máxima.** Una fuente que
   falla (por error o por agotar sus reintentos) queda como `error` y se nombra; una que **tarda** simplemente tarda: el
   indicador sigue visible mientras haya una petición en vuelo. **No se debe decir «30 segundos» como tope**: es el de cada
   petición, y los reintentos y los saltos suman. Un plazo explícito (p. ej. 20 s por fuente) cambiaría lo que devuelve el
   servicio y no lo piden los criterios. *Aprobado por el revisor: no se exige en U14, con esa salvedad de redacción.*
6. **Controles del sistema.** El `select` de tradición reutiliza el patrón ya existente de `.politica-form select`
   (borde de tinta, `--paper`, `--ink`, ≥ 40 px), válido en los dos temas; **no** se añade ningún componente nuevo.
7. **Enlace externo.** `aria-label` «Ver la ficha de «{título}» en {fuente} (se abre en otra pestaña)»; el `↗` queda
   `aria-hidden`. Se mantiene `rel="noopener noreferrer"`.

## Invariantes de ZascArr

- **No mentir:** «Ningún resultado» no se dice cuando **todas** las fuentes fallaron; «las demás sí respondieron» solo
  se dice de las que dieron `ok`. Una fuente **apagada** o **sin clave** no es un fallo y no se mezcla con ellos.
- **Seguridad:** el HTML de la fuente nunca se interpreta (se convierte a texto y Jinja lo escapa); la portada sigue por
  el proxy con lista blanca; el token firmado no cambia.
- **Sin JS propio ni migraciones** (ADR 0005); sin dependencia nueva (`html.parser`).
- **Pi:** sin consultas nuevas; el cambio es de presentación y de qué se hace con un estado que el servicio ya calcula.

## Casos de prueba antes de implementar

Con `FakeSession` y el servicio simulado (los clientes de las fuentes se sustituyen, como en `test_discovery_estados.py`):
1. **Progreso (criterio 1):** la página trae el indicador con el texto «Buscando en Comic Vine, AniList, Tebeosfera y GCD…»
   solo con las fuentes **encendidas**, enlazado con `hx-indicator`, oculto en reposo y con un retardo de 400 ms en la hoja.
2. **Resultado anunciado (2):** existe **una** región `aria-live="polite"`, fuera del destino; la respuesta la actualiza por
   `hx-swap-oob` con el recuento; el fragmento de resultados **no** contiene otro `role="status"`/`aria-live`.
3. **Texto limpio (3):** una descripción `<p>Mortadelo <a href="/x">Bruguera</a> &amp; Filemón</p><script>x()</script>` se
   ve como «Mortadelo Bruguera & Filemón», sin `<`, sin `script`; entidades decodificadas; vacía → no se pinta el bloque.
4. **Fuente legible (4):** «Comic Vine», no `comic_vine`/`COMIC_VINE`; un valor desconocido → «otra fuente».
5. **Select (5):** la regla del selector de tradición de Descubrir existe, usa los tokens y **cumple el contraste** en los
   dos temas (se amplía `test_web_css_contraste.py`).
6. **Enlace (6):** el nombre accesible dice el título, la fuente y «se abre en otra pestaña»; el `↗` no es un nombre.
7. **Errores (7):** una fuente caída → «No respondió Comic Vine. Los resultados de … sí…», sin `COMIC_VINE` ni excepciones;
   dos caídas se enumeran; **todas** caídas no dice «sin coincidencias»; apagada/sin clave no se cuenta como caída.
8. **Navegador real (Chrome, 375 px y escritorio, claro y oscuro):** con una fuente lenta simulada, el indicador aparece
   a los ~400 ms y desaparece al terminar; sin fuente lenta, **no parpadea**; la región viva anuncia una vez (se
   comprueba con el árbol de accesibilidad y, si procede, con Orca como en U11).

## Estimación refinada

Se mantiene **5 (M)**, **confianza Media**: pasar de `search()` a `search_detallada()`, la plantilla y la región viva, una
función pura de texto plano con sus pruebas, la tabla de etiquetas, CSS del indicador y del `select`, y la verificación
en navegador. Lo que puede moverla: que el revisor pida un plazo global (decisión 5b) o dejar el texto de «sin clave».

## Decisión final

**Pendiente de revisión.** Sin ADR (sin esquema, sin JS propio, sin dependencia). Las decisiones 5, 5b y el alcance de la
medición en la Pi son del revisor; el resto sigue los criterios de la tarjeta.
