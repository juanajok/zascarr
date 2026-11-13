# SPEC: SCR1 — `robots.txt` (RFC 9309) y caché HTTP condicional en PostgreSQL — v0.1

> **Estado:** spec para el builder (2026-11-13); no autoriza fusionar ni se ha tocado código, migraciones, `pyproject.toml` ni commit. **Base:** `main` en
> `c1e3dea9` (SCR2 fusionada y verificada); leídos y citados por línea `peticiones.py`, `cortesia.py`, `fandom.py`, `enricher.py`, `main.py`, `database.py`,
> `tests/_pg.py`, `test_migracion_fandom_pg.py`, `test_fandom.py` y `pyproject.toml`. **Fuentes:** anexo C de `ANEXOS-IMPLEMENTACION-ZASCARR-V2.md`,
> §5.2–5.3 del `estudio-scraping-fuentes-v2.md`, informes `fase0` y `secops-SCR2`; ADR 0018 sigue **Propuesto** (esta spec lo implementa, no lo aprueba) y
> manda el código real cuando el anexo discrepe. **Fuera de alcance:** guías (SCR3), foro/Tebeosfera (no se migran), UI de reintentar, `LEGAL.md`, tocar `peticiones.py`.

## 1. Resumen

(a) `utils/robots.py`: evaluador RFC 9309 con `protego` (estado por origen en memoria + cuerpo 200 en `http_cache`). (b) `utils/cache_http.py` + tabla
`http_cache` (migración **0037**): caché condicional `zlib`, dos horizontes (`fresh_until`/`retain_until`), negativa corta y *singleflight*. (c)
`services/fandom.py` usa `pedir_con_cache` en su único punto de red, `_api()` (725); sin `cache` inyectada se comporta como hoy. En vivo, `robots.txt` de
Fandom responde **403** ⇒ «sin restricciones» (RFC 9309 §2.3.1.3): SCR1 **no cambia el tráfico de Fandom** (robots rinde en SCR3).

## 2. Anexo → código real (obligatorio para el builder)

| Anexo/estudio dice | En este repo |
|---|---|
| `politica.min_intervalo_s` | `PoliticaFuente.intervalo_min_s` (`cortesia.py:188`) |
| «devuelve 304/404» | `pedir_con_cortesia` los **levanta** como `RespuestaNoTransitoria(código)` (`peticiones.py:331-337`); la caché los interpreta y `peticiones.py` no se toca |
| `pedir_con_cache(..., sesion)` / `weakref` | `CacheHttp(sesion_factory)`: **sesión corta propia** por operación (nunca la del ciclo del enricher) y candados **de módulo** por `url_hash` (patrón `_Candados`, `cortesia.py:289`) |

## 3. Dependencia

`pyproject.toml` → `dependencies`: `"protego>=0.7,<1"`. Verificado en PyPI (2026-11-13): 0.7.0, BSD-3-Clause, wheel `py3-none-any`,
`requires-python >=3.10` y **sin dependencias** ⇒ aarch64 sin compilar. SCR1 no toca `config.py` ni `.env`.

## 4. Tabla `http_cache` + migración 0037

`alembic/versions/20261113_0037_http_cache.py` (`revision="0037"`, `down_revision="0036"`), aditiva y reversible como `0036`; modelo `HttpCache(Base)` en
`models/__init__.py` (junto a `ImportRun`) que mapee **exactamente** la migración.

```
id BigInteger PK · url_hash String(64) NOT NULL UNIQUE (uq_http_cache_url_hash) · url_canonical Text NOT NULL
domain String(255) NOT NULL · status_code SmallInteger NOT NULL · content_type String(255) · is_negative Boolean default false
etag Text · last_modified Text · body_zlib LargeBinary · fetched_at, fresh_until, retain_until DateTime(timezone=True) NOT NULL
Índices: ix_http_cache_domain (domain), ix_http_cache_retain_until (retain_until)
```

