# Evidencia de T0.4: carga efectiva de instrucciones (2026-11-27)

Comprobación pedida por el plan SDD: si Claude Code, Codex y OpenCode cargan las instrucciones del proyecto. **No** mide calidad de respuestas, aislamiento de herramientas ni equivalencia entre harnesses.

## Método

Directorio sintético aislado, sin código, credenciales ni datos reales, con dos ficheros de instrucciones y marcas distintas:

- `AGENTS.md` con la marca `ZAS-T04-8842`.
- `CLAUDE.md` con la marca `ZAS-T04-7731`.

Criterio: se pide al harness `Responde solo con OK` desde ese directorio; si la respuesta contiene una de las marcas, ese fichero se cargó. Un control con `CLAUDE.md` permite distinguir «no carga» de «método inválido». Una sola ejecución por harness; no se repitieron intentos tras un fallo de entorno.

## Resultados

| Harness | Versión | `AGENTS.md` | `CLAUDE.md` | Observación |
|---|---|---|---|---|
| Claude Code | 2.1.332 | **No** (marca ausente) | **Sí** (marca `ZAS-T04-7731` presente) | Respuesta `OK` en ambos casos; solo el control con `CLAUDE.md` incluyó la marca |
| Codex CLI | 0.170.0 | NOT RUN | NOT RUN | `codex exec --skip-git-repo-check`: `failed to initialize in-process app-server client: Read-only file system (os error 30)`, exit 1 |
| OpenCode | — | NOT RUN | NOT RUN | `opencode --version`: `cannot create transient scope: DBus error ...`, exit 46 |

## Interpretación y consecuencias

- En esta versión y configuración, **Claude Code lee `CLAUDE.md` y no `AGENTS.md`**. El control demuestra que el método detecta una carga real, así que la ausencia de la marca en el caso `AGENTS.md` no es un fallo del procedimiento.
- Consecuencia directa: `AGENTS.md` **no puede presentarse como índice portátil único** mientras un harness principal lo ignore. El índice sirve como documentación navegable, no como canal garantizado.
- Refuerza la decisión de **no retirar todavía** las reglas de `CLAUDE.md`: hoy es el único fichero con evidencia de carga en un harness.
- No se deduce nada sobre restricciones de herramientas, sandbox, lectura de otros ficheros ni seguridad del contenido enviado.

## Límites

- Una ejecución por harness, con la sesión de suscripción del operador; no se probaron configuraciones alternativas ni otras versiones.
- No se aisló la autenticación: la prueba de Claude usó la sesión ya iniciada del operador.
- No se verificó qué herramientas tenía disponibles el agente ni si leyó ficheros distintos de los de instrucciones.
- Codex y OpenCode quedan **NOT RUN** por limitaciones de entorno; repetir el mismo intento no aportaría evidencia.
- No se ejecutaron pruebas de producto, CI ni gates: esto no habilita ninguno.

## Investigación: por qué no se carga `AGENTS.md` en Claude Code

Búsqueda de cadenas en el binario instalado (`~/.local/share/claude/versions/2.1.332`):

- Existe una lista de nombres reconocidos: `["AGENTS.md", ".claude/AGENTS.md"]` junto a `["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"]`.
- Existen cuatro modos de instrucciones de proyecto: `claude-md`, `claude-md-or-agents-md` (constante de modo por defecto declarada en el código), `claude-md-and-agents-md` y `managed-only`, con alias `none`, `claude`, `agents-fallback` y `both`.
- El propio binario describe: «AGENTS.md as project instructions: by default loaded where the project has no CLAUDE.md».
- Hay telemetría específica del camino (`agents_md_mode`, `agents_md_load`, `agents_md_nested`, `instruction_files_not_loaded`) y opciones de configuración `projectInstructions` (leída como `instructionFiles`) y `instructionFiles`.

Configuraciones probadas, todas con `AGENTS.md` que contiene una marca verificable y `CLAUDE.md` de control:

| Configuración | Resultado |
|---|---|
| `AGENTS.md` + `CLAUDE.md` en la raíz | Solo se cargó `CLAUDE.md` |
| Solo `AGENTS.md`, sin `CLAUDE.md` | No se cargó |
| `.claude/AGENTS.md` | No se cargó |
| `--settings` con `projectInstructions: "both"` y con el nombre del modo completo | Solo se cargó `CLAUDE.md` |
| `AGENTS.md` anidado en un subdirectorio | No se cargó |

Conclusión acotada: **el soporte existe en el código de esta versión, pero con esta cuenta y configuración no se activó por ninguna de las vías probadas.** No se puede afirmar desde fuera si depende de un flag de despliegue, de la cuenta o de una versión posterior. Lo que sí queda acreditado: `CLAUDE.md` es el canal que funciona, y no hay que contar con `AGENTS.md` como entrada garantizada.
