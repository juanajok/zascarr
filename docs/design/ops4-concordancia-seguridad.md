# OPS4 — concordancia de seguridad entre app y host (M3)

Auditoría de código del 2026-11-20 sobre `b9f5a612`. **M3 sigue abierto.**

**Decisión del usuario (2026-11-20):** la autoridad será la app, que
reautentica y emite una [autorización corta de un solo uso](ops4-autorizacion-app-host.md);
el host no leerá el hash para esa comprobación. El contrato aislado ya existe,
pero la composición, el consumo durable y la revisión SecOps siguen pendientes.
Una coincidencia con el hash de PostgreSQL no demuestra coincidencia con la
configuración efectiva. OPS4 está desconectado; este documento no acredita
explotación en una actualización desplegada ni aprueba integración.

## Fuentes actuales

- La app combina la configuración base con las claves presentes de
  `runtime_settings`: [declaración de campos](../../src/zascarr/config.py),
  [aplicación de overrides](../../src/zascarr/services/runtime_settings.py#L231-L240).
- El host consulta exclusivamente `auth_mode` y `auth_password_hash` de la
  fila 1: [lector fijo](../../deploy/ops/lector_credenciales_ops4.py). Las
  claves ausentes se convierten en vacío y deniegan; no reconstruye el entorno.
- La [prueba viva](../../deploy/ops/prueba_viva_ops4.py) acredita únicamente
  que el texto recibido coincide con el hash aportado por ese lector.

## Escenarios que deben cerrarse

| Escenario | App | Host aislado | Consecuencia |
| --- | --- | --- | --- |
| Credenciales solo en configuración base | Puede tener autenticación válida | Faltan claves SQL | Denegación conservadora, no bypass |
| Modo en base y hash en BD, o viceversa | Combina ambas fuentes | Falta una clave SQL | Denegación conservadora |
| Ambos overrides SQL presentes y startup correcto | Aplica ambos overrides | Lee ambos | Concordancia posible; cambiar solo el entorno no vence esos overrides |
| Guardar contraseña B antes de commit | Memoria puede haber cambiado a B | Otra conexión SQL aún ve A | Puede aceptar A aunque el proceso activo ya use B |
| Fallo de commit o rollback posterior al guardado | Memoria puede conservar B | SQL conserva A | Divergencia que puede durar hasta recarga/reinicio |
| Recuperación CLI/SQL/restauración con app viva | Puede conservar A en memoria | Ve B confirmado | Puede aceptar B aunque esa app aún use A |
| `user_password` con usuario efectivo vacío | No hay login normal utilizable | Modo/hash bastan para comparar | No acredita identidad utilizable |
| App degradada o conectada a otra BD | Puede no estar lista o usar otra identidad | Una BD sana responde | No acredita readiness ni identidad común |

### Publicación anterior al commit: evidencia concreta

[RuntimeSettingsService.save](../../src/zascarr/services/runtime_settings.py#L139-L155)
hace `flush()` y llama inmediatamente a `apply_overrides(values)`. El commit
normal ocurre después, tras el `yield` de
[get_db](../../src/zascarr/database.py#L39-L47). En su excepción se hace
rollback SQL, pero esos servicios no restauran el objeto Settings global.

El [guardado de seguridad](../../src/zascarr/services/seguridad.py#L299-L317)
puede conservar el hash anterior si no llega una contraseña nueva, sube la
versión de sesión y limpia la caché antes de ese commit. Por ejemplo, pasar
modo a `none` en memoria mientras SQL aún conserva modo protegido puede dejar
que la comprobación aislada host acepte la contraseña SQL anterior. No basta
con validar el formato o repetir la consulta para resolverlo.

### Cambios fuera del proceso e identidad

Settings es una instancia cacheada por proceso y la carga normal de overrides
se hace en el arranque. La [recuperación CLI](../../src/zascarr/cli/seguridad.py)
modifica SQL desde otro proceso. Si se usa sin recargar/reiniciar el proceso
activo, no se ha demostrado propagación automática. No se afirma aquí que el
procedimiento habitual omita ese reinicio: el riesgo es condicional.

El modo `user_password` de [autenticación](../../src/zascarr/services/auth.py)
requiere usuario efectivo no vacío; la reautenticación utiliza internamente
ese usuario. OPS4 no lo consulta. La ruta normal de Ajustes valida el usuario,
pero eso no acredita configuraciones históricas, externas o restauradas.
Tampoco se ha demostrado que la base identificada por `zascarr-db` sea la
conexión efectiva de la app, ni que esta se encuentre lista para operar.

## Opciones de diseño, ninguna aprobada por esta auditoría

1. **Autoridad de la app efectiva:** reautenticar en ella y entregar al host
   autorización corta, de un solo uso y vinculada a instalación, operación y
   generación de credenciales. Requiere decidir si confiar en la app satisface
   el modelo de amenaza y cómo invalidar la prueba si cambia la generación.
2. **Comprobación independiente en host:** snapshot/generación confirmado y
   prueba autenticada de que la app activa ha aplicado exactamente la misma
   generación. Sin identidad, concordancia o readiness, denegar. Leer entorno
   además de SQL no resuelve por sí solo memoria desfasada ni rollback.
3. **Restringir alcance inicial:** exigir credenciales completas en SQL y
   recarga confirmada tras cambios reduce casos, pero no basta como garantía:
   aún necesita publicación posterior al commit y generación activa acreditada.

Antes de elegir, precisar qué significa «actual» (proceso activo o último
estado SQL confirmado), confianza en la app, sincronización de CLI y
restauraciones, readiness, invalidación de pruebas, bloqueo de intentos
compartido y vínculo instalación–app–BD–auxiliar. No se cambia el protocolo ni
se concede confianza nueva por el mero resultado de una prueba aislada.

## Alcance de la evidencia

La revisión fue solo lectura. Los ensayos previos de Docker/PostgreSQL prueban
lectura y rotación de hashes sintéticos, **no** estos escenarios de app viva,
rollback o cambios concurrentes. No se ha reproducido esta divergencia en la
Pi ni usado credenciales reales. Los módulos continúan desconectados y la
actualización deshabilitada. Cualquier futura corrección de autenticación en
servicio necesitará regresiones y revisión SecOps del SHA final antes de una
fusión, conforme a la regla vigente del proyecto.
