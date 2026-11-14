# SPEC: tope de `Crawl-delay` y olvido de robots por fuente (M-4, #813) — v0.1

> **Estado:** spec implementable (P2, S), sin código ni commits. **Base:** `origin/main` `6b8f53fe` (RES-3 ya fusionada; el `main` local
> está 154 commits por detrás): el código se leyó con `git show origin/main:…` y manda ese código. **Sin migraciones ni cambios en `models`.**
> **Origen:** M-4 en `docs/design/secops-SCR1-2026-11-13.md` y diferida con motivo en `docs/design/deudas-menores-2026-11-14.md`; issue **#813**.
> **§5.8:** esta PR toca `web/ajustes.py` ⇒ **SecOps debe dictaminar el SHA final** antes de fusionar (CLAUDE.md §5.8), aunque no cambie
> contraseña, sesión ni la whitelist.

## 0. Estado real (qué hay y qué falta)

| Pieza | Estado hoy (fichero:línea) | Falta |
|---|---|---|
| Tope de `Crawl-delay` | `aplicar_crawl_delay` solo **sube** el intervalo; un `Crawl-delay: 86400` deja la fuente inutilizable (`utils/robots.py:93-106`) | Recorte a un máximo configurable |
| Dónde se aplica | `cache_http._politica_con_robots` aplica el retraso a la política (`:503-510`); `EntradaRobots` guarda el parser crudo | Recortar en `evaluar` (parser crudo) y que la política reciba el valor ya recortado |
| Olvido de estado | `reiniciar()` existe y su docstring dice «apagado/encendido de fuentes», pero **solo lo usan las pruebas** (`robots.py:130-133`; `_reiniciar_gestor_compartido` `:200-204`) | `olvidar(origen)` + llamada desde Ajustes |
| Singleflight | `_candados` por origen, atados al bucle (`:118-127`); `evaluar` cachea en `:135-156` | Semántica con evaluación en vuelo |
| Mapa fuente→origen | No existe. Orígenes reales: Fandom (`services/fandom.py:65-68`), Reading Orders (`reading_orders/comicbookreadingorders.py:29`), Continuity Guide (`reading_orders/continuity_guide.py:27`), Herald (config `comic_book_herald_feed_url:128-129`, host `www.comicbookherald.com`). El foro **no** usa robots | Función única reutilizando config/adaptadores |
| Ajustes | `guardar_fuentes` guarda 11 flags (`web/ajustes.py:347-380`) y no toca robots; foro y seguridad son rutas aparte (`:484,553`) | Olvidar solo orígenes de fuentes que cambian |
| Caché persistente | `POLITICA_CACHE_ROBOTS` cachea el **cuerpo** de `robots.txt` 24 h / negativa 12 h; 429/5xx/red **no** se cachean (`cache_http.py` + `robots.py:158-186`) | Documentar el límite: `olvidar` limpia memoria, no el `http_cache` |

## 1. Tope de `Crawl-delay`

`config.py`: **`crawl_delay_max_s: int = Field(default=60, ge=5, le=300)`** (env; **no** se expone en Ajustes ni se cambia en caliente; requiere
reiniciar). `GestorRobots.evaluar` lee el tope y devuelve el `Crawl-delay` **ya recortado**: `None`, no numérico, `NaN` o `<= 0` ⇒ sin cambio;
`inf` o finito `> maximo_s` ⇒ `maximo_s`. El parser/`EntradaRobots` queda **crudo**, así que cambiar el setting no descarga nada: la siguiente
evaluación usa el valor nuevo. `aplicar_crawl_delay` no cambia: recibe el valor recortado y aplica `max(local, recortado)` (nunca por debajo del
mínimo local; sigue «solo sube»). Log `robots.crawl_delay_recortado` con `origen` (`scheme://host[:puerto]`, sin path ni query), `declarado_s`,
`recortado_s`, `maximo_s`, solo cuando `declarado > maximo_s` (el mínimo local lo aplica después `aplicar_crawl_delay`). **Deduplicado por origen
mientras la entrada de robots esté viva** (no una línea por petición); `olvidar`/expiración lo rearman.

## 2. Olvido de robots por origen

