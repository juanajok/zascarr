# Benchmark previo — LECUX4 (errores de preparación)

- **Historia:** [#1071](https://github.com/juanajok/zascarr/issues/1071); épica #1067.
- **Fuente:** `docs/design/benchmark-BL-LEC-mercado-lectores-2026.md` y revisión de las apps del
  benchmark (2026-11-18).

## Lo que se puede afirmar

La ficha de mercado compara lectores en formatos, modos, OPDS, sync y lectura, pero **no mide el
flujo concreto de error de preparación de un CBR** en Kavita, Komga, Panels, Chunky, YACReader,
CDisplayEx, Perfect Viewer, etc. Por tanto, no se les atribuye un diseño de error no comprobado:
se marca **NOT RUN** y se resuelve con los invariantes propios del proyecto.

## Decisión local

- Mantener la pantalla sobre el cascarón inmersivo de LECUX6.
- Mostrar el motivo en llano, con `role="alert"`.
- Ofrecer **Reintentar** (consulta explícita) y **Volver al número**.
- No recargar en bucle: el sondeo se detiene al recibir `error` o al agotar el máximo acotado.
- Reutilizar los motivos que ya devuelve LEC4 (`services/cache_lectura.py`) y el timeout del servidor;
  no se cambian topes, cuota ni extracción.
- Sin dependencias nuevas ni peticiones adicionales de página.

## Verificación

- Node/DOM: error detiene el sondeo, muestra motivo y `Reintentar`; `listo` recarga una vez.
- Navegador real con un CBR que falle si hay uno disponible; si no, **NOT RUN** separado.
- Textos revisados para no incluir códigos de salida, rutas ni nombres internos.
