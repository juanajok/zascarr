# Backlog de producto: SecuenciArr "listo para usar"

## Visión y persona

**Visión:** un coleccionista de tebeos instala SecuenciArr una vez, apunta a su
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
| A1 | Como coleccionista, quiero un único comando o script que lo instale todo, para no tener que seguir un manual de 20 pasos | `bootstrap.sh` pregunta 3 cosas (¿dónde están tus tebeos? ¿dónde descargas? ¿idioma?) y termina con una URL que funciona | P0 | M |
| A2 | Como coleccionista, quiero que el instalador me diga en español llano qué falló ("no encuentro el disco", no "exit code 1") | Mensajes de error del bootstrap mapeados a causas y soluciones comunes | P0 | S |
| A3 | Como coleccionista, quiero que si algo se tuerce, mi colección nunca se dañe | El instalador y el importador NUNCA borran archivos originales; solo copian/mueven a destinos verificados | P0 | S |
| A4 | Como coleccionista, quiero desinstalar sin dejar restos ni perder mi tebeoteca | `make uninstall` conserva biblioteca y BD con aviso claro | P1 | S |

### Épica B — "Importo mi caos actual"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| B1 | ~~Como coleccionista, quiero arrastrar mi carpeta de descargas y que el sistema la organice solo~~ | ~~El importador procesa `/downloads` y `_Unsorted/` según matcher/triage ya construidos, con informe final legible~~ | ✅ Backend hecho | M |
| B2 | Como coleccionista, quiero ver los tebeos que el sistema no supo clasificar y decidir yo con un clic | Bandeja de "pendientes de revisar" en la UI: miniatura, título detectado, botones "es esta serie / ninguna / ignorar" | P0 | L |
| B3 | ~~Como coleccionista, quiero que los duplicados se detecten y no se importen dos veces~~ | ~~Dedupe por SHA256 ya existe; la UI muestra "duplicado de X, descartado" en el informe~~ | ✅ Backend hecho | S |
| B4 | Como coleccionista, quiero que cada tebeo aparezca con portada, guionista, dibujante y sinopsis aunque el archivo no traiga metadatos | Enricher multi-fuente (GCD/AniList/Tebeosfera/Comic Vine) + corrección del bug de `metadata_source='manual'` del peer review (C3) | P0 | L |
| B5 | ~~Como coleccionista de tankōbon y álbumes BD, quiero que Vol./T/Tomo funcionen tan bien como el # americano~~ | ~~Tests de naming con fixtures reales de releases españolas (patrones `nº`, `v01c047` rescatados de zascarr)~~ | ✅ Hecho | M |

**Notas de implementación:**

- **B4 (parcial):** implementado `EnrichmentService` (`src/secuenciarr/services/enricher.py`) solo con Comic Vine, como job periódico en `main.py`. GCD, AniList y Tebeosfera quedan pendientes — el diseño es pluggable, añadirlas no requiere tocar el core del enricher.
- **B4 (Tebeosfera):** para el scraper de Tebeosfera, partir de [theotocopulitos/tebeosfera-scraper](https://github.com/theotocopulitos/tebeosfera-scraper) en vez de empezar de cero — cubre el sitio que más aporta para grapa/álbum español y ya resuelve el scraping HTML (sin API oficial).
- **B5 (hecho):** `naming.py` ahora resuelve los 8 casos reales de `tests/test_naming_core.py::TestRealWorldFilenames`, incluyendo "Batman_v2_012" (guion bajo como separador), "Batman (New 52) 012 (2013)" (paréntesis de reboot no confundidos con año), "Sandman.001.(1989)" (años 19xx, no solo 20xx), "MF #001 - Safari Callejero" y "Asterix T01 - Asterix el Galo" (subtítulo tras " - ", y "T01" de BD de tomo único tratado como número, a diferencia de "Vol."/"Tomo N" que siguen siendo volumen puro).
- **B1/B3 (backend hecho, falta UI):** `Importer.scan_and_import()` ahora devuelve un `ImportReport` (importados/duplicados/sin-clasificar/errores, en líneas legibles) y corre solo como job periódico en `main.py` (antes `import_interval_minutes` era un ajuste sin usar — el importador nunca se ejecutaba solo). Cada ciclo se persiste en la nueva tabla `import_runs` (migración `0002`), idea rescatada de zascarr (`scrape_runs`) para poder responder "¿qué pasó en el ciclo de las 03:00?" desde una futura UI. Sin endpoint API todavía — eso le toca a B2/Épica C cuando haya UI que lo consuma.

### Épica C — "Exploro y leo mi tebeoteca"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| C1 | Como coleccionista, quiero ver mi biblioteca en una web bonita desde el móvil o el sofá, ordenada por serie, autor o nacionalidad | Kavita cubre lectura; SecuenciArr aporta el *catálogo enriquecido*: UI propia (o integración OPDS) con filtros por tradición, editorial, personaje, saga | P0 | L |
| C2 | Como coleccionista, quiero saber de un vistazo qué números me faltan de cada serie | Vista "huecos" por serie: `missing` ya existe en API; corregir el bug de `sort_order` truncado detectado en el review | P0 | M |
| C3 | Como coleccionista, quiero marcar un tebeo como leído y puntuarlo | `reading_progress` ya está en el modelo; falta exponerlo + UI | P1 | M |
| C4 | Como coleccionista, quiero listas como "Court of Owls en orden" aunque crucen varias series | `story_arc_issues.reading_order` ya soporta crossovers; falta UI de arcos | P1 | M |

### Épica D — "El sistema busca lo que me falta"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| D1 | Como coleccionista, quiero marcar "quiero esta serie" y olvidarme: el sistema la encuentra y la añade | Wishlist → orchestrator → Transmission/aMule → import; visible como "Buscando... Descargando... En tu biblioteca" en la UI | P0 | L |
| D2 | Como coleccionista, quiero elegir "solo CBZ de calidad" o "acepto escaneos" sin entender qué es un quality profile | Selector de 3 opciones legibles ("solo lo mejor / equilibrado / lo que haya"); mapea a `quality_tier` interno | P1 | M |
| D3 | Como coleccionista, quiero que si sale una edición mejor de algo que ya tengo, el sistema me la ofrezca | Lógica de upgrade sobre `quality_tier`; la UI propone, no sustituye sin confirmar | P1 | M |
| D4 | Como coleccionista, quiero que el sistema me avise si está descargando sin VPN sin que se pare todo | Warning del healthcheck visible como aviso en UI + log del orchestrator (decisión ya acordada, ver fix C2) | P0 | S |

### Épica E — "Confío en el sistema"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| E1 | Como coleccionista, quiero una pantalla de estado con semáforos ("todo bien / atención: sin VPN / error: disco lleno") | Dashboard sobre `/api/health` con iconos y textos en español, no JSON | P0 | M |
| E2 | Como coleccionista, quiero que haya copias de seguridad automáticas sin configurar nada por mi parte | Cron de `pg_dump` a segundo disco (el backup actual al mismo disco del dato era hallazgo del review) | P0 | S |
| E3 | Como coleccionista, quiero un botón "restaurar copia" si algo sale mal | Script de restore documentado y probado (el test del backup no es hacerlo, es restaurarlo) | P1 | M |

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
