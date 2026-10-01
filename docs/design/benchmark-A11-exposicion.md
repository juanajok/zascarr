# A11 — elegir la exposición de red al instalar (ficha §13)

> Ficha de la historia A11 (P1/M). La **postura** ya está decidida en el
> [ADR 0004](../adr/0004-exposicion-de-red.md); esta ficha responde a **cómo se
> ofrece la elección** sin dejar una puerta abierta por descuido.

## Problema y datos de partida

- **Historia:** el coleccionista quiere usar ZascArr desde el móvil o la tablet sin
  editar `docker-compose.yml` a mano, y sin que «abrir» signifique «sin contraseña».
- **Hoy:** el puerto 8000 se publica fijo en `127.0.0.1` (`docker-compose.yml`).
  Para abrir a la LAN hay que editar el compose, y **nada obliga a que haya una
  contraseña** antes: A6 la hace opcional y se pone después, desde Ajustes.
- **Hecho técnico que condiciona el diseño:** el puerto publicado es propiedad de
  Docker/Compose en el host. **La aplicación no puede abrir ni cerrar su propio
  puerto**; Ajustes solo puede *informar* del estado. La elección tiene que hacerla
  quien escribe el `.env`: el instalador.
- **Resultado deseado:** tres opciones legibles, **por defecto la segura**, y que las
  dos que abren no puedan quedar activas sin contraseña.

## Referencias consultadas (código, commit fijado)

| Referencia | Commit | Qué hace |
|---|---|---|
| Sonarr (`v5-develop`) | `a8a82905e7` (2026-09-26) | `BindAddress` por defecto `*` (`ConfigFileProvider.cs`). `AuthenticationMethod` por defecto `None`, pero `AuthenticationRequired` por defecto **`Enabled`**: la autenticación es *obligatoria* y se relaja de forma explícita (`DisabledForLocalAddresses`, `DisabledForLocalhost`; `UiAuthorizationHandler.cs`). La relajación para «direcciones locales» **no se aplica si la petición trae `X-Forwarded-For`** (`IsClientAddressKnown`), es decir, detrás de un proxy no confía en la IP. En el primer arranque sin autenticación, `Page.tsx` abre un **modal sin botón de cierre ni clic de fondo** (`AuthenticationRequiredModal`) que obliga a decidir. Al guardar, `AllowedHosts` es obligatorio si se relaja la autenticación (`HostConfigController.cs`). Aviso de salud si `AllowedHosts` no está configurado. |
| Kapowarr | `c191dda661` (2026-09-14) | `host = '0.0.0.0'`, `auth_password = ''` por defecto (`backend/internals/settings.py`); `EXPOSE 5656` en el Dockerfile. Solo he leído los valores por defecto; **no he verificado** si fuerza algo en el primer arranque. |
| Mylar3 | `cdc94a4442` (2025-08-17) | `HTTP_HOST = '0.0.0.0'`, `HTTP_USERNAME`/`HTTP_PASSWORD = None` por defecto (`mylar/config.py`). Mismo alcance de lectura que Kapowarr. |

**Lo único que se puede afirmar con evidencia:** las tres escuchan en todas las
interfaces por defecto, y solo Sonarr —de las leídas a fondo— **obliga a decidir**
sobre la autenticación en el primer arranque. «No lo he leído» no es «no existe».

## Qué se adopta, adapta y descarta

- **Descartar** el bind por defecto de las tres (`*`/`0.0.0.0`): es la elección que el
  ADR 0004 ya rechaza.
- **Adoptar** la idea de Sonarr de que abrir **obliga a decidir, no se puede pasar por
  alto**: aquí, la pregunta del instalador no deja continuar con las opciones 2/3 sin
  contraseña.
- **Adaptar** el «aviso de salud» de Sonarr (`AllowedHostsCheck`): `/api/health` y
  `/estado` avisan si el puerto está abierto (o hay URL pública) y no hay contraseña.
