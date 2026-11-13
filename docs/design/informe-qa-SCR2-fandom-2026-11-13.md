# Informe QA — SCR2: integración Fandom (2026-11-13)

**Rol:** QA · **Tarea:** task-4 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Árbol revisado:** *working tree* del workspace compartido sobre `main` (HEAD `17a5995e`) con los
cambios de SCR2 **sin commitear** (2 ficheros nuevos y 13 modificados; el detalle, en §5).
**Entorno:** `PYTHONPATH=src .tmp-test-venv/bin/python -m pytest -q`, sin `TEST_DATABASE_URL`
(Postgres se salta, como corresponde a este entorno). Python 3.14, pytest 9.2 + pytest-asyncio.
No se ha modificado código ni tests: este informe es el único fichero que escribe QA.

> Contexto de ejecución: carga del sistema entre 3,2 y 4,9 (media 4,5) durante las pasadas, por
> trabajo concurrente de otras sesiones; relevante para §1.3.

---

## 1. Regresión

### 1.1 Contadores y tiempos

| # | Comando | Resultado | Tiempo |
|---|---|---|---|
| 1 | `PYTHONPATH=src .tmp-test-venv/bin/python -m pytest -q` | **2 failed, 6565 passed, 2256 skipped**, 4 warnings | 413,88 s (wall 6:57,8) |
| 2 | `PYTHONPATH=src .tmp-test-venv/bin/python -m pytest -q` | **6567 passed, 2256 skipped**, 4 warnings | 407,08 s (wall 6:50,6) |
| 3 | `PYTHONPATH=src .tmp-test-venv/bin/python -m pytest -q tests/test_fandom.py` | **24 passed** | 1,96 s (wall 3,52 s) |

Total coleccionado constante entre pasadas: **8823 pruebas** (run-1: 6565+2+2256; run-2: 6567+2256).
Sin `TEST_DATABASE_URL`, los **2256 skips** son los esperados: 113 ficheros `tests/*_pg.py` con
`pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL…")`, más pruebas dependientes de
binarios/entorno. No se han revisado una a una (el entorno de QA no tiene Postgres).

### 1.2 Fallos de la pasada 1

| Test | Módulo | Mecanismo |
|---|---|---|
| `test_lider_muere_con_term_y_un_hijo_lo_ignora` | `tests/test_ensayo_f1bis_arnes.py:604` | el hijo que ignora `TERM` no llega a escribir su PID antes de que el arnés corte |
| `test_listar_que_se_cuelga_tambien_vence` | `tests/test_lector_rar.py:303` | tras vencer el `timeout` de 0,6 s, el hijo del RAR falso seguía vivo |

Evidencia de que **no son de SCR2**:

* Ninguno de los dos ficheros está tocado por el cambio (`git status` no los lista).
* Los dos pasan **3/3 veces aislados**:
  `pytest -q tests/test_ensayo_f1bis_arnes.py::TestElCorteTerminaElGrupoEntero::test_lider_muere_con_term_y_un_hijo_lo_ignora tests/test_lector_rar.py::test_listar_que_se_cuelga_tambien_vence`
  → `2 passed in 2.79s`, `2 passed in 2.81s`, `2 passed in 2.57s`.
* La pasada 2 (sin cambios de código entre medias) queda **limpia**.

Conclusión de contaminación: **no hay contaminación atribuible a la integración Fandom**; los dos
fallos son *flakes* de pruebas de señales/tiempos bajo carga, en módulos ajenos al cambio. La suite
completa queda verde en la segunda pasada.

### 1.3 Warnings (4, sin fallo)

`UserWarning: Duplicate name: 'ComicInfo.xml'` en `test_b6_cbz` y `RuntimeWarning: coroutine
'AsyncMockMixin._execute_mock_call' was never awaited` en `test_importer`/`test_bucle_no_bloqueado`.
No apuntan a Fandom; no se investigan aquí (pre-existentes, fuera del alcance de SCR2).

---

## 2. Aceptación por criterio

