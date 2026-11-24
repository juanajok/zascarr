# UXA-13b · Dejar de esperar una búsqueda o una tanda en Deseados

**Historia:** [#1254](https://github.com/juanajok/zascarr/issues/1254) · **Origen:** UXA-13
([#1130](https://github.com/juanajok/zascarr/issues/1130)), tercer criterio · **Fecha:** 2026-11-24
· **Estado:** implementación en rama; la prueba con integraciones reales queda para el PO.

## 1. Problema

«Buscar ahora» y «Buscar seleccionados» lanzan peticiones que pueden durar hasta ~2 minutos por
deseo (foro y cortesía). El botón de cancelar hacía `htmx:abort` sobre la petición del navegador y
el texto decía «La espera se cancela; lo ya enviado no se deshace». Esa frase no explicaba qué
seguía ocurriendo y daba a entender que la búsqueda había enviado algo a descargar, cuando no es así.

## 2. Medición (2026-11-24)

### 2.1 Qué hace el servidor

- `web/wishlist.py::buscar_ahora` → `Orchestrator.preview_candidates`.
- `web/wishlist.py::buscar_lote` recorre hasta `MAX_LOTE = 8` deseos en secuencia y llama al mismo
  `preview_candidates` de cada uno.
- `Orchestrator.preview_candidates` se detiene **antes** de `_send`: devuelve los candidatos para que
  el coleccionista elija. No toca Transmission ni aMule. Solo `send_manual_candidate` (el «Sí,
  descargar» de un candidato concreto) envía al cliente.
- Lo que queda registrado si la búsqueda termina: el estado final (`WANTED`, o `last_error` con el
  motivo), la marca `last_searched_at` y, en items de política, el commit corto de esa marca. Los
  candidatos del preview **no se persisten**: son HTML de la respuesta.
- La tanda no tiene ninguna comprobación de cancelación en el bucle; si el navegador deja de
  esperar, el servidor puede seguir con los deseos que ya había empezado.

### 2.2 Qué hace htmx al abortar

`htmx.trigger('#boton-buscar-…', 'htmx:abort')` (y el equivalente sobre el formulario de la tanda)
aborta la petición **del navegador**. No hay una señal al servidor que detenga el handler.

Medido con uvicorn **0.54.0** y un endpoint lento de 1,5 s: el cliente abrió la conexión, pidió
`/slow`, cerró el socket a los 0,3 s y la tarea del servidor siguió hasta escribir su marca a los
1,5 s. Mismo mecanismo que la búsqueda real. Si el proceso se apaga o el proxy cancela la tarea,
la transacción se revierte; por eso el aviso dice «puede seguir», no «sigue siempre».

Consecuencia práctica: tras dejar de esperar, la fila puede actualizarse en el servidor (motivo o
marca) y el navegador no lo sabrá hasta actualizar Deseados. La búsqueda puede consumir la ventana
de Prowlarr/foro y la marca de intento; el envío a descargas, no.

### 2.3 Qué no pasa

- No se ha enviado nada a Transmission ni a aMule: eso solo ocurre después de «Sí, descargar».
- Los candidatos de esa búsqueda/tanda no se guardan; si se quieren ver, hay que volver a buscar.

## 3. Decisión

No se implementa cancelación cooperativa en el servidor (tendría que consultar una señal entre
pasos y no forma parte de esta historia). El cambio es **decir la verdad** y no prometer una
cancelación que no ocurre:

- El botón se llama **«Dejar de esperar»** por búsqueda y **«Dejar de esperar la tanda»** en el
  lote.
- Al pulsarlo se aborta la petición htmx y se pide un aviso a
  `GET /ui/wishlist/aviso-cancelado` o `GET /ui/wishlist/aviso-cancelado-lote`, que se pinta fuera
  de la fila del indicador para que no desaparezca al ocultarse este.
- El aviso de una búsqueda dice: qué dejó de esperar el navegador, que ZascArr puede seguir
  consultando las fuentes y actualizar la fila, que **no se ha enviado nada al programa de
  descargas** (solo ocurre al confirmar un candidato), que los resultados no se guardan y que hay
  que actualizar Deseados y volver a buscar.
- El de la tanda añade que el servidor puede seguir con los deseos ya empezados (hasta 8) y que los
  que no haya empezado no se buscan.
- El botón de la tanda no se deshabilita con la petición (`hx-disable="find #boton-buscar-lote"`):
  el submit se deshabilita, el de dejar de esperar no.

## 4. Pruebas

- `tests/test_web_wishlist_lote.py`:
  - la barra de lote tiene formulario, submit, botón de dejar de esperar, objetivo del aviso y
    `htmx:abort` sobre el formulario;
  - el botón de «Buscar ahora» pide el aviso y aborta la búsqueda; ya no queda el texto «lo ya
    enviado»;
  - los dos avisos (búsqueda y tanda) dicen qué sigue, que no se envía al programa de descargas y
    que los resultados no se guardan;
  - `buscar-ahora` y `buscar-lote` **no llaman** a `send_manual_candidate` (no envían nada).
- Las pruebas son de contrato HTML con `TestClient` y dobles. **No** hay Prowlarr, foro ni
  Transmission reales: esa prueba es la del PO en la Pi (como en
  `uxa13-prueba-en-la-pi.md`). Tampoco hay móvil real ni lector de pantalla.

## 5. Límites

- La búsqueda puede seguir en el servidor después de que el navegador deje de esperar; el aviso no
  la detiene. Para detenerla de verdad haría falta cancelación cooperativa, otra historia.
- La marca de intento puede hacer que el ciclo automático espere; es el comportamiento actual y no
  se cambia aquí.
- Sin migración, sin dependencias nuevas y sin JavaScript nuevo: htmx y los endpoints de aviso.
