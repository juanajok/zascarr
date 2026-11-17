# Guía de capturas sin obra protegida (OCTA-E6)

- **Estado:** aceptada por el PO (2026-11-17).
- **Historias:** [#953](https://github.com/juanajok/zascarr/issues/953), [#937](https://github.com/juanajok/zascarr/issues/937)
  y decisión de capturas de [#922](https://github.com/juanajok/zascarr/issues/922).
- **Objetivo:** que el repo público no gane capturas nuevas con portadas comerciales ni datos de
  una biblioteca privada.

## Regla

Una captura que se vaya a guardar en `docs/design/` debe usar **solo material libre o el marcador
propio**:

1. **Marcador de portada** (`ui.portada`): es la opción por defecto. No muestra ninguna imagen de
   terceros y conserva el hueco visual.
2. **Biblioteca de prueba con material de dominio público** (imágenes libres o sintéticas de
   color/trama) y nombres inventados. No uses la biblioteca real del PO.
3. Si la pantalla necesita una portada para explicar la UI, se sustituye por una **imagen
   sintética** generada para la captura (bloques de color, portada falsa con texto «muestra») y se
   indica en el pie de la captura.

Nunca:

- capturas de la biblioteca real con carátulas comerciales;
- títulos/autores reales de la biblioteca privada como dato de ejemplo;
- capturas hechas contra un servidor con la colección real sin sustituir las portadas.

## Procedimiento

1. Prepara una instancia/demo con datos sintéticos o el marcador. Si se usa la Pi, no se enseña la
   biblioteca real.
2. Fija el ancho de la captura (1280 px de escritorio, 375/320 px de móvil) y el tema.
3. Haz la captura solo de la pantalla necesaria, no de datos personales.
4. Revisa que no haya títulos reales, rutas privadas, correos, tokens ni portadas comerciales.
5. Guarda la imagen con nombre descriptivo y enlázala desde el informe. Las capturas nuevas del
   repo deben seguir la decisión de A3: **no se añaden capturas nuevas salvo excepción justificada**;
   la evidencia va preferentemente a adjuntos/releases.

## Lo ya existente

Las capturas anteriores se rigen por la decisión de A3 y la revisión de E2; esta guía **no**
justifica las antiguas ni autoriza añadir más. Si una captura antigua se reutiliza, se revisa
primero con esta misma regla.
