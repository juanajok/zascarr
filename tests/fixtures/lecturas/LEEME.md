# Fixtures de guías de lectura (SCR3, entrega 1)

Recortes **reales** de las dos fuentes, tomados en vivo el **2026-11-13** (verificación de la
spec `docs/design/especificacion-SCR3-lecturas.md`, §1) y recortados a la estructura que leen
los extractores. La prosa del autor se ha sustituido por `PROSA_DE_PRUEBA` (o se ha eliminado)
para no almacenar contenido de terceros: estos fixtures solo conservan clases, anidamiento y
los textos fácticos (serie, número, año, sección). No hay `?format=json` en ninguna petición.

| Fichero | Origen | Qué conserva |
|---|---|---|
| `cbro_guia.html` | `https://comicbookreadingorders.com/dc/events/crisis-on-infinite-earths-reading-order/` (200, HTML clásico) | `main > h1`, `ol.issues` con 2 secciones (`li > h2`), 11 `li.issue` (uno sin `a.read-link`), 1 `li.aside.note-row` de prosa y `label.check` que se ignora; año del número en `span.year` en 3 ítems |
| `cbro_sitemap.xml` | `https://comicbookreadingorders.com/sitemap.xml` (200, `urlset` con `lastmod`) | 10 `<loc>`: 7 guías válidas (eventos/personajes de DC y Marvel) y 3 rutas que se descartan; namespaces reales |
| `continuity_planetx.html` | `https://www.continuityguide.net/planetx` (200, Squarespace sin `h1/h2`) | 7 `div.image-card` en orden DOM con `p` de `.image-subtitle` (6 con `#`), títulos de arco entre comillas que se descartan y 2 `p` con `#` **fuera** de tarjeta que se excluyen |
| `continuity_sitemap.xml` | `https://www.continuityguide.net/sitemap.xml` (200, `urlset` con páginas e imágenes) | 8 páginas + 3 imágenes de `images.squarespace-cdn.com` que se filtran; 2 `<lastmod>` |

**Caducidad:** revisar en la primera ejecución contra las fuentes vivas o el 2027-01-12 (lo
antes que pase). Si la maqueta cambia, los tests fallarán en el recorte, que es exactamente lo
que se quiere detectar.
