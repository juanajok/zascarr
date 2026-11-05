# SPEC: «Compartir cortesía y política de peticiones» (MIT-M8-US02, #134) — v1.0

> **Estado:** v1.0 candidata. Ratifica los 9 criterios del issue y el contrato de
> `docs/design/benchmark-cortesia-compartida.md` (SCOUT, 2026-11-05, CONSTRUIR SOBRE LO PROPIO). No añade
> fuentes, no cambia Tebeosfera y no introduce estado compartido.
> **Base:** `3562f3a` (worktree `.squad/wt-134`); las citas son de ese árbol. **Notación:** EARS y
> Given/When/Then. Decide el PO; esta spec no implementa ni despliega.

---

## 0. Resumen

Hoy solo **Tebeosfera** comparte su límite en todo el proceso (`utils/cortesia.py:24-63`,
`tebeosfera.py:139-141`). Comic Vine, AniList, GCD y el foro espacian **por instancia**
(`comic_vine.py:82-125`, `anilist.py:74-110`, `gcd.py:79-126`, `forum_scraper.py:77-161`); las portadas no
pasan por cortesía (`url_portada.py:207-226`) y la prueba de Comic Vine de Ajustes pide directo
(`web/ajustes.py:373-392`). No hay espera visible ni estado.

**Contrato:** limitador **por proceso** con **dos niveles** (fuente y host efectivo), política declarativa por
fuente, envoltura común para cada petición/salto/reintento, redirecciones manuales ≤3, reintentos acotados con
`Retry-After` compartido, espera visible sin prometer recuperación y snapshot por fuente. Tebeosfera conserva
2,5 s, ≤3 saltos, mismo origen y 1 intento. Sin dependencias, sin Redis/PostgreSQL, sin escritura en disco/BD;
estado en memoria acotado. Tres PRs (§11).

---

## 1. Comportamiento actual y consumidores

| Pieza | Hoy | Dónde |
|---|---|---|
| Limitador compartido | Por **sitio** y **proceso**, FIFO, reloj/dormir inyectables; una espera cancelada no cuenta | `utils/cortesia.py:24-63` |
| Despliegue | Un solo proceso (`uvicorn --workers 1`) | `Dockerfile:56-60`; `cortesia.py:9-15` |
| Tebeosfera | 2,5 s mínimo (config solo sube), ≤3 redirecciones a mano, solo su origen, cada salto espera | `tebeosfera.py:65,68,74,112-119,139-172` |
| Comic Vine / AniList | Espera y reintento de 429 **por instancia**; sin redirecciones manuales | `comic_vine.py:19,82-125`; `anilist.py:39,74-110` |
| GCD / foro | Espera por instancia; GCD sin reintento; el `login()` del foro **no espera**; saltos a mano ≤3 | `gcd.py:79-126`; `forum_scraper.py:36,77-97,138-161` |
| Portadas externas | Redirecciones a mano ≤3 con SSRF/allowlist, **sin cortesía** | `url_portada.py:38-45,183-226`; `cover.py:79,161-193` |
| Prueba CV de Ajustes | Petición directa sin limitador | `web/ajustes.py:326-336,373-392` |
| Estado/observabilidad | No existe; `esperar()` devuelve la espera y se ignora | `cortesia.py:43-53`; `tebeosfera.py:139-141` |

**Coordinación (criterio 1):** quedan coordinados enricher y Descubrir (CV, AniList, Tebeosfera, GCD), el foro
del orchestrator (`orchestrator.py:556-584`), las portadas (**solo por host**) y la prueba de CV. **No
coordinados:** Prowlarr/Transmission/aMule (LAN, otra política), webhooks (`services/notifier.py`), otras
instalaciones y otros procesos. La coordinación es **de proceso** (memoria); no se promete entre procesos.

---

## 2. Alcance y no-goals

**En alcance:** presupuesto por fuente y host efectivo; cada salto/reintento por la cola; redirecciones
manuales acotadas; reintentos con condición, máximo, backoff y `Retry-After` compartido; fuente apagada sin
envío; cancelación segura; espera visible; snapshot observable; pruebas de los 9 criterios; documentación de
qué está coordinado y qué no.

**No-goals:** fuentes nuevas; cambios masivos de reglas; coordinación entre instalaciones o procesos;
resolución automática de fallos; despliegue; prioridades de cola; Redis/PostgreSQL como estado compartido;
dependencias nuevas (`aiolimiter`…); intervalos editables en Ajustes; cambiar el mínimo o las reglas de
Tebeosfera; coordinar clientes LAN o webhooks; prometer disponibilidad de una fuente. **Después:** prioridades,
jitter, histórico de métricas, multi-proceso (exigiría ADR).

---

## 3. Contrato del limitador

### 3.1 Política por fuente

