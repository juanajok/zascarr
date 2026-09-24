# Backlog de producto: ZascArr "listo para usar"

## Visión y persona

**Visión:** un coleccionista de tebeos instala ZascArr una vez, apunta a su
carpeta de descargas, y a partir de ahí su tebeoteca se organiza, se enriquece
y se completa sola — sin saber qué es Docker, PostgreSQL ni un indexador.

**Persona principal — "El Coleccionista":** aficionado al tebeo con cientos o
miles de CBZ/CBR acumulados, mezcla de grapa americana, manga y clásicos
Bruguera. Sabe leer en Kavita o en su tablet. No sabe, ni quiere saber, qué es
un contenedor. Su frustración actual: carpetas caóticas, duplicados, tebeos
descargados a medias y no saber qué le falta de una saga.

**Implicación de producto honesta:** el estado actual del repo es un backend
con API REST. Para esta persona, `curl http://127.0.0.1:8000/api/series` no es
"usable". El agujero de producto más grande del proyecto no es ningún bug del
peer review — es la **Fase 6 (UI web)**, que para este stakeholder no es una
fase futura sino EL producto. Todo el backlog fluye de esa constatación.

## Backlog priorizado

Formato: ID · historia · criterio de aceptación clave · prioridad
(P0 = indispensable para el release, P1 = primera mejora, P2 = parking) ·
estimación (S < 2 días, M < 1 semana, L > 1 semana).

### Épica A — "Lo instalo yo solo"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| A1 | ~~Como coleccionista, quiero un único comando o script que lo instale todo, para no tener que seguir un manual de 20 pasos~~ | ~~`bootstrap.sh` pregunta 3 cosas (¿dónde están tus tebeos? ¿dónde descargas? ¿idioma?) y termina con una URL que funciona~~ | ✅ Hecho | M |
| A2 | ~~Como coleccionista, quiero que el instalador me diga en español llano qué falló ("no encuentro el disco", no "exit code 1")~~ | ~~Mensajes de error del bootstrap mapeados a causas y soluciones comunes~~ | ✅ Hecho | S |
| A3 | ~~Como coleccionista, quiero que si algo se tuerce, mi colección nunca se dañe~~ | ~~El instalador y el importador NUNCA borran archivos originales; solo copian/mueven a destinos verificados~~ | ✅ Hecho | S |
| A4 | Como coleccionista, quiero desinstalar sin dejar restos ni perder mi tebeoteca | `make uninstall` conserva biblioteca y BD con aviso claro | P1 | S |
| A5 | Como coleccionista con el disco casi lleno, quiero repartir tradiciones entre discos sin engañar al sistema | N carpetas-raíz; cada una asignada a una o varias tradiciones; el importer escribe en la raíz que le toca a esa tradición | P2 | L |
| A6 | Como coleccionista, cuando abra ZascArr fuera de localhost quiero contraseña y que funcione tras un reverse proxy | Auth none/password/user+password + `base_url` configurable | P1 | M |

**Notas de implementación (A2+A3, hecho):**

