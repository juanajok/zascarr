# Informe QA — #993: seguir series (fuentes de descarga, deseos y aviso) (2026-11-17)

**Rol:** QA · **Tarea:** task-68 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/seguimiento-build`
**Rama:** `feat/seguimiento-series`, SHA **`5dea736325970f7ee2675f5f85054ce5358392a1`** (verificado
con `git rev-parse HEAD`; PR #993 según el encargo).
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). PG real: contenedor `zascarr-ux508-pg`, base
`zascarr_qa_seg_test` creada y borrada para QA; las pruebas `_pg` usan `bd_efimera_sync`.
**Spec/decisiones:** `docs/design/especificacion-seguimiento-series.md`, benchmark §12 y los cinco
defaults del PO (primera pasada sin histórico; config `.env`; no retirar al desactivar; sin aviso
extra de importación; no duplicar deseo manual de serie).

---

## 1. Regresión

| Comando | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7703 passed, 2383 skipped**, 7 warnings, 0 fallos | 388,58 s (wall 6:28) |
| `pytest -q` (suite completa, 2.ª pasada) | **7703 passed, 2383 skipped**, 7 warnings, 0 fallos | 375,64 s (wall 6:15) |
| `pytest -q` suites tocadas (seguimiento*, web_serie_seguimiento, enums, orchestrator, notifier, migraciones_cadena, web_series) | **322 passed, 1 skipped** (el `_pg` sin URL) | 7,01 s |
| `pytest -q tests/test_migracion_seguimiento_pg.py` **con** `TEST_DATABASE_URL` | **1 error** ← **BLOQUEANTE B1** | 3,10 s |
| `ruff check src/` | **All checks passed!** | — |

Los 2383 skips son los esperados sin `TEST_DATABASE_URL` (`*_pg`). Los 7 warnings son
preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en importer). No aparecieron flaky
de `test_lector_rar.py`.

---

## 2. Bloqueantes

### B1 — La migración 0047 **no sube en PostgreSQL** (índice parcial con cast no IMMUTABLE)

Reproducción independiente con base efímera:

```
TEST_DATABASE_URL=postgresql://…/zascarr_qa_seg_test PYTHONPATH=src … \
  python -m pytest -q tests/test_migracion_seguimiento_pg.py
→ 1 error

sqlalchemy.exc.ProgrammingError: (postgresql.asyncpg.ProgrammingError)
  <class 'asyncpg.exceptions.InvalidObjectDefinitionError'>:
  functions in index predicate must be marked IMMUTABLE
[SQL: CREATE UNIQUE INDEX uq_wishlist_seguimiento_numero ON wishlist
      (series_id, numero)
      WHERE origen::text = 'seguimiento' AND numero IS NOT NULL]
```

El predicado `origen::text = 'seguimiento'` contiene una función/cast no inmutable y PostgreSQL
rechaza el índice. Como `migrar_a_head` falla, no se puede verificar ninguna de las columnas, el
enum, la tabla ni el downgrade en PG real. La prueba **se salta sin `TEST_DATABASE_URL`**, por eso
la suite completa (sin URL) queda verde y no lo detecta.

**Fix esperado:** usar el literal de enum sin cast, p. ej.
`postgresql_where=sa.text("origen = 'seguimiento' AND numero IS NOT NULL")` (en la migración y en
`Wishlist.__table_args__`), que PostgreSQL acepta como predicado inmutable; después repetir
`upgrade/downgrade` con PG efímero.

### B2 — Primera pasada: la frontera `follow_new_issues_since` es global, no por serie

`_procesar_foro` (`services/seguimiento.py:331-332`) usa
`since = min(follow_new_issues_since de TODAS las series seguidas)`. Si una serie se activó hace
meses y otra se activa hoy, un tema antiguo (anterior al `since` de la **segunda**) se abre y puede
casar con la segunda, creando un deseo histórico. Sonda independiente:

```
serie A (Linterna Verde) since 2026-01-01;
serie B (Batman) since 2026-11-17 12:00;
tema del foro con actividad 2026-06-01 y enlace Batman 12.cbz
→ _procesar_foro devuelve hallazgo de B (lee el tema), cuando la primera pasada de B no debe
  mirar nada anterior a su since (default PO: primera pasada sin histórico).
