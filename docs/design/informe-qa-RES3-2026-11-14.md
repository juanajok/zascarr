# Informe QA — RES-3: streaming con tope real de bytes (2026-11-14)

**Rol:** QA · **Tarea:** task-38 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/res3-streaming`
**Rama:** `feat/res3-streaming`, SHA **`01525ef17542c20f27e61df971d28f637cacac40`**
(verificado con `git rev-parse HEAD`; PR #819 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL` (RES-3 no usa Postgres).
El único fichero escrito es este informe; el scratch de QA (`.qa-res3/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7011 passed, 2285 skipped**, 4 warnings, 0 fallos | 335,79 s (wall 5:39) |
| `pytest -q` (suite completa, 2.ª pasada) | **7011 passed, 2285 skipped**, 4 warnings, 0 fallos | 336,42 s (wall 5:40) |
| `pytest -q` suites tocadas/consumidores (peticiones, cache_http, fandom, enricher, foro, herald, guías, ajustes) | **414 passed** | 8,67 s (wall 10,08 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos: no hay
contaminación entre pruebas. Los 2285 skips son los esperados sin `TEST_DATABASE_URL` (pruebas
`*_pg`). Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado; `AsyncMock` sin await en
importer), ajenos a RES-3.

---

## 2. Reproducción independiente — **15/15 OK**

Además de las pruebas del builder, construí un transporte propio (`MockTransport` y
`httpx.AsyncByteStream` con contadores de trozos), un reloj simulado y una caché en memoria, y
ejercité `pedir_con_cortesia`/`pedir_con_cache` reales con un tope pequeño (1024 B):

* **AC-01** cap exacto → `.content` completo, 1 petición.
* **AC-02** cap+1 → `CuerpoDemasiadoGrande(motivo="chunks")`, `bytes_leidos=1025` (>cap y
  ≤cap+64 KiB), 1 petición, **un único** log `peticiones.cuerpo_demasiado_grande`, y el volcado
  del log no contiene URL/query; la excepción **no** es `RespuestaNoTransitoria`.
* **AC-03** sin `Content-Length` → mismo corte por chunks.
* **AC-04** `Content-Length` > cap → `motivo="content_length"`, `bytes_leidos=0` y el stream
  **no sirvió ni un trozo**.
* **AC-05** `Content-Length` mentiroso (dice 10, manda 1025) → corta por chunks.
* **AC-06** 302 con cuerpo de 10×cap → **no se lee** (`leidos=0`), se siguen 2 peticiones y se
  devuelve el destino pequeño.
* **AC-07** 500→200 normal → 200 con 2 peticiones; cap+1 en la final → corta; el tope **no** se
  reintenta (1 petición).
* **AC-08** `pedir_con_cache` con cuerpo cap+1 → `CuerpoDemasiadoGrande` propagada y **0 filas**
  escritas en la caché falsa (ni negativa); el cuerpo normal sigue cacheando y sirviendo JSON.
* **AC-09** la `Response` reconstruida conserva `.status_code`, `.content`, `.text`, `.json()` y
  `.headers`.
* **AC-10** POST `form=True` con `form_charset="iso8859-1"` mantiene el cuerpo
  (`q=A%F1o`) y el `Content-Type` con charset.
* **AC-11** goteo lento que agota `deadline` → `CortesiaEnEspera(motivo="cuerpo_lento")`.
* **AC-12** gzip-bomba (comprimido pequeño, decodificado > cap) → corta por chunks contando
  bytes **descomprimidos**.
* **AC-13** suites existentes verdes (abajo).

También comprobé a mano: 307 conserva POST y cuerpo (la suite cubre además 301/302/303→GET,
307/308 y 4 saltos), y la configuración: `Settings(_env_file=None).max_cuerpo_transfer_bytes ==
4 MiB`, acepta 1 MiB y 16 MiB, rechaza los valores fuera de rango, y la variable llega por
`docker-compose.yml` (`MAX_CUERPO_TRANSFER_BYTES=${…:-4194304}`) y figura en `.env.example`.

---

## 3. Aceptación (13 AC de la spec)

Todos los AC se cumplen:

* **AC-01…AC-07 (corte y redirecciones/reintentos).** `_leer_con_tope` (`peticiones.py:252-290`)
  abre `cliente.stream`, devuelve los 3xx **sin leer el cuerpo**, pre-chequea `Content-Length`
  (solo pista) y lee `aiter_bytes(64 KiB)` acumulando; al superar el límite lanza
  `CuerpoDemasiadoGrande` (ErrorDePeticion, **no** `RespuestaNoTransitoria`) con
  `motivo/bytes_leidos/limite` y un log único con `host` (nunca URL). Las redirecciones siguen
  resolviéndose en `_seguir_redirecciones` (301/302/303→GET; 307/308 conservan método y cuerpo);
  el reintento 500→200 no cambia y el corte no entra en el bucle de reintentos.
  Pruebas: `tests/test_peticiones.py` (`_Flujo`, `TestTopeDeCuerpo`, AC-01…07/10) + sonda §2.
* **AC-08 (`cache_http`).** La excepción se propaga antes de `cache.escribir`; no hay fila ni
  negativa falsa. Pruebas: `tests/test_cache_http.py::test_un_cuerpo_enorme_se_propaga_sin_escribir_cache`
  y `test_el_cuerpo_normal_sigue_cacheando_y_sirviendo_json`; sonda §2.
* **AC-09 (consumidores).** Fandom, Herald, guías y Ajustes siguen recibiendo `.json()/.text/
  .content/.headers/.status_code` normales; las suites tocadas (414 tests) y la completa quedan
  verdes. Sonda §2.
* **AC-10 (`form_charset`/POST).** El cambio de transporte conserva `_argumentos_de_peticion` y el
  cuerpo codificado; prueba nueva y sonda.
* **AC-11 (goteo lento).** Entre trozos se comprueba `reloj() > deadline` y se lanza
  `CortesiaEnEspera(..., "cuerpo_lento")`; prueba y sonda.
* **AC-12 (gzip-bomba).** `aiter_bytes` descomprime antes del conteo; prueba y sonda.
* **AC-13 (suites).** Completa verde (dos pasadas) y consumidores verdes (414 aislados).

**Config/compose.** `config.py:46-52` define `max_cuerpo_transfer_bytes` con default 4 MiB y
`ge=1 MiB, le=16 MiB`; `.env.example` y `docker-compose.yml` lo documentan/inyectan.

**Log.** Evento único `peticiones.cuerpo_demasiado_grande` con `fuente`, `motivo`,
`bytes_leidos`, `limite` y `host`; sin URL, query ni cuerpo (verificado en la sonda).

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1 — `CuerpoDemasiadoGrande` en consumidores que no capturan `ErrorDePeticion`.** Comic Vine,
GCD y Discovery capturan `RespuestaNoTransitoria`, no `ErrorDePeticion`; un cuerpo >4 MiB les
llega al `except Exception` del enricher (registra y sigue), y el ciclo podría repetirlo en cada
pasada de 6 h. La spec §6 lo declara y lo deja al Corte 2; no es un fallo de RES-3 (no hay bucle
de reintentos dentro de la petición), pero conviene marcarlo explícitamente en el ciclo en una
tarea posterior.

**O2 — No hay prueba dedicada del rango de `max_cuerpo_transfer_bytes` en el repo.** El builder
no añadió un test de `Settings` para `ge/le` (sí la prueba de comportamiento con un tope pequeño).
Lo he verificado con sonda propia (1/16 MiB aceptados, fuera de rango rechazado); recomendaría un
test mínimo de config para que no se pierda.

**O3 — Doble copia final.** La `Response` reconstruida con `bytes(bytearray)` duplica el pico
(≈2×cap por petición en vuelo); la spec lo documenta y lo acepta para 512 MB. No se mide aquí el
pico real con el default de 4 MiB; la prueba usa topes pequeños.

---

## 5. Veredicto

**APTO.** RES-3 cumple los 13 AC: suite completa verde **dos veces** con contadores idénticos
(7011 passed / 2285 skipped, 0 fallos), suites de consumidores tocadas verdes (414 passed) y
`ruff check src/` limpio. El tope real se comporta como la spec: cap exacto pasa; cap+1, chunked,
`Content-Length` mentiroso y gzip-bomba cortan por chunks; `Content-Length` > cap corta sin leer
ni un trozo; los 3xx con cuerpo enorme no se leen y las redirecciones/reintentos siguen igual; el
goteo lento da `CortesiaEnEspera("cuerpo_lento")`; `cache_http` no escribe fila/negativa; la
`Response` conserva `.content/.text/.json()/.headers/.status_code`; `form_charset`/POST intactos;
el log no lleva URL; `max_cuerpo_transfer_bytes` tiene default 4 MiB, rango 1–16 MiB y llega por
`.env.example`/Compose.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1 (consumidores que no capturan
`ErrorDePeticion` — Comic Vine/GCD/Discovery — lo verán en el manejador genérico del enricher y
podrían repetirlo cada ciclo; deuda declarada del Corte 2), O2 (no hay test dedicado del rango de
config; verificado con sonda) y O3 (doble copia final ≈2×cap documentada y aceptada).

---

## 6. Comandos reproducibles

```
cd .worktrees/res3-streaming
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_peticiones.py tests/test_cache_http.py \
    tests/test_fandom.py tests/test_enricher.py tests/test_forum_scraper.py \
    tests/test_forum_flood.py tests/test_forum_ajustes_http.py tests/test_forum_intervalos.py \
    tests/test_comic_book_herald.py tests/test_reading_orders.py tests/test_web_ajustes.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-res3/probe.py      # 15/15 OK
```

---

## 7. Inventario del cambio revisado (`01525ef1`)

8 ficheros, **+522 / −59**: `.env.example`, `docker-compose.yml`, `src/zascarr/config.py`,
`src/zascarr/utils/peticiones.py` y `tests/{test_peticiones,test_cache_http,test_enricher,
test_web_ajustes}.py`. Sin cambios en `models/`, `alembic/`, `web/ajustes.py` ni
`services/seguridad.py`; `url_portada.py` no se toca (camino aparte).
