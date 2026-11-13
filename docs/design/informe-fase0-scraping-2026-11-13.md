# Informe de Fase 0 — Spike de verificación en vivo (2026-11-13)

> Ejecutado contra `docs/estudio-scraping-fuentes-v2.md` §7 y
> `docs/ANEXOS-IMPLEMENTACION-ZASCARR-V2.md` Anexo B. Herramienta:
> `scripts/spike_fase0_fuentes.py` (1 petición por comprobación, pausa 2,5 s,
> UA identificado de ZascArr). Sin código de producción ni migraciones.

## Resultados del spike

| # | Comprobación | Resultado | Implicación |
| :--- | :--- | :--- | :--- |
| 1 | `dc.fandom.com/api.php` `action=parse` de `Batman_Vol_1_404` (con `redirects=1`) | **200**, JSON 56 KB, `displaytitle` = *Batman (1940) #404* | API y redirecciones funcionan; el contrato de `fandom.py` §5.5 es válido |
| 2 | `action=parse` de artículo inexistente | **200** con `mw_error=missingtitle` (345 B) | **Trampa 1 confirmada**: el clasificador de respuestas (`clasificar_respuesta_mediawiki`) es obligatorio |
| 3 | `comicbookreadingorders.com/sitemap_index.xml` | **200 pero `text/html`** (19 KB, no XML) | **No existe** `sitemap_index.xml`; el check 3 del Anexo B debe corregirse |
| 4 | `comicbookreadingorders.com/sitemap.xml` | **200**, `application/xml` 78 KB, `ETag` | El sitemap real es `sitemap.xml` (el que declara su robots.txt); revalidable por ETag |
| 5 | Guía interior (`/dc/events/crisis-on-infinite-earths-reading-order/`) | **200**, HTML 89 KB | Cloudflare NO interpone JS Challenge con el UA de ZascArr; extracción con XPath viable |
| 6 | `continuityguide.net/planet-x` (URL supuesta) | **404** con HTML de 663 KB y `ETag` | La URL era errónea; además revela que Squarespace sirve su 404 con cuerpo grande: tratar `RespuestaNoTransitoria(404)` → negativa, no como página vacía |
| 7 | `continuityguide.net/sitemap.xml` | **200**, `text/xml` **1,7 MB**, locs reales (`/planetx`, `/house-of-m`, `/disassembled`…) | Descubrimiento viable; el sitemap es grande (descargarlo por caché, no en cada arranque) |
| 8 | Página interior real `continuityguide.net/home` | **200**, HTML 208 KB, `ETag` | Extracción SSR con XPath viable y revalidación 304 aprovechable |
| 9 | `comicbookherald.com/feed/` | **200**, `application/rss+xml` 172 KB, `ETag` + `Last-Modified` | **Hallazgo importante:** el WAF bloquea `robots.txt`/`wp-json` pero NO `/feed/` con el UA de ZascArr. La cuarentena de Herald (§2) puede revisarse vía RSS si el PO aprueba |

## Hallazgos para el diseño

1. **Fandom no emite `ETag`/`Last-Modified` en `api.php`** (checks 1 y 2): la revalidación 304 no aplica aquí; la caché para Fandom será TTL fijo (24 h) + clasificador (`missingtitle` → negativa corta; `maxlag` → no cachear), exactamente como prevé el Anexo C.2.
2. **Corrección al Anexo B**: sustituir `sitemap_index.xml` por `sitemap.xml` en el check 3 del spike (verificado en vivo).
3. **Continuity Guide**: URLs sin guion (`/planetx`), sitemap de 1,7 MB (caché + TTL), 404 con cuerpo grande y ETag (negativa con TTL, sin reintentos).
4. **Pendiente (requiere cuenta del usuario)**: las tres validaciones del foro CRG (charset `ISO-8859-1`/`Windows-1252`, *Search Flood Control* y aviso `http://`) no se ejecutan sin credenciales. Quedan para el PO/usuario antes de cerrar Fase 0.

## Decisión registrada del PO

Pendiente: prioridad de Fandom en el enricher (§8.2), modelo de producto de órdenes de lectura (§8.1) y destino de Comic Book Herald (§8.3, ahora con el dato de que `/feed/` responde 200).

## Corrección técnica para los documentos v2 (verificada contra el código)

`services/legal.py:13-15,40-45`: `legal_version` **no se sube a mano** — es el hash sha256 del
propio `LEGAL.md` (`current_legal_version()`), y editarlo invalida automáticamente la aceptación
anterior. Los puntos del estudio (§0.3, §6) y del Anexo E.2 que dicen «reversionar/subir
`legal_version`» deben leerse como «**actualizar `LEGAL.md` en el mismo PR**» (el hash cambia
solo, y `require_legal_acknowledgment` queda protegido sin ningún otro paso).