| Fuente | UI | `intervalo_min_s` | `max_intentos` | `max_redirecciones` | `retry_after` | Config |
|---|---|---:|---:|---:|---|---|
| `comicvine` | Comic Vine | `comicvine_rate_limit` (1,0) | 3 | 3 | sí | `config.py:44` |
| `anilist` | AniList | `anilist_rate_limit` (1,5) | 3 | 3 | sí | `config.py:72` |
| `tebeosfera` | Tebeosfera | `max(2,5, tebeosfera_rate_limit)` | **1** | 3 | sí (bloquea, sin reintento) | `config.py:82` |
| `gcd` | GCD | `gcd_rate_limit` (2,0) | 2 | 3 | sí | `config.py:90` |
| `foro` | Foro | `forum_rate_limit` (2,0) | 2 | 3 | sí | `config.py:122` |
| `portada` | Portadas | por host: CV 1,0 · AniList 1,5 · Tebeosfera 2,5 · GCD 2,0; desconocido 2,5 | **1** | 3 | sí (bloquea el host) | `url_portada.py:39` |

`backoff_base_s=2,0`, `factor=2`, `tope_backoff_s=30`, `bloqueo_max_s=3600`. Tebeosfera no baja de 2,5 s y una
configuración menor se eleva con aviso (`tebeosfera.py:112-119`).

### 3.2 Dos niveles, ambos por proceso

1. **Fuente:** entre dos peticiones a la misma fuente, al menos `intervalo_min_s`, sin importar host ni
   instancia. Clave `fuente`.
2. **Host efectivo:** entre dos peticiones al mismo host, al menos el **máximo** de los intervalos de las
   fuentes que lo usan. Clave = origen normalizado `(esquema, host, puerto)`; `http` y `https` del mismo nombre
   son destinos distintos (normalización de `forum_scraper.py:63-72`).
3. **Host efectivo** = origen de la URL a pedir; tras un 3xx, el de `Location`. Un CDN distinto tiene su host,
   pero la fuente sigue aplicando su intervalo (salvo portadas, punto 4).
4. **Excepción declarada:** las portadas se coordinan **solo por host** (ficha §1.2) porque su URL no lleva la
   fuente; el intervalo del host sale de la tabla de §3.1. Se declara en el snapshot.
5. La **primera** petición del proceso no espera; las concurrentes se escalonan FIFO. No hay limitador por
   cliente ni por instancia: dos colas y un registro por proceso.

### 3.3 API (contrato)

| API | Comportamiento |
|---|---|
| `politica_de(fuente, ajustes)` | Construye la política de §3.1; pura y testeable con ajustes simulados. |
| `reservar(fuente, host, *, motivo="cortesia")` → `Turno` | Contexto asíncrono: registra la intención en las dos colas (FIFO) sin dormir; al entrar espera el hueco y entrega una `Espera`; al salir llama a `liberar`. |
| `esperar(fuente, host, *, motivo, espera_max_s)` → `Espera` | Atajo: reserva, espera y libera. Registra el inicio de la petición en cada cola. |
| `Espera` | `fuente`, `host_efectivo`, `espera_s`, `motivo` (`cortesia`, `reintento`, `bloqueo_fuente`), `intentos_restantes`. |
| `liberar(turno)` | Idempotente. Antes de autorizar retira la reserva y **no** consume hueco; después de autorizar no devuelve nada (conservador). |
| `bloquear(fuente, host, segundos, motivo)` | Aplica un `Retry-After`/429 a **toda** la fuente y a ese host, visible para todos. |
| `snapshot()` / `reiniciar_para_pruebas()` | Estado serializable (§6.1) / limpieza para tests. |

Orden de adquisición **siempre fuente → host** (evita interbloqueos). La autorización se marca con
`time.monotonic`; la espera no se descuenta del intervalo.

### 3.4 Cancelación

- **Antes de autorizar:** `CancelledError` sale del `async with`; `liberar` retira la reserva de las colas no
  autorizadas, **no** consume hueco ni deja candados; la siguiente petición respeta el intervalo; no se emite
  petición adicional.
- **Tras autorizar:** el hueco **cuenta** y no se devuelve (conservador); si se autorizó la fuente y se
  canceló esperando al host, la fuente ya consumió su hueco. Nunca se mantiene un candado durante la petición
  HTTP: la cola cubre la autorización, no la red.
- **Presupuesto agotado:** `CortesiaEnEspera` **antes** de enviar; no se emite la petición, se libera lo no
  autorizado y el llamador muestra la espera (§6.5); lo ya autorizado cuenta.

### 3.5 `asyncio.to_thread`

