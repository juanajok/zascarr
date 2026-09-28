# Ficha E7 — qué expone de verdad la API de GCD (evaluación, solo lectura)

**Estado:** evaluación hecha (2026-09-28). **No** integra GCD en el enricher.
**Método:** peticiones de lectura contra `https://www.comics.org/api/` con
`Accept: application/json` y un `User-Agent` propio; `issue_count`, `variant_of`
y `cover` **observados** en las respuestas, no inferidos del serializador ni de
la web. Los IDs y valores citados son reproducibles con esas mismas llamadas.

## 1. Edición identificada — la API SÍ distingue ediciones

`GET /series/name/Absolute Batman/` devuelve 30 resultados, separables por
`language`/`country`/`publisher`:

| Edición | Serie | `language`/`country` | `publisher` | `publishing_format`/`binding` |
|---|---|---|---|---|
| Panini España (la que interesa) | **224764** | `es`/`es` | `publisher/3932` = **Panini España** | `serie regular` / `grapa`, 17×26 cm |
| DC, grapa USA | **216143** | `en`/`us` | `publisher/54` (DC) | `ongoing series` / `saddle-stitched` |
| DC, recopilatorios 2025 | 226632/226633 | `en`/`us` | `publisher/54` | `collected edition` / hardcover y TPB |

**Decisión:** la API basta para **identificar la edición** (idioma, país,
editorial, formato). Es la capacidad que mejor se sostiene.

## 2. Números catalogados — hay registros, NO un recuento fiable

Lo que **no** existe: **ningún campo `issue_count`** en la respuesta de serie
(es `None` tanto en la búsqueda como en el detalle, pese a existir en el modelo
Django interno). Lo que sí hay: `active_issues` (lista de URLs de issue) y
`issue_descriptors` (lista de cadenas).

Medido:

| Serie | `active_issues` | descripciones | sin `[` (base) | con `[` (variantes) |
|---|---|---|---|---|
| 236622 *Fall of the House of Slaughter* (miniserie de 4) | **37** | 37 | **3** (`1`,`2`,`4`) | 34 |
| 224764 *Absolute Batman* Panini (14 números) | 14 | 14 | 14 (`1`..`14`) | 0 |
| 216143 *Absolute Batman* DC (ongoing) | **284** | 284 | **0** | 284 |

Dos conclusiones que corrigen la expectativa:

- **Contar registros engaña**: la miniserie de 4 tiene **37** registros. Un
  contador así **no** es «total previsto» ni «números catalogados base».
- **El truco de las descripciones sin `[` no es fiable**: da 3 en la
  miniserie (y **falta el `3` base**), 14 en la edición española, y **0** en la
  serie USA (todas sus descripciones llevan corchete). No se puede derivar el
  recuento base de ahí.
- La señal **fiable** es el campo por número **`variant_of`**: `None` en el
  número base, y la URL del base en cada variante (verificado: el `1` base de
  236622 tiene `variant_of=null`; sus variantes apuntan a
  `/issue/2832392/`). Pero exige **pedir cada número** (284 peticiones en la
  serie USA a 2 s/petición ≈ 10 min) — no es un recuento barato.

**Decisión:** GCD sirve para **listar y distinguir números base de variantes**
con `variant_of`, a coste de N peticiones; **no** ofrece un recuento de
confianza y **ningún recuento pasa** a `Series.total_issues`.

## 3. Portadas — el campo existe, la imagen NO es usable directamente

El serializador de `Issue` expone `cover` con una URL real, p. ej. para el `#1`
de la edición española:
`https://files1.comics.org//img/gcd/covers_by_id/1812/w400/1812885.jpg`.

**Resultado observado (negativo):** esa URL devuelve **HTTP 403**. Probado con
UA propio, UA de navegador, cabecera `Referer: https://www.comics.org/` y la
URL sin la doble barra (`https://files1.comics.org/img/...`). No es, hoy,
recuperable como imagen desde este entorno. Que el campo exista **no** implica
que sea una fuente de imagen utilizable (era exactamente la hipótesis a
verificar).

Además, varios issues base de 236622 devuelven `cover=""` (vacío): ni siquiera
siempre hay URL.

**Uso/condiciones:** los datos de GCD son **CC BY-SA 4.0** (atribución + enlace
de vuelta).

**Decisión:** **no** usar `cover` de GCD como fuente de portada hasta resolver
el 403 (cookies/otro host/proxy) y confirmar términos; hoy queda como
**capacidad negativa**.

## 4. Huecos — nada que trasladar

La edición española existe y se identifica, pero sus registros de número son
**esqueléticos**: el `#1` de 224764 devuelve `publication_date`, `on_sale_date`,
`key_date`, `price`, `title` **vacíos** y `page_count=None` — solo número y
portada. Y sin recuento fiable (punto 2), GCD **no** acredita un universo
`1..N` para grapas.

**Decisión:** GCD **no** entra en el cálculo de huecos ni habilita C6. Fuente,
edición, unidad del recuento y fecha de observación seguirían sin estar
acreditadas.

## Resumen por capacidad

| Capacidad | Resultado observado | Decisión |
|---|---|---|
| **Serie / edición** | `language`, `country`, `publisher`, `publishing_format`, `binding` | ✅ aprovechable |
| **Números** | `active_issues` (URLs) + `variant_of` por número; sin `issue_count`; descripciones no fiables | ⚠️ listar/distinguir, no contar |
| **Portadas** | campo `cover` con URL, pero **403** al recuperarla | ❌ no usable hoy |
| **Huecos** | sin recuento acreditado; metadatos de número vacíos | ❌ fuera de C6 |

## Reproducible

```
GET /api/series/name/Absolute%20Batman/      -> 30 ediciones (es/es 224764; en/us 216143)
GET /api/series/224764/  GET /api/series/236622/  GET /api/series/216143/
GET /api/issue/<id>/                          -> number, variant_of, cover, ...
HEAD https://files1.comics.org//img/gcd/covers_by_id/1812/w400/1812885.jpg  -> 403
```
