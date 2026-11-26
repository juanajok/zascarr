# Contrato de biblioteca e interfaz

**Estado: migración en curso.** Reglas trasladadas desde la guía vigente. La copia de `CLAUDE.md` se conserva: trasladar **no** retira la norma hasta aprobación expresa. Ante discrepancia, manda la guía.

## PRE-04 — Sin hotlinking en la interfaz

Las portadas se sirven desde caché local o desde la extracción del propio CBZ; **nunca** un `src` externo directo en la interfaz. La cascada está en `web/series.py::portada`. Es una regla permanente desde el 2026-09-22.

## PRE-31 — Caché local-first y revalidación

Todo lo que se puede cachear (portadas, metadatos, datos de pantalla) se escribe a disco o base de datos y se sirve local después.

- Los endpoints de imagen responden `Cache-Control: private, max-age=86400` con `ETag` por fecha de modificación (`utils/cover.py::cached_image_response`).
- `/static` responde `Cache-Control: no-cache` (`main.py::RevalidatedStaticFiles`): el navegador revalida con el `ETag` y recibe un 304 vacío si nada cambió. Sin eso, tras `update.sh` seguía pintando el CSS antiguo.

## PRE-32 — Portadas de archivo, de fuente externa y lectura de RAR

- `covers/v3/<id>.jpg` guarda **solo** portadas extraídas de un archivo; la portada externa va a `covers/externa/`.
- Un `.cbr` que en realidad es RAR se lee con `unar` (`utils/lector_rar.py`): por subproceso acotado, **uno a la vez**, solo en la etapa `runtime` de la imagen.
- Un fallo atribuible al archivo se recuerda en `covers/v3/fallos/<file_id>.json` —sin ruta ni nombre— hasta que ese archivo cambie, para no repetir el coste.

Detalle completo en [especificación BL-PORT3](../docs/design/especificacion-BL-PORT3.md).

## PRE-36-1 — Las cifras del Inicio cuadran

La frase de entrada desglosa lo registrado en partes que **suman el total** (`services/inicio.py::Desglose`, una sola consulta; «por revisar» con el filtro de la lista). Lo referido al disco va aparte, con su fecha y el motivo de la diferencia (copias idénticas que el registro dejó fuera). Un paso no añade cifras sueltas.

## PRE-37 — El sistema de diseño se consulta y su deuda no se copia

### PRE-37-1 — Consultar antes de pintar o tocar estilos

Antes de pintar una pantalla o tocar `web.css` hay que leer el sistema de diseño ([`docs/design/sistema-de-diseno-zascarr.md`](../docs/design/sistema-de-diseno-zascarr.md), con sus muestras visuales en PDF). Los tokens y las macros (`ui.*`, `web/componentes.py`) mandan sobre el aspecto heredado.

### PRE-37-2 — La deuda declarada no se replica

La revisión de la última versión del sistema deja deuda abierta (escala de texto sin tokens, grosores de borde literales, clases inexistentes, avisos sin icono ni `role`). No se copia en pantallas ni componentes nuevos.

## Límites

Este contrato no sustituye a los ADR de interfaz ni a las pruebas de accesibilidad y contraste existentes. No autoriza cambios de comportamiento de portadas, caché o diseño.
