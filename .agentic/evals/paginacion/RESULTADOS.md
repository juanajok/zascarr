# Comparación: agente único frente al pipeline

Fecha: 2026-11-26. Una ejecución exploratoria, no benchmark estadístico. Fixture sintético, **no es un bug real de ZascArr**. Un operador humano/raíz intervino en el transporte entre el motor y DSH. La batería y el contrato se escribieron antes de las soluciones; el control adicional de introspección se añadió después del finding QA, por lo que no es una prueba ciega predefinida.

## Caso y reproducción

El código base [`pagina.py`](<pagina.py>) devolvía la última página cuando se solicitaba una página fuera del rango. Se fijó el contrato [R1–R4](<spec.md>) y el [oráculo independiente](<oraculo.py>) antes de invocar a los implementadores. SHA-256 del oráculo `748d0f28f87005d9c5a260a7332615bb04c383b1898c10f0da33113ce73cd95f`; del código base `c57e415c247c39d837a6b7ad50923fbc36768bdf6761983a7d61c43323671707`. Ejecutar:

```bash
python3 .agentic/evals/paginacion/oraculo.py .agentic/evals/paginacion/pagina.py  # debe fallar
python3 .agentic/evals/paginacion/comparar.py
```

El oráculo son tres métodos unittest, uno con nueve subcasos de valores inválidos. La salida RED base fue 7 fallos y 3 errores: uno por fuera de rango y los restantes relacionados con las entradas inválidas. Los agentes no recibieron el código del oráculo; en esta sesión se les pidió no usar herramientas, pero **no se verificó un aislamiento de herramientas por sistema operativo**.

## Resultado

| Medida | Agente único | Pipeline STANDARD |
|---|---|---|
| Base sintética | `a00a7c2cf587356187e6636f9e97a9f41e229f06` | La misma |
| Candidato | `6ddd203a6fbcf66851f09673d580dbe9de7feaea`; [código](<solucion-unica.py>) | `4a2dc2dc5f1534ffb3963790db61e1054fca775f`; [código](<solucion-pipeline.py>) |
| RED/GREEN Docker, caso fuera de rango | GREEN `0`; RED común en base `42` | RED `42`, GREEN `0`, registrados en el motor |
| Oráculo independiente común | 3/3 métodos pasan | 3/3 métodos pasan |
| Firma por introspección, comparación posterior | Igual a la original | Distinta: se añaden anotaciones; los parámetros y la forma de llamada son los mismos |
| QA / SECOPS | PASS / PASS tras aclarar el dominio de `items` | PASS_WITH_WARNINGS / PASS, con finding LOW de QA por anotaciones |
| Mismo gate `STANDARD` | PASS, calculado aparte con ambos dictámenes y el check común | PASS, calculado por el motor; estado `COMPLETED` |
| Llamadas de agentes | 1 implementación + 2 revisiones y 2 aclaraciones | 8 intentos reservados: BRAIN, BENCHMARKER, SPEC, DEVELOPER, QA y SECOPS más 2 correcciones de formato |

Las dos revisiones del agente único inicialmente interpretaron que `items` debía validarse para tipos distintos de lista; R3 exige `ValueError` para `number` y `size`, mientras que lista es una precondición de `items`. Se les aclaró el contrato original y reevaluaron. No se modificó la SPEC ni el código. En el pipeline, las primeras salidas QA y SECOPS no respetaron el esquema; el motor las rechazó y ambas se reintentaron. QA reportó que las anotaciones cambian la firma introspectiva: el gate predeterminado permite LOW, pero no determina si R4 exigía identidad introspectiva estricta. **La SPEC es ambigua en ese punto; no se afirma que el candidato pipeline cumpla esa interpretación más estricta.**

Los revisores recibieron el código, la SPEC y el resumen de la batería comunicado por el operador; no ejecutaron sus propias pruebas ni verificaron el SHA de forma autónoma. Los controles automáticos son idénticos, pero las revisiones no fueron ciegas entre brazos y fueron hechas por instancias distintas. El agente único no recibió explícitamente la evidencia RED y el desarrollador del pipeline sí. `STANDARD` y agente único no hicieron el mismo número de invocaciones, y no se midieron tiempos comparables, tokens ni precio. Por ello los números no demuestran un coste o rendimiento general.

## Evidencia del motor y límites

Workflow `879bbef05b9749518421b50c351e8ff0`; SPEC `ad9ad180fd165b3781c9987674b92144211410610ce3413067e5cc42e5b88b3a`; política `b1ac61b21d39850c3905539a595207e301ca6f7e98ac23eda7a2651550f0d77d`; RED `3d33384c35d953651079f1be522b767499ea8cb0df58725d165e0ad4fc3bf5a6`; GREEN `0fd55e7bbcbdb879ccbabe1d72de18045fd8385b3c0406b9db946a8c14b1a987`; entrega `b54ce25ae4a17756d473d11fa3813e62a2b539b37b9779ec516dc54864ef4402`. El run está en un directorio local ignorado, no versionado. El commit es un snapshot Git parcial del fixture, no un commit de ZascArr.

El oráculo de tres métodos no prueba ausencia de dependencias ni identidad de firma de forma automática; Ruff aprobó ambos candidatos y se inspeccionaron los imports. `comparar.py` muestra la firma introspectiva como observación, no la convierte en gate retroactivamente. Coste, tokens y modelo realmente resuelto: desconocidos.

**Conclusión:** en este caso ambos resuelven el comportamiento probado; el pipeline aporta una advertencia útil sobre una ambigüedad de compatibilidad, pero también requirió más coordinación y dos reintentos por formato. No hay evidencia suficiente para afirmar superioridad general. Antes de usar datos privados o aprobar fusiones hacen falta aislamiento efectivo, acuerdos verificables sobre firma, más casos, repeticiones y mediciones comparables.
