# Informe QA — SCR5: Comic Book Herald por RSS (2026-11-14)

**Rol:** QA · **Tarea:** task-31 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr5-herald`
**Rama:** `feat/scr5-herald`, SHA **`7c6f8be2d1978a8e66f2a302b8a892537f7bf687`** (verificado con
`git rev-parse HEAD`; PR #800 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL` (SCR5 no usa Postgres).
El único fichero escrito es este informe; el scratch de QA (`.qa-scr5/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **6950 passed, 2282 skipped**, 4 warnings, 0 fallos | 353,52 s (wall 5:57) |
| `pytest -q` (suite completa, 2.ª pasada) | **6950 passed, 2282 skipped**, 4 warnings, 0 fallos | 339,71 s (wall 5:43) |
| `pytest -q tests/test_comic_book_herald.py` (aislada) | **17 passed** | 0,97 s (wall 2,07 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
contaminación entre pruebas. Los 2282 skips son los esperados sin `TEST_DATABASE_URL` (pruebas
`*_pg`), ajenos a SCR5. Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado; `AsyncMock`
sin await en importer).

---

## 2. Reproducción independiente con fixtures propios — **16/16 OK**

Además de las pruebas del builder, construí un **feed RSS propio** (no sus fixtures), una caché
en memoria y un transporte simulado, y ejercité el servicio real:

* **Parseo.** Título, enlace, fecha (`pubDate` RFC822) y categorías; la `description` con prosa
  **no** se lee. Tildes/ñ bien.
* **Allowlist.** Rechaza `http://`, host ajeno (`evil.example`) y credenciales en la URL.
  **Observación (O1):** también acepta el ápex `https://comicbookherald.com/…` y un puerto no
  estándar (`:8443`); ver §4.
* **XML hostil.** XML roto, XXE (`file:///etc/passwd`) y bomba de entidades → `[]` sin excepción
  y sin resolver entidades (0,1 ms).
* **Cliente.** Solo se pide el feed (ni HTML de artículos ni imágenes): una petición a la URL
  del feed en la primera llamada y **cero** en la segunda (hit de caché). Fila de caché con
  **6 h fresca / 2 días de retención** (= 6 h + margen 304), como la política.
* **Robots.** Denegado → `[]` sin pedir el feed.
* **Fallos esperables.** 404 → `[]`; cuerpo > 1 MiB → `[]` (no se parsea); fallo de red → `[]`;
  feed configurado fuera de la allowlist → `[]` sin pedir; `FuenteApagada` se propaga sin
  peticiones; `CortesiaEnEspera` (bloqueo) se propaga sin peticiones.
* **UI.** `_novedades_de_herald` no instancia el cliente con la fuente apagada y **recorta a 5**
  items con la fuente encendida; `/ui/arcos` pinta la sección con `rel="noopener noreferrer"` y
  `target="_blank"`, **sin `<img>`** ni hotlinking.
* **Defaults/LEGAL.** `Settings(_env_file=None).comic_book_herald_enabled is False`, ritmo 3,5 s
  y 1 intento; toggle en Ajustes y fuente en `/api/health`; `LEGAL.md` con la fila del feed
  público y hash versionado nuevo (`d2b2983f21313779`, distinto de `HEAD~1`).

---

## 3. Aceptación por criterio

**Solo feed RSS público, nunca HTML de artículos ni imágenes.** PASA.
`services/comicbook_herald.py` hace **una** petición GET al feed configurado (`novedades`,
`:207-255`) y no descarga artículos, imágenes ni JSON del tema; los fixtures incluyen
`description` con prosa y el parser no la lee (`parsear_feed`, `:125-161`). La sonda contó una
sola URL (el feed). La UI solo usa el enlace para atribuir/abrir (`arcos.html:30-42`), sin
hotlinking.

**Allowlist `https://www.comicbookherald.com/` (sin http/otros hosts/credenciales).** PASA con
la observación O1: `_url_del_articulo` exige `https`, host en
`HOSTS_PERMITIDOS = ("comicbookherald.com", "www.comicbookherald.com")` y rechaza
userinfo/control; `http://`, host ajeno y `user:pass@` se rechazan (prueba y sonda). El ápex y
puertos distintos de 443 se aceptan (misma web; ver O1).

**XML roto/XXE/entidades → `[]` sin excepción.** PASA. `parsear_feed` (`:125-140`) usa
`etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=False)` y
captura `XMLSyntaxError`/`ValueError`/`TypeError`; probado con `feed_xml_roto.xml`,
`feed_xxe.xml` y bomba de entidades propia.

**Tope 1 MiB.** PASA. `MAX_CUERPO = 1 MiB` y `novedades` devuelve `[]` con log
`comicbook_herald.cuerpo_demasiado_grande` si el cuerpo lo supera (`:246-249`); prueba y sonda.

**TTL 6 h y hit sin red.** PASA. `POLITICA_CACHE_FEED` = 6 h fresca, +2 días de retención y
negativa 6 h (`:57-66`); el cliente pasa por `pedir_con_cache`; la 2.ª llamada de la prueba y de
la sonda no hace peticiones (hit).

**robots y `FuenteApagada`/`CortesiaEnEspera`.** PASA. Se pasa `robots` a `pedir_con_cache`
(`:217-235`); `AccesoProhibidoPorRobots` → `[]` con log `robots`; `FuenteApagada` y
`CortesiaEnEspera` se propagan sin pedir (`:226-232`). Pruebas y sonda.

**Flag apagado por defecto en config/Ajustes/health.** PASA. `config.py:119-123` define
`comic_book_herald_enabled=False`, ritmo 3,5 s y feed por defecto; Ajustes lo muestra en
`ajustes.html:58-60` y lo guarda por `Form` (`web/ajustes.py:359-373`);
`/api/health` lo lista `disabled` (`api/health.py:480-481`); `runtime_settings` lo incluye en
`fuentes` (grupo override) y `cortesia` en nombres/declaradas (13 fuentes). Pruebas
`test_fuentes_apagadas_por_defecto`, `test_health`, `test_web_ajustes_fuentes_nuevas`,
`test_cortesia`/`test_web_estado_cortesia`; sonda.

**Fila en `LEGAL.md`.** PASA. `LEGAL.md:66` describe el feed público (título/enlace/fecha/
categorías), sin HTML ni imágenes, con atribución a `comicbookherald.com`; `current_legal_version`
cambia por hash (sonda: `d2b2983f…` ≠ `HEAD~1`).

**Sección en `/ui/arcos` solo con la fuente encendida, ≤5 items, `rel="noopener noreferrer"`,
sin hotlinking.** PASA. `web/arcos.py:100-117` (`_novedades_de_herald`) solo actúa si
`fuente_habilitada("comic_book_herald")`, recorta `[:5]` y se traga fallos esperables; la
plantilla `arcos.html:30-42` pinta título/fecha/enlace con `target="_blank"` y
`rel="noopener noreferrer"`, sin `<img>`. Pruebas de `test_web_arcos` y sonda (7 items → 5,
fuente apagada → nada, HTML con rel/no `<img>`).

**Fixtures reales con LEEME.** PASA. `tests/fixtures/herald/LEEME.md` documenta el origen
(`https://www.comicbookherald.com/category/reading-orders/feed/`, captura 2026-11-14), y los
fixtures conservan estructura RSS real con tildes/ñ, `pubDate` RFC822, categorías y `description`
con prosa; `feed_urls_no_permitidas.xml`, `feed_xml_roto.xml` y `feed_xxe.xml` cubren los casos
hostiles.

**Sin migraciones ni cambios en `models`.** PASA. `git diff HEAD~1 HEAD --name-only` no incluye
`models/` ni `alembic/`; el commit son 23 ficheros (+914/−9): servicio nuevo, integración
config/Ajustes/health/cortesía/LEGAL/arcos, fixtures y pruebas.

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — La allowlist acepta el ápex y puertos no estándar.** `HOSTS_PERMITIDOS` incluye
`comicbookherald.com` además de `www.comicbookherald.com`, y `_url_del_articulo` valida el puerto
con `partes.port` pero **no exige 443**: `https://comicbookherald.com/…` y
`https://www.comicbookherald.com:8443/…` pasan. Es la misma web y los enlaces de ítem solo se
muestran/navegan (el feed configurado sí se pide, pero lo elige el operador); el riesgo es bajo.
Si el criterio es allowlist exacta, conviene dejar solo `www.comicbookherald.com` y puerto 443.
Las pruebas actuales no cubren estos dos casos.

**O2 — `/ui/arcos` hace la petición del feed en el GET de la página cuando la fuente está
encendida.** Con caché caliente es un hit sin red, pero el primer GET tras 6 h (o con la caché
vacía) espera a robots/cortesía y hasta ~20 s de timeout HTTP en el peor caso, bloqueando el
render en la Pi. No incumple la aceptación (la sección solo aparece encendida), pero conviene
valorar cargarla con HTMX/lazy o un presupuesto más corto para esta vista.

**O3 — El título del feed se recorta a 500 en `HeraldItem`, pero `categorias` no tiene cota
explícita.** El cuerpo ya está limitado a 1 MiB, así que el riesgo práctico es bajo; las
categorías hoy no se pintan en la UI. Anotado por completitud.

---

## 5. Veredicto

**APTO.** Suite completa verde dos veces con contadores idénticos (**6950 passed / 2282 skipped**,
0 fallos), `tests/test_comic_book_herald.py` aislada verde (**17 passed**) y `ruff check src/`
limpio. La aceptación se cumple: solo feed RSS público, allowlist https con rechazo de `http://`,
host ajeno y credenciales, XML roto/XXE/entidades y 404/red → `[]`, tope 1 MiB, TTL 6 h con hit
sin red, robots/`FuenteApagada`/`CortesiaEnEspera` correctos, flag apagado por defecto y visible
en config/Ajustes/health, fila en `LEGAL.md` con hash nuevo, sección de `/ui/arcos` solo con la
fuente encendida (máx. 5, `rel="noopener noreferrer"`, sin hotlinking), fixtures reales con
LEEME y sin cambios en `models`/`alembic`.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 (la allowlist acepta el ápex y
puertos ≠ 443; si se quiere allowlist literal, dejar solo `www.comicbookherald.com` y 443) y O2
(`/ui/arcos` pide el feed en el GET cuando la fuente está encendida; con caché caliente es hit,
pero el primer GET puede esperar robots/cortesía/timeout — valorar carga perezosa).

---

## 6. Comandos reproducibles

```
cd .worktrees/scr5-herald
PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_comic_book_herald.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-scr5/probe.py     # 16/16 OK
```

---

## 7. Inventario del cambio revisado (`7c6f8be2`)

23 ficheros, **+914 / −9**: `CHANGELOG.md`, `src/zascarr/LEGAL.md`, `api/health.py`,
`config.py`, `services/comicbook_herald.py` (nuevo), `services/runtime_settings.py`,
`utils/cortesia.py`, `web/ajustes.py`, `web/arcos.py`, `web/templates/{ajustes,arcos}.html`,
6 fixtures en `tests/fixtures/herald/`, `tests/test_comic_book_herald.py` (nuevo) y ajustes en
`test_cortesia.py`, `test_fuentes_apagadas_por_defecto.py`, `test_health.py`,
`test_web_ajustes_fuentes_nuevas.py`, `test_web_arcos.py` y `test_web_estado_cortesia.py`.
Sin cambios en `models/` ni `alembic/`.
