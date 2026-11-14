# Capturas de la verificación de #205 (AC5) — 2026-11-14

> **Qué es.** Evidencia de navegador real de la aplicación **desplegada en la Pi** con los textos
> del glosario U7 aplicados (#205 BL-U18 AC5). No es una validación con usuarios ni una prueba de
> accesibilidad con lector de pantalla.

| | |
|---|---|
| **Fecha** | 2026-11-14, 16:28–16:31 (Europe/Madrid) |
| **Código desplegado** | Pi en `2d7aeb92` (merge de #804); `status: healthy`, versión 1.15.1, migración `head` |
| **Entorno** | Chrome headless, sin extensiones, sesión real de la Pi |
| **Tamaños** | Escritorio 1280×900 · Móvil 390×844 |
| **Datos** | Biblioteca real del PO (224 series, 667 pendientes); sin datos inventados |

| Archivo | Qué demuestra |
|---|---|
| `pendientes--escritorio-1280x900-claro.png` | «Pendientes que el sistema no supo clasificar», «resuelves varios pendientes», enlace «Ver los pendientes sueltos». |
| `pendientes--movil-390x844-claro.png` | Los mismos textos en móvil, sin desbordamiento. |
| `pendientes-sueltos--escritorio-1280x900-claro.png` | `<title>`/`h1` «Pendientes sueltos», error/vacío con «pendientes sueltos». |
| `pendientes-carpetas--escritorio-1280x900-claro.png` | Título «Pendientes por carpeta», miga «Por revisar › Pendientes por carpeta», «N pendientes visibles», «N pendientes» y «Ver pendientes (N)». |
| `biblioteca-filtro--escritorio-1280x900-claro.png` | Filtro «Estado de la serie» (conserva `name="coleccion"`). |
| `estado-descarga--escritorio-1280x900-claro.png` | «Descargar tebeoteca y deseados (CSV)». |

**Comprobado además por HTML servido** en la Pi: `Pendientes que el sistema no supo clasificar`,
`varios pendientes`, `Ver los pendientes sueltos`, `Pendientes sueltos`, `Pendientes por carpeta —
Por revisar`, `pendientes visibles`, `% de los pendientes`, `Estado de la serie`, `Descargar
tebeoteca y deseados`. El aviso «Estamos registrando la biblioteca» solo aparece mientras hay un
registro en curso; su texto se cubre con prueba automática, no con estas capturas.

**Excepción conservada:** el desplegable «¿De dónde salen estos datos?» de Pendientes por carpeta
mantiene «registros pendientes de verificar, no archivos confirmados» porque distingue la fila de la
biblioteca del fichero del disco.

**NOT RUN:** lector de pantalla (Orca/NVDA/VoiceOver), otros navegadores y contraste medido en
dispositivo. La captura de la ficha de serie no se incluye: `main` ya usa «Completitud» en su
encabezado (#805) y esta historia solo cambia la etiqueta del filtro de Biblioteca.
