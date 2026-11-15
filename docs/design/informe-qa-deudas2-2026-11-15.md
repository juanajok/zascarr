# Informe QA — Deudas lote 2: rotación de huecos, payloads vacíos, atribución e importación (2026-11-15)

**Rol:** QA · **Tarea:** task-52 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/deudas2`
**Rama:** `fix/deudas2`, SHA **`3e2cebf71287fcbe14b3002126ea1a3faf2e2f7a`** (verificado con
`git rev-parse HEAD`; PR #850 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin red ni `TEST_DATABASE_URL`.
El único fichero escrito es este informe; el scratch de QA (`.qa-deudas2/`) se borra al terminar.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q` (suite completa, 1.ª pasada) | **7111 passed, 2289 skipped**, 4 warnings, 0 fallos | 350,15 s (wall 5:50) |
| `pytest -q` (suite completa, 2.ª pasada) | **7111 passed, 2289 skipped**, 4 warnings, 0 fallos | 361,46 s (wall 6:01) |
| `pytest -q` suites tocadas (enricher, relleno, clientes GCD/Metron/OL, web_arcos_guia, web_series) | **236 passed** | 5,62 s (wall 7,01 s) |
| `ruff check src/` | **All checks passed!** | — |

Las dos pasadas completas dan **exactamente los mismos contadores** y cero fallos; los 2289 skips
son los esperados sin `TEST_DATABASE_URL` (pruebas `*_pg`). Los 4 warnings son preexistentes (`ComicInfo.xml` duplicado;
`AsyncMock` sin await en importer), ajenos al lote.

---

## 2. Reproducción independiente — **9/9 OK**

Sonda propia con series falsas (incluido `enrichment_attempted_at`), una sesión que captura la
consulta, clientes contadores y `httpx.MockTransport`:

* **O1 rotación.** Con dos series candidatas y `limit=1`, se procesa la de
  `enrichment_attempted_at` más antiguo (no la primera por id); el límite solo lo consume una fila
  cubrible. Tres series con todos los campos en `locked_fields` no consumen el lote: se marcan con
  `metadata_["relleno"]["_sin_huecos_cubribles"]` y la serie cubrible sí se rellena (años GCD). La
  segunda pasada no vuelve a pedir para las marcadas; a los 31 días la marca caduca y se reevalúa.
* **O2 payloads vacíos.** GCD `{"name": ""}`, Metron `{"id": 1}` sin datos y Open Library
  `{"key": "/works/OL1W"}` sin título/descripción/año devuelven `None`; con datos útiles devuelven
  ficha (GCD años, Metron descripción/años, OL descripción/año).
* **O3 atribución sin URL.** Con `url_ficha="javascript:alert(1)"`, `atribucion_de_relleno` sigue
  devolviendo la entrada con `url_ficha=""` (nombre GCD y licencia CC BY-SA 4.0 visibles); la
  plantilla usa `{% if datos.url_ficha %}…{% else %}{{ datos.nombre }}{% endif %}` y no genera
  `href=""` ni `javascript:`. La prueba de ficha con URL de host ajeno pasa en la suite.
* **O4 guía UI.** Commit que lanza `RuntimeError` y servicio que lanza `RuntimeError` → **200** con
  «No se pudo importar la guía», `rollback` llamado y sin 500. El log genérico
  `arcos.importar_guia_failed` contiene solo `fuente` y `error` (tipo), sin `exc_info` ni URL
  (la excepción de prueba llevaba la URL y no aparece en el volcado).
* **f) diff limpio.** Sin `web/ajustes.py`, `models/`, `alembic/`, `services/seguridad.py` ni
  `reautenticacion`.

---

## 3. Aceptación

