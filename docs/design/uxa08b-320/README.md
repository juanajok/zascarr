# UXA-08b · Ronda 4 a 320 px (evidencia sintética)

**Fecha:** 2026-11-26 · **Historia:** #1205 · **Método:** agentes sintéticos deterministas (sin LLM) con Playwright, viewport 320×568.

> **No es una prueba con personas y no vale para aceptar #1205.** La decisión sigue necesitando `../uxa08b-prueba-con-personas.md`. Los agentes recorren la ruta mínima visible; no simulan pulso, prisa ni errores humanos.

## Contenido

- [`resultado.json`](resultado.json): las 8 sesiones (2 perfiles × 2 variantes × 2 tareas) con primer toque, toques hasta la sección, toques totales, éxito, dudas y medidas de la barra/panel.
- [`resumen.md`](resumen.md): tabla legible generada desde el JSON.
- [`capturas/`](capturas/): inicio, panel «Más», Biblioteca, Estado y ficha de la serie, a 320×568.

## Cómo se generó

El guion, los perfiles y el Compose aislado están en [`../../../uxlab/nav320/`](../../../uxlab/nav320/) y [`../../../uxlab/compose.nav320.yml`](../../../uxlab/compose.nav320.yml). Se usaron dos instancias de UXLab con el mismo Postgres y el mismo fixture, una con `NAV_MOVIL_VARIANTE=a` y otra con `b`; ninguna publica puertos ni toca la Pi.

No se usó el piloto DeepSeek porque no había clave en `uxlab/.secrets/deepseek_api_key`. No se enviaron capturas ni datos a ningún proveedor externo.

## Límites

- Agentes deterministas, sin LLM: miden etiquetas y recorrido mínimo, no comportamiento humano.
- Un solo viewport (320×568), sin texto ampliado, lector de pantalla ni móvil real.
- Fixture sintético de 4 series; no es la biblioteca real.
- Los resultados no desempatan entre A y B: confirman el mismo intercambio de costes de las rondas 1–3 y el encaje de la barra a 320 px.
