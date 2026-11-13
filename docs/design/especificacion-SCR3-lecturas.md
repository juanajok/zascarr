# SPEC: guías y órdenes de lectura (SCR3, #704) — v0.1

> **Estado:** especificación de la **entrega 1** (extractores + resolver + caché/robots; **sin modelo de BD ni UI**).
> La persistencia y la pantalla dependen de la decisión §8.1 del PO y quedan como propuesta de entrega 2 (§10).
> Solo documento: sin código, sin migraciones, sin commit.
>
> **Base contrastada:** `main` `9ef7d29d` (SCR1 y SCR2 fusionadas; sin cambios en ficheros rastreados), 2026-11-13. Manda el código real.
> **Fuentes:** estudio §2 dominio C, §5.6 y §6; **Anexo D** (el resolver es D, **no C.3**); fila SCR3 del BACKLOG;
> `informe-fase0-scraping-2026-11-13.md`; `especificacion-SCR1-robots-cache.md`; ADR 0018 (**sigue «Propuesto»**).
> **Verificación en vivo:** 2026-11-13, 22:56–23:05, UA `ZascArr/1.15.1 (+https://github.com/juanajok/zascarr; verificacion puntual SCR3)`,
> pausa ≥3 s, HTTP 200 sin challenge ni bloqueo. 10 peticiones contando 4 reintentos (el temporal del entorno se descarta entre comandos).
> **No ejecutado:** suite completa, Postgres real y tráfico con credenciales (no aplica: las dos fuentes son públicas).
> **Caducidad:** 2027-01-12, o antes si cambian las maquetas (fijar con el fixture de §7).

## 0. Alcance: dos entregas separadas

| | Entrega 1 — **esta historia** | Entrega 2 — **requiere PO** |
|---|---|---|
| Qué hace | Descubrir guías (sitemap) y leer una guía a demanda; normalizar cada referencia a datos fácticos; cruzar con el catálogo local en **solo lectura** | Guardar guías/ítems (modelo), refrescarlas y mostrarlas en pantalla |
| Qué NO hace | No crea tablas, ni rutas, ni plantillas, ni toca wishlist/descubrir | No decide aquí si se persigue la lista, se marca leído o se envía a Deseados |
| Valor | Contrato estable y probado para que la entrega 2 no reabra el parseo | Producto visible para el coleccionista |

**Sin modelo `ReadingOrder`/`ReadingOrderItem` en esta entrega** (§8.1 del estudio sigue abierta). La reconciliación
tampoco escribe: devuelve un informe en memoria. Si el PO decide «solo consulta», la entrega 2 puede no persistir nada;
si decide «listas seguidas», el modelo y la UI se especifican aparte.

## 1. Verificación en vivo (manda sobre el estudio)

