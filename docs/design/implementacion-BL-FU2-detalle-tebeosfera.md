# Implementación BL-FU2 — PR-1: detalle de edición de Tebeosfera (#465)

> Base: `main` `6f54968` (benchmark fusionado). **No implementa** Discovery ni el banco;
> tampoco CV/GCD ni ninguna escritura de modelo. Es la primera entrega del corte de la
> [spec](../design/especificacion-BL-FU2-detalle-edicion.md) (PR abierto #470).

## Qué entra

- `TebeosferaClient.get_collection(slug)` pide **una** ficha `/colecciones/{slug}.html` por
  `pedir_con_cortesia` (2,5 s compartidos, redirecciones de #134), sin galería de portadas.
- `TebeosferaColeccion` y `parse_collection`: parser tolerante de editorial/sello, país, fechas,
  numeración, formato, paginación y ficha; lo que no encuentra queda `None`.
- `services/detalle_edicion.py`: `DetalleEdicion` y `ResultadoDetalle` in-memory con
  `campos_ausentes` por campo, `CAPACIDAD_DETALLE` (#133) y estados de fuente.
- `contrastar(detalle, etiqueta, unidad=...)`: reglas de la spec (editorial exacta, año exacto,
  número si la etiqueta lo trae, país/idioma discrepantes, formato discrepante → ambiguo,
  etiqueta no acreditada → sin veredicto).
- **No** se escribe en `Series`/`Issue`; no hay ruta UI nueva, migración ni fuente nueva.

## Verificación

- `tests/test_detalle_edicion.py`: parser, ficha sin entidad, saga, ausencias, 404, estados,
  cortesía (dos fichas separadas ≥2,5 s) y contraste (verificado/ambiguo/incorrecto/no acreditada).
- Fixtures saneadas en `tests/fixtures/`; sin red ni claves.
- **NOT RUN:** la generalización a más fichas y la cobertura real; PR-2 (Discovery/GCD/banco) y
  PR-3 (Comic Vine con clave) no están en esta entrega.

## Límites

`numero_publicacion` queda ausente en una ficha de colección: el rango 1–153 no acredita el
ejemplar 15. Por eso ES-018/ES-019 son `ambiguo` hasta que exista un método de número verificado.