### (a) Fuentes apagadas por defecto (ADR 0013) y encendido en Ajustes — **PASA**

* Defaults: `src/zascarr/config.py:100-103` → `fandom_dc_enabled=False`, `fandom_dc_rate_limit=1.5`,
  `fandom_marvel_enabled=False`, `fandom_marvel_rate_limit=1.5`.
* Ajustes los muestra y persiste: `src/zascarr/web/ajustes.py:128-129` (contexto), `:277-278`
  (`Form(default=False)`), `:288-289` (`RuntimeSettingsService.save`), y
  `src/zascarr/services/runtime_settings.py:46` (`OVERRIDABLE_FIELDS["fuentes"]`). Plantilla:
  `web/templates/ajustes.html:41-47` (dos checkboxes en «Fuentes de datos», sin `checked` por defecto).
* Enricher: solo instancia clientes Fandom si el toggle está activo
  (`services/enricher.py:268-278`); con la fuente apagada no hay tráfico (`FandomClient` lanza
  `FuenteApagada` antes de enviar, probado en `tests/test_fandom.py::test_fuente_apagada_no_envia`).
* Comprobación en vivo con `TestClient` (sin BD, `FakeSession`; `Origin: http://localhost`):
  `Settings(_env_file=None)` → `False/False`; `GET /ui/ajustes` → ambos `<input …>` **sin `checked`**;
  `POST /ui/ajustes/guardar/fuentes` con los dos a `true` → **200**, `fila.values` con
  `fandom_dc_enabled=True`, `fandom_marvel_enabled=True`, `fuentes_heredadas=False`, y los `Settings`
  vivos actualizados (`RuntimeSettingsService.save` → `apply_overrides`).
* **Carencia de prueba dedicada:** `tests/test_fuentes_apagadas_por_defecto.py:11` (`CAMPOS`) sigue
  sin incluir `fandom_*`; AC-10 de la spec pedía ampliarlo. El comportamiento está verificado a mano
  (arriba) y el default es correcto, pero no queda pinneado por regresión. Ver §3-O3.

### (b) Snapshot de cortesía incluye `fandom_dc`/`fandom_marvel` (test y endpoint) — **PASA**

* `src/zascarr/utils/cortesia.py:109-110` (nombres), `:117-118`
  (`FUENTES_DECLARADAS = (… "fandom_dc", "fandom_marvel", …)`), `:240-244` (política 1,5 s/2 intentos),
  `:259-264` (origen lógico `fandom` para portadas).
* Tests: `tests/test_cortesia.py::TestSnapshot::test_forma_y_datos_sin_secretos` (lista exacta de 10
  fuentes) y `tests/test_cortesia.py::TestSnapshot::test_el_estado_esta_acotado` (10);
  `tests/test_web_estado_cortesia.py::TestEndpoint::test_devuelve_el_snapshot_con_no_store_y_sin_hosts_fuera_de_la_allowlist`
  (conjunto de 10 fuentes). Los tres pasan en las dos pasadas.
* Comprobación directa del endpoint: `GET /api/estado/cortesia` → **200**, `cache-control: no-store`,
  `fuentes = [comicvine, anilist, tebeosfera, gcd, metron, open_library, fandom_dc, fandom_marvel, foro, portada]`;
  el JSON no contiene URLs. El snapshot lista las fuentes declaradas **siempre**, estén apagadas o no:
  que aparezcan no contradice ADR 0013 (no se sondean si están apagadas).

### (c) Migración 0034: cadena y downgrade coherentes — **PASA** (sin Postgres)

`alembic/versions/20261113_0034_fandom_slugs.py`:

* `revision = "0034"`, `down_revision = "0033"` (líneas 18-19). Docstring correcto («Revision ID:
  0034 / Revises: 0033»).
* `upgrade()`: para `("series", "issues")` añade `fandom_dc_slug` y `fandom_marvel_slug` `String(255)`
  y crea `uq_<tabla>_fandom_dc_slug` / `uq_<tabla>_fandom_marvel_slug` (2 columnas × 2 tablas).