El limitador vive en el bucle y se `await` allí. Las peticiones usan `httpx.AsyncClient`; **no** se llama al
limitador desde un hilo. `to_thread` sigue para trabajo local (Pillow, disco): en portadas la espera y la
descarga van en el bucle (`cover.py:180-190`) y solo el redimensionado/escritura va al hilo. Un consumidor
síncrono dentro de un hilo no puede usar este limitador; no hay variante thread-safe en esta historia.

### 3.6 Envoltura común

Nuevo `utils/peticiones.py`: `pedir_con_cortesia(cliente, metodo, url, *, politica, espera_max_s,
hosts_redireccion, datos, cabeceras)` aplica §3-§5 y devuelve una respuesta no-3xx. Errores con **código
corto, nunca URL**: `CortesiaEnEspera(fuente, host, espera_estimada_s, motivo)`, `FuenteApagada`,
`RedireccionNoPermitida(host, motivo)`, `DemasiadasRedirecciones`, `ReintentosAgotados(fuente, intentos,
ultimo_codigo)`, `RespuestaNoTransitoria(codigo)`. Cada cliente conserva su parser y tolerancia; solo cambia
que una espera **no** se convierte en «sin resultados» (AC-16).

### 3.7 Presupuestos de espera por contexto

| Contexto | `espera_max_s` | Si se agota |
|---|---:|---|
| UI interactiva (Descubrir, probar conexión) | 10 | `CortesiaEnEspera`, aviso visible, no se envía |
| Fondo (enricher, foro del orchestrator) | 30 | se omite la fuente ese ciclo; no es fallo ni consume los 30 días |
| Portada (imagen del navegador) | 5 | no se descarga; 404 → marcador; la ausencia no se cachea |

El presupuesto cubre **todas** las esperas, saltos y reintentos de una llamada. Un `Retry-After` mayor que el
presupuesto restante no duerme la tarea: marca bloqueo y devuelve espera visible.

---

## 4. Redirecciones

- `follow_redirects=False` en **todos** los clientes; nunca automáticas. Tebeosfera (`tebeosfera.py:143-172`),
  foro (`forum_scraper.py:138-161`) y portadas (`url_portada.py:207-226`) ya lo hacen a mano; CV/AniList/GCD
  lo ganan con la envoltura (`comic_vine.py:90-92`, `anilist.py:81-83`, `gcd.py:86-92`).
- **Tope 3 saltos** (4 peticiones por llamada). `301/302/303` → GET sin cuerpo; `307/308` conservan método y
  cuerpo; el resto de 3xx es fallo.
- **Destino:** APIs y foro, solo el **mismo origen** de la fuente/foro; portadas, cada salto pasa otra vez por
  allowlist + DNS/IP + tamaño (`url_portada.py:38-45,207-226`).
- **Cada salto cuenta:** pasa por las dos colas con el host del salto, cuenta en §3.7 y **no reinicia** nada.
  Un bucle se corta por el tope, sin detección aparte.
- **Sin envío al destino prohibido:** `Location` ausente, malformado, con credenciales, otro origen o fuera de
  allowlist → fallo **antes** de pedir; solo se registra el host (`tebeosfera.py:163-168`).
- Un fallo de redirección es fallo de la petición; no se disfraza de «sin resultados» donde el contrato de la
  fuente no lo permite. Tebeosfera y GCD conservan su tolerancia actual (§7, §14.4). Los saltos de un intento
  fallido y su reintento **vuelven a contar** si se repiten.

---

## 5. Reintentos

- **Condición:** solo transitorios: red/timeout, `408`, `5xx`, `429`. **No** se reintenta otro `4xx`, un error
  de parseo/API ni una fuente apagada.
- **Máximo:** el de §3.1 (CV/AniList 3; GCD/foro 2; Tebeosfera/portadas 1).
- **Backoff:** `2 s ×2` (2, 4, 8…), tope **30 s**, sin jitter; cada espera vuelve a pasar por la cola y no se
  acelera para recuperar tiempo. Tras una espera larga, intervalo normal: sin ráfaga.
- **`Retry-After`:** segundos o fecha HTTP (stdlib); se **comparte** como bloqueo de fuente y del host del
  salto. Si supera `bloqueo_max_s` (1 h) se recorta a 1 h con aviso. Si no cabe en el presupuesto del
  llamador, espera visible sin dormir (§3.7). Ausente o inválido → backoff del intento.
- **429:** se obedece; todos los consumidores de la fuente ven el bloqueo. Un 429 no se reintenta en caliente
  si el bloqueo supera el presupuesto.
- **Fuente apagada:** se comprueba **antes de reservar** y **antes de cada intento/salto**; si se apaga
  durante la espera, no se envía ni se reintenta. La prueba de conexión de Ajustes es una acción explícita:
  se permite con la fuente apagada (sujeta a cortesía, sin reintento).
- El backoff es local al intento; **solo** el `Retry-After`/bloqueo es compartido.

---

## 6. Espera visible y observabilidad

