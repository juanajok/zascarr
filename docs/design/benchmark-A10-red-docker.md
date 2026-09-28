# Ficha de benchmarking — A10: diagnóstico de la red Docker/UFW

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). El riesgo
> no es detectar «falta una regla»: es **imprimir un comando que parece preciso
> y no arregla nada** porque apunta a otra subred o a otra interfaz.

**Historia / problema observado:**
A10 — un coleccionista con `ufw` activo (ya protege el resto de la suite *arr
con reglas «solo LAN») ve que «Probar conexión» falla para Prowlarr,
Transmission y aMule **sin más pista**, y acaba descubriendo a mano con
`ss`/`iptables` que el puente de Docker no encaja en ninguna subred permitida.
El backlog pide que el instalador (o el arranque) lo detecte y dé el comando
exacto.

**Datos reales y medición de partida:**
Caso real cerrado a mano en producción el 2026-09-25 (registrado en
`CHANGELOG.md` y en las notas de D11 del BACKLOG). No fue una causa, fueron
**tres**, descartadas/confirmadas en orden con datos del usuario:

1. **Descartada:** el servicio escuchando solo en `127.0.0.1`. `ss -tlnp` los
   mostró en `0.0.0.0`/`*`.
2. **Confirmada y no suficiente:** `ufw` con reglas «solo LAN». El usuario
   aplicó `ufw allow from 172.17.0.0/16 …` y **el fallo persistió**.
3. **Causa real:** `host.docker.internal` resolvía a la puerta de enlace del
   puente **por defecto** (`docker0`, `172.17.0.1`) en vez de a la de la red
   **personalizada** que el contenedor usa de verdad (`172.18.0.1`, creada por
   `docker-compose`). La regla de ufw, correcta en sí, apuntaba a una red que el
   contenedor **ni usaba**. Corregido en `docker-entrypoint.sh`, que reescribe
   `/etc/hosts` con la puerta de enlace real leída de `/proc/net/route`.

**Verificación propia en sandbox (2026-09-28), antes de diseñar nada:**
reproducido con una red de usuario y `--add-host=host.docker.internal:host-gateway`:

```text
red zascarr-diag-test   subred 172.18.0.0/16   gateway 172.18.0.1
com.docker.network.bridge.name = <vacío>
interfaz real del puente        = br-089a55cef040   (= "br-" + 12 hex del id)
DENTRO del contenedor: host.docker.internal -> 172.17.0.1   ← la causa real, reproducida
puerta de enlace REAL de su red             -> 172.18.0.1
```

Dos hechos que cambian el diseño: la interfaz **no** viene en
`com.docker.network.bridge.name` (hay que derivarla del id, y cambia si Docker
recrea la red), y `ufw status` **exige root** (`ERROR: Debe ser root…`, salida 1
en `ufw 0.36.2`), así que un diagnóstico que no sea root no puede leer el
estado y debe decirlo en vez de interpretarlo mal.

**Referencias consultadas (URL, versión/commit):**

- **`ufw(8)`**, Debian bookworm, **ufw 0.36.2-1** —
  <https://manpages.debian.org/bookworm/ufw/ufw.8.en.html>. Hechos que se usan
  en el diseño, citados de ahí:
  - «By default, **ufw** will apply rules to all available interfaces. To limit
    this, specify DIRECTION **on** INTERFACE» → una regla **sin `on`** aplica a
    todas, que es justo lo que queremos mientras la interfaz del puente pueda
    cambiar. **Decisión: no se propone `on br-…`.**
  - «'Anywhere' is synonymous with 'any', 0.0.0.0/0 (IPv4) and ::/0 (IPv6)» →
    el parseo de `ufw status` tiene que tratar `Anywhere` como «cualquier
    origen», no como texto literal.
  - Ejemplo oficial `ufw allow from 172.16.0.0/12` («Allow all access from
    RFC1918 networks to this host») y sintaxis completa `ufw deny proto tcp from
    10.0.0.0/8 to 192.168.0.1 port 25`.
  - «Rule ordering is important and the first match wins» → una regla nueva se
    **añade al final**: si antes hay un DENY/REJECT que case, la propuesta no
    serviría. Hay que mirarlo, no solo contar ALLOWs.
- **Docker — Bridge network driver**, <https://docs.docker.com/engine/network/drivers/bridge/>
  (consultada; la página devolvió solo el encabezado, así que **los datos de
  subred/gateway/interfaz que usa esta ficha son de la reproducción propia en
  sandbox**, no de la documentación).
- **Registro del propio proyecto**, que para esta historia es evidencia de
  primera mano y no una referencia externa: `CHANGELOG.md` (v1.4.2 y v1.4.3) y
  las notas de D11 en `docs/BACKLOG.md`. De ahí sale la regla amplia
  `172.16.0.0/12` que el proyecto adoptó entonces, que es **exactamente** el
  ejemplo RFC1918 del manual de ufw.
- **Búsqueda web no disponible** en este entorno (el endpoint de búsqueda
  devuelve error de configuración); no se pudieron consultar las wikis de
  LinuxServer.io ni de Sonarr/Radarr, que son donde vive la convención de
  `ufw allow from <subred docker>` para el ecosistema *arr. Se sustituye por el
  manual de `ufw` y por medición propia, y se deja dicho aquí.

**Cómo lo resuelve cada una:**

