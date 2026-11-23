# UATP-09 · Decisión de cierre sin pruebas con usuarios reales

**Fecha:** 2026-11-23  
**Decisión del PO:** **no habrá pruebas con usuarios reales en UATP-09.**  
**Alcance:** UATP-09 / UXA-16 (#1133) y cierre de la épica #1141.

## Qué se acepta

- Se cierra UATP-09 **administrativamente**, no como validación humana superada.
- Evidencia usada: simulación con 5 personas-agente (`simulacion.md`), evidenciasChrome/DOM/A6/UAT-31 de UATP-01…08 y los P1 corregidos en PR #1242.
- Los P1 de la simulación quedan corregidos o mitigados en código: legal, continuidad, lector, previa (ARIA) y filtros.

## Qué NO se acredita (NOT RUN aceptados)

- **3–5 participantes reales**, consentimiento, sesión moderada y métricas de éxito/tiempo/comprensión.
- **Móvil físico** iOS/Android.
- **Lector de pantalla real** NVDA/Orca/VoiceOver.
- **Firefox/Safari** y teclado humano.
- **Pi:** frío/caliente, biblioteca grande, CBZ/CBR, red lenta, p50/p95.
- El anuncio real de la previa en una región viva y el foco real del lector a baja altura.

Ningún NOT RUN se convierte en PASS. La frase «UATP-09 cerrada» significa **decisión de producto con residuales aceptados**, no validación con personas.

## Consecuencias

- La épica #1141 se cierra con estos residuales declarados.
- Quedan como seguimiento, fuera de la épica: P2/P3 de la simulación (títulos truncados, `error=comprobacion`, ceros del resumen, fieldset/hash legal, H1/ruido del lector, enlaces de copia sin fecha), `N-01-systemd-host` de A6 y `T-08-15` de UATP-08.
- Si en el futuro se hacen sesiones reales, deben abrir una historia nueva y no reutilizar este cierre como PASS.
