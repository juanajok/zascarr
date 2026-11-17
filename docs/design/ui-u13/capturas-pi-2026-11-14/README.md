# Capturas de U13 en la Pi — 2026-11-14

| | |
|---|---|
| **Qué es** | Render real de las tres hijas de U13 sobre la app desplegada en la Pi. Complementa (no sustituye) la verificación local de `verificacion-navegador-u13a-u13b-2026-10-22.md` y `verificacion-u13c-2026-10-23.md`. |
| **SHA de la Pi** | `f0d6bd99` (merge de #816); `status: healthy`, versión 1.15.1 |
| **Cuándo** | 2026-11-14, 17:40–17:45 (Europe/Madrid) |
| **Entorno** | Chrome headless, sesión real, datos reales de la biblioteca del PO |
| **Tamaños** | Escritorio 1280×900 · Móvil 390×844 |

| Archivo | Qué enseña |
|---|---|
| `u13a-carpetas--escritorio-1280x900-claro.png` | U13a: recuentos (579 en 174 carpetas + 77 sueltos; 665 pendientes visibles), orientación y paginación («Carpetas 1–50 de 179»), tarjetas con «Elegir la serie de esta carpeta». |
| `u13a-carpetas--movil-390x844-claro.png` | U13a en móvil, sin desbordamiento horizontal (`scrollWidth == innerWidth == 390`). |
| `u13a-carpetas--escritorio-1280x900-oscuro.png` | U13a con tema nocturno. |
| `u13b-sueltos--escritorio-1280x900-claro.png` | U13b: «Pendientes sueltos», «Sueltos 1–50 de 77», solo lectura y aviso de que desde ahí no se asigna ni se ignora; casos «Sin serie candidata guardada». |
| `u13b-sueltos--movil-390x844-claro.png` | U13b en móvil, sin desbordamiento. |
| `u13c-asistente--escritorio-1280x900-claro.png` | U13c: apertura del asistente desde una tarjeta de carpeta, pasos «Elegir la serie → Revisar los archivos → Vincular», aviso de que abrir no consulta fuentes ni vincula nada y estado de la carpeta. |

**Sin escrituras:** no se pulsó «Vincular» ni se confirmó nada; abrir el asistente es de solo lectura y no crea series ni vincula archivos.
