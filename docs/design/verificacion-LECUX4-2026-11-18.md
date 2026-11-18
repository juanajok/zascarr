# Verificación BL-LECUX4 — errores de preparación

- **Historia:** [#1071](https://github.com/juanajok/zascarr/issues/1071); épica #1067.
- **Código verificado:** Pi en `134e4dc`; health OK.
- **Benchmark previo:** `docs/design/benchmark-LECUX4-errores-2026-11-18.md`.

## PASS

| Comprobación | Evidencia |
|---|---|
| Acciones visibles | La pantalla de preparación pinta `Reintentar` y `Volver al número`. |
| Error | El JS detiene el sondeo al recibir `error`, muestra el motivo y lo deja en `role="alert"`. |
| Reintentar | Vuelve a consultar; no recarga en bucle si sigue en error. |
| Listo | Si el estado pasa a `listo`, recarga una vez. |
| Sin cambios de servidor | Se reutilizan los motivos/estado de LEC4; no se tocaron topes, cuota ni extracción. |
| Tests | Node/DOM (detención, reintento, listo) y plantilla; suite completa **7.931 passed**. |

## NOT RUN

- Navegador real con un **CBR que falle de verdad** (no había una muestra corrupta disponible);
  el comportamiento JS está cubierto con Node y la pantalla se sirve, pero no se declara PASS real.
- Lector de pantalla y táctil físico: **NOT RUN**.

## Cómo repetir

Con un CBR que devuelva `error` en `/ui/leer/{id}/estado`, abrir el lector: debe verse el motivo,
«Reintentar» y «Volver al número»; Reintentar no debe recargar si sigue fallando; si la
preparación termina, debe recargar una sola vez.
