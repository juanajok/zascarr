# Informe QA — #985: backoff persistente tras fallos de envío (2026-11-17)

**Rol:** QA · **Tarea:** task-65 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/backoff` (la rama se
fusiona como PR #985; este informe se escribe en `.worktrees/cierre` desde `origin/main`).
**Rama:** `feat/backoff-envios`, SHA final **`cfac090d45fc0493fa287992c0e122d744ed9ba9`**
(verificado con `git rev-parse HEAD`; incluye la corrección de B1 sobre `18814b97`).
Árbol limpio antes de la verificación; no se ha modificado código. Informe sin commitear.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). PG real: contenedor `zascarr-ux508-pg`, base
`zascarr_qa_backoff2_test` creada y borrada para QA (`bd_efimera_sync`).

---

## 1. Regresión

| Comando | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa en `cfac090d`) | **7427 passed, 2373 skipped, 0 fallos**, 7 warnings | 445,89 s (wall 7:25) |
| `pytest -q tests/test_orchestrator.py` | **106 passed** | 4,11 s |
| `pytest -q tests/test_migracion_backoff_pg.py tests/test_backoff_envios_pg.py` con `TEST_DATABASE_URL` | **3 passed** | 19,89 s |
| `ruff check src/` | **All checks passed!** | — |

Las pruebas `_pg` saltan sin `TEST_DATABASE_URL` (documentado); con URL pasan. No aparecieron los
flaky de `test_lector_rar.py` en las pasadas previas.

---

## 2. Corrección de B1 y comportamiento final

`cfac090d` cambia **solo** `src/zascarr/services/orchestrator.py` y `tests/test_orchestrator.py`
(+16/−8): el envío **extra** de un deseo ya en `DOWNLOADING` es auxiliar; si el cliente falla,
**no** programa `retry_count`/`next_retry_at`, **no** cambia el estado (sigue `DOWNLOADING`, no
`FAILED`) y solo deja `last_error` del cliente en ese intento. El auto y el manual siguen
programando backoff y dejando `FAILED`; éxito y `retry` limpian.

Sonda independiente **5/5 OK**:

* helper cinco pasos ⇒ 10 min, 30 min, 2 h, 6 h, 6 h (`retry_count=5`);
* fallo automático ⇒ `FAILED` + `retry_count=1` + `next_retry_at` futuro;
* fallo manual ⇒ `FAILED` + backoff;
* fallo **extra** ⇒ `DOWNLOADING`, `retry_count` intacto (0/ausente), `next_retry_at=None`,
  `last_error=MOTIVO_TRANSMISSION_INACCESIBLE`;
* éxito extra ⇒ limpia el backoff.

---

## 3. Migración 0046 y PG real

* Cadena única `0044 → 0045 → 0046`; **una sola cabeza** `0046 (head)`.
* Sonda independiente **subir → bajar a 0045 → volver a subir** (4/4 OK): `retry_count integer
  NOT NULL DEFAULT '0'`, `next_retry_at timestamptz NULL`; el downgrade las elimina y el segundo
  upgrade las restaura.
* Sonda PG independiente de aceptación (3/3 OK): elegibilidad real en `wishlist` (futuro fuera;
  vencido entra aunque `last_searched_at` esté dentro del cooldown; sin backoff dentro del cooldown
  fuera; normal entra), `WishlistService.retry` limpia y vuelve a `WANTED`, y la reactivación de
  política (`_materializar`) limpia `retry_count`/`next_retry_at`.
* Pruebas del repo con PG real en `cfac090d`: **3 passed**.

El `WHERE` de `process_wishlist` es: `next_retry_at IS NOT NULL AND next_retry_at <= ahora` **o**
`next_retry_at IS NULL AND (last_searched_at IS NULL OR last_searched_at < cutoff)`. Decisión del
builder verificada: un backoff vencido exime del cooldown global; un futuro bloquea; el cooldown
sigue para los intentos sin backoff.

---

## 4. Aceptación

| Criterio | Resultado |
|---|---|
| Migración 0046 encadenada, una cabeza, subir/bajar | **Cumple** |
| Columnas `retry_count`/`next_retry_at` | **Cumple** (tipo/default) |
| Helper 10m/30m/2h/6h con tope | **Cumple** |
| Fallo auto ⇒ backoff + `status=FAILED` | **Cumple** |
| Fallo manual ⇒ backoff + `status=FAILED` | **Cumple** |
| Fallo extra ⇒ auxiliar: sin backoff, sin cambio de estado (decisión de producto) | **Cumple** en `cfac090d` |
| Éxito limpia backoff (auto/manual/extra) | **Cumple** |
| `retry` manual limpia backoff | **Cumple** |
| `process_wishlist`: vencido sin cooldown; futuro y sin backoff en cooldown fuera | **Cumple** (PG real) |
| Reactivación de política limpia backoff | **Cumple** (PG real) |
| Sin backoff en «sin resultados»/«candidato rechazado» | **Cumple** (pruebas/sonda previa) |
| Sin tocar `web/ajustes.py` | **Cumple** |

---

## 5. Veredicto

**APTO para `cfac090d`.** B1 queda cerrado por la decisión de producto: el envío extra auxiliar no
degrada la descarga principal ni programa un backoff que el ciclo automático no consumiría (solo
mira WANTED/FAILED); deja `last_error` del intento. Auto y manual conservan backoff y `FAILED`;
éxito y «Reintentar» limpian. Migración 0046 reversible, una sola cabeza y columnas correctas;
elegibilidad PG y reactivación de política verificadas. Guion de pruebas: suite completa nueva **7427 passed / 2373 skipped / 0 fallos** (445,89 s),
`test_orchestrator.py` **106 passed**, PG real **3 passed**, sonda de comportamiento **5/5** y
`ruff` limpio. En `18814b97` la suite completa había pasado dos veces con 7427/2373/0; el cambio
posterior solo toca el path del envío extra y sus pruebas.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: `next_retry_at` no tiene índice (filtro de
elegibilidad; valorar índice parcial en el futuro) y el backoff del extra desaparece por diseño
(no aplica a `DOWNLOADING`).

---

## 6. Comandos reproducibles

```
cd .worktrees/backoff
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_orchestrator.py
TEST_DATABASE_URL=postgresql://…/zascarr_qa_backoff2_test PYTHONPATH=src … -m pytest -q \
    tests/test_migracion_backoff_pg.py tests/test_backoff_envios_pg.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-backoff2/probe.py   # 5/5 OK
```

---

## 7. Inventario del cambio revisado (`cfac090d`, PR #985)

11 ficheros, **+507 / −11** respecto a `96b18588`: `CHANGELOG.md`,
`alembic/versions/20261117_0046_backoff_envios.py`, `docs/BACKLOG.md`,
`docs/design/benchmark-DESEADOS-2026-11-16.md`, `src/zascarr/models/__init__.py`,
`src/zascarr/services/orchestrator.py`, `src/zascarr/services/wishlist.py` y
`tests/{test_backoff_envios_pg,test_migracion_backoff_pg,test_orchestrator,test_wishlist_service}.py`.
Sin `web/ajustes.py`.