`GestorRobots.olvidar(origen: str) -> None`: normaliza con `_origen` (acepta URL u origen; sin origen válido ⇒ no-op, sin lanzar), **`_cache.pop`**, incrementa `_generacion[origen]`
y **no borra `_candados`** (el candado se conserva: borrarlo abriría una segunda descarga simultánea del mismo origen). `evaluar` captura la
generación antes de cargar y **solo escribe `_cache` si la generación no cambió**: una evaluación en vuelo sigue su curso y devuelve su
resultado a quien la pidió, pero no resucita la entrada; la siguiente llamada reutiliza el mismo candado y descarga de nuevo. `reiniciar()`
vacía caché, candados y generación (pruebas/apagado de la app). Memoria acotada: los candados no crecen con las fuentes, solo con los
orígenes ya vistos (`_candado` ya los reutiliza).

`origenes_de_fuente(fuente: str) -> tuple[str, ...]` en `robots.py`, con imports **lazy** (evita ciclos robots↔adaptadores): `fandom_dc`/
`fandom_marvel` desde `services.fandom.FUENTES`; `reading_orders`/`continuity_guide` desde el `ORIGEN` de su adaptador; `comic_book_herald`
desde `_origen(get_settings().comic_book_herald_feed_url o default)`; cualquier otra (foro, portada, fuentes de enriquecimiento) ⇒ `()`.
`olvidar_origenes_de_fuente(fuente) -> tuple[str, ...]` module-level: si `_GESTOR_DE_PROCESO` es `None` no instancia nada (no hay estado que
olvidar) y devuelve los orígenes mapeados; si existe, llama a `olvidar` en cada uno. `gestor_robots_de_proceso()` sigue exponiendo el gestor
único y su `olvidar`.

**Límite explícito:** `olvidar` limpia el estado **en memoria** (parser, TTL y bloqueo por 429/5xx/red/parse). **No** invalida la fila de
`http_cache` del cuerpo de `robots.txt` (24 h un 2xx, 12 h un 4xx≠429). Los estados que el toggle desbloquea (429/5xx/red, no cacheados) se
reintentan de verdad; un `robots.txt` 200/404 ya cacheado se re-parsea con el mismo cuerpo hasta que expire. Forzar red (`bypass_cache`) en el
primer GET tras `olvidar` es una mejora posible (fuera de M-4; si el PO la quiere, historia aparte).

## 3. Ajustes: olvidar solo lo que cambia

En `guardar_fuentes` (`web/ajustes.py:347-380`), y solo ahí: antes de `RuntimeSettingsService.save`, capturar el estado previo de las cinco
fuentes con robots (`{f: bool(getattr(get_settings(), f"{f}_enabled", False))}` para `fandom_dc`, `fandom_marvel`, `reading_orders`,
`continuity_guide`, `comic_book_herald`); después del save correcto, para cada fuente cuyo booleano **cambia**, llamar a
`olvidar_origenes_de_fuente(f)` (helper puro `_fuentes_de_robots_cambiadas(previas, nuevas)` para las pruebas). Si no cambia nada, **no se
olvida**: un «prohibido» cacheado sobrevive. No se tocan `guardar_foro` ni `guardar_seguridad`, ni la whitelist `OVERRIDABLE_FIELDS`, ni el
flujo de contraseña/sesión; no hay campos `Form` nuevos. Si `save` falla, no se olvida (el estado en memoria sigue al de la configuración real).
Sin migraciones.

## 4. Criterios de aceptación medibles

| # | Criterio | Verificación |
|---|---|---|
| AC-01 | `Crawl-delay: 86400` + `crawl_delay_max_s=60` ⇒ intervalo 60 s y **un** log por origen/entrada `robots.crawl_delay_recortado` (`declarado_s=86400`, `recortado_s=60`) | unitario con log capturado; dos peticiones seguidas ⇒ un solo aviso |
| AC-02 | `Crawl-delay: 30` (< cap) no se recorta (30 s) y **no** hay log | unitario |
| AC-03 | `Crawl-delay: 1` con mínimo local 2,5 s ⇒ 2,5 s (nunca reduce); tope 5 con mínimo local 90 s ⇒ 90 s (el cap no baja del mínimo) | unitario |
| AC-04 | Ausente/`None`/`0`/negativo/`NaN`/`"abc"` ⇒ sin cambios ni excepción; `inf` ⇒ cap | unitario parametrizado |
| AC-05 | `EntradaRobots` no cambia de forma; cambiar `crawl_delay_max_s` surte efecto en la siguiente evaluación/política, sin red y sin recargar robots | unitario con reloj/caché falsos |
| AC-06 | Dos orígenes cacheados; `olvidar` uno ⇒ el otro intacto; el olvidado vuelve a descargar (contador +1) | `descargar_robots_fn` falso contador |
| AC-07 | Estado `unreachable_disallow` sobrevive si se guarda la misma fuente; si se apaga/enciende, solo ese origen se olvida y la siguiente evaluación descarga y puede permitir | Ajustes `TestClient` + gestor con contador |
| AC-08 | Evaluación en vuelo + `olvidar` ⇒ no escribe caché (no resucita); siguiente llamada descarga de nuevo y el candado no se duplica | `asyncio.Event` en `descargar_robots_fn` |
| AC-09 | `origenes_de_fuente`: 5 fuentes correctas (Fandom DC/Marvel, RO, CG, Herald con URL de config); foro/desconocida ⇒ `()`; sin instanciar el gestor | unitario + monkeypatch de settings |
| AC-10 | Ajustes: cambiar `fandom_dc` olvida solo `https://dc.fandom.com`; no toca Marvel/RO/CG/Herald; la respuesta 200 no expone secretos; foro y seguridad verdes | `tests/test_web_ajustes*.py` y pruebas de contraseña/sesión |
| AC-11 | Sin red ni Postgres en las pruebas nuevas; `test_robots.py` (197 líneas) y `test_web_ajustes*` siguen verdes | ejecución completa por QA |

