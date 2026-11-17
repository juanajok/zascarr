# Especificación — BL-DUP3: resolver una carpeta repetida o contenida (#266)

**Estado:** implementada; pendiente de verificación manual en navegador sobre una biblioteca real.

## Contrato

Para una pareja de carpetas del informe de auditoría, la pantalla muestra:

- archivos comunes con **contenido idéntico** (candidatos a apartar);
- archivos comunes con **contenido distinto** (no se tocan; se remiten a BL-R6);
- archivos que solo están en A o solo en B (no se tocan nunca).

La persona elige qué carpeta se queda; ninguna opción viene preseleccionada. De la carpeta
descartada se apartan **solo** los comunes idénticos, uno por uno, con la vista previa, el
token, la cuarentena, el catálogo y el deshacer de BL-DUP1. Si la carpeta descartada queda
vacía de verdad (sin subcarpetas ni archivos que no se hayan apartado), se ofrece apartarla
también; nunca se borra.

## Invariantes

- Solo se comparan archivos directos de cada carpeta; no se fusionan carpetas ni se mueven
  archivos que solo estén en un lado.
- Un común con contenido distinto no se toca aunque comparta nombre.
- La comprobación de identidad se hace antes de cada vista previa y antes de mover.
- El catálogo no crea filas nuevas; cada grupo usa la mecánica de BL-DUP1.
- La carpeta vacía se mueve a la cuarentena y su operación se puede deshacer sin sobrescribir.
- Sin migración: se reutilizan `apartado_operaciones.grupos` y la columna `modo`.

## Pruebas

- `tests/test_carpetas_duplicadas_pg.py`: subconjunto perfecto, solape parcial, anidamiento,
  comunes distintos, archivos solo en un lado, carpeta vacía y deshacer.
- `tests/test_web_carpetas_dup3.py`: detalle sin preselección, vista previa y confirmación.
- CI completa con PostgreSQL y sistema de ficheros real.

## Límites

- No se ejecuta sobre la biblioteca real del PO.
- No se implementa vaciar la cuarentena (D2 de ADR 0017).
- No se fusionan carpetas ni se renombra.
