# Especificación SDD-T1.2: inicializar OpenSpec sin pisar el cambio

**Estado:** aprobada por el mantenedor el 2026-11-26. La aprobación del contrato no autoriza fusión ni despliegue. No se ha publicado ni ejecutado. Depende de que exista una versión de OpenSpec utilizable: el pin de #1293 sigue **candidato** (falta instalación limpia del lock exacto y revisión de suministro/licencias). Esta especificación no adopta ese pin.

## Problema

La propuesta SDD-001 ya vive como cambio OpenSpec en `openspec/changes/sdd-001/`, pero el repositorio no tiene la configuración de proyecto ni plantillas propias. Inicializar la herramienta de forma descuidada puede sobrescribir ese cambio, introducir telemetría o añadir un runtime Node al producto.

## Alcance

Solo andamiaje documental y de configuración: `openspec/config.yaml`, plantillas de trabajo, reglas de identificadores y definiciones de preparación/cierre. No cambia comportamiento del producto, no toca CI bloqueante, no añade dependencias de runtime y no activa gates.

## Criterios propuestos

- **T1.2-C01 No destructivo.** Antes y después de inicializar, los ficheros de `openspec/changes/sdd-001/` conservan sus hashes; cualquier diferencia se explica y se revierte, no se normaliza.
- **T1.2-C02 Configuración explícita.** La configuración de proyecto fija la versión de herramienta usada, desactiva telemetría y actualización automática, y no contiene credenciales ni rutas personales.
- **T1.2-C03 Plantillas con contrato.** Existen plantillas de delta, diseño, tareas, benchmark y evidencia con los campos obligatorios; una plantilla incompleta se detecta antes de crear un cambio real.
- **T1.2-C04 Identificadores.** Regla escrita para IDs de requisito, escenario y tarea, con unicidad comprobable y sin reutilizar un ID retirado. La trazabilidad tiene un único registro por cambio.
- **T1.2-C05 DoR y DoD.** Definiciones de preparación y cierre ligadas a la clasificación de riesgo; un cambio trivial no arrastra controles de uno alto.
- **T1.2-C06 Validación con caso negativo.** La validación estricta del cambio existente pasa y un delta manipulado falla por el motivo esperado; el resultado registra comando y entorno.
- **T1.2-C07 Sin impacto en producto.** El directorio de herramienta queda fuera del contexto Docker y del runtime; se demuestra con la prueba de exclusión, no por convención.
- **T1.2-C08 Reversión.** Retirar la configuración y las plantillas no altera specs, evidencias ni historial; se documenta qué se revierte y qué se conserva.

## Pruebas previstas

| Criterio | Verificación | Estado |
|---|---|---|
| C01 | Hashes de `openspec/changes/sdd-001/` antes/después; diff vacío | NOT RUN |
| C02 | Lectura de la configuración generada; comprobar ausencia de telemetría y credenciales | NOT RUN |
| C03–C04 | Caso negativo por plantilla y por ID duplicado o reutilizado | NOT RUN |
| C05 | Revisión con el mantenedor de las definiciones y de su proporcionalidad | NOT RUN |
| C06 | `validate` estricto en verde y delta manipulado en rojo con motivo esperado | NOT RUN |
| C07 | Prueba de exclusión de `.dockerignore` y build sin Node | NOT RUN |
| C08 | Ejercicio de reversión en rama desechable | NOT RUN |

## Riesgos y límites

- Si la instalación limpia del lock falla o no se acredita, esta historia no debe ejecutarse con el pin candidato como si estuviera aprobado.
- Inicializar puede generar skills para harnesses; generarlos **no** demuestra que se carguen (T0.4 sigue NOT RUN).
- La validación estructural no acredita semántica: un `Purpose` de relleno ya provocó un falso verde en H0.
- No se promete protección de rama ni gates: eso es T3.4/T5.3 y requiere decisión aparte.

## Secuencia propuesta

1. Aprobar esta SPEC (o su sustituta) y fijar el SHA del contrato.
2. Capturar hashes del cambio existente.
3. Inicializar en rama desechable y comparar; dejar fuera del commit cualquier fichero generado que no corresponda.
4. Añadir plantillas e IDs con pruebas negativas.
5. Registrar evidencia real y revisar con el mantenedor antes de dar la historia por cerrada.
