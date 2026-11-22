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

## Qué enciende el punto de aviso (actualizado con #1219)

El punto (sobre «Estado» en A, sobre «Más» en B) se enciende cuando **la última comprobación de salud** (`GET /api/health`, la que llama el HEALTHCHECK de Docker cada 30 s) dijo «Atención» o «Error» —lo mismo que el resumen de la pantalla Estado— o cuando la interfaz está abierta a la red sin contraseña. Un servicio apagado en Ajustes no cuenta.

- El menú **no sondea**: lee el veredicto guardado por esa comprobación. Si no hay veredicto o tiene más de 2 minutos (p. ej. justo tras reiniciar, o en local sin HEALTHCHECK), no se enciende nada.
- Una instalación sin copias de seguridad configuradas da «Atención» (copia y restauración en error), así que el punto estará encendido hasta configurarlas. Es coherente con Estado, pero hay que saberlo al probar: **en A y en B el punto saldrá encendido en una instancia recién creada**. Para ver la barra sin aviso, configura las copias o comprueba con una instancia sana.
- Para probar con un problema real: detén Transmission o aMule (si están activados en Ajustes) y espera a la siguiente pasada (≤ 30 s).

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
- Anotar si «Más» **no responde a la primera** (dos agentes de la simulación lo dijeron; con el panel oculto no se pudo distinguir de un fallo de la herramienta).

## Cómo se decide

La decisión es del PO. Referencias, no umbrales estadísticos (n es pequeño):

- Si B ahorra toques a Biblioteca **y** nadie falla en Estado → B es candidata.
- Si en B alguien no encuentra Estado o tarda claramente más, o el perfil que opera el sistema lo pide → B solo con un aviso de salud completo (punto sobre «Más»), que habría que construir antes.
- Si no hay diferencia clara → se mantiene A (no se cambia por cambiar).

Con el resultado, la decisión y las filas anotadas se añade una sección «Resultado» a este documento y se cierra #1205.

## Qué no cubre

Lector de pantalla, 320 px, tiempos fiables y una muestra estadística. Es una comprobación de orientación, no un experimento.
