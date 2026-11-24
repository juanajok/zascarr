# UXLab Fase 2 — piloto IA mediante la API de DeepSeek

El **portátil ejecuta Docker y Playwright, no modelos locales**. Las decisiones las toma DeepSeek en la nube. Sin Ollama, llama.cpp ni GPU dedicada.

**Alcance:** dos escenarios (encontrar ciencia ficción y continuar lectura), tres perfiles (móvil no técnico, solo teclado, reflow/baja visión aproximada), seis sesiones.

## Qué sale a Internet

Únicamente el contenedor **agent** contacta HTTPS con api.deepseek.com/chat/completions, utilizando el modelo **deepseek-flash** con visión. Se transmiten capturas JPEG de la interfaz **sintética**, árbol de accesibilidad y URL saneada (sin UUID, parámetros ni fragmentos). Estas capturas y textos se envían a DeepSeek como proveedor externo.

El navegador remoto Playwright, PostgreSQL y la aplicación están en la red Docker interna sin salida a Internet. La clave solo existe en el contenedor **agent**, montada como secreto Docker.

## Clave API sin exponerla en la consola ni en Git

Crea una clave API en la plataforma de DeepSeek. En la raíz del proyecto:

    mkdir -p uxlab/.secrets
    chmod 700 uxlab/.secrets
    read -r -s -p "DeepSeek API key: " DS_KEY; echo
    printf '%s' "$DS_KEY" > uxlab/.secrets/deepseek_api_key
    unset DS_KEY
    chmod 600 uxlab/.secrets/deepseek_api_key

La carpeta uxlab/.secrets/ está excluida de Git. No compartas la clave en el chat ni la guardes en la configuración de producción de ZascArr.

## Ejecución

    bash uxlab/run-agents.sh

El script crea una base de prueba efímera y ejecuta las seis sesiones, restaurando favoritos y progreso antes de cada una. No usa tu biblioteca real.

Resultados:

    uxlab/results/agents/<run-id>/
    ├── report.md
    ├── report.json
    ├── PILOT-01-p1-movil/
    │   ├── session.json
    │   ├── steps.jsonl
    │   ├── trace.zip
    │   └── screenshots/
    └── ... (otras cinco sesiones)

Se restaura la propiedad de uxlab/results/ al UID/GID del host.

## Presupuesto y límites

Límite inicial de **0,05 USD estimados por sesión**, como máximo 0,30 USD estimados entre las seis. El cliente utiliza tarifas pico publicadas en noviembre de 2026: entrada sin caché de Flash 0,30 USD/1M tokens y salida 1,20 USD/1M tokens. El importe real puede variar según tarifas, caché, horario y facturación final. **No es un tope de gasto en la cuenta de DeepSeek.** Configura límites de crédito también en el proveedor si están disponibles.

Máximo por sesión: 18 acciones por defecto (`UXLAB_MAX_STEPS`), 240 segundos, 60.000 tokens de entrada (`UXLAB_MAX_INPUT_TOKENS`), 280 tokens de salida por decisión, tres acciones inválidas consecutivas, una decisión por llamada. No reintenta automáticamente llamadas facturables. Si se agota el presupuesto, el experimento se detiene y guarda la evidencia.

Para repetir solo un perfil/escenario con otro presupuesto:

    UXLAB_SCENARIOS="PILOT-01 PILOT-02" UXLAB_PERSONAS="p2-teclado" UXLAB_MAX_STEPS=30 bash uxlab/run-agents.sh

## Seguridad y límites metodológicos

- **Solo catálogo de prueba**: la API recibe imágenes/texto, por lo que no debe utilizarse con colecciones reales.
- El agente no recibe selectores, rutas solucionadoras, UUID ni oráculos; se verifica el resultado en Playwright.
- P2 no admite acciones de ratón; P3 aproxima reflow a 640×400 CSS px y **no es prueba equivalente a zoom real al 200 %**.
- Si DeepSeek no acepta imágenes, devuelve JSON inválido o no responde, **fallar explícitamente**, nunca pasar inadvertidamente a texto.
- Una red Docker con salida de **agent** no restringe a nivel de kernel los destinos a un único dominio: el código llama solo al origen fijo HTTPS de DeepSeek. Para una garantía de egress de red exacta sería necesario un proxy que filtre dominios.
- El cliente no activa búsquedas web, ejecución de código ni llamadas a herramientas del modelo.
- Los usuarios sintéticos no son usuarios humanos. SSR y calibración real vendrán después.
- Este piloto **no se ha ejecutado** contra la API desde el entorno donde se creó la PR.

## Diagnóstico

    find uxlab/results/agents -name report.md -print
    cat uxlab/results/agents/*/report.md

Para seguir ejecutando L1 sin gastar en DeepSeek:

    bash uxlab/run.sh --stability

Los resultados de navegación de IA no bloquean la CI: el fracaso en localizar una función puede ser un hallazgo de UX.
