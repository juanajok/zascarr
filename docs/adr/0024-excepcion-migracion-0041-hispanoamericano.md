# ADR 0024 — Excepción de compatibilidad en la migración 0041

**Estado:** aceptada por necesidad técnica (2026-11-18, #1115)
**Contexto:** la regla del proyecto prohíbe reescribir migraciones ya aplicadas. La migración 0041
sembraba `library_root_traditions` recorriendo el enum **vivo** `ComicTradition`. Al añadir
`hispanoamericano` en 0052, una instalación nueva fallaba en 0041: el `INSERT` usaba un valor que el
tipo `comic_tradition` todavía no tenía.

**Decisión:** 0041 usa una tupla **histórica** de tradiciones (las que existían al aplicarse) en lugar
de importar el enum vivo. No cambia el resultado en bases ya migradas: 0041 no se re-ejecuta. 0052
sigue siendo la única migración que añade el valor.

**Consecuencias:** las instalaciones nuevas pueden recorrer `upgrade head`; las existentes no se tocan.
Es una corrección de compatibilidad, no un cambio funcional. Cualquier futura tradición debe añadirse
en una migración nueva, nunca haciendo que 0041 dependa del enum actual.
