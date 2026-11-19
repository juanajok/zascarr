# Informe QA — #983: cancelar búsqueda en curso y buscar en lote (2026-11-17)

**Rol:** QA · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Rama:** `feat/deseos-lote`, PR #983, **SHA final `927fc5e4`**, fusionada como
**merge `b02583bd`** (`Merge pull request #983 from juanajok/feat/deseos-lote`; este informe se
escribe en `.worktrees/cierre`, desde `origin/main`, sin commitear).
**SHA verificado en origen:** `927fc5e4` (`test(legal): el lote de Deseados entra en las acciones
protegidas`), sobre el commit de funcionalidad `631b3886` y la corrección de B1 `dd635f51`.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL`.

---

## 1. Historial y regresión

La primera QA sobre `631b3886` detectó **B1**: la ruta nueva
`POST /ui/wishlist/buscar-lote` estaba correctamente protegida con
`Depends(require_legal_acknowledgment)`, pero el conjunto esperado del test estático de U17 no la
incluía, así que la suite fallaba:

```
FAILED tests/test_u17_avisos.py::TestLaAceptacionProtegeLoMismo::test_las_acciones_de_riesgo_protegidas_son_las_de_siempre
Extra items in the left set:
('wishlist', 'POST', '/ui/wishlist/buscar-lote')
```

La corrección `dd635f51` (y su equivalente final `927fc5e4`) es **solo de test**: añade
`("wishlist", "POST", "/ui/wishlist/buscar-lote")` al conjunto esperado y actualiza el docstring.
No cambia código de la aplicación.

| Comando | Resultado |
|---|---|
| Suite completa en `631b3886` (1.ª QA) | 1 failed, 7426 passed, 2370 skipped |
| Suite completa en `dd635f51` (re-dictamen) | **7427 passed, 2370 skipped, 0 fallos** (328,87 s) |
| `tests/test_u17_avisos.py` + `tests/test_web_wishlist_lote.py` en `dd635f51` | **26 passed** |
| Mismos tests en el árbol final fusionado (`.worktrees/cierre`, HEAD con `b02583bd`) | **26 passed** (5,98 s) |
| `ruff check src/` | **All checks passed!** |

Sin otras regresiones en la suite completa del re-dictamen.

---

## 2. Reproducción independiente — **10/10 OK**

Sonda propia con `TestClient` (base `http://localhost`, `Origin` de mismo origen), dobles de
`Orchestrator.preview_candidates`/`send_manual_candidate` y `get_db`:

* **Cancelar.** `#boton-buscar-{id}`, `hx-on::click` con `htmx:abort` sobre ese botón,
  `aria-label="Cancelar la búsqueda de Sandman"`, texto «lo ya enviado no se deshace»; el botón
  vive dentro del `span.htmx-indicator` (`#buscando-{id}`), oculto fuera de `.htmx-request`, así
  que **solo se ve durante la espera**.
* **Checkbox solo buscables.** Fila `WANTED` pinta `name="item_id"` y
  `aria-label="Seleccionar Sandman"`; fila `DOWNLOADING` no lo pinta.
* **Barra de lote.** `hx-post="/ui/wishlist/buscar-lote"`,
  `hx-include="#wishlist-list input[name='item_id']:checked"`, `hx-target="#resultado-lote"`,
  indicador `#buscando-lote` y `#resultado-lote aria-live="polite"`.
* **Sin selección** → 200 «No has seleccionado ningún deseo», sin `preview_candidates`.
* **Más de 8** → 200 «máximo por tanda es 8», sin `preview_candidates` ni OOB.
* **Gate legal.** POST sin aceptación → **403** con `HX-Redirect: /ui/legal`.
* **Lote de 2** → 200, dos `hx-swap-oob` para `#candidatos-{id}`, `status=WANTED` intacto y
  `send_manual_candidate` no llamado (solo `preview_candidates`, sin descargas).
* **Id inexistente** → se salta y el mensaje dice «1 ya no estaba en la lista».
* **Sin `_row`/relaciones perezosas** → item cuyas propiedades `series`/`issue` lanzan si se leen:
  la ruta responde 200 con candidatos (no accede a ellas).
