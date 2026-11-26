# Mapa de reglas durante la migración (propuesta)

**Estado: sin migrar.** Inventario de trabajo de la historia T1.1. Su función es demostrar cobertura regla por regla, no crear normas: cada fila apunta a la guía vigente y a un destino **propuesto**. Ninguna regla se retira hasta que su traslado esté revisado y aprobado (criterio T1.1-C02). Origen fijado: `CLAUDE.md` de la rama de la propuesta; la referencia de sección es orientativa y debe reverificarse si la guía cambia. La columna «Regla» es un resumen de trabajo, nunca el texto normativo.

| ID | Origen | Regla o decisión a conservar | Destino propuesto | Estado |
|---|---|---|---|---|
| PRE-01 | §3.1 | La capa de servicios concentra el negocio; routers finos | Arquitectura de dominio | sin migrar |
| PRE-02 | §3.1 | No mover archivos con la sesión ORM viva; conservar la deuda declarada del código heredado | Arquitectura de dominio | sin migrar |
| PRE-03 | §3.1 | Escritura con esquemas explícitos; prohibido el mass assignment | Arquitectura y seguridad | sin migrar |
| PRE-04 | §3.1 | Sin hotlinking en la interfaz | Seguridad de interfaz | sin migrar |
| PRE-05 | §3.1 | Toda decisión de arquitectura nueva requiere ADR | Gobierno de ADR | sin migrar |
| PRE-06 | §3.2 | Configuración centralizada; ninguna credencial utilizable por defecto; escritura atómica del entorno | Configuración y credenciales | sin migrar |
| PRE-07 | §3.2 | Integraciones P2P y fuentes de metadatos apagadas por defecto; una actualización no las apaga en silencio | Configuración | sin migrar |
| PRE-08 | §3.2 | Healthcheck observacional y aviso de versión de solo lectura | Contratos de estado | sin migrar |
| PRE-09 | §3.2 | Actualización manual: decisión de confianza no habilita la función ni su despliegue | ADR de actualización | sin migrar |
| PRE-10 | §5 | El software gestiona, no facilita fuentes de contenido | Visión y marco legal | sin migrar |
| PRE-11 | §5 | La aceptación legal bloquea solo acciones de riesgo; nunca un middleware global | Contrato legal | sin migrar |
| PRE-12 | §5 | Cero telemetría, logs sin datos sensibles y campos de formulario explícitos | Seguridad y privacidad | sin migrar |
| PRE-13 | §5 | Interfaz en localhost por defecto; abrir exige decisión explícita y contraseña | ADR de exposición de red | sin migrar |
| PRE-14 | §5 | Toda URL variable pasa por la validación SSRF central | Contrato de red | sin migrar |
| PRE-15 | §5 | Un cambio sensible de contraseña espera dictamen de seguridad del SHA final | Política de revisión | sin migrar |
| PRE-16 | §8 | Patrón de pruebas con sesión simulada es la referencia | Guía técnica de pruebas | sin migrar |
| PRE-17 | §8 | La suite se ejecuta también con temporal en el dispositivo raíz | Guía de pruebas y CI | sin migrar |
| PRE-18 | §8 | Sin dependencias nuevas por probar; cada bug real cierra con regresión nombrada | Definición de hecho | sin migrar |
| PRE-19 | §8 | Pruebas con Postgres real: base cuyo nombre lleve test, migrada a head una vez; estado alternativo en base efímera y subprocesos de Alembic sin sombra del paquete | Guía de Postgres | sin migrar |
| PRE-20 | §9 | Commits atómicos en español; el histórico explica el mecanismo de cada cierre | Guía de contribución | sin migrar |
| PRE-21 | §9 | Flujo Scrumban con límites de trabajo en curso | Planificación | sin migrar |
| PRE-22 | §9.1 | El piloto de ingeniería local queda fuera del runtime y no sustituye CI ni aprobaciones | Índice y ADR del piloto | sin migrar |
| PRE-23 | §10 | Antipatrones explícitos del proyecto, con sus excepciones | Arquitectura y seguridad | sin migrar |
| PRE-24 | §11 | Documentos vivos: consultar antes de tocar cada área | Índice de fuentes | sin migrar |
| PRE-25 | §12 | Principios de modelo y datos ya validados por comparación | ADR y contratos | sin migrar |
| PRE-26 | §13 | Benchmark proporcional antes de cambios grandes; la ficha informa, no aprueba | Procedimiento de benchmark | sin migrar |
| PRE-27 | §13 | Barrera legal por archivo antes de reutilizar una implementación | Procedimiento de licencias | sin migrar |
| PRE-28 | §14 | El glosario fija superficie y no renombra datos persistidos | Glosario | sin migrar |
| PRE-29 | §4 | Nada bloqueante en handlers asíncronos; descargas externas con semáforo | NFR de rendimiento | sin migrar |
| PRE-30 | §4 | Cortesía compartida por fuente y por host efectivo, también en redirecciones | Contrato de red | sin migrar |
| PRE-31 | §4 | Caché local-first y reglas de revalidación de estáticos | Contrato HTTP | sin migrar |
| PRE-32 | §4 | Portadas locales y externas separadas; lectura RAR acotada y recordada | Contrato de portadas | sin migrar |
| PRE-33 | §6 | Lenguaje llano, estados visibles y tarjetas tolerantes al fallo | Diseño y accesibilidad | sin migrar |
| PRE-34 | §6 | Fuentes y marca locales, con licencias y variantes por tamaño | Sistema de diseño | sin migrar |
| PRE-35 | §6 | Tramas, contraste, botones, avisos y títulos con sus excepciones | Sistema de diseño | sin migrar |
| PRE-36 | §6 | Cifras coherentes y presupuesto textual con umbrales provisionales | Contratos de interfaz | sin migrar |
| PRE-37 | §6 | El sistema de diseño se consulta antes de cambiar una pantalla | Índice de fuentes | sin migrar |
| PRE-38 | §7 | Migraciones aplicadas inmutables y reglas de tipos Postgres | Guía de migraciones | sin migrar |
| PRE-39 | §14 | Conceptos de superficie y reglas de contexto entre términos | Glosario | sin migrar |
| PRE-40 | Cabecera | Toda decisión nueva sobre cómo se trabaja se registra el día que se decide | Constitución y guía | sin migrar |
| PRE-41 | §1 | Producto para el coleccionista y presupuesto de Raspberry Pi | Visión | sin migrar |
| PRE-42 | §2 | Convenciones de lenguaje, tipos e imports; aclarar la tensión del ejemplo de nombres | Guía técnica | sin migrar |
| PRE-43 | §2 | Justificar dependencias y centralizar enums del dominio | Guía técnica | sin migrar |

