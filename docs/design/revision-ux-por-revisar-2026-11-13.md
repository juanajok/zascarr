# Revisión UX/UI — flujo «Por revisar»

> Revisión heurística del código y las plantillas vigentes, 2026-11-13.
> No es un test con usuarios: las propuestas incluyen cómo validarlas.
> Base actual: 224 series, 4.197 Issues, 663 archivos activos sin Issue.

## 1. Mapa del flujo actual

```
Inicio / menú
  └─ Por revisar
       ├─ tarjetas individuales (50 por página)
       │    ├─ sugerencia de serie → «Ver antes de organizar»
       │    ├─ buscar serie → elegir serie y número
       │    ├─ «Vincular como especial sin número»
       │    └─ «Ignorar»
       ├─ Verlos por carpeta → tarjetas de carpeta
       │    ├─ Elegir/Preparar la serie de la carpeta
       │    ├─ Ver propuesta de contexto
       │    ├─ Declarar carpeta
       │    └─ asistente: revisar selección y números → confirmar
       └─ Ver los archivos sueltos (solo lectura)
```

Pantallas revisadas:

- `web/templates/pendientes.html`
- `web/templates/_tarjeta_pendiente.html`
- `web/templates/_resultados_serie.html`
- `web/templates/carpetas.html`
- `web/templates/_vinculacion_revision.html`
- `web/templates/_pendientes_rango.html`
- `web/templates/sueltos.html`
- Rutas y textos de `web/pendientes.py`
- Antecedentes: `docs/design/auditoria-ui-2026-10-15.md`,
  `benchmark-U12-pendientes-escala.md`, `benchmark-U20-marcar-todos.md`,
  `benchmark-FILT1-filtro-carpetas.md`.

## 2. Lo que ya funciona

- La promesa importante está escrita cerca de la acción: «no se mueve ni se
  renombra nada hasta que confirmes».
- «Mostrando X–Y de N pendientes» evita la sensación de lista infinita.
- Hay búsqueda por nombre de carpeta y filtros por estado/conflicto.
- El asistente distingue «se vinculará», «marcado pero bloqueado» y «no se
  puede marcar»; no oculta los conflictos.
- Los estados vacíos explican la causa y ofrecen una salida.
- Hay etiquetas accesibles (`sr`), `aria-live`, foco en avisos y textos de
  error junto a la tarjeta.
- El flujo por carpeta ya evita repetir la misma decisión archivo a archivo.

## 3. Hallazgos priorizados

### F1 — Dos entradas compitiendo y ninguna recomendada · Alta

En `/ui/pendientes` hay dos botones de entrada, ambos `ghost` y sin jerarquía:

- «Verlos por carpeta».
- «Ver los archivos sueltos».

El coleccionista no sabe cuál es el camino normal. La propia pantalla mezcla
tarjetas individuales con una entrada a carpetas, así que la tarea «revisar»
no tiene un punto de partida claro.

**Impacto:** parálisis inicial, uso de la vía lenta (archivo a archivo) para
carpetas que podrían resolverse en bloque.

### F2 — «Vincular» y «Organizar» se mezclan · Alta

En la tarjeta individual la acción principal se llama «Ver antes de organizar»
y **mueve y renombra**. En el asistente la acción se llama «Vincular» y **no
mueve nada**. El efecto está explicado, pero el verbo cambia según la pantalla
y el usuario tiene que recordar cuál es cuál.

Esto ya está reconocido en el ADR 0007: la acción de «Por revisar» debía
separarse en «Vincular» y «Organizar».

**Impacto:** miedo a mover archivos, o movimiento accidental si se confía en
la sugerencia.

### F3 — La tarjeta individual concentra demasiadas decisiones · Alta

Cada tarjeta contiene, a la vez:

- nombre, «Detectado», portada, motivo;
- sugerencia con porcentaje;
- campo de número y «Ver antes de organizar»;
- buscador de serie con resultados y formularios;
- «Ignorar».

