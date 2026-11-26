# Repetición de B1 con procesos reales

Evidencia del replay del candidato B1 (`feat/ops4-b1-443`) sobre el motor, con el oráculo puro
y una prueba de procesos real dentro del gate. No es una prueba del producto completo ni se
ejecuta en CI.

## Piezas

- `procesos_b1.py`: driver del operador. Cuatro procesos publican a la vez, comprueba que el
  cierre terminal no se pierde, que un fallo de `fsync` devuelve `INCIERTO` sin cambiar el
  estado y que no quedan temporales.
- Oráculo de solo lectura: `docs/design/ops4-b1-check.py` en el árbol de B1.
- Suites del proyecto: `tests/test_ops4_escritor_estado.py` y
  `tests/test_ops4_estado_actualizacion.py`, ejecutadas **fuera** del gate.

## Replay

- Base: `b32ce410^`; candidato: `f6d86257` (el código fuente es idéntico al fusionado en
  `c4a34203`; `690b77b9` añade las pruebas finales).
- Perfil `HIGH_ASSURANCE`; 6 llamadas; 2 aprobaciones humanas; 1 ronda; sin bloqueos.
- RED `42` con `contrato-v2`; GREEN `0` en `contrato-v2`, `monotonia`, `reconciliacion` y
  `procesos`. Entrega `3eb1de49ad5f1529338736f1fff275c7689c53d6`.
- Imagen de los checks: `python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`;
  el check `procesos` usa `"scratch": true`.
- Driver: `python3 -B procesos_b1.py`; pasó en 1,77 s; el estado inicial y los procesos usan
  `/scratch`; `/src` queda en solo lectura.

## Suite del proyecto

En un contenedor Python 3.11 con las dependencias del producto: **80 pruebas pasan**, incluida
`test_publicacion_concurrente_no_pierde_terminal` (5/5 estable). La imagen local de esa
ejecución fue `sha256:11766282d845470fbf250f1eeba82892059d25cf9f381593faade9bb3fe14e37`
(construida desde `zascarr-uxlab-app:local` + `pytest==8.4.2`); no está versionada.

## Límite

Las respuestas de los roles del replay fueron fixtures del operador, no dictámenes
independientes de modelos. La suite completa no cabe en el manifiesto actual (64 rutas,
512 KB) y sigue fuera del gate. Este driver cubre el ciclo de publicación, no la operación
real del host, systemd, instalador ni `update.sh`.
