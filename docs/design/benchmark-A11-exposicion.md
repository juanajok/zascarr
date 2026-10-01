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
   | 3. Detrás de un proxy inverso | `127.0.0.1` | `https://dominio` | **obligatoria** |

   En la 3 el puerto sigue en localhost porque lo expuesto es el proxy; el instalador
   pide el dominio, exige `https://` y enseña un ejemplo de Caddy. **No instala ni
   configura el proxy ni el TLS.**
4. **La contraseña se fija ANTES de publicar el puerto.** Orden en el instalador:
   Postgres → migraciones → fijar contraseña → `up -d zascarr`. Así no existe ni un
   instante con el puerto abierto y sin contraseña (el modal de Sonarr deja una
   ventana: gana el primero que llega).
5. **La contraseña nunca viaja por argumentos ni por el entorno**: se lee oculta en el
   instalador y entra por **stdin** a un comando dentro de la imagen
   (`python -m zascarr.cli.seguridad`), que usa el **mismo servicio** que Ajustes. Una
   única regla de longitud (mínimo 12, aviso por debajo de 15); el instalador la
   comprueba antes de empezar solo para no fallar tarde, y una prueba impide que las
   dos constantes diverjan.
6. **Sin terminal interactiva** (`curl … | sudo bash`) **no se pregunta**: queda en la
   opción 1 y se explica cómo abrir después. Nunca se abre sin poder pedir contraseña.
7. **`0.0.0.0`, no una IP concreta**: una IP de DHCP que cambia rompería el arranque
   del contenedor. A cambio, el instalador **no puede garantizar** que el router no
   reenvíe el puerto; lo dice en el aviso final. El cortafuegos del equipo (`ufw`) es
   asunto aparte (A10): el instalador solo imprime la regla sugerida, **no la aplica**.
8. **Encaje con A1 («3 preguntas, nada más»):** se añade una cuarta pregunta, pero
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
- En vivo contra Postgres real: el comando fija la contraseña, `estado` responde que
  hay una, y con el puerto en `0.0.0.0` una petición sin credenciales recibe el login,
  no la interfaz.

## Lo que NO resuelve (deuda declarada)

- **TLS y proxy** siguen siendo del operador; la cookie de sesión sigue sin `Secure`
  (`SECURITY.md`) y debería activarse cuando `BASE_URL` empiece por `https://`.
- No se detecta si el router reenvía el puerto a internet.
- No hay forma de cambiar la exposición desde la interfaz: por diseño, la app no
  controla su propio puerto.
