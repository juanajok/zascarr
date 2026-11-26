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
