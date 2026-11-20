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


## Auditoría de cierre del incremento actual (2026-11-20)

Base frente a `origin/main`: `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9`.
Cabeza inspeccionada: `3cfa7117`.

El diff vigente **sí modifica runtime**, además de altas de pruebas/documentación:

- `src/zascarr/web/templates/estado.html`: bloque informativo con botón
  `disabled`, sin formulario, `hx-*`, `onclick` ni acción.
- Cuatro módulos nuevos en `src/zascarr/services/` (transporte, protocolo de
  petición, preparación de solicitud y lectura de estado). No están importados
  por `main.py`, routers web/API ni el auxiliar; el propio servicio de solicitud
  solo importa el constructor de protocolo. Las pruebas estáticas de
  aislamiento lo comprueban.

No hay cambios en `scripts/**`, `deploy/systemd/**`, `Dockerfile`,
`docker-compose.yml`, el auxiliar `zascarr_ops.py` ni el instalador. La acción
`actualizar` continúa rechazada y no existe unidad de actualización. En
consecuencia, este incremento **no puede ejecutar la actualización desde la UI**
y la mantiene deshabilitada.

Evidencia de esta cabeza: suite completa **8864 passed, 2431 skipped, 0 failed,
7 warnings**; 670 pruebas OPS4/paridad; Ruff limpio en módulos aislados, tests
OPS4 y arnés de restauración. El caso PostgreSQL real con Docker quedó omitido
sin opt-in. Persisten M3 (concordancia efectiva de seguridad app/host), la
reserva global, el cerrojo, la unidad endurecida, la integración UI/auxiliar y
la revisión SecOps del SHA final. Esta auditoría no fusiona, habilita ni
despliega nada.