## 5. Plan de pruebas sin red

`tests/test_robots.py`: clase `TestTopeCrawlDelay` (AC-01…05; log con structlog capturado o `caplog`; `origen` sin `/` ni `?`) y
`TestOlvidar` (AC-06, AC-08; `descargar_robots_fn` con contador y `asyncio.Event`; `_reiniciar_gestor_compartido()` entre pruebas).
`tests/test_robots_fuentes.py`: AC-09 (mapeo y singleton no instanciado). `tests/test_web_ajustes_fuentes_robots.py`: `TestClient` + patrón
`FakeSession`/override de `get_db` y restauración de settings como `test_fuentes_apagadas_por_defecto.py`; se monkeypatchea el gestor para
contar olvidos. Nada de red, ni `TEST_DATABASE_URL`, ni `skip`.

## 6. Riesgos y límites

- **Recortar `Crawl-delay` incumple lo que pide un sitio** que declare más de 60 s: es una decisión de disponibilidad adoptada por el PO
  (máx. 1 req/min por defecto, techo 300 s). Queda registrada con log; si un sitio legítimo pide más, se sube el setting en `.env` y se reinicia.
- **Límite del olvido:** no invalida `http_cache` (§2); el caso que motiva el toggle (429/5xx/red, no cacheados) sí se reintenta; un cuerpo
  cacheado se re-parsea igual. Documentado, no se finge cubierto.
- **Carrera toggle/evaluación:** la generación evita resucitar la entrada; la evaluación en vuelo devuelve su resultado ya calculado (no se cancela).
  No hay coordinación entre procesos: el proyecto corre con `--workers 1` (ADR-0011); un reinicio limpia todo.
- **Fuente sin robots** (foro, fuentes de enriquecimiento): mapping `()` y `olvidar_origenes_de_fuente` no-op; no rompe ni crea estado.
- **Herald con URL de feed cambiada por `.env`:** el mapeo usa el valor vigente; el cambio de `.env` exige reiniciar (no hay toggle en Ajustes).
- **§5.8:** el PR toca `web/ajustes.py`; sin dictamen de SecOps sobre el SHA final no se fusiona, aunque las pruebas de contraseña/sesión estén verdes.

## 7. Cortes para el builder

| Corte | Contenido | §5.8 | Est. |
|---|---|---|---|
| 1 | `crawl_delay_max_s` + recorte/log en `GestorRobots.evaluar` (`aplicar_crawl_delay` sin cambios) + pruebas `test_robots.py` | No | 0,25–0,5 d |
| 2 | `olvidar`/generación/mapeo + wiring en `guardar_fuentes` + pruebas de Ajustes | **Sí** (SecOps del SHA final) | 0,5–1 d |

El Corte 1 es independiente y ya evita la fuente inutilizable; el Corte 2 cierra el toggle. Una historia = una PR, un commit por corte.

## 8. Trazabilidad

M-4 (`secops-SCR1-2026-11-13.md`; `deudas-menores-2026-11-14.md:40`) → §1 (tope), §2 (olvido), §3 (Ajustes). Issue #813 (P2/S). Sin
migraciones, sin `models`, sin tocar contraseña/sesión/whitelist; §5.8 obliga a la pasada final de seguridad.
