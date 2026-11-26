# OPS4 — Permisos del estado inicial (#443, SEC-B1-01)

**Estado:** propuesta para revisión; no autoriza habilitar ni desplegar OPS4.
**Base:** `c4a3420349153f2ac3185df3da46b37c8211aa3d`.

## Problema

El auxiliar de actualización se ejecuta con UID 0 y sin capacidades Linux. El
instalador asigna al directorio `ops` el grupo de servicio; el escritor toma ese
GID e intenta publicar el estado como `root:<grupo>` y modo `0640`. Cuando el
GID de `ops` no coincide con el grupo efectivo ni con uno suplementario del
auxiliar, `fchown` puede devolver `EPERM` sin `CAP_CHOWN`. En ese caso se devuelve
`INCIERTO`, se rechaza la solicitud y no se inicia la unidad. El fallo depende
de la identidad y del sistema de ficheros; no se presume universal.

## Solución propuesta, sujeta a revisión SecOps

La unidad auxiliar fijará explícitamente `User=root` y `Group=@GRUPO@`. El
instalador ya sustituye `@GRUPO@` con el grupo de servicio. El auxiliar conserva
`CapabilityBoundingSet=` vacío, `NoNewPrivileges=yes`, la acción fija, el modo
`0640` del estado y el rechazo si la publicación no se confirma. No se concede
`CAP_CHOWN`, no se relaja el modo del estado ni se omite un error de `fchown`.

El cambio del grupo efectivo también cambia las comprobaciones de acceso del
proceso: SecOps debe revisar el acceso a la clave, el cerrojo, los directorios
`ops` y `ops4`, la herencia de grupos y la superficie accesible por el grupo de
servicio. Las marcas privadas deben seguir protegidas; el UID 0, sin capacidades,
no garantiza acceso a archivos ajenos. El grupo configurado debe coincidir con
el que exige el directorio `ops`; una divergencia debe fallar cerrada. Un cambio
de grupo posterior exige reprovisionar, sin modificar la instalación en esta
historia. ACL, sistemas de ficheros y políticas LSM pueden alterar el resultado.

## Criterios y pruebas previstas

- **AC1.** La unidad instalada usa `User=root`, `Group=@GRUPO@`, y mantiene
  `CapabilityBoundingSet=` vacío, `NoNewPrivileges=yes` y el resto de límites.
  Prueba: `test_unidad_auxiliar_usa_grupo_configurado_sin_cap_chown`.
- **AC2.** El instalador sustituye el grupo en la unidad sin aceptar marcadores
  sin resolver y sin activar socket ni servicio por defecto. Prueba: ampliar la
  prueba del instalador con un grupo de fixture y comprobar el contenido
  instalado, no solo la plantilla.
- **AC3.** Si el cambio de propietario falla, la publicación devuelve
  `INCIERTO`, no sustituye el destino anterior y elimina el temporal; el
  auxiliar responde `no_disponible` y no inicia. Pruebas con error `EPERM`
  inyectado en el escritor y con el auxiliar conectado al escritor real.
- **AC4.** Las credenciales del directorio `ops4` y las marcas de consumo
  siguen siendo privadas; las pruebas comprueban sus modos y la ausencia de
  ampliación de capacidades. Los mocks no demuestran DAC real.
- **AC5.** Antes de habilitar, una VM desechable con systemd debe demostrar
  UID 0, GID de servicio distinto de root, capacidades efectivas vacías,
  lectura de clave, publicación `root:<grupo>` `0640` y lectura desde la
  identidad de la app; también debe probar divergencia de grupo y fallo
  cerrado. No se arranca la actualización real ni se toca la Pi en este paso.

## Límites y puertas

No modifica la app, los protocolos, la autenticación, el cerrojo B2 ni la
opción apagada por defecto. No instala ni activa nada en el host. La prueba de
VM, la revisión SecOps del SHA final y las demás condiciones OPS4 permanecen
pendientes; las pruebas unitarias no equivalen a validación real de systemd.
La SPEC se aprueba antes de la implementación. El pipeline solo puede editar
archivos `100644` ya versionados; las pruebas de regresión y las comprobaciones
independientes las prepara la persona operadora y no son editables por el rol
DEVELOPER.