`url_hash` = sha256 hex de `MÉTODO + " " + url_canónica`. **Topes:** `MAX_CUERPO_CACHE = 2 * 1024 * 1024` bytes descomprimidos; por encima no se persiste (log
`cache_http.cuerpo_demasiado_grande`). `ZLIB_LEVEL = 6`; comprimir y descomprimir en `asyncio.to_thread` (CLAUDE.md §4) con `decompressobj().decompress(datos,
MAX_CUERPO_CACHE)`; cola no consumida ⇒ fila descartada. **Purga:** `DELETE WHERE retain_until < now()` (nunca por `fresh_until`: destruiría ETag/cuerpo y el 304),
una vez por ciclo de `_enrichment_loop` (`main.py:163-180`) tras el commit, con `try/except`; `ON CONFLICT (url_hash) DO UPDATE` para no duplicar.

## 5. TTL por dominio (`PoliticaCacheDominio`)

| Recurso | `ttl_positivo` | `margen_retencion_304` | `ttl_negativo` | `codigos_negativos` |
|---|---|---|---|---|
| `fandom_dc`/`fandom_marvel` (`api.php`) | 24 h | +14 d | 12 h | `{404, 410}` |
| `robots.txt` de cualquier origen | 24 h | +14 d | 12 h | 4xx≠429 (`{400..499} - {429}`) |
| Guías SCR3 (referencia, no se implementa) | 14 d | +60 d | 24 h | `{404, 410}` |

`PoliticaCacheDominio` (`frozen`, `slots`) con `calcular_ventanas(ahora, *, es_negativo)`; negativa ⇒ `fresh_until = retain_until = ahora + ttl_negativo`. Políticas en su módulo:
`_POLITICA_CACHE` (`fandom.py`) y `POLITICA_CACHE_ROBOTS` (`robots.py`).

## 6. Semántica de `pedir_con_cache`

`pedir_con_cache(cliente, "GET", url, *, politica, politica_cache, cache, robots=None, espera_max_s, clasificar=None, bypass_cache=False,
datos=None, cabeceras=None, hosts_redireccion=None, permitir_apagada=False, cortesia=None, reloj=time.monotonic, dormir=asyncio.sleep,
ahora=lambda: datetime.now(UTC)) -> httpx.Response`; solo `GET` (otro método ⇒ `ValueError`).

1. **Fuente apagada primero:** `fuente_habilitada(politica.fuente)` ⇒ `FuenteApagada` **antes** de la caché y de robots; `FuenteApagada` y `CortesiaEnEspera` **nunca** se re-envuelven.
2. **Hit** (`ahora < fresh_until`, sin `bypass`): `httpx.Response(status_code, content=descomprimido, headers=content-type + "x-zascarr-cache: hit")`, sin llamar a `pedir_con_cortesia`: **ni turno ni socket**.
3. ***Singleflight*:** candado de módulo por `url_hash` con doble comprobación; si no se consigue en `espera_max_s` ⇒ `CortesiaEnEspera(..., "candado")` (visible, sin URL); `bypass_cache=True` salta lectura y candado.
4. **Robots:** `evaluar(url, descargar_robots_fn=<closure>)`; prohibido ⇒ `AccesoProhibidoPorRobots(ErrorDePeticion)` (fuente/origen, sin URL); `crawl_delay`
   ⇒ `aplicar_crawl_delay`. El closure descarga `robots_url` con **el mismo** `pedir_con_cache` (`robots=None`, `POLITICA_CACHE_ROBOTS`,
   `espera_max_s=min(espera_max_s, 10.0)`), convierte `RespuestaNoTransitoria(código)` en `httpx.Response(código)` para clasificar 403/404 y deja propagar
   `FuenteApagada`/`CortesiaEnEspera`. Nunca con un hit ni para `url.path == "/robots.txt"`.
5. **Stale** (`fresh_until <= ahora < retain_until`) con `etag`/`last_modified`: añade `If-None-Match`/`If-Modified-Since` y llama a `pedir_con_cortesia`; si levanta
   `RespuestaNoTransitoria(304)` renueva `fetched_at`/`fresh_until`/`retain_until` (mismos validadores: el 304 no expone cabeceras) y devuelve el **cuerpo guardado**
   (`x-zascarr-cache: revalidada`).
