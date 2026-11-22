# UATP-09 · Resultados de la primera pasada

**Fecha:** 2026-11-22  
**Base:** `origin/main` `3ce1bd5e`; Pi `HEAD=3ce1bd5e`, `health=200`.  
**Estado:** **EN CURSO — no se declara UATP-09 cumplida.** No hay sesiones con participantes, móvil físico ni lector de pantalla.

## 1. Evidencia automatizada/artefacto disponible

| Recorrido | Evidencia | Resultado |
|---|---|---|
| UATP-01 aviso legal y retorno | PR #1180, A1 y pruebas de UATP-01 | PASS de código; sesión humana NOT RUN |
| UATP-02 Biblioteca y foco | PR #1196, T14 Chrome 320/390/escritorio | PASS Chrome; móvil físico NOT RUN |
| UATP-03 lector móvil | PR #1207, T12 Chrome 320/390/568×320 | PASS Chrome; móvil físico/lector NOT RUN |
| UATP-04 Deseados homónimos | PR #1210, T-11 Chrome 320/390 | PASS Chrome |
| UATP-05 vista previa teclado | PR #1211, T9 Chrome 1440/1024/720/390 | PASS de contrato; red lenta/reduced-motion NOT RUN |
| UATP-06/07 recuperación | A6 real 25/25 checks + PR #1221 | PASS; `N-01-systemd-host` NOT RUN |
| UATP-08 resumen de recuperación | PR #1236, UAT-31 3c | PASS A–F |

## 2. Matriz UATP-09

| Entorno / caso | Estado | Motivo |
|---|---|---|
| Escritorio Chrome/Firefox | **PARCIAL** | Chrome cubierto por artefactos; Firefox y sesión moderada **NOT RUN** |
| Móvil físico 320/390 | **NOT RUN** | Sin dispositivo físico ni sesión |
| Teclado sin ratón | **PARCIAL** | Pruebas DOM/Chrome de UATP-03/05; recorrido humano **NOT RUN** |
| Lector de pantalla (NVDA/Orca/VoiceOver) | **NOT RUN** | Sin lector ni persona usuaria |
| 3–5 participantes (#272) | **NOT RUN** | Sin agenda/consentimientos |
| Pi: frío/caliente, biblioteca grande, CBZ/CBR, red lenta, p50/p95 | **NOT RUN** | No se midió; no se usó la Pi para la batería |

## 3. Bloqueos y siguientes acciones

1. Agendar **3–5 participantes** con consentimiento y separar observado/interpretado.
2. Preparar **móvil físico** iOS/Android y **lector de pantalla** (NVDA/Orca/VoiceOver).
3. Ejecutar la batería de **Pi** con fixture sintético y red lenta; registrar modelo, almacenamiento, versión y p50/p95.
4. Repetir los recorridos UATP-01…08 con **sesión nueva** y conservar primer intento + réplica.
5. Actualizar esta matriz con PASS/FAIL/NOT RUN por participante; **ningún NOT RUN se convierte en PASS**.

## 4. Criterio de cierre

No se cierra UATP-09 hasta que los casos obligatorios tengan evidencia ejecutada o el PO acepte por escrito los NOT RUN de hardware/asistencia. La épica #1141 se cierra después.
