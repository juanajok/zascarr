# Especificación — BL-C5 (#160): catálogo OPDS 1.2 de solo catálogo

> **Estado: implementado en la rebanada de #160.** Sin migración ni dependencias
> nuevas. Este documento fija el contrato y las decisiones; cualquier ampliación
> (descarga, adquisición, escritura, búsqueda) exige otra historia.

## 1. Alcance

ZascArr publica **solo el catálogo** de su biblioteca como OPDS 1.2 (Atom). Un
cliente de e-reader/tableta (KOReader, Moon+, Calibre) puede navegar por las
series, sus tradiciones y editoriales y por los números de cada serie. **No hay
enlaces de descarga ni de adquisición**, ni rutas de archivo, ni hashes, ni
contenido de los CBZ/CBR.

Es una vista de lectura: no escribe en la BD, no mueve archivos, no lanza el
importador ni toca la biblioteca. La autenticación es la misma del resto de
ZascArr cuando `auth_mode` está activo.

## 2. Estado actual reutilizado

- `services/auth.py::intentar_credenciales` ya valida usuario/contraseña con
  retraso progresivo, cola acotada (`ColaDeVerificacionLlenaError` → 429) y
  caché de aciertos de Basic (`_basic_auth_valido`). El middleware
  `AuthMiddleware` ya trata `/api/*` como zona Basic y bloquea `/ui/*` sin
  redirección a `/login` solo cuando corresponde; con `auth_mode="none"` no
  exige credenciales y aplica la comprobación de Host existente.
- `Series`, `Issue`, `Creator`/`IssueCreator` y `Publisher` son la fuente del
  catálogo; `sort_title` puede ser NULL (por eso el orden alfabético cae a
  `title_norm`, igual que en Biblioteca).
- Los clientes OPDS **no tienen cookies** y muchos no siguen una redirección
  a HTML. Por eso `/opds/*` nunca responde `303` a `/login`.

## 3. Endpoints

Todos son `GET`, sin cuerpo de entrada, y devuelven
`application/atom+xml;profile=opds-catalog;kind=navigation`.

| Ruta | Contenido |
|---|---|
| `/opds` | Raíz de navegación: «Todas las series», «Por tradición», «Por editorial». |
| `/opds/series?page=N&tradition=…&publisher_id=…` | Series paginadas (50 por página), con título, autores si hay créditos, actualizado, resumen, tradición y enlace `alternate` a la ficha HTML. |
| `/opds/series/{uuid}` | Ficha de navegación de una serie y sus números (título/número/fecha). Sin archivos. |
| `/opds/tradiciones` | Valores de tradición presentes en el catálogo, enlazando a `/opds/series?tradition=…`. |
| `/opds/editoriales` | Editoriales presentes, enlazando a `/opds/series?publisher_id=…`. |

Filtros: solo `tradition` y `publisher_id` en `/opds/series`. No se amplía el
filtrado en esta historia. `page` fuera de rango devuelve un feed vacío con sus
enlaces, nunca un 500.

## 4. XML y semántica Atom/OPDS

Cada feed lleva:

- `id` = URL canónica del feed (incluida la query de paginación/filtros).
- `title`, `updated` (máximo `updated_at` de las filas que lo componen; epoch
  fijo si no hay filas).
- `link rel="self"` a la URL exacta, `rel="start"` a `/opds`, `rel="up"` al
  nivel padre cuando exista. Las entradas de navegación usan
  `rel="subsection"`.
- Entradas de navegación sin `rel` de adquisición/descarga. Las entradas de
  serie llevan `alternate` a `/ui/series/{id}`; los números enlazan a la ficha
  HTML de su serie.
- `author/name` solo cuando hay créditos de guionista; `summary` desde
  `description` o el sinopsis del número; `category term`/`label` con la
  tradición; `dc:issued`/fecha en los números cuando existe.

El XML se construye con `xml.etree.ElementTree`, nunca concatenando cadenas, de
modo que títulos con `& < > " '` quedan escapados por el serializador.

## 5. Autenticación

- Con `auth_mode="none"`: igual que el resto de la app, sin credenciales.
- Con `auth_mode` activo: `/opds` y `/opds/*` son **zona Basic**, como `/api/*`.
  El middleware reutiliza `_basic_auth_valido` (que a su vez usa
  `intentar_credenciales` con su retraso/caché/cola).
- Sin credenciales válidas: `401` con
  `WWW-Authenticate: Basic realm="ZascArr"`, `Cache-Control: no-store` y un
  cuerpo de texto pequeño; **nunca** `303` a `/login`. Credenciales malas
  conservan el retraso progresivo y el `429` existentes.
- No se añaden exenciones nuevas: `/opds` no está en `_RUTAS_EXENTAS`.

## 6. Caché y ETag

- `ETag` = hash de la versión del formato + `updated` máximo + ruta/query
  normalizada. Es estable entre peticiones mientras no cambie el catálogo.
- Si `If-None-Match` coincide → `304`, sin cuerpo.
- `Cache-Control: private, max-age=300` en respuestas de catálogo (200/304).
- Las respuestas 401 llevan `Cache-Control: no-store`.

## 7. Paginación

- Tamaño fijo 50.
- `next`/`previous` conservan los filtros mediante query string.
- Página 1 sin anterior; última sin siguiente. Página fuera de rango: feed
  vacío con `self`, `start`, `up` y `previous` si aplica.
- `page` no numérico se interpreta como página 1 (no se devuelve HTML de
  error). Valores de filtro inválidos devuelven un error XML 400 pequeño.

## 8. Errores

| Caso | Respuesta |
|---|---|
| Serie inexistente o UUID inválido | `404` XML pequeño (`application/xml`), sin HTML. |
| Tradición o editorial inválida | `400` XML pequeño. |
| Sin credenciales / credenciales malas | `401` texto pequeño + `WWW-Authenticate`, nunca redirección. |
| Cola de PBKDF2 llena | `429` existente, sin redirección. |
| BD degradada | `503`; no se sirve un feed que parezca válido. |

## 9. Privacidad y seguridad

- No se publican rutas de archivo, nombres de archivo, hashes ni `File`.
- Los IDs internos solo aparecen donde son la URL de navegación OPDS
  (`/opds/series/{uuid}`); no se exponen en texto.
- No se sirven portadas ni binarios en esta historia: un feed es solo
  metadatos de catálogo.
- No hay escritura, migración, ni dependencias nuevas; no se toca
  `web/ajustes.py` ni `services/seguridad.py`.

## 10. Riesgos y decisiones

- **No adquisición:** algunos clientes esperan `acquisition`; aquí no existe a
  propósito. Es un catálogo de navegación, no una tienda ni un servidor de
  descargas. La descarga es una decisión posterior.
- **Autores:** se muestran guionistas con créditos (`IssueCreator`); no se
  inventan autores ni se consultan fuentes externas.
- **Actualización:** `updated` depende de las filas de catálogo; cambios solo
  en disco no cambian el feed hasta que el catálogo se actualice.
- **Complejidad del catálogo:** el orden alfabético usa
  `coalesce(sort_title, title_norm)` porque `sort_title` puede ser NULL en
  bibliotecas reales (#664).
- **Autenticación:** se reutiliza el middleware existente en vez de duplicar
  PBKDF2/retraso; así una credencial válida de OPDS comparte caché con `/api`.

## 11. Trazabilidad

- Historia #160 (BL-C5), AC de catálogo OPDS 1.2.
- `services/auth.py`, `services/series.py` (orden #664), modelos `Series`,
  `Issue`, `Creator`, `Publisher`.
- Tests: `tests/test_api_opds.py` y regresiones de auth.
