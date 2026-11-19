# SecOps — Dictamen de #993: seguir series (foro/Prowlarr, deseos y aviso)

**Rol:** SecOps · **Tarea:** task-69 · **Fecha:** 2026-11-17 (13:18–14:10, Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/seguimiento-build` (rama `feat/seguimiento-series`)
**SHA dictaminado:** **`ffb0e8e8a3abd65e8a0e3042c4677feeb3e41078`**, verificado: `git rev-parse HEAD` = ese
SHA y `gh pr view 1012` → `headRefOid = ffb0e8e8a3abd65e8a0e3042c4677feeb3e41078`, base `main`,
`state=OPEN`, `mergeable=MERGEABLE` (checks en curso). `git diff 8cf17b73..HEAD` solo añade CHANGELOG,
BACKLOG, la nota de la migración 0047 y el informe QA: **el código funcional es el de `8cf17b73`**
(QA APTO).
**Cambio:** 28 ficheros, **+1700/−18** (feature 22 ficheros +1290/−17, fix QA 8 ficheros, docs 4). No
toca `web/ajustes.py` → **§5.8 no aplica**, pero se dictamina igual.
**Entorno:** `PYTHONPATH=src` con el venv de pruebas del repo (Python 3.14, pytest 9.2, ruff 0.17.5);
sin `TEST_DATABASE_URL` (la prueba `_pg` de migración queda skip; QA la ejecutó con Postgres real).
**No se ha tocado código ni se han hecho commits**; este informe es el único fichero escrito.

---

## 0. Veredicto

**FAVORABLE para `ffb0e8e8a3abd65e8a0e3042c4677feeb3e41078`**, sin bloqueantes de seguridad ni de
legalidad de la puerta de acuse. **§5.8 no aplica** (no toca `web/ajustes.py` ni seguridad/
reautenticación). Se verifican: credenciales/cookies/URLs `s=` fuera de logs/HTML/`seguimiento_vistos`,
un listado de foro (`showforum=5`) con **una** GET de lectura y sin Search de 25 s, cortesía/rate limit
e intervalo 45 min con topes; SSRF cerrado al origen del foro y al Prowlarr configurados; notifier sin
URL/token y sin nombres salvo `webhook_incluir_nombres`; puerta legal antes de crear deseos/avisar;
`seguimiento_vistos` sin enlaces ni títulos; migraciones 0047/0048 aditivas y sin secretos. Quedan
observaciones **no bloqueantes**: O-1 (el foro no consulta `robots.txt`; el benchmark documenta
`Disallow: /` y pide ratificación de PO/legal; el scraper ya era opt-in y el job sigue opt-in), O-2
(frontera por serie no aplicada a temas ya vistos que se actualizan), O-3 cobertura (Prowlarr/rotación,
integración de aviso, AC-16 y HTML real NOT RUN) y O-4 (`crear_deseos` sin `ON CONFLICT`; job
secuencial). Cualquier commit/rebase posterior exige nuevo dictamen.

---

## 1. Verificación por criterio

### 1.1 Credenciales, cookies y URLs `s=`/tokens

* **Cookie del foro:** `ForumScraper._cabeceras` solo añade `Cookie` si `origen_de(url) == self._origen`
  (`forum_scraper.py:526-531`); el login guarda las cookies en memoria, nunca las pinta, y el único log
  del login es `forum.login_no_confirmado` con **host** (`:522`). No hay valor de cookie en logs, HTML ni
  mensajes. `cookies_recibidas` es un contador (`:491`).
* **URLs con `s=`:** `_resolver_enlace` elimina los parámetros de sesión **por defecto**
  (`:533-564`, `_sin_parametros_de_sesion`), y solo conserva `s=` para la acción de login
  (`conservar_sesion=True`, `:500-503`). `listar_temas` resuelve cada `href` con
  `_resolver_enlace(href)` (`:593-610`), así que `TemaForo.url` no lleva `s=`; `TemaForo` **no se
  persiste** y `leer_tema` exige el mismo origen (`:614-620`). Los logs de `seguimiento` no incluyen
  URLs: solo `seguimiento.ambiguo` (número + UUIDs de serie, `seguimiento.py:136-137`),
  `seguimiento.deseo_de_serie_vivo` (`:288`), `*_fallido` con `type(exc).__name__` (`:316,358,423,510,
  530,552`) y `pass_done` con contadores (`:553-556`).
* **`SeguimientoVisto`:** el modelo solo tiene `fuente`, `clave` (`tema:<id>`, `release:<hash>`,
  `serie:<uuid>`), `huella` (actividad/fecha o hash de release), `visto_en` y `procesado_en`
  (`models/__init__.py:1214-1235`); **no hay columnas de URL ni de título**, y `_huella_release` es un
  SHA-256 truncado (`seguimiento.py:187-188`). No guarda magnet/ed2k, ni nombre de release, ni título de
  tema.
* **Notifier:** no registra `webhook_url`/`webhook_token`; `enviar` devuelve código HTTP o clase de
  excepción, nunca `str(exc)` (`notifier.py:87-103`, docstring), y `notify_novedades` registra solo
  `type` y `motivo` saneado (`:118-134`). **Pasa.**

### 1.2 Foro: listado, cortesía, intervalo y topes

* `ForumScraper.listar_temas` hace **una** GET `{base}/index.php?showforum={foro_id}` por `_get`
  (`forum_scraper.py:593-610`); el test `test_listar_temas_usa_una_get_de_lectura_y_no_la_busqueda`
  fija `vistas == ["…?showforum=5"]` y que no hay `Search` (`tests/test_seguimiento_foro.py:24-39`).
  No usa `_buscar_ipb` ni el ritmo de búsqueda de 25 s.
* La lectura pasa por `ForumScraper._politica` (lectura, `forum_rate_limit`, 2 s por defecto), con la
  cortesía compartida y el bloqueo por flood (`forum_scraper.py:367-400,449-456`); `_get` decodifica,
  detecta flood y no sigue redirecciones fuera de origen (`:566-590`).
* **Intervalo/cupos:** `_seguimiento_loop` duerme `seguimiento_interval_minutes` (45 por defecto) entre
  pasadas (`main.py:263-276,435`); `ejecutar_pasada` limita temas, series de Prowlarr, deseos y avisos
  (`seguimiento.py:504-505,524-525,536-545,548`); `config.py:282-288` fija 45/10/10/10/5/90 y los
  topes `ge/le`. `max_temas` se pasa a `listar_temas` y el bucle corta a `max_temas`;
  `max_series_prowlarr` ordena y corta; `max_deseos` deduplica y recorta antes de `crear_deseos`;
  `max_avisos` recorta antes de `avisar`. **Pasa.**
* **Robots:** el foro **no consulta `robots.txt`**: `_get` usa `pedir_con_cortesia`, y
  `FUENTES_CON_ROBOTS` no incluye `foro` (`utils/robots.py:57-58`; M4 lo declara «el foro **no** usa
  robots», `docs/design/especificacion-M4-robots.md:17,42,94`). No es una regresión de esta PR, pero el
  benchmark documenta que el robots del foro es `Disallow: /` y pide ratificación de PO/legal antes de
  convertir la integración en función estable (`benchmark-deseados-prowlarr-foro-2026-11-15.md:218-220,
  265-268`). **O-1.**

### 1.3 SSRF: sin URLs externas nuevas

* El foro es el configurado por el operador: `ejecutar_pasada` crea `ForumScraper(base_url=settings.forum_url)`
  (`seguimiento.py:487-495`), y **todos** los enlaces del HTML pasan por `_resolver_enlace`, que exige
  el origen exacto, rechaza credenciales y esquemas/host ajenos y reduce los absolutos a ruta+query
  (`forum_scraper.py:533-564`). `listar_temas` ignora los `href` que no resuelven; `leer_tema` vuelve a
  comprobar `origen_de(url) == self._origen` (`:614-620`). No hay parámetro de URL del usuario en la
  ruta ni en el job.
* Prowlarr se usa con el `ProwlarrClient()` de la configuración existente (`seguimiento.py:513-527`);
  `_procesar_prowlarr` solo pasa `serie.title` como consulta y los indexers elegidos, nunca una URL
  externa (`:407-413`). `prowlarr.search` usa su `_base` configurada (`prowlarr.py:93-120`).
* No hay nuevas fuentes, hosts ni descargas; los enlaces ed2k/magnet solo se **leen** para extraer
  nombres de fichero y no se guardan (`seguimiento.py:142-160`). **Pasa.**

### 1.4 Notifier: nombres opcionales y mejor esfuerzo

`_texto_novedades` devuelve un título con el número de novedades y **cuerpo genérico** («Abre ZascArr…»)
si `webhook_incluir_nombres` está apagado; solo con el flag activo incluye `titulo_serie #numero`
(`notifier.py:106-116`). `notify_novedades` no hace red si el webhook está apagado o no hay novedades
(`:118-124`); `avisar` es mejor esfuerzo tras el `commit` y captura cualquier error (`seguimiento.py:305-318`).
No se envían URLs, enlaces ed2k/magnet ni el título del tema del foro. **Pasa**; O-3 deja como deuda la
prueba de integración de llamada única/máximo 5.

### 1.5 Legal: activar exige acuse; el job no actúa sin él

* `ejecutar_pasada` llama a `is_acknowledged(db)` **antes** de cargar series o abrir foro/Prowlarr; si no
  hay acuse, registra `seguimiento.sin_legal` y retorna sin deseos ni red (`seguimiento.py:469-480`).
* `POST /ui/series/{id}/seguimiento` (`web/series.py:953-982`) solo fija `follow_new_issues`/`since` al
  activar si `is_acknowledged`; sin acuse devuelve el parcial con «Falta aceptar el aviso legal», enlace
  `/ui/legal` y **no cambia el flag**. Desactivar no exige acuse y no borra `since` ni deseos.
* `avisar` solo se llama después del commit y de `crear_deseos`; si no hay acuse, el retorno temprano
  impide ambos. **Pasa.**

### 1.6 Datos: `seguimiento_vistos` sin enlaces ni títulos

`SeguimientoVisto` (`models/__init__.py:1214-1235`) no tiene columnas de URL/título; `_marcar_visto` guarda
`fuente`, `clave`, `huella` y `procesado_en` (`seguimiento.py:211-224`). Para el foro `clave=tema:<id>` y
`huella` es la actividad normalizada; para Prowlarr `clave=release:<sha256(indexer|título|size)>` y
`huella` es la fecha ISO; para rotación `serie:<uuid>` (`:382-441`). El título del tema del foro
(`TemaForo.titulo`) **no se persiste**; el de Prowlarr solo entra en el hash. **Pasa.**

### 1.7 Migraciones 0047/0048

* **0047** (`alembic/versions/20261117_0047_seguimiento_series.py:19-52`): añade
  `series.follow_new_issues` (`NOT NULL DEFAULT false`), `follow_new_issues_since` (nullable), el valor
  `seguimiento` a `wishlist_origen`, la tabla `seguimiento_vistos` y su índice `visto_en`. No usa el valor
  nuevo en la misma transacción; el índice único se separa en 0048.
* **0048** (`..._0048_seguimiento_indice.py:17-31`): crea `uq_wishlist_seguimiento_numero` con predicado
  inmutable `origen <> 'manual' AND numero IS NOT NULL`, que cubre política y seguimiento y deja fuera los
  manuales. La migración es aditiva; el downgrade de 0047 retira tabla/columnas (el valor de enum no se
  puede quitar y queda documentado). No hay columnas de enlace/título ni secretos. QA la ejecutó con
  Postgres real (`informe-qa-seguimiento-series-2026-11-17.md`, addendum: `0046→0047→0048→0046→head`,
  OK). **Pasa.**

### 1.8 §5.8 y ficheros sensibles

El diff **no incluye** `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`; la
nueva ruta es `web/series.py` y no toca contraseña de acceso, sesión ni reautenticación. **§5.8 no
aplica**; no hay secretos nuevos en configuración ni HTML.

### 1.9 Regresión y herramientas

* QA final (`8cf17b73`): **7705 passed / 2383 skipped ×2**, 0 fallos; suites tocadas **324 passed,
  1 skip**; `ruff check src/` limpio; sonda 4/4 de B1/B2 y migración PG real.
* Mi ejecución focalizada (`test_seguimiento_*`, `test_web_serie_seguimiento`,
  `test_migracion_seguimiento_pg` [skip sin URL], `test_enums_bd_strenum`, `test_orchestrator`,
  `test_migraciones_cadena`, `test_notifier`, `test_web_series`): **324 passed, 1 skipped** en 7,40 s;
  `ruff check src/` y `--select S` verdes. La suite completa del Lead está en curso.
* `ffb0e8e8` solo cambia documentación y la **nota** de 0047; el código funcional es el QA-APTO.

---

## 2. Observaciones no bloqueantes

### O-1 — El foro no consulta `robots.txt` (decisión legal ya documentada, a ratificar)

`ForumScraper._get` usa `pedir_con_cortesia` y no `GestorRobots`; `FUENTES_CON_ROBOTS` excluye `foro`
(`utils/robots.py:57-58`) y M4 lo declara «el foro **no** usa robots»
(`especificacion-M4-robots.md:17,42,94`). El benchmark documenta `Disallow: /` en el foro y exige que la
integración siga siendo **opt-in**, con URL/credenciales del operador y aviso, y que PO/legal ratifiquen
antes de convertirla en función estable (`benchmark-…:218-220,265-268`). La PR **no añade** una consulta
de robots ni un aviso nuevo de ese punto: el foro sigue apagado por defecto y el job solo se activa si el
operador lo configuró y aceptó el aviso legal. **No es una regresión de esta PR**, pero conviene que
PO/legal confirmen expresamente el caso de scraping periódico (no solo búsqueda manual) antes de
fusionar; si se decide añadir robots, `foro` debe entrar en el mapa de `FUENTES_CON_ROBOTS` y el job
debe tratar `AccesoProhibidoPorRobots` como parada, no como error.

### O-2 — Frontera por serie en temas ya vistos que se actualizan

En `_procesar_foro` la comprobación `actividad < serie.follow_new_issues_since` solo se aplica cuando
`fila is None` (`seguimiento.py:340-355`). Si un tema ya estaba en `seguimiento_vistos` y su huella
cambia, se abre y **no** se filtra por la frontera de una serie activada después; un enlace antiguo del
tema podría generar su deseo. Es una arista funcional de la primera pasada (no de seguridad), no cubierta
por el fix B2 (que solo prueba tema nuevo). Recomendación: aplicar el filtro por serie también a las
filas existentes o guardar la frontera por `(serie, tema)`.

### O-3 — Cobertura declarada por QA

Sin `tests/test_seguimiento_prowlarr.py` (rotación/cupo/duplicados), sin integración de
`notify_novedades` única/máximo, sin prueba AC-16 y con **NOT RUN** del HTML real autenticado de
`showforum=5` y del comportamiento de IPB ante temas actualizados/flood. Son deudas de QA ya declaradas;
no hay hallazgo de seguridad.

### O-4 — `crear_deseos` sin `ON CONFLICT DO NOTHING`

`crear_deseos` hace `db.add(Wishlist(...))` y el índice único parcial está pensado para pasadas
solapadas; dos inserts concurrentes podrían lanzar `IntegrityError`. El job es secuencial y de un solo
worker, riesgo bajo; no bloqueante.

---

## 3. Conclusión

**Dictamen FAVORABLE para `ffb0e8e8a3abd65e8a0e3042c4677feeb3e41078`**, con **§5.8 no aplicable**. No hay
fugas de credenciales/cookies/`s=`, ni URLs nuevas que permitan SSRF; el listado de foro es una sola
lectura por pasada, sin Search, con cortesía/rate limit e intervalo/topes; el notifier no revela URL/token
ni nombres sin el flag; la puerta legal bloquea deseos y avisos sin acuse; `seguimiento_vistos` no guarda
enlaces/títulos; las migraciones son aditivas y sin secretos. O-1 (robots del foro) y O-2 (frontera por
serie en tema actualizado) son observaciones no bloqueantes para seguimiento; O-3/O-4 son deudas ya
declaradas. Este informe aplica solo a este SHA y está en el árbol de trabajo sin commitear.

| Punto de task-69 | Sección |
|---|---|
| Cookies/credenciales/`s=` fuera de logs, HTML y `seguimiento_vistos` | 1.1, 1.6 |
| Foro: una GET `showforum`, sin Search 25 s, 45 min, topes/rate limit | 1.2 |
| SSRF: foro configurado, `_resolver_enlace`/origen, Prowlarr local | 1.3 |
| Notifier: sin URL/token, nombres solo con flag, mejor esfuerzo | 1.4 |
| Legal: acuse para activar; sin deseos/avisos sin acuse | 1.5 |
| `seguimiento_vistos` solo fuente/clave/huella | 1.6 |
| Migraciones 0047/0048 aditivas y sin secretos | 1.7 |
| §5.8 n/a; ruff y regresión | 1.8, 1.9 |
