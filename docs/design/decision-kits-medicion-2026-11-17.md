# Decisión OCTA-A6 — kits de medición y `alembic/versions/__init__.py`

- **Estado:** aceptada por el PO (2026-11-17).
- **Historia:** [#925](https://github.com/juanajok/zascarr/issues/925), épica OCTA-A [#914](https://github.com/juanajok/zascarr/issues/914).

## Inventario revisado

| Qué | Tamaño | Decisión |
|---|---:|---|
| `scripts/medicion/evaluacion_rar/` | 70 ficheros, 0,8 MiB | **Archivar documentación y retirar el código**; era un kit histórico del lector RAR, usaba `unrar` non-free solo para comparar y no es código de producción ni se ejecuta en CI. Se conserva el modo de uso y los resultados en `docs/design/mediciones/evaluacion-rar-archivada.md`. |
| `scripts/medicion/evaluacion_cnv/` y censos | pequeño | **Mantener**: documenta la medición de conversión CBR→CBZ y no introduce dependencias de ejecución. |
| `alembic/versions/__init__.py` | 0 bytes | **Borrar**: el directorio de migraciones no se importa como paquete; Alembic carga los scripts por ruta. |

## Por qué

- El kit RAR no se usa en la app, la imagen ni las pruebas; mantenerlo en `scripts/` sugería
  que era una herramienta viva. Se archiva la evidencia, no el ejecutable.
- `unrar` es non-free; aunque solo se usaba en un contenedor desechable de comparación, evitar
  conservarlo como kit “listo para usar” reduce el riesgo de que alguien lo trate como parte del
  producto.
- El `__init__.py` vacío no aporta nada y puede confundir sobre si `alembic/versions` es un
  paquete Python.

## Verificación

- `alembic heads` sigue funcionando sin el `__init__.py`.
- `test_migraciones_cadena` y la suite completa en `main`.
- No se toca la imagen ni ningún fichero de la biblioteca.
