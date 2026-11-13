# ADR 0018: auxiliar del host para operaciones pedidas desde la interfaz («Hacer una copia ahora»)

- **Estado:** **Propuesto** (2026-11-13). El PO decidió fusionar BL-OPS1 entera; la aceptación del ADR
  la da el PO al fusionar. **No autoriza instalar el auxiliar en ninguna Pi**: lo instala quien opera,
  con `scripts/instalar_ops.sh`.
- **Relación:** #443 BL-OPS1, especificación `docs/design/especificacion-BL-OPS1.md` (FR-01…FR-34),
  ADR 0004 (exposición de red), ADR 0012 (credenciales del `.env`). Prepara BL-OPS2 (restaurar), que
  añadirá acciones a la misma lista cerrada.

## Contexto

La copia de seguridad la hace `scripts/backup.sh` en el host (timer de las 04:00). El contenedor de la
app no puede ni debe lanzarla: no tiene `docker.sock` ni privilegios (CLAUDE.md §3), y darle cualquiera
de los dos equivale a darle root del host. El coleccionista, sin embargo, quiere pedir una copia antes
de tocar algo, desde `/estado`, sin abrir una terminal.

## Decisión

1. **Un auxiliar en el host, activado por socket** (`zascarr-ops.socket`, `Accept=yes`): un proceso de
   solo biblioteca estándar de Python por conexión, sin residente en la Pi. Socket `root:<grupo del
   usuario de servicio>` `0660`; la app lo alcanza por un único volumen `:ro` de la carpeta `ops`.
2. **Protocolo mínimo y cerrado**: una línea JSON de ≤ 512 B con `v`, `id`, `accion`, `creada` y
   `firma` (HMAC-SHA256 con una clave de 32 bytes en `ops.key`, `0440 root:<grupo>`). Orden de
   comprobación fijo: esquema → firma → caducidad (±120 s) → repetición (`id` de un solo uso) →
   acción → frecuencia (300 s entre copias, 6 al día) → cerrojo. Respuesta con códigos de lista cerrada,
   nunca texto libre.
3. **Una sola acción, `copia`**, que el auxiliar traduce con una tabla que vive en su código a
   `systemctl start --no-block zascarr-backup.service` con entorno vacío. No ejecuta scripts ni recibe
   rutas ni argumentos.
4. **Un único cerrojo de operaciones** (`/run/zascarr-ops.lock`, `flock`, descriptor 9, código 75 si
   está ocupado) compartido por `backup.sh`, `update.sh`, `rollback.sh`, `probar_restauracion.sh` y
   `restaurar_datos.sh`. El auxiliar solo lo comprueba, en lectura.
5. **Solo `POST /ui/copias/pedir`**, sin cuerpo; nada en `/api/*`. El estado se lee de ficheros que
   escribe el host (`status.json`, `ops-status.json`, `omitida.json`, `copias.json`).
6. La unidad de instancia va endurecida (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateNetwork`,
   `RestrictAddressFamilies=AF_UNIX`, `MemoryMax=64M`, `CapabilityBoundingSet` vacío).

## Consecuencias y riesgos aceptados

- **Quien tenga el grupo puede pedir copias** (con límite de frecuencia) y saturar el socket (límite de
  ráfaga: tras él systemd lo deja en `failed` y la app muestra «No activado»). Solo afecta a la
  disponibilidad de esta función.
- **Root con acceso a systemd sigue siendo root**: el auxiliar no se presenta como frontera de
  seguridad frente a root, sino como un canal que no amplía lo que el contenedor puede hacer.
- **`CapabilityBoundingSet=` vacío no se ha comprobado en una Pi** (NOT RUN): si `systemctl start`
  fallara, se sube desde ahí. `Requires=docker.service` en la unidad de copia puede arrancar Docker; si
  no puede, la copia no empieza y la interfaz cae en «Sin noticias» a los 35 minutos.
- El reinicio vacía `/run` y con él los `id` vistos y la cola: no queda ninguna orden pendiente.
- **Instalación explícita**: `update.sh` solo refresca lo ya instalado (FR-27).

## Alternativas descartadas

- Montar `docker.sock` o dar `privileged`/`cap_add` a la app: equivale a root del host.
- Directorio de peticiones que el host lee (cola de ficheros): sin autenticación del origen, y deja
  órdenes pendientes tras un reinicio.
- SSH desde el contenedor: una credencial de shell para una sola acción.
- Un timer que sondee: latencia, consumo permanente y sin garantía de quién pidió qué.
