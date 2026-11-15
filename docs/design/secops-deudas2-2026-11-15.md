# SecOps — Revisión ligera del lote 2 de deudas

**Rol:** SecOps · **Tarea:** task-53 · **Fecha:** 2026-11-15 (01:55–02:25, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/deudas2` (rama `fix/deudas2`)
**SHA dictaminado:** **`6e61aadc95bf8ab32123da80590e21728af2c5da`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 850` → `headRefOid = 6e61aadc95bf8ab32123da80590e21728af2c5da`, base `main`,
`state=OPEN`, `mergeable=MERGEABLE` (`mergeStateStatus=UNSTABLE`: checks en curso). Árbol limpio.
**Cambio:** `3e2cebf7` (feature, 10 ficheros, +237/−23) + `6e61aadc` (informe QA); total **12 ficheros,
+415/−23**. No toca `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`, `models/`
ni migraciones; **§5.8 no aplica**.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python` (Python 3.14,
pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL`.
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito y queda
sin commitear.

---

## 0. Veredicto

**FAVORABLE para `6e61aadc`.** Sin bloqueantes ni hallazgos de seguridad: el lote no cambia identidad ni
datos de la serie fuera de `metadata_["relleno"]`, `_sin_huecos_cubribles` es una fecha ISO acotada sin
inyección, los clientes devuelven `None` en payloads vacíos sin borrar campos, la atribución inválida se
pinta como texto sin `href=""`/`javascript:`, y la importación de guías queda con extractor,
reconciliación y `commit` dentro del `try`, `rollback` y mensaje llano ante `RuntimeError`, sin traza ni
URL en el log. **§5.8 n/a.** Quedan observaciones no bloqueantes: **m-1** (`_enrich_huecos_por_id` no
actualiza `enrichment_attempted_at`, así que la rotación no avanza en series con fuente cortada), **m-2**
(la marca `_sin_huecos_cubribles` de 30 días no se limpia al encender después una fuente) y **O2** (`None`
de payload vacío se trata como 404 y deja TTL de 30 días, sin borrar datos). Condición de vigencia:
cualquier commit/rebase posterior exige repetir el dictamen.

---

## 1. Hallazgos

### 1.1 Bloqueantes / mayores

**Ninguno.**

### 1.2 Menores

#### m-1 — La rotación ordena por `enrichment_attempted_at` pero no lo actualiza

La consulta de `_enrich_huecos_por_id` ordena por
`Series.enrichment_attempted_at.asc().nullsfirst(), Series.id` (`enricher.py:452`) y reordena en Python
(`:459-464`), pero el bucle **no escribe** `enrichment_attempted_at` en las series que procesa. Esas
series tienen id GCD/Metron/OL, por lo que el lote primario —que sí marca el campo (`:674,736,747,758`)—
las excluye; el campo queda `NULL` y el orden efectivo es por `id`. Si una fuente se corta por un fallo
transitorio, la serie no recibe TTL y vuelve a ser la primera en el siguiente ciclo, consumiendo el
límite y pudiendo dejar sin turno a series posteriores (es la observación O1b de QA, agravada por la
falta de avance de la marca). No altera datos ni identidad; es disponibilidad del relleno. **Recomendación:**
marcar el intento al procesar (o excluir las fuentes `cortadas` y avanzar el cursor) para que la
rotación sea real.

#### m-2 — `_sin_huecos_cubribles` de 30 días puede omitir series tras encender una fuente

`_marcar_sin_huecos_cubribles` escribe `metadata_["relleno"]["_sin_huecos_cubribles"]` con la fecha
(`enricher.py:283-290`) y `_sin_huecos_cubribles_vigente` la respeta 30 días (`:266-280`). La marca se
pone cuando `_fuente_cubrible` (`:292-310`) no ve ninguna fuente cubrible, y esa función devuelve
`False` si la fuente está apagada o Metron no tiene token. Si el usuario enciende después esa fuente (o
pone el token), la serie sigue marcada hasta 30 días y no se rellena aunque ya tenga una fuente que la
cubra; no hay invalidación al cambiar Ajustes. Es la observación O2 de QA; no es seguridad, pero el
filtro puede omitir series que sí deberían rellenarse. **Recomendación:** limpiar/no poner la marca cuando
haya fuentes apagadas, o invalidarla al cambiar la configuración de fuentes.

### 1.3 Observaciones no bloqueantes

* **O2 — `None` de payload vacío deja TTL de 30 días.** Los clientes devuelven `None` en payload sin
  datos (`gcd.py:293-296`, `metron.py:185-188`, `open_library.py:161-164`), y `aplicar_relleno(None)`
  registra `campos=[]` con TTL (sonda: `campos=[]`, descripción/años intactos, TTL vigente a 29 días).
  No borra ni pisa datos; trata el vacío como 404 (documentado en `relleno_huecos.py`). Si el payload
  vacío fuera transitorio, quedaría una negativa de 30 días; es la decisión de la spec/QA, no un fallo de
  seguridad.
* **O1a de QA — prefetch de 500.** Las marcadas se saltan sin consumir `limit`, pero la consulta trae como
  máximo `max(limit*50,500)`; si hubiera más marcadas por delante, una pasada podría no llegar a
  candidatas posteriores. No afecta a la aceptación.
* **O3/O4 de QA:** la licencia se enlaza a constantes https (no `href=""`); `logger.error` en la guía es
  deliberado (sin traza). **Verificados.**

---

## 2. Verificación por criterio

### 2.1 O1: identidad/datos intactos, JSONB acotado y sin inyección

`_marcar_sin_huecos_cubribles` solo crea un **dict nuevo** de `metadata_` y escribe
`relleno["_sin_huecos_cubribles"] = ahora.isoformat()` (`enricher.py:283-290`); no toca `title`, ids,
`metadata_source`, `cover_url`, `total_issues` ni `locked_fields`, y no modifica campos de la serie.
`_fuente_cubrible` es una función de solo lectura (`:292-310`), y el bucle solo llama a
`aplicar_relleno` (lista cerrada/locks de SCR7) y a `db.flush`. La clave y el valor ISO están acotados y
pasan por JSONB parametrizado (sin SQL crudo): no hay inyección. Pruebas
`tests/test_relleno_huecos.py:408-431` (marcadas no consumen lote, no cambian datos; segunda pasada sin
peticiones) y sonda QA. El filtro de TTL/huecos cubribles no borra datos; **m-1/m-2** afectan a qué se
procesa, no a qué se escribe. **Pasa.**

### 2.2 O2: `None` no borra ni pisa datos

Los clientes GCD/Metron/OL devuelven `None` si el JSON no trae nombre/años/descripción/título
(`gcd.py:293-296`, `metron.py:185-188`, `open_library.py:161-164`). `aplicar_relleno(None)` no recorre
campos ni asigna nada; solo `_registrar` deja `campos=[]` y `ultimo_intento` (TTL 30 d; sonda propia:
descripción/años intactos, TTL vigente). No hay borrado ni `setattr` con `None`; el pipeline no toca
identidad. **Pasa**; el TTL del vacío es el comportamiento documentado, no un borrado.

### 2.3 O3: atribución visible sin URL, sin `href=""`/`javascript:`

`atribucion_de_relleno` incluye la fuente si hay `campos` aunque `_url_de_ficha` devuelva `None`, y deja
`url_ficha=""` (`atribucion.py:64-72`). `series_detail.html:72` usa
`{% if datos.url_ficha %}<a href=…>…</a>{% else %}{{ datos.nombre }}{% endif %}`: sin URL se pinta el
**nombre como texto**, sin `href` vacío; la licencia va a `url_licencia` constante https (`:73`;
`FUENTES_DE_RELLENO`). `_url_de_ficha` exige https/host esperado y sin credenciales, así que
`javascript:`/host ajeno se rechazan; no hay `|safe` ni imágenes. Pruebas
`tests/test_web_series.py:1343-1360` (`href=""` y javascript ausentes; licencia presente) y
`TestAtribucionRellenoSinUrl`. **Pasa.**

### 2.4 Guía UI: todo dentro del `try`, rollback y mensaje llano

En `web/arcos.py:200-243`, el extractor (`:201`), la lectura/reconciliación (`:202-203`), la comprobación
de `resultado`/`arco_id` (`:204-209`) y el `commit` (`:211`) están dentro del `try`; `RuntimeError` de
servicio o de commit cae en `except Exception` (`:230`), hace `rollback` (`:234`) y devuelve 200 con
«No se pudo importar la guía. Inténtalo de nuevo.»; el log es
`logger.error("arcos.importar_guia_failed", fuente=fuente, error=type(exc).__name__)` (`:232-233`), sin
`exc_info`, URL, query ni cuerpo. No hay estados parciales (commit atómico o rollback). Pruebas
`tests/test_web_arcos_guia.py:181-228` (commit/ servicio que lanzan → 200, rollback, sin 500; log sin
traza ni URL). La rama `resultado is None` también hace rollback. **Pasa.**

### 2.5 §5.8 y ficheros sensibles

El delta no incluye `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`, ni
`models/`/`alembic/`; solo servicios de enriquecimiento/clientes, `web/arcos.py`, `web/atribucion.py`,
una plantilla y tres tests. **§5.8 no aplica**; no hay secretos ni formularios nuevos.

### 2.6 Regresión

* QA sobre `3e2cebf7`: suite completa **7111 passed / 2289 skipped ×2**, 0 fallos, contadores
  idénticos; suites tocadas **236 passed**; `ruff check src/` limpio; sonda 9/9.
* Mi ejecución focalizada (`test_relleno_huecos`, `test_enricher`, `test_web_arcos_guia`,
  `test_web_series`, `test_health`): **220 passed** en 15,03 s; `ruff check src/` y `--select S`
  verdes. La suite completa del Lead sobre este SHA está en curso. Sin migraciones ni cambios en
  `models/`.

---

## 3. Coherencia con QA

QA dio **APTO** sobre `3e2cebf7` (7111×2, 236 tocadas, sonda 9/9) con O1a (prefetch), O1b (fuente
cortada cuenta como cubrible), O2 (marca de 30 días no se limpia al encender una fuente), O3 (licencia
siempre enlazada a constante) y O4 (`logger.error` deliberado). Mis m-1 (falta de actualización de
`enrichment_attempted_at`) y m-2 (marca con fuentes apagadas) amplían O1b/O2; la observación de TTL del
payload vacío confirma que no hay borrado. **Sin contradicción y sin hallazgos de seguridad.**

---

## 4. Conclusión y trazabilidad

**Dictamen FAVORABLE para `6e61aadc95bf8ab32123da80590e21728af2c5da`**, con **§5.8 n/a**. No hay
bloqueantes de seguridad: O1 no cambia identidad/datos fuera de `metadata_` y no inyecta; O2 no borra;
O3 pinta texto/licencia segura sin `href` vacío ni esquemas peligrosos; la guía UI revierte y devuelve
200 sin trazas/URL. Recomendaciones no bloqueantes: m-1 (marcar `enrichment_attempted_at` o excluir
fuentes cortadas), m-2 (invalidar la marca al cambiar fuentes) y O2 de payload vacío (TTL como 404,
documentado). Este informe aplica solo a este SHA; cualquier commit/rebase posterior exige nuevo
dictamen. El informe está en el árbol de trabajo sin commitear.

| Punto de task-53 | Sección |
|---|---|
| O1: identidad/datos intactos, JSONB acotado, TTL, sin inyección | 2.1, m-1/m-2 |
| O2: `None` sin borrados ni TTL indebido | 2.2, O2 |
| O3: atribución sin URL, sin `href=""`/`javascript:` | 2.3 |
| Guía UI: 200/rollback/log sin traza/URL/secretos | 2.4 |
| §5.8 n/a | 2.5 |
| ruff y regresión | 2.6, 3 |

---

## 5. Addendum de vigencia (SHA 079ca7a6) — cierre de m-1 y m-2

**Fecha:** 2026-11-15 (02:25–02:40, Europe/Madrid). **Tarea:** task-53 (ronda final). **PR:** #850.
**SHA dictaminado:** **`079ca7a6598e3010528525a6065b4c91373ec616`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 850` → `headRefOid = 079ca7a6598e3010528525a6065b4c91373ec616`, base `main`,
`state=OPEN`, `mergeable=MERGEABLE` (`mergeStateStatus=UNSTABLE`: checks en curso). El commit incluye este
informe de SecOps.

**Delta `6e61aadc..079ca7a6`:** 3 ficheros, **+256/−11**: este informe (+169), `services/enricher.py`
(+52/−11) y `tests/test_relleno_huecos.py` (+46). **El resto del árbol de deudas2 es idéntico**
(`git diff --quiet` para GCD/Metron/OL, `web/arcos.py`, `web/atribucion.py`, la plantilla y los tests de
guía/series no dio diferencias); §5.8 sigue **n/a**.

### 5.1 m-1 cerrado — la rotación avanza de verdad

`_enrich_huecos_por_id` asigna ahora `serie.enrichment_attempted_at = ahora` en los tres caminos:
- serie procesada (`enricher.py:513`),
- serie con huecos solo cubiertos por fuentes **cortadas** en el ciclo (`:508-510`; además `cortadas` se
  excluye de `cubribles` en `:496-503`, así que una fuente cortada no cuenta como cubrible ni consume el
  límite sin petición),
- serie marcada `_sin_huecos_cubribles` (`:504-506`).

La consulta ya ordenaba por `enrichment_attempted_at.asc().nullsfirst()` (`:452`), pero antes el campo no
se actualizaba para estas series (las del lote primario lo marcan en `:674,736,747,758`, pero el primario
las excluye por tener id). Ahora el lote avanza también cuando una fuente se corta. Prueba nueva
`test_m1_secops_la_serie_procesada_avanza_en_la_rotacion` (`test_relleno_huecos.py:451-462`); suite
`test_relleno_huecos` + `test_enricher` → **85 passed**. **m-1 cerrado.**

### 5.2 m-2 cerrado — la marca está ligada a las fuentes disponibles

La marca guarda ahora `{"fecha": iso, "fuentes": huella}` (`_marcar_sin_huecos_cubribles`,
`enricher.py:299-307`), con la huella de los clientes presentes en el ciclo
(`huella_fuentes = ",".join(sorted(...))`, `:475`). `_sin_huecos_cubribles_vigente`
(`:271-295`) exige que la huella coincida y la fecha esté dentro de 30 días; el **formato antiguo**
(string de fecha suelta) devuelve `False` y se reevalúa una vez. Así, encender después una fuente o
añadir el token de Metron cambia la huella y la serie se reevalúa, mientras que con las mismas fuentes
la marca sigue vigente y no consume lote ni red. Pruebas nuevas
`test_m2_secops_la_marca_caduca_si_cambian_las_fuentes_disponibles` y
`test_m2_secops_la_marca_vigente_con_mismas_fuentes_se_respeta` (`:464-500`). **m-2 cerrado.**

### 5.3 Resto del dictamen y veredicto

El cambio solo afecta al reloj de rotación y a la vigencia de la marca: no toca identidad/campos de la
serie, `CAMPOS_PROHIBIDOS`/locks, clientes O2, atribución O3 ni la Guía UI. Por tanto se mantiene el
dictamen **FAVORABLE** de §0-§4 (O2 del payload vacío como TTL de 404, O1a prefetch, O3/O4 de QA).

* **Regresión:** `test_relleno_huecos` + `test_enricher` → **85 passed** en 2,32 s; `ruff check src/` →
  *All checks passed!*. QA de referencia **7111 passed / 2289 skipped ×2**, 236 tocadas, sonda 9/9; la
  suite completa de este SHA la está ejecutando el Lead. Sin migraciones ni cambios en `models/`.
* **Veredicto: FAVORABLE para `079ca7a6598e3010528525a6065b4c91373ec616`**, sin condiciones: m-1 y m-2
  cerrados; el resto del dictamen se mantiene. Este addendum aplica **solo** a este SHA; cualquier
  commit/rebase posterior exigirá nuevo dictamen. El addendum está en el árbol de trabajo sin commitear,
  a la espera de la PR documental.
