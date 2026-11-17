# Informe QA — #1027/ADR 0022: obras autoconclusivas (one-shot) (2026-11-17)

**Rol:** QA · **Tarea:** task-72 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/oneshot-build`
**Rama:** `feat/obras-autoconclusivas`, PR #1029, SHA **`413f3902156fb55d02607870c415c8ed3fa985d2`**
(verificado con `git rev-parse HEAD`). Spec v1.0/ADR 0022 aceptados.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). PG real: contenedor `zascarr-ux508-pg`, base
`zascarr_qa_oneshot_test` creada y borrada para QA (`bd_efimera_sync`).
Sin modificar código; el único fichero escrito es este informe (sin commitear).

---

## 1. Regresión

| Comando | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7778 passed, 2398 skipped**, 7 warnings, 0 fallos | 407,05 s (wall 6:47) |
| `pytest -q` (suite completa, 2.ª pasada) | **7778 passed, 2398 skipped**, 7 warnings, 0 fallos | 389,82 s (wall 6:29) |
| `pytest -q` suites tocadas (obras, web one-shot, migración, colección, pendientes/review, series, enums, centralización) | **273 passed, 3 skipped** (los `_pg` sin URL) | 13,58 s |
| `pytest -q tests/test_migracion_oneshot_pg.py` **con** `TEST_DATABASE_URL` | **1 passed** | 7,70 s |
| `ruff check src/` | **All checks passed!** | — |

Los 2398 skips son los esperados sin `TEST_DATABASE_URL` (`*_pg`). Los 7 warnings son
preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en importer). Sin cambios en
`web/ajustes.py` ni `services/seguridad.py`.

---

## 2. Migración 0049 (PG real)

* `TEST_DATABASE_URL=… pytest -q tests/test_migracion_oneshot_pg.py` → **1 passed** (7,70 s).
* Sonda independiente en base efímera **5/5**:
  - una sola cabeza **`0049 (head)`**;
  - `series_kind` = `regular, annual, special, one_shot`;
  - **no añade columnas** (`kind` ya existía); no hay DML/backfill;
  - `downgrade 0048` deja el valor de enum (documentado como irreversible) y **no borra filas**;
  - volver a head restaura el estado.
* Sin cambios de modelo más allá del valor de enum; las series existentes siguen `regular`.

**AC-9: cumple.**

---

## 3. Bloqueante

### B1 — Una ONE_SHOT con `Issue` pero **sin archivo** se da por completa

La spec D4 dice que una obra autoconclusiva está completa cuando tiene «al menos una **publicación
con archivo disponible** (o su publicación vinculada, según el caso)». El código actual sólo
comprueba que exista una fila `Issue`, **no** que tenga un `File` no `is_missing`:

* `huecos_de_serie` (`services/series.py:658+`): para `ONE_SHOT` hace
  `select(Issue.id).where(Issue.series_id == series.id)` y devuelve `Huecos([], True)` si hay
  cualquier `Issue`, sin mirar `File`.
* `estado_de_coleccion` usa esos huecos; `condicion_estado_coleccion("completa")` usa
  `EXISTS (SELECT 1 FROM issues …)`; `ids_por_estado("completa")` usa el conjunto de `Issue`.
* Sonda propia con PG real: serie `ONE_SHOT` + `Issue` sin ningún `File` ⇒
  `Huecos(faltantes=[], computable=True)`, `estado=completa`, aparece en `ids_por_estado("completa")`
  y en el SQL de `condicion_estado_coleccion("completa")`.

Si la lectura correcta de D4 es «archivo disponible» (como pide el AC-2), es un **falso completo**
bloqueante. Si el PO decide que «publicación vinculada» incluye un `Issue` sin `File`, entonces no es
bloqueante, pero debe documentarse la excepción y el nombre de los estados; el código actual no lo
dice. En ambos casos, **no hay prueba** del caso `Issue` sin archivo: el test
`test_huecos_obra_unica_completa_con_publicacion` sólo devuelve un UUID de `Issue`.

**Fix esperado (si aplica D4):** comprobar `File.is_missing == false` en `huecos_de_serie`,
`condicion_estado_coleccion` y `ids_por_estado` (join `Issue`→`File`), y cubrir con PG/`FakeSession`
los casos con archivo y sin archivo.

---

## 4. Evidencia adicional (sin red)

* **Completitud sin publicación**: `huecos_de_serie` devuelve `computable=False` y motivo
  «sin publicación…»; `estado_de_coleccion` da **no calculable**, no «falta #1». Correcto en la
  ruta async que usa la ficha (`web/series.py:566,590`).
* **`estado_puro`** (`coleccion.py:140`) devuelve **COMPLETA para cualquier ONE_SHOT**, incluso sin
  publicación; el test `test_razon_pura_no_bloquea_la_obra_unica` lo fija así. **No tiene usos en
  producción** (solo `tests/test_coleccion.py` y el test nuevo); la ficha usa
  `estado_de_coleccion` async. Es deuda menor/latente, no el bloqueante actual.
* **Política/seguimiento**: `querer_de_serie` devuelve vacío + `MOTIVO_OBRA_AUTOCONCLUSIVA`;
  `cargar_series_seguidas` excluye `ONE_SHOT`; UI oculta el formulario de seguimiento y avisa. La
  prueba existente pasa.
* **Alta**: sonda HTTP propia con `TestClient` y `File` falso → **3/3**: crea `Series` ONE_SHOT +
  `Issue` con `issue_number=None`, formato elegido, enlaza `File.issue_id`, **conserva
  `file_path`** y no duplica; archivo ya enlazado y título vacío devuelven 400 sin crear.
  `test_obras_autoconclusivas` cubre creación/validaciones básicas.
* **Toggle/selector**: pruebas `test_web_serie_oneshot.py` (marcar/desmarcar, >1 publicación, badge)
  y `test_obras_autoconclusivas`; el filtro `ReviewService.search_series` excluye ONE_SHOT salvo
  `incluir_one_shot` y el partial de Pendientes pasa `mostrar_tomos`. La prueba del selector usa un
  `FakeSession` que devuelve la fila sin compilar el SQL; conviene una prueba de consulta real
  (deuda de cobertura).
* **Normal/anual/especial**: `condicion_estado_coleccion` mantiene la rama regular con `~es_obra_unica`
  y las suites de colección/series pasan; no se encontró regresión.

---

## 5. Deuda menor / cobertura

* **O1 — `estado_puro`**: completa incondicional para ONE_SHOT, incluso sin publicación; sin uso en
  producción pero con test que lo fija. Corregir para que refleje la publicación/archivo (o
  eliminarlo del camino de la ficha) antes de reutilizarlo.
* **O2 — Tests**: no hay caso `Issue` sin `File` (el que motiva B1) ni prueba de `huecos` con
  archivo real; el test de `estado_puro` contradice AC-3 en la práctica.
* **O3 — Selector**: `test_el_selector_oculta_one_shot_por_defecto` no inspecciona el SQL; el filtro
  está en `ReviewService.search_series`, pero una prueba con consulta real lo blindaría.
* **O4 — `puede_marcar_obra_unica`** usa `total_issues <= 1` como pista de UI; la ruta comprueba el
  recuento real de `Issue`, correcto, pero un `total_issues` desfasado puede ocultar el control.
* **O5 — `crear_one_shot`** no pasa por la puerta legal; la spec no lo exige (no crea deseo ni
  descarga), pero conviene confirmarlo en la revisión de producto.
* **NOT RUN:** navegador real/320 px, ComicInfo (fase posterior) y backfill (fuera de v1) siguen sin
  validar; la migración PG sí se ha ejecutado en esta QA.

---

## 6. Veredicto

**NO APTO por B1** (falso «completa» con `Issue` sin archivo si D4 exige archivo disponible), con una
salvedad explícita: si el PO interpreta «publicación vinculada» como `Issue` sin `File`, B1 pasa a
deuda de aclaración/documentación. La migración 0049, el alta sin `#1`, el enlace sin mover, el
toggle ≤1 publicación, el selector y la política/seguimiento están verificados; la suite completa
está verde dos veces (7778 passed / 2398 skipped, 0 fallos) porque no hay prueba del caso sin
archivo. `ruff` limpio. No se toca `web/ajustes.py` ni `services/seguridad.py`.

