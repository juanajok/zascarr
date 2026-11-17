# SecOps — Revisión ligera de #854: parcial de Herald y pasada UI/UX

**Rol:** SecOps · **Tarea:** task-57 · **Fecha:** 2026-11-15 (02:51–03:20, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/uiux` (rama `feat/uiux`)
**SHA dictaminado:** **`77a128b053fe9ce57d188fffca1ba5720b2c0a75`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 856` → `headRefOid = 77a128b053fe9ce57d188fffca1ba5720b2c0a75`, base `main`,
`state=OPEN`, `mergeable=MERGEABLE` (`mergeStateStatus=UNSTABLE`: checks en curso). Árbol limpio.
**Cambio:** `535491cb` (feature, 20 ficheros, +475/−197) + `77a128b0` (informe QA); total **22 ficheros,
+764/−197**. No toca `web/ajustes.py`, `services/seguridad.py`, `services/reautenticacion.py`, `models/`
ni migraciones (solo `templates/ajustes.html` textual); **§5.8 no aplica**.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python` (Python 3.14,
pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL`.
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito y queda
sin commitear.

---

## 0. Veredicto

**FAVORABLE para `77a128b0`.** Sin bloqueantes ni hallazgos de seguridad: el parcial de Herald es una
ruta fija sin parámetros de usuario, con clientes de allowlist, `espera_max_s=10`, `Cache-Control:
no-store`, vacío si la fuente está apagada o falla (sin peticiones), y `/ui/arcos` ya no hace red; los
títulos/enlaces se escapan con Jinja y no hay `|safe`, `href` vacío, `javascript:` ni hotlinking; los
cambios de foco/`aria-live`/nombres son coherentes (un solo `autofocus`), no hay `Form` nuevo ni
`hx-disabled-elt`; **§5.8 n/a**. Queda una observación **m-1** de accesibilidad (el error htmx no marca
`aria-invalid` en el campo, aunque mueve el foco y lo anuncia) y las observaciones O2–O5 de QA; ninguna
de seguridad. Condición de vigencia: cualquier commit/rebase posterior exige repetir el dictamen.

---

## 1. Hallazgos

### 1.1 Bloqueantes / mayores

**Ninguno.**

### 1.2 Menores

#### m-1 — El error htmx no actualiza `aria-invalid`/`aria-describedby` del campo

En `GET /ui/arcos/importar-guia` el campo URL lleva `aria-invalid="true"` y
`aria-describedby="importar-error"` si hay `errores` (`importar_guia.html:26-29`), pero en la respuesta
**htmx** de error se devuelve solo `_importar_guia_resultado.html` (`web/arcos.py:164-170`), que pinta el
`ui.aviso` con `foco=true` pero no modifica el `<input>` ya presente. El mensaje se anuncia (foco y
`aria-live` del contenedor) y no hay 500; el campo no queda marcado como inválido para lectores que
consulten su estado. Es la observación O1 de QA. **Recomendación:** incluir en el parcial un
`hx-swap-oob` del input (o devolver el formulario completo) con `aria-invalid`/`aria-describedby`. No es
seguridad.

### 1.3 Observaciones no bloqueantes (de QA, verificadas)

* **O2 — `hx-disable="find button"`** en el formulario de importación (`importar_guia.html:15`) en vez de
  `hx-disabled-elt`; es el patrón del proyecto y mantiene el botón deshabilitado durante la petición.
* **O3 — Esqueleto de carga con `min-height`** y `:has(#…:empty)` para ocultar la sección vacía
  (`web.css:2401-2407`); sin impacto de seguridad; navegadores sin `:has` mostrarían el contenedor vacío.
* **O4 — Log genérico del parcial**: `_novedades_de_herald` captura fallos y registra
  `comicbook_herald.ui_sin_novedades` sin URL; el cliente de SCR5 registra host/estado, no la URL ni
  títulos. Correcto.
* **O5 — Sin parámetros**: la ruta del parcial no acepta query/form; usa el feed configurado y la
  allowlist de SCR5. Correcto.

---

## 2. Verificación por criterio

### 2.1 Parcial de Herald: ruta acotada, sin SSRF y sin bloquear Sagas

* `GET /ui/arcos/novedades-herald` (`web/arcos.py:181-189`) **no tiene parámetros**; llama a
  `_novedades_de_herald(espera_max_s=10.0)`, que comprueba `fuente_habilitada("comic_book_herald")`
  **antes** de instanciar `ComicBookHeraldClient` (`:117-135`). El cliente usa el feed configurado y la
  allowlist/URL de SCR5; no hay URL de usuario, no hay SSRF ni hosts ajenos.
* `_respuesta` fija `Cache-Control: no-store` (`:107-110`), también para este parcial.
* La fuente apagada devuelve `[]` antes de la red; `CortesiaEnEspera`/`FuenteApagada` y cualquier
  `Exception` devuelven `[]` sin 500; no genera datos sensibles (solo títulos/fechas/URLs públicas del
  feed, y las URL ya pasaron la validación de SCR5).
* `/ui/arcos` ya **no** llama a `_novedades_de_herald` (`arcos()` `:275+`); la sección se hidrata con
  `hx-get="/ui/arcos/novedades-herald"` + `hx-trigger="revealed once"` (`arcos.html:41-51`). Pruebas
  `test_el_marcado_de_novedades_es_perezoso`, `test_el_parcial_de_novedades_pinta_los_items`,
  `test_el_parcial_sin_novedades_devuelve_vacio`, `test_el_parcial_con_la_fuente_apagada_no_hace_red`,
  `test_el_parcial_ante_un_fallo_devuelve_200_vacio` (`tests/test_web_arcos.py:376-486`). **Pasa.**

### 2.2 HTML: escapado, sin `|safe`/`href` vacío/`javascript:`/hotlinking

`_novedades_herald.html` pinta `item.titulo` y `item.url` con Jinja autoescape; la URL viene validada por
`_url_del_articulo` de SCR5 (https/host/puerto/sin credenciales), y el enlace lleva
`target="_blank"`/`rel="noopener noreferrer"`. `arcos.html` no introduce títulos externos; `series_detail`
mantiene la atribución Fandom/relleno con `{% if datos.url_ficha %}` y licencia a constante https
(`:70-74`), sin `href=""`; `arco.html` escapa títulos/series en `aria-label`; `estado.html` pinta
`f.motivo_bloqueo` ya traducido por `_MOTIVOS_DE_BLOQUEO` (`cortesia_estado.py:114-121`). No hay `|safe`
ni `<img>`/hotlinking en los cambios. Pruebas `test_el_parcial…`, `test_la_atribucion…` y la sonda QA
(grep sin `|safe`/`href=""`/`javascript:`). **Pasa.**

### 2.3 Accesibilidad y forma

* **Foco:** `arco.html` reparte `foco=` entre aviso/importada/pedido para que solo uno lleve
  `autofocus` (`:6-14`); el formulario de importación y el parcial de error usan `foco=true`
  (`importar_guia.html:7`, `_importar_guia_resultado.html:1`); QA verificó un solo `autofocus` con
  ficha + importación + pedido simultáneos.
* **`aria-live`:** `#resultado-importar` y `#importar-espera` (`importar_guia.html:32-34`), y
  `#novedades-herald-contenido` (`arcos.html:46`).
* **Nombres únicos:** `aria-label` de subir/bajar/quitar incluye serie/número (`arco.html:78-84`); QA
  comprobó unicidad por fila; los `aria-label` de navegación de Sagas son únicos.
* **htmx:** `hx-disable="find button"` (`importar_guia.html:15`), sin `hx-disabled-elt`; `HX-Redirect`
  en éxito (`web/arcos.py:270`), parcial solo en error (`:164-170`).
* **Formularios:** no se añade ningún `Form` ni campo nuevo; `templates/ajustes.html` solo reorganiza
  textos y `role="group"`/ids; no hay secretos en HTML/logs. **Pasa** (m-1 en el estado `aria-invalid`
  del error htmx).

### 2.4 §5.8

El delta **no incluye** `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`; solo
`templates/ajustes.html` textual. **§5.8 no aplica**; sin formularios/secretos nuevos.

### 2.5 Regresión

* QA sobre `535491cb`: suite completa **7142 passed / 2296 skipped ×2**, 0 fallos, contadores idénticos;
  suites UI/CSS **592 passed**; `ruff check src/` limpio; sonda 15/15.
* Mi ejecución focalizada (`test_web_arcos`, `test_web_arcos_guia`, `test_web_series`,
  `test_web_ajustes_fuentes_nuevas`, `test_web_estado_cortesia`, `test_revision_ux_2026_11`,
  `test_web_ficha_447`, `test_forum_ajustes_http`): **183 passed** en 5,80 s; `ruff check src/` y
  `--select S` verdes. La suite completa del Lead sobre este SHA está en curso. Sin migraciones ni
  cambios en `models/`.

---

## 3. Coherencia con QA

QA dio **APTO** sobre `535491cb` (7142×2, 592 UI/CSS, sonda 15/15) con O1 (error htmx no refresca
`aria-invalid`; incluido como m-1), O2 (`hx-disable`), O3 (esqueleto/`:has`) y O4/O5 (log genérico y
ruta sin parámetros). Mis comprobaciones coinciden; no hay hallazgos de seguridad ni contradicciones.

---

## 4. Conclusión y trazabilidad

**Dictamen FAVORABLE para `77a128b053fe9ce57d188fffca1ba5720b2c0a75`**, con **§5.8 n/a**. El parcial de
Herald no añade superficie de red desde la UI, respeta `no-store`, no hace red con la fuente apagada ni
bloquea Sagas, y los cambios de HTML/accesibilidad son seguros/escapados. Recomendaciones no bloqueantes:
m-1 (`aria-invalid`/`aria-describedby` en el parcial htmx) y O2–O5. Este informe aplica solo a este SHA;
cualquier commit/rebase posterior exige nuevo dictamen. El informe está en el árbol de trabajo sin
commitear.

| Punto de task-57 | Sección |
|---|---|
| Parcial Herald: ruta acotada, sin SSRF, no-store, vacío sin red, Sagas sin red | 2.1 |
| HTML escapado, sin `|safe`/`href=""`/`javascript:`/hotlinking, `rel` | 2.2 |
| Accesibilidad/forma: foco, aria-live, labels únicos, htmx, sin Form nuevo | 2.3, m-1 |
| §5.8 n/a | 2.4 |
| ruff y regresión | 2.5, 3 |
