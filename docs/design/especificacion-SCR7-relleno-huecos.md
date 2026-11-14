# SPEC: relleno de huecos con GCD, Metron y Open Library (SCR7, #736) — v0.1

> **Estado:** especificación implementable (P2, M), sin código ni commits. **Base:** `origin/main` `d9adf361` (el `main` local está 168
> commits por detrás: el código se leyó con `git show origin/main:…`). **Sin migraciones ni cambios en `models`**: las columnas
> `gcd_id`/`metron_id`/`open_library_id` ya existen (`models/__init__.py:585-592`) y la procedencia cabe en `metadata_` (JSONB).
> **Contexto:** el PO aceptó el **ADR 0018** y pidió arrancar SCR7; ADR 0002 cerraba el enricher en CV/AniList/Tebeosfera. Se entrega
> **ADR 0019** (`docs/adr/0019-relleno-de-huecos-enricher-secundario.md`) y, en el mismo PR, se actualiza el estado de ADR 0018 a
> **Aceptado** (hoy el documento aún dice «Propuesto»).

## 0. Estado real (qué hay y qué falta)

| Pieza | Estado hoy (fichero:línea) | Falta |
|---|---|---|
| Clientes | GCD/Metron/OL solo se usan en Descubrir: `gcd.get_series` (`services/gcd.py:224-260`), `metron.get_series` (`:160-177`), OL solo `search_works` (`services/open_library.py:117-146`) | OL no tiene lectura por obra; nadie los llama desde el enricher |
| Identidad | `Series.gcd_id`/`metron_id`/`open_library_id` existen y el alta las escribe (`services/alta_serie.py:453-463`); el primario **excluye** solo `gcd_id` y los ids de CV/AniList/Tebeosfera/Fandom (`enricher.py:456-465`), pero **no** `metron_id`/`open_library_id` | Rellenar huecos **y** impedir que el primario reclame identidad CV/Fandom de una serie ya identificada por Metron/OL |
| Campos del primario | `_apply_series_match` rellena descripción/portada/total/años sin pisar (`enricher.py:605-626`); `metadata_source == manual` excluido | Mismo patrón, pero por ID y sin cambiar identidad |
| Procedencia/atribución | `web/atribucion.py` solo cubre Fandom; `series_detail.html:65-69` pinta su aviso | GCD/Metron/OL sin atribución al rellenar |
| `LEGAL.md` | GCD tiene fila (`:107`); **Metron y Open Library no tienen fila** | Añadirlas y actualizar la nota de metadatos |
| Health | `api/health.py:464+` lista CV/AniList/Tebeosfera/GCD/Fandom/guías | Metron y Open Library (que ahora enriquecen) |
| Ajustes | Los textos dicen «Metron y Open Library solo se usan en Descubrir» (`templates/ajustes.html:35,39,121`) | Texto coherente; sin tocar `web/ajustes.py` |

## 1. Paso (a) — relleno por ID (contrato cerrado)

Módulo nuevo `services/relleno_huecos.py` (lógica pura + orquestación de una serie). Función pura
`aplicar_relleno(serie, fuente, ficha, ahora) -> list[str]`: rellena **solo campos vacíos** (`None` o `""`) y **nunca** campos en
`locked_fields`; **no toca** `title`, ningún `*_id`, `metadata_source`, `cover_url` ni `total_issues`; devuelve los campos rellenados.
Lista **cerrada** (lo demás se ignora aunque la API lo traiga):

| Fuente (solo con su id ya guardado) | Campos que puede rellenar | Dato de la fuente |
|---|---|---|
| **GCD** (`gcd_id`; tradición `american`/`british`) | `start_year`, `end_year` | `year_began`, `year_ended` (`GCDSerie`) |
| **Metron** (`metron_id`; token; tradición `american`/`fumetti`) | `description`, `start_year`, `end_year` | `descripcion`, `year_began`, `year_ended` (`MetronResult`) |
| **Open Library** (`open_library_id`; obra/tomo) | `description`, `start_year` | `description` de la obra y `first_publish_year` (`get_work` nuevo) |

