# Ficha de benchmarking — #134 MIT-M8-US02: cortesía compartida y política de peticiones

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Es un
> paso de diseño **antes de la spec**: no escribe código de producto, no toca
> fuentes reales y no cambia el mínimo de Tebeosfera. Decide el PO.
>
> - **Fecha:** 2026-11-05
> - **SHA contrastado:** `3562f3a` (worktree aislado `.squad/wt-134`, rama
>   `feat/134-cortesia-compartida`, desde `origin/main`). Los ficheros citados
>   se leyeron en ese árbol.
> - **Alcance:** coordinación dentro de **una instalación / un proceso**,
>   presupuesto por fuente y destino efectivo, redirecciones, reintentos,
>   cancelación y observabilidad. **Fuera:** coordinación entre instalaciones,
>   fuentes nuevas, cambios de reglas de Tebeosfera, colas/prioridades nuevas y
>   almacenamiento compartido (Redis/PostgreSQL) en esta historia.
> - **Nivel 1–2.** No se incluye matriz 0–5: no hay productos completos que
>   elegir; se extiende un contrato propio y las alternativas se descartan por
>   incompatibilidad o coste, no por suma de puntos. La tabla de opciones de §6
>   cumple esa función sin fingir precisión.
> - **Caducidad:** 2027-01-04 (~60 días), o antes si cambia `utils/cortesia.py`,
>   el modelo de despliegue o las referencias.

---

## 0. Resultado en una línea

Se adopta el **concepto** de presupuesto compartido por fuente y destino de
Prowlarr/Sonarr, y se **descarta** su implementación: ZascArr debe **extender
`utils/cortesia.py`** para que todos los consumidores del proceso usen la misma
cola, cada salto y cada reintento pasen por ella, con política de reintento
acotada, cancelación segura y estado observable. Tebeosfera ya lo tiene; faltan
Comic Vine, AniList, GCD, el foro, las portadas y la prueba de conexión de
Ajustes. Kapowarr no sirve como contrato (ráfagas por lote y sin `Retry-After`);
Mylar3 se descarta (esperas fijas dispersas).

---

## 1. Problema fijado en el código vigente

### 1.1 Lo que ya existe

| Hecho | Evidencia |
|---|---|
| Limitador **por sitio y por proceso**, FIFO, reloj y espera inyectables | `utils/cortesia.py:24-53`; registro `:56-63` |
| Garantiza el mínimo entre **inicios** de peticiones; las concurrentes hacen cola; una espera cancelada no marca la petición | `utils/cortesia.py:43-53`; pruebas `tests/test_cortesia.py` |
| Depende de **un solo proceso**; lo declara | `utils/cortesia.py:9-15`; `Dockerfile:56-60` (`--workers 1`) |
| Tebeosfera lo usa con **2,5 s mínimo** y mínimo duro (solo se puede subir) | `services/tebeosfera.py:56,65,115-119,139-141` |
| Tebeosfera sigue **redirecciones a mano** (máx. 3), cada salto por el limitador, solo su origen | `services/tebeosfera.py:68,143-172` |
| Comic Vine y AniList usan **espera por instancia** y reintento propio de 429 con `Retry-After` | `comic_vine.py:19,85-86,107-120`; `anilist.py:39,76-77,93-105` |
| CV, AniList y GCD no configuran `follow_redirects` (httpx por defecto `False`): un 3xx **no se sigue** como salto presupuestado; el cliente lo tratará como respuesta no válida/final | `comic_vine.py:89-93`; `anilist.py:80-83`; `gcd.py:85-96` |
| GCD usa espera por instancia, sin reintento | `gcd.py:81-82,102-106` |
| El foro usa espera por instancia; su `login()` **no espera**; sus saltos se siguen a mano | `forum_scraper.py:77-86,88-97,138-161` |
| Las portadas externas siguen redirecciones a mano (máx. 3) pero **no pasan por cortesía** | `utils/url_portada.py:38-45,207-226` |
| La prueba de conexión de Comic Vine en Ajustes hace una petición directa, **sin limitador** | `web/ajustes.py:373-392` |
| `aMule` usa `follow_redirects=True`, pero es un servicio **local/LAN**, no una fuente externa | `services/amule.py:47-52` |
| No hay estado/observabilidad: `esperar()` devuelve la espera, pero los llamadores la ignoran | `utils/cortesia.py:43-53`; `tebeosfera.py:139-141` |

