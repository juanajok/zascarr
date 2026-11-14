# U13 en la Pi — verificación de navegador (2026-11-14)

> **Alcance.** Render real de U13a/b/c en la app desplegada en la Pi. **No** ejecuta vinculaciones, no
> crea series y no mide rendimiento. Complementa la evidencia local de las tres historias; no la
> sustituye ni cambia sus cierres.

| Dato | Valor |
|---|---|
| **SHA** | `f0d6bd99` en la Pi (merge de #816); versión 1.15.1, `healthy` |
| **Fecha** | 2026-11-14, 17:40–17:45 (Europe/Madrid) |
| **Método** | Chrome headless con sesión real, `Page.captureScreenshot`; comprobación de `scrollWidth`/`innerWidth` y de textos en el DOM |
| **Datos** | Biblioteca real (656 por revisar: 579 en 174 carpetas + 77 sueltos) |
| **Capturas** | `capturas-pi-2026-11-14/` (README con detalle) |

## PASS

| Hija / criterio | Resultado |
|---|---|
| **U13a** recuentos y orientación | «656 por revisar: 579 en 174 carpetas + 77 sueltos. 9 con serie sugerida, aparte. 665 pendientes visibles.» Visible y legible; miga «Por revisar › Pendientes por carpeta». |
| **U13a** paginación | «Carpetas 1–50 de 179» con enlaces de página; la primera página carga en el servidor. |
| **U13a** móvil y tema | 390 px: `scrollWidth = innerWidth = 390`, sin desplazamiento horizontal; captura en claro y oscuro (1280). |
| **U13b** cola de sueltos | «Pendientes sueltos», «Sueltos 1–50 de 77 · 77 de 656 por revisar»; aviso de solo lectura («desde aquí no se asigna, crea, mueve ni ignora nada»); casos «Sin serie candidata guardada. No se deduce ninguna serie…». |
| **U13b** móvil | 390 px sin desbordamiento horizontal. |
| **U13c** apertura del asistente | Desde la tarjeta se abre `/ui/pendientes/carpetas/asistente?clave=…` con los tres pasos, aviso «no se crea ninguna serie ni se vincula ningún archivo» y el recuento de la carpeta; sin jerga visible (`token`, `series_id`, `payload`, `endpoint`, `UUID`, `hash`, `cursor`). |
| **No escrituras** | No se pulsó «Vincular» ni «Confirmar»; abrir el asistente no escribe. |

## FAIL / hallazgo menor

- **Terminología residual:** el asistente dice «**Registros** en esta carpeta 4» en un paso de la cola de Por revisar. El glosario U7 reserva «registro» para la fila técnica y pide «pendientes» en la cola; no se corrigió aquí porque U13 está cerrada y este trabajo es verificación. Candidato a limpieza posterior (junto con «catálogo» de Auditoría).

## NOT RUN

- **Lector de pantalla** (Orca/NVDA/VoiceOver) y prueba de **cinco segundos**: no ejecutadas.
- **Rendimiento en la Pi**: no se midió latencia/p95; solo render y orientación.
- **Confirmación real de una vinculación** en navegador: no ejecutada para no escribir en la biblioteca del PO; el comportamiento está cubierto por las pruebas de aceptación de #289.
