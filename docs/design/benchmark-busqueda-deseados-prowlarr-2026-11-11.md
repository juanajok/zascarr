# Benchmark — por qué «Deseados» no busca en Prowlarr y cómo lo hacen Mylar3/Kapowarr

> **Ficha de benchmarking** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13).
> **Pregunta del PO (2026-11-11):** «¿Por qué en Deseados no busca en Prowlarr? Haz benchmarking
> a ver cómo lo hace Mylar3, Kapowarr, etc.».
> **Alcance:** diagnóstico del flujo actual y comparación de patrón; **no** implementa cambios.
> **Método:** lectura del código de ZascArr y de los repos de referencia; **no** se ha llamado a
> Prowlarr, Transmission, aMule, Mylar3 ni Kapowarr en vivo. Todo lo no ejecutado es **NOT RUN**.

## 0. Respuesta corta

**Deseados sí busca en Prowlarr**, pero solo cuando se cumplen **todas** estas condiciones:

1. Prowlarr está **encendido** en Ajustes (`prowlarr_enabled`), con **URL** y **API key** guardadas.
2. El **aviso legal** está aceptado; si no, el ciclo entero se salta.
3. El deseo está en estado **`wanted` o `failed`** y no está dentro del **cooldown** de 6 h.
4. El ciclo de fondo corre (cada `scan_interval_minutes`, por defecto **60 min**) o se pulsa
   **«Buscar ahora»** en la fila.
5. Prowlarr responde y sus indexadores devuelven algo en las categorías de cómic `7030`/`7020`,
   y el resultado tiene un **backend de descarga activo** (Transmission/aMule).

Si falla el punto 1, hoy el motivo puede quedar como «no se encontró nada» en vez de «Prowlarr no
está configurado»: el cliente devuelve `[]` cuando falta la API key y el orquestador no distingue
esa causa de una búsqueda sin resultados. Es la **deuda de diagnóstico** principal que sale de este
benchmark. La comprobación rápida es **Ajustes → Prowlarr → «Probar conexión»**.

## 1. Comportamiento actual de ZascArr (evidencia)

- `src/zascarr/services/orchestrator.py`
  - `hay_fuente_de_busqueda()`: Prowlarr activo **o** foro configurado. Si no, ni se llama.
  - `process_wishlist()`: solo `WANTED`/`FAILED`, cooldown
    `orchestrator_retry_cooldown_hours` (6 h por defecto); el ciclo de fondo está en
    `main.py::_orchestrator_loop`, cada `scan_interval_minutes` (60 min por defecto).
  - `_search_and_rank()`: comprueba el aviso legal, construye la consulta con **título + número**,
    llama a `ProwlarrClient.search(query, categories=[7030, 7020])`, filtra por número y por
    backend activo, y deja el motivo en `Wishlist.last_error` (D9).
  - `preview_candidates()`: lo usa «Buscar ahora»; busca igual pero **no envía** nada hasta que la
    persona confirma un candidato (D10).
- `src/zascarr/services/prowlarr.py`
  - Consulta directa a `GET {prowlarr_url}/api/v1/search` con `X-Api-Key`.
  - **Si falta la API key devuelve `[]`** (`prowlarr.no_api_key`), sin una causa tipada que el
    orquestador pueda convertir en «configuración incompleta».
- `src/zascarr/web/wishlist.py`
  - «Buscar ahora» solo se ofrece en `WANTED`/`FAILED` (`puede_buscar_ahora`).
  - La fila muestra `last_error`, pero no el estado de configuración de Prowlarr.
- `src/zascarr/config.py`: `prowlarr_enabled=False` por defecto, URL por defecto
  `http://127.0.0.1:9696`, cooldown 6 h, ciclo 60 min.

**Consecuencia:** no hay una búsqueda «al añadir» inmediata: se espera al ciclo o se pulsa «Buscar
ahora». Y una configuración incompleta de Prowlarr puede parecer «sin resultados».

## 2. Referencias y versiones

| Referencia | Versión/commit | Fecha | Qué se leyó |
|---|---|---|---|
| **Mylar3** | `v0.8.3`, commit `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` | 2025-08-17 | `mylar/search.py`, `mylar/config.py`, `mylar/webserve.py`, `mylar/importer.py` |
| **Kapowarr** | `v1.3.2`, commit `c191dda6617929c81292483a8cc07f631111dae2` | 2026-09-14 | `backend/implementations/indexer_clients/`, `backend/features/search_full.py`, `docs/src/settings/indexers.md` |