### 6.1 Snapshot (forma)

```json
{
  "coordinacion": "proceso",
  "generado": "2026-11-05T15:00:00+00:00",
  "fuentes": [{
    "fuente": "comicvine", "nombre": "Comic Vine", "habilitada": true,
    "intervalo_min_s": 1.0, "max_intentos": 3, "max_redirecciones": 3,
    "esperando_ahora": 0, "siguiente_hueco_s": 0.0,
    "bloqueada_hasta_s": null, "bloqueo_motivo": null,
    "ultimos_intentos": [{"hace_s": 3.2, "intento": 1, "resultado": "429", "espera_s": 2.0}]
  }],
  "hosts": [{
    "host": "comicvine.gamespot.com", "fuentes": ["comicvine"],
    "intervalo_min_s": 1.0, "esperando_ahora": 0,
    "siguiente_hueco_s": 0.0, "bloqueada_hasta_s": null
  }]
}
```

Fuentes siempre listadas (también apagadas, `habilitada: false`; foro sin URL = `false`).
`ultimos_intentos`: máximo 3 por fuente, `resultado` en conjunto cerrado (`ok`, `red`, `408`, `429`, `5xx`,
`4xx`, `redireccion`), `hace_s` relativo. Todo tiempo es relativo o ISO en `generado`; nunca una fecha de
recuperación. Actualizar el snapshot no toca BD, disco ni red.

### 6.2 Endpoint y autenticación

`GET /api/estado/cortesia` (solo lectura) devuelve §6.1 con `Cache-Control: no-store`. Pasa por el
`AuthMiddleware`: **no** está en `_RUTAS_EXENTAS` (`services/auth.py:119-124,668-691`), así que con contraseña
responde 401/redirige como el resto; en `auth_mode=none` rige el mismo modelo local que la app. En arranque
degradado responde 503 como cualquier `/api/` (`services/auth.py:637-648`). `/ui/estado` pinta el mismo
snapshot **en servidor**, sin JS nuevo.

### 6.3 Bloque en Estado

Sección «**Cortesía con las fuentes**» bajo el resumen (`web/estado.py:36-50`, `estado.html`):
- «Cuánto se espera entre peticiones a cada fuente y qué está pasando ahora.»
- «La espera se comparte dentro de este ZascArr. Si ejecutas varias copias o procesos, cada una espera por su
  cuenta: no hay coordinación entre instalaciones.»
- Tabla **Fuente · Estado · Próxima petición · En espera · Reintentos recientes**. Estados «Disponible», «En
  espera (~Ns)», «Bloqueada temporalmente (~Ns)», «Apagada» (gris, no es fallo), «Sin configurar» (foro).
  Próxima «Ahora»/«En ~Ns»/«—»; reintentos «Ninguno» o «429 hace ~Ns».
- Si hay bloqueos: «Hay fuentes en espera por indicación del servicio. No se les hará ninguna petición
  durante el tiempo indicado; después se volverá a intentar, sin garantía de que respondan. La espera es local
  de este ZascArr.»
- Apagadas: «Apagada» y «No se consulta ni se reintenta».

### 6.4 Bloque en Ajustes

En «Fuentes de datos» (`templates/ajustes.html:10-41`), tras los interruptores:
«Cortesía: Comic Vine {v} s y 3 intentos; AniList {v} s y 3; Tebeosfera 2,5 s y 1; GCD {v} s y 2. Las portadas
se descargan al ritmo del sitio del que vienen y no se reintentan.» y «La espera se comparte dentro de este
ZascArr; otras instalaciones no se coordinan.» Fuente apagada: «Apagada: no se consulta ni se reintenta.»
Valores de `config.py`, no escritos a mano. El foro no tiene tarjeta en Ajustes; sale solo en Estado.

### 6.5 Espera visible en una acción

- **Descubrir:** nueva fuente de estado `espera` junto a `ok`/`apagada`/`sin_clave`/`error`
  (`services/discovery.py:57-60`). Aviso: «{Nombre}: no se ha consultado; hay que esperar ~{N} s por cortesía.
  No se ha enviado nada; vuelve a intentarlo en un momento.» (sin «~{N} s» si no hay estimación). No se cuenta
  como caída ni ausencia; si no se consultó ninguna: «Todavía no se ha consultado ninguna fuente: hay que
  esperar por cortesía.»
- **Ajustes, probar conexión:** «No se ha probado: hay que esperar ~{N} s por cortesía. Inténtalo de nuevo en
  un momento.», como aviso neutro (`warn`); `_ajustes_prueba.html` gana el estado `aviso`.
- **Portada:** sin texto nuevo; 404 → marcador existente, sin cachear la ausencia.
- Nunca «se recuperará», «volverá a estar disponible» ni una hora/fecha de recuperación.

