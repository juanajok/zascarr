<!--
Plantilla de PR (docs/design/benchmark-calidad-front.md, a partir de sapegin/frontend-pull-request-checklist).
Borra lo que no aplique; no dejes casillas marcadas sin haberlo hecho. Lo que no se pudo comprobar va en NOT RUN.
-->

## Qué cambia

<!-- Qué ve el coleccionista y por qué. Enlaza la historia o el hallazgo (#123). -->

## Decisiones anteriores que revisa o conserva

<!-- ADR, decisiones del PO, pruebas que fijaban otra cosa. Si choca con una, dilo aquí: no se resuelve en silencio. -->

## Cómo se comprobó

- [ ] Pruebas: una de regresión por fallo o hallazgo, nombrada con su mecanismo (CLAUDE.md §8)
- [ ] `ruff check src/` sin errores y sin avisos nuevos en la consola del navegador
- [ ] En el navegador, si toca la interfaz: escritorio, 375 px y 320 px, sin desplazamiento horizontal
- [ ] Tema claro y oscuro
- [ ] Teclado: se llega a todo, el foco se ve y el orden es el de la pantalla
- [ ] Sistema de diseño: un solo botón principal, didascalia solo para confirmar, procedencia o aviso legal, tokens y no literales (`docs/design/sistema-de-diseno-zascarr.md`)
- [ ] Textos según el glosario (CLAUDE.md §14) y el presupuesto de texto (§6)
- [ ] Capturas o medidas de lo que cambia a la vista

## NOT RUN

<!-- Lo que no se pudo comprobar y por qué (la Pi, un lector de pantalla, datos reales…). -->

<!-- Si toca services/seguridad.py, web/ajustes.py o services/reautenticacion.py: espera el dictamen de SecOps sobre el SHA final (CLAUDE.md §5.8). -->
