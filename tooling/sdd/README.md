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

## Verificación del lock exacto (2026-11-26)

Instalación limpia desde este directorio, con caché nueva y configuración de usuario propia:

```bash
env HOME=<dir vacío> npm_config_cache=<dir vacío> npm_config_userconfig=<dir>/.npmrc \
  npm ci --ignore-scripts --no-audit --no-fund
```

Resultado observado:

- 66 paquetes instalados; `node node_modules/@fission-ai/openspec/bin/openspec.js --version` responde `2.2.0`.
- SHA-256 del lock antes y después: `a952b8ddfc3dab97428a54c94e3d80c830cda7c1b90cda2076b4bd430d5103b7` (sin cambios).
- 66 entradas con `integrity`; **0** con `hasInstallScript`.
- `npm audit`: 0 vulnerabilidades (info/low/moderate/high/critical).
- Licencias declaradas: 54 MIT, 7 ISC, 4 BlueOak-1.0.0, 1 BSD-3-Clause.

Límites: la auditoría consulta la base pública de npm en el momento de la prueba y no autentica al proveedor ni inspecciona el contenido de los tarballs; no se ha revisado el aviso de terceros empaquetado dentro de `skills`. Una instalación limpia no demuestra reproducibilidad en otras plataformas ni ausencia de tráfico adicional.

## Estado del pin: adoptado como dependencia de desarrollo (2026-11-27)

Decisión del mantenedor: OpenSpec `2.2.0` **se adopta** como dependencia de desarrollo del proyecto, con las condiciones siguientes. No es una dependencia de runtime y no entra en la imagen.

Condiciones que forman parte de la decisión:

1. Versión exacta y lock con integridad; se instala con `npm ci --ignore-scripts` y se ejecuta el binario local, sin `npx`.
2. `tooling/sdd/node_modules/` no se versiona (regla en `.gitignore`).
3. Auditoría separada de la instalación: `--no-audit` es una comodidad, no una revisión. Se ejecuta `npm audit` al actualizar el pin y al menos cada trimestre, registrando el resultado.
4. Cualquier actualización de versión requiere repetir la verificación completa: instalación limpia, hash del lock, integridad, scripts de instalación y auditoría.
5. Si la auditoría devuelve una vulnerabilidad alta o crítica, el pin no se usa hasta revisarla y decidir la actualización.

Límites conocidos y aceptados en esta decisión:

- La auditoría consulta la base pública de npm en el momento de ejecutarse; no autentica al proveedor ni inspecciona el contenido de los tarballs.
- El aviso de terceros empaquetado dentro de `skills` (Apache-2.0, ISC y MIT de terceros) **no** se ha revisado en detalle; no se presenta el inventario de licencias como resuelto.
- La instalación limpia se acreditó en Linux x86_64 con Node 24.22.3 y npm 11.19.1; no hay evidencia de reproducibilidad en otras plataformas.
- Adoptar el pin no activa gates, no habilita CI bloqueante y no modifica el runtime.
