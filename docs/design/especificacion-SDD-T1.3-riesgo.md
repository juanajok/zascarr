# Especificación SDD-T1.3: riesgo, preparación, cierre y excepciones

**Estado:** aprobada por el mantenedor el 2026-11-26. La aprobación del contrato no autoriza fusión ni despliegue. No se ha ejecutado ni publicado más que este fichero. Depende de T1.2 para los destinos documentales y de tus decisiones de proporcionalidad: este documento propone criterios, no los impone.

## Problema

El mapa de reglas deja 39 reglas sin destino porque faltan documentos que decidan **cuánto rigor** exige cada cambio, **cuándo** un trabajo está listo para empezar y **cuándo** se considera terminado. Sin esos acuerdos, migrar consiste en reformatear la guía, y cualquier excepción urgente se convierte en norma de facto.

## Alcance

Política documental y de proceso: clasificación de riesgo, preparación y cierre, excepción de emergencia, propiedad de las aprobaciones y plantillas asociadas. No cambia comportamiento del producto, no activa gates obligatorios y no modifica CI.

## Criterios propuestos

- **T1.3-C01 Clasificación objetiva.** Cuatro niveles —trivial, bajo, medio, alto— con criterios verificables por ámbito (código, datos, ficheros, seguridad, interfaz, infraestructura). El diff puede **elevar** el nivel; nunca reducirlo. El ámbito afectado decide el bloqueo, no la etiqueta declarada.
- **T1.3-C02 Proporcionalidad.** Cada nivel fija artefactos y revisiones exigidos (por ejemplo, un cambio trivial no arrastra análisis de amenazas). La tabla es explícita y no deja «según criterio» como respuesta.
- **T1.3-C03 Preparación (DoR).** Un trabajo entra solo si tiene problema descrito, criterio de aceptación verificable, ámbito delimitado, pruebas existentes identificadas y dependencias desbloqueadas. Para código, el contrato debe estar aprobado antes de implementar.
- **T1.3-C04 Cierre (DoD).** Un trabajo se cierra con pruebas en verde y evidencia del rojo previo cuando aplique, documentación actualizada, sin hallazgos bloqueantes abiertos y aprobación de quien corresponda. Un criterio sin prueba nombrada exige decisión explícita, no silencio.
- **T1.3-C05 Excepción de emergencia.** Toda excepción registra causa, alcance, riesgo, mitigaciones, responsable, caducidad con fecha y seguimiento. **No** exime de controles de seguridad ni de la aprobación de fusión, y no certifica la discrepancia que la motivó.
- **T1.3-C06 Propiedad de las aprobaciones.** Ningún agente se autocertifica. La aprobación humana se verifica por su identidad en la plataforma, no por un texto. La revisión de seguridad se ata al SHA final que se fusiona, incluidos commits posteriores.
- **T1.3-C07 Plantillas consecuentes.** Backlog y PR incorporan la sección de riesgo, la referencia al contrato aprobado y el hueco para la evidencia RED/GREEN. Una plantilla que no se rellena no acredita cumplimiento.
- **T1.3-C08 Verificación con casos negativos.** Pruebas de excepción caducada, riesgo rebajado a mano, falta de evidencia RED, aprobación de un SHA anterior y plantilla sin sección. Nada de esto se conecta a CI bloqueante en esta historia.

## Decisiones que necesito de ti

1. **Niveles y umbrales.** ¿Te sirven cuatro niveles con estos ámbitos, o prefieres tres?
2. **Quién aprueba cada nivel.** Propongo: trivial, cualquiera con permiso de fusión; bajo, revisión de código del área; medio, contrato aprobado y revisión independiente; alto, además análisis de amenazas y revisión de seguridad del SHA final.
3. **Caducidad de excepciones.** Propongo fecha obligatoria y revisión en el siguiente ciclo; ninguna excepción sin fecha.
4. **DoR para documentación.** Propongo criterio más ligero que para código, pero sin librar de la aprobación de contrato.

## Pruebas previstas

| Criterio | Verificación | Estado |
|---|---|---|
| C01 | Caso negativo de reclasificación a la baja; clasificación por ámbito | NOT RUN |
| C02 | Tabla de proporcionalidad revisada contra cambios reales del histórico | NOT RUN |
| C03–C04 | Recorrido de una historia ficticia por DoR y DoD, con y sin prueba nombrada | NOT RUN |
| C05 | Excepción sin fecha y excepción que intenta saltarse seguridad: deben rechazarse | NOT RUN |
| C06 | Aprobación de SHA anterior debe invalidarse al añadir commits | NOT RUN |
| C07 | Plantilla sin sección de riesgo detectada antes de su uso | NOT RUN |
| C08 | Los cinco casos negativos fallan por el motivo esperado | NOT RUN |

## Límites

- Esta SPEC no crea gates, no modifica `.github/` ni la protección de rama.
- No sustituye la revisión de seguridad ni la aprobación de fusión, que siguen requiriendo decisión separada.
- Los umbrales son propuesta: sin tu decisión no se consideran acordados ni se migra la regla correspondiente.
