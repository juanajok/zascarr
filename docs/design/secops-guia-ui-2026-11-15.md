# SecOps — Revisión ligera de #843: importación de guías desde la UI

**Rol:** SecOps · **Tarea:** task-50 · **Fecha:** 2026-11-15 (01:13–01:40, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/guia-ui` (rama `feat/guia-ui`)
**SHA dictaminado:** **`18219e076335d33b8f4b4f63ca33452e69a62735`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 846` → `headRefOid = 18219e076335d33b8f4b4f63ca33452e69a62735`, base `main`,
`state=OPEN`, `mergeable=MERGEABLE` (`mergeStateStatus=UNSTABLE`: checks en curso). Árbol limpio.
**Cambio:** `f976423c` (feature, 8 ficheros, +338/−3) + `18219e07` (informe QA); total **10 ficheros,
+491/−3**. No toca `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`; **§5.8
no aplica**.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python` (Python 3.14,
pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL`.
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito y queda
sin commitear.

---

## 0. Veredicto

**FAVORABLE para `18219e07`.** Sin bloqueantes ni hallazgos de seguridad: la URL se valida antes de
instanciar nada con `url_de_sitio_valida` (https, host de la allowlist del extractor, puerto 443, sin
query/userinfo/controles/`..`, rutas prohibidas y ruta de página) y la fuente contra
`ORIGENES_DE_GUIA`; no hay redirecciones ni hosts ajenos; los errores/cortesía/robots se pintan en llano
sin 500 en los caminos probados; la plantilla escapa con Jinja (sin `|safe`, sin imágenes), hay un solo
`.primary`, y el `Form` es explícito. **§5.8 n/a.** Quedan **m-1** (dos caminos fuera del `try` pueden
dar 500 en fallos inesperados: construcción del extractor y `commit`) y **m-2** (el `logger.exception`
genérico puede volcar trazas con URL/parámetros a logs); ambos menores y no bloqueantes. Condición de
vigencia: cualquier commit/rebase posterior exige repetir el dictamen.

---

## 1. Hallazgos

### 1.1 Bloqueantes / mayores

**Ninguno.**

### 1.2 Menores

#### m-1 — Dos caminos fuera del `try` pueden producir 500

La construcción del extractor se evalúa **antes** del bloque `try`:
`extractor = _EXTRACTORES_DE_GUIA[fuente](CacheHttp(async_session_factory))`
(`web/arcos.py:201`), y `await db.commit()` también está fuera (`:234`). Si el constructor o el `commit`
fallan (p. ej. error de BD), la excepción no se convierte en mensaje llano y la respuesta puede ser 500;
es la observación O3 de QA, ampliada al `commit`. No es alcanzable con una URL/fuente inválida (se rechaza
antes) ni con cortesía (se captura), por lo que el impacto es de robustez, no de seguridad.
**Recomendación:** mover construcción y `commit` dentro del `try` (o un `try` específico), hacer
`rollback` ante fallo de `commit` y mantener el mensaje llano.

#### m-2 — `logger.exception` genérico puede volcar trazas con datos de la petición

El `except Exception` hace `logger.exception("arcos.importar_guia_failed", fuente=fuente)`
(`web/arcos.py:222-224`); la respuesta al usuario es llana, pero el traceback puede incluir el mensaje
de una excepción con la URL de la guía o parámetros de SQL. La URL ya está validada (https/allowlist/sin
query) y no hay credenciales en juego, pero la política de logs del proyecto pide no arrastrar datos de
la petición. **Recomendación:** registrar `error=type(exc).__name__` (y como mucho `fuente`) sin
`exc_info`, como ya hace SCR4/SCR7. No es un fallo de seguridad actual.

### 1.3 Observaciones no bloqueantes (de QA, verificadas)

* **O1 — Orden de validaciones:** URL antes que fuente apagada; con ambos problemas gana el mensaje de
  URL. No hay llamada al servicio; solo UX.
* **O2 — `except Exception` genérico:** mensaje llano a propósito; oculta el tipo al usuario (correcto),
  con el matiz de logs de m-2.
* **O3 — Extractor fuera del `try`** (incluido en m-1).
* **O4 — `motivos` truncado a 400** en URL/vista; evita URLs gigantes; los recuentos no se truncan.
* **O5 (adicional) — El extractor se traga cortesía/robots/red.** `ExtractorGuias._descargar`
  (`reading_orders/comun.py:317-343`) captura `CortesiaEnEspera`/`AccesoProhibidoPorRobots`/
  `ErrorDePeticion` y devuelve `None`; la ruta muestra «La guía no tiene entradas legibles o no se pudo
  leer» en vez del mensaje específico de espera. Sigue siendo 200 y mensaje llano (no 500), pero el
  mensaje es menos preciso; las ramas `except CortesiaEnEspera`/robots de la ruta solo se ejercitan con
  dobles. No es seguridad.

---

## 2. Verificación por criterio

### 2.1 Allowlist/SSRF: solo hosts de las dos fuentes, sin redirecciones

* La fuente POST se valida contra `ORIGENES_DE_GUIA` (`arcos.py:184-187`), y `_HOSTS_DE_GUIA` toma
  `HOSTS_PERMITIDOS` y `RUTAS_PROHIBIDAS` de los extractores RO/CG (`:84-87`).
* `url_de_sitio_valida` (`reading_orders/comun.py:107-144`) exige `https`, host exacto de la allowlist,
  puerto `None`/443, **sin userinfo**, **sin query**, sin `..` (también `%2e%2e`, 3 pasadas), sin
  controles, sin extensión de recurso, fuera de `/api/`, `/search/`, `/admin/` y con ruta de página
  (`exigir_pagina=True`). Se llama **antes** de construir el extractor
  (`arcos.py:188-193`). El extractor vuelve a validar en `leer_guia` (`comun.py:359-363`).
* La descarga va por `pedir_con_cache`/`pedir_con_cortesia` sin `hosts_redireccion`: las redirecciones
  solo se aceptan al mismo origen (`peticiones.py:127-151`); no se piden enlaces de ítems ni hosts
  ajenos. Prueba `test_post_rechaza_un_host_ajeno` (`tests/test_web_arcos_guia.py:106-119`) y
  `test_post_rechaza_una_fuente_desconocida` (`:121-130`) confirman que el servicio no se llama.
  **Pasa.**

### 2.2 Errores sin trazas/URLs al usuario y sin 500 en los caminos probados

La ruta captura `CortesiaEnEspera` (mensaje «pide esperar ~N s»), `AccesoProhibidoPorRobots`, 
`ErrorDePeticion` y `Exception`; en todos hace `db.rollback()` y devuelve `200` con mensaje fijo
(`arcos.py:205-231`). Un `resultado` `None`/sin `arco_id` también devuelve 200 y `rollback` (`:228-233`).
No se interpola excepción ni URL; `url` solo se re-pinta escapada en el formulario. Pruebas
`test_post_sin_entradas_no_redirige` (`:132-143`) y `test_post_con_cortesia_avisa_de_la_espera_sin_500`
(`:144-157`). **m-1** deja dos fallos inesperados fuera del `try` (construcción/`commit`) que podrían dar
500; **m-2** afecta solo a logs. **Pasa en los caminos de aceptación.**

### 2.3 HTML: Jinja, sin `|safe` ni hotlinking

`importar_guia.html:7,9` pinta `errores.general` (fijo) y el aviso de fuente apagada por `ui.aviso`, que
usa `{{ texto }}` con autoescape (`_componentes.html:19-23`); `valores.url` se escapa en el `value`
(`:20`). `arco.html:8` pinta el resumen `importada.enlazados/omitidos/motivos` con `ui.aviso`, también
autoescapado. No hay `|safe` en las plantillas nuevas ni `<img>`/hotlinking; el resumen es texto. La
prueba `test_la_saga_muestra_el_resumen_de_la_importacion` (`tests/test_web_arcos_guia.py:159-171`) y la
cuenta de un único `.btn.primary` (`:43-56`). **Pasa.**

### 2.4 Forma, CSRF y `arco_id` opcional

`POST` usa `Form` explícito para `fuente` y `url` (`arcos.py:179-181`), sin `Model(**data)` ni
`setattr` de body; guarda solo vía el servicio de reconciliación, no mass assignment. La UI no tiene
token CSRF en ninguna pantalla (patrón existente), y esta pantalla sigue el mismo patrón; no introduce
uno nuevo. `ResultadoReconciliacion.arco_id` es un campo con default `None` al final del dataclass
(`reconciliacion_lecturas.py:71-74`) y `reconciliar_guia` lo rellena (`:203,284-288`); el script de
lecturas no lo usa y `--help` sigue funcionando; la prueba de reconciliación solo añade la aserción
(`tests/test_reconciliacion_lecturas.py`). **Pasa.**

### 2.5 §5.8

El delta **no incluye** `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`; solo
`web/arcos.py`, una plantilla nueva y un enlace en `arcos.html`. **§5.8 no aplica.**

### 2.6 Regresión

* QA sobre `f976423c`: suite completa **7101 passed / 2289 skipped ×2**, 0 fallos, contadores
  idénticos; suites tocadas **89 passed, 3 skips `_pg`**; `ruff check src/` limpio; sonda 12/12.
* Mi ejecución focalizada (`test_web_arcos_guia`, `test_web_arcos`, `test_reconciliacion_lecturas`,
  `test_log_acceso`): **89 passed, 2 skipped** en 22,46 s; `ruff check src/` y `--select S` verdes. La
  suite completa del Lead sobre este SHA está en curso. Sin migraciones ni cambios en `models/`.

---

## 3. Coherencia con QA

QA dio **APTO** sobre `f976423c` (7101×2, 89 tocadas, sonda 12/12) con O1 (orden de validaciones), O2
(`except Exception` genérico), O3 (extractor fuera del `try`) y O4 (`motivos` a 400). Mi m-1 amplía O3 al
`commit` y m-2 añade la preocupación de logs del genérico; O5 documenta que el extractor se traga
cortesía/robots y la ruta muestra el mensaje genérico. **Sin contradicción** y sin hallazgos de
seguridad.

---

## 4. Conclusión y trazabilidad

**Dictamen FAVORABLE para `18219e076335d33b8f4b4f63ca33452e69a62735`**, con **§5.8 n/a**. La pantalla de
importación no permite SSRF ni hosts ajenos, valida antes de pedir, no filtra trazas/URLs al usuario, no
usa `|safe` ni hotlinking y mantiene el patrón de `Form`/CSRF existente. Recomendaciones no bloqueantes:
m-1 (mover construcción/`commit` al `try` y rollback), m-2 (log sin traceback) y O1–O5. Este informe
aplica solo a este SHA; cualquier commit/rebase posterior exige nuevo dictamen. El informe está en el
árbol de trabajo sin commitear.

| Punto de task-50 | Sección |
|---|---|
| Allowlist/SSRF: hosts RO/CG, https, 443, sin query, rutas prohibidas, sin redirecciones | 2.1 |
| Errores/cortesía/robots sin trazas ni 500; rollback; logs | 2.2, m-1/m-2 |
| HTML escapado, sin `|safe`/hotlinking, un solo `.primary` | 2.3 |
| `Form` explícito, CSRF existente, `arco_id` opcional | 2.4 |
| §5.8 n/a | 2.5 |
| ruff y regresión | 2.6, 3 |
