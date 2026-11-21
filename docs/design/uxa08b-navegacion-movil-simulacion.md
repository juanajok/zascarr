# UXA-08b · «Biblioteca directa» frente a «Más» en móvil (simulación con agentes)

**Fecha:** 2026-11-21 · **Historia:** #1205 · **Origen:** #1125 (UXA-08) · **Estado:** simulación hecha; **la decisión del PO sigue abierta** y la medición con personas, pendiente.

## Qué se comparó

| Variante | Barra inferior (móvil) | Dentro de «Más» |
|---|---|---|
| **A (hoy)** | Inicio · Revisar · Deseados · Estado · Más | Biblioteca, Mejoras, Colecciones, Listas, Duplicados, Descubrir, Novedades, Ajustes |
| **B (prueba)** | Inicio · Revisar · Biblioteca · Deseados · Más | Mejoras, Colecciones, Listas, Duplicados, Descubrir, Novedades, **Estado**, Ajustes |

B es solo un experimento: se movió `movil_principal` de Biblioteca y de Estado en `web/menu.py` (3 líneas) en una rama local que **no se fusionó ni se publicó**. En B el punto de aviso de Estado (`#cnt-estado`) queda dentro del panel y no se ve desde la barra.

## Método

- Dos instancias locales idénticas (mismo Postgres, 24 series sembradas, incluidas «Flash» y «Flash Gordon»), sin tocar la Pi.
- Cuatro agentes de IA, uno por celda (2 perfiles × 2 variantes), sin saber que se comparaban variantes, en una pestaña propia a 375×812. Podían escribir la URL de partida (`/ui/`) y después solo pulsar lo que veían; máximo 12 clics.
  - **Marta** (58 años, coleccionista, no técnica) y **Dani** (34 años, vigila el servidor).
- Tareas, ambas desde Inicio: abrir la ficha de la serie «Flash» y comprobar si el sistema tiene algún problema o aviso.
- Se registró cada clic, el primero, las dudas y el éxito.

## Resultados

| Perfil · variante | Tarea | Primer clic | Clics hasta la sección | Clics totales | Éxito |
|---|---|---|---|---|---|
| Marta · A | Flash | Más | 2 | 5 | Sí |
| Marta · A | Estado | Estado | 1 | 1 | Sí |
| Dani · A | Flash | Más | 2 | 5 | Sí |
| Dani · A | Estado | Estado | 1 | 1 | Sí |
| Marta · B | Flash | Biblioteca | 1 | 4 | Sí |
| Marta · B | Estado | Más | 2 | 2 | Sí |
| Dani · B | Flash | Biblioteca | 1 | 4 | Sí |
| Dani · B | Estado | Más (un fallo de puntería, descontado) | 2 | 2 (3 con el fallo) | Sí |

- **Éxito:** 8 de 8 en las dos variantes.
- **Biblioteca:** A cuesta 2 clics hasta la lista (Más → Biblioteca), B cuesta 1. En A el primer clic fue siempre «Más», por descarte («no vi nada que dijera Biblioteca»).
- **Estado:** A cuesta 1 clic, B cuesta 2 (Más → Estado). En B ambos fueron a «Más» por descarte.
- **El intercambio es simétrico:** cada variante ahorra un clic en una tarea y lo pierde en la otra.

### Comentarios espontáneos

- En A, los dos pidieron ver Biblioteca en la barra («Me habría gustado ver "Biblioteca" directamente abajo»; «Biblioteca, que es lo que más se usa, queda escondida detrás de "Más"»).
- En B, los dos echaron en falta una señal de Estado fuera de «Más» («un punto en "Más" cuando hay problemas»; «la palabra "Estado" o un aviso se viera sin abrir ese menú»).
- En B, Marta dudó si «Revisar» era lo de los problemas.

### Observación aparte (no depende de la navegación)

En Biblioteca, tras pulsar «Buscar» los resultados quedan bajo la fila de botones y el texto explicativo; tres agentes no vieron cambio hasta desplazarse. Es de la pantalla, igual en A y en B. Candidato a historia propia.

## Límites (qué no demuestra)

- **No son personas.** Son agentes de IA que leen etiquetas: el «primer clic» refleja cómo se leen los rótulos, no el comportamiento, la prisa, el pulgar ni los errores de una persona real. Sirve para detectar problemas de etiquetado, no para medir tiempos ni decidir.
- **n = 1 por celda**, dos perfiles. Ninguna diferencia es estadística.
- Dani en A no pudo hacer capturas (el panel del navegador estaba oculto) y trabajó con el árbol de accesibilidad; los demás vieron la pantalla.
- Varios agentes cargaron la URL de partida más de una vez por fallos de carga; no se contó como clic.
- No se probó móvil real, ni lector de pantalla, ni 320 px.
- Un agente dijo que los enlaces de la barra no tenían nombre accesible; se comprobó y **no es cierto** (el enlace tiene el texto visible; fue una limitación de la herramienta).

## Lectura

La simulación no inclina la balanza por sí sola: el coste se desplaza entre dos tareas. Lo que sí aporta es la **condición para que B sea defendible**: si Biblioteca va directa, Estado necesita una señal visible fuera de «Más» (por ejemplo, el punto de aviso sobre «Más» cuando hay avisos). Sin ella, B empeora el camino a Estado, que el criterio de #1125 pide conservar claro.

## Decisión del PO (pendiente)

1. Mantener A (sin cambios).
2. Probar B **con** el punto de aviso sobre «Más», detrás de una prueba controlada, y medir con personas reales (primer clic y éxito con una persona que lee y otra que opera, en móvil real).
3. Otra variante (p. ej. B cambiando «Inicio» en vez de «Estado»).

Hasta que el PO decida, la navegación por defecto no cambia.
