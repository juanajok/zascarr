# U10 — Resultados de la simulación con agentes (2026-10-21)

> **Estado: simulación declarada, no sesión con usuarios reales.**
> 3 perfiles interpretados por agentes (P1 María, P2 Javier, P3 Carmen). No hay personas reales, ni clics reales,
> ni tiempos medidos, ni una muestra representativa. **U10 no queda acreditada y G1 no se desbloquea por sí sola.**
> La decisión de aceptar esta simulación como evidencia es del responsable y debe quedar escrita en #197.

## 1. Qué se ha hecho

- Prototipos estáticos A (carpetas primero) y B (lista compacta con lotes), con 1.322 pendientes sintéticos:
  1.308 en 108 carpetas + 14 archivos sueltos.
- Guion común de 7 tareas (`guion-sesion.md`), con T1 de cinco segundos y T7 de cierre.
- 3 perfiles no técnicos, con orden alterno declarado (A→B, B→A, A→B).
- Informes individuales: [`resultados-P1.md`](resultados-P1.md), [`resultados-P2.md`](resultados-P2.md),
  [`resultados-P3.md`](resultados-P3.md).

### Límites del instrumento (leer antes de usar los números)

1. **T1 no es una prueba de cinco segundos real.** P2 leyó los dos HTML completos antes de responder y su orden
   real fue A→B, no B→A; P1 y P3 intentaron limitarse al primer bloque, pero la lectura de HTML es secuencial.
2. **T5 no es comparable entre variantes.** En A no existe «Asignar…»; se respondió sobre «Elegir la serie de esta
   carpeta». En B existe, pero su explicación está al final.
3. **T3 y T4 no se pueden mapear en B.** B no muestra carpetas ni archivos sueltos; los fallos de B en esas tareas
   son ausencias del prototipo, no errores de la persona.
4. **No hay tiempos, tasas ni significación.** Los SEQ son opiniones construidas, no medidas. No se comparan A y B
   estadísticamente.
5. **No se ha probado el flujo posterior:** revisión, confirmación, deshacer, errores, accesibilidad real, tablet,
   lector de pantalla ni el resultado de una asignación.

## 2. Resultado descriptivo por perfil

| Perfil | Orden | Preferencia | SEQ A | SEQ B | Motivo principal |
|---|---|---|---|---|---|
| P1 María, 58, tablet, ~1.200 archivos | A→B | A, con reservas | 4/7 | 3/7 | A se parece a sus carpetas; B es una lista de archivos y puede dar falsa sensación de haber terminado |
| P2 Javier, 42, portátil, ~450 archivos | B→A (declarado; lectura real A→B) | A | 4/7 | 3/7 | A avisa de que la sugerencia no está aplicada; B parece una hoja de cálculo con «asignar todo» |
| P3 Carmen, 66, iPad, ~2.300 archivos | A→B | A | 5/7 | 3/7 | A respeta su forma de organizar; B la obliga a ir archivo por archivo y el botón de lote le da miedo |

**3 de 3 prefieren A como punto de partida**, pero **ninguno considera A terminada**. La preferencia es cualitativa y
está influida por el orden y por el hecho de que B recibe tareas que su pantalla no contempla.

### Recuento por tarea (descriptivo, sin tasa)

| | Éxito sin ayuda | Con ayuda | Fallo / no aplica | Abandono |
|---|---|---|---|---|
| A (3 perfiles) | T1, T2, T4 en los tres; T3 con reservas | T3 en P1 | T5 y T6 en los tres | 0 |
| B (3 perfiles) | T1, T2; T5/T6 parciales o con ayuda | T5 en P1/P2/P3 | T3 y T4 en los tres; T6 sin salida completa | 0 |

No se registró abandono de sesión. Las negativas a pulsar en A (T5/T6) se registran como fallo de la tarea, no como
abandono.

## 3. Hallazgos transversales

### H1 — No se entiende qué hace la acción principal (bloqueante)

Los tres perfiles dudan entre **elegir, asignar, vincular, mover y crear**. A no lo explica; B lo explica en un
desplegable al final y con la palabra «mover», que es justo lo que temen.

