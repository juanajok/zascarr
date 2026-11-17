# Benchmark — CompartiComics (referencia externa, 2026-11-15)

> **Decisión:** usar solo como **referencia de benchmarking**. **No se integra** como fuente
> de metadatos ni de descarga. Este documento no añade código, endpoints, migraciones ni
> enlaces de descarga.
>
> **Alcance de la observación:** HTML público de portada y biblioteca, `robots.txt` y
> metadatos visibles. **NO RUN:** descarga de archivos, inspección de enlaces de descarga,
> cuentas, API (no documentada) ni validación móvil real.

## 1. Qué es

`https://comparticomics.lat/` se presenta como una **biblioteca digital de cómics en
español** con descarga gratuita:

- `meta description`: «Más de 150.000 cómics en español para descargar gratis».
- La vista de biblioteca muestra **173.385 libros**.
- Navegación: Inicio, Tendencias, Novedades, Categorías, Autores, Favoritos, Vistos
  recientemente, búsqueda (`Ctrl K`), Fuentes, Cómo leer, Ingresar y Donar.
- La portada enlaza a canales de Telegram, foros y blogs de terceros, además de enlaces de
  donación.
- `robots.txt`: `User-agent: *` / `Allow: /` y un sitemap. **Permitir el rastreo no concede
  licencia sobre el contenido.**

No se ha encontrado una página de términos, aviso legal o DMCA en las rutas probadas
(`/terminos`, `/dmca` devuelven 404). No hay una API pública documentada.

## 2. Benchmark por dimensiones

| Dimensión | CompartiComics | Komga / Kavita | Sonarr/Radarr | ZascArr |
|---|---|---|---|---|
| **Catálogo** | 173k libros, categorías, autores, tendencias y novedades | Biblioteca local del usuario | Biblioteca + indexers | Biblioteca local + fuentes de metadatos legales |
| **Búsqueda** | Buscador global con atajo `Ctrl K`, filtros por categoría/autor | Búsqueda local y filtros | Búsqueda + «Add New» | Búsqueda local, fuentes y filtros |
| **Ficha** | Ficha de libro/serie dentro de la web | Ficha de serie con pestañas/paneles | Ficha de serie con pestañas | Ficha de serie con navegación por anclas |
| **Origen del contenido** | Descargas alojadas/enlazadas por el sitio | Archivos del usuario | P2P/eD2K vía clientes del usuario | Archivos del usuario; clientes e indexers que él configura |
| **Metadatos** | No declara procedencia ni licencia | Embebidos/ComicInfo | Desde TVDB/TMDB | Comic Vine, AniList, Tebeosfera, GCD, Fandom; procedencia visible |
| **Legalidad** | Sitio de descarga gratuita sin términos/localizables; contenido de terceros | Gestor local | Herramienta neutra con indexers del usuario | `LEGAL.md`: gestiona, no facilita |
| **API** | No documentada | API propia | API propia | API FastAPI propia |
| **Móvil** | Tema oscuro y navegación responsive (no validado) | Apps/web responsive | Web responsive | Web mobile-first |
| **Modelo** | Donaciones + enlaces externos | Self-hosted | Self-hosted | Self-hosted GPL |

## 3. Ideas de UX que se pueden estudiar sin copiar contenido

Estas ideas son de **interacción**, no de catálogo ni de descarga:

| Idea | Veredicto |
|---|---|
| Buscador global con atajo `Ctrl K` y resultados agrupados | **Estudiar** para Descubrir; ya hay búsqueda, no atajo global |
| «Tendencias» / «Novedades» como entradas de descubrimiento | **Descartar** para ZascArr: no hay telemetría ni catálogo propio; inventarlo sería deshonesto |
| Favoritos y «vistos recientemente» | **Fuera de alcance** de esta historia; ya existe estado de lectura y Deseados |
| Página «Fuentes» con estado de cada fuente | **Estudiar** para Ajustes/Estado, sin integrar este sitio |
| «Cómo leer» con apps recomendadas | **Descartar** en ZascArr: la app sirve su propia biblioteca; no necesita derivar a lectores externos |

## 4. Por qué no se integra

1. **No hay licencia ni términos**: no se puede acreditar que los metadatos o archivos sean
   lícitos ni que permitan su uso por terceros.
2. **La descarga es el producto**: un scraper convertiría a ZascArr en facilitador de acceso
   a copias de terceros, en contra de `LEGAL.md` §1 y §3.
3. **Sin API**: cualquier integración sería scraping HTML frágil de un sitio que no ofrece
   contrato de uso.
4. **Privacidad y seguridad**: enlaces a Telegram/foros y descargas externas quedan fuera
   del modelo de fuentes evaluadas y de la política de cortesía/SSRF.
5. **Ya existe la vía legítima**: el usuario puede configurar Prowlarr/indexers y sus
   clientes; ZascArr no necesita conocer este sitio.

## 5. Qué haría falta para reconsiderarlo

- Autorización/licencia escrita del titular o contenido propio.
- Términos de uso que permitan expresamente el acceso automatizado y la caché local.
- API estable o contrato de scraping; rate limit y `User-Agent` identificable.
- Diseño **opt-in**, desactivado por defecto, sin URL hardcodeada, sin enlaces de descarga
  en la UI y con la misma puerta legal que las descargas actuales.
- Revisión de `LEGAL.md` y del PO antes de escribir código.

## 6. PASS / FAIL / NOT RUN

- **PASS (observación):** el sitio es una biblioteca de descarga gratuita con 173k libros,
  navegación por categorías/autores y buscador; `robots.txt` permite rastreo; no se
  localizaron términos/DMCA en las rutas comprobadas.
- **FAIL (como fuente ZascArr):** sin licencia/términos, sin API y con descarga directa;
  no cumple la política del proyecto.
- **NOT RUN:** descarga de archivos, inspección de enlaces de descarga, cuentas, API,
  navegador real y validación móvil. No se ha copiado contenido ni código del sitio.
