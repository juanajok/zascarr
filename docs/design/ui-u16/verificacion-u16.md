# Verificación de U16 (#203) — alcance revisado: validación emulada en un Debian de ensayo

> **Decisión de producto (responsable, 2026-10-16).** #203 se acepta como **validación emulada**, sin móviles de prueba y **sin tocar la
> Raspberry de producción**. El entorno de aceptación es un **Debian aislado con PostgreSQL y datos sintéticos** y **navegadores
> emulados**. iPhone/Safari real, Android/Chrome real y las pruebas contra la Pi **siguen sin realizarse (NOT RUN) pero quedan fuera
> del alcance exigido para cerrar esta versión de #203; no son deuda que impida su aceptación.**
> **El cierre se referirá a las comprobaciones de este documento, no a compatibilidad certificada con teléfonos reales.**
> Este documento **no declara #203 como PASS ni la cierra**: eso es una decisión posterior.
>
> Sustituye a la lectura anterior del criterio 4 de la tarjeta («la tarjeta no se cierra con iPhone y Android en NOT RUN») y a «Safari no
> hace zoom» (ahora: campos con tamaño calculado ≥ 16 px). La redacción original de la tarjeta se conserva en #203 como historial.

## Contrato de aceptación (revisado) y resultado

| # | Comprobación | Resultado | Evidencia |
|---|---|---|---|
| 1 | **Sin desplazamiento horizontal** en las pantallas verificadas a **360, 390 y 414 px** | **PASS** | 14 pantallas × 3 anchos = 42 medidas; **0** con `scrollWidth > clientWidth` (antes: 4) · [`medicion-despues.json`](medicion-despues.json) |
| 2 | **Campos de entrada con tamaño calculado ≥ 16 px** (sustituye a «Safari no hace zoom») | **PASS** | **0** campos por debajo de 16 px de los **138** medidos (antes: 102 incidencias) · `getComputedStyle(...).fontSize`, mismo fichero |
| 3 | **Controles primarios ≥ 44 px de alto y ningún control < 24 px** | **PASS** | **0** controles < 44 px y **0** < 24 px de los **690** objetivos medidos (antes: 241 y 18) · mismo fichero |
| 4 | **Evidencia reproducible** con SHA, entorno, navegador, dimensiones y resultados explícitos | **PASS** | Esta tabla y «Entorno», «Qué se midió» y «Cómo repetirlo» (abajo) |

Los resultados valen **para los elementos que selecciona el script en las pantallas cargadas** (ver «Límites»): no son una certificación
exhaustiva.

## Entorno (comprobado, no supuesto)

| Dato | Valor |
|---|---|
| Aplicación | contenedor **Debian GNU/Linux 12 (bookworm)**, Python 3.11.16, **x86-64**, imagen construida con el `Dockerfile` del repositorio (`python:3.11-slim-bookworm`); **no** es una Pi ni arm64 |
| Base de datos | PostgreSQL real, contenedor del mismo ensayo (`docs/design/ui-baseline/ensayo.sh`), **datos sintéticos** (los siembra `sembrar.py`) |
| Código servido | `main` `dc9841aec9f709dba1b7c0e9eb5d96f462cb9079`. El `web.css` servido por el ensayo y el del repositorio tienen el mismo SHA-256 (`6b04c0536eb9c4e4…`) y contiene el bloque «U16 (#203)» |
| Navegador | **Google Chrome 154.0.8037.92**, que corre en la máquina del desarrollador (Ubuntu 26.04.1, Linux 7.0), **no** dentro de Debian; viewport **táctil emulado** por CDP |
| Dimensiones | 360×740, 390×844 y 414×896 px, `mobile: true` (los tres anchos de la tarjeta; el alto es el de la emulación) |

**Qué evidencia ya existente corresponde a este entorno.** Las mediciones `medicion-antes.json` y `medicion-despues.json` se tomaron en ensayos
**reconstruidos desde cero con este mismo `Dockerfile`** (base `python:3.11-slim-bookworm`, es decir, el mismo Debian 12) y con **la misma
herramienta**: «antes» sobre `main` `57259ac`; «después» sobre el commit funcional `aa46cccba9617b51db1c97acab938c8346a8c6ee`. **Entre
`aa46ccc` y `main` `dc9841a` no hay ningún cambio en `src/` ni en `tests/`** (comprobado con `git diff`), así que el «después» describe el
mismo código que `main`. **No se han repetido por formalismo.** Lo que se hizo hoy es comprobar el entorno (arriba) y que el ensayo sirve ese CSS.
*Lo que no se registró entonces fue el `os-release` del contenedor: se infiere del `Dockerfile` y se comprobó hoy en un ensayo reconstruido.*

## Qué se midió

Ver [`README.md`](README.md): desborde lateral (WCAG 1.4.10), tamaño de fuente calculado de campos y selectores, y alto de botones, campos,
selectores, `summary` y enlaces-botón (≥ 44 px) y de cualquier control suelto (≥ 24 px), con la exención WCAG 2.5.8 para enlaces dentro de
una frase (heurística del script). 14 pantallas: panel, biblioteca, ficha de serie, Descubrir, Por revisar, Pendientes por carpeta, asistente
de carpeta, revisión de la vinculación, Deseados, Mi biblioteca, Ajustes, Estado y el aviso legal (asistente y texto).

## Cómo repetirlo

```bash
UI_BASE_DATOS=/ruta/nueva docs/design/ui-baseline/ensayo.sh preparar         # Debian + PostgreSQL + datos sintéticos
python3 docs/design/ui-u16/medir_u16.py ETIQUETA http://127.0.0.1:18000 docs/design/ui-u16
UI_BASE_DATOS=/ruta/nueva docs/design/ui-baseline/ensayo.sh bajar
```

`medir_u16.py` solo acepta destinos locales (`comprobar_entorno`) y **escribe en el ensayo** (acepta el aviso legal): es desechable.

## Límites (no se convierten en PASS)

- **Estados que aparecen tras interactuar** (resultados de Descubrir, panel «Más» abierto, errores) y el **tema oscuro**: no medidos con esta
  herramienta. La verificación completa por anchos es V13.
- **Regresión visual de escritorio: no ejecutada.**
- **Selección de elementos por el script:** un enlace se exime si su contenedor tiene más texto además del enlace (heurística); puede excluir
  un grupo de acciones que no sea una frase.
- **Emulación ≠ teléfono:** Chrome emulado no reproduce el motor de entrada, el teclado, las fuentes ni el rendimiento de un móvil, ni
  dice nada de Safari (WebKit, no instalado aquí).

## Verificaciones no realizadas (fuera del alcance exigido para cerrar esta versión)

| Verificación | Estado | Nota |
|---|---|---|
| iPhone con Safari real (zoom al enfocar, toque) | **NOT RUN** | Sustituido por el contrato 2 (tamaño calculado ≥ 16 px) |
| Android de gama baja con Chrome real | **NOT RUN** | Ver la simulación suplementaria abajo: es un perfil emulado, **no** un teléfono |
| Aplicación desplegada en la Pi (medición de +127 px de la auditoría, SHA servido allí) | **NOT RUN** | La Pi no se toca |

Registro por pantalla y dispositivo, conservado tal cual: [`ronda-dispositivos-reales.md`](ronda-dispositivos-reales.md) (todo NOT RUN).

## Simulación suplementaria: perfil de Android modesto (emulado)

Ver [`simulacion-android.md`](simulacion-android.md). **No forma parte del contrato de aceptación**: se ejecutó solo para informar.
