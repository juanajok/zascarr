# SDD-001 — Transformación de ZascArr a Spec-Driven Development

- Issue: [#1291](https://github.com/juanajok/zascarr/issues/1291)
- Estado: dirección de revisión aprobada; propuesta normativa pendiente de aprobación del mantenedor. No activa todavía reglas nuevas.
- Línea base histórica de auditoría: main @ ea9bc603eb2aa86265abd5b0697b3e03ef87e732; contraste posterior: main @ c4a3420349153f2ac3185df3da46b37c8211aa3d.
- Fecha: 2026-11-26

## Why

Las decisiones normativas residen hoy en CLAUDE.md, backlog, ADR, diseños y pruebas. ZascArr ya dispone de una disciplina fuerte de QA, benchmarking y revisiones, pero no de un catálogo único de requisitos vigentes con trazabilidad ejecutable. Queremos evitar perder contexto al alternar harnesses y evitar que un agente convierta una implementación accidental en comportamiento aprobado.

## What Changes

- Adoptar OpenSpec como formato de especificaciones vivas y deltas, con el principio de constitución y análisis de consistencia de Spec Kit. No desplegar dos frameworks.
- Incorporar gobierno, AGENTS.md como índice portátil, matriz de riesgo, DoR/DoD y plantillas.
- Reconstruir requisitos históricos por dominios críticos, dejando discrepancias abiertas y evidencias de procedencia.
- Añadir gates deterministas, trazabilidad y revisiones independientes sobre un candidato inmutable.
- Bootstrap H0 antes de fijar el pin; matriz de autoridad y adopción del flujo piloto `.agentic/`, versionado en main desde #1307, dentro de sus límites y sin crear otra orquestación innecesaria.
- Piloto real de riesgo medio y activación gradual de checks requeridos tras autorización.

## Capabilities

### New Capabilities

- `development-governance`: reglas del ciclo de desarrollo SDD y su verificación.

### Modified Capabilities

- Ninguna capacidad funcional de producto en esta propuesta. Las futuras PR de baseline describirán el comportamiento aprobado y las de producto propondrán deltas separados.

## Impact

Solo entorno de desarrollo, documentación y CI. Mantener FastAPI, PostgreSQL, Jinja2, HTMX, arquitectura ARM64 y límite existente de recursos. Sin cambios de runtime, esquemas de datos, instalación, credenciales, integraciones o despliegue. Preservar suite, UXLab, ADR y autorización humana de merge y despliegue.

## Éxito

100 % de los requisitos nuevos o modificados con escenarios y evidencia; cero pruebas críticas omitidas, cambios funcionales no aprobados o hallazgos bloqueantes abiertos; código y especificación consolidada en el mismo merge; cero nuevas dependencias SDD de runtime. Las cifras de deuda histórica se reportan separadas. No confundir trazabilidad con cobertura semántica.

## Aprobaciones

La PR de diseño puede entrar como propuesta sin activar el proceso. La implementación de H1 y cada cambio normativo requiere aprobación explícita. El cierre de la épica exige los hitos H0–H5, piloto y aprobación humana. No se permite autocertificación de agentes.
