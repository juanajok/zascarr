# ADR 0021: JavaScript propio solo en la pantalla de lectura

- Estado: **Aceptado** · 2026-11-17 (D-L1 del PO, 2026-11-14).
- Relacionado: ADR 0001 (UI con HTMX), ADR 0015 (lector de RAR), `docs/design/benchmark-BL-LEC-lector.md`, BL-LEC0 (#823).

## Contexto

La épica BL-LEC (#822) añade un lector de tebeos. Para pasar páginas, precargar la siguiente,
cambiar a doble página y guardar la posición hace falta estado de cliente que HTMX no cubre
con la calidad necesaria. Hoy el proyecto tiene tres textos que no dicen lo mismo:

- **ADR 0001** (2021) admitía Alpine.js «para interactividad puramente de cliente»;
- **CLAUDE.md §10** prohíbe «Alpine/Vue/React» como anti-patrón definitivo;
- **el libro de marca** dice que no hay JavaScript propio.

El PO decidió el 2026-11-14 un lector propio y D-L1: **JavaScript propio solo en la pantalla de
lectura**, un único fichero sin dependencias ni compilación, servido desde `static/`.

## Decisión

1. **Un solo fichero**, `src/zascarr/static/lector.js`, escrito a mano, sin dependencias, sin
   build, sin CDN y servido por la propia app. Es el **único** JavaScript propio del producto
   además de HTMX vendorizado.
2. **Alcance cerrado:** solo la pantalla de lectura (`/ui/series/{id}/numero/{issue_id}/leer`).
   Ninguna otra pantalla lo carga. El resto de la interfaz sigue con HTMX y plantillas Jinja.
3. **Sin framework de cliente:** no Alpine, Vue, React ni SPA. El fichero usa APIs estándar del
   navegador; no hay estado global ni navegación de aplicación.
4. **Degradación:** sin JS, la ficha del número sigue ofreciendo sus enlaces y el lector puede
   mostrar un aviso claro; no se convierte en una pantalla en blanco.

## Reconciliación de los textos

- **ADR 0001** queda **aclarada**: su mención a Alpine era una posibilidad de la primera UI;
  el proyecto adoptó HTMX y nunca usó Alpine. Esta ADR no deroga el «sin SPA ni build»; concreta
  que el único JS propio permitido es el del lector.
- **CLAUDE.md §10** se corrige para nombrar la excepción y enlazar esta ADR.
- **El libro de marca** se corrige: «nada de JavaScript propio **salvo el lector** (ADR 0021)».

## Consecuencias

- La pantalla de lectura es la única que puede requerir pruebas de navegador/JS; el resto sigue
  verificándose con TestClient y HTML estático.
- El fichero debe poder auditarse de una vez: sin dependencias, sin `eval`, sin red; cualquier
  crecimiento fuera del lector exige una ADR nueva.
- Si el lector se retira, se retira el fichero y la excepción de los textos; HTMX no cambia.
- No cambia la autenticación, el modelo de datos ni el lector de RAR; esas decisiones viven en sus
  ADR/propuestas.
