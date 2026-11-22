# ADR 0026 — Actualización manual desde la UI confiando en `main` (#443, historia B)

## Decisión

El propietario del producto sustituye la aprobación individual por SHA de C-12
por una actualización manual desde la interfaz que instala `origin/main` y
aplica migraciones. No hay actualización programada, aprobación root por SHA
ni rollback automático.

La acción es **fija**: un servicio de host separado ejecuta solo
`scripts/update.sh --rama main`; la petición web no elige rama, remoto, ruta,
entorno, opciones ni comandos. La UI exige sesión, origen/CSRF y reautenticación
con la contraseña actual. La app emite un testigo HMAC corto y de un solo uso,
ligado a la operación y a un ID; el host comprueba firma, frescura, ID y
consumo durable antes de arrancar la unidad. La contraseña no viaja al host.

## Autoridad y riesgo residual

La autoridad de autenticación es **la app**: el host no relee el hash ni la
base de datos para esta ruta. El testigo y la firma usan la misma clave
dedicada, y la app la lee para poder emitir el testigo. Por tanto, cualquier
código del contenedor o proceso del grupo con acceso a la clave puede fabricar
una petición válida sin contraseña. Lo que acota el daño es la acción fija, el
socket/clave restringidos, el consumo único y el cerrojo de operaciones; no es
una garantía de identidad humana verificada por el host. Esta desviación de la
propuesta inicial queda aceptada solo mientras la función esté deshabilitada y
hasta que una revisión de seguridad decida separar claves o endurecer el
binding del socket.

## Consecuencias

- Confiar en `main` incluye confiar en scripts, Compose, Dockerfile,
  dependencias y migraciones; el SHA identifica contenido, no autoría.
- La actualización puede requerir copia, migraciones y reinicio; no hay vuelta
  atrás automática.
- La unidad de actualización necesita escribir en el repo, datos, copias y
  rutas de refresco de auxiliares. El sandbox y el estado durable son
  condiciones de habilitación, no detalles opcionales.
- La UI no debe prometer éxito mientras no exista un estado durable que el
  host escriba y la app lea; una respuesta perdida o un `start` ambiguo no
  autorizan reintento ciego.
- No se habilita ni despliega por este ADR. La función sigue apagada por
  defecto y requiere autorización explícita y cerrar las condiciones CE de
  SecOps.

## Referencias

- [Especificación main](../design/ops4-especificacion-main.md)
- [Autorización app-host](../design/ops4-autorizacion-app-host.md)
- [Auxiliar y unidad](../design/ops4-auxiliar-unidad.md)
- [Informe SecOps final](../design/secops-ops4-b-final-f34c30ba-2026-11-22.md)


## Desviación de Compose

`docker-compose.yml` pasa `OPS4_ACTUALIZACION_HABILITADA` (default `false`),
`OPS4_AUTORIZACION_KEY_FILE` y `OPS4_SOCKET_FILE`/`OPS4_ESTADO_FILE`. No activa
nada por sí mismo: sin clave, socket y unidades la ruta responde 404 o
`no_disponible`; el socket solo lo arranca root con el instalador.