```

Con **una sola serie** el mismo tema se salta correctamente; el fallo aparece al combinar series con
fechas distintas. **Fix:** decidir la frontera por serie — al abrir un tema, filtrar las series
candidatas por `follow_new_issues_since <= actividad`, o descartar cada hallazgo cuya serie tenga
`since` posterior a la actividad —; no usar el mínimo global.

---

## 3. Evidencia adicional (sin red)

* **Matcher:** casa `Batman Vol. 3 012.cbz`/`Batman #12.cbz` con Batman; alias `La Patrulla-X` con
  X-Men; rechaza `Batman Beyond`, tomos/anuales/especiales, `1.5`; ambigüedad (dos series iguales) ⇒
  `None`. `_probar` 3/3 en matcher/alias tras el fallo B2 (el único fallo de la sonda es B2).
* **Prowlarr (adaptador):** sonda 5/5: una consulta por serie, `publish_date >= since`, un hallazgo
  por fichero; fecha antigua/ausente descarta; serie sin `since` o lista vacía no consulta. No hay
  prueba de repo `test_seguimiento_prowlarr.py` (el builder no la añadió).
* **Dedupe:** pruebas `test_seguimiento_pasada.py`: File no missing, deseo vivo, RETIRADO, manual de
  serie, dos fuentes mismo número; pasan. El bloqueo por manual de serie y RETIRADO está cubierto.
* **Foro:** parser sintético, `listar_temas` usa **una** GET `showforum` y no `Search`, `leer_tema`
  extrae ed2k/magnet; `test_seguimiento_foro.py` pasa. **No hay prueba de tema actualizado/huella**
  ni de la frontera de primera pasada; el HTML real autenticado sigue **NOT RUN** (spec §11).
* **Notifier:** 3/3 de `test_seguimiento_notifier.py` (nombres solo con
  `webhook_incluir_nombres`, sin nombres por defecto, webhook apagado sin red); el código llama
  `notify_novedades` una vez por pasada y recorta a `seguimiento_max_avisos`, pero falta una prueba
  de integración de esa llamada única/máximo.
* **UI:** 3/3 `test_web_serie_seguimiento.py`: activar fija `since` sin tocar `wishlist_policy`;
  desactivar conserva `since`; sin acuse no cambia el flag y devuelve el aviso con `/ui/legal`.
  Nav «Seguimiento» y parcial incluidos en `series_detail.html`.
* **Política:** `querer_de_serie` solo cambia `origen.in_([MANUAL, SEGUIMIENTO])` para ocupar
  números; no toca `wishlist_policy` ni la retirada por origen. **No hay prueba específica** de
  AC-16 en el repo (deuda de cobertura).
* **Alcance:** sin cambios en `web/ajustes.py`; diff 22 ficheros (**+1290/−17**), migración aditiva
  (aunque B1 impide aplicarla). `config.py`/`.env.example`/Compose con defaults del PO.

---

## 4. Aceptación

| AC | Resultado |
|---|---|
| AC-1 migración 0047 aditiva/reversible, enum/tabla/índice | **NO CUMPLE** (B1: el índice falla al crear) |
| AC-2 toggle independiente de política | **Cumple** (tests UI) |
| AC-3 primera pasada sin histórico (frontera por serie) | **NO CUMPLE** en multi-serie (B2); una serie sí |
| AC-4 foro tema nuevo ⇒ un deseo SEGUIMIENTO/WANTED | **Cumple** en pruebas sintéticas; no reabrir sin cambios no probado |
| AC-5 tema actualizado por huella | **No cubierto** por tests; código compara huella y reabre |
| AC-6 matcher por nombre/alias/ambiguo | **Cumple** (sonda/tests) |
| AC-7 especiales/tomos/anuales/no entero | **Cumple** (tests matcher) |
| AC-8 Prowlarr por serie, rotación/cupo, fechas, apagado | **Cumple** en sonda; falta test de repo/rotación |
| AC-9 dedupe File/Wishlist/RETIRADO/manual de serie | **Cumple** (tests) |
| AC-10 ciclo existente/backoff intacto | **Cumple** (orchestrator solo reexporta helpers; pruebas del ciclo verdes) |
| AC-11 aviso una vez, máx. 5, nombres opcionales | **Cumple** en código/pruebas unitarias; falta integración |
| AC-12 puerta legal y toggle | **Cumple** (tests UI/e2e) |
| AC-13 límites/loop/sin red | **Cumple** por código/config; sin pruebas de límites reales |
| AC-14 logs sin URL/credenciales | **Cumple** por inspección/código |
| AC-15 pruebas sin red, NOT RUN declarado | **Parcial**: NOT RUN declarado; faltan pruebas Prowlarr/frontera/huella/AC-16 |
| AC-16 política no duplica SEGUIMIENTO ni toca retirada | **Cumple** por inspección; **falta prueba** |
| AC-17 docs/backlog/dependencias | **Cumple** por diff/inspección |