### 6.6 Qué no se expone nunca

URL completa, ruta, query, `Location`, `Referer`, claves de API, tokens, cookies, cabeceras de autenticación,
cuerpo de petición/respuesta, User-Agent, títulos o términos buscados, rutas de archivos, URL del webhook.
Solo: slugs y nombres públicos, hosts de fuente/allowlist, intervalos, contadores, segundos, códigos de un
conjunto cerrado y booleanos. Los **logs nuevos** de cortesía llevan fuente, host y código; nunca `query` ni
`str(exc)`. En los clientes migrados se deja de registrar `query=` (`gcd.py:118,125`,
`forum_scraper.py:172`); `discovery.py:168` deja de volcar `str(exc)` y registra solo la clase. Tebeosfera
conserva su log actual (§7, §14.4).

### 6.7 Coordinación declarada

El snapshot declara `coordinacion: "proceso"` **siempre**; Estado y Ajustes lo dicen en llano; el nuevo
`docs/design/cortesia-compartida.md` lista coordinados y no coordinados (ficha §1.2) y CLAUDE.md §4 se
actualiza. **No** se detecta multi-worker: `--workers` no es consultable (`Dockerfile:56-60`) y un falso
positivo sería peor que la declaración (§14.1).

---

## 7. Tebeosfera: sin cambios

Se migra a la envoltura conservando **exactamente**: 2,5 s mínimo (solo subir; config menor se eleva con
aviso), ≤3 redirecciones a mano, solo su origen, cada salto por la cola, 1 intento sin reintento y fallo → sin
resultados. `tests/test_tebeosfera_cortesia.py` debe seguir pasando; el cambio de API se absorbe en el
wrapper, no en su comportamiento. Sus 2,5 s no se contagian a otras fuentes.

---

## 8. Criterios de aceptación (Given/When/Then)

> pytest con transporte simulado y reloj/dormir inyectables; sin red real ni esperas reales.

**AC-01 (criterio 1) — ámbito.** Given dos clientes distintos de la misma fuente, When piden a la vez, Then
comparten la cola de proceso; fuentes distintas no se bloquean; snapshot y doc declaran coordinados/no
coordinados. *pytest + inspección.*

**AC-02 (criterio 2) — dos niveles.** Given dos hosts de una fuente y dos fuentes que comparten host, When se
pide en paralelo, Then se respeta el mínimo de fuente y el del host (máximo de intervalos); la primera no
espera; no hay limitador por instancia. *pytest.*

**AC-03 (criterio 3) — redirecciones.** Given 301/302/303/307/308, cadenas de 1–3 saltos, cuarto salto, bucle,
`Location` ausente/malformado/otro origen y destino fuera de allowlist, When se sigue, Then 1–3 pasan y cada
salto espera y consume presupuesto sin reiniciarlo; el resto falla **sin enviar**; 301/302/303 → GET sin
cuerpo, 307/308 conservan método/cuerpo. *pytest con transporte que registra cada salto.*

**AC-04 (criterio 4) — reintentos.** Given red/timeout, 408, 500, 503, 400, 401 y error de parseo, When se
ejecuta, Then los transitorios reintentan con backoff 2,4… (tope 30) hasta el máximo y sin acelerar; 4xx no
transitorios y parseo no; una fuente apagada no se reintenta. *pytest.*

**AC-05 (criterio 4) — `Retry-After` compartido.** Given 429 con segundos y con fecha HTTP en dos consumidores,
When el primero lo recibe, Then la fuente y el host quedan bloqueados para todos; el segundo no se salta el
bloqueo; no se acelera; un bloqueo mayor que el presupuesto no duerme la tarea (espera visible); >1 h se
recorta con aviso; inválido cae al backoff. *pytest.*

**AC-06 (criterio 5) — espera visible.** Given una espera estimada que supera el presupuesto (10/30/5), When
se intenta, Then no se envía; se recibe `CortesiaEnEspera` con fuente/motivo/estimación; Estado muestra «En
espera (~Ns)»/«Bloqueada temporalmente»; Descubrir y Ajustes usan §6.5; ningún texto promete recuperación.
*pytest + inspección.*

**AC-07 (criterio 6) — coordinación declarada.** Given dos registros independientes (dos procesos), When ambos
piden, Then cada uno respeta su intervalo y declara `"proceso"`; la documentación dice que no hay coordinación
entre procesos/instalaciones; no se presenta el límite local como global. *pytest + inspección.*

**AC-08 (criterio 7) — FIFO y cancelación.** Given concurrentes, cancelación en espera, cancelación tras
autorizar y presupuesto agotado, When se cancelan, Then FIFO sin prioridades; cancelar antes no consume ni
deja candado ni pide de más; tras autorizar consume (no se devuelve); la siguiente respeta el intervalo; nadie
queda bloqueado. *pytest.*

