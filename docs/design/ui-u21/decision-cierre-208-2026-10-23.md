# Ficha §13 — Decisión de cierre de U21 (#208) — propuesta sin firma

- **Feature:** #196 Auditoría de UI del 2026-10-15.
- **Historia:** #208 BL-U21, «Que Carpetas y la ficha de serie me digan en una frase qué puedo hacer».
- **Alcance de la decisión:** aceptación explícita de los límites de validación de U21 y cierre de #208.
- **Código de producto de referencia:** `origin/main` `245402e78a6357cfc79e726a4484662ba9ef8151` (U21 Carpetas y ficha, desplegado por el responsable el 2026-10-22). La prueba 39 → 44 se fusionó después en `0fb10f09` (#291), sin cambio de `src/`.
- **Responsable de la decisión:** juanajok.
- **Fecha de la propuesta:** 2026-10-23.
- **Fecha de firma:** ____________________.
- **Estado:** **propuesta, sin firma**. No cierra #208 por sí sola.

## 1. Decisión propuesta

Se propone **cerrar #208 como `Hecha`** con estos límites declarados:

1. La **prueba de cinco segundos con personas** sigue `NOT RUN`. La validación sintética con agentes (5/5 en Carpetas y 5/5 en ficha) se acepta solo como **evidencia complementaria** de comprensión de la acción principal; **no es validación con personas** y no sustituye la sesión humana.
2. El **lector de pantalla real** de Carpetas y ficha sigue `NOT RUN`; queda como deuda de #196.
3. La verificación de navegador y tema oscuro es **local** (Chromium headless, base sintética); no se presenta como validación en la Pi ni con la biblioteca real.
4. No se reescribe el DoD original de #208 para hacer encajar la evidencia. El cierre se apoya en esta ficha firmada, no en una modificación del contrato.

## 2. Qué sí está cubierto

- **Carpetas:** texto de entrada y presupuesto de 20/50; prueba `TestPresupuestoTexto` actualizada de 39 a 44 en #291 (`0fb10f09`). Navegador real en 1280/360 y teclado según #309 (`17f0da9`). Tema oscuro comprobado el 2026-10-23 en 360/1280: fondo oscuro, 50 tarjetas, 50 enlaces «Elegir la serie de esta carpeta», sin desbordamiento ni errores de consola.
- **Ficha de serie:** texto breve, política antes del listado, 360 px y teclado según #280 (`38b1f772`); capturas 1280/360 en claro/oscuro.
- **Cinco segundos sintético:** 5 agentes independientes por pantalla; Carpetas 5/5 y ficha 5/5 identifican la acción principal. Evidencia: comentario de #208 del 2026-10-23 (`https://github.com/juanajok/zascarr/issues/208#issuecomment-6360697932`).
- **CI de #291:** suite unitaria, Postgres real, Docker y pip-audit en verde; ruff informativo con los 14 hallazgos preexistentes.

## 3. Qué NO se acepta como acreditado

- Que la prueba de cinco segundos se haya hecho con personas: **no se ha hecho**.
- Que el lector de pantalla real se haya ejecutado: **no se ha ejecutado**.
- Que la comprobación de tema oscuro o de navegador sea en la Pi o con la biblioteca real: fue local y sintética.
- Que la validación sintética sea una validación con usuarios o un `PASS` humano.
- Que este cierre autorice un despliegue nuevo: el código de U21 ya está en `245402e`; cualquier despliegue posterior sigue sujeto a la ventana única de #196.

## 4. Hallazgos y erratas

- **U13b (fuera de #208):** 2/5 agentes creyeron que podían ignorar pendientes en «Archivos sueltos». Se corrige el copy en la PR #320 y se registra en #196; no se usa para cerrar #208.
- **B4 (evidencia sintética):** la respuesta B4 dijo «nueve» faltantes donde hay **7**. Se conserva la transcripción literal de la respuesta y se anota la errata; no es copy de la aplicación. El dato correcto de la ficha es 3 presentes y 7 ausentes.
- **Carpetas:** 4/5 respuestas usan «confirmar» en vez del CTA literal «Elegir la serie»; se considera comprensión suficiente de la tarea, no una cita literal.

## 5. Consecuencias si se firma

1. **#208 pasa a `Hecha`** con los límites de §1; no se declara validación con personas.
2. **#196 mantiene** las deudas de lector de pantalla real y de medición/despliegue que correspondan; #208 no las absorbe.
3. **No se autoriza ningún despliegue nuevo.** La ventana única de #196 sigue pendiente de autorización y de la medición Pi/LAN.
4. **#200** puede cerrarse cuando se cierre el despliegue de U13 o mantenerse como contenedor hasta entonces.

## 6. Evidencia

1. **#208, validación sintética:** comentario del 2026-10-23, 5/5 Carpetas y 5/5 ficha; límites declarados.
2. **#208, tema oscuro:** comentario del 2026-10-23; 360/1280, sin desbordamiento, CTA visible.
3. **#309:** `docs/design/ui-u13/verificacion-navegador-u13a-u13b-2026-10-22.md`; Carpetas en 1280/360 y teclado.
4. **#280:** `docs/design/ui-u21/verificacion-ficha-2026-10-21.md`; ficha en 1280/360, claro/oscuro y teclado.
5. **#291:** PR y CI; `TestPresupuestoTexto` 39 → 44.
6. **Esta ficha:** decisión propuesta; no válida hasta la firma del responsable.

## 7. Firma

**Decisión propuesta:** aceptar los límites de §1 y cerrar #208 como `Hecha`, sin declarar validación con personas ni lector de pantalla real.

**Responsable:** juanajok — fecha de la propuesta: 2026-10-23.

**Firma:** ____________________ — **Fecha de firma:** ____________________.

> Sin la firma de este apartado, #208 permanece abierta en `IN REVIEW` / `En revisión` y esta ficha es solo una propuesta.