> «No pone si crea, mueve o vincula. No lo pulsaría así.» — P1
> «Si no sé si mueve archivos, no lo toco.» — P2
> «“Prepara” no es crear, “mover” no es vincular, y arriba pone “vinculables”.» — P3

**Consecuencia:** ninguna variante permite completar con confianza la tarea central. Es un problema de contrato de
la acción, no de estética.

### H2 — Las cuentas no cuadran: los 14 sueltos (bloqueante de confianza)

A dice «1.322 pendientes en 108 carpetas» y, aparte, «14 archivos sueltos». Los tres preguntan si los sueltos están
dentro de los 1.322 o si son 1.336. B ni siquiera los muestra.

> «¿Los 14 sueltos están dentro de los 1.322 o son aparte?» — P1
> «O los sueltos están dentro o son 1.336.» — P2
> «Es la primera cuenta que yo haría y no cuadra.» — P3

**Consecuencia:** el recuento, que debería dar confianza, la resta. Hay que declarar el total y el desglose de forma
inequívoca.

### H3 — El porcentaje no se interpreta y aumenta el miedo

«Serie sugerida: Flash (1987) · 94%» se lee como «94% de los archivos son de Flash» o como una nota de la máquina.
Los tres calculan el 6% restante y concluyen que aplicar a toda la carpeta es peligroso.

> «¿94% de qué? ¿Y el 6% que falta qué es, un error mío o del programa?» — P3
> «Un 6% de 155 son unos nueve; prefiero que me enseñe los archivos antes de aplicarlo todo.» — P2

**Consecuencia:** o se explica el porcentaje y se usa para decidir, o se quita de la tarjeta y se sustituye por
«sugerencia, sin aplicar».

### H4 — «Sugerida» parece un estado aplicado

El chip de sugerencia compite visualmente con los chips de estado. En A, la frase que tranquiliza («Es una sugerencia:
no está elegida ni asignada») es la más pequeña y se repite 20 veces; a la tercera tarjeta ya no se lee.

> «Si no está elegida, ¿por qué me la enseña como una etiqueta pegada?» — P3
> «La frase que más me tranquiliza es la más pequeña de la tarjeta.» — P1

**Consecuencia:** la sugerencia debe ser texto secundario, no un chip de estado; el estado real («sin serie») debe
ser el que domine.

### H5 — B no tiene mapa de carpetas ni salida para sueltos

B resuelve el control fino (marcar/desmarcar), pero no muestra carpetas ni archivos sueltos. Los tres fallan T3 y T4.
Además, «Mostrando 1–20 de 1.322» puede hacer creer que se ha clasificado la carpeta entera cuando solo son 20
archivos.

> «¿Arreglo la carpeta entera o solo estos veinte?» — P1
> «No hay ninguna entrada de sueltos.» — P2
> «No puedo clasificar la carpeta: no sé cuántos archivos tiene Flash en total.» — P3

**Consecuencia:** B necesita un punto de entrada por carpeta y un lugar explícito para los sueltos, o no puede ser
la pantalla principal.

### H6 — La carpeta mezclada no tiene salida (bloqueante para el caso real)

Ninguna variante permite decir «esta carpeta tiene dos series». A aplicaría una sola sugerencia; B permite desmarcar,
pero no asignar la otra serie ni descartar.

> «Con “Elegir la serie de esta carpeta” se lo pondría todo a Flash.» — P1
> «No veo cómo decir que ese archivo es de otra serie.» — P2
> «No hay “dividir”, “no es una serie”, “ignorar” ni “elegir otra”.» — P3

**Consecuencia:** el caso de carpeta mezclada es frecuente en la colección real. Sin una salida, la pantalla no es
segura para el trabajo completo.

### H7 — El lote de B asusta y su explicación está escondida

«Marcar todos los vinculables de esta página» está pegado a «Asignar…». «Vinculable» no se entiende. La explicación
de revisión y confirmación está debajo de la tabla y de la paginación, y habla de «mover».

> «Es una casilla que decide por mí sobre cosas que no entiendo.» — P3
> «No sé si me marca los veinte que veo o los 1.322.» — P1
> «La explicación está en el peor sitio posible.» — P2