---

## 5. Deuda menor / cobertura

* No hay `tests/test_seguimiento_prowlarr.py` (la sonda cubre el camino básico, no rotación/cupo
  completo ni resultados duplicados).
* No hay prueba de tema actualizado/huella ni de la frontera de primera pasada multi-serie (el
  defecto B2 no se detecta con la suite actual).
* No hay prueba de que `notify_novedades` se llame **una sola vez** por pasada con máximo 5 (la
  unidad sí; falta integración).
* No hay prueba específica de AC-16 (`querer_de_serie` con deseo SEGUIMIENTO vivo); el diff es una
  única línea y no toca la retirada, pero conviene regresión.
* `crear_deseos` usa `db.add(Wishlist(...))` sin `ON CONFLICT DO NOTHING`; el índice único parcial
  está pensado para pasadas solapadas, pero dos insertos concurrentes lanzarían `IntegrityError`
  (el job es secuencial, riesgo bajo).
* **NOT RUN** sigue vigente: HTML real autenticado de `showforum=5`, comportamiento de IPB ante
  temas actualizados/flood y muestras reales de nombres; el parser es sintético.

---

## 6. Veredicto

**NO APTO.** Hay dos bloqueantes reales:

1. **B1:** `alembic upgrade head` falla en PostgreSQL al crear
   `uq_wishlist_seguimiento_numero` (`functions in index predicate must be marked IMMUTABLE`, por
   `origen::text`); la migración 0047 no se puede aplicar, y su test `_pg` se salta sin URL.
2. **B2:** la primera pasada usa el `min()` global de `follow_new_issues_since`; una serie recién
   activada puede procesar temas anteriores a su frontera si otra serie tiene una frontera más
   antigua, incumpliendo el default «primera pasada sin histórico».

El resto se ha verificado sin red (matcher, dedupe, Prowlarr básico, notifier, UI/legal, política
por inspección) y la suite completa queda verde **dos veces** (7703 passed / 2383 skipped) porque
las pruebas PG y las nuevas no cubren B1/B2. `ruff` limpio. **NOT RUN** y deudas de cobertura
listadas arriba.

---

## 7. Comandos reproducibles

```
cd .worktrees/seguimiento-build
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_seguimiento_casar.py tests/test_seguimiento_foro.py \
    tests/test_seguimiento_pasada.py tests/test_seguimiento_notifier.py \
    tests/test_web_serie_seguimiento.py tests/test_migracion_seguimiento_pg.py \
    tests/test_enums_bd_strenum.py tests/test_orchestrator.py tests/test_migraciones_cadena.py \
    tests/test_notifier.py tests/test_web_series.py
TEST_DATABASE_URL=postgresql://…/zascarr_qa_seg_test PYTHONPATH=src … -m pytest -q \
    tests/test_migracion_seguimiento_pg.py       # B1: 1 error
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-seg/probe.py           # B2 reproducido
PYTHONPATH=src … <venv>/bin/python .qa-seg/probe_prowlarr.py  # 5/5 OK
```

---

## 8. Inventario del cambio revisado (`5dea7363`)

22 ficheros, **+1290/−17**: migración `20261117_0047_seguimiento_series.py`, `config.py`,
`.env.example`, `docker-compose.yml`, `main.py`, `models/__init__.py`, `forum_scraper.py`,
`notifier.py`, `orchestrator.py`, `politica.py`, `prowlarr.py`, `services/seguimiento.py` (555
líneas), `web/series.py`, `web/templates/_seguimiento_serie.html`, `series_detail.html` y 7 ficheros
de pruebas nuevas/ajustadas. Sin `web/ajustes.py`.

---

## Addendum — re-dictamen de B1/B2 sobre `8cf17b73` (2026-11-17)

**SHA corregido:** `8cf17b73810c3bc58ccd0145743db0b7cc91fb56`. Diff desde `5dea7363`: migración
partida **0047** (columnas/enum/tabla) + **0048** (índice parcial), modelo y `_procesar_foro`, spec,
la prueba PG y `tests/test_seguimiento_foro_pasada.py` nuevos.

### B1 — cerrado: migración real subir/bajar

* `TEST_DATABASE_URL=… zascarr_qa_seg2_test pytest -q tests/test_migracion_seguimiento_pg.py` →
  **1 passed** (8,54 s).
