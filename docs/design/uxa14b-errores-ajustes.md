# UXA-14b · Los errores de Ajustes, junto al campo

**Historia:** [#1257](https://github.com/juanajok/zascarr/issues/1257) · **Origen:** UXA-14
([#1131](https://github.com/juanajok/zascarr/issues/1131)), tercer criterio · **Fecha:** 2026-11-24
· **Estado:** implementación en rama; pendiente de la pasada de SecOps (§5.8 de `CLAUDE.md`).

## 1. Problema

Los errores de validación de Ajustes se pintaban todos en un hueco `aria-live` al final de la
tarjeta (`#resultado-<tarjeta>`), lejos del control que los causaba. En una tarjeta con varios
campos, la persona tenía que releerla para saber cuál corregir; con dos errores no había resumen ni
orden de foco. UXA-14 dejó el índice y los destinos estables de la pantalla; esto es el tercer
criterio, que quedó como follow-up.

## 2. Inventario de validaciones (2026-11-24)

Rutas de `web/ajustes.py` y lo que devuelven hoy. «Campo» es el control que causa el error, no el
hueco de resultado.

| Ruta | Qué valida | Campo(s) | Estado en UXA-14b |
|---|---|---|---|
| `POST /guardar/avisos` | tipo conocido; URL http(s) con host (salvo Telegram) | `webhook_type`, `webhook_url` | **Cubierta.** Dos errores posibles: resumen A1 y los dos mensajes junto a su control |
| `POST /guardar/blog` | dirección pública y del conector; activar sin dirección | `blog_feed_url` | **Cubierta.** Un error: foco en la dirección, sin resumen |
| `POST /guardar/nombres` | preset conocido | `naming_preset` | **Cubierta.** Un error: foco en el selector |
| `POST /guardar/transmission` | carpeta de descargas absoluta del host, sin `..` | `transmission_download_dir` | **Cubierta.** Un error: foco en la carpeta |
| `POST /guardar/foro` | dirección base http(s), sin credenciales, query ni fragmento | `forum_url` | **Cubierta.** Un error: foco en la dirección; la URL visible nunca lleva credenciales ni `?s=` |
| `POST /guardar/seguridad` | modo, usuario, contraseña, contraseña actual, dirección | varios | **Fuera de este PR.** BL-OPS3: la contraseña actual y las nuevas tienen su propio contrato OOB (`_campos_contrasena.html`) y §5.8 exige la pasada de SecOps. No se mezcla con esa regla |
| `POST /guardar/raices`, `POST /raices/crear`, `.../{id}/habilitar`, `predeterminada`, `borrar` | validación del servicio de discos | `path`, `name` en la tarjeta «Discos» | **Fuera de este PR.** No es una integración y usa un formulario propio; queda como follow-up explícito |
| `POST /guardar/comic-vine`, `metron` | no valida en guardar (solo secreto) | — | Sin error de campo que mover |
| `POST /guardar/prowlarr` | no valida en guardar | — | Sin error de campo. El fallo de `GET /prowlarr/indexers` es conexión/configuración, no validación de un control |
| `POST /guardar/prowlarr-indexers` | no valida (ids) | — | Sin error de campo |
| `POST /guardar/amule` | no valida en guardar | — | Sin error de campo |
| `POST /guardar/fuentes`, `importacion`, `compartidos` | no valida | — | Sin error de campo |
| `POST /guardar/calidad`, `actualizar-biblioteca` | valores fuera de la lista caen a un valor seguro, sin error | — | No hay error que colocar; comportamiento actual |
| `POST /probar/*` | mayoría: conexión, espera, login o resultado del servicio; no validación del formulario | — | **Fuera de este PR.** El resultado de una prueba no es un error de campo; la excepción son las mismas comprobaciones de `probar/avisos` y `probar/foro`, que hoy siguen en su región de prueba. Se puede unificar en un follow-up si el PO lo pide |

## 3. Contrato de error

Se reutiliza el patrón A1 de la app, ya probado en las fichas de edición:

- `errores`: diccionario `campo → mensaje`. Solo los campos con error entran en `orden_campos`.
- `ui.resumen_errores(errores, orden, id_titulo)`: con **dos o más** errores, al principio del
  formulario, `role="alert"`, `tabindex="-1"` y `autofocus`, con un enlace a cada campo. El tercer
  argumento es nuevo y permite un `id` único por tarjeta (`resumen-errores-avisos`); sin él se
  conserva el `id` de siempre para las fichas.
- `ui.invalido(errores, campo, orden)`: en el control, `id="campo-<campo>"`,
  `aria-invalid="true"`, `aria-describedby="error-<campo>"` y, si es el **único** error,
  `autofocus`. El texto va en un `<span class="campo-error" id="error-<campo>">` junto al campo.
- Con un solo error no hay resumen: el foco va al campo y su descripción lo anuncia.

## 4. Cómo se repinta sin perder el formulario

No se sustituye la tarjeta ni el formulario: se sustituye **solo el bloque de campos**, fuera de
banda.

1. Cada tarjeta envuelve sus campos en `<div id="campos-<tarjeta>">` e incluye un parcial
   `_ajustes_campos_<tarjeta>.html`. Las acciones (`Guardar`, `Probar conexión`) y el hueco
   `#resultado-<tarjeta>` quedan fuera.
2. La respuesta normal va al hueco de resultado (`hx-target="#resultado-<tarjeta>"`) y, además,
   incluye `<div id="campos-<tarjeta>" hx-swap-oob="true">…</div>`. htmx sustituye el bloque de
   campos con los valores enviados y los errores; el botón que tenía el foco no se sustituye.
3. En un error, el `autofocus` del resumen (dos o más) o del campo (uno) lleva el foco al sitio
   correcto. En un guardado válido, el bloque se repinta sin errores y el foco sigue en el botón.
4. **Valores válidos:** el bloque repintado conserva lo enviado en los campos no secretos (por
   ejemplo, la URL válida de Avisos si el error es el tipo, o el nombre del blog si falla la
   dirección).
5. **Secretos:** el token de Avisos, la contraseña de Transmission y la del Foro **no entran en el
   contexto**; su campo se repinta vacío y solo cambia el placeholder («ya configurada — deja en
   blanco para no cambiarla»). En la URL del Foro se usa `url_de_foro_visible`, que quita
   credenciales y query.
6. La tarjeta de Seguridad no se toca: mantiene su intercambio OOB de contraseñas y su regla de
   contraseña actual (BL-OPS3).

## 5. Pruebas

En `tests/test_web_ajustes.py`, clase `TestUxa14bErroresJuntoAlCampo`:

- las cinco tarjetas tienen su `#campos-<tarjeta>` en la carga inicial;
- Avisos con dos errores: `aria-invalid`, `aria-describedby`, los dos textos junto a sus campos,
  resumen con enlaces y `autofocus`; los valores válidos (chat ID) siguen;
- Avisos con un error: campo con `autofocus` y **sin** resumen;
- el token secreto no vuelve en la respuesta (ni el valor ni un `value`);
- Blog: error junto a la dirección, nombre y casilla conservados;
- Nombres: error en el selector, casilla conservada;
- Transmission: error en la carpeta, dirección y usuario conservados;
- Foro: error en la dirección y ni usuario ni `?s=` de la URL vuelven;
- guardado válido: bloque repintado sin `aria-invalid` ni resumen y resultado «guardado».

Las pruebas son de contrato HTML con `TestClient` y `FakeSession`. **No hay navegador real, lector de
pantalla ni teclado humano en esta entrega**: el `autofocus` de un fragmento OOB y el anuncio del
resumen se comprobarán en navegador. Tampoco se ha ejecutado la suite completa ni la Pi.

## 6. Límites y pendientes

- **SecOps:** `web/ajustes.py` está en la lista de §5.8; la rama **no se fusiona** hasta el dictamen
  del SHA final. No se toca `services/seguridad.py` ni la regla de la contraseña actual.
- **Seguridad** y **Discos**: fuera de este PR, con su propio contrato y pruebas.
- **Probar**: los resultados de conexión/prueba no se convierten en errores de campo; queda
  documentado arriba. Si el PO quiere unificar `probar/avisos` y `probar/foro`, es un follow-up
  pequeño sobre el mismo patrón.
- **Sin migración, sin dependencias nuevas, sin JavaScript nuevo:** htmx y los macros existentes.
- **Probar conexión** sigue usando lo que se ve en el formulario; el OOB no cambia esa regla.
