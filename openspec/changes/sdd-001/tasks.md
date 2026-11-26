# Tareas SDD-001

Tareas de la propuesta. Una PR por historia, no cerrar #1291 hasta H0–H5. IDs de requisitos del delta de development-governance. Estado al 2026-11-26: H0 cerrado con excepciones explícitas (ver `h0-evidencia.md`); el resto sigue pendiente y las casillas marcan trabajo documental, no capacidades verificadas.

## 0. Inventario y decisión
- [x] T0.1 Fijar baseline, inventariar capacidades/documentos y evidencias; detectar contradicciones e IDs duplicados; proponer matriz de autoridad y mapa de migración sin retirar normas vigentes. (R001,R002)
- [x] T0.2 Bootstrap aislado: evaluar licencia y versión candidata de OpenSpec; smoke init, validate, sync/archive y negativos; verificar tráfico/telemetría y desactivación efectiva, sin red cuando sea posible. Fijar pin solo tras las comprobaciones correspondientes; si fallan o no son verificables, escalar. La carga efectiva de harnesses queda como deuda autorizada que no impide H1, pero bloquea la activación de gates obligatorios. (R007,R008,R010) — evaluada y escalada: el pin sigue candidato en #1293 (instalación limpia del lock, licencias y suministro pendientes).
- [ ] T0.4 Verificar carga efectiva de instrucciones en Claude Code, Codex y OpenCode en entorno autorizado, con datos sintéticos y suscripciones; registrar versiones, resultados y limitaciones antes de activar gates obligatorios. (R008,R010) — NOT RUN; bloquea gates obligatorios.
- [x] T0.3 Aprobar propuesta y resolver alcance con mantenedor. (R001,R009) — aprobación conversacional registrada y ligada al SHA revisado; no es revisión de GitHub ni autoriza fusión.

## 1. Infraestructura y gobierno (depende de H0)
- [ ] T1.1 Constitución y glosario; mapa de reglas de CLAUDE.md a destino; AGENTS.md y adaptadores probados. (R001,R008)
- [ ] T1.2 Inicializar OpenSpec sin pisar este cambio; plantillas de delta, benchmark, diseño, tareas, evidencia; IDs y DoR/DoD. (R001,R003,R007)
- [ ] T1.3 Política proporcional de riesgo, excepción de discrepancia/hotfix (causa, alcance, riesgo, mitigaciones, responsable, caducidad y seguimiento) y aprobación; adaptar CONTRIBUTING, backlog y plantillas GitHub. (R003,R009)

## 2. Baseline crítica (depende de H1)
- [ ] T2.1 Importación, movimiento, deduplicación e integridad; escenarios adversativos. (R002,R004)
- [ ] T2.2 Seguridad, autenticación, exposición, credenciales y puerta legal. (R002,R004)
- [ ] T2.3 Backup, restauración, migraciones y actualización. (R002,R004)
- [ ] T2.4 Registrar deuda de dominios restantes, resolver divergencias críticas o delimitar alcance bloqueado; revisión del mantenedor. (R002,R010)

## 3. Validación y CI (depende de H1, coordinar H2)
- [ ] T3.1 TDD de validadores de sintaxis, IDs, enlaces, impacto y riesgo, con casos de bypass. (R003,R004,R005)
- [ ] T3.2 Trazabilidad y resultados pytest/JUnit por run, job exigido y SHA exacto; fallo cerrado por job fallido/cancelado, informe ausente/malformado, SHA distinto, skip o xfail no aprobado; integración y evidencia manual; reportes JSON/Markdown. (R004,R005)
- [ ] T3.3 Validar deltas/consolidación y contratos; pruebas de divergencia. (R007)
- [ ] T3.4 Workflow SDD informativo, permisos mínimos, checks existentes intactos; verificar política confiable. (R009,R010)
- [ ] T3.5 Makefile y documentación; comprobar sin LLM, sin red salvo instalación fijada y sin runtime nuevo. (R008)

## 4. Multiagente (depende de H1 y contratos H3)
- [ ] T4.1 Adoptar el flujo piloto versionado `.agentic/` dentro de sus capacidades; contrastar roles, schemas, garantías y brechas con SDD antes de añadir otra orquestación. Brain clasifica por reglas y aplica roles proporcionalmente. (R003,R006,R008)
- [ ] T4.2 Orquestar gates, revisiones paralelas, SHA de aprobación de SPEC separado del candidato de merge, comprobación del árbol integrado o equivalencia para squash/cola, N/A, bloqueo y nueva revisión; pruebas de dictamen falso/obsoleto. (R006,R009)
- [ ] T4.3 Presupuestos, límites, sanitización, proveedores/harnesses intercambiables; pruebas de recuperación y escalado. (R008,R009)

## 5. Piloto y puesta en servicio (depende H2–H4)
- [ ] T5.1 Seleccionar historia de riesgo medio con mantenedor; ejecutar ciclo completo con SPEC y TDD, jueces y evidencias. (R004,R005,R006,R007,R010)
- [ ] T5.2 Probar PR negativas y cambio trivial; medir falsos positivos, coste, tokens, tiempo, deuda y cobertura trazada. (R003,R008,R010)
- [ ] T5.3 Aprobación humana de política; configurar required check si disponible, documentar limitaciones y rollback. (R009,R010)
- [ ] T5.4 Consolidar SPEC de gobierno y archivar este cambio con evidencias; revisión final y cierre de épica. (R007,R010)
