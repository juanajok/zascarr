# AGENTS.md — índice de instrucciones para agentes

Este fichero es un **índice de navegación**, no una norma nueva. La autoridad **vigente** sigue siendo [CLAUDE.md](CLAUDE.md) hasta que cada regla tenga traslado revisado y aprobado (criterio T1.1-C02 de [la especificación](docs/design/especificacion-SDD-T1.1-gobierno.md)).

## Por dónde empezar

1. [CLAUDE.md](CLAUDE.md): reglas operativas vigentes del proyecto. Es la autoridad durante la migración.
2. [governance/constitution.md](governance/constitution.md): principios generales propuestos.
3. [governance/product-vision.md](governance/product-vision.md): producto, persona y restricciones.
4. [governance/glossary.md](governance/glossary.md): vocabulario; **no** es todavía la fuente única.
5. [governance/mapa-reglas.md](governance/mapa-reglas.md): inventario de reglas y su destino, todas «sin migrar».
6. [openspec/changes/sdd-001/proposal.md](openspec/changes/sdd-001/proposal.md): propuesta SDD-001.
7. [.agentic/README.md](.agentic/README.md): piloto de ingeniería local. Queda fuera del runtime y no sustituye CI, UX Lab ni las aprobaciones de fusión.
8. [docs/adr/0027-pipeline-ingenieria-local.md](docs/adr/0027-pipeline-ingenieria-local.md): decisión sobre ese piloto.

## Estado real de la migración

- Autoridad actual: `CLAUDE.md`. Los documentos de `governance/` son destinos propuestos y figuran como «sin migrar».
- Carga efectiva de instrucciones (T0.4): **evidencia parcial**. Claude Code 2.1.332 lee `CLAUDE.md` y **no** este fichero; Codex CLI y OpenCode no pudieron ejecutarse (errores de entorno). Conclusión operativa: este índice sirve para navegar, **no** es un canal garantizado de instrucciones. Ver [evidencia T0.4](docs/design/t04-evidencia.md).
- Gates obligatorios: no activados. El pin de OpenSpec sigue candidato.

## Cómo se trabaja una historia con código

1. `spec:`: contrato en `docs/design/especificacion-<ID>.md` más requisitos y escenarios en OpenSpec, aprobados antes de programar.
2. `test:`: las pruebas fallan por el motivo esperado y el rojo queda acreditado en la PR.
3. Implementación mínima hasta el verde, sin comportamiento fuera de la especificación.
4. `refactor:` con todo en verde.

Un enlace no acredita ejecución ni cobertura semántica. La revisión de seguridad de un cambio sensible se ata al SHA final que se fusiona.

## Consultar antes de tocar un área (PRE-24)

Los documentos vivos no son decoración: antes de modificar un área hay que leer el documento que la gobierna.

| Área a tocar | Consultar primero |
|---|---|
| Plantillas, rutas o contratos `hx-*` | [inventario de la UI](docs/design/ui-migracion.md) |
| Estilos o componentes | [sistema de diseño](docs/design/sistema-de-diseno-zascarr.md) |
| Formato por contenido, triage o auditoría de formatos | [contrato 307](docs/design/contrato-307-formato-por-contenido.md) |
| Registro incremental de biblioteca | [registro incremental](docs/design/registro-incremental-326.md) |
| Rescan de la biblioteca | [especificación BL-R9](docs/design/especificacion-BL-R9-rescan-biblioteca.md) |
| Copias de seguridad y auxiliar del host | [BL-OPS1](docs/design/especificacion-BL-OPS1.md) |
| Estado durable de la actualización | [contrato B1](docs/design/ops4-b1-contrato-estado.md) |
| Disponibilidad de archivos | [disponibilidad 231](docs/design/disponibilidad-231.md) |
| Marco legal | [LEGAL.md](src/zascarr/LEGAL.md) |

Si se actualiza el marco legal, ese mismo día se rehace el hash de versión legal en `services/legal.py`.
