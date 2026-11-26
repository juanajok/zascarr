# Propuesta de especificación: reforzar la prueba del contexto Docker en #1293

Estado: borrador para aprobación, no implementado. Aplica solo a `tests/test_sdd_tooling.py`; no cambia `.dockerignore`, el lock, la imagen ni el runtime. Base propuesta: `bdc9f5e516c3ce8722684aef19bfd6255d1db335` sobre la PR #1293.

## Problema

La prueba actual comprueba excepciones que empiezan literalmente por `!`. Una excepción precedida de espacios podría escapar al análisis aunque Docker procese el patrón de otra manera. La configuración actual excluye tooling; esto es una carencia de la prueba, no evidencia de que esté incluido.

## Contrato propuesto

- **D01:** La lista actual de patrones del `.dockerignore` pasa la comprobación. Una línea no vacía y no comentada con espacio inicial o final es rechazada, antes de analizar excepciones; no se intenta interpretar toda la gramática de Docker.
- **D02:** El control exige el patrón de exclusión general `**` y solo permite las excepciones de la lista ya aceptada por el test. No se aceptan nuevas excepciones implícitamente.
- **D03:** Un fixture con ` !tooling/**`, uno con `!tooling/**` y uno con una excepción desconocida fallan por la razón prevista; se incluyen casos de línea vacía, comentario y CRLF para evitar rechazos espurios.
- **D04:** El test es determinista, usa Python y bibliotecas existentes, no requiere Docker ni acceso a red. Su PASS acredita estas propiedades de la lista de patrones, no demuestra por sí solo la semántica Docker completa ni seguridad de la imagen.
- **D05:** El resultado no altera el pin ni permite habilitar gates o fusionar. Los experimentos de instalación del lock exacto y las revisiones de suministro/licencias siguen siendo evidencias separadas.

## TDD y evidencia

1. Antes de código, obtener aprobación humana de esta SPEC o su versión revisada y registrar el SHA del contrato aprobado.
2. Añadir pruebas que fallen por las mutaciones D03; registrar RED y comprobar que el motivo es la aceptación indebida, no error de importación/infraestructura.
3. Cambiar únicamente la comprobación mínima; ejecutar las pruebas nuevas y `tests/test_sdd_tooling.py` en verde, además de ruff y `git diff --check`.
4. Revisar el diff final y adjuntar comando, SHA y salida. No confundir este análisis textual conservador con una prueba funcional del contexto de Docker.
