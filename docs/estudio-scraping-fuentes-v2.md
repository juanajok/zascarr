# Estudio y Especificación Técnica (v2): Solución de Scraping y Consumo Respetuoso de Fuentes Externas en ZascArr

- **Fecha:** 2026-11-13
- **Versión base comprobada:** ZascArr `v1.15.1`
- **Entorno objetivo:** Python 3.11+, FastAPI `async` *end-to-end*, SQLAlchemy `async` (`asyncpg`) + PostgreSQL 15, contenedor en Raspberry Pi 4/5 limitado a **512 MB de RAM**, `uvicorn --workers 1`, licencia `GPL-3.0-only`.
- **Pregunta del PO:** *«Necesito scrapear páginas (`dc.fandom.com`, `marvel.fandom.com`, `comicbookreadingorders.com`, `comicbookherald.com`, `continuityguide.net`, `lamansion-crg.net/forum/`). Me gustaría encontrar una solución de scraping open source, sensata, respetuosa y sencilla para embeber en mi proyecto.»*

## Respuesta corta

**No hay que embeber ningún framework externo de scraping.** ZascArr ya resolvió el 80 % del problema en su propio código (`utils/cortesia.py` + `utils/peticiones.py` + `lxml` + `services/forum_scraper.py`), con un control de cortesía más estricto y ligero que cualquier framework de propósito general.

La solución consiste en construir **piezas pequeñas y cohesivas sobre la infraestructura actual** (con **`protego`** como única dependencia nueva), separando las seis webs según los **tres dominios funcionales** reales a los que pertenecen:
1. **Adquisición P2P** (`lamansion-crg.net` → ya cubierto por `services/forum_scraper.py`, sujeto a validar *charset* y *flood control*).
2. **Enriquecimiento de metadatos** (`dc.fandom.com` y `marvel.fandom.com` → vía su API JSON oficial `/api.php`, nunca raspando su HTML público).
3. **Guías y órdenes de lectura** (`comicbookreadingorders.com`, `continuityguide.net` y, condicionalmente, `comicbookherald.com` → requieren caché HTTP condicional en PostgreSQL + un motor puro de normalización de referencias de cómics).

---

## 0. Directivas Operativas para el Agente / LLM Implementador (LEER ANTES DE TOCAR CÓDIGO)

1. **Inspección obligatoria de firmas reales antes de editar:**
   Antes de proponer migraciones o código, lee en el repositorio:
   - `CLAUDE.md`, `LEGAL.md` y los ADRs vigentes (especialmente `ADR-0011` y `ADR-0013`).
   - `src/zascarr/utils/cortesia.py` y `src/zascarr/utils/peticiones.py` (verifica la firma exacta de `pedir_con_cortesia`, cómo distingue *query params* de *body data*, cómo propaga bloqueos `Retry-After` y qué excepciones lanza).
   - `src/zascarr/services/forum_scraper.py`, `src/zascarr/services/tebeosfera.py`, `src/zascarr/services/enricher.py`, `src/zascarr/services/legal.py` y `src/zascarr/config.py`.
   - `pyproject.toml` (comprueba las dependencias exactas instaladas).
2. **Dependencias prohibidas y permitidas:**
   - **PROHIBIDO añadir:** `Scrapy`, `Crawlee`, `Scrapling`, `Playwright`, `Selenium`, `Crawl4AI`, `aiohttp`, `niquests`, `requests`, `BeautifulSoup4`, `selectolax`, `aiolimiter`, `tenacity`, `Redis` o bases `SQLite` auxiliares.
   - **ÚNICA dependencia nueva autorizada:** `protego` (BSD-3-Clause, Python puro) para evaluar `robots.txt` conforme a RFC 9309.
   - **Parseo HTML:** Usar `lxml.html` con **`.xpath()`** nativo (incluido en C dentro de `lxml`). **NO usar `.cssselect()`** salvo que compruebes que `cssselect` ya está declarado explícitamente en `pyproject.toml` (en `lxml` estándar no se instala por defecto y lanzaría `ImportError`).
3. **Invariantes arquitectónicas y legales del proyecto:**
   - **Fuentes apagadas por defecto (`ADR-0013`):** Toda fuente nueva añade `*_enabled: bool = False` y `*_rate_limit: float` en `config.py`. Se activa manualmente en Ajustes; las migraciones o actualizaciones jamás apagan fuentes que el usuario ya tuviera activas.
   - **Sincronía legal obligatoria:** Añadir una fuente exige actualizar `LEGAL.md` y reversionar `legal_version` en `services/legal.py` **el mismo día / en el mismo PR**, protegiendo su activación tras `require_legal_acknowledgment`.
   - **Prohibido el hotlinking:** Las portadas externas se descargan una sola vez a disco local (`covers/externa/`) y se sirven desde local.
   - **Fallo de parseo = «sin resultado»:** Un cambio de maquetación HTML o JSON inesperado devuelve `None` / lista vacía con log estructurado (respetando la regla de no volcar URLs sensibles/credenciales en errores), **nunca** una excepción no capturada que rompa el ciclo del orquestador.
   - **Tests deterministas offline:** Toda prueba automatizada usa `httpx.MockTransport` y *fixtures* locales en `tests/fixtures/`. Cero tráfico real en CI.

---

## 1. Inventario: lo que ZascArr ya tiene (y no se debe reinventar)

Comprobado contra la rama actual (`v1.15.1`) en `src/zascarr/`:

