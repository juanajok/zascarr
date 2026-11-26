# Especificación SDD-T1.1: constitución, glosario y adaptadores

**Estado:** SPEC aprobada por el mantenedor el 2026-11-26 para iniciar T1.1; su contenido canónico es este fichero (SHA-256 de la versión aprobada en el comentario de la PR). H0 se cerró con la excepción explícita de `T0.4` (ver `openspec/changes/sdd-001/h0-evidencia.md`, «Cierre de H0»). Esta SPEC no autoriza fusiones, despliegues ni gates obligatorios.

**Alcance:** documental y de gobierno. Crea constitución, visión, glosario, mapa de reglas e índice `AGENTS.md` con adaptadores. No cambia comportamiento del producto, permisos, CI, secretos, datos, imagen de runtime ni dependencias.

## Problema

La guía vigente mezcla instrucciones operativas, restricciones de producto, referencias, excepciones y vocabulario. Separar autoridad y navegación por harness es necesario para el piloto SDD, pero sin pérdida de reglas, sin dos fuentes normativas contradictorias y sin declarar carga efectiva de instrucciones que no se ha verificado.

## Decisiones de diseño

- **D-1 Contrato canónico.** El contrato exacto de una historia con código vive en `docs/design/especificacion-<ID>.md`; el delta OpenSpec expresa los requisitos y escenarios del cambio y enlaza a ese contrato y al registro único de trazabilidad. Decisión del mantenedor del 2026-11-26.
- **D-2 Autoridad de transición.** La guía actual conserva la autoridad hasta que cada regla tenga traslado revisado y aprobado. No se elige precedencia implícita ante una contradicción: se escala con fuentes y alcance.
- **D-3 Sin duplicación silenciosa.** Un destino nuevo no se convierte en segunda norma mientras la regla siga viva en su origen. La duplicación temporal se marca como tal y tiene fecha de retirada.

## Criterios de aceptación

- **T1.1-C01 Inventario.** Cada regla activa de la baseline fijada tiene origen preciso, destino propuesto, excepciones, estado y decisión. Referencias históricas y reglas no verificadas se distinguen. Un agrupamiento por secciones no acredita cobertura.
- **T1.1-C02 Autoridad.** Ningún destino desplaza una norma vigente sin traslado completo y aprobado; las contradicciones no resueltas se registran y escalan.
- **T1.1-C03 Constitución y visión.** Recogen restricciones generales aprobadas (incluidas Raspberry Pi y seguridad) y conservan matices y excepciones; no absorben contratos de dominio.
- **T1.1-C04 Glosario.** Conserva conceptos y excepciones aprobados sin renombrar entidades, valores persistidos, rutas ni texto visible por el mero traslado. Se fija explícitamente la fuente única antes de eliminar duplicación.
- **T1.1-C05 Índice y adaptadores.** `AGENTS.md` y los adaptadores enlazan autoridades vigentes y no afirman soporte de carga no probado. La guía actual no se sustituye por un adaptador hasta completar y verificar la migración.
- **T1.1-C06 Verificación estructural.** Existen comprobaciones deterministas de enlaces, rutas y duplicación prohibida, con casos negativos; se documenta comando, entorno y límites. Un PASS estructural no demuestra equivalencia semántica.
- **T1.1-C07 Harnesses.** La carga efectiva en Claude Code, Codex y OpenCode sigue sin verificar; esta historia no la declara ni habilita gates obligatorios.
- **T1.1-C08 Reconciliación SDD+TDD.** Se aplica D-1 y el protocolo de equivalencia; no se publican cambios locales ajenos ni se atribuye a `main` una regla que no esté en su baseline.
- **T1.1-C09 Entrega.** Cambios pequeños y revisables, sin borrar reglas vigentes; pruebas posteriores al candidato final; fusión y despliegue con autorización expresa y separada.

## Protocolo de equivalencia (desarrollo de D-1)

1. El contrato de diseño identifica entradas, salidas, errores, datos tocados y criterios con IDs estables. El delta OpenSpec contiene requisitos y escenarios y referencia esos IDs. Un registro único vincula criterio, escenario y prueba.
2. Una comprobación determinista detecta IDs ausentes, duplicados o sin vínculo, y referencias rotas. No deduce equivalencia semántica.
3. QA revisa manualmente cada criterio afectado frente a sus escenarios y reporta contradicciones u omisiones con fuente y ubicación. Una discrepancia bloquea el ámbito afectado.
4. Si cambia el contrato aprobado, se revisa primero el diseño y se obtiene nueva aprobación; después se actualizan delta y trazabilidad.
5. Excepciones y pruebas manuales registran causa, evidencia, responsable y decisión. No sustituyen la exigencia de una prueba nombrada por criterio salvo decisión expresa.

## Pruebas por criterio

| Criterio | Verificación prevista | Tipo |
|---|---|---|
| C01 | Lista regla por regla con origen, destino, excepción y estado; revisión del mantenedor sobre una muestra y sobre las excepciones | Revisión manual registrada |
| C02 | Caso negativo: un destino que contradice una regla vigente debe quedar bloqueado y escalado | Manual documentado |
| C03–C04 | Comparación término a término del glosario y de las restricciones generales; lista de excepciones conservadas | Manual; apoyo determinista de enlaces |
| C05 | Prueba de enlaces y rutas de adaptadores; caso negativo de enlace roto; ausencia de afirmaciones de carga | Automatizada + revisión |
| C06 | Ejecutar las comprobaciones con un enlace roto y con una duplicación prohibida; el rojo debe ser por el motivo esperado | Automatizada |
| C07 | Sesiones sintéticas de cada harness, versiones y trazas autorizadas | **NOT RUN**; no bloquea H1, bloquea gates |
| C08 | Registro de la decisión D-1 y del protocolo; confirmar que no se publicó ningún cambio local ajeno | Manual documentado |
| C09 | Diff del candidato final, pruebas ejecutadas y autorización separada de fusión | Proceso |

## Dependencias y límites

- H0 cerrado con excepciones; `T0.4` pendiente. El pin de OpenSpec sigue candidato en #1293.
- El inventario previo (`borrador-mapa-h1.md`) es insumo parcial trazado fuera del repositorio, no evidencia de cobertura, y no se cita como fuente normativa.
- Esta SPEC no crea gates, no modifica CI y no retira ninguna regla de `CLAUDE.md`.