- **Adoptar** su cautela con los proxies: no confiar en una IP «local» cuando hay un
  intermediario. ZascArr ya no usa la IP del cliente para decidir nada (A6), así que
  aquí no hace falta una lista de redes de confianza.
- **Descartar** el modo «sin contraseña en direcciones locales»: ZascArr es de un solo
  operador y cualquier dispositivo de la LAN debe autenticarse (ADR 0004).

## Decisiones de diseño

1. **La elección vive en el instalador y en el `.env`**, no en Ajustes. Ajustes solo
   muestra el estado. Volver a ejecutar `bootstrap.sh` permite cambiarla (idempotente,
   el valor actual es el que aparece por defecto).
2. **Una sola variable manda: `ZASCARR_BIND_ADDRESS`** (`127.0.0.1` por defecto,
   `0.0.0.0` para LAN). El compose la usa para publicar el puerto de la **aplicación**
   y la app la lee para saber si está expuesta; así no pueden contradecirse.
   **Postgres y Redis no se parametrizan nunca** (ADR 0004).
3. **Las tres opciones** se traducen así:

   | Opción | `ZASCARR_BIND_ADDRESS` | `BASE_URL` | Contraseña |
   |---|---|---|---|
   | 1. Solo esta máquina (defecto) | `127.0.0.1` | — | opcional (A6) |
   | 2. Mi red local | `0.0.0.0` | — | **obligatoria** |
   | 3. Detrás de un proxy inverso | `127.0.0.1` | `https://dominio[:puerto]` | **obligatoria** |

   En la 3 el puerto sigue en localhost porque lo expuesto es el proxy; el instalador
   pide el dominio y enseña un ejemplo de Caddy. **No instala ni configura el proxy ni
   el TLS.** La dirección admitida es **solo `https://host[:puerto]`**: sin ruta
   (ZascArr no está probado bajo un prefijo), puerto 1–65535, sin IPv6 ni credenciales,
   nombre DNS válido (o IPv4 real: `https://999.1.1.1` se rechaza). Python y Bash
   usan la misma regla y una prueba de paridad impide que diverjan.
4. **La contraseña se fija ANTES de publicar el puerto, y también al reinstalar.**
   Orden en el instalador: **parar la app si ya existe** (publique donde publique) →
   Postgres → migraciones → fijar contraseña → reconciliar `BASE_URL` → escribir la
   dirección → comprobar la configuración **efectiva** → `up -d --force-recreate zascarr`.
   Tres razones, las tres de la revisión de la PR #59: **(a)** escribir `127.0.0.1` en
   el `.env` **no cierra** el puerto de un contenedor ya creado, y cualquier fallo
   posterior (migración, build) lo dejaría abierto. Se para **siempre** que haya
   contenedor, y no solo si publica fuera de localhost, porque con un proxy el puerto
   ya está en localhost y la app sigue siendo accesible con sus ajustes antiguos: la
   parada avisa de la interrupción. Y la consulta distingue **cuatro estados**
   (`ausente`, `local`, `abierta`, `indeterminada`) en vez de un booleano: un fallo
   de Docker al consultar **no** equivale a «cerrado», y el instalador **aborta** con
   un diagnóstico en vez de seguir (`docker ps -a` + `docker inspect`, que además ven
   un contenedor parado cuyo `HostIp` reabriría el puerto al arrancar); **(b)** `up -d` no
   recrea un contenedor si Compose no ve cambios, y la app carga la contraseña al
   arrancar: **verificado en vivo, tras cambiarla seguía aceptando la antigua y
   rechazando la nueva**; con `--force-recreate`, solo vale la nueva; **(c)** no basta
   con que el orden textual del script sea correcto: se prueba además con transiciones
   (ver «Casos de prueba»). El modal de Sonarr deja una ventana abierta (gana el
   primero que llega); aquí no existe.
