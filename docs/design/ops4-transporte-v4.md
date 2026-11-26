# OPS4 — transporte v4 aislado

Envía la petición v4 por el socket Unix configurado y valida la respuesta del
host. Está conectado al auxiliar desde B2b; la UI de último intento (B7)
sigue pendiente. `aceptada` solo acredita admisión, no éxito.

## Contrato

- Petición: línea v4 ya construida, 1–4096 bytes; no se registra.
- Respuesta: JSON + LF, máximo 4096, campos exactos
  `v=4, id, resultado ("aceptada"|"rechazada"|"incierta"), codigo`.
- Códigos cerrados: `aceptada`, `esquema_invalido`, `firma_invalida`,
  `caducada`, `autorizacion_invalida`, `repetida`, `operacion_en_curso`,
  `no_disponible`, `incierta`.
- `resultado=aceptada` exige `codigo=aceptada`; cualquier combinación
  incoherente, ID distinto, CRLF, duplicado o esquema inventado es
  `respuesta_invalida`. `resultado=incierta` exige `codigo=incierta` y se
  mapea a `ResultadoSolicitudV4.INCIERTA`; es una adición de B2 pendiente de
  ratificar en la spec de cierre (decisión 4: «no se añaden códigos nuevos»).
- Timeout o fallo **después** de abrir el socket es `incierto`: pudo enviarse
  algo y perderse la respuesta. Fallo de conexión previo es `no_disponible`.
  Nunca se reintenta automáticamente.

## Evidencia

- [Transporte](../../src/zascarr/services/actualizacion_transporte_v4.py) y
  [tests](../../tests/test_ops4_transporte_v4.py): **23 casos**.
- Conversador inyectable; respuestas válidas/inválidas, timeout, fallo previo,
  incertidumbre, petición/ID inválidos y socket Unix temporal real.
- E2E socket temporal: app construye el testigo v4, el host lo admite y consume
  el registro durable; la segunda petición se rechaza.
- **447 pruebas OPS4/instalador** verdes en B2b. La suite completa debe
  repetirse tras este cambio.

## Límites

- Conectado al auxiliar; no hay ruta UI (B7). La VM de B2b usó un `update.sh`
  inofensivo: no se ha probado un host real, Docker, PostgreSQL ni la Pi.
- La respuesta `aceptada` no se reconcilia con estado durable; no hay
  tratamiento de respuesta perdida más allá de `incierto`, ni botón de reintento.
- El socket real no se usa en las pruebas salvo un Unix temporal; el test E2E
  simula el host con `admitir_v4` y registro durable.
- Siguen pendientes provisión de clave, composición app real, respuesta
  incierta/estado, unidad endurecida y revisión SecOps final.

La actualización sigue deshabilitada.
