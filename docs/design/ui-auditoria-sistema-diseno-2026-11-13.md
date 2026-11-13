# Auditoría de las pantallas nuevas contra el sistema de diseño (2026-11-13)

> Referencia: **“ZascArr — Sistema de diseño”**, versión 2026-11-13 (`76e7812`). Alcance:
> pantallas de Sagas, Mejoras, Calidad y la ficha del número. **No** es una auditoría de toda la
> app ni sustituye a la revisión en navegador real.

## Corregido

| Hallazgo | Cambio |
|---|---|
| La tarjeta **Calidad** estaba dentro de «Fuentes de datos» | Movida a **Descargas**, junto a Prowlarr y los clientes; leyenda reducida a **«Calidad y mejoras»** (≤3 palabras) |
| El `h1` «Buscar una edición mejor» son 4 palabras y se pintaba en Anton | Pasa a `.titulo-frase` (Archivo, caja normal), como manda el sistema para títulos que son frases |
| El título de una saga es dinámico y puede superar 3 palabras | La ficha de saga usa `.titulo-frase` para no rotular una frase en Anton |
| Botones «Subir»/«Bajar» sin objeto | «Subir una posición» / «Bajar una posición» |
| «Descartar» de Mejoras se pintaba como fantasma | `.btn-ignorar` (variante del sistema para descartar) |
| Filas de Sagas/Mejoras con borde de 2 px paper-2 | Viñeta paper-2 con borde de **3 px en ink**, como el resto de bloques |

## PASS

- Colores por tokens (`paper`, `paper-2`, `ink`, `--paper-2`); sin colores a mano en las plantillas nuevas.
- Un solo botón principal por pantalla en las pantallas nuevas (Guardar/Add en formularios; ninguno en listas de acciones repetidas).
- Avisos con `ui.aviso`, estados vacíos con `ui.estado_vacio`, chips con `ui.chip`.
- Sin emoji, sin `onerror`, sin diálogos nativos; botones con verbo y objeto.
- Texto informativo ≥14 px (lo vigila `test_web_css_contraste`).

## NOT RUN / deuda que no toca esta revisión

- Navegador real (Chrome/Firefox, claro/oscuro, 320/768/1280) y Pi: **NOT RUN**.
- La deuda general del sistema (escala tipográfica sin tokens, grosores literales, `btn-secondary`
  inexistente, etc.) sigue abierta y es anterior a estas pantallas.

## Cierre de la deuda 1 y 2 (tokens CSS, PR #738)

- **Deuda 1 — escala de texto con nombre:** `:root` declara un token por estilo del sistema
  (`--text-titulo-pagina`, `--text-cifra`, `--text-titulo-seccion`, `--text-marca`,
  `--text-numero-paso`, `--text-titulo-bloque`, `--text-cuerpo`, `--text-titulo-frase`,
  `--text-estado-resumen`, `--text-didascalia`, `--text-nav`, `--text-boton`,
  `--text-secundario`, `--text-chip`, `--text-etiqueta`) y conserva `--text-nav-movil` como
  excepción declarada. Las 140 declaraciones `font-size` usan `var(--text-*)`; fuera de `:root`
  no queda ningún literal. Solo dos redondeos subpíxel: `.92rem→.9rem` y `1.02rem→1.05rem`.
- **Deuda 2 — forma y espaciado:** `--border-panel` (3 px), `--border-control` (2,5 px),
  `--border-chip` (2 px) y `--border-line` (1 px) sustituyen 130 grosores literales;
  `--space-1..6` (4/8/12/16/24/32 px) sustituye 335 huecos exactos. Los valores fuera de la
  escala del sistema se conservan con tokens heredados para no cambiar píxeles.
- **Verificación:** `scripts/comparar_tokens_css.py` compara declaración a declaración antes y
  después y solo admite los redondeos de la tabla; `tests/test_web_css_tokens.py` impide que
  vuelvan los literales (mordida comprobada). Suite completa y CI en verde; revisado en la Pi en
  claro/oscuro a 1280 y 375 px (Inicio, Biblioteca, Auditoría, Ajustes).

## Deuda 6 — portada de «Por revisar» (decisión del PO, 2026-11-13)

La revisión proponía usar `ui.portada` en las tarjetas de «Por revisar» para que una fila no cambie de alto
al cargar, sabiendo que **revierte U12** (el hueco 2:3 volvía a empujar los nombres). El PO lo aprobó.

- La tarjeta (`_tarjeta_pendiente.html`) pinta **siempre** el marcador de `ui.portada` (inicial + tinta) y la
  `<img>` solo cuando el servidor sabe que la extensión tiene extractor: una ausencia conocida (CBR, PDF…)
  no lanza ninguna petición `/portada`, y el marcador ocupa su 2:3 para alinear la fila.
- `.portada-pendiente` acota el bloque a 120 px de ancho; `.cover` se conserva en la hoja por compatibilidad
  hasta la V14.
- Sin `onerror`: si la portada no llega, se ve el marcador, como en la Biblioteca.
- Pruebas: los tres casos de portada de `tests/test_pendientes_tarjeta.py` se reescriben para el mecanismo
  nuevo (marcador sin petición; `<img>` con marcador debajo; 2:3 y 120 px); la verificación visual se hace
  en navegador real a 1280 y 375 px tras desplegar.