Por qué se excluye el resto: GCD no da sinopsis ni portada por su API de series (ADR 0002, actualización 2026-09-25); Metron no cubre
portadas por licencia; `publisher` exigiría crear/emparejar filas `Publisher` (decisión de producto ajena) y `total_issues` de GCD/
Metron no está acreditado como unidad de grapa (BACKLOG #13). Open Library **nunca** es una grapa: si no hay `open_library_id`, no se consulta.

Comportamiento: 1 petición por fuente y serie y ciclo, por ID exacto (`/series/{id}/` de GCD, `/series/{id}/` de Metron,
`/works/{OL…W}.json` de Open Library); **sin búsqueda por título** (no reclama identidad ni quema la cuota de 30/h de GCD).
`HTTP 404`/respuesta vacía ⇒ `metadata_["relleno"][fuente]["campos"]=[]` y `ultimo_intento`; rate-limit/red/token ausente ⇒ **sin
cambios, sin borrar** y sin marcar el TTL de 30 días (se reintenta en el siguiente ciclo). Guardar `metadata_["relleno"]` con
`{fuente: {"id": str, "campos": [...], "ultimo_intento": ISO, "url_ficha": str|None}}` asignando un **dict nuevo** (SQLAlchemy no
detecta mutaciones in-place de JSONB). Si `ultimo_intento` tiene menos de 30 días, esa fuente no se vuelve a pedir (idempotencia y
caché negativa propia, independiente de `enrichment_attempted_at`). `metadata_source` queda **byte a byte igual**.

## 2. Paso (b) — enricher secundario de huecos (orden, límites, cortesía)

Además, el primario debe excluir también `metron_id` y `open_library_id` en su consulta (hoy solo excluye `gcd_id` y el resto):
una serie identificada por Metron/OL no puede recibir por título una identidad CV/Fandom ni cambiar `metadata_source`.
Tras el primario `_enrich_series_batch` (`enricher.py:430+`) y **solo si quedan huecos**, `enrich_pending` llama a
`_enrich_huecos_por_id(limit, report)`: selecciona series con `metadata_source != manual`, al menos un id de las tres fuentes y algún
hueco entre `description/start_year/end_year` (no exige `enrichment_attempted_at`; no lo modifica), ordenadas por `id`, como mucho
`limit`. Por serie, en este orden: **Metron → Open Library → GCD** (GCD el último, «último recurso factual»), parando en cuanto no
queden huecos que esa fuente pueda cubrir.

| Fuente | Se consulta si… | Cortesía |
|---|---|---|
| Metron | `metron_id` + `metron_token` no vacío + `metron_enabled` + tradición `american`/`fumetti` | `politica_de("metron")`: 3 s ≈ 20/min, 2 intentos |
| Open Library | `open_library_id` + `open_library_enabled` (obra/tomo por construcción) | `politica_de("open_library")`: 1 s, 2 intentos |
| GCD | `gcd_id` + `gcd_enabled` + tradición `american`/`british` | `politica_de("gcd")`: 2 s, 2 intentos |

Fuente apagada ⇒ ni cliente ni petición (patrón B8; cero red). Token ausente ⇒ no se consulta Metron. Tope por ciclo y fuente:
`MAX_PETICIONES_FUENTE = 5` (protege la cuota anónima de GCD y el 20/min de Metron); un fallo transitorio (rate-limit/red) corta
esa fuente para el resto del ciclo sin marcar TTL. `EnrichmentReport` añade `series_rellenadas: list[str]` (en memoria, sin modelo) y
el ciclo registra `enricher.huecos_rellenados` con fuente/campos (sin URL ni valores). Errores de una fuente no impiden las demás.

## 3. UI, licencias y salud

- **Atribución**: `web/atribucion.py` añade `atribucion_de_relleno(series) -> list[dict]` a partir de `metadata_["relleno"]` (solo
  fuentes con `campos` no vacíos): enlace a la ficha (GCD `https://www.comics.org/series/{id}/`; Metron `url_ficha` guardada; OL
  `https://openlibrary.org/works/{id}`), nombre y licencia (GCD/Metron **CC BY-SA 4.0**, enlace a
  `https://creativecommons.org/licenses/by-sa/4.0/`; Open Library, enlace a su ficha y a su página de licencias). `series_detail`
  pinta ese aviso **visible sin desplegar** «Fuentes y atribución» (mismo criterio que m-1 de SCR2) y actualiza la nota
  `legal_disclaimer("metadata")`. **Nunca** se muestra una portada de Metron.
- **`LEGAL.md`**: filas de Metron (CC BY-SA 4.0, token, 20/min, sin portadas) y Open Library (datos de Internet Archive, enlace a la
  obra, sin portadas en el relleno; documentar su licencia vigente al redactar la fila); actualizar la fila del enricher y la nota de
  metadatos. El hash de `services/legal.py` versiona la aceptación solo.
- **`api/health.py`**: añadir `metron` y `open_library` a `fuentes` (apagadas por defecto), con prueba.
- **Ajustes**: actualizar los textos de `templates/ajustes.html:35,39,121` («también rellena huecos vacíos»); **no** se toca
  `web/ajustes.py`, contraseña/sesión ni la whitelist.

## 4. Criterios de aceptación medibles

| # | Criterio | Verificación |
|---|---|---|
| AC-01 | Serie con huecos y `gcd_id`: GCD `year_began/year_ended` rellenan **solo** `start_year`/`end_year`; título, ids, `metadata_source`, `cover_url`, `total_issues` intactos | unitario `aplicar_relleno` + MockTransport |
| AC-02 | Metron rellena `description`/años solo si vacíos; nunca portada ni título; id/token/tradición respetados | unitario + cliente simulado |
| AC-03 | Open Library rellena `description`/`start_year` desde la obra; sin `open_library_id` **no hay petición** | nuevo `get_work` + MockTransport |
| AC-04 | Campos ya rellenos o en `locked_fields` no se tocan; `metadata_source` no cambia; nunca se escribe `title`/ids | unitario con todos los campos llenos y con locks |
| AC-05 | 404/vacío ⇒ sin cambios, `campos=[]` y TTL 30 d; rate-limit/red/token ausente ⇒ sin cambios y **sin** TTL | MockTransport con 404/429/red |
| AC-06 | Idempotente: segunda pasada = 0 peticiones (huecos llenos o TTL); el `metadata_` no se duplica | dos ejecuciones con contador |
| AC-07 | Orden y límites: Metron→OL→GCD, se para al no quedar huecos, GCD solo `american`/`british`, Metron solo `american`/`fumetti`, OL solo con id de obra | unitario con ids múltiples y tradiciones |
| AC-08 | Fuentes apagadas ⇒ **cero** peticiones (ninguna instancia); Metron sin token ⇒ cero peticiones | flags a `False` + doble que registra llamadas |
| AC-09 | `LEGAL.md` con filas de Metron/OL; nota de metadatos y atribución visibles en la ficha (con enlaces y licencia); sin portada Metron | `TestClient` sobre la ficha + lectura de LEGAL |
| AC-10 | `api/health.fuentes` incluye `metron` y `open_library` | `tests/test_health.py` |
| AC-11 | El primario no selecciona series con `metron_id`/`open_library_id` (no reclama identidad CV/Fandom por título) | prueba de selección con `FakeSession` + estas columnas rellenas |
| AC-12 | Sin migraciones ni cambios en `models`; `tests/test_health.py`, `test_fandom.py` y la suite de Ajustes siguen verdes | ejecución completa por QA |

## 5. Plan de pruebas sin red

`tests/test_relleno_huecos.py` (puro, AC-01…07): fichas sintéticas de `GCDSerie`/`MetronResult`/obra OL y series con huecos;
`aplicar_relleno` no debe importar `httpx`. `tests/test_enricher_huecos.py` (AC-01…08 y AC-11) con `FakeSession`, clientes inyectados
(`_injected_gcd`/`_injected_metron`/`_injected_open_library`) y `MockTransport` con contador de URLs (assert de `/series/ID/` y
`/works/ID.json`, ninguna búsqueda por título). `tests/test_web_atribucion_relleno.py` (AC-09) con `TestClient` y una serie cuyo
`metadata_` simula relleno; `tests/test_health.py` (AC-10). Cero red y sin `TEST_DATABASE_URL`.

## 6. Riesgos y límites

- **GCD: cuota anónima de 30/h** (sin cifra publicada): por eso solo por ID, tope 5/ciclo y sin búsqueda por título; si se agota,
  `ReintentosAgotados` corta la fuente en el ciclo y no se marca TTL.
- **Descripciones**: las de Metron/OL son texto creativo de la fuente; CC BY-SA 4.0 (Metron) y la licencia de Open Library obligan a
  atribución visible (AC-09). `LEGAL.md` §7.1 sigue mandando: eso **no** se copia al `ComicInfo.xml`; aquí solo se muestra en la ficha.
- **Identidad**: no se escribe ningún id ni `metadata_source`; si el usuario cambia de opinión sobre el id, el relleno no la reclama.
- **JSONB**: toda escritura de `metadata_` se hace con dict nuevo; una mutación in-place se pierde y rompería la idempotencia.
- **Metron** exige token y solo EN/IT; sin token el hueco queda y no es un error. **Open Library** no sirve para grapas: una serie
  con `open_library_id` es obra/tomo y su `description` puede ser de la edición, no de la serie.
- **No hay búsqueda por título** en esta entrega (evita ambigüedad, identidad y cuota). Si el PO la quiere, es otra decisión (revisar
  ADR 0019), no un añadido silencioso.
- Atribución: una fila nueva en `LEGAL.md` cambia `current_legal_version()` (re-aceptación); es el comportamiento previsto.

## 7. Cortes para el builder

| Corte | Contenido | Est. |
|---|---|---|
| 1 | Clientes: `OpenLibraryClient.get_work` + `services/relleno_huecos.py` (mapa cerrado, `aplicar_relleno`) + pruebas puras | 0,5–1 d |
| 2 | Enricher secundario (selección, orden, límites, TTL en `metadata_`, report) + pruebas con clientes inyectados | 0,5–1 d |
| 3 | Atribución/UI, `LEGAL.md`, `health`, textos de Ajustes, ADR 0019 y actualización de ADR 0018 + pruebas | 0,5 d |

Sin migraciones ni `models`. Una historia = una PR, un commit por corte; el corte 3 incluye la documentación legal que no puede ir
separada del código que muestra los datos.

## 8. Trazabilidad

SCR7 (#736) → §1 (relleno por ID), §2 (enricher secundario), §3 (atribución/legal). ADR 0002 (enricher cerrado en CV/AniList/
Tebeosfera; GCD solo Descubrir) y ADR 0018 (aceptado) → ADR 0019, que fija la política de huecos y el orden. AC-01…12 cubren «solo
huecos, nunca pisa, no cambia identidad, idempotencia, límites por tradición, apagadas = cero red, atribución». Backlog fila SCR7
actualizada en el mismo PR.
