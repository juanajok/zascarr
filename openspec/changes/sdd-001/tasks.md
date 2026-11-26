# Tareas SDD-001

Todas pendientes; no representan ejecución real. Una PR por historia, no cerrar #1291 hasta H0–H5. IDs de requisitos del delta de development-governance.

## 0. Inventario y decisión
- [ ] T0.1 Fijar baseline, inventariar capacidades/documentos y evidencias; detectar contradicciones e IDs duplicados. (R001,R002)
- [ ] T0.2 Pin de OpenSpec, licencia, smoke en worktree: init, validate, sync/archive y casos negativos, verificar harnesses. Registrar versiones. (R007,R008)
- [ ] T0.3 Aprobar propuesta y resolver alcance con mantenedor. (R001,R009)

## 1. Infraestructura y gobierno (depende de H0)
- [ ] T1.1 Constitución y glosario; mapa de reglas de CLAUDE.md a destino; AGENTS.md y adaptadores probados. (R001,R008)
- [ ] T1.2 Inicializar OpenSpec sin pisar este cambio; plantillas de delta, benchmark, diseño, tareas, evidencia; IDs y DoR/DoD. (R001,R003,R007)
- [ ] T1.3 Política de riesgo, excepciones y aprobación; adaptar CONTRIBUTING, backlog y plantillas GitHub. (R003,R009)

## 2. Baseline crítica (depende de H1)
- [ ] T2.1 Importación, movimiento, deduplicación e integridad; escenarios adversativos. (R002,R004)
- [ ] T2.2 Seguridad, autenticación, exposición, credenciales y puerta legal. (R002,R004)
- [ ] T2.3 Backup, restauración, migraciones y actualización. (R002,R004)
- [ ] T2.4 Registrar deuda de dominios restantes, resolver divergencias críticas o delimitar alcance bloqueado; revisión del mantenedor. (R002,R010)

## 3. Validación y CI (depende de H1, coordinar H2)
- [ ] T3.1 TDD de validadores de sintaxis, IDs, enlaces, impacto y riesgo, con casos de bypass. (R003,R004,R005)
- [ ] T3.2 Trazabilidad y consumo de resultados reales pytest/JUnit, integración y evidencia manual; reportes JSON/Markdown. (R004,R005)
- [ ] T3.3 Validar deltas/consolidación y contratos; pruebas de divergencia. (R007)
- [ ] T3.4 Workflow SDD informativo, permisos mínimos, checks existentes intactos; verificar política confiable. (R009,R010)
- [ ] T3.5 Makefile y documentación; comprobar sin LLM, sin red salvo instalación fijada y sin runtime nuevo. (R008)

## 4. Multiagente (depende de H1 y contratos H3)
- [ ] T4.1 Definir siete roles y schemas de entrada/salida; Brain clasifica por reglas. (R003,R006,R008)
- [ ] T4.2 Orquestar gates, revisiones paralelas, SHA candidato, N/A, bloqueo y nueva revisión; pruebas de dictamen falso/obsoleto. (R006,R009)
- [ ] T4.3 Presupuestos, límites, sanitización, proveedores/harnesses intercambiables; pruebas de recuperación y escalado. (R008,R009)

## 5. Piloto y puesta en servicio (depende H2–H4)
- [ ] T5.1 Seleccionar historia de riesgo medio con mantenedor; ejecutar ciclo completo con SPEC y TDD, jueces y evidencias. (R004–R007,R010)
- [ ] T5.2 Probar PR negativas y cambio trivial; medir falsos positivos, coste, tokens, tiempo, deuda y cobertura trazada. (R003,R008,R010)
- [ ] T5.3 Aprobación humana de política; configurar required check si disponible, documentar limitaciones y rollback. (R009,R010)
- [ ] T5.4 Consolidar SPEC de gobierno y archivar este cambio con evidencias; revisión final y cierre de épica. (R007,R010)
