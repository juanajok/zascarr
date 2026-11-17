# SecOps — Dictamen de #877: «Probar conexión» del foro

**Rol:** SecOps · **Tarea:** task-60 · **Fecha:** 2026-11-16 (00:15–00:45, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/probar-foro` (rama `feat/probar-foro`)
**SHA dictaminado:** **`d68c48126e726ff06a8cbf1d465356941528b07c`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 880` → `headRefOid = d68c48126e726ff06a8cbf1d465356941528b07c`, base `main`,
`state=OPEN`; GitHub aún calculaba `mergeable/mergeStateStatus=UNKNOWN` al consultarlo. Árbol limpio.
**Cambio:** `a759b12a` (feature, 4 ficheros, +264/−3) + `d68c4812` (informe QA); total **6 ficheros,
+428/−3**. Toca `web/ajustes.py` → **§5.8 aplica** y se dictamina favorable sobre este SHA.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python` (Python 3.14,
pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL`.
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito y queda
sin commitear.

---

## 0. Veredicto

**FAVORABLE para `d68c4812`.** Sin bloqueantes ni hallazgos de seguridad: la prueba usa los valores del
formulario sin persistir nada, la contraseña vacía toma la guardada pero **nunca** se refleja en HTML ni
en logs, la URL se valida con `_direccion_de_foro_valida` (http(s), sin userinfo/query/fragmento) antes de
crear el scraper, `permitir_apagada=True` solo se activa aquí (el resto de `ForumScraper` conserva
`False`), se hace **un único login** sin búsqueda y los errores/cortesía/flood se devuelven como 200 con
mensaje llano, sin trazas, URL sensible ni secretos. **§5.8 favorable**: no cambia contraseña de
acceso/sesión/reautenticación, no añade campos fuera del grupo `foro` ni `Form` nuevos, y no expone
secretos. Observación no bloqueante: `ForumScraper` hereda `espera_max_s=30` en esta prueba (QA O4); está
acotado, pero es mayor que los 10 s de las otras pruebas de Ajustes. Condición de vigencia: cualquier
commit/rebase posterior exige repetir el dictamen.

---

## 1. Verificación

### 1.1 Secretos: no persistencia, no reflejo

* `probar_foro` (`web/ajustes.py:748-760`) recibe `forum_url`, `forum_username`, `forum_password` con
  `Form` explícito, **no usa `db` ni `RuntimeSettingsService`** y solo delega en `_test_foro`; no guarda
  ajustes. La contraseña vacía pasa por `_secreto_o_guardado` (`:696-701`, mismo criterio que Guardar):
  usa la guardada, sin escribirla en ningún sitio.
* `_test_foro` (`:704-745`) no incluye la contraseña ni la URL en ningún mensaje; los `logger.warning`
  de error llevan solo `integracion="foro"` y `error=type(exc).__name__` (`:735-743`); `ForumScraper`
  registra como mucho el host (`login_no_confirmado`, etc.) y `pedir_con_cortesia` usa códigos cortos.
  La sonda QA y `test_la_ruta_ok_pinta_el_resultado`/`test_la_ruta_de_error_pinta_una_equis` confirman que
  `CLAVE_SECRETA` no aparece en la respuesta.
* La respuesta es `_ajustes_prueba.html` con `ok`/`mensaje`/`aviso`; `{{ mensaje }}` va con Jinja
  autoescape y los mensajes son constantes del servidor. No hay secretos en HTML.
* URL: `_direccion_de_foro_valida` (`:530-548`) exige http(s), sin userinfo/`@`, sin query ni fragmento;
  se comprueba **antes** de construir `ForumScraper` (`:710-713`). Una URL con credenciales/query se
  rechaza sin red. `ForumScraper` además aplica `url_de_foro_visible` al construir la base (defensa en
  profundidad). **Pasa.**

### 1.2 `permitir_apagada` solo en la prueba manual

`ForumScraper.__init__` añade `permitir_apagada: bool = False` y lo propaga a `_pedir` →
`pedir_con_cortesia` (`forum_scraper.py:329,352,385`). El único uso con `True` para el foro es
`_test_foro` (`web/ajustes.py:718`); el orquestador (`orchestrator.py:724`) y el diagnóstico
(`scripts/diagnostico_foro.py:181`) construyen el scraper con el valor por defecto `False`, y el gate de
`fuente_habilitada` de `pedir_con_cortesia` sigue intacto para el resto. La prueba
`test_scraper_propaga_permitir_apagada_a_la_envoltura` y `test_login_ok_usa_permitir_apagada_y_solo_login`
lo cubren. **Pasa.**

### 1.3 Red, cortesía y abuso

La prueba llama **una vez** a `ForumScraper.login` y **no** a `use_ipb_search` ni a búsqueda de temas
(`_test_foro:719`; prueba del scraper falso con una sola llamada). El `login()` real de IPB hace GET de
la página de entrada + POST de credenciales (QA O1): es un solo intento de login, sin tráfico de
búsqueda, como pide la historia. La cortesía va por `pedir_con_cortesia`; `CortesiaEnEspera` y
`ForumFloodControl` se convierten en aviso llano con los segundos (`:722-731`), y `AccesoProhibidoPorRobots`
y `ErrorDePeticion`/red también. La ruta devuelve siempre `200` con `_ajustes_prueba.html`; no hay 500
en los caminos probados. **Pasa.** Observación O4: `ForumScraper` hereda `espera_max_s=30` (la prueba no
lo baja a 10 como las otras); está acotado y es el mismo presupuesto del resto del foro.

### 1.4 §5.8 sobre `web/ajustes.py`

El diff de esta ronda en `web/ajustes.py` es **solo**: imports de `ForumFloodControl`/`ForumScraper`/
`OrigenNoPermitidoError` y `AccesoProhibidoPorRobots`, `_test_foro` y la ruta `POST /probar/foro`.
**No toca** contraseña de acceso, sesión ni reautenticación (no hay cambios en `services/seguridad.py`/
`services/reautenticacion.py`); **no añade** `Form` nuevos: usa `forum_url`/`forum_username`/
`forum_password`, que ya están en el grupo `foro` de la whitelist (`OVERRIDABLE_FIELDS`); no hay secretos
en HTML ni logs. La ruta no persiste. **Dictamen §5.8: favorable** para este SHA.

### 1.5 Regresión

* QA sobre `a759b12a`: suite completa **7181 passed / 2296 skipped ×2**, 0 fallos, contadores idénticos;
  suites de foro/ajustes/log **277 passed, 2 skips `_pg`**; `ruff check src/` limpio; sonda 13/13.
* Mi ejecución focalizada (mismas suites): **277 passed, 2 skipped** en 42,89 s; `ruff check src/` y
  `--select S` verdes. La suite completa del Lead sobre este SHA está en curso. Sin `models/` ni
  `alembic/` en el diff.

---

## 2. Coherencia con QA y observaciones

QA dio **APTO** sobre `a759b12a` (7181×2, 277 suites, sonda 13/13) con O1 (login real GET+POST, un solo
intento), O2 (confirmación por cookie de miembro, preexistente), O3 (URL antes que credenciales), O4
(`espera_max_s` heredado de 30 s) y O5 (§5.8 exige dictamen). Mis comprobaciones coinciden; no hay
hallazgos de seguridad nuevos. O4 queda como observación no bloqueante: si se quiere acotar más la
prueba manual, pasar `espera_max_s=10` como en Comic Vine/Metron; no es una debilidad actual.

---

## 3. Conclusión y trazabilidad

**Dictamen FAVORABLE para `d68c48126e726ff06a8cbf1d465356941528b07c`**, con **§5.8 favorable**. La
prueba no persiste ni refleja secretos, valida la URL antes de red, solo activa `permitir_apagada` en la
acción manual, hace un único login sin búsqueda y devuelve mensajes llanos sin 500. Observación no
bloqueante O4 (`espera_max_s=30` heredado). Este informe aplica solo a este SHA; cualquier commit/rebase
posterior exige nuevo dictamen. El informe está en el árbol de trabajo sin commitear.

| Punto de task-60 | Sección |
|---|---|
| Contraseña formulario/guardada nunca en HTML/logs; no persiste; URL sin query/credenciales | 1.1 |
| `permitir_apagada` solo en la prueba; resto conserva el gate | 1.2 |
| Un login, sin búsqueda; cortesía/flood; 200 sin trazas/URL/secretos | 1.3 |
| §5.8: acceso/sesión/reautenticación intactas, whitelist foro, sin Form/secretos | 1.4 |
| ruff, regresión y QA | 1.5, 2 |

---

## 4. Addendum de vigencia §5.8 (SHA 7876dfeb, tras rebase)

**Fecha:** 2026-11-16 (00:50–01:05, Europe/Madrid). **Tarea:** task-60 (ronda final).
**SHA dictaminado:** **`7876dfebc75f708e2a8151639ec2878f9eb53c88`** (`git rev-parse HEAD` en
`.worktrees/probar-foro`; `gh pr view 880` → `headRefOid = 7876dfebc75f708e2a8151639ec2878f9eb53c88`,
`mergeable=MERGEABLE`, checks en curso). Sustituye a `d68c4812` como SHA final.

**Delta `d68c4812..7876dfeb`:** **44 ficheros, +2514/−248**, todo procedente de `main` (cortes,
biblioteca, tests y merges #878/#859) más la resolución del conflicto de `CHANGELOG.md` (se conservaron
ambos lados). **Los ficheros de #877 no cambian**:

* `src/zascarr/services/forum_scraper.py`: `git diff --quiet d68c4812..7876dfeb` → **igual**.
* `src/zascarr/web/ajustes.py`: **igual** (incluida la ruta `/probar/foro` y `_test_foro`).
* `src/zascarr/web/templates/ajustes.html`: **igual** (botón/indicador/desplegable).
* `tests/test_web_ajustes_foro_probar.py`: **igual**.
* `docs/design/informe-qa-probar-foro-2026-11-16.md`: **igual**.

**§5.8 mantenido.** Al ser `web/ajustes.py` idéntico al SHA dictaminado, se mantienen las conclusiones
del §1.4: la prueba no persiste ni refleja contraseñas, usa solo campos del grupo `foro`, no crea `Form`
fuera de la whitelist y no toca contraseña de acceso/sesión/reautenticación; `permitir_apagada=True`
sigue limitado a la acción manual. No aparece ningún fichero nuevo de seguridad en el delta (el resto es
de `main`, fuera de la PR).

**Comprobaciones sobre el SHA rebasado:** `tests/test_web_ajustes_foro_probar.py` → **16 passed** (3,90 s);
`ruff check src/` → *All checks passed!*. La suite completa del rebase la está ejecutando el Lead (QA
había dado 7181×2 antes del rebase). Sin `models/` ni `alembic/` en la PR.

**Veredicto: FAVORABLE para `7876dfebc75f708e2a8151639ec2878f9eb53c88`**, con **§5.8 favorable**, sin
condiciones. El dictamen anterior sigue vigente en todo lo demás; este addendum aplica **solo** a este
SHA y cualquier commit/rebase posterior exigirá nuevo dictamen. El addendum está en el árbol de trabajo
sin commitear, a la espera de la PR documental.
