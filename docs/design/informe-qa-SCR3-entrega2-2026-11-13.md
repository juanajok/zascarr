# Informe QA — SCR3 entrega 2: integración, reconciliación y fixes de SecOps (2026-11-13)

**Rol:** QA · **Tarea:** task-22 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr3-entrega2`
**Rama:** `feat/scr3-entrega2`, HEAD **`c8df218a`** (PR #771 según el encargo; no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2 + pytest-asyncio, ruff 0.17.5, lxml). Sin `TEST_DATABASE_URL` en el
entorno; la validación con Postgres real se hizo con el contenedor disponible (ver §2).
**Ejecución real:** 2026-11-14, 00:09–00:22 CET (la tarea se abrió pasada la medianoche); el
nombre del informe sigue la indicación del Lead (`…-2026-11-13.md`).
El único fichero escrito es este informe; el scratch de QA (`.qa-scr3e2/`) se borró al terminar.

---

## 1. Regresión

| # | Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|---|
| 1 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6778 passed, 2278 skipped**, 4 warnings | 358,60 s (wall 6:02) |
| 2 | `PYTHONPATH=src <venv>/bin/python -m pytest -q` | **6778 passed, 2278 skipped**, 4 warnings | 339,83 s (wall 5:43) |
| 3 | `… pytest -q tests/test_reconciliacion_lecturas.py tests/test_reading_orders.py tests/test_reading_order_resolver.py tests/test_web_ajustes_fuentes_nuevas.py tests/test_fuentes_apagadas_por_defecto.py tests/test_health.py tests/test_web_arcos.py tests/test_cortesia.py tests/test_web_estado_cortesia.py` | **194 passed** | 11,96 s (wall 13,43 s) |

* Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
  contaminación entre pruebas. Los 2278 skips son los esperados sin `TEST_DATABASE_URL`
  (pruebas `tests/*_pg.py` y dependientes de entorno); la validación con Postgres se hizo aparte
  (§2), porque la reconciliación no tiene prueba `_pg` commiteada (ver O2).
* Lint: `ruff check src/` → **All checks passed!**; `ruff check --select S src/` → **All checks
  passed!**.
* 4 warnings, ajenos a SCR3 y preexistentes (`Duplicate name: 'ComicInfo.xml'`; `RuntimeWarning:
  coroutine … never awaited` en `test_importer`/`test_bucle_no_bloqueado`).

---

## 2. Postgres real: reconciliación de punta a punta

El entorno no define `TEST_DATABASE_URL`, pero había un contenedor disponible
(`zascarr-ux508-pg`, `postgres:15-alpine`, `127.0.0.1:55508`, PG 15.19). Creé una base de pruebas
**nueva** (`zascarr_qa_scr3e2_test`), la migré a `head` con `tests._pg.migrar_a_head` y ejecuté dos
sondas E2E propias (no las pruebas del builder); después borré la base (`DROP DATABASE … WITH
(FORCE)`), sin dejar estado en el contenedor compartido.

**A. Reconciliación core (10/10 OK):** semilla de 1 serie (Daredevil) y 5 números locales; guía con
`#1-8`, prosa, TPB, número inexistente y serie inexistente.
* 1.ª pasada: arco creado con `metadata_={"origen": "reading_orders", "url": …}`, enlaces
  `reading_order` 1..5 en el orden de la guía, `enlazados=5`, `omitidos=4` con motivos
  (`sin_referencia`, `no_aplica`, `numero_no_encontrado`, `serie_no_encontrada`).
* 2.ª pasada reordenada (`#3`, `#1-2`): **no duplica el arco**, reordena (3→1, 1→2, 2→3),
  **quita** los enlaces que ya no constan y deja 3 filas.
* 3.ª pasada idéntica: **idempotente** (mismos `issue_id`, mismo orden, sin altas).
* Una guía que no casa con nada **no vacía** el arco existente.
* Biblioteca intacta (mismas series/números/valores antes y después; `files=0`), `metadata_`
  estable y sin cambios en `models`/`alembic`.

**B. Cadena completa extractor real → reconciliación → Postgres (3/3 OK):** con el fixture HTML
`cbro_guia.html`, `CacheHttp` falsa y `MockTransport`, `leer_y_reconciliar` creó el arco y enlazó
los 4 números sembrados en orden DOM (`Green Lantern Vol. 2 #173`, `Batman Vol. 3 #1`, `#2`,
`Detective Comics #1000`), con `omitidos=7` (`serie_no_encontrada`) y metadata correcta.

---

## 3. Aceptación por criterio

### (a) Fuentes apagadas por defecto y toggles en Ajustes — **PASA**

`config.py:108-113`: `reading_orders_enabled=False` (ritmo 2,5 s) y
`continuity_guide_enabled=False` (3,5 s). Ajustes: `web/ajustes.py:130-131` (contexto), `:315-316`
(`Form(default=False)`), `:328-329` (`RuntimeSettingsService.save`); plantilla
`ajustes.html:50,54` (dos checkboxes sin `checked`). `runtime_settings.py:47` los incluye en
`OVERRIDABLE_FIELDS`. `utils/cortesia.py:111-112` (nombres), `:118-120` (`FUENTES_DECLARADAS` con
12 fuentes), `:248-255` (política con 1 intento y los intervalos de la spec).
Pruebas: `test_web_ajustes_fuentes_nuevas.py:24` (checkbox y texto en Ajustes), `:70` (guardar
persiste los dos toggles), `test_fuentes_apagadas_por_defecto.py` (`CAMPOS` ampliado a los 8),
`test_cortesia.py::TestSnapshot` y `test_web_estado_cortesia.py::TestEndpoint` (12 fuentes).
Sonda independiente (10/10 OK): defaults `False`, política 2,5/3,5 s y 1 intento,
`fuente_habilitada` False sin overrides, checkboxes sin `checked`, y `POST
/ui/ajustes/guardar/fuentes` persiste ambos a `True` sin tocar las demás fuentes.

### (b) `/api/health` lista las dos fuentes `disabled` — **PASA**

`api/health.py:476-479`: `reading_orders`/`continuity_guide` → `"disabled"` si su flag está
apagado (default). Prueba: `tests/test_health.py:595-610`
(`test_fuentes_de_metadatos_incluyen_las_fuentes_nuevas`), verde en la pasada aislada y en las dos
completas. El health es observacional: no sondea las fuentes apagadas (mismo criterio que el resto).

### (c) `LEGAL.md` con las dos filas y hash que cambia la aceptación — **PASA**

`src/zascarr/LEGAL.md:108-109`: fila de **Comic Book Reading Orders** (solo referencias fácticas,
`Content-Signal: use=reference`, sin prosa ni IA, atribución con enlace) y de **Continuity Guide**
(sin `?format=json`, sin prosa ni títulos de arco, sin hotlinking, atribución). `legal_version` es
el SHA-256 del fichero (`services/legal.py`): actual **`8a546cf5fd2ce242`** ≠ `HEAD~1`
**`77e66dcf43b13b5a`**, comprobado por hash directo; la aceptación anterior queda invalidada como
exige CLAUDE.md §11.

### (d) Reconciliación guía → `StoryArc` + `StoryArcIssue.reading_order`, idempotente — **PASA**

`services/reconciliacion_lecturas.py`: `reconciliar_guia` (`:151-243`) reutiliza los modelos
existentes (sin entidad ni migración nuevas): un `StoryArc` por guía (título como clave, patrón de
`enricher._upsert_arc`) con `metadata_={"origen","url"}` (`:136-148`) y un `StoryArcIssue` por
número local con `reading_order` 1..N en orden DOM (`:183-227`). Match conservador por título
normalizado, desempate por `volumen` y `anio_volumen` ±1 (nunca `anio_numero`; `:86-102`), tpb/
volume = `no_aplica`, omitidos contados y logueados sin prosa ni URL (`:168-200`). **No hace
`commit`** (lo decide el llamador). Enlaces: actualiza el orden de los existentes, añade nuevos,
quita los que ya no constan y **no vacía** el arco si la guía no enlaza nada (`:210-227`).
Pruebas: `test_reconciliacion_lecturas.py:90-217` (creación, reordenado idempotente sin duplicar,
omitidos con motivos, ambiguo, desempate, número repetido, solo escribe `StoryArc`/`StoryArcIssue`),
`:220-247` (título por slug, `leer_y_reconciliar`, resultado inmutable). Validación real con
Postgres §2-A (10/10) y §2-B (3/3): orden, idempotencia, bajas de enlaces, biblioteca intacta,
`files` sin tocar. Sin migraciones ni cambios de modelo (§3-h).

### (e) Fixes de SecOps M-1 y m-1…m-5 — **PASA**

* **M-1 (resolver lineal):** `_grupos_finales` se reescribió como escaneo desde el final con
  índices y tope `MAX_GRUPOS=64` (`reading_order_resolver.py:85-110`), y la entrada pública se
  acota a `MAX_REFERENCIA=2000` (`:247`). Sonda independiente: `_grupos_finales` directo con 250.000
  grupos tarda **0,19 ms** (100.000: 0,04 ms); `parsear_referencia` con 100.000 grupos devuelve
  `None` en 0,002 ms (rechazo por el tope). Ver O1 sobre la prueba del builder.
* **m-1 (`int()` acotado):** `_entero_acotado` (`:135-139`), `_parsear_numero` (`:160`) y
  `expandir_rango` (`:266`) rechazan números de miles de dígitos antes de `int()`. Sonda: `Vol.` y
  `#` con 5.000 dígitos → `None`/`[]` sin `ValueError`.
* **m-2 (`item_url` solo http(s)):** `comun.url_de_item` (`:127-145`) rechaza `javascript:`,
  `data:`, `mailto:`, userinfo, puertos no estándar y > 500 caracteres; los extractores lo aplican
  al construir cada entrada (`entrada_de_guia`, `:148-158`). En la ficha, `web/arcos.py:45-63`
  valida también el enlace guardado en `metadata_` y `arco.html` no pinta `javascript:`/`data:`.
  Pruebas: `test_reading_orders.py:382`, `test_web_arcos.py:93`; sonda OK.
* **m-3 (URL endurecida):** `comun.url_de_sitio_valida` (`:92-124`) exige `https`, host de la
  allowlist, sin userinfo/`@`, puerto 443, sin query, sin `..`, sin caracteres de control, sin
  extensión de recurso y (CG) con página real; los adaptadores delegan en ella. Pruebas:
  `test_reading_orders.py:394,438`; sonda: userinfo, 8443, query, `/api/`, `..`, `.jpg`, http,
  puerto inválido y control → rechazados.
* **m-4 (sitemap vacío):** `parsear_sitemap` captura `XMLSyntaxError`/`ValueError` y devuelve `[]`
  (`:200-205`). Prueba `test_reading_orders.py:375`; sonda: `b""`, `b"no es xml"`, `<urlset>` → `[]`.
* **m-5 (cotas):** `MAX_REFERENCIA=2000`, `MAX_SECCION=200`, `MAX_TITULO_GUIA=500`,
  `MAX_URL_ITEM=500` (`comun.py:63-66`), saneado en `entrada_de_guia` y renumerado contiguo 1..N
  en `leer_guia` (`:348-366`); en el resolver, `MAX_AVISOS=10`, `MAX_AVISO=120`, `MAX_NUMERO=32`,
  `MAX_TITULO_SERIE=500` y `MAX_DIGITOS_ENTERO=9` (`:36-42`). Pruebas `test_reading_orders.py:415`,
  `test_reading_order_resolver.py:160`; sonda OK.

### (f) `arco.html` muestra la fuente como enlace `rel="noopener noreferrer"` — **PASA**

`web/arcos.py:45-63` (`fuente_de_guia`: solo orígenes de guía conocidos, URL http(s) sin
credenciales y ≤ 500 chars) se inyecta en el contexto (`:132,214`) y la plantilla
`web/templates/arco.html:10-11` pinta «Guía de lectura: <a … target="_blank" rel="noopener
noreferrer">…</a>» (texto, sin hotlinking). Pruebas: `test_web_arcos.py:76` (fuente visible y
`rel`) y `:93` (URL peligrosa no se pinta); verde en aisladas y en las dos completas. Sonda:
template con `rel="noopener noreferrer"`, sin `<img>`.

### (g) `scripts/reconciliar-lecturas.py --help` funciona y usa la API pública — **PASA**

El script (`scripts/reconciliar-lecturas.py:27-66`) importa `leer_y_reconciliar`, los dos
extractores, `CacheHttp` y `async_session_factory` de la API pública; no reimplementa parseo ni
usa funciones privadas. `--help` comprobado con el venv del repo: **exit 0**, usage y opciones
`--fuente {continuity_guide,reading_orders}` / `--url`. El disparo es manual (la UI de importación
queda para otra historia, según la spec).

### (h) Sin migraciones ni cambios de modelo — **PASA**

`git diff HEAD~1 HEAD --name-only | grep -E "models|alembic"` → **sin resultados**; tampoco
`pyproject.toml`. El commit toca `config.py`, `cortesia.py`, `runtime_settings.py`,
`web/ajustes.py`, `web/arcos.py`, plantillas, `api/health.py`, `LEGAL.md`, los servicios y tests;
la reconciliación reutiliza `story_arcs`/`story_arc_issues` existentes. Confirmado también en la
E2E: migrar a `head` y reconciliar no requiere ninguna tabla nueva.

---

## 4. Observaciones (ninguna bloqueante)

**O1 — La prueba de M-1 del builder no ejecuta el parser.** 
`test_m1_grupos_finales_consecutivos_es_lineal` (`test_reading_order_resolver.py:133`) pasa
`"X-Men #1" + "(a)"*100_000` a `parsear_referencia`; esa entrada supera `MAX_REFERENCIA=2000` y
`parsear_referencia` la rechaza **antes** de llamar a `_grupos_finales`, así que el test mide el
atajo de longitud (0,002 ms), no el algoritmo. **No es un fallo de M-1:** el tope de entrada ya
acota el riesgo y `_grupos_finales` es lineal (sonda directa: 250k grupos → 0,19 ms); la prueba
del builder simplemente no demuestra por sí sola la parte que dice. Recomendación: añadir un test
directo de `_grupos_finales` o bajar el número de grupos para que no lo corte el tope.

**O2 — La reconciliación no tiene prueba `_pg` en el repo.** Las pruebas commiteadas usan
`FakeSession` (correctas y deterministas), pero ninguna toca Postgres; la validación E2E de este
informe se hizo con el contenedor y no queda como regresión de CI. Si cambian `story_arcs` o el
ORM, una rotura no la detectaría la suite. Recomendación: añadir `tests/…_pg.py` con
`bd_efimera()` que cubra al menos `#1-5` + reejecución idempotente (el patrón ya existe en el
repo). No bloquea la entrega: la E2E manual ha pasado.

**O3 — Tope de enlaces (`MAX_ENLACES=1000`): contabilidad teórica inexacta.** Si una guía
superase 1.000 enlaces, el ítem que topa suma `motivo["tope"]` y además puede caer en
`numero_no_encontrado` (el `omitidos` puede contar dos veces). No se alcanza con guías reales
(~100 referencias) y la spec no pide ese contador exacto; lo dejo anotado por si se reutiliza el
servicio con otras fuentes.

**O4 — Fecha del informe.** La tarea se abrió a las 00:09 del 2026-11-14 (pasada la medianoche) y
el Lead pidió el nombre `…-2026-11-13.md`; he seguido la indicación explícita del Lead y dejo la
fecha real de ejecución en la cabecera.

---

## 5. Veredicto

**APTO.** SCR3 entrega 2 cumple los criterios (a)-(h): suite completa verde dos veces con
contadores idénticos (6778 passed / 2278 skipped), aisladas verdes (194 passed), `ruff` y
`ruff --select S` limpios, integración de fuentes con defaults apagados/Ajustes/health/LEGAL,
reconciliación con `story_arcs` **idempotente y validada contra Postgres real** de punta a punta
(2 sondas E2E propias: 10/10 y 3/3), fixes de SecOps M-1 y m-1…m-5 verificados con sonda propia
(10/10) y enlace de fuente con `rel="noopener noreferrer"`.
**Bloqueantes: ninguno.** Recomendaciones no bloqueantes: O1 (test de M-1 que ejecute el parser) y
O2 (prueba `_pg` de reconciliación en CI).

---

## 6. Inventario del cambio revisado (`c8df218a`)

25 ficheros, **+1065 / −101**: `scripts/reconciliar-lecturas.py`, `src/zascarr/LEGAL.md`,
`api/health.py`, `config.py`, `services/reading_order_resolver.py`,
`services/reading_orders/{__init__,comun,comicbookreadingorders,continuity_guide}.py`,
`services/reconciliacion_lecturas.py`, `services/runtime_settings.py`, `utils/cortesia.py`,
`web/ajustes.py`, `web/arcos.py`, `web/templates/{ajustes,arco}.html` y los tests/fixtures
correspondientes (sin `models/`, `alembic/` ni `pyproject.toml`).
