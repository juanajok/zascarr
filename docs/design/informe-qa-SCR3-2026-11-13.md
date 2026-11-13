# Informe QA — SCR3: extractores de guías y resolver puro (2026-11-13)

**Rol:** QA · **Tarea:** task-19 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr3-lecturas`
**Rama:** `feat/scr3-lecturas`, HEAD **`df06c889`** (PR #765 según el encargo; no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2 + pytest-asyncio, ruff 0.17.5, lxml disponible).
Sin `TEST_DATABASE_URL`; SCR3 no necesita Postgres (no hay migraciones ni ORM nuevos).
El único fichero escrito es este informe; el scratch de QA (`.qa-scr3/`, logs y sonda) se borró.

> Nombre con **fecha real 2026-11-13** (la descripción de la tarea decía 11-14).

---

## 1. Regresión

| # | Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|---|
| 1 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6737 passed, 2275 skipped**, 4 warnings | 332,22 s (wall 5:35) |
| 2 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6737 passed, 2275 skipped**, 4 warnings | 353,79 s (wall 5:57) |
| 3 | `… pytest -q tests/test_reading_orders.py tests/test_reading_order_resolver.py` | **48 passed** | 1,20 s (wall 2,27 s) |

* Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
  contaminación entre pruebas. Los 2275 skips son los esperados sin `TEST_DATABASE_URL`
  (pruebas `tests/*_pg.py` y dependientes de entorno); SCR3 no aporta ninguna prueba con BD.
* Conteo aislado: `test_reading_orders.py` 15 y `test_reading_order_resolver.py` 33.
* Lint: `ruff check src/` → **All checks passed!**; `ruff check --select S src/` (bandit) →
  **All checks passed!**.
* 4 warnings, ajenos a SCR3 y preexistentes (`Duplicate name: 'ComicInfo.xml'` en `test_b6_cbz`;
  `RuntimeWarning: coroutine … never awaited` en `test_importer`/`test_bucle_no_bloqueado`).

---

## 2. Aceptación por criterio

### (a) Descargas por `CacheHttp`/`pedir_con_cache`; 2.ª lectura = hit; TTL guía 14 d / sitemap 24 h — **PASA**

`services/reading_orders/comun.py:225-251`: `_descargar` llama a `pedir_con_cache` con
`politica_cache=POLITICA_CACHE_GUIA/SITEMAP`, `cache` inyectada y `robots`, sin `bypass_cache`.
Políticas: guía 14 d fresca + 60 d de revalidación (retención 74 d) y negativa 24 h; sitemap 24 h
+ 14 d (15 d) y negativa 6 h (`comun.py:62-74`).
Pruebas: `test_reading_orders.py:219-232` (2.ª guía y 2.º sitemap sin peticiones nuevas),
`:235-247` (TTL exactos: 14 d / 74 d / 24 h / 15 d) y `:250-266` (404 negativo sin reintento,
24 h/6 h y caducidad). Sonda independiente: 2 lecturas → 1 petición de red, TTLs exactos.

### (b) robots evaluado y fuentes apagadas → vacío sin excepción — **PASA**

`_descargar` pasa `robots` a `pedir_con_cache` (`comun.py:228-238`) y captura
`FuenteApagada`, `CortesiaEnEspera`, `AccesoProhibidoPorRobots` y `ErrorDePeticion`:
registra `reading_orders.sin_turno`/`negativa` y devuelve `None`; los métodos públicos lo
traducen a `[]`/`None` (`comun.py:239-246, 254-284`). Nunca se propaga excepción al llamador.
Pruebas: `test_robots_que_prohibe_devuelve_vacio_y_log_sin_turno` (`test_reading_orders.py:269-283`)
y `test_fuente_apagada_devuelve_vacio_sin_peticiones` (`:286-294`).
Sonda independiente: con robots `Disallow: /` → `None` + log `sin_turno` y **0** peticiones a la
guía; con los `Settings` reales (sin flags, que es el estado de este commit) → vacío + **0**
peticiones (ver O1).

### (c) Cero prosa en el resultado — **PASA**

`RawReadingEntry` solo declara `orden`, `referencia`, `seccion` e `item_url`
(`comun.py:112-120`): no hay campo donde guardar prosa. El extractor RO **ignora** los
`li.aside.note-row` (`comicbookreadingorders.py:78-87`) y solo lee
`span.issue-title`/`span.year`/`a.read-link`; el CG solo toma los `p` de `.image-subtitle` que
contienen `#` (`continuity_guide.py:74-91`) y descarta títulos de arco y prosa.
Pruebas: `test_reading_orders.py:137-140` (lista exacta de campos y ningún `PROSA`) y `:163-164`.
Fixtures: prosa sustituida por `PROSA_DE_PRUEBA` (verificado por grep en los 2 HTML).
Sonda independiente: 11 entradas RO y 7 CG sin ningún `PROSA`, campos exactos `[…4…]`.

### (d) CG sin `?format=json` ni query; RO sin `/api/`, `/search/`, `/admin/` — **PASA**

RO: `RUTAS_PROHIBIDAS = ("/api/", "/search/", "/admin/")` (`comicbookreadingorders.py:34`) y
`_url_del_sitio` exige `https`, host de la allowlist, ruta permitida y **sin query**
(`:47-59`). CG: `_url_del_sitio` rechaza **cualquier** query (`continuity_guide.py:47-57`).
Pruebas: `test_cg_nunca_pide_query_ni_sitemap_index` (`test_reading_orders.py:206-214`) registra
todas las URLs y no hay `?` ni `sitemap_index.xml`; `test_urls_fuera_del_sitio_o_con_query_se_rechazan`
(`:322-335`) rechaza host ajeno, `/api/` y `?format=json` **antes** de pedir.
`grep "format=json"`: solo aparece en comentarios, en el LEEME (dice que no hay) y en las pruebas
que lo rechazan; ninguna petición real lo usa. Sonda independiente: RO rechaza
host/http/`/api/`/`/search/`/`/admin/`/query con 0 peticiones; CG rechaza `?format=json` con 0.

### (e) Sitemap filtrado por host (sin `images.squarespace-cdn.com`) — **PASA**

RO: `_filtrar_sitemap` valida la URL y exige `^/(marvel|dc)/(events|characters)/…-reading-order/`
(`comicbookreadingorders.py:61-64`). CG: allowlist de host + descarte de extensiones/estáticos
(`continuity_guide.py:31-34, 59-63`). Pruebas: `test_descubrimiento_filtra_los_dos_sitemaps`
(`:169-187`: 7 guías RO sin `about`/`not-a-guide`; 8 CG sin `images.squarespace-cdn.com`),
`test_topes_de_sitemap` (`:190-201`: 10.000 `<loc>` / 2.000 guías y namespaces) y
`test_filtro_del_sitemap_cg_excluye_imagenes_y_query` (`:357-363`).
Sonda independiente: 7 guías RO y 8 CG, cero URLs del CDN.

### (f) HTML roto / cuerpo > 2 MiB → `None`/`[]` + log, sin excepción — **PASA**

Tope `MAX_CUERPO = 2 MiB` (`comun.py:53-56`): `_descargar` registra
`reading_orders.cuerpo_demasiado_grande` y devuelve `None` (`:247-250`); `leer_guia` envuelve el
parseo en `try/except` → `reading_orders.parse_fallido` y `None` (`:275-283`); `descubrir_guias`
hace lo mismo con el sitemap (`:259-265`). Parseo en `asyncio.to_thread` (`:260, :276`).
Pruebas: `test_html_irreconocible_devuelve_none_y_log` (`:299-306`),
`test_cuerpo_demasiado_grande_no_se_parsea` (`:309-317`) y `test_el_parseo_corre_fuera_del_bucle`
(`:340-354`). Sonda independiente: CG con `<html></html>` y con cuerpo > 2 MiB → `None` + log
correspondiente, sin excepción.

### (g) Resolver puro con los casos de la spec — **PASA**

`services/reading_order_resolver.py` (sin red/BD; solo importa `re`, `dataclasses`,
`typing` y `core.matcher.normalize_title`, puro): `parsear_referencia`, `expandir_rango` (solo
enteros, tope 100), `ReadingOrderItem` con `anio_volumen`/`anio_numero` separados.
Pruebas: `test_reading_order_resolver.py:22-77` (21 casos parametrizados: tabla de la spec §3,
rangos, `Annual`, `Vol.`, `½`, `12.NOW`, `1A`, `0.1`, `1/2`, TPB/Omnibus, `one-shot`,
`limited series`, prosa/encabezados → `None`, `Vol. 1-3` → `None`), `:80-87` (los dos años no se
mezclan), `:90-93` (paréntesis no reconocido → confianza baja), `:96-115` (`expandir_rango`),
`:118-127` (clave con `normalize_title` y ausencia de imports de `httpx`/`sqlalchemy`).
Sonda independiente (18 casos propios): **0 fallos**, incluidos los 6 obligatorios del Anexo D y
la separación `anio_volumen`/`anio_numero`.

### (h) Sin migraciones ni cambios en `models`/`web` — **PASA**

El commit es **solo aditivo**: 12 ficheros nuevos, `+1512 / −0`
(`git diff HEAD~1 HEAD --numstat`), todos en `src/zascarr/services/reading_order*` y
`tests/` (paquete, resolver, fixtures y 2 ficheros de pruebas). No toca `models/__init__.py`,
`web/`, `alembic/`, `config.py`, `cortesia.py` ni `LEGAL.md` (comprobado con
`git diff HEAD~1 HEAD --name-only | grep …` → sin resultados). Árbol limpio.

### (i) Fixtures reales recortados y anonimizados con LEEME — **PASA**

`tests/fixtures/lecturas/` (2 HTML + 2 sitemap) con
`tests/fixtures/lecturas/LEEME.md`: origen y URL de cada recorte, fecha de captura **2026-11-13**,
qué conserva cada fixture, caducidad de revisión **2027-01-12** y la nota de que la prosa del
autor se sustituye por `PROSA_DE_PRUEBA`. Revisión manual: no queda prosa del autor ni datos
personales; solo estructura, series/números/años/secciones y URLs de la guía. No hay
`?format=json` en ningún fixture.

### Comprobación independiente (15/15)

Además de ejecutar las pruebas del builder, corrí una **sonda propia** con caché falsa y
transporte simulados escritos al efecto (no la `CacheHttpFalsa` del builder): **15/15 OK** —
resolver (tabla/variantes/años/rangos), fuentes apagadas sin flags (0 peticiones), RO
(11 ítems, orden, secciones, 0 prosa, hit y TTLs), CG (7 tarjetas, 0 prosa, sin query, sitemap
filtrado), HTML roto y > 2 MiB, URLs rechazadas sin socket y robots que prohíbe.

---

## 3. Observaciones y riesgos (ninguno bloquea la aceptación de task-19)

**O1 — Entrega parcial respecto a la spec: sin integración §5 ni corte 4; los extractores no son
alcanzables desde la app.** Este commit implementa cortes 1–3 (resolver + dos extractores), que es
lo que pedía task-18 («sin modelo/UI»), pero **no** la integración de fuentes de la spec §5
(`config.py` con `reading_orders_enabled`/`continuity_guide_enabled`, `cortesia.py`, Ajustes,
`/api/health` y filas de `LEGAL.md`) ni la reconciliación del corte 4/AC-08. Consecuencia real:
no hay flags (`grep` en `src/` no encuentra `reading_orders_enabled`/`continuity_guide_enabled`),
`fuente_habilitada()` las considera siempre apagadas y **ningún módulo de la app instancia o llama
a los extractores** (`grep` de `ReadingOrdersExtractor`/`ContinuityGuideExtractor` fuera del
paquete: vacío). Es coherente con el alcance de esta tarea y con (b)/(h), y el contrato queda
probado, pero **SCR3 «entrega 1» tal como la escribe la spec no queda cerrada**: falta la tarea de
integración (y, si el PO la quiere, la reconciliación). Decisión del Lead/PO.

**O2 — Deriva menor de nombres respecto a la spec.** La spec §7/AC-11 proponía
`tests/fixtures/reading_orders/README.md`; la entrega usa `tests/fixtures/lecturas/LEEME.md`
(equivalente en contenido y con fecha/URL). Nada roto: solo lo dejo anotado para que no se busquen
rutas inexistentes.

**O3 — Pruebas acopladas a `tests.test_cache_http`.** `tests/test_reading_orders.py` importa
`CacheHttpFalsa` y `Reloj` del módulo de pruebas de SCR1 (igual que hizo SCR1-Fandom). Funciona y
la pasada aislada sale verde, pero mover esos fakes a un helper compartido evitaría acoplar dos
suites.

**O4 — Riesgo declarado, no nuevo:** el cuerpo se bufferiza antes de la caché (R-2 de la spec);
con el tope de 2 MiB y el parseo en hilo aparte queda acotado, pero una página CG cercana al tope
sigue costando memoria en la Pi. La spec lo declara como deuda compartida; no se finge resuelto.

**O5 — Caducidad de los fixtures:** revisar contra las fuentes vivas antes del **2027-01-12** (o en
la primera ejecución con red); si cambia la maqueta, las pruebas fallarán en el recorte, que es lo
que se quiere detectar.

---

## 4. Veredicto

**APTO** para la aceptación de task-19 (extractores de guías + resolver puro, sin modelo/UI): suite
completa verde dos veces con contadores idénticos (6737 passed / 2275 skipped), suites de SCR3
aisladas verdes (48 passed), `ruff` limpio, criterios (a)-(i) verificados con evidencia y **15/15**
comprobaciones independientes.
**Bloqueantes: ninguno.** Observación mayor que el Lead debe resolver antes de cerrar SCR3:
**O1** (falta la integración §5 de fuentes y el corte 4; sin flags ni callers, los extractores
devuelven siempre vacío en la app real).

---

## 5. Inventario del cambio revisado (`df06c889`)

12 ficheros, **+1512 / −0** (todo aditivo, árbol limpio):
`src/zascarr/services/reading_order_resolver.py`,
`src/zascarr/services/reading_orders/{__init__,comun,comicbookreadingorders,continuity_guide}.py`,
`tests/test_reading_orders.py`, `tests/test_reading_order_resolver.py` y
`tests/fixtures/lecturas/{LEEME.md,cbro_guia.html,cbro_sitemap.xml,continuity_planetx.html,continuity_sitemap.xml}`.