| Pieza | Fichero | Qué aporta hoy |
| :--- | :--- | :--- |
| **Limitador de cortesía compartido** | `utils/cortesia.py` | Una cola FIFO por fuente y otra por host efectivo para todo el proceso (`uvicorn --workers 1`), intervalos mínimos por fuente, bloqueos compartidos por `Retry-After`, presupuesto máximo de espera del llamador y *snapshot* observable en Estado/Ajustes. |
| **Envoltura HTTP segura** | `utils/peticiones.py` | `pedir_con_cortesia()`: aborta si la fuente se apagó antes de cada salto, resuelve redirecciones manualmente (≤ 3, **solo al mismo origen** como defensa SSRF), reintenta fallos transitorios (`408`/`429`/`5xx`/red) con *backoff*, aplica `Retry-After` al bloqueo compartido y emite códigos cortos de error sin filtrar URLs. |
| **Cliente genérico de foros IPB** | `services/forum_scraper.py` | Login con credenciales aportadas por el usuario, búsqueda puntual por títulos, extracción de enlaces `ed2k://` y `magnet:`, envío de cookies restringido al origen exacto del foro y validación de enlaces. Cubre conceptualmente *La Mansión CRG*. |
| **Adaptadores de metadatos** | `services/gcd.py`, `metron.py`, `open_library.py`, `anilist.py`, `comic_vine.py`, `tebeosfera.py` | Patrón consolidado «adaptador por fuente»: política declarativa + `pedir_con_cortesia` + parseo + modelos Pydantic + tests con transporte simulado. |
| **Fuentes apagadas por defecto** | `ADR-0013` + `config.py` | Patrón `*_enabled` / `*_rate_limit` gobernado desde Ajustes. |
| **Parser HTML rápido** | `lxml` (`pyproject.toml`) | Ya en uso en `services/tebeosfera.py` con `lxml.html`. |
| **Caché negativa funcional** | `services/enricher.py` | Ventana de 30 días por fuente para no insistir sobre elementos inexistentes. |
| **Marco legal versionado** | `LEGAL.md` + `services/legal.py` | Reglas de atribución, uso personal en caché local, prohibición de redistribución y aceptación versionada por hash (`legal_version`). |

---

## 2. Separación Funcional en 3 Dominios de Producto

Antes de codificar adaptadores, el diseño debe respetar que las seis webs sirven a tres casos de uso distintos:

1. **Dominio A — Adquisición P2P (`lamansion-crg.net/forum/`):**
   - **Propósito:** Encontrar enlaces `ed2k://` para series/números en la *wishlist* del usuario.
   - **Ubicación:** `services/forum_scraper.py` (existente).
