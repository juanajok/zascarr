# OPS4 — propuesta de ejecutor y laboratorio desechable (#443)

**Estado: PROPUESTA PARA REVISIÓN, no implementación ni autorización de activación.**
Complementa la [SPEC OPS4](especificacion-BL-OPS4.md), no sustituye sus FR ni AC.
La acción `actualizar` permanece deshabilitada en app, auxiliar y host. La
[PR #1159](https://github.com/juanajok/zascarr/pull/1159) sigue en borrador.

## 1. Decisiones de producto y límites

- La persona solicita la instalación desde la UI; **no hay actualización
  automática**. Antes de cada versión el administrador aprueba localmente, con
  `sudo`, el SHA completo `S` de `origin/main`; la UI no emite la aprobación.
- Una aprobación `A` vence exactamente 24 horas después de emitirse; solo se
  acepta antes del vencimiento. Autoriza como máximo un intento y está ligada a
  la instalación, `S`, `HEAD0`, `P`, origen/ref y nonce.
- Una migración nueva o cambio en configuración privilegiada rechaza el SHA
  completo y requiere intervención administrativa. Nunca se instala una parte
  de `S` ni se anuncia como completo un despliegue parcial.
- No hay reintento ni rollback automáticos. Una situación incierta se bloquea
  hasta reconciliación en el host y requiere una **nueva** aprobación explícita.
  La copia previa verificada no garantiza una recuperación sin pérdida.

## 2. Piezas y fronteras propuestas

1. **Emisor administrativo instalado previamente**, propiedad de root, fuera
   de la UI y del repositorio candidato. Reconoce la instalación y confirma
   explícitamente `S` completo, `HEAD0`, ref y huella de `P`. Solo publica una
   `A` si la escritura y la sincronización se han confirmado. No interpreta
   código ni configuración del candidato como autoridad.
2. **Auxiliar host** recibe una petición cerrada con id, SHA, tiempo, prueba de
   contraseña y HMAC. El HMAC identifica posesión de clave de grupo, no a la
   persona. Comprueba contraseña viva con controles de intentos, y valida `A`;
   nunca confía en un booleano de la app ni expone secretos por argv, entorno,
   estado o logs. No se reutiliza el flujo de aceptación de copia/restauración
   si su orden o compensación contradicen las garantías de OPS4.
3. **Libro de autorización root-owned**, fuera de contenedor, separado del
   estado informativo: contiene `A` y la identidad/fase durable del intento.
   Cada apertura verifica tipo, propiedad, permisos y ancestros sin seguir
   enlaces controlables; la implementación debe escoger y probar una primitiva
   por descriptores que resista sustitución concurrente. No se presupone que
   el enlace `.env` existente sea ilegítimo: se verifica su destino permitido,
   su propiedad y toda su cadena.
4. **Receptor no privilegiado y snapshot**: obtiene objetos con aislamiento
   efectivo y transporte/configuración fijos; no ejecuta checkout, hooks,
   filtros ni scripts candidatos. El host verifica árbol, modos, P y lista
   positiva completa contra `S`, sin tratar el resultado puro experimental como
   autoridad. Se requiere una entrega al ejecutor que impida sustituciones;
   aún no está decidido el mecanismo y un `chmod` no basta. SHA-1 no demuestra
   autoría ni elimina el riesgo de colisiones.
5. **Unidad y ejecutor fijos instalados previamente**, root-owned y sin
   parámetros arbitrarios; un id opaco identifica la reserva, no es autoridad
   por sí mismo. La unidad comprueba A, id, S, P y vigencia de nuevo y consume A
   durablemente antes de cualquier efecto. El protocolo concreto que evita un
   segundo arranque o una invocación directa aún requiere diseño y prueba; una
   capacidad efímera o un PID, por sí solos, no lo garantizan.
6. **Estado informativo** legible por la UI, con id, SHA, fase, resultado y
   hora, sin secretos. No concede permisos; `aceptada` significa solicitud
   admitida, nunca actualización terminada.

## 3. Orden propuesto y punto de no retorno

| Paso | Condición y efecto | Si falla |
|---|---|---|
| 0. Gate | Antes de cualquier fetch, el host verifica que la función está habilitada conforme a todas las puertas, autentica y aplica límites. Unidad invocada directamente sin autorización también deniega. | Rechazar con contador de fetch/build/start igual a cero. |
| 1. Preparar y admitir | Solo tras gate, receptor obtiene objetos aislados; se comprueban procedencia observada, tiempo fiable, identidad, P y BD. Tomar cerrojos en un orden fijo aún no definido y verificarlo con OPS1/OPS2; ocupado no pisa estado ni consume otra A. | Rechazo previo sin efectos sobre instalación ni consumo. |
| 2. Reservar | Bajo exclusión, guardar reserva `(id,S,HEAD0,P)` y sincronizar antes de pedir el arranque. | Si la escritura o sincronización es incierta, denegar y reconciliar; no declarar A libre. |
| 3. Lanzar | Tras las guardas previas, solicitar **una sola vez** la unidad fija. «Aceptada» solo significa que esas guardas pasaron y se ordenó el inicio, no que terminó; la unidad repite guardas antes de efectos. | Timeout, error o respuesta perdida pueden coexistir con unidad arrancada: no repetir, cuarentena. |
| 4. Consumir | Unidad verifica su reserva, A/P y reloj, toma el cerrojo común y persiste `consumida` antes de efectos. La caducidad se comprueba aquí; no se cancela una operación ya consumida solo por cruzar las 24 h. | Denegar efectos; resultado incierto/bloqueado si no se acredita el estado durable. |
| 5. Guardas | Reconfirmar ref `S`, fast-forward desde `HEAD0`, snapshot inmutable, P/allowlist completa, migraciones idénticas, BD compatible, árbol/protecciones/espacio. | Detener antes de backup/build/cambio; no liberar A. |
| 6. Resguardar | Crear y verificar la copia previa, registrar ancla de recuperación. | Detener antes de tocar código/BD; no afirmar que la copia garantiza restauración sin pérdida. |
| 7. Construir y arrancar | Construcción con controles host fijos y bases por digest, sin ejecutar archivos de control del candidato como root. Registrar ID de imagen inmutable. | Dejar evidencia, no reintentar ni ejecutar rollback automático. |
| 8. Confirmar | Comprobar identidad `S`/snapshot/imagen/contenedor y salud app + BD; avance de HEAD condicionado a `HEAD0`→`S`. | Si cualquier identidad o efecto es incierto: no anunciar éxito, conservar evidencias. |

Todas las guardas aplicables de FR-08 —incluidas superficie, ref,
fast-forward, BD, limpieza y protección del árbol y `.env`, credenciales y
espacio— deben evaluarse antes de la respuesta «aceptada» y repetirse en la
unidad antes del primer efecto: la reserva no elimina las carreras. El traspaso efectivo del cerrojo entre auxiliar y unidad,
su orden respecto a OPS1/OPS2 y la protección del intervalo entre procesos aún
no están diseñados; no se declara resuelta la exclusión ni se habilita la ruta.

No se presupone una transacción atómica entre Git, Docker y PostgreSQL. Los
cambios simultáneos externos de root o miembros de `docker` están fuera del
cerrojo cooperativo y obligan a detectar incoherencia o rechazar.

## 4. Durabilidad, fallo incierto y reconciliación

- Escribir temporal exclusivo en el mismo filesystem, sincronizar archivo,
  renombrar y sincronizar el directorio son **requisitos**, no prueba de
  supervivencia frente a cualquier avería física. Un `fsync` fallido después
  del rename puede dejar a la vista tanto el estado antiguo como el nuevo tras
  un corte. No se puede demostrar que el fallo quedó registrado intentando
  escribir un segundo mensaje en el mismo medio averiado.
- **Cuestión de diseño abierta, no resuelta:** qué ancla permite distinguir tras
  reinicio una aprobación antigua aparentemente libre de una transición
  incierta, y cómo se revoca una capacidad cuando el coordinador muere pero
  systemd conserva un trabajo o proceso. La hipótesis conservadora de puerta
  cerrada al arranque está en el [plan de validación](ops4-plan-validacion-aislada.md);
  exige definir identidad, entrega y consumo, no solo nombrar una capacidad.
  Hasta demostrar el mecanismo, no implementar ni habilitar la ruta productiva.
- A reservada o consumida nunca vuelve automáticamente a libre. Antes de la
  reserva durable se distingue un rechazo sin efectos de una reserva incierta;
  después de ella, cualquier estado no demostrable queda en cuarentena.
- Reconciliación: con el cerrojo apropiado, el administrador inspecciona
  unidad/trabajos y procesos, identidad del intento, HEAD, snapshot, IDs de
  imagen y contenedor, salud y revisión/estado de BD y copia. Si algo sigue en
  curso o no puede determinarse, no desbloquea. Si es necesario reparar o
  restaurar, lo hace mediante un procedimiento manual separado y verificado;
  después hace falta nueva A, nunca reutilizar la anterior.
- El reloj debe ser fiable y no retroceder; la técnica concreta de verificarlo
  entre reinicios sigue abierta. No confundir la tolerancia del mensaje HMAC
  con la vigencia de 24 horas de A.

## 5. Laboratorio: VM desechable, no Pi

**Objetivo:** Debian/Linux con systemd, Docker y PostgreSQL *dentro de la VM*,
repositorio remoto local sintético, imágenes/datos sintéticos, copia y disco
virtual propios; cero `.env`, credenciales o tebeoteca reales, sin montar el
checkout de producción ni socket Docker del host. Un nombre/prefijo dedicado
para proyecto Compose y una lista explícita de rutas del disco de pruebas son
obligatorios. El arnés debe comprobarlos antes de cada acción destructiva y
fallar cerrado ante cualquier ambigüedad. No se autoriza borrar imágenes ni
recursos fuera de ese laboratorio.

**Sondeo QEMU, no prueba de OPS4:** QEMU 10.2.1 y libvirt 12.0.0 están
presentes; `/dev/kvm` no aparece en este entorno. Se ha iniciado y terminado
QEMU con `-machine q35,accel=tcg -nodefaults -nic none -display none -S` y
128 MiB, sin discos ni imagen; QMP respondió `prelaunch`, `running=false` y
`query-block=[]`, y aceptó `quit`. Después se ejecutó QEMU durante 30 segundos
con la ISO conectada como CD de solo lectura, sin NIC ni disco escribible;
terminó por el límite de tiempo y la consola serie no produjo salida. En otro
sondeo QMP confirmó un dispositivo de bloque `ro=true` y `running=true` tras
`cont`, antes de `quit`. Un tercer sondeo, con VGA virtual y los mismos límites
sin NIC ni disco escribible, mostró en captura el **menú del instalador Debian
GNU/Linux (BIOS mode)**. QMP confirmó el único dispositivo de bloque como
solo lectura y cerró con `quit`; la captura se conserva solo en evidencia
privada. Llegar al menú no instala Debian ni prueba el runtime de OPS4. Red de
aprovisionamiento, snapshots y stack completo siguen sin probarse. Ninguna VM
existente se ha iniciado o modificado.

**Sondeo serial sin disco:** se extrajeron kernel e initrd desde la ISO y se
creó una copia del initrd con preconfiguración mínima sin red ni credenciales.
La comprobación del archivo adicional confirmó únicamente `preseed.cfg`; no se
ha probado que todos sus valores se apliquen. Con QEMU sin NIC ni disco
escribible, el kernel Debian 6.12 inició `/init` y la consola alcanzó el
instalador. Con 768 MiB mostró un diálogo de memoria baja y la ejecución se
cerró al cumplirse 150 s de pared. Con 1536 MiB llegó a examinar el CD y cargar
componentes adicionales, pero terminó con código 152 al alcanzar el límite de
100 s de CPU; **no terminó la instalación**. No se conectó el qcow2 en ninguno
de los dos casos. Los registros quedan fuera de Git. Ajustar los límites y
verificar la interacción del instalador siguen pendientes; no se acredita que
el preseed sea suficiente o que el sistema instalado arranque.

La [guía oficial de Debian](https://www.debian.org/CD/verify.es.html) describe
sumas firmadas para imágenes de instalación. Para Debian 13.7.0 amd64 se ha
verificado con `gpgv` la firma del manifiesto SHA-256 con la clave CD de huella
`DF9B9C49EAA9298432589D76DA87E80D6294BE9B`. La clave y la huella proceden de
la web oficial por HTTPS: esto confía en TLS/PKI y no constituye corroboración
por canal independiente. La imagen `debian-13.7.0-amd64-netinst.iso` se ha
comparado con el manifiesto firmado: SHA-256
`a7ef94ac2fb9a7fec454552abd629b7cc9d5155c886165a45649f5ce6167e355`,
792.723.456 bytes, `sha256sum --check` OK. Se conserva fuera de Git en un
subdirectorio privado. Se ha observado el menú inicial, no una instalación
completada. La verificación no asegura que la imagen contenga todos los paquetes
ni sustituye una fuente independiente de la
huella. Una ISO netinst puede requerir red y no demuestra un laboratorio
completo offline. Deben resolverse la confianza de la clave y el aprovisionamiento
antes de iniciar la instalación; no se asumirá que la red de QEMU por defecto
impide acceso a la LAN. Hay recursos aparentes, sin garantías de cuota real.
Sin VM y stack preparados, las pruebas de host siguen **NOT RUN**.

**Preparación del disco:** se ha creado exclusivamente para este laboratorio
un directorio privado `0700` fuera de Git y un disco qcow2 nuevo `0600`, con
12 GiB virtuales. `qemu-img info` muestra ausencia de backing file y
`qemu-img check` pasó. También se extrajeron de la ISO verificada el kernel y
el initrd del instalador a ese directorio. Posteriormente se conectó el qcow2
como único disco escribible y la ISO como CD de solo lectura a QEMU **con el
invitado detenido**; QMP confirmó ambos tipos y el estado detenido. La línea
incluía `-nodefaults -nic none`; después se cerró QEMU. No se ha particionado ni
instalado nada.

Se verificó aparte que `RLIMIT_FSIZE` de 1 MiB rechaza por `EFBIG` una escritura
adicional en un archivo sintético y se observó un límite de 15 GiB por archivo
en el proceso QEMU detenido. También se comprobó que `RLIMIT_AS` de 64 MiB
rechaza una reserva sintética de 100 MiB, y que QEMU con límites observados de
4 GiB de espacio de direcciones, 15 GiB por archivo y 120/125 segundos de CPU
alcanzó el menú de Debian con 768 MiB de RAM virtual, ISO de solo lectura y
sin NIC ni disco escribible. QMP cerró la instancia. La captura se conserva en
evidencia privada.

Estos límites son **por proceso o por archivo**, no una cuota global de disco,
no limitan otros procesos y `RLIMIT_AS` limita espacio virtual, no una cuota
agregada de RAM física. `RLIMIT_CPU` es tiempo de CPU, no un plazo de pared.
Los 12 GiB virtuales tampoco garantizan una cuota física; siguen pendientes el
límite total efectivo y el aislamiento adicional antes de la instalación.

Inspección adicional del entorno: el filesystem del laboratorio aparece como
`ntfs3`; `/sys/fs/cgroup` es cgroup2 montado de solo lectura, el bus de
`systemctl --user` no está disponible y no aparecen `/dev/fuse` ni `/dev/kvm`.
No se ha demostrado aquí un cgroup delegado ni una cuota física agregada. Una
posible vía futura es un volumen con cuota ya provisionada y un cgroup delegado,
con ensayos de `ENOSPC` y memoria; no se ha creado ninguno. Un vigilante de
`du` puede reaccionar tarde y no equivale a un límite. Además, los resultados de
fallos sobre qcow2 almacenado en NTFS no prueban durabilidad física de la Pi.

**Instalación real en la VM desechable:** se reinstaló Debian 13.7.0 amd64
en el qcow2 de pruebas con preseed, sin NIC y con la ISO como único CD. El
instalador terminó con código 0; el disco arrancó sin la ISO hasta el login
`ops4lab login:` en `ttyS0`. Se entró como usuario `ops4` y se comprobó que
PID 1 es `/sbin/init` (systemd), que existe `/run/systemd/private` y que
`systemctl --version` informa `systemd 257 (257.13-1~deb13u1)`.

El bus D-Bus del sistema no está instalado, por lo que `systemctl` sin más
falla. Usando el socket privado de systemd,
`DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/systemd/private`, la misma orden sí
responde: `systemctl is-system-running` devolvió **`running`** con código 0.
`systemd-run` transitorio siguió fallando con «Invalid request descriptor» y no
se usó.

En esa VM se creó una unidad fija de prueba `ops4-test.service` (oneshot,
`/bin/true`), se hizo `daemon-reload` y se arrancó por el socket privado:
**`Result=success`, `ExecMainStatus=0`, `inactive/dead`**. Otra unidad
`ops4-fail.service` con `/bin/false` terminó en **`Result=exit-code`,
`ExecMainStatus=1`, `failed/failed`**. Esto acredita el ciclo básico de una
unidad systemd en el laboratorio y la observación de su resultado; no acredita
el futuro ejecutor, la actualización, Docker, PostgreSQL ni un entorno de
producción.

También se creó una unidad de laboratorio `ops4-hardened.service`
(`Type=oneshot`, `ExecStart=/bin/true`) con `NoNewPrivileges=yes`,
`PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`, protección de kernel,
módulos y cgroups, `PrivateDevices`, `RestrictNamespaces`, `RestrictSUIDSGID`,
`RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`, `CapabilityBoundingSet=`
vacío y `UMask=0077`. `systemd-analyze security` informó **3.9 OK** y la unidad
arrancó con **`Result=success`, `inactive/dead`**. Es una estimación estática y
una prueba con `/bin/true`, no del futuro ejecutor; el conjunto de capacidades
puede no servir para `update.sh`/Docker y deberá revisarse. La exposición 3.9
no es una certificación de seguridad.

Los primeros intentos con una NIC de usuario de QEMU no obtuvieron IPv4:
`dhclient` falló y la configuración estática posterior falló al añadir la ruta.
**Diagnóstico corregido el 2026-11-20:** al reiniciar QEMU, la interfaz volvía a
estar apagada. El intento estático no había ejecutado `ip link set enp0s1 up`
en ese arranque; no era evidencia de que la red de QEMU estuviera inutilizable.

### Laboratorio regenerado y verificado (2026-11-20)

Se creó `lab-debian-02/disco.qcow2`, un overlay qcow2 sobre el disco Debian
anterior, sin modificar la base. Ambos están en la evidencia privada ignorada
por Git. El overlay depende de la base: no moverla ni modificarla mientras se
use el overlay. No hay carpetas compartidas, discos físicos, socket Docker del
anfitrión ni red puente. El aprovisionamiento usó una NIC de usuario de QEMU,
sin redirección de puertos; permite tráfico saliente y **no es aislamiento de
red completo**. No se usó SSH a la Pi ni datos de producción.

Dentro del invitado, como root, funcionó esta secuencia en el mismo arranque:

```sh
ip link set enp0s1 up
ip addr replace 10.0.2.15/24 dev enp0s1
ip route replace default via 10.0.2.2
printf 'nameserver 10.0.2.3\n' > /etc/resolv.conf
getent ahostsv4 deb.debian.org
```

El espejo HTTPS falló al verificar su certificado. No se desactivó TLS ni la
verificación de paquetes: se usó el espejo HTTP de Debian con autenticación de
APT por firmas del archivo, sin `trusted=yes` ni `--allow-unauthenticated`.
`apt-get -o APT::Update::Error-Mode=any update` y la instalación terminaron con
código 0. Paquetes: `docker.io`, **`docker-cli`** (el cliente es separado en
esta versión), `postgresql`, `ca-certificates`, `dbus` y `busybox-static`.
HTTP no aporta confidencialidad del transporte; la autenticidad del archivo
se mantiene mediante las firmas que APT verifica. No se diagnosticó la causa
exacta del error de certificado.

Después se arrancó **sin NIC** (`-nic none`) y se verificó:

| Comprobación real | Resultado |
| --- | --- |
| `docker version`, cliente y servidor | `26.1.5+dfsg1`, ambos responden |
| `pg_lsclusters` | PostgreSQL `17/main`, `online` |
| Consulta en base sintética `ops4_test` | PostgreSQL `17.11` |
| Crear tabla, insertar dentro de transacción y `ROLLBACK` | Recuento final `0` |
| Imagen local importada desde el BusyBox estático del invitado | Contenedor ejecutado; imprime `OPS4_CONTAINER_OK` |
| Contenedor con `--network none --read-only --cap-drop ALL` | Código `0` |
| `systemctl is-active docker postgresql` | `active`, `active` |
| Escucha PostgreSQL (`ss -lnt`) | Solo `127.0.0.1:5432` y `[::1]:5432` |
| Apagado por `poweroff` | QEMU terminó con código `0` |

Para las consultas se usaron `psql -X -P pager=off -v ON_ERROR_STOP=1` y
marcadores de salida con comprobación del código de cada comando. Un primer
intento quedó en el paginador; otro revirtió también el `CREATE TABLE` al
agruparlo en el mismo `-c`. Ambos se corrigieron y no cuentan como PASS.

La imagen local de BusyBox evita depender de Docker Hub. En este primer
ensayo PostgreSQL se ejecutó como servicio del invitado, no como contenedor;
la validación posterior del lector contra el contenedor real se detalla abajo.
Compose, la aplicación, las migraciones, la unidad y el ejecutor de
actualización, las interrupciones y el flujo completo siguen **NOT RUN**. No
se instaló la unidad de actualización ni se ejecutó `update.sh`.

Para nuevos ensayos desde la raíz de este worktree, crear **otro overlay sin
NIC**. La base ya tiene descendientes de los ensayos de corte: no arrancarla
en modo escribible ni modificarla mientras se conserven esos descendientes.
Elegir un nombre nuevo; la guarda impide sobrescribir un ensayo existente:

```sh
BASE="$(pwd)/fuera-de-zascarr/ops4-vm-evidencia/lab-debian-02/disco.qcow2"
DISCO="$(pwd)/fuera-de-zascarr/ops4-vm-evidencia/nuevo-ensayo.qcow2"
test ! -e "$DISCO" &&
qemu-img create -f qcow2 -F qcow2 -b "$BASE" "$DISCO" &&
qemu-system-x86_64 -machine q35,accel=tcg -m 2048 -smp 2 \
  -nodefaults -no-user-config -nic none -display none \
  -serial stdio -monitor none -no-reboot \
  -drive "file=$DISCO,if=virtio,format=qcow2"
```

No ejecutar dos instancias sobre el mismo disco. No conectar discos de
producción ni el socket Docker del anfitrión. La cuenta `ops4` conserva una
contraseña sintética de laboratorio en la evidencia privada: no sirve para
producción y no se publica en Git. Para controlar servicios desde la consola
root se conserva la receta `DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/systemd/private`.

El laboratorio regenerado queda apagado, con disco persistente para nuevas
pruebas. Registros privados: `lab-debian-02/serial.log`, `aprovisionar.log`,
`verificar-servicios.log` y `verificar-offline.log`, bajo el directorio de
evidencia ignorado por Git. Estos ensayos no prueban durabilidad física de la
Pi ni eliminan las limitaciones de cuota/cgroups indicadas arriba.

### Lector real contra PostgreSQL en Docker (2026-11-20)

Se añadió Python 3 al invitado mediante APT autenticado y se importó una
imagen local `ops4-debian:lab` a partir de los binarios, bibliotecas y
configuración **sintética** de ese invitado, sin descargar una imagen de
Docker Hub. Su ID local fue
`sha256:97f8bcee317d54f4f442ffae518ef04a5075d575eb25170ca401c58a6d24d1d6`;
no es un digest de imagen publicada ni una certificación de procedencia.

Se reinició QEMU con `-nic none`. Dentro de la VM se detuvo PostgreSQL nativo
antes de montar su directorio de datos sintéticos en el contenedor (nunca dos
servidores sobre el mismo directorio). Se ejecutó:

```sh
docker run -d --name zascarr-db --network none --read-only --cap-drop ALL \
  --user postgres --tmpfs /tmp:rw,mode=1777 \
  --tmpfs /var/run/postgresql:rw,mode=1777 \
  -v /var/lib/postgresql/17/main:/var/lib/postgresql/17/main \
  ops4-debian:lab /usr/lib/postgresql/17/bin/postgres \
  -D /var/lib/postgresql/17/main \
  -c config_file=/etc/postgresql/17/main/postgresql.conf \
  -c ssl=off -c listen_addresses= \
  -c unix_socket_directories=/var/run/postgresql
```

La carpeta montada pertenece al **invitado**, no al anfitrión ni a la Pi.
PostgreSQL no escucha TCP: se usa el socket Unix dentro del contenedor.
`docker inspect` confirmó `network=none readonly=true user=postgres`.

Se transfirieron por consola serie los módulos de
[lector](../../deploy/ops/lector_credenciales_ops4.py) y
[verificación](../../deploy/ops/prueba_viva_ops4.py) del commit `2b507790`, sin
modificarlos. Se creó una tabla mínima sintética `runtime_settings` (`id`,
`values` JSONB) en `ops4_test`. El lector usó su ejecutor **por defecto**, no
un doble: `/usr/bin/docker exec zascarr-db psql`, con usuario `postgres` y
base `ops4_test` configurados en su constructor. Resultados comprobados con
aserciones dentro de la VM:

- **PASS:** lectura exacta del modo/hash sintéticos, contraseña correcta
  aceptada y contraseña incorrecta denegada.
- **PASS:** tras cambiar el hash en SQL, el lector ve el nuevo valor; la
  contraseña anterior deja de valer y la nueva coincide, sin caché.
- **PASS:** un hash de 5000 caracteres en la BD hace que el lector devuelva
  `None` por exceso de salida.
- **PASS:** tras detener el contenedor, el lector devuelve `None` y la prueba
  viva deniega.

El caso terminó con código 0; se comprobó la configuración del contenedor,
se dejó detenido y se arrancó nuevamente PostgreSQL nativo. QEMU se apagó
limpiamente (código 0). El registro privado `lector-verificar.log` tiene
SHA-256 `29123ae0d788bf930fce631013bd0d09a818e5e1ff8e1727c7e3ba4cfa9c1cd5`.
Los controladores y el caso sintético están en la evidencia privada, fuera de
Git; no contienen credenciales de producción.

**Límites:** esquema mínimo, sin migraciones Alembic ni app real, imagen
local de laboratorio (no imagen oficial de PostgreSQL), credenciales y
usuario distintos de producción. No demuestra identidad autorizada de host,
contenedor o base, concordancia de `auth_mode` con la app, reclamación
durable, cerrojo, unidad actualizadora ni cancelación de consultas remotas.
La actualización sigue deshabilitada.

### Timeout y contención por cgroup en la VM (2026-11-20)

Se instalaron **solo dentro de la VM sin NIC** los fixtures versionados de
[unidad de sondeo](../../tests/fixtures/ops4-vm/ops4-lab-timeout.service),
[proceso sintético](../../tests/fixtures/ops4-vm/timeout-probe.py) y
[verificador](../../tests/fixtures/ops4-vm/verify-timeout.py). No son la unidad
actualizadora ni están incluidos en el instalador de OPS.

La unidad usa `Type=exec`, `RuntimeMaxSec=2s`, `TimeoutStopSec=1s`,
`KillMode=control-group`, `SendSIGKILL=yes` y `Restart=no`; corre como
`nobody:nogroup`, sin capacidades, con `ProtectSystem=strict` y otras
restricciones. El proceso padre y su hijo ignoran SIGTERM; el hijo invoca
`setsid()` y registra su nueva sesión en el directorio de runtime. No llaman a
Docker, a la app, a la BD ni a la red.

**Resultado real:** `Result=timeout`, `ExecMainStatus=9`,
`ActiveState=failed`, `SubState=failed`, `NRestarts=0`. El verificador comprobó
que el hijo sí creó otra sesión y que ninguno de los dos procesos seguía
activo (ausente o zombi, no ejecutable). El caso terminó con código 0. La
unidad no tiene sección `[Install]`; se limpió el estado fallido y QEMU se
apagó limpiamente. Evidencia privada: `lector-timeout-v2.log`.

Un primer intento con `systemctl start --wait` falló por «Invalid request
descriptor» sobre el socket privado. No cuenta como PASS. Se sustituyó por
`start` normal y observación acotada de propiedades hasta el estado fallido;
`start=0` no se interpreta como éxito del trabajo.

**Consecuencia para el diseño:** `RuntimeMaxSec` no limita la fase activa de
`Type=oneshot`; una futura unidad de ese tipo necesitará `TimeoutStartSec`
explícito. El sondeo usa `Type=exec` deliberadamente. La unidad final sigue
pendiente de revisión: no copiar estas restricciones a `update.sh`/Docker
sin verificar permisos, red y directorios escribibles. El cgroup de esta
unidad no contiene tareas ya delegadas al daemon Docker; tampoco demuestra
reclamación durable, recuperación ni estado fiable tras cortes.

Los [tests estáticos](../../tests/test_ops4_unidad_laboratorio.py) fijan el
contrato `Type=exec`/timeout/cgroup/sin reinicio, comprueban que importar los
fixtures no ejecuta procesos y que el instalador no los referencia. Pytest no
instala ni ejecuta unidades systemd.

También se realizaron [tres cortes abruptos del registro antirrepetición](ops4-registro-repeticiones.md#tres-cortes-abruptos-de-vm-2026-11-20)
en overlays independientes, antes/después de sus sincronizaciones. Ninguno
inició una actualización. Las marcas confirmadas sobrevivieron; esto no
simula pérdida eléctrica del anfitrión ni acredita recuperación del ejecutor.

**Plan de aprovisionamiento offline, aún no ejecutado:**

1. La [guía de instalación Debian](https://www.debian.org/releases/trixie/amd64/apas02.en.html)
   indica que netinst incluye paquetes para un sistema mínimo, pero está
   orientada a obtener paquetes adicionales por red; el primer DVD permite una
   instalación sin red con mayor selección. Ninguna de las dos opciones prueba
   por sí sola disponibilidad de Docker, PostgreSQL o los artefactos de ZascArr.
2. Seleccionar una versión e imagen **inmutables**, obtener suma y firma
   oficiales, validar la identidad de la clave y luego la firma del manifiesto
   y la suma exacta de la imagen. La huella obtenida de la web oficial mediante
   HTTPS depende de la confianza en TLS y ese sitio; no es corroboración por
   canal independiente. Sin una cadena de confianza aceptable, no afirmar que
   la imagen está autenticada ni arrancarla para estas pruebas.
3. Preparar fuera del invitado los paquetes y dependencias necesarios para la
   arquitectura y versiones exactas, y las imágenes de contenedor por digest;
   trasladarlos mediante medio dedicado de solo lectura. No copiar `.env`,
   credenciales, datos o imágenes privadas de producción. Documentar de forma
   separada cómo se autentican los paquetes y las imágenes. En el invitado,
   Docker puede necesitar una red interna para app y BD; `--network none` en
   cada contenedor no permitiría esa comunicación.
4. El instalador [acepta preconfiguración](https://www.debian.org/releases/trixie/amd64/apbs02.en.html)
   desde initrd o medios especificados; no asumir que cualquier segundo CD se
   monta automáticamente en `/cdrom`. El [ejemplo oficial](https://www.debian.org/releases/trixie/amd64/apbs04.en.html)
   permite desactivar red y espejo, pero advierte que el nombre de los discos
   depende de la detección y que el particionado automático puede borrar el
   disco elegido. No automatizarlo hasta demostrar que solo aparece un disco
   virtual recién creado y comprobar su identidad.
5. El sondeo de arranque usaría QEMU sin NIC ni dispositivos compartidos con
   el invitado, sin socket Docker del host, con límites y directorio dedicado;
   un fichero qcow2 disperso con tamaño virtual limitado no garantiza por sí
   solo una cuota física. Una protección adicional por namespaces es deseable,
   pero el último intento de comprobarla **no llegó a ejecutar `bwrap`**: el
   propio backend sandbox de la herramienta rechazó la operación al no poder
   crear namespaces no privilegiados. No se ha verificado que el aislamiento
   adicional funcione y no se eludirá esa protección. Ni QEMU ni namespaces
   equivalen a aislamiento perfecto frente a fallos del kernel o hipervisor.

### Matriz mínima de interrupciones y oráculos

- Inyectar barreras deterministas y cortar antes/después de cada escritura,
  sincronización de fichero, renombrado y sincronización de directorio de A y
  reserva. Probar tanto recuperación del nombre anterior como del nuevo cuando
  corresponda; no simular `fsync` exitoso como garantía de hardware.
- Cortar antes y después de pedir `start`, perder su respuesta, o devolver
  código no cero aunque la unidad haya arrancado. Tras reinicio: **cero
  segundo lanzamiento automático**, A anterior no reutilizable, UI no anuncia
  éxito, y estado `no iniciada`/`incierta`/`parcial` solo si está acreditado.
- Dos solicitudes simultáneas y colisión con copia/restauración: como máximo
  una reserva y un inicio; ocupado no destruye la aprobación o estado de otro.
- Si `origin/main` cambia **antes de la reconfirmación**, rechazar; si cambia
  después, usar solo S aprobado o detener. Si la alteración de HEAD, snapshot/P
  o BD se detecta antes de build, no construir ni avanzar; si se detecta durante
  o después, detener efectos posteriores, no anunciar éxito y poner en
  cuarentena si hay incertidumbre, sin negar efectos ya ocurridos.
- Control positivo: S ordinario permitido, P fijo y BD compatible: verificar
  árbol y SHA, ID de imagen, contenedor efectivo y health de app/BD. Aprobación
  y código candidato no son sinónimos de seguridad.
- Reconciliación: unidad activa, salida perdida o HEAD/imagen/BD dispares ⇒
  mantener cuarentena. Si la fase había completado la copia, verificar su
  existencia; antes de esa fase no inventar una copia. Nueva aprobación solo
  después de inspección y, si procede, reparación manual explícitas.

### Trazabilidad mínima para la futura suite

Todos los renglones están **NOT RUN**; deben tener fixture, estímulo, contador
independiente de efectos y controles positivo/negativo cuando corresponda.

| Criterio | Oráculo pendiente en laboratorio |
|---|---|
| AC-01 | Gate o unidad directa sin puertas: cero fetch, backup, build y start; sin botón UI. |
| AC-02 | Ref cambia antes de reconfirmar o remoto cae: rechazo; nunca instalar T. |
| AC-03 | A ausente, alterada, consumida, de otro host/HEAD0/P, SHA abreviado, enlace o ruta escribible: auxiliar y unidad directa rechazan; ensayar sustitución concurrente de ancestros. |
| AC-04–05 | Con A y HMAC válidos, contraseña incorrecta, modo none, hash ilegible o BD caída rechazan; actor con HMAC y contraseña sin A también rechaza. Control positivo con A y contraseña válidas. Buscar centinelas en logs, argv, entorno, HTTP y estado. |
| AC-06 | Barreras en ref/snapshot/HEAD: identidad exacta S o detención, sin mezclar árboles. |
| AC-07 | Repo hostil con hook/filtro/helper e indicador de ejecución: ignorados en control positivo; altas, bajas, renombres y modos de cada clase P rechazados antes de efectos. |
| AC-08 | N peticiones con una misma A e ids distintos, junto con copia/restauración: máximo una reserva/inicio, sin pisar estado. |
| AC-09 | Caídas y fallos de escritura/rename/fsync en aprobación y estado, antes/después de efectos; no reutilizar A ni reintentar. |
| AC-10 | Comparar de fuentes independientes HEAD/snapshot, ID de imagen, contenedor, BD y ambos health; alterar por separado tag, LABEL y JSON no basta. |
| AC-11 | Esquemas, duplicados, límites, HMAC/replay/caducidad y secretos; paridad de v1/v2 y cero efectos en solicitudes inválidas. |
| AC-12 | Migración o revisión distinta: rechazo previo a backup/build/avance; sin ejecutar upgrade. |
| AC-13 | Control positivo completo de código ordinario permitido y P fijo, con BD compatible y ejecución root solo de controles previamente instalados. |
| AC-14 | Emisión local con sudo y confirmación exacta del SHA; sin sudo, sin confirmación, desde UI o desde auxiliar no se emite A. |
| AC-15 | Frontera 24 h menos una unidad, exacta y posterior; reloj retrocedido; expira antes/después de consumo; simultaneidad, corte y reconciliación con nueva A. |

El laboratorio debe denegar egress durante ensayos, usar remoto Git local,
retirar credenciales y agent forwarding, y no compartir directorios ni socket
Docker con el host. Los límites del build, los artefactos instalados y el acceso
del candidato a red/secretos deben ensayarse con centinelas; un contenedor no
es prueba de aislamiento perfecto. Limpieza solo tras verificar identidad de
VM, disco y proyecto. Un reboot limpio, snapshot de VM o fallo inyectado no
prueban por sí solos durabilidad ante pérdida física de energía.

La matriz no sustituye el texto de AC-01…AC-15 ni la revisión de QA. Cada
resultado se registra como PASS/FAIL/NOT RUN con escenario y artefacto; una
simulación no es evidencia de un corte físico real.

## 6. Puertas pendientes

Dos revisiones independientes de seguridad y QA del borrador identificaron
problemas de gate antes del fetch, orden de guardas, cronología de efectos y
oráculos de aceptación. Se han incorporado sus correcciones al texto. **No son
un dictamen formal ni aprueban un SHA de implementación**; no se han ejecutado
los AC en VM.

Permanecen abiertos: ancla durable tras `fsync` incierto,
capacidad y llamada directa a unidad, origen/ref e identidad de imagen,
reloj, orden de cerrojos, completitud de P, anclaje/entrega del snapshot y
operación segura de HEAD. `S == HEAD0` se mantiene **sin decisión**; no se
inventa éxito. Ninguna puerta se considera satisfecha por esta propuesta.
