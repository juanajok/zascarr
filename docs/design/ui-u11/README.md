# Evidencia de U11 (#198): foco visible y nombre accesible

Capturas y mediciones **antes/después** de la PR #209, para que la revisión no dependa de capturas
locales. Fecha: 2026-10-15.

| Dato | Antes | Después |
|---|---|---|
| Código de la aplicación | `main` en `cd00093` | `claude/u11-foco-etiquetas` en `4e18ffc` (esta carpeta se añade encima y no toca código) |
| Marca en el `web.css` servido | sin «U11» (`web_css_con_u11: false`) | con «U11» (`true`): la imagen en marcha lleva el cambio |
| Entorno | ensayo aislado `docs/design/ui-baseline/ensayo.sh` (Compose `zascarr-uibase`, **Postgres real**, datos **sintéticos** de `sembrar.py`, app en `127.0.0.1:18000`) | el mismo, rehecho desde cero |
| Navegador | Google Chrome 154.0.8037.92 headless por CDP, 1280 × 800, escala 1 | el mismo |
| Herramienta | [`capturar_u11.py`](capturar_u11.py) | la misma |

**Cómo llega el foco:** con una pulsación **real** de Tab (`Input.dispatchKeyEvent`) desde el
control anterior, no con `element.focus()`, para que aplique `:focus-visible` como con un teclado.
**De dónde sale el nombre:** del árbol de accesibilidad de Chromium (`Accessibility.getPartialAXTree`),
que es lo que el navegador entrega a un lector de pantalla. Los datos en bruto están en
[`datos-antes.json`](datos-antes.json) y [`datos-despues.json`](datos-despues.json).

## Resultados

| Vista · tema · URL | Antes | Después |
|---|---|---|
| Por revisar · oscuro · `/ui/pendientes` (buscador de la tarjeta «Mundo Cobalto») | sin anillo, solo una sombra de **1,14:1**; nombre `Buscar serie…`, el mismo en todas las tarjetas | anillo continuo de 3 px, **8,67:1**; nombre `Serie de «Mundo Cobalto - Edicion Integral 01 [Equipo X].cbz»` |
| Biblioteca · claro · `/ui/biblioteca` (selector de tradición) | sin anillo (sombra de tinta, 16,14:1); nombre **vacío**; 2 de 5 controles sin nombre | anillo **5,39:1**; nombre `Tradición`; 0 de 5 sin nombre |
| Deseados · oscuro · `/ui/wishlist` (buscador) | sin anillo, sombra de **1,08:1**; nombre `Buscar serie para añadir…` (el placeholder) | anillo **9,37:1**; nombre `Buscar serie para añadir a Deseados` |

Nota: antes, Chromium **sí** daba nombre a los `input` de Por revisar y Deseados, porque usa el
placeholder como último recurso. El problema era que el nombre se repetía en todas las tarjetas
(`Buscar serie…`, `nº`) y desaparecía visualmente al escribir. Los `select` de Biblioteca no tienen
placeholder, así que su nombre quedaba vacío.

| | Antes | Después |
|---|---|---|
| Por revisar (oscuro) | ![antes](antes--por-revisar-foco-buscador--dark.png) | ![después](despues--por-revisar-foco-buscador--dark.png) |
| Biblioteca (claro) | ![antes](antes--biblioteca-foco-tradicion--light.png) | ![después](despues--biblioteca-foco-tradicion--light.png) |
| Deseados (oscuro) | ![antes](antes--deseados-foco-buscador--dark.png) | ![después](despues--deseados-foco-buscador--dark.png) |

## Lo que esto cubre y lo que no

- **PASS** foco visible ≥ 3:1 en los dos temas y nombres accesibles calculados por Chromium.
- **PASS** el DOM después de los intercambios HTMX de estas pantallas: lo comprueba
  `tests/test_web_nombre_y_foco.py`; además, en el primer ensayo de la PR se buscó «Mundo» en
  Por revisar y el campo «nº» insertado salió con nombre `Número en «Mundo Cobalto»`.
- **NOT RUN** un lector de pantalla real (NVDA, VoiceOver, Orca): el árbol de accesibilidad es su
  entrada, pero no cómo lo verbaliza cada uno.
- **NOT RUN** la Raspberry Pi del responsable y los móviles reales.

## Repetirlo

```bash
export UI_BASE_DATOS=/ruta/nueva/de/ensayo
docs/design/ui-baseline/ensayo.sh preparar
python3 docs/design/ui-u11/capturar_u11.py despues http://127.0.0.1:18000 /ruta/de/salida
docs/design/ui-baseline/ensayo.sh bajar
```