6. **Negativa** (`código in politica_cache.codigos_negativos`): fila `is_negative=true`, `body_zlib=NULL`, `fresh_until=retain_until=ahora+ttl_negativo`
   y **se relanza** `RespuestaNoTransitoria(código)`; un hit negativo con `status_code >= 400` la relanza y con 200 devuelve el cuerpo. **Éxito 2xx:**
   `clasificar(respuesta)` ⇒ `"ok"` · `"negativo"` (negativa **conservando el cuerpo**: `_api` necesita el JSON de `missingtitle`) · `"no_cachear"`
   (un fallo del clasificador nunca tumba la petición); sesión corta y `commit` inmediato. **429/5xx/red o redirección no permitida:** se propagan
   (`ReintentosAgotados`, `RedireccionNoPermitida`, `DemasiadasRedirecciones`) y **no se escribe fila**.
7. **Canónica:** `normalizar_y_hashear_url(metodo, url, params)` quita userinfo, ordena query (`parse_qsl`+`urlencode`), minúsculas en esquema/host y fuera puertos
   por defecto. `url_canonical` redacta como `REDACTADO` los `PARAMETROS_SENSIBLES = {"api_key","apikey","key","token","access_token","refresh_token",
   "password","sig","signature"}`; el **hash** va sobre la URL completa (dos claves no colapsan y el secreto no llega a la BD).

## 7. Contrato de `utils/robots.py`

`EstadoRobots = Literal["parsed","unavailable_allow","unreachable_disallow"]`; `EntradaRobots(estado, parser: Protego|None, expira_monotonic: float)` (`frozen`, `slots`);
`GestorRobots(user_agent=USER_AGENT, reloj=monotonic)` con `TTL_OK_S=86_400`, `TTL_UNAVAILABLE_S=43_200`, `TTL_UNREACHABLE_S=900`; `async evaluar(url, *, descargar_robots_fn)` con
candado por origen y doble comprobación; `reiniciar()`; `gestor_robots_de_proceso()` singleton perezoso (patrón `cortesia_de_proceso()`, `cortesia.py:634`).

| Respuesta de `/robots.txt` | Estado | Permiso | Caducidad |
|---|---|---|---|
| 2xx | `parsed` (`Protego.parse(content[:512*1024]`, decode utf-8 replace) | `can_fetch(url, UA)` | 24 h |
| 4xx ≠ 429 (403 de Fandom, 404) | `unavailable_allow` | permitido, con `PoliticaFuente` | 12 h |
| 429, 5xx, `ReintentosAgotados`, `httpx.TransportError`, parse que lanza | `unreachable_disallow` | **prohibido** | 15 min |

`FuenteApagada`, `CortesiaEnEspera`, `RedireccionNoPermitida` y `DemasiadasRedirecciones` se propagan (política o presupuesto, no indisponibilidad); no hay `except Exception`.
Persistencia: tabla guarda el **cuerpo 200** (24 h) y el estado vive en memoria. `aplicar_crawl_delay(politica, crawl_delay) = replace(politica,
intervalo_min_s=max(...))` (solo sube). `USER_AGENT = f"ZascArr/{version('zascarr')}"` con `importlib.metadata` y respaldo `"ZascArr"`; `FandomClient._cliente()` (708)
añade `headers={"User-Agent": USER_AGENT}`.

## 8. Integración exacta

`services/fandom.py`: `FandomClient.__init__` (676) gana `cache: CacheHttp | None = None` y `robots: GestorRobots | None = None` al final (compatibles). En `_api()`
(725), compuesta `url`: **sin caché** ⇒ la llamada actual a `pedir_con_cortesia` (735-741) **sin cambios**; **con caché** ⇒ `pedir_con_cache` con
`politica_cache=_POLITICA_CACHE`, `clasificar=clasificar_respuesta_mediawiki`, `robots=self._robots_actual()` (singleton si no se inyectó), `cortesia`, `reloj`,
`dormir` y el `espera_max_s` de hoy. El resto de `_api` (tope `MAX_CUERPO_API`, JSON, `missingtitle` → `None`, `maxlag` → `FandomMaxLagError` + bloqueo) **no se
toca**. `clasificar_respuesta_mediawiki(respuesta)`: `len(content) > MAX_CUERPO_API` ⇒ `"no_cachear"`; `error.code` en `_CODIGOS_INEXISTENTE` ⇒ `"negativo"`; otro
`error` (`maxlag`, `internal_api_error`) o JSON ilegible ⇒ `"no_cachear"`; sin `error` ⇒ `"ok"`. `_wikitext` (768), `_displaytitle` (792) y `_url_de_imagen` (799)
heredan la caché por pasar por `_api`; las portadas **no** pasan por robots ni por esta caché (siguen gobernadas por `utils/url_portada.py` y `covers/externa/`).