Licencias: Mylar3 **GPL-3.0**; Kapowarr **GPL-3.0**. Solo se comparan **patrones**, no se copia
código. No se han ejecutado sus interfaces ni sus ciclos.

## 3. Cómo lo hace Mylar3

- **No tiene integración nativa con la API de Prowlarr.** Su modelo es de **proveedores**:
  Newznab, Torznab, DDL (GetComics/External), 32P y torrents públicos
  (`mylar/search.py::provider_order`, líneas 557–658). Prowlarr se usa como proveedor
  **Newznab/Torznab** (la config even menciona Prowlarr al deduplicar nzb.su/dognzb,
  `mylar/config.py` 802–806); no hay cliente de la API `/api/v1/search` de Prowlarr.
- **Cola de Wanted/Failed** con búsqueda automática por intervalo: `SEARCH_INTERVAL`
  por defecto **1440 min**, mínimo 360 (`mylar/config.py` 117 y 1324); scheduler
  `SEARCH_SCHEDULER` (`mylar/__init__.py` 505).
- **Búsqueda manual por número**: `searchit`/`searchforissue` y `search_init` con título, número,
  año, editorial y fecha; el matching descarta releases de otro número/serie.
- **Proveedores ordenados y con pausa por proveedor**; si un proveedor falla, se pasa al siguiente.
  Envía a SABnzbd/NZBGet/Blackhole o cliente torrent.
- La búsqueda se **dispara al añadir** y en el ciclo de wanted; no hay que esperar solo al ciclo
  (aunque el ciclo sea el que barre lo pendiente).

**Lección:** el patrón útil no es «integrar Prowlarr de forma nativa», sino **una búsqueda por
número, con cola de wanted y un botón manual**, y **distinguir proveedor no configurado de sin
resultados**. ZascArr ya tiene lo primero y parte de lo segundo; le falta la distinción explícita.

## 4. Cómo lo hace Kapowarr

- Su capa de **indexer clients** contiene **solo GetComics DDL**
  (`backend/implementations/indexer_clients/ddl/GetComics.py`); la documentación de indexers solo
  describe GetComics (`docs/src/settings/indexers.md`). **No hay Prowlarr, Torznab ni Newznab** en
  esta versión.
- Tiene un **SearchCoordinator** (`backend/features/search_full.py`) que consulta todos los
  indexers activos, construye consultas por volumen/número, **puntúa y filtra** resultados
  (`backend/implementations/matching.py`) y los ofrece para descarga; sigue un modelo de
  «wanted issues» y clientes de descarga.
- Por tanto, en **Prowlarr** Kapowarr no sirve de referencia directa: su ecosistema de descarga es
  DDL. Lo que sí se puede adaptar es su **separación entre buscar, puntuar y descargar**, que
  ZascArr ya tiene en `preview_candidates` + `send_manual_candidate`.

## 5. Comparación de patrones

| Idea | ZascArr actual | Mylar3 | Kapowarr | Veredicto |
|---|---|---|---|---|
| Fuente de búsqueda | API directa de Prowlarr | Proveedores Newznab/Torznab/DDL; Prowlarr como Torznab/Newznab | Solo GetComics DDL; sin Prowlarr | **Conservar la API directa**: menos configuración y agrega indexadores |
| Disparo al añadir | Espera al ciclo o «Buscar ahora» | Búsqueda al añadir + cola wanted | Cola wanted/search | **Adaptar**: ofrecer «Buscar ahora» inmediato y dejar claro que el ciclo es cada 60 min |
| Cola / cooldown | Wanted/Failed + 6 h | Wanted/Failed + intervalo 1440 min | Wanted issues + search coordinator | **Conservar** el cooldown; no quemar Prowlarr |
| Búsqueda por número | Título + número, filtro y alias | Título/número/año/editorial, matching | Query builder + matching/ranking | **Conservar**; ya cubre el caso |
| Diagnóstico de fuente | D9 distingue sin fuente/fallo/sin resultados, **pero no Prowlarr sin API key** | Logs de proveedor; orden y pausas | Estados de indexer | **Mejorar**: estado explícito de configuración de Prowlarr |
| Manual con confirmación | «Buscar ahora» previsualiza y confirma | Búsqueda manual y descarga | Búsqueda manual y descarga | **Conservar** (D10) |
| Multi-proveedor | Prowlarr abstrae | Lista de proveedores y prioridades | Solo DDL | **Conservar**: no construir un segundo orquestador de indexadores |