### 1.2 Consumidores: qué está coordinado y qué no (criterio 1)

| Consumidor | Hoy | Propuesta |
|---|---|---|
| Enricher / Descubrir: Comic Vine | Por instancia; cada ciclo crea cliente | **Coordinado** |
| Enricher / Descubrir: AniList | Por instancia | **Coordinado** |
| Enricher / Descubrir: Tebeosfera | Ya compartido por sitio | **Coordinado** (se conserva) |
| Descubrir: GCD | Por instancia | **Coordinado** |
| Foro configurado | Por instancia; login sin espera | **Coordinado** |
| Portadas externas (`url_portada`) | Sin cortesía; redirecciones a mano | **Coordinado por host** |
| Prueba de conexión de Comic Vine en Ajustes | Directa | **Coordinado** (una petición sujeta a la misma política) |
| Prowlarr, Transmission, aMule (API local/LAN) | Clientes propios | **No coordinados** con fuentes externas; su ritmo es otro |
| Notificador/webhooks (URL del operador) | Cliente directo | **No coordinado** con fuentes; no es una fuente |
| Otras instalaciones / procesos | Sin estado compartido | **No coordinados**: se declara |

La coordinación es **de proceso**: el limitador vive en memoria. No hay
coordinación entre réplicas ni instalaciones y esta historia no la promete.

---

## 2. Referencias consultadas (3; Mylar3 descartada)

Se usan tres contratos: Prowlarr, Sonarr/Radarr y Kapowarr. Mylar3 se revisó y
se descarta al final; no se añaden más referencias.

### 2.1 Prowlarr — presupuesto por host y reintentos con estado

