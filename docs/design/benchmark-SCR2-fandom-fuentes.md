# Ficha de benchmarking — SCR2: Fandom (DC Database y Marvel Database) como fuente

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Paso de diseño previo a la
> spec; no aprueba nada: decide el PO.
>
> - **Fecha:** 2026-11-13.
> - **SHA contrastado:** `17a5995e` (`main` + cambios sin commitear). La rama `feat/fandom-fuentes`
>   apunta a `8f90aa4b` y **no** contiene estos cambios; los documentos de referencia (estudio,
>   anexos, informe Fase 0) solo existen en `docs/scraping-v2` (`db200c35`), no en `main`.
> - **Alcance:** `services/fandom.py`, cadena del `enricher` (serie/número/arcos), `config.py`,
>   `cortesia.py`, `url_portada.py`, migración 0035, Ajustes y `LEGAL.md`. **Fuera:** Fase 3
>   (guías de lectura) y foro CRG. **Caducidad:** 2027-01-12 o antes si cambia MediaWiki/estudio.

## 0. Resultado en una línea

La integración es **viable y su contrato de API está verificado en vivo**, pero **no está lista
para fusionar**: falta el mapeo ORM de las columnas de 0035 (el ciclo del enricher revienta en el
estado actual), la fecha DC mezcla el día de venta con el mes de portada, la Fase 1 del estudio
(robots + caché HTTP) no existe y la atribución CC-BY-SA no es visible en la ficha.

## 1. Contraste con la referencia escrita

| Pieza | Referencia | Implementación (evidencia) | Resultado |
|---|---|---|---|
| Vía de lectura | §5.5: `action=parse` HTML + `lxml`/XPath | `query&prop=revisions` wikitext + regex (`fandom.py:459-507`); wikitext real 8–41 KB | **Adaptar** (mejor: más ligero y determinista; el estudio no lo contemplaba) |
| Errores en HTTP 200 | §5.5 / Trampa 1: `missingtitle`, `maxlag` | `_api()` inspecciona `error`; 5 códigos de inexistente; `maxlag` bloquea cortesía ≥5 s (`fandom.py:459-491,629-640`) | **Adoptar** |
| Portadas | §5.5: `imageinfo` → CDN y limpiar sufijos de miniatura | `_url_de_imagen()` + allowlist/intervalo del CDN (`url_portada.py:53`, `cortesia.py:129`) | **Adoptar** (la limpieza no hace falta: `iiprop=url` da la original) |
| Caché HTTP | Fase 1: `http_cache` (positivo 24 h, negativo 12 h) | No implementada; solo caché negativa de BD (`enrichment_attempted_at`, 30 d) | **Aplazar** a Fase 1; registrar deuda |
| robots.txt | Fase 1: `utils/robots.py` | No existe ni se consulta; `api.php` abierto según el estudio | **Aplazar** con dictamen del PO |
| Arcos / orden | Fase 3: `ReadingOrder` + resolver puro | `StoryArc`/`StoryArcIssue.reading_order` ya existentes; `StoryArcs` de la plantilla DC | **Construir sobre lo propio** (§12) |
| Prioridad en enricher | §8.2 abierta para el PO | Cadena fija Comic Vine → DC → Marvel (`enricher.py:542-556`) | **Adaptar**; la spec debe fijarla o hacerla configurable |
| Legal / UI | CC-BY-SA 3.0: enlace al artículo **y** a la licencia | `LEGAL.md:107` correcta; aviso UI genérico sin Fandom ni enlaces (`_legal_disclaimer.html:21-26`) | **Mejorar** (gap de cumplimiento) |

## 2. Verificación en vivo (2026-11-13, 4 peticiones, UA `ZascArr/1.15.1 (+…; benchmark SCR2)`)

Pausa de 2,2 s entre peticiones; todas `HTTP 200`, `application/json`, sin `ETag`/`Last-Modified`.

| # | Petición | Hecho confirmado |
|---|---|---|
| 1 | `dc.fandom.com/api.php` `action=query&prop=revisions&titles=Batman Vol 1\|Batman Vol 1 404` | Prefijos `{{DC Database:Volume Template}}` y `{{DC Database:Comic Template}}`. Volumen: `StartYear=1940`, `EndYear=2011`, `TotalIssues=715`, `Type=Ongoing Series`, `IssueImage=Batman 1.jpg`, `StoryArcs=[[Batman: Year One\|Year One]];…`. Issue 404: `Day=21 <!-- GCD -->`, `Month=2`, `Year=1987`, `Pubmonth=10 <!-- GCD -->`, `Pubyear=1986`, `Image=Batman 404.jpg`, `Writer1_1=Frank Miller` |
| 2 | `marvel.fandom.com` `titles=Fantastic Four Vol 1 1` | `{{Marvel Database:Comic Template}}`; `ReleaseDate=August 8, 1961`, `Image1`, `Writer1_1=Stan Lee`. El `ReleaseDate` existe y es la fecha de venta |
| 3 | `action=parse&page=ZascArr SCR2 Nonexistent Benchmark Page` | HTTP 200 con `error.code=missingtitle` (Trampa 1 confirmada) |
| 4 | `prop=imageinfo&iiprop=url&titles=File:Batman 1.jpg` | URL `https://static.wikia.nocookie.net/marvel_dc/images/0/06/Batman_1.jpg/revision/latest?cb=…`; host del CDN el esperado |

## 3. Hallazgos que cambian la spec (con evidencia)

