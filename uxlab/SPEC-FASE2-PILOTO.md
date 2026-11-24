# SPEC UXLab Fase 2 — piloto de agentes IA

**Estado:** especificación de diseño; no hay código de agentes ejecutándose ni resultados sintéticos todavía.  
**Dependencia:** PR de mantenimiento L1 de estabilidad y propiedad de los informes.  
**Alcance estricto:** 2 escenarios × 3 perfiles = **6 sesiones**, no los seis escenarios de L1.  
**Ejecución:** portátil Linux con Docker, nunca la Raspberry Pi de producción.

## 1. Objetivo y condición de entrada

Medir si un usuario sintético puede **descubrir** acciones en una UI desconocida.
No confundir esto con un test determinista que ya conoce la forma de navegar.

Antes de implementar los agentes, ejecutar en el portátil:

    bash uxlab/run.sh --stability
    cat uxlab/results/stability-summary.md
    stat -c '%u:%g %n' uxlab/results/results.json

Se esperan 36/36 ejecuciones correctas: seis tests de L1 por dos dispositivos y tres
repeticiones. Comprobar también el UID/GID del host. Cualquier intermitencia requiere
análisis antes de comparar con agentes. Una ausencia de fallos en 36 ejecuciones **no
demuestra** que no exista flakiness.

## 2. Dos escenarios piloto

### PILOT-01 · Descubrir una serie por género (UX-01)

- **Inicio:** Biblioteca, vista Gestión.
- **Objetivo presentado:** «Encuentra en mi biblioteca una serie de ciencia ficción
  y abre su ficha».
- **Información NO presentada:** título correcto, UUID, etiquetas preconocidas,
  selectores, rutas de solución ni mecanismo de filtrado.
- **Oráculo:** la serie abierta tiene género ciencia ficción en el fixture/BD;
  se valida mediante su ID, no por una declaración del modelo ni por texto casual.
- **Hallazgos de interés:** descubrir que el panel no ofrece «Género» explícito,
  comprender «Etiquetas», intentos con tradición, búsquedas fallidas, abandono.

### PILOT-02 · Retomar lectura pendiente (UX-04)

- **Inicio:** Biblioteca, modo Escaparate.
- **Objetivo presentado:** «Tenías un cómic a medias; continúa desde donde lo
  dejaste».
- **Información NO presentada:** serie, archivo, página, URL del lector ni IDs.
- **Oráculo:** entrar al lector del archivo del fixture con la página persistida
  inicialmente (**3**), validando UI y registro inicial de base de datos.
- **Hallazgos de interés:** visibilidad de «Continuar leyendo», visita intermedia
  a la ficha de serie, volver al inicio por error, pasos extra hasta lector.

Cada sesión arranca desde una **semilla restaurada**: no compartir cambios de
lectura, favoritos o estado local entre perfiles ni escenarios.

## 3. Exactamente tres perfiles

| ID | Perfil | Emulación del entorno |
| --- | --- | --- |
| P1 | No técnico móvil | Viewport CSS 390 × 844, interacción táctil, desconocimiento de filtros avanzados |
| P2 | Solo teclado | Escritorio 1280 × 800, prohibir ratón/clic; permitir Tab, Shift+Tab, Enter, Espacio, Escape y desplazamiento mediante teclas |
| P3 | Baja visión y zoom | Verificar reflow a zoom real de navegador 200 %. Puede usarse viewport CSS efectivo de 640 × 400 para aproximar el reflow, **sin confundir deviceScaleFactor=2 con zoom** |

Las restricciones son perfiles sintéticos de interacción y **no sustituyen
pruebas de accesibilidad con personas reales**.

## 4. Arquitectura y aislamiento

    Portátil Linux
    └── Docker Compose, proyecto UXLab (red interna)
        ├── postgres + seed + app (solo datos ficticios)
        ├── Playwright + orquestador + oráculos
        │   ├── capturas de pantalla y ariaSnapshot
        │   ├── validador de acciones permitidas
        │   └── trazas, métricas, informes
        └── API DeepSeek `deepseek-flash` (servicio remoto, solo vía orquestador)