No hay jerarquía visual entre «confirmar la sugerencia» y «buscar otra serie».
La advertencia de que organizar mueve y renombra se repite en la tarjeta y en
los resultados.

**Impacto:** la tarea principal (decidir si la sugerencia es correcta) queda
enterrada entre opciones secundarias.

### F4 — El asistente masivo no muestra el progreso de la carpeta · Alta

El asistente dice «esta página» varias veces, pero no hay un progreso global:

- «Archivos en la carpeta: 148».
- «Esta página: archivos 1–100».
- «Lo que marques vale solo para esta página».

El usuario no sabe cuántas páginas quedan, cuántos archivos ha resuelto ya ni
qué pasará con las páginas anteriores. Los borradores de otras páginas están
en un desplegable («Trabajo guardado en otras páginas»), no en el flujo
principal.

**Impacto:** sensación de trabajo interminable y riesgo de dejar páginas a
medias sin saberlo.

### F5 — Los conflictos se explican, pero no se resuelven · Alta

Cuando dos archivos marcados comparten número, la interfaz dice:

> «Otro archivo marcado tiene el mismo número: marca solo uno de los dos.»

Pero no ofrece una acción directa para resolverlo. El usuario tiene que
desmarcar uno, recordar cuál, y repetir la operación. En el caso de un pack y
un archivo ajeno, el mensaje es correcto pero no ayuda a decidir.

**Impacto:** abandono en el punto exacto donde el sistema detecta un problema;
vuelta a la lista para una decisión que la pantalla podría facilitar.

### F6 — Las tarjetas de carpeta tienen cuatro acciones y mucho texto · Media

Cada carpeta ofrece:

- elegir/preparar la serie;
- ver la propuesta de contexto;
- declarar la carpeta;
- desplegar datos, señales y registros.

Las tres primeras son acciones con consecuencias distintas, pero todas son
`ghost` y van seguidas de una línea explicativa. El usuario tiene que leer
cuatro párrafos para saber cuál es la acción normal.

**Impacto:** sobrecarga cognitiva; se pierde la acción principal «revisar esta
carpeta».

### F7 — Vocabulario inestable · Media

En el mismo flujo conviven:

- «Por revisar», «Pendientes por carpeta», «archivos sueltos»;
- «registros», «archivos», «carpetas útiles», «borradores»;
- «vincular», «organizar», «asignar» (heredado), «preparar».

El término «registros» aparece en los resúmenes y en la explicación, pero el
usuario ve «archivos» en las tarjetas. La diferencia importa cuando la base y
el disco no coinciden.

**Impacto:** el usuario no sabe si está tratando con archivos reales o con
apuntes de la base.

### F8 — No se ve el resultado de la revisión en conjunto · Media

Tras resolver una tarjeta, esta desaparece y se recalcula el rango. Es correcto,
pero no hay un resumen de «qué he hecho» ni una confirmación persistente más
allá del aviso. En el asistente, el resumen de la página está al final del
formulario, no en una barra visible mientras se revisa.

**Impacto:** el usuario no sabe si avanzó o si solo cambió de página.

### F9 — Filtros y vuelta desde el asistente · Media

Los filtros de carpeta existen, pero el flujo de vuelta desde el asistente
puede perder el contexto de página/filtro (ya detectado en el benchmark
FILT1). Esto convierte una revisión de 100 archivos en una navegación de ida y
vuelta.

**Impacto:** repetición de trabajo y pérdida de confianza en la navegación.

### F10 — Móvil y teclado · Media/baja

Las tarjetas y el asistente son densos: muchos controles por fila, textos
largos y acciones al final de la página. Los `labels` están bien puestos, pero
falta comprobar:

- foco tras sustituir una tarjeta;
- navegación por teclado entre checkbox, número y confirmar;
- barra de acción fija en móvil;
- anuncio del resultado de «marcar todos».

