# Informe QA — #854: pasada UI/UX y Herald perezoso (2026-11-15)

**Rol:** QA · **Tarea:** task-56 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/uiux`
**Rama:** `feat/uiux`, SHA **`535491cbf2c22a125fa1eed1246a1d9400962da0`** (verificado con
`git rev-parse HEAD`; PR #856 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL`.
El único fichero escrito es este informe; el scratch de QA (`.qa-uiux/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7142 passed, 2296 skipped**, 4 warnings, 0 fallos | 338,28 s (wall 5:38) |
| `pytest -q` (suite completa, 2.ª pasada) | **7142 passed, 2296 skipped**, 4 warnings, 0 fallos | 336,12 s (wall 5:36) |
| `pytest -q` suites UI/CSS (css_contraste, css_previa, css_sistema_diseno, css_tokens, arcos, arcos_guia, estado_cortesia, revision_ux, ajustes*, series, ficha_447, htmx4, nombre_y_foco) | **592 passed** | 12,71 s (wall 14,39 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos; los 2296 skips
son los esperados sin `TEST_DATABASE_URL` (pruebas `*_pg`). Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado;
`AsyncMock` sin await en importer), ajenos a #854.

---

## 2. Reproducción independiente — **15/15 OK**

Sonda propia con `TestClient` (base `http://localhost`, `Origin` de mismo origen), parches de
`listar_arcos`, `_novedades_de_herald`, `fuente_habilitada`, `ComicBookHeraldClient`,
`detalle_arco` y `leer_y_reconciliar`:

* **(a)** `GET /ui/arcos` con `_novedades_de_herald` parcheado para **fallar si se llama** → 200: la
  página de Sagas ya no hace red por Herald.
* **(b)** `GET /ui/arcos/novedades-herald` con items simulados → 200, `Cache-Control: no-store`,
  `.novedades-lista`, enlaces con `target="_blank"`/`rel="noopener noreferrer"`, fecha `08/11/2026`;
  con lista vacía → 200 y **cuerpo exactamente vacío** (`""`, para que `:empty` oculte la sección);
  fuente apagada → vacío **sin instanciar** el cliente; cliente que falla (`RuntimeError`) → 200
  vacío, nunca 500. El marcado de `arcos.html` lleva `hx-get`, `hx-trigger="revealed once"`,
  `aria-live="polite"` y esqueleto; el CSS reserva `min-height: calc(5 * 2.75rem …)` y oculta con
  `:has(#novedades-herald-contenido:empty)`.
* **(c)** `ajustes.html`: GCD/Metron/OL rellenan huecos (texto actualizado), la ayuda separa
  «Metron, año, fin y sinopsis; Open Library, sinopsis y año», placeholder del foro
  `ya configurada (vacío = no cambiar)`, subgrupos `role="group"` con ids de metadatos/guías y nota
  HTTP estática del foro.
* **(d)** Importar: GET con `hx-post`, `hx-target="#resultado-importar"`, indicador
  `#importar-espera` y un solo `.btn primary`; error de URL → 200 con `autofocus` y
  `aria-invalid="true"`; error con `HX-Request: true` → solo el parcial con aviso, sin `<html>`;
  éxito htmx → 303 con `HX-Redirect` a la saga.
* **(e)** `series_detail.html`: una sola `class="atribucion-fuentes"`, `<summary>Aviso legal</summary>`
  y aviso legal dentro del `<details>`, atribución Fandom/relleno fuera.
* **(f)** `cortesia_estado._MOTIVOS_DE_BLOQUEO` mapea `429`/`flood`/`maxlag` a llano y
  `estado.html` pinta `f.motivo_bloqueo` bajo el estado.
* **(g)** Ficha de saga con `autofocus` + importación + pedido simultáneos → **un solo**
  `autofocus`; `aria-label` de subir/bajar/quitar incluyen serie y número y son únicos por fila.
* **(h)** `git diff HEAD~1 HEAD --name-only` no incluye `models/`, `alembic/` ni `web/ajustes.py`;
  contraste/14 px/`rel`/un primary cubiertos por las suites UI/CSS.

---

## 3. Aceptación

**(a) `/ui/arcos` sin red.** `arcos()` (`web/arcos.py:274-290`) ya **no** pasa `herald_items` ni
llama a `_novedades_de_herald`; la sección se carga con `hx-get` (`arcos.html:38-51`). Prueba:
`test_web_arcos.py::test_la_pagina_de_sagas_no_pide_el_feed` + sonda.

**(b) Parcial de Herald.** Ruta `GET /ui/arcos/novedades-herald` (`web/arcos.py:185-195`), sin `db`,
llama a `_novedades_de_herald(espera_max_s=10)` (`:117-135`); `_respuesta` fija
`Cache-Control: no-store` (`:107-110`). Fuente apagada ⇒ `[]` sin instanciar cliente; fallo
inesperado ⇒ `except Exception` loguea `comicbook_herald.ui_sin_novedades` y devuelve `[]`; el
parcial (`_novedades_herald.html`) no emite nada sin items. Marcado perezoso, `aria-live`, esqueleto
y CSS `:has` en `arcos.html`/`web.css`. Pruebas:
`test_el_marcado_de_novedades_es_perezoso`, `test_el_parcial_de_novedades_pinta_los_items`,
`test_el_parcial_sin_novedades_devuelve_vacio`,
`test_el_parcial_con_la_fuente_apagada_no_hace_red`,
`test_el_parcial_ante_un_fallo_devuelve_200_vacio` + sonda.

**(c) Ajustes.** Texto de GCD corregido («GCD, Metron y Open Library también rellenan huecos…»);
ayuda de Metron/OL separa campos (OL sin «fin»); placeholder de contraseña del foro corto; nota
HTTP estática junto al campo; subgrupos «Metadatos»/«Guías y novedades». Prueba:
`test_web_ajustes_fuentes_nuevas.py` (textos y `role="group"`) + sonda.

**(d) Importar.** `importar_guia.html` usa htmx (`hx-post`, `hx-target`, `hx-indicator`,
`hx-disable="find button"`), `aria-live` en `#resultado-importar`, aviso de error con `foco=true` y
`aria-invalid`/`aria-describedby` en la URL; `_respuesta_importar` devuelve el parcial
`_importar_guia_resultado.html` en htmx; el éxito añade `HX-Redirect` a la respuesta 303
(`web/arcos.py:164-169,266-273`). Pruebas en `test_web_arcos_guia.py` + sonda.

**(e) Ficha de serie.** Una sola caja `.atribucion-fuentes` con lista de Fandom y relleno, fuera del
`<details>`; el desplegable pasa a «Aviso legal» y contiene `legal_disclaimer("metadata")`
(`series_detail.html:64-88`). Prueba:
`test_revision_ux_2026_11.py::test_la_ficha_tiene_una_sola_caja_de_atribucion_y_details_coherente`
+ sonda.

**(f) Estado.** `_MOTIVOS_DE_BLOQUEO` (`cortesia_estado.py:114-119`) traduce `429`/`flood`/`maxlag` a
«La web nos pidió esperar» / «El foro pidió esperar» / «La wiki pidió bajar el ritmo»;
`estado.html` pinta `f.motivo_bloqueo`; prueba `test_web_estado_cortesia.py` + sonda.

**(g) Ficha de saga.** Prioridad de foco (`pedido` > `importación` > `guardado`) con un solo
`autofocus`; `aria-label` únicos por fila; h1 `titulo-frase` solo si >3 palabras; paginación sin
flechas de texto pero con `aria-label` en el `<nav>`. Prueba:
`test_revision_ux_2026_11.py` + sonda.

**(h) Transversal / alcance.** Contrastes, 14 px, un primary y `rel` intactos (suites CSS y de
pantalla); sin `models/`, `alembic/` ni `web/ajustes.py`; 20 ficheros (**+475/−197**), incluidas
plantillas, CSS y pruebas. La única zona de Ajustes tocada es `templates/ajustes.html` (textos y
grupos), no la ruta ni la whitelist.

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — El error htmx no actualiza `aria-invalid` del input.** El parcial
`_importar_guia_resultado.html` contiene el aviso con foco, pero no reemplaza el `<input>` de URL
(que conserva los atributos del GET inicial). En el POST de página completa sí aparece
`aria-invalid="true"`. La aceptación se cumple (foco en error/aria-invalid en el formulario y
parcial en htmx); si se quiere marcar el campo también tras htmx, habría que incluir el input en el
swap.

**O2 — `hx-disable="find button"` es el patrón del proyecto**, no `hx-disabled-elt`; la prueba lo
exige así y el comportamiento de htmx 4 vendorizado es coherente con el resto de formularios. No es
un fallo, pero conviene no mezclar ambos atributos en plantillas nuevas.

**O3 — El esqueleto reserva 5 filas; con menos novedades la sección se acorta** por debajo del
esqueleto (empuja el pie, no el contenido que se lee). Es el compromiso documentado en la
auditoría §5; a 320 px un título de tres líneas puede superar la reserva.

**O4 — El log `comicbook_herald.ui_sin_novedades` es genérico** (sin URL ni traza), coherente con
«sin feed no se pinta nada»; no permite distinguir fuente apagada de fallo salvo por el nivel.

**O5 — `novedades_herald` no acepta parámetros de paginación/forzado**; siempre feed topado a 5 y
caché de 6 h. Es el diseño de la historia.

---

## 5. Veredicto

**APTO.** #854 cumple (a)-(h): `/ui/arcos` ya no hace red para Herald (la sección es perezosa);
`GET /ui/arcos/novedades-herald` devuelve el parcial con items, vacío exacto si no hay feed/fuente
apagada/fallo, con `Cache-Control: no-store` y esqueleto CSS sin layout shift; Ajustes corrige los
textos de GCD/Metron/OL y el placeholder del foro; Importar tiene foco/`aria-invalid`, htmx con
indicador y `HX-Redirect`; la ficha pinta una sola caja de atribución y un `<details>` coherente;
Estado traduce `motivo_bloqueo`; la saga deja un solo `autofocus` y nombres accesibles únicos;
contraste/14 px/un primary/`rel` siguen verdes; sin migraciones, `models`, `web/ajustes.py` ni
seguridad. Suite completa verde **dos veces** con contadores idénticos (7142 passed / 2296 skipped,
0 fallos), suites UI/CSS verdes (592 passed) y `ruff check src/` limpio.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 el parcial htmx de error no actualiza
`aria-invalid` del input (sí el POST de página completa); O2 `hx-disable="find button"` es el patrón
del proyecto (no `hx-disabled-elt`); O3 el esqueleto reserva 5 filas y con menos la sección se
acorta por debajo (compromiso documentado, posible salto a 320 px con títulos de 3 líneas); O4 el
log `comicbook_herald.ui_sin_novedades` es genérico; O5 el endpoint no acepta forzado/paginación
(diseño de la historia).

---

## 6. Comandos reproducibles

```
cd .worktrees/uiux
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_web_css_contraste.py tests/test_web_css_previa.py \
    tests/test_web_css_sistema_diseno.py tests/test_web_css_tokens.py tests/test_web_arcos.py \
    tests/test_web_arcos_guia.py tests/test_web_estado_cortesia.py \
    tests/test_revision_ux_2026_11.py tests/test_web_ajustes.py \
    tests/test_web_ajustes_fuentes_nuevas.py tests/test_web_ajustes_fuentes_robots.py \
    tests/test_web_series.py tests/test_web_ficha_447.py tests/test_web_htmx4.py \
    tests/test_web_nombre_y_foco.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-uiux/probe.py      # 15/15 OK
```

---

## 7. Inventario del cambio revisado (`535491cb`)

20 ficheros, **+475 / −197**: `services/arcos.py` (`hay_guia`), `services/cortesia_estado.py`
(motivos), `static/web.css` (novedades/esqueleto/atribución/tabular), `web/arcos.py` (Herald
perezoso, htmx/HX-Redirect), 8 plantillas (`_importar_guia_resultado`, `_novedades_herald`,
`ajustes`, `arco`, `arcos`, `estado`, `importar_guia`, `series_detail`) y 9 ficheros de pruebas.
Sin `models/`, `alembic/` ni `web/ajustes.py`.