2. **Dominio B — Enriquecimiento de fichas (`dc.fandom.com`, `marvel.fandom.com`):**
   - **Propósito:** Completar metadatos de series/números (sinopsis, fecha exacta de publicación, creadores, arcos o portadas) como complemento/*fallback* de Metron, Comic Vine y GCD.
   - **Ubicación:** `services/fandom.py` (mismo nivel y contrato que `services/tebeosfera.py` y `services/comic_vine.py`, integrado en `services/enricher.py`).
3. **Dominio C — Guías y Órdenes de Lectura (`comicbookreadingorders.com`, `continuityguide.net`, `comicbookherald.com`):**
   - **Propósito:** Mostrar secuencias curadas de lectura de eventos/etapas y cruzarlas con la colección local y la *wishlist*.
   - **Ubicación dividida en dos capas:**
     - **Extractores HTML:** Descargan y extraen la lista cruda de entradas de cada web.
     - **Normalizador y reconciliador (`services/reading_order_resolver.py`):** Módulo de funciones puras (sin red ni HTML) que convierte cadenas libres como `"Uncanny X-Men (1963) #141–142"` o `"Batman Annual #1"` en referencias estructuradas `(serie, año, rango_números, tipo)` y las cruza con el catálogo local. Aquí reside el 75 % de la complejidad real de las guías.

---

## 3. Auditoría de las Seis Fuentes (Verificado en Vivo el 2026-11-13 + Trampas Críticas)

| Fuente | Tecnología y respuesta real (2026-11-13) | Estrategia obligatoria y trampas de implementación |
| :--- | :--- | :--- |
| **`dc.fandom.com`**<br>**`marvel.fandom.com`** | **MediaWiki 1.43.10**.<br>`/robots.txt` → `403` (Cloudflare a clientes planos).<br>`/api.php?action=query&meta=siteinfo` → `200 OK` JSON sin clave. | **PROHIBIDO raspar el HTML público (`/wiki/...`).** Consumir solo `/api.php` (`format=json`, `formatversion=2`, `redirects=1`, `maxlag=5`).<br>⚠️ **Trampa 1 (Errores en HTTP 200):** MediaWiki devuelve **HTTP `200 OK`** cuando un artículo no existe (`error.code = "missingtitle"`) o hay sobrecarga (`error.code = "maxlag"`). Hay que inspeccionar siempre el JSON.<br>⚠️ **Trampa 2 (Redirecciones en wikis):** Sin `redirects=1`, `action=parse` devuelve el texto literal `#REDIRECT [[...]]` sin infobox.<br>⚠️ **Trampa 3 (Portadas vs defensa SSRF):** `Special:FilePath` responde `301` hacia otro dominio (`static.wikia.nocookie.net`), lo que bloqueará `pedir_con_cortesia` (solo mismo origen). Obtener la URL directa vía `action=query&prop=imageinfo&iiprop=url` y descargar contra `static.wikia.nocookie.net` con política propia.<br>⚖️ **Legal:** El **texto** es `CC-BY-SA 3.0` (exige enlazar al artículo **y** a la licencia). Las **portadas NO son CC-BY-SA** (*fair use* editorial): cachear en local sin atribuirlas como CC-BY-SA. |
| **`comicbookreadingorders.com`** | HTML clásico SSR tras Cloudflare.<br>`/robots.txt` → `200 OK`: `Allow: /`; `Disallow: /admin/ /api/ /search/`; `sitemap.xml`; `Content-Signals: search=yes, ai-train=no, use=reference` (reserva Art. 4 Directiva UE 2019/790). | Permitido extraer páginas de guías con `lxml.html` (`.xpath()`), TTL largo (14–30 días) y validación condicional `304`.<br>⚖️ **Cumplimiento estricto de `use=reference`:** Extraer **únicamente** la secuencia fáctica `(orden, serie, número, arco)` + enlace visible a la guía original. **Prohibido guardar o reproducir párrafos explicativos/reseñas del autor**, y prohibido usar estos datos en funciones de IA/LLM. |
| **`www.continuityguide.net`** | **Squarespace**.<br>`/robots.txt` → `200 OK` (plantilla Squarespace): **`Disallow: /*?format=json`** explícito, además de `/search` y `/api`. Expone `sitemap.xml`. | **PROHIBIDO usar `?format=json`** (viola explícitamente su `robots.txt`). Parsear el HTML SSR estándar con `.xpath()`, intervalo alto (`3–5 s`) y caché larga en PostgreSQL. |
| **`www.comicbookherald.com`** | **WordPress** tras WAF (Sucuri/equivalente).<br>`/robots.txt` y `/wp-json/` → `403` ambos a clientes planos. | **Bloqueado en Fase 4 (condicional):** El WAF bloquea clientes no navegador incluso en `/robots.txt` y REST. No escribir parser hasta verificar en Fase 0 si `/feed/` o los artículos HTML responden `200` con `httpx` + UA real de ZascArr, y hasta que el PO decida sobre pedir permiso expreso al autor. |
| **`lamansion-crg.net/forum/`** | **Invision Power Board (IPB)** clásico, `http://` sin TLS.<br>`/forum/robots.txt` → `404`. Requiere login de usuario. | Usar `services/forum_scraper.py` solo bajo demanda puntual (jamás indexar subforos).<br>⚠️ **Tres puntos críticos a validar/ajustar:**<br>1. **Codificación `ISO-8859-1` / `Windows-1252`:** Si el foro no es UTF-8, un POST de búsqueda con tildes o `ñ` (`"Capitán América"`, `"Año Uno"`) en UTF-8 devolverá **0 resultados silenciosos**.<br>2. **Search Flood Control (15–30 s):** IPB bloquea búsquedas seguidas devolviendo **HTTP `200 OK`** con HTML de aviso (*flood control*). Si no se detecta ese HTML, se confundirá con «sin resultados» y se meterá 30 días en caché negativa.<br>3. **HTTP plano:** Asegurar que el validador acepte `http://` y advertir en Ajustes/`LEGAL.md` que las credenciales viajan sin TLS. |

---

## 4. Comparativa de Soluciones Open Source (Justificación para ADR)

Evaluación bajo las restricciones de `CLAUDE.md` (`GPL-3.0-only`, contenedor de `512 MB` en Raspberry Pi ARM64, `asyncio` nativo en FastAPI, cortesía estricta y mínimas dependencias):

| Alternativa | Veredicto | Motivo técnico |
| :--- | :--- | :--- |
| **Micro-stack propio existente (`httpx` + `pedir_con_cortesia` + `cortesia.py` + `lxml` + PostgreSQL) + `protego`** | ✅ **Elegida** | Ya está en producción en 11 servicios del repo, probado, observable en UI y con memoria extra cercana a cero. Solo le falta caché HTTP condicional en PostgreSQL y evaluación RFC 9309 de `robots.txt`. |
| **Scrapy** (BSD-3) | ❌ Descartado | Basado en el reactor de Twisted; integrarlo dentro del bucle `asyncio` de FastAPI/Uvicorn complica señales y ciclo de vida. Sobredimensionado para consultas puntuales a `/api.php` o páginas sueltas. |
| **Crawlee for Python** (Apache-2.0) | ❌ Descartado | Impone su propio sistema de almacenamiento en disco (`./storage/...`) duplicando PostgreSQL, y su ecosistema arrastra Playwright/Chromium (~500 MB), inviable en un contenedor de 512 MB. |
| **Scrapling** (BSD-3) | ❌ Descartado | Su extra `scrapling[fetchers]` empaqueta `curl_cffi` junto con `playwright`, `patchright` y `browserforge`; su modo adaptativo escribe en SQLite local (estado duplicado en Docker); y su propuesta principal (evasión *stealth*, Turnstile, MCP) va en dirección opuesta a la política de ZascArr. Su paquete base solo aportaría un *wrapper* sobre `lxml` que ya tenemos. |
| **Playwright / Selenium / Crawl4AI** | ❌ Descartado | Ninguna de las seis fuentes requiere ejecutar JavaScript. Levantar un navegador consume 300–800 MB de RAM y descarga publicidad/trackers innecesarios. |
| **`aiohttp` / `niquests` / `aiolimiter` / `tenacity`** | ❌ No añadir | Duplican pieza por pieza lo que ya hacen `httpx`, `cortesia.py` y `peticiones.py`. Mantener dos clientes HTTP y dos sistemas de colas rompería la garantía de cortesía global por proceso. |

---

## 5. Arquitectura y Especificación Técnica Detallada

### 5.1 Mapa de ficheros a crear o tocar

```text
src/zascarr/
├── config.py                         # (tocar) flags *_enabled=False y *_rate_limit nuevas (ADR-0013)
├── utils/
│   ├── cortesia.py                   # (tocar) registrar nuevas fuentes y host static.wikia.nocookie.net
│   ├── peticiones.py                 # (NO tocar salvo bug demostrado en Fase 0)
│   ├── robots.py                     # NUEVO: cliente/evaluador RFC 9309 con protego + Crawl-delay
│   └── cache_http.py                 # NUEVO: caché HTTP condicional en Postgres (zlib, 304, singleflight)
├── services/
│   ├── legal.py                      # (tocar) bump de legal_version sincronizado con LEGAL.md
│   ├── enricher.py                   # (tocar) conectar fandom_dc y fandom_marvel según prioridad
│   ├── forum_scraper.py              # (revisar/ajustar) charset latin1/cp1252 y detector de flood IPB
│   ├── fandom.py                     # NUEVO: cliente MediaWiki api.php (DC + Marvel Database + portadas)
│   ├── reading_order_resolver.py     # NUEVO: parser/normalizador puro de referencias de cómics
│   └── reading_orders/               # NUEVO (paquete de extractores de guías)
│       ├── comicbookreadingorders.py # Extractor XPath + sitemap (use=reference)
│       ├── continuity_guide.py       # Extractor XPath Squarespace (sin ?format=json)
│       └── comicbookherald.py        # (Fase 4 condicional, bloqueado hasta validación WAF + autor)
└── models/ + migrations/             # NUEVO: tabla http_cache (+ modelos ReadingOrder si aplica Fase 3)
```

---

### 5.2 `src/zascarr/utils/robots.py` (RFC 9309 estricto + `Crawl-delay`)

Descarga `/robots.txt` una vez por origen (`scheme://host`) pasando por `cortesia.py` y persiste el texto/estado en memoria + `http_cache`.

**Reglas obligatorias de interpretación de códigos HTTP en `/robots.txt` (RFC 9309 §2.3.1):**
1. **HTTP `200 OK`:** Parsear con `Protego.parse(texto)`. Evaluar `rp.can_fetch(url, user_agent)` y `rp.crawl_delay(user_agent)`. Cachear `24 h` (hasta `7 días` en blogs estáticos).
2. **HTTP `4xx` distinto de `429` (incluye el `403` de Fandom y el `404` de CRG):** Según RFC 9309 §2.3.1.3 (*unavailable*), equivale a ausencia de restricciones explícitas de `robots.txt` → permitir la petición aplicando siempre la `PoliticaFuente` conservadora de ZascArr. Cachear este resultado `12–24 h` para no reintentar `/robots.txt` en cada llamada.
3. **HTTP `429`, HTTP `5xx` o fallo de red/timeout:** Según RFC 9309 §2.3.1.4 (*unreachable*), **PROHIBIDO asumir permiso**. Debe tratarse como **`Disallow: /` temporal** durante una ventana corta (p. ej. `15–30 min` en memoria, respetando `Retry-After` si viene presente) y abortar la petición actual sin contaminar la caché negativa funcional.

**Inyección limpia de `Crawl-delay` sin modificar `peticiones.py`:**
```python
from dataclasses import replace
from zascarr.utils.cortesia import PoliticaFuente

def aplicar_crawl_delay(politica: PoliticaFuente, crawl_delay: float | None) -> PoliticaFuente:
    """Si robots.txt declara un Crawl-delay superior al intervalo configurado, manda el mayor."""
    # Nota para el implementador: usar el nombre exacto del atributo de intervalo en PoliticaFuente
    if crawl_delay is not None and crawl_delay > politica.intervalo_min_s:
        return replace(politica, intervalo_min_s=float(crawl_delay))
    return politica
```

---

### 5.3 Caché HTTP en PostgreSQL (`http_cache` + `src/zascarr/utils/cache_http.py`)

Sin caché condicional, reabrir una guía o refrescar vistas descargaría cientos de KB repetidos. El diseño protege los **512 MB de RAM** de la Raspberry Pi y garantiza que `304 Not Modified` funcione realmente.

#### DDL de la tabla `http_cache` (Migración Alembic)
```sql
CREATE TABLE IF NOT EXISTS http_cache (
    id               BIGSERIAL PRIMARY KEY,
    url_hash         TEXT NOT NULL UNIQUE,   -- sha256(metodo_upper + " " + url_canonica_sin_credenciales)
    url_canonical    TEXT NOT NULL,          -- URL normalizada sin secretos (para inspección y purgas)
    domain           TEXT NOT NULL,
    status_code      SMALLINT NOT NULL,      -- Solo códigos finales cacheables (200, 404)
    content_type     TEXT,                   -- Conserva MIME y charset (ej. 'text/html; charset=utf-8')
    etag             TEXT,
    last_modified    TEXT,
    body_zlib        BYTEA,                  -- Cuerpo comprimido con zlib nivel 6 (NULL si is_negative=TRUE)
    is_negative      BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at       TIMESTAMPTZ NOT NULL,
    fresh_until      TIMESTAMPTZ NOT NULL,   -- Mientras now() < fresh_until: HIT local (0 red, 0 turno)
    retain_until     TIMESTAMPTZ NOT NULL    -- > fresh_until: retiene ETag y body para revalidar con 304
);

CREATE INDEX IF NOT EXISTS ix_http_cache_domain ON http_cache (domain);
CREATE INDEX IF NOT EXISTS ix_http_cache_retain_until ON http_cache (retain_until);
```

#### Cinco invariantes de implementación en `cache_http.py`
1. **Doble horizonte temporal (`fresh_until` vs `retain_until`):**
   - Si `now() < fresh_until` y `not bypass_cache`: **Cache Hit directo** (no entra en `cortesia.py` ni abre socket).
   - Si `fresh_until <= now() < retain_until`: **Entrada caducada pero retenida**. Si dispone de `etag` o `last_modified`, pasa por `robots.py` + `cortesia.py` enviando `If-None-Match` / `If-Modified-Since`. Si el servidor responde `304 Not Modified`, actualiza `fetched_at`, `fresh_until` y `retain_until` en PostgreSQL y devuelve `zlib.decompress(body_zlib)` sin re-descargar el documento.
   - **Purga periódica:** Borrar **únicamente** donde `retain_until < now()` (si borras cuando vence `fresh_until`, destruyes el `etag` y el `body_zlib` e inutilizas el `304`).
2. **Compresión y techo de memoria (protección 512 MB):**
   - Comprimir siempre con `zlib.compress(raw_bytes, level=6)` (reduce HTML y JSON un 80–90 %).
   - Fijar `MAX_CACHEABLE_BODY_BYTES = 2 * 1024 * 1024` (2 MB descomprimido). Respuestas mayores se entregan al llamador sin persistirse en `http_cache`.
3. **Coalescencia en vuelo (*Singleflight*):**
   - Mantener un registro acotado de `asyncio.Lock` por `url_hash` en memoria. Si 5 tareas piden a la vez la misma URL fría antes de que exista en BD, la primera descarga y persiste mientras las otras 4 esperan el lock y leen el resultado recién cacheado (*double-checked locking*), evitando gastar 5 turnos en `cortesia.py`.
4. **Clasificador opcional de respuestas (`clasificar_respuesta`):**
   - Algunas APIs (como MediaWiki `api.php` o foros IPB con *flood control*) devuelven errores lógicos o transitorios con **HTTP `200 OK`**. `pedir_con_cache()` debe aceptar un *callback* opcional `clasificar_respuesta(response) -> Literal["ok", "negativo", "no_cachear"]` para:
     - Guardar como `is_negative = True` errores definitivos en HTTP 200 (ej. `missingtitle` en Fandom).
     - **No cachear jamás** errores transitorios en HTTP 200 (ej. `maxlag` en Fandom o *flood control* en IPB), ni tampoco `429`/`5xx`.
5. **Separación respecto a la caché negativa de 30 días de `enricher.py`:**
   - En `http_cache`, las respuestas negativas (`404` / `missingtitle`) llevan un TTL corto (`6–24 h`) pensado para frenar ráfagas repetidas.
   - Exponer `bypass_cache: bool = False` para que las acciones manuales del usuario en la UI («Reintentar enriquecimiento / Actualizar guía») fuercen validación contra origen sin quedar atrapadas en un negativo previo.

#### Matriz de TTLs iniciales en `http_cache`
| Fuente / recurso | `fresh_until` (positivo) | `retain_until` (ventana `304`) | `fresh_until` (negativo) |
| :--- | :--- | :--- | :--- |
| `reading_orders` (página de guía) | 14 días | +60 días | 24 h |
| `continuity_guide` (página de guía) | 14 días | +60 días | 24 h |
| `sitemap.xml` / índices de guías | 24 h | +14 días | 6 h |
| `fandom_dc` / `fandom_marvel` (`api.php`) | 24 h | +14 días | 12 h |
| `comicbookherald` (si supera Fase 0/4) | 7 días | +30 días | 24 h |

---

### 5.4 Registro de Políticas en `utils/cortesia.py` y `config.py`

Añadir siguiendo el estilo exacto del repositorio y `ADR-0013`:
- `fandom_dc` ("DC Database") → `fandom_dc_enabled: bool = False`, `fandom_dc_rate_limit: float = 1.5`
- `fandom_marvel` ("Marvel Database") → `fandom_marvel_enabled: bool = False`, `fandom_marvel_rate_limit: float = 1.5`
- Host CDN de portadas Fandom (`static.wikia.nocookie.net`) → registrado con intervalo mínimo `1.0 s` y concurrencia `1`, gobernado por que al menos una fuente Fandom esté habilitada.
- `reading_orders` ("Comic Book Reading Orders") → `reading_orders_enabled: bool = False`, `reading_orders_rate_limit: float = 2.5`
- `continuity_guide` ("Continuity Guide") → `continuity_guide_enabled: bool = False`, `continuity_guide_rate_limit: float = 3.5`
- `comicbookherald` ("Comic Book Herald") → reservar solo si entra en Fase 4 (`3.5 s`).
- `forum_scraper` (existente) → elevar el mínimo por defecto para lectura de temas a `3.0–4.0 s` y separar/elevar el intervalo entre **búsquedas** (`act=Search`) según el *flood control* real medido en Fase 0 (`20–30 s`).

---

### 5.5 Contrato Técnico de `src/zascarr/services/fandom.py`

Un único módulo parametrizado por dominio (`dc.fandom.com` / `marvel.fandom.com`):

```python
"""Cliente para DC Database y Marvel Database vía MediaWiki Action API (api.php).

Invariantes:
- Nunca pedir /wiki/... (HTML público pesado con anuncios/JS); usar siempre /api.php.
- Pasar siempre format=json, formatversion=2, redirects=1 y maxlag=5.
- Inspeccionar payload['error'] aunque status_code sea 200 ('missingtitle', 'maxlag').
- Resolver portadas vía action=query&prop=imageinfo&iiprop=url y descargar desde
  static.wikia.nocookie.net (evita el 301 cross-origin de Special:FilePath bloqueado por SSRF).
"""
from urllib.parse import unquote, urlparse

FANDOM_HOSTS = frozenset({"dc.fandom.com", "marvel.fandom.com"})
FANDOM_CDN_HOSTS = frozenset({"static.wikia.nocookie.net"})

class FandomMaxLagError(Exception):
    def __init__(self, retry_after_s: float):
        self.retry_after_s = retry_after_s

def parsear_url_articulo_fandom(url_articulo: str) -> tuple[str, str]:
    parsed = urlparse(url_articulo)
    if parsed.scheme != "https" or parsed.netloc not in FANDOM_HOSTS:
        raise ValueError("Host Fandom no permitido")
    if "/wiki/" not in parsed.path:
        raise ValueError("Ruta de artículo Fandom inválida")
    slug = parsed.path.split("/wiki/", 1)[1]
    if not slug:
        raise ValueError("Slug de artículo vacío")
    return f"https://{parsed.netloc}/api.php", unquote(slug)

def clasificar_respuesta_mediawiki(resp) -> str:
    """Clasificador para cache_http: distingue éxito, inexistente y sobrecarga en HTTP 200."""
    if resp.status_code == 404:
        return "negativo"
    if resp.status_code != 200:
        return "no_cachear"
    try:
        data = resp.json()
    except ValueError:
        return "no_cachear"
    err = data.get("error")
    if not err:
        return "ok" if "parse" in data or "query" in data else "no_cachear"
    if err.get("code") in ("missingtitle", "invalidtitle", "pagecannotexist"):
        return "negativo"
    return "no_cachear"  # Incluye 'maxlag' y errores internos transitorios
```

**Flujo de extracción de ficha y portada:**
1. Llamar a `GET https://<host>/api.php` con *query params* (`action=parse`, `page=<titulo>`, `redirects=1`, `prop=text|categories|properties|displaytitle`, `format=json`, `formatversion=2`, `maxlag=5`).
   - Si `error.code == "maxlag"`: leer cabecera `Retry-After` (o `error.lag`, mínimo `5.0 s`), notificar bloqueo temporal al limitador compartido en `cortesia.py` y lanzar/propagar error transitorio sin cachear.
   - Si `error.code in ("missingtitle", "invalidtitle")`: devolver `None`.
2. Parsear `data["parse"]["text"]` con `lxml.html.fromstring(...)` usando expresiones `.xpath()` sobre `.//aside[contains(@class, "portable-infobox")]` para extraer fecha de portada/publicación, guionistas, dibujantes, sinopsis y nombre/URL de imagen principal.
3. **Descarga segura de portada a disco local (`covers/externa/`):**
   - Si el nodo `<img>` de la infobox contiene en `data-src` o `src` una URL `https://static.wikia.nocookie.net/...` (ignorando placeholders `data:image/...`), limpiar sufijos de miniatura (`/scale-to-width-down/\d+`) conservando la ruta base de revisión válida.
   - Si solo se dispone del nombre del archivo (`File:...`), consultar `api.php` con `action=query`, `titles=File:<nombre>`, `prop=imageinfo`, `iiprop=url`, `format=json`, `formatversion=2`, `maxlag=5`.
   - Validar que el host de la URL obtenida esté en `FANDOM_CDN_HOSTS` y descargar los bytes una sola vez hacia `covers/externa/` usando la política de cortesía asignada al CDN.

---

### 5.6 Contrato para Guías de Lectura (`reading_order_resolver.py` + Extractores)

1. **Extractores (`comicbookreadingorders.py`, `continuity_guide.py`):**
   - Descubrimiento perezoso: descargar `sitemap.xml` o índice principal solo cuando el usuario busca/explora guías, y descargar únicamente la guía concreta que el usuario seleccione.
   - Parsear con `lxml.html` + `.xpath()`.
   - Emitir objetos simples `RawReadingEntry(position: int, raw_reference: str, section_title: str | None, item_url: str | None)`. **Descartar cualquier bloque de prosa, sinopsis o comentario editorial** para cumplir `Content-Signal: use=reference`.
2. **Normalizador puro (`services/reading_order_resolver.py`):**
   - Entrada: `raw_reference: str` (ej. `"Batman (2016) #1-6"`, `"Uncanny X-Men Vol. 1 #141–142"`, `"Secret Wars (1984) #1 (of 12)"`, `"Swamp Thing Annual #2"`).
   - Salida: `NormalizedIssueRef(series_name: str, volume_or_year: int | None, issue_start: str, issue_end: str | None, kind: Literal["issue", "annual", "special", "tpb"]) | None`.
   - Cero llamadas a red o base de datos; cubierto al 100 % por tests unitarios parametrizados.

---

### 5.7 Ajustes requeridos en `services/forum_scraper.py` para *La Mansión CRG*

En Fase 0/4 verificar y garantizar estos tres comportamientos:
1. **Soporte de codificación legacy (`encoding` autodetectado o configurable):**
   - Al hacer login y al enviar el formulario de búsqueda, codificar los parámetros del formulario en el charset real del foro (p. ej. `iso-8859-1` / `windows-1252` si el HTML del foro declara `charset=iso-8859-1`), y decodificar los bytes de la respuesta antes o durante `lxml.html.fromstring(..., parser=HTMLParser(encoding=...))`.
2. **Detección explícita de *Search Flood Control* en respuestas HTTP `200`:**
   - Inspeccionar si el HTML devuelto contiene el cuadro de error de IPB (control de *flood* / espera obligatoria entre búsquedas). Si aparece, lanzar excepción transitoria de cortesía (aplicando una pausa compartida de `20–30 s` sobre la fuente) en lugar de devolver lista vacía `[]` (lo que provocaría un falso negativo de 30 días).
3. **Advertencia de transporte `http://`:**
   - Permitir `http://` cuando el usuario configura explícitamente `forum_url`, asegurando que las cookies nunca salgan hacia otro host/esquema, y mostrar advertencia visible en Ajustes de que las credenciales viajan sin cifrado TLS.

---

## 6. Cortesía, Licencias, UI y Gobernanza Legal

| Obligación | Implementación concreta en ZascArr |
| :--- | :--- |
| **Comportamiento de cliente personal, no de crawler** | Solo se consulta bajo acción explícita del usuario o ciclo acotado sobre su *wishlist*/colección, siempre con `http_cache` por delante. Prohibidos los barridos completos de wikis o blogs. |
| **Atribución CC-BY-SA 3.0 en Fandom (texto vs portadas)** | En las vistas donde se muestre texto/metadatos provenientes de Fandom, renderizar **ambos enlaces**: enlace al artículo original (`site_url`) **y** enlace a la licencia `CC-BY-SA 3.0` (`https://creativecommons.org/licenses/by-sa/3.0/`). **Nunca** etiquetar la imagen de portada como CC-BY-SA (en Fandom solo el texto es CC-BY-SA; las portadas son *fair use* editorial). |
| **Cumplimiento `Content-Signals` y Directiva UE 2019/790 (`reading_orders`)** | Guardar únicamente referencias estructuradas `(orden, título, número)` y enlazar de forma prominente a la guía original (`use=reference`). Prohibido almacenar/mostrar prosa del autor y prohibido inyectar estos datos en pipelines de IA (`ai-train=no`). |
| **Prohibición de redistribución y hotlinking** | La caché vive exclusivamente en el PostgreSQL y disco local (`covers/externa/`) de la instancia del usuario. ZascArr no distribuye bases pre-pobladas ni exporta catálogos de terceros. |
| **Actualización atómica de `LEGAL.md` + `legal_version`** | Añadir una entrada en `LEGAL.md` por cada fuente incorporada (Fandom, Reading Orders, Continuity Guide y advertencia HTTP para foros) y actualizar `legal_version` en `services/legal.py` en el mismo PR. |

