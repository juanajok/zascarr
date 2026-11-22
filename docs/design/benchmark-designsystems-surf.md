# Ficha de benchmarking — los 90 sistemas de diseño de designsystems.surf (2026-11-22)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13), pedida por el PO: estudiar los
> sistemas de diseño que recoge designsystems.surf y tomar lo que sirva a ZascArr. Es **insumo, no
> aprobación**; decide el PO. Contrastada con `main@9fe0be06` y con el sistema de diseño publicado
> (que manda sobre la copia del repo).

**Barrera legal (CLAUDE.md §13).** Se toman **patrones y reglas**, redactados de nuevo en español; ni
código, ni textos, ni ilustraciones, ni iconos. Las licencias varían: GOV.UK (código MIT, contenido
OGL), Cloudscape (Apache-2.0), GitLab Pajamas (MIT), Wikimedia Codex (GPL-2.0 y CC BY-SA), Atlassian
y Polaris (documentación propietaria). Inspirarse en una regla no obliga; copiar un componente sí.

## Método

1. **Barrido de los 90** (todas las fichas de designsystems.surf, una sola página sin paginar): sus
   fundamentos, componentes y guías. Sirve para saber qué temas trata la mayoría y quién los trata
   mejor.
2. **Inmersión por tema** en las guías oficiales de quien mejor lo resuelve: errores y formularios
   (GOV.UK, USWDS, Atlassian), estados vacíos y carga (GitLab Pajamas, Cloudscape), avisos (GOV.UK,
   GitLab, Cloudscape), filtrado, colecciones y borrado (Cloudscape, GitLab), contenido y
   accesibilidad (Wikimedia Codex, GOV.UK, GitLab), paneles, tema oscuro y divulgación progresiva
   (GitLab, Cloudscape, Atlassian, Primer).
3. **Contraste con ZascArr**: cada idea se mira en `main` antes de proponerla (lo que ya existe consta
   como «ya lo tenemos»).

## Lo que dice el barrido

- **Temas casi universales:** botón, campos, avisos (banner y snackbar), indicadores de progreso,
  tablas, pestañas, paginación. ZascArr los tiene todos.
- **Estado vacío como componente propio:** lo documentan unos 30 de los 90 (GitLab, Cloudscape,
  Polaris, Atlassian, Salesforce, Ant, Elastic, Orbit…). ZascArr lo tiene (`ui.estado_vacio`).
- **Voz y tono:** unos 40 de los 90 lo tienen como fundamento. ZascArr también (Voz y contenido).
- **Ciclo de vida del componente** (estable, en pruebas, obsoleto): Primer, GitLab, USWDS, Polaris,
  Thumbtack, Twilio… ZascArr solo tiene la lista «heredado (V14)».
- **Datos sin mucho de lo nuestro:** casi ninguno documenta tramas, didascalias ni rotulación: la
  identidad de tebeo de ZascArr no tiene referente en esta lista, y no hace falta.
- **No documentan página de tema oscuro como tal** (salvo Atlassian, Basis, Brainly, Ant, Sigma); la
  mayoría lo resuelve con «Theming». ZascArr ya tiene los dos temas con contraste en la CI.

## Resultado por idea

Resultado: **adoptar** (tal cual), **adaptar** (cambia algo), **lo propio** (ya lo tenemos o casi),
**descartar**. «Ya lo tenemos» se ha comprobado en `main`.

