# U10 — Simulación de usabilidad con agentes (2026-10-21)

> **Esto no es un test con usuarios reales.** Es una **simulación declarada** con agentes de IA que interpretan
> personas de coleccionistas no técnicos. Sirve para detectar fricciones evidentes y preparar la sesión real;
> **no acredita U10, no sustituye a 3–5 personas y no desbloquea G1 por sí sola**. La decisión de aceptar esta
> simulación como evidencia para G1 es del responsable y debe quedar escrita.

## Qué se simula

- **Feature:** #196, historia U10 (#197), puerta G1 de U13/V5/V6b.
- **Variantes:** A (carpetas primero) y B (lista compacta con lotes).
- **Datos:** 1.322 pendientes: 1.308 en 108 carpetas + 14 archivos sueltos. Nombres largos, carpetas ambiguas y
  series sugeridas con puntuación. Los prototipos son estáticos y no ejecutan acciones.
- **Participantes simulados:** 3 personas (mínimo del rango 3–5), con perfiles distintos.
- **Orden:** se alterna A→B, B→A, A→B para reducir el efecto de aprendizaje.
- **Moderación:** un agente [UX] presenta cada variante y recoge las respuestas; no corrige ni guía durante la tarea.

## Prototipos

- [`prototipos/variante-a-carpetas.html`](prototipos/variante-a-carpetas.html)
- [`prototipos/variante-b-lista.html`](prototipos/variante-b-lista.html)
- Generador reproducible: [`generar_prototipos.py`](generar_prototipos.py) (solo stdlib; no toca la app).

## Tareas

Ver [`guion-sesion.md`](guion-sesion.md). Cada participante recibe las tareas en el mismo orden, pero las variantes
en orden alterno.

## Métricas

| Métrica | Cómo se registra |
|---|---|
| Éxito | Sin ayuda / con ayuda / fallo / abandono |
| Tiempo | Segundos desde que se lee la tarea hasta que responde o abandona |
| Errores | Acción o interpretación equivocada, con la frase que la provocó |
| SEQ | 1–7 por variante y tarea |
| Confusión | Cita textual de lo que no entiende |
| Preferencia | A, B o indiferente, con motivo |

## Límites

- Los agentes no tienen memoria visual ni emociones reales; sus tiempos no son comparables con los de una persona.
- No se simulan lectores de pantalla ni dispositivos reales.
- Los prototipos no ejecutan asignaciones; no se prueba el resultado de una acción, solo su comprensión.
- **G1 sigue bloqueada** hasta que el responsable acepte esta simulación como evidencia o se ejecute la sesión real.

## Salida

[`resultados-simulacion.md`](resultados-simulacion.md) con observaciones por participante, hallazgos transversales,
límites, decisión recomendada y lo que queda en NOT RUN. Informes individuales:
[`resultados-P1.md`](resultados-P1.md), [`resultados-P2.md`](resultados-P2.md), [`resultados-P3.md`](resultados-P3.md).