---

## 7. Plan de Ejecución por Fases y Criterios de Aceptación

### Fase 0 — Spike de Verificación en Vivo y Cierre de Producto (0,5 días — BLOQUEANTE)
Antes de generar migraciones Alembic:
1. Comprobar en el código real las firmas exactas de `pedir_con_cortesia`, `PoliticaFuente`, `CortesiaProceso`, `forum_scraper.py` y `pyproject.toml`.
2. Hacer **1 petición puntual en vivo** usando `httpx` con el `User-Agent` real de ZascArr a:
   - Una página interior de guía en `https://comicbookreadingorders.com/` (confirmar `200 OK` sin *JS Challenge* de Cloudflare).
   - Una página interior en `https://www.continuityguide.net/` (confirmar `200 OK` y estructura XPath).
   - `/feed/` y 1 artículo en `https://www.comicbookherald.com/` (confirmar si el WAF bloquea toda la web con `403`).
   - *(Con credenciales del usuario)* 2 búsquedas seguidas con tildes/`ñ` en `http://lamansion-crg.net/forum/` para medir su `charset` y los segundos exactos de su *Search Flood Control*.
3. Confirmar con el PO:
   - Prioridad de `fandom_dc` / `fandom_marvel` en `services/enricher.py` frente a Metron, Comic Vine y GCD.
   - Alcance y esquema de tablas `ReadingOrder` / `ReadingOrderItem`.