1. **Bloqueante — el ORM no mapea las columnas de 0035.** La migración añade `fandom_dc_slug`/`fandom_marvel_slug` a `series` e `issues`, pero `models/__init__.py` solo añade los valores del enum (`:285-286`). `hasattr(Series, "fandom_dc_slug") is False` y `enricher.py:415` lo usa en el `SELECT` incondicional de `_enrich_series_batch`: hoy **todo** ciclo de enriquecimiento falla con `AttributeError` (con cualquier fuente encendida, no solo Fandom). Los 21 tests de `tests/test_fandom.py` pasan porque solo prueban el cliente y `_sources_for`, nunca el `EnrichmentService` contra el ORM.
2. **Fecha DC semánticamente invertida.** `fecha_de_parametros` combina `Day` (día de venta marcado GCD) con `Month`/`Year` (fecha de **portada**): Batman #404 devuelve `1987-02-21`. Los parámetros de publicación (`Pubmonth=10`, `Pubyear=1986`) darían `1986-10-21`; solo se usan como respaldo si falta `Month`/`Year`. Si `Issue.release_date` significa salida a la venta (es el único escritor hoy), la prioridad está invertida. El fixture del test fija `Month=5` (en vivo es `2`) y espera `1987-05-21`: la prueba no cubre el caso real.
3. **Documentos citados ausentes en la rama.** `fandom.py:3,15`, la migración 0035 y el docstring del enricher remiten a `docs/estudio-scraping-fuentes-v2.md` (y su Anexo C), que no está en `main`/`feat/fandom-fuentes`. Hay que fusionar la rama de docs o corregir referencias antes de la fusión.
4. **Fase 1 no implementada.** No existen `utils/cache_http.py` ni `utils/robots.py`; el cliente no evalúa `robots.txt` ni cachea respuestas HTTP y se apoya en la caché negativa de BD. La secuencia del estudio (Fase 1 antes de Fase 2) no se cumple: el PO debe ratificarlo o bloquear.
5. **Atribución incompleta.** `LEGAL.md` exige enlace al artículo y a la licencia CC-BY-SA 3.0, pero la UI muestra un aviso genérico (ni Fandom ni enlaces) y `procedencia.NOMBRE_DE_FUENTE` no conoce las fuentes Fandom. El CDN tampoco está en `HOST_DE_FUENTE_PARA_PORTADAS`: apagar Fandom no corta sus portadas (contradice AC-12/ADR 0013).
6. **Coste por serie mayor de lo que sugiere el estudio.** `get_volume` hace 2–3 peticiones (wikitext + `displaytitle` si faltan años + `imageinfo`, siempre, aunque ya haya portada) y `_find_fandom_match` abre hasta 2 candidatos: peor caso ~7 peticiones/serie a 1,5 s. No bloquea la Pi, pero condicionar `imageinfo` a «falta portada» es una mejora barata.
7. **No verificado en vivo** (fuera del presupuesto de 4 peticiones): invocación de `{{Marvel Database:Volume Template}}` y formato del `displaytitle` de un volumen Marvel (el informe Fase 0 verificó un issue DC, «Batman (1940) #404», no un volumen); tampoco la sección `Issues` de una página de arco.

## 4. Decisión por pieza

| Pieza | Decisión |
|---|---|
| Wikitext (`query&prop=revisions`) en vez de HTML con XPath | **Adaptar** (mejor); mantener tests de plantilla y añadir el de la plantilla Marvel de volumen |
| Prefijos `DC Database:*` / `Marvel Database:*` y parámetros verificados | **Adoptar** (Marvel Volume pendiente de verificación) |
| Clasificador de errores en HTTP 200 | **Adoptar** (verificado `missingtitle`; `maxlag` no se provocó) |
| `imageinfo` + descarga desde `static.wikia.nocookie.net` | **Adoptar** (host verificado; con cortesía propia del CDN) |
| `release_date` DC: `Pubmonth`/`Pubyear` + `Day` antes que `Month`/`Year` | **Mejorar**: corregir antes de fusionar y decidir en spec si se guarda fecha de venta o de portada |
| Caché HTTP condicional y `robots.py` | **Aplazar** a Fase 1; deuda explícita, no fingir que existe |
| Arcos sobre `StoryArc`/`StoryArcIssue` (sin `ReadingOrder` nuevo) | **Construir sobre lo propio**; documentar el límite: números sin serie local se omiten y `reading_order` colapsa huecos |
| CDN de portadas no mapeado a fuente Fandom | **Mejorar**: mapearlo (con dos fuentes posibles) o documentar la excepción a AC-12 |
| Cadena fija CV → DC → Marvel | **Adaptar** según decisión §8.2 del PO |

## 5. Riesgos y veredicto

Riesgos: (a) ORM/migración desalineados → QA con Postgres real; (b) anuales y especiales con otra convención de título caen en caché negativa de 30 días; (c) crossovers solo enlazan series que ya tengan `fandom_dc_slug`; (d) títulos de arco genéricos colisionan por `title` exacto; (e) plantilla/`displaytitle` Marvel de volumen sin verificar.

**Veredicto: NO APTA para fusionar en el estado actual.** El diseño es correcto y verificable, pero el mapeo ORM y la fecha DC son bloqueantes. Recomendación: builder corrige ambos; spec ratifica prioridad en el enricher y qué hacer con Fase 1 y la atribución; QA añade una prueba de integración del `EnrichmentService` con Postgres real (no solo `MockTransport`) y una regresión de la fecha DC con los parámetros reales de Batman #404.