- **La convención del ecosistema *arr (no verificada en su fuente):** recomendar
  `ufw allow from 172.16.0.0/12 to any port <puerto>`. Es lo que ZascArr ya dice
  hoy en `/ui/ajustes`. Es una regla **amplia a propósito** (todo el rango de
  Docker) para no depender de qué subred tocó.
- **`ufw`:** no sabe nada de Docker. Aplica la política por defecto al tráfico
  **entrante al host**, que es exactamente el caso contenedor→servicio del host.
  No hay «modo Docker» que activar.
- **Docker:** asigna la subred por IPAM (por defecto de sus pools, p. ej.
  `172.18.0.0/16` para una red de usuario) y crea un puente por red
  (`br-<12 hex del id>`), distinto del `docker0` por defecto.

**Supuestos de su modelo que NO valen en ZascArr:**

- **Que la subred de Docker es `172.17.0.0/16`.** Es la de `docker0`; la red de
  Compose es **otra** y tiene otra puerta de enlace. Ésta es la causa real del
  caso cerrado, y una regla para la subred equivocada no arregla nada.
- **Que el nombre de la interfaz se puede fijar.** Depende del id de la red, que
  cambia si Docker la recrea. Una regla con `on br-…` caduca sola.
- **Que basta con contar ALLOWs.** `ufw` es *first match wins* y las reglas
  nuevas van al final.
- **Que el problema es siempre el cortafuegos.** Puede ser el recorrido
  (`host.docker.internal` resolviendo a la red equivocada), o que el servicio
  apunte a `127.0.0.1` —que dentro del contenedor es el contenedor—, o a **otra
  máquina**, donde la regla de ufw de *esta* Pi no pinta nada.

**Adoptar / adaptar / descartar, con motivo:**

- **Adoptar:** el `ufw allow from <subred> to any port <puerto> proto tcp` del
  backlog y de la convención, **sin `on`** (el manual confirma que así aplica a
  todas las interfaces, que es lo robusto aquí).
- **Adoptar:** determinar la subred **real** con `docker network inspect` sobre
  la red del contenedor, en vez de asumirla.
- **Adaptar:** el criterio de «¿ya está cubierto?» no es igualdad de texto sino
  **contención CIDR**, para que `172.16.0.0/12` (la regla que el proyecto ya
  recomienda) cuente como cobertura de `172.18.0.0/16` y no se proponga una
  regla redundante.
- **Adaptar:** comprobar también el **recorrido** dentro del contenedor
  (`host.docker.internal` vs. la puerta de enlace real), porque el caso real
  necesitó las dos cosas y una regla sola no lo habría arreglado.
- **Adaptar:** si una URL no apunta a `host.docker.internal`, **no** proponer
  regla: se dice por qué (otra máquina / `127.0.0.1` imposible) en vez de
  imprimir un comando inútil.
- **Descartar:** aplicar la regla automáticamente. El comando se imprime para
  que lo revise y lo pegue el coleccionista; el script **no** ejecuta `ufw`.
- **Descartar:** proponer `in on <interfaz>`: no se puede fijar un nombre que
  Docker puede cambiar, y un `on` equivocado no casa con nada.

**Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi):**

- **No mentir:** si no se puede determinar la subred, el recorrido o el estado
  de ufw (falta root, contenedor parado, ufw ausente, salida irreconocible), se
  dice **«no puedo determinarlo»** y **no se imprime ninguna regla**. Una regla
  precisa mal dirigida es peor que un «no lo sé».
- **No tocar nada:** el diagnóstico es de solo lectura. No ejecuta `ufw`, no
  cambia rutas ni montajes.
- **Coste Pi:** solo se ejecuta a mano (o al final del instalador). Son tres
  comandos de Docker y uno de `ufw`; nada periódico.
- **El comando se enseña con la subred exacta** que se ha leído, y se dice de
  dónde sale, para que el coleccionista pueda comprobarlo.

**Casos de prueba antes de implementar (entorno sintético, sin ufw real):**

1. ufw **ausente** → nada que proponer, salida 0.
2. ufw **inactivo** → nada que proponer, salida 0.
3. ufw activo, **sin** regla para el puerto → propone el `allow from <subred
   real>` con **la subred leída de Docker**, no `172.17.0.0/16`.
4. ufw activo con `172.16.0.0/12` → **cubre** `172.18.0.0/16` (contención CIDR),
   no propone nada redundante.
5. ufw activo con `172.17.0.0/16` (la subred **equivocada**, el caso real) → no
   cuenta como cobertura y propone la buena.
6. Regla con `on eth0` → **no** cuenta como cobertura (interfaz equivocada).
7. `Anywhere` como origen → **sí** cubre (el manual lo equipara a 0.0.0.0/0).
8. Recorrido roto: el contenedor resuelve `host.docker.internal` fuera de sus
   redes → se avisa con los dos valores; no se presenta la regla como la
   solución.
9. URL a **otra máquina** o a `127.0.0.1` → no se propone regla y se explica.
10. **Sin root** → «no puedo determinarlo», salida 2, sin propuesta.
11. Docker sin el contenedor arrancado → «no puedo determinarlo», salida 2.
12. **Nunca ejecuta `ufw`**: el doble de `ufw` de las pruebas registra las
    llamadas y solo puede aparecer `status`/`status numbered`.

**Decisión final / ADR:** no requiere ADR (script de diagnóstico, no
arquitectura). Entregable: `scripts/diagnostico-red.sh` (solo lectura) + el
mensaje de «Probar conexión» apuntando a él en vez de a una subred adivinada.