### A. Errores y formularios

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| A1 | Con un error o más, **resumen de errores** al principio («Hay un problema») con un enlace a cada campo, y el foco en el resumen | GOV.UK (error summary) | El foco va al primer campo con error (#1227); no hay resumen | **Adaptar:** resumen solo con 2 errores o más; con uno, el foco al campo, como ahora (Primer pide resumen desde 3) |
| A2 | `<title>` con el prefijo «Error: » al volver con errores | GOV.UK (validation) | No | **Adoptar** |
| A3 | El mensaje reutiliza las palabras de la etiqueta; **instrucción** si falta («Escribe el título») y **descripción** si el formato no vale («El año va en cifras, por ejemplo 1987») | GOV.UK (error message) | Mezcla («El título no puede estar vacío.») | **Adoptar** como regla de Voz |
| A4 | **Palabras vetadas** en mensajes: «por favor», «lo sentimos», «válido/inválido», «ups», «error» genérico, «inténtalo» | GOV.UK, Wikimedia, GitLab | Casi limpio; el resumen del etiquetado dice «N inválidos» (`services/tagger.py`) | **Adoptar** como lista en Voz y contenido |
| A5 | **No desactivar el envío** aunque falte algo; decirlo con el error | Atlassian, Primer, UNICEF | Hecho en #1227 para dos casos | **Lo propio:** convertirlo en regla del sistema |
| A6 | **Validar al enviar**, no al salir del campo; validar siempre en el servidor | GOV.UK | Así se hace | **Lo propio:** escribirlo |
| A7 | **No borrar lo escrito** al volver con errores | GOV.UK | Así se hace (`valores`) | **Lo propio** |
| A8 | Página de **confirmación** al acabar una operación larga: qué ha pasado, qué pasa después y a dónde ir | GOV.UK (confirmation pages) | Parcial (resultados de vinculación y registro) | **Adaptar:** plantilla de resultado con esas tres partes |

### B. Estados vacíos y sin resultados

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| B1 | **Distinguir «vacío» de «sin resultados»**: el segundo tiene título fijo y una sola acción, «Quitar filtros» | Cloudscape, GitLab | Biblioteca sin resultados: «Prueba a quitar algún filtro de los de arriba.» (sin acción, con dirección y «prueba») | **Adoptar:** `ui.estado_vacio("Sin resultados", "Ninguna serie cumple estos filtros.", ("Quitar filtros", url))` |
| B2 | Título ≤ 5 palabras, sin punto; descripción en frase completa; **una** acción; no repetir el título | GitLab | La macro lo permite; no está escrito | **Adoptar** como regla de EstadoVacio |
| B3 | Un estado vacío **no** se usa para errores (para eso, aviso con reintento) | Cloudscape | Así se hace en Biblioteca | **Lo propio:** escribirlo |
| B4 | **Valor vacío** con una sola convención («—» en tablas y listas) | Cloudscape | Conviven «—», «No consta», «Sin dato» | **Adaptar:** «No consta» en fichas (frase), «—» en tablas; una regla |

### C. Carga y tareas largas

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| C1 | **Umbrales:** < 1 s nada; 1–10 s indicador en el propio botón y sin repetir la acción; > 10 s barra de progreso y que se pueda seguir trabajando (tarea en segundo plano) | Cloudscape, Primer | Indicadores sueltos; panel de tareas en curso (#991) para lo largo | **Adoptar** como regla de Interacción: une lo que ya hay |
| C2 | **Recarga:** los datos siguen visibles y usables mientras se refresca; al acabar, la hora de la última actualización en una región viva | Cloudscape | «Actualizar la biblioteca» ya muestra «Última vez · Próxima» | **Lo propio** |
| C3 | «**Cargar más**» lleva el foco al primer elemento nuevo | GitLab | Los pliegues usan `<details>`; no hay «cargar más» | **Adoptar** si se añade alguno |
| C4 | **Esqueleto** en vez de hueco mientras llega un fragmento (evita saltos) | Cloudscape | Sagas, Etiquetas y Colecciones llegan tarde y empujan lo de abajo | **Adaptar:** reservar alto en el marcador, sin JavaScript |

### D. Avisos

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| D1 | **Un aviso de página como mucho**; si hay varios, se combinan o va el más grave | GOV.UK, GitLab | No hay regla | **Adoptar** |
| D2 | El aviso de **éxito desaparece al navegar** | GOV.UK | **Sin comprobar:** los avisos llegan por `?guardado=` en la URL; puede que se repitan al recargar | **Adaptar** si se confirma: limpiar la URL tras pintarlo |
| D3 | **Tres alturas:** global (bajo la cabecera), de página (bajo el `h1`) y en contexto (junto a lo que afecta) | GitLab | Sin regla escrita | **Adoptar** como regla de Aviso |
| D4 | Un aviso que **necesita acción** recibe el foco; uno informativo, región viva educada | GitLab, GOV.UK | Así lo hacen `ui.aviso` y `ui.region_viva` | **Lo propio** |
| D5 | Ningún aviso **descartable** si bloquea o si su condición sigue; los de condición se van solos | GitLab | No hay descartables | **Lo propio** |

### E. Filtrado y colecciones

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| E1 | **La URL es la fuente única** del filtro: se lee al cargar, lo que no vale se descarta | Cloudscape | Biblioteca filtra por parámetros GET | **Lo propio:** escribir la regla (descartar lo inválido sin error) |
| E2 | Botón «Filtros» con el **número aplicado** cuando el panel está cerrado | GitLab | Ya: «Filtros (N)» | **Lo propio** |
| E3 | Búsqueda a la izquierda, filtros, orden a la derecha; 3–5 filtros a la vista | GitLab | Así es la barra | **Lo propio** |
| E4 | **Tabla** para comparar datos; **tarjetas** si hay imagen | Cloudscape | Vista «tarjetas» y «lista» | **Lo propio** |

### F. Acciones destructivas

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| F1 | **Tres niveles por gravedad:** bajo, sin fricción; medio, un paso más (plegado); alto, confirmación con las consecuencias listadas | Cloudscape, GitLab | «Retirar» plegado + página con lo que se retira; «Borrar nota» con «Sí, borrar nota» | **Adaptar:** la confirmación es una **página o paso visible**, nunca un modal (sistema de diseño: sin diálogos) |
| F2 | En lo **irreversible y en cascada**, escribir el nombre para confirmar | Cloudscape, GitLab, Atlassian | No | **Adaptar** solo si hay un caso: hoy nada borra archivos (CLAUDE.md: «no se mueve ni se renombra nada»); candidato, borrar una colección con sus decisiones |
| F3 | Botones con **verbo y objeto en los dos lados**: «Sí, retirar la serie» / «No, conservarla» | GitLab | Ya en parte («Sí, borrar nota») | **Adoptar** como regla de Botón |

### G. Contenido

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| G1 | **El mismo término en el título y en su botón** | Wikimedia | Glosario §14 | **Lo propio** |
| G2 | **Sin indicaciones de posición** («arriba», «a la derecha»): no sirven a un lector de pantalla ni en el móvil | Cloudscape, Wikimedia, GOV.UK | Al menos «los de arriba» en Biblioteca | **Adoptar** |
| G3 | **«Elige», no «haz clic»** | Cloudscape, GOV.UK | Limpio | **Lo propio:** escribirlo |
| G4 | **Fechas** sin ordinales y rangos con «a» | GOV.UK | `fecha_llana` | **Lo propio** |
| G5 | Lista breve de **términos preferidos** de interfaz | Wikimedia | Glosario §14 | **Lo propio** |

### H. Paneles, tema y otros

| # | Idea | Fuente | En ZascArr hoy | Resultado |
|---|---|---|---|---|
| H1 | Panel en **12 columnas** que pasa a una; lo general arriba, el detalle abajo; disposición fija cuando el orden importa | GitLab, Cloudscape | Ajustes; propuesta de plantillas | **Lo propio** (respalda `plantillas-de-pagina.md`) |
| H2 | **Tendencias, no solo una foto:** «+N esta semana» junto a cada cifra | GitLab | Las cifras del Inicio son fotos | **Mejorar:** candidata, con los datos de `import_runs`; decide el PO |
| H3 | **Foco y selección distintos**; lo seleccionado lleva una segunda señal | Atlassian | Foco `cyan-t`; activo en amarillo con borde | **Lo propio** |
| H4 | **Divulgación progresiva** con icono y texto; nunca solo texto | Primer | `<details>` con ▸ y texto | **Lo propio** |
| H5 | **Ciclo de vida** de cada componente (en pruebas, estable, obsoleto) en el sistema de diseño | Primer, GitLab, USWDS | Solo «Heredado (V14)» | **Adaptar:** una columna «estado» en la tabla de componentes |

### Descartado

- Modales de confirmación (Cloudscape, GitLab, Atlassian): el sistema de diseño los prohíbe.
- Analítica de uso en cada estado vacío (GitLab): telemetría cero (CLAUDE.md §5.3).
- Paneles configurables y arrastrables (GitLab, Cloudscape): JavaScript y estado; ADR 0001.
- Recarga automática por intervalo como norma (Cloudscape, 10 s): en la Pi solo se sondea lo que está
  en marcha (y el hallazgo 8 de `benchmark-calidad-front.md` ya mostró el riesgo).
- Ilustraciones de estado vacío (Polaris, GitLab): el estado vacío ya tiene su trama de esquina.
- Lista de comprobación en vivo mientras se escribe (USWDS «validation»): la propia USWDS la retira por
  accesibilidad.

## IGUALAR (mínimo competitivo que falta)

A1 (resumen con 2+ errores), A2, A3, A4, B1, B2, C1, D1, D3, F3, G2.

## MEJORAR (con evidencia)

- **H2 Tendencias (hipótesis, sin evidencia todavía):** los paneles de GitLab piden tendencias y no
  fotos fijas. **No se ha comprobado** si Kapowarr, Mylar3, Komga o Kavita lo hacen: antes de
  proponerla como «mejorar» hace falta ese benchmark (`.bench-refs`). Criterio de «mejor»: la cifra
  dice qué ha cambiado desde la última visita sin abrir otra pantalla.

## Casos de prueba propuestos

Una por idea adoptada: resumen de errores con 2 fallos y foco en él; `<title>` con «Error: »; ningún
texto visible con palabras vetadas (prueba sobre plantillas y `services/*.py` de cara al usuario);
Biblioteca sin resultados con `ui.estado_vacio` y «Quitar filtros»; ningún texto con «arriba/abajo»
como indicación; un solo aviso de página por respuesta.

## NOT RUN

- No se pudieron leer: Carbon (patrones de vacío, carga, avisos, estado, filtrado, movimiento y
  accesibilidad: la descarga falla), Polaris (redirige a su API), BBC GEL (no permite la descarga),
  GitLab voz y tono (pide identificarse). Sus temas se cubrieron con otras fuentes.
- Del barrido, las listas son las que da designsystems.surf; no se abrió cada documentación oficial.
- Sin prueba con personas ni con lector de pantalla.

**Caduca:** 2027-01-21 (~60 días).
