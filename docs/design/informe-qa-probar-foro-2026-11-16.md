# Informe QA — #877: «Probar conexión» del foro (2026-11-16)

**Rol:** QA · **Tarea:** task-59 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/probar-foro`
**Rama:** `feat/probar-foro`, SHA **`a759b12a77473af295a7d2845b5b23a283147a04`** (verificado con
`git rev-parse HEAD`; PR #880 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL`.
El único fichero escrito es este informe; el scratch de QA (`.qa-probar/`) se borra al terminar.
**§5.8:** el commit toca `src/zascarr/web/ajustes.py` ⇒ SecOps debe dictaminar el SHA final antes de
fusionar (task-60).

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7181 passed, 2296 skipped**, 4 warnings, 0 fallos | 533,24 s (wall 8:53) |
| `pytest -q` (suite completa, 2.ª pasada) | **7181 passed, 2296 skipped**, 4 warnings, 0 fallos | 541,90 s (wall 9:01) |
| `pytest -q` suites de foro/ajustes/log (`test_web_ajustes_foro_probar`, `test_web_ajustes`, `test_forum_*`, `test_diagnostico_foro`, `test_log_acceso`) | **277 passed, 2 skipped** | 32,63 s (wall 34,50 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos; los 2296 skips
son los esperados sin `TEST_DATABASE_URL` (pruebas `*_pg`). Los 4 warnings son preexistentes
(`ComicInfo.xml` duplicado; `AsyncMock` sin await en importer), ajenos a #877.

---

## 2. Reproducción independiente — **13/13 OK**

Sonda propia con `TestClient` (base `http://localhost`, `Origin` de mismo origen), dobles de
`ForumScraper`/`_test_foro`/`_secreto_o_guardado` y `MockTransport`:

* La tarjeta Foro tiene el botón `hx-post="/ui/ajustes/probar/foro"`, `hx-include="closest form"`,
  `hx-target="#prueba-foro"`, `id="prueba-foro" aria-live="polite"`, indicador `#prueba-foro-espera`
  («Probando…») y el desplegable «Solo inicia sesión».
* URL inválida (`ftp://…`) → mensaje llano **sin instanciar** el scraper.
* Usuario/contraseña ausentes → «Falta el usuario o la contraseña», sin login.
* Login OK con URL con `/` final y usuario con espacios → `permitir_apagada=True` y **una sola**
  llamada a `login` (sin búsqueda).
* Credenciales rechazadas → «No se pudo iniciar sesión…».
* Cortesía (12 s), flood (42 s), robots, origen ajeno, `httpx.ConnectError` y `RuntimeError` →
  mensajes en llano, sin excepción.
* Ruta POST OK → 200 con `✓`, sin la contraseña; credenciales mal → 200 con `✗`, sin contraseña;
  cortesía → 200 con `ajustes-aviso` neutro y «12».
* Contraseña vacía → `_secreto_o_guardado` aporta la guardada; la ruta no persiste nada.
* `ForumScraper` normal conserva `permitir_apagada=False` (resto de usos intacto).
* Diff sin `models/`/`alembic/`; **sí** toca `web/ajustes.py` (§5.8).

---

## 3. Aceptación

* **Botón y contenedor.** `ajustes.html` añade `button type="button"` con
  `hx-post="/ui/ajustes/probar/foro"`, `hx-include="closest form"`, `hx-target="#prueba-foro"`,
  `hx-indicator="#prueba-foro-espera"`; fuera del `<form>` hay
  `<div id="prueba-foro" aria-live="polite">` y el indicador. Prueba:
  `test_web_ajustes_foro_probar.py::test_la_plantilla_tiene_boton_target_e_indicador` + sonda.
* **POST con valores del formulario, sin guardar.** `probar_foro` (`web/ajustes.py:735-746`) recibe
  `forum_url`, `forum_username`, `forum_password`; no usa `db` ni `RuntimeSettingsService`; el
  password vacío cae en `_secreto_o_guardado(..., "forum_password")` y `_test_foro` solo instancia
  `ForumScraper` + `login`. Pruebas: `test_contrasena_vacia_usa_la_guardada`, `_test_foro`.
* **Mensajes OK/credenciales/cortesía/flood/URL/red.** `_test_foro` (`:704-734`) cubre:
  `True` → «Conexión correcta…»; `login=False` → «No se pudo iniciar sesión…»; `ForumFloodControl`
  → «el foro pidió esperar ~N s»; `CortesiaEnEspera` → «hay que esperar ~N s por cortesía»;
  `AccesoProhibidoPorRobots` → robots; `OrigenNoPermitidoError`/URL inválida → dirección;
  `ErrorDePeticion`/`OSError`/`httpx.HTTPError` → «No se pudo conectar…»; `Exception` genérica →
  «No se pudo comprobar…». Todos 200 en la ruta, sin 500. Pruebas parametrizadas del fichero nuevo
  + sonda.
* **Aviso neutro de cortesía.** La ruta marca `aviso = (not ok) and mensaje.startswith("No se ha
  probado")`; la plantilla `_ajustes_prueba.html` pinta `ajustes-aviso` con `role="status"` para
  cortesía/flood. Prueba: `test_la_ruta_de_espera_usa_aviso_neutro` + sonda.
* **Contraseña vacía = guardada.** `_secreto_o_guardado` (mismo criterio que Guardar) y prueba
  específica; no se muestra ni se guarda.
* **Una sola petición de login, sin búsqueda.** `_test_foro` llama una vez a `scraper.login` y no a
  `buscar`/`login` adicional; el doble registra `[(URL, {"permitir_apagada": True})]`. Prueba:
  `test_login_ok_usa_permitir_apagada_y_solo_login` + sonda. (El `login()` real de IPB hace GET de
  entrada + POST de credenciales, ambas de login; no hay petición de búsqueda.)
* **Foro apagado.** `ForumScraper(..., permitir_apagada=True)` en `_test_foro`; la envoltura
  `_pedir` (`forum_scraper.py:382-384`) propaga `permitir_apagada` a `pedir_con_cortesia`; el resto
  de usos mantiene `False` por defecto. Prueba:
  `test_scraper_propaga_permitir_apagada_a_la_envoltura` + sonda.
* **Sin credenciales en la respuesta.** La ruta solo pasa `ok`/`mensaje`/`aviso` a
  `_ajustes_prueba.html`; `_test_foro` no incluye URL ni password en mensajes; los `logger.warning`
  solo llevan `integracion` y `error=type(exc).__name__`. Prueba de ruta con `CLAVE_SECRETA`
  ausente + sonda.
* **Sin migraciones/`models`.** El diff son 4 ficheros (**+264/−3**): `services/forum_scraper.py`
  (`permitir_apagada`), `web/ajustes.py` (ruta/helper), `templates/ajustes.html` y el test nuevo.
  Sin `models/` ni `alembic/`.
* **§5.8.** `web/ajustes.py` tocado; requiere dictamen de SecOps sobre el SHA final (task-60).

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — `login()` real hace dos peticiones HTTP** (GET de la página de entrada + POST de
credenciales), no una. La aceptación se interpreta como **un solo intento de login, sin búsqueda**
(que es lo que exige la historia: «solo inicia sesión, no busca ni gasta el intervalo de
búsqueda»); no hay ninguna llamada a búsqueda ni al scraper de temas. Si el criterio literal fuera
«una única petición HTTP», IPB no permitiría el login por formulario sin el GET previo.

**O2 — Confirmación por cookie de miembro.** `login()` devuelve `True` solo si aparece una cookie
de miembro con valor distinto de `""`/`"0"`; un foro que confirme el login sin esa cookie daría un
falso negativo (comportamiento preexistente de `ForumScraper.login`, no del botón).

**O3 — La validación de URL va antes que la de credenciales vacías**: con URL inválida y campos
vacíos gana el mensaje de URL. Es coherente con «no hacer red con una URL inválida» y no cambia la
aceptación.

**O4 — `ForumScraper` se construye sin `espera_max_s` explícito** (hereda 30 s); la prueba manual
puede tardar como máximo lo que el resto de usos del foro. La cortesía/flood se muestra en llano.

**O5 — §5.8:** aunque no toca contraseña/sesión/whitelist, `web/ajustes.py` es superficie de
seguridad; el dictamen de SecOps (task-60) es preceptivo.

---

## 5. Veredicto

**APTO.** #877 cumple la aceptación: botón y `#prueba-foro` con `aria-live` en la tarjeta Foro;
POST con valores del formulario sin guardar; OK, credenciales mal, cortesía (aviso neutro con 12 s),
flood, URL inválida y red devuelven mensajes llanos y 200, sin 500; contraseña vacía usa la guardada;
una sola llamada a `login` sin búsqueda; funciona con el foro apagado (`permitir_apagada=True`) y el
resto de usos conserva `False`; la respuesta no contiene contraseña ni URL con query; sin
migraciones ni `models`. Suite completa verde **dos veces** con contadores idénticos (7181 passed /
2296 skipped, 0 fallos), suites de foro/ajustes/log verdes (277 passed, 2 skips `_pg` documentados) y
`ruff check src/` limpio.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 el `login()` real usa GET+POST (un solo
intento, sin búsqueda); O2 confirmación por cookie de miembro (preexistente); O3 URL inválida se
avisa antes que credenciales vacías; O4 `espera_max_s` heredado de 30 s; O5 §5.8 exige dictamen de
SecOps (task-60).

---

## 6. Comandos reproducibles

```
cd .worktrees/probar-foro
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_web_ajustes_foro_probar.py tests/test_web_ajustes.py \
    tests/test_forum_scraper.py tests/test_forum_ajustes_http.py tests/test_forum_cortesia.py \
    tests/test_forum_flood.py tests/test_forum_charset.py tests/test_forum_intervalos.py \
    tests/test_diagnostico_foro.py tests/test_log_acceso.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-probar/probe.py      # 13/13 OK
```

---

## 7. Inventario del cambio revisado (`a759b12a`)

4 ficheros, **+264 / −3**: `src/zascarr/services/forum_scraper.py` (parámetro
`permitir_apagada` y propagación a `_pedir`), `src/zascarr/web/ajustes.py` (`_test_foro` y ruta
POST `/probar/foro`), `src/zascarr/web/templates/ajustes.html` (botón, contenedor/indicador,
desplegable) y `tests/test_web_ajustes_foro_probar.py` (183 líneas). Sin `models/` ni `alembic/`.
