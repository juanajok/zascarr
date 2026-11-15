# Benchmark nivel 2 — Deseados: Prowlarr + foro IPB del CRG

**Historia / problema:** al buscar un deseo, ZascArr debe consultar Prowlarr **y** el foro
configurado (La Mansión del CRG en la instalación del PO), no solo uno como fallback. El
caso real que lo motivó: «DC K.O. está en La Mansión, pero Deseados mostraba un resultado
irrelevante de Prowlarr y no consultaba el foro».

**Fecha:** 2026-11-15. **SHA de ZascArr analizado:** `d20aad3d` (+ correcciones de la
rama de búsqueda conjunta). **Nivel:** 2 (toca búsqueda y fuentes externas). **Caduca:**
2027-01-14.

> **Aviso de proceso:** la implementación se hizo antes de esta ficha, por una petición
> directa y una incidencia en producción. Esta ficha es **post-hoc**; no se presenta como
> el benchmark previo que el procedimiento exige. Las lagunas están en §9.

## 1. Problema local y estado vigente

- **Deseados** busca por serie o número (`Orchestrator._search_and_rank`), con Prowlarr si
  está configurado y un plugin IPB genérico para el foro.
- **Antes:** el foro solo se consultaba si Prowlarr no dejaba candidatos. Un resultado
  irrelevante de Prowlarr impedía ver el foro.
- **Ahora:** Prowlarr y foro se consultan en paralelo; se mezclan, deduplican y rankean.
  Prowlarr usa categorías `7030`/`7020`; el foro usa el formulario IPB real.
- **Invariantes:** la búsqueda no descarga ni vincula; D10 exige confirmación humana; el
  aviso legal sigue bloqueando la búsqueda si no está aceptado; el foro no tiene URL por
  defecto.

## 2. Referencias y versiones

