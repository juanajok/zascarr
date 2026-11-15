# Informe QA — #843: pantalla de importación de guías de lectura (2026-11-15)

**Rol:** QA · **Tarea:** task-49 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/guia-ui`
**Rama:** `feat/guia-ui`, SHA **`f976423c5367d038d84af9efc4dc198879797ecd`** (verificado con
`git rev-parse HEAD`; PR #846 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL`.
El único fichero escrito es este informe; el scratch de QA (`.qa-guia/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7101 passed, 2289 skipped**, 4 warnings, 0 fallos | 314,42 s (wall 5:14) |
| `pytest -q` (suite completa, 2.ª pasada) | **7101 passed, 2289 skipped**, 4 warnings, 0 fallos | 336,45 s (wall 5:36) |
| `pytest -q tests/test_web_arcos_guia.py tests/test_web_arcos.py tests/test_reconciliacion_lecturas.py tests/test_reconciliacion_lecturas_pg.py tests/test_log_acceso.py` | **89 passed, 3 skipped** (los `*_pg` sin `TEST_DATABASE_URL`) | 16,33 s (wall 17,48 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
contaminación entre pruebas. Los 2289 skips son los esperados sin `TEST_DATABASE_URL` (pruebas
`*_pg`). Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en
importer), ajenos a #843.

---

## 2. Reproducción independiente — **12/12 OK**

Sonda propia con `TestClient` (base `http://localhost`, `Origin` de mismo origen y
`follow_redirects=False` en el POST):

* **GET** `/ui/arcos/importar-guia` → 200, formulario con `fuente` (Reading Orders/Continuity
  Guide), `url`, aviso de Ajustes y **exactamente un** `class="btn primary"`.
* **Enlace** desde `/ui/arcos` («Sagas en orden») → `href="/ui/arcos/importar-guia"` y texto
  «Importar una guía».
* **POST válido** (servicio monkeypatched, `ResultadoReconciliacion` con `arco_id`) → **303** a
  `/ui/arcos/{arco_id}?importada=1&enlazados=3&omitidos=1&motivos=…` (motivo legible
  «números que no tienes»), servicio llamado una vez.
* **Fuente apagada** → 200 con «apagada» y servicio **no** llamado.
* **Host ajeno**, **http/URL con query** → 200 con «no es una guía válida» y servicio **no**
  llamado; **fuente desconocida** (`fandom_dc`) → 200 con «Elige una de las dos fuentes».
* **Guía sin entradas** (`leer_y_reconciliar` → `None`) → 200 con «no tiene entradas legibles»,
  sin `Location`.
* **`CortesiaEnEspera`** (12 s) → 200 con «pide esperar ~12 s», sin 500.
* **Compatibilidad**: `ResultadoReconciliacion(...)` sin `arco_id` sigue construyéndose
  (`arco_id is None`); `scripts/reconciliar-lecturas.py --help` funciona; el fichero de test
  existente solo añade una aserción (`resultado.arco_id == arcos[0].id`).
* **Diff** sin `web/ajustes.py`, `models/` ni `alembic/`.

---

## 3. Aceptación

* **GET + enlace.** `web/arcos.py` registra `GET /importar-guia` (`arcos.py:174-180`) y
  `arcos.html` añade el enlace «Importar una guía» (`arcos.html:8`). La plantilla
  `importar_guia.html` tiene un solo botón `.btn primary`.
* **POST válido → 303 con resumen.** `importar_guia` (`arcos.py:183-241`) valida, lee/reconcilia,
  hace `commit` y redirige con `urlencode` a
  `/ui/arcos/{arco_id}?importada=1&enlazados=N&omitidos=M&motivos=…`; `arco.html` pinta
  «Guía importada: N números enlazados, M omitidos. Motivos: …» con `ui.aviso("ok", …,
  foco=true)`. `ResultadoReconciliacion.arco_id` se rellena en `reconciliar_guia`
  (`reconciliacion_lecturas.py:203,283-288`) con el id ya asignado (`uuid4` al crear).
* **Entradas inválidas → 200 sin servicio.** El orden es: fuente desconocida → mensaje; URL
  inválida/host ajeno/query → mensaje; fuente apagada → mensaje. En los tres casos se retorna
  antes de construir el extractor o llamar a `leer_y_reconciliar` (probado con `AsyncMock` y
  `await_count == 0`). Mensajes en llano, sin códigos internos.
