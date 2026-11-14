# Informe QA — SCR7: relleno de huecos con GCD, Metron y Open Library (2026-11-14)

**Rol:** QA · **Tarea:** task-46 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr7-huecos`
**Rama:** `feat/scr7-huecos`, SHA **`b61af493737dfa96a9ae8933cded06426ef4bbd7`** (verificado con
`git rev-parse HEAD`; PR #838 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL`.
El único fichero escrito es este informe; el scratch de QA (`.qa-scr7/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7088 passed, 2286 skipped**, 4 warnings, 0 fallos | 522,00 s (wall 8:42) |
| `pytest -q` (suite completa, 2.ª pasada) | **7088 passed, 2286 skipped**, 4 warnings, 0 fallos | 543,75 s (wall 9:03) |
| `pytest -q` suites tocadas (relleno, enricher, clientes, health, legal, ficha) | **287 passed** | 20,49 s (wall 22,55 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
contaminación entre pruebas. Los 2286 skips son los esperados sin `TEST_DATABASE_URL` (pruebas
`*_pg`). Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en
importer), ajenos a SCR7.

---

## 2. Reproducción independiente — **20/20 OK**

Además de las pruebas del builder, escribí una sonda propia con `SimpleNamespace` para series,
fichas reales (`GCDSerie`, `MetronResult`, `OpenLibraryResult`), una sesión falsa que captura la
consulta, clientes contadores y `httpx.MockTransport` para los tres clientes:

* **AC-01/02/03** `aplicar_relleno` rellena solo la lista cerrada de cada fuente (GCD años;
  Metron descripción+años; OL descripción+año) y **no** toca `title`, ids, `metadata_source`,
  `cover_url`, `total_issues` ni `description` ya presente.
* **AC-04** campos llenos y `locked_fields` no se pisas; una ficha con `title`/`cover_url`/
  `total_issues`/`metadata_source` falsos no cambia nada.
* **AC-05** `ficha=None` registra `metadata_["relleno"][fuente]["campos"]=[]` con
  `ultimo_intento` y TTL vigente a 29 días / vencido a 31; un cuerpo normal también deja su TTL.
* **AC-05/06** un fallo transitorio (`ErrorDePeticion`) **corta la fuente** en el ciclo, no deja
  `relleno` (no TTL) y se reintenta; un 404 no vuelve a pedirse en la segunda pasada; tras rellenar,
  la segunda pasada no hace peticiones ni cambios (idempotencia).
* **AC-07** orden Metron→Open Library→GCD y parada al cubrir los huecos; 8 series con solo GCD ⇒
  **5 peticiones** (tope por fuente/ciclo); tradición `manga` no consulta GCD/Metron.
* **AC-08** sin clientes no se ejecuta la consulta a la BD; fuentes apagadas o Metron sin token
  devuelven `None` sin instanciar clientes (`enter_async_context` 0 veces).
* **Clientes reales** por `MockTransport`: GCD `GET /api/series/{id}/` (200, 404→None,
  429→`ReintentosAgotados` transitorio), Open Library `GET /works/OL1W.json` con
  `description.value` y `first_publish_year`; sin búsqueda por título.
* **AC-11** `puede_enlazarse_con_comic_vine` rechaza series con `metron_id` u
  `open_library_id`; el `select` del primario añade los dos `is_(None)` (estático).
* **AC-09** `atribucion_de_relleno` solo devuelve fuentes con `campos` y URL de ficha https del
  host esperado (Metron CC BY-SA 4.0, OL con su página de licencia; URL http/ajena se descarta);
  la plantilla pinta el bloque **fuera** del `<details>` de Fuentes; `LEGAL.md` tiene las filas de
  Metron y Open Library y su hash cambia (`d2b2983f…` → `8ba20a23…`, calculado con sha256 del
  fichero anterior/actual).
* **AC-10** health lista `metron` y `open_library` (comprobado en el código y en `test_health.py`).

---

## 3. Aceptación (12 AC de la spec)

* **AC-01…AC-04 (solo huecos, nunca pisa).** `aplicar_relleno` (`relleno_huecos.py:104-131`)
  recorre la lista cerrada `CAMPOS_POR_FUENTE` (`:21`), salta `locked_fields` y campos no vacíos,
  y escribe con `setattr` solo esos campos; `CAMPOS_PROHIBIDOS` (`:47`) añade defensa en
  profundidad. `_registrar` crea un **dict nuevo** para `metadata_` (JSONB).
* **AC-05/06 (TTL, transitorio, idempotencia).** `aplicar_relleno(None)` registra la negativa de
  30 días (`TTL_RELLENO`, `:28`; `ttl_vigente`, `:134-149`). En `_enrich_huecos_por_id`
  (`enricher.py:379-448`) los `ErrorDePeticion`/`httpx.HTTPError`/`RuntimeError` se capturan antes
  de `aplicar_relleno`, marcan la fuente como cortada y **no** escriben TTL; la siguiente pasada
  reintenta. Idempotente por TTL y por `campos_faltantes`.
* **AC-07 (orden y límites).** `FUENTES_CON_RELLENO = ("metron","open_library","gcd")`; `limit`
  de la consulta; `MAX_PETICIONES_FUENTE_POR_CICLO=5`; `TRADICIONES_DE_FUENTE` restringe Metron
  (`american`/`fumetti`) y GCD (`american`/`british`); OL no depende de tradición; una fuente
  cortada no se vuelve a consultar en el ciclo.
* **AC-08 (apagadas/sin token = cero red).** `_cliente_metron` exige `metron_enabled` **y**
  `metron_token` no vacío; GCD/OL exigen su flag; si no, devuelven `None` sin instanciar el
  cliente. Si no hay ningún cliente, `_enrich_huecos_por_id` retorna antes de consultar la BD.
* **Clientes por id (AC-01/02/03/05/07).** `GCDClient.get_series_por_id` (`gcd.py:265`),
  `MetronClient.get_series_por_id` (`metron.py:161`) y `OpenLibraryClient.get_work`
  (`open_library.py:122`) piden la ficha por id exacto; 404 ⇒ `None`; 429/red ⇒ excepción para
  que el enricher corte sin TTL. No hay llamadas a `search`/`get_series` por título.
* **AC-11 (identidad del primario).** `puede_enlazarse_con_comic_vine` añade `metron_id` y
  `open_library_id` a las exclusiones (`enricher.py:221-229`) y el `select` del lote primario
  añade `.where(Series.metron_id.is_(None))` / `.where(Series.open_library_id.is_(None))`
  (`:575-576`).
* **AC-09 (atribución/LEGAL).** `FUENTES_DE_RELLENO` (`atribucion.py:30-37`) define nombre, host,
  licencia y URL de licencia; `atribucion_de_relleno` (`:53-76`) valida https/host y solo incluye
  fuentes con `campos`; `series_detail.html` pinta el bloque fuera del desplegable; `LEGAL.md`
  añade ambas filas y el hash de aceptación cambia automáticamente
  (`services/legal.py::current_legal_version`).
* **AC-10 (health).** `api/health.py:470-473` añade `metron` y `open_library` a `fuentes`
  (apagadas por defecto); `test_health.py` lo comprueba.

**AC-12 (sin migraciones ni cambios en `models`; suites verdes).** El diff son 15 ficheros
(**+872/−12**), ninguno de
`models/` ni `alembic/`: `LEGAL.md`, `api/health.py`, cuatro servicios, `relleno_huecos.py` nuevo,
`web/atribucion.py`, `web/series.py`, tres plantillas y tres ficheros de pruebas
(`test_relleno_huecos.py` nuevo, `test_health.py`, `test_web_series.py`).

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — Posible inanición del lote (limitación de selección).** La consulta selecciona series con
algún hueco (`description`/`start_year`/`end_year`) aunque ese hueco no lo pueda cubrir ninguna
fuente con id (p. ej. solo `open_library_id` y falta `end_year`, que OL no rellena) o esté en
`locked_fields`; esas filas se quedan en el `limit` ordenado por `id` y, si hay más que el lote,
pueden no dejar sitio a filas posteriores con huecos sí cubribles. No incumple ningún AC (solo
rellena huecos y no pisa), pero conviene filtrar por «hueco cubrible» o excluir `locked_fields` en
la consulta en una tarea posterior.

**O2 — `MetronClient.get_series_por_id` con JSON `{}`** devuelve un `MetronResult` vacío en vez de
`None`; el efecto práctico es el mismo (se registra TTL con `campos=[]`), pero la simetría con GCD/OL
sería más clara devolviendo `None`.

**O3 — La atribución exige URL de ficha válida.** Si la API devolviera un `site_url` con host/esquema
inesperado, `atribucion_de_relleno` omite ese aviso (defensa), aunque el dato se haya rellenado; es
el comportamiento declarado en el helper.

**O4 — El TTL también se marca tras un relleno exitoso**, no solo tras 404: no se vuelve a consultar
la fuente en 30 días aunque queden huecos que esa fuente podría cubrir más adelante. Es lo que pide
la spec («1 petición por fuente y serie y ciclo», caché de 30 días) y evita quemar cuota.

---

## 5. Veredicto

**APTO.** SCR7 cumple los 12 AC: suite completa verde **dos veces** con contadores idénticos
(7088 passed / 2286 skipped, 0 fallos), suites tocadas verdes (287 passed) y `ruff check src/`
limpio. El relleno solo escribe la lista cerrada de campos vacíos y no pisa `locked_fields` ni
`title`/ids/`metadata_source`/`cover_url`/`total_issues`; el 404/vacío deja TTL de 30 días y el
fallo transitorio no lo deja (se reintenta); es idempotente; respeta el orden Metron→Open
Library→GCD, las tradiciones y el tope de 5 peticiones por fuente/ciclo; una fuente apagada o
Metron sin token no instancia cliente ni hace red; el primario excluye series identificadas por
Metron/OL; la atribución (Metron CC BY-SA 4.0 y Open Library) se ve fuera del desplegable, health
lista las dos fuentes y `LEGAL.md` cambia de hash; sin migraciones ni cambios en `models`.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 posible inanición del lote (filas con
huecos no cubribles o bloqueados siguen entrando en el `limit` ordenado por id), O2 Metron con JSON
`{}` devuelve un `MetronResult` vacío en vez de `None` (el efecto —TTL con `campos=[]`— es el
mismo), O3 la atribución exige URL de ficha válida y omite el aviso si el `site_url` no pasa la
validación, y O4 el TTL también se marca tras un relleno exitoso (no se reconsulta en 30 días,
como pide la spec).

---

## 6. Comandos reproducibles

```
cd .worktrees/scr7-huecos
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_relleno_huecos.py tests/test_enricher.py \
    tests/test_enricher_identidad.py tests/test_gcd_cortesia.py tests/test_gcd_idioma_464.py \
    tests/test_gcd_paginar_523.py tests/test_gcd_year_errors_526.py tests/test_fix_qa_gcd_526.py \
    tests/test_clientes_cortesia.py tests/test_clientes_fuente_apagada.py \
    tests/test_discovery_metron_openlibrary.py tests/test_fuentes_metron_openlibrary.py \
    tests/test_health.py tests/test_legal.py tests/test_web_series.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-scr7/probe.py      # 20/20 OK
```

---

## 7. Inventario del cambio revisado (`b61af493`)

15 ficheros, **+872 / −12**: `src/zascarr/LEGAL.md`, `src/zascarr/api/health.py`,
`src/zascarr/services/{enricher,gcd,metron,open_library,relleno_huecos}.py`,
`src/zascarr/web/{atribucion,series}.py`,
`src/zascarr/web/templates/{_legal_disclaimer,ajustes,series_detail}.html` y
`tests/{test_health,test_relleno_huecos,test_web_series}.py`. Sin `models/` ni `alembic/`.
