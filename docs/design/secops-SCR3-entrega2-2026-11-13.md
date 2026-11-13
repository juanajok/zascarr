# SecOps — Dictamen de SCR3 entrega 2: integración de fuentes, reconciliación y cierre de M-1/m-1…m-5

**Rol:** SecOps · **Tarea:** task-23 · **Fecha:** 2026-11-14 (00:22–00:40, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr3-entrega2` (rama `feat/scr3-entrega2`)
**SHA auditado (el que se fusiona):** **`79955b7665bf6b74873909144ef117d156f19ca2`**, verificado:
`git rev-parse HEAD` = ese SHA y `gh pr view 771` → `headRefOid = 79955b7665bf6b74873909144ef117d156f19ca2`,
base `main`, `state=OPEN`, `mergeable=MERGEABLE`. Árbol limpio antes y después.
**Base del cambio:** `1567d95a` (decisión PO/spec/CHANGELOG), `c8df218a` (feature, 25 ficheros **+1065/−101**)
y `79955b76` (solo informe de QA, +216 líneas). El delta completo `git diff --stat 1567d95a^..HEAD` no incluye
`models/`, `alembic/`, `pyproject.toml` ni `LEGAL.md` fuera de las dos filas nuevas (verificado con
`git diff --name-only`).
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python` (Python 3.14,
pytest 9.2, ruff 0.17.5, lxml). Sin `TEST_DATABASE_URL`.
**Alcance:** dictamen **final §5.8** sobre el SHA (la PR toca `web/ajustes.py`), cierre de M-1/m-1…m-5,
integración §5, reconciliación con `story_arcs`, red/SSRF, script manual y regresión.
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito y queda sin
commitear.

> **Nota de fecha:** el informe se nombra `…-2026-11-13.md` por indicación del Lead, como el de QA; la
> ejecución real es de la madrugada del 2026-11-14.

---

## 0. Veredicto

**FAVORABLE CON CONDICIONES.** 0 bloqueantes, **1 mayor** (C-1, integridad de la reconciliación) y 5 menores.
Para la superficie que dispara §5.8 (`web/ajustes.py`) el dictamen es **favorable**: el diff son solo las
dos casillas de fuentes y su persistencia; **no altera el flujo de contraseña/sesión** ni introduce secretos
ni campos fuera de `OVERRIDABLE_FIELDS`. Todos los fixes de SecOps (M-1 y m-1…m-5) están cerrados con
mediciones, la integración §5 es correcta (flags off por defecto, health, `LEGAL.md` con hash que invalida la
aceptación, cortesía, Ajustes seguros) y la red sigue pasando solo por `pedir_con_cache`/robots de SCR1.

**Condición C-1 (mayor):** la reconciliación hace *upsert por título* (`StoryArc.title`), **no por
`metadata_` origen+URL** como exige el encargo. Con una guía cuyo título coincida con un arco existente
(p. ej. uno creado por Fandom o manual), el script **reutiliza ese arco, sobrescribe su metadata y borra sus
enlaces de lectura**; y si la guía cambia de título, crea un arco nuevo dejando el antiguo (duplicado).
Es integridad de datos, no confidencialidad, y hoy solo se alcanza con el script manual (fuentes apagadas por
defecto), pero es la clave que el encargo pide: **corregirla antes de fusionar** (o, si el Lead/PO acepta
explícitamente la clave por título, añadir el guard que impida adoptar/borrar arcos de otra fuente y la prueba
de colisión). El resto de menores no bloquean.

---

## 1. Método

1. Lectura completa de los servicios nuevos/modificados (`reconciliacion_lecturas.py`, resolver, `comun.py`,
   adaptadores, `web/arcos.py`, `web/ajustes.py`, `scripts/reconciliar-lecturas.py`) y de los tests/QA.
2. **Suite completa** desde el worktree: `PYTHONPATH=src <venv>/bin/python -m pytest -q` →
   **6.778 passed, 2.278 skipped** en 329,97 s (coincide con las dos pasadas de QA: mismos contadores).
3. **Gates de CI:** `ruff check src/` → *All checks passed!*; `ruff check --select S src/` → *All checks passed!*.
4. **Sondas propias** (independientes de los tests del builder): M-1 con 100k/250k grupos; m-1 con 5.000
   dígitos; m-2 con `javascript:`/`data:`/terceros; m-3 con userinfo/puerto/query/`..`/recursos;
   m-4 con XML vacío/roto; m-5 con cotas; §5.8 con el diff de Ajustes y `RuntimeSettingsService.save`;
   `LEGAL.md` por hash; fuente apagada con `Settings(_env_file=None)` (0 peticiones); colisión de título en la
   reconciliación con el mismo doble de sesión de los tests; títulos con caracteres de control.
5. **Contraste con QA:** su informe se generó sobre `c8df218a`; el SHA auditado añade solo ese informe
   (216 líneas). Sus criterios (a)-(h) se reproducen; O1/O2/O3/O4 se confirman; no hay contradicciones.

---

## 2. Hallazgos

### 2.1 Bloqueantes

**Ninguno.**

### 2.2 Mayores

#### C-1 — El upsert de la reconciliación es por título, no por `metadata_` origen+URL; puede adoptar y vaciar arcos de otra fuente

**Qué.** `_upsert_arco` busca el arco solo por `StoryArc.title` (`reconciliacion_lecturas.py:136-148`, consulta
en `:141`) y no por `metadata_["origen"]`/`metadata_["url"]`. Si lo encuentra, le **fusiona**
`{"origen": guia.sitio, "url": guia.url}` (`:147`); después `reconciliar_guia` **borra los
`StoryArcIssue` existentes que la guía no declara** cuando la guía enlaza algo (`:227-232`). `StoryArc.title`
no es único (`models/__init__.py:615-625`) y el título sale del HTML de la guía
(`titulo_de_guia`, `:72-83`), es decir, de contenido externo.

**Evidencia (sonda con el `SesionFalsa` de los tests).** Arco existente de **Fandom** (`metadata_` con
`fandom_dc`, `origen=fandom_dc`) titulado «Crisis on Infinite Earths» y con un enlace propio; se reconcilia
una guía de otra fuente con el mismo título y un número local:

```
creado: False | origen resultado: reading_orders
arco reutilizado: id= arco-fandom title= Crisis on Infinite Earths
metadata_ tras reconciliar: {'fandom_dc': '...', 'origen': 'reading_orders', 'url': 'https://...continuityguide...'}
enlaces borrados: ['i-9']
enlaces añadidos: [('i-1', 1)]
arcos nuevos añadidos: []
```

Es decir: **el arco ajeno se reatribuye a la guía y pierde su enlace i-9**. Además, un cambio de título en la
guía produce `creado=True` y deja el arco antiguo (duplicado), porque la búsqueda es solo por título
(`:140-146`).

**Riesgo.** Integridad de datos: corrupción/adopción cruzada de un arco (Fandom, manual u otra guía) con
borrado de enlaces y atribución cambiada; duplicados cuando el título cambia. Requiere que el usuario
reconcilie una guía concreta (script manual, fuentes apagadas por defecto), pero el título lo controla la
fuente y la operación es destructiva sobre datos propios. QA lo dio por bueno como «patrón de
`enricher._upsert_arc`» (su §3d) y su E2E valida idempotencia con el **mismo** título; no cubre la colisión ni
el cambio de título.

**Condición C-1 (antes de fusionar, o aceptación explícita del PO/Lead):**
1. Buscar por `metadata_` de origen+URL (`StoryArc.metadata_["origen"].astext == guia.sitio` y
   `metadata_["url"].astext == guia.url`), crear si no existe y **actualizar el título en esa misma fila** si
   cambió (idempotente por URL).
2. No adoptar un arco con metadata de otra fuente ni borrar sus enlaces; si el producto quiere fusionar
   guías equivalentes, que sea una decisión explícita y con confirmación, no un efecto colateral.
3. Pruebas: mismo título con origen/URL distintos ⇒ arcos distintos (o regla explícita); título cambiado ⇒
   misma fila sin duplicado; reejecución sin cambios; no borrar enlaces de un arco ajeno.

### 2.3 Menores

#### c-1 — m-3: el chequeo de `..` no normaliza el porcentaje (`%2e%2e` se acepta)

`url_de_sitio_valida` comprueba el `..` **literal** en la ruta (`comun.py:92-124`). Sonda:
`https://comicbookreadingorders.com/dc/events/x%2e%2e/y/` → **True** (el `..%2f..%2f` literal sí se rechaza
porque contiene `..`). El servidor puede decodificar `%2e%2e` y navegar fuera de la ruta prevista; el host
sigue siendo el de la allowlist (no hay SSRF), pero podría alcanzarse una ruta que `RUTAS_PROHIBIDAS` o
`robots.txt` excluyen (cumplimiento, no confidencialidad). Fix: `unquote` de la ruta antes de comprobar
`..`/rutas prohibidas/extensión (o rechazar `%` en la ruta de RO, como ya hace el regex de página de CG).

#### c-2 — El script imprime un título externo sin sanear controles de terminal

`reconciliar-lecturas.py:60` imprime `resultado.titulo`, que viene del HTML de la guía (`<h1>`/`<title>`) y
`titulo_de_guia` solo colapsa espacios (`reconciliacion_lecturas.py:72-83`). Sonda: un título con
`\x1b[2J`/`\x1b]52;…\x07` **conserva** los caracteres de control; al ejecutar el script en una terminal, una
fuente maliciosa/comprometida podría inyectar secuencias ANSI/OSC (limpiar pantalla, portapapeles). Riesgo
bajo (herramienta manual, sin secretos), fix trivial: eliminar C0/ESC y acotar antes de imprimir (o en
`titulo_de_guia`). En la web el título se escapa con Jinja; no afecta a XSS.

#### c-3 — `_buscar_issue` no desempata por volumen

`_buscar_issue` selecciona por `series_id` + `issue_number` (`reconciliacion_lecturas.py:130-133`); el UNIQUE
real es `(series_id, issue_number, volume)` (`models/__init__.py:635`), así que una serie con varios volúmenes
y el mismo número puede enlazar el `Issue` equivocado (`.first()`). Es corrección de datos, no seguridad;
conviene filtrar por `Series.volume`/`anio_volumen` hasta donde el resolver lo sepa, y registrar el
descartes si sigue ambiguo.

#### c-4 — `fuente_de_guia` valida esquema/userinfo pero no host de la allowlist; URL de metadata sin cota de longitud

`web/arcos.py:45-63` pinta solo `origen` conocido y URL `http(s)` sin credenciales y ≤500; no exige host de
la allowlist (el `metadata_` lo escribe el extractor con URL ya validada; una fila manipulada en BD solo
produciría un enlace de navegación con `rel="noopener noreferrer"`, sin XSS). El `url` se guarda en JSONB sin
cota (la vista lo oculta si >500). Defensa en profundidad menor; no bloquea.

#### c-5 — Deudas/observaciones de QA ya declaradas (no contradicen)

* QA O1: el test de M-1 del builder pasa 100k grupos a `parsear_referencia`, que los rechaza por
  `MAX_REFERENCIA` **antes** de llamar a `_grupos_finales`; no demuestra el algoritmo (mi sonda directa sí:
  `_grupos_finales` 100k/250k → 0,06/0,07 ms). No es fallo del fix.
* QA O2: la reconciliación no tiene prueba `_pg` commiteada (la E2E de QA fue manual con Postgres real);
  QA O3: doble conteo teórico de `MAX_ENLACES`; QA O4: fecha del informe. Ninguna es de seguridad.
* M-3/RES-3 de SCR1 (cuerpo bufferizado antes del tope) sigue como deuda compartida; SCR3 no la empeora
  (páginas CG ~975 KB, tope 2 MiB y parseo en `to_thread`).

---

## 3. Cierre de los fixes de SecOps (M-1 y m-1…m-5)

| Fix | Evidencia en el SHA | Verificación propia |
|---|---|---|
| **M-1** `_grupos_finales` lineal + tope | `reading_order_resolver.py:36-42` (cotas), `:85-110` (escaneo desde el final con índices y `MAX_GRUPOS=64`), `:243-248` (`MAX_REFERENCIA=2000`) | `_grupos_finales("Serie X " + "(a)"*n)`: **100.000 → 0,06 ms**, **250.000 → 0,07 ms** (antes: 16.000 → 9,3 s, 32.000 → 33,3 s). `parsear_referencia` con 100k grupos → `None` en 0,002 ms (atajo por tope). **Cerrado** |
| **m-1** `int()` acotado | `:135-139` (`_entero_acotado`, ≤9 dígitos), `:160` (`_parsear_numero` ≤32 chars), `:256-267` (`expandir_rango` valida longitud antes de `int`) | `"X Vol. "+"9"*5000+" #1"` → `None`; `"X #"+"9"*5000` → `None`; `ReadingOrderItem(numero 5000 dígitos)` → `expandir_rango=None`; `#1-5` → 1..5; sin `ValueError`. **Cerrado** |
| **m-2** `item_url` solo http(s) + `rel` | `comun.py:127-145` (`url_de_item`: http(s), sin credenciales, puertos 80/443, ≤500), `:148-158` (`entrada_de_guia`); adaptadores lo usan (`comicbookreadingorders.py:94-100`, `continuity_guide.py:73-82`); `web/templates/arco.html:10-11` (`target="_blank" rel="noopener noreferrer"`) | Sonda: `javascript:`/`data:`/`mailto:`/userinfo/`:8443`/URL >500 → `None`; `https://www.dcuniverseinfinite.com/…` (tercero **por diseño**, enlace de lectura) se conserva; no se descarga. **Cerrado** |
| **m-3** `url_de_sitio_valida` | `comun.py:92-124`: https, allowlist, sin userinfo/`@`, puerto 443, sin query, sin `..` literal/controles, sin extensión de recurso, rutas prohibidas y página real (CG); adaptadores delegan (`comicbookreadingorders.py:47-52`, `continuity_guide.py:42-57`) | Acepta la guía válida; rechaza userinfo, `:8443`, `http`, `?q=1`, `..`, `.jpg`, `/api/`, `/search/`, `/admin/` y host ajeno. **Cerrado con el residuo c-1 (%2e%2e)** |
| **m-4** sitemap vacío | `comun.py:200-206`: `try/except (XMLSyntaxError, ValueError) → []` | `b""`, `b"no es xml"`, `b"<urlset>"`, `b"<urlset></urlset>"` → `[]`, sin excepción. **Cerrado** |
| **m-5** cotas | `comun.py:63-66` `MAX_REFERENCIA=2000`/`MAX_SECCION=200`/`MAX_TITULO_GUIA=500`/`MAX_URL_ITEM=500`; saneado `:148-158`, renumerado 1..N `:348-366`; resolver `:36-42` `MAX_AVISOS=10`/`MAX_AVISO=120`/`MAX_NUMERO=32`/`MAX_TITULO_SERIE=500` | Entradas y títulos por encima de las cotas se descartan/truncan; los tests (`test_reading_orders.py:377-443`, `test_reading_order_resolver.py:145-165`) las cubren. **Cerrado** |

---

## 4. Integración §5 y dictamen §5.8

### 4.1 Fuentes apagadas por defecto y Ajustes seguro

* `config.py:110-113`: `reading_orders_enabled=False`/`rate_limit=2.5` y
  `continuity_guide_enabled=False`/`3.5`. Sonda con `Settings(_env_file=None)`: ambos `False`; una lectura de
  guía devuelve `None` con **0 peticiones de red** (`reading_orders.sin_turno`, motivo «apagada»).
* Ajustes: contexto `web/ajustes.py:130-131`, dos `Form(default=False)` (`:315-316`) persistidos con
  `RuntimeSettingsService.save` (`:328-329`); plantilla `ajustes.html:50,54` (checkboxes sin `checked`).
* `runtime_settings.py:47`: los dos campos están en `OVERRIDABLE_FIELDS["fuentes"]`; `save()` solo acepta
  `_ALL_FIELDS` (unión de `OVERRIDABLE_FIELDS` + internos, `:102-104`) y rechaza claves desconocidas
  (`:138-140`); no hay mass assignment ni campos de secreto nuevos.
* `/api/health`: `api/health.py:476-479` lista `reading_orders`/`continuity_guide` como `disabled` si su flag
  está apagado (comportamiento observacional ya usado por las demás fuentes).
* `cortesia.py:111-112` (nombres), `:118-120` (`FUENTES_DECLARADAS`, 12 fuentes), `:248-255` (política con
  **1 intento**, 3 redirecciones y 2,5/3,5 s); tests de snapshot/endpoint actualizados (QA los pasa).

### 4.2 Dictamen §5.8 (la PR toca `web/ajustes.py`)

El diff de `web/ajustes.py` es **solo aditivo** (`git diff --stat`: **6 líneas añadidas**; plantilla +8): dos
entradas en `_contexto`, dos parámetros `Form(default=False)` y dos claves en el dict de `save`. No se cambia
ninguna línea de contraseña, sesión, cookie ni autenticación (el diff no contiene `password`/`session`/
`cookie`; `services/seguridad.py` y `services/reautenticacion.py` **no** están en el delta). Los dos toggles
nuevos son on/off de fuentes de metadatos, sin secretos, y su persistencia pasa por la lista blanca de
`RuntimeSettingsService`. **Dictamen §5.8: favorable** para el SHA `79955b76…`: la PR no altera «qué exige la
contraseña actual» ni la superficie de autenticación. Si se añade cualquier commit posterior (aunque sea
documental), habrá que emitir addendum sobre el SHA nuevo (§5.8).

### 4.3 `LEGAL.md` y `legal_version`

`LEGAL.md:108-109` añade las filas de Comic Book Reading Orders y Continuity Guide (solo referencias, sin
prosa/IA, robots, sin `?format=json`, atribución con enlace). `legal_version` es el SHA-256 del fichero
(`services/legal.py:35-45`): hash del árbol **`8a546cf5fd2ce242`** ≠ HEAD~1 **`77e66dcf43b13b5a`** (y
`current_legal_version()` devuelve `8a546cf5fd2ce242`): la aceptación anterior queda invalidada
automáticamente, sin constante manual. La atribución visible se pinta en la vista de la saga (§4.4).

### 4.4 Enlace de fuente del arco (XSS)

`web/arcos.py:45-63` (`fuente_de_guia`) solo acepta orígenes de guía conocidos (`ORIGENES_DE_GUIA`), URL
`http(s)` sin credenciales y ≤500; se inyecta en la ficha (`:132,214`) y `arco.html:10-11` lo pinta con
`target="_blank" rel="noopener noreferrer"`, como enlace de navegación (sin `<img>`, sin `src` externo, sin
`|safe`). Jinja escapa el texto y el `href` viene validado: no hay XSS ni hotlinking. **Correcto.**

---

## 5. Reconciliación: alcance, escrituras y transacción

* **Solo lee la biblioteca y solo escribe arcos/enlaces.** Importa únicamente `Series`/`Issue` (lectura) y
  `StoryArc`/`StoryArcIssue` (escritura): `db.add` solo de `StoryArc`/`StoryArcIssue`
  (`reconciliacion_lecturas.py:145,225`) y `db.delete` solo de `StoryArcIssue` (`:232`). No toca `files`,
  wishlist, series ni números, ni el disco. Test explícito `test_solo_escribe_en_arcos_y_enlaces`
  (`tests/test_reconciliacion_lecturas.py:210-218`) y E2E de QA con Postgres real (biblioteca y `files`
  intactos).
* **Sin `commit` en el servicio** (`:151-157` documenta «no hace commit; lo decide el llamador»; solo
  `flush` en `:233`). El llamador es `scripts/reconciliar-lecturas.py`, que usa una sesión propia y hace
  `await db.commit()` (`:51`) tras `leer_y_reconciliar`; no hay ruta web que reconcilie (grep: solo el
  script). Transacción correcta para el caso de uso.
* **Idempotencia con la misma clave:** reejecutar la misma guía actualiza `reading_order`, añade/elimina
  enlaces y no duplica (`:206-233`; test `:119-146`; E2E QA). **Pero la clave es el título, no
  origen+URL** → C-1 (§2.2).
* **Inyección desde HTML externo:** las referencias se convierten a `ReadingOrderItem` (solo hechos, sin SQL
  manual: consultas SQLAlchemy parametrizadas `:121-133`); el título del arco sale de `<h1>`/`<title>` y se
  acota a 500 (la columna es `String(500)`, `models:618`) y se escapa en Jinja; la URL de `metadata_` viene
  del extractor ya validada por m-3; no se persiste prosa ni `item_url`. No hay inyección SQL ni XSS
  almacenado en la ficha (sí el riesgo de colisión de C-1).
* **Cotas:** `MAX_ENTRADAS=5000`, `MAX_ENLACES=1000` (`:50-52`), referencias ≤2000, títulos ≤500, URL de guía
  validada; los descartes se cuentan y se loguean sin prosa ni URL (`lecturas.item_descartado`,
  `:168-204`).
* **Límite/observación:** `_buscar_issue` no desempata volumen (c-3); `MAX_ENLACES` puede contar dos veces el
  ítem que topa (QA O3, sin impacto real).

---

## 6. Red, SSRF y script manual

* **Toda la red sigue por SCR1:** los extractores descargan exclusivamente con `pedir_con_cache` (caché +
  robots), sin `bypass_cache` ni cabeceras de credenciales (`comun.py:296-316` en este SHA, con `url_de_sitio_valida` antes de pedir); la reconciliación y el script **no** hacen
  HTTP propio (grep: no hay `httpx` en `reconciliacion_lecturas.py` ni en `scripts/`).
* **Sin SSRF nuevo:** host allowlist por adaptador, https, sin userinfo, puerto 443, sin query/`..` y
  redirecciones solo del mismo origen (`peticiones.py:127-151`); las URLs de `item_url` no se descargan, solo
  se guardan como enlace de lectura validado http(s); el enlace de la fuente en la ficha es navegación con
  `rel="noopener noreferrer"`.
* **Fuente apagada ⇒ cero tráfico:** sonda con `Settings(_env_file=None)` y transporte que cuenta peticiones:
  `leer_guia(...)` → `None` y **0** peticiones (el gate de `pedir_con_cache` mira `fuente_habilitada` antes de
  caché y robots). Con la fuente encendida en Ajustes, el flujo es el ya auditado de SCR1.
* **Script:** `scripts/reconciliar-lecturas.py` (66 líneas) importa la API pública (`CacheHttp`,
  `ReadingOrdersExtractor`/`ContinuityGuideExtractor`, `leer_y_reconciliar`, `async_session_factory`), no
  reimplementa parseo, no imprime URLs, rutas, referencias ni datos de la biblioteca (solo el título de la guía
  y contadores); `--url` es obligatoria y la valida el extractor. Único reparo: el título externo se imprime
  sin sanear controles de terminal (c-2).

---

## 7. Regresión y contraste con QA

* **Suite completa (mi ejecución):** **6.778 passed, 2.278 skipped** en 329,97 s; los *skips* son los
  esperados sin `TEST_DATABASE_URL`. Coincide con las dos pasadas de QA (mismos contadores).
* **Lint:** `ruff check src/` y `ruff check --select S src/` → *All checks passed!*.
* **QA no se contradice:** su informe es sobre `c8df218a`; el SHA auditado añade solo el informe de QA
  (`git diff --stat c8df218a..HEAD` → 1 fichero, 216 líneas). Sus criterios (a)-(h) se reproducen y sus
  observaciones O1-O4 se confirman; O1 (el test de M-1 no ejecuta el parser) queda cubierto por mi medición
  directa; O2 (falta prueba `_pg` de reconciliación) sigue como recomendación; O3/O4 son menores ya
  declaradas. QA no cubre la colisión de título de C-1 (la considera «patrón del enricher»): es una
  ampliación, no una contradicción.

---

## 8. Recomendaciones y condiciones

1. **C-1 (condición):** upsert por `metadata_` origen+URL (o aceptación explícita del PO/Lead con guard que no
   adopte/borre arcos de otra fuente), con pruebas de colisión de título y de título cambiado. Es el único
   punto que impide cerrar el encargo tal cual.
2. **c-1:** normalizar porcentaje/`unquote` antes de comprobar `..`, rutas prohibidas y extensiones en
   `url_de_sitio_valida` (o rechazar `%` en rutas de RO).
3. **c-2:** sanear controles C0/ESC del título antes de imprimirlo en el script (o en `titulo_de_guia`).
4. **c-3/c-4:** desempatar `Issue` por volumen cuando exista y, opcionalmente, acotar la URL de `metadata_` y
   validar host de la allowlist en `fuente_de_guia` (defensa en profundidad).
5. **QA O2:** añadir prueba `_pg` de reconciliación idempotente (recomendación, no seguridad).
6. **§5.8:** el dictamen favorable aplica al SHA `79955b76…`; cualquier commit o rebase posterior exige
   repetirlo (si es doc-only, un addendum de vigencia como en SCR1).

---

## 9. Trazabilidad

| Punto de task-23 | Sección |
|---|---|
| Cierre de M-1/m-1…m-5 con mediciones | §3 |
| Integración §5, flags off, Ajustes, health, LEGAL y hash, §5.8 | §4 |
| Reconciliación: escrituras, idempotencia, inyección, longitudes, transacción | §5, §2.2 C-1 |
| XSS en enlace de fuente (`rel`, `href` http(s)) | §4.4 |
| Red solo por SCR1/robots; sin SSRF; off ⇒ cero tráfico; script | §6, §2.3 c-1/c-2 |
| `ruff` y regresión de pruebas | §7 |
| Coherencia con QA | §7, §2.3 c-5 |
