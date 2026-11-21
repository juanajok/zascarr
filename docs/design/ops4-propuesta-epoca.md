# OPS4 — hipótesis de época efímera y fencing (#443)

**Estado: hipótesis de diseño para revisión adversarial; no implementada ni
aprobada.** No habilita la actualización ni sustituye la SPEC. Pretende cerrar
el hueco descrito en el [plan de validación](ops4-plan-validacion-aislada.md):
tras un `rename` seguido de `fsync` fallido puede reaparecer el estado anterior
como si la aprobación estuviese libre. Escribir otro aviso en el mismo disco no
resuelve ese problema.

## Propuesta de admisión por época

- En **cada** inicio o reinicio del coordinador, incluso dentro del mismo boot,
  crear una época nueva y empezar con gate cerrado. Ninguna A de una época
  anterior es utilizable, aunque el disco muestre `libre`; esto incluye A que
  no llegó a usarse. **Esto puede restringir AC-15**, que contempla usar A no
  utilizada antes de las 24 horas: requiere decisión y, si se acepta, revisión
  explícita de la SPEC y sus criterios. No se considera acordado. Un archivo en
  `/run` o `boot_id` no es por sí solo fencing.
- Antes de abrir una época, un administrador reconcilia explícitamente la
  instalación: trabajos systemd, unidad, procesos/cgroup, HEAD, snapshot,
  imagen/contenedor, BD y copia según fase. Ante trabajos activos, información
  incompleta o almacenamiento incierto, se mantiene cerrado. No automatizar la
  decisión ni reanudar una operación vieja.
- El emisor administrativo, integrado en el coordinador confiable, liga cada A
  a identidad de instalación, boot, época, nonce, SHA S completo, HEAD0, P,
  origen/ref y fecha. Solo registra A utilizable **en memoria** después de la
  confirmación explícita del administrador y del éxito de escritura, `fsync`
  de fichero, rename y `fsync` de directorio. Si hay error o incertidumbre, la
  época debería pasar a cuarentena en memoria antes de responder y no volver a
  leer esa A como libre. Sigue sin demostrarse la seguridad si se mata el
  proceso entre fallo y cuarentena o si hay otro coordinador. Al reiniciarse
  el proceso debe nacer otra época cerrada. Falta el protocolo de emisión que
  pruebe que solo una herramienta local invocada con sudo confirma exactamente
  el SHA completo y el origen reconfirmado; ni la app ni su grupo pueden pedir
  o fabricar A. Propiedad root por sí sola no demuestra esa frontera.
- Durante la época, un único coordinador autoritativo serializa estados en
  memoria (`libre → reservando → reservada → consumiendo → consumida`, con
  estado absorbente `incierta`). La **reserva se persiste y sincroniza antes
  de pedir start**; el consumo se persiste antes de conceder efectos. Ocupado
  no debe consumir otra A; el orden/traspaso del cerrojo común de OPS1/OPS2
  sigue por diseñar. Si el coordinador muere tras conceder permiso, hay que
  mantener exclusión también frente a OPS1/OPS2 mientras sobreviva la unidad;
  cerrar la época no basta. No se ha demostrado esa exclusión. La memoria no
  reemplaza A durable ni los registros host.

## Unidad, canal y efectos

La unidad y coordinador son artefactos fijos root-owned, instalados previamente;
la app y su grupo no pueden iniciar directamente la unidad ni acceder al canal.
El id en argv no autoriza nada. La unidad, incluso si es invocada directamente,
no realiza fetch ni otros efectos sin una reserva y un permiso para su instancia
exacta. Se propone un canal Unix privado autenticado por credenciales del
kernel, más verificación de la instancia systemd y del trabajo esperado; **no
se ha demostrado** que `SO_PEERCRED`, PID, cgroup e InvocationID sean suficientes
frente a PID reutilizados, jobs fusionados y carreras. La interfaz, acceso,
orden, tiempos de espera y entrega única requieren diseño y pruebas reales.

El permiso efímero, vinculado a época, intento y unidad, solo se envía tras
consumo durable y revalidación de A/P/reloj/guardas; su utilización es única.
Sin coordinador vivo ni permiso no hay efectos. Si el coordinador muere antes
de entregarlo, la unidad debe denegar. Si muere **después**, la unidad ya pudo
realizar efectos y puede seguir ejecutándose: EOF no los revoca. La nueva época
permanece cerrada hasta comprobar trabajos y procesos residuales y reconciliar
el estado. No hay reintento, rollback ni relanzamiento automáticos. La entrega
incierta del permiso, su consumo atómico y la identidad de la instancia son
objetivos sin protocolo probado, no garantías actuales.

## Contraejemplos que debe superar

| Interrupción o ataque | Resultado exigido; aún NOT RUN |
|---|---|
| `fsync` del directorio de A o reserva falla después de rename; reboot revive estado antiguo | Nueva época cerrada; A anterior no utilizable. |
| Coordinador muere tras ordenar `start` pero antes de entregar permiso | No repetir start; unidad sin permiso deniega y reconciliación revisa trabajos supervivientes. |
| Respuesta de `start` se pierde tras entrega de permiso | Nunca relanzar; la unidad puede seguir activa o haber causado efectos, por lo que no se anuncia ausencia de cambios. |
| Dos ids intentan usar una A o una unidad directa coincide con un start | A lo sumo una autorización; verificar además que systemd no fusione jobs de una forma que conceda al proceso incorrecto. |
| Reinicio del coordinador dentro del mismo boot | Nueva época cerrada y A anterior inútil; no confiar solo en `boot_id`. |
| Reloj retrocede, `/run` no es fiable, duplicado de coordinador o ACL de unidad débil | Fallar cerrado; el comportamiento exacto debe poder demostrarse. |
| Reversión completa del host/VM a un snapshot antiguo | No resuelto sin ancla monotónica externa o prohibición operacional verificable de restaurar estado antiguo. |

## Supuestos y puertas

Root, systemd y la protección de sus permisos son de confianza; los miembros de
`docker` o procesos root pueden saltarse cerrojos cooperativos. Se requiere
exclusión del coordinador, identificación de boot/época no repetida, protección
real del canal y del lock, reloj fiable, filesystem y hardware que respeten las
sincronizaciones exitosas, snapshot inmutable y P completo. Fallos de hardware
que miente, rollback completo y clonación de memoria/estado no quedan resueltos.
Antes de implementarlo hay que someter la secuencia al contraste con AC-01…15,
SecOps y QA, definir identidad de unidad/job y transferencia del cerrojo, y
probar todos los cortes en una VM desechable. No se han ejecutado esos ensayos.