`services/enricher.py`: en `enrich_pending` (282), al construir un `FandomClient` real (297-307) se le pasa `cache_http = CacheHttp(async_session_factory)`, con ambos imports
**locales dentro del método**, solo si `dc_activa or marvel_activa` y el cliente no se inyectó (los dobles `SimpleNamespace` no declaran `fandom_*_enabled` ⇒ `False`, así que ningún
test existente llega ahí). `main.py`: `_enrichment_loop` purga una vez por ciclo (§4).

## 9. Criterios de aceptación (medibles; prueba entre paréntesis)

| ID | Criterio |
|---|---|
| AC-01 | 5 corrutinas sobre la misma URL fría ejecutan **1** petición; sobre 5 URLs del mismo origen, **1** `/robots.txt` (`test_cache_http::test_singleflight`) |
| AC-02 | Hit vigente: 0 peticiones y **0** llamadas a cortesía (`CortesiaEspia.esperar` no se invoca) (`test_hit_sin_turno`) |
| AC-03 | Stale con ETag envía `If-None-Match`; 304 renueva `fresh_until`, conserva `body_zlib` y devuelve el mismo cuerpo (`test_304`) |
| AC-04 | 404 ⇒ negativa: 2.ª llamada con 0 peticiones relanza `RespuestaNoTransitoria(404)`; pasada la TTL vuelve a la red (`test_negativa`) |
| AC-05 | 429/5xx/red **no** crean fila y una 2.ª llamada vuelve a la red (`test_transitorios`) |
| AC-06 | `missingtitle` (HTTP 200) se cachea negativo; `maxlag` no (2.ª llamada a red y `FandomMaxLagError`) (`test_fandom_cache.py`) |
| AC-07 | Robots: 200 aplica `Disallow` y `Crawl-delay` eleva `intervalo_min_s`; 403/404 permite y cachea 12 h; 429/5xx/red prohíbe 15 min sin repedir (`test_robots.py`) |
| AC-08 | Migración 0037: de `0036` a head aparecen tabla, UNIQUE e índices; `downgrade 0036` los quita; el ORM inserta/lee (`test_migracion_http_cache_pg.py`) |
| AC-09 | Cuerpo > 2 MiB no se persiste y `_api` sigue devolviendo `None`; `purgar()` borra solo `retain_until < now` (`test_cuerpo_grande`, `test_cache_http_pg::test_purga`) |
| AC-10 | `?b=2&a=1` y `?a=1&b=2` dan el mismo `url_hash`; `api_key` sale `REDACTADO`; `bypass_cache` va a red y reescribe (`test_canonica`, `test_bypass`) |
| AC-11 | Fuente apagada ⇒ `FuenteApagada` sin leer caché, sin robots y sin petición; imports en cualquier orden sin ciclo (`test_cache_http`, `test_fandom_cache`) |
| AC-12 | La suite actual (los tests de `test_fandom.py` incluidos) pasa **sin edits** y `ruff` limpio (`pytest`, `ruff check`) |

## 10. Plan de pruebas