**Consecuencia:** el lote necesita un alcance explícito («20 de esta página»), un recuento de seleccionados y la
revisión visible antes del botón, no después.

### H8 — Falta orientación con 108 carpetas

No hay búsqueda, filtro ni orden explicado. La paginación solo ofrece «Siguientes». A muestra 20 tarjetas idénticas
con 20 botones amarillos; no hay jerarquía entre «empieza por esta» y las demás.

> «Con 108 carpetas, encontrar una que no esté en la primera página es a ciegas.» — P1
> «¿Por qué está Flash antes? ¿Es la que más corre prisa?» — P2

**Consecuencia:** añadir búsqueda/filtro/orden y una acción prioritaria clara, o reducir el alcance de la primera
pantalla.

### H9 — B pierde la columna de sugerencia en pantalla estrecha

El CSS de B oculta la tercera columna por debajo de 600 px. En iPad en pantalla partida desaparece lo único que
ayuda a decidir.

> «Si uso el iPad en pantalla partida, la columna “Serie sugerida” desaparece.» — P3

**Consecuencia:** en móvil/estrecho, la sugerencia debe pasar a la fila, no desaparecer.

## 4. Lo que la simulación sí permite concluir

- Hay **fricciones reproducibles en los tres perfiles** en torno al significado de la acción, los recuentos, el
  porcentaje y la carpeta mezclada. Son hipótesis fuertes para la sesión real, no tasas.
- **A es mejor punto de partida** para personas que piensan en carpetas; **B aporta el control fino y la idea de
  revisión/confirmación**, pero no debe ser la pantalla principal sin mapa de carpetas.
- El prototipo **no está listo** para una prueba con personas reales: primero hay que corregir H1, H2, H4, H6 y H7,
  porque inducirían los mismos fallos y contaminarían la sesión.

## 5. Lo que NO se puede concluir

- Que A sea mejor que B en general, o que B sea peor.
- Que 3 agentes representen a los coleccionistas no técnicos.
- Que la acción sea segura o comprensible en el producto real: los prototipos no ejecutan nada.
- Que se cumpla U10 o G1. **No se cumple.**
- Nada sobre accesibilidad real, tablets, tiempos, errores motores o aprendizaje.

## 6. Recomendación

1. **No cerrar U10** con esta simulación. Mantener #197 en «En refinamiento» y #200 (U13) bloqueada.
2. **Iterar el prototipo A** con estas correcciones mínimas antes de la sesión real:
   - Declarar el total y el desglose: «1.322 pendientes: 1.308 en 108 carpetas + 14 sueltos».
   - Sustituir el chip de sugerencia por texto secundario y un estado real «Sin serie».
   - Explicar la acción en la propia tarjeta: «Revisar los archivos antes de asignar»; revisión + confirmación +
     deshacer visibles.
   - Añadir salida para carpeta mezclada: «Esta carpeta tiene varias series» → revisar y separar.
   - Añadir búsqueda/filtro/orden y una acción prioritaria.
   - Quitar o explicar el porcentaje; si se mantiene, decir qué mide y qué implica el resto.
3. **Tomar B como patrón de revisión dentro de A**, no como pantalla principal: selección fina, recuento de
   seleccionados, revisión antes de aplicar y confirmación.
4. **Decisión pendiente del responsable:** ¿se acepta esta simulación como evidencia suficiente para G1, con la
   deuda de la sesión real visible, o se exige la sesión con 3–5 personas reales? Hasta que se responda, G1 no se
   desbloquea.

## 7. Evidencia y reproducibilidad

- Prototipos: `prototipos/variante-a-carpetas.html`, `prototipos/variante-b-lista.html`.
- Generador: `generar_prototipos.py` (solo stdlib; datos sintéticos; no toca la app).
- Guion: `guion-sesion.md`.
- Informes: `resultados-P1.md`, `resultados-P2.md`, `resultados-P3.md`.
- Fecha: 2026-10-21. Código de producto: `origin/main` `8589b47` (los prototipos no dependen de la app).