* **Guía sin entradas.** Los extractores devuelven `None` si no hay entradas
  (`comicbookreadingorders.py:107-108`; `continuity_guide.py` análogo); la ruta responde con
  «La guía no tiene entradas legibles o no se pudo leer» y `rollback`, sin redirección.
* **`CortesiaEnEspera`.** Se captura antes del genérico (`arcos.py:205-210`), se hace
  `rollback` y se muestra el mensaje con segundos redondeados (`max(1, round(...))`); no hay 500.
  También se capturan `AccesoProhibidoPorRobots` y `ErrorDePeticion` con mensajes propios.
* **`arco_id` nuevo.** Campo con default `None` al final del dataclass; el script
  `scripts/reconciliar-lecturas.py` no lo usa y sigue funcionando; la prueba de reconciliación
  solo añade la aserción del id. Sin migraciones (`arco_id` es de resultado, no de modelo).
* **Un solo `.primary`.** El formulario tiene un único `button.btn.primary`; la sonda cuenta
  exactamente 1 en el HTML de la pantalla.
* **Sin tocar `web/ajustes.py`/`models`/migraciones.** `git diff HEAD~1 HEAD --name-only` no
  incluye ninguno; los 8 ficheros son `services/reconciliacion_lecturas.py`, `web/arcos.py`, tres
  plantillas y tres ficheros de pruebas (incluido `test_web_arcos_guia.py` nuevo).

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — Orden de validaciones.** La URL se valida antes de comprobar si la fuente está apagada;
con ambos problemas a la vez el mensaje es «no es una guía válida» (no «apagada»). No afecta a la
aceptación (no se llama al servicio en ningún caso), pero podría ser más útil avisar primero de
la fuente apagada.

**O2 — `except Exception` genérico.** Cualquier fallo inesperado del extractor/servicio se
traduce a un mensaje llano y se registra con `logger.exception("arcos.importar_guia_failed")`;
correcto de cara al usuario, pero oculta el tipo en la respuesta (a propósito).

**O3 — Construcción del extractor fuera del `try`.** `_EXTRACTORES_DE_GUIA[fuente](
CacheHttp(...))` se evalúa antes del bloque `try`; si esa construcción fallara (p. ej. ajustes
inválidos), sería un 500. En el flujo actual no lanza; se puede mover dentro del `try` como
mejora defensiva.

**O4 — `motivos` limitado a 400 caracteres** en la URL y en la vista; evita URLs gigantes y
pérdida de foco; el resumen de recuentos no se trunca.

---

## 5. Veredicto

**APTO.** #843 cumple la aceptación: GET y enlace desde «Sagas en orden»; POST válido → **303** a
`/ui/arcos/{arco_id}?importada=1&enlazados=N&omitidos=M&motivos=…` con resumen legible en la saga;
fuente apagada, URL inválida/host ajeno/query y fuente desconocida → 200 con mensaje llano **sin
llamar al servicio**; guía sin entradas → mensaje; `CortesiaEnEspera` → mensaje con segundos sin
500; `arco_id` opcional no rompe script ni tests (script `--help` y `ResultadoReconciliacion` sin
id); un solo `.primary`; sin tocar `web/ajustes.py`, `models/` ni migraciones. Suite completa verde
**dos veces** con contadores idénticos (7101 passed / 2289 skipped, 0 fallos), suites tocadas
verdes (89 passed, 3 skips `_pg` documentados) y `ruff check src/` limpio.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 orden de validaciones (URL antes que
fuente apagada, con ambos problemas gana el mensaje de URL); O2 `except Exception` genérico con
mensaje llano (a propósito); O3 el extractor se construye fuera del `try` (hoy no lanza; mejora
defensiva); O4 `motivos` se trunca a 400 caracteres en URL/vista.

---

## 6. Comandos reproducibles

```
cd .worktrees/guia-ui
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_web_arcos_guia.py tests/test_web_arcos.py \
    tests/test_reconciliacion_lecturas.py tests/test_reconciliacion_lecturas_pg.py \
    tests/test_log_acceso.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-guia/probe.py      # 12/12 OK
```

---

## 7. Inventario del cambio revisado (`f976423c`)

8 ficheros, **+338 / −3**: `src/zascarr/services/reconciliacion_lecturas.py` (`arco_id`),
`src/zascarr/web/arcos.py` (GET/POST y resumen), `web/templates/{arco,arcos,importar_guia}.html`
y `tests/{test_log_acceso,test_reconciliacion_lecturas,test_web_arcos_guia}.py`. Sin
`web/ajustes.py`, `models/` ni `alembic/`.