* `downgrade()`: recorre `("issues", "series")`, **borra primero las 4 constraints** y después las 4
  columnas; revierte exactamente lo que añade `upgrade()`.
* Cadena comprobada con `alembic.script.ScriptDirectory` (sin BD): `heads=['0034']`, `bases=['0001']`,
  **34 revisiones**, cadena `0001…0034` completa y única, `0034.down_revision == '0033'`.
* ORM alineado: `Series.fandom_dc_slug/fandom_marvel_slug` e `Issue.fandom_dc_slug/fandom_marvel_slug`
  son `VARCHAR(255)`, `unique=True`, `nullable=True` (comprobado sobre `__table__.columns`); coincide
  con la migración.
* **Límite esperado:** no se ha ejecutado `upgrade`/`downgrade` contra Postgres real (sin
  `TEST_DATABASE_URL`) y no hay prueba `_pg` nueva para 0034 (AC-01). Ver §3-O3.

### (d) `tests/test_fandom.py` cubre los casos pedidos, incluido Batman #404 (1986-10-21) — **PASA**

24 pruebas, todas verdes aisladas y dentro de la suite (1,96 s):

| Criterio | Prueba(s) |
|---|---|
| `missingtitle` (HTTP 200) → `None` | `test_missingtitle_es_none` (l. 381-390) |
| `maxlag` → excepción transitoria + bloqueo de cortesía | `test_maxlag_lanza_y_bloquea_cortesia` (l. 393-405; comprueba `retry_after_s == 20`) |
| Fechas | `test_fechas` (l. 179-196); caso real Batman #404: `Day=21, Month=2, Year=1987, Pubmonth=10, Pubyear=1986` → `date(1986, 10, 21)` (l. 185-188) y de nuevo en `test_get_issue_dc` (l. 335-351, fixture con comentarios `<!-- GCD -->` reales) |
| Créditos por rol | `test_creditos_por_rol` (l. 199-206); también `test_get_issue_dc` (`writer=Frank Miller`) y `test_get_issue_marvel` (`penciler=Jack Kirby`) |
| Arcos y orden de lectura | `test_arcos_en_orden_de_lectura` (l. 215-217: deduplica el 405 repetido y respeta el orden), `test_get_arc` (l. 370-378), `test_get_volume_dc` (`story_arcs`) |
| Sin red real | todo con `httpx.MockTransport`; fixtures de wikitext reales (comentario de cabecera, l. 1-8) |

Extras del mismo fichero que refuerzan los criterios: `test_gate_de_portadas_del_cdn_comun_de_fandom`,
`test_atribucion_fandom_enlaza_articulo_y_licencia`, `test_fuente_apagada_no_envia`,
`test_cadena_de_fuentes_american_con_fandom` (cadena `comic_vine → fandom_dc → fandom_marvel`).

### (e) `LEGAL.md` con fila CC-BY-SA y atribución visible en la ficha — **PASA** (con observación)

* `src/zascarr/LEGAL.md:107`: fila «**DC Database y Marvel Database (Fandom)**» → texto CC-BY-SA 3.0,
  portadas *fair use* no cubiertas, solo API oficial `/api.php`, apagadas por defecto, 1,5 s por wiki;
  exige «Atribución visible en la UI: enlace al artículo original **y** a la licencia CC-BY-SA 3.0»,
  sin hotlinking ni redistribución.
* Atribución en la ficha de serie: `web/series.py:1453-1483` (`WIKIS_DE_FANDOM`,
  `URL_DE_LA_LICENCIA_CC_BY_SA`, `atribucion_fandom()`), inyectada en el contexto en `web/series.py:541`
  y pintada en `web/templates/series_detail.html:49-58` dentro de `<details> «Fuentes y atribución»`:
  enlace al artículo (`https://<wiki>/wiki/<slug>`, espacios → `_`) y enlace a
  `https://creativecommons.org/licenses/by-sa/3.0/`; los dos enlaces llevan `rel="noopener noreferrer"`
  y la portada se declara explícitamente **no** CC-BY-SA. Sin `src` externo (sin hotlinking).