- **Versión/commit:** v2.7.0.5723, commit
  `aa4e451400118342bf9546a6d23e20526ab9ad66` (`develop`, consultado el
  2026-11-05). [Código en ese commit](https://github.com/Prowlarr/Prowlarr/tree/aa4e451400118342bf9546a6d23e20526ab9ad66).
- **Presupuesto:** `RateLimitService` guarda una marca por **clave** y espacia
  `WaitAndPulseAsync`; `HttpClient` usa `request.Url.Host` como clave
  (`src/NzbDrone.Common/TPL/RateLimitService.cs:18-52`;
  `HttpClient.cs:148-164`). El **host efectivo** es, por tanto, la unidad; dos
  indexers del mismo host comparten la marca.
- **Intervalo:** cada indexer declara `RateLimit` (2 s por defecto) y
  `HttpIndexerBase` eleva el mínimo del `HttpRequest` a ese valor
  (`HttpIndexerBase.cs:82,724-727`).
- **Redirecciones:** hasta **5** (`HttpClient.cs:43`); cada salto vuelve a
  entrar en `ExecuteRequestAsync`, que vuelve a esperar por el host del salto
  (`HttpClient.cs:71-106,148-164`). No se reinicia el presupuesto por saltar.
- **Reintentos:** Polly reintenta **2** veces (3 intentos) solo 5xx, 408 o
  excepción con respuesta 5xx; espera `RateLimit` con backoff exponencial y
  jitter (`HttpIndexerBase.cs:36-65`). Un **429 no se reintenta en caliente**:
  se convierte en `TooManyRequestsException`, se lee `Retry-After` (segundos o
  fecha) y el indexer queda bloqueado `RetryAfter` o **1 h** mínimo
  (`HttpIndexerBase.cs:479-486`; `TooManyRequestsException.cs`).
- **Observabilidad:** endpoint `GET /api/v1/indexerstatus` con
  `IndexerId`, `DisabledTill`, `MostRecentFailure`, `InitialFailure`
  (`Prowlarr.Api.V1/Indexers/IndexerStatusController.cs` y
  `IndexerStatusResource.cs`). No expone cola, espera actual ni intervalo; no
  expone credenciales.
- **Qué no resuelve:** no hay coordinación entre procesos/réplicas; no hay cola
  visible ni cancelación con reserva. **Un salto sí cuenta** porque cada hop
  vuelve a pasar por el cliente.

### 2.2 Sonarr / Radarr — presupuesto por indexer (misma familia)

- **Versión/commit:** Sonarr v4.0.20.3014,
  `c018578e4b79ee048575c02d7a8aa2b929e4b837`; Radarr v6.4.4.10685,
  `479b6f2a17b5e5b0378659bc27401750f10829a7` ([Sonarr](https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837),
  [Radarr](https://github.com/Radarr/Radarr/tree/479b6f2a17b5e5b0378659bc27401750f10829a7)).
  Misma familia `NzbDrone`; se cita Sonarr como fuente y se comprueba Radarr por
  estructura.
- **Presupuesto:** `HttpIndexerBase.RateLimit` por defecto 2 s (`:33`) y
  `RateLimitKey = Definition.Id` (`:353-360`); `RateLimitService` combina la
  clave base (host) con la subclave (indexer). Es un presupuesto **por indexer**
  además de la marca de host.
- **Redirecciones:** hasta **5** (`HttpClient.cs:43,71-106`); como en Prowlarr,
  cada salto vuelve a pasar por el cliente y por el limitador.
- **Reintentos:** un 429 bloquea el indexer `RetryAfter`/mínimo 1 h
  (`HttpIndexerBase.cs:245-270`); no acelera para recuperar. No se ha
  encontrado un Polly equivalente al de Prowlarr en esta ruta
  (**[sin verificar directamente]**: no se ha ejecutado; se ha leído el
  fichero).
- **Observabilidad:** mismo patrón de estado bloqueado/fallos que Prowlarr.
- **Diferencia útil para ZascArr:** Prowlarr prioriza **host**; Sonarr prioriza
  **indexer**. ZascArr debe combinar ambos: la fuente (política) y el host
  efectivo (destino).

### 2.3 Kapowarr — cooldown por lote y retries de 5xx (lo que no se copia)

- **Versión/commit:** v1.3.2,
  `c191dda6617929c81292483a8cc07f631111dae2` (2026-09-14).
  [Código en ese commit](https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2).
- **Ritmo:** `CV_BRAKE_TIME = 1.0` s es un **promedio**: `__sleep_iter` lanza un
  lote (hasta el tamaño del lote) y duerme `1.0 × tamaño_lote` entre lotes
  (`backend/base/definitions.py:118-120`;
  `backend/implementations/comicvine.py:421-446`). Es una ráfaga seguida de
  pausa, no un mínimo entre peticiones; dos consumidores no comparten estado.
- **Reintentos:** `AsyncSession` hace hasta **5 intentos** con los 5xx/522 y esperas
  efectivas `1, 1, 2, 4` s entre ellos; **429 no está en la lista forzada** y no se lee `Retry-After`
  (`backend/base/helpers.py:1069-1105`;
  `backend/base/definitions.py:98-108`).
- **Redirecciones:** las gestiona `aiohttp` por su cuenta (no se contabilizan
  contra el cooldown). No hay presupuesto por host.
- **Conclusión:** Kapowarr confirma que el retry de 5xx con backoff es un patrón
  útil, pero **no** sirve como contrato de cortesía: ráfagas, sin compartir y
  sin `Retry-After`. Se descarta su implementación.

### 2.4 Mylar3 — descartada con motivo

Commit `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (release v0.8.3;
[código en ese commit](https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316)). Usa
`time.sleep()` fijo y disperso antes de llamadas a Comic Vine (`mylar/cv.py:70-72`,
`mylar/mb.py:73-75`, `mylar/importer.py:901-903`); **no se encontró** un
limitador compartido, `Retry-After` ni estado observable reutilizable. **Se descarta como
referencia de contrato**; no se afirma que no tenga otras esperas en el resto del
árbol.

---

## 3. Cómo lo resuelve cada una (contrato y unidad)

| Referencia | Qué decide | Unidad | Qué haría ZascArr distinto |
|---|---|---|---|
| **Prowlarr** | Espera por **host**; eleva al `RateLimit` del indexer; reintenta 5xx/408 con backoff+jitter; 429 bloquea el indexer con `Retry-After`/1 h; estado de bloqueo | Host efectivo + indexer | Añadir presupuesto por **fuente** además del host; estado con cola/espera, no solo bloqueo; un solo proceso explícito |
| **Sonarr/Radarr** | Espera por **indexer** (subclave) y host base; 429 bloquea; redirecciones ≤ 5 | Indexer + host | Fuente y host a la vez; sin “indexers” ni definiciones; la fuente es la política y el host el destino |
| **Kapowarr** | Cooldown promedio por lotes; hasta 5 intentos para 5xx; sin `Retry-After`; redirecciones de `aiohttp` | Lote de peticiones | Mínimo entre peticiones (no promedio), estado compartido, `Retry-After` compartido y saltos contados |
| **Mylar3** | Esperas fijas por llamada | Llamada | Descartada; no hay contrato central |

**Unidad de ZascArr:** una **petición HTTP** (incluido cada salto de redirección
y cada reintento), no una búsqueda de alto nivel. Es la unidad que ya usa
Tebeosfera: una búsqueda emite dos peticiones y cada redirección otra.

---

## 4. Adoptar / adaptar / descartar

| Idea | Resultado | Motivo |
|---|---|---|
| Presupuesto compartido por proceso entre consumidores de la misma fuente | **Adoptar** | Es el núcleo de #134; Tebeosfera ya lo demostró (`cortesia.py`) |
| Clave por **host efectivo** | **Adoptar** de Prowlarr | Es la unidad de destino real; un CDN o un host distinto no debe heredar el presupuesto del anterior |
| Clave por **fuente** además del host | **Adaptar** de Sonarr | Prowlarr se queda en host; Sonarr en indexer; aquí hacen falta las dos dimensiones |
| Cada salto de redirección cuenta y no reinicia el presupuesto | **Adoptar** de Tebeosfera/Prowlarr | Es el fallo actual de `follow_redirects=True`/clientes sin límite; el contrato lo prohíbe |
| Tope de redirecciones | **Adaptar** | Prowlarr/Sonarr usan 5; ZascArr ya usa 3 en Tebeosfera, foro y portadas: conservar **3** y no crear otra cifra |
| Reintento solo transitorio (5xx, 408, red) con máximo y backoff | **Adoptar** de Prowlarr/Kapowarr (idea) | Evita reintentar 4xx/errores de parseo; el número y la espera se fijan por política |
| `Retry-After` respetado y **compartido** (segundos o fecha) | **Adoptar** de Prowlarr/Sonarr | Hoy cada instancia duerme su 429 sin avisar a las demás; debe enfriar la fuente entera |
| Bloqueo/backoff sin acelerar para recuperar tiempo | **Adoptar** | Los saltos y reintentos consumen presupuesto; no hay ráfaga de recuperación |
| Estado observable de bloqueo/fallos | **Adaptar** de Prowlarr | Hace falta más: intervalo, cola, espera estimada y últimos reintentos; sin credenciales |
| Prioridades de cola | **Descartar** en v1 | No hay evidencia de necesidad; FIFO evita starvation y saltarse el mínimo; si se añade, nunca puede violar la cortesía |
| Cooldown por lotes (Kapowarr) | **Descartar** | Ráfaga + pausa no es un mínimo entre peticiones y no lo comparten los consumidores |
| Espera por instancia (CV/AniList/GCD/foro actuales) | **Descartar** | Es el bug que la historia corrige |
| Estado compartido en Redis/PostgreSQL | **Descartar** en esta historia | Fuera de alcance; añade dependencia y solo hace falta para multi-proceso, que no se soporta |
| Librería externa de rate limit | **Descartar** | No resuelve retry/redirecciones/observabilidad y añade dependencia a la Pi; `utils/cortesia.py` ya cubre la cola |
| Copiar código de Prowlarr/Sonarr/Kapowarr | **Descartar** | GPL-3.0 compatible, pero C#/otro modelo; se copian patrones, no ficheros |

**Licencias:** Prowlarr, Sonarr, Radarr, Kapowarr y Mylar3 son **GPL-3.0**
(compatible con ZascArr, pero no se reutiliza código); no hay ficheros copiados.

---

## 5. Recomendación de contrato para ZascArr

Parte de lo propio: `utils/cortesia.py` ya tiene la cola y la cancelación. Lo que
falta es una **política declarativa por fuente** y un **envoltorio común** que
usen todos los consumidores. No requiere ADR nuevo: no cambia arquitectura ni
añade estado compartido; si algún día se opta por coordinación multi-proceso,
eso sí exigirá ADR.

### 5.1 Política por fuente

Cada fuente declara, en configuración/registro (sin credenciales en el estado):

| Campo | Para qué |
|---|---|
| `fuente` | Identidad estable (`comicvine`, `anilist`, `tebeosfera`, `gcd`, `foro`, `portada:<host>`) |
| `intervalo_min_s` | Mínimo entre inicios de peticiones (el de Tebeosfera no baja de 2,5) |
| `max_intentos` | Total de intentos, incluido el primero; 1 = sin reintento |
| `backoff_base_s`, `factor`, `tope_s` | Espera entre reintentos transitorios |
| `max_redirecciones` | Tope de saltos; propuesta 3 (coherente con lo existente) |
| `hosts_redireccion` | Origen permitido: solo el origen de la fuente en APIs; allowlist de CDN en portadas |
| `respeta_retry_after` | Leer y obedecer `Retry-After` (segundos o fecha) |
| `bloqueo_max_s` | Si `Retry-After` supera este tope, no dormir la tarea: marcar la fuente bloqueada y devolver espera visible |

Valores iniciales (conservan los actuales; la spec los confirma):
Comic Vine 1,0 s / 3 intentos; AniList 1,5 s / 3; Tebeosfera 2,5 s / 1
(scraping sin contrato: no se reintenta); GCD 2,0 s / 2; foro 2,0 s / 2;
portadas: el intervalo de la fuente de la que procede la URL / 1 intento.
**Tebeosfera no se toca:** su mínimo sigue siendo 2,5 y solo se puede subir.

### 5.2 Presupuesto: fuente y destino efectivo

- **Dos niveles**, ambos por proceso:
  1. **Fuente:** entre dos peticiones cualesquiera a la misma fuente, sin
     importar el host ni la instancia, al menos `intervalo_min_s`.
  2. **Host efectivo:** entre dos peticiones cualesquiera al mismo host, al
     menos el máximo de los intervalos de las fuentes que lo usan (conservador
     si dos fuentes comparten CDN).
- **Clave de espera:** `(fuente, host_efectivo)` para la política y dos colas
  FIFO; no se crea un limitador por cliente. La primera petición del proceso no
  espera; las concurrentes se escalonan.
- **Todo salto y todo reintento** vuelve a pasar por ambas colas con el host de
  ese salto; el presupuesto no se reinicia al redirigir ni al reintentar.
- **Host efectivo** = origen normalizado (esquema, host, puerto) de la URL que
  se va a pedir; en la primera petición es el de la fuente; tras un 3xx es el
  del `Location`. Un CDN distinto tiene su propio host, pero la fuente sigue
  aplicando su intervalo.
- **Cancelación:** una espera cancelada libera la cola y **no** marca la
  petición; si ya fue autorizada y luego se cancela, cuenta (es conservador y
  evita ráfagas). No hay reserva de capacidad que liberar: la cola no reserva
  huecos. Cancelar no genera una petición adicional ni deja el candado tomado.
- **Prioridad:** **FIFO sin prioridades** en v1. Descubrir y enricher compiten
  igual; si el PO quiere prioridad, debe ser compatible con el mínimo y no
  saltarse la cola. No se implementa ahora.

### 5.3 Redirecciones

- **Manuales** en todos los clientes de fuentes (`follow_redirects=False`);
  nunca automáticas para APIs externas.
- Códigos 301/302/303/307/308; el resto de 3xx es fallo. 301/302/303 pasan a
  GET sin cuerpo; 307/308 conservan método y cuerpo.
- **Tope 3**; cada salto debe ser del **mismo origen** de la fuente (API/foro)
  o de la allowlist de portadas; sin `Location`, `Location` malformado u origen
  no permitido: fallo **sin enviar** al destino.
- Cada salto consume presupuesto de su host efectivo; no se reinicia; no se
  reintenta un salto por el simple hecho de redirigir.
- El fallo por redirección se trata como fallo de la petición, no como
  resultado vacío silencioso en la capa de fuente (la UI puede decir «sin
  resultados» solo si el contrato de esa fuente lo permite).

### 5.4 Reintentos

- **Condición:** solo fallo transitorio: red/timeout, 408, 5xx, y 429 con
  `Retry-After`/cooldown. **No** se reintenta 4xx distinto de 408/429, ni una
  respuesta de parseo/errores de API, ni una fuente apagada.
- **Máximo:** por política; inicial: 3 intentos totales en Comic Vine/AniList,
  2 en GCD/foro, 1 en Tebeosfera/portadas. Cada intento pasa por el
  presupuesto.
- **Backoff:** exponencial con base y tope de la política (propuesta: 2 s,
  factor 2, tope 30 s); **sin acelerar** después de una espera larga: se vuelve
  al intervalo normal, no se recuperan peticiones “perdidas”.
- **`Retry-After`:** se parsea como segundos o fecha HTTP; se obedece tal cual.
  El 429 **no se reintenta en caliente** si el bloqueo supera `bloqueo_max_s`:
  se marca la fuente como bloqueada hasta ese instante y se devuelve espera
  visible. Todos los consumidores de la fuente ven el mismo bloqueo; no cada
  instancia su propio `sleep`.
- **Fuente apagada:** se comprueba antes de encolar y antes de reintentar; si se
  apaga durante la espera, no se envía ni se reintenta. No se reintenta una
  fuente apagada.

### 5.5 Espera visible y observabilidad

- `esperar()` debe devolver un objeto/valor con `fuente`, `host_efectivo`,
  `espera_estimada_s`, `motivo` (`cortesia`, `reintento`, `bloqueo_fuente`) y
  `intentos_restantes`; los clientes lo registran y, si supera un umbral
  (p. ej. 1 s) en una acción de UI, la UI muestra «esperando por cortesía a
  <fuente> (~Ns)». **Nunca** promete una hora de recuperación ni disponibilidad;
  el estado es local y estimado.
- **Snapshot de estado** por fuente: `habilitada`, `intervalo_min_s`,
  `max_intentos`, `max_redirecciones`, `esperando_ahora`, `siguiente_hueco_s`,
  `ultima_peticion`, `ultimos_reintentos` (código/espera/resultado), `bloqueada_hasta`,
  `coordinacion: "proceso"`. Sin URL completa, sin query, sin API key, sin
  credenciales, sin datos personales.
- **Superficie mínima propuesta:** endpoint de solo lectura autenticado
  (`/api/estado/cortesia`) y un bloque en `/ui/estado`; la spec decide el nombre.
  No se mete en `/api/health` público más de lo imprescindible: es un estado de
  operación, no un healthcheck.
- **Coordinación limitada:** el snapshot declara `coordinacion: "proceso"` y la
  documentación dice que varias instancias/workers **no** comparten estado. Si
  se detecta un despliegue con más de un worker (variable/entorno), se registra
  un aviso y no se simula una garantía global. La política por instancia es la
  conservadora.
- **Prowlarr** expone solo bloqueo/fallos por indexer; ZascArr puede dar más
  (cola, espera, último reintento) sin exponer credenciales.

### 5.6 Qué falta para cubrir los 9 criterios de #134

| Criterio | Estado hoy | Contrato propuesto |
|---|---|---|
| 1. Ámbito de coordinación | **FAIL parcial**: solo Tebeosfera; CV/AniList/GCD/foro por instancia; portadas y Ajustes sin cortesía | Registro de consumidores coordinados + lista de no coordinados (§1.2) |
| 2. Presupuesto por fuente y destino | **FAIL parcial**: Tebeosfera por sitio; resto por instancia; portadas sin límite | Dos niveles fuente+host efectivo, todas las peticiones/saltos/reintentos |
| 3. Redirecciones acotadas | **FAIL parcial**: Tebeosfera/foro/portadas a mano; CV/AniList/GCD no siguen; portadas no presupuestan | Manual, ≤3, mismo origen/allowlist, cada salto cuenta, sin reinicio |
| 4. Reintentos controlados | **FAIL**: reintento propio por instancia en CV/AniList; resto sin política; 429 no compartido | Política única: condición, máximo, backoff, `Retry-After`, fuente apagada, sin acelerar |
| 5. Espera visible sin promesas | **FAIL**: `esperar()` devuelve pero se ignora; no hay superficie | Devolución con fuente/motivo/estimación; UI solo si > umbral; sin promesas |
| 6. Fallos de coordinación visibles | **PASS documental**: `cortesia.py:9-15` y `cortesia-tebeosfera.md` lo declaran; no está en estado | Snapshot `coordinacion: "proceso"` + aviso si multi-worker; documentación |
| 7. Prioridad y cancelación | **PASS parcial**: cancelación segura en el limitador y probada; no hay prioridad ni estado de cola | FIFO sin prioridad; cancelar no consume ni bloquea; sin petición extra |
| 8. Observabilidad mínima | **FAIL**: solo logs; no hay estado de fuente/cola/reintentos | Snapshot por fuente con campos de §5.5; sin credenciales |
| 9. Evidencia verificable | **FAIL parcial**: tests de `cortesia` y Tebeosfera; no hay pruebas de CV/AniList/GCD/foro/portadas bajo contrato común | Matriz de pruebas §7 (concurrencia, redirects, retry, 429, apagada, cancelación, multi-proceso) |

---

## 6. Opciones y decisión (sin matriz ponderada)

No hay una matriz 0–5: no se elige un producto completo y una suma de pesos
fingiría una precisión que el problema no tiene. La decisión se toma por
compatibilidad y riesgo:

| Opción | Veredicto | Motivo |
|---|---|---|
| A. Seguir con límites por instancia | **Descartar** | Es el bug: CV/AniList/GCD/foro no comparten; portadas y Ajustes no pasan por cola |
| B. Extender `utils/cortesia.py` con política común y envoltorio para todos los consumidores | **Adoptar** | Es la base ya probada; cubre 9 criterios sin dependencia nueva; Tebeosfera no cambia |
| C. Copiar/portar el patrón Prowlarr/Sonarr | **Descartar** | C# y modelo de indexers; solo sirve como evidencia de host/indexer, retry y estado |
| D. Coordinación multi-proceso con Redis/PostgreSQL | **Descartar en esta historia** | Fuera de alcance, dependencia nueva y ADR; el despliegue soportado es un proceso |
| E. Librería de rate limit (`aiolimiter` u otra) | **Descartar** | Nueva dependencia en la Pi; no resuelve retry/redirect/observabilidad; se necesitaría envolver igual |

**Recomendación:** B. La política se declara una vez; el envoltorio común aplica
presupuesto, redirecciones, reintentos y estado; los clientes solo aportan su
fuente, su host inicial y su parser. Si el PO quiere prioridades, se posponen a
una segunda iteración con evidencia; no se incluyen ahora.

---

## 7. Pruebas exigidas por el contrato (criterio 9)

Sin red real; transporte simulado y reloj/dormir inyectables, como ya hacen
`tests/test_cortesia.py` y `tests/test_tebeosfera_cortesia.py`.

1. **Concurrencia de consumidores:** dos clientes distintos (p. ej. enricher y
   Descubrir) de la misma fuente se espacian; dos fuentes distintas no se
   bloquean entre sí.
2. **Host efectivo:** una redirección a otro host consume el presupuesto del
   host final y el de la fuente; el presupuesto no se reinicia; no hay ráfaga
   tras el salto.
3. **Tope de redirecciones:** 1–3 saltos pasan; el cuarto corta; `Location`
   ausente/malformado/origen no permitido no envía nada al destino.
4. **Reintentos:** 5xx/408/red reintentan con backoff y máximo; 4xx no;
   429 respeta `Retry-After` (segundos y fecha) y bloquea a **todos** los
   consumidores; no se acelera después.
5. **Fuente apagada:** no se encola, no se envía, no se reintenta; si se apaga
   durante la espera, no se hace la petición.
6. **Cancelación:** cancelar en la espera no consume ni marca la petición; no
   deja el candado tomado; la siguiente petición respeta el intervalo; cancelar
   después de autorizar cuenta.
7. **Espera visible:** el resultado incluye fuente, motivo y estimación; la UI
   solo la muestra si supera el umbral; nunca promete recuperación.
8. **Observabilidad:** snapshot con fuente/intervalo/cola/reintentos/bloqueo;
   sin URL completa, query, API key ni credenciales.
9. **No coordinado:** simular dos procesos/limitadores separados y comprobar que
   el contrato **no** promete coordinación (el estado lo declara); no se intenta
   coordinar.

---

## 8. IGUALAR y MEJORAR (semilla de spec)

### IGUALAR (mínimos que ya hacen las referencias o lo propio)

1. **Un presupuesto compartido** por fuente dentro del proceso, no por
   instancia (Prowlarr/Sonarr; ya en Tebeosfera).
2. **Host efectivo** como destino de la espera y **cada salto** cuenta
   (Prowlarr), sin reiniciar el presupuesto.
3. **Tope de redirecciones** y política de origen (Tebeosfera/foro ya lo hacen).
4. **Reintento acotado** por condición, máximo y backoff; `Retry-After`
   respetado; 429 compartido (Prowlarr/Sonarr).
5. **Fuente apagada = sin petición ni reintento**; sin acelerar para recuperar.
6. **Cancelación segura** y **estado observable** de bloqueo/fallos (Prowlarr),
   más la cola local.
7. **Contrato único**, no siete copias de `self._last_req`.

### MEJORAR (huecos que las referencias no cubren o cubren parcialmente)

1. **Dos niveles fuente+host** (Prowlarr solo host, Sonarr solo indexer) y
   presupuesto común para portadas, foro y la prueba de Ajustes, que hoy se
   escapan.
2. **Espera visible con estimación** y motivo, sin prometer disponibilidad; el
   estado de Prowlarr solo dice bloqueo/fallos.
3. **429 compartido por fuente**: hoy cada instancia duerme su 429 y las demás
   siguen llamando; debe enfriar la fuente entera.
4. **Coordinación declarada** en el estado y en la UI, no solo en el docstring;
   con aviso si el despliegue no es de un proceso.
5. **Pruebas de los 9 criterios en todos los consumidores**, no solo en
   Tebeosfera; matriz de transporte simulado con redirects/reintentos/cola.

---

## 9. PASS / FAIL / NOT RUN de esta ficha

| Comprobación | Estado | Evidencia / motivo |
|---|---|---|
| Referencias pertinentes, con versión/commit y contrato | **PASS** | Prowlarr, Sonarr/Radarr y Kapowarr; Mylar3 descartada con motivo |
| Problema local fijado en el código de `3562f3a` | **PASS** | §1 con fichero:línea; no se infiere por UI |
| Licencias revisadas | **PASS** | Prowlarr/Sonarr/Radarr/Kapowarr/Mylar3 GPL-3.0; no se copia código |
| Recomendación de contrato y 9 criterios | **PASS** | §5–§6; sin código de producto |
| Contraste de las referencias en ejecución | **NOT RUN** | No se ejecutaron Prowlarr/Sonarr/Radarr/Kapowarr/Mylar3; solo lectura de código |
| Pruebas de concurrencia/redirect/retry/429/cancelación | **NOT RUN** | No se ejecutó la suite ni bancos; §7 es el plan |
| Comportamiento real en la Pi (latencia, uso de CPU, esperas) | **NOT RUN** | No se midió; la historia no lo exige para decidir el contrato |
| **FAIL** | — | Ninguno de la ficha: no se ha implementado ni ejecutado nada que pueda fallar; los gaps de §5.6 son el estado actual, no un fallo de esta investigación |

---

## 10. Lo que esta ficha NO decide y caducidad

- No implementa el contrato ni toca `utils/cortesia.py`, clientes, tests o
  configuración; no añade ADR (no hay cambio arquitectónico ni estado
  compartido).
- No cambia el mínimo de Tebeosfera (2,5 s), ni sus redirecciones a mano, ni
  añade fuentes.
- No decide prioridades de cola, nombres exactos de endpoint/campos ni el
  umbral de espera visible: eso es de la spec.
- No promete coordinación entre procesos, réplicas ni instalaciones; si el PO
  la quisiera, sería otra historia con ADR y estado compartido.
- **Caduca:** 2027-01-04, o antes si cambian `utils/cortesia.py`/los clientes,
  el despliegue de un solo worker o las referencias.
