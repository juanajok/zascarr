# Definición de preparación (DoR) — aprobada el 2026-11-26

Un trabajo no entra en curso hasta cumplir lo que exige su nivel de riesgo. El nivel se fija con [la clasificación de riesgo](risk-classification.md).

## Común a todo trabajo

- Problema descrito con el caso real que lo motiva, no solo la solución deseada.
- Ámbito delimitado: qué se toca y qué queda fuera.
- Dependencias desbloqueadas; si algo está bloqueado, se dice cuál y por qué.
- Nivel de riesgo declarado y justificado.

## Cambios con código

- Contrato aprobado antes de programar, con criterios de aceptación verificables.
- Pruebas existentes identificadas y forma de comprobarlas en local.
- Una prueba prevista por criterio, con nombre; una excepción manual necesita decisión explícita.
- Riesgo `medio` o `alto`: revisión independiente prevista y, si aplica, análisis de amenazas.

## Documentación y decisiones

- Criterio de exactitud: qué afirmación debe poder comprobarse y con qué fuente.
- Nada de afirmar resultados de pruebas que no se hayan ejecutado.
- Si el documento cambia una norma vigente, el traslado y la retirada de la copia anterior se aprueban por separado.

## Límites

Cumplir el DoR **no** autoaprueba nada: es condición para empezar, no permiso de fusión.