**AC-09 (criterio 8) — observabilidad.** Given uso y el endpoint y `/ui/estado`, When se consultan, Then hay
fuente, intervalo, intentos, cola, siguiente hueco, reintentos y bloqueo; solo lectura y `no-store`; con
contraseña exige sesión como el resto; no aparece URL/query/clave/credencial/dato personal; el HTML pinta lo
mismo con los textos de §6.3. *pytest + inspección.*

**AC-10 (criterio 9) — evidencia.** Given el contrato, When se revisa la suite, Then hay casos de concurrencia,
redirecciones, reintentos, límite, fuente apagada, cancelación, `Retry-After` y despliegue no coordinado;
PASS/FAIL/NOT RUN separados; los NOT RUN son solo Pi/red real (§9.2). *pytest + informe.*

**AC-11 — Tebeosfera intacta.** Given su cliente, When corren sus pruebas, Then 2,5 s, ≤3 saltos, mismo origen,
1 intento y elevación de config se comportan igual. *`test_tebeosfera_cortesia.py`.*

**AC-12 — portadas.** Given una portada con redirecciones, host permitido y 429, When se descarga, Then cada
salto pasa por la cola **del host** una sola vez, sin reintento; allowlist/SSRF/tiempo/tamaño intactos; espera
>5 s → 404/marcador sin cachear ausencia; fuente apagada no recibe portadas. *pytest + pruebas H1.*

**AC-13 — `asyncio.to_thread`.** Given una portada, When se ejecuta, Then espera y petición van en el bucle, el
limitador no se llama desde el hilo y el trabajo local sigue en `to_thread`; usarlo desde un hilo falla
explícito. *pytest (hilo actual).*

**AC-14 — Descubrir distingue espera.** Given una fuente con `CortesiaEnEspera` y otra que responde, When se
busca, Then la primera es `espera` (no `error`), su aviso es §6.5 y no se dice «Ningún resultado» por ella; si
no se consultó ninguna, manda el anuncio de §6.5. *tests de Descubrir.*

**AC-15 — fuente apagada sin tráfico.** Given una fuente apagada, When enricher/Descubrir/foro/portada la
intentan, Then no se reserva/envía/reintenta y no consumen los 30 días; si se apaga en la espera, no se envía;
la prueba manual de Ajustes es la excepción explícita. *pytest.*

**AC-16 — espera ≠ fallo.** Given una petición no enviada por espera, When se propaga, Then no se marca
`error`, no se registra fallo ni se degrada la fuente; se muestra `espera` (UI) u omisión de ciclo (fondo).
*pytest.*

**AC-17 (NFR-01/02/04) — sin dependencias ni estado compartido.** Given la suite y el diff, When se inspecciona,
Then no hay dependencia/migración/Redis/PostgreSQL, el estado vive en memoria y el snapshot no escribe disco ni
BD. *pytest + `git diff`.*

**AC-18 (estados) — gris no es fallo.** Given una fuente apagada y una bloqueada, When se abre Estado, Then la
apagada sale «Apagada» (gris) sin contar como fallo, la bloqueada «Bloqueada temporalmente (~Ns)», la foro sin
URL «Sin configurar» y la disponible «Disponible»; los textos coinciden con §6.3. *pytest + inspección.*

**AC-19 (NFR-03/06/09) — coste y determinismo.** Given reloj simulado y una petición, When corre, Then no hay
I/O ni red añadida, el estado está acotado (6 fuentes, 3 intentos, hosts conocidos) y la suite no duerme de
verdad; mismos datos ⇒ mismos reintentos/esperas. *pytest.*

---

## 9. Pruebas y evidencia

### 9.1 Plan (sin red real; transporte simulado y reloj inyectable)

- `tests/test_cortesia.py` (extender): dos niveles, FIFO, primera sin espera, concurrencia, cancelación en
  espera/tras autorizar, presupuesto agotado, `Retry-After` compartido, snapshot, fuentes independientes.
- `tests/test_peticiones.py` (nuevo): redirecciones (códigos, tope, bucle, `Location`, origen/allowlist,
  métodos), reintentos (condición/máximo/backoff/tope), fuente apagada, errores con códigos.
- `tests/test_tebeosfera_cortesia.py`: intactas (regresión).
- `test_discovery_service.py`, `test_discovery_estados.py`, `test_descubrir_estados_web.py`: estado `espera` y
  avisos, sin contarlo como caída. `test_enricher.py`: espera/apagada no consumen los 30 días.
- `test_forum_scraper.py`: login y saltos por la cola, mismo origen intacto. `test_cover_ssrf.py` y
  `test_cover.py`: redirects contados por host, allowlist/SSRF, presupuesto, 404 sin cachear.