* `legal_version` se recalcula sola (es el hash del fichero, `services/legal.py:41-45`): actual
  `77e66dcf43b13b5a` ≠ `HEAD` `cad93d00f1436e60`; la fila nueva invalida las aceptaciones anteriores
  como exige CLAUDE.md §11. Verificado por hash directo.
* **Observación (§3-O2):** la atribución se ha añadido **solo a la ficha de serie**; la ficha de
  número (`web/templates/issue_detail.html`) y `/ui/arcos` (`web/templates/arco.html`) muestran datos
  de Fandom (sinopsis/origen «DC Database») sin enlaces a artículo ni licencia. La spec AC-03 `[B]` y
  AC-16 / D-6 pedían las tres superficies; task-4 (e) pedía «la ficha» y eso se cumple.

### (f) Gate de portadas: origen «fandom» activo si DC **o** Marvel encendida — **PASA**

* `utils/cortesia.py:143-145`: `("static.wikia.nocookie.net", "fandom")` en
  `HOST_DE_FUENTE_PARA_PORTADAS`; `:259-264`: `fuente_habilitada("fandom")` =
  `fandom_dc_enabled or fandom_marvel_enabled` (y `False` solo si **ambas** apagadas).
* `utils/cover.py:321-328`: antes de descargar, `fuente_de_host_portada(host)` y
  `fuente_habilitada(...)`; si está apagada → `cover.fuente_apagada`, `motivo_fallo="apagada"`,
  `return False` (no se cachea ni se sirve).
* `utils/url_portada.py:55`: el CDN `static.wikia.nocookie.net` está en `HOSTS_PERMITIDOS` (SSRF/H1).
* Prueba: `tests/test_fandom.py::test_gate_de_portadas_del_cdn_comun_de_fandom` (l. 287-295) cubre los
  cuatro casos (ambas off → cerrado; DC on → abierto; Marvel on → abierto; ambas off → cerrado). Verde.

---

## 3. Observaciones y riesgos (ninguno bloquea los criterios de task-4)

**O1 — Fecha: se guarda fecha de venta y la etiqueta sigue diciendo «Fecha de portada».** La spec
decidió en D-5 «fecha de **portada** (mes/año; día 1)… la venta no se guarda en esta entrega»
(`docs/design/especificacion-SCR2-fandom-fuentes.md:358`), pero el código implementa fecha de **venta**
(`services/fandom.py:310-322`, `Pubmonth`/`Pubyear` + `Day`) y el test fija 1986-10-21 — que es lo que
task-4 (d) pide. AC-04 admite la venta «con una decisión explícita del PO (D-5)», y esa decisión no
está registrada en ningún documento. Además la etiqueta visible sigue siendo «Fecha de portada»
(`services/ficha_numero.py:35`). Acción: que el Lead/PO ratifique la semántica por escrito y decida
la etiqueta (o se revierta a portada) antes del cierre de la spec. No rompe tests.

**O2 — Atribución CC-BY-SA ausente en ficha de número y en `/ui/arcos`.** La spec AC-03 `[B]`,
AC-16 y D-6 (`…:187-205, :263-268, :359`) piden enlace al artículo + licencia en las tres superficies;
hoy solo está en `series_detail.html`. La ficha de número muestra sinopsis con `procedencia` «DC
Database» y el arco muestra su nombre y orden de lectura, sin esos dos enlaces. Si AC-03 se mantiene
como bloqueante legal, es un pendiente antes de fusionar; task-4 no lo exigía (pedía la ficha de serie).

**O3 — Cobertura de integración no añadida.** Solo hay pruebas del cliente Fandom. No hay pruebas
nuevas de: enricher (`AC-02/07/11/12/14/15`: idempotencia de series/números/arcos, fuente apagada sin
tráfico en el ciclo, arcos con Postgres), migración 0034 con `tests._pg.bd_efimera()` (AC-01), ni
extensión de `CAMPOS` en `test_fuentes_apagadas_por_defecto.py` para AC-10. No impide aceptar el
código (suite verde y comportamiento del cliente probado), pero son las verificaciones que la propia
spec marca `[B]` y quedan sin evidencia ejecutable. El siguiente rol (SecOps) y el Lead deberían
saberlo antes de dar SCR2 por cerrado.

