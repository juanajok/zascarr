# Benchmark previo — LECUX3 (precarga)

- **Historia:** [#1070](https://github.com/juanajok/zascarr/issues/1070); épica #1067.
- **Fuente:** `docs/design/benchmark-BL-LEC-mercado-lectores-2026.md` (revisión 2026-11-17).

## Lo que dice el benchmark

La ficha clasifica la precarga como **IGUALAR** del mercado, pero **no midió el comportamiento
interno de precarga de cada app**: sus fichas se centran en OPDS, formatos, sync, filtros y
modos de lectura. Por tanto, aquí **no se atribuye a Kavita, Komga, Panels, Chunky, etc. una
implementación concreta no verificada**. Lo único medido es el coste local de servir una página
en la Pi: **0,7–2 ms** por página (LEC0), con `Cache-Control: private` y `ETag`.

## Decisión

Se implementa la precarga como **mejora opcional**:

- `new Image()` con la **misma URL** de página, para reutilizar la caché HTTP privada;
- máximo **2** imágenes en vuelo (la pareja);
- nunca fuera de `[1, total]`;
- no se precarga mientras el CBR no está listo (el `lector.js` sale por la rama de `/estado`);
- sin peticiones nuevas desde el servidor ni cambios de contrato.

No se copia una técnica de una app concreta: es la forma mínima de conseguir el objetivo sin
dependencias ni cambios en el servidor.

## Verificación prevista

- Node/DOM: pide exactamente la siguiente, no pide fuera de rango, no duplica y recalcula al
  cambiar de modo/sentido.
- Chrome real: comprobar peticiones de página y que la página visible no cambia hasta que la
  siguiente está cargada.
- Pi: p50/p95 del cambio de página y RSS; la precarga no debe lanzar `unar` de nuevo.
- **NOT RUN:** medición por app y dispositivo táctil físico; no se convierten en PASS.
