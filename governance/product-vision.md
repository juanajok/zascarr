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

## Reglas migradas

Texto trasladado desde la guía vigente (sección 1). La copia de la guía se conserva hasta la aprobación de la retirada; mientras exista, esta sección es duplicación declarada, no autoridad nueva.

### PRE-10 — El software gestiona, nunca facilita

El software gestiona la biblioteca; no facilita el acceso a contenido. Sin URLs hardcodeadas de foros dispuestos a enlaces; el scraper IPB es genérico y la URL la aporta el usuario en runtime mediante `FORUM_URL`. El marco legal completo está en [LEGAL.md](../src/zascarr/LEGAL.md).

### PRE-41 — Producto, persona y restricción de plataforma

ZascArr es un gestor self-hosted de tebeoteca (CBZ/CBR) tipo Sonarr/Radarr, optimizado para Raspberry Pi 4/5 y pensado para el público hispanohablante. Stack: FastAPI + SQLAlchemy async + PostgreSQL + Jinja2 + HTMX. Sin Redis (ADR-0011). Sin SPA, sin build de Node, htmx vendorizado en disco (ADR-0001).

**Persona:** «El Coleccionista»: no técnico, no abre terminales ni JSON. Las decisiones de producto se miden contra él, no contra la experiencia del desarrollador.

**Restricción dura que nunca se rompe:** corre dentro de una Pi compartida con Transmission, aMule, Prowlarr y Kavita. El presupuesto de RAM por contenedor está documentado en `docker-compose.yml` (512M). Todo lo «bonito» viene segundo; lo ligero y lo fiable, primero.