---

## 7. Comandos reproducibles

```
cd .worktrees/oneshot-build
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_obras_autoconclusivas.py tests/test_web_serie_oneshot.py \
    tests/test_migracion_oneshot_pg.py tests/test_coleccion.py tests/test_pendientes.py \
    tests/test_pendientes_tarjeta.py tests/test_web_accesibilidad_pendientes.py \
    tests/test_web_series.py tests/test_enums_bd_strenum.py \
    tests/test_centralizacion_de_series.py tests/test_series_service.py tests/test_review.py
TEST_DATABASE_URL=postgresql://…/zascarr_qa_oneshot_test PYTHONPATH=src … -m pytest -q \
    tests/test_migracion_oneshot_pg.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-oneshot/migracion.py          # 5/5 OK
PYTHONPATH=src … <venv>/bin/python .qa-oneshot/completitud_pg.py      # evidencia B1
PYTHONPATH=src … <venv>/bin/python .qa-oneshot/probe_alta.py          # 3/3 OK
```

---

## 8. Inventario del cambio revisado (`413f3902`)

21 ficheros, **+616/−21**: migración `20261117_0049_serie_one_shot.py`, `models/__init__.py`
(`SeriesKind.ONE_SHOT`), `services/{coleccion,obras_autoconclusivas,politica,resumen,review,
seguimiento,series}.py`, `web/{pendientes,series}.py`, plantillas
`_obra_unica_serie.html`, `_seguimiento_serie.html`, `_tarjeta_pendiente.html`,
`series_detail.html` y 7 ficheros de pruebas. Sin `web/ajustes.py` ni
`services/seguridad.py`.

