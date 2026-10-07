# H5 — `ForumScraper`: enlaces que cambian de host y cookies de sesión que viajan a cualquier sitio

> Hallazgo de la auditoría de peticiones salientes que cerró H1 (2026-10-07), corregido en una PR propia. Código leído en `main` @ `77f3b79`.
> Este documento recoge **exposición y condiciones de explotación**, no una calificación de riesgo.

## Qué ocurría

`ForumScraper` (`services/forum_scraper.py`) busca temas en un foro IPB que **elige quien administra la instalación** (`FORUM_URL`). Tenía tres fallos encadenados:

1. **El destino salía del HTML del foro, que no es de fiar.** `TOPIC_PATTERN` captura cualquier `href` que acabe en `showtopic=N`, y `urljoin(base, href)` **deja pasar una URL absoluta**: `http://127.0.0.1:9091/x?showtopic=1` o `//otro-host/x?showtopic=1` cambian el destino.
2. **Redirecciones automáticas** (`follow_redirects=True`) sin ninguna comprobación del salto.
3. **Las cookies de sesión del foro iban como `dict` en `httpx.AsyncClient(cookies=…)`, y `httpx` las envía a TODOS los hosts.** Comprobado con `httpx` 0.28.1 y un transporte simulado: el mismo `Cookie: member_id=1; pass_hash=…` llegaba a `foro.example`, a `127.0.0.1:9091` y a un host de terceros.

Por eso no era solo un SSRF: **filtraba la credencial de sesión del foro**.

## Condiciones de explotación (sin etiquetas de riesgo)

| Condición | Detalle |
|---|---|
| La integración debe estar activa | `FORUM_ENABLED=false` por defecto; hacen falta `FORUM_URL`, usuario y contraseña. **Cuando se activa, la vulnerabilidad estaba presente** |
| Quién controla el HTML | El propio foro (hostil o comprometido); contenido inyectado en una página del foro (XSS almacenado); o **alguien en la red si `FORUM_URL` es `http://`** (puede modificar la respuesta) |
| Quién provoca la búsqueda | El flujo de «Buscar» de una petición de Deseados: quien pueda disparar una búsqueda con la integración activa |

**Qué permitía:** una petición `GET` a un destino elegido (incluidos servicios de la propia Pi), y **enviar la cookie de sesión del foro a ese destino** (a un tercero: robo de la sesión del operador en el foro). La respuesta del destino solo se interpreta buscando enlaces `ed2k://` y `magnet:`.
**Qué no permitía:** leer la respuesta, ni enviar cuerpo o métodos distintos de `GET`.

## La corrección: la frontera es el origen del foro

**Por qué no se reutiliza la política de H1.** Los contratos son distintos: H1 admite solo nombres de una lista de CDN, exige direcciones públicas y puertos por defecto. El foro es **el sitio que eligió el operador**: puede estar en la LAN, con puerto propio o por IP. La frontera correcta no es una lista ni «solo direcciones públicas»: es **«el mismo origen»** (esquema, host y puerto de `FORUM_URL`).

| Capa | Qué hace |
|---|---|
| Enlaces | Un `href` solo se sigue si pertenece al origen del foro. Un absoluto de **otro** origen, con esquema ajeno (`javascript:`, `file:`…), con credenciales, `//otro-host`, barras invertidas, espacios o caracteres de control, **se descarta** (con el host y un código en el registro, nunca el enlace entero) |
| **Absolutos del propio foro** | **Se aceptan** y se reducen a ruta y consulta *antes* de `urljoin`. Los foros IPB suelen emitir enlaces absolutos a sus propios temas: rechazarlos todos dejaría la integración sin resultados. Una sola barra inicial en la ruta (ver abajo) |
| Redirecciones | **A mano**, máximo 3, y cada salto se valida contra el origen **antes** de pedirlo |
| Cookies | Solo en peticiones del origen **exacto** del foro, como cabecera explícita; el cliente se crea **sin jar de cookies** |
| Origen | Esquema, host (sin mayúsculas ni punto final) y puerto (el por defecto del esquema si no se escribe) |

## Dos fallos más que apareció al corregir

- **La propia reducción a ruta abría un desvío.** `https://foro.example//atacante.example/x` se reducía a la ruta `//atacante.example/x`, que `urljoin` lee como una referencia **sin esquema** y lleva a `https://atacante.example/x`. Se normaliza a una sola barra inicial, y se mantiene la comprobación del origen del resultado como segunda capa (con su propia prueba).
- **`urlsplit` y `urljoin` lanzan `ValueError` con ciertos caracteres Unicode** (normalización NFKC). Sin atenderlo, **un solo enlace hostil abortaba la búsqueda entera** (antes lo cazaba un `except Exception` más amplio). Se trata como un enlace rechazado.

## Qué cambia para quien administra la instalación

- **`FORUM_URL` debe ser el origen canónico** (el esquema y el host finales). Una redirección a **otro origen** —incluido `http → https` o `www → sin www`— **corta la petición** (con el registro `forum.tema_rechazado`/`forum.search_rechazada`, motivo `otro_origen`, y la búsqueda devuelve vacío). Antes se seguía sola. Es un cambio de comportamiento deliberado: las cookies no pueden acompañar a un salto de origen.

## Lo que esta corrección NO cubre

- **No exige que el host del foro sea público**: un foro en la LAN es legítimo y lo elige el operador (a diferencia de las portadas de H1).
- La contraseña se envía por `POST` a `FORUM_URL` tal cual: **con `http://` viaja en claro** (decisión del operador; fuera de alcance).
- Las cookies que el foro establezca después del login **no se actualizan** (como antes).
- Nada se ha probado contra un foro IPB real ni contra la red: **solo transporte simulado**.
- `logger.exception("forum.search_failed", query=query)` sigue registrando la consulta (no se ha tocado).

## Verificación

Transporte `httpx.MockTransport` que **registra cada petición con su host y su cabecera `Cookie`**; la aserción central es que **ninguna petición sale del origen del foro y ninguna cookie va a otro host**, con enlaces absolutos hostiles, redirecciones hostiles y el caso legítimo (enlaces relativos y absolutos del propio foro) funcionando.