- Proveedor **remoto** DeepSeek vía HTTPS `https://api.deepseek.com/chat/completions` con
  `deepseek-flash` (admite capturas e imágenes). El portátil **no ejecuta LLM local**.
  Verificar modelo, visión y formato JSON con una petición multimodal real de arranque; no degradar a solo texto.
- El navegador, PostgreSQL y ZascArr se mantienen en red Docker `internal`;
  únicamente el proceso orquestador tiene salida a Internet a través de otra red
  para llamar a DeepSeek. No habilitar herramientas web/URL del modelo.
- La clave `DEEPSEEK_API_KEY` se entrega al orquestador mediante secreto de Docker
  montado en `/run/secrets/deepseek_api_key`, nunca en argumentos de comando,
  capturas, logs, git ni el entorno del navegador. Añadir `.secrets/` a `.gitignore`.
- **Aviso de privacidad:** cada petición transmite una captura de la interfaz
  ficticia y el árbol de accesibilidad a DeepSeek; la redacción de URLs no elimina
  por sí sola contenido sensible si se probara sobre datos reales. Solo datos UXLab.
- Navegador solo puede solicitar recursos del dominio interno de ZascArr.
  Bloquear CDN, analítica, proveedores de IA y todos los dominios ajenos.
- Interceptar solicitudes de escritura: bloquear borrados, administración,
  favoritos y operaciones externas; para PILOT-02 permitir únicamente el
  progreso de lectura indispensable, siempre sobre datos desechables.
- No compartir secretos, carpetas de producción, discos del usuario ni
  configuraciones de servicios externos.
- El modelo ve objetivo, perfil, captura, **árbol de accesibilidad y URL
  saneada**; no HTML, JavaScript, CSS, IDs ni oráculos. La URL observada
  conserva solo la categoría de pantalla (p. ej. `/ui/biblioteca`,
  `/ui/series/:serie`, `/ui/leer/:archivo`), sin UUIDs, query string ni
  fragmentos. La URL real permanece exclusiva de Playwright y los oráculos.

## 5. Contrato de acciones permitido

Una única acción JSON de tipo y argumentos validados por paso. El navegador
traduce rol + nombre accesible a elementos visibles; si hay varias coincidencias,
se solicita desambiguación por contexto visible. **Nunca elegir al azar**.

| Acción | Alcance |
| --- | --- |
| click | Clic/tap por rol + nombre accesible en P1 y P3 |
| type | Escribir en un campo visible nombrado; en P2 puede escribir en el foco actual |
| scroll | Avanzar/retroceder una cantidad acotada; P2 usa PageDown/PageUp |
| back | Retroceso en historial, solo dentro de UXLab |
| wait | Espera corta (p. ej. 250–1000 ms) por carga de HTMX |
| press | Exclusiva de P2, teclas expresamente autorizadas |
| finish | Declarar completado, abandono o «necesito ayuda» y motivo |

No permitir comandos de shell, navegación directa a rutas de solución,
selectores, ejecución de código, uso de page.evaluate, lectura de archivos
o herramientas externas. El controlador inicializa la URL de inicio sin
exponer el destino al agente.

**Éxito objetivo = oráculo Playwright/BD**. El modelo puede declarar que
terminó, pero eso no equivale a éxito. Registrar expresamente:
false_success = declared_complete AND NOT objective_success;
goal_reached_before_finish y help_requests/abandono por ayuda.

## 6. Límites iniciales

- **18 acciones** como máximo por sesión.
- **240 segundos** de tiempo total por sesión; peticiones de modelo con
  timeout propio, sin espera infinita.
- Máximo 3 acciones inválidas consecutivas, 3 errores de inferencia o 2
  estados repetidos sin avance antes de detener como bloqueo.
