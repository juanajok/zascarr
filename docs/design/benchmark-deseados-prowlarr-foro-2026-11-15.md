# Benchmark — Deseados: Prowlarr + foro CRG en paralelo

**Fecha:** 2026-11-15. **Carácter:** adenda **post-hoc** al benchmark de Deseados/Prowlarr del
2026-11-11. **No es exhaustivo** en el sentido de haber comparado todos los productos antes de
implementar: la implementación se hizo primero por una petición directa y una incidencia real.
Esta ficha documenta las referencias que sí se consultaron, las que faltan y por qué.

## 1. Pregunta y alcance

¿Debe «Deseados» buscar en **Prowlarr** y en el **foro de La Mansión del CRG** a la vez, o mantener
una cascada Prowlarr → foro? ¿Cómo lo resuelven otras herramientas?

**Alcance:** búsqueda de una serie/número en Deseados; no descarga, no importación, no scraping de
contenido. **Fuera:** validar legalidad de cada foro, medir catálogos, comparar calidad de releases.

## 2. Comportamiento de ZascArr antes y después

| Momento | Prowlarr | Foro | Resultado |
|---|---|---|---|
| Antes | Se consulta primero | Solo si Prowlarr no deja candidatos | Un resultado irrelevante de Prowlarr impedía consultar el foro |
| Después | Se consulta siempre | Se consulta siempre, en paralelo | Se mezclan, deduplican y rankean; un flood del foro no oculta Prowlarr |

El foro sigue siendo el **plugin IPB genérico**: la URL la configura el usuario, no hay URL por
defecto ni foro recomendado. La instalación del PO usa `lamansion-crg.net`.

## 3. Referencias consultadas

| Referencia | Patrón | Qué enseña | Qué no cubre |
|---|---|---|---|
| **Sonarr / Radarr** | Prowlarr como agregador de indexers; la app consulta una API y recibe resultados normalizados | Separar agregador de consumidor; una sola lista de candidatos | No scrapea foros; no mezcla una fuente HTML con indexers |
| **Prowlarr** | Agrega Newznab/Torznab y devuelve resultados de todos los indexers | El consumidor no debe reconstruir un segundo agregador | No conoce eD2K ni un foro IPB |
| **Mylar3** | Proveedores Newznab/Torznab/DDL; Prowlarr puede entrar como Torznab/Newznab | Búsqueda por número, cola y proveedores; una fuente no bloquea a las demás | No usa la API nativa de Prowlarr; no aporta un patrón de foro CRG |
| **Kapowarr** | Indexer client GetComics (DDL) | Separar búsqueda, scoring y descarga | No usa Prowlarr ni foros |
| **Komga / Kavita** | Escaneo de biblioteca y metadatos; no buscan descargas | Separar identificación/catálogo de adquisición | No resuelven «buscar un release en un foro» |
| **La Mansión del CRG (IPB)** | Foro HTML con login; búsqueda por POST (`forums[]=all`, `search_in=titles`, `result_type=topics`); temas con enlaces eD2K | El foro no es una API: hay que enviar el formulario real, no inventar una URL GET | Sin API, sin promesa de estabilidad, flood y cambios de skin |

Fuentes:

- Sonarr: [Library](https://wiki.servarr.com/en/sonarr/library).
- Prowlarr: [API de búsqueda](https://prowlarr.com/docs/api/) (documentación pública del proyecto).
- Mylar3: [README](https://github.com/mylar3/mylar3).
- Kapowarr: [documentación](https://kapowarr.readthedocs.io/).
- Komga: [Full Text Search](https://komga.org/es/docs/guides/search/).
- Kavita: [Metadata](https://wiki.kavitareader.com/kavita+/metadata/).

## 4. Comparación de patrones

| Dimensión | Sonarr/Radarr | Mylar3 | Kapowarr | ZascArr actual |
|---|---|---|---|---|
| Entrada | API Prowlarr | Proveedores | GetComics | Prowlarr + foro |
| Fuentes simultáneas | Sí, dentro de Prowlarr | Sí, por proveedor | Un cliente | Sí, dos fuentes |
| Resultados HTML | No | DDL/foro según proveedor | DDL | Sí (IPB) |
| Normalización | La hace Prowlarr | Por proveedor | Propia | `SearchResult` común |
| Fallo de una fuente | Aislado por Prowlarr | Pasa al siguiente | Falla la búsqueda | Aislado: Prowlarr y foro se capturan por separado |
| Flood/rate limit | Gestionado por indexer | Pausas por proveedor | Rate limit propio | Cola compartida + `ForumFloodControl` |
| Deduplicación | Prowlarr/indexers | Según proveedor | No aplica | URL + título |
| Relevancia | Motor de búsqueda | Matching | Matching | Palabras completas + filtro de número + alias |
| Descarga | Cliente externo | Cliente externo | Cliente externo | Transmission/aMule, confirmación manual (D10) |

## 5. Decisiones

1. **Mantener Prowlarr como agregador**: no se construye un segundo sistema de indexers.
2. **Foro como fuente opcional y genérica**: URL y credenciales del usuario; el proyecto no
   hardcodea ni recomienda un foro.
3. **Consultar ambas en paralelo**: una fuente lenta o en flood no debe impedir ver la otra.
4. **Mezclar y deduplicar**: URL + título; ranking existente (torrents antes que eD2K).
5. **Filtrar por palabras completas**: «DC K.O.» no debe aceptar un título que solo contiene
   «dc» o «ko» dentro de otra palabra («Konar»).
6. **Conservar la confirmación humana**: la búsqueda no envía nada; D10 sigue decidiendo.

## 6. Lo que falta para llamarlo exhaustivo

- **No** se comparó el comportamiento de otros foros IPB/CRG ni de varios foros simultáneos.
- **No** se midieron latencias reales de Prowlarr + foro en paralelo frente a cascada.
- **No** se midió la tasa de duplicados entre Prowlarr y el foro, ni el ranking resultante.
- **No** se probaron títulos cortos, acrónimos, tildes y ediciones españolas de forma sistemática.
- **No** se ejecutó una prueba con 5 coleccionistas ni lectura con lector de pantalla.
- **No** se revisó la licencia/términos de La Mansión para una integración recomendada; se usa como
  foro configurado por el usuario, no como fuente incluida.

## 7. PASS / FAIL / NOT RUN

- **PASS (código):** Prowlarr y foro se consultan en paralelo; el fallo/flood de uno no oculta al
  otro; el foro usa POST real con `forums[]=all`; el filtro de relevancia exige palabras completas.
- **PASS (producción, 2026-11-15):** «DC K.O.» devuelve 10 temas del foro, incluido el tema
  principal con 27 enlaces eD2K; Prowlarr no devuelve resultados relevantes para esa consulta.
- **FAIL (benchmark exhaustivo):** no se ha comparado el patrón con otras herramientas en vivo ni
  medido resultados; esta ficha es una revisión de referencias y del comportamiento propio.
- **NOT RUN:** latencias, duplicados, usuarios, otros foros y términos.
