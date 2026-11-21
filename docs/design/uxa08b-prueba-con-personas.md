# UXA-08b · Prueba con personas: barra inferior A frente a B

**Historia:** #1205 · **Antecedente:** [`uxa08b-navegacion-movil-simulacion.md`](uxa08b-navegacion-movil-simulacion.md) (simulación con agentes; no decide) · **Estado:** preparada; falta hacerla y decidir.

## Qué se compara

| | Barra inferior | Dentro de «Más» | Aviso de Estado |
|---|---|---|---|
| **A** (por defecto) | Inicio · Revisar · Deseados · Estado · Más | Biblioteca y el resto | Punto sobre «Estado» |
| **B** | Inicio · Revisar · Biblioteca · Deseados · Más | Estado y el resto | Punto sobre «Más» (el de «Estado» sigue en la barra lateral del escritorio) |

## Cómo cambiar de variante

El interruptor es `NAV_MOVIL_VARIANTE` (`a` o `b`; cualquier otro valor impide arrancar). No cambia nada si no se toca.

1. Añade `NAV_MOVIL_VARIANTE=b` al `.env` de la Pi y recrea el contenedor de la aplicación.
2. Para volver, quita la línea (o pon `a`) y recréalo otra vez.
3. En local: `NAV_MOVIL_VARIANTE=b uvicorn zascarr.main:app …`. Dos instancias con la misma base, una por variante, permiten enseñar A y B a la vez.

## Limitación que hay que conocer antes de probar

El punto de aviso de Estado se enciende **solo por seguridad** (interfaz abierta a la red sin contraseña; `services/seguridad.py::estado_de_seguridad`). Los avisos de VPN, copias o restauración los calcula la propia pantalla Estado desde `/api/health`, en el navegador, y **no** encienden ningún punto, ni en A ni en B. Por eso:

- En B, un problema de VPN o copias **no se ve** desde la barra; hay que abrir «Más» → Estado. Es justo el riesgo que la simulación señaló (los dos agentes en B fueron a «Más» por descarte).
- Hacer que el punto refleje la salud completa exige un resumen cacheado de `/api/health` (no se puede sondear cada 30 s desde el menú). Es trabajo aparte; **no está hecho**.

La prueba mide el recorrido con lo que hay hoy. Si quieres ver el punto durante la sesión, expón la interfaz a la LAN sin contraseña **solo en una instancia de prueba**.

## Participantes

2–4 personas, mejor 4: dos que leen su colección (perfil «Marta») y dos que operan el sistema (perfil «Dani»). Cada persona ve **una sola** variante (entre sujetos) y las variantes se reparten por igual. Móvil real en vertical; si no hay, 375×812.

## Guion (por persona)

Se parte siempre de Inicio. No se explica la barra. Se pide pensar en voz alta. No se ayuda; si se atasca más de 60 s, se anota «sin éxito» y se pasa a la siguiente tarea.

1. **Biblioteca:** «Quieres abrir la ficha de la serie "Flash" de tu colección.»
2. **Estado:** «Quieres comprobar si el sistema tiene algún problema o aviso.»
3. **Pendientes:** «Quieres ver qué tebeos tienes por revisar.» (control: es una entrada de la barra en ambas variantes)

Alterna el orden de las tareas 1 y 2 entre personas.

## Qué se anota (una fila por persona y tarea)

| Persona · perfil · variante | Tarea | Primer toque (etiqueta) | Toques hasta la sección | Toques totales | Éxito (sí/no) | Segundos | Dudas / frases textuales |
|---|---|---|---|---|---|---|---|

- «Toque» = cada pulsación (abrir y cerrar paneles incluidos; escribir no cuenta; Atrás cuenta).
- «Hasta la sección» = hasta ver la lista de series (tarea 1) o la pantalla Estado (tarea 2).
- Un fallo de puntería se anota aparte y no cuenta.

## Cómo se decide

La decisión es del PO. Referencias, no umbrales estadísticos (n es pequeño):

- Si B ahorra toques a Biblioteca **y** nadie falla en Estado → B es candidata.
- Si en B alguien no encuentra Estado o tarda claramente más, o el perfil que opera el sistema lo pide → B solo con un aviso de salud completo (punto sobre «Más»), que habría que construir antes.
- Si no hay diferencia clara → se mantiene A (no se cambia por cambiar).

Con el resultado, la decisión y las filas anotadas se añade una sección «Resultado» a este documento y se cierra #1205.

## Qué no cubre

Lector de pantalla, 320 px, tiempos fiables y una muestra estadística. Es una comprobación de orientación, no un experimento.