## Cobertura incompleta: filas que agrupan sub-reglas

Una fila puede resumir varias sub-reglas, y eso **no** cuenta como traslado completo. Hoy agrupan como mínimo:

- **PRE-23**: los siete antipatrones de la sección 10, cada uno con su excepción.
- **PRE-33 a PRE-36**: viñetas de interfaz, tipografía, tramas y presupuesto textual, con excepciones por tamaño y contraste.
- **PRE-06 y PRE-12**: reglas de credenciales, privacidad y campos de formulario que se verifican por separado.

Antes de marcar «migrada» una de estas filas hay que desglosarla en sub-reglas con su propia decisión. Mientras tanto, C01 sigue en PARCIAL.

## Fuera de este inventario

- La regla SDD+TDD que aparece en el checkout principal **no** está en la baseline versionada inspeccionada; se conserva sin publicar ni atribuir hasta decisión expresa (T1.1-C08).
- Las referencias históricas, revisiones de ADR duplicados y cifras de inventario no son reglas operativas: viven en la evidencia de H0.

## Cómo se cierra una fila

1. Redactar el texto de destino conservando matices y excepciones.
2. Comparar con el origen y registrar diferencias con motivo.
3. Revisar con el mantenedor y obtener aprobación del traslado.
4. Solo entonces retirar la copia anterior y marcar aquí «migrada» con su SHA.

Este documento no acredita ejecución: las filas describen intención de traslado, no capacidades verificadas.