| Sitio / recurso | Respuesta | Estructura real observada |
|---|---|---|
| `comicbookreadingorders.com/dc/events/crisis-on-infinite-earths-reading-order/` | 200, `text/html; charset=utf-8`, 89.101 B, **sin ETag/LM** (`cache-control: must-revalidate`) | `main > h1` (título de la guía), 2 `h2` de sección; **`ol.issues`** con 105 `li` directos: 102 `li.issue` (con o sin `gap`), 2 `li > h2` (sección) y 1 `li.aside.note-row` (prosa). Ítem: `label.check` (`input` + `span.box` + `span.sr` «Mark … as read»), `div.issue-main > span.issue-title` (+ `span.year`) y `a.read-link` («Read» → DC Universe Infinite). Año **después** del `#`: «Green Lantern Vol. 2 #173» + `1984`; marcadores `(limited series)`, `(one-shot)`, `Annual #2` |
| `comicbookreadingorders.com/sitemap.xml` | 200, `application/xml`, 78.104 B, **ETag** | `urlset` (no índice): 604 `<loc>`, 585 `<lastmod>`; guías tipo `/dc/events/<slug>-reading-order/`, `/marvel/events/…`, `/dc/characters/…` |
| `www.continuityguide.net/planetx` | 200, `text/html;charset=utf-8`, **975.383 B**, ETag `W/"caa98f…"`, 121 `<script>` | Sin `h1/h2/h3`. Entradas = **`div.image-card` en orden DOM**: dentro, `p.sqsrte-small` con `a` a Marvel Unlimited; la referencia fáctica es el `p` con `#` («Daredevil (1998) #1-8»); el `p` hermano entre comillas («“Guardian Devil”») es título de arco/historia y **se descarta**. 82 tarjetas, 109 `p` con `#` en subtítulos; 18 `p` con `#` **fuera** de tarjeta (prosa o referencias sueltas: se excluyen) |
| `www.continuityguide.net/sitemap.xml` | 200, `text/xml`, **1.714.846 B**, sin ETag/LM | `urlset` con **4.253 `<loc>` mezclando páginas y `images.squarespace-cdn.com`**; solo 63 con `<lastmod>`. Hay que filtrar por host; no es índice de sitemaps |

**Correcciones al material de referencia:** (1) el año puede ir **antes** del `#` (volumen: «Daredevil (1998) #1-8») o
**después** (año del número: «Green Lantern Vol. 2 #173 (1984)»); el anexo solo contempla el primero. (2) Continuity Guide
no tiene encabezados: el orden y las secciones no se leen de `h1/h2`. (3) La guía de RO no tiene validador: su caché es
TTL fijo, no 304. (4) `robots.txt` ya está verificado (RO permite todo salvo `/admin /api /search` y declara
`Content-Signal: use=reference`; CG prohíbe `/*?format=json`): no se ha vuelto a pedir.

## 2. Contrato de los extractores

**Paquete nuevo:** `src/zascarr/services/reading_orders/` (`__init__.py`, `comicbookreadingorders.py`, `continuity_guide.py`)
y `src/zascarr/services/reading_order_resolver.py`. **Sin** modelos, migración, rutas ni plantillas.

| Pieza | Contrato |
|---|---|
| Descubrimiento | `descubrir_guias() -> list[GuiaResumen]` lee **solo `sitemap.xml`** (nunca el inexistente `sitemap_index.xml`), una vez y con caché (TTL 24 h). RO: conservar `loc` con path `/(marvel|dc)/(events|characters)/`, `*-reading-order/` o `*-master-reading-order`; CG: conservar solo `netloc == www.continuityguide.net` y descartar imágenes/extensions. Topes: 10.000 `<loc>`, 2.000 guías |
| Lectura | `leer_guia(url: str) -> GuiaLeida \| None`; URL validada contra el origen del adaptador (host allowlist) **antes** de pedir; RO rechaza `/api/`, `/search/`, `/admin/`; CG rechaza cualquier query (`?format=json` incluida) |
| Salida cruda | `RawReadingEntry(orden: int, referencia: str, seccion: str \| None, item_url: str \| None)`. `orden` = 1..N en orden DOM; **solo hechos** (serie/número/año), nunca prosa |
| Selectores RO | `ol.issues > li.issue` en orden; `div.issue-main > span.issue-title` (sin `span.year`) → `referencia`; si hay `span.year`, se añade a la referencia entre paréntesis (para que el resolver lo separe como `anio_numero`); sección = `h2` del `li` de sección anterior más cercano; `a.read-link[href]` → `item_url`; ignorar `label.check` y `li.aside.note-row` |
| Selectores CG | `div.image-card` en orden; por tarjeta, cada `p` de `.image-subtitle` que contenga `#` → una entrada; el resto de `p` (títulos de arco entre comillas, prosa) se descarta; `a` del `p` → `item_url`; `seccion=None` (la página no declara secciones) |
| Red | Todo GET pasa por `utils/cache_http.pedir_con_cache` con `politica_de(fuente)`, `CacheHttp` inyectado y `gestor_robots_de_proceso()`. Dos políticas: **guía** 14 d / +60 d / negativa 24 h y **sitemap** 24 h / +14 d / negativa 6 h (matriz del estudio §5.3), negativas `{404,410}`. Nunca `bypass_cache`, ni HEAD, ni cabeceras de credenciales (contrato «solo respuestas públicas»; M-1 de SecOps SCR1) |
| Cortesía | Fuentes nuevas `reading_orders` (2,5 s) y `continuity_guide` (3,5 s) en `config.py`/`cortesia.py`; el `Crawl-delay` de robots solo sube el intervalo (SCR1). UA = `utils/robots.USER_AGENT` |
| Robustez | Tope `MAX_CUERPO_HTML = MAX_CUERPO_SITEMAP = 2 MiB` (alineado con la caché); por encima → `None`/`[]` + `log.warning` sin cuerpo. Parseo en `asyncio.to_thread` con `lxml.html.HTMLParser(recover=True, no_network=True)` y `etree.XMLParser(resolve_entities=False, no_network=True, recover=True)`. Cualquier cambio de maqueta/código inesperado → lista vacía + log estructurado (`reading_orders.parse_fallido`, con sitio y motivo, sin URLs con query ni prosa); `FuenteApagada`/`CortesiaEnEspera`/`ErrorDePeticion` se registran como «sin turno/negativa» y devuelven `[]` sin reintento ciego; **nunca** excepción al orquestador |

## 3. `reading_order_resolver.py` (puro)

Funciones sin red ni BD (el módulo no importa `httpx`/`sqlalchemy`; reutiliza `core.matcher.normalize_title`, que es puro).
`parsear_referencia(texto: str) -> ReadingOrderItem | None` y `expandir_rango(item) -> list[str] | None` (solo enteros, tope 100).

`ReadingOrderItem`: `titulo_serie: str`; **`anio_volumen: int | None`** (paréntesis **antes** del `#` o junto a `Vol.`; año de la
edición); **`anio_numero: int | None`** (paréntesis **después** del `#`; año del número); `volumen: int | None`; `numero_inicio: str | None`;
`numero_fin: str | None`; `tipo: Literal["issue","annual","special","tpb","volume"]`; `confianza: Literal["alta","media","baja"]`; `avisos: tuple[str, ...]`.
`confianza` = alta con serie + número + (año de volumen o `Vol.`); media con serie + número; baja si no hay número (tpb/volume) o hay
paréntesis no reconocidos. Un `tpb`/`volume` **no es una grapa**: nunca cuenta como «falta».

Gramática (guiones tipográficos normalizados; acentos según `normalize_title`): `[SERIE] [Vol. N | (AÑO)] # NUM [- NUM] [(AÑO)] [(MARCADOR)]`, donde
`NUM` admite `1`, `0.1`, `1/2`, `12.NOW`, `1A`, `½`; `MARCADOR` reconocido (`of N`, `limited series`, `one-shot`) se anota en `avisos` y no
altera el tipo. `Annual` en la serie → `annual`; `Special|Giant-Size|One-Shot` → `special`; `TPB|Trade Paperback|Omnibus|Hardcover|HC|Collected`
sin `#` → `tpb`; `Vol. N` sin `#` → `volume`; encabezado o prosa sin `#` → `None`.

**Casos obligatorios** (los 6 del Anexo D, con los nombres reales de la verificación en vivo, + variantes):

| Entrada | Salida (serie, vol, año vol/año núm, números, tipo) |
|---|---|
| `Uncanny X-Men (1963) #141-142` | Uncanny X-Men, —, 1963/—, 141–142, issue |
| `Batman Vol. 3 (2016) #1-6` | Batman, 3, 2016/—, 1–6, issue |
| `New Teen Titans Annual #2 (1983)` | New Teen Titans, —, —/1983, 2, annual |
| `Green Lantern Vol. 2 #173 (1984)` | Green Lantern, 2, —/1984, 173, issue |
| `Daredevil (1998) #1-8` | Daredevil, —, 1998/—, 1–8, issue |
| `Crisis on Infinite Earths #1 (limited series) (1985)` | Crisis on Infinite Earths, —, —/1985, 1, issue (aviso) |
| `Legends of the DC Universe: Crisis on Infinite Earths #1 (one-shot) (1999)` | …lo mismo…, 1, special (aviso) |
| `Batman Vol. 2 TPB` / `Batman: Year One Omnibus` | Batman…, 2/—, —/—, None, tpb |
| `Amazing Spider-Man #0.1` | Amazing Spider-Man, —, —/—, 0.1, issue |
| `Part II: The Dark Phoenix Saga` | `None` |

Límites declarados: no se interpretan tomos por ISBN, ni «Vol. 1-3» como rango de volúmenes, ni fechas exactas; una referencia con
dudas no se adivina (confianza baja + aviso).

## 4. Reconciliación con el catálogo (solo lectura)

`reconciliar(items, indice_local) -> InformeGuia` (puro) y una fina `leer_y_reconciliar(url)` en `services/reading_orders/`:
consulta `Series` (`title_norm`, `start_year`, `volume`) y `Issue`+`File` (`is_missing=false`; misma posesión que huecos #13), **sin escribir**.
Reglas: match por `normalize_title`/`Series.title_norm`; 1 candidata → match; varias → desempate por `volumen` contra `Series.volume` y por
`anio_volumen` contra `Series.start_year` (tolerancia ±1; **nunca** `anio_numero`, que es del número); si sigue ambiguo → `dudoso` y **no** cuenta como
falta. Rango → expandir (≤100) y comparar número a número; si el rango no es entero, comparar el literal. Estado por ítem:
`completo / parcial / falta / dudoso / no_aplica` (tpb/volume). Un ítem sin serie (p. ej. edición española con otro título) o ambiguo:
**se descarta del informe de faltas y se registra** (`lecturas.item_descartado`: sitio, orden, motivo); la guía solo se descarta entera si el
extractor devuelve 0 entradas. No se crean series ni issues, no se mueve nada, no se escribe en wishlist.

## 5. Integración que sí toca el árbol

`config.py` (`reading_orders_enabled=False`/`rate_limit=2.5`, `continuity_guide_enabled=False`/`3.5`), `cortesia.py` (nombres, `FUENTES_DECLARADAS`,
`politica_de` y ramas de habilitación), `runtime_settings.OVERRIDABLE_FIELDS["fuentes"]`, `web/ajustes.py` + `templates/ajustes.html`
(interruptores apagados), `api/health.py` (`fuentes`), `LEGAL.md` (filas de las dos fuentes: RO solo referencia + enlace, prohibido almacenar prosa
y uso en IA; CG respeta robots, sin `?format=json`, enlace a la guía; la atribución visible llega con la UI de la entrega 2; el hash versiona la aceptación), ADR 0018 a **Aceptado** con los TTL reales.
Pruebas de defaults/ajustes/health como en SCR2. **No** hay UI de guías ni modelo nuevo.

## 6. Criterios de aceptación (medibles)

| # | Criterio | Verificación |
|---|---|---|
| AC-01 | `parsear_referencia` cubre la tabla de §3 y devuelve `None` en prosa/encabezados | `tests/test_reading_order_resolver.py`, parametrizado ≥16 casos; el módulo no importa `httpx` ni `sqlalchemy` |
| AC-02 | El extractor RO sobre el fixture produce N ítems, `orden` 1..N contiguo, secciones correctas y **0 prosa** | fixture recortado; se afirma que ningún texto contiene una frase de prosa y que no existe campo para ella |
| AC-03 | El extractor CG sobre el fixture produce los ítems de tarjeta en orden DOM; excluye títulos entre comillas y `p` fuera de tarjeta | fixture recortado; se afirma el orden de dos tarjetas conocidas |
| AC-04 | Ninguna petición de CG lleva query (`?format=json` incluida) y ninguna usa `sitemap_index.xml` | `MockTransport` registra todas las URLs y se asserta |
| AC-05 | Descubrimiento filtra bien ambos sitemaps (con los fixtures: N guías esperadas; ningún `images.squarespace-cdn.com`) | fixtures de sitemap; contar guías esperadas |
| AC-06 | Caché/robots de SCR1: 2.ª lectura = hit (0 red); negativa 404 no se reintenta; robots que prohíbe o fuente apagada ⇒ `[]` + log `sin_turno`, sin excepción y 0 peticiones | `CacheHttpFalsa` de `tests/test_cache_http.py` + `MockTransport`; TTL 14 d/60 d/24 h assertados |
| AC-07 | Maqueta irreconocible o cuerpo >2 MiB ⇒ `[]`/`None` + log, sin excepción | fixtures rotos (`<html></html>`, cuerpo sintético grande) |
| AC-08 | Reconciliación: `#1-8` con locales 1–5 ⇒ `parcial` con faltan 6–8; título ausente/ambiguo ⇒ `dudoso` y fuera de faltas; tpb ⇒ `no_aplica` | `FakeSession`/catálogo en memoria; se asserta **cero escrituras** (`add`/`flush`/`commit` no llamados) |
| AC-09 | Parseo fuera del bucle de eventos y sin red en CI | `asyncio.to_thread` invocado (doble); `pytest` sin `TEST_DATABASE_URL` |
| AC-10 | Fuentes apagadas por defecto, en Ajustes y en `/api/health`; `LEGAL.md` con las dos filas | `tests/test_fuentes_apagadas_por_defecto.py` ampliado + ajustes/health |
| AC-11 | Fixtures = estructura sin prosa del autor, con URL y fecha de origen anotadas | `tests/fixtures/reading_orders/README.md`; revisión manual |

## 7. Plan de pruebas y fixtures

Fixture por adaptador, recortado del HTML real **sustituyendo la prosa por texto neutro** (p. ej. `PROSA_DE_PRUEBA`) y conservando
clases y anidamiento: `tests/fixtures/reading_orders/cbro_guia.html` (10–12 ítems + 2 secciones + 1 nota), `cbro_sitemap.xml` (10 `<loc>`),
`continuity_planetx.html` (6–8 tarjetas + 2 `p` de prosa neutra + esqueleto de nav), `continuity_sitemap.xml` (8 páginas + 3 imágenes CDN + 2 `lastmod`).
`MockTransport` para todas las respuestas; `CacheHttpFalsa` para hits/negativas; nada de red. Los fixtures actuales se revisan cuando cambie la maqueta
(la fecha de captura va en el README del fixture).

## 8. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-1 | Maqueta cambiada (RO es HTML clásico; CG es Squarespace de 975 KB sin `h1/h2`) | Selectores por clase/contenedor, no por texto; `[]`+log; fixture caduco detectable en la primera prueba |
| R-2 | Memoria/pico: página CG 975 KB y sitemap 1,7 MB; el cuerpo se bufferiza antes de la caché (RES-3/M-3 de SecOps SCR1) | Topes de 2 MiB, parseo en `to_thread`, caché comprimida; deuda compartida declarada, no se finge resuelta |
| R-3 | Matching bajo: títulos en español, ediciones distintas, años del número vs del volumen, rangos | Desempate solo con `volumen`/`anio_volumen`; ambiguo = `dudoso`, nunca falta; no crear series |
| R-4 | Fuga de prosa a BD/log/fixture (Content-Signal `use=reference`) | Dataclasses solo con hechos; fixtures neutros; log sin texto de la guía; enlace a la guía en la entrega 2 |
| R-5 | Continuity Guide no da orden **entre** capítulos (una página = un capítulo) | Límite declarado; entrega 2 decide si se encadenan capítulos |
| R-6 | `Crawl-delay` alto o robots con bloqueo temporal | Cola de cortesía de SCR1 (espera visible, sin reintento ciego); nunca `bypass_cache` |
| R-7 | Validadores desiguales: RO guía y CG sitemap no tienen ETag; CG guía y RO sitemap sí | TTL fijo donde no hay validador; el 304 se aprovecha donde existe (M-5 cosmético ya declarado) |
| R-8 | Entrega 1 no da producto visible | Explícito: es contrato + pruebas; el valor llega con la entrega 2. No se promete en UI |

## 9. Cortes para el builder y esfuerzo

| Corte | Entrega | Est. |
|---|---|---|
| 1 | `reading_order_resolver.py` puro + tabla de casos + pruebas (sin red, sin config) | 0,5–1 d |
| 2 | Fuentes nuevas (config/cortesía/health/Ajustes/LEGAL) + extractor RO (sitemap, guía, caché/robots) + fixtures | 1–1,5 d |
| 3 | Extractor CG (filtro de sitemap, tarjetas) + fixtures | 1–1,5 d |
| 4 | Reconciliación solo lectura + pruebas (sin modelo ni UI) | 0,5–1 d |

Total **3–5 días**; una historia = una PR, con un commit por corte. Si hay que recortar, el corte 4 es el último y se puede
dejar fuera sin romper los tres primeros. El modelo/UI (entrega 2) no se estima aquí.

## 10. Decisiones del PO

| # | Decisión | Recomendación |
|---|---|---|
| D-1 | **§8.1:** ¿modelo persistente (`ReadingOrder`/`ReadingOrderItem`) y UI, o solo consulta bajo demanda? | Cerrar tras la entrega 1; si es persistente, especificar refresco y reconciliación manual antes de construir |
| D-2 | Ítem no reconciliado: ¿descartar con log (no molesta) o mostrarlo como «no reconciliado»? | Descartar con log en entrega 1; mostrarlo exige UI y es entrega 2 |
| D-3 | ¿Solo títulos originales en inglés (ediciones españolas no casan) o se abren alias/identificadores? | Declarar el límite ahora; alias es otra historia |
| D-4 | ¿Se encadenan capítulos de Continuity Guide para un orden global? | No en entrega 1; decidir en entrega 2 |
| D-5 | Comic Book Herald (SCR5) sigue condicionado a `/feed/` y permiso | Fuera de SCR3 |

## 11. Trazabilidad

Objetivo «ver órdenes curadas cruzadas con mi colección» → §2 (extracción), §3 (normalización), §4 (cruce), AC-01…AC-08.
«Solo referencia, no prosa» y `use=reference` → §2/§5/AC-02/AC-11. «Sin `?format=json`» → §2/AC-04. «HTML irreconocible →
lista vacía y log» → §2/AC-07. «`ReadingOrder` solo si el PO lo aprueba» → §0/§10.


---

## Entrega 2 implementada (decisión del PO, 2026-11-13)

El PO decidió **reutilizar `story_arcs` / `story_arc_issues.reading_order`** en lugar de una
entidad `ReadingOrder` nueva: no hay migración. La entrega 2 añade:
- Integración de fuentes §5 (flags apagados por defecto, cortesía, Ajustes, `/api/health`,
  filas en `LEGAL.md`).
- `services/reconciliacion_lecturas.py`: guía → `StoryArc` (`metadata_={"origen","url"}`) +
  `StoryArcIssue.reading_order`, idempotente, con omitidos contados y logueados; solo escribe
  arcos y enlaces.
- Cierre de las condiciones de SecOps (M-1 lineal; m-1…m-5) y enlace de fuente en la ficha del arco.
- Disparador manual: `scripts/reconciliar-lecturas.py --fuente … --url …` (la UI de importación
  queda para una historia posterior).
