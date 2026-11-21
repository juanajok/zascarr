# OPS4: estado y límite de avance (#443)

Fecha: 2026-11-20. Este documento no autoriza nada.

## Hecho y verificado en aislamiento

- Gate del auxiliar: rechaza `actualizar` en los protocolos actuales, JSON
  ambiguo/sobredimensionado y firmas incorrectas, sin lanzar subprocesos.
- Puerta UI: Estado no ofrece controles de actualización ni existe una ruta POST
  ejecutable en el enrutador actual.
- Lector puro de objetos Git y comparación textual de identidades: solo modelos
  sintéticos, sin autenticidad, procedencia ni snapshot real.
- Modelo puro de aprobación, caducidad, intento y cortes alrededor de
  `fsync`/`rename`; reconciliar exige una nueva aprobación.
- Barreras estáticas: experimentos no importados por la app/auxiliar y sin E/S.
- Suite completa: 8234 passed, 2429 skipped; 237 pruebas OPS4 y Ruff PASS.

## Descartado tras revisión

- Prototipo de almacén de reserva: no resolvía el estado incierto tras un fallo
  de `fsync`, la sustitución del cerrojo ni la transferencia al ejecutor.
- WAL append-only: un cierre visible tras `fsync` fallido podía parecer durable,
  el truncado de líneas completas no se detectaba y la marca de arranque no era
  fencing.

## Bloqueo concreto

Para avanzar en la actualización real hacen falta, como mínimo:

1. un arnés de host aislado con root/permisos controlados, filesystem que
   respete `fsync`, cortes/reboots inyectados y reconciliación verificable;
2. un aislamiento efectivo para consultar objetos Git no fiables o una copia
   controlada equivalente;
3. revisión independiente de SecOps/QA del SHA final y autorización expresa
   separada para fusionar/desplegar;
4. una decisión del PO sobre activar actualizaciones automáticas frente a la
   garantía de rollback manual y la interfaz «sin consola».

No se puede demostrar durabilidad ni ejecución privilegiada desde esta sesión
sin esas condiciones. La PR #1159 permanece en borrador; la acción está
deshabilitada y no hay cambios en la Pi.
