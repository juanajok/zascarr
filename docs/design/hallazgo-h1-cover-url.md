# H1 — Descarga de portadas desde el servidor: SSRF en `Series.cover_url`

> Hallazgo de la revisión de la rebanada 2 (2026-10-07), corregido en una PR independiente. Código leído en `main` @ `5645628`.
> Este documento recoge **exposición y condiciones de explotación**, no una calificación de riesgo: depende de cómo se despliegue.

## Qué ocurría

`Series.cover_url` es una URL que **descarga el servidor** (`GET /ui/series/{id}/portada` → `fetch_and_cache_cover` en `utils/cover.py`, con `httpx.AsyncClient(follow_redirects=True)` y **sin ninguna restricción de destino**). La URL llegaba a la base de datos por cuatro caminos:

| Entrada | Quién la controla |
|---|---|
| Campo oculto `cover_url` de `POST /ui/descubrir/crear` | Quien envíe el formulario (no se validaba) |
| `POST /api/series` y `PATCH /api/series/{id}` | Quien llame a la API (solo `max_length=500`) |
| El enriquecedor (`Series.cover_url`) | **Lo que devuelva una fuente** (Comic Vine, AniList, Tebeosfera, GCD) |

Solo el proxy `GET /ui/descubrir/portada` tenía una lista de nombres de host; la cascada de portadas de una serie, no. `Issue.cover_url` también lo escribe el enriquecedor, pero **nada lo descarga** (comprobado).

## Condiciones de explotación (sin etiquetas de riesgo)

| Configuración | Quién puede provocar la petición |
|---|---|
| `auth_mode = none`, puerto solo en `127.0.0.1` (el valor por defecto, ADR 0004) | Cualquier proceso o usuario de **la propia máquina** que pueda enviar una petición HTTP al puerto con `Host` local. **No** una página web abierta en el navegador (la comprobación de origen rechaza el POST entre sitios) |
| Abierto a la LAN **con contraseña** (ADR 0004) | Cualquier sesión autenticada o cliente con Basic |
| Abierto a la LAN **sin contraseña** | Cualquiera que alcance el puerto con un `Host` admitido (el instalador A11 fija la contraseña antes de publicar el puerto; **el código por sí solo no lo impide**) |
| Cualquiera de las anteriores | **Sin acceso al puerto**: una fuente (o quien intercepte el tráfico entre la Pi y la fuente) que devuelva una URL hostil, que el enriquecedor guarda |

**Qué permitía:** que el servidor hiciera una petición `GET` a un destino elegido (servicios de la propia Pi como Transmission, Prowlarr, Kavita o aMule, o cualquier otro host alcanzable), siguiendo redirecciones, con 15 s de espera. Además el nombre de host podía resolver a una dirección interna aunque fuera «permitido» (*DNS rebinding*).
- **No es del todo ciego:** si el destino devuelve una **imagen válida**, se guarda y se **sirve de vuelta** en `/ui/series/{id}/portada`.
- **Canal lateral:** éxito o fallo (200 frente a 404) y **tiempo de respuesta**, que permite saber qué servicios internos están en marcha.
- **Efectos laterales:** cualquier servicio interno que cambie de estado con un `GET`.

**Qué no permitía:** leer una respuesta que no sea una imagen válida, enviar cuerpo, cabeceras o métodos distintos de `GET`, ni usar esquemas distintos de `http`/`https`.

Un token firmado (como el de Deseados, que usará la rebanada 2) garantiza la **integridad** de lo que vio la persona; **no** hace segura una URL externa. Por eso la corrección vive donde se hace la petición.

## La corrección (`utils/url_portada.py`)

| Capa | Qué hace | Prueba que la rompe |
|---|---|---|
| Sintaxis | Solo `http`/`https`; sin usuario ni contraseña; sin dirección IP escrita; puerto implícito o el de su esquema; nombre ASCII; sin caracteres de control; **y de la lista de fuentes** (solo la URL inicial) | `TestSintaxis` (31 rechazos, 10 aceptaciones) |
| Dirección resuelta | **Todas** las direcciones del nombre deben ser públicas. IPv4: fuera de los rangos de uso especial. IPv6: **solo** el unicast global (`2000::/3`) sin sus rangos especiales: no pasan las mapeadas, NAT64, 6to4, Teredo, locales ni de bucle. **Lista explícita**, no `is_global`, porque su resultado cambia entre versiones de Python y la CI usa otra que el desarrollo | `TestDirecciones` |
| Conexión fijada | Se conecta a **la IP ya validada**, con el nombre en `Host` y en la SNI de TLS; no hay una segunda resolución | prueba de la petición simulada y **servidor TLS local real** (el certificado se verifica contra el nombre, y uno de otro nombre se rechaza) |
| Redirecciones | A mano, **máximo 3**; cada salto repite las capas anteriores (los CDN de portadas redirigen con normalidad: prohibirlas rompía portadas legítimas). En los saltos no se exige la lista de fuentes | `TestDescarga` |
| Tamaño y tiempo | 8 MB (por `Content-Length` y también en streaming) y 15 s en total | `TestDescarga` |
| Al escribir | `POST/PATCH /api/series` y el alta de Descubrir rechazan lo que no cumpla la sintaxis (422 / 400) | `TestPuntosDeEntrada` |
| Al leer | La política está en `fetch_and_cache_cover`: **también protege los registros ya guardados** | `TestPuntoComun`, `test_un_registro_guardado…` |

El cliente por defecto usa `follow_redirects=False` y `trust_env=False` (un proxy del entorno resolvería el nombre por su cuenta y anularía la IP fijada).

## Qué cambia para quien ya tiene datos

- Los registros con una `cover_url` que no cumpla la política **no se borran ni se modifican**: al pedir su portada se ignoran (404 y marcador CSS). Para contar cuántos hay, en solo lectura:
  ```sql
  SELECT count(*) FROM series
  WHERE cover_url IS NOT NULL
    AND cover_url !~* '^https?://([a-z0-9-]+\.)*(comicvine\.gamespot\.com|cbsistatic\.com|anilist\.co|tebeosfera\.com|comics\.org)\.?(:(80|443))?/';
  ```
- Una portada servida desde un host fuera de la lista **dejaría de cargarse**. Las listas son las de `/ui/descubrir/portada`, que ya estaban en uso; si una fuente cambia de CDN y aparecen portadas rotas, se amplía **la lista**, no la política.
- Los **saltos** de una redirección pueden ir a otro CDN público (p. ej. `picsum.photos`), siempre que cumpla todas las demás capas.

## Lo que esta corrección NO cubre

- Un host **de la lista** que sirva contenido hostil: se descarga como imagen y la decodifica Pillow (riesgo de la biblioteca, acotado por el tope de 8 MB).
- Otros sitios donde el servidor haga peticiones a una URL no fija: **no hay otros hoy** en el código leído (el resto de clientes usan URL base fijas), pero la regla queda escrita en `CLAUDE.md` §5 para los nuevos.
- No se ha probado contra la red real ni con Python 3.11 (solo 3.14 en desarrollo): la lista explícita de direcciones es independiente de la versión **por construcción**, y la CI ejecuta las pruebas en 3.11.

## Verificación

Red simulada (resolutor y transporte inyectados), más un servidor TLS local con `openssl`. **32 mutaciones, las 32 detectadas** (cada capa se rompe a propósito y alguna prueba falla; con el bytecode desactivado). Los tres tests antiguos de `fetch_and_cache_cover` parcheaban `httpx.AsyncClient.get` con `cdn.example` (un host que la política ya no admite): se actualizaron conservando sus tres casos.