| Referencia | Versión/commit leído | Qué se inspeccionó | Límite de la inspección |
|---|---|---|---|
| Sonarr | documentación pública (wiki Servarr, 2026) | Add New, Library Import, estados | No ejecutado |
| Radarr | documentación pública (wiki Servarr) | Mismo patrón de agregación | No ejecutado |
| Prowlarr | documentación de API + instalación real del PO | `/api/v1/search`, indexers, categorías | Ejecutado en la Pi |
| Mylar3 | v0.8.3, `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (ficha previa) | `mylar/search.py`, proveedores Newznab/Torznab/DDL | No ejecutado |
| Kapowarr | v1.3.2, `c191dda6617929c81292483a8cc07f631111dae2` (ficha previa) | `backend/implementations/indexer_clients`, search coordinator | No ejecutado |
| Komga | documentación pública | Escaneo, metadatos, búsqueda local | No ejecutado |
| Kavita | documentación pública | Escáner y metadata match | No ejecutado |
| La Mansión del CRG | IPB observado en vivo 2026-11-15 | Login, formulario de búsqueda, tabla de resultados, temas, eD2K | Sin API ni versión pública |

Fuentes:

- Sonarr: <https://wiki.servarr.com/en/sonarr/library>
- Prowlarr: <https://wiki.servarr.com/prowlarr>
- Mylar3: <https://github.com/mylar3/mylar3>
- Kapowarr: <https://kapowarr.readthedocs.io/>
- Komga: <https://komga.org/es/docs/guides/search/>
- Kavita: <https://wiki.kavitareader.com/kavita+/metadata/>
- La Mansión: observación directa del formulario y la búsqueda; sin URL hardcodeada en
  el producto.

## 3. Cómo lo resuelve cada referencia

### Sonarr / Radarr

El consumidor consulta **Prowlarr** como agregador y recibe resultados normalizados. La
biblioteca/importación es otro flujo. No scrapean un foro: la fuente es un indexer.

**Lección:** una sola consulta al agregador; no reconstruir un segundo agregador. **No
cubre:** eD2K ni un foro HTML.

### Prowlarr

API REST `/api/v1/search`; devuelve resultados de varios indexers, cada uno con su nombre,
tamaño, seeders y URL de descarga. La instalación real del PO devuelve **0 resultados**
para «DC K.O.» con las categorías de cómic.

**Lección:** Prowlarr ya resuelve la agregación torrent/NZB. **No cubre:** foros, eD2K,
login, flood ni HTML.

### Mylar3

Modelo de proveedores (Newznab, Torznab, DDL) con orden y pausas; Prowlarr puede entrar
como proveedor Torznab/Newznab, pero no usa su API nativa. Búsqueda por número, cola de
wanted y matching.

**Lección:** una fuente no debe bloquear a las demás; conservar el filtro por número.
**No cubre:** un patrón listo para un foro IPB de eD2K.

### Kapowarr

Un indexer client DDL (GetComics); sin Prowlarr en la versión leída. Separa búsqueda,
scoring y descarga.

**Lección:** normalizar y puntuar antes de ofrecer; no unir búsqueda y descarga.
**No cubre:** Prowlarr ni foro.

### Komga / Kavita

Gestionan biblioteca/escaneo y metadatos; no buscan releases en fuentes externas.

**Lección:** separar catálogo de adquisición; ZascArr ya lo hace. **No cubre:** este flujo.

### La Mansión del CRG (IPB)

- Login con cookies de miembro.
- Formulario `act=Search&CODE=01` por **POST** con `forums[]=all`, `search_in=titles`,
  `result_type=topics`.
- Los resultados están en filas `<!-- Begin Topic Entry -->`; mezclan temas reales con
  paginación y «Último mensaje».
- Cada tema puede contener enlaces eD2K (y potencialmente magnet).
- Un `GET` con `keywords` no encuentra títulos cortos como «DC K.O.»; además puede
  devolver «No has elegido ningún foro».

**Lección:** hay que enviar el formulario real y filtrar la tabla, no enlazar a ojo.
**Límite:** sin API, sin contrato de estabilidad, con flood/rate limit y cambios de skin.

## 4. Matriz ponderada (nivel 2)

Criterios y pesos por defecto del procedimiento; suma 100.

| Criterio (peso) | Prowlarr solo | Cascada Prowlarr→foro | **Paralelo Prowlarr+foro** | Proveedores Mylar3 | DDL Kapowarr |
|---|---:|---:|---:|---:|---:|
| Flujo del Coleccionista (25) | 3 | 3 | **5** | 4 | 2 |
| Coste en Pi (20) | 5 | 4 | **4** | 3 | 3 |
| Seguridad/legalidad/licencia (20) | 4 | 3 | **3** | 3 | 1 |
| Cobertura del requisito (15) | 3 | 3 | **5** | 4 | 2 |
| Stack/modelo de datos (10) | 3 | 4 | **4** | 2 | 2 |
| Mantenimiento (5) | 4 | 3 | **3** | 2 | 2 |
| Lock-in/salida (5) | 4 | 3 | **3** | 3 | 2 |
| **Total ponderado /100** | **370 (3,70)** | **330 (3,30)** | **410 (4,10)** | **325 (3,25)** | **200 (2,00)** |

**Por qué gana el paralelo:** cubre el requisito real (ambas fuentes), no deja que un
resultado irrelevante de Prowlarr esconda el foro y mantiene el coste de Pi acotado
(consulta en paralelo, sin descargar contenido). La cascada era más barata pero peor para
el caso que motivó la historia; Prowlarr solo no cumple el «también foro». Mylar3 exige
otro modelo de proveedores y no resuelve el foro; Kapowarr no usa Prowlarr.

La puntuación de legalidad no es un aval: el foro es una integración genérica configurada
por el usuario, con aviso legal. Integrar/recomendar un foro concreto sigue descartado.

## 5. Resultado por idea (adoptar / adaptar / mejorar / construir sobre lo propio / descartar)

| Idea | Resultado | Motivo |
|---|---|---|
| Prowlarr como agregador de indexers | **Adoptar** | Ya resuelve torrent/NZB y aísla el fallo de cada indexer |
| Consultar Prowlarr y foro en paralelo | **Adaptar** | La concurrencia es del consumidor; la referencia no mezcla HTML |
| Formulario IPB por POST con `forums[]=all` | **Adaptar** | Depende del foro; se conserva el origen y las cookies del plugin |
| Resultado común `SearchResult` y ranking | **Construir sobre lo propio** | Ya existe; el foro se traduce a ese contrato |
| Deduplicación por URL+título | **Mejorar** | Evita dos botones de la misma release; se conserva el título como discriminante |
| Filtro de relevancia por palabras completas | **Mejorar** | Evidencia: «ko» dentro de «Konar» colaba un manual de ginecología |
| Mostrar estado de cada fuente en los resultados | **Mejorar** | Hoy un fallo del foro se silencia si Prowlarr trae algo; el Coleccionista no lo sabe |
| Mostrar enlace al tema/tamaño desconocido | **Mejorar** | El candidato del foro muestra 0 B y no permite verificar el tema |
| Autoimportar/autoenviar sin confirmar | **Descartar** | Rompe D10 y el consentimiento por efecto |
| Construir un stack Newznab/Torznab propio (Mylar3) | **Descartar** | Prowlarr ya hace de agregador; coste y RAM en la Pi |
| DDL GetComics como única fuente | **Descartar** | No cubre eD2K ni el foro del caso real |

## 6. Medición en la Pi (2026-11-15)

Se usó la configuración real de la instalación y una política de cortesía a 0 para medir
red+parseo del foro (la aplicación real añade `forum_search_rate_limit` de 25 s entre
búsquedas). Las cifras del foro son 5 ejecuciones para «Batman»; las de «DC K.O.» son la
muestra del caso real.

| Operación | Resultado | Tiempo observado |
|---|---|---:|
| Prowlarr `/api/v1/search` «DC K.O.» (categorías 7030/7020) | **0 resultados** | 0,30–0,57 s |
| Prowlarr «Batman» (5 ejecuciones) | **127 resultados** | media 2,62 s |
| Foro: login + POST búsqueda «DC K.O.» | **10 temas** | 3,75–5,18 s |
| Foro: login + POST «Batman» (5 ejecuciones) | **10 temas** | media 4,97 s |
| Foro: primer tema de «DC K.O.» | **27 enlaces eD2K** | — |
| Solapamiento exacto de títulos Prowlarr/foro («Batman») | **0** | — |
| Suma secuencial Prowlarr + foro («Batman») | 127 + 10 candidatos | ~7,6 s |
| Paralelo (estimación con las medias) | 127 + 10 candidatos | ~5 s |

**Lectura:** Prowlarr y el foro cubren cosas distintas. «DC K.O.» no aparece en Prowlarr
con esas categorías, pero sí en el foro; «Batman» devuelve 127 resultados de indexers y 10
temas del foro. El solapamiento de **títulos exactos** es 0, pero no se puede concluir que
no haya duplicados de release: los nombres de un topic y de un release no son comparables
sin normalizar más. La deduplicación actual (URL+título) no cubre ese caso.

**Coste de UI:** 127 + 10 candidatos es una lista grande; la ficha no mide renderizado ni
decide un límite. Es una deuda para una historia aparte.

## 7. Casos de prueba que deben quedar cubiertos

- Prowlarr y foro consultados aunque Prowlarr devuelva resultados.
- Resultado irrelevante de Prowlarr filtrado por palabras completas («Konar» no es «ko»).
- Foro con GET: no se usa; con POST y `forums[]=all`: devuelve temas.
- Parser ignora navegación y paginación; lee solo filas `Begin Topic Entry`.
- Flood del foro no oculta candidatos de Prowlarr; sin candidatos, deja `MOTIVO_FORO_ESPERA`.
- Deduplicación URL+título.
- El aviso legal y D10 no cambian.
- Ancho de la UI de candidatos con dos fuentes y tamaños desconocidos.

Pruebas existentes: `tests/test_orchestrator.py`, `tests/test_forum_scraper.py`,
`tests/test_forum_flood.py`, `tests/test_forum_charset.py`, `tests/test_forum_cortesia.py`,
`tests/test_web_wishlist.py`.

## 8. Recomendaciones (no implementadas en esta ficha)

1. **Estado por fuente en la lista**: si el foro falla, mostrar «Foro no disponible» sin
   ocultar los resultados de Prowlarr (y viceversa).
2. **Candidato del foro legible**: «Tamaño desconocido» en vez de `0 B`; enlace al tema
   para verificar la release.
3. **No cambiar el ranking sin datos**: hoy los torrents van antes que eD2K; el foro solo
   aporta eD2K. Medir antes de priorizar de otra forma.
4. **Instrumentar**: duración, número de resultados y estado por fuente por búsqueda, para
   repetir este benchmark con datos.
5. **Mantener el foro como opcional**: URL/credenciales del usuario, sin foro recomendado.

## 9. Ejecutado, FAIL y NOT RUN

### Ejecutado

- **Prowlarr real**: 5 ejecuciones de «Batman» (127 resultados, media 2,62 s) y «DC K.O.»
  (0 resultados, < 1 s).
- **Foro real**: login + POST, 5 ejecuciones de «Batman» (10 temas, media 4,97 s) y
  «DC K.O.» (10 temas; primer tema con 27 enlaces eD2K).
- **Solapamiento exacto de títulos** Prowlarr/foro («Batman»): 0.
- **Robots de La Mansión**: `http://lamansion-crg.net/robots.txt` responde
  `User-agent: * / Disallow: / / Noindex: /`.
