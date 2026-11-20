# OPS4: auditoría de integración del incremento aislado (#443)

> **Histórica:** esta auditoría se refiere exclusivamente al SHA indicado abajo.
> La rama ha incorporado después una modificación de plantilla para mostrar un
> botón deshabilitado; la afirmación de que no cambia `src` ya no describe el
> diff actual. La función de actualización sigue sin estar conectada.

- **Base:** `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9` (merge-base con `main`).
- **Cabeza auditada:** `a9dc9d7f`.
- **Método:** `git diff --name-status origin/main...HEAD` y búsqueda de rutas de
  ejecución.

## Resultado

El incremento contiene **solo altas** de documentación, pruebas, arneses y
módulos experimentales. No hay ficheros modificados ni eliminados y **no hay
cambios** en:

- `src/zascarr/**`
- `scripts/**`
- `docker-compose.yml`, `Dockerfile` ni entrypoint
- `deploy/systemd/**`

Por tanto, este incremento **no puede activar la actualización desde la UI** por
sí solo. Los módulos experimentales no se importan desde la aplicación ni el
auxiliar (comprobado por `test_ops4_aislamiento.py`).

## Evidencia

- 275 pruebas OPS4 y Ruff: PASS.
- Suite completa: 8.273 passed, 2.429 skipped.
- Host sin privilegios, sandbox bubblewrap, socket real y systemd transitorio:
  documentados en `verificacion-OPS4-host-2026-11-20.md`.
- La acción `actualizar` sigue rechazada y no existe unidad de actualización.

## Límite

La auditoría prueba que el **diff** no toca runtime; no aprueba el diseño del
futuro ejecutor, la persistencia durable, la fusión ni el despliegue. La PR
#1159 permanece en borrador.
