# Aceptación integral de M3 — «Asistente completo» (#106)

> **Fecha:** 2026-11-05. **Base:** `main` `6cde4ab`. **No reimplementa:** acredita el recorrido completo del
> asistente de la rebanada 2e sobre el contrato ya entregado. Hijas: #118, #119 y #120; mejoras #206/#207.

## 1. Hijas y evidencia

| Historia | Issue | Entrega | Estado al cerrar | Evidencia |
|---|---|---|---|---|
| MIT-M3-US01 Descubrir o crear desde un grupo | #118 | PR #185 (`8473ad3`) | Implementada, fusionada; se cierra con esta aceptación | `tests/test_asistente_carpetas_pg.py` (36) |
| MIT-M3-US02 Revisar selección y números | #119 | PR #186 (`50981c6`) | Cerrada; se mantiene | `tests/test_asistente_vinculacion_pg.py` (31), `…_masivo_pg.py` (29) |
| MIT-M3-US03 Confirmar y resolver pendientes | #120 | PR #187 (`80014ce`) | Implementada, fusionada; se cierra con esta aceptación | `tests/test_asistente_confirmar_pg.py` (23) |
| BL-U19 De la carpeta a sus archivos | #206 | PR #219 | Hecha; mejora del recorrido | Pruebas y referencia de recuperación |
| BL-U20 Marcar todos y textos | #207 | PR #212 | Hecha; mejora de revisión | Pruebas de marcado masivo y motivos |

La deuda de #196 no se marca resuelta por esta aceptación: se revisó que #206/#207 cubren sus hallazgos de recorrido y
textos, no el resto de la auditoría.

## 2. Matriz criterio → prueba de las hijas

| Historia | Criterios | Clases de prueba |
|---|---|---|
| #118 | 1–7 | `TestCriterio1Apertura`, `…2Busqueda`, `…3SinPreseleccion`, `…4Eleccion`, `…5ErroresParciales`, `…6Manual`, `…7Senales` (`test_asistente_carpetas_pg.py`) |
| #119 | 1–2 (entrada/página), 3 (número), 4 (ausente/ambiguo), 5 (repetidos), 6 (existentes), 7–8 (selección), 9 (renovación), 10 (sin efectos), 11 (borrador) | `TestCriterio1y12Entrada`, `…2Paginas`, `…3Numero`, `…4AusenteYAmbiguo`, `…5Repetidos`, `…6Existentes`, `…7y8Seleccion`, `…9Renovacion`, `…10SinEfectos`, `…11Borrador` (`test_asistente_vinculacion_pg.py`) |
| #120 | 1 (token), 2 (consentimiento), 3 (resultado), 4 (parcial), 5 (reintento), 6 (pendientes), 7 (accesibilidad), 8 (fallos) | `TestCriterio1Token`, `…2Consentimiento`, `…3Resultado`, `…4Parcial`, `…5Reintento`, `…6Pendientes`, `…7Accesibilidad`, `…8Fallos` (`test_asistente_confirmar_pg.py`) |

La correspondencia es por clase; el detalle de cada `test_*` está en el fichero citado. #119 ya estaba cerrada; esta matriz
solo acredita que la aceptación integral no la reabre.

## 2. Plan de aceptación — resultado

| # | Paso del plan de #106 | Resultado | Evidencia |
|---|---|---|---|
| 1 | Abrir un grupo de Pendientes con contexto, sin consultas externas automáticas | **PASS** | Tests de apertura sin red ni escrituras; navegador local: carpeta y 3 registros |
| 2 | Elegir serie local o recorrer candidata/alta, con consentimientos separados | **PASS** | #118 (36 pruebas); alta manual #189; navegador: serie local «Flash (1987)» |
| 3 | Llegar a revisión con clave del grupo y serie local válida | **PASS** | Revisión con `clave=Comics/Flash (1987)` y `series_id` local; no se sustituye por id externo |
| 4 | Revisar página, bloqueos y renovación de la vista previa | **PASS** | 60 pruebas de revisión/masivo; la vista inicial no trae nada marcado; «Marcar todos» renueva y emite token |
| 5 | Confirmar solo lo revisado y presentar el resultado acreditado | **PASS** | Flujo real: 3 marcados → confirmar → **3 vinculados**, **1** operación, resultado con enlace de 24 h |
| 6 | Cancelar, volver, fallo y recuperación sin repetir escrituras | **PASS** | `test_asistente_confirmar_pg`, `test_vinculacion_recuperacion_pg`, resultado incierto B-1 (#116) |
| 7 | Teclado, móvil y temas | **PASS parcial + NOT RUN** | PR #185/#187: teclado, 375 px y claro/oscuro; los propios PR declaran NOT RUN el móvil físico y el lector de pantalla |
| 8 | Reconciliar #118/#120/#206/#196/#207 y B14 | **PASS** | Esta nota; B14 actualizada a Hecha en `docs/BACKLOG.md` |

## 3. Pruebas ejecutadas

- **127 pruebas** de los cuatro ficheros M3 (`test_asistente_*_pg.py`) con PostgreSQL 15 real: **127 passed**.
- **600 pruebas** de la selección de 13 ficheros usada en la revisión (`test_asistente_*`, `test_vinculacion_*`,
  `test_tokens_vinculacion*`, `test_revision_carpetas_pg`, `test_web_carpetas_pg`, `test_alta_sin_carpeta_api_pg`) con
  PostgreSQL 15 real: **600 passed, 0 fallos**. No es «toda la suite»: es esa selección; el número 127 son 119 funciones
  más 8 parametrizaciones de los cuatro ficheros M3.
- **Prueba de recorrido manual** en navegador local (Chrome 156; base desechable, datos sintéticos, fuentes apagadas):
  carpeta → asistente → serie local → revisión sin marcas → «Marcar todos» → confirmar → resultado.
  Comprobado en base: **3 archivos vinculados**, **1** fila en `vinculacion_operaciones`, **1** serie y **3** issues
  (no se creó una serie nueva) y **las rutas de los archivos no cambiaron**.

## 4. Límites declarados (NOT RUN)

- Fuentes reales y biblioteca real: no se han ejecutado; las pruebas usan fuentes simuladas.
- La Pi real, el móvil físico y el lector de pantalla: **NOT RUN** en esta revisión. La evidencia de teclado/móvil/temas
  es la de las PR #185/#187, no una nueva pasada.
- Despliegue: no se ha desplegado nada nuevo desde esta revisión.

## 5. Decisión

Se acepta el recorrido completo de M3 y se cierran #118, #120 y #106. #119 ya estaba cerrada. B14 pasa a Hecha con la
nota de mecanismo en el backlog. Cualquier fuente real, medición en la Pi o lector de pantalla queda como verificación
posterior, no como PASS de esta aceptación.
