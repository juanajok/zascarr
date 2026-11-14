# ADR 0018: Caché HTTP condicional en PostgreSQL e integración de wikis Fandom y guías de lectura

- Estado: **Aceptado** · 2026-11-14 (aceptación del PO; el borrador es del 2026-11-13, Fase 0 del estudio `docs/estudio-scraping-fuentes-v2.md`). Implementado y desplegado en la épica SCR.
- Relacionado con: [ADR 0011](0011-retirar-redis.md) (PostgreSQL como única tienda, sin Redis), [ADR 0013](0013-fuentes-de-metadatos-apagadas-por-defecto.md) (fuentes apagadas por defecto), CLAUDE.md §4 (cortesía compartida, caché local-first) y §5 (LEGAL.md).

## Contexto

ZascArr necesita consultar fuentes adicionales de metadatos (DC/Marvel Database en Fandom) y
órdenes de lectura (Comic Book Reading Orders, Continuity Guide), manteniendo el límite de
512 MB de RAM en Raspberry Pi y la política de máxima cortesía con terceros.

Verificado en vivo el 2026-11-13 (informe completo en `docs/design/informe-fase0-scraping-2026-11-13.md`):

- `api.php` de Fandom responde JSON sin clave (`MediaWiki 1.43.10`), con errores lógicos en HTTP 200 (`missingtitle`) y sin `ETag`/`Last-Modified`.
- `comicbookreadingorders.com` y `www.continuityguide.net` sirven sus páginas de guía y sitemaps a clientes `httpx` con el UA de ZascArr (sin challenge de Cloudflare), con `ETag` aprovechable.
- `www.comicbookherald.com` bloquea `robots.txt` y `wp-json` (WAF) pero **no** `/feed/` (RSS 200) — decisión de alcance pendiente del PO.
- `lamansion-crg.net/forum/` queda cubierto por `services/forum_scraper.py`; sus validaciones de charset y flood control requieren credenciales del usuario.

## Decisión

1. No introducir frameworks de crawling ni navegadores headless (Scrapy, Crawlee, Scrapling,
   Playwright) ni un segundo cliente HTTP: reutilizar `httpx` + `cortesia.py` + `peticiones.py` + `lxml`.
2. Incorporar `protego` (BSD-3) como única dependencia nueva para cumplimiento estricto de RFC 9309
   (`robots.txt`, comodines, `Crawl-delay` y bloqueo preventivo ante `429`/`5xx`).
3. Crear la tabla `http_cache` en PostgreSQL con cuerpos comprimidos (`zlib`, máx. 2 MiB),
   separando `fresh_until` (hit sin red) de `retain_until` (ventana de revalidación `304 Not Modified`)
   y aplicando coalescencia en vuelo (*singleflight*).
4. Consumir Fandom exclusivamente mediante su API oficial `/api.php` (`redirects=1`, `maxlag=5`),
   nunca mediante scraping del frontend web.
5. Mantener todas las fuentes nuevas desactivadas por defecto (ADR 0013) y vinculadas a
   `LEGAL.md` (cuyo hash versiona la aceptación: `services/legal.py::current_legal_version`; no hay
   constante que subir a mano).

## Consecuencias

- Cero servicios adicionales en Docker y huella de memoria controlada en 512 MB.
- Reducción drástica de tráfico repetido hacia blogs independientes mantenidos por creadores.
- Obligación de separar legal y visualmente en UI el texto CC-BY-SA de Fandom de las portadas
  editoriales, y de almacenar solo referencias fácticas (`use=reference`) en guías de lectura.
- Las piezas nuevas (`utils/robots.py`, `utils/cache_http.py`, adaptadores) se prueban con
  `httpx.MockTransport` y fixtures locales: cero tráfico real en CI.


---

## Estado de implementación (2026-11-14)

Aceptado por el PO tras implementar y verificar en vivo las piezas que lo materializan:

- **SCR1** (PR #756): tabla `http_cache` (migración `0038`, tras renumerar por colisión), caché condicional con
  `304`/negativas y `singleflight`; `robots.txt` con `protego` (RFC 9309). Topes reales de transferencia
  añadidos después en **RES-3** (PR #819): streaming con `CuerpoDemasiadoGrande`; y **M-4** (PR #832): tope de
  `Crawl-delay` y reinicio del estado de robots al apagar/encender una fuente.
- **SCR2** (PRs #734/#749): Fandom DC/Marvel como fuente de serie, número y arcos, con Comic Vine prevaleciendo;
  fuentes apagadas por defecto y atribución CC-BY-SA.
- **SCR3** (PRs #765/#771): guías de lectura de Reading Orders y Continuity Guide; reconciliación reutilizando
  `story_arcs`/`story_arc_issues.reading_order` (decisión del PO, sin entidad nueva).
- **SCR4** (PRs #783/#785/#787/#792): foro IPB con charset latin-1/cp1252, detector de flood control y aviso HTTP.
- **SCR5** (PR #800): Comic Book Herald por su feed RSS público (decisión §8.3: sin evasión del WAF).

Los puntos §8 del estudio que siguen abiertos (no bloquean este ADR) se registran en
`docs/design/deudas-menores-2026-11-14.md` y en el backlog (p. ej. SCR7: GCD/Metron/Open Library rellenando huecos).
