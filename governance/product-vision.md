# Visión de producto (propuesta)

**Estado: sin migrar.** Destino propuesto; la autoridad vigente sigue en [CLAUDE.md](../CLAUDE.md). Ver [el mapa de reglas](mapa-reglas.md).

## Qué es

ZascArr es un gestor self-hosted de tebeoteca para archivos CBZ/CBR: registra lo que hay en disco, propone correspondencias, organiza pendientes y avisa de problemas, sin mover ni borrar nada sin decisión explícita.

## Para quién

Para «el coleccionista»: alguien con una biblioteca grande que quiere orden, que usa el navegador y no la terminal, y que abandona el producto si tiene que interpretar errores técnicos. El vocabulario de superficie está fijado en la guía vigente y se trasladará al [glosario](glossary.md) sin renombrar entidades ni datos persistidos.

## Restricciones que no se negocian

- **Raspberry Pi compartida.** La aplicación convive con otros servicios; el presupuesto de memoria por contenedor está documentado en el despliegue. Nada bloquea el event loop de forma síncrona.
- **Sin SPA ni build de Node en runtime.** La interfaz es HTML servido con mejoras puntuales en el servidor; el stack y la excepción del lector están en las reglas vigentes.
- **Local-first y sin datos de terceros en claro.** Portadas y metadatos se cachean en local; los registros no exponen rutas ni credenciales.
- **Seguridad por defecto.** La interfaz escucha en localhost salvo decisión explícita del operador, y las credenciales no tienen valores por defecto utilizables.

## Fuera de alcance

Este documento no describe arquitectura de módulos, contratos de API ni el detalle de cada dominio: eso vive en las especificaciones de dominio y en las decisiones de arquitectura. Tampoco define el proceso de trabajo, que se documenta en la constitución y en las reglas operativas vigentes.

## Referencias

- Criterios de diseño visual: [sistema-de-diseno-zascarr.md](../docs/design/sistema-de-diseno-zascarr.md).
- Comparación con referencias antes de features grandes: [benchmark-referencias.md](../docs/design/benchmark-referencias.md).
