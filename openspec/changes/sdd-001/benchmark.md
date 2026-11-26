# Benchmark SDD-001

Fecha de revisión documental: 2026-11-26. Base: ea9bc603eb2aa86265abd5b0697b3e03ef87e732. No se han instalado ni ejecutado los frameworks, ni auditado aquí su licencia transitiva o versiones. H0 debe fijar versiones/tags y ejecutar un piloto de CLI aislado.

## Referencias y decisiones

| Fuente | Patrón documentado | Decisión y evidencia que falta |
|---|---|---|
| [OpenSpec: conceptos](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md) | Specs vigentes por capacidad; deltas activos y archivo | ADOPTAR formato y ciclo para brownfield; demostrar sincronización y archivo en worktree |
| [OpenSpec: CLI](https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md) | Validación y consolidación de cambios | ADAPTAR como gate de estructura, no como prueba de corrección semántica; fijar versión, probar flags y códigos de salida |
| [OpenSpec: customización](https://github.com/Fission-AI/OpenSpec/blob/main/docs/customization.md) | Configuración y esquemas versionados | ADAPTAR solo si la configuración estándar no basta. No hacer depender la validación de extensiones no soportadas |
| [Spec Kit: quickstart](https://github.github.com/spec-kit/quickstart) y [agentic SDD](https://github.com/github/spec-kit/blob/main/docs/reference/agentic-sdd.md) | Constitución, clarificación, planificación, tareas, análisis de consistencia | ADAPTAR principios; DESCARTAR un segundo framework instalado; contrastar plantilla y DoR |
| [AGENTS.md](https://agents.md/) | Índice de instrucciones para agentes | ADOPTAR como índice común; comprobar lectura real en Claude Code, Codex, OpenCode y otros harnesses elegidos |
| ZascArr: CLAUDE.md, docs/design/benchmark-referencias.md, CONTRIBUTING.md, docs/TESTING_MASTER_PLAN.md, .github/workflows/ci.yml, uxlab/SPEC-FASE2-PILOTO.md | Reglas, benchmarking, TDD/regresiones, CI, revisiones, oráculos | CONSTRUIR SOBRE LO PROPIO. No sustituir herramientas ni repetir documentos |

## Comparación cualitativa

| Criterio | OpenSpec | Spec Kit | Solo Markdown propio |
|---|---|---|---|
| Baseline viva + deltas | Encaje directo | Requiere definir consolidación por dominio | Implementación propia |
| Constitución y análisis | Incorporar reglas locales | Patrón documentado | Implementación propia |
| Coste de integración | CLI de desarrollo; verificar pin | Segundo stack innecesario si ya se adopta OpenSpec | Mayor mantenimiento de parsers y convenciones |
| Control de trazabilidad y aprobaciones | Extensión local | Extensión local | Extensión local |
| Portabilidad de harness | Artefactos comunes, comprobar adaptadores | Artefactos comunes, comprobar adaptadores | Depende de nuestra disciplina |

## Decisión propuesta

OpenSpec como único formato y CLI SDD, constitución y controles inspirados en Spec Kit, validadores Python pequeños y CI existente. No atribuir a OpenSpec gates que son responsabilidad de ZascArr. Validar licencias GPL-3.0-only, instalación reproducible y compatibilidad con CI antes de adoptar dependencias. Fuentes consultadas son documentación mutable; registrar versión y enlaces a commit en H0. Si la prueba falla, mantener Markdown compatible y volver al mantenedor con alternativas, no sustituir la decisión en silencio.
