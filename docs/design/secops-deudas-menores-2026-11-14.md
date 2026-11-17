# SecOps — Revisión ligera del lote de deudas menores

**Rol:** SecOps · **Tarea:** task-35 · **Fecha:** 2026-11-14 (15:05–15:30, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/deudas-menores` (rama `fix/deudas-menores`)
**SHA dictaminado:** **`15a6e908bfad81546830981fc031469c8925eaa4`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 805` → `headRefOid = 15a6e908bfad81546830981fc031469c8925eaa4`, base `main`,
`state=OPEN`, `mergeable=MERGEABLE` (`mergeStateStatus=UNSTABLE`: checks en curso). Árbol limpio.
**Cambio:** `938654ea` (lote, 14 ficheros, +401/−14) + `15a6e908` (informe QA + fix del bloqueante de
test: `bd_efimera_sync` → `async with bd_efimera`); total **15 ficheros, +569/−14**. **No toca
`web/ajustes.py`, `services/seguridad.py`, `services/reautenticacion.py`, `models/` ni migraciones**, por
lo que **§5.8 no aplica** (confirmado por `git diff --name-only`).
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python` (Python 3.14,
pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL` (la prueba `_pg` nueva se salta, como documenta QA).
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito y queda sin
commitear.

---

## 0. Veredicto

**FAVORABLE para `15a6e908`.** No hay hallazgos de seguridad ni bloqueantes: el único bloqueante de QA
era un defecto de la prueba `_pg` (contexto síncrono dentro de un test async), corregido en este SHA y
reconfirmado por QA con Postgres real (**1 passed**). Las seis deudas se cierran con evidencia y sin
regresiones de seguridad; §5.8 **no aplica**. Queda una observación de cobertura (m-3 en pruebas CI) no
bloqueante.

---

## 1. Hallazgos

### 1.1 Bloqueantes / mayores

**Ninguno.**

### 1.2 Observaciones no bloqueantes

* **o-1 — La cobertura CI de m-3 sigue siendo de doble sesión, no de Postgres.** Las pruebas de
  `_upsert_arc` usan `_SesionArcos`, que simula las dos consultas por texto SQL
  (`tests/test_enricher.py:961-1068`); la lógica se validó además con Postgres real en la sonda E2E de
  QA (§3 de su informe, 4/4 OK) y con la prueba `_pg` de reconciliación, pero no hay una prueba `_pg`
  específica de enricher en CI. Es la observación **O2** de QA; no afecta a la seguridad del cambio y
  puede añadirse en una ronda posterior.
* **o-2 — La prueba `_pg` nueva se salta sin `TEST_DATABASE_URL`.** Es el patrón documentado del repo
  (`pytest.mark.skipif`); con Postgres real QA la ejecutó tras el fix y dio **1 passed** (§ QA,
  addendum). Sin URL, mi ejecución local da **1 skipped**, no un fallo.

---

## 2. Verificación por deuda

### 2.1 m-1/m-2 — atribución legal y UI (CC-BY-SA, sin hotlinking)

* **Aviso genérico con Fandom:** `_legal_disclaimer.html:17-23` (kind `metadata`) menciona ahora
  «Comic Vine, AniList, Tebeosfera y DC/Marvel Database de Fandom»; la ficha de serie mantiene el aviso
  genérico dentro de `<details>` (`series_detail.html:47-50`).
* **Ficha de serie fuera del desplegable:** `series_detail.html:51-52` pinta
  `aviso_de_atribucion(atribucion_fandom, "esta ficha", true)` **después** de cerrar
  `<details class="series-fuentes">`; el macro (`_atribucion_fandom.html:6-16`) enlaza el artículo y la
  licencia CC-BY-SA 3.0 con `target="_blank"` y `rel="noopener noreferrer"`. Prueba
  `test_web_series.py:1214-1234` (`TestAtribucionFandomVisible`): la atribución visible fuera y el
  desplegable conserva el aviso genérico; 0 referencias a «BY-SA» dentro.
* **Listado `/ui/arcos`:** `services/arcos.py:28-33,53-60,73-104` añade `ArcoResumen.origen` y
  `PaginaArcos.hay_fandom` (derivado de `metadata->>'origen'`/`fandom_dc`, sin cambiar orden,
  `offset`/`limit`); `templates/arcos.html:22-23` pinta el aviso CC-BY-SA solo si `pagina.hay_fandom`,
  con enlace a la licencia (`target="_blank"`, `rel="noopener noreferrer"`) y `/legal`, después de la
  lista y antes de la paginación. Pruebas `test_web_arcos.py:430-466` (con Fandom: aviso, `rel`, orden;
  sin Fandom: no se pinta).
* **Sin hotlinking:** estas plantillas no incluyen `<img>` externos; el aviso es texto y enlaces de
  atribución, no imágenes ni contenido copiado. La portada de serie sigue siendo local
  (`ui.portada`, caché). **Pasa.**

### 2.2 m-3 — `_upsert_arc` no adopta ni sobrescribe arcos manuales o de otra fuente

`services/enricher.py:999-1038`:
1. busca primero por identidad real `StoryArc.metadata_["fandom_dc"].astext == arco.page_title`;
2. solo si no hay, prueba por título una **compatibilidad** con un arco que ya sea de Fandom
   (`metadata_["origen"] == "fandom_dc"` o legado sin `origen` pero con `metadata_["fandom_dc"]`);
3. un arco manual (sin metadata de Fandom) o de otra fuente (`origen` distinto) **no se adopta**: se crea
   un `StoryArc` nuevo con `{"origen": "fandom_dc", "fandom_dc": page_title}`; si reutiliza uno de
   Fandom, actualiza su metadata con merge (`:1037`), nunca la de un arco ajeno.
Los enlaces `StoryArcIssue` solo se calculan para el arco seleccionado (`:1040-1085`); el manual ajeno no
recibe enlaces ni cambios. Pruebas: `test_enricher.py:961-1068` (manual homónimo intacto, otra fuente
intacta, idempotencia del segundo enricher, legado Fandom sin `origen` reutilizado por título). QA validó
además con Postgres real (sonda E2E 4/4 OK: manual con metadata y enlace intactos, arco Fandom aparte,
segunda pasada sin duplicados). **Pasa.**

### 2.3 M-5 — 304 es «304» («Sin cambios»), no «4xx», y no afecta a cortesía

`utils/peticiones.py:364-371` registra `"304"` cuando el código es 304 y mantiene `"4xx"` para
400/404; `services/cortesia_estado.py:36-45` añade `"304": "Sin cambios"` al mapa que pinta Estado
(`:110`). `registrar_resultado` solo anota el intento en el snapshot
(`utils/cortesia.py:561-571`), no modifica rate limits, bloqueos ni colas; por tanto el 304 no tiene
efecto en la cortesía. Pruebas `test_peticiones.py:574-600` (`Test304NoEs4xx`): 304 → `"304"`;
400 y 404 → `"4xx"`; una sola petición. QA confirmó con transporte real 304/400/404 y snapshot.
**Pasa.**

### 2.4 Cotas de categorías del feed Herald

`services/comicbook_herald.py:74-75,121-134`: `_categorias_de` limita a **10** categorías
(`MAX_CATEGORIAS`) y **100** caracteres por categoría (`MAX_CATEGORIA`), descarta las que contienen
controles C0/DEL, colapsa espacios y se detiene en 10; `parsear_feed` la usa (`:166-172`). No hay
inyección: las categorías no se pintan en la UI (`HeraldItem.categorias` no se usa en las plantillas) y
todo texto pasa por Jinja si se usara; el cuerpo del feed ya está acotado a 1 MiB (`:67,251-254`) y el
número de `<item>` a 10 (`:69,160-162`). Pruebas `test_comic_book_herald.py:284-303`: 50 categorías
largas → 10 y cada una ≤100; categoría con control (`&#127;[2J`) se descarta. **Pasa.**

### 2.5 Prueba `_pg` — fix del bloqueante de QA

`tests/test_reconciliacion_lecturas_pg.py:14,55` usa ahora
`from tests._pg import bd_efimera` y `async with bd_efimera(URL) as url:`, la versión **async** del
context manager (`tests/_pg.py:110-121`), en lugar de `bd_efimera_sync` (`asyncio.run` anidado). QA
reconfirmó con Postgres real tras el fix: **1 passed** (antes `RuntimeError: asyncio.run() cannot be
called from a running event loop`); sin `TEST_DATABASE_URL`, **1 skipped** documentado. La prueba no
imprime la URL ni credenciales; `tests/_pg.py` no registra logs y `alembic()` captura stderr, y el fix no
añade ningún `print`/log con `DATABASE_URL`. **Pasa.**

### 2.6 §5.8 y ficheros sensibles

`git diff --name-only f47d21f8..15a6e908` no incluye `web/ajustes.py`, `services/seguridad.py`,
`services/reautenticacion.py`, `models/` ni `alembic/` (solo servicios `arcos.py`,
`comicbook_herald.py`, `cortesia_estado.py`, `enricher.py`, `peticiones.py`, 3 plantillas y 6 ficheros
de tests). **§5.8 no aplica**; no hay cambios de contraseña/sesión, secretos ni migraciones.

---

## 3. Regresión

* **QA (documento e informe incluidos en el SHA):** suite completa sin `TEST_DATABASE_URL`
  **6987 passed / 2284 skipped ×2**, 0 fallos, contadores idénticos; con URL, la prueba `_pg` dio
  **1 failed** antes del fix y **1 passed** después (QA, addendum); `ruff check src/` limpio.
  Focalizadas de QA (enricher/arcos/series/herald/peticiones) **239 passed**.
* **Mi ejecución focalizada** (`test_enricher.py`, `test_web_arcos.py`, `test_web_series.py`,
  `test_comic_book_herald.py`, `test_peticiones.py`, `test_reconciliacion_lecturas_pg.py`,
  `test_cortesia.py`, `test_web_estado_cortesia.py`): **281 passed, 1 skipped** en 5,30 s.
* **Gates:** `ruff check src/` y `ruff check --select S src/` → *All checks passed!*.
  La suite completa del Lead sobre este SHA está en curso; el fix solo toca el test `_pg`.

---

## 4. Coherencia con QA

QA dio **NO APTO** sobre `938654ea` por un único bloqueante de test (f): `bd_efimera_sync` dentro de
un test async, que falla con Postgres real. `15a6e908` corrige exactamente eso (`async with bd_efimera`)
y QA lo reconfirmó con Postgres real (1 passed); el resto de deudas ya las había validado (m-1/m-2,
m-3 con sonda E2E, M-5, categorías, §5.8 n/a). Mis comprobaciones no contradicen su informe; solo queda
su O2 (cobertura CI de m-3 con `_pg`) como recomendación.

---

## 5. Conclusión y trazabilidad

**Dictamen FAVORABLE para `15a6e908bfad81546830981fc031469c8925eaa4`.** Sin hallazgos de seguridad ni
bloqueantes; el bloqueante de QA era de test y está corregido; §5.8 no aplica. Observación no bloqueante:
añadir una prueba `_pg` de enricher para que m-3 tenga cobertura Postgres en CI. Este informe aplica solo
a este SHA; cualquier commit/rebase posterior que cambie el árbol exigirá revisión. El informe está en el
árbol de trabajo sin commitear.

| Punto de task-35 | Sección |
|---|---|
| m-1/m-2 atribución CC-BY-SA visible, sin hotlinking, rel | 2.1 |
| m-3 sin adopción/sobrescritura de arcos ajenos, idempotencia | 2.2, o-1 |
| M-5 304 «Sin cambios» sin efecto en cortesía; 400/404 «4xx» | 2.3 |
| Cotas de categorías (10/100/controles) sin inyección/DoS | 2.4 |
| `_pg` async, sin credenciales en logs | 2.5, o-2 |
| Sin ajustes/seguridad/models/migraciones; §5.8 n/a | 2.6 |
| ruff, regresión, coherencia QA | 3, 4 |
