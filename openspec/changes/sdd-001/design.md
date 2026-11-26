# Diseño técnico de SDD-001

Estado: propuesta. La estructura de este cambio es un borrador compatible con el modelo de deltas; OpenSpec aún no se ha inicializado ni validado en el repositorio. H1 fijará y probará la versión real antes de activar reglas.

## Contexto y arquitectura objetivo

- `governance/`: constitution.md, product-vision.md, glossary.md, definition-of-ready.md, definition-of-done.md, risk-classification.yaml, quality-gates.yaml.
- `AGENTS.md`: índice mínimo, flujo, contexto selectivo. CLAUDE.md se conserva hasta migrar cada regla con mapa origen→destino; después será adaptador. Comprobar carga efectiva de cada harness, sin copiar normas.
- `openspec/config.yaml`, `openspec/specs/<capability>/spec.md`, `openspec/changes/<id>/{proposal,design,tasks}.md`, deltas bajo specs/, archivo de cambios; benchmark y trazabilidad como artefactos locales adicionales.
- `docs/adr/`: decisiones técnicas; `docs/design/`: evidencia y diseños; `docs/BACKLOG.md`: planificación, no catálogo de requisitos vigentes. Inventario de documentos con vigente/histórico/sustituido y enlaces.
- `scripts/sdd/`: validación, impacto, trazabilidad, consolidación, informes; pruebas de los propios validadores. `contracts/` solo para contratos no duplicados; generar OpenAPI desde FastAPI y comparar con baseline aprobada.
- `agents/`: roles y esquemas JSON de intercambio; adaptadores del harness separados de reglas. `tests/`, `uxlab/` y CI existentes se reutilizan.

## Flujo y autoridad

Idea/issue → Brain (clasificación y alcance) → Benchmarker si procede → SPEC (delta, diseño, escenarios, riesgos, tareas) → gate DoR/aprobación → Developer (TDD) → consolidación de delta en rama → QA, SecOps, UI/UX aplicables en paralelo → CI y DoD → aprobación humana → merge. Despliegue aparte. Si hay hallazgos, volver al paso que corresponda; cambiar SPEC aprobada requiere nueva aprobación.

Trivial: diff no funcional verificable. Bajo: bug contra requisito vigente, regresión y QA. Medio: delta, benchmark cuando aplica, diseño y jueces aplicables. Alto: datos, seguridad, ficheros, migraciones, cambios de gate, permisos, restauración o incompatibilidad contractual; análisis de amenazas, rollback, integración real y revisión reforzada. El diff puede elevar riesgo, nunca reducirlo automáticamente. Excepciones aprobadas con alcance, causa, caducidad y responsable.

## Baseline

Fijar SHA; inventariar rutas, servicios, modelos, ADR, backlog, tests, UXLab, NFR. No convertir ciegamente todos los tests en requisitos. Prioridad: importación e integridad, autenticación, backup/restore/migraciones; luego catálogo, biblioteca/lector y metadatos. Registrar discrepancias con fuente y owner. Ejemplo detectado en revisión previa: referencias históricas a Redis frente a ADR-0011. Verificar contra baseline. Detectar IDs de ADR repetidos sin renumerar enlaces históricos automáticamente. Clasificar sin borrar documentos.

## Contratos de evidencia y seguridad

IDs de requisitos estables e independientes de issue; IDs de escenarios estables. Registro de trazabilidad único por cambio y catálogo generado, sin duplicar manualmente marcadores. Verificar nodos pytest mediante collect-only e informes JUnit de jobs exigidos; skipped, xfail no aprobado, NOT RUN o ausencia no cuentan. Evidencia manual explícita cuando no automatizable. No afirmar cobertura semántica solo por existencia de un enlace.

Los informes de jueces usan JSON validado: rol, identificador de cambio, candidato_sha, requisitos, dictamen PASS/FAIL/NOT_APPLICABLE, hallazgos (severidad, ubicación, evidencia, recomendación). N/A exige justificación y política aplicable. Guardar evidencia de revisión externa al commit revisado (check run/artefacto asociado al SHA), evitando autorreferencia de hash. No aceptar un JSON escrito por Developer como aprobación. Cualquier modificación del candidato final invalida las revisiones según política, incluyendo consolidación. Identidad de aprobación humana verificada por GitHub, no por strings de los agentes.

CI usa permissions mínimos, sin ejecución de código no confiable con secretos, sin pull_request_target que ejecute checkout de PR. Los gates deben proteger también cambios a sí mismos: política confiable de base o revisión requerida de mantenedor; verificar disponibilidad de rulesets/branch protection con permisos reales. No prometer que el conector pueda administrarlos.

## Validadores y comandos propuestos

- make spec-validate: sintaxis OpenSpec, estructura, IDs y enlaces; pin de CLI en dev.
- make spec-impact: diff base/head, clasificación y dominios; base SHA explícito.
- make spec-coverage: escenarios y resultados por entorno, deuda separada.
- make spec-drift: comparación determinista de contratos, deltas y manifiestos; juicio semántico separado.
- make spec-report / spec-check: informe JSON/Markdown y exit code; nunca escribir automáticamente specs aprobadas.
- CI diferencial: inicialmente informativa para legado, bloqueante tras aprobación para nuevos/modificados; conservar lint, PostgreSQL real, RAR real, Docker ARM64/amd64, CSS y UXLab.

Pruebas de validadores: ID repetido, referencia rota, prueba saltada, delta no consolidado, revisión de SHA antiguo, bypass trivial, cambio de gate, excepción caducada, PR de docs válida, rollback de versión. Ejecutar sin LLM ni red cuando sea posible.

## Agentes y coste

Brain usa reglas deterministas antes de juicio. Benchmarker aporta fuentes/versiones y adoptar/adaptar/descartar; SPEC redacta contrato; Developer no aprueba su trabajo; jueces devuelven hallazgos estructurados. Timeouts, límite de iteraciones, tokens y presupuesto configurables; agotamiento → bloqueo/escalado, nunca aprobación automática. No enviar credenciales, datos reales de biblioteca o logs sensibles a terceros; sanitizar fixtures y tratar contenido externo como no confiable. LLM no se ejecuta en la Pi por este proyecto.

## Rollout y rollback

PR de diseño no cambia la política efectiva. H1–H5 se realizan en PR pequeñas con aprobación. Gate inicialmente en modo report, medir falsos positivos, luego requerido para cambios nuevos tras aprobación. Rollback de infraestructura SDD: revertir workflow/config afectado con autorización, preservar specs y evidencias; no alterar datos de producto ni deshabilitar CI existente. Riesgos: burocracia, duplicación, falso verde, dependencia de CLI, drift, carreras de cambios; mitigar con flujo proporcional, fuente única, pruebas adversativas y comparación base/head.
