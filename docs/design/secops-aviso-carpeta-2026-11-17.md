# SecOps — Dictamen de PR #984: aviso de carpeta de Transmission

> **Informe reconstruido** tras retirarse `.worktrees/carpeta` después de la fusión (el original quedó
> sin commitear). Reproduce el dictamen emitido sobre el SHA final y sus dos addenda; el worktree de
> cierre está en `main` (`eb454fbe`), con PR #984 fusionada en `3cb7f9fb`.

**Rol:** SecOps · **Tarea:** task-64 · **Fecha:** 2026-11-17
**SHA final dictaminado:** **`9b91a8264cb4510e1aaee7ab52ac15d1ab7dd6cb`** (PR #984, `headRefOid`
verificado antes de la fusión; merge en `main`: **`3cb7f9fb`**, `mergedAt 2026-11-17T09:12:54Z`).
**Worktree de cierre:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/cierre`, HEAD `eb454fbe`.
**Cambio final de la PR:** 6 ficheros, **+171/−12**: `CHANGELOG.md`,
`services/runtime_settings.py`, `web/ajustes.py`, `templates/ajustes.html`,
`tests/test_ajustes_carpeta_descargas.py` y `tests/test_web_ajustes.py`. Toca `web/ajustes.py` →
**§5.8 aplica**.
**Entorno de la revisión:** `PYTHONPATH=src` con el venv de pruebas del repo (Python 3.14, pytest 9.2,
ruff 0.17.5). Sin `TEST_DATABASE_URL`.
**Sin código ni commits**; este informe es el único fichero escrito.

---

## 0. Veredicto final

**FAVORABLE para `9b91a8264cb4510e1aaee7ab52ac15d1ab7dd6cb`; §5.8 FAVORABLE; sin bloqueantes ni
observaciones pendientes.** La funcionalidad de carpeta de descargas de Transmission queda completa:
campo validado y persistido por `RuntimeSettingsService`, aviso de «Probar conexión» que solo compara
rutas y no revela credenciales, y `_test_transmission` con 3-tupla que tolera respuestas no-JSON o con
tipos anómalos sin 500. **B-1** (500 al guardar por whitelist incompleta), **O-1** (Probar no validaba la
ruta), **O-2** (`/` aceptada) y **m-1** (500 con respuestas anómalas) quedaron **cerrados** en los
addenda de `dd2752e4` y `9b91a826`. Autenticación, sesión, reautenticación y secretos no cambian.

---

## 1. Historial de dictámenes (trazabilidad)

1. **`5906fc97` — NO FAVORABLE (B-1).** `transmission_download_dir` no estaba en
   `OVERRIDABLE_FIELDS["transmission"]`; `guardar_transmission` lo pasaba a `save()`, que lanza
   `ValueError` para claves desconocidas. Probe: `POST /ui/ajustes/guardar/transmission` con ruta
   válida (`/media/comics`) → **500**; con ruta inválida (`/media/../etc`) → 200 (sale antes de `save`).
   Además m-1 (`r.json()` no protegido) y O-1/O-2.
2. **`dd2752e4` — FAVORABLE con residual m-1.** Se añadió el campo a
   `OVERRIDABLE_FIELDS["transmission"]` y el test de guardado válido → 200 con
   `get_settings().transmission_download_dir` aplicado (**B-1 cerrado**); «Probar» valida la ruta antes
   de red y `/` deja de ser válida (**O-1/O-2 cerrados**); `r.json()`/no-dict ya devuelve mensaje llano.
   Quedaba un residual: un JSON **objeto** con `arguments` no-dict o `download-dir` no-str lanzaba
   `AttributeError`/`TypeError` y podía dar 500.
3. **`9b91a826` — FAVORABLE final.** `_test_transmission` valida `arguments` como `dict` y
   `download-dir` como `str | None`; respuestas anómalas devuelven 200 con «respuesta inesperada»
   (**m-1 cerrado**). Tests nuevos para `arguments: "x"` y `download-dir: 123`. Sin observaciones.

---

## 2. Verificación por criterio (SHA final)

### 2.1 Campo, validación y guardado

* `transmission_download_dir` existe en `config.py` (default `/media/downloads/comics`), se pinta en
  `ajustes.html` con Jinja autoescape y se recibe como `Form` explícito en `guardar_transmission`
  (`web/ajustes.py:670`) y `probar_transmission` (`:981`).
* `_carpeta_de_descargas_valida` (`:1123-1128`) exige ruta absoluta (`startswith("/")`), rechaza `..` en
  `PurePosixPath(...).parts`, rechaza **la raíz `/`** y cualquier carácter de control (`ord(c) < 32`).
  Pruebas en `tests/test_ajustes_carpeta_descargas.py` (absoluta, relativa, `..`, `/`, `\x01`).
* `guardar_transmission` valida antes de escribir (`:674-682`); con ruta inválida devuelve 200 con aviso
  y no guarda. El campo está en `OVERRIDABLE_FIELDS["transmission"]`
  (`services/runtime_settings.py:53-56`) y por tanto en `_ALL_FIELDS`; `save()` (`:147-149`) ya no lanza
  `ValueError`. Test `test_guardar_transmission_carpeta_valida_aplica`: POST válido → **200** y
  `get_settings().transmission_download_dir` aplicado. **B-1 cerrado.**

### 2.2 «Probar conexión» sin credenciales y con solo rutas

`probar_transmission` (`:978-999`) obtiene la contraseña con `_secreto_o_guardado` (no la devuelve), toma
la carpeta del formulario o la guardada y **valida la ruta antes de la red** (`:984-992`); con `/` o ruta
inválida devuelve el aviso sin llamar a Transmission (**O-1/O-2 cerrados**). `_test_transmission`
(`:1147-1190`) hace solo `session-get`; `_aviso_de_carpeta_transmission` (`:1132-1144`) compara
`PurePosixPath` de la ruta esperada y la de `arguments["download-dir"]` y devuelve un mensaje con ambas.
**No incluye usuario/contraseña ni la respuesta RPC completa**; `_ajustes_prueba.html` usa `{{ mensaje }}`
con autoescape. La ruta no persiste nada.

### 2.3 3-tupla y helpers de 2

`_test_transmission` devuelve `tuple[bool, str, bool]` en todos los caminos; `probar_transmission` lo
desempaqueta y pasa `aviso` al template. `_test_prowlarr` y `_test_amule` conservan `tuple[bool, str]` y
sus rutas (`/probar/prowlarr`, `/probar/amule`) no cambian. El test de respuestas anómalas cubre
`{"result":"success","arguments":"x"}` y `{"result":"success","arguments":{"download-dir":123}}` → 200 y
«respuesta inesperada»; el test `<html>no json</html>` cubre el no-JSON. **m-1 cerrado.**

### 2.4 §5.8, autenticación y secretos

El diff final no toca `services/seguridad.py`, `services/reautenticacion.py` ni la contraseña de acceso o
sesión; solo añade el campo al grupo `transmission`, su validación, el aviso y la robustez del helper. El
campo no es secreto; la contraseña de Transmission mantiene `_secreto_o_guardado`, `SECRET_FIELDS` y el
tratamiento existente de logs. No hay secretos en HTML ni en logs. **§5.8 favorable.**

### 2.5 Regresión y herramientas

* Ajustes/Estado: **127 passed** (suite focalizada de la revisión final; en el checkout de cierre se
  re-ejecutó con 128 por los tests nuevos de `main`, sin fallos).
* `ruff check src/` y `--select S`: **All checks passed!**
* La suite completa de `main` queda a cargo del Lead. Sin `models/` ni `alembic/` en la PR.

---

## 3. Conclusión

**Dictamen FAVORABLE para `9b91a8264cb4510e1aaee7ab52ac15d1ab7dd6cb`**, con **§5.8 favorable**, sin
condiciones. B-1, O-1, O-2 y m-1 cerrados; el campo se guarda por runtime settings, la ruta se valida
(absoluta, sin `..`/controles, sin `/`), el aviso no revela credenciales y los errores de respuesta de
Transmission no producen 500. La PR se fusionó en `3cb7f9fb`; cualquier cambio posterior a la fusión
exigiría nuevo dictamen. Este informe aplica al SHA final dictaminado y está sin commitear.
