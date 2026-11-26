# Constitución del proyecto (propuesta)

**Estado: sin migrar.** Este documento propone principios generales; **no** sustituye a [CLAUDE.md](../CLAUDE.md), que sigue siendo la autoridad vigente. Ningún punto de este fichero se convierte en norma hasta que la regla correspondiente figure trasladada, revisada y aprobada en [el mapa de reglas](mapa-reglas.md).

## Principios

- **P1 — El coleccionista primero.** El producto se mide contra una persona no técnica que no abre terminales ni edita JSON. Una función que exige consola para lo cotidiano es un defecto de producto.
- **P2 — Ligero y fiable antes que vistoso.** El sistema convive con otros servicios en una Raspberry Pi con presupuesto de memoria acotado. Una dependencia nueva es memoria y superficie de ataque.
- **P3 — Gestiona, no facilita.** El software organiza una biblioteca propia; no aporta ni promueve fuentes de contenido. Ver el marco legal en [LEGAL.md](../src/zascarr/LEGAL.md).
- **P4 — Regla única por concepto.** Dos documentos no deben definir el mismo comportamiento con matices distintos. Cuando ocurre, se registra la contradicción con fuentes y la resuelve el mantenedor; no se elige precedencia por conveniencia.
- **P5 — Evidencia antes que afirmación.** Una prueba que no se ejecutó, un dictamen de un SHA anterior o un enlace existente no acreditan cumplimiento. Se distingue explícitamente lo observado, lo inferido y lo pendiente.
- **P6 — Cambio proporcional al riesgo.** Un arreglo de texto no exige el mismo recorrido que un cambio en datos, seguridad o ficheros.

## Límites de esta propuesta

- No crea gates, no modifica CI y no retira reglas.
- No afirma carga efectiva de instrucciones en ningún harness: esa comprobación está pendiente (T0.4).
- Las excepciones operativas vigentes (por ejemplo, la deuda del movimiento con sesión ORM abierta) se conservan tal como están en la guía; no se convierten en cumplimiento por aparecer aquí.

## Reglas migradas

Texto trasladado desde la guía vigente. La copia de la guía se conserva hasta la aprobación de la retirada; mientras exista, es duplicación declarada.

### PRE-40 — Registrar las decisiones del modo de trabajo

La guía es contexto operativo para agentes y personas que colaboren en el repositorio y debe leerse antes de tocar código. Toda decisión nueva sobre cómo se trabaja se registra el día que se decide, no cuando alguien la recuerde.