4. Escribir el ADR correspondiente (extensión de `ADR-0011`/`ADR-0013` o ADR nuevo).

### Fase 1 — Infraestructura Común: `http_cache` + `robots.py` + Políticas (1,5–2 días)
- **Entregables:** `protego` en `pyproject.toml`; migración Alembic `http_cache`; `utils/robots.py`; `utils/cache_http.py`; nuevas entradas apagadas por defecto en `cortesia.py` y `config.py`.
- **Criterios de aceptación (tests con `MockTransport`):**
  - Un *cache hit* vigente (`now() < fresh_until`) devuelve respuesta sin consumir turno en `cortesia.py` ni tocar red.
  - Una entrada *stale* (`fresh_until <= now() < retain_until`) envía `If-None-Match` y, ante `304`, renueva `fresh_until` conservando el cuerpo comprimido.
  - 5 corrutinas pidiendo a la vez la misma URL fría ejecutan **1 sola petición HTTP** (*singleflight*).
  - `/robots.txt` con `403`/`404` permite continuar bajo política local, mientras que `429`/`503`/error de red bloquea temporalmente el host conforme a RFC 9309.

### Fase 2 — Adaptador Fandom DC/Marvel (`services/fandom.py`) (1–1,5 días)
- **Entregables:** `services/fandom.py`, soporte de descarga de portadas desde `static.wikia.nocookie.net` a `covers/externa/`, integración en `enricher.py`, doble enlace `CC-BY-SA 3.0` en UI, actualización de `LEGAL.md` y bump de `legal_version`.
- **Criterios de aceptación:**
  - Resuelve redirecciones (`redirects=1`), convierte `missingtitle` (en HTTP 200) en `None` cacheado como negativo corto, y ante `maxlag` (en HTTP 200) respeta `Retry-After` sin cachear basura.
  - Las portadas se guardan en local sin disparar errores SSRF por redirección *cross-origin*.

