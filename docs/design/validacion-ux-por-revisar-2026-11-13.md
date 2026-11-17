# Validación UX del flujo «Por revisar» — kit y prueba en seco

> **Protocolo superado (2026-11-14).** El kit operativo vigente es
> [`docs/design/ui-u10/kit/`](ui-u10/kit/README.md): añade consentimiento y conservación,
> reclutamiento, guion sobre la app real (una sola versión, sin A/B), registro por tarea y análisis.
> Este documento se conserva como referencia histórica de perfiles, tareas y métricas; **no se
> ejecutan los dos protocolos** ni se cuentan dos veces las mismas sesiones.


> **Estado:** las sesiones con 5 coleccionistas **NO se han ejecutado**. No hay
> personas reales reclutadas desde este entorno. Lo que sí se ejecutó es una
> **prueba en seco automatizada** de los cinco recorridos sobre el código real
> (216 tests, 2026-11-13). Este documento separa ambos niveles.

## 1. Objetivo

Comprobar si el flujo rediseñado reduce:

- el tiempo hasta la primera decisión;
- los movimientos accidentales al confundir «Vincular» con «Organizar»;
- el abandono en carpetas grandes y conflictos;
- la pérdida de trabajo al cerrar la página.

Y si el coleccionista **entiende** las acciones, no solo si los tests pasan.

## 2. Perfiles para las 5 sesiones reales

| Perfil | Criterio | Qué pone a prueba |
|---|---|---|
| P1. Coleccionista no técnico | 50+, usa la app para ordenar, no terminal | Entrada «Por revisar», vocabulario, miedo a mover |
| P2. Móvil de una mano | usa el móvil como pantalla principal | Barra sticky, objetivos de 44 px, acciones ocultas |
| P3. Teclado/lector | navega sin ratón o con lector | Foco, etiquetas, anuncios de progreso |
| P4. Volumen alto | cientos de pendientes, carpetas grandes | Carpetas, progreso, conflictos, guardar/reanudar |
| P5. Cauteloso | ya sufrió un movimiento no deseado | Diferencia «Vincular» / «Organizar», confirmaciones |

Reclutamiento: 5 personas que ya tengan una biblioteca real; no sirve probar
con datos inventados ni con el propio equipo. Evitar que hayan visto el diseño.

## 3. Tareas (20–30 min por persona)

No decir el nombre del botón ni la pantalla. Dar solo el objetivo.

1. **Archivo suelto con sugerencia:** «Tienes este archivo pendiente. Déjalo
   vinculado a la serie que creas correcta, sin moverlo de sitio».
   - Éxito: no se mueve ni renombra nada; queda vinculado.
2. **Carpeta:** «Esta carpeta tiene 30 archivos. Resuelve los de la primera
   página y deja el resto para mañana».
   - Éxito: usa la entrada por carpeta, entiende el alcance de la página y
     guarda o sale sin perder las marcas.
3. **Conflicto:** «Dos archivos comparten número. Decide qué hacer sin salir de
   esta pantalla».
   - Éxito: resuelve o deja explícitamente uno fuera; no abandona.
4. **Pack/especial:** «Este archivo es un pack. Decide qué hacer y explica por
   qué».
   - Éxito: no lo fuerza a una grapa; entiende que queda pendiente.
5. **Retomar:** «Vuelve mañana y continúa la revisión que dejaste a medias».
   - Éxito: encuentra «Reanudar», recupera marcas y no duplica decisiones.

## 4. Guion del moderador

- «Piensa en voz alta; no hay respuestas correctas».
- No corregir durante la tarea. Anotar minuto, clic y duda.
- Si se bloquea más de 90 s, preguntar: «¿Qué esperabas que pasara?».
- Al final:
  1. ¿Qué fue lo más confuso?
  2. ¿Qué botón te dio más miedo?
  3. ¿Confiarías en volver mañana con esto?
  4. SEQ 1–7 por tarea.
- Consentimiento: participación voluntaria; no se graba pantalla sin permiso;
  no se recogen rutas ni nombres de archivos en las notas.

## 5. Métricas

| Métrica | Cómo |
|---|---|
| Tiempo hasta primera decisión | cronómetro desde que ve la lista |
| Tarea completada | sí/no, con motivo |
| Movimientos accidentales | contar «Organizar» cuando pedía «Vincular» |
| Conflictos resueltos sin abandonar | sí/no |
| Abandono del asistente | sí/no |
| Recuperación del borrador | sí/no |
| SEQ por tarea | 1–7 |
| SUS al final | opcional, 10 preguntas |

Criterios de éxito:

- 5/5 completan la tarea 1; 4/5 la 3.
- Cero movimientos accidentales en la tarea 1.
- Reducción ≥30 % del tiempo hasta la primera decisión frente a la versión
  anterior.
- 4/5 entienden la diferencia «Vincular» / «Organizar» sin explicación.

## 6. Prueba en seco ejecutada (automatizada)

Comando:

```bash
pytest tests/test_pendientes.py \
  tests/test_web_nombre_y_foco.py \
  tests/test_web_accesibilidad_pendientes.py \
  tests/test_asistente_vinculacion_masivo_pg.py::TestBorradorGuardado \
  tests/test_vinculacion_en_sitio_pg.py \
  tests/test_asistente_vinculacion_masivo_pg.py::TestMarcarTodos::test_quitar_un_archivo_del_conflicto_deja_el_otro_listo
```

Resultado: **216 passed**.

Cobertura de la prueba en seco:

- La entrada principal y los formularios tienen nombre accesible.
- «Vincular en su sitio» enlaza sin tocar el archivo y rechaza `_Unsorted`.
- «Organizar» conserva su vista previa.
- Guardar/reanudar y conflicto en la fila funcionan sin aplicar nada solo.
- La barra y los rangos son regiones vivas; hay reglas móviles y objetivos de
  44 px.

**Lo que la prueba en seco no puede demostrar:** comprensión, confianza,
descubrimiento de «Reanudar», miedo a mover, ni comportamiento real con lector
de pantalla. Eso exige las 5 sesiones.

## 7. Hallazgos de la prueba en seco / sospechas para observar

1. **«Vincular en su sitio» aparece en archivos `_Unsorted`** aunque el servicio
   lo rechaza y remite a «Organizar». En la sesión real hay que mirar si el
   error se entiende o si conviene ocultar el formulario cuando el archivo
   todavía está en `_Unsorted`.
2. **Foco tras una tarjeta resuelta:** el aviso con error recibe foco, pero al
   desaparecer una tarjeta correctamente el foco puede quedar en el body. El
   rango se anuncia por `aria-live`; hay que comprobarlo con lector real.
3. **Barra sticky en 320 px:** los tests verifican la regla CSS, no que no tape
   controles. Medir en dispositivo real.
4. **Descubrimiento de «Guardar y salir»:** está junto al formulario, pero no
   sabemos si el coleccionista lo ve antes de cerrar.
5. **Conflicto:** el botón «Quitar este del lote» resuelve, pero hay que ver si
   el usuario entiende que el otro sigue marcado.

## 8. Cómo cerrar la validación

1. Ejecutar las 5 sesiones con los perfiles P1–P5.
2. Rellenar una tabla de resultados por tarea y perfil.
3. Contrastar con los criterios de éxito.
4. Abrir issues solo para los fallos observados, no para hipótesis.
5. Repetir la prueba con 3 personas tras los cambios si hay cambios grandes.

**Sin esos datos, la validación con usuarios sigue siendo NOT RUN.**
