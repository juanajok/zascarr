# Tooling SDD (propuesta)

Este directorio propone fijar OpenSpec 2.2.0 para desarrollo, sin incorporarlo al
runtime ni a la imagen de la aplicación. No activa gates ni supone que H0 haya
terminado o que se apruebe la adopción. La evidencia y sus límites están en
`openspec/changes/sdd-001/h0-evidencia.md`: quedan pendientes la revisión de
licencias y suministro, la reproducibilidad en otras plataformas y la carga
real de instrucciones en los harnesses; las comprobaciones de tráfico no
constituyen aislamiento de red.

Para reproducir el entorno explorado se requieren Node 24.22.3 y npm 11.19.1.
Tras revisar el lock propuesto, instalar desde este directorio con
`npm ci --ignore-scripts --no-audit --no-fund` y ejecutar el binario local
`node_modules/.bin/openspec`, no `npx`. Usar `DO_NOT_TRACK=1` y
`OPENSPEC_TELEMETRY=0` no garantiza ausencia universal de tráfico. La
instalación puede acceder al registro npm y desactivar scripts de instalación
no impide que la CLI ejecute código después. `--no-audit` omite la auditoría
npm automática: revisar suministro, vulnerabilidades y licencias por el proceso
aprobado antes de adoptar el lock; no se declara una auditoría superada.

`engines` documenta las versiones probadas, pero npm puede limitarse a avisar;
comprueba explícitamente `node --version` y `npm --version` antes de instalar.
Al procesar una PR o contenido no confiable, usa un entorno desechable sin
credenciales ni acceso al directorio personal y, cuando deba trabajar sin red,
con aislamiento de red aplicado por el sistema operativo. Las variables de
telemetría no son un cortafuegos. No ejecutar dependencias de terceros con
secretos de CI o despliegue.