### Fase 3 — Guías de Lectura: Resolver + Reading Orders + Continuity Guide (2–3 días)
- **Entregables:** Modelos/migración `ReadingOrder`, `services/reading_order_resolver.py`, adaptadores XPath `comicbookreadingorders.py` y `continuity_guide.py`, vistas UI con atribución de referencia, actualización de `LEGAL.md` y `legal_version` (si va en PR independiente).
- **Criterios de aceptación:**
  - Ninguna petición a `continuityguide.net` incluye `?format=json`.
  - Ningún texto editorial/reseña de `comicbookreadingorders.com` se almacena en base de datos.
  - Batería de tests unitarios sobre `reading_order_resolver.py` y *fixtures* HTML reales; si el HTML cambia a algo irreconocible, el adaptador devuelve lista vacía sin lanzar excepción al orquestador.

### Fase 4 — Ajustes Foro CRG y Comic Book Herald (Condicional)
- Aplicar en `services/forum_scraper.py` soporte de `charset` no UTF-8, detector de *Search Flood Control* en HTTP 200 y aviso de `http://` sin TLS.
- Abordar `comicbookherald.py` **únicamente** si en Fase 0 su RSS/HTML resultó accesible legítimamente sin técnicas de evasión de WAF y el PO validó el permiso/alcance.

