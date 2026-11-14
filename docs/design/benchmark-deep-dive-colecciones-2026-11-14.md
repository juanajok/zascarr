# Benchmark — deep dive Colección → Serie → Issue

> Investigación previa a implementar el 2026-11-14. FUENTES consultadas como
> documentación pública; no se copia código.

## 1. Problema local

Hoy:

- Desde una **colección** se ve la lista de series; el nombre lleva a la ficha,
  pero **la portada no es clicable** y la vista de tarjetas no se comporta como
  un enlace entero.
- La **ficha de serie** ya muestra un panel de colecciones
  (`_colecciones_serie.html`) y enlaza a la colección.
- La **ficha de issue** no dice en qué colecciones está, aunque pertenece a
  ellas por su serie.
- El recorrido natural del coleccionista —colección → serie → número— no tiene
  una portada/nombre clicable en los dos primeros saltos de forma consistente.

## 2. Referencias

### Komga

- Las colecciones agrupan series; la ficha de serie muestra un panel de
  colecciones y la colección se puede abrir desde ahí.
- La pantalla de detalle de la colección lista sus series; las tarjetas de serie
  son el punto de entrada a la ficha.
- Fuente: [Colecciones | Komga](https://komga.org/es/docs/guides/collections/).

**Adoptar:** colección → serie mediante tarjeta entera (portada + nombre);
panel de colecciones en la ficha de serie.
**Descartar:** orden manual/drag-and-drop de series (fuera de alcance).

### Kavita

- Una colección agrupa series de cualquier biblioteca; se accede desde la lista
  de bibliotecas o desde una serie que pertenece a la colección.
- La colección muestra todas sus series; la portada y el nombre identifican la
  colección.
- Fuente: [Collections | Kavita Wiki](https://wiki.kavitareader.com/guides/features/collections/).

**Adoptar:** acceso bidireccional colección ↔ serie y colecciones visibles desde
la serie.
**Adaptar:** en ZascArr la pertenencia es **solo por serie**, no por issue; el
issue mostrará las colecciones de su serie, dicho explícitamente.

## 3. Revisión UI/UX contra el sistema de diseño

Reglas aplicables de `docs/design/sistema-de-diseno-zascarr.md`:

- Tarjetas que enlazan suben 3–4 px y usan `shadow-ink` al pasar; portada 2:3,
  título en una línea.
- La portada que falta la dibuja `ui.portada`; no se añade `onerror` ni imagen
  externa.
- Un enlace de tarjeta no debe anidar otro enlace; si la tarjeta entera es el
  enlace, el contenido secundario no se hace interactivo dentro.
- Objetivos táctiles ≥40 px; foco visible; el nombre accesible debe incluir la
  serie/número, no solo «Ver».
- Chips de colección con `ui.chip`; no inventar colores.
- No crear un botón principal nuevo: la navegación es enlace, no acción de
  efecto.

Decisiones:

1. **Colección → serie:** en la vista de tarjetas, un único `<a>` envolvente con
   la portada y el nombre; el botón «Quitar de la colección» queda fuera del
   enlace. En la vista de lista, el nombre y el botón de previa ya funcionan;
   se añade portada clicable en una miniatura cuando exista, sin duplicar el
   enlace.
2. **Serie → issue:** los chips de número ya son enlaces; se conserva. No se
   convierte la previa flotante en un enlace anidado.
3. **Issue → colecciones:** se añade un bloque de solo lectura con chips que
   enlazan a cada colección y una frase que aclara que la pertenencia es por la
   serie.
4. **Sin migración ni nueva entidad:** `collection_series` ya soporta la
   relación; el issue hereda las colecciones de su serie.

## 4. Criterios de aceptación

- [ ] En `/ui/colecciones/{id}?vista=tarjetas`, la portada y el nombre de cada
      serie abren `/ui/series/{id}` con un solo clic/toque.
- [ ] En `/ui/colecciones`, la portada de la colección abre su detalle.
- [ ] En `/ui/series/{id}`, el panel de colecciones sigue enlazando a cada
      colección.
- [ ] En `/ui/series/{id}/numero/{numero}`, se ven las colecciones de la serie
      con enlace, o un vacío explícito.
- [ ] Teclado: cada enlace tiene foco visible y nombre accesible; no hay enlaces
      anidados.
- [ ] Tests de plantilla/ruta y contraste; sin cambios de esquema.