`tests/_cache_falsa.py`: `CacheHttpFalsa` (protocolo `leer`/`escribir`/`renovar`/`purgar`, dict en memoria, `ahora` fijo) para probar `pedir_con_cache` sin Postgres.
`tests/test_cache_http.py`: `httpx.MockTransport` que anota URL y cabeceras, `TransporteLento(httpx.AsyncBaseTransport)` para solapamiento real y `Reloj`/`CortesiaEspia`
(patrones de `tests/test_peticiones.py`); sin red ni BD. `tests/test_cache_http_pg.py` y `tests/test_migracion_http_cache_pg.py`: Postgres real con
`tests._pg.bd_efimera()` + `migrar_a_head()` (patrón `test_migracion_fandom_pg.py`), `skipif` sin `TEST_DATABASE_URL` y `async_sessionmaker(create_async_engine(
url_asyncpg(url), poolclass=NullPool), expire_on_commit=False)`. `tests/test_robots.py`: `GestorRobots` con `reloj` simulado y fixtures reales (Fandom 403 Cloudflare,
CRG con `Allow: /` y `Crawl-delay`, Continuity Guide), sin red. `tests/test_fandom_cache.py`: `FandomClient(cache=CacheHttpFalsa(), robots=GestorRobots())` +
`MockTransport` (`missingtitle`/`maxlag`/404/tope) y espía de `FandomClient` que comprueba que el enricher pasa `cache` (`FakeSession`, flags Fandom encendidos).

## 11. Plan por cortes (builder)

1. **Corte 0 — esquema:** `protego` en `pyproject.toml`; migración 0037; `HttpCache` en `models/__init__.py`; `test_migracion_http_cache_pg.py` (AC-08). *Puerta:* ida/vuelta en `_pg`, suite intacta.
2. **Corte 1 — primitivas:** `cache_http.py` (hash/canónica, compresión, `PoliticaCacheDominio`, `CacheHttp` con sesión corta, upsert y `purgar`) + tests unitarios y `test_cache_http_pg.py`.
3. **Corte 2 — `pedir_con_cache`:** hit, stale+304, negativa, singleflight, bypass, clasificador y `AccesoProhibidoPorRobots`; `_cache_falsa.py` y `test_cache_http.py` (AC-01 a AC-05, AC-09, AC-10).
4. **Corte 3 — robots:** `utils/robots.py` + `tests/test_robots.py` (AC-07) + promover `Candados` a público.
5. **Corte 4 — integración:** rama de `_api`, `clasificar_respuesta_mediawiki`, `_POLITICA_CACHE`, enricher y purga en `main.py`; `tests/test_fandom_cache.py` (AC-06, AC-11, AC-12). *Puerta:* `pytest`, `ruff check`, `test_fandom.py` intacto.
6. **Corte 5 — cierre:** nota de mecanismo en `docs/BACKLOG.md` (deuda «Fase 1 de SCR1»); ADR 0018 lo decide el PO.

Cada corte deja la suite verde y es un commit atómico; no mezclar el corte de esquema con lógica.

## 12. Riesgos y deudas declaradas

- **RES-3 sigue abierta:** `httpx` bufferiza el cuerpo entero antes de que la caché vea el tamaño; el tope de 2 MiB limita **lo persistido**, no la transferencia ni el pico de memoria (cerrarlo exige `cliente.stream(...)` en `peticiones.py`).
- **304 vía excepción:** se pierden cabeceras nuevas del 304 (ETag) y el snapshot de cortesía anota «4xx» (cosmético). Fandom no emite `ETag`/`Last-Modified` (informe Fase 0): el 304 no
  se ejerce en producción hasta SCR3, que sí los tiene.
- **robots es inocuo hoy para Fandom** (403 ⇒ permitir): no prometer reducción de tráfico por robots; la reduce la caché (24 h por URL) y evita repetir `missingtitle` (12 h).
- **Espera del candado:** quien espera no consume presupuesto de cortesía salvo el corte por `espera_max_s` (`motivo="candado"`); una URL muy pedida puede encolar. Sin tope duro de
  filas: `retain_until` de 14 d acota por nº de URLs de la biblioteca (deuda: `MAX_FILAS` si QA lo mide).
- **Sesión corta extra por operación:** +1 conexión del pool en el ciclo del enricher (7 por defecto con `db_pool_size + db_max_overflow`); en SCR1 solo la usa el enricher (un
  worker, secuencial). **`FandomClient` sin caché no aplica robots** (modo pruebas/cliente aislado): el enricher siempre inyecta caché.
