# Decisión OCTA-E5 — portadas de Tebeosfera

- **Estado:** aceptada por el PO (2026-11-17).
- **Historia:** [#952](https://github.com/juanajok/zascarr/issues/952), épica OCTA-E [#918](https://github.com/juanajok/zascarr/issues/918).
- **Contexto:** Tebeosfera es una asociación cultural sin ánimo de lucro; sus fichas se leen
  raspando con cortesía (2,5 s) y sus portadas no son un dato factual.

## Decisión

1. **No se descargan portadas nuevas de Tebeosfera.** Se retira `tebeosfera.com` de las listas
   de hosts de portada (`web/discovery.py` y `utils/url_portada.py`).
2. **Los metadatos de Tebeosfera siguen disponibles** si el usuario activa la fuente, con su
   ritmo y atribución; lo que se retira es la imagen.
3. La UI muestra el **marcador `ui.portada`** y enlaza a la ficha externa; no hay hotlinking.
4. Las portadas ya cacheadas **en local** no se borran: son uso privado del operador. No se
   vuelven a descargar ni se incorporan a capturas públicas nuevas (E2/E6).

## Verificación

- `tests/test_cover_ssrf.py`: una URL de Tebeosfera ya no pasa la lista de portadas.
- `tests/test_web_discovery.py`: un resultado de Tebeosfera con `cover_url` se pinta con marcador
  y no con `<img>`.
- Las pruebas de descubrimiento/metadatos de Tebeosfera siguen pasando.
