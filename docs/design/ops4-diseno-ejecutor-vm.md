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
`query-block=[]`, y aceptó `quit`. No arrancó ningún sistema invitado. No se
ha probado la imagen de SO, red de aprovisionamiento, snapshots ni el stack
completo. Ninguna VM existente se ha iniciado o modificado.

La [guía oficial de Debian](https://www.debian.org/CD/verify.es.html) describe
sumas firmadas para imágenes de instalación. `gpgv` está instalado, pero no se
ha identificado una clave de firma CD local de confianza ni se ha verificado
una imagen. Una ISO netinst puede requerir red y no demuestra un laboratorio
completo offline. Deben decidirse imagen, cadena de confianza y aprovisionamiento
antes de iniciar la instalación; no se asumirá que la red de QEMU por defecto
impide acceso a la LAN. Hay recursos aparentes, sin garantías de cuota real.
Sin VM y stack preparados, las pruebas de host siguen **NOT RUN**.

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