- **Página de términos/registro**: responde 200; no se aceptó ni se interpretó el contrato.
- **Smoke de apps de referencia**: ver §9.1.

### FAIL

- **Robots del foro:** prohíbe a todos los robots acceder a todo el contenido. El plugin es
  opt-in y de URL aportada por el usuario, pero una integración recomendada o por defecto no
  es aceptable con esta política. Debe ser una decisión explícita del operador, con aviso.
- **Duplicados:** 0 coincidencias de título exacto no equivale a 0 duplicados de release.
  No hay medición release-a-release; la deduplicación URL+título no los detecta si cambian
  el nombre.
- **UI con 127 candidatos:** no se midió renderizado; el listado no tiene un límite visible.

### NOT RUN / bloqueado

- **Flujos completos de Sonarr, Radarr, Mylar3, Kapowarr, Komga y Kavita**: no se
  ejecutaron búsqueda, importación ni matching. El smoke de arranque no los demuestra.
- **Otros foros IPB**: no se probaron; faltan credenciales y permiso.
- **5 coleccionistas / lector de pantalla**: no se puede ejecutar desde este entorno.
- **Términos completos del foro**: solo se comprobó robots y que la página responde.
- **Ranking con datos**: no se midió qué fuente produce mejores descargas.
- **Títulos con tildes/acrónimos/ediciones españolas**: no hay matriz sistemática.