5. **La contraseña nunca viaja por argumentos ni por el entorno**: se lee oculta en el
   instalador y entra por **stdin** a un comando dentro de la imagen
   (`python -m zascarr.cli.seguridad`), que usa el **mismo servicio** que Ajustes. Una
   única regla de longitud (mínimo 12, aviso por debajo de 15); el instalador la
   comprueba antes de empezar solo para no fallar tarde, y una prueba impide que las
   dos constantes diverjan.
6. **Sin terminal interactiva** (`curl … | sudo bash`) **no se pregunta**: se mantiene
   la opción que ya hubiera (leída del `.env` y de la `BASE_URL` efectiva) y, si no hay
   ninguna, la 1. Nunca se abre sin poder pedir contraseña: si lo que había era una
   opción abierta y no hay terminal para exigirla, solo continúa abierta si **ya hay una
   contraseña**; si no, vuelve a «solo esta máquina».
7. **`0.0.0.0`, no una IP concreta**: una IP de DHCP que cambia rompería el arranque
   del contenedor. A cambio, el instalador **no puede garantizar** que el router no
   reenvíe el puerto; lo dice en el aviso final. El cortafuegos del equipo (`ufw`) es
   asunto aparte (A10): el instalador solo imprime la regla sugerida, **no la aplica**.
   La subred de esa regla **se lee del sistema** (`ip route`), no se deduce de la IP:
   `192.168.1.149` no está siempre en un `/24`. Si no se puede saber, no se propone
   ninguna regla y se dice.
8. **`BASE_URL` tiene dos dueños** (el `.env` y Ajustes; manda Ajustes). El instalador
   deja **una sola fuente de verdad**: la del `.env`, y retira de Ajustes la dirección
   pública que ya no se usa (`retirar-base-url`); el resumen final cuenta la
   configuración **efectiva** (`efectiva`), no lo que se escribió en el `.env`.
   Qué se limpia lo decide el criterio **de la app** (`base_url_publica`, laxo:
   `http://`, subrutas…), **no** el validador estricto de entradas nuevas: una
   dirección histórica que hoy no se aceptaría seguiría siendo pública para la app.
   Ojo: retirarla de ZascArr **no desactiva el proxy** que el operador ya hubiera
   configurado; ese proxy sigue existiendo y apuntando al puerto 8000.
9. **Salud técnica y aviso de seguridad van separados.** `/api/health` conserva
   `status=healthy` (observacional, igual que la VPN) y añade un bloque
   `seguridad: {exposicion, contrasena, atencion}`; una futura interfaz podrá pintar
   «Atención» sin confundirlo con un servicio caído.
10. **Encaje con A1 («3 preguntas, nada más»):** se añade una cuarta pregunta, pero
   **con valor por defecto seguro** (Intro = solo esta máquina). Las preguntas de
   contraseña y dominio solo aparecen si se opta por abrir.

## Casos de prueba (antes de implementar)

- La regla de contraseña es única: 11 caracteres se rechazan, 12 se aceptan con aviso,
  15 sin aviso; el router de Ajustes y el comando del instalador dan el mismo veredicto.
- `docker compose config` con el valor por defecto publica `127.0.0.1:8000`; con
  `ZASCARR_BIND_ADDRESS=0.0.0.0` publica `0.0.0.0:8000`; **Postgres y Redis siguen en
  `127.0.0.1` en ambos casos**.
- `/api/health` avisa (`warnings.exposicion`) si el puerto está abierto o hay `BASE_URL`
  pública **y** no hay contraseña; no avisa en el caso local ni con contraseña.
- Funciones del instalador (en `scripts/_exposicion.sh`, sin efectos): traducción
  opción → variables, validación de la URL pública (solo `https://`, con host), y la
  longitud mínima igual a la de Python.
- **Transiciones** (no solo fotos fijas), sobre un `docker` de pega con estado y, en vivo,
  sobre Postgres real: localhost→proxy, proxy→localhost, proxy A→proxy B **con un
  override previo en Ajustes**, y pública **solo en Ajustes**→cerrar; en todas, la
  configuración efectiva es la esperada y no queda un override fantasma.