* **Diff** con `MAX_LOTE=8`/`_resultado_lote`; sin `models/`, `alembic/`, `web/ajustes.py` ni
  plantillas de Ajustes.

---

## 3. Aceptación final

* **Cancelación.** Botón solo en la espera (`_estado_wishlist.html`), `htmx:abort` sobre el botón
  que lanzó la petición y `aria-label` con el título; mensaje de que lo ya enviado no se deshace.
* **Checkboxes y barra.** Checkbox condicionado a `row.puede_buscar_ahora`; barra de lote con
  `MAX_LOTE = 8`; avisos sin selección y por exceso sin llamar al orquestador; gate legal 403 con
  `HX-Redirect` (verificado).
* **OOB sin estados/descargas.** `buscar_lote` usa `db.get` (sin `_row`), llama solo a
  `preview_candidates` y renderiza `_candidatos_wishlist.html` con `hx-swap-oob`; no cambia
  `status` explícitamente ni llama a `send_manual_candidate`.
* **Ids inexistentes.** Se cuentan como `saltados` y se informa; sin 500.
* **Mensajes/aria.** `_resultado_lote.html` con `role="status"`; barra/indicador con `aria-live`;
  cancelar/checkbox con `aria-label`.
* **Alcance.** Sin migraciones ni `models`; no toca Ajustes ni `web/ajustes.py`; `ruff` limpio.

**B1 cerrado** en `dd635f51`/`927fc5e4`: el test estático incluye la ruta y la suite queda verde.
El gate legal y la funcionalidad no cambian.

---

## 4. Observaciones (deuda menor, aceptada)

**O1 — La ruta no revalida el estado de cada `item_id`.** Acepta cualquier UUID enviado a mano
(aunque no tuviera checkbox) y llama a `preview_candidates`; un POST manipulado podría buscar sobre
un deseo `DOWNLOADING`/`IMPORTED`. Es el mismo comportamiento que «Buscar ahora»; conviene filtrar
por `WANTED`/`FAILED` en servidor en una tarea de endurecimiento.

**O2 — `preview_candidates` puede revertir `SEARCHING`/`FAILED` a `WANTED`** porque
`_search_and_rank` marca la búsqueda; no lo introduce el lote, pero matiza el «sin cambiar
estados»: el estado final no queda en `SEARCHING` ni se envía nada; la prueba cubre `WANTED`
intacto. El Lead aceptó ambas como deuda menor para otra pasada.

---

## 5. Veredicto

**APTO para `927fc5e4` (merge `b02583bd`).** La funcionalidad de cancelación y lote cumple
(a)-(f); el único bloqueante de la primera QA (B1, test estático de U17 desactualizado) quedó
cerrado con la corrección test-only; suite completa verde en el re-dictamen (7427 passed / 2370
skipped, 0 fallos), 26 tests de U17+lote verdes también en el árbol fusionado, `ruff` limpio y sin
regresiones. Observaciones O1/O2 quedan documentadas como deuda menor aceptada.

---

## 6. Comandos reproducibles

```
cd .worktrees/cierre
PYTHONPATH=src … -m pytest -q tests/test_u17_avisos.py tests/test_web_wishlist_lote.py
cd .worktrees/lote        # pre-fusión
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-lote/probe.py       # 10/10 OK (QA original)
```

---

## 7. Inventario del cambio revisado

* Funcionalidad #983 (`631b3886`): 7 ficheros, **+260/−0**: `CHANGELOG.md`,
  `src/zascarr/web/templates/_estado_wishlist.html`, `_fila_wishlist.html`,
  `_resultado_lote.html`, `wishlist.html`, `src/zascarr/web/wishlist.py` (`MAX_LOTE=8`,
  `_resultado_lote`, `buscar_lote`) y `tests/test_web_wishlist_lote.py`.
* Corrección B1 (`dd635f51`/`927fc5e4`): **solo** `tests/test_u17_avisos.py` (+3/−1).
* Sin `models/`, `alembic/`, `web/ajustes.py` ni plantillas de Ajustes.
