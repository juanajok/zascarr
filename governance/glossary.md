# Glosario de producto (propuesta)

**Estado: sin migrar. La fuente única vigente sigue siendo la sección de glosario de [CLAUDE.md](../CLAUDE.md).** Este fichero no la duplica todavía: fija el destino, el principio de trabajo y lo que falta decidir antes de consolidar.

## Principio

Un término por concepto. Dos conceptos distintos no se convierten en sinónimos por comodidad, y un mismo concepto no cambia de nombre según la pantalla. La interfaz habla como el coleccionista («tebeo», «número», «carpeta»), no como el esquema (`File`, `Issue`, `StoryArc`).

## Reglas que se conservarán al consolidar

- **La superficie no renombra datos.** Los valores persistidos, las URLs, los `value` de formularios y los enums internos no cambian por traducir texto visible.
- **Excepciones declaradas.** Las que hoy están aprobadas (por ejemplo, la etiqueta móvil de la barra inferior y su motivo) se conservan con su prueba asociada; no se acortan etiquetas para cumplir un umbral.
- **Un concepto, un lugar.** El glosario fija el texto visible; no define contratos de comportamiento, que pertenecen a la especificación del dominio.
- **Los enlaces no sustituyen al texto.** Un término traducido en superficie no queda cubierto por existir en una tabla: la prueba que lo comprueba debe mirar el texto visible.

## Índice de conceptos

Nombres y ubicación canónica únicamente: **no** se copian definiciones mientras la guía siga siendo la fuente única. Una prueba comprueba que este índice y la guía tengan exactamente los mismos conceptos, sin repetidos; si la guía gana o pierde un término, la prueba falla hasta que este índice lo refleje.

| Concepto | Fuente canónica |
|---|---|
| **serie** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **número** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **archivo** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **tebeo** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **registro** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **pendiente** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **suelto** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **carpeta** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **colección** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **estado de la serie** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **tebeoteca** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **biblioteca** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **Por revisar** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **revisión de la biblioteca (Duplicados)** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **actualizar la biblioteca** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **ignorado** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **duplicado** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **editorial** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **tradición** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **saga / arco** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **edición** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **mejora** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **publicación** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |
| **catálogo** | [CLAUDE.md](../CLAUDE.md), sección 14.1 |

## Pendiente antes de considerarlo fuente única

1. Comparar término a término con la guía vigente y registrar cada diferencia con su motivo.
2. Confirmar qué documento conserva las excepciones de tamaño, fuente y contraste.
3. Decidir si las tablas de navegación por pantalla siguen aquí o en el índice de interfaz.
4. Aprobar el traslado y solo entonces retirar la copia anterior.

## Referencias

- Tabla de cambios de vocabulario: [glosario-u7.md](../docs/design/ui-u7/glosario-u7.md).
- Inventario y vigencia de textos: [vigencia-2026-11-14.md](../docs/design/ui-u18/vigencia-2026-11-14.md).

## Reglas de contexto (migradas de PRE-39)

- **Tebeo.** «Tebeo español» es la etiqueta de la tradición (`ComicTradition.TEBEO`), siempre con «español» y en mayúscula cuando encabeza. «Tebeo» a secas es el objeto o ejemplar: «El mismo tebeo, dos veces» o «En tu disco había 1.542 tebeos». No es «número» cuando se cuenta numeración ni «registro» cuando se habla de la fila.
- **Pendiente no es archivo.** Un pendiente es un registro en un estado; el archivo es el fichero del disco. «Por revisar» lista pendientes, y algunos pueden apuntar a un archivo que ya no está: por eso el subtítulo no dice «archivos».
- **Suelto = pendiente sin carpeta.** Un suelto es un pendiente cuya ruta no tiene carpeta de serie contextual; no es una categoría distinta.
- **Registro = fila, no archivo.** El registro es la fila de `files`; el archivo es el fichero. La frase que lo explica se conserva en el desplegable de procedencia; fuera de ahí, «registro» no es unidad de contador.
- **Biblioteca, tebeoteca, colección y catálogo.** Biblioteca es la pantalla `/ui/biblioteca` (y el conjunto en disco); tebeoteca es el conjunto entero del coleccionista; colección es un grupo con nombre de series; catálogo es el nombre interno de la base de datos. No se usan como sinónimos.
- **Revisión (Duplicados) no es «Por revisar».** Por revisar es la cola de pendientes; Duplicados es la revisión del disco y su acción es «Revisar mi biblioteca».
- **Número, tebeo, edición y publicación.** Número es la unidad bibliográfica; tebeo es el objeto o archivo; edición es una línea editorial (para el coleccionista, otra serie); formato es grapa, tomo u ómnibus; copia u origen distinto es un archivo del mismo número; publicación es la unidad de destino en una declaración de carpeta.
- **Saga, arco, editorial y sello.** En superficie, «Saga»; «arco» y `StoryArc` son código. Editorial es `Publisher`; sello es `Imprint` y solo se usa cuando el dato distingue el sello.
