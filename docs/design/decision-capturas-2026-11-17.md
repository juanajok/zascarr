# Decisión OCTA-A3 — capturas de `docs/design`

- **Estado:** aceptada por el PO (2026-11-17).
- **Historia:** [#922](https://github.com/juanajok/zascarr/issues/922), épica OCTA-A [#914](https://github.com/juanajok/zascarr/issues/914).
- **Datos medidos en `main`:** **178 ficheros de imagen, 30,1 MiB** bajo `docs/` (el informe
  original hablaba de 41,7 MiB porque contaba una revisión anterior).

## Decisión

1. **Se mantienen** las capturas actuales en `docs/design/` como evidencia reproducible de las
   validaciones ya cerradas. No se reescribe el historial.
2. **No se añaden capturas nuevas al repositorio.** Las próximas evidencias visuales van a
   adjuntos/releases o a almacenamiento externo; en el repo queda el informe y, si acaso, una
   captura mínima representativa.
3. **No se mueven a Releases las actuales** en esta entrega: moverlas no reduce el tamaño de un
   clon de Git sin reescribir la historia y rompería los enlaces de los informes existentes.
4. Excepción: las capturas que formen parte del **sistema de diseño publicado** (`docs/design/
   sistema-de-diseno-zascarr.pdf` y sus muestras) se conservan por ser documentación de producto,
   no solo evidencia de una tarea.

## Consecuencias

- La imagen Docker ya no las lleva (OCTA-A2), así que no afectan a la Pi.
- El repo conserva ~30 MiB en el árbol de trabajo; es el coste aceptado de mantener la evidencia.
- Si en el futuro se decide reducir el clon, la vía sería un repo de documentación o una reescritura
  de historia explícita, nunca un borrado silencioso.
