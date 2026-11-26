# SPEC v1: pipeline multiagente de desarrollo (herramienta, no runtime)

Base de descubrimiento: `f9d0cf76a78d087e2dcc37a3e15c0ead1c5b3d27`, rama del piloto UX Lab; el borrador local no forma parte del cambio. ZascArr mantiene Python 3.11+, FastAPI, PostgreSQL, HTMX y su presupuesto de 512 MiB en Pi. El pipeline vive en `.agentic/` y se ejecuta en un puesto de desarrollo/CI, no en Docker de producción. No instala dependencias ni cambia el perfil de ningún harness.

## Benchmark previo (comparativa documental, no tiempos medidos)

| Alternativa | Mecanismo disponible | Decisión y coste |
|---|---|---|
| UX Lab (`uxlab/run-agents.sh`, `uxlab/compose.agents.yml`, SHA base) | Compose aislado, fixture sintético, Playwright y sesiones separadas con presupuesto. | Reusar las comprobaciones del dominio cuando se integre el lab; no generalizar su runner acoplado a 2 escenarios y a la API de un proveedor. |
| [LangGraph](https://github.com/langchain-ai/docs/blob/933a2f92/src/oss/langgraph/durable-execution.mdx) | Persistencia, `interrupt`, tareas idempotentes/replay. | Adoptar el patrón checkpoint; no incorporar el runtime ni un checkpointer extra para una secuencia pequeña. |
| [Temporal Python](https://docs.temporal.io/develop/python/workers/run-worker-process) | Workers, colas y cliente de servicio. | Descartar hasta necesitar ejecución distribuida; operar otro servicio no mejora este MVP. |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | Guardrails, handoffs, trazas, sesiones y sandboxes. | Útil para futuros adaptadores; no requerir SDK, cuenta o transporte concreto para validar gates y persistir. |
| Python stdlib, Git, runner Docker local | Persistencia local, commits exactos, límites de procesos y reaprovechamiento del Docker existente. | Adaptar; el runner no conoce al proveedor y Git no sustituye la comprobación del código. |

No se instalaron bibliotecas ni se ejecutaron POC de los tres frameworks externos; no se concluye cuál es más rápido o seguro. Integración gratuita/ofline por defecto; un proveedor remoto requiere autorización de datos y de coste. No se traslada código de terceros.

## Criterios de aceptación del núcleo

| ID | Comportamiento verificable |
|---|---|
| P-01 | Máquina de estados explícita; checkpoints atómicos y registro; una interrupción no repite resultados ya incorporados. Dos escritores no aceptan simultáneamente resultados para el mismo task. Cancelación no publica. |
| P-02 | Configuración y SPEC congeladas por hash; contrato estricto JSON, IDs de requisito únicos; ignora respuestas de otra tarea/revisión. Solo caminos de texto permitidos pueden cambiar. No hay merges, despliegue, comandos de agente ni ejecución ofensiva. |
| P-03 | Los controles se ejecutan antes de jueces. El runner recibe un snapshot aislado y un comando aprobado por el operador, nunca una orden de un agente. RED usa baseline y prueba separada; el runner ejecuta GREEN sobre el candidato. Excepciones no se autoconceden. |
| P-04 | SECOPS y QA obligatorios; UI/UX obligatoria si se declara interfaz. Cada juez recibe el mismo SHA candidato y la misma SPEC; no recibe los informes de pares. Un HIGH/CRITICAL, incumplimiento de cobertura obligatoria, no aplicable o inconcluso en juez requerido bloquea. HIGH_ASSURANCE bloquea también MEDIUM y pide decisión humana vinculada al hash. |
| P-05 | Presupuesto de intentos y rondas, concurrencia y tamaño de contexto; sin progreso o rework agotado bloquea. Evidencia identifica origen y versión; no acredita tokens/coste no observados. |
| P-06 | Ejemplo E2E reproducible positivo y negativos (fallo de check, resultado obsoleto, vulnerabilidad defensiva representada como hallazgo, intento de eludir gate). Diferenciar fixtures simulados de ejecución real y de observaciones cualitativas. |

## Alcance y confianza

Roles consultivos separados de estado y ejecución. API de transporte: solicitud JSON y respuesta correlacionada; adaptadores no tienen autoridad de escribir estado. Revisor dispone de contexto selectivo como dato, no acceso de escritura al repo. Operador controla manifiesto y comandos de validación. Directorio de run y Docker daemon son parte de la base de confianza administrativa; no se promete defensa contra un operador malicioso con acceso al almacén. Las herramientas y modelos carecen de objetivos ofensivos. No se invocan redes externas desde el ejecutor de pruebas. La entrega es un candidato/patch para revisión, no una publicación. MVP orientado a cambios de texto acotados; los casos binarios, repos enormes y workflows distribuidos quedan fuera. El runner admite E/S de un solo contenedor mediante `scratch: true` (tmpfs efímero acotado); la concurrencia entre contenedores, la red, la base de datos y los servicios externos siguen exigiendo una prueba de procesos real fuera del gate actual.
