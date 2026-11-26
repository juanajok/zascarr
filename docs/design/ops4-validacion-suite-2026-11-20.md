# OPS4 — validación completa del worktree (2026-11-20)

Código de producto validado: `b9f5a612`; las correcciones posteriores son
solo de tests (arnés de restauración). Directorio de trabajo explícito:
`.worktrees/ops4-443`. No se atribuyen a este SHA los recuentos históricos de
8.045 pruebas superadas comunicados anteriormente.

## Ejecución completa

```sh
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python \
  -m pytest -q --basetemp=/var/tmp/zascarr-ops4-suite-r67
```

Se comprobaron los dispositivos: `/var/tmp` y `/` están en el mismo
filesystem; `/tmp` no. El primer intento dentro del sandbox no pudo crear el
directorio (`EROFS`): **8.655 errores de preparación y 2.427 omitidas**. No
acredita ejecución de los casos ni una regresión del código. Se repitió la
misma orden mediante la ampliación de permiso aprobada para escribir allí.

Resultado del segundo intento (antes de corregir el arnés): **2 failed,
8651 passed, 2429 skipped, 7 warnings**, código de salida 1, 502,99 segundos.
La repetición tras las correcciones de tests, con temporales nuevos, terminó
en **8950 passed, 2454 skipped, 7 warnings**, código de salida 0, 483,37
segundos. **La suite completa está verde en el árbol de trabajo actual.** Los
avisos son de ZIP duplicado en un test y de AsyncMock no esperado en pruebas
del importador; no se han corregido y no son fallos.

La ejecución pudo acceder al Docker local. La prueba de restauración usa su
propio proyecto Compose temporal y llama a `down -v --remove-orphans` en su
`finally`; esa rutina no comprueba el código de limpieza y aquí no se ha
verificado por separado el inventario final de Docker. No usa datos de
producción ni la Pi. El fallo de su opt-in descrito abajo debe corregirse antes
de repetir una suite que no solicite expresamente integración Docker.

## Fallos inspeccionados

### Ruta temporal confundida con una BD

[TestRestoreScript.test_restaura_y_comprueba_recuentos](../../tests/test_restore_script.py#L250-L271)
busca ausencia de la subcadena `zascarr` en el registro completo del Docker
falso, salvo el prefijo temporal `zascarr_restore_`. La ruta elegida para
`--basetemp` contiene `zascarr-ops4-suite-r66`, por lo que dispara la aserción
sin demostrar uso de la BD de producción.

La corrección debía distinguir rutas de archivos de argumentos de BD sin
suprimir la guardia que rechaza nombres de producción, y conservar una
regresión con `zascarr` en el nombre de la carpeta. **Corregido en el arnés**
(no en el script operativo): ver abajo.

### PostgreSQL aún no disponible y opt-in sobrescrito

[test_la_seguridad_vigente_hostil_vuelve_byte_a_byte](../../tests/test_restaurar_produccion_pg.py#L274-L293)
falló al crear su esquema: el socket PostgreSQL no estaba disponible.
[esperar_postgres](../../tests/test_restaurar_produccion_pg.py#L115-L127)
usa `pg_isready` sobre el socket Unix, que puede dar listo durante el servidor
temporal de inicialización de la imagen oficial, antes del arranque final.
La causa es consistente con esa ventana; no se ha capturado un trazado completo
del contenedor que descarte toda otra causa. La espera debería acreditar el
servidor final (p. ej., TCP local dentro del contenedor y consulta real).

Además, el mismo módulo asignaba `pytestmark` varias veces:
[marcas de selección](../../tests/test_restaurar_produccion_pg.py#L33-L46).
La última asignación sustituía la condición `TEST_DATABASE_URL`/`ZASCARR_PG_IT`
y la de plataforma por disponibilidad de Docker. Por ello el test podía
arrancar Compose aun sin opt-in. **Corregido en el arnés**: ver abajo.

## Corrección del arnés (mismo 2026-11-20)

Cambios solo en tests:

- [test_restaurar_produccion_pg.py](../../tests/test_restaurar_produccion_pg.py):
  tres marcas combinadas en una lista; el sondeo de Docker usa cortocircuito y
  **no se invoca sin opt-in**. La espera exige `pg_isready` por TCP local
  dentro del contenedor **y** una consulta `SELECT 1` con contraseña de
  laboratorio, en vez de aceptar el socket Unix del `initdb` temporal.
- [test_restore_script.py](../../tests/test_restore_script.py): la guardia
  sustituye únicamente las rutas conocidas del compose y del `.env`; conserva
  la comprobación de nombres de BD/app de producción y se ejecuta con carpetas
  normales y con `zascarr` en la ruta. Un parámetro adicional demuestra que
  `createdb`, `dropdb`, `psql -d` y `stop` de producción siguen fallando.
- [test_ops4_pg_optin.py](../../tests/test_ops4_pg_optin.py): regresiones
  unitarias que cargan el arnés sin Docker, comprueban las tres condiciones y
  que la readiness no acepta el socket Unix.

Resultados de las pruebas dirigidas: **90 passed, 2 skipped** al ejecutar
`test_restore_script.py`, `test_restaurar_produccion_pg.py` (omitido sin
opt-in) y `test_ops4_pg_optin.py`; Ruff limpio en esos ficheros. La selección
OPS4/paridad pasó a **391 pruebas superadas**.

La suite completa **se repitió después de esta corrección**: 8880 passed,
2431 skipped, 0 failed. Los dos fallos históricos quedan cerrados a nivel de
suite. El caso PostgreSQL real sigue omitido sin `TEST_DATABASE_URL` o
`ZASCARR_PG_IT`; esta ejecución no revalidó esa integración con Docker.

## Evidencia complementaria

- **391 pruebas seleccionadas de OPS4/paridad** superadas tras corregir el
  arnés. El código de producto no cambió en esta corrección.
- Ruff pasó sobre todos los módulos `deploy/ops`, tests OPS4, fixtures de VM y
  los cuatro servicios nuevos aislados de actualización.
- La [auditoría de concordancia de seguridad](ops4-concordancia-seguridad.md)
  deja M3 abierto: publicación antes del commit, rollback y diferencias entre
  SQL y proceso activo no quedan resueltas por leer correctamente un hash.
- No se ha fusionado, habilitado ni desplegado OPS4. La revisión final SecOps
  sigue pendiente. La suite global está verde, pero el caso PostgreSQL real con
  Docker sigue sin revalidarse en esta pasada ni acredita producción.


## Revisión posterior (2026-11-21)

Se añadieron dos pruebas de composición con el servicio real de
reautenticación. La primera pasada completa dio 8881 passed y 1 fallo de
temporización en `test_ensayo_f1bis_arnes` (umbral de 4 s y `pgrep -f` que se
autocoincidía). Se estabilizó el test comprobando la ausencia del KILL de
respaldo y procesos `sleep 61.37` exactos, sin subir el umbral para ocultar el
comportamiento. La repetición completa terminó en **8950 passed, 2454 skipped,
7 avisos, 0 failed**. Las **391 pruebas OPS4/instalador** y Ruff pasan.