---

## 8. Decisiones Abiertas para el PO

1. **Modelo de producto para Órdenes de Lectura:** ¿Las guías importadas se guardan como listas seguidas por el usuario que marcan automáticamente «tengo / me falta -> enviar a wishlist», o solo como consulta en vivo en Descubrir? (Determina las tablas de Fase 3).
2. **Prioridad de Fandom en `enricher.py`:** ¿Actúa únicamente para rellenar huecos vacíos tras Metron / Comic Vine / GCD, o el usuario puede elegirla como fuente primaria de serie?
3. **Comic Book Herald:** Dado su bloqueo por WAF (`403` en `robots.txt` y `wp-json`), ¿se descarta de entrada para el MVP o se contacta al autor?

---

## Anexo: Registro de Verificación en Vivo (2026-11-13)

| Comprobación realizada | Resultado obtenido | Implicación directa en el diseño |
| :--- | :--- | :--- |
| `dc.fandom.com/api.php?action=query&meta=siteinfo` | `200 OK`, JSON (`MediaWiki 1.43.10`), abierta sin API key | Consumir exclusivamente `/api.php` con `redirects=1` y `maxlag=5`. |
| `dc.fandom.com/robots.txt` y `marvel.fandom.com/robots.txt` | `403 Forbidden` (*«Just a moment…»* Cloudflare a clientes planos) | No tocar el frontend web público; tratar `403` en `robots.txt` según RFC 9309 §2.3.1.3. |
| `comicbookreadingorders.com/robots.txt` | `200 OK`: `Allow: /`; `Disallow: /admin/ /api/ /search/`; `Content-Signals: search=yes, ai-train=no, use=reference`; `sitemap.xml` | Permitido extraer guías solo como referencia estructurada con enlace; prohibido reproducir prosa o usar en IA. *(Pendiente Fase 0: probar 1 guía interior).* |
| `www.continuityguide.net/robots.txt` | `200 OK`: plantilla Squarespace; `Disallow: /search, /api, /*?format=json`; `sitemap.xml` | Prohibido usar `?format=json`; extraer HTML estándar con pausa de `3–5 s`. *(Pendiente Fase 0: probar 1 página interior).* |
| `www.comicbookherald.com/robots.txt` y `/wp-json/` | `403 Forbidden` en ambos (WAF) | REST bloqueada; fuente en cuarentena hasta probar `/feed/` y acordar permiso con el autor. |
| `lamansion-crg.net/forum/robots.txt` | `404 Not Found` (sin `robots.txt`, sobre `http://`) | Usar `forum_scraper.py` con credenciales del usuario, validando `charset` y *Search Flood Control* en Fase 0. |
| Repositorio ZascArr (`v1.15.1`) | `cortesia.py`, `peticiones.py`, `forum_scraper.py`, `config.py`, `ADR-0011`, `ADR-0013`, `LEGAL.md`, `httpx` y `lxml` presentes | No añadir frameworks ni clientes HTTP nuevos; añadir solo `protego` + `http_cache` + adaptadores. |