* Sonda independiente en base efímera **0046 → 0047 → 0048 → 0046 → head (8/8 OK)**:
  una sola cabeza `0048 (head)`; columnas `follow_new_issues boolean NOT NULL` y
  `follow_new_issues_since timestamptz NULL`; enum `seguimiento`; tabla `seguimiento_vistos`;
  índice `uq_wishlist_seguimiento_numero` con predicado
  `origen <> 'manual' AND numero IS NOT NULL` (inmutable; política+seguimiento, sin manuales);
  bajar a 0047 **solo** retira el índice y conserva columnas/tabla; bajar a 0046 retira columnas y
  tabla; volver a head restaura todo. La prueba ya no falla por `functions in index predicate must
  be marked IMMUTABLE`.

### B2 — cerrado: frontera por serie y tema actualizado

Sonda independiente **4/4 OK**:

* serie vieja (Sandman, since enero) + serie nueva (Batman, since 17/11) + tema del 01/06 con
  `Batman 12.cbz` ⇒ **sin hallazgo** (el tema puede abrirse por la serie vieja, pero el hallazgo de
  Batman se filtra por su propio `since`);
* una sola serie nueva con el mismo tema ⇒ se salta sin abrir;
* tema actualizado (misma clave, huella distinta) ⇒ se abre y crea el hallazgo;
* tema nuevo posterior al `since` ⇒ se abre y crea el hallazgo.

`tests/test_seguimiento_foro_pasada.py` añade esos dos casos (nuevo 2 passed); la suite tocada
incluye ya 324 passed / 1 skip.

### Regresión final

* Suite completa ×2: **7705 passed / 2383 skipped / 0 fallos** (428,46 s y 447,10 s; 2 tests nuevos
  respecto a la QA anterior).
* Suites tocadas (seguimiento*, web_serie_seguimiento, enums, orchestrator, notifier,
  migraciones_cadena, migración seguimiento, web_series): **324 passed, 1 skip**.
* `ruff check src/`: **All checks passed!**
* Dedupe/legal/caps/notifier/UI no cambian en el fix; sus pruebas siguen verdes. La deuda declarada
  (tests Prowlarr/rotación, integración aviso único/máx. 5, AC-16, NOT RUN real de `showforum=5`)
  sigue como deuda menor, no bloqueante.

**Veredicto actualizado: APTO para `8cf17b73`.** B1 y B2 quedan cerrados; no aparece bloqueante
nuevo. Observaciones menores: el docstring de 0047 aún dice «retira … índice» aunque el índice vive
en 0048 (solo documentación), y un tema con `ultima_actividad` no reconocida se marca visto sin
abrir en primera pasada (fail-closed); ambas son deuda menor.

## Cierre de la deuda #1017 (2026-11-17)

**Alcance:** O-2, cobertura O-3, ratificación O-1 y humo del parser; sin migración nueva.

- **O-2 — cerrado.** La frontera por serie se aplica también a temas ya vistos usando la actividad
  previa (huella guardada; `visto_en` si la huella no es fecha). Regresión en
  `tests/test_seguimiento_foro_pasada.py`: serie vieja + serie nueva + tema actualizado ⇒ solo el
  histórico de la vieja; control positivo posterior a la frontera; fallback `visto_en`.
- **O-1 — ratificado por el PO.** El foro sigue sin consultar `robots.txt` (postura M4), opt-in, con
  acuse y aviso legal; queda escrito en la spec (§13) y en el benchmark (§12). No hay cambio de
  comportamiento.
- **O-3 — cobertura añadida.** `tests/test_seguimiento_prowlarr.py` (rotación/cupo, corte por
  `publish_date`, cupo de deseos, una consulta por serie y pasada); aviso único y máximo 5 en
  `tests/test_seguimiento_pasada.py`; AC-16 explícito (deseo `SEGUIMIENTO` vivo ocupa su número y no
  consume el cupo de la política); humo del parser con
  `tests/fixtures/foro/showforum_real_anonimizado.html`.
- **O-4 — sigue abierta como deuda menor** (`crear_deseos` sin `ON CONFLICT`; job secuencial).

**Suites ejecutadas (sin Postgres):**

| Comando | Resultado |
|---|---|
| `pytest -q tests/test_seguimiento_pasada.py tests/test_seguimiento_foro.py tests/test_seguimiento_prowlarr.py tests/test_seguimiento_foro_pasada.py` | **26 passed** |
| `pytest -q` (suites de seguimiento + web de la ficha) | **38 passed** |
| `ruff check src/` | **All checks passed!** |

El HTML real de `showforum=5` ya se validó en la Pi al cerrar #993; el fixture anonimizado fija el
humo sin red. No se toca la Pi ni la biblioteca real.