- Hasta 60 000 tokens de entrada agregados por sesión y 512 tokens de salida
  por decisión; registrar llamadas, tiempo de respuesta y tokens facturados.
- Modelo `deepseek-flash`, versión recibida/huella backend, temperatura,
  parámetros y commit SHA registrados. No se puede fijar digest de servicio remoto.
- **API DeepSeek facturable**, con límite global de sesiones, peticiones,
  tokens y coste estimado en USD. Cada llamada comprueba presupuesto restante;
  detener en cuanto se alcance el límite. Registrar tarifas y tokens reales;
  la factura final puede variar por caché, horario y revisiones de precios.
- Modelo inicial `deepseek-flash` (visión), con versión real `model` de cada
  respuesta, huella backend `system_fingerprint` cuando exista, fecha y parámetros.
  Un alias de API no equivale a un digest inmutable: registrarlo explícitamente.
- Ante modelo no disponible, no multimodal o fuera de presupuesto, informar
  fallo de infraestructura; no inventar resultados de usuarios sintéticos.

## 7. Métricas y evidencias

Por cada sesión registrar: scenario_id, persona_id, objective_success,
declared_success, false_success, steps, elapsed_ms, backtracks, loops,
invalid_actions, blocked_requests, help_requests, model_calls, input_tokens,
output_tokens, model_id, system_fingerprint, estimated_usd, temperature, git_sha y fixture_version.

- Registro JSONL por paso: estado accesible resumido, acción elegida, resultado
  del navegador, progreso y razón de bloqueo cuando proceda.
- Capturas de cada paso, trace.zip de Playwright y session.json por sesión.
- Informe HTML y resumen JSON con **seis filas de sesiones**; enlazar evidencias.
- Coste de tokens, tiempo y tasas de finalización objetiva por escenario/perfil.
- Guardar falso éxito tanto si el agente declaró éxito prematuramente como si
  la prueba de contrato fuerza deliberadamente una declaración incorrecta.

No combinar estos indicadores con resultados Likert de SSR ni extrapolar
porcentajes a usuarios reales. SSR y calibración humana se implementarán después.

## 8. Criterios de aceptación del piloto

1. Arrancan exactamente **6 sesiones**: 2 tareas × 3 perfiles.
2. Cada sesión dispone de una restauración verificable del catálogo/progreso.
3. Se entregan realmente **captura, árbol accesible y URL** al modelo visual.
4. No hay selectores, rutas internas ni respuestas correctas en prompts.
5. P2 navega sin ratón ni clic; cualquier violación invalida la sesión.
6. La whitelist impide código arbitrario y peticiones externas **desde el navegador**;
   solo el orquestador contacta HTTPS a DeepSeek y registra los bloqueos.
7. Los oráculos verifican estados finales independientemente del agente.
8. Se prueba con un caso forzado de **falso éxito** y queda contabilizado.
9. El controlador termina por límites de tiempo, pasos y presupuesto.
10. Existen trazas e informes por sesión **incluso cuando la IA fracasa**.
11. Los resultados mantienen el UID/GID del usuario del host.
12. La tasa de acierto del agente **no** bloquea CI: un bajo éxito puede
    revelar problemas de descubribilidad y no defectos del test runner.

**No se establece un objetivo artificial 6/6 de éxito.** La finalidad del
piloto es encontrar fricciones de navegación, no entrenar al agente para
imitar los caminos deterministas.

## 9. Entregable posterior, no incluido en esta SPEC

Una PR posterior incluirá orquestador, cliente API de DeepSeek con capturas, observador,
guardarraíl, perfiles P1/P2/P3, escenarios PILOT-01/PILOT-02, oráculos aparte,
informe agregado y guía de secreto API y ejecución controlada. Los otros cuatro escenarios
de L1, SSR y usuarios humanos quedan **fuera de alcance**.

**Decisión de secuencia:** validar y cerrar primero L1; revisar esta SPEC;
solo después implementar el piloto de seis sesiones.
