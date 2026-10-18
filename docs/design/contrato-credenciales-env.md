# Contrato de credenciales y compatibilidad del `.env` (referencia de comparación)

> **Estado: referencia de comparación fijada por el responsable de producto el 2026-10-18. No aprueba ninguna solución concreta.**
> Existe para comparar las PRs #237 y #238 (y cualquier otra que toque credenciales) contra los mismos requisitos. Nace de la
> fase 1 del ensayo M4 (candidato `0a591d6f91a6b54f8cecb1e675afc59dc0290873`): instalación limpia que no termina y `.env` abierto a
> cuentas no administrativas. Enlazado desde `docs/BACKLOG.md` («Mapa del tablero», «Estado de M4»).

## Requisitos

| ID | Requisito |
|---|---|
| C1 | Una instalación nueva genera las credenciales locales obligatorias ausentes, vacías o de plantilla antes de poner en servicio los componentes que las requieren. No exige una edición manual oculta. |
| C2 | Una credencial personal existente se conserva sin regenerarla ni mostrarla, aunque sea débil. Los valores publicados como predeterminados o marcadores se distinguen explícitamente de una credencial personal. |
| C3 | Con una base ya inicializada y credenciales ausentes o conocidas por defecto, no se inventa otra ni se rota silenciosamente. Se detiene el flujo afectado y se ofrece recuperación explícita. |
| C4 | El secreto nace protegido y permanece protegido durante las escrituras: propietario administrativo, modo `0600`, temporales protegidos y sustitución segura. |
| C5 | Una identidad no autorizada no puede leer, sustituir ni redirigir el secreto mediante su directorio o componentes intermedios del camino. La validación precede a las escrituras. |
| C6 | Los consumidores administrativos y comandos manuales funcionan bajo una identidad autorizada o fallan claramente antes de realizar acciones dependientes de la configuración. Ilegible no equivale a ausente. |
| C7 | Ninguna ruta de arranque soportada pone el sistema en servicio con una credencial obligatoria ausente, vacía o conocida por defecto. No basta con proteger únicamente `bootstrap.sh`. |
| C8 | La solución trata expresamente la confianza del código ejecutado como root. Proteger `.env` no permite afirmar aislamiento frente a una cuenta que puede modificar ese código. Cualquier cambio de propiedad debe delimitarse y probarse, sin reclamar carpetas compartidas indiscriminadamente. |
| C9 | Se preservan biblioteca, descargas, credenciales válidas y datos existentes. Los fallos no dejan una configuración parcialmente aplicada presentada como correcta. |
| C10 | La evidencia distingue pruebas con dobles, identidades reales, Compose real e instalación completa. Cada resultado queda ligado al SHA, con PASS, FAIL y NOT RUN separados. |

## Decisión explícita sobre C2 y C3

Conservar una contraseña **personal** débil no equivale a aceptar como segura una contraseña **publicada en el repositorio**
(`SuperSecretPassword123`, `cambia_esto_ahora`). Esta decisión **no autoriza rotar ninguna instalación existente**.

## Cómo se usa

La comparación indica, **para cada fila**, uno de: **cumple · parcial · no cumple · no acreditado**, con la evidencia enlazada
(SHA, prueba, salida). **No se elige por número de pruebas ni por tamaño del diff.** Esta tabla es la plantilla; está sin rellenar a
propósito.

| ID | #237 (`cada61ac`) | #238 (`6a7a9fe8`) |
|---|---|---|
| C1 | — | — |
| C2 | — | — |
| C3 | — | — |
| C4 | — | — |
| C5 | — | — |
| C6 | — | — |
| C7 | — | — |
| C8 | — | — |
| C9 | — | — |
| C10 | — | — |

*(Sin rellenar. **Responsables (2026-10-18):** Perplexity rellena la matriz con lectura de código, pruebas y CI ligadas a SHA; Claude aporta reproducciones locales o salidas que falten, por peticiones acotadas; el responsable de producto decide la PR portadora y las excepciones, y solo entonces una única línea de trabajo consolida la implementación. La matriz distingue cumplimiento acreditado, parcial, incumplimiento y ausencia de evidencia; no se resuelve por número de pruebas ni por fusión mecánica de las ramas. Las cabezas indicadas son las vigentes el 2026-10-18.)*
