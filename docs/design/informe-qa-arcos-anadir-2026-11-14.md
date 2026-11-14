# Informe QA — Arreglo «añadir un número a una saga» (2026-11-14)

**Rol:** QA · **Tarea:** task-25 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/arcos-anadir`
**Rama:** `fix/arcos-anadir-numero`, SHA **`8108c73f22ce81bdfc80f33f75ac5d5bfbd85c2d`**
(verificado con `git rev-parse HEAD`; PR #779 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL` en el entorno; la aceptación con
datos reales se hizo con el contenedor Postgres disponible (§2).
El único fichero escrito es este informe; el scratch de QA (`.qa-arcos/`) se borró al terminar.

---

## 1. Regresión

| # | Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|---|
| 1 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6802 passed, 2280 skipped**, 4 warnings | 338,68 s (wall 5:42) |
| 2 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6802 passed, 2280 skipped**, 4 warnings | 335,85 s (wall 5:39) |
| 3 | `… pytest -q tests/test_web_arcos.py` | **16 passed** | 2,54 s (wall 3,93 s) |

* Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
  contaminación entre pruebas. Los 2280 skips son los esperados sin `TEST_DATABASE_URL`
  (pruebas `tests/*_pg.py` y dependientes de entorno).
* Lint: `ruff check src/` → **All checks passed!**.
* 4 warnings, ajenos a este arreglo y preexistentes (`Duplicate name: 'ComicInfo.xml'`;
  `RuntimeWarning: coroutine … never awaited` en `test_importer`/`test_bucle_no_bloqueado`).

---

## 2. Aceptación por HTML/TestClient — **14/14 OK** (con Postgres real)

Para no depender solo de los dobles del builder, ejecuté una sonda propia **TestClient + Postgres
real**: base nueva `zascarr_qa_arcos_test` en el contenedor `zascarr-ux508-pg`
(`postgres:15-alpine` 15.19), migrada a `head` con `tests._pg.migrar_a_head`, con una serie
(Batman) y 5 números sembrados y una saga con los números 1 y 2 ya enlazados; al terminar se
**borró** la base. Las peticiones pasan por la app real, la plantilla real y el servicio real
(`agregar_numero`), no por mocks.

**GET `/ui/arcos/{id}`**
* 200, muestra «**Añadir un número**», el formulario `action="/ui/arcos/{id}/numeros"` y los tres
  campos `serie`, `numero` y `orden` con sus etiquetas (Serie/Número/Posición).
* El botón es **neutro**: `<button type="submit" class="btn ghost">Añadir número</button>`, y la
  sección no contiene `primary` en ninguna clase.
* Las acciones existentes siguen: «Editar la saga», «Eliminar la saga», «Subir una posición»,
  «Bajar una posición» y «Quitar de la saga».
* Reutiliza clases del sistema de diseño ya definidas (ver §3), sin CSS nuevo.

**POST válido**
* `serie=Batman&numero=3` (posición vacía) → **303** a
  `/ui/arcos/{id}?guardado=numero`; en BD el número 3 queda en `reading_order=3` (al final).
  El GET con `?guardado=numero` muestra «Número añadido a la saga.».
* `serie=Batman&numero=4&orden=al-final` (no numérica) → **303** y queda al final (`reading_order=4`).
* `serie=Batman&numero=5&orden=1` → **303** e inserta renumerando:
  `5→1, 1→2, 2→3, 3→4, 4→5`.

**POST inválido**
* `serie=Batmanx&numero=7&orden=2` (serie inexistente) → **200**, re-renderiza la ficha con el
  aviso en español llano «No encuentro una única serie con ese nombre. Escribe el título exacto.»,
  conserva `value="Batmanx"`, `value="7"` y `value="2"`, marca `class="campo-error"` y **no** añade
  enlaces. Sin traceback ni error 500.
* Número ya enlazado (`serie=Batman&numero=1`) → **200** con «Ese número ya está en la saga.» y
  sin duplicar filas.
* La biblioteca queda intacta: 1 serie, 5 números, 0 ficheros antes/después; solo cambian
  `story_arc_issues`.

---

## 3. Alcance del cambio y comprobaciones estáticas

