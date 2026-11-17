# Verificación OCTA-F1/F2 (2026-11-17)

- **Historias:** [#940](https://github.com/juanajok/zascarr/issues/940) y
  [#941](https://github.com/juanajok/zascarr/issues/941), épica OCTA-F [#919](https://github.com/juanajok/zascarr/issues/919).
- **Base:** `main` `451b4a10` (2026-11-17). Solo lectura; no se cambió código.
- **Método:** búsqueda en el árbol y lectura de los ficheros citados. Lo que no se localiza se
  marca **descartado**, no «confirmado por no encontrarlo».

## F1 — accesibilidad, includes y lecturas de pruebas

| Afirmación | Resultado | Evidencia |
|---|---|---|
| ARIA fija en el importador de guías | **Descartada / no localizada**. No hay plantilla de «importar guía» con ARIA fija; el único `aria-label` de esa zona es la paginación de arcos, que es correcta. | `src/zascarr/web/templates/arcos.html:23`; no existe `importar_guia.html` |
| `include` dinámico | **Confirmado, pero controlado**. `{% include plantilla %}` aparece en dos plantillas; `plantilla` la devuelve `preparar_vista_previa`/`_pagina_alta` desde un conjunto fijo (`_alta_vista_previa.html`, `_alta_error.html`, formulario). No es una cadena del usuario. | `_asistente_eleccion.html:13`, `asistente_alta.html:18`; `web/discovery.py:292`; `web/asistente_carpetas.py:309` |
| Filtro `safe` sobre `LEGAL.md` | **Confirmado, sin riesgo nuevo**. `legal_full.html` usa `| safe` sobre `markdown.markdown` de `LEGAL.md`, un fichero empaquetado con la app, no de una petición. Es el contrato de la página legal. | `legal_full.html:5`; `services/legal.py:32,49` |
| Lecturas de fichero sin codificación en pruebas | **Parcialmente confirmado y solo en tests**. Hay `read_text()` sin `encoding=` en pruebas de plantillas/CSS y en dobles de RAR; no afecta a producción y no es una regresión funcional. | `tests/test_web_progreso_lectura.py:7-9`; `tests/_rar_falso.py:99-116` |

## F2 — motor SQL, documentos y licencia htmx

| Afirmación | Resultado | Evidencia |
|---|---|---|
| Motor SQL creado al importar y sin `dispose` en la CLI | **Descartada en el estado actual**. El motor se crea en `database.py`, pero las tres CLI que lo usan lo cierran con `await engine.dispose()` en su `finally`. | `database.py:16`; `cli/etiquetar.py:174`, `cli/rellenar_formato.py:85`, `cli/seguridad.py:160` |
| «Documentos a medias y la rama version 1.1» | **Descartada / no accionable**: no se identifica documento ni rama `version 1.1` vigente; las coincidencias son versiones de herramientas o textos históricos. | búsqueda `version 1.1`/`v1.1` en `docs/` |
| Aviso de licencia de htmx | **Ya documentado**: el README de `static/vendor` indica versión 4.0.0, origen, URL y licencia **BSD 2-Clause**. | `src/zascarr/static/vendor/README.md:7-13` |

## Conclusión

- No hay un fallo de accesibilidad o seguridad nuevo que corregir por F1/F2 en el estado actual.
- Sí queda una **deuda menor de estilo en tests** (`read_text()` sin `encoding=`), que no se toca
  aquí para no mezclar una verificación con un cambio de pruebas.
- Las afirmaciones que OCTA daba por hechas sobre htmx/CLI ya están resueltas; las de ARIA y
  «versión 1.1» no se sostienen con el árbol actual.

**NOT RUN:** no se ha ejecutado un lector de pantalla real ni una prueba de accesibilidad con
herramientas externas; F1 es una revisión estática de las afirmaciones citadas.