- **A2 (bootstrap en español llano):** cada punto de fallo de `bootstrap.sh`
  queda mapeado a una causa y una acción concretas en lugar de un "exit code":
  Docker ausente (cómo instalarlo), plugin compose ausente, demonio parado
  (`systemctl start docker`), disco de tebeos no montado ("no encuentro el
  disco… ¿está conectado?"), disco de descargas sin permisos, PostgreSQL/Redis
  que no levantan (apunta a `docker compose logs`), migraciones fallidas y
  ZascArr que no arranca. Añadido chequeo previo del demonio (`docker info`) y
  guardas `|| die` en cada `mkdir`/`cd`/`docker compose up`/`alembic`/`pip`.
- **A3 (nunca dañar la colección):** nuevo `src/zascarr/utils/fs.py` con
  `sanitize_segment` (un título con "/" o ".." ya no puede escapar de la
  biblioteca al construir la ruta canónica) y `safe_move`/`safe_move_async`
  (nunca sobreescribe un destino ocupado — elige nombre único con sufijo — y,
  entre discos distintos, copia a un temporal y verifica el tamaño ANTES de
  borrar el original; si la copia falla, el original queda intacto). Aplicado
  en `Importer._import_file` y `ReviewService.assign_to_series`, que antes
  usaban `shutil.move` a ciegas (sobrescribía en silencio). `build_library_path`
  sanitiza título y número de issue. Regresión: `tests/test_fs.py` y
  `tests/test_importer.py::TestBuildLibraryPathSanitizado`. El instalador
  documenta su garantía en cabecera: solo crea directorios y copia `.env`,
  jamás borra ni mueve ficheros de la colección.

### Épica B — "Importo mi caos actual"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| B1 | ~~Como coleccionista, quiero arrastrar mi carpeta de descargas y que el sistema la organice solo~~ | ~~El importador procesa `/downloads` y `_Unsorted/` según matcher/triage ya construidos, con informe final legible~~ | ✅ Backend hecho | M |
| B2 | ~~Como coleccionista, quiero ver los tebeos que el sistema no supo clasificar y decidir yo con un clic~~ | ~~Bandeja de "pendientes de revisar" en la UI: miniatura, título detectado, botones "es esta serie / ninguna / ignorar"~~ | ✅ Hecho | L |
| B3 | ~~Como coleccionista, quiero que los duplicados se detecten y no se importen dos veces~~ | ~~Dedupe por SHA256 ya existe; la UI muestra "duplicado de X, descartado" en el informe~~ | ✅ Backend hecho | S |
| B4 | ~~Como coleccionista, quiero que cada tebeo aparezca con portada, guionista, dibujante y sinopsis aunque el archivo no traiga metadatos~~ | ~~Enricher multi-fuente (Comic Vine/AniList/Tebeosfera; GCD pospuesto — ADR-0002) + corrección del bug de `metadata_source='manual'` (C3)~~ | ✅ Hecho | L |
| B5 | ~~Como coleccionista de tankōbon y álbumes BD, quiero que Vol./T/Tomo funcionen tan bien como el # americano~~ | ~~Tests de naming con fixtures reales de releases españolas (patrones `nº`, `v01c047` rescatados de zascarr)~~ | ✅ Hecho | M |
| B6 | Como coleccionista, quiero que mi biblioteca sea legible por Kavita/ComicTagger/cualquier otra herramienta sin depender de ZascArr | Tras enriquecer, escribir `ComicInfo.xml` dentro del CBZ (hoy solo se lee, nunca se escribe) | P1 | M |
| B7 | Como coleccionista, si borro un tebeo del disco a mano, quiero que deje de contar como "lo tengo" sin que yo avise | El ciclo de scan detecta `File.file_path` que ya no existe y lo marca desaparecido, con aviso en el informe del ciclo | P1 | S |
| B8 | Como administrador de la Pi, quiero apagar una fuente de metadatos (p.ej. Tebeosfera) sin redesplegar si se rompe su scraping | Toggle runtime por proveedor (`comicvine_enabled`/`anilist_enabled`/`tebeosfera_enabled` en `Settings`, mismo patrón que `forum_enabled`) + estado visible en el healthcheck | P1 | S |
| B9 | Como coleccionista, quiero que un número sin título no se quede "Issue 5 - Unknown" y que cada tradición nombre distinto sin que yo edite plantillas | Plantillas de naming por tipo (número / sin título / special version / pack) con padding configurable; UI solo on/off y preset | P2 | M |
| B10 | Como coleccionista, si descargo un pack con varios números quiero que se deshaga solo; y si llega un CBR, prefiero CBZ si es posible | Extracción de archives multi-número; conversión cbr→cbz opt-in con cadena de preferencia documentada | P2 | M |

**Notas de implementación:**

- **B4 (parcial, Comic Vine + AniList + Tebeosfera):** `EnrichmentService` enruta cada serie a UNA fuente según `Series.tradition`: `american`/`british` → Comic Vine, `manga`/`manhwa`/`manhua` → AniList, `tebeo`/`franco_belgian` → Tebeosfera. Solo `fumetti` queda sin fuente todavía. AniList y Tebeosfera enriquecen solo a nivel de Serie (título/sinopsis/portada/nº de números): ninguna tiene aquí un concepto de "issue" equivalente al de Comic Vine, así que `Issue.metadata_source` nunca se pone a `anilist` ni `tebeosfera`. Nuevas columnas `series.anilist_id` (migración `0003`) y `series.tebeosfera_slug` (migración `0004`, texto — Tebeosfera identifica por slug, no por ID numérico), paralelas a `comic_vine_id`.
- **B4 (Tebeosfera, hecho):** `src/zascarr/services/tebeosfera.py` — scraping de los dos endpoints AJAX internos del buscador de tebeosfera.com (sin API oficial), portado con inspiración de [theotocopulitos/tebeosfera-scraper](https://github.com/theotocopulitos/tebeosfera-scraper) tras leer su cliente HTTP y su parser. Confirmado en vivo contra el sitio real (no solo contra el repo de referencia, que puede haber quedado desactualizado): búsquedas de "Thorgal" (BD) y "Mortadelo y Filemón" (tebeo español) devuelven resultados correctos. Se encontró y arregló un bug real solo visible probando en vivo — `lxml.text_content()` no inserta espacio donde había un `<br>`, así que "1986 a 1988<br>4 números" se leía como el número de colección "19884" en vez de "4". GCD queda como única fuente pendiente — sin API ni referencia de scraping ya identificada, a diferencia de Tebeosfera.
- **B4 (H1+H2+H3 del peer review v2, hecho):** migración `0006`, una sola pasada porque las tres tocan schema.
  - **H1 (tildes en el matcher):** `matcher.find_series` comparaba `lower(title)` crudo contra un `:norm` ya sin acentos/puntuación — un título con tilde en BD ("Nausicaä") nunca hacía exact-match con un archivo sin tilde ("Nausicaa"). Se añadió `series.title_norm` (columna generada por Postgres, `f_title_norm(title)`, espejo inmutable de `core.matcher.normalize_title`) y el matcher pasa a consultar contra ella. Verificado con una batería de títulos patológicos, no solo los de la propuesta original, encontrando y corrigiendo **dos divergencias reales** antes de aceptar la función: (1) `f_title_norm` no replicaba el paso que quita puntos de abreviación antes de la limpieza general ("S.H.I.E.L.D." salía "s h i e l d" en vez de "shield"); (2) el patrón de artículo inicial no cubría el caso de un título que ES solo el artículo ("The" a secas quedaba en "the" en vez de ""), un caso que el propio `matcher.py` ya documentaba como corrección deliberada en Python. Test de paridad automatizado en `tests/test_title_norm.py` (se salta si no hay `TEST_DATABASE_URL` — es la única prueba de la suite que toca Postgres real).
  - **H2 (caché negativa del enricher):** una serie/issue sin match en ninguna fuente entraba en el batch en CADA ciclo para siempre, quemando rate limit de APIs externas en búsquedas condenadas. Ahora `enrichment_attempted_at` (columnas nuevas en `series`/`issues`) marca el intento — con match o sin él — y solo se reintenta pasados 30 días o si nunca se intentó. Un fallo de red (excepción) NO marca el intento, para poder reintentar en el siguiente ciclo en vez de esperar 30 días.
  - **H3 (`locked_fields` mal ubicado):** por un descuido de la migración `0001`, `locked_fields` había aterrizado solo en `wishlist`, donde ningún código lo leía. Se movió a `series`/`issues`/`creators`/`characters`. Caso de uso inmediato: `ReviewService.assign_to_series` creaba el `Issue` al vuelo con `metadata_source='manual'` para proteger la asignación serie+número, pero eso bloqueaba TAMBIÉN sinopsis/portada/créditos que el enricher debería poder rellenar después. Ahora usa `locked_fields=['series_id', 'issue_number']` — protege solo la asignación, el resto del enriquecimiento sigue funcionando.
  - **Bugs de infraestructura encontrados de paso (no venían en el review), corregidos en el mismo commit:**
    - La migración `0001` **nunca había podido aplicarse contra una base de datos realmente vacía**, desde el origen del proyecto — confirmado con Postgres real (contenedor limpio, offline SQL vía `alembic upgrade head --sql` aplicado con `psql`), no una suposición. Cada `sa.Enum(...)` usado en `op.create_table()` volvía a emitir `CREATE TYPE` aunque el tipo ya se hubiera creado a mano unas líneas antes en la misma migración (cada `create_table` es un contexto de compilación DDL independiente sin memoria de eso), y además `create_type=False` no es un parámetro real del `sa.Enum` genérico de SQLAlchemy — se acepta en silencio y se ignora; hace falta `postgresql.ENUM` explícito para que surta efecto.
    - Los 6 `Enum(PythonEnum, name=...)` del ORM (`models/__init__.py`) mandaban el `.name` del enum de Python (mayúsculas, p.ej. `"AMERICAN"`) en vez del `.value` (minúsculas, `"american"`) — que es justo lo que el tipo `comic_tradition` de Postgres acepta. Ninguna escritura ORM de `tradition`/`format`/`role`/`file_format`/`status` (wishlist y reading_progress) había funcionado nunca contra una Postgres real. Corregido con `values_callable=lambda obj: [e.value for e in obj]` en los 6.
- **B5 (hecho):** `naming.py` ahora resuelve los 8 casos reales de `tests/test_naming_core.py::TestRealWorldFilenames`, incluyendo "Batman_v2_012" (guion bajo como separador), "Batman (New 52) 012 (2013)" (paréntesis de reboot no confundidos con año), "Sandman.001.(1989)" (años 19xx, no solo 20xx), "MF #001 - Safari Callejero" y "Asterix T01 - Asterix el Galo" (subtítulo tras " - ", y "T01" de BD de tomo único tratado como número, a diferencia de "Vol."/"Tomo N" que siguen siendo volumen puro).
- **B1/B3 (backend hecho, falta UI):** `Importer.scan_and_import()` ahora devuelve un `ImportReport` (importados/duplicados/sin-clasificar/errores, en líneas legibles) y corre solo como job periódico en `main.py` (antes `import_interval_minutes` era un ajuste sin usar — el importador nunca se ejecutaba solo). Cada ciclo se persiste en la nueva tabla `import_runs` (migración `0002`), idea rescatada de zascarr (`scrape_runs`) para poder responder "¿qué pasó en el ciclo de las 03:00?" desde una futura UI. Sin endpoint API todavía — eso le toca a B2/Épica C cuando haya UI que lo consuma.
- **B4 (cierre formal, ADR-0002):** declarada completa con alcance Comic Vine
  + AniList + Tebeosfera, que cubren **7 de las 9** tradiciones
  (`american`/`british` → Comic Vine; `manga`/`manhwa`/`manhua` → AniList;
  `tebeo`/`franco_belgian` → Tebeosfera). GCD queda pospuesta a post-1.0 con
  estrategia de mirror local de dumps (no API en vivo); quedan sin fuente
  `fumetti` (pospuesto a GCD) y `other` (cajón de sastre). De paso se corrigió
  que las series sin fuente se re-seleccionaran en cada ciclo acaparando el
  lote: ahora se marcan `enrichment_attempted_at` igual que las que no
  encuentran match (H2). Decisión completa en `docs/adr/0002-enricher-scope.md`.

### Épica C — "Exploro y leo mi tebeoteca"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| C1 | ~~Como coleccionista, quiero ver mi biblioteca en una web bonita desde el móvil o el sofá, ordenada por serie, autor o nacionalidad~~ | ~~Kavita cubre lectura; ZascArr aporta el *catálogo enriquecido*: UI propia con filtros por tradición, editorial, personaje, saga~~ | ✅ Hecho | L |
| C2 | ~~Como coleccionista, quiero saber de un vistazo qué números me faltan de cada serie~~ | ~~Vista "huecos" por serie: `missing` ya existe en API; corregir el bug de `sort_order` truncado detectado en el review~~ | ✅ Hecho | M |
| C3 | Como coleccionista, quiero marcar un tebeo como leído y puntuarlo | `reading_progress` ya está en el modelo; falta exponerlo + UI | P1 | M |
| C4 | Como coleccionista, quiero listas como "Court of Owls en orden" aunque crucen varias series | `story_arc_issues.reading_order` ya soporta crossovers; falta UI de arcos | P1 | M |
| C5 | Como coleccionista, quiero leer mi catálogo enriquecido desde cualquier lector (tablet, e-reader) sin pasar por Kavita | Endpoint OPDS de solo catálogo (no de contenido) sobre los datos ya enriquecidos | P2 | M |
| C6 | Como coleccionista, quiero un botón en cada serie que detecte los números que me faltan y los ponga todos en búsqueda, para completar sagas sin ir número a número | Desde la ficha de serie (`/ui/series/{id}`, ya existe desde C2), "Completar" crea los items de wishlist correspondientes a `missing`, visibles con su estado en `/ui/wishlist` | P1 | M |
| C7 | Como coleccionista curioso, quiero que cada carpeta de serie lleve un fichero que describa su estado, para que otras herramientas lo lean sin hablar con la API | `series.json` por carpeta de serie, regenerado tras cada cambio relevante | P2 | S |

**Notas de implementación (Fase 6 / UI web):**

- **Decisión de arquitectura:** ver [`docs/adr/0001-ui-stack.md`](adr/0001-ui-stack.md) — Jinja2 servido por el propio FastAPI + HTMX vendorizado (no CDN), sin SPA ni build de Node. Primer ADR del repo; las decisiones previas (PostgreSQL, enrutado del enricher) no quedaron documentadas como ADR retroactivamente.
- **Esqueleto:** `src/zascarr/web/` (router `/ui`, `Jinja2Templates`, layout `base.html` con nav), `src/zascarr/static/vendor/htmx.min.js` (v4.0.0, verificado en un navegador real antes de vendorizarlo), `src/zascarr/static/web.css`. El dashboard de E1 se queda como está por ahora (página autocontenida que funciona); se migra a este layout cuando exista otra pantalla más con la que compartir cabecera.
- **B2 (hecho), primera pantalla real:** `src/zascarr/web/pendientes.py` — bandeja en `/ui/pendientes` sobre `ReviewService` (`src/zascarr/services/review.py`). Dos acciones, no tres: "es esta serie" (busca y asigna, creando el `Issue` al vuelo si el número no existe — marcado `metadata_source='manual'`, igual que el `File`, así el enricher nunca lo toca) e "ignorar" (nueva columna `files.review_dismissed`, migración `0005`). "Ninguna" se fusionó con "ignorar" — sin candidatos del matcher persistidos en BD, mantenerlas separadas no aportaba distinción real (ver hilo de decisión). Miniaturas extraídas bajo demanda de la primera página del CBZ y redimensionadas con Pillow (`src/zascarr/utils/cover.py`); CBR se queda sin miniatura a propósito (necesitaría unrar). Verificado en un navegador real de principio a fin: listar, buscar, asignar (con movimiento de archivo real a disco, confirmado con `find`), ignorar, y que ambas acciones persisten tras recargar. Nota de la propia verificación: el disparo `hx-trigger="keyup changed"` no siempre reaccionaba a la escritura simulada por la herramienta de automatización del navegador (sí a un evento `keyup` real) — probable limitación de la herramienta, no del código, pero queda anotado por si un usuario real reporta que la búsqueda no responde al teclear.
- **C2 (hecho):** el bug de `sort_order` truncado era real —
  `int(1.5) == 1` hacía que un Annual/especial "cubriera" el hueco del
  número entero adyacente aunque ese número no existiera de verdad.
  Extraído `compute_missing_issues()` (`api/series.py`) como función
  compartida: un hueco `i` solo se da por cubierto si existe un `Issue`
  cuyo `sort_order` es EXACTAMENTE `float(i)`, no su truncamiento. Usada
  tanto por `GET /api/series/{id}/missing` como por la nueva
  `GET /ui/series/{id}` (ficha de serie **mínima**: solo números
  presentes/ausentes, sin pósters/filtros/navegación — eso es trabajo de
  C1, que sigue sin construir; esta pantalla se ampliará o rehará
  cuando llegue, no es el diseño final, y por eso no tiene enlace en el
  topnav — no hay desde dónde navegar a ella todavía). Test de
  regresión con `sort_order=1.5` en `tests/test_api_series.py` y
  `tests/test_web_series.py`. Verificado en un navegador real contra
  Postgres real con el caso exacto del bug: una serie con SOLO un
  Annual `sort_order=1.5` (sin el `1.0`) muestra correctamente `#1` como
  pendiente — con el código anterior se habría dado por presente.
- **C1 (hecho):** `/ui/biblioteca` — primera pantalla de navegación real
  de la biblioteca (hasta ahora solo había pantallas de un único
  propósito). Filtros por tradición/editorial (dropdown) y
  personaje/saga (búsqueda-y-navegación, universo demasiado grande para
  un dropdown); clic en una tarjeta lleva a la ficha de C2, que por fin
  tiene desde dónde ser alcanzada (gana portada + editorial + géneros +
  enlace de vuelta). `SeriesService` (`services/series.py`) centraliza
  el listado/filtrado — usado tanto por la API JSON como por la UI, con
  JOIN explícito (no `.any()` anidado) para personaje/saga, verificado
  con Postgres real (no solo `FakeSession`, que no detecta un JOIN M:N
  mal construido): `Series → Issue → issue_characters`/`StoryArcIssue`.
  - **Portadas — cascada unificada de 3 niveles**: (1) primera página
    del CBZ ya importado más antiguo, (2) `cover_url` externo descargado
    y cacheado una sola vez, (3) placeholder si no hay ninguna — nunca
    se cachea una ausencia. Todo el resultado (venga de CBZ o de fuente
    externa) se escribe a un único fichero en disco
    (`covers_cache_path/{series_id}.jpg`), así que una segunda petición
    no vuelve a tocar ni el CBZ ni la red. **Cierra M4** de paso (el
    thumbnail de B2 nació sin cabeceras de caché): `cached_image_response`
    compartida entre `pendientes.py` y `series.py` (304 con `If-None-Match`,
    `Cache-Control: private, max-age=86400`).
  - **Bug real encontrado probando en vivo** (no algo que un mock hubiera
    revelado): `httpx.AsyncClient` no sigue redirecciones por defecto, y
    tanto `picsum.photos` (usado para verificar esto) como CDNs reales de
    portadas devuelven 302 con normalidad — sin `follow_redirects=True`,
    `raise_for_status()` trataba el redirect como fallo y ninguna portada
    externa se descargaba nunca. Corregido y reverificado en vivo.
  - **Bug real encontrado probando en un navegador real**: los campos
    ocultos del formulario de filtros (`publisher_id`/`character_id`/
    `story_arc_id`) llegan como `""` cuando no hay selección, no
    ausentes de la query string — un parámetro `UUID | None` de FastAPI
    no acepta `""` y daba 422 en cuanto se tocaba cualquier otro filtro.
    Corregido convirtiendo a mano (`_uuid_or_none`) y añadido como test
    de regresión explícito (ningún test con query string vacía lo había
    cubierto hasta entonces).
  - Trabajo bloqueante (zipfile, Pillow, descarga, disco) siempre en
    `asyncio.to_thread`/`httpx.AsyncClient`, con un semáforo
    (`asyncio.Semaphore(2)`) limitando descargas externas concurrentes —
    no disparar una ráfaga al CDN cuando una rejilla entera carga en frío.
  - **Deuda registrada, no resuelta aquí**: la caché de portada en disco
    no se invalida nunca automáticamente — si una serie cachea primero
    la externa y más tarde llega un archivo real, o si el enricher
    cambia de fuente, el fichero viejo se sirve indefinidamente hasta
    que alguien lo borre a mano. Aceptable para una biblioteca personal
    de un solo usuario; revisar si algún día se vuelve confuso en la
    práctica.
  - Nuevo volumen Docker + `mkdir` en `bootstrap.sh` para
    `covers_cache_path` (`/mnt/nvme/tebeoteca/config/covers`, mismo
    patrón que `config/{postgres,redis}`).

### Épica D — "El sistema busca lo que me falta"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| D1 | ~~Como coleccionista, quiero marcar "quiero esta serie" y olvidarme: el sistema la encuentra y la añade~~ | ~~Wishlist → orchestrator → Transmission/aMule → import; visible como "Buscando... Descargando... En tu biblioteca" en la UI, con reintento automático de candidato y de búsqueda~~ | ✅ Hecho | L |
| D2 | Como coleccionista, quiero elegir "solo CBZ de calidad" o "acepto escaneos" sin entender qué es un quality profile | Selector de 3 opciones legibles ("solo lo mejor / equilibrado / lo que haya"); mapea a `quality_tier` interno | P1 | M |
| D3 | Como coleccionista, quiero que si sale una edición mejor de algo que ya tengo, el sistema me la ofrezca | Lógica de upgrade sobre `quality_tier`; la UI propone, no sustituye sin confirmar | P1 | M |
| D4 | ~~Como coleccionista, quiero que el sistema me avise si está descargando sin VPN sin que se pare todo~~ | ~~Warning del healthcheck visible como aviso en UI + log del orchestrator (decisión ya acordada, ver fix C2)~~ | ✅ Hecho (vía E1) | S |
| D5 | Como coleccionista, quiero ver lo que sale esta semana —tanto grapa americana como novedades de Norma/ECC/Panini España— de las series que sigo, para no perderme lanzamientos | Vista de novedades agrupada por semana y filtrable por editorial; doble track por tradición (Comic Vine para fechas futuras USA, scrapers editoriales españoles para el resto); cada novedad se cruza contra wishlist/series monitorizadas y queda marcada "Te interesa" | P2 | L |
| D6 | Como coleccionista, quiero agrupar series en colecciones ("grapas en curso", "clásicos Bruguera") y que cada colección decida si se busca, con qué fuentes y con qué calidad | Tabla `collections` con políticas tri-estado (include/exclude/unset) de auto-búsqueda aplicadas en el orquestador; una serie sin colección conserva el comportamiento actual | P1 | M |
| D7 | Como coleccionista, quiero pedir un arco argumental entero aunque cruce varias series, en orden de lectura | Wishlist por `story_arc` que genera items por issue respetando `reading_order` | P2 | L |

### Épica E — "Confío en el sistema"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| E1 | ~~Como coleccionista, quiero una pantalla de estado con semáforos ("todo bien / atención: sin VPN / error: disco lleno")~~ | ~~Dashboard sobre `/api/health` con iconos y textos en español, no JSON~~ | ✅ Hecho | M |
| E2 | ~~Como coleccionista, quiero que haya copias de seguridad automáticas sin configurar nada por mi parte~~ | ~~Cron de `pg_dump` a segundo disco (el backup actual al mismo disco del dato era hallazgo del review)~~ | ✅ Hecho | S |
| E3 | Como coleccionista, quiero un botón "restaurar copia" si algo sale mal | Script de restore documentado y probado (el test del backup no es hacerlo, es restaurarlo) | P1 | M |
| E4 | Como coleccionista, quiero un aviso al móvil cuando una descarga se importa, para no estar mirando el dashboard | Webhook configurable (Gotify/ntfy/Telegram/URL genérica) al completar descarga+import; desactivado por defecto | P1 | S |
| E5 | Como coleccionista que reporta un fallo, quiero un botón en el dashboard que genere un fichero con los logs recientes, sin tocar la terminal | Botón "Descargar logs" en el dashboard, sin acceso a shell | P2 | S |

**Notas de implementación (E1/A1/E2/D4):**

- **E1 (dashboard):** `src/zascarr/static/dashboard.html`, servido en `GET /` (antes esa ruta no existía; la API vivía solo bajo `/api/*`). Página única sin build tooling, sondea `/api/health` cada 10s. Verificado visualmente en el navegador en los 4 estados (todo bien / atención / error / sin conexión) y en viewport móvil. Al mostrar el array `warnings` del healthcheck (VPN sin proteger, etc.) como un aviso visible, esta misma pieza cierra también **D4**.
- **E1 (empaquetado):** `pyproject.toml` no incluía datos no-Python en `pip install .` (no editable, el que usa el Dockerfile) — sin `[tool.setuptools.package-data]`, `dashboard.html` no habría llegado a la imagen. Verificado con una instalación real no-editable en un venv limpio.
- **A1 (bootstrap.sh):** 3 preguntas (biblioteca, raíz de descargas, idioma), escritas en `.env` de forma idempotente (`set_env_var`, no duplica al re-ejecutar). `docker-compose.yml` parametriza el lado HOST de los 3 volúmenes correspondientes (`HOST_LIBRARY_DIR`, `HOST_DOWNLOADS_DIR`, `HOST_AMULE_INCOMING_DIR`) manteniendo el lado del contenedor fijo, así que `config.py` no necesitó cambios. El idioma se guarda en `APP_LOCALE` para cuando exista i18n real — hoy no traduce nada. Probado en aislamiento (sin Docker) con respuestas por defecto y personalizadas, incluyendo idempotencia.
- **E2 (backup):** `scripts/backup.sh` (mismo patrón que `vpn-state.sh`: script host + timer systemd embebido), escribe en `/media/WDElements/backups/postgres/` (disco distinto al de los datos) con retención automática de 14 días. `make backup` ahora lo invoca en vez de duplicar la lógica.

**Notas de implementación (D1):**

- **El backend de búsqueda/descarga ya existía y era sustancial**
  (`orchestrator.py`, `transmission.py`, `amule.py`, `prowlarr.py`,
  `forum_scraper.py`) pero D1 no funcionaba en absoluto: tenía tres huecos
  sin documentar, encontrados al explorar el repo para esta historia.
  - **El orquestador nunca se ejecutaba solo** — mismo bug de fondo que
    B1/B3 encontraron en el importador antes de arreglarlo:
    `scan_interval_minutes`/`max_concurrent_downloads` eran ajustes que
    nadie leía, ningún código llamaba `process_wishlist()` jamás. Fijado
    con un `_orchestrator_loop` en `main.py`, calcado de
    `_import_loop`/`_enrichment_loop`.
  - **Un item sin resultados o cuya descarga fallaba se abandonaba para
    siempre** — mismo bug que H2 del enricher (peer review v2), aplicado
    aquí: `process_wishlist` solo seleccionaba `status == WANTED`, así que
    un `FAILED` no se reintentaba nunca, y uno sin resultados se
    reintentaba en CADA ciclo sin límite. Fijado con un cooldown de
    `orchestrator_retry_cooldown_hours` (6h por defecto, config.py) sobre
    `last_searched_at` — mismo patrón que `enrichment_attempted_at`.
  - **Nada cerraba el círculo "descargado → en tu biblioteca"**: cero
    referencias a `WishlistStatus.DOWNLOADED`/`IMPORTED` en todo el código
    aparte de su propia definición. En vez de scrapear el estado de
    Transmission/aMule (aMule no da nombre/hash del completado hoy, solo
    un % global), `Orchestrator.check_completions()` comprueba si ya
    existe un `File` enlazado al `Issue`/`Series` que el item pedía — el
    import loop periódico ya existente es quien de verdad clasifica el
    archivo, esto solo refleja ese hecho en la wishlist. Agnóstico de
    backend, sin scraping frágil de HTML de aMule.
- **Reintento con el siguiente candidato del pool (idea de Mylar3,
  benchmarking anterior):** si el mejor resultado falla al enviarse al
  backend de descarga, se prueba el siguiente en vez de rendirse a la
  primera. `_select_best` pasó a `_ranked_candidates` (devuelve todo el
  pool rankeado, no solo el ganador).
- **M1 cerrado de raíz** (no en otra pasada): `Wishlist(**data)` y
  `setattr(item, field, value)` sobre el body crudo en `api/wishlist.py`
  sustituidos por `WishlistCreate`/`WishlistUpdate` (Pydantic, campos
  explícitos) delegando en el nuevo `WishlistService`
  (`src/zascarr/services/wishlist.py`) — misma fuente de verdad para
  la API JSON y la nueva UI, sin lógica duplicada.
- **UI**: `/ui/wishlist` (`src/zascarr/web/wishlist.py`), mismo patrón
  HTMX que `pendientes.py` — buscar una serie ya catalogada, añadirla,
  ver su badge de estado ("Buscando…"/"Descargando…"/"En tu
  biblioteca"/"Sin resultados"), reintentar manualmente o quitarla.
  Verificado en un navegador real de principio a fin contra Postgres real
  (no solo con FakeSession): buscar, añadir, recargar y comprobar que
  persiste, quitar, recargar y comprobar que desaparece. El botón
  "Quitar" usa `hx-confirm` (diálogo nativo del navegador) — la
  herramienta de automatización no lo acepta sola (mismo tipo de
  limitación que el `hx-trigger="keyup changed"` de B2, confirmado
  disparando la petición directamente por fetch: el backend responde
  bien, es la herramienta la que no interactúa con el diálogo nativo).
- **Verificación end-to-end contra Postgres real**, no solo con dobles:
  migración 0001→0007 aplicada de cero; un ciclo completo simulado
  (`Series` + `Wishlist` WANTED → `Orchestrator` con Prowlarr/Transmission
  simulados → `DOWNLOADING` con `download_ref`/`download_backend`
  correctos → insertar el `File` que el import loop habría creado →
  `check_completions` → `IMPORTED` con `downloaded_at`); y un segundo
  ciclo confirmando que un `FAILED` reciente NO se reintenta antes del
  cooldown (Prowlarr no se vuelve a llamar).
- **Fuera de alcance deliberado**: tabla `OrchestratorRun` estilo
  `ImportRun` para historial (no la pide el criterio de aceptación);
  ampliar `AMuleClient`/`TransmissionClient` (no hace falta, ver arriba);
  cancelar/pausar una descarga en curso desde la UI (solo "quitar" antes
  de que empiece a descargar, vía el `DELETE` ya existente).
**Notas de implementación (D5 — módulo Novedades, spec recibida
2026-09-22, NO implementado todavía):**

- Spec completa en `/mnt/Datos/Descargas/SPEC_MODULO_NOVEDADES.md` (fuera
  del repo — copiar a `docs/` si se decide construir, para que no se
  pierda): tabla `novedades` nueva, scrapers Comic Vine (reutiliza
  `ComicVineClient`) + Norma/Panini/ECC (HTML nuevo) + Whakoom opcional,
  `NovedadItem` como contrato Pydantic entre scrapers y core, matching
  contra `series.title_norm` (exacto, luego fuzzy pg_trgm ≥0.60), job
  semanal, endpoint `/api/novedades`, pantalla `/ui/novedades`.
- **Dos correcciones antes de dar la spec por buena:**
  - **La migración que propone es `0007`, pero ese número ya existe**
    (`20260921_0007_wishlist_download_ref.py`, de D1). La tabla
    `novedades` sería `0008`. Revisar el resto de la spec por si asume
    algo más sobre el estado de las migraciones que ya no es cierto.
  - **La spec asume que ya existe un patrón `optional=True` en los
    scrapers ("mismo patrón que el scraper del foro CRG") — no existe.**
    Verificado de nuevo contra el código (tercera vez que un documento
    externo da esto por hecho): ningún scraper del repo tiene un
    parámetro `optional`; `forum_enabled` es un booleano de config para
    activar/desactivar la fuente del foro, no un mecanismo genérico
    reutilizable. Este mecanismo es exactamente **F15/B8** (toggle por
    proveedor), que sigue sin construir — la spec de Novedades lo da por
    prerequisito sin serlo todavía.
- **Dependencias reales, no las que asume el orden sugerido de la spec**
  ("tras H1-H3 y F1/F2"): H1-H3 sí están hechos. F1 (reintento) también,
  pero solo la parte de reintento — el "motivo de fallo legible" que F1
  también pedía sigue pendiente (ver nota de D1 arriba). **F2 NO está
  hecho** (ni el fix de `sort_order` ni el botón "Completar", C6) — la
  propia spec depende de un estado que todavía no existe. F4 (webhooks),
  F15/B8 (toggle por proveedor) y C1/C2 (ficha de serie) tampoco existen,
  y la spec los da por disponibles en varios puntos (notificación al
  casar novedad, ficha de serie con insignia "próximo número").
- **No verificado en vivo todavía**: a diferencia de Tebeosfera (scrapeado
  y confirmado contra el sitio real antes de construir el cliente), no se
  ha comprobado la estructura HTML real de Norma/Panini/ECC/Whakoom. Antes
  de escribir un solo scraper nuevo, tocaría repetir esa disciplina —
  visitar los sitios reales, confirmar que la cadencia semanal/rate limit
  propuestos son viables, y que el HTML no cambia tan rápido como para
  que el diseño "un WARNING silencioso si rompe" sea suficiente en la
  práctica.
- **Fuera de alcance de la v1 (según la propia spec, razonable):**
  disparar descargas automáticas desde novedades, precios históricos,
  novedades de tiendas/quiosco.

- **Hueco confirmado por el benchmarking de ronda 2 (F1):** el reintento
  con el siguiente candidato ya está (ver arriba), pero un `FAILED` no
  guarda ningún motivo legible en ningún sitio — solo hay un
  `logger.exception` sin persistir. La UI de `/ui/wishlist` muestra "Sin
  resultados" para cualquier fallo, sin distinguir "nada encontrado" de
  "Transmission no responde". Pendiente: columna `Wishlist.last_error`
  (texto corto) rellenada en el `except` de `process_wishlist` y en la
  rama "todos los candidatos fallaron" de `_process_item`, mostrada en
  la fila de la wishlist.

## Deuda técnica registrada (peer review v2, hallazgos medios)

Sin arreglar todavía — nombrados aquí a propósito para que no vuelvan a caer
en el agujero de "estaba en el review pero nadie lo pasó al board":

- **M1 — mass assignment en la API — cerrado.**
  Se cerró para `api/wishlist.py` en D1 y, para `api/series.py`, con
  `SeriesCreate`/`SeriesUpdate` Pydantic (`extra="forbid"`, campos
  explícitos snake_case) en POST/PATCH. Regresión en `tests/test_api_series.py`
  (campos internos como `id`, `metadata_source`, `locked_fields` → 422).
- **M2 — normalizador duplicado:** `naming.normalize_series_name` y
  `matcher.normalize_title` resuelven un problema parecido (limpiar un
  título para comparar) con lógica independiente y ya divergente en algún
  matiz. Unificar o documentar explícitamente por qué deben seguir siendo
  dos, antes de que una tercera copia aparezca en el enricher.
- **M3 — `bootstrap.sh` sigue instalando con `pip install --break-system-packages`
  en el host** para poder correr las migraciones fuera de Docker. Frágil en
  distros que no sean Debian/Ubuntu recientes; considerar ejecutar la
  migración inicial dentro de un contenedor efímero en su lugar. Relacionado:
  migrar Alembic a contenedor también permitiría **eliminar el
  `ports: 127.0.0.1:5432` de PostgreSQL** (hoy el bootstrap corre `alembic`
  en el host contra loopback; sin ese `ports` bastaría con `expose`).
- **M5 — caché de portada en disco sin invalidación (de C1):**
  `covers_cache_path/{series_id}.jpg` se escribe una vez y no se vuelve
  a comprobar nunca. Si se cachea primero una portada externa y más
  tarde llega un archivo real, o si el enricher cambia de fuente, el
  fichero viejo se sirve indefinidamente hasta que alguien lo borre a
  mano. Aceptable para una biblioteca personal de un solo usuario por
  ahora; revisar si se vuelve confuso en la práctica.
- **Riesgo symlink (seguridad, P0-4):** si un usuario crea manualmente un
  symlink en `DOWNLOADS_PATH` apuntando fuera, el importador podría seguirlo
  al leer/copiar. Riesgo bajo en single-user. Mitigación: documentar en
  README.md que no se deben crear symlinks en la carpeta de descargas.
- **Deuda P1 — `ReviewService.assign_to_series` mueve archivos con la sesión
  abierta:** `safe_move_async` ocurre con la transacción de BD viva; si el
  proceso muere entre el move y el commit, fichero y BD divergen. Solución
  completa: tabla `file_operations` con estados y un reconciliador al arrancar.
  Para 1.0 se acepta el riesgo (single-user, sin concurrencia masiva).

## Benchmarking competitivo (2026-09-21)

Comparado contra tres proyectos del mismo espacio para no reinventar ni
perder de vista el hueco real:

- **[Kapowarr](https://github.com/Casvt/Kapowarr)** (Python, GPL-3.0): el más
  parecido en forma (UI server-side, Docker, Pi-friendly). Solo Comic Vine
  como fuente, descarga por DDL (MediaFire/Mega/GetComics, sin eD2K), sin
  naming consciente de tradición. Confirma que el ADR-0001 (server-side, sin
  SPA) es la elección correcta para este dominio.
- **[Mylar3](https://github.com/mylar3/mylar3)** (Python, GPL-3.0): el veterano
  del espacio arr-cómic. Aporta tres ideas de valor que ZascArr no
  tiene todavía — pull-list/calendario de lanzamientos (**D5** arriba),
  reintento automático con el siguiente resultado si una descarga falla
  (nota añadida a **D1**), y escritura de `ComicInfo.xml` tras enriquecer
  (**B6** arriba) para que la biblioteca sea legible por cualquier otra
  herramienta sin pasar por la API de ZascArr. Mismo punto ciego que
  Kapowarr: solo Comic Vine, sin tebeo español.
- **[Suwayomi-Server](https://github.com/Suwayomi/Suwayomi-Server)**
  (Kotlin/JVM, MPL-2.0): servidor de manga con arquitectura de fuentes como
  plugins independientes y OPDS nativo (**C5** arriba). JVM no encaja en el
  presupuesto de memoria de una Pi junto al resto del stack — se estudia
  como referencia de diseño, no se integra.
- **Corrección sobre una idea propuesta en el análisis:** se sugirió que
  Tebeosfera ya tenía un flag `optional=True` y que solo faltaba "el toggle
  operativo" para poder desactivar fuentes de enriquecimiento sin
  redeploy. Verificado contra el código actual: **no existe tal flag** — ni
  en `tebeosfera.py`, ni en `enricher.py`, ni en `config.py` (que sí tiene
  `forum_enabled`, pero para la fuente de descarga del foro, sin relación
  con el enricher). Un toggle por fuente (`comicvine_enabled`,
  `anilist_enabled`, `tebeosfera_enabled` en `Settings`, mirando el patrón
  ya usado por `forum_enabled`) sigue siendo una mejora barata y razonable
  — pendiente de registrar como historia si se decide priorizar — pero
  parte de cero, no de una base ya construida.
- **Ninguno de los tres cubre tebeo español con fuentes honestas + eD2K**:
  ese sigue siendo el hueco real de ZascArr frente a los tres.

## Benchmarking competitivo, ronda 2 (2026-09-22)

El usuario trajo un segundo documento de benchmarking (mismas tres
herramientas, análisis más profundo: 16 historias F1-F16 + lecciones de
modelo de datos). Antes de registrar nada se verificó cada claim contra
el código real — tres de las 16 historias resultaron ser lo mismo que ya
se había registrado la ronda anterior, y de paso se encontraron dos
huecos reales no mencionados por ningún documento:

- **F3 = B6, F5 = D5** exactamente (mismo alcance) — no se duplican,
  solo se referencian.
- **F9 vs C5: relacionadas pero no iguales.** C5 se decidió a propósito
  como "solo catálogo, no contenido". F9 añade OPDS-PSE (streaming
  progresivo de páginas), que ES servir contenido — en tensión directa
  con esa decisión. Se deja fuera de C5 por ahora (ver "Lo que no se
  roba" más abajo); si algún día se quiere lectura progresiva por OPDS,
  es una historia nueva, no una ampliación silenciosa de C5.
- **F1 (reintento) ya estaba hecho por D1** (ver sus notas); lo que
  faltaba de verdad —motivo de fallo legible— se registró como hueco
  pendiente en las notas de D1, no como historia nueva.
- **F2 llevó a revisar `api/series.py` de verdad, no solo confiar en la
  descripción del documento**: confirmado el bug de `sort_order`
  truncado (`int(r) for r in ... Issue.sort_order`, con `sort_order`
  siendo `Float` — un `1.5` trunca a `1` y puede colisionar con el
  issue entero 1 en el cálculo de huecos) — ya estaba anotado en C2
  desde el review anterior, esto solo lo confirma con el código delante.
  De paso se encontró que **M1 (mass assignment) no estaba tan cerrado
  como decía este mismo documento el día anterior**: `api/series.py`
  tiene el mismo `Series(**data)`/`setattr` crudo que `api/wishlist.py`
  tenía antes de D1, sin tocar. Corregido el propio backlog (ver M1
  arriba) — más vale corregirse a uno mismo que dejar un "cerrado" falso.
- Los 16 ítems restantes (F4, F6, F7, F8, F10-F16) se registraron como
  historias nuevas en sus épicas correspondientes (A5/A6, B7-B10, C6/C7,
  D6/D7, E4/E5) — ninguno estaba construido, confirmado contra el código
  antes de anotarlo, no solo contra lo que decía el documento.

**Lecciones de diseño del documento (no son historias, son principios):**

- **Validado por comparación, no tocar:** JSONB por entidad para
  metadata suelta (mismo patrón que el `memo` de Suwayomi), IDs de
  proveedor en columnas paralelas en vez de una clave global acoplada a
  una sola fuente (a diferencia de Mylar3, que usa el ID de Comic Vine
  como clave y se queda cojo sin él), `issue_number VARCHAR + sort_order
  FLOAT` (Suwayomi necesitó un módulo entero para resolver lo que este
  diseño ya resolvía, aparte del propio bug de truncado de arriba),
  `story_arc_issues.reading_order` (ya modelado antes de mirar a la
  competencia).
- **Regla nueva, pendiente de auditar:** no mantener la transacción de
  BD abierta cruzando un `shutil.move` de archivo grande — el tracker de
  Kapowarr está lleno de bloqueos de SQLite por esto. ZascArr usa
  Postgres (MVCC, no bloqueo de fichero completo), así que el riesgo no
  es idéntico, pero `ReviewService.assign_to_series` y el importer sí
  hacen `shutil.move` con la sesión de la request todavía abierta — no
  es un incidente confirmado, pero vale la pena revisar si conviene
  mover primero y hacer el upsert en una transacción corta después,
  antes de que la biblioteca crezca lo bastante para que un `move` de
  archivos grandes tarde de verdad.
- **Regla nueva:** cualquier `UNIQUE` de una tabla gestionada desde la UI
  necesita reconciliación amable (upsert/mensaje claro), no una excepción
  cruda de integridad — Kapowarr tiene un bug abierto justo por esto con
  sus carpetas raíz. Aplica el día que exista alguna tabla así en
  ZascArr (hoy ninguna se gestiona desde la UI salvo `wishlist`, que
  no tiene UNIQUE propio).

**Lo que no se roba (y por qué), del propio documento — confirmado
razonable:** Comic Vine como fuente única (mata el diferencial), NZB/
usenet (ecosistema ajeno), extensiones Tachiyomi/JVM (no cabe en la Pi),
GraphQL como segunda API (REST+OPDS bastan para un usuario), WebView
embebido para logins (la vía de cookies exportadas ya lo cubre), sync de
progreso con trackers externos (duplica a Kavita), editor de plantillas
de naming con variables en UI (demasiada superficie para el
coleccionista) — y, añadido en esta ronda, **OPDS-PSE** (streaming de
contenido) por la misma razón que ya motivó que C5 fuera solo catálogo.

## Fuera de alcance (parking lot honesto)

Multiusuario con perfiles, sincronización de lectura entre dispositivos (es de
Kavita), app móvil nativa, descubrimiento por recomendación IA, integración
con tiendas o wishlists de compra física. Apuntarlos explícitamente evita que
el MVP engorde hasta no salir nunca — el coleccionista quiere su tebeoteca
ordenada, no un Facebook del cómic.

## Definition of Done del release "listo para usar"

El release 1.0 se corta cuando un coleccionista sin conocimientos técnicos,
partiendo de una Pi con Raspberry Pi OS limpio:

1. ejecuta un comando,
2. espera menos de 20 minutos,
3. ve su caos de descargas organizado en series con portadas,
4. marca una serie como deseada y la ve aparecer días después sin intervenir, y
5. jamás ha abierto una terminal, un JSON ni un log.

Las historias P0 suman ~10-14 semanas de trabajo a ritmo de proyecto personal;
el orden sugerido de ataque es **B** (vale oro y está medio hecha) →
**E1/A1** (confianza) → **C1/D1** (la UI que convierte backend en producto).
