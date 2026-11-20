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