**O4 — El árbol no está en la rama que dice el encargo.** El encargo habla de la rama
`feat/fandom-fuentes`; el workspace está en `main` (HEAD `17a5995e`) con los cambios **sin commitear**.
`feat/fandom-fuentes` existe en local, pero apunta a `8f90aa4b` y **no contiene** estos cambios. Es un
riesgo de entrega (un commit accidental iría a `main`), no del código revisado: confirmar la rama y
los ficheros antes de commitear/pushear.

**O5 — *Flakes* ajenos a SCR2.** Ver §1.2; conviene no confundirlos con regresiones al interpretar la
primera pasada.

---

## 4. Veredicto

**APTO** para los criterios de aceptación de task-4 (a-f) y para la regresión: la suite queda verde
(segunda pasada: 6567 passed / 2256 skipped) y `tests/test_fandom.py` pasa aislado (24/24). **No hay
bloqueantes** imputables a la integración Fandom.

Pendientes que el Lead debe resolver **antes de fusionar/cerrar** (no bloquean mi aceptación, pero
afectan a la spec y a la entrega):

1. **O1**: ratificar por escrito la semántica de `release_date` (venta vs portada) y alinear la
   etiqueta «Fecha de portada»; AC-04/D-5 exige decisión explícita del PO.
2. **O2**: si AC-03 `[B]`/AC-16 se mantienen, añadir la atribución CC-BY-SA a ficha de número y
   `/ui/arcos`.
3. **O4**: confirmar rama antes de commitear (hoy: cambios sin commitear sobre `main`).
4. **O3**: decidir si se aceptan como deuda las pruebas de integración/migración `[B]` que no se
   añadieron (o abrir tarea para ellas).

---

## 5. Inventario del cambio revisado (`git status`, sin commitear)

Modificados: `src/zascarr/LEGAL.md`, `config.py`, `models/__init__.py`, `services/enricher.py`,
`services/procedencia.py`, `services/runtime_settings.py`, `utils/cortesia.py`, `utils/url_portada.py`,
`web/ajustes.py`, `web/series.py`, `web/templates/ajustes.html`, `web/templates/series_detail.html`,
`tests/test_cortesia.py`, `tests/test_enums_bd_strenum.py`, `tests/test_web_estado_cortesia.py`.
Nuevos: `src/zascarr/services/fandom.py`, `tests/test_fandom.py`,
`alembic/versions/20261113_0034_fandom_slugs.py` (y los documentos de benchmark/spec de los otros roles).
Lint: `ruff check` sobre los 14 ficheros del cambio → **All checks passed!** (ruff 0.17.5).


---

## Nota de cierre post-fusión (2026-11-13, tras desplegar)

Al fusionar todo en `main`, la migración **0034 quedó duplicada** (otra historia —BL-D3,
`upgrade_proposals`— usó el mismo número en paralelo), lo que rompía `alembic upgrade head`
con «Multiple head revisions». La resolución de `main` la renumeró a **0036** (`0034 mejoras`
→ `0035 portada` → `0036 fandom`), sin cambiar el SQL.

Verificación de esta sesión, con Postgres real y la app arrancada:
- `alembic upgrade head` desde 0033 aplica 0034→0035→0036; `alembic current` = 0036.
- `\d series` / `\d issues`: `fandom_dc_slug`/`fandom_marvel_slug` con `UNIQUE`;
  `alembic downgrade 0035` las retira y `upgrade head` las repone.
- `/api/health` servido por la app real: añade `fandom_dc`/`fandom_marvel` como «disabled»
  (AC-17, corregido en PR posterior) y `db: ok`.
- Añadida regresión `tests/test_migracion_fandom_pg.py` (upgrade desde 0035, columnas, UNIQUE
  y downgrade) para cerrar AC-01/AC-06 «sin Postgres real».