- Contenedor existente → se para antes de migrar, **también con la app solo en
  localhost tras un proxy**. Estados de la consulta: `abierta` (`0.0.0.0`, IP de la LAN,
  `HostIp` vacío, mixto IPv4/IPv6), `local`, `ausente` (comprobado), `indeterminada`
  (Docker falla al listar o al leer puertos, salida ilegible → el instalador aborta).
- Dirección histórica (`http://…`, con subruta, IP de la LAN) en `.env` o en Ajustes → se
  limpia al reinstalar aunque el validador nuevo no la aceptaría.
- Cambio de contraseña con la app en marcha → tras `--force-recreate` la nueva entra y
  la antigua no.
- Los espacios de los extremos de la contraseña llegan intactos al comando (`IFS= read -rsp`).
- Subred: la que da el sistema (`/23` incluido); sin ruta, no se inventa ni se propone regla.
- En vivo contra Postgres real: el comando fija la contraseña, `estado` responde que
  hay una, y con el puerto en `0.0.0.0` una petición sin credenciales recibe el login,
  no la interfaz.

## Lo que NO resuelve (deuda declarada)

- **TLS y proxy** siguen siendo del operador; la cookie de sesión sigue sin `Secure`
  (`SECURITY.md`) y debería activarse cuando `BASE_URL` empiece por `https://`.
- No se detecta si el router reenvía el puerto a internet.
- No hay forma de cambiar la exposición desde la interfaz: por diseño, la app no
  controla su propio puerto.

## Resultado de la verificación (2026-10-01, ampliado tras la revisión de la PR #59)

Todo lo de «Casos de prueba» se escribió antes y pasa. Además, en vivo contra Docker y
Postgres reales (no contra dobles):

| Configuración | Escuchan | Desde la IP de la LAN |
|---|---|---|
| Por defecto | `127.0.0.1:8000`, `:5432`, `:6379` | sin conexión |
| `ZASCARR_BIND_ADDRESS=0.0.0.0` + contraseña | `0.0.0.0:8000` (solo la app); Postgres y Redis siguen en `127.0.0.1` | `/ui/` y `/ui/biblioteca` → `303` a `/login` |
| Abierto y **sin** contraseña | igual | `/api/health` trae `warnings.exposicion` |
| `BASE_URL` pública y sin contraseña | `127.0.0.1` | aviso de «dirección pública» |

La verificación en vivo encontró **dos fallos que las pruebas unitarias no veían**:
`docker compose run -T` consume la entrada estándar aunque el comando no la use (la
contraseña llegaba vacía), y la validación de URL de Python era más laxa que la de Bash
(`https://a b.org`). Ver las notas de A11 en `docs/BACKLOG.md`.

Tras la revisión, en vivo y con la imagen reconstruida:

| Escenario | Resultado |
|---|---|
| localhost → proxy | efectiva `proxy`, `.env` y Ajustes coinciden |
| proxy → localhost | efectiva `local`, sin dirección pública fantasma |
| proxy A (override en Ajustes) → proxy B | efectiva `b.ejemplo.org` (sin retirar el override seguía `a`) |
| pública solo en Ajustes → quitar la dirección | detectada como `proxy`, retirada, efectiva `local` |
| Dirección histórica `http://…` / con subruta / IP de la LAN | detectada como pública y retirada (antes la ignoraba el validador nuevo) |
| Estado de publicación (Docker real) | sin contenedor `ausente`; `127.0.0.1` `local`; `0.0.0.0` `abierta` (también parado); Docker inaccesible `indeterminada` |
| Contenedor ya abierto (`0.0.0.0`) | detectado, parado; la IP de la LAN deja de responder |
| Cambio de contraseña con la app en marcha | sin recrear: acepta la vieja; con `--force-recreate`: solo la nueva |
