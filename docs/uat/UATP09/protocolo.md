# UATP-09 · Protocolo de validación con dispositivos y personas

**Historia:** UATP-09 / UXA-16 ([#1133](https://github.com/juanajok/zascarr/issues/1133)) · épica [#1141](https://github.com/juanajok/zascarr/issues/1141)  
**Estado:** protocolo listo para ejecutar. **No declara UATP-09 cumplida.**

## 1. Objetivo

Medir con personas y dispositivos reales que los recorridos de continuidad y recuperación se entienden y se completan: retomar tras el aviso legal, volver a la Biblioteca, leer en móvil, distinguir ediciones, usar la vista previa con teclado y recuperar una copia sin perder la instalación.

## 2. Participantes y sesiones

- **3–5 participantes** coleccionistas, coordinados con #272; al menos una persona usuaria de teclado y una de lector de pantalla.
- Sesión moderada de 45–60 min, presencial o remota; consentimiento para grabación/capturas y anonimización.
- **No** usar datos personales reales: biblioteca sintética o copia desechable; nunca credenciales, `.env` ni dumps.
- Separar en el registro **observado** (qué hizo/dijo) de **interpretación** (hipótesis del equipo).

## 3. Matriz mínima

| Entorno | Requisito | Casos |
|---|---|---|
| Escritorio 1440 y portátil 1280 | Chrome/Firefox actuales | UAT-01, 02, 05, 06/07 |
| Móvil físico 320/390 | iOS y Android, táctil | UAT-03, primer intento sin pistas, volver al número, continuar |
| Teclado | Sin ratón | UAT-05, UAT-34, foco/orden/Enter/Escape |
| Lector de pantalla | NVDA u Orca; VoiceOver en iOS | UAT-34 y UAT-36: nombres, foco, anuncios |
| Raspberry Pi | Modelo, almacenamiento, versión y documentación | UAT-30/31 con datos sintéticos y respaldos desechables |

## 4. Tareas y medidas

Por tarea registrar: **éxito/fracaso**, **primer paso**, **nº de reintentos**, **tiempo**, **comprensión del cambio** (qué cree que pasó), **incidencia** y **cita textual anonimizada**.

- **UAT-01** retomar la acción tras aceptar el aviso legal.
- **UAT-02** volver de la ficha a la Biblioteca consultada.
- **UAT-03** mostrar la barra del lector en móvil, volver al número y reabrir en la página guardada.
- **UAT-04** distinguir Flash 1987/2011 en Deseados.
- **UAT-05** consultar y apartar la vista previa con teclado.
- **UAT-06** rechazar una copia dañada sin perder la instalación.
- **UAT-07/A6** restaurar catálogo y archivos y reabrir en la página guardada.
- **UAT-31** explicar, a partir del resumen, por qué una fila añadida después de la copia quedó fuera.

## 5. Pi: rendimiento

Medir en frío y en caliente, con biblioteca grande y CBZ/CBR, y red lenta simulada: **p50/p95** de primera página, siguiente página y búsqueda. Registrar modelo, almacenamiento, versión/imagen, duración y si se usó la documentación. Comparar la misma batería después de las historias.

## 6. Evidencia

- `docs/uat/A1/`, `docs/uat/A2/`, `docs/uat/A3/`, `docs/uat/A6/` y este directorio.
- Capturas solo con consentimiento y sin datos personales; registrar versión, SHA/tag, dispositivo, navegador y fecha.
- Cada caso termina en **PASS**, **FAIL** o **NOT RUN** con motivo. Un entorno ausente no se convierte en PASS.

## 7. Criterio de cierre

UATP-09 se cierra cuando los casos obligatorios tienen evidencia ejecutada en sus entornos o el PO acepta por escrito qué NOT RUN quedan. La épica #1141 se cierra después.
