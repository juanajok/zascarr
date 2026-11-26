## ADDED Requirements

### Requirement: SDD-R001 Normas y autoridad

ZascArr SHALL disponer de una constitución aprobada, catálogo de requisitos vigentes por capacidad, ADR y reglas operativas sin duplicación normativa. Un conflicto se registra y resuelve por el mantenedor; el código observado no sustituye al requisito aprobado.

#### Scenario: Conflicto normativo

- **GIVEN** una implementación que contradice un requisito aprobado
- **WHEN** se evalúa el comportamiento
- **THEN** se registra una discrepancia con fuentes y riesgo y se bloquea el ámbito afectado hasta resolverla, salvo excepción controlada autorizada previamente por el mantenedor

#### Scenario: Hotfix urgente con discrepancia abierta

- **GIVEN** una discrepancia sin resolver y un hotfix urgente en su ámbito
- **WHEN** el mantenedor autoriza previamente una excepción con causa, alcance, riesgo, mitigaciones, responsable, caducidad y seguimiento con fecha de resolución
- **THEN** procede solo el hotfix delimitado con controles de seguridad y aprobación de merge vigentes; la discrepancia sigue abierta y no se certifica

### Requirement: SDD-R002 Baseline brownfield verificable

Cada requisito reconstruido SHALL identificar su origen y estado (candidato, aprobado, discrepancia o pendiente de verificación). Solo lo aprobado integra la especificación vigente.

#### Scenario: Comportamiento legado sin consenso

- **GIVEN** una prueba o un documento histórico en conflicto con otro
- **WHEN** se reconstruye la baseline
- **THEN** se conserva la evidencia y se solicita decisión sin certificar el comportamiento

### Requirement: SDD-R003 Cambio proporcional al riesgo

Todo cambio SHALL clasificarse como trivial, bajo, medio o alto antes de su ejecución; el riesgo podrá elevarse por impacto. Un cambio funcional nuevo o modificado exige delta SPEC aprobado; una corrección contra SPEC vigente exige referencia y regresión.

#### Scenario: Reclasificación de cambio sensible

- **GIVEN** un cambio declarado trivial que afecta autenticación, migraciones o integridad de ficheros
- **WHEN** el clasificador analiza el diff
- **THEN** exige el flujo alto y no acepta la declaración del desarrollador como excepción

### Requirement: SDD-R004 Trazabilidad verificable

Cada requisito y escenario nuevo o modificado SHALL tener ID estable y evidencia vinculada. Los checks verificarán existencia y ejecución mediante JUnit de cada job exigido vinculado por metadatos confiables a run, job y SHA ejecutado y conclusión exitosa. Fallo, error, cancelación, informe ausente o malformado, SHA incorrecto, skip o xfail no aprobado cierran el gate por defecto; QA verificará adecuación. Las excepciones manuales deberán registrar evidencia, responsable y aprobación.

#### Scenario: Prueba vinculada pero no ejecutada

- **GIVEN** un requisito nuevo con un test vinculado
- **WHEN** el test no figura como ejecutado y aprobado en el informe requerido
- **THEN** el gate de aceptación falla, salvo evidencia manual previamente aprobada para un escenario no automatizable

### Requirement: SDD-R005 Desarrollo y regresión

El Developer SHALL aplicar TDD a comportamiento nuevo o corregido y preservar las pruebas existentes; cualquier modificación de tests normativos requiere justificación y aprobación de cambio de requisito si procede.

#### Scenario: Regresión eliminada

- **GIVEN** una prueba vigente que falla con el nuevo código
- **WHEN** se propone eliminarla para obtener CI verde
- **THEN** se rechaza el cambio hasta justificar el requisito o reparar la implementación

### Requirement: SDD-R006 Revisiones independientes

El Brain SHALL coordinar Benchmarker, SPEC, Developer, QA, SecOps y UI/UX según el riesgo. Los jueces aplicables no serán el Developer, emitirán dictámenes verificables sobre el mismo candidato inmutable, y los bloqueantes no podrán ser anulados por el Brain. Roles y controles serán proporcionales al riesgo, sin exigir el ciclo completo a cambios triviales; la orquestación reutiliza contratos y adaptadores portables sin duplicar el pipeline local no versionado.

#### Scenario: Dictamen obsoleto

- **GIVEN** una revisión favorable sobre un candidato
- **WHEN** cambia su SHA o el contenido que constituye el candidato revisado
- **THEN** se invalida el dictamen y se exige nueva revisión aplicable

#### Scenario: SHA de aprobación y candidato de merge

- **GIVEN** una SPEC aprobada y un candidato de merge con SHA distinto
- **WHEN** se solicita la fusión
- **THEN** se registran ambos SHA, se verifica el contrato aprobado y CI y jueces del candidato final; si cambia el contrato se renueva su aprobación, y si cambia el candidato sus revisiones. Para squash, merge commit o cola se verifica contenido integrado o equivalencia verificable, o se bloquea

### Requirement: SDD-R007 Consolidación atómica

Los deltas aprobados SHALL consolidarse con código y pruebas en la misma PR de entrega antes de fusionar. Los cambios se archivarán sin perder evidencias ni reutilizar IDs.

#### Scenario: Código sin sincronización de SPEC

- **GIVEN** un cambio de comportamiento implementado y validado
- **WHEN** el delta aprobado no coincide con la SPEC final consolidada
- **THEN** se bloquea la entrega

### Requirement: SDD-R008 Deterministic first y portabilidad

Las verificaciones estructurales, selección de pruebas y validación de informes SHALL realizarse sin LLM. Los agentes tendrán contexto selectivo, presupuesto y contratos neutrales respecto al proveedor. El SDD no añade dependencias de runtime.

#### Scenario: Harness alternativo

- **GIVEN** un checkout limpio y un harness diferente
- **WHEN** se carga el índice de agentes y los artefactos pertinentes
- **THEN** el flujo puede continuar sin conversaciones previas ni credenciales del harness anterior

### Requirement: SDD-R009 Gobierno y seguridad de CI

El proceso SHALL preservar los checks existentes y la autorización humana de merge y despliegue. Los validadores se ejecutarán con mínimo privilegio, sin secretos en PR no confiables y sin confiar en el texto generado por agentes como aprobación.

#### Scenario: Cambio en el propio gate

- **GIVEN** una PR que modifica el mecanismo de validación o la clasificación de riesgo
- **WHEN** se solicita fusionarla
- **THEN** se exige revisión independiente reforzada y aprobación del mantenedor con política de referencia confiable

### Requirement: SDD-R010 Migración gradual y piloto

La implantación SHALL establecer en H0 matriz de autoridad y bootstrap que evalúe licencia, telemetría y smoke de OpenSpec antes de fijar su pin; si falla o no se verifica se escala sin activar H1. También deberá registrar deuda histórica sin bloquear indiscriminadamente contribuciones, exigir conformidad a cambios nuevos tras la activación aprobada y completar un piloto de riesgo medio con métricas y evidencias.

#### Scenario: Activación de gates

- **GIVEN** los dominios críticos inventariados y un piloto terminado
- **WHEN** se solicita hacer obligatorio el check SDD
- **THEN** se presentan evidencias, fallos controlados, coste y deuda pendiente al mantenedor para su aprobación
