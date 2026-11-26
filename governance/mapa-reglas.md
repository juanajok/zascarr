# Mapa de reglas durante la migración (propuesta)

**Estado: sin migrar.** Inventario de trabajo de la historia T1.1. Su función es demostrar cobertura regla por regla, no crear normas: cada fila apunta a la guía vigente y a un destino **propuesto**. Ninguna regla se retira hasta que su traslado esté revisado y aprobado (criterio T1.1-C02). Origen fijado: `CLAUDE.md` de la rama de la propuesta; la referencia de sección es orientativa y debe reverificarse si la guía cambia. La columna «Regla» es un resumen de trabajo, nunca el texto normativo.

| ID | Origen | Regla o decisión a conservar | Destino propuesto | Estado |
|---|---|---|---|---|
| PRE-01 | §3.1 | La capa de servicios concentra el negocio; routers finos | [Contrato de datos](contrato-datos.md#pre-01--la-capa-de-servicios-es-la-única-fuente-de-verdad-del-negocio) | migrada |
| PRE-02 | §3.1 | No mover archivos con la sesión ORM viva; conservar la deuda declarada del código heredado | [Contrato de datos](contrato-datos.md#pre-02--el-orm-nunca-cruza-un-movimiento-de-ficheros-con-la-sesión-viva) | migrada |
| PRE-03 | §3.1 | Escritura con esquemas explícitos; prohibido el mass assignment | [Contrato de seguridad](contrato-seguridad.md#pre-03--mass-assignment-prohibido-en-endpoints) | migrada |
| PRE-04 | §3.1 | Sin hotlinking en la interfaz | [Contrato de biblioteca](contrato-biblioteca.md#pre-04--sin-hotlinking-en-la-interfaz) | migrada |
| PRE-05 | §3.1 | Toda decisión de arquitectura nueva requiere ADR | [Constitución](constitution.md#pre-05--decisión-de-arquitectura-requiere-adr) | migrada |
| PRE-06 | §3.2 | Configuración centralizada; ninguna credencial utilizable por defecto; escritura atómica del entorno | [Contrato de seguridad](contrato-seguridad.md#pre-06--credenciales-del-entorno-adr-0012) | migrada |
| PRE-07 | §3.2 | Integraciones P2P y fuentes de metadatos apagadas por defecto; una actualización no las apaga en silencio | Configuración | sin migrar |
| PRE-08 | §3.2 | Healthcheck observacional y aviso de versión de solo lectura | Contratos de estado | sin migrar |
| PRE-09 | §3.2 | Actualización manual: decisión de confianza no habilita la función ni su despliegue | ADR de actualización | sin migrar |
| PRE-10 | §5 | El software gestiona, no facilita fuentes de contenido | [Visión](product-vision.md#pre-10--el-software-gestiona-nunca-facilita) | migrada |
| PRE-11 | §5 | La aceptación legal bloquea solo acciones de riesgo; nunca un middleware global | [Contrato de seguridad](contrato-seguridad.md#pre-11--la-aceptación-legal-bloquea-solo-acciones-de-riesgo) | migrada |
| PRE-12 | §5 | Cero telemetría, logs sin datos sensibles y campos de formulario explícitos | [Contrato de seguridad](contrato-seguridad.md#pre-12--privacidad-registros-y-superficie-de-api) | migrada |
| PRE-13 | §5 | Interfaz en localhost por defecto; abrir exige decisión explícita y contraseña | ADR de exposición de red | sin migrar |
| PRE-14 | §5 | Toda URL variable pasa por la validación SSRF central | [Contrato de seguridad](contrato-seguridad.md#pre-14--toda-url-variable-pasa-por-la-validación-ssrf-central) | migrada |
| PRE-15 | §5 | Un cambio sensible de contraseña espera dictamen de seguridad del SHA final | [Clasificación de riesgo](risk-classification.md#pre-15--cambio-sensible-de-contraseña-espera-seguridad-del-sha-final) | migrada |
| PRE-16 | §8 | Patrón de pruebas con sesión simulada es la referencia | [Definición de hecho](definition-of-done.md#pre-16--patrón-de-pruebas-con-sesión-simulada) | migrada |
| PRE-17 | §8 | La suite se ejecuta también con temporal en el dispositivo raíz | [Definición de hecho](definition-of-done.md#pre-17--la-suite-también-con-temporal-en-el-dispositivo-raíz) | migrada |
| PRE-18 | §8 | Sin dependencias nuevas por probar; cada bug real cierra con regresión nombrada | [Definición de hecho](definition-of-done.md#pre-18--regresión-nombrada-y-sin-dependencias-por-probar) | migrada |
| PRE-19 | §8 | Pruebas con Postgres real: base cuyo nombre lleve test, migrada a head una vez; estado alternativo en base efímera y subprocesos de Alembic sin sombra del paquete | [Definición de hecho](definition-of-done.md#pre-19--pruebas-con-postgres-real) | migrada |
| PRE-20 | §9 | Commits atómicos en español; el histórico explica el mecanismo de cada cierre | [Definición de hecho](definition-of-done.md#pre-20--git-como-documentación) | migrada |
| PRE-21 | §9 | Flujo Scrumban con límites de trabajo en curso | [Preparación](definition-of-ready.md#pre-21--flujo-de-trabajo-y-límite-de-trabajo-en-curso) | migrada |
| PRE-22 | §9.1 | El piloto de ingeniería local queda fuera del runtime y no sustituye CI ni aprobaciones | Índice y ADR del piloto | sin migrar |
| PRE-23 | §10 | Antipatrones explícitos del proyecto, con sus excepciones | Arquitectura y seguridad | sin migrar |
| PRE-24 | §11 | Documentos vivos: consultar antes de tocar cada área | Índice de fuentes | sin migrar |
| PRE-25 | §12 | Principios de modelo y datos ya validados por comparación | ADR y contratos | sin migrar |
| PRE-26 | §13 | Benchmark proporcional antes de cambios grandes; la ficha informa, no aprueba | [Preparación](definition-of-ready.md#pre-26--benchmark-proporcional-antes-de-implementar) | migrada |
| PRE-27 | §13 | Barrera legal por archivo antes de reutilizar una implementación | [Benchmark de referencias](../docs/design/benchmark-referencias.md#barrera-legal-de-reutilización-regla-migrada-pre-27) | migrada |
| PRE-28 | §14 | El glosario fija superficie y no renombra datos persistidos | Glosario | sin migrar |
| PRE-29 | §4 | Nada bloqueante en handlers asíncronos; descargas externas con semáforo | NFR de rendimiento | sin migrar |
| PRE-30 | §4 | Cortesía compartida por fuente y por host efectivo, también en redirecciones | [Contrato de seguridad](contrato-seguridad.md#pre-30--cortesía-compartida-por-fuente-y-por-host-efectivo) | migrada |
| PRE-31 | §4 | Caché local-first y reglas de revalidación de estáticos | [Contrato de biblioteca](contrato-biblioteca.md#pre-31--caché-local-first-y-revalidación) | migrada |
| PRE-32 | §4 | Portadas locales y externas separadas; lectura RAR acotada y recordada | [Contrato de biblioteca](contrato-biblioteca.md#pre-32--portadas-de-archivo-de-fuente-externa-y-lectura-de-rar) | migrada |
| PRE-33 | §6 | Lenguaje llano, estados visibles y tarjetas tolerantes al fallo | Diseño y accesibilidad | sin migrar |
| PRE-34 | §6 | Fuentes y marca locales, con licencias y variantes por tamaño | Sistema de diseño | sin migrar |
| PRE-35 | §6 | Tramas, contraste, botones, avisos y títulos con sus excepciones | Sistema de diseño | sin migrar |
| PRE-36 | §6 | Cifras coherentes y presupuesto textual con umbrales provisionales | Contratos de interfaz | sin migrar |
| PRE-37 | §6 | El sistema de diseño se consulta antes de cambiar una pantalla | [Contrato de biblioteca](contrato-biblioteca.md#pre-37--el-sistema-de-diseño-se-consulta-y-su-deuda-no-se-copia) | migrada |
| PRE-38 | §7 | Migraciones aplicadas inmutables y reglas de tipos Postgres | [Contrato de datos](contrato-datos.md#pre-38--migraciones-aplicadas-inmutables-y-tipos-postgres-explícitos) | migrada |
| PRE-39 | §14 | Conceptos de superficie y reglas de contexto entre términos | [Glosario](glossary.md#reglas-de-contexto-migradas-de-pre-39) | migrada |
| PRE-40 | Cabecera | Toda decisión nueva sobre cómo se trabaja se registra el día que se decide | [Constitución](constitution.md#pre-40--registrar-las-decisiones-del-modo-de-trabajo) | migrada |
| PRE-41 | §1 | Producto para el coleccionista y presupuesto de Raspberry Pi | [Visión](product-vision.md#pre-41--producto-persona-y-restricción-de-plataforma) | migrada |
| PRE-42 | §2 | Convenciones de lenguaje, tipos e imports; aclarar la tensión del ejemplo de nombres | Guía técnica | sin migrar |
| PRE-43 | §2 | Justificar dependencias y centralizar enums del dominio | Guía técnica | sin migrar |


### Desglose de PRE-33

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-33-1 | Español llano; los errores técnicos se traducen a causa y acción | Diseño y textos | sin migrar |
| PRE-33-2 | Semáforos visibles con texto concreto; un servicio apagado en Ajustes no es fallo | Contratos de interfaz | sin migrar |
| PRE-33-3 | Sin diálogos nativos ni balas invisibles; la limitación de automatización se documenta, no se oculta | Guía de pruebas de interfaz | sin migrar |
| PRE-33-4 | Tarjetas tolerantes al fallo: marcador de portada y campo ausente con icono | Diseño de componentes | sin migrar |
| PRE-33-5 | Texto informativo de 14 px como mínimo, con la única excepción declarada y su prueba | Accesibilidad | sin migrar |

### Desglose de PRE-34

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-34-1 | Dos familias libres servidas por la app, nunca desde CDN; ni comerciales ni de rotulación | Sistema de diseño | sin migrar |
| PRE-34-2 | Anton solo en mayúsculas; frases en Archivo; los chips fijan su fuente | Sistema de diseño | sin migrar |
| PRE-34-3 | Cifras comparables con cifras tabulares | Sistema de diseño | sin migrar |
| PRE-34-4 | Iconos SVG de trazo con su aviso de licencia; nunca caracteres de texto | Iconografía | sin migrar |
| PRE-34-5 | Marca y variantes por tamaño, con reglas en su README | Marca | sin migrar |

### Desglose de PRE-35

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-35-1 | Trama donde no hay texto que leer, con porcentajes máximos y apagado por preferencias; una prueba exige que cada trama nueva esté en ese bloque | Accesibilidad y diseño | sin migrar |
| PRE-35-2 | Desalineamiento de planchas solo en el rótulo de la página de error | Sistema de diseño | sin migrar |
| PRE-35-3 | Un único botón principal por pantalla, con la excepción del verde de aceptación | Componentes | sin migrar |
| PRE-35-4 | Un aviso no se representa como botón | Componentes | sin migrar |
| PRE-35-5 | Títulos de frase o ruta en Archivo; los h1 de pantalla siguen en Anton | Sistema de diseño | sin migrar |

### Desglose de PRE-36

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-36-1 | Las cifras del Inicio cuadran; lo del disco va aparte con su fecha y motivo | Contratos de Inicio | [Contrato de biblioteca](contrato-biblioteca.md#pre-36-1--las-cifras-del-inicio-cuadran) | migrada |
| PRE-36-2 | Frase de entrada de 20 palabras como máximo y 50 palabras visibles antes de la primera acción | Presupuesto de texto | sin migrar |
| PRE-36-3 | La garantía va junto a la acción con efecto y en su confirmación | Presupuesto de texto | sin migrar |
| PRE-36-4 | Resumen antes que listado; mayúsculas solo en rótulos de tres palabras o menos | Presupuesto de texto | sin migrar |
| PRE-36-5 | Los textos explican la tarea, no el contrato | Presupuesto de texto | sin migrar |
| PRE-36-6 | Umbrales provisionales hasta validarlos con uso real | Presupuesto de texto | sin migrar |

### Desglose de PRE-37

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-37-1 | El sistema de diseño se consulta antes de pintar una pantalla o tocar el CSS | Índice de fuentes | [Contrato de biblioteca](contrato-biblioteca.md#pre-37-1--consultar-antes-de-pintar-o-tocar-estilos) | migrada |
| PRE-37-2 | La deuda declarada de la última revisión no se copia en pantallas nuevas | Diseño y accesibilidad | [Contrato de biblioteca](contrato-biblioteca.md#pre-37-2--la-deuda-declarada-no-se-replica) | migrada |

### Desglose de PRE-06

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-06-1 | Ninguna ruta de arranque soportada sirve con credencial obligatoria ausente, vacía o conocida por defecto | Contrato de credenciales | [Contrato de seguridad](contrato-seguridad.md#pre-06-1--ninguna-credencial-utilizable-por-defecto) | migrada |
| PRE-06-2 | `DB_PASSWORD` la genera el instalador y la rechazan el servicio de credenciales y la app; nunca un valor real por defecto en Compose | Contrato de credenciales | [Contrato de seguridad](contrato-seguridad.md#pre-06-2--db_password-la-genera-el-instalador-y-se-verifica) | migrada |
| PRE-06-3 | El entorno se escribe solo de forma atómica, sin copias, y es de root con permisos 600 | Contrato de credenciales | [Contrato de seguridad](contrato-seguridad.md#pre-06-3--el-entorno-se-escribe-de-forma-atómica) | migrada |
| PRE-06-4 | El usuario de servicio no es dueño del código ni de la carpeta del entorno | Contrato de credenciales | [Contrato de seguridad](contrato-seguridad.md#pre-06-4--el-usuario-de-servicio-no-posee-el-entorno-ni-el-código) | migrada |
| PRE-06-5 | Los scripts de operación no imprimen credenciales | Guía de operación | [Contrato de seguridad](contrato-seguridad.md#pre-06-5--los-scripts-de-operación-no-imprimen-credenciales) | migrada |

### Desglose de PRE-12

| Sub-regla | Regla a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-12-1 | Datos cacheados son uso privado y la telemetría es cero | Seguridad y privacidad | [Contrato de seguridad](contrato-seguridad.md#pre-12-1--datos-cacheados-son-uso-privado-telemetría-cero) | migrada |
| PRE-12-2 | No se redistribuye contenido; obligaciones de la tabla de fuentes | Marco legal | [Contrato de seguridad](contrato-seguridad.md#pre-12-2--no-se-redistribuye-contenido) | migrada |
| PRE-12-3 | Los registros no llevan datos sensibles; si un error los lleva, se sanea antes | Contrato de logs | [Contrato de seguridad](contrato-seguridad.md#pre-12-3--registros-sin-datos-sensibles) | migrada |
| PRE-12-4 | Los endpoints mutables usan campos explícitos y su caché está documentada; el rechazo de la puerta legal redirige | Contrato legal y de API | [Contrato de seguridad](contrato-seguridad.md#pre-12-4--endpoints-mutables-explícitos-y-caché-documentada) | migrada |

### Desglose de PRE-23

| Sub-regla | Antipatrón a conservar | Destino propuesto | Estado |
|---|---|---|---|
| PRE-23-1 | SPA, build de Node o framework reactivo en la interfaz; excepción única del lector con un script sin build | Arquitectura de interfaz | sin migrar |
| PRE-23-2 | `create_type=False` esperando que funcione sin `postgresql.ENUM` explícito | Guía de migraciones | sin migrar |
| PRE-23-3 | `Wishlist(**data)` desde el cuerpo crudo; cerrado con esquemas Pydantic | Seguridad de API | sin migrar |
| PRE-23-4 | Hotlinking en la interfaz | Seguridad de interfaz | sin migrar |
| PRE-23-5 | Copiar scrapers de referencia sin verificar en vivo; el caso Tebeosfera y sus redirecciones | Contrato de clientes externos | sin migrar |
| PRE-23-6 | Credenciales o fuentes por defecto en configuración o bootstrap | Configuración y credenciales | sin migrar |
| PRE-23-7 | Middleware global de aceptación legal; debe ser dependencia, no middleware | Contrato legal | sin migrar |

Hoy hay 39 sub-reglas repartidas en ocho bloques. Cada sub-regla necesita su propia decisión de traslado: desglosar la fila no la migra.

## Cobertura incompleta: filas que agrupan sub-reglas

Una fila puede resumir varias sub-reglas, y eso **no** cuenta como traslado completo. Hoy agrupan como mínimo:

- **PRE-23**: desglosada arriba en siete sub-reglas (PRE-23-1 a PRE-23-7), cada una con su excepción y pendiente de traslado propio.
- **PRE-33 a PRE-37**: desglosadas arriba (interfaz, tipografía, tramas, presupuesto textual y referencia de diseño), con sus excepciones por tamaño y contraste.
- **PRE-06 y PRE-12**: desglosadas arriba en cinco y cuatro sub-reglas respectivamente; cada una necesita su propio traslado.

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

## Estado de los destinos

Los destinos que faltaban ya existen, pero **en otra rama sin fusionar**: [#1320](https://github.com/juanajok/zascarr/pull/1320) añade `governance/risk-classification.md`, `definition-of-ready.md` y `definition-of-done.md`. Esta rama (#1312) no los contiene, así que migrar aquí esas reglas crearía enlaces a ficheros inexistentes.

| Destino | Estado | Reglas que desbloquea |
|---|---|---|
| `risk-classification.md` | En #1320 | PRE-03, PRE-09, PRE-15, PRE-27 |
| `definition-of-ready.md` | En #1320 | PRE-21, PRE-26 |
| `definition-of-done.md` | En #1320 | PRE-16, PRE-17, PRE-18, PRE-19, PRE-36-6 |
| Contratos de dominio | Pendiente de decisión | PRE-01, PRE-02, PRE-06, PRE-11, PRE-12, PRE-14, PRE-30, PRE-31, PRE-32, PRE-38 |
| Piloto `.agentic` | Ya vive en ADR 0027 | PRE-22: no se duplica aquí |

Consecuencia: **4 reglas migradas** (PRE-05, PRE-10, PRE-40, PRE-41) y 39 pendientes. El siguiente lote se hace cuando ambas ramas estén integradas; hacerlo antes produciría enlaces rotos, que la propia guarda del repositorio rechaza.

## Propuesta: destinos para los contratos de dominio

Quedan 35 reglas sin destino. Las de contratos de dominio no pueden migrarse a un documento que no existe, y crearlos exige decidir su granularidad. Propongo **tres** documentos, no once:

| Documento propuesto | Reglas que cubriría |
|---|---|
| `governance/contrato-datos.md` | PRE-01, PRE-02, PRE-38 (servicios, movimiento y sesión, migraciones) |
| `governance/contrato-seguridad.md` | PRE-03, PRE-06, PRE-11, PRE-12, PRE-14, PRE-30 (API, credenciales, legal, red) |
| `governance/contrato-biblioteca.md` | PRE-04, PRE-31, PRE-32, PRE-36-1, PRE-37 (portadas, caché, lectura de archivos, cifras del Inicio, sistema de diseño) |

Cada uno se escribe leyendo el código vigente para confirmar el comportamiento, no copiando la guía. Sin tu decisión sobre esta agrupación no los creo: hacerlo por mi cuenta sería inventar autoridad nueva.
