# Validación A5 — navegador real y a11y a 320 px (2026-11-17)

> Historia [#156](https://github.com/juanajok/zascarr/issues/156), tarjeta «Discos de la biblioteca».
> **PASS** en navegador real contra la app desplegada en la Pi. **NOT RUN:** lector de pantalla
> real (VoiceOver/NVDA/Orca); la comprobación es semántica y de teclado, no de lectores.

## Entorno

- Pi `raspberrypi` (aarch64), ZascArr desplegado en `/opt/zascarr`, `main` `afe7ee4d`,
  esquema **0048**, health OK.
- Navegador: **Firefox 157.0.1** en modo headless, ventana **320×900**.
- Autenticación: sesión de operador generada desde la BD para la prueba; la contraseña no se
  usó ni se expuso. La UI se sirvió a través de un proxy local que solo añadía la cookie de
  sesión; la app siguió viendo `Host` local y el mismo usuario.

## Evidencia visual

La captura `docs/design/ui-156/ajustes-discos-320.png` (320×1950 px) **se retiró del repo público por E2** (mostraba la ruta y el recuento reales de la biblioteca); está en el archivo privado del operador. La validación descrita se conserva como evidencia textual:

- La tarjeta ocupa el ancho disponible (≈306 px útiles) y **no hay recorte horizontal**.
- Cada tradición va en su línea, con etiqueta encima y selector debajo (ancho completo).
- «Biblioteca», los chips «disponible»/«Por defecto», los 9 selectores, «Guardar reparto» y la
  nota final se leen sin solaparse.
- El texto informativo se mantiene a **14 px**; los selectores miden ~40 px de alto.

## A11y (semántica y teclado, Firefox real)

- `fieldset` con `legend` «Discos de la biblioteca».
- Grupo «Tradición → disco» con `role="group"` y `aria-labelledby="mapa-tradiciones"`; el `h3`
  con ese id existe.
- Los 9 `<select>` van dentro de su `<label>`; **0 controles sin nombre accesible**.
- Botón «Guardar reparto» con nombre por texto; `tabindex` 0 y alcanzable.
- Todos los controles de la tarjeta son enfocables (`document.activeElement` tras `focus()`).
- Texto mínimo calculado: **14 px**; sin textos por debajo.
- Contraste: cubierto por `tests/test_web_css_contraste.py`; no se tocó CSS en esta pasada.

## Límites

- El ancho de ventana mínimo de Firefox es 500 px; la captura a **320 px** se hizo con
  `--window-size=320,900` (el viewport real del render es 320). Las comprobaciones de foco y
  semántica se hicieron en la misma página con Firefox/WebDriver.
- No se probó lector de pantalla ni Safari/Chrome en la Pi.
- No se cambió código ni la configuración de producción: la sesión y el proxy temporales se
  retiraron al terminar; la biblioteca no se tocó.

## Veredicto

**PASS** para el punto pendiente de A5: navegador real en la Pi a 320 px, sin desborde ni
recortes, con semántica y foco correctos. A5 queda cerrada.