---

## Addendum — re-dictamen de B1 sobre `fb5e07cd` (2026-11-17)

**SHA corregido:** `fb5e07cdca0405ca4db3bfd7f17eba49e3de4ec4`. Diff desde `413f3902`:
`huecos_de_serie` exige `Issue` + `File.is_missing=false`; `condicion_estado_coleccion` y
`ids_por_estado` usan el mismo join a `files`; `estado_puro` recibe `tiene_publicacion` explícito;
tests ajustados. Sin otros cambios de comportamiento.

### B1 — cerrado (PG real)

Sonda independiente con `zascarr_qa_oneshot_test` **4/4 OK**:

* ONE_SHOT + `Issue` **sin File** ⇒ `Huecos(computable=False, motivo="sin publicación con archivo
  disponible…")`, `estado_de_coleccion=no_calculable`, **no** sale en `ids_por_estado("completa")`
  ni en `condicion_estado_coleccion("completa")`; **sí** en `no_calculable`;
* ONE_SHOT + `Issue` + `File(is_missing=False)` ⇒ completa, en `ids_por_estado("completa")` y en
  el SQL de completa;
* sin `Issue` ⇒ no calculable, no completa;
* `estado_puro(..., tiene_publicacion=False)` ⇒ no calculable; `True` ⇒ completa.

La ficha usa la ruta async (`estado_de_coleccion`), que ahora aplica la regla correcta.
`test_migracion_oneshot_pg.py` sigue pasando con PG real (**1 passed**, 7,30 s; 0049 sin cambios:
una cabeza, enum, sin DML/columnas).

### Regresión

* Suite completa 1.ª pasada: **7779 passed / 2398 skipped / 0 fallos** (388,04 s).
* Segunda pasada: **7779 passed / 2398 skipped / 0 fallos** (352,48 s).
* Suites tocadas: **274 passed, 3 skipped** (17,57 s); `ruff check src/` limpio.
* Normal/anual/especial y migración 0049 sin cambios; el resto de la aceptación de #1027
  (alta sin `#1`, enlace sin mover, toggle, selector, política/seguimiento) se mantiene verificado.

### Deuda menor que permanece

* `estado_puro` conserva `tiene_publicacion=True` por defecto para no romper llamadas antiguas; un
  consumidor que lo omita seguiría diciendo «completa». **No hay usos en producción** (solo tests),
  pero conviene que el valor por defecto sea explícito en futuras llamadas.
* El caso `Issue` sin `File` ya tiene prueba; sigue sin probarse un `File` con `is_missing=True` en
  PG (misma rama) y la consulta real del selector.
* NOT RUN: navegador/320 px, ComicInfo y backfill (fuera de este corte).

**Veredicto actualizado: APTO para `fb5e07cd`.** B1 queda cerrado; no aparece bloqueante nuevo.