**(a) O1 — rotación y marca `_sin_huecos_cubribles`.** `_enrich_huecos_por_id` (`enricher.py:425+`)
ordena por `Series.enrichment_attempted_at.asc().nullsfirst(), Series.id` (`:452`), recupera
`max(limit*50, 500)` filas y las reordena en Python por «intentada antes / timestamp / id»
(`clave_de_turno`). `_sin_huecos_cubribles_vigente` (`:266`) y
`_marcar_sin_huecos_cubribles` (`:283`) marcan en JSONB (dict nuevo) durante 30 días; las marcadas
se saltan sin consumir `limit` ni hacer red. `procesadas` solo incrementa cuando
`_fuente_cubrible` (`:292`) encuentra al menos una fuente con id, tradición, TTL y
`campos_faltantes`. Pruebas: `test_relleno_huecos.py::test_o1_el_lote_salta_series_sin_huecos_cubribles_y_avanza`
y sonda §2.

**(b) O2 — payload vacío → `None`.** `GCDClient.get_series_por_id` devuelve `None` si no hay
nombre ni años (`gcd.py:293-296`); `MetronClient.get_series_por_id` si no hay nombre, años ni
descripción (`metron.py:185-188`); `OpenLibraryClient.get_work` si no hay título, descripción ni
año (`open_library.py:161-164`). Con datos útiles siguen devolviendo ficha. Pruebas:
`test_relleno_huecos.py::test_o2_payload_vacio_o_sin_datos_utiles_es_none` + sonda.

**(c) O3 — atribución visible sin URL válida.** `atribucion_de_relleno` (`atribucion.py:53-74`)
incluye la fuente si tiene `campos`, aunque `url_ficha` no valide (`""`); `series_detail.html:72`
pinta el nombre como texto sin `<a>` cuando no hay URL y mantiene el enlace de licencia. No puede
haber `href=""` (se usa `{% if datos.url_ficha %}`) ni `javascript:` (`_url_de_ficha` exige https y
host permitido; `javascript:` se rechaza). Prueba:
`test_web_series.py::TestAtribucionRellenoSinUrl` + sonda.

**(d) O4 — errores de importación controlados.** En `importar_guia` (`arcos.py:200-243`) el
extractor, `leer_y_reconciliar`, la comprobación de `resultado`/`arco_id` y **el `commit`** están
dentro del `try`; `RuntimeError` cae en `except Exception` (`:230`), hace `rollback` y devuelve
200 con «No se pudo importar la guía. Inténtalo de nuevo.». Sin 500. Pruebas:
`test_web_arcos_guia.py::test_m1_si_el_commit_falla_no_hay_500_y_se_revierte` y
`test_m1_si_el_servicio_lanza_no_hay_500_y_se_revierte` + sonda.

**(e) O4/m-2 — log genérico sin URL ni traza.** `logger.error("arcos.importar_guia_failed",
fuente=fuente, error=type(exc).__name__)`; sin `exc_info`, URL, query ni cuerpo. Prueba:
`test_web_arcos_guia.py::test_m2_el_log_generico_no_vuelca_traza_ni_url` + sonda (el `repr` del
log no contiene `comicbookreadingorders` ni `exc_info`).

**(f) Sin migraciones/`models`/Ajustes/seguridad.** `git diff HEAD~1 HEAD --name-only` son 10
ficheros (**+237/−23**): `services/{enricher,gcd,metron,open_library}.py`,
`web/{arcos,atribucion}.py`, `web/templates/series_detail.html` y
`tests/{test_relleno_huecos,test_web_arcos_guia,test_web_series}.py`. No hay `models/`,
`alembic/`, `web/ajustes.py`, `services/seguridad.py` ni `services/reautenticacion.py`.

---

## 4. Observaciones y riesgos (no bloqueantes)

**O1a — Marcadas y `limit` de la consulta.** Las filas con `_sin_huecos_cubribles` se saltan sin
consumir `limit`, pero la consulta trae como máximo `max(limit*50, 500)` filas; si hubiera más de
esas filas marcadas por delante, una pasada podría no llegar a candidatas posteriores. No afecta a
los AC (la marca evita repetir y no consume el `limit` lógico), pero conviene excluirlas también en
el `select` o aumentar el prefetch.

