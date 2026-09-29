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

---

## Endurecimiento tras la revisión de la PR #32 (2026-09-28)

La primera implementación cumplía el criterio a medias: **seguía imprimiendo
una regla o dando por cubierto algo que sus propios datos no sostenían**. Queda
fijado como parte del contrato:

20. **Sin recorrido comprobado no hay propuesta.** Si no se puede preguntar
    dentro del contenedor a dónde resuelve `host.docker.internal`, no se imprime
    ninguna regla: sin ese dato, la regla podría apuntar a una red que el
    contenedor ni usa (se dice cómo comprobarlo y se sale con 2). Y si resuelve
    a una dirección que **no es la puerta de enlace de ninguna de sus redes**,
    el recorrido está roto y **tampoco** se propone regla — se explica la causa
    conocida y cómo reiniciar; imprimir la regla «correcta» sería un comando
    preciso que no arregla nada (se sale con 1).
21. **La subred es la del recorrido comprobado, no la primera de la lista.**
    Con varias redes se busca cuál tiene por puerta de enlace la dirección a la
    que resuelve el contenedor y se usa **su** subred. Si ninguna coincide → 20;
    si **varias comparten** esa puerta de enlace, no se puede saber a cuál
    pertenece el tráfico → indeterminado y sin propuesta.
22. **La decisión no depende del orden de las reglas, porque no se puede
    leer.** `ufw(8)` avisa de que `ufw show added` «does not show the status of
    the running firewall» y que «does not record command ordering, so an
    equivalent ordering is used». Así que:
    - **si ALGUNA regla deniega** este tráfico, no se propone un `allow` al
      final (podría quedarle por detrás) **ni se dice que ya está cubierto**
      (podría ganar la que deniega): se remite a `sudo ufw status numbered`;
    - si alguna regla que **no se entiende** podría denegarlo, no se propone
      nada;
    - solo si **ninguna** regla lo toca se propone añadir una — que es la única
      conclusión que no depende del orden: una regla al final solo se alcanza si
      ninguna otra casa.
    Además, si el número de reglas de `ufw status` y el de `ufw show added` no
    cuadra, no se puede decir qué está en vigor → se sale con 2 sin proponer.
    **Con la horquilla de IPv6:** con IPv6 habilitado (lo está por defecto) una
    misma orden aparece como **dos** reglas activas —la IPv4 y la IPv6—, así que
    `status` puede tener hasta el doble de líneas que `show added` sin que nada
    vaya mal. Se acepta esa horquilla `[N, 2N]` y se avisa de ella; comparar por
    igualdad estricta habría convertido A10 en un falso «no puedo determinarlo»
    en instalaciones perfectamente válidas.
23. **Los puertos salen de la configuración ACTIVA, no del `.env`.**
    `prowlarr_url`, `transmission_url` y `amule_url` están en la lista blanca de
    **D11**, así que Ajustes las sobrescribe en caliente (fila
    `runtime_settings` de PostgreSQL) y el `.env` puede estar desfasado: una
    regla calculada sobre el valor viejo apuntaría **al host o al puerto
    equivocados**. El diagnóstico le pide al propio contenedor que aplique los
    overrides como los aplica al arrancar (mismo código: `get_overrides()` +
    `apply_overrides()`), así que mira **lo mismo que usa la app**. Si no se
    puede leer esa configuración, **no se analiza el `.env` en su lugar**: o se
    le dan los puertos con `--puerto`, o se declara indeterminado.
24. **Protocolo y dirección de destino se interpretan, o la regla no acredita
    nada.** La sintaxis de ufw distingue `proto` y `to DIRECCIÓN`: un
    `ufw allow proto udp from … to any port 9696` **no** autoriza tráfico TCP, y
    `ufw allow from … to 192.168.1.5 port 9696` **no** autoriza el tráfico que
    va a la puerta de enlace de Docker. Un campo que no se sepa interpretar
    (un nombre de aplicación, un protocolo raro) se marca como desconocido: un
    `ALLOW` ilegible **no acredita cobertura** (y se avisa de que no se ha
    contado), y un `DENY` ilegible **impide proponer**.

