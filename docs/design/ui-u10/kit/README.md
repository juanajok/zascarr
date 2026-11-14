# Kit operativo para validar «Por revisar» con personas (#272)

> **Estado: kit listo; sesiones con personas: NOT RUN.**
>
> Este kit **no acredita #272 ni U10**. Es la preparación para que el PO ejecute las sesiones con
> 3–5 coleccionistas reales. Ningún agente, simulación o prueba en seco sustituye a esas personas:
> la deuda de U10 sigue abierta hasta que haya sesiones fechadas, consentimiento, registros y ficha
> §13 actualizada.

## 1. Qué es este kit y qué no es

**Es** el conjunto de documentos que permiten reclutar, consentir, moderar, registrar y analizar una
sesión de usabilidad de la pantalla «Por revisar» sin improvisar y sin meter datos personales en el
repositorio.

**No es** evidencia de validación. Que estos documentos existan no demuestra que el diseño se
entienda: eso solo lo dicen las personas. Por eso el estado es **NOT RUN** y no cambia hasta que se
ejecuten las sesiones.

El material que se prueba es **una sola versión: la app real** (el flujo implementado de «Por
revisar»), y el entorno congelado lo fija el [guion de la sesión real](guion-sesion-real.md) antes
de la primera sesión. Este kit no elige pantallas ni variantes: no hay A/B en esta ronda.

## 2. Índice del kit

Todos los ficheros viven en esta carpeta (`docs/design/ui-u10/kit/`).

| Fichero | Para qué | Cuándo se usa |
|---|---|---|
| [reclutamiento.md](reclutamiento.md) | Perfil, exclusiones, mensaje de invitación, agenda y riesgos de la muestra | Antes de invitar |
| [consentimiento-y-conservacion.md](consentimiento-y-conservacion.md) | Qué se recoge y qué no, consentimiento, plazos, anonimización y plantilla | Antes y durante la sesión |
| [piloto-tecnico-2026-11-14.md](piloto-tecnico-2026-11-14.md) | Piloto del **instrumento de registro** (hoja, CSV, definiciones) con datos sintéticos; el ensayo del montaje (entorno, grabación, audio, borrado, restauración) sigue **NOT RUN** y depende de la checklist | Antes de la primera sesión |
| [guion-sesion-real.md](guion-sesion-real.md) | Tareas T1–T7, encuadre, orden de las carpetas de ejemplo (F-A/F-B, si hay dos) y qué se dice (y qué no) | Durante la sesión |
| [checklist-moderador.md](checklist-moderador.md) | Lista de comprobación del día: antes, durante y después | El día de la sesión |
| [registro-y-analisis.md](registro-y-analisis.md) | Hoja por participante y tarea, tabla agregada, análisis y límites | Al terminar cada sesión y al cerrar |

Orden de lectura recomendado: **reclutamiento → consentimiento → piloto técnico → guion →
checklist → registro**. El registro se lee antes de la primera sesión aunque se rellene después.

Si algún enlace de esta tabla no resuelve, ese fichero todavía no está en la rama: **el kit está
incompleto y las sesiones no deben empezar**.

## 3. Estado y qué falta

Hecho:

- Este índice, el [reclutamiento](reclutamiento.md) y el
  [consentimiento y conservación](consentimiento-y-conservacion.md).
- El guion, la checklist, el registro y el piloto técnico forman parte del mismo kit y se enlazan
  arriba; si falta alguno, el kit está incompleto.
- El criterio de honestidad está fijado: sin personas no hay validación, y una simulación no se
  convierte en PASS humano.

Falta, y cada punto lo hace una **persona**, no un agente:

- [ ] Reclutar 3–5 coleccionistas no técnicos y aplicar los criterios de exclusión
      ([reclutamiento](reclutamiento.md)).
- [ ] Leer y firmar o registrar verbalmente el consentimiento de cada persona; guardar el original
      en privado ([consentimiento](consentimiento-y-conservacion.md)).
- [ ] Congelar material y entorno (versión, navegador, viewport, tema, guion) y no cambiarlos entre
      participantes.
- [ ] Ejecutar las sesiones con el [guion](guion-sesion-real.md) y la
      [checklist](checklist-moderador.md), con la misma versión de la app; si se usan dos carpetas
      de ejemplo (F-A/F-B), alternar su orden y registrarlo.
- [ ] Registrar por tarea: éxito sin ayuda, éxito con ayuda, fallo o abandono; tiempo, errores,
      intervenciones, cita y SEQ.
- [ ] Analizar y separar lo observado de las hipótesis ([registro y análisis](registro-y-analisis.md)).
- [ ] Actualizar la ficha §13 ([decisión G1 del 2026-10-21](../decision-g1-2026-10-21.md)) con el
      material exacto usado y las diferencias con la simulación.
