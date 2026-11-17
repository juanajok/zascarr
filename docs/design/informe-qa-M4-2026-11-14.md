# Informe QA — M-4: tope de `Crawl-delay` y olvido de robots por fuente (2026-11-14)

**Rol:** QA · **Tarea:** task-42 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/m4-robots`
**Rama:** `feat/m4-robots`, SHA **`8c8d6eec87e5d82917062c9cdbfef4b95ca5ef71`** (verificado con
`git rev-parse HEAD`; PR #832 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL` en las pruebas nuevas.
El único fichero escrito es este informe; el scratch de QA (`.qa-m4/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7056 passed, 2285 skipped**, 4 warnings, 0 fallos | 450,40 s (wall 7:30) |
| `pytest -q` (suite completa, 2.ª pasada) | **7056 passed, 2285 skipped**, 4 warnings, 0 fallos | 541,06 s (wall 9:01) |
| `pytest -q` suites tocadas (`robots`, `web_ajustes*`, `cache_http`, `cortesia*`) | **167 passed** | 10,97 s (wall 12,74 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
contaminación entre pruebas. Los 2285 skips son los esperados sin `TEST_DATABASE_URL` (pruebas
`*_pg`). Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en
importer), ajenos a M-4.

---

## 2. Reproducción independiente — **11/11 OK**

Además de las pruebas del builder, escribí una sonda propia con `GestorRobots`, cuerpos de
`robots.txt` sintéticos, `descargar_robots_fn` con contador y `structlog.testing.capture_logs`:

* **AC-01** `Crawl-delay: 86400` con máximo 60 ⇒ `(permitido=True, 60.0)` y **un único** log
  `robots.crawl_delay_recortado` (`declarado_s=86400`, `recortado_s=60`, `maximo_s=60`,
  `origen=https://dc.fandom.com` sin path/query); dos evaluaciones seguidas ⇒ una sola descarga y
  un solo aviso.
* **AC-02** `Crawl-delay: 30` ⇒ 30 y **sin** log.
* **AC-03** mínimo local 2,5 s con delay 1 ⇒ 2,5 s; mínimo local 90 s con cap 5 ⇒ 90 s.
* **AC-04** ausente/`0`/`-3`/`NaN`/`abc` ⇒ sin cambio (`None`), sin excepción; `inf` ⇒ 60 (cap).
* **AC-05** cambiar `crawl_delay_max_s` de 60 a 120 sobre la misma entrada cacheada ⇒ 120 en la
  siguiente evaluación, **sin** nueva descarga y con el parser crudo (86400) intacto.
* **AC-06** dos orígenes cacheados; `olvidar(uno)` ⇒ el otro no descarga y el olvidado vuelve a
  descargar (contador 2→3).
* **AC-07** `unreachable_disallow` (500) sobrevive sin olvidar; al olvidar, la siguiente
  evaluación descarga y permite.
* **AC-08** evaluación en vuelo (`asyncio.Event`) + `olvidar` ⇒ devuelve su resultado pero **no**
  escribe la caché; la siguiente descarga otra vez (2 descargas).
* **AC-09** `origenes_de_fuente`: DC (`https://dc.fandom.com`), Marvel
  (`https://marvel.fandom.com`), RO (`https://comicbookreadingorders.com`), CG
  (`https://www.continuityguide.net`), Herald (`https://www.comicbookherald.com` desde config);
  foro/portada/desconocida ⇒ `()`; `olvidar_origenes_de_fuente` devuelve el mapeo **sin instanciar**
  `_GESTOR_DE_PROCESO`.
* **AC-10** POST real a `/ui/ajustes/guardar/fuentes` (TestClient, `save` y gestor simulados):
  **200**, solo se olvida `fandom_dc` cuando cambia; guardar lo mismo no olvida nada; la respuesta
  no contiene secretos (`SECRETO`/`password`). Las suites `test_web_ajustes*` (incluidas foro,
  contraseña y sesión) están verdes.
* **Config** `crawl_delay_max_s`: default 60, acepta 5 y 300, rechaza 4 y 301;
  `CRAWL_DELAY_MAX_S=${CRAWL_DELAY_MAX_S:-60}` en Compose y documentado en `.env.example`.

---

## 3. Aceptación (11 AC de la spec)

Todos se cumplen:

* **AC-01…AC-05 (tope de `Crawl-delay`).** `config.py:55` define `crawl_delay_max_s` (default 60,
  ge=5, le=300); `GestorRobots._maximo_crawl_delay` lo lee en cada evaluación y
  `_recortar_crawl_delay` (`robots.py:180-201`) aplica: `None`/no numérico/`NaN`/`<=0` ⇒ `None`
  (sin cambio); `inf` o > máximo ⇒ máximo, con log único por origen/entrada; `aplicar_crawl_delay`
  sigue subiendo el intervalo local. La entrada guarda el valor **crudo**, así que cambiar el
  setting no recarga robots (probado AC-05).
* **AC-06…AC-08 (olvido y generación).** `olvidar(origen)` (`robots.py:151-166`) normaliza con
  `_origen`, hace `_cache.pop`, sube `_generacion` y conserva `_candados`; `evaluar` captura la
  generación antes de cargar y solo escribe caché si no cambió, de modo que una evaluación en
  vuelo no resucita la entrada; `reiniciar()` limpia caché/candados/generación. Probado con dos
  orígenes, un `unreachable_disallow` y un `asyncio.Event`.
* **AC-09 (mapeo).** `origenes_de_fuente` (`robots.py:268-297`) usa imports perezosos y devuelve
  las 5 fuentes; `olvidar_origenes_de_fuente` (`:300-310`) no instancia el gestor si no existe y
  devuelve el mapeo. Sin ciclos de import (robots↔adaptadores).
* **AC-10 (Ajustes).** `guardar_fuentes` (`web/ajustes.py:358-406`) captura el estado previo de las
  cinco fuentes, guarda, y solo entonces olvida los orígenes de las que cambian
  (`_fuentes_de_robots_cambiadas`, `:351-355`); si `save` falla no se olvida. No toca
  `guardar_foro`/`guardar_seguridad`, no añade `Form` ni campos de whitelist, y la respuesta 200 no
  expone secretos. Las pruebas de contraseña/sesión (`test_web_ajustes.py`) siguen verdes.
* **AC-11 (sin red/Postgres).** Las pruebas nuevas usan cuerpos sintéticos y funciones falsas de
  descarga; no hay red ni `TEST_DATABASE_URL`; `test_robots.py` y `test_web_ajustes*` verdes en las
  dos pasadas completas.

**Sin migraciones ni cambios de whitelist.** `git diff HEAD~1 HEAD --name-only` no incluye
`models/`, `alembic/` ni `services/runtime_settings.py` (whitelist `OVERRIDABLE_FIELDS` intacta);
el commit son 7 ficheros (+480/−3): `.env.example`, `docker-compose.yml`, `config.py`,
`utils/robots.py`, `web/ajustes.py` y los dos ficheros de pruebas nuevos/ampliados.

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — `_FUENTES_CON_ROBOTS` está duplicado.** `robots.py:57` exporta `FUENTES_CON_ROBOTS` y
`web/ajustes.py:347` repite la misma tupla con nombre `_FUENTES_CON_ROBOTS`; si se añade una fuente
con robots en el futuro, el mapeo y el olvido pueden desincronizarse. Recomendación: importar la
constante de `utils.robots` en Ajustes (import local, como ya se hace con
`olvidar_origenes_de_fuente`). No es un fallo actual.

**O2 — No hay prueba dedicada del rango de `crawl_delay_max_s`.** El builder no añadió un test de
`Settings` para `ge/le`; lo he verificado con la sonda (5/300 válidos, 4/301 rechazados). Sería
barato dejarlo como test de config.

**O3 — El olvido no invalida `http_cache`.** Es el límite explícito de la spec §2: `olvidar` limpia
solo memoria (parser/TTL/bloqueo); un `robots.txt` 200/4xx ya cacheado se re-parsea con el mismo
cuerpo hasta que expire (24 h/12 h). El caso que motiva el toggle (429/5xx/red, no cacheados) sí se
reintenta. Documentado, no se finge cubierto.

**O4 — `crawl_delay_max_s` solo por `.env` y requiere reinicio** (decisión de la spec: no se expone
en Ajustes ni se cambia en caliente). Está en Compose con default 60. Correcto por diseño.

---

## 5. Veredicto

**APTO.** M-4 cumple los 11 AC: suite completa verde **dos veces** con contadores idénticos
(7056 passed / 2285 skipped, 0 fallos), suites tocadas verdes (167 passed) y `ruff check src/`
limpio. El `Crawl-delay` se recorta al máximo configurable (60 s por defecto, 5–300), con log
único por origen/entrada y sin bajar nunca el mínimo local; los valores ausentes/0/negativos/NaN/
texto no cambian nada e `inf` cae al tope; cambiar el setting surte efecto en la siguiente
evaluación sin red; `olvidar(origen)` limpia solo ese origen, conserva el candado y la generación
impide que una evaluación en vuelo resucite la entrada; el mapeo cubre las 5 fuentes sin instanciar
el gestor; Ajustes solo olvida las fuentes que cambian (nunca si el guardado falla), responde 200
sin secretos y no toca foro, contraseña/sesión ni la whitelist; sin migraciones ni cambios en
`models`.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 (`_FUENTES_CON_ROBOTS` duplicado entre
robots y Ajustes: conviene importar la constante), O2 (no hay test dedicado del rango de config;
verificado con sonda), O3 (el olvido no invalida `http_cache` del cuerpo de robots, límite explícito
de la spec) y O4 (`crawl_delay_max_s` solo por `.env` y requiere reinicio, por diseño).

---

## 6. Comandos reproducibles

```
cd .worktrees/m4-robots
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_robots.py tests/test_web_ajustes_fuentes_robots.py \
    tests/test_web_ajustes.py tests/test_web_ajustes_fuentes_nuevas.py \
    tests/test_cache_http.py tests/test_cortesia.py tests/test_cortesia_estado.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-m4/probe.py      # 11/11 OK
```

---

## 7. Inventario del cambio revisado (`8c8d6eec`)

7 ficheros, **+480 / −3**: `.env.example`, `docker-compose.yml`, `src/zascarr/config.py`
(`crawl_delay_max_s`), `src/zascarr/utils/robots.py` (tope/log/olvido/generación/mapeo),
`src/zascarr/web/ajustes.py` (olvido solo de fuentes cambiadas), `tests/test_robots.py` (197 líneas
nuevas) y `tests/test_web_ajustes_fuentes_robots.py` (116). Sin `models/`, `alembic/` ni cambios en
la whitelist de ajustes en caliente.