## 4. Propuestas, por prioridad

### P0 — Una entrada clara y una acción principal

**Cambio:** en `/ui/pendientes`, recomendar explícitamente la revisión por
carpeta cuando hay carpetas con contexto; dejar los sueltos como vía
secundaria.

Copy propuesto:

```text
POR REVISAR
663 archivos pendientes · 40 carpetas

Empieza por carpeta: resuelves varios archivos con una sola decisión.
[Revisar por carpeta]        [Ver archivos sueltos]
```

- El botón de carpetas es `primary`; el de sueltos, `ghost`.
- El número de carpetas se pide después (como hoy); si falla, el enlace sigue.
- Si no hay carpetas, la entrada principal pasa a ser «Revisar archivos
  individuales».

**Éxito:** más sesiones empiezan por carpeta y baja el tiempo hasta la primera
decisión.

### P0 — Separar «Vincular» de «Organizar»

**Cambio:** dos verbos y dos consecuencias, nunca un botón ambiguo:

- **Vincular:** enlaza el archivo a un Issue **sin moverlo ni renombrarlo**.
  Es la acción normal de «Por revisar».
- **Organizar:** mueve y renombra; va en segundo plano, con vista previa
  obligatoria y texto de confirmación propio.

En la tarjeta individual, la acción principal debe ser «Vincular» cuando el
archivo ya está en su sitio; «Organizar» solo para archivos en `_Unsorted` o
cuando el usuario lo elija explícitamente.

**Dependencia:** es la decisión pendiente de ADR 0007; no se implementa como
cambio cosmético.

### P0 — Barra fija de progreso en el asistente

**Cambio:** barra sticky (o cabecera compacta) siempre visible:

```text
Carpeta: Comics/Flash (1987) · Página 1 de 2
12 marcados · 7 listos para vincular · 1 bloqueado
[Revisar y vincular]
```

- El CTA lleva al resumen de confirmación, no vincula directamente.
- Al cambiar de página, la barra conserva el progreso global.
- El resumen actual del final se mantiene, pero deja de ser el único sitio
  donde se ve.

**Éxito:** menos vueltas al final de la página y menos envíos accidentales.

### P0 — Resolver conflictos en la propia fila

**Cambio:** cuando hay dos archivos con el mismo número, mostrar un bloque
comparativo:

```text
Dos archivos comparten el número 1:
[ ] Batman #1 (2011) — 32 páginas
[ ] Batman #1 (copia) — 31 páginas

[Dejar el primero] [Dejar el segundo] [No vincular ninguno]
```

- La decisión es explícita y afecta solo a esos dos.
- Nunca se elige sola.
- Si el conflicto es pack/especial, la acción recomendada es «Dejarlo para
  después», no «elegir uno».

**Éxito:** el usuario resuelve el conflicto sin salir de la página ni recordar
nombres.

### P1 — Tarjeta individual con jerarquía

**Cambio:** reducir la tarjeta a tres zonas:

1. Identidad: portada, nombre, «Detectado».
2. Decisión: sugerencia + un botón principal.
3. Salida: «Elegir otra serie» (desplegable con búsqueda) e «Ignorar» (menos
   prominente).

Copy:

```text
[portada] Batman #001.cbr
Detectado: Batman #1
Sugerencia: Batman Vol 1 (2011) · 84 %

[Vincular con esta serie]   [Elegir otra serie]   [Ignorar]
```

- La búsqueda manual vive detrás de «Elegir otra serie», no siempre abierta.
- El efecto («no se mueve nada») va en una sola línea bajo la acción.
- No repetir la misma advertencia dentro de los resultados.

**Éxito:** primera acción visible sin leer toda la tarjeta; menos clics para
confirmar la sugerencia.

### P1 — Carpeta con una acción principal y un menú secundario

**Cambio:** por carpeta:

```text
[Revisar esta carpeta]   [Cambiar serie]   [⋯]
```

- «Revisar» es la acción principal.
- «Cambiar serie» solo si hay sugerencia.
- «Ver propuesta de contexto» y «Declarar carpeta» pasan a `[⋯]` o a
  «Avanzado», con una explicación de una línea.
- El resumen (`24 archivos · serie sugerida Batman (2011)`) va antes que las
  acciones.

**Éxito:** se entiende en 5 segundos qué hacer con una carpeta.

### P1 — Guardar y reanudar de forma explícita

**Cambio:** en el asistente:

- «Guardar y salir» visible, con confirmación de qué queda guardado.
- Al volver, ofrecer «Reanudar la revisión de esta carpeta (12/30)».
- No depender de un `<details>` para descubrir los borradores.

**Éxito:** menos abandono en carpetas grandes; el usuario puede irse sin
perder la sensación de progreso.

### P1 — Mantener filtros, página y serie al volver

**Cambio:** propagar el contexto en el enlace «Volver a las carpetas» y en el
resultado del asistente (ya identificado en FILT1). Sin parámetro de retorno
abierto: guardar el filtro en la URL y reutilizarlo.

**Éxito:** volver no obliga a repetir la búsqueda.

### P2 — Mensajes de resultado y accesibilidad

- Un solo aviso persistente: «Vinculados 7 archivos. Quedan 12 en esta
  carpeta.»
- `aria-live="polite"` en la barra de progreso y en el resultado.
- Foco al primer control editable de la tarjeta reemplazada.
- No usar solo color para «se vinculará / bloqueado»; el chip ya lleva texto,
  conservarlo.
- Probar con teclado: checkbox → número → acción → confirmar.

### P2 — Móvil

- Barra de progreso/CTA fija abajo.
- Tarjeta en columna; acciones principales a ancho completo.
- Ocultar metadatos secundarios en un desplegable.
- Evitar tablas de dos columnas en favor de bloques.

## 5. Qué no propongo

- No auto-vincular por sugerencia, aunque el porcentaje sea alto: ya hay
  conflictos reales y el producto promete revisión explícita.
- No unificar todo en una tabla con checkbox gigante: la decisión de identidad
  no es una fila de importación.
- No eliminar «Ignorar»: es la salida para archivos que no pertenecen a la
  colección.

## 6. Plan de validación con coleccionistas

### Tareas (5 participantes, 20–30 min)

1. Tienes un archivo con sugerencia clara: vincúlalo sin moverlo.
2. Una carpeta con 30 archivos: revisa y vincula la página 1; deja el resto.
3. Dos archivos comparten número: resuelve el conflicto sin salir.
4. Un archivo es un pack: decide qué hacer y explica por qué.
5. Vuelve mañana y retoma una revisión a medias.

### Métricas

- tiempo hasta la primera decisión;
- porcentaje de tareas completadas;
- errores de acción (mover creyendo vincular);
- conflictos resueltos sin abandonar;
- abandonos en el asistente;
- SEQ (confianza) por tarea;
- SUS si hay tiempo.

### Criterio de éxito

- 5/5 completan la tarea 1 y 4/5 la 3.
- Cero movimientos accidentales en la tarea 1.
- Reducción ≥ 30 % del tiempo hasta la primera decisión frente a la versión
  actual.
- Sin regresiones en los tests existentes de textos, foco y estados.

## 7. Resumen ejecutivo

El flujo ya es seguro y honesto, pero sigue contando demasiado. La mejora de
mayor impacto no es añadir otra pantalla: es **elegir una entrada principal,
separar «Vincular» de «Organizar» y llevar el progreso/confirmación a una barra
visible**. Después, resolver conflictos en la propia fila y simplificar la
tarjeta. Esas cuatro cosas reducen la carga cognitiva sin debilitar la regla
de oro: nada se mueve ni se vincula sin confirmación.