### 9.1 Smoke de aplicaciones de referencia

Imágenes oficiales levantadas en Docker el 2026-11-15. **PASS de smoke** = contenedor
arriba y UI/API responde. **No es PASS de benchmark**: no se configuraron indexers, no se
añadieron series ni se ejecutaron búsquedas/importaciones.

| Aplicación | Imagen | Evidencia | Resultado |
|---|---|---|---|
| Sonarr | `linuxserver/sonarr:latest` | `/ping` → 200 `{"status":"OK"}` | **PASS smoke** |
| Radarr | `linuxserver/radarr:latest` | `/ping` → 200 `{"status":"OK"}` | **PASS smoke** |
| Mylar3 | `linuxserver/mylar3:latest` | UI redirige a login (303), app viva | **PASS smoke** |
| Komga | `gotson/komga:latest` | UI 200, Lucene/index inicializado | **PASS smoke** |
| Kavita | `linuxserver/kavita:latest` | UI 200, `Kavita - v0.9.1.4` | **PASS smoke** |
| Kapowarr | `mrcas/kapowarr:latest` | UI 200, API key generada al arrancar | **PASS smoke** |

No se creó una biblioteca en Komga/Kavita, no se añadió un indexer a Sonarr/Radarr, no se
configuró Prowlarr en ellos y no se ejecutó una búsqueda en Mylar3/Kapowarr. Por tanto **no
se comparó su flujo completo**; solo se acreditó que las versiones arrancan en este entorno.

**Caducidad:** revisar en ~60 días (2027-01-14) o antes si cambia Prowlarr, el foro o la
historia.

## 10. Decisión propuesta

**Mantener el patrón paralelo Prowlarr + foro**, con Prowlarr como agregador y el foro como
fuente opcional IPB configurada por el usuario, y aplicar las mejoras de transparencia de
§8 en una historia aparte. No se introduce modelo de datos nuevo ni se recomienda un foro
concreto.

**Condición legal:** el `robots.txt` del foro prohíbe a todos los robots. La integración
debe seguir siendo opt-in, con URL y credenciales del operador, y no puede presentarse como
«foro recomendado» ni activarse por defecto. Antes de convertirla en función de producto
estable, el PO y legal deben decidir si se mantiene el scraping de un sitio con
`Disallow: /`; esta ficha no lo autoriza.

IGUALAR: agregación de Prowlarr, resultado normalizado, rate limit, confirmación humana.
MEJORAR: paralelismo real, búsqueda POST del foro, filtro por palabras completas,
deduplicación y (pendiente) transparencia de estado por fuente.
