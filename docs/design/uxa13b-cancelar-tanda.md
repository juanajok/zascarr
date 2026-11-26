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
  el coleccionista elija. No toca Transmission ni aMule. En la búsqueda manual, solo
  `send_manual_candidate` (el «Sí, descargar» de un candidato concreto) envía al cliente; el ciclo
  automático tiene su propio `_send` y puede enviar por su cuenta.
- Lo que queda registrado si la búsqueda termina: el estado final (`WANTED`, o `last_error` con el
  motivo), la marca `last_searched_at` y, en items de política, el commit corto de esa marca. Los
  candidatos del preview **no se persisten**: son HTML de la respuesta.
- La tanda no tiene ninguna comprobación de cancelación en el bucle; si el navegador deja de
  esperar, el servidor puede seguir con la tanda completa (hasta 8), incluidos los deseos que aún
  no había empezado.

### 2.2 Qué hace htmx al abortar

`htmx.trigger('#boton-buscar-…', 'htmx:abort')` (y el equivalente sobre el formulario de la tanda)
aborta la petición **del navegador**. No hay una señal al servidor que detenga el handler.

Medido con uvicorn **0.54.0** y un endpoint lento de 1,5 s: el cliente abrió la conexión, pidió
`/slow`, cerró el socket a los 0,3 s y la tarea del servidor siguió hasta escribir su marca a los
1,5 s. Es el mismo mecanismo ASGI que usan las rutas reales, aunque la prueba no ejecuta Prowlarr
ni el foro. Si el proceso se apaga o el proxy cancela la tarea, la transacción se revierte; por eso
el aviso dice «puede seguir», no «sigue siempre».

Consecuencia práctica: tras dejar de esperar, la fila puede actualizarse en el servidor (motivo o
marca) y el navegador no lo sabrá hasta actualizar Deseados. La búsqueda manual puede consumir la
ventana de Prowlarr/foro y la marca de intento; esa búsqueda no envía a descargas. El ciclo
automático, que corre aparte, sí puede enviar por su cuenta.

### 2.3 Qué no pasa

- Esta búsqueda/tanda no envía nada a Transmission ni a aMule: en la vía manual, el envío solo
  ocurre después de «Sí, descargar». El ciclo automático puede enviar por su cuenta.
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
  consultando las fuentes y actualizar el estado del deseo, que **esta búsqueda no envía nada al
  programa de descargas** (en la vía manual, el envío solo ocurre al confirmar un candidato; el
  ciclo automático puede enviar por su cuenta), que los resultados no se guardan y que hay que
  actualizar Deseados y volver a buscar. También indica dónde mirar si aparece algo nuevo:
  «Descargas en curso» o Transmission/aMule.
- El de la tanda añade que el servidor puede seguir con la tanda completa (hasta 8), incluidos los
  deseos que aún no había empezado.
- El botón de la tanda no se deshabilita con la petición (`hx-disable="find #boton-buscar-lote"`):
  el submit se deshabilita, el de dejar de esperar no.

## 4. Pruebas

- `tests/test_web_wishlist_lote.py`:
  - la barra de lote tiene formulario, submit, botón de dejar de esperar, objetivo del aviso y
    `htmx:abort` sobre el formulario;
  - el botón de «Buscar ahora» pide el aviso y aborta la búsqueda; ya no queda el texto «lo ya
    enviado»;
  - los dos avisos (búsqueda y tanda) dicen qué sigue, que esta búsqueda/tanda no envía al programa
    de descargas, que el ciclo automático puede enviar y que los resultados no se guardan;
  - `buscar-ahora` y `buscar-lote` **no llaman** a `send_manual_candidate` (no envían nada);
  - con un `Request` cuyo `receive` devuelve `http.disconnect`, `buscar_ahora` sigue buscando,
    `buscar_lote` recorre todos los deseos y `enviar_candidato` puede completar el envío. Es un
    doble de cliente a nivel ASGI: fija el comportamiento del handler, no el de htmx.
- La medición con uvicorn 0.54.0 es manual (ver §2.2): no se ejecuta en la suite porque necesita un
  servidor real y un socket que se cierra a mitad. La suite usa `TestClient` para el contrato HTML y
  el doble ASGI para la desconexión. **No** hay Prowlarr, foro ni Transmission reales: esa prueba es
  la del PO en la Pi (como en `uxa13-prueba-en-la-pi.md`). Tampoco hay móvil real ni lector de
  pantalla.

## 5. Límites

- La búsqueda puede seguir en el servidor después de que el navegador deje de esperar; el aviso no
  la detiene. Para detenerla de verdad haría falta cancelación cooperativa, otra historia. La tanda
  puede continuar con todos los deseos seleccionados (hasta 8), no solo con los ya empezados.
- El ciclo automático corre aparte y puede enviar a descargas por su cuenta; la marca de intento
  puede hacer que espere. Es el comportamiento actual y no se cambia aquí.
- Sin migración, sin dependencias nuevas y sin JavaScript nuevo: htmx y los endpoints de aviso.