- [ ] Comentar en #272 y decidir el cierre. Si los resultados contradicen la decisión G1, **abrir
      una decisión nueva**; no reescribir la historia ni convertir la simulación en validación.

Mientras quede una casilla sin marcar, el estado sigue siendo **NOT RUN**.

## 4. Por qué esto no cierra #272 ni U10

El criterio de cierre de #272 es: **sesiones reales registradas y ficha §13 actualizada**. El kit
solo cubre la preparación. La simulación del 2026-11-11
([informe](../simulacion-272-2026-11-11.md)) aporta hipótesis y fricciones candidatas (F1–F4), pero
sus «citas» son reconstrucciones de perfiles, no transcripciones, y sus tiempos no son comparables.
La [prueba en seco](../../validacion-ux-por-revisar-2026-11-13.md) del flujo implementado aporta
comprobaciones automáticas, no comprensión.

Por tanto:

- **Kit listo** significa «se puede ejecutar», no «se ha ejecutado».
- **U10** sigue siendo **simulación aceptada**, no validación real.
- **#272** sigue abierta y su deuda debe seguir visible en #196 y en el tablero.

## 5. Relación con la decisión G1 y con #197 / #200

- **G1, 2026-10-21** ([ficha §13](../decision-g1-2026-10-21.md)): el responsable aceptó la
  simulación con agentes como evidencia suficiente para **desbloquear U13** (#200), con la deuda de
  la validación real visible y separada. No se declaró que U10 hubiera validado el diseño con
  coleccionistas.
- **#197 (U10)**: se cerró como decisión de producto con esa ficha; el informe quedó marcado como
  simulación. Este kit sirve para pagar la deuda, no para reabrir ni reescribir #197.
- **#200 (U13)**: dejó de estar bloqueada por G1 y siguió su propio refinamiento. Las sesiones de
  este kit prueban «Por revisar» (la app real, una sola versión que fija el guion) y
  pueden producir correcciones; no cierran #200 por sí solas.
- **#196**: feature de la auditoría de UI donde se originó U10; la deuda debe seguir visible allí.
- **#272**: esta tarjeta. Solo se cierra con personas reales y ficha actualizada.

Si las sesiones reales contradicen la decisión del 2026-10-21, se abre una **decisión nueva** y se
enlaza desde la ficha; la decisión anterior no se reescribe.

## 6. Material relacionado

- [Guion base T1–T7](../guion-sesion.md): el de la simulación; el real lo adapta
  [guion-sesion-real.md](guion-sesion-real.md).
- [Simulación #272 del 2026-11-11](../simulacion-272-2026-11-11.md): hipótesis F1–F4, **no**
  validación.
- [Resultados de la simulación U10](../resultados-simulacion.md) e informes
  [P1](../resultados-P1.md), [P2](../resultados-P2.md), [P3](../resultados-P3.md).
- Prototipos A y B (`../prototipos/`) y su generador: **histórico de la simulación de 2026-10-21,
  no se usan en esta ronda** (se prueba la app real).
- [README de U10](../README.md) y [ficha G1](../decision-g1-2026-10-21.md).
- [Validación UX del flujo «Por revisar» del 2026-11-13](../../validacion-ux-por-revisar-2026-11-13.md):
  primer protocolo (5 perfiles, 5 tareas, métricas y prueba en seco). **Este kit lo sustituye como
  protocolo único** para la app actual; del anterior se conservan los perfiles y las métricas como
  referencia. Hay **un solo consentimiento y un solo registro por persona**: no se ejecutan dos
  protocolos ni se cuentan dos veces las mismas sesiones.
- [Walkthroughs sintéticos del 2026-11-13](../../validacion-ux-por-revisar-2026-11-13-simulada.md):
  simulación; no son participantes.

## 7. Convenciones del kit

- **P1…P5 son seudónimos de participante**, asignados por orden de sesión. No son perfiles fijos ni
  las personas simuladas del informe del 2026-11-11. El mapa seudónimo → identidad vive solo en el
  original privado del consentimiento.
- **Sin PII en el repositorio**: ni nombres, ni correos, ni rutas, ni nombres de archivos, ni
  capturas de bibliotecas. Ver [§3 del consentimiento](consentimiento-y-conservacion.md#3-qué-no-se-recoge).
- **Fechas en ISO** (`AAAA-MM-DD`) y horas con zona cuando importen.
- **Lo observado se separa de lo interpretado**: una cita literal no es una conclusión; una
  impresión del moderador se marca como tal.
- **Lo que no se preguntó queda NOT RUN**; no se rellena por inferencia.
- **Enlaces relativos** dentro del repositorio.

## 8. Versión

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-11-14 | Índice y estado del kit #272; criterio de cierre y relación con G1, #197 y #200. |