## 6. Por qué puede no buscar en tu instalación (checklist)

1. **Ajustes → Prowlarr**: ¿está encendido?, ¿URL correcta para Docker
   (`http://host.docker.internal:9696` si Prowlarr vive en la Pi)?, ¿API key guardada?
   Pulsa **Probar conexión**.
2. **Aviso legal**: si está pendiente, el banner de Deseados lo dice; las búsquedas automáticas
   están en pausa.
3. **Estado de la fila**: solo se busca en «Por buscar» o «Sin resultados»; «Buscando…»,
   «Descargando…» o «En tu biblioteca» no se relanzan. «Buscar ahora» no aparece en esos estados.
4. **Cooldown**: tras un intento, espera `orchestrator_retry_cooldown_hours` (6 h) para el ciclo
   automático; «Buscar ahora» es la vía inmediata.
5. **Categorías de Prowlarr**: ZascArr pide `7030`/`7020`; si tus indexadores no tienen categorías
   de cómic, Prowlarr devuelve vacío aunque la conexión sea correcta.
6. **Backend**: si hay candidatos pero Transmission/aMule están apagados, el motivo es «ningún
   cliente de descarga activo», no «Prowlarr no busca».
7. **Caso especial de error de configuración**: Prowlarr encendido sin API key → `ProwlarrClient`
   devuelve `[]` y el orquestador puede escribir «No se encontró nada». Es un **fallo de
   diagnóstico conocido**, no una prueba de que Prowlarr no tenga resultados.

## 7. Recomendaciones (sin implementar en esta ficha)

1. **Distinguir configuración incompleta de Prowlarr** de «sin resultados» en
   `_search_and_rank` (por ejemplo, que `ProwlarrClient` exponga un estado tipado
   `configuracion_incompleta` cuando falte URL/key, y que el orquestador lo mapee a un motivo D9).
2. **Mostrar en la fila de Deseados** el estado de la fuente de búsqueda («Prowlarr apagado»,
   «sin API key», «última búsqueda…»), sin jerga ni secretos.
3. **Valorar «Buscar ahora» como acción primaria** en filas wanted/failed, y explicar que el ciclo
   automático tarda hasta 60 min; no cambiar el cooldown sin datos.
4. **No** introducir un sistema de proveedores Newznab/Torznab como Mylar3: Prowlarr ya hace de
   agregador y la API directa es más simple; **no** copiar su modelo.
5. **No** tomar Kapowarr como referencia de Prowlarr: en esta versión solo descarga de GetComics.
6. Mantener la búsqueda por título+número, el filtro por backend y la confirmación humana.

## 8. PASS / FAIL / NOT RUN

- **PASS (lectura de código):** el flujo Prowlarr existe y está conectado al ciclo y a «Buscar
  ahora»; el cooldown, el gate legal y los estados D9 están implementados; Mylar3 usa
  Newznab/Torznab y no un cliente nativo de Prowlarr; Kapowarr solo tiene GetComics.
- **FAIL de diagnóstico:** Prowlarr sin API key devuelve `[]` y puede presentarse como «sin
  resultados»; no hay estado de configuración visible en la fila.
- **NOT RUN:** Prowlarr real, indexadores reales, ciclo de 60 min, búsqueda en la Pi, Mylar3 y
  Kapowarr ejecutados. No se ha tocado ninguna instalación.

## 9. Criterio de siguiente paso

Abrir una historia pequeña para el **diagnóstico de Prowlarr en Deseados** (configuración
incompleta vs. sin resultados) y, si el PO quiere, otra para el disparo inmediato al añadir. Este
benchmark no autoriza cambios por sí solo.


## 10. Implementación (2026-11-11)

Historia **#647**: se distingue Prowlarr incompleto de «sin resultados», con aviso en Deseados y
motivo explícito en la fila. **No** se implementa búsqueda automática al añadir (no lanzar red sin
acción/consentimiento); sí se aclara que el ciclo es periódico y «Buscar ahora» es inmediato.


## 11. Filtro de indexers para ZascArr (2026-11-11, #652)

Prowlarr admite `indexerIds` en `/api/v1/search`. Se añadió en Ajustes una **multiselección de
indexers** para ZascArr: se cargan desde Prowlarr, se guardan como lista de IDs y solo esos se
envían en la búsqueda. Vacío = todos. No modifica la configuración de Prowlarr ni afecta a otras
apps; evita desactivar globalmente 78 indexers para dejar 2–3 de cómics.