**O1b — Fuente cortada cuenta como cubrible.** `_fuente_cubrible` no conoce el conjunto `cortadas`;
si una fuente se corta por un fallo transitorio, las series posteriores que solo tienen esa fuente
se cuentan en `procesadas` aunque el bucle no les haga peticiones. Es una pérdida de eficiencia
puntual en el ciclo (no repite red ni cambia datos); pasar `cortadas` a `_fuente_cubrible` lo
evitaría.

**O2 — La marca de 30 días no distingue de por qué no había huecos cubribles.** Si el usuario
enciende después una fuente con token, esas series siguen marcadas hasta que caduque la marca (30
días). Es coherente con el TTL pedido, pero conviene limpiar la marca al cambiar la configuración
de fuentes en una historia futura.

**O3 — La licencia se pinta siempre como enlace**, aunque la ficha no tenga URL válida; las URLs de
licencia de `FUENTES_DE_RELLENO` son constantes https no vacías, así que no hay `href=""` actual.

**O4 — `logger.error` en vez de `logger.exception`**: correcto para no volcar traza; el tipo se
conserva en `error`. No se registra el mensaje de la excepción (podría llevar datos), lo que es
deliberado.

---

## 5. Veredicto

**APTO.** El lote 2 cumple (a)-(f): O1 filtra por huecos cubribles/TTL, ordena por
`enrichment_attempted_at` (más antigua primero) y marca `_sin_huecos_cubribles` durante 30 días sin
consumir el límite lógico; O2 los tres clientes devuelven `None` con payloads vacíos/sin datos
útiles; O3 la atribución se ve aunque la URL de ficha no valide, sin `href=""` ni `javascript:`;
O4 el extractor, la reconciliación y el `commit` están dentro del `try` y un `RuntimeError` de
servicio o de commit devuelve 200 con mensaje llano y rollback; el log genérico solo lleva fuente y
tipo de error, sin URL ni traza; sin migraciones, `models`, `web/ajustes.py` ni seguridad. Suite
completa verde **dos veces** con contadores idénticos (7111 passed / 2289 skipped, 0 fallos),
suites tocadas verdes (236 passed) y `ruff check src/` limpio.

**Bloqueantes: ninguno.** Observaciones no bloqueantes: O1a el prefetch (`max(limit*50, 500)`)
podría no llegar a candidatas si hay más de esas filas marcadas por delante; O1b una fuente cortada
tras un fallo transitorio sigue contando como «cubrible» en series posteriores (consume cupo del
ciclo sin petición, sin cambiar datos); O2 la marca de 30 días no se limpia al encender después una
fuente con token; O3 la licencia se pinta siempre como enlace (constantes https no vacías); O4 se
usa `logger.error` en vez de `logger.exception` (deliberado: sin traza).

---

## 6. Comandos reproducibles

```
cd .worktrees/deudas2
PYTHONPATH=src … -m pytest -q
PYTHONPATH=src … -m pytest -q tests/test_enricher.py tests/test_relleno_huecos.py \
    tests/test_web_arcos_guia.py tests/test_web_series.py tests/test_fix_qa_gcd_526.py \
    tests/test_gcd_cortesia.py tests/test_gcd_idioma_464.py tests/test_gcd_paginar_523.py \
    tests/test_gcd_year_errors_526.py tests/test_fuentes_metron_openlibrary.py \
    tests/test_discovery_metron_openlibrary.py tests/test_clientes_cortesia.py
PYTHONPATH=src … -m ruff check src/
PYTHONPATH=src … <venv>/bin/python .qa-deudas2/probe.py      # 9/9 OK
```

---

## 7. Inventario del cambio revisado (`3e2cebf7`)

10 ficheros, **+237 / −23**: `services/enricher.py` (rotación/marca),
`services/{gcd,metron,open_library}.py` (payload vacío), `web/arcos.py` (commit/log),
`web/atribucion.py` + `web/templates/series_detail.html` (atribución sin URL) y
`tests/{test_relleno_huecos,test_web_arcos_guia,test_web_series}.py`. Sin migraciones, `models`,
`web/ajustes.py` ni seguridad.
