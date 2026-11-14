# SPEC: tope real de bytes con streaming en `peticiones.py` (RES-3, #812) — v0.1

> **Estado:** spec implementable (P1, M), sin código ni commits. **Base:** `origin/main` `2d7aeb92` (SCR1–SCR5 + deudas #805); el `main` local está
> 135 commits por detrás y no tiene `comicbook_herald.py`: el código se leyó con `git show origin/main:…` y manda ese código. **Spike local** (sin tocar
> el repo): `cliente.stream()` funciona con `httpx.MockTransport` y la `Response` reconstruida conserva `.content/.text/.json()/.headers/.status_code`.
> **Origen:** RES-3/M-3 (`secops-SCR1-2026-11-13.md:123-134`) y `deudas-menores-2026-11-14.md`; issue **#812** (P1, M). Se cierra con pruebas sin red.

## 0. Problema y estado real

`pedir_con_cortesia` hace la petición **bufferizada** y el tope se comprueba después, en cada consumidor. Una respuesta enorme
(hostil o rota) se descarga entera antes de que nadie la rechace: pico de RAM/transferencia sin cota en la Pi compartida (512 MB).

| Pieza | Estado hoy (fichero:línea) | Qué falta |
|---|---|---|
| Transporte | `_enviar` usa `cliente.get/post/request` buffered (`utils/peticiones.py:176-195`); cada salto de redirección repite el buffer (`:198-252`) | `cliente.stream()` + lectura por chunks con tope |
| Tope general | **No existe** en `peticiones.py` ni en `config.py`; el cuerpo llega entero a `return respuesta` (`:366`) | `MAX_CUERPO_TRANSFER` configurable |
| Caché | Tope de **persistencia** 2 MiB comprimido (`utils/cache_http.py:62,161-165`), comprobado tras el buffer; `pedir_con_cache` llama a `pedir_con_cortesia` (`:411`) y solo captura `RespuestaNoTransitoria` (`:418`) | Excepción nueva que **no** escriba caché ni negativa |
| Consumidores | Topes propios **después** de descargar: Fandom 2 MiB (`services/fandom.py:75,125,811-812`), Herald 1 MiB (`services/comicbook_herald.py:67,265-268`), guías SCR3 2 MiB (`services/reading_orders/comun.py:55`); foro y Ajustes, sin tope | Tope general como último recurso |
| Portadas | `utils/url_portada.py` **ya** hace streaming con tope propio de 8 MiB (`:59,205-235`) y timeout de 15 s | No tocar ni duplicar |
| Robots | `MAX_ROBOTS` 512 KiB en `utils/robots.py` (parseo, no transferencia) | El tope general lo cubre también |

## 1. Contrato y excepción

`pedir_con_cortesia(...) -> httpx.Response` sigue devolviendo la respuesta con `.content` **solo si** el cuerpo decodificado no supera
`limite`. Si lo supera: se corta la lectura, se cierra la respuesta y se lanza **`CuerpoDemasiadoGrande(ErrorDePeticion)`** con
`fuente: str`, `bytes_leidos: int`, `limite: int`, `motivo: str` (`"content_length"` o `"chunks"`). Mensaje corto, **sin URL, query ni cuerpo**.

**Herencia: `ErrorDePeticion`, NO `RespuestaNoTransitoria`.** `RespuestaNoTransitoria` significa «4xx no reintentable» y su `.codigo` se consulta
para negativas/304 en `cache_http.py:418-430`; un 2xx con cuerpo grande encajaría mal y podría crear una negativa falsa. Impacto:
- `cache_http`: propaga **antes** de `cache.escribir` ⇒ no cachea ni registra negativa; hit y 304 intactos.
- Capturan `ErrorDePeticion`: Herald (`comicbook_herald.py:256`) y guías (`reading_orders/comun.py:335`) → fuente caída/`[]`. Capturan
  `RespuestaNoTransitoria` (Comic Vine `:192,210`; GCD `:351`; Discovery `:232`): no la capturan y se propaga al `except Exception` del enricher
  (`enricher.py:523` y similares), que registra y sigue; **no se reintenta**. Portadas/`web/series.py` no pasan por aquí y no cambian.

## 2. Implementación (streaming conservando todo lo demás)

Sustituir el interior de `_enviar` por un lector `_leer_con_tope(...) -> httpx.Response`:
1. Construir la petición como hoy (GET con `params`/`datos`; POST JSON o formulario con `_cuerpo_de_formulario`/`form_charset`) y abrir
   `async with cliente.stream(metodo, url, **kwargs) as r:`. `follow_redirects=False` se mantiene.
2. 3xx: **no leer el cuerpo** (se descarta; los clientes no lo usan) y devolver una `httpx.Response` con estado, cabeceras y cuerpo vacío para que
   `_seguir_redirecciones` resuelva el salto como ahora (H5, 301/302/303→GET, 307/308 conservan método/cuerpo, `Location` antes de pedir).
3. Pre-check de `Content-Length` (entero válido y `> limite`): `CuerpoDemasiadoGrande(motivo="content_length")` sin leer chunks; es **solo una
   pista** (puede faltar, mentir o ser el tamaño comprimido).
4. Leer con `async for trozo in r.aiter_bytes(chunk_size=64*1024)`, acumular en `bytearray` y, tras cada trozo, si `len(acumulado) > limite`
   lanzar `CuerpoDemasiadoGrande(motivo="chunks")`. `aiter_bytes` descomprime ⇒ el tope cuenta bytes **decodificados** (cubre bombas gzip). Entre
   trozos, si `reloj() > deadline`, cerrar y lanzar `CortesiaEnEspera(fuente, host, 0, "cuerpo_lento")` (un goteo no retiene el worker).
5. Al terminar, devolver `httpx.Response(r.status_code, headers=r.headers, content=bytes(acumulado), request=r.request)`; el `async with` cierra
   siempre. La copia final duplica el pico (≈2×cap por respuesta en vuelo): aceptado y medido.
6. `form_charset`/`datos`/POST y redirecciones **no cambian**; `pedir_con_cortesia` no atrapa la excepción nueva (no entra en red/timeout/429/5xx),
   así que no se reintenta; el `except CortesiaEnEspera` existente la deja pasar.

## 3. Config y relación con los topes existentes

`config.py`, sección de red (junto a `comicvine_rate_limit`): **`max_cuerpo_transfer_bytes: int = Field(default=4_194_304, ge=1_048_576, le=16_777_216)`**
(4 MiB por defecto, 1–16 MiB; el `.env` puede sobrescribirlo). Se lee con `get_settings()` en el lector; **no** se expone en Ajustes ni se cambia en
caliente. El 4 MiB queda por encima de los topes de consumidores (1–2 MiB) y por debajo del de portadas (8 MiB, camino distinto con streaming propio).

| Capa | Valor | Papel |
|---|---|---|
| `max_cuerpo_transfer_bytes` (nuevo) | 4 MiB (1–16) | Último recurso para **toda** petición de `peticiones.py` y `cache_http` |
| `MAX_CUERPO_CACHE` | 2 MiB | Solo persistencia; un cuerpo 2–4 MiB se lee y no se guarda (log actual) |
| Fandom / Herald / guías | 2 / 1 / 2 MiB | Validación de la fuente de negocio, **después** del tope general (no se duplica el buffer) |
| Robots | 512 KiB | Parseo; el general lo cubre |
| `url_portada.MAX_BYTES` | 8 MiB | Portadas, camino aparte que ya hace streaming; no se unifica |

Log (una línea, `structlog`): `peticiones.cuerpo_demasiado_grande` con `fuente`, `motivo`, `bytes_leidos`, `limite` y `host` (nunca URL,
query ni cuerpo). Un evento por petición cortada.

## 4. Criterios de aceptación medibles

| # | Criterio | Verificación |
|---|---|---|
| AC-01 | Cuerpo exactamente igual al tope → devuelve `.content` completo, sin excepción, 1 petición | `MockTransport` con N=cap |
| AC-02 | Cuerpo cap+1 → `CuerpoDemasiadoGrande` (`motivo="chunks"`), `bytes_leidos` en `(cap, cap+64 KiB]`, 1 petición, log único | transporte con cuerpo cap+1; contar peticiones y log |
| AC-03 | Sin `Content-Length` (chunked) → mismo corte por chunks | `AsyncByteStream` propio sin cabecera |
| AC-04 | `Content-Length` > cap → excepción `motivo="content_length"` **sin leer chunks** (`bytes_leidos==0`) | transporte que registra lecturas |
| AC-05 | `Content-Length` mentiroso (dice 10, manda 100) → corta por chunks, no por cabecera | `MockTransport` con cabecera falsa |
| AC-06 | Redirección 302 con cuerpo enorme seguida de destino pequeño → **no** hay excepción, se siguen 2 peticiones y se devuelve la final | transporte con 302 grande → 200 |
| AC-07 | Reintentos intactos: 500→200 normal devuelve 200 (2 peticiones); 500→200 enorme corta en la final; el tope **no** se reintenta | `MockTransport` secuencial |
| AC-08 | `cache_http`: cuerpo enorme ⇒ excepción propagada y **0** escrituras/negativas en `CacheHttpFalsa`; 304 y hit siguen verdes | `tests/test_cache_http.py` ampliado |
| AC-09 | `pedir_con_cache` y `pedir_con_cortesia` con cuerpos normales siguen devolviendo `.json()/.text/.content/.headers/.status_code` | consumidores Fandom/Herald/guías y Ajustes con `MockTransport` |
| AC-10 | `form_charset` y POST intactos (cuerpo y `Content-Type` con charset; 303 pasa a GET sin cuerpo) | pruebas de SCR4 que ya existen |
| AC-11 | Goteo lento: trozos con reloj simulado agotando `deadline` ⇒ `CortesiaEnEspera("cuerpo_lento")` antes del tope y respuesta cerrada | `AsyncByteStream` + `reloj` falso |
| AC-12 | Gzip-bomba: `Content-Encoding: gzip` con comprimido pequeño y decodificado > cap ⇒ corta por bytes decodificados | contenido gzip sintético |
| AC-13 | Las suites existentes (`tests/test_peticiones.py` 571 líneas, `test_cache_http.py`, `test_clientes_cortesia.py`) siguen verdes | ejecución completa por QA |

## 5. Plan de pruebas sin red

Todo con `httpx.MockTransport` o un `AsyncByteStream` propio que sirve trozos y **cuenta peticiones y bytes leídos**; cero red, sin Postgres. Clase nueva
`TestTopeDeCuerpo` en `tests/test_peticiones.py` (AC-01…07, 10), casos en `tests/test_cache_http.py` (AC-08) y un consumidor real (`FandomClient` con
`MockTransport`) para AC-09. Fixtures sintéticas generadas en la prueba (nada grande en el repo); goteo con `dormir`/`reloj` falsos; se mide el máximo
acumulado y que el pre-check de `Content-Length` no lea cuerpo. Nada de `skip`.

## 6. Riesgos en la Pi y límites

- **El tope es por respuesta, no global.** Varias peticiones concurrentes a fuentes distintas pueden coexistir (la cortesía serializa por fuente/host;
  el enricher es secuencial): pico ≈ cap × peticiones en vuelo (p. ej. 4 × 4 MiB = 16 MiB), aceptable en 512 MB; un semáforo global sería otra historia.
- **Doble copia final** (`bytearray` + `bytes`) ⇒ pico ≈2×cap por petición (~8 MiB con el default); se documenta y se mide.
- **`Content-Length` no es de fiar**: solo acelera el corte; el tope real son los chunks decodificados.
- **Compatibilidad de la `Response` reconstruida:** conserva status/headers/request y `.content/.text/.json()/.cookies`; auditar dobles de `_enviar` o
  tests que miren atributos internos (`._content`, `.elapsed`). `httpx>=0.27`.
- **Consumidores que no capturan `ErrorDePeticion`** (Comic Vine/GCD/Discovery) la verán en su manejador genérico y el ciclo la repetirá: no hay bucle
  dentro de la petición, pero es un fallo no transitorio; el Corte 2 decide si se marca explícitamente.
- **Fuera de alcance:** Prowlarr/Transmission/aMule y `url_portada.py` (portadas) no usan `peticiones.py`; no se finge cubrirlos. El cuerpo de una redirección no se lee (correcto por RFC); un `Location` en el cuerpo no se soporta.

## 7. Cortes para el builder

| Corte | Contenido | Est. |
|---|---|---|
| 1 | `_leer_con_tope` + `CuerpoDemasiadoGrande` + setting en `config.py` + log + `TestTopeDeCuerpo` y AC-01…07/10/13 | 0,5–1 d |
| 2 | Auditoría de consumidores y `cache_http` (AC-08/09/11/12), decisión sobre marcar explícitamente el fallo en Comic Vine/GCD/Discovery, nota en `deudas-menores` y BACKLOG | 0,5 d |

El Corte 1 ya cierra RES-3 (el riesgo de memoria queda acotado); el Corte 2 evita que un cuerpo grande se repita cada ciclo en los
consumidores que no capturan `ErrorDePeticion` y deja las pruebas de integración. Una historia = una PR, un commit por corte.

## 8. Trazabilidad

RES-3/M-3 (`secops-SCR1-2026-11-13.md:123-134`, `deudas-menores-2026-11-14.md`) → §1-§5; issue #812 (P1/M). No toca `services/seguridad.py`/`web/ajustes.py`: no aplica §5.8 de CLAUDE.md.