- `test_web_ajustes.py`: prueba de CV por cortesía, estado `aviso` y textos. `test_web_estado.py` (nuevo):
  bloque, filas, textos, sin secretos; endpoint JSON y autenticación.

### 9.2 PASS / FAIL / NOT RUN

Antes: criterios 1–5 y 8 en **FAIL parcial**; 6 documental; 7 PASS parcial; 9 FAIL parcial (ficha §5.6).
Cierre: **PASS** de lo cubierto por §9.1; **NOT RUN** solo latencia/CPU reales en la Pi, servicios externos
reales y despliegue multi-proceso (no soportado, no se prueba como PASS). Cada criterio cierra con su test o
con NOT RUN declarado; nunca «debería funcionar».

---

## 10. NFR

| ID | NFR | Regla / verificación |
|---|---|---|
| NFR-01 | Sin dependencias nuevas | Solo stdlib (`asyncio`, `time`, `datetime`, `email.utils`); `pyproject.toml` sin cambios |
| NFR-02 | Sin estado compartido | Nada de Redis/PostgreSQL; estado en memoria; sin migración |
| NFR-03 | Coste en la Pi | Una comparación de reloj y un contador por petición; sin I/O ni procesos/hilos nuevos; estado acotado |
| NFR-04 | Sin escritura | Snapshot y colas no escriben disco ni BD; endpoint solo lectura |
| NFR-05 | Sin red nueva | La cortesía espacia, no añade peticiones |
| NFR-06 | Testeable sin dormir | Reloj y `dormir` inyectables; la suite no espera de verdad |
| NFR-07 | Privacidad | Snapshot y logs nuevos sin URL/query/clave/credenciales; `no-store` en el estado |
| NFR-08 | Presupuesto 512 MB | Sin procesos/hilos nuevos; tablas del snapshot pequeñas y fijas |
| NFR-09 | Determinismo | Mismo reloj/respuestas ⇒ mismos reintentos/esperas; backoff sin jitter |
| NFR-10 | Compatibilidad | Tebeosfera, SSRF de portadas y contratos de cada cliente se conservan |

---

## 11. División en PRs

**Propuesta del Lead:** (1) limitador + migración + redirecciones; (2) observabilidad + Estado/Ajustes + docs;
(3) pruebas de los 9 criterios si no caben. **La veo bien con dos matices:** las pruebas de cada criterio van
con el PR que lo implementa (TDD), y PR-1 se parte si crece.

| PR | Contenido | Depende de |
|---|---|---|
| **PR-1a** | Núcleo: política, dos niveles, `reservar`/`esperar`/`liberar`, cancelación, `Retry-After`, presupuestos, `utils/peticiones.py`; migrar CV y AniList y la prueba de Ajustes; redirecciones manuales contadas. | — |
| **PR-1b** | Tebeosfera (regresión), GCD, foro (incluido `login`) y portadas (nivel host); fuente apagada sin tráfico; retirada de los `_last_req` restantes. | PR-1a |
| **PR-2** | Snapshot, `/api/estado/cortesia`, bloque de Estado, textos de Ajustes, estado `espera` en Descubrir; `docs/design/cortesia-compartida.md` y CLAUDE.md §4. | PR-1b |
| **PR-3** | Matriz de los 9 criterios entre consumidores + evidencia PASS/FAIL/NOT RUN de Pi/red real. | PR-1b (y PR-2 para AC-09) |

PR-2 y PR-3 pueden ir en paralelo tras PR-1b (AC-09 necesita PR-2). No cambia el contrato entre PRs.

---

## 12. Riesgos

| ID | Riesgo | Mitigación |
|---|---|---|
| R-01 | Migrar cinco clientes + portadas + Ajustes es grande | PR-1a/1b; tests por cliente; sin cambiar parsers |
| R-02 | Interbloqueo por orden de adquisición | Orden fijo fuente → host; prueba concurrente |
| R-03 | Cancelar deja candado | `async with`; el candado no cubre la red; prueba |
| R-04 | Limitador desde `to_thread` | Contrato y prueba de hilo; trabajo local aparte |
| R-05 | `Retry-After` enorme/inválido | Tope 1 h; fallback al backoff; no dormir la tarea |
| R-06 | Esperas largas en Descubrir | Presupuesto 10 s, aviso visible y no «sin resultados» |
| R-07 | Tebeosfera cambia sin querer | Sus pruebas siguen; 2,5/≤3/mismo origen/1 intento |
| R-08 | Regresión SSRF/allowlist en portadas | Reutilizar `url_portada.py`; pruebas H1 |
| R-09 | El snapshot filtra datos | Lista blanca de campos y pruebas de ausencia de URL/query/clave |
| R-10 | Falsa garantía multi-proceso | `coordinacion: "proceso"` + docs; sin detección |
| R-11 | Fuente apagada y portadas | No se piden portadas de fuentes apagadas; caché/legado siguen; prueba |
| R-12 | Logs existentes con `query=`/URL | Los caminos migrados usan fuente/host/código; Tebeosfera queda como deuda anotada |

