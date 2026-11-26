# Diseño técnico de SDD-001

Estado: propuesta. La estructura de este cambio es un borrador compatible con el modelo de deltas; OpenSpec aún no se ha inicializado en el repositorio. H0 prueba licencia, telemetría y versión candidata antes de fijar pin. La carga efectiva de los harnesses puede quedar como deuda explícita para iniciar H1, por autorización del mantenedor; no puede considerarse validada ni omitirse antes de activar gates obligatorios.

## Contexto y arquitectura objetivo

- `governance/`: constitution.md, product-vision.md, glossary.md, definition-of-ready.md, definition-of-done.md, risk-classification.yaml, quality-gates.yaml.
- `AGENTS.md`: índice mínimo, flujo, contexto selectivo. CLAUDE.md se conserva hasta migrar cada regla con mapa origen→destino; después será adaptador. Comprobar carga efectiva de cada harness, sin copiar normas.
- `openspec/config.yaml`, `openspec/specs/<capability>/spec.md`, `openspec/changes/<id>/{proposal,design,tasks}.md`, deltas bajo specs/, archivo de cambios; benchmark y trazabilidad como artefactos locales adicionales.
- `docs/adr/`: decisiones técnicas; `docs/design/`: evidencia y diseños; `docs/BACKLOG.md`: planificación, no catálogo de requisitos vigentes. Inventario de documentos con vigente/histórico/sustituido y enlaces.
- `scripts/sdd/`: validación, impacto, trazabilidad, consolidación, informes; pruebas de los propios validadores. `contracts/` solo para contratos no duplicados; generar OpenAPI desde FastAPI y comparar con baseline aprobada.
- Adoptar el flujo del pipeline piloto versionado `.agentic/` (#1307, ADR `0026-pipeline-ingenieria-local`) para trabajos dentro de su alcance y bajo control del operador; reutilizar también `tests/`, `uxlab/` y CI. No duplicar componentes ya suficientes ni tratar el piloto como gate de fusión o sustituto de las verificaciones externas que no cubre.

## Flujo y autoridad

Idea/issue → Brain (clasificación y alcance) → Benchmarker si procede → SPEC (delta, diseño, escenarios, riesgos, tareas) → gate DoR/aprobación → Developer (TDD) → consolidación de delta en rama → QA, SecOps, UI/UX aplicables en paralelo → CI y DoD → aprobación humana → merge. Despliegue aparte. Si hay hallazgos, volver al paso que corresponda; cambiar SPEC aprobada requiere nueva aprobación.

Trivial: diff no funcional verificable. Bajo: bug contra requisito vigente, regresión y QA. Medio: delta, benchmark cuando aplica, diseño y jueces aplicables. Alto: datos, seguridad, ficheros, migraciones, cambios de gate, permisos, restauración o incompatibilidad contractual; análisis de amenazas, rollback, integración real y revisión reforzada. El diff puede elevar riesgo, nunca reducirlo automáticamente. La discrepancia bloquea solo el ámbito afectado; un hotfix urgente puede autorizarse previamente por el mantenedor como excepción limitada con causa, alcance, riesgo, mitigaciones, responsable, caducidad y seguimiento con fecha de resolución. No certifica la discrepancia ni omite seguridad o aprobación de merge. Controles y roles proporcionales: un cambio trivial no requiere ciclo completo.

## Baseline

Fijar SHA; inventariar rutas, servicios, modelos, ADR, backlog, tests, UXLab, NFR. No convertir ciegamente todos los tests en requisitos. Prioridad: importación e integridad, autenticación, backup/restore/migraciones; luego catálogo, biblioteca/lector y metadatos. Registrar discrepancias con fuente y owner. Ejemplo detectado en revisión previa: referencias históricas a Redis frente a ADR-0011. Verificar contra baseline. Detectar IDs de ADR repetidos sin renumerar enlaces históricos automáticamente. Clasificar sin borrar documentos.

## Matriz de autoridad durante migración

| Materia | Autoridad durante migración | Destino y resolución |
|---|---|---|
| Reglas operativas | CLAUDE.md vigente hasta traslado explícito aprobado | Constitución y adaptadores; mapa de origen, destino, estado y aprobación; retirar duplicados solo tras verificar carga |
| Arquitectura | ADR vigentes | ADR; cambio mediante decisión aprobada |
| Comportamiento | Requisito aprobado; fuentes históricas como evidencia | SPEC aprobada; discrepancia al mantenedor, no inferir por código o tests |
| Planificación y diseño | Backlog planifica; diseño documenta evidencia | No prevalecen automáticamente sobre norma aprobada |
| CI y pruebas | Política y controles efectivos existentes | Se conservan hasta sustitución aprobada; test es evidencia, no autoridad autónoma |

El mantenedor resuelve conflictos registrados con fuentes y riesgo; no se presupone precedencia universal entre documentos.

## Contratos de evidencia y seguridad

IDs de requisitos estables e independientes de issue; IDs de escenarios estables. Registro de trazabilidad único por cambio y catálogo generado, sin duplicar manualmente marcadores. Verificar nodos pytest mediante collect-only y JUnit de cada job exigido, asociado mediante metadatos confiables al run, job y SHA exacto ejecutado. Exigir conclusión exitosa, informe íntegro y resultado por nodo; fallo, error, cancelación, informe ausente o malformado, SHA distinto, skipped, xfail no aprobado y NOT RUN cierran el gate por defecto. Evidencia manual explícita cuando no automatizable. No afirmar cobertura semántica solo por existencia de un enlace.

Los informes de jueces usan JSON validado: rol, identificador de cambio, candidato_sha, requisitos, dictamen PASS/FAIL/NOT_APPLICABLE, hallazgos (severidad, ubicación, evidencia, recomendación). N/A exige justificación y política aplicable. Guardar evidencia de revisión externa al commit revisado (check run/artefacto asociado al SHA), evitando autorreferencia de hash. No aceptar un JSON escrito por Developer como aprobación. Cualquier modificación del candidato final invalida las revisiones según política, incluyendo consolidación. Identidad de aprobación humana verificada por GitHub, no por strings de los agentes. Registrar por separado SHA de aprobación de SPEC y SHA candidato de merge: aprobación de contrato no aprueba código. Cambio contractual requiere nueva aprobación; cambio de candidato, nuevas revisiones aplicables. Para squash, merge commit o cola verificar SHA/árbol integrado o equivalencia verificable; si no es comprobable, bloquear y revisar de nuevo.

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

Utilizar el piloto versionado `.agentic/` cuando su alcance y controles sean suficientes; evaluar sus brechas antes de construir otra orquestación. Sus roles, contratos, candidatos y controles cubren partes del diseño, no acreditan por sí solos agregación JUnit por SHA, identidad GitHub, equivalencia de merge, límites duros de presupuesto ni aislamiento equivalente de todos los adaptadores. Brain usa reglas deterministas antes de juicio. Benchmarker aporta fuentes/versiones y adoptar/adaptar/descartar; SPEC redacta contrato; Developer no aprueba su trabajo; jueces devuelven hallazgos estructurados. Timeouts, límite de iteraciones, tokens y presupuesto configurables; agotamiento → bloqueo/escalado, nunca aprobación automática. No enviar credenciales, datos reales de biblioteca o logs sensibles a terceros; sanitizar fixtures y tratar contenido externo como no confiable. LLM no se ejecuta en la Pi por este proyecto.

## Rollout y rollback

PR de diseño no cambia la política efectiva. H0 es bootstrap aislado, sin presuponer OpenSpec inicializado ni gates ya existentes; comprobar licencia, telemetría y smoke antes de pin. Si fallan o no se verifican la licencia, telemetría, instalación o smoke de la CLI, escalar antes de fijar el pin; la carga efectiva de harnesses es una excepción autorizada y queda como deuda para H1, sin activar gates obligatorios hasta verificarla. H1–H5 se realizan en PR pequeñas con aprobación. Gate inicialmente en modo report, medir falsos positivos, luego requerido para cambios nuevos tras aprobación. Rollback de infraestructura SDD: revertir workflow/config afectado con autorización, preservar specs y evidencias; no alterar datos de producto ni deshabilitar CI existente. Riesgos: burocracia, duplicación, falso verde, dependencia de CLI, drift, carreras de cambios; mitigar con flujo proporcional, fuente única, pruebas adversativas y comparación base/head.