* **Diff**: 4 ficheros, **+174 / −0**, todos aditivos:
  `src/zascarr/web/arcos.py` (+3: `errores`/`valores` vacíos en el GET y `aviso=""` en el
  re-render de error), `src/zascarr/web/templates/arco.html` (+31: la sección del formulario),
  `tests/test_web_arcos.py` (+133: 7 pruebas nuevas) y `CHANGELOG.md` (+7).
  Comprobado con `git diff HEAD~1 HEAD --name-only`: **sin** `models/`, `alembic/`,
  `web/ajustes.py`, `services/seguridad.py` ni `config.py`.
* **CSS**: la sección usa solo clases ya existentes en `static/web.css`:
  `.edicion-manuales` (l. 2354), `.edicion-form` (l. 2347-2350), `.edicion-dos` (l. 2351),
  `.edicion-acciones` (l. 2353), `.campo-error` (l. 2352), `.titulo-frase`, `.muted`, `.caption`,
  `.btn`/`.ghost` (definidas antes). No se añade ninguna regla nueva.
* **Pruebas nuevas** (`test_web_arcos.py:183-303`): formulario y botón neutro, acciones
  existentes, redirect `?guardado=numero`, paso de posición al servicio, posición no numérica,
  re-render con valores y aviso, y aviso general neutro.
* El endpoint `POST /ui/arcos/{id}/numeros` y el servicio `agregar_numero` ya existían; el arreglo
  es de superficie (plantilla + contexto de la vista), y el E2E confirma que el flujo completo
  funciona sin tocarlos.

---

## 4. Observaciones (ninguna bloqueante)

**O1 — Posición no numérica en el navegador.** El campo es `type="number"`, así que un navegador
no enviaría «al-final»; el servidor la trata como vacía (`isdigit()` → `None`) y la pone al final,
que es el comportamiento seguro. La prueba y la sonda lo POSTean directamente. Correcto.

**O2 — No hay prueba `_pg` commiteada para esta pantalla.** La suite usa el servicio sustituido
(`AsyncMock`), como el resto de tests web; mi E2E con Postgres real valida el empalme
plantilla→endpoint→servicio→BD, pero no queda como regresión de CI. No bloquea: la lógica de
servicio ya estaba cubierta por `test_arcos_pg.py`/su suite.

**O3 — `aviso` explícitamente vacío en el re-render de error.** El commit añade `"aviso": ""`
(`web/arcos.py:230`) para que un POST fallido no arrastre un aviso de éxito anterior; verificado
en el E2E (POST inválido → solo el aviso de error).

**O4 — «Solo cambia el orden de lectura en ZascArr…».** El texto de garantía («no se toca ningún
número ni archivo») está junto al formulario, como pide el presupuesto de texto de la UI; el E2E
confirma que no se toca `files` ni las series/números.

---

## 5. Veredicto

**APTO.** El arreglo cumple la aceptación: GET con formulario «Añadir un número» (Serie/Número/
Posición) y botón neutro sin `.primary`; POST válido añade y redirige a `?guardado=numero`; POST
con serie inexistente re-renderiza con aviso en español llano conservando `serie`/`numero`/`orden`;
posición vacía y no numérica van al final; acciones existentes intactas; sin migraciones ni cambios
en `models`/`ajustes`/`seguridad`; solo clases CSS ya existentes. Suite completa verde dos veces
con contadores idénticos (6802 passed / 2280 skipped), `test_web_arcos.py` aislada verde (16
passed) y `ruff check src/` limpio.
**Bloqueantes: ninguno.** Observaciones O1-O4 no bloqueantes.

---

## 6. Comandos reproducibles

```
cd .worktrees/arcos-anadir
PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_web_arcos.py
PYTHONPATH=src … -m ruff check src/
# E2E (contenedor Postgres, base temporal; se borra al terminar):
TEST_DATABASE_URL=postgresql://…/zascarr_qa_arcos_test PYTHONPATH=src <venv>/bin/python \
    .qa-arcos/e2e_ui_pg.py      # 14/14 OK
```

---

## 7. Inventario

`8108c73f` · rama `fix/arcos-anadir-numero`: `CHANGELOG.md`, `src/zascarr/web/arcos.py`,
`src/zascarr/web/templates/arco.html`, `tests/test_web_arcos.py` (+174/−0). Sin cambios en
modelos, migraciones, Ajustes ni seguridad.