---

## 13. Trazabilidad

| Criterio issue | FR | AC |
|---|---|---|
| 1. Ámbito de coordinación | FR-01 | AC-01, AC-07, AC-15 |
| 2. Presupuesto por fuente y destino | FR-02 | AC-02 |
| 3. Redirecciones acotadas | FR-03 | AC-03, AC-12 |
| 4. Reintentos / 429 / apagada | FR-04, FR-05, FR-06 | AC-04, AC-05, AC-15 |
| 5. Espera visible sin promesas | FR-07 | AC-06, AC-13, AC-14, AC-18 |
| 6. Fallos de coordinación visibles | FR-08 | AC-07, AC-09 |
| 7. Prioridad y cancelación | FR-09 | AC-08 |
| 8. Observabilidad mínima | FR-10 | AC-09, AC-17 |
| 9. Evidencia verificable | FR-11 | AC-10, AC-19 |

**FR (EARS):** FR-01 ubicuo (misma cola de proceso por fuente); FR-02 ubicuo (dos niveles); FR-03 ubicuo
(redirecciones manuales ≤3, mismo origen/allowlist, cada salto cuenta); FR-04 por evento (ante transitorio, se
reintenta con backoff y máximo); FR-05 estado (MIENTRAS la fuente esté bloqueada no se envía y la espera es
compartida); FR-06 no deseado (SI la fuente está apagada, no se envía ni se reintenta); FR-07 no deseado (SI
la espera supera el presupuesto, no se envía y se informa sin prometer recuperación); FR-08 ubicuo (estado y
documentación declaran coordinación por proceso); FR-09 ubicuo (FIFO sin prioridades y cancelación segura);
FR-10 ubicuo (snapshot sin secretos); FR-11 ubicuo (cada criterio con prueba o NOT RUN declarado).

---

## 14. Precisión sobre la ficha

1. **Detección multi-worker:** la ficha propone «si se detecta…, aviso». No es fiable: `--workers` no es
   consultable (`Dockerfile:56-60`) y un falso positivo sería peor. Se ratifica solo `coordinacion: "proceso"`
   + documentación; sin detección automática.
2. **Intervalo de portadas:** la URL no lleva la fuente; se resuelve con el mapa allowlist→fuente y el nivel
   host de §3.1/§3.2.
3. **`web/pendientes.py (portadas)`:** ahí la portada es local (zipfile/Pillow), sin peticiones externas; la
   descarga vive en `utils/cover.py:161-193`, llamada desde `web/series.py:320-326` y
   `web/discovery.py:150-155`.
4. **3xx actuales:** la ficha dice que CV/AniList/GCD lo tratan como «respuesta no válida/final»; en código,
   CV/AniList elevarían un error de JSON no capturado y GCD lo convierte en «sin resultados»
   (`gcd.py:110-126`). La spec fija redirección manual y conserva la tolerancia de cada cliente; un fallo de
   redirección no se disfraza donde el contrato no lo permite.
5. **Tebeosfera:** se migra solo a la envoltura; conserva ritmo/redirecciones/reintentos. Su log `query=`
   (`tebeosfera.py:179`) queda como deuda; los clientes migrados dejan de registrarlo.
6. **Prueba de conexión con fuente apagada:** la ficha no lo decide; aquí es una excepción explícita (acción
   manual del operador, con cortesía y sin reintento).

---

## 15. Auto-revisión

- [x] Los 9 criterios tienen AC (AC-01…AC-10) y los 7 casos del criterio 9 están cubiertos.
- [x] Números citados: intervalos (`config.py:44,72,82,90,122`), tope 3 (`tebeosfera.py:68`,
      `url_portada.py:43`), 1 proceso (`Dockerfile:56-60`), redirecciones manuales (`tebeosfera.py:143-172`,
      `forum_scraper.py:138-161`, `url_portada.py:207-226`).
- [x] Nada no verificable: cada AC es pytest/inspección; textos exactos; NOT RUN acotados.
- [x] Tebeosfera no cambia; sin dependencias, sin Redis/PostgreSQL, sin escritura, sin red nueva.
- [x] Snapshot y logs nuevos sin URL/query/clave; auth y `no-store` definidos.
- [x] Si la ficha se excede, se dice (§14).
- [x] PRs con dependencias y pruebas en el PR que implementa.

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-05 | v1.0 | Primera especificación de #134 sobre la ficha y `3562f3a`: limitador de dos niveles, redirecciones, reintentos, espera visible, observabilidad y pruebas de los 9 criterios. Tebeosfera sin cambios. |